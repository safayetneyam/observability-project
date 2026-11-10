#!/usr/bin/env bash
# Generate DevTrails traffic at different rates and controlled failures, and show metric deltas.
#
#   ./scripts/traffic-test.sh snapshot          # print key counters from /metrics
#   ./scripts/traffic-test.sh normal [n]        # ~2 req/s mixed browsing + valid enrollments (default 60)
#   ./scripts/traffic-test.sh burst [secs]      # higher rate: ~100 req/s from 8 parallel clients (default 60s)
#   ./scripts/traffic-test.sh fail [n]          # controlled failures: 400 validation, 500 payment, 404 (default 10 each)
#   ./scripts/traffic-test.sh chaos [rate] [s]  # enable chaos error ratio (default 0.5 for 240s) + drive traffic → alert fires
#   ./scripts/traffic-test.sh chaos-off         # disable chaos immediately
#   ./scripts/traffic-test.sh demo              # snapshot → normal → burst → fail → snapshot
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
CHAOS_TOKEN="${CHAOS_TOKEN:-}"
TOPICS=(kubernetes docker linux observability cicd cloud)
PLANS=(free pro team)
POSTS=(what-is-a-pod deployments-and-rolling-updates images-layers-and-build-cache reading-memory-correctly promql-rate-sum-histogram-quantile ec2-essentials)

c_green=$'\e[32m'; c_red=$'\e[31m'; c_yel=$'\e[33m'; c_dim=$'\e[2m'; c_off=$'\e[0m'
say() { printf '%s==>%s %s\n' "$c_green" "$c_off" "$*"; }

req() { # method path [json]  -> prints status code
  local m=$1 p=$2 d=${3:-}
  if [[ -n $d ]]; then
    curl -s -o /dev/null -w '%{http_code}' -X "$m" -H 'Content-Type: application/json' -d "$d" "$BASE_URL$p"
  else
    curl -s -o /dev/null -w '%{http_code}' -X "$m" "$BASE_URL$p"
  fi
}

pick() { local a=("$@"); echo "${a[RANDOM % ${#a[@]}]}"; }

order_json() { printf '{"topic":"%s","plan":"%s","email":"learner%d@example.com"}' "$(pick "${TOPICS[@]}")" "$(pick "${PLANS[@]}")" "$RANDOM"; }

snapshot() {
  say "Metric snapshot from $BASE_URL/metrics"
  curl -s "$BASE_URL/metrics" | awk '
    /^devtrails_http_requests_total/ { split($0,a,"status=\""); split(a[2],b,"\""); s[substr(b[1],1,1)"xx"]+=$NF; t+=$NF }
    /^devtrails_orders_total/ { split($0,a,"result=\""); split(a[2],b,"\""); o[b[1]]+=$NF }
    /^devtrails_http_request_duration_seconds_count/ { c+=$NF }
    /^devtrails_post_views_total/ { v+=$NF }
    END {
      printf "  http requests total : %d  (2xx=%d 4xx=%d 5xx=%d)\n", t, s["2xx"], s["4xx"], s["5xx"]
      printf "  latency observations: %d\n", c
      printf "  orders              : success=%d failed=%d rejected=%d\n", o["success"], o["failed"], o["rejected"]
      printf "  post reads          : %d\n", v
    }'
}

normal() {
  local n=${1:-60} codes=""
  say "Normal traffic: $n iterations at ~2 req/s"
  for ((i = 1; i <= n; i++)); do
    codes+=" $(req GET /api/topics)"
    codes+=" $(req GET "/api/posts/$(pick "${POSTS[@]}")")"
    ((i % 5 == 0)) && codes+=" $(req POST /api/orders "$(order_json)")"
    ((i % 10 == 0)) && codes+=" $(req GET /health)"
    sleep 0.5
  done
  summarize "$codes"
}

burst() {
  local secs=${1:-60} workers=8
  say "Burst traffic: $workers parallel clients for ${secs}s"
  local end=$((SECONDS + secs)) tmp; tmp=$(mktemp)
  for ((w = 0; w < workers; w++)); do
    ( while ((SECONDS < end)); do
        echo "$(req GET "/api/posts/$(pick "${POSTS[@]}")")"
        echo "$(req GET "/api/topics/$(pick "${TOPICS[@]}")")"
        ((RANDOM % 4 == 0)) && echo "$(req POST /api/orders "$(order_json)")"
        sleep 0.05
      done >>"$tmp" ) &
  done
  wait
  summarize "$(cat "$tmp")"
  echo "  ${c_dim}~$(( $(wc -l <"$tmp") / secs )) req/s${c_off}"
  rm -f "$tmp"
}

fail() {
  local n=${1:-10} codes=""
  say "Controlled failures: $n × (invalid order → 400, payment failure → 500, unknown post → 404)"
  for ((i = 1; i <= n; i++)); do
    codes+=" $(req POST /api/orders '{"topic":"basket-weaving","plan":"gold","email":"nope"}')"
    codes+=" $(req POST /api/orders "$(printf '{"topic":"%s","plan":"pro","email":"fail@example.com","simulate_failure":true}' "$(pick "${TOPICS[@]}")")")"
    codes+=" $(req GET /api/posts/does-not-exist)"
    sleep 0.3
  done
  summarize "$codes"
}

chaos() {
  local rate=${1:-0.5} secs=${2:-240}
  say "Enabling chaos mode: ${rate} of /api/* requests fail with 503 for ${secs}s"
  curl -s -X POST -H 'Content-Type: application/json' ${CHAOS_TOKEN:+-H "X-Chaos-Token: $CHAOS_TOKEN"} \
    -d "{\"error_rate\":$rate,\"latency_ms\":150,\"duration_s\":$secs}" "$BASE_URL/api/admin/chaos"; echo
  say "Driving traffic so the 5xx ratio is measurable (alert: >5% for 1m, evaluated every 30s)"
  echo "  ${c_dim}Watch: Grafana → Alerting → Alert rules → 'DevTrails API high error rate' (Normal → Pending → Firing)${c_off}"
  local end=$((SECONDS + secs)) codes=""
  while ((SECONDS < end)); do
    codes+=" $(req GET /api/topics) $(req GET "/api/posts/$(pick "${POSTS[@]}")") $(req POST /api/orders "$(order_json)")"
    sleep 0.3
    if ((SECONDS % 30 == 0)); then printf '  %ss left\n' $((end - SECONDS)); sleep 1; fi
  done
  summarize "$codes"
  say "Chaos window over. The alert resolves after the error ratio drops (a resolved email is sent too)."
}

chaos_off() { curl -s -X DELETE ${CHAOS_TOKEN:+-H "X-Chaos-Token: $CHAOS_TOKEN"} "$BASE_URL/api/admin/chaos"; echo; }

summarize() {
  echo "$1" | tr ' ' '\n' | grep -E '^[0-9]{3}$' | sort | uniq -c | while read -r cnt code; do
    case $code in 2*) col=$c_green ;; 4*) col=$c_yel ;; *) col=$c_red ;; esac
    printf '  %s%s%s × %s\n' "$col" "$code" "$c_off" "$cnt"
  done
}

case "${1:-demo}" in
  snapshot) snapshot ;;
  normal) normal "${2:-60}" ;;
  burst) burst "${2:-60}" ;;
  fail) fail "${2:-10}" ;;
  chaos) chaos "${2:-0.5}" "${3:-240}" ;;
  chaos-off) chaos_off ;;
  demo) snapshot; normal 30; burst 30; fail 10; snapshot ;;
  *) sed -n '2,12p' "$0"; exit 1 ;;
esac
