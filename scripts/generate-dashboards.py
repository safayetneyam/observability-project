#!/usr/bin/env python3
"""Generate the Grafana dashboard JSON files in grafana/dashboards/.

The JSON files are committed. This script just keeps them consistent and reviewable:
    python3 scripts/generate-dashboards.py
"""
import json
import pathlib

OUT = pathlib.Path(__file__).resolve().parent.parent / "grafana" / "dashboards"
PROM = {"type": "prometheus", "uid": "prometheus"}
LOKI = {"type": "loki", "uid": "loki"}
RATE = "$__rate_interval"
APP = 'devtrails_http_requests_total{route!~"/static.*"}'

_id = 0


def nid():
    global _id
    _id += 1
    return _id


def target(expr, legend="", ref="A", ds=PROM, instant=False):
    t = {"datasource": ds, "expr": expr, "legendFormat": legend, "refId": ref}
    if instant:
        t["instant"] = True
    return t


def row(title, y):
    return {"type": "row", "id": nid(), "title": title, "collapsed": False,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "panels": []}


def stat(title, exprs, unit, x, y, w=4, h=4, thresholds=None, desc="", decimals=None, color_mode="background"):
    steps = thresholds or [{"color": "green", "value": None}]
    p = {
        "type": "stat", "id": nid(), "title": title, "description": desc, "datasource": PROM,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "targets": [target(e, l, chr(65 + i)) for i, (e, l) in enumerate(exprs)],
        "fieldConfig": {"defaults": {"unit": unit, "thresholds": {"mode": "absolute", "steps": steps},
                                     "color": {"mode": "thresholds"}}, "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                    "colorMode": color_mode, "graphMode": "area", "textMode": "auto", "justifyMode": "center"},
    }
    if decimals is not None:
        p["fieldConfig"]["defaults"]["decimals"] = decimals
    return p


def ts(title, exprs, unit, x, y, w=12, h=8, desc="", stack=False, overrides=None, min0=True, ds=PROM, fill=12):
    p = {
        "type": "timeseries", "id": nid(), "title": title, "description": desc, "datasource": ds,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "targets": [target(e, l, chr(65 + i), ds) for i, (e, l) in enumerate(exprs)],
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "color": {"mode": "palette-classic"},
                "custom": {"drawStyle": "line", "lineWidth": 2, "fillOpacity": fill, "gradientMode": "opacity",
                           "showPoints": "never", "spanNulls": True,
                           "stacking": {"mode": "normal" if stack else "none", "group": "A"}},
            },
            "overrides": overrides or [],
        },
        "options": {"legend": {"displayMode": "table", "placement": "bottom", "calcs": ["mean", "max", "lastNotNull"]},
                    "tooltip": {"mode": "multi", "sort": "desc"}},
    }
    if min0:
        p["fieldConfig"]["defaults"]["min"] = 0
    return p


