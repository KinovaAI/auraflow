# ================================================
# AuraFlow API Dockerfile — production only
# ================================================

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System dependencies (includes postgresql-client for pg_dump/psql used by backup service)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    libcairo2 \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# ── Production Builder ────────────────────────────────────────────────────────
FROM base AS builder

COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt

# ── Production Stage ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1

# Non-root user for security
RUN groupadd -r auraflow && useradd -r -g auraflow auraflow

WORKDIR /app

# System dependencies (minimal for production; postgresql-client for backup/restore)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libcairo2 \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    curl \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY --chown=auraflow:auraflow . .

USER auraflow

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--access-log", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "127.0.0.1,172.16.0.0/12", \
     "--timeout-keep-alive", "75"]
