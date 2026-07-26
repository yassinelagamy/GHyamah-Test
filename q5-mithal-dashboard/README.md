# Q5 — Monitoring dashboard for mithal.space

A single container that continuously measures the availability and performance of
**https://mithal.space** and serves a live dashboard of the results on port 8080.

```
q5-mithal-dashboard/
├── collector/
│   ├── collect.py             # measures latency, uptime, DNS, TLS, search — every 60s
│   └── requirements.txt       # requests (pinned); everything else is stdlib
├── dashboard/
│   ├── index.html             # self-contained dashboard (Chart.js from CDN)
│   └── data/metrics.json      # rolling 48h JSON array, written by the collector
├── start.sh                   # entrypoint: collector in background + static server
├── Dockerfile
└── README.md
```

**Why `data/` lives inside `dashboard/`:** the dashboard directory *is* the web
root, so the page fetches `data/metrics.json` from its own origin. One container,
one port, no CORS, no API layer.

---

## 1. What is collected

Every 60 seconds `collector/collect.py` appends one record to the JSON array:

```json
{
  "ts": "2026-07-26T15:46:40.381676+00:00",
  "up": true,
  "code": 200,
  "latency_ms": 848.58,
  "dns_ms": 0.67,
  "ssl_days_left": 50,
  "search_ms": 1056.08
}
```

| Field | How it is measured |
|---|---|
| `latency_ms` | timed `GET https://mithal.space`, 10 s timeout, redirects followed |
| `up` | `true` when the status code is **200–399** |
| `code` | the HTTP status code — `null` when the connection itself failed |
| `dns_ms` | timed `socket.getaddrinfo("mithal.space", 443)` |
| `ssl_days_left` | TLS handshake to `mithal.space:443`, cert `notAfter` parsed → days remaining |
| `search_ms` | timed `GET https://mithal.space/search?q=test` (`null` if it errors or returns ≥ 400) |

Every measurement is independent: a failure records `null` for that field only and
never aborts the run or crashes the loop. Records older than **48 hours** are
pruned on each write, and the file is written atomically (temp file + rename) so
the dashboard never reads a half-written array.

**Configuration** — constants at the top of `collect.py`, all overridable by env var:

| Variable | Default | Meaning |
|---|---|---|
| `TARGET_URL` | `https://mithal.space` | site under test |
| `SEARCH_URL` | `https://mithal.space/search?q=test` | search endpoint to time |
| `INTERVAL_S` | `60` | seconds between collections |
| `TIMEOUT_S` | `10` | per-request timeout |
| `RETENTION_HOURS` | `48` | how much history to keep |
| `METRICS_FILE` | `dashboard/data/metrics.json` | output path |

---

## 2. Run locally (without Docker)

```bash
cd q5-mithal-dashboard
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r collector/requirements.txt
```

One-shot collection (useful as a smoke test or under cron):

```bash
python collector/collect.py --once
```

Continuous collection every 60 s — leave this running:

```bash
python collector/collect.py
```

In a second terminal, serve the dashboard (the `data/` directory must be inside
the served root, which it is):

```bash
cd q5-mithal-dashboard/dashboard && python -m http.server 8080
```

Open <http://localhost:8080/index.html>.

> Opening `index.html` straight from disk does **not** work — browsers block
> `fetch()` over `file://`. The page detects this and shows an explanatory banner
> instead of failing silently.

---

## 3. The dashboard

| Element | Detail |
|---|---|
| Status badge | green `UP` / red `DOWN` from the newest record, with HTTP code and timestamp |
| Uptime tile | `up_checks / total_checks × 100` over the **last 24 h**, one decimal |
| TLS card | "*X* days remaining" — green > 30, yellow 8–30, red ≤ 7 (`Expired` at ≤ 0) |
| Latest response | newest `latency_ms`, with `search_ms` and `dns_ms` underneath |
| Chart | `latency_ms` (solid blue) and `search_ms` (dashed purple) for the **last hour**; failed checks draw gaps, red points mark down checks |
| Table | last 10 checks — time, ✅/❌, code, latency, DNS, search |
| Refresh | re-fetches every 60 s; last-updated clock in the header |

