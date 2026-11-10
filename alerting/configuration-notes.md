# Alerting configuration notes

Everything is provisioned from files: [`grafana/provisioning/alerting/alerting.yaml`](../grafana/provisioning/alerting/alerting.yaml).
Nothing has to be clicked together in the UI, and a fresh `docker compose up -d` recreates the same setup.

## SMTP (outbound email)

Grafana's SMTP client is configured **only through environment variables** that Compose reads from `.env`
(git-ignored, `chmod 600`). No credentials appear in any committed file.

| Variable in `.env`      | Grafana setting          | Example                     |
|-------------------------|--------------------------|-----------------------------|
| `SMTP_HOST`             | `GF_SMTP_HOST`           | `smtp.gmail.com:587`        |
| `SMTP_USER`             | `GF_SMTP_USER`           | `you@gmail.com`             |
| `SMTP_PASSWORD`         | `GF_SMTP_PASSWORD`       | Gmail **App Password**      |
| `SMTP_FROM_ADDRESS`     | `GF_SMTP_FROM_ADDRESS`   | `you@gmail.com`             |
| `SMTP_STARTTLS_POLICY`  | `GF_SMTP_STARTTLS_POLICY`| `MandatoryStartTLS`         |
| `ALERT_EMAIL_TO`        | contact point `addresses`| `oncall@yourdomain.com`     |

Tested providers:
* **Gmail**: enable 2-Step Verification, create an App Password, use port 587 with STARTTLS.
* **Mailtrap sandbox**: a real SMTP test inbox (`sandbox.smtp.mailtrap.io:2525`).
* **Mailpit** (local only): `docker compose --profile mailpit up -d`, `SMTP_HOST=mailpit:1025`,
  `SMTP_STARTTLS_POLICY=NoStartTLS`, inbox UI at http://127.0.0.1:8025.

> EC2 note: AWS throttles outbound port 25, so use 587 (STARTTLS) or 2525.

## Contact point and notification policy

* Contact point **`devtrails-oncall-email`** (type: email, single email to all recipients).
  Subject: `[FIRING] DevTrails: <alertname>` / `[RESOLVED] ...`. Resolve messages are enabled.
* Default policy routes everything to that contact point, grouped by `grafana_folder, alertname`.
  * `group_wait: 30s`: waits 30s after the first alert so related alerts arrive in one email.
  * `group_interval: 2m`: minimum gap between emails for the same group.
  * `repeat_interval: 4h`: re-notifies while the alert is still firing.

## Alert rules (folder: *DevTrails Alerts*)

| Rule | Query (A) | Threshold (C) | Pending | Severity | Operator action |
|---|---|---|---|---|---|
| **DevTrails API high error rate** (the actionable rule) | `100 * sum(rate(devtrails_http_requests_total{status=~"5.."}[2m])) / sum(rate(devtrails_http_requests_total[2m]))` | `> 5` (%) | 1m (evaluated every 30s) | critical | Check *Error rate by route* panel, `docker compose logs app`, check chaos switch (`GET /api/admin/chaos`), roll back or `DELETE /api/admin/chaos`. |
| **Scrape target down** | `up{job=~"devtrails-app\|node-exporter"}` | `< 1` | 1m | critical | `docker compose ps`, Prometheus → Targets error, `docker compose up -d <svc>`. No data also counts as alerting. |
| **Ubuntu host CPU above 90%** | `100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])))` | `> 90` | 5m | warning | `top`/`htop`, find the noisy process, scale or throttle. |

Why these thresholds:
* **5% 5xx for 1 minute**: normal traffic has 0% 5xx (validation errors are 4xx and do not count).
  Over 5% sustained across two evaluations means users are failing, while one bad request cannot page anyone.
* The 2-minute `rate()` window smooths single-scrape noise (scrape interval is 15s, so 8 samples).

## Triggering the alert safely

```bash
./scripts/traffic-test.sh chaos 0.5 240   # 50% of /api/* return 503 for 4 minutes, plus traffic
```
Timeline: **Normal → Pending** (first evaluation over 5%, ≤30s) → **Firing** (after 1m pending) →
email arrives after `group_wait` (30s). That is about 2 minutes end to end. When chaos expires the ratio decays and the
rule returns to Normal, then a **RESOLVED** email is sent.

Alternative trigger for the *target down* rule: `docker compose stop app` (restart with `docker compose start app`).

Evidence to capture: Alerting → Alert rules (state *Firing*), Alerting → History, the contact point page
(the password field is masked by Grafana), and the received email showing subject and timestamp.
