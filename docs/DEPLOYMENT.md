# TripMate AI — Production Deployment Guide

This guide covers deployment procedures for **TripMate AI** across VPS instances (Docker Compose) and modern PaaS platforms (Railway, Render, Fly.io), along with a production-ready Caddy reverse-proxy configuration optimized for Server-Sent Events (SSE).

---

## 1. Architecture Overview

TripMate AI runs as a containerized multi-process application:
- **Application Server**: Python 3.11 slim runner wrapped by `tini` (PID 1) executing `gunicorn` with `uvicorn.workers.UvicornWorker` workers.
- **MCP Toolchain**: Pre-cached `aviationstack-mcp` CLI binary managed by `uv` / `uvx` without runtime package downloads.
- **Primary Database**: PostgreSQL 15.8 (with SCRAM-SHA-256 authentication and connection pooling).
- **Cache & Task Broker**: Redis 7.2.5 (AOF persistence, LRU memory cap).
- **Reverse Proxy**: Caddy (automated Let's Encrypt TLS, unbuffered SSE streaming).

```
 Internet (HTTPS / SSE)
          │
          ▼
   ┌──────────────┐
   │ Caddy Proxy  │  (Port 80/443, Automatic TLS, flush_interval -1)
   └──────┬───────┘
          │ Internal Network
          ▼
 ┌─────────────────┐       ┌─────────────────┐
 │  TripMate API   │ ◄───► │  PostgreSQL 15  │ (Port 5432 unexposed)
 │ (Gunicorn/Uvic) │       └─────────────────┘
 └────────┬────────┘
          │
          ▼
 ┌─────────────────┐
 │   Redis 7.2     │ (Port 6379 unexposed)
 └─────────────────┘
```

---

## 2. Deploying on a VPS with Docker Compose

### Prerequisites
- Linux Server (Ubuntu 22.04 LTS or Debian 12 recommended)
- Docker Engine 24.0+ & Docker Compose v2.20+
- Domain name pointed at server public IP (`A` / `AAAA` DNS records)

### Step 1: Host Firewall Setup (UFW)
Ensure external access to database and cache ports is strictly forbidden:
```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP (Let's Encrypt challenge)
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

### Step 2: Clone Repository & Configure Secrets
```bash
git clone https://github.com/your-org/tripmate-ai.git /opt/tripmate
cd /opt/tripmate

# Generate production environment file
cp .env.example .env
chmod 600 .env
```

Edit `.env` and fill in all mandatory production secrets:
```bash
APP_ENV=production
SECRET_KEY=$(openssl rand -hex 32)
API_KEY=$(openssl rand -hex 24)
POSTGRES_PASSWORD=$(openssl rand -hex 24)
REDIS_PASSWORD=$(openssl rand -hex 24)

# LLM Providers (at least one is required)
GROQ_API_KEY=gsk_your_groq_key_here

# MCP Integration Keys
AVIATIONSTACK_API_KEY=your_aviationstack_key
```

### Step 3: Launch Production Stack
```bash
# Validate compose configuration without printing inline secrets
docker compose -f docker-compose.prod.yml config -q

# Build and start services in background
docker compose -f docker-compose.prod.yml up -d --build

# Verify all containers are healthy
docker compose -f docker-compose.prod.yml ps
```

### Step 4: Health Verification
```bash
# Liveness probe (verifies web process is active)
curl -f http://127.0.0.1:8000/health/live

# Readiness probe (verifies Postgres, Redis, and MCP connectivity)
curl -f http://127.0.0.1:8000/health/ready
```

---

## 3. Caddy Reverse Proxy Configuration

Caddy provides zero-configuration automatic HTTPS with Let's Encrypt and handles HTTP/2 connection multiplexing and SSE buffer flushing natively.

### Sample `Caddyfile`

Create `/etc/caddy/Caddyfile`:

```caddyfile
api.tripmate.example.com {
    # Automatic HTTPS with HSTS
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
        Content-Security-Policy "default-src 'none'; frame-ancestors 'none';"
    }

    # Compress non-streaming responses
    encode zstd gzip

    # Handle Server-Sent Events (SSE) streaming paths without buffering
    @sse {
        path /api/v1/travel/stream /api/travel/stream
    }
    handle @sse {
        reverse_proxy app:8000 {
            # Disable buffering for real-time streaming chunks
            flush_interval -1
            
            # Streaming timeouts
            transport http {
                response_header_timeout 300s
                read_timeout 300s
                write_timeout 300s
            }

            # Forward client IP headers
            header_up X-Forwarded-For {remote_host}
            header_up X-Forwarded-Proto {scheme}
            header_up X-Real-IP {remote_host}
        }
    }

    # Standard API routes and endpoints
    handle {
        reverse_proxy app:8000 {
            # Forward client IP headers to FastAPI proxy middleware
            header_up X-Forwarded-For {remote_host}
            header_up X-Forwarded-Proto {scheme}
            header_up X-Real-IP {remote_host}

            # Upstream health check
            health_uri /health/live
            health_interval 15s
            health_timeout 5s
        }
    }

    # Access logging with sanitized fields
    log {
        output file /var/log/caddy/tripmate_access.log {
            roll_size 50mb
            roll_keep 5
        }
        format json
    }
}
```

Reload Caddy:
```bash
sudo systemctl reload caddy
```

---

## 4. Platform-as-a-Service (PaaS) Deployment

### Option A: Railway
1. **New Project**: Connect your GitHub repository to Railway.
2. **Add Services**:
   - Provision a **PostgreSQL** database addon.
   - Provision a **Redis** addon.
3. **Configure Environment**:
   - Bind `DATABASE_URL` to `${{Postgres.DATABASE_URL}}`.
   - Bind `REDIS_URL` to `${{Redis.REDIS_URL}}`.
   - Add `GROQ_API_KEY`, `AVIATIONSTACK_API_KEY`, `API_KEY`, `SECRET_KEY`.
   - Set `APP_ENV=production`.
4. **Health Check**:
   - Liveness Probe Path: `/health/live`
   - Readiness Probe Path: `/health/ready`

### Option B: Render
1. Create a **Web Service** pointing to the repository.
2. Runtime: **Docker** (Render automatically picks up `Dockerfile`).
3. Create managed **Render PostgreSQL** and **Render Redis** instances.
4. Set Environment Variables (`DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `API_KEY`).
5. Set Health Check Path to `/health/live`.