def gauge(title, expr, x, y, w=4, h=6, desc=""):
    return {
        "type": "gauge", "id": nid(), "title": title, "description": desc, "datasource": PROM,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "targets": [target(expr, "", "A")],
        "fieldConfig": {"defaults": {"unit": "percent", "min": 0, "max": 100, "decimals": 1,
                                     "thresholds": {"mode": "absolute", "steps": [
                                         {"color": "green", "value": None}, {"color": "#EAB839", "value": 70},
                                         {"color": "red", "value": 90}]}}, "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                    "showThresholdLabels": False, "showThresholdMarkers": True},
    }


def dashboard(uid, title, panels, tags, templating=None, refresh="15s", time_from="now-1h", desc=""):
    return {
        "uid": uid, "title": title, "description": desc, "tags": tags, "timezone": "browser",
        "editable": True, "graphTooltip": 1, "refresh": refresh, "schemaVersion": 39, "version": 1,
        "time": {"from": time_from, "to": "now"},
        "templating": {"list": templating or []},
        "annotations": {"list": [{"builtIn": 1, "datasource": {"type": "grafana", "uid": "-- Grafana --"},
                                  "enable": True, "hide": True, "iconColor": "rgba(0, 211, 255, 1)",
                                  "name": "Annotations & Alerts", "type": "dashboard"}]},
        "links": [{"title": "Kubernetes logs", "type": "link", "url": "/d/devtrails-k8s-logs", "icon": "doc"},
                  {"title": "Overview", "type": "link", "url": "/d/devtrails-overview", "icon": "dashboard"}],
        "panels": panels,
    }


# --------------------------------------------------------------------------- overview
RED = [{"color": "green", "value": None}, {"color": "#EAB839", "value": 1}, {"color": "red", "value": 5}]
PCT = [{"color": "green", "value": None}, {"color": "#EAB839", "value": 70}, {"color": "red", "value": 90}]

CPU = f'100 * (1 - avg(rate(node_cpu_seconds_total{{mode="idle"}}[{RATE}])))'
RAM = "100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)"
DISK = ('100 * (1 - node_filesystem_avail_bytes{mountpoint="/",fstype!~"tmpfs|overlay|squashfs"}'
        ' / node_filesystem_size_bytes{mountpoint="/",fstype!~"tmpfs|overlay|squashfs"})')
ERR = (f'100 * (sum(rate({APP[:-1]},status=~"5.."}}[{RATE}])) or vector(0))'
       f' / clamp_min(sum(rate({APP}[{RATE}])), 0.001)')
P95 = f'histogram_quantile(0.95, sum by (le) (rate(devtrails_http_request_duration_seconds_bucket{{route!~"/static.*"}}[{RATE}])))'

y = 0
ov = [row("🖥  Ubuntu host (node_exporter)", y)]
y += 1
ov += [
    stat("Uptime", [("time() - node_boot_time_seconds", "")], "s", 0, y, desc="Seconds since host boot (compare with `uptime`).", color_mode="value"),
    stat("CPU busy", [(CPU, "")], "percent", 4, y, thresholds=PCT, decimals=1, desc="All cores, non-idle share."),
    stat("RAM used", [(RAM, "")], "percent", 8, y, thresholds=PCT, decimals=1, desc="1 - MemAvailable/MemTotal (compare with `free`)."),
    stat("Root disk used", [(DISK, "")], "percent", 12, y, thresholds=PCT, decimals=1, desc="Filesystem mounted at / (compare with `df -h /`)."),
    stat("CPU cores", [('count(count by (cpu) (node_cpu_seconds_total{mode="idle"}))', "")], "short", 16, y, color_mode="value"),
    stat("Total RAM", [("node_memory_MemTotal_bytes", "")], "bytes", 20, y, color_mode="value"),
]
y += 4
ov += [
    ts("CPU utilisation by mode", [(f'100 * sum by (mode) (rate(node_cpu_seconds_total{{mode!="idle"}}[{RATE}])) / scalar(count(count by (cpu) (node_cpu_seconds_total)))', "{{mode}}")],
       "percent", 0, y, w=8, stack=True, desc="Share of total CPU time per mode."),
    ts("Memory", [("node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes", "used"),
                  ("node_memory_MemAvailable_bytes", "available"),
                  ("node_memory_Cached_bytes + node_memory_Buffers_bytes", "buff/cache")],
       "bytes", 8, y, w=8),
    ts("Network throughput", [(f'sum by (device) (rate(node_network_receive_bytes_total[{RATE}]))', "rx {{device}}"),
                              (f'-sum by (device) (rate(node_network_transmit_bytes_total[{RATE}]))', "tx {{device}}")],
       "Bps", 16, y, w=8, min0=False, desc="Receive above zero, transmit below zero."),
]
y += 8
ov += [
    ts("Disk utilisation by mount", [('100 * (1 - node_filesystem_avail_bytes{fstype!~"tmpfs|overlay|squashfs|ramfs"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay|squashfs|ramfs"})', "{{mountpoint}}")],
       "percent", 0, y, w=8, fill=0),
    ts("Disk I/O", [(f'sum by (device) (rate(node_disk_read_bytes_total[{RATE}]))', "read {{device}}"),
                    (f'-sum by (device) (rate(node_disk_written_bytes_total[{RATE}]))', "write {{device}}")],
       "Bps", 8, y, w=8, min0=False),
    ts("Load average", [("node_load1", "1m"), ("node_load5", "5m"), ("node_load15", "15m")], "short", 16, y, w=8, fill=0),
]
y += 8
ov.append(row("🎓  DevTrails application", y))
y += 1
ov += [
    stat("Requests / sec", [(f"sum(rate({APP}[{RATE}]))", "")], "reqps", 0, y, decimals=2, color_mode="value"),
    stat("5xx error rate", [(ERR, "")], "percent", 4, y, thresholds=RED, decimals=2, desc="5xx responses / all responses."),
    stat("p95 latency", [(P95, "")], "s", 8, y, decimals=3,
         thresholds=[{"color": "green", "value": None}, {"color": "#EAB839", "value": 0.25}, {"color": "red", "value": 1}]),
    stat("Enrollments (range)", [('sum(increase(devtrails_orders_total{result="success"}[$__range]))', "")], "short", 12, y, decimals=0, color_mode="value",
         desc="Business event: successful POST /api/orders in the selected time range."),
    stat("Revenue (range)", [("sum(increase(devtrails_order_revenue_dollars_total[$__range]))", "")], "currencyUSD", 16, y, decimals=0, color_mode="value"),
    stat("Targets up", [('sum(up{job=~"devtrails-app|node-exporter"})', "")], "short", 20, y,
         thresholds=[{"color": "red", "value": None}, {"color": "#EAB839", "value": 1}, {"color": "green", "value": 2}],
         desc="Expected: 2 (node-exporter + devtrails-app)."),
]
y += 4
ov += [
    ts("Requests per second by route", [(f"sum by (method, route) (rate({APP}[{RATE}]))", "{{method}} {{route}}")], "reqps", 0, y, stack=True),
    ts("Responses by status code", [(f"sum by (status) (rate({APP}[{RATE}]))", "{{status}}")], "reqps", 12, y, stack=True,
       overrides=[{"matcher": {"id": "byRegexp", "options": "5.."}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}}]},
                  {"matcher": {"id": "byRegexp", "options": "4.."}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "orange"}}]},
                  {"matcher": {"id": "byRegexp", "options": "2.."}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "green"}}]}]),
]
y += 8
ov += [
    ts("Latency percentiles", [
        (f'histogram_quantile(0.50, sum by (le) (rate(devtrails_http_request_duration_seconds_bucket{{route!~"/static.*"}}[{RATE}])))', "p50"),
        (P95, "p95"),
        (f'histogram_quantile(0.99, sum by (le) (rate(devtrails_http_request_duration_seconds_bucket{{route!~"/static.*"}}[{RATE}])))', "p99")],
       "s", 0, y, fill=0),
    ts("Error rate by route (5xx %)", [(f'100 * sum by (route) (rate({APP[:-1]},status=~"5.."}}[{RATE}])) / on (route) group_left sum by (route) (rate({APP}[{RATE}]))', "{{route}}")],
       "percent", 12, y, fill=0, desc="Alert threshold: overall 5xx > 5% for 1m."),
]
y += 8
ov += [
    ts("Enrollment orders by result", [(f"sum by (result) (rate(devtrails_orders_total[{RATE}])) * 60", "{{result}}")], "short", 0, y, w=8, stack=True,
       desc="Orders per minute: success | failed (5xx) | rejected (400).",
       overrides=[{"matcher": {"id": "byName", "options": "failed"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}}]},
                  {"matcher": {"id": "byName", "options": "rejected"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "orange"}}]},
                  {"matcher": {"id": "byName", "options": "success"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "green"}}]}]),
    ts("Blog post reads per minute by topic", [(f"sum by (topic) (rate(devtrails_post_views_total[{RATE}])) * 60", "{{topic}}")], "short", 8, y, w=8, stack=True),
    ts("In-flight requests & chaos ratio", [("devtrails_http_requests_in_progress", "in-flight"), ("devtrails_chaos_error_ratio", "chaos error ratio")],
       "short", 16, y, w=8, fill=0),
]

