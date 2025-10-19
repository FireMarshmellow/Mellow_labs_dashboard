FROM python:3.11-slim

ARG APP_VERSION=dev
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=3000 \
    DATABASE_PATH=/data/finance.db \
    APP_VERSION=${APP_VERSION}

WORKDIR /app

# Install system dependencies (if any are needed in the future)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory for persistent DB volume
RUN mkdir -p /data

EXPOSE 3000

LABEL org.opencontainers.image.title="Mellow Biz" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.source="https://github.com/${GITHUB_REPOSITORY}"

HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python - <<'PY' || exit 1
import os, sys, json, urllib.request
try:
    url = f"http://127.0.0.1:{os.environ.get('PORT','3000')}/api/ping"
    with urllib.request.urlopen(url, timeout=3) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        raise SystemExit(0 if data.get('ok') else 1)
except Exception:
    raise SystemExit(1)
PY

CMD ["python", "server.py"]
