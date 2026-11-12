# Architecture — Multi-AI-Agent

> [!NOTE]
> This document describes the production architecture as of **v3.0.0** (commit on 2026-11-03).  
> Component paths reference the repository root.

---

## System Overview

Multi-AI-Agent is a **FastAPI** application that orchestrates a team of AI specialist agents using **LangGraph** state graphs, coordinated via **MCP** (Model Context Protocol) tool servers, persisted with **PostgreSQL**, and cached with **Redis**.

```mermaid
flowchart TD
    Client["HTTP Client\n(browser / curl / SDK)"]
    FastAPI["FastAPI App\napp.py"]

    subgraph Middleware
        RateLimit["Sliding-Window\nRate Limiter"]
        Auth["Bearer Auth\nDependency"]
        CorrelID["Request-ID\nMiddleware"]
        SecHeaders["Security Headers\nMiddleware"]
        BodyLimit["Body Size\nLimit Middleware"]
        Prometheus["Prometheus\nMetrics Middleware"]
    end

    subgraph API["REST API  /api/v1/"]
        Health["health / liveness / readiness"]
        Status["status"]
        AuthRoutes["auth  (register / login / me)"]
        Travel["travel  (POST, POST /stream)"]
        Approval["travel/approve"]
        Watchlists["watchlists"]
        Alerts["alerts"]
        Assets["assets"]
        Financial["financial"]
        AI["ai/plan, ai/agents/{name}/invoke, ai/analysis"]
        Booking["booking (flights, hotels, price-lock, reserve)"]
        Runs["runs (details, metrics, agents, replay)"]
        Tasks["tasks (submit, get, list, cancel)"]
        Admin["admin (stats, users, circuit-breakers, cache, runs)"]
        Metrics["metrics (Prometheus scrape)"]
    end

    subgraph Graph["LangGraph Workflow"]
        Guardrail["Input Guardrail\nAgent"]
        Supervisor["Supervisor\nAgent"]
        Planner["Dynamic Planner\nDAG"]
        Specialists["Specialist Agents\n(flight, hotel, weather,\nbudget, itinerary)"]
        Critic["Critic\nAgent"]
        HITL["Human-In-The-Loop\nCheckpoint"]
        Synthesizer["Synthesis Node"]
    end

    subgraph MCPLayer["MCP Tool Servers"]
        WeatherMCP["OpenWeather\nMCP Server (stdio)"]
        TavilyMCP["Tavily Search\nMCP (remote)"]
        AviationMCP["AviationStack\nMCP (remote)"]
    end

    subgraph Persistence
        Postgres["PostgreSQL 16\nUsers · Watchlists · Alerts · Assets"]
        PgCheckpointer["LangGraph\nPostgresSaver Checkpointer"]
        Redis["Redis 7\nHybrid Cache\n(rate-limiting · MCP cache · response TTL)"]
        MemorySaver["MemorySaver\n(dev fallback only)"]
    end

    subgraph Observability
        LangSmith["LangSmith\n(optional tracing)"]
        PrometheusExport["/metrics Prometheus\nExporter"]
        AuditLog["In-Memory\nAudit Logger"]
    end

    Client --> FastAPI
    FastAPI --> Middleware --> API
    Travel --> Graph
    Approval --> Graph
    Graph --> MCPLayer
    Graph --> Persistence
    Graph --> Observability
    Travel --> Persistence
    AuthRoutes --> Persistence
    Watchlists --> Persistence
    Alerts --> Persistence
    Assets --> Persistence
    Booking --> MCPLayer
```

---

## Component Map

| Path | Role |
|------|------|
| [`app.py`](../app.py) | FastAPI application factory; middleware chain; lifespan hooks |
| [`tripmate/config/settings.py`](../tripmate/config/settings.py) | Pydantic Settings — single source of truth for all env vars |
| [`tripmate/api/v1/routes/`](../tripmate/api/v1/routes/) | All REST routers (16 files, 13 domains) |
| [`tripmate/agents/`](../tripmate/agents/) | Guardrail, Supervisor, Planner, Critic, Specialist agents |
| [`tripmate/graph/workflow.py`](../tripmate/graph/workflow.py) | LangGraph StateGraph assembly & routing |
| [`tripmate/services/travel_service.py`](../tripmate/services/travel_service.py) | Orchestrates workflow execution, streaming, HITL, run storage |
| [`tripmate/services/model_router.py`](../tripmate/services/model_router.py) | Multi-tier LLM provider selection (Groq → OpenRouter → HuggingFace) |
| [`tripmate/cache/redis_cache.py`](../tripmate/cache/redis_cache.py) | Hybrid Redis + bounded in-memory TTL cache |
| [`tripmate/database/`](../tripmate/database/) | PostgreSQL pool, store, Alembic migrations, checkpointer |
| [`tripmate/integrations/`](../tripmate/integrations/) | Circuit breakers, MCP wrappers, GDS client |
| [`tripmate/middleware/`](../tripmate/middleware/) | Rate limiter, security headers, correlation ID, body limit, Prometheus |
| [`mcp_client.py`](../mcp_client.py) | MultiServerMCPClient session manager |
| [`custom_weather_mcp_server.py`](../custom_weather_mcp_server.py) | FastMCP OpenWeather stdio server |

