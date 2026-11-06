# Runbook & Operations — Multi-AI-Agent

Operational runbook and monitoring guide for Multi-AI-Agent v3.0.0.

---

## 1. Prerequisites

| Component | Minimum Version | Note |
|:---|:---|:---|
| Python | 3.11+ | 3.11 through 3.13 supported |
| PostgreSQL | 16+ | Required in production (in-memory store used in dev) |
| Redis | 7+ | Recommended for distributed rate-limiting and cache |
| LLM API Key | — | At least one required (`GROQ_API_KEY`, `OPENROUTER_API_KEY`, or `HUGGINGFACE_API_KEY`) |

---

## 2. Service Management

### Development (Hot-Reload)
```bash
cp .env.example .env
# Set ENV=dev and configure GROQ_API_KEY
python app.py
```
App starts on `http://127.0.0.1:8000`.

### Production (Gunicorn + Uvicorn Workers)
```bash
gunicorn -c gunicorn.conf.py app:app
```
Override worker count via environment:
```bash
WEB_CONCURRENCY=4 gunicorn -c gunicorn.conf.py app:app
```

### Docker Compose
```bash
docker compose up --build
```

---

## 3. Health & Readiness Probes

| Endpoint | Probe | Success Criteria | Action on Failure |
|:---|:---|:---|:---|
| `GET /api/v1/health` | Liveness | HTTP 200, `"status": "ok"` | Restart container |
| `GET /health/ready` | Readiness | HTTP 200, `"status": "ready"` or `"degraded"` | Check DB pool and Redis connectivity |
| `GET /api/v1/metrics` | Telemetry | HTTP 200 (Prometheus exposition) | Check internal network / METRICS_TOKEN |

---

## 4. Service Level Objectives (SLOs)

| Capability | SLI Indicator | Target (SLO) | Window |
|:---|:---|:---|:---|
| **Availability** | Non-5xx HTTP requests | **99.9%** | Rolling 30 Days |
| **Readiness** | `/health/ready` probe success | **99.95%** | Rolling 30 Days |
| **REST Latency** | Non-workflow REST endpoints | **p95 < 250ms, p99 < 500ms** | 5-minute rolling |
| **Workflow Stream** | End-to-end multi-agent stream | **p95 < 12s, p99 < 20s** | 5-minute rolling |
| **Checkpointer Latency**| Checkpoint save/retrieve | **p95 < 50ms, p99 < 150ms** | 5-minute rolling |

---

## 5. Prometheus Alerting Rules

Place these rules in your Prometheus alert manager (`/etc/prometheus/alerts/tripmate.yml`):

### High 5xx Error Rate (`TripMateHigh5xxRate`)
- **Severity**: Critical
- **Condition**: `sum(rate(tripmate_http_requests_total{status=~"5.."}[5m])) / sum(rate(tripmate_http_requests_total[5m])) * 100 > 1.0`
- **Action**: Check `tripmate.access` logs filtered by `status=500` for unhandled exceptions.

### Readiness Probe Failing (`TripMateReadinessFailing`)
- **Severity**: Critical
- **Condition**: `tripmate_http_requests_total{path="/health/ready",status!="200"} > 0`
- **Action**: Verify PostgreSQL connection pool (`DB_POOL_MAX_SIZE`), Redis ping, and MCP subprocesses.

### LLM Token Spikes (`TripMateLLMTokenSpike`)
- **Severity**: Warning
- **Condition**: `sum(rate(tripmate_llm_tokens_total{type="total"}[5m])) * 60 > 250000`
- **Action**: Review active user quotas; enforce `DAILY_TOKEN_BUDGET_PER_USER`.

---

## 6. Circuit Breakers & Cache Management

### Reset a Tripped Circuit Breaker
```bash
curl -X POST http://localhost:8000/api/v1/admin/circuit-breakers/groq/reset \
  -H "Authorization: Bearer <admin-token>"
```

### Flush Redis / In-Memory Cache
```bash
curl -X POST http://localhost:8000/api/v1/admin/cache/clear \
  -H "Authorization: Bearer <admin-token>"
```

---

## 7. Incident Response Playbook

### High Error Rate on `/api/v1/travel`
1. Check `/api/v1/health` → `circuit_breakers`. If open, verify provider status (Groq, OpenRouter, HuggingFace status pages).
2. Check `/api/v1/status` → `model_tiers` to confirm valid API keys.
3. Review structured JSON logs for `[WORKFLOW ERROR]` lines.

### Rate Limiting Spikes (Unexpected 429 Responses)
1. Verify `RATE_LIMIT_REQUESTS` / `RATE_LIMIT_WINDOW_SECONDS` in environment.
2. Confirm Redis connectivity; when Redis is unreachable, `EMERGENCY_IN_MEMORY_RATE_LIMIT` (default 5/min) applies.
3. If necessary during an outage, toggle `FAIL_OPEN_REDIS=true` temporarily.

### Stalled HITL Approvals
Approvals automatically expire after `APPROVAL_TTL_SECONDS` (default 900s = 15m). Force resolution:
```bash
curl -X POST http://localhost:8000/api/v1/travel/approve \
  -H "Authorization: Bearer <user-token>" \
  -H "Content-Type: application/json" \
  -d '{"thread_id": "<thread-id>", "approved": false, "feedback": "Manual operator override"}'
```

---

## 8. Log Reference

| Prefix / Logger | Purpose |
|:---|:---|
| `tripmate.access` | Structured JSON access logs with sanitized query and request IDs |
| `tripmate.travel_service` | Multi-agent planning, specialist execution, and HITL lifecycle |
| `tripmate.cache` | Cache hit, miss, and Redis fallback logs |
| `[STARTUP ERROR]` | Fatal missing production configuration |
| `[WORKFLOW ERROR]` | Graph node failure or timeout |
