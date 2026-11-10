#!/usr/bin/env bash
# End-to-end verification. It prints the evidence the assessment asks for and saves it to
# evidence/verification-<timestamp>.txt. It only reads (plus a few GET/POST calls to the app).
set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p evidence
OUT="evidence/verification-$(date +%Y%m%d-%H%M%S).txt"
exec > >(tee "$OUT") 2>&1

PROM=http://127.0.0.1:9090
LOKI=http://127.0.0.1:3100
APP=http://127.0.0.1:8000
K="microk8s kubectl"
h() { printf '\n\033[1;36m### %s\033[0m\n' "$*"; }
promq() { curl -s "$PROM/api/v1/query" --data-urlencode "query=$1" | jq -r '.data.result[] | "\(.metric | del(.__name__) | tostring)  \(.value[1])"'; }

h "1. Toolchain versions"
lsb_release -ds 2>/dev/null || grep PRETTY /etc/os-release
docker --version
docker compose version
microk8s version
microk8s status --wait-ready | head -4
$K get nodes -o wide

h "2. Docker Compose services"
docker compose ps --format 'table {{.Name}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
docker volume ls --filter name=devtrails-observability

h "3. MicroK8s pods (all namespaces)"
$K get pods -A -o wide

h "4. Prometheus targets"
curl -s "$PROM/api/v1/targets" | jq -r '.data.activeTargets[] | "\(.labels.job)\t\(.scrapeUrl)\t\(.health)\t\(.lastError)"' | column -t -s $'\t'

h "5. Application endpoints"
echo "GET /health  -> $(curl -s -w ' [%{http_code}]' $APP/health)"
echo "POST /api/orders (valid) -> $(curl -s -w ' [%{http_code}]' -H 'Content-Type: application/json' -d '{"topic":"kubernetes","plan":"pro","email":"verify@example.com"}' $APP/api/orders)"
echo "POST /api/orders (invalid) -> $(curl -s -w ' [%{http_code}]' -H 'Content-Type: application/json' -d '{"topic":"nope"}' $APP/api/orders)"
echo "POST /api/orders (simulated failure) -> $(curl -s -w ' [%{http_code}]' -H 'Content-Type: application/json' -d '{"topic":"docker","plan":"pro","email":"verify@example.com","simulate_failure":true}' $APP/api/orders)"
echo "--- /metrics (custom series excerpt)"
curl -s $APP/metrics | grep -E '^devtrails_(http_requests_total|orders_total\{.*result="(success|failed)",topic="kubernetes"|order_revenue|post_views_total\{topic="kubernetes"|http_request_duration_seconds_(count|sum))' | head -25

h "6. PromQL results"
echo "CPU busy %:";      promq '100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])))'
echo "RAM used %:";      promq '100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)'
echo "Root disk used %:"; promq '100 * (1 - node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"})'
echo "Uptime (s):";      promq 'time() - node_boot_time_seconds'
echo "Requests/s:";      promq 'sum(rate(devtrails_http_requests_total[5m]))'
echo "5xx error rate %:"; promq '100 * (sum(rate(devtrails_http_requests_total{status=~"5.."}[5m])) or vector(0)) / clamp_min(sum(rate(devtrails_http_requests_total[5m])), 0.001)'
echo "p95 latency (s):"; promq 'histogram_quantile(0.95, sum by (le) (rate(devtrails_http_request_duration_seconds_bucket[5m])))'
echo "Orders by result (1h):"; promq 'sum by (result) (increase(devtrails_orders_total[1h]))'

h "7. Ubuntu cross-checks (compare with section 6)"
echo "--- free -m";  free -m
echo "--- df -h /";  df -h /
echo "--- uptime";   uptime; awk '{print "uptime seconds: " $1}' /proc/uptime
echo "note: df 'Use%' = used/(used+avail) excludes root-reserved blocks; PromQL uses 1-avail/size, so it reads ~2-5 points higher."

h "8. Kubernetes logs: kubectl vs Loki"
echo "--- microk8s kubectl logs (blog-indexer, last 5)"
$K logs -n devtrails deploy/blog-indexer --tail=5
echo "--- Loki labels"
curl -s "$LOKI/loki/api/v1/labels" | jq -c .data
echo "--- Loki: line counts per pod/stream, last 10m"
curl -s -G "$LOKI/loki/api/v1/query" --data-urlencode 'query=sum by (pod, stream) (count_over_time({namespace="devtrails"}[10m]))' \
  | jq -r '.data.result[] | "\(.metric.pod)\t\(.metric.stream)\t\(.value[1])"' | column -t
echo "--- Loki: latest errors (stderr) in namespace devtrails"
curl -s -G "$LOKI/loki/api/v1/query_range" --data-urlencode 'query={namespace="devtrails", stream="stderr"}' --data-urlencode 'limit=5' \
  | jq -r '.data.result[] | .stream.pod as $p | .values[] | "\($p)  \(.[1])"' | head -5

h "9. Grafana alert rules"
if [[ -f .env ]]; then
  envget() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- | sed -e 's/^["\x27]//' -e 's/["\x27]$//'; }
  GU=$(envget GRAFANA_ADMIN_USER); GP=$(envget GRAFANA_ADMIN_PASSWORD)
  curl -s -u "${GU:-admin}:${GP}" http://127.0.0.1:3000/api/prometheus/grafana/api/v1/rules \
    | jq -r '.data.groups[].rules[] | "\(.name)\t\(.state)\t\(.health)"' | column -t -s $'\t'
fi

echo; echo "Saved to $OUT"
