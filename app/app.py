"""DevTrails: a topic-based tech blog learning platform, instrumented for Prometheus.

Endpoints required by the assessment:
  GET  /health        liveness + database check
  POST /api/orders    enroll in a topic track (the business event)
  GET  /metrics       Prometheus exposition
"""

import json
import logging
import os
import random
import re
import sqlite3
import sys
import threading
import time
from contextlib import closing

from flask import Flask, Response, abort, g, jsonify, render_template, request
from markupsafe import Markup, escape
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
)

from catalog import AUTHOR, PLANS, POSTS_BY_SLUG, TOPICS, TOPICS_BY_SLUG, all_posts

APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
DB_PATH = os.getenv("DB_PATH", "/data/devtrails.db")
GRAFANA_URL = os.getenv("PUBLIC_GRAFANA_URL", "http://127.0.0.1:3000")
CHAOS_TOKEN = os.getenv("CHAOS_TOKEN", "")
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}$")

# ---------------------------------------------------------------- logging
class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + "Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        payload.update(getattr(record, "extra_fields", {}))
        return json.dumps(payload)


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
log = logging.getLogger("devtrails")
log.addHandler(handler)
log.setLevel(logging.INFO)
log.propagate = False


def log_event(level, msg, **fields):
    log.log(level, msg, extra={"extra_fields": fields})


