# Evidence

Capture these after `docker compose up -d`, `./scripts/deploy-k8s.sh` and some traffic.
**Hide credentials** (Grafana masks the SMTP password; crop or blur email addresses if needed).

| # | File | What it must show | How |
|---|---|---|---|
| 1 | `compose-and-cluster.png` | `docker compose ps`, `microk8s status`, `microk8s kubectl get pods -A`, versions | terminal (or `verification-*.txt`) |
| 2 | `prometheus-targets.png` | `node-exporter` and `devtrails-app` **UP** | http://127.0.0.1:9090/targets |
| 3 | `app-metrics.png` | `/metrics` output + traffic-test before/after snapshot + failure test | `./scripts/traffic-test.sh demo` |
| 4 | `promql-crosscheck.png` | five PromQL results next to `free`, `df`, `uptime` | Prometheus graph tab + terminal, or verify.sh output |
| 5 | `grafana-metrics.png` | Overview dashboard (≥ 8 panels) with live data | Grafana → DevTrails → Overview |
| 6 | `kubernetes-logs.png` | `microk8s kubectl logs ...` and the same lines in Grafana Explore (Loki) | Explore → Loki → `{namespace="devtrails"}` |
| 7 | `alert-firing.png` + `email-alert.png` | rule in **Firing** / history, contact point, received email with subject and timestamp | `./scripts/traffic-test.sh chaos` |
| 8 | `verification-*.txt` | full text evidence | `./scripts/verify.sh` |
