# Q1 — Deploy & Monitor an API on Ghaymah

A minimal FastAPI service, containerised and deployed on the **Ghaymah** container
platform, plus a polling monitor and a static dashboard that visualises its
availability, response time and request count.

```
q1-deploy-monitor/
├── app/
│   ├── main.py            # FastAPI app: /, /health, /metrics
│   ├── requirements.txt   # pinned fastapi + uvicorn
│   ├── Dockerfile         # python:3.12-slim, non-root, HEALTHCHECK
│   └── .dockerignore
├── monitor/
│   ├── monitor.py         # polls /health + /metrics every 30s (stdlib only)
│   └── data/checks.json   # created on first run — the dashboard's data source
├── dashboard/
│   └── index.html         # single self-contained page (Chart.js from CDN)
└── README.md
```

---

## 1. The API

| Method | Path | Response |
|---|---|---|
| `GET` | `/` | service name, version, endpoint list, start time |
| `GET` | `/health` | `{"status":"ok","uptime_s":12.34,"timestamp":"2026-07-26T15:36:50.283265+00:00"}` — HTTP 200 |
| `GET` | `/metrics` | `{"requests_total":42,"started_at":"<iso8601>"}` |
| `GET` | `/docs` | interactive OpenAPI docs (FastAPI built-in) |

`/health` performs **no** downstream checks (no DB, no network) — it reports
process liveness only, so a failing check always means "restart me", which is
exactly the signal an orchestrator's health probe should act on.

`/metrics` is backed by an in-memory counter incremented by an HTTP middleware on
every request. It is per-process and deliberately resets on restart — a counter
that drops to zero in the dashboard is a visible signal that the container was
restarted or redeployed.

Environment variables (all optional): `APP_NAME`, `APP_VERSION`, `RELEASE_SHA`,
and `PORT` (default `8080`). CI embeds the immutable Git commit in
`RELEASE_SHA`, and `/health` exposes it as `release` for deployment verification.

### Run locally without Docker

```bash
cd q1-deploy-monitor/app
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py            # or: uvicorn main:app --host 0.0.0.0 --port 8080
```

```bash
curl http://localhost:8080/health
```

---

## 2. Build and run the Docker image locally

```bash
docker build -t ghaymah-api:latest ./q1-deploy-monitor/app
```

```bash
docker run --rm -p 8080:8080 --name ghaymah-api ghaymah-api:latest
```

Verify:

```bash
curl -f http://localhost:8080/health && curl http://localhost:8080/metrics
```

Docker's own health probe (defined by `HEALTHCHECK` in the Dockerfile) shows up
after ~10s in `docker ps` as `(healthy)`:

```bash
docker ps --filter name=ghaymah-api
```

**Image design notes** (what the Dockerfile is doing and why):

- `python:3.12-slim` — small base, no build toolchain in the final image.
- `requirements.txt` is copied and installed **before** the application code, so
  editing `main.py` reuses the cached dependency layer instead of reinstalling
  FastAPI on every build.
- Runs as the non-root user `appuser` (uid 10001).
- `curl` is the only extra apt package, installed solely for the `HEALTHCHECK`;
  apt lists are removed in the same layer.
- `EXPOSE 8080` matches the port Ghaymah is configured with below.

---

## 3. Push the image and deploy on Ghaymah

Ghaymah deploys a container from a container image URL. This deployment uses
Docker Hub namespace `agamy74`.

### 3.1 Push to Docker Hub

```bash
docker login
```

```bash
docker tag ghaymah-api:latest docker.io/agamy74/ghaymah-api:latest
```

```bash
docker push docker.io/agamy74/ghaymah-api:latest
```

> Building on an Apple Silicon / ARM machine? Build for the platform Ghaymah runs
> (`linux/amd64`) or the container will fail to start:
> ```bash
> docker buildx build --platform linux/amd64 -t docker.io/agamy74/ghaymah-api:latest --push ./q1-deploy-monitor/app
> ```

Make sure the Docker Hub repository is **public** — Ghaymah pulls the image
anonymously from the URL you paste in.

### 3.2 Deploy on the Ghaymah dashboard

| Field | Value |
|---|---|
| Container Image URL | `docker.io/agamy74/ghaymah-api:<git-commit-sha>` |
| Application Name | `ghaymah-api` |
| Port Number | `8080` (must match the `EXPOSE`d port) |
| Public Access | **enabled** |
| Environment Variables | *(optional)* `APP_NAME=ghaymah-api`, `APP_VERSION=1.0.0` |

Then click **Deploy**. Once the deployment reports as running, Ghaymah assigns the
service a public URL.

### 3.3 Verify the live deployment

```bash
curl -f https://ghaymah-api-615e99f13665.hosted.ghaymah.systems/health
```

Expected: HTTP 200 with
`{"status":"ok","release":"<git-commit-sha>","uptime_s":...,"timestamp":"..."}`.

Also open `https://ghaymah-api-615e99f13665.hosted.ghaymah.systems/docs` in a browser for the OpenAPI page,
and screenshot both the running service in the Ghaymah dashboard and the `/health`
response for the submission.

