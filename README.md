# DevTrails: System & Application Observability

**DevTrails** is a topic-based tech-blog learning platform (Kubernetes, Docker, Linux, Observability,
CI/CD, AWS). Each topic is a trail of short, hands-on blog posts. This repository runs it with full observability:

| Flow | Path | Proof |
|---|---|---|
| **Live metrics** | Ubuntu host (Node Exporter) + DevTrails `/metrics` → **Prometheus** (15s) → **Grafana** | 25-panel dashboard, PromQL cross-checked against `free`, `df`, `uptime` |
| **Kubernetes logs** | MicroK8s pods (namespace `devtrails`) → **Grafana Alloy** (DaemonSet) → **Loki** → Grafana Explore / logs dashboard | `microk8s kubectl logs` matches the lines in Loki |
| **Email alerting** | Grafana alert rule (5xx > 5% for 1m, target down, CPU) → SMTP contact point → inbox | Rule history + received email |

All data is real: host metrics come from the actual machine, app metrics from real HTTP requests, and logs from live pods.

## Quick start (local)

> Full step-by-step instructions (setup, ingress note, EC2, demo, evidence, troubleshooting, cleanup):
> **[project-explore.md](project-explore.md)**

```bash
cd Observability
cp .env.example .env && chmod 600 .env          # set GRAFANA_ADMIN_PASSWORD (+ SMTP, see below)

# 1. Metrics + logging backend + app (add --profile mailpit for a local test inbox)
docker compose --profile mailpit up -d --build
docker compose ps

# 2. MicroK8s workloads + Grafana Alloy
./scripts/deploy-k8s.sh

# 3. Traffic, failures, alert
./scripts/traffic-test.sh demo                  # normal → burst → failures, before/after counters
./scripts/traffic-test.sh chaos 0.5 240         # fires the email alert in about 2 min

# 4. Evidence
./scripts/verify.sh                             # writes evidence/verification-*.txt
```

| Open | URL |
|---|---|
| DevTrails blog | http://127.0.0.1:8000 |
| Grafana | http://127.0.0.1:3000 (admin / your `.env` password) |
| Prometheus targets | http://127.0.0.1:9090/targets |
| Mailpit inbox | http://127.0.0.1:8025 |

For the Mailpit inbox, set these in `.env`: `SMTP_HOST=mailpit:1025`, `SMTP_USER=`, `SMTP_PASSWORD=`,
`SMTP_STARTTLS_POLICY=NoStartTLS`. For a real inbox, use Gmail or Mailtrap (see `.env.example`).

---

## Architecture

```
                         ┌──────────────── Ubuntu host (laptop / EC2) ─────────────────────────────┐
                         │                                                                          │
  Docker Compose         │   ┌──────────────┐  scrape 15s   ┌────────────┐  PromQL  ┌───────────┐   │
  network "observability"│   │ DevTrails app│◀──────────────│ Prometheus │◀─────────│  Grafana  │──SMTP──▶ inbox
  172.28.0.0/24          │   │ Flask :8000  │               │   :9090    │          │   :3000   │   │
                         │   └──────▲───────┘   ┌──────────▶└────────────┘   LogQL  └─────┬─────┘   │
                         │          │           │ scrape 172.28.0.1:9100     ┌──────────┐ │         │
                         │          │     ┌─────┴────────┐                  │   Loki   │◀┘         │
                         │          │     │ Node Exporter│ (host net + pid, │  :3100   │           │
                         │          │     │ /:/host:ro   │  read-only rootfs)└────▲─────┘           │
                         │          │     └──────────────┘                        │                 │
                         │ 172.28.0.1:8000 (host-only bridge IP)   172.28.0.1:3100 │ push            │
  ───────────────────────┼──────────┼─────────────────────────────────────────────┼─────────────────│
  MicroK8s               │   ┌──────┴────────────┐  ┌────────────────┐   ┌────────┴─────────┐       │
                         │   │ learner-simulator │  │  blog-indexer  │   │ Alloy DaemonSet  │       │
                         │   │ (calls the API)   │  │ ×2 (worker)    │   │ tails /var/log/  │       │
                         │   └───────────────────┘  └────────────────┘   │ pods, CRI parse  │       │
                         │        namespace: devtrails                   └──────────────────┘       │
                         │                                               namespace: monitoring      │
                         └──────────────────────────────────────────────────────────────────────────┘
  Published ports: 127.0.0.1 only (3000, 9090, 3100, 8000, 8025) + 172.28.0.1 (host-only bridge). Nothing public.
```

