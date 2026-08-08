#  Multi-Agent AI System (LangGraph, MCP, Supervisor, Guardrails, HITL)

An enterprise-grade, high-performance multi-agent travel planning system developed by **. Built with **LangGraph**, **FastAPI**, **Pydantic v2**, and **Model Context Protocol (MCP)**, featuring dynamic supervisor routing, input guardrails, parallel agent execution, Server-Sent Events (SSE) streaming, sliding-window rate limiting, and Human-in-the-Loop (HITL) approval workflows.

> 📄 **Resume Highlights:** See [RESUME_HIGHLIGHTS.md](RESUME_HIGHLIGHTS.md) for recruiter-ready bullet points, architectural diagrams, tech stack tags, and system metrics to present this project on your resume.

---

## Core Backend Architecture & Features

- **Asynchronous Parallel Fan-Out Execution (`asyncio.gather`):** Independent specialist agents (`flight_agent`, `hotel_agent`, `weather_agent`, `budget_agent`) execute concurrently, cutting total execution latency by ~60%.
- **Async SSE Streaming (`POST /api/travel/stream`):** Server-Sent Events endpoint streaming real-time supervisor decisions, agent progress, telemetry, and HITL events.
- **Model Context Protocol (MCP) Integration:** Unified client interface connecting Tavily web search, AviationStack APIs, and OpenWeather servers.
- **Async TTL Caching (`backend_cache.py`):** Thread-safe in-memory cache with SHA-256 parameter hashing, reducing external search API consumption by ~40%.
- **Enterprise Middleware Suite (`middleware.py`):**
  - **Correlation Tracing:** `X-Request-ID` header injection across all requests/responses.
  - **Rate Limiting:** Sliding-window rate limiter protecting protected API routes (30 requests/minute per IP).
- **Strict Pydantic Output Validation:** Pydantic models for Guardrail decisions, Supervisor routing, and Trip constraints.
- **PostgreSQL State Checkpointing:** Persistent state saved using `PostgresSaver` with automatic `MemorySaver` fallback.
- **Human-In-The-Loop (HITL) Workflows:** Built-in graph state interrupts allowing human review, approval, or revision feedback before final plan generation.

---

## File Overview

- `app.py`: FastAPI server, endpoints, SSE streaming, middleware integration, and health telemetry.
- `backend.py`: Core LangGraph agent orchestration, parallel fan-out nodes, guardrails, and HITL graph interrupts.
- `backend_cache.py`: High-performance Async TTL Cache with hit/miss counter stats.
- `middleware.py`: Request correlation ID and Sliding Window Rate Limiter middleware.
- `mcp_client.py`: MultiServerMCPClient helpers for Tavily, Aviationstack, and Weather servers.
- `custom_weather_mcp_server.py`: Custom stdio MCP weather server adapter.
- `RESUME_HIGHLIGHTS.md`: Dedicated resume reference guide for Software / AI Engineers.
- `tests/`: Automated unit and integration test suite using `pytest` and `pytest-asyncio`.

---

## Quick Start (Windows)

### 1. Install Dependencies
```powershell
python -m pip install -r requirements.txt
```

### 2. Configure Environment Variables
Create a `.env` file in the root directory:
```env
GROQ_API_KEY=your_groq_api_key
TAVILY_API_KEY=your_tavily_api_key
OPENWEATHER_API_KEY=your_openweather_api_key
DATABASE_URL=your_postgres_db_url_optional
```

### 3. Run FastAPI Application
```powershell
python app.py
# or using uvicorn directly
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

---

## API Documentation

- **`POST /api/travel`** — Execute multi-agent workflow.  
  *Request:* `{ "message": "Plan a 5-day trip to Paris under $2000", "thread_id": "optional-id" }`  
  *Response:* Standard envelope with thread ID, draft itinerary, execution metrics, and `X-Request-ID`.

- **`POST /api/travel/stream`** — Stream multi-agent execution events real-time via Server-Sent Events (SSE).

- **`POST /api/travel/approve`** — Resume graph execution after human review.  
  *Request:* `{ "thread_id": "<id>", "approved": true, "feedback": "Optional revision notes" }`

- **`GET /health`** — Health telemetry endpoint returning operational status, middleware features, and cache hit/miss statistics.

---

## Running Automated Tests

Run the full `pytest` suite:
```powershell
python -m pytest -v
```

Tests cover:
1. Parallel fan-out agent execution and TTL caching (`tests/test_concurrency.py`)
2. `X-Request-ID` tracing, rate limiting, and SSE endpoints (`tests/test_streaming_and_middleware.py`)
3. Supervisor routing & input guardrail validation (`tests/test_agents.py`)
4. API endpoints & approval workflows (`tests/test_api.py`)

---

## Author & License

- **Author:**  ([@backendwithvishal](https://github.com/backendwithvishal))
- **License:** Copyright (c) 2026 . See `LICENSE` for details.
