# PromQL reference: what each query means

All queries are used in the *DevTrails · Host & Application Overview* dashboard or the alert rules.
`$__rate_interval` is Grafana's automatic window (≥ 4 × scrape interval = 1m).

## Host (node_exporter)

| Signal | PromQL | Explanation | Cross-check |
|---|---|---|---|
| CPU busy % | `100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])))` | `node_cpu_seconds_total` is a per-core counter of seconds spent in each mode. `rate()` of the idle counter is the idle fraction per core. Averaging over cores and subtracting from 1 gives the busy share. | `top` / `vmstat 1` (100 − id) |
| RAM used % | `100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)` | *MemAvailable* is the kernel's estimate of memory available without swapping (it counts reclaimable cache), the same figure as `free`'s *available* column. | `free -m`: `1 - available/total` |
| Disk used % (/) | `100 * (1 - node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"})` | Space available to unprivileged users over total size. | `df -h /`. `df` excludes root-reserved blocks from the denominator, so it reads a few points lower. |
| Network throughput | `sum by (device) (rate(node_network_receive_bytes_total[1m]))` (and `transmit`) | Bytes per second per NIC. Virtual interfaces (veth, cali, docker bridges) are excluded at the exporter. | `ip -s link`, `ifstat` |
| Uptime | `time() - node_boot_time_seconds` | Current time minus boot timestamp. | `uptime`, `cat /proc/uptime` |

## Application (DevTrails)

| Signal | PromQL | Explanation |
|---|---|---|
| Requests / second | `sum(rate(devtrails_http_requests_total[1m]))` | Counter of handled requests, labelled `method`, `route` (Flask URL template, which keeps cardinality bounded) and `status`. |
| Requests / second by route | `sum by (method, route) (rate(devtrails_http_requests_total[1m]))` | Same counter, split by route. |
| Error / failure rate % | `100 * sum(rate(devtrails_http_requests_total{status=~"5.."}[1m])) / sum(rate(devtrails_http_requests_total[1m]))` | Share of responses that are server errors. 4xx (client mistakes) are excluded on purpose. |
| Order failure rate % | `100 * sum(rate(devtrails_orders_total{result="failed"}[5m])) / sum(rate(devtrails_orders_total[5m]))` | Business-level failure ratio. |
| p95 latency | `histogram_quantile(0.95, sum by (le) (rate(devtrails_http_request_duration_seconds_bucket[5m])))` | Per-bucket rate of the latency histogram, summed across routes by bucket bound `le`. The 95th percentile is interpolated within buckets. |
| p95 latency per route | `histogram_quantile(0.95, sum by (le, route) (rate(devtrails_http_request_duration_seconds_bucket[5m])))` | Keep `route` in the `by` clause. |
| Enrollments (business event) | `sum(increase(devtrails_orders_total{result="success"}[1h]))` | Successful `POST /api/orders` in the last hour. |
| Revenue | `sum(increase(devtrails_order_revenue_dollars_total[1h]))` | Dollars from successful paid enrollments. |

## Metric catalogue exposed at `/metrics`

| Metric | Type | Labels | Unit |
|---|---|---|---|
| `devtrails_http_requests_total` | counter | method, route, status | requests |
| `devtrails_http_request_duration_seconds` | histogram | method, route | seconds (buckets 5ms to 5s) |
| `devtrails_http_requests_in_progress` | gauge | none | requests |
| `devtrails_orders_total` | counter | topic, plan, result | orders |
| `devtrails_order_revenue_dollars_total` | counter | plan | USD |
| `devtrails_post_views_total` | counter | topic | post reads |
| `devtrails_chaos_error_ratio` | gauge | none | ratio 0 to 1 |
| `devtrails_app_info` | info | version | none |
