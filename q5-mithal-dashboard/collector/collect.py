#!/usr/bin/env python3
"""Metrics collector for https://mithal.space.

Every 60 seconds (or once with --once) it measures availability, page latency,
DNS resolution time, TLS certificate lifetime and search-endpoint latency, then
appends one record to the JSON array the dashboard reads.

Record schema:
    {"ts": "<iso8601 utc>", "up": bool, "code": int|null, "latency_ms": float|null,
     "dns_ms": float|null, "ssl_days_left": int|null, "search_ms": float|null}

A failing measurement never aborts the run — it is recorded as null.

Usage:
    python collect.py            # loop every 60s
    python collect.py --once     # single collection, then exit
"""

import argparse
import json
import os
import socket
import ssl
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

# --- Configuration -----------------------------------------------------------

TARGET_URL = os.getenv("TARGET_URL", "https://mithal.space")

# Confirmed working search endpoint for mithal.space.
SEARCH_URL = os.getenv("SEARCH_URL", "https://mithal.space/search?q=test")

INTERVAL_S = float(os.getenv("INTERVAL_S", "60"))
TIMEOUT_S = float(os.getenv("TIMEOUT_S", "10"))
RETENTION_HOURS = float(os.getenv("RETENTION_HOURS", "48"))

# The dashboard is served as the web root and fetches "data/metrics.json",
# so the data directory lives inside dashboard/ both locally and in the image.
DEFAULT_METRICS_FILE = (
    Path(__file__).resolve().parent.parent / "dashboard" / "data" / "metrics.json"
)
METRICS_FILE = Path(os.getenv("METRICS_FILE", str(DEFAULT_METRICS_FILE)))

USER_AGENT = "mithal-monitor/1.0 (+uptime collector)"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def host_port(url: str) -> tuple:
    """Extract (hostname, port) from a URL, defaulting to 443 for https."""
    parsed = urlparse(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return parsed.hostname, port


# --- Individual measurements (each returns None on failure) ------------------


def measure_page(url: str):
    """Timed GET of the home page. Returns (code|None, latency_ms|None)."""
    started = time.perf_counter()
    try:
        resp = requests.get(
            url, timeout=TIMEOUT_S, headers={"User-Agent": USER_AGENT}, allow_redirects=True
        )
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return resp.status_code, latency_ms
    except requests.RequestException:
        # Connection refused, DNS failure, TLS error, timeout — no status code.
        return None, None


def measure_search(url: str):
    """Timed GET of the search endpoint. Returns search_ms|None."""
    started = time.perf_counter()
    try:
        resp = requests.get(
            url, timeout=TIMEOUT_S, headers={"User-Agent": USER_AGENT}, allow_redirects=True
        )
        if resp.status_code >= 400:
            return None
        return round((time.perf_counter() - started) * 1000, 2)
    except requests.RequestException:
        return None


def measure_dns(hostname: str, port: int):
    """Timed DNS resolution. Returns dns_ms|None."""
    started = time.perf_counter()
    try:
        socket.getaddrinfo(hostname, port)
        return round((time.perf_counter() - started) * 1000, 2)
    except (socket.gaierror, OSError):
        return None


def measure_ssl_days_left(hostname: str, port: int):
    """Days until the TLS certificate expires. Returns int|None."""
    context = ssl.create_default_context()
    try:
        with socket.create_connection((hostname, port), timeout=TIMEOUT_S) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as tls:
                cert = tls.getpeercert()
    except (ssl.SSLError, socket.error, OSError):
        return None

    not_after = (cert or {}).get("notAfter")
    if not not_after:
        return None
    try:
        # OpenSSL format, always in GMT: "Sep 12 23:59:59 2026 GMT"
        expires = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None
    return (expires - now_utc()).days


def collect_once() -> dict:
    """Run every measurement and build one record. Never raises."""
    hostname, port = host_port(TARGET_URL)

    dns_ms = measure_dns(hostname, port) if hostname else None
    code, latency_ms = measure_page(TARGET_URL)
    ssl_days_left = measure_ssl_days_left(hostname, port) if hostname else None
    search_ms = measure_search(SEARCH_URL)

    return {
        "ts": now_utc().isoformat(),
        "up": code is not None and 200 <= code < 400,
        "code": code,
        "latency_ms": latency_ms,
        "dns_ms": dns_ms,
        "ssl_days_left": ssl_days_left,
        "search_ms": search_ms,
    }


# --- Storage -----------------------------------------------------------------


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


def prune(records: list) -> list:
    """Drop records older than the retention window."""
    cutoff = now_utc() - timedelta(hours=RETENTION_HOURS)
    kept = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        try:
            ts = datetime.fromisoformat(str(rec.get("ts")))
        except (TypeError, ValueError):
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts >= cutoff:
            kept.append(rec)
    return kept


def append_record(path: Path, record: dict) -> None:
    """Append a record, prune the window, and write atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    records = prune(load_records(path))
    records.append(record)

    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=2)
        fh.write("\n")
    tmp.replace(path)


def format_line(rec: dict) -> str:
    def num(value, suffix=""):
        return f"{value}{suffix}" if value is not None else "-"

    return (
        f"{rec['ts']}  {'UP  ' if rec['up'] else 'DOWN'}  "
        f"code={num(rec['code']):<4} "
        f"latency={num(rec['latency_ms'], 'ms'):<10} "
        f"dns={num(rec['dns_ms'], 'ms'):<9} "
        f"search={num(rec['search_ms'], 'ms'):<10} "
        f"ssl={num(rec['ssl_days_left'], 'd')}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect availability metrics for mithal.space.")
    parser.add_argument("--once", action="store_true", help="collect a single sample and exit")
    args = parser.parse_args()

    print(f"Target:  {TARGET_URL}", flush=True)
    print(f"Search:  {SEARCH_URL}", flush=True)
    print(f"Output:  {METRICS_FILE} (keeping {RETENTION_HOURS:g}h)", flush=True)
    if not args.once:
        print(f"Interval: {INTERVAL_S:g}s", flush=True)

    while True:
        try:
            record = collect_once()
            append_record(METRICS_FILE, record)
            print(format_line(record), flush=True)
        except Exception as exc:  # a bug here must not kill a long-running collector
            print(f"[error] collection failed: {exc!r}", file=sys.stderr, flush=True)

        if args.once:
            return 0
        time.sleep(INTERVAL_S)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)
