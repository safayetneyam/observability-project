#!/usr/bin/env bash
# Deploy the DevTrails MicroK8s workloads and Grafana Alloy (log shipper → Loki).
# Prerequisite: `docker compose up -d` is running (Loki listens on 172.28.0.1:3100).
set -euo pipefail
cd "$(dirname "$0")/.."
K="microk8s kubectl"
H="microk8s helm3"
ALLOY_CHART_VERSION="${ALLOY_CHART_VERSION:-1.15.0}"

echo "==> Checking Loki is reachable on the host-only bridge"
curl -fsS --max-time 3 http://172.28.0.1:3100/ready || { echo "Loki not ready; run: docker compose up -d"; exit 1; }
echo

echo "==> Namespaces + workloads"
$K apply -f kubernetes/namespace.yaml
$K apply -f kubernetes/workload.yaml

echo "==> Grafana Alloy (Helm chart grafana/alloy $ALLOY_CHART_VERSION)"
$H repo add grafana https://grafana.github.io/helm-charts >/dev/null 2>&1 || true
$H repo update grafana >/dev/null
$H upgrade --install alloy grafana/alloy --version "$ALLOY_CHART_VERSION" \
  --namespace monitoring -f kubernetes/alloy-values.yaml

echo "==> Waiting for rollouts"
$K rollout status -n devtrails deploy/blog-indexer --timeout=180s
$K rollout status -n devtrails deploy/learner-simulator --timeout=180s
$K rollout status -n monitoring ds/alloy --timeout=180s
$K get pods -n devtrails -o wide
$K get pods -n monitoring -o wide