# ---------------------------------------------------------------- metrics
# Label values are bounded: route is the Flask URL rule (template), never the raw path.
HTTP_REQUESTS = Counter(
    "devtrails_http_requests_total",
    "Total HTTP requests handled, by method, route template and status code.",
    ["method", "route", "status"],
)
HTTP_LATENCY = Histogram(
    "devtrails_http_request_duration_seconds",
    "HTTP request latency in seconds, by method and route template.",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
HTTP_IN_PROGRESS = Gauge(
    "devtrails_http_requests_in_progress", "HTTP requests currently being served."
)
ORDERS = Counter(
    "devtrails_orders_total",
    "Enrollment orders by topic, plan and result (success|failed|rejected).",
    ["topic", "plan", "result"],
)
REVENUE = Counter(
    "devtrails_order_revenue_dollars_total",
    "Revenue from successful enrollment orders, in US dollars.",
    ["plan"],
)
POST_VIEWS = Counter(
    "devtrails_post_views_total", "Blog post reads (page or API), by topic.", ["topic"]
)
CHAOS_RATIO = Gauge(
    "devtrails_chaos_error_ratio",
    "Configured fraction (0-1) of API requests deliberately failed by chaos mode.",
)
APP_INFO = Info("devtrails_app", "DevTrails build information.")
APP_INFO.info({"version": APP_VERSION})

# Initialise label combinations so series exist (as 0) before first traffic.
for _t in TOPICS:
    POST_VIEWS.labels(_t["slug"])
    for _p in PLANS:
        for _r in ("success", "failed"):
            ORDERS.labels(_t["slug"], _p, _r)
ORDERS.labels("invalid", "invalid", "rejected")

# ---------------------------------------------------------------- chaos mode
_chaos_lock = threading.Lock()
_chaos = {"error_rate": 0.0, "latency_ms": 0, "until": 0.0}


def chaos_state():
    with _chaos_lock:
        if _chaos["until"] and time.time() > _chaos["until"]:
            _chaos.update(error_rate=0.0, latency_ms=0, until=0.0)
            CHAOS_RATIO.set(0)
        return dict(_chaos)


# ---------------------------------------------------------------- database
def db():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with closing(db()) as conn, conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL, plan TEXT NOT NULL, email TEXT NOT NULL,
                amount INTEGER NOT NULL, created_at REAL NOT NULL)"""
        )


def mask_email(email):
    user, _, domain = email.partition("@")
    return f"{user[:1]}***@{domain}"


# ---------------------------------------------------------------- app
app = Flask(__name__)
init_db()


_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")


@app.template_filter("md")
def inline_markdown(text):
    """Tiny, safe inline formatter: escape first, then `code` and **bold**."""
    html = str(escape(text))
    html = _CODE_RE.sub(r"<code>\1</code>", html)
    html = _BOLD_RE.sub(r"<strong>\1</strong>", html)
    return Markup(html)


@app.template_filter("datefmt")
def datefmt(iso):
    return time.strftime("%b %d, %Y", time.strptime(iso, "%Y-%m-%d")).replace(" 0", " ")


@app.context_processor
def inject_globals():
    return {"topics": TOPICS, "topics_by_slug": TOPICS_BY_SLUG, "author": AUTHOR,
            "grafana_url": GRAFANA_URL, "version": APP_VERSION}


@app.before_request
def start_timer():
    g.start = time.perf_counter()
    if request.path != "/metrics":
        HTTP_IN_PROGRESS.inc()
        g.tracked = True


@app.after_request
def record_metrics(response):
    if getattr(g, "tracked", False):
        route = request.url_rule.rule if request.url_rule else "unmatched"
        elapsed = time.perf_counter() - g.start
        HTTP_REQUESTS.labels(request.method, route, str(response.status_code)).inc()
        HTTP_LATENCY.labels(request.method, route).observe(elapsed)
        if not route.startswith("/static"):
            log_event(
                logging.WARNING if response.status_code >= 500 else logging.INFO,
                "request",
                method=request.method,
                route=route,
                status=response.status_code,
                duration_ms=round(elapsed * 1000, 2),
            )
    return response


@app.teardown_request
def end_in_progress(_exc):
    if getattr(g, "tracked", False):
        HTTP_IN_PROGRESS.dec()
        g.tracked = False


def maybe_inject_chaos():
    """Deliberately fail or slow /api/* requests while chaos mode is enabled."""
    state = chaos_state()
    if state["latency_ms"]:
        time.sleep(state["latency_ms"] / 1000 * random.uniform(0.5, 1.5))
    if state["error_rate"] and random.random() < state["error_rate"]:
        log_event(logging.ERROR, "chaos: injected failure", path=request.path)
        return jsonify(error="chaos mode: injected upstream failure"), 503
    return None


# ------------------------------------------------------------------ pages
@app.get("/")
def home():
    posts = all_posts()
    with closing(db()) as conn:
        enrollments = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    stats = {
        "topics": len(TOPICS),
        "posts": len(posts),
        "minutes": sum(p["minutes"] for p in posts),
        "enrollments": enrollments,
    }
    return render_template("home.html", featured=posts[0], side=posts[1:4], latest=posts[4:10], stats=stats)


@app.get("/blog")
def blog_index():
    return render_template("blog.html", posts=all_posts())


@app.get("/topics/<slug>")
def topic_page(slug):
    topic = TOPICS_BY_SLUG.get(slug) or abort(404)
    return render_template("topic.html", topic=topic)


@app.get("/blog/<slug>")
def post_page(slug):
    post = POSTS_BY_SLUG.get(slug) or abort(404)
    topic = TOPICS_BY_SLUG[post["topic"]]
    POST_VIEWS.labels(topic["slug"]).inc()
    i = post["part"] - 1
    prev_post = topic["posts"][i - 1] if i > 0 else None
    next_post = topic["posts"][i + 1] if i + 1 < len(topic["posts"]) else None
    related = [p for p in all_posts() if p["topic"] != topic["slug"]][:3]
    return render_template("post.html", post=post, topic=topic, prev_post=prev_post,
                           next_post=next_post, related=related)


@app.get("/enroll")
def enroll_page():
    return render_template("enroll.html", plans=PLANS, selected=request.args.get("topic", ""))


@app.get("/platform")
def platform_page():
    return render_template("platform.html")


@app.errorhandler(404)
def not_found(_e):
    if request.path.startswith("/api/"):
        return jsonify(error="not found"), 404
    return render_template("404.html"), 404


# -------------------------------------------------------------------- api
@app.get("/health")
def health():
    try:
        with closing(db()) as conn:
            conn.execute("SELECT 1")
        return jsonify(status="ok", version=APP_VERSION, chaos=chaos_state()["error_rate"] > 0)
    except sqlite3.Error as exc:
        log_event(logging.ERROR, "health check failed", error=str(exc))
        return jsonify(status="degraded", error="database unavailable"), 503


@app.get("/api/topics")
def api_topics():
    if (resp := maybe_inject_chaos()) is not None:
        return resp
    return jsonify([
        {"slug": t["slug"], "name": t["name"], "posts": len(t["posts"]), "tagline": t["tagline"]}
        for t in TOPICS
    ])


@app.get("/api/topics/<slug>")
def api_topic(slug):
    if (resp := maybe_inject_chaos()) is not None:
        return resp
    topic = TOPICS_BY_SLUG.get(slug) or abort(404)
    return jsonify({**{k: v for k, v in topic.items() if k != "posts"},
                    "posts": [{"slug": p["slug"], "title": p["title"], "minutes": p["minutes"]} for p in topic["posts"]]})


@app.get("/api/posts/<slug>")
def api_post(slug):
    if (resp := maybe_inject_chaos()) is not None:
        return resp
    post = POSTS_BY_SLUG.get(slug) or abort(404)
    POST_VIEWS.labels(post["topic"]).inc()
    return jsonify(post)


@app.post("/api/orders")
def create_order():
    if (resp := maybe_inject_chaos()) is not None:
        data = request.get_json(silent=True) or {}
        t, p = data.get("topic"), data.get("plan")
        if t in TOPICS_BY_SLUG and p in PLANS:
            ORDERS.labels(t, p, "failed").inc()
        return resp

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        ORDERS.labels("invalid", "invalid", "rejected").inc()
        return jsonify(error="request body must be a JSON object"), 400

    topic, plan, email = data.get("topic"), data.get("plan", "free"), str(data.get("email", ""))
    errors = []
    if topic not in TOPICS_BY_SLUG:
        errors.append(f"unknown topic; choose one of {sorted(TOPICS_BY_SLUG)}")
    if plan not in PLANS:
        errors.append(f"unknown plan; choose one of {sorted(PLANS)}")
    if not EMAIL_RE.match(email):
        errors.append("a valid email is required")
    if errors:
        ORDERS.labels("invalid", "invalid", "rejected").inc()
        log_event(logging.WARNING, "order rejected", errors=errors)
        return jsonify(error="validation failed", details=errors), 400

    # Paid plans call a (simulated) payment provider: adds realistic latency.
    if PLANS[plan]["price"]:
        time.sleep(random.uniform(0.02, 0.15))
    if data.get("simulate_failure") or request.headers.get("X-Simulate-Failure") == "1":
        ORDERS.labels(topic, plan, "failed").inc()
        log_event(logging.ERROR, "order failed: payment provider timeout", topic=topic, plan=plan)
        return jsonify(error="payment provider unavailable, please retry"), 500

    amount = PLANS[plan]["price"]
    with closing(db()) as conn, conn:
        cur = conn.execute(
            "INSERT INTO orders (topic, plan, email, amount, created_at) VALUES (?,?,?,?,?)",
            (topic, plan, email, amount, time.time()),
        )
        order_id = cur.lastrowid
    ORDERS.labels(topic, plan, "success").inc()
    REVENUE.labels(plan).inc(amount)
    log_event(logging.INFO, "order created", order_id=order_id, topic=topic, plan=plan, amount=amount)
    return jsonify(id=order_id, topic=topic, plan=plan, amount=amount, status="confirmed"), 201


@app.get("/api/orders")
def list_orders():
    with closing(db()) as conn:
        rows = conn.execute(
            "SELECT id, topic, plan, email, amount, created_at FROM orders ORDER BY id DESC LIMIT 20"
        ).fetchall()
    return jsonify([{**dict(r), "email": mask_email(r["email"])} for r in rows])


@app.route("/api/admin/chaos", methods=["GET", "POST", "DELETE"])
def chaos():
    """Controlled-failure switch used by scripts/traffic-test.sh for the alert demo."""
    if CHAOS_TOKEN and request.headers.get("X-Chaos-Token") != CHAOS_TOKEN:
        return jsonify(error="forbidden"), 403
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        try:
            rate = min(max(float(data.get("error_rate", 0.5)), 0.0), 1.0)
            latency = min(max(int(data.get("latency_ms", 0)), 0), 3000)
            duration = min(max(int(data.get("duration_s", 300)), 10), 3600)
        except (TypeError, ValueError):
            return jsonify(error="invalid chaos parameters"), 400
        with _chaos_lock:
            _chaos.update(error_rate=rate, latency_ms=latency, until=time.time() + duration)
        CHAOS_RATIO.set(rate)
        log_event(logging.WARNING, "chaos mode enabled", error_rate=rate, latency_ms=latency, duration_s=duration)
    elif request.method == "DELETE":
        with _chaos_lock:
            _chaos.update(error_rate=0.0, latency_ms=0, until=0.0)
        CHAOS_RATIO.set(0)
        log_event(logging.INFO, "chaos mode disabled")
    state = chaos_state()
    state["seconds_left"] = max(0, int(state.pop("until") - time.time())) if state["until"] else 0
    return jsonify(state)


@app.get("/metrics")
def metrics():
    chaos_state()  # expire chaos window so the gauge stays accurate
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
