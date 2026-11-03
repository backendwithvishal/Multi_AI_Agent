# Runbook — Multi-AI-Agent

> [!NOTE]
> Operations guide for v3.0.0. Keep this document updated when infrastructure changes.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Starting the Service](#starting-the-service)
3. [Health Checks](#health-checks)
4. [Scaling](#scaling)
5. [Circuit Breaker Management](#circuit-breaker-management)
6. [Cache Operations](#cache-operations)
7. [Database Migrations](#database-migrations)
8. [Incident Response](#incident-response)
9. [Log Reference](#log-reference)

---

## Prerequisites

| Dependency | Minimum version | Required? |
|------------|----------------|-----------|
| Python | 3.11 | ✅ |
| PostgreSQL | 16 | Production only |
| Redis | 7 | Strongly recommended |
| Groq, OpenRouter, or HuggingFace API key | — | At least one required |

---

## Starting the Service

### Development (hot-reload, localhost)

```bash
cp .env.example .env
# fill in at least GROQ_API_KEY and set ENV=dev
python app.py
```

Server binds to `http://127.0.0.1:8000` in dev mode.

### Production (gunicorn + uvicorn workers)

```bash
gunicorn -c gunicorn.conf.py app:app
```

Or override worker count:

```bash
WEB_CONCURRENCY=4 gunicorn -c gunicorn.conf.py app:app
```

### Docker Compose (local full stack)

```bash
docker compose up --build
```

Brings up: API + PostgreSQL 16 + Redis 7. API available at `http://localhost:8000`.

### Docker Compose (production profile)

```bash
docker compose -f docker-compose.prod.yml up -d
```

---

## Health Checks

| Endpoint | Purpose | Expected when healthy |
|----------|---------|----------------------|
| `GET /health/live` | Liveness probe (k8s / Docker) | `200 {"status": "ok"}` |
| `GET /health/ready` | Readiness probe (DB + Redis + MCP) | `200 {"status": "ready"}` |
| `GET /api/v1/health` | Detailed telemetry (features, cache stats, circuit breakers) | `200 {"status": "ok", …}` |
| `GET /api/v1/status` | Operational status (uptime, agent registry, model tiers) | `200 {"success": true, …}` |

If `/health/ready` returns `503`, check:

```bash
# Database
curl http://localhost:8000/api/v1/health | python -m json.tool | grep -A5 database

# Redis
curl http://localhost:8000/api/v1/health | python -m json.tool | grep -A3 cache_stats
```

---

## Scaling

- **Horizontal:** Increase `WEB_CONCURRENCY` in `.env` or via `WEB_CONCURRENCY=N gunicorn …`.
- **Vertical:** PostgreSQL pool size: `DB_POOL_MAX_SIZE` (default 10); Redis uses a single async connection per worker.
- **Rate limits:** `RATE_LIMIT_REQUESTS` / `RATE_LIMIT_WINDOW_SECONDS` are per-IP and share state via Redis. Scale correctly by ensuring all workers point to the same Redis instance.

---

## Circuit Breaker Management

Circuit breakers protect against cascading failures to external APIs.

### View current states

```bash
curl http://localhost:8000/api/v1/health | python -m json.tool | python -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d['circuit_breakers'], indent=2))"
```

States: `closed` (healthy) → `open` (failing) → `half_open` (testing recovery).

### Manually reset an open breaker

Requires admin credentials:

```bash
curl -X POST http://localhost:8000/api/v1/admin/circuit-breakers/tavily/reset \
  -H "Authorization: Bearer <admin-token>"
```

Valid service names: `tavily`, `aviationstack`, `openweather`, `gds`, `all`.

---

## Cache Operations

### Clear all caches (admin)

```bash
curl -X POST http://localhost:8000/api/v1/admin/cache/clear \
  -H "Authorization: Bearer <admin-token>"
```

### View cache stats

```bash
curl http://localhost:8000/api/v1/health | python -m json.tool | python -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d['cache_stats'], indent=2))"
```

### Flush Redis directly (emergency)

```bash
redis-cli -u "$REDIS_URL" FLUSHDB
```

> [!CAUTION]
> `FLUSHDB` clears all rate-limit windows and cached responses. Use only in emergencies.

---

## Database Migrations

Migrations are managed by Alembic and run automatically on startup when `DATABASE_URL` is configured.

### Manual migration

```bash
# Apply all pending migrations
alembic upgrade head

# View current revision
alembic current

# Roll back one step
alembic downgrade -1
```

Migration files are in [`migrations/versions/`](../migrations/versions/).

---

## Incident Response

### High error rate on `/api/v1/travel`

1. Check `/api/v1/health` → `circuit_breakers` — if any are `open`, reset or wait for half-open.
2. Check LLM provider status (Groq, OpenRouter, HuggingFace status pages).
3. Check `/api/v1/status` → `model_tiers` to confirm keys are configured.
4. Review structured logs for `[WORKFLOW ERROR]` lines.

### Rate limit false positives

1. Check `RATE_LIMIT_REQUESTS` / `RATE_LIMIT_WINDOW_SECONDS` in `.env`.
2. Confirm Redis is reachable; if not, `EMERGENCY_IN_MEMORY_RATE_LIMIT` (default 5/min) applies.
3. Set `FAIL_OPEN_REDIS=true` only as a temporary emergency measure.

### Worker OOM / memory growth

1. Reduce `MAX_PARALLEL_AGENTS` (default 4).
2. Reduce `LANGGRAPH_RECURSION_LIMIT` (default 15).
3. Reduce `WEB_CONCURRENCY`.

### HITL workflow stuck (pending_approval never resolved)

HITL approvals expire after `APPROVAL_TTL_SECONDS` (default 900 = 15 min). To force-resolve:

```bash
curl -X POST http://localhost:8000/api/v1/travel/approve \
  -H "Authorization: Bearer <user-token>" \
  -H "Content-Type: application/json" \
  -d '{"thread_id": "<stuck-thread-id>", "approved": false, "feedback": "Timed out — admin override"}'
```

---

## Log Reference

| Log prefix | Meaning |
|------------|---------|
| `[Checkpointer]` | PostgreSQL checkpointer initialization |
| `[STARTUP ERROR]` | Production configuration failure — service will not start |
| `[STARTUP WARNING]` | Non-fatal startup notice (dev mode) |
| `[WORKFLOW ERROR]` | LangGraph workflow execution failure |
| `[MCP]` | MCP client connection events |
| `tripmate.travel_service` | Travel orchestration events |
| `tripmate.app` | Application-level events |

Log level is controlled by `LOG_LEVEL` (default `INFO`). Set to `DEBUG` for detailed agent step output.

