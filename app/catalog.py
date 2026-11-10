"""DevTrails content catalog: topics, each with a series of blog posts.

The catalog is content (like a CMS export), not observability data. Every metric the
app exposes comes from real requests handled at runtime.

Inline formatting in paragraphs: `code` and **bold** (rendered by the `md` filter).
"""

import math

AUTHOR = {"name": "DevTrails Editorial", "initials": "DT"}

TOPICS = [
    # ------------------------------------------------------------------ Kubernetes
    {
        "slug": "kubernetes",
        "name": "Kubernetes",
        "badge": "K8s",
        "accent": "#326ce5",
        "tagline": "From your first Pod to observable, production-grade clusters.",
        "level": "Beginner → Advanced",
        "posts": [
            {
                "slug": "what-is-a-pod",
                "title": "What Is a Pod, Really?",
                "level": "Beginner",
                "date": "2026-09-02",
                "summary": "Kubernetes schedules Pods, not containers. Here is what a Pod shares, why it is disposable, and how its lifecycle works.",
                "takeaways": [
                    "A Pod is the smallest deployable unit: one or more containers that share a network namespace and can share volumes.",
                    "Containers in the same Pod talk to each other over `localhost`.",
                    "Pods are not self-healing. Controllers such as Deployments replace them.",
                ],
                "sections": [
                    {"h": "One IP, many containers", "p": [
                        "A Pod wraps one or more containers that are always scheduled together on the same node. They share a single network namespace, so every container in the Pod has the same IP address and port space and can reach the others on `localhost`.",
                        "Containers can also share data through volumes declared at the Pod level, for example an `emptyDir` written by one container and read by another. This is how the **sidecar** pattern works: a helper container, such as a log shipper or proxy, runs next to the main application.",
                    ]},
                    {"h": "Pods are disposable", "p": [
                        "A Pod is never rescheduled to a different node. If its node fails or the Pod is evicted, it is gone, and a controller (a Deployment, StatefulSet or DaemonSet) creates a **new** Pod with a new name and IP to replace it. That is why you rarely create bare Pods in production, and why clients should talk to a Service rather than a Pod IP.",
                    ]},
                    {"h": "Lifecycle phases and init containers", "p": [
                        "`status.phase` is one of `Pending`, `Running`, `Succeeded`, `Failed` or `Unknown`. A Pod stays `Pending` while it waits for scheduling or image pulls.",
                        "**Init containers** run one after another, each to completion, before any app container starts. They are a clean place for setup work such as waiting for a dependency or rendering a config file.",
                    ], "code": "kubectl run hello --image=nginx --restart=Never\nkubectl get pod hello -o wide\nkubectl describe pod hello      # events, IP, node, container states\nkubectl delete pod hello"},
                ],
            },
            {
                "slug": "deployments-and-rolling-updates",
                "title": "Deployments and Rolling Updates",
                "level": "Beginner",
                "date": "2026-09-09",
                "summary": "How a Deployment uses ReplicaSets to roll out a new version gradually, and how to roll back when it goes wrong.",
                "takeaways": [
                    "A Deployment manages ReplicaSets, and each ReplicaSet manages identical Pods.",
                    "Changing the Pod template triggers a rollout, which creates a new ReplicaSet.",
                    "`maxSurge` and `maxUnavailable` (both 25% by default) control the pace of a rollout.",
                ],
                "sections": [
                    {"h": "Desired state, continuously reconciled", "p": [
                        "You declare how many replicas you want and what each Pod looks like (`spec.template`). The Deployment controller creates a ReplicaSet for that template, and the ReplicaSet keeps the requested number of Pods running, replacing any that disappear.",
                    ]},
                    {"h": "How a rolling update works", "p": [
                        "Changing anything in the Pod template, such as the image tag, creates a new ReplicaSet. The controller then scales the new one up and the old one down step by step. With the default `RollingUpdate` strategy, `maxSurge: 25%` allows extra Pods above the desired count and `maxUnavailable: 25%` limits how many can be missing at any moment.",
                        "Readiness probes matter here. A new Pod only counts as available once it is Ready, so a broken release with failing probes stalls the rollout instead of taking down every replica.",
                    ]},
                    {"h": "Rolling back", "p": [
                        "Old ReplicaSets are kept (scaled to zero) up to `revisionHistoryLimit`, which defaults to 10. `kubectl rollout undo` scales the previous one back up.",
                    ], "code": "kubectl create deployment web --image=nginx:1.26 --replicas=3\nkubectl set image deployment/web nginx=nginx:1.27\nkubectl rollout status deployment/web\nkubectl rollout history deployment/web\nkubectl rollout undo deployment/web"},
                ],
            },
            {
                "slug": "services-and-cluster-dns",
                "title": "Services and Cluster DNS",
                "level": "Intermediate",
                "date": "2026-09-16",
                "summary": "Pods come and go, but Services give them a stable virtual IP and DNS name. Here are ClusterIP, NodePort and LoadBalancer in plain terms.",
                "takeaways": [
                    "A Service selects Pods by label and load-balances to the Ready ones.",
                    "`ClusterIP` is the default. `NodePort` uses ports 30000–32767 by default.",
                    "DNS name: `<service>.<namespace>.svc.cluster.local`.",
                ],
                "sections": [
                    {"h": "Selectors and endpoints", "p": [
                        "A Service has a label selector. Kubernetes continuously tracks the Ready Pods matching it in **EndpointSlices**, and kube-proxy (iptables or IPVS mode) programs every node so traffic to the Service's virtual IP is spread across those Pods.",
                    ]},
                    {"h": "The three common types", "p": [
                        "`ClusterIP` (default) is reachable only inside the cluster. `NodePort` additionally opens the same port on every node, from 30000–32767 by default. `LoadBalancer` asks the cloud provider for an external load balancer that forwards to the node ports.",
                    ]},
                    {"h": "Finding a Service by name", "p": [
                        "CoreDNS gives every Service an A record. From the same namespace the short name `web` works. From elsewhere use `web.<namespace>` or the fully qualified `web.<namespace>.svc.cluster.local`.",
                    ], "code": "kubectl expose deployment web --port=80\nkubectl get endpointslices -l kubernetes.io/service-name=web\nkubectl run -it dns-test --image=busybox:1.36 --rm --restart=Never -- nslookup web"},
                ],
            },
            {
                "slug": "pod-logs-with-alloy-and-loki",
                "title": "Shipping Pod Logs with Alloy and Loki",
                "level": "Advanced",
                "date": "2026-09-23",
                "summary": "Where container logs actually live on a node, and how Grafana Alloy turns them into searchable, labelled streams in Loki.",
                "takeaways": [
                    "Container stdout and stderr land in `/var/log/pods/` in CRI format on each node.",
                    "Loki indexes labels, not log content, so keep labels low-cardinality.",
                    "Use stream selectors first, then filter with `|=`, `|~` or `| json`.",
                ],
                "sections": [
                    {"h": "Where the logs live", "p": [
                        "Applications should write to stdout and stderr. The container runtime stores each line in `/var/log/pods/<namespace>_<pod>_<uid>/<container>/0.log` in **CRI format**: a timestamp, the stream (`stdout` or `stderr`), a partial-line flag and the message. `kubectl logs` reads these same files through the kubelet, and the files are rotated, so they are not long-term storage.",
                    ]},
                    {"h": "The collector pipeline", "p": [
                        "Grafana Alloy runs as a DaemonSet, so there is one Alloy Pod per node. It discovers Pods through the Kubernetes API, turns metadata such as namespace, pod and container into labels, tails the matching files, parses the CRI format (keeping `stream` as a label) and pushes the result to Loki.",
                        "Loki only indexes labels, and the log text is compressed into chunks. Never use unbounded values like user IDs or request IDs as labels. Filter for them at query time instead.",
                    ]},
                    {"h": "Querying with LogQL", "p": [
                        "Start with a stream selector in braces, then narrow it with line filters or parsers. Wrapping a query in `count_over_time` turns logs into a metric you can graph or alert on.",
                    ], "code": '{namespace="devtrails"}\n{namespace="devtrails", stream="stderr"}\n{namespace="devtrails"} |= "ERROR" | json | line_format "{{.pod}} {{.msg}}"\nsum by (pod) (count_over_time({namespace="devtrails"}[1m]))'},
                ],
            },
        ],
    },
    # ------------------------------------------------------------------ Docker
    {
        "slug": "docker",
        "name": "Docker",
        "badge": "DKR",
        "accent": "#1d91e6",
        "tagline": "Images, containers and Compose, without the magic.",
        "level": "Beginner → Intermediate",
        "posts": [
            {
                "slug": "images-layers-and-build-cache",
                "title": "Images, Layers and the Build Cache",
                "level": "Beginner",
                "date": "2026-08-12",
                "summary": "Why the order of the instructions in your Dockerfile decides whether a rebuild takes 3 seconds or 3 minutes.",
                "takeaways": [
                    "`RUN`, `COPY` and `ADD` create filesystem layers. Most other instructions only add metadata.",
                    "When one layer's cache is invalidated, every layer after it is rebuilt.",
                    "Copy dependency manifests and install them before copying the source code.",
                ],
                "sections": [
                    {"h": "Layers are stacked diffs", "p": [
                        "An image is an ordered stack of read-only layers. Every `RUN`, `COPY` or `ADD` adds a layer containing the filesystem changes it made, while instructions like `ENV`, `EXPOSE` and `CMD` only change image configuration. A running container adds one thin writable layer on top.",
                    ]},
                    {"h": "How the cache decides", "p": [
                        "BuildKit reuses a cached layer when the instruction and its inputs are unchanged. For `COPY`, that means the checksums of the copied files. Once one step misses the cache, **all following steps** run again. So put things that rarely change (base image, system packages, dependency install) first and things that change constantly (your source code) last.",
                    ], "code": "FROM python:3.12-slim\nWORKDIR /srv\nCOPY requirements.txt .          # changes rarely: cached\nRUN pip install --no-cache-dir -r requirements.txt\nCOPY . .                         # changes often: only this layer rebuilds\nCMD [\"python\", \"app.py\"]"},
                    {"h": "Multi-stage builds", "p": [
                        "Use one stage with compilers and build tools, then `COPY --from=build` only the finished artifacts into a small runtime stage. The final image stays small and has less attack surface.",
                    ]},
                ],
            },
            {
                "slug": "compose-volumes-networks-healthchecks",
                "title": "Compose: Volumes, Networks and Health Checks",
                "level": "Intermediate",
                "date": "2026-08-19",
                "summary": "Everything a multi-service stack needs: durable data, service discovery, startup ordering and private ports.",
                "takeaways": [
                    "Services on the same Compose network reach each other by service name.",
                    "Named volumes survive `docker compose down`. Only `down -v` deletes them.",
                    "Publish internal tools on `127.0.0.1` only, because Docker's port rules bypass ufw.",
                ],
                "sections": [
                    {"h": "Networks and service discovery", "p": [
                        "Compose creates a default network for the project, and Docker's embedded DNS resolves each **service name** to its container. That is why Prometheus can scrape `app:8000` without knowing any IP addresses.",
                    ]},
                    {"h": "Durable data with named volumes", "p": [
                        "A named volume is managed by Docker and lives independently of any container, so recreating or upgrading a container keeps its data. A bind mount (`./config:/etc/app:ro`) maps a host path instead, which is ideal for read-only configuration files.",
                    ]},
                    {"h": "Ports, health checks and ordering", "p": [
                        "`ports: \"3000:3000\"` listens on **all** host interfaces, and Docker inserts its own iptables rules, so ufw does not block it. Write `\"127.0.0.1:3000:3000\"` for anything that should stay private.",
                        "A `healthcheck` lets Docker mark a container healthy or unhealthy, and `depends_on` with `condition: service_healthy` delays dependants until it passes.",
                    ], "code": "services:\n  grafana:\n    image: grafana/grafana:12.1.1\n    ports: [\"127.0.0.1:3000:3000\"]\n    volumes: [grafana-data:/var/lib/grafana]\n    restart: unless-stopped\nvolumes:\n  grafana-data:"},
                ],
            },
            {
                "slug": "container-security-basics",
                "title": "Container Security Basics",
                "level": "Intermediate",
                "date": "2026-08-26",
                "summary": "Four habits that remove most container risk: non-root users, fewer capabilities, read-only filesystems and no baked-in secrets.",
                "takeaways": [
                    "Set `USER` to a non-root UID in the image.",
                    "Drop all capabilities and add back only the ones you need.",
                    "Secrets in `ENV` or `ARG` stay visible in the image metadata and history.",
                ],
                "sections": [
                    {"h": "Do not run as root", "p": [
                        "Processes in a container run as root by default unless the image sets `USER`. Create a dedicated user in the Dockerfile and switch to it, so a compromised process has far less power, especially if a container escape bug exists.",
                    ]},
                    {"h": "Shrink what a process can do", "p": [
                        "`--cap-drop=ALL` removes Linux capabilities, and `--cap-add` restores only the ones you need, such as `NET_BIND_SERVICE` for ports below 1024. `--read-only` makes the root filesystem immutable. Mount a `tmpfs` where the app genuinely needs to write.",
                    ], "code": "docker run --rm --read-only --cap-drop=ALL --user 10001:10001 alpine id"},
                    {"h": "Keep secrets out of images", "p": [
                        "Anyone who pulls an image can read values passed through `ENV` or `ARG` with `docker history` or `docker inspect`. Inject secrets at runtime through environment files that are kept out of git, or through an orchestrator's secret store. For build-time secrets, use BuildKit's `RUN --mount=type=secret`.",
                    ]},
                ],
            },
        ],
    },
    # ------------------------------------------------------------------ Linux
    {
        "slug": "linux",
        "name": "Linux for DevOps",
        "badge": "LNX",
        "accent": "#d99a06",
        "tagline": "The shell skills every operator leans on daily.",
        "level": "Beginner",
        "posts": [
            {
                "slug": "reading-memory-correctly",
                "title": "Reading Linux Memory Correctly",
                "level": "Beginner",
                "date": "2026-07-08",
                "summary": "Why low \"free\" memory is usually fine, and which number to watch.",
                "takeaways": [
                    "Linux uses spare RAM as page cache, so `free` looks low on a healthy system.",
                    "Watch `available`, the kernel's estimate of memory usable without swapping.",
                    "RAM usage % = `1 - MemAvailable / MemTotal`.",
                ],
                "sections": [
                    {"h": "Free memory is wasted memory", "p": [
                        "The kernel keeps recently read files in the **page cache** so the next read comes from RAM instead of disk. That memory shows up under `buff/cache`, and most of it can be reclaimed the moment an application needs it. A small `free` column is therefore normal.",
                    ]},
                    {"h": "Use the available column", "p": [
                        "`available` (`MemAvailable` in `/proc/meminfo`, added in kernel 3.14) estimates how much memory new workloads can use without swapping, including reclaimable cache. It is the right input for dashboards and alerts, and it is exactly what node_exporter exposes as `node_memory_MemAvailable_bytes`.",
                    ], "code": "free -h\ngrep -E 'MemTotal|MemAvailable' /proc/meminfo\n# PromQL equivalent:\n# 100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)"},
                ],
            },
            {
                "slug": "load-average-explained",
                "title": "Load Average, Explained",
                "level": "Beginner",
                "date": "2026-07-15",
                "summary": "What the three numbers from uptime measure on Linux, and how to tell whether they are high.",
                "takeaways": [
                    "The three numbers are 1-, 5- and 15-minute exponentially damped averages.",
                    "Linux counts runnable tasks **and** tasks in uninterruptible sleep (state D).",
                    "Compare load with the number of CPUs (`nproc`), not with a fixed value.",
                ],
                "sections": [
                    {"h": "What is counted", "p": [
                        "On Linux, load average tracks the number of tasks that are runnable (running or waiting for a CPU) **plus** tasks in uninterruptible sleep, which are usually waiting on disk or network storage I/O. So high load does not always mean a busy CPU. It can also mean a slow disk.",
                    ]},
                    {"h": "Is it high?", "p": [
                        "Divide by the CPU count. A load of 4 on a 16-core machine is light, while a load of 4 on one core means tasks are queueing. If the 1-minute value is far above the 15-minute value, load is rising. Check `vmstat 1`: high `wa` points to I/O, while high `us` or `sy` points to CPU.",
                    ], "code": "uptime\nnproc\ncat /proc/loadavg\nvmstat 1 5"},
                ],
            },
            {
                "slug": "df-vs-du",
                "title": "df vs du: Why the Numbers Disagree",
                "level": "Beginner",
                "date": "2026-07-22",
                "summary": "Your disk shows full but du cannot find the files. Here are the three usual reasons.",
                "takeaways": [
                    "`df` asks the filesystem, while `du` walks directories and adds up file sizes.",
                    "Deleted files that a process still holds open use space but are invisible to `du`.",
                    "ext4 reserves 5% of blocks for root by default, and `df`'s Use% excludes them.",
                ],
                "sections": [
                    {"h": "Two different questions", "p": [
                        "`df` reports used and available blocks straight from the filesystem's superblock. `du` walks a directory tree and sums the sizes of the files it can see. Most of the time the results agree, and when they do not, the cause is usually one of the following.",
                    ]},
                    {"h": "The usual suspects", "p": [
                        "**Deleted but still open.** A log file deleted while a process keeps writing to it still uses space. Find it with `lsof +L1` and restart that process.",
                        "**Reserved blocks.** ext4 keeps 5% of blocks for root by default. `df` shows Use% as used / (used + available), so the reserved space is in neither number.",
                        "**Mounts hiding files.** Data written to a directory before something was mounted on top of it is invisible to `du`.",
                    ], "code": "df -h /\ndf -i /                          # inode usage\nsudo du -xh --max-depth=1 / | sort -h | tail\nsudo lsof +L1                    # deleted-but-open files"},
                ],
            },
        ],
    },
    # ------------------------------------------------------------------ Observability
    {
        "slug": "observability",
        "name": "Observability",
        "badge": "OBS",
        "accent": "#e8590c",
        "tagline": "Metrics, logs and alerts that tell you the truth.",
        "level": "Intermediate → Advanced",
        "posts": [
            {
                "slug": "prometheus-fundamentals",
                "title": "Prometheus Fundamentals",
                "level": "Intermediate",
                "date": "2026-10-07",
                "summary": "The pull model, the four metric types and the label-cardinality trap.",
                "takeaways": [
                    "Prometheus scrapes HTTP `/metrics` endpoints on an interval.",
                    "There are four metric types: counter, gauge, histogram and summary.",
                    "Every unique label combination is a separate time series, so keep labels bounded.",
                ],
                "sections": [
                    {"h": "Pull, not push", "p": [
                        "Prometheus scrapes each target's `/metrics` endpoint on a fixed interval (15s is a common choice) and stores the samples in its local time-series database. For every target it also records a synthetic `up` metric: `1` if the scrape succeeded and `0` if it failed. That gives you target-down alerting for free.",
                    ]},
                    {"h": "Choosing a metric type", "p": [
                        "A **counter** only goes up (it resets on restart), for example requests served. A **gauge** goes up and down, for example memory in use or in-flight requests. A **histogram** counts observations into configurable buckets (`_bucket`, `_sum`, `_count`), and its buckets can be aggregated across instances to compute percentiles. A **summary** computes quantiles on the client, which cannot be meaningfully aggregated.",
                    ]},
                    {"h": "Watch your labels", "p": [
                        "Each distinct set of label values creates a new series. Labelling HTTP metrics with the raw URL (`/blogs/123`, `/blogs/124`, and so on) lets the series count grow without limit. Use the route template (`/blogs/<slug>`) instead, and keep values like user IDs out of labels entirely.",
                    ], "code": "curl -s localhost:8000/metrics | grep '^devtrails_http_requests_total'"},
                ],
            },
            {
                "slug": "promql-rate-sum-histogram-quantile",
                "title": "PromQL Essentials: rate, sum, histogram_quantile",
                "level": "Advanced",
                "date": "2026-10-14",
                "summary": "Build requests per second, error ratio and p95 latency from first principles, in the right order.",
                "takeaways": [
                    "`rate()` gives the per-second average increase of a counter and handles resets.",
                    "Apply `rate()` first and aggregate with `sum` afterwards, never the reverse.",
                    "For percentiles, use `histogram_quantile(0.95, sum by (le) (rate(..._bucket[5m])))`.",
                ],
                "sections": [
                    {"h": "rate() turns counters into speeds", "p": [
                        "A raw counter value is rarely useful. `rate(x[5m])` computes the per-second average increase over the last five minutes and corrects for counter resets. Make the range at least four times the scrape interval so every window contains enough samples. Grafana's `$__rate_interval` does this automatically.",
                    ]},
                    {"h": "Rate first, then sum", "p": [
                        "Always `sum(rate(...))`, never `rate(sum(...))`. Summing raw counters first hides each series' individual reset and produces nonsense spikes. Error ratio follows the same rule: the rate of 5xx responses divided by the rate of all responses.",
                    ], "code": "sum(rate(devtrails_http_requests_total[5m]))\n\nsum(rate(devtrails_http_requests_total{status=~\"5..\"}[5m]))\n  / sum(rate(devtrails_http_requests_total[5m]))"},
                    {"h": "Percentiles from histograms", "p": [
                        "Take the rate of every bucket, sum them by `le` (the bucket's upper bound) and let `histogram_quantile` interpolate. The result is an estimate whose accuracy depends on where your bucket bounds sit, so put buckets near your SLO threshold.",
                    ], "code": "histogram_quantile(0.95,\n  sum by (le) (rate(devtrails_http_request_duration_seconds_bucket[5m])))"},
                ],
            },
            {
                "slug": "grafana-alerting-that-works",
                "title": "Grafana Alerting That Pages the Right Person",
                "level": "Advanced",
                "date": "2026-10-21",
                "summary": "Rules, pending periods, contact points and notification policies, with email delivered over SMTP.",
                "takeaways": [
                    "Alert on symptoms users feel, such as error rate and latency, not on every cause.",
                    "A pending period keeps a rule from firing on a single bad evaluation.",
                    "Keep SMTP credentials in environment variables, never in the repository.",
                ],
                "sections": [
                    {"h": "Anatomy of a rule", "p": [
                        "A Grafana-managed rule runs one or more queries, then **expressions** (reduce, math or threshold) that produce the condition. It is evaluated on an interval. When the condition is true, the alert goes from **Normal** to **Pending**, and if it stays true for the whole pending period (`for`), it goes to **Firing**. Separate settings decide what happens on *No data* and *Error*.",
                    ]},
                    {"h": "Routing notifications", "p": [
                        "A **contact point** says how to notify, for example an email address list. A **notification policy** decides which alerts go to which contact point and how they are batched. `group_wait` holds the first notification briefly to collect related alerts, `group_interval` spaces out updates for the same group, and `repeat_interval` controls re-sends while an alert keeps firing.",
                    ]},
                    {"h": "Email over SMTP", "p": [
                        "Grafana sends email through the `[smtp]` settings, which you can supply as `GF_SMTP_*` environment variables so passwords never land in git. Test the contact point from the UI before relying on it, and remember that many cloud providers throttle outbound port 25, so use 587 with STARTTLS.",
                    ], "code": "GF_SMTP_ENABLED=true\nGF_SMTP_HOST=smtp.gmail.com:587\nGF_SMTP_USER=${SMTP_USER}\nGF_SMTP_PASSWORD=${SMTP_PASSWORD}\nGF_SMTP_FROM_ADDRESS=${SMTP_FROM_ADDRESS}"},
                ],
            },
        ],
    },
    # ------------------------------------------------------------------ CI/CD
    {
        "slug": "cicd",
        "name": "CI/CD",
        "badge": "CI",
        "accent": "#2f9e44",
        "tagline": "Ship small, ship often, ship safely.",
        "level": "Intermediate",
        "posts": [
            {
                "slug": "designing-a-pipeline",
                "title": "Designing a Delivery Pipeline",
                "level": "Intermediate",
                "date": "2026-06-03",
                "summary": "Fast feedback first, one immutable artifact, and promotion instead of rebuilds.",
                "takeaways": [
                    "Order stages from fastest and cheapest to slowest.",
                    "Build an artifact once, tag it immutably and promote that same artifact.",
                    "Pin tool and base-image versions so builds are reproducible.",
                ],
                "sections": [
                    {"h": "Fail fast", "p": [
                        "Put linting and unit tests first, because they take seconds and catch most mistakes. Integration tests, image scans and end-to-end suites come later. A developer should hear about a typo in under a minute, not after a 20-minute pipeline.",
                    ]},
                    {"h": "Build once, promote many times", "p": [
                        "Build the container image once and tag it with the commit SHA. Staging and production then deploy **that exact image**. Rebuilding per environment risks shipping something you never tested, because base images and dependencies drift between builds.",
                    ], "code": "docker build -t registry.example.com/app:${GIT_SHA} .\ndocker push registry.example.com/app:${GIT_SHA}\n# deploy the same tag to staging, then production"},
                ],
            },
            {
                "slug": "github-actions-from-zero",
                "title": "GitHub Actions from Zero",
                "level": "Intermediate",
                "date": "2026-06-10",
                "summary": "Workflows, jobs, steps, secrets and caching: a minimal but real CI workflow.",
                "takeaways": [
                    "Workflows live in `.github/workflows/*.yml` and are started by `on:` events.",
                    "Jobs run in parallel by default. Use `needs:` to order them.",
                    "Prefer OIDC (`permissions: id-token: write`) to long-lived cloud keys.",
                ],
                "sections": [
                    {"h": "The building blocks", "p": [
                        "A **workflow** is triggered by events such as `push` or `pull_request`. It contains **jobs**, each running on a fresh runner, and each job runs **steps** in order. A step either runs shell commands with `run:` or uses a published action with `uses:`.",
                    ], "code": "name: ci\non: [push, pull_request]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-python@v5\n        with:\n          python-version: \"3.12\"\n          cache: pip\n      - run: pip install -r requirements.txt\n      - run: pytest -q"},
                    {"h": "Secrets and cloud access", "p": [
                        "Read repository secrets with `${{ secrets.NAME }}`. GitHub masks their values in logs. For AWS and other clouds, OpenID Connect lets a job exchange a short-lived GitHub token for temporary cloud credentials, so there is no stored access key to leak.",
                    ]},
                ],
            },
            {
                "slug": "canary-and-blue-green",
                "title": "Canary and Blue-Green Releases",
                "level": "Advanced",
                "date": "2026-06-17",
                "summary": "Limit the blast radius of a bad release, and let your metrics decide when to proceed.",
                "takeaways": [
                    "A canary sends a small share of traffic to the new version first.",
                    "Blue-green keeps two full environments and switches traffic between them in one step.",
                    "Gate each step on error rate and latency, and roll back automatically.",
                ],
                "sections": [
                    {"h": "Canary", "p": [
                        "Route a small slice of traffic, say 5%, to the new version and compare its error rate and p95 latency with the stable version. If the numbers hold, increase the share step by step. If they do not, shift everything back. Only a few users ever see the bad build.",
                    ]},
                    {"h": "Blue-green", "p": [
                        "Run the new version (green) next to the current one (blue), test it in place, then switch the router or load balancer to green all at once. Rollback is the same switch in reverse. The cost is running two environments during the release, and database schema changes must stay compatible with both.",
                    ]},
                ],
            },
        ],
    },
    # ------------------------------------------------------------------ AWS
    {
        "slug": "cloud",
        "name": "AWS Cloud",
        "badge": "AWS",
        "accent": "#ff9900",
        "tagline": "Run real workloads on EC2, VPC and IAM.",
        "level": "Beginner → Intermediate",
        "posts": [
            {
                "slug": "ec2-essentials",
                "title": "EC2 Essentials",
                "level": "Beginner",
                "date": "2026-05-06",
                "summary": "AMIs, instance types, security groups and EBS: what you need before you launch, and how to reach private dashboards safely.",
                "takeaways": [
                    "Security groups are stateful: by default all inbound traffic is denied and all outbound is allowed.",
                    "EBS volumes persist independently of the instance. Instance store disks do not.",
                    "Reach internal UIs through an SSH tunnel instead of opening ports.",
                ],
                "sections": [
                    {"h": "Security groups", "p": [
                        "A security group is a stateful firewall attached to an instance's network interface. A new group has no inbound rules and allows all outbound traffic. Because it is stateful, responses to allowed outbound connections are let back in automatically. Open only what you need, typically SSH (22) from your own IP.",
                    ]},
                    {"h": "Storage", "p": [
                        "EBS volumes are network block devices that live independently of the instance and can be snapshotted. The root volume is deleted on termination by default. **Instance store** disks are physically attached and fast, but their data is lost when the instance stops or terminates.",
                    ]},
                    {"h": "Private dashboards over SSH", "p": [
                        "Keep Grafana and Prometheus bound to `127.0.0.1` on the instance and forward them to your laptop with an SSH tunnel. Nothing new is exposed to the internet.",
                    ], "code": "ssh -i key.pem -L 3000:127.0.0.1:3000 ubuntu@<ec2-public-ip>\n# then open http://localhost:3000 locally"},
                ],
            },
            {
                "slug": "vpc-networking",
                "title": "VPC Networking in One Diagram",
                "level": "Intermediate",
                "date": "2026-05-13",
                "summary": "Subnets, route tables, internet gateways and NAT, and what actually makes a subnet public.",
                "takeaways": [
                    "A subnet is public if its route table sends `0.0.0.0/0` to an internet gateway.",
                    "Private subnets reach the internet outbound through a NAT gateway.",
                    "Network ACLs are stateless and evaluated in rule-number order. Security groups are stateful.",
                ],
                "sections": [
                    {"h": "Public vs private is a routing decision", "p": [
                        "Nothing about a subnet is inherently public. A subnet is public when its route table has a default route (`0.0.0.0/0`) to an **internet gateway**, and its instances also need a public IP. A private subnet's default route points at a **NAT gateway** that sits in a public subnet, which allows outbound connections only.",
                    ]},
                    {"h": "Two layers of filtering", "p": [
                        "**Security groups** apply per network interface, are stateful and only contain allow rules. **Network ACLs** apply per subnet, are stateless (you must allow return traffic explicitly) and are evaluated in ascending rule-number order, where the first match wins. AWS also reserves five IP addresses in every subnet.",
                    ], "code": "aws ec2 describe-route-tables --filters Name=vpc-id,Values=<vpc-id> \\\n  --query 'RouteTables[].Routes[]'"},
                ],
            },
            {
                "slug": "iam-least-privilege",
                "title": "IAM and Least Privilege",
                "level": "Intermediate",
                "date": "2026-05-20",
                "summary": "Users, roles and policies, and why an instance role beats an access key on disk.",
                "takeaways": [
                    "Everything is denied unless a policy allows it, and an explicit Deny always wins.",
                    "Roles provide temporary credentials through STS. Prefer them to long-lived keys.",
                    "Grant the specific actions and resources a workload needs, nothing more.",
                ],
                "sections": [
                    {"h": "How AWS evaluates a request", "p": [
                        "By default, every request is implicitly denied. An identity or resource policy must explicitly allow the action, and any applicable **explicit Deny** overrides every Allow. Start narrow, with specific actions on specific ARNs, and widen only when something legitimately fails.",
                    ]},
                    {"h": "Roles over keys", "p": [
                        "Attach an IAM role to an EC2 instance through an instance profile, and the SDKs and CLI automatically receive short-lived credentials from the instance metadata service. There is no access key on disk to leak or rotate. `aws sts get-caller-identity` shows which identity you are actually using.",
                    ], "code": "aws sts get-caller-identity"},
                ],
            },
        ],
    },
]