Empty, missing, or corrupt data renders a "no data yet" state on every tile plus a
banner explaining what to do — it never throws.

To point the page elsewhere, edit the one constant at the top of the `<script>`:

```js
const DATA_URL = 'data/metrics.json';
```

---

## 4. Build the image

The container runs the collector in the background and serves the dashboard in the
foreground, both from one process tree (`start.sh`):

```bash
docker build -t mithal-monitor:latest ./q5-mithal-dashboard
```

```bash
docker run --rm -p 8080:8080 --name mithal-monitor mithal-monitor:latest
```

Open <http://localhost:8080/index.html>. The first record appears within a few
seconds of startup, then one per minute.

Image notes:

- `python:3.12-slim`, non-root user `appuser` (uid 10001) owning the served tree
  so the collector can write into it.
- `requirements.txt` installed before the code is copied, for layer caching.
- `start.sh` restarts the collector if it ever exits, and traps `SIGTERM`/`SIGINT`
  so the container stops promptly.
- `HEALTHCHECK` fetches the dashboard page itself.
- Metrics live inside the container's filesystem, so **history resets on redeploy**.
  That is intentional for this exercise; to keep history across restarts, mount a
  volume at `/app/dashboard/data` (this is exactly what Ghaymah Block Storage is
  for — see Q4).

---

## 5. Deploy to Ghaymah

Ghaymah deploys from a **public image URL**, so push the image to Docker Hub first.
Replace `<MY_DOCKERHUB_USER>` with your account name.

```bash
docker login
```

```bash
docker tag mithal-monitor:latest docker.io/<MY_DOCKERHUB_USER>/mithal-monitor:latest
```

```bash
docker push docker.io/<MY_DOCKERHUB_USER>/mithal-monitor:latest
```

> On Apple Silicon / ARM, build for the platform Ghaymah runs:
> ```bash
> docker buildx build --platform linux/amd64 -t docker.io/<MY_DOCKERHUB_USER>/mithal-monitor:latest --push ./q5-mithal-dashboard
> ```

Make sure the Docker Hub repository is **public** — Ghaymah pulls it anonymously.

Then, in the Ghaymah dashboard:

| Field | Value |
|---|---|
| Container Image URL | `docker.io/<MY_DOCKERHUB_USER>/mithal-monitor:latest` |
| Application Name | `mithal-monitor` |
| Port Number | `8080` (matches `EXPOSE`) |
| Public Access | **enabled** |
| Environment Variables | *(optional)* `INTERVAL_S=60`, `TARGET_URL=https://mithal.space`, `SEARCH_URL=https://mithal.space/search?q=test` |

Click **Deploy**, then open `<the public URL Ghaymah assigns>/index.html` and
screenshot the live dashboard. Leave it running so the 24 h uptime tile and the
hourly chart fill with real history before submission.

---

## 6. Local verification performed

Measured against the live site on 2026-07-26:

| Check | Result |
|---|---|
| `collect.py --once` against mithal.space | `UP code=200 latency=2693ms dns=7.07ms search=866ms ssl=50d` |
| 60 s loop (run at 6 s for testing) | 5 further records appended, pruning and atomic writes working |
| Failure path (unreachable host) | recorded `up:false` with `code/latency_ms/dns_ms/ssl_days_left/search_ms` all `null`, exit 0, no crash |
| Dashboard against real `metrics.json` | badge UP, uptime 100.0% (6/6), TLS card "50 days — Healthy" in green, chart with both series, 6-row table; no console errors |
| Dashboard with the data file removed | "no data yet" state on every tile + banner, no crash |
| `docker build` | **not run** — the local Docker daemon was not running; build with the command in §4 before pushing |

The `dashboard/data/metrics.json` in this repo holds those first real samples; the
collector prunes anything older than 48 h automatically.
