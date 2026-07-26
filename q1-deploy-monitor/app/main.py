"""Ghaymah demo API — liveness and request metrics with no external dependencies.

Endpoints:
    GET /         basic service info
    GET /health   liveness probe (process-only, no downstream checks)
    GET /metrics  in-memory request counter
"""

import os
import time
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

APP_NAME = os.getenv("APP_NAME", "ghaymah-api")
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
RELEASE_SHA = os.getenv("RELEASE_SHA", "local")
PORT = int(os.getenv("PORT", "8080"))

# Process start time drives both uptime and the /metrics started_at field.
STARTED_AT_MONOTONIC = time.monotonic()
STARTED_AT_ISO = datetime.now(timezone.utc).isoformat()

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Minimal API deployed on the Ghaymah container platform.",
)

# In-memory counter. Deliberately per-process: it resets on restart, which is
# exactly what we want the dashboard to show after a redeploy or a crash-loop.
_requests_total = 0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uptime_s() -> float:
    return round(time.monotonic() - STARTED_AT_MONOTONIC, 3)


@app.middleware("http")
async def count_requests(request: Request, call_next):
    """Increment the counter for every request, including failed ones."""
    global _requests_total
    _requests_total += 1
    return await call_next(request)


@app.get("/")
async def root():
    return {
        "service": APP_NAME,
        "version": APP_VERSION,
        "release": RELEASE_SHA,
        "message": "Ghaymah deployment demo API",
        "endpoints": ["/", "/health", "/metrics", "/docs"],
        "started_at": STARTED_AT_ISO,
        "timestamp": _now_iso(),
    }


@app.get("/health")
async def health():
    """Liveness only — no DB or network calls, so it never fails for a
    downstream reason the orchestrator cannot fix by restarting us."""
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "release": RELEASE_SHA,
            "uptime_s": _uptime_s(),
            "timestamp": _now_iso(),
        },
    )


@app.get("/metrics")
async def metrics():
    return {
        "requests_total": _requests_total,
        "started_at": STARTED_AT_ISO,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=PORT, log_level="info")
