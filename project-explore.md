# DevTrails Observability: How to Run the Project

This guide covers every step from a fresh Ubuntu machine to a finished demo: setup, running locally,
moving to EC2, the demo sequence, collecting evidence, troubleshooting and cleanup.

- **App:** DevTrails, a topic-based tech blog (Flask) with `/health`, `POST /api/orders` and `/metrics`
- **Docker Compose:** Prometheus, Grafana, Loki, Node Exporter, the app, and an optional Mailpit test inbox
- **MicroK8s:** `blog-indexer` and `learner-simulator` workloads, plus Grafana Alloy shipping their logs to Loki
- **Alerting:** Grafana alert rules → SMTP → email inbox

---

## 0. Folder layout

```
Observability/
├── project-explore.md       ← this file
├── README.md                ← architecture + reference
├── compose.yaml             ← Docker Compose stack
├── .env.example             ← copy to .env (never commit .env)
├── Makefile                 ← shortcuts (make up / k8s / demo / chaos / verify / clean)
├── app/                     ← DevTrails Flask app (Dockerfile, app.py, catalog.py, templates/, static/)
├── prometheus/prometheus.yml
├── loki/config.yml
├── kubernetes/              ← namespace.yaml, workload.yaml, alloy-values.yaml
├── grafana/                 ← dashboards/*.json + provisioning/ (datasources, dashboards, alerting)
├── alerting/configuration-notes.md
├── docs/promql.md
├── scripts/                 ← setup-ubuntu.sh, deploy-k8s.sh, traffic-test.sh, verify.sh, generate-dashboards.py
└── evidence/                ← screenshots + verification-*.txt
```

---

## 1. Prerequisites (one time)

| Requirement | Check |
|---|---|
| Ubuntu 26.04 (24.04 also works) | `lsb_release -ds` |
| Docker Engine + Compose plugin | `docker --version && docker compose version` |
| MicroK8s with `dns`, `helm3`, `hostpath-storage` | `microk8s status --wait-ready` |
| Your user in the `docker` and `microk8s` groups | `groups` |
| `curl`, `jq`, `bc`, `column`, `zip` | `which jq bc column zip` |
| Free ports on 127.0.0.1: 3000, 3100, 8000, 8025, 9090 | `ss -ltnp \| grep -E ':(3000\|3100\|8000\|8025\|9090)\b'` (should print nothing) |
| Subnet `172.28.0.0/24` not already in use | `ip -br addr \| grep 172.28` (should print nothing before the first start) |

**Fresh machine?** One script installs everything:

```bash
cd ~/Desktop/Observability
sudo ./scripts/setup-ubuntu.sh
# log out and back in (or run: newgrp docker) so the group changes apply
```

### 1.1 Disable the MicroK8s ingress add-on (important on Ubuntu 26.04)

The project does not use ingress. On Ubuntu 26.04, the `ingress` add-on of MicroK8s 1.31 crash-loops
(`nginx-ingress-microk8s-controller ... CrashLoopBackOff`). Ubuntu 26.04 ships AppArmor 5.0, which
blocks a signal (`SIGURG`) the controller needs:

```
apparmor="DENIED" operation="signal" profile="cri-containerd.apparmor.d" comm="nginx-ingress-c" signal=urg
```

You can confirm it with `sudo journalctl -k | grep 'apparmor="DENIED".*nginx-ingress'`.

Turn it off so `microk8s kubectl get pods -A` is clean for the evidence:

```bash
microk8s disable ingress
microk8s kubectl get pods -A          # everything should be Running
```

Do **not** enable ingress on the EC2 instance either. If you need it later, try a newer MicroK8s channel
(for example `sudo snap refresh microk8s --channel=1.33/stable`). That is untested here.

---

## 2. Configure secrets (`.env`)

```bash
cd ~/Desktop/Observability
cp .env.example .env
chmod 600 .env
nano .env
```

Minimum to set:

| Variable | Meaning |
|---|---|
| `GRAFANA_ADMIN_PASSWORD` | Grafana `admin` password (choose a long one) |
| `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM_ADDRESS`, `SMTP_STARTTLS_POLICY` | outbound mail server |
| `ALERT_EMAIL_TO` | inbox that receives alert emails |
| `APP_BIND` | keep `127.0.0.1` (private). Use `0.0.0.0` only to make the blog public on purpose |