**How MicroK8s reaches Loki privately.** Compose creates the `observability` bridge with gateway
`172.28.0.1`. That address exists only on the host's `br-*` interface. Loki (and the app) publish their
ports there in addition to `127.0.0.1`. Pod traffic to the host is delivered locally (Calico allows
workload→host), so Alloy pushes to `http://172.28.0.1:3100` without any public listener and without
`hostNetwork`. Node Exporter runs in the host network namespace (so network metrics are the host's) and
binds only to that same IP.

---

## Repository layout

```
.
├── README.md                ← you are here
├── compose.yaml             ← Prometheus, Grafana, Loki, Node Exporter, app (+ optional Mailpit)
├── .env.example             ← copy to .env (git-ignored): Grafana admin, SMTP, recipient
├── Makefile                 ← shortcuts: make up / k8s / verify / demo / chaos / clean
├── app/                     ← DevTrails Flask app (Dockerfile, app.py, catalog.py, templates, static)
├── prometheus/prometheus.yml
├── loki/config.yml
├── kubernetes/
│   ├── namespace.yaml       ← devtrails + monitoring namespaces
│   ├── workload.yaml        ← blog-indexer + learner-simulator Deployments (+ ConfigMap scripts)
│   └── alloy-values.yaml    ← Helm values for grafana/alloy (pod discovery → Loki)
├── grafana/
│   ├── dashboards/          ← exported dashboard JSON (overview: 25 panels, k8s logs: 4 panels)
│   └── provisioning/        ← datasources, dashboard provider, alerting (rules, contact point, policy)
├── alerting/configuration-notes.md   ← thresholds, SMTP setup, how to trigger, operator actions
├── docs/promql.md           ← every PromQL expression explained + metric catalogue
├── scripts/
│   ├── setup-ubuntu.sh      ← installs Docker Engine/Compose + MicroK8s (fresh EC2)
│   ├── deploy-k8s.sh        ← applies manifests, installs Alloy via Helm
│   ├── traffic-test.sh      ← normal / burst / fail / chaos traffic + metric snapshots
│   ├── verify.sh            ← end-to-end checks, writes evidence/verification-*.txt
│   └── generate-dashboards.py
└── evidence/                ← screenshots + verification output (see evidence/README.md)
```

---

## 1. Prerequisites

* Ubuntu 26.04 (24.04 works too), ≥ 2 vCPU / 4 GB RAM (EC2 `t3.medium` or larger; `t3.large` is comfortable)
* Docker Engine + Compose plugin, MicroK8s with `dns`, `helm3`, `hostpath-storage`
* `curl`, `jq`, `bc`, `column` (for the scripts)

Fresh machine: `sudo ./scripts/setup-ubuntu.sh`, then log out and back in.

Record the toolchain:
```bash
lsb_release -ds
docker --version && docker compose version
microk8s status --wait-ready
microk8s kubectl get nodes -o wide
```

## 2. Configure secrets

```bash
cp .env.example .env && chmod 600 .env
nano .env          # GRAFANA_ADMIN_PASSWORD, SMTP_*, ALERT_EMAIL_TO
```
`.env` is in `.gitignore`. SMTP options (Gmail App Password, Mailtrap, local Mailpit) are documented in
[alerting/configuration-notes.md](alerting/configuration-notes.md).

## 3. Start the metrics + logging backend

```bash
docker compose config -q          # validate
docker compose up -d --build      # or: docker compose --profile mailpit up -d --build
docker compose ps
```

| UI | URL |
|---|---|
| DevTrails site | http://127.0.0.1:8000 |
| Grafana | http://127.0.0.1:3000 (admin / password from `.env`) |
| Prometheus | http://127.0.0.1:9090/targets |
| Mailpit (optional) | http://127.0.0.1:8025 |

**Persistence check:** `docker compose restart` (or reboot). Dashboards, alert history, Prometheus TSDB,
Loki chunks and enrollments (SQLite) live in named volumes (`docker volume ls`). All services use
`restart: unless-stopped`.

## 4. Deploy the MicroK8s workload and Alloy

```bash
./scripts/deploy-k8s.sh
microk8s kubectl get pods -A
microk8s kubectl logs -n devtrails deploy/blog-indexer --tail=20
microk8s kubectl logs -n devtrails deploy/learner-simulator --tail=20
```
The workloads write JSON lines: normal events to **stdout**, failures to **stderr**. `blog-indexer`
fails every 12th job on purpose (`FrontMatterParseError`). Set `FAILURE_MODE=true` to fail every job.
`learner-simulator` logs every API response, so app outages and chaos show up in pod logs too.

In Grafana → **Explore → Loki**:
```logql
{namespace="devtrails"}                                   # everything from the workload
{namespace="devtrails", stream="stderr"}                  # only errors
{namespace="devtrails", app="blog-indexer"} |= "FrontMatterParseError"
{namespace="devtrails"} | json | level="ERROR" | line_format "{{.pod}} {{.msg}}"
sum by (pod) (count_over_time({namespace="devtrails"}[1m]))
```
Labels: `namespace, pod, container, app, node, job, stream, level, cluster`.

## 5. Generate traffic and observe changes

```bash
./scripts/traffic-test.sh snapshot     # counters before
./scripts/traffic-test.sh normal 60    # ~2 req/s browsing + valid enrollments  → 200/201
./scripts/traffic-test.sh burst 60     # 8 parallel clients, ~100 req/s         → req/s and p95 climb
./scripts/traffic-test.sh fail 10      # 400 validation, 500 payment failure, 404 → failed/rejected counters
./scripts/traffic-test.sh snapshot     # counters after
# or all of it: ./scripts/traffic-test.sh demo
```
Manual requests:
```bash
curl -s localhost:8000/health
curl -s -XPOST localhost:8000/api/orders -H 'Content-Type: application/json' \
     -d '{"topic":"kubernetes","plan":"pro","email":"me@example.com"}'          # 201
curl -s -XPOST localhost:8000/api/orders -H 'Content-Type: application/json' -d '{"topic":"x"}'   # 400
curl -s -XPOST localhost:8000/api/orders -H 'Content-Type: application/json' \
     -d '{"topic":"docker","plan":"pro","email":"me@example.com","simulate_failure":true}'       # 500
curl -s localhost:8000/metrics | grep ^devtrails_
```

**Custom metrics** (full list in [docs/promql.md](docs/promql.md)):
`devtrails_http_requests_total{method,route,status}` (counter),
`devtrails_http_request_duration_seconds` (histogram),
`devtrails_orders_total{topic,plan,result}` (business event),
`devtrails_order_revenue_dollars_total`, `devtrails_post_views_total{topic}`,
`devtrails_http_requests_in_progress`, `devtrails_chaos_error_ratio`.
Labels are bounded: `route` is the Flask URL template (`/blog/<slug>`), never the raw path.

## 6. PromQL and Ubuntu cross-checks

| Signal | PromQL | Compare with |
|---|---|---|
| CPU % | `100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])))` | `vmstat 1`, `top` |
| RAM % | `100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)` | `free -m` → `1 - available/total` |
| Disk % | `100 * (1 - node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"})` | `df -h /` (reads ~2-5 pts lower: excludes reserved blocks) |
| Uptime | `time() - node_boot_time_seconds` | `uptime`, `/proc/uptime` |
| Requests/s | `sum(rate(devtrails_http_requests_total[1m]))` | traffic-test summary |
| Error % | `100 * sum(rate(devtrails_http_requests_total{status=~"5.."}[1m])) / sum(rate(devtrails_http_requests_total[1m]))` | |
| p95 latency | `histogram_quantile(0.95, sum by (le) (rate(devtrails_http_request_duration_seconds_bucket[5m])))` | |

Example from the local run: RAM 61.4% vs `free` 1 − 5759/14940 = 61.4%. Uptime 1477.7 s vs `/proc/uptime` 1477.1 s.

`./scripts/verify.sh` prints all of the above side by side and saves it to `evidence/`.

## 7. Dashboards

Provisioned automatically into the **DevTrails** folder (JSON in `grafana/dashboards/`):

* **DevTrails · Host & Application Overview** (home dashboard): uptime, CPU %, RAM %, disk %, CPU by
  mode, memory, network throughput, disk utilisation/I/O, load, req/s, 5xx %, p95, enrollments, revenue,
  targets up, req/s by route, status codes, p50/p95/p99, error % by route, orders by result, post reads, in-flight/chaos.
* **DevTrails · MicroK8s Pod Logs (Loki)**: namespace/pod/search variables, log volume per pod,
  stderr/ERROR rate, live log panel, errors-only panel.

## 8. Email alerting

Provisioned rules, contact point and policy are described in [alerting/configuration-notes.md](alerting/configuration-notes.md).
Trigger safely:
```bash
./scripts/traffic-test.sh chaos 0.5 240     # 50% of /api/* → 503 for 4 min
```
Grafana → Alerting → Alert rules: *DevTrails API high error rate* goes **Normal → Pending → Firing**,
and the email `[FIRING] DevTrails: DevTrails API high error rate` arrives about 90 s later (locally: pending
19:25:50 → email 19:27:20 UTC). When the chaos window ends, a **RESOLVED** email follows.
Stop early: `./scripts/traffic-test.sh chaos-off`.

## 9. Moving to EC2

1. Launch Ubuntu 26.04 (or 24.04), `t3.large`, 30 GB gp3. **Security group: inbound TCP 22 from your IP only.**
2. Copy the project: `scp -r ./Observability ubuntu@<ip>:~/` (or `git clone`). Do **not** copy `.env`. Create it on the instance.
3. `sudo ./scripts/setup-ubuntu.sh` → re-login → `cp .env.example .env` → edit.
4. `docker compose up -d --build && ./scripts/deploy-k8s.sh && ./scripts/verify.sh`
5. Open the UIs through an SSH tunnel (nothing is exposed publicly):
   ```bash
   ssh -i key.pem -L 3000:127.0.0.1:3000 -L 9090:127.0.0.1:9090 -L 8000:127.0.0.1:8000 -L 8025:127.0.0.1:8025 ubuntu@<ec2-ip>
   ```
   Then browse to http://localhost:3000 on your laptop.
6. SMTP from EC2: use port 587/2525 (AWS throttles outbound 25).
7. If `172.28.0.0/24` overlaps your VPC, change the subnet in `compose.yaml`, `prometheus/prometheus.yml`,
   `kubernetes/alloy-values.yaml` and `kubernetes/workload.yaml` (search for `172.28.0.1`).

To make the learning site public on purpose, set `APP_BIND=0.0.0.0` and open 8000 in the security group.
Grafana, Prometheus, Loki and the exporter stay private either way.

## 10. Evidence

See [evidence/README.md](evidence/README.md) for the screenshot checklist. `./scripts/verify.sh` writes
the text evidence (versions, `docker compose ps`, pods, targets, PromQL vs Linux, Loki vs kubectl, alert states).

## 11. Cleanup

```bash
make k8s-down                       # helm uninstall alloy + delete namespaces
docker compose --profile mailpit down        # stop, keep data
docker compose --profile mailpit down -v     # stop and delete all volumes
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `node-exporter` target down | `ip addr \| grep 172.28.0.1`: the bridge must exist. Run `docker compose up -d` again (the network is created first). Check `ufw` allows the docker bridge. |
| No logs in Loki | `microk8s kubectl logs -n monitoring ds/alloy -c alloy`; from a pod: `wget -qO- http://172.28.0.1:3100/ready`. |
| No email | Grafana → Alerting → Contact points → *Test*; `docker compose logs grafana \| grep -i smtp`; Gmail needs an App Password. |
| Alert never fires | Chaos only affects `/api/*`; the script must keep sending traffic for over 1.5 min. |

## Limitations and possible improvements

* **Single node / single replica**: Prometheus, Loki and Grafana are not HA, and Loki uses local filesystem
  storage. In production use object storage (S3) and Mimir/Thanos for long-term metrics.
* **App metrics in one process**: gunicorn runs 1 worker × 8 threads so `prometheus_client` keeps one
  registry. Scaling to several workers needs `PROMETHEUS_MULTIPROC_DIR` multiprocess mode.
* **Docker container logs** of the Compose app are not shipped to Loki (only Kubernetes logs, as specified).
  Alloy's `loki.source.docker` could add them.
* Improvements: tracing (OpenTelemetry → Tempo) with exemplars linking p95 spikes to traces, SLO burn-rate
  alerts instead of a fixed threshold, and TLS + reverse proxy if anything must become public.
