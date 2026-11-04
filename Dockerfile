# ==============================================================================
# Multi-stage Dockerfile for TripMate AI Production Service
# Stage 1: Build & Dependency Resolution Stage
# ==============================================================================
FROM python:3.11.11-slim-bookworm@sha256:081075da77b2b55c23c088251026fb69a7b2bf92471e491ff5fd75c192fd38e5 AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy uv & uvx binaries from pinned official image
COPY --from=ghcr.io/astral-sh/uv:0.5.29@sha256:88d7b48fc9f17462c82b5482e497af250d337f3f14e1ac97c16e68eba49b651e /uv /uvx /usr/local/bin/

# Install python dependencies strictly from hashed lockfile into isolated prefix
COPY requirements.lock .
RUN pip install --no-cache-dir --require-hashes -r requirements.lock --prefix=/install

# Pre-cache AviationStack MCP tool at build time so runtime requires zero internet downloads
ENV UV_TOOL_DIR=/install/share/uv/tools \
    UV_TOOL_BIN_DIR=/install/bin
RUN uv tool install --no-cache aviationstack-mcp

# ==============================================================================
# Stage 2: Minimal Hardened Production Runtime (No compiler, No git, No curl)
# ==============================================================================
FROM python:3.11.11-slim-bookworm@sha256:081075da77b2b55c23c088251026fb69a7b2bf92471e491ff5fd75c192fd38e5 AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/usr/local/bin:${PATH}" \
    UV_TOOL_DIR=/home/appuser/.local/share/uv/tools \
    UV_TOOL_BIN_DIR=/usr/local/bin

# Install runtime utilities: tini for PID 1 signal reaping, libpq5 for PostgreSQL
RUN apt-get update && apt-get install -y --no-install-recommends \
    tini \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy uv/uvx binaries from pinned official image
COPY --from=ghcr.io/astral-sh/uv:0.5.29@sha256:88d7b48fc9f17462c82b5482e497af250d337f3f14e1ac97c16e68eba49b651e /uv /uvx /usr/local/bin/

# Copy python dependencies and cached tools from builder
COPY --from=builder /install /usr/local

# Create non-root system user and prepare home directory for pre-cached uv tools
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -m -s /bin/bash appuser && \
    mkdir -p /home/appuser/.local/share/uv/tools && \
    cp -r /usr/local/share/uv/tools/* /home/appuser/.local/share/uv/tools/ 2>/dev/null || true && \
    chown -R appuser:appgroup /home/appuser /app

# Copy application source code
COPY --chown=appuser:appgroup . /app

USER appuser

EXPOSE 8000

# Healthcheck probing /health/live with Python stdlib (no curl required)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request, os; port = os.environ.get('PORT', '8000'); urllib.request.urlopen(f'http://127.0.0.1:{port}/health/live')"

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sh", "-c", "exec gunicorn -b 0.0.0.0:${PORT:-8000} -c gunicorn.conf.py app:app"]