### Option C: Fly.io
1. Initialize configuration: `fly launch --no-deploy`.
2. Attach Postgres cluster: `fly postgres attach <cluster-name>`.
3. Set secrets:
   ```bash
   fly secrets set \
     SECRET_KEY=$(openssl rand -hex 32) \
     API_KEY=$(openssl rand -hex 24) \
     GROQ_API_KEY="gsk_..." \
     AVIATIONSTACK_API_KEY="..."
   ```
4. In `fly.toml`:
   ```toml
   [http_service]
     internal_port = 8000
     force_https = true

   [[http_service.checks]]
     grace_period = "10s"
     interval = "30s"
     method = "GET"
     path = "/health/live"
     timeout = "5s"
   ```

---

## 5. Security & Maintenance Operations

### Automated Database Backups
Create a nightly cron job on the host:
```bash
0 2 * * * docker compose -f /opt/tripmate/docker-compose.prod.yml exec -T postgres pg_dump -U postgres -d tripmate_db | gzip > /opt/backups/tripmate_$(date +\%Y\%m\%d_\%H\%M\%S).sql.gz
```

### Zero-Downtime Rolling Restarts
```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d --no-deps --build app
```

### Rotating API Keys
1. Update `.env` with new keys.
2. Re-run:
   ```bash
   docker compose -f docker-compose.prod.yml up -d app
   ```

### Updating Pinned Container Images Safely

To maintain reproducible and tamper-proof builds, base images and toolchains in `Dockerfile` are pinned by both tag and multi-arch digest (`image:tag@sha256:<digest>`).

**1. Inspect and Retrieve Official Digests from Registry:**
Never guess or fabricate a sha256 digest. Retrieve the exact multi-arch index digest directly using Docker CLI or registry inspect:
```bash
# For Docker Hub images (e.g. Python):
docker buildx imagetools inspect python:3.11.11-slim-bookworm

# For GitHub Container Registry (ghcr.io) images (e.g. uv):
docker buildx imagetools inspect ghcr.io/astral-sh/uv:0.5.29
```

**2. Verify Resolution with Local Script:**
Before committing, run the repository verification script to ensure all registry endpoints resolve:
```bash
python scripts/verify_pins.py
# or via pytest
pytest tests/test_pins.py -v
```

**3. Automated Updates via Dependabot:**
Because images retain readable semantic version tags alongside their digests (e.g., `python:3.11.11-slim-bookworm@sha256:...` and `ghcr.io/astral-sh/uv:0.5.29@sha256:...`), Dependabot and container vulnerability scanners automatically track newer patch releases and generate Pull Requests with updated tags and real resolved digests from the registry.