---

## Core Design & Architecture Principles

The codebase emphasizes lean, maintainable, production-ready engineering:

- **State Machine**: LangGraph `StateGraph` in [`tripmate/graph/workflow.py`](../tripmate/graph/workflow.py) coordinates multi-agent routing.
- **Provider Strategy**: Dynamic LLM routing with fallback in [`tripmate/strategies/llm_strategies.py`](../tripmate/strategies/).
- **Resilience**: Circuit breakers in [`tripmate/integrations/circuit_breaker.py`](../tripmate/integrations/).
- **Data Adapters**: Output normalization in [`tripmate/adapters/`](../tripmate/adapters/).
- **Singleton Resources**: Process-safe singletons via [`tripmate/core/singleton.py`](../tripmate/core/singleton.py).

---

## Data Flow — Travel Request

```mermaid
sequenceDiagram
    participant Client
    participant FastAPI
    participant Guardrail
    participant Supervisor
    participant Specialists
    participant Critic
    participant HITL
    participant Synthesizer

    Client->>FastAPI: POST /api/v1/travel {message, thread_id}
    FastAPI->>Guardrail: Validate input (deterministic checks)
    Guardrail-->>FastAPI: blocked? → 400 / OK → continue
    FastAPI->>Supervisor: Plan & delegate
    Supervisor->>Planner: Build Task DAG
    Planner-->>Supervisor: DAG with agent assignments
    Supervisor->>Specialists: Parallel execution (flight, hotel, weather…)
    Specialists-->>Supervisor: Structured outputs
    Supervisor->>Critic: Quality & completeness check
    Critic-->>Supervisor: Score + violations
    alt score >= threshold
        Supervisor->>Synthesizer: Merge & format itinerary
        Synthesizer-->>FastAPI: Final answer
    else needs HITL
        Supervisor->>HITL: Pause workflow
        FastAPI-->>Client: 200 {status: pending_approval, thread_id}
        Note over Client,HITL: User reviews draft
        Client->>FastAPI: POST /api/v1/travel/approve {thread_id, approved}
        FastAPI->>HITL: Resume with decision
        HITL->>Synthesizer: Continue
        Synthesizer-->>FastAPI: Final answer
    end
    FastAPI-->>Client: 200 {success, data: {answer, run_id, …}}
```

---

## LLM Provider Failover

```mermaid
flowchart LR
    R["ModelRouter"] --> G["Groq\nllama-3.1-8b / 3.3-70b"]
    G -- "circuit open or key missing" --> O["OpenRouter\nmeta-llama/…:free"]
    O -- "circuit open or key missing" --> H["HuggingFace\nMeta-Llama-3-…"]
    H -- "all failed" --> E["RuntimeError:\nNo LLM provider available"]
```

---

## Persistence Topology

```mermaid
flowchart LR
    App["FastAPI Workers"]
    App -- "asyncpg pool" --> PG["PostgreSQL 16\n• users\n• watchlists\n• alerts\n• assets\n• checkpoint tables"]
    App -- "redis-py async" --> RD["Redis 7\n• rate-limit sliding windows\n• MCP tool response cache\n• hybrid response cache"]
    App -- "psycopg sync pool" --> CP["LangGraph\nPostgresSaver\n(checkpoint tables)"]
```

---

## Agents

| Agent | Role |
|-------|------|
| **GuardrailAgent** | Deterministic input validation; blocks prompt injection, PII, off-topic |
| **SupervisorAgent** | Routes to planner; aggregates specialist results; decides HITL |
| **ParallelSupervisorAgent** | Runs specialist nodes concurrently via `asyncio.gather` |
| **DynamicPlannerAgent** | Emits a Task DAG with per-task agent assignments |
| **CriticAgent** | Scores itinerary quality; returns violations and recommendations |
| **FlightAgent** | Queries AviationStack via MCP; formats flight options |
| **HotelAgent** | Queries GDS client for hotel availability |
| **WeatherAgent** | Queries OpenWeather via FastMCP stdio server |
| **BudgetAgent** | Runs deterministic financial calculations |
| **ItineraryAgent** | Synthesizes day-by-day itinerary from specialist outputs |