PLANS = {
    "free": {"name": "Reader", "price": 0, "perks": ["All public posts", "Weekly digest email"]},
    "pro": {"name": "Pro", "price": 19, "perks": ["Hands-on lab guides", "Downloadable cheat sheets", "Track certificate"]},
    "team": {"name": "Team", "price": 79, "perks": ["Everything in Pro", "5 seats", "Progress reports"]},
}


def _reading_minutes(post):
    words = len(post["summary"].split())
    for s in post["sections"]:
        words += sum(len(p.split()) for p in s["p"]) + len(s.get("code", "").split())
    words += sum(len(t.split()) for t in post["takeaways"])
    return max(2, math.ceil(words / 200))


TOPICS_BY_SLUG = {t["slug"]: t for t in TOPICS}
POSTS_BY_SLUG = {}
for _t in TOPICS:
    for _i, _p in enumerate(_t["posts"], 1):
        _p["topic"] = _t["slug"]
        _p["part"] = _i
        _p["minutes"] = _reading_minutes(_p)
        _p["anchors"] = [
            "".join(c if c.isalnum() else "-" for c in s["h"].lower()).strip("-") for s in _p["sections"]
        ]
        POSTS_BY_SLUG[_p["slug"]] = _p


def all_posts():
    """Newest first."""
    return sorted(POSTS_BY_SLUG.values(), key=lambda p: p["date"], reverse=True)