Pick **one** SMTP option:

**A. Local Mailpit test inbox** (no account needed, good for local testing)
```
SMTP_HOST=mailpit:1025
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM_ADDRESS=alerts@devtrails.local
SMTP_STARTTLS_POLICY=NoStartTLS
SMTP_SKIP_VERIFY=true
ALERT_EMAIL_TO=oncall@devtrails.local
```
Start the stack with `--profile mailpit` (step 3). The inbox is at http://127.0.0.1:8025.

**B. Gmail** (real inbox; needs 2-Step Verification plus an App Password from https://myaccount.google.com/apppasswords)
```
SMTP_HOST=smtp.gmail.com:587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=<16-character app password>
SMTP_FROM_ADDRESS=you@gmail.com
SMTP_STARTTLS_POLICY=MandatoryStartTLS
SMTP_SKIP_VERIFY=false
ALERT_EMAIL_TO=you@gmail.com
```

**C. Mailtrap sandbox** (a real SMTP test inbox): `SMTP_HOST=sandbox.smtp.mailtrap.io:2525`, plus the user
and password from your Mailtrap inbox settings.

> `.env` is git-ignored. Never commit it, zip it or screenshot it.
> After changing `.env`, apply it with `docker compose up -d grafana`.

---

## 3. Start the metrics + logging stack (Docker Compose)

```bash
cd ~/Desktop/Observability
docker compose config -q && echo "compose file OK"

# with the local Mailpit inbox:
docker compose --profile mailpit up -d --build
# or, with Gmail/Mailtrap (no Mailpit):
docker compose up -d --build

docker compose ps
```

All services should be `Up`, and `devtrails-app` should show `(healthy)` after about 15 s.

| Open | URL | Login |
|---|---|---|
| DevTrails blog | http://127.0.0.1:8000 | none |
| Grafana | http://127.0.0.1:3000 | `admin` / `GRAFANA_ADMIN_PASSWORD` |
| Prometheus targets | http://127.0.0.1:9090/targets | none |
| Mailpit inbox | http://127.0.0.1:8025 | none |

Quick checks:

```bash
curl -s localhost:8000/health                       # {"status":"ok",...}
curl -s localhost:8000/metrics | grep ^devtrails_   # custom metrics
curl -s localhost:3100/ready                        # ready (wait ~15 s after start)
ip -br addr | grep 172.28.0.1                       # host-only bridge exists
```

Grafana automatically provisions:
- data sources **Prometheus** and **Loki**
- dashboards in folder **DevTrails**: *Host & Application Overview* (25 panels) and *MicroK8s Pod Logs (Loki)*
- alert rules in folder **DevTrails Alerts**, contact point `devtrails-oncall-email` and the notification policy

---

## 4. Deploy the Kubernetes workloads + Grafana Alloy

Run this after step 3, because Alloy pushes to Loki on `172.28.0.1:3100`.

```bash
./scripts/deploy-k8s.sh
```

The script:
1. checks that Loki is reachable on `http://172.28.0.1:3100/ready`
2. applies `kubernetes/namespace.yaml` (namespaces `devtrails` and `monitoring`) and `kubernetes/workload.yaml`
3. installs Grafana Alloy with Helm (`grafana/alloy`, chart 1.15.0) using `kubernetes/alloy-values.yaml`
4. waits for all rollouts

Verify:

```bash
microk8s kubectl get nodes -o wide
microk8s kubectl get pods -A
microk8s kubectl logs -n devtrails deploy/blog-indexer --tail=20
microk8s kubectl logs -n devtrails deploy/learner-simulator --tail=20
microk8s kubectl logs -n monitoring ds/alloy -c alloy --tail=20
```

What the workloads do:
- **blog-indexer** (2 replicas) writes normal events to **stdout**. Every 12th job it fails on purpose
  (`FrontMatterParseError`) and writes the error to **stderr**. To make every job fail, run
  `microk8s kubectl set env -n devtrails deploy/blog-indexer FAILURE_MODE=true`, and set it back to `false` afterwards.
- **learner-simulator** calls the DevTrails API about every 2 s and logs each response. When the app fails or
  goes down, its errors appear in the pod logs too.

See the logs in Grafana under **Explore → Loki**:

```logql
{namespace="devtrails"}
{namespace="devtrails", stream="stderr"}
{namespace="devtrails", app="blog-indexer"} |= "FrontMatterParseError"
{namespace="devtrails"} | json | level="ERROR" | line_format "{{.pod}} {{.msg}}"
sum by (pod) (count_over_time({namespace="devtrails"}[1m]))
```

Or open **Dashboards → DevTrails → MicroK8s Pod Logs (Loki)**.

---

## 5. Demo sequence (what to show the evaluator)

### 5.1 Normal traffic, higher traffic, controlled failure

```bash
./scripts/traffic-test.sh snapshot     # counters BEFORE
./scripts/traffic-test.sh normal 60    # ~2 req/s, browsing + valid sign-ups → 200/201
./scripts/traffic-test.sh burst 60     # 8 parallel clients, ~100 req/s      → req/s and p95 rise
./scripts/traffic-test.sh fail 10      # 400 validation, 500 payment failure, 404 unknown post
./scripts/traffic-test.sh snapshot     # counters AFTER
# or everything at once:
./scripts/traffic-test.sh demo
```

Single requests by hand:

```bash
curl -s -XPOST localhost:8000/api/orders -H 'Content-Type: application/json' \
  -d '{"topic":"kubernetes","plan":"pro","email":"me@example.com"}'              # 201 success
curl -s -XPOST localhost:8000/api/orders -H 'Content-Type: application/json' \
  -d '{"topic":"nope"}'                                                         # 400 rejected
curl -s -XPOST localhost:8000/api/orders -H 'Content-Type: application/json' \
  -d '{"topic":"docker","plan":"pro","email":"me@example.com","simulate_failure":true}'   # 500 failed
```

What changes:
- **Overview dashboard:** *Requests/sec*, *Responses by status code*, *Latency percentiles*,
  *Enrollment orders by result* (success, failed, rejected) and *Blog post reads per minute*.
- **Metrics:** `devtrails_http_requests_total{status="500"}`, `devtrails_orders_total{result="failed"}` and
  `devtrails_http_request_duration_seconds_bucket`.
- **Kubernetes logs:** `learner-simulator` shows `-> 400` as WARN and `-> 5xx` or `unreachable` as ERROR on stderr.

### 5.2 PromQL and Ubuntu cross-checks

Run these in Prometheus (http://127.0.0.1:9090/graph) or Grafana Explore, then compare with the terminal:

| Signal | PromQL | Compare with |
|---|---|---|
| CPU % | `100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])))` | `vmstat 1 5`, `top` |
| RAM % | `100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)` | `free -m` → 1 − available/total |
| Disk % | `100 * (1 - node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"})` | `df -h /` (reads 2–5 points lower because it excludes root-reserved blocks) |
| Uptime | `time() - node_boot_time_seconds` | `uptime`, `cat /proc/uptime` |
| Requests/s | `sum(rate(devtrails_http_requests_total[1m]))` | traffic-test output |
| Error % | `100 * sum(rate(devtrails_http_requests_total{status=~"5.."}[1m])) / sum(rate(devtrails_http_requests_total[1m]))` | |
| p95 latency | `histogram_quantile(0.95, sum by (le) (rate(devtrails_http_request_duration_seconds_bucket[5m])))` | |

`docs/promql.md` explains every query.

### 5.3 Email alert

```bash
./scripts/traffic-test.sh chaos 0.5 240     # 50% of /api/* return 503 for 4 minutes
```

1. Grafana → **Alerting → Alert rules** → *DevTrails API high error rate*: Normal → **Pending** (≤ 30 s) → **Firing** (after 1 min).
2. The email `[FIRING] DevTrails: DevTrails API high error rate` arrives about 30 s later (Mailpit, Gmail or Mailtrap).
3. After the chaos window ends, the rule returns to Normal and a **RESOLVED** email is sent.
4. To stop early: `./scripts/traffic-test.sh chaos-off`.

To trigger the *Scrape target down* alert instead, run `docker compose stop app`, wait about 2 min, then run `docker compose start app`.

To test only the SMTP settings: Grafana → **Alerting → Contact points** → `devtrails-oncall-email` → **Test**.

Thresholds, timing and operator actions are in `alerting/configuration-notes.md`.

---

## 6. Collect evidence

```bash
rm -f evidence/verification-*.txt
./scripts/verify.sh          # prints + saves evidence/verification-<timestamp>.txt
```

The file contains tool versions, `docker compose ps`, volumes, `kubectl get pods -A`, Prometheus targets,
app responses, `/metrics`, PromQL values next to `free`/`df`/`uptime`, kubectl logs vs Loki, and alert rule states.

Screenshots to save in `evidence/` (details in `evidence/README.md`):

| File | Show |
|---|---|
| `compose-and-cluster.png` | `docker compose ps`, `microk8s status`, `microk8s kubectl get pods -A` |
| `prometheus-targets.png` | `node-exporter` and `devtrails-app` UP |
| `grafana-metrics.png` | Overview dashboard with live data |
| `kubernetes-logs.png` | `microk8s kubectl logs ...` + the same lines in Grafana Explore |
| `email-alert.png` | alert Firing / history + received email (hide addresses if needed) |

---

## 7. Moving to the EC2 instance

1. **Launch:** Ubuntu **26.04** (same as local; 24.04 also works), `t3.large` (2 vCPU / 8 GB; `t3.medium` is the minimum), 30 GB gp3.
2. **Security group:** inbound **TCP 22 from your IP only**. Do not open 3000, 9090, 3100 or 9100.
3. **Copy the project without secrets or local state:**
   ```bash
   # from your laptop
   cd ~/Desktop
   rsync -av --exclude .env --exclude '__pycache__' --exclude 'evidence/verification-*' \
     Observability/ ubuntu@<ec2-ip>:~/Observability/
   ```
4. **On the instance:**
   ```bash
   ssh -i key.pem ubuntu@<ec2-ip>
   cd ~/Observability
   sudo ./scripts/setup-ubuntu.sh        # skip the parts you already installed
   exit                                  # log out and back in for the docker/microk8s groups
   ssh -i key.pem ubuntu@<ec2-ip>
   cd ~/Observability
   microk8s disable ingress              # see section 1.1 (or simply don't enable it)
   cp .env.example .env && chmod 600 .env && nano .env    # use Gmail/Mailtrap SMTP on port 587/2525
   docker compose up -d --build
   ./scripts/deploy-k8s.sh
   ./scripts/traffic-test.sh demo
   ./scripts/verify.sh
   ```
5. **Open the UIs from your laptop through an SSH tunnel** (nothing is exposed publicly):
   ```bash
   ssh -i key.pem \
     -L 3000:127.0.0.1:3000 -L 9090:127.0.0.1:9090 \
     -L 8000:127.0.0.1:8000 -L 8025:127.0.0.1:8025 \
     ubuntu@<ec2-ip>
   ```
   Then browse to http://localhost:3000, http://localhost:9090, http://localhost:8000 and http://localhost:8025 on your laptop.
6. **EC2 notes**
   - AWS throttles outbound port 25, so use 587 (STARTTLS) or 2525 for SMTP.
   - If your VPC uses `172.28.0.0/24`, change that subnet everywhere it appears:
     `grep -rn 172.28.0 compose.yaml prometheus kubernetes`.
   - To make the blog public on purpose: set `APP_BIND=0.0.0.0` in `.env`, run `docker compose up -d app`, and open
     port 8000 in the security group. Grafana, Prometheus, Loki and Node Exporter stay private.

---

## 8. Everyday commands

| Task | Command |
|---|---|
| Start / update stack | `docker compose --profile mailpit up -d --build` |
| Status | `docker compose ps` · `microk8s kubectl get pods -A` |
| App logs | `docker compose logs -f app` |
| Rebuild only the app after code changes | `docker compose up -d --build app` |
| Apply `.env` changes to Grafana | `docker compose up -d grafana` |
| Re-apply Kubernetes changes | `./scripts/deploy-k8s.sh` |
| Regenerate dashboards after editing the generator | `python3 scripts/generate-dashboards.py` (Grafana reloads within 30 s) |
| Restart without losing data | `docker compose restart` |
| Make shortcuts | `make help` |

Persistence test: run `docker compose restart` (or reboot). Dashboards, alert history, Prometheus TSDB, Loki chunks
and sign-ups survive because they live in named volumes (`docker volume ls | grep devtrails`).

---

## 9. Stop and clean up

```bash
# stop containers, KEEP data volumes
docker compose --profile mailpit down

# remove Kubernetes workloads + Alloy
microk8s helm3 uninstall alloy -n monitoring
microk8s kubectl delete -f kubernetes/workload.yaml
microk8s kubectl delete -f kubernetes/namespace.yaml
#   (same as: make k8s-down)

# DELETE everything including all stored metrics, logs, dashboards state and sign-ups
docker compose --profile mailpit down -v
#   (make clean = down + k8s-down + down -v)
```

> ⚠️ `down -v` deletes the named volumes permanently. Use plain `down` unless you really want a fresh start.
> Removing the Compose stack also removes the `172.28.0.1` bridge. MicroK8s may then restart its services
> once, so each pod shows one extra restart. That is harmless.

---

## 10. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `nginx-ingress-microk8s-controller` in CrashLoopBackOff | AppArmor 5 on Ubuntu 26.04 blocks its SIGURG signal. Ingress is not used by this project: `microk8s disable ingress` (section 1.1). |
| `docker compose up` fails: `set GRAFANA_ADMIN_PASSWORD in .env` | `.env` is missing or incomplete: `cp .env.example .env` and fill it in. |
| Port already in use | Find the owner with `ss -ltnp \| grep :3000` and stop it, or change the host port in `compose.yaml`. |
| `node-exporter` target DOWN | Check that the bridge exists (`ip -br addr \| grep 172.28.0.1`), then run `docker compose up -d` again. If ufw is enabled: `sudo ufw allow from 172.28.0.0/24` (plus `sudo ufw allow from 10.1.0.0/16` for MicroK8s pods). |
| `deploy-k8s.sh`: "Loki not ready" | Start the Compose stack first (step 3) and wait about 15 s. |
| No logs in Loki | Check `microk8s kubectl logs -n monitoring ds/alloy -c alloy --tail=50`. Test from a pod: `microk8s kubectl run t --rm -it --image=busybox:1.36 --restart=Never -- wget -qO- http://172.28.0.1:3100/ready` |
| Pods `ImagePullBackOff` | The node needs internet access to pull `python:3.12-alpine` and the Alloy images. |
| No alert email | Contact point → **Test**. Check `docker compose logs grafana \| grep -i smtp`. Gmail needs an App Password. On EC2 use port 587. With Mailpit, start with `--profile mailpit`. |
| Alert stays Normal during chaos | Keep `traffic-test.sh chaos` running at least 1.5 min, because the rule needs over 5% 5xx for 1 min. |
| Dashboard panels empty | Generate traffic (`traffic-test.sh normal`) and check the time range (last 1 h). Rate panels need about 1 min of data. |
| CPU panel briefly very high | Builds and image pulls are real CPU load. It settles within the 5-minute rate window. |
| Disk % differs from `df` | Expected: `df` excludes ext4 root-reserved blocks (about 5%). |

---

## 11. Package for submission

```bash
cd ~/Desktop
zip -r <candidate-ID>_observability.zip Observability \
  -x 'Observability/.env' 'Observability/*__pycache__*' 'Observability/*.pdf'
unzip -l <candidate-ID>_observability.zip | grep -c '\.env$'    # must print 0 (.env.example is fine)
```

Or push to GitHub. `.gitignore` already excludes `.env`:

```bash
cd ~/Desktop/Observability
git init && git add . && git status     # confirm .env is NOT listed
git commit -m "DevTrails observability project"
git remote add origin https://github.com/<you>/<repo>.git && git push -u origin main
```
