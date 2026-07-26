#!/usr/bin/env python3
"""Uptime monitor for the API deployed on Ghaymah.

Polls ``$APP_URL/health`` (and ``/metrics``) every 30 seconds and appends one
record per check to ``monitor/data/checks.json`` — the file the dashboard reads.

Record schema:
    {"ts": "<iso8601>", "status": "up"|"down", "code": <int|null>,
     "latency_ms": <float|null>, "requests": <int|null>}

Usage:
    APP_URL=https://my-app.example  python monitor.py
    APP_URL=https://my-app.example  python monitor.py --once

Standard library only — no pip install needed to run the monitor.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# --- Configuration (env-overridable) -----------------------------------------

APP_URL = os.getenv("APP_URL", "").rstrip("/")
INTERVAL_S = float(os.getenv("INTERVAL_S", "30"))
TIMEOUT_S = float(os.getenv("TIMEOUT_S", "5"))
ALERT_AFTER = int(os.getenv("ALERT_AFTER", "3"))

DEFAULT_DATA_FILE = Path(__file__).resolve().parent / "data" / "checks.json"
DATA_FILE = Path(os.getenv("DATA_FILE", str(DEFAULT_DATA_FILE)))

# Keep the JSON array bounded so the dashboard stays fast and the file small.
MAX_RECORDS = int(os.getenv("MAX_RECORDS", "2880"))  # 24h at one check / 30s


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_json(url: str, timeout: float):
    """GET a URL and parse JSON. Returns (status_code, parsed_body).

    Raises on timeout, connection failure, or non-2xx status.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "ghaymah-monitor/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = None
        return resp.status, body


def check_once(app_url: str) -> dict:
    """Run one health + metrics check and return the record to persist."""
    health_url = f"{app_url}/health"
    metrics_url = f"{app_url}/metrics"

    started = time.perf_counter()
    try:
        code, _body = fetch_json(health_url, TIMEOUT_S)
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        status = "up"
    except urllib.error.HTTPError as exc:
        # The app answered, just not with a healthy status — record the code.
        return {
            "ts": now_iso(),
            "status": "down",
            "code": exc.code,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "requests": None,
        }
    except Exception:
        # Timeout, DNS failure, connection refused, TLS error, ...
        return {
            "ts": now_iso(),
            "status": "down",
            "code": None,
            "latency_ms": None,
            "requests": None,
        }

    # /metrics is best-effort: a failure there must not turn a healthy app "down".
    requests_total = None
    try:
        _mcode, mbody = fetch_json(metrics_url, TIMEOUT_S)
        if isinstance(mbody, dict):
            value = mbody.get("requests_total")
            if isinstance(value, int):
                requests_total = value
    except Exception:
        pass

    return {
        "ts": now_iso(),
        "status": status,
        "code": code,
        "latency_ms": latency_ms,
        "requests": requests_total,
    }


def load_records(path: Path) -> list:
    """Read the existing JSON array; tolerate a missing or corrupt file."""
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        print(f"[warn] {path} unreadable or corrupt — starting a fresh array", file=sys.stderr)
        return []


def append_record(path: Path, record: dict) -> None:
    """Append one record to the JSON array, writing atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    records = load_records(path)
    records.append(record)
    if len(records) > MAX_RECORDS:
        records = records[-MAX_RECORDS:]

    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=2)
        fh.write("\n")
    tmp.replace(path)


def format_line(record: dict) -> str:
    latency = f"{record['latency_ms']:.1f}ms" if record["latency_ms"] is not None else "  -  "
    code = record["code"] if record["code"] is not None else "---"
    reqs = record["requests"] if record["requests"] is not None else "-"
    return (
        f"{record['ts']}  {record['status'].upper():<4}  "
        f"code={code:<4} latency={latency:<9} requests={reqs}"
    )


def run(app_url: str, once: bool) -> int:
    consecutive_failures = 0
    alerted = False

    while True:
        record = check_once(app_url)
        append_record(DATA_FILE, record)
        print(format_line(record), flush=True)

        if record["status"] == "down":
            consecutive_failures += 1
            if consecutive_failures >= ALERT_AFTER and not alerted:
                print(
                    f"ALERT: {app_url} has failed {consecutive_failures} consecutive "
                    f"health checks (since {record['ts']})",
                    flush=True,
                )
                alerted = True
        else:
            if alerted:
                print(f"RECOVERED: {app_url} is responding again at {record['ts']}", flush=True)
            consecutive_failures = 0
            alerted = False

        if once:
            return 0 if record["status"] == "up" else 1

        time.sleep(INTERVAL_S)


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor the Ghaymah-deployed API.")
    parser.add_argument("--once", action="store_true", help="run a single check and exit")
    parser.add_argument("--url", default=APP_URL, help="app base URL (default: $APP_URL)")
    args = parser.parse_args()

    app_url = (args.url or "").rstrip("/")
    if not app_url:
        print(
            "error: no app URL. Set APP_URL, e.g.\n"
            "  APP_URL=https://my-app.ghaymah.example python monitor.py",
            file=sys.stderr,
        )
        return 2

    print(f"Monitoring {app_url} every {INTERVAL_S:g}s (timeout {TIMEOUT_S:g}s)", flush=True)
    print(f"Writing checks to {DATA_FILE}", flush=True)

    try:
        return run(app_url, args.once)
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)
        return 0


if __name__ == "__main__":
    sys.exit(main())