overview = dashboard("devtrails-overview", "DevTrails · Host & Application Overview", ov, ["devtrails", "prometheus"],
                     desc="Ubuntu host metrics (node_exporter) and DevTrails HTTP/business metrics.")

# --------------------------------------------------------------------------- k8s logs
_id = 0
NS = '{namespace=~"$namespace", pod=~"$pod"}'
SEARCH = '|~ "(?i)$search"'
tpl = [
    {"name": "namespace", "label": "Namespace", "type": "query", "datasource": LOKI,
     "query": {"label": "namespace", "refId": "LokiVariableQueryEditor-VariableQuery", "stream": "", "type": 1},
     "definition": "label_values(namespace)", "refresh": 2, "current": {"text": "devtrails", "value": "devtrails"},
     "includeAll": True, "allValue": ".+", "multi": False, "sort": 1},
    {"name": "pod", "label": "Pod", "type": "query", "datasource": LOKI,
     "query": {"label": "pod", "refId": "LokiVariableQueryEditor-VariableQuery", "stream": '{namespace=~"$namespace"}', "type": 1},
     "definition": 'label_values({namespace=~"$namespace"}, pod)', "refresh": 2,
     "current": {"text": "All", "value": "$__all"}, "includeAll": True, "allValue": ".+", "multi": True, "sort": 1},
    {"name": "search", "label": "Search (regex)", "type": "textbox", "query": "", "current": {"text": "", "value": ""}},
]
lp = [
    ts("Log lines per minute by pod", [(f'sum by (pod) (count_over_time({NS} {SEARCH} [1m]))', "{{pod}}")], "short", 0, 0, w=12, h=7, ds=LOKI, stack=True),
    ts("stderr / ERROR lines per minute", [(f'sum by (pod) (count_over_time({{namespace=~"$namespace", pod=~"$pod", stream="stderr"}} [1m]))', "stderr {{pod}}"),
                                           (f'sum by (pod) (count_over_time({NS} |~ "\\"level\\": ?\\"(ERROR|CRITICAL)\\"" [1m]))', "ERROR {{pod}}")],
       "short", 12, 0, w=12, h=7, ds=LOKI,
       overrides=[{"matcher": {"id": "byRegexp", "options": "stderr.*"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}}]}]),
    {"type": "logs", "id": nid(), "title": "Pod logs: $namespace / $pod", "datasource": LOKI,
     "gridPos": {"h": 14, "w": 24, "x": 0, "y": 7},
     "targets": [{"datasource": LOKI, "expr": f"{NS} {SEARCH}", "refId": "A", "queryType": "range"}],
     "options": {"showTime": True, "showLabels": False, "showCommonLabels": False, "wrapLogMessage": True,
                 "prettifyLogMessage": False, "enableLogDetails": True, "dedupStrategy": "none", "sortOrder": "Descending"}},
    {"type": "logs", "id": nid(), "title": "Errors only (stderr stream)", "datasource": LOKI,
     "gridPos": {"h": 10, "w": 24, "x": 0, "y": 21},
     "targets": [{"datasource": LOKI, "expr": f'{{namespace=~"$namespace", pod=~"$pod", stream="stderr"}} {SEARCH}', "refId": "A", "queryType": "range"}],
     "options": {"showTime": True, "showLabels": True, "wrapLogMessage": True, "enableLogDetails": True,
                 "dedupStrategy": "none", "sortOrder": "Descending"}},
]
logs = dashboard("devtrails-k8s-logs", "DevTrails · MicroK8s Pod Logs (Loki)", lp, ["devtrails", "loki", "kubernetes"],
                 templating=tpl, refresh="10s", time_from="now-30m",
                 desc="Logs collected from MicroK8s pods by Grafana Alloy and stored in Loki.")

OUT.mkdir(parents=True, exist_ok=True)
for name, d in [("devtrails-overview.json", overview), ("devtrails-k8s-logs.json", logs)]:
    (OUT / name).write_text(json.dumps(d, indent=2) + "\n")
    print("wrote", OUT / name, f"({sum(1 for p in d['panels'] if p['type'] != 'row')} panels)")