> **Redeploying a new version:** push a new image tag and update the Container
> Image URL on the service. Prefer an explicit tag (e.g. `:v2` or the git SHA)
> over `:latest` so a redeploy is unambiguous about which build is running.

---

## 4. Run the monitor

`monitor/monitor.py` uses the **Python standard library only** — nothing to install.

```bash
export APP_URL="https://ghaymah-api-615e99f13665.hosted.ghaymah.systems"
python q1-deploy-monitor/monitor/monitor.py
```

On Windows PowerShell:

```bash
$env:APP_URL="https://ghaymah-api-615e99f13665.hosted.ghaymah.systems"; python q1-deploy-monitor\monitor\monitor.py
```

Every 30 seconds it issues `GET $APP_URL/health` with a 5 s timeout, then
`GET $APP_URL/metrics`, and appends one record to `monitor/data/checks.json`
(a JSON array, created on first run):

```json
{
  "ts": "2026-07-26T15:37:29.886772+00:00",
  "status": "up",
  "code": 200,
  "latency_ms": 65.3,
  "requests": 2
}
```

- Any timeout, connection error, TLS failure or non-2xx response → `"status":"down"`
  with `latency_ms: null` (and the HTTP code when the server did answer).
- `/metrics` is best-effort: if only that call fails, the check still counts as
  **up** and `requests` is `null`.
- After **3 consecutive failures** it prints an `ALERT:` line to stdout (once per
  outage), and a `RECOVERED:` line when the service answers again.

Single check (useful for cron, CI or a smoke test — exits `0` if up, `1` if down):

```bash
APP_URL="https://ghaymah-api-615e99f13665.hosted.ghaymah.systems" python q1-deploy-monitor/monitor/monitor.py --once
```

Leave the loop running well before the submission so the dashboard has real history.

**Tuning via environment variables**

| Variable | Default | Meaning |
|---|---|---|
| `APP_URL` | *(required)* | base URL of the deployed app (also settable with `--url`) |
| `INTERVAL_S` | `30` | seconds between checks |
| `TIMEOUT_S` | `5` | per-request timeout |
| `ALERT_AFTER` | `3` | consecutive failures before the ALERT line |
| `DATA_FILE` | `monitor/data/checks.json` | where records are written |
| `MAX_RECORDS` | `2880` | rolling window (24 h at one check / 30 s) |

Records are written atomically (temp file + rename), so the dashboard never reads
a half-written file.

---

## 5. Open the dashboard

The page fetches `../monitor/data/checks.json`, so it must be served over HTTP —
opening `index.html` directly from the filesystem is blocked by the browser's
`file://` fetch restrictions (the page detects this and tells you so instead of
failing silently).

```bash
cd q1-deploy-monitor && python -m http.server 8000
```

Then open <http://localhost:8000/dashboard/index.html>.

It shows:

- **Status badge** — green `UP` / red `DOWN` from the most recent check, with the
  HTTP code and timestamp.
- **Total requests** — `requests_total` from the latest check.
- **Latest latency** + the average across the stored window.
- **Uptime %** across all stored checks.
- **Latency line chart** — `latency_ms` over time (last 120 checks); down checks
  appear as gaps with red points.
- **Last-updated timestamp**, auto-refreshing every 30 s.

With no data (monitor not started yet, file missing, or an empty/corrupt array)
it renders a "no data yet" state and an explanatory banner rather than erroring.

To point the page at a different data file, edit the one constant at the top of
the `<script>` block:

```js
const DATA_URL = '../monitor/data/checks.json';
```

---

## 6. Verification performed

### Locally

| Check | Result |
|---|---|
| `pip install -r requirements.txt` (pinned versions) | fastapi 0.115.6, uvicorn 0.34.0 installed cleanly |
| `GET /health` | HTTP 200 · `{"status":"ok","uptime_s":7.797,"timestamp":"..."}` |
| `GET /` and `GET /metrics` | valid JSON; `requests_total` increments per request |
| `monitor.py --once` against the running app | `UP code=200 latency=45.8ms requests=5`, exit 0 |
| `monitor.py` loop across an app shutdown | up records → down records → `ALERT` printed on the 3rd consecutive failure |
| Dashboard against real `checks.json` | badge, tiles, chart and uptime % all rendered; no console errors |
| Dashboard with the data file removed | "no data yet" state + banner, no crash |
| `docker build` | image builds clean (249 MB) |
| `docker run` | container reports `(healthy)` via the `HEALTHCHECK`; all three endpoints respond |

### Against the live Ghaymah deployment

Checked on 2026-07-26 at 17:23 UTC, ~32 minutes after deployment:

| Endpoint | Result |
|---|---|
| `/health` | HTTP 200 · `{"status":"ok","uptime_s":1950.129,"timestamp":"2026-07-26T17:23:30.797215+00:00"}` |
| `/` | service metadata, `started_at` `2026-07-26T16:51:00.668703+00:00` |
| `/metrics` | `{"requests_total":118,"started_at":"2026-07-26T16:51:00.668703+00:00"}` — the counter reflects real traffic from the monitor |

The monitor has been polling the live URL every 30 s since deployment; `monitor/data/checks.json`
contains only checks against the deployed application (earlier records from local
container testing were removed so the dashboard reflects one target).
