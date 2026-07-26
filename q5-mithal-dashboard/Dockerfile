FROM python:3.12-slim

# curl is used by the HEALTHCHECK below.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080 \
    WEB_ROOT=/app/dashboard \
    METRICS_FILE=/app/dashboard/data/metrics.json

WORKDIR /app

# Dependencies first so editing the collector or dashboard doesn't reinstall them.
COPY collector/requirements.txt ./collector/requirements.txt
RUN pip install --no-cache-dir -r collector/requirements.txt

# Application: the collector and the static dashboard it feeds.
COPY collector/collect.py ./collector/collect.py
COPY dashboard/index.html ./dashboard/index.html
COPY start.sh ./start.sh

# Tolerate CRLF line endings if the repo was checked out on Windows.
RUN sed -i 's/\r$//' ./start.sh && chmod +x ./start.sh

# Non-root user; it must be able to write metrics into the served directory.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/dashboard/data \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

# The dashboard page is the liveness signal for the whole container.
HEALTHCHECK --interval=60s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8080/index.html || exit 1

CMD ["./start.sh"]
