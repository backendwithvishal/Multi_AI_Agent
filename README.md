# Vishal Sanam Multi-Agent AI System (LangGraph, MCP, Supervisor, Guardrails, HITL)

An enterprise-grade, production-oriented multi-agent travel planning backend developed by **Vishal Sanam**. Built as a clean **Modular Monolith** using **LangGraph**, **FastAPI**, **Pydantic v2**, and **Model Context Protocol (MCP)**, featuring dynamic supervisor routing, multi-stage guardrails, parallel specialist execution, Server-Sent Events (SSE) streaming, circuit breakers, sliding-window rate limiting, and Human-in-the-Loop (HITL) approval workflows.

> 📄 **Resume Highlights:** See [RESUME_HIGHLIGHTS.md](RESUME_HIGHLIGHTS.md) for recruiter-ready bullet points, architectural diagrams, tech stack tags, and empirical benchmark results.

---

## Core Backend Architecture & Features

- **Modular Monolith Architecture (`tripmate/`):** Clean domain separation (`config`, `schemas`, `middleware`, `agents`, `graph`, `integrations`, `cache`, `database`, `services`, `api/v1/`).
- **Asynchronous Parallel Fan-Out Execution (`asyncio.gather`):** Independent specialist agents (`flight_agent`, `hotel_agent`, `weather_agent`, `budget_agent`) execute concurrently, achieving an empirical **57.8% latency reduction** (0.559s vs 1.325s).
- **Resilience & Circuit Breakers (`circuit_breaker.py`):** Circuit Breaker pattern (`CLOSED`, `OPEN`, `HALF_OPEN`) with timeouts and retries protecting downstream Tavily, AviationStack, and OpenWeather MCP services.
- **Single-Flight Bounded TTL Cache (`ttl_cache.py`):** Bounded async TTL cache featuring single-flight locking to prevent cache stampedes on concurrent misses.
- **Async SSE Streaming (`POST /api/v1/travel/stream`):** Server-Sent Events endpoint streaming real-time supervisor decisions, agent progress, telemetry, and HITL events.
- **Enterprise Security & Middleware (`middleware/` & `dependencies.py`):**
  - **API Key Authentication:** `X-API-Key` or `Bearer` token verification dependency.
  - **Correlation Tracing:** `X-Request-ID` header injection across all requests/responses.
  - **Rate Limiting:** Sliding-window rate limiter enforcing 30 requests/minute per IP.
  - **Security Headers:** Enforces `X-Content-Type-Options`, `X-Frame-Options`, and `HSTS`.
- **PostgreSQL State Checkpointing:** Persistent workflow state saved using `PostgresSaver` with automatic `MemorySaver` fallback for development.
- **Human-In-The-Loop (HITL) Workflows:** LangGraph graph state interrupts allowing human review, approval, or revision feedback before final plan generation.

---

## Repository Structure

```text
Multi_AI_Agent/
├── app.py                      # Main FastAPI entry point & legacy aliases
├── benchmark.py                # Empirical latency benchmark script
├── custom_weather_mcp_server.py # Custom stdio MCP weather server adapter
├── mcp_client.py               # MultiServerMCPClient connection helpers
├── docker-compose.yml          # Development Docker Compose (FastAPI + PostgreSQL)
├── Dockerfile                  # Multi-stage production Dockerfile
├── RESUME_HIGHLIGHTS.md        # Resume reference guide & interview preparation
├── postman/                    # Postman API Collection
│   └── Multi_AI_Agent.postman_collection.json
├── tripmate/                   # Core Modular Monolith Package
│   ├── config/                 # Typed Pydantic settings & env validation
│   ├── schemas/                # Travel & response envelope Pydantic models
│   ├── middleware/             # Request ID, rate limit, logging, security headers
│   ├── integrations/           # Circuit breakers & resilient MCP wrappers
│   ├── cache/                  # Single-flight bounded TTL cache
│   ├── database/               # Connection pooling & PostgresSaver manager
│   ├── agents/                 # Guardrail, supervisor, & specialist agents
│   ├── graph/                  # LangGraph state, routing, & workflow assembly
│   ├── services/               # High-level travel orchestration service
│   └── api/                    # Dependencies & v1 routes (travel, approval, health)
└── tests/                      # Pytest suite (21 unit & integration tests)
```

---

## Quick Start (Local & Docker)

### 1. Install Dependencies
```powershell
python -m pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```powershell
cp .env.example .env
```
Fill in your `GROQ_API_KEY`, `TAVILY_API_KEY`, and optional `DATABASE_URL`.

### 3. Run FastAPI Application
```powershell
python app.py
# or using uvicorn directly
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

### 4. Run via Docker Compose
```powershell
docker-compose up --build
```

---

## API Documentation (`/api/v1/`)

- **`POST /api/v1/travel`** — Execute multi-agent workflow.  
  *Request:* `{ "message": "Plan a 5-day trip to Paris under $2000", "thread_id": "test_thread_1" }`  
  *Response:* Standard envelope with thread ID, draft itinerary, execution metrics, and `X-Request-ID`.

- **`POST /api/v1/travel/stream`** — Stream multi-agent execution events real-time via Server-Sent Events (SSE).

- **`POST /api/v1/travel/approve`** — Resume graph execution after human review.  
  *Request:* `{ "thread_id": "<id>", "approved": true, "feedback": "Optional revision notes" }`

- **`GET /api/v1/health`** — Health telemetry endpoint returning operational status, middleware features, database health, and cache statistics.

- **`GET /api/v1/liveness`** — Process liveness probe.

- **`GET /api/v1/readiness`** — Readiness probe inspecting database connectivity.

---

## Running Automated Tests & Benchmarks

Run the full `pytest` suite (21 tests):
```powershell
python -m pytest -v
```

Run empirical latency benchmark:
```powershell
python benchmark.py
```

---

## Postman API Collection

Import `postman/Multi_AI_Agent.postman_collection.json` into Postman to test all versioned endpoints, streaming responses, HITL approval flows, and health probes.

---

## Author & License

- **Author:** Vishal Sanam ([@backendwithvishal](https://github.com/backendwithvishal))
- **License:** Copyright (c) 2026 Vishal Sanam. See `LICENSE` for details.
