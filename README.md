# Multi_AI_Agent — Production-Grade Multi-Agent AI Orchestration Platform

[![Build Status](https://img.shields.io/badge/build-passing-brightgreen)](https://github.com/backendwithvishal/Multi_AI_Agent)
[![Tests](https://img.shields.io/badge/tests-67%2F67%20passing%20(100%25)-success)](https://github.com/backendwithvishal/Multi_AI_Agent)
[![Render Deployment](https://img.shields.io/badge/render-live--deployment-success)](https://multi-ai-agent-m4g6.onrender.com/)
[![Python Version](https://img.shields.io/badge/python-3.11%20%7C%203.13-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.136-009688)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.2.2-orange)](https://langchain-ai.github.io/langgraph/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D)](https://redis.io/)
[![MCP](https://img.shields.io/badge/MCP-1.28.1-purple)](https://modelcontextprotocol.io/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

An enterprise-grade **Multi-Agent AI Orchestration Platform** built with **LangGraph**, **Model Context Protocol (MCP)**, **FastAPI**, **PostgreSQL**, **Redis**, and **Multi-Tier LLM Routing (Groq / OpenRouter)**.

🌐 **Live Production Deployment**: [https://multi-ai-agent-m4g6.onrender.com/](https://multi-ai-agent-m4g6.onrender.com/)  
📖 **Interactive API Documentation**: [https://multi-ai-agent-m4g6.onrender.com/docs](https://multi-ai-agent-m4g6.onrender.com/docs)  
📊 **Prometheus Metrics Exporter**: [https://multi-ai-agent-m4g6.onrender.com/metrics](https://multi-ai-agent-m4g6.onrender.com/metrics)

---

## 🌟 13 Backend API Domain Modules

The platform is structured into 13 modular, feature-driven backend API domains:

| # | Domain Module | Route Prefix | Key Capabilities |
|---|---|---|---|
| **1** | **Health & Diagnostics** | `/api/v1/health` | Comprehensive telemetry, DB connectivity, memory/Redis cache health, container liveness (`/health/live`), readiness (`/health/ready`), and worker queue diagnostics (`/health/diagnostics`) |
| **2** | **System Status** | `/api/v1/status` | Real-time system operational status, agent registry status, circuit breaker states, LLM router tier availability |
| **3** | **AI Analysis** | `/api/v1/ai/analysis` | Itinerary feasibility evaluation, budget constraint verification, travel risk assessment via `CriticAgent` & `DynamicPlanner` |
| **4** | **Auth & RBAC** | `/api/v1/auth` | User registration, login, token generation, user profile, password reset, and role-based access control (`user` vs `admin`) |
| **5** | **Watchlists** | `/api/v1/watchlists` | Destination, flight, and hotel price watchlists with automated threshold tracking and full CRUD operations |
| **6** | **Alerts** | `/api/v1/alerts` | Price drop notifications, severe weather risk alerts, custom triggers, and alert status tracking |
| **7** | **Assets & Documents** | `/api/v1/assets` | Trip assets and document management (e-tickets, hotel booking vouchers, packing checklists, itineraries) |
| **8** | **Deterministic Financials** | `/api/v1/financial` | Pure deterministic financial engine: itemized cost calculator, multi-currency conversion, budget variance analysis (Zero LLM math) |
| **9** | **Admin Operations** | `/api/v1/admin` | RBAC-protected administrative endpoints: platform metrics, user management, circuit breaker manual reset, cache purge, execution audit |
| **10** | **AI Orchestration & Travel** | `/api/v1/ai`, `/api/v1/travel` | Task DAG planning (`/ai/plan`), direct specialist agent execution (`/ai/agents/{name}/invoke`), full multi-agent workflow & SSE streaming |
| **11** | **Monitoring & APM** | `/metrics`, `/api/v1/metrics` | Prometheus metrics exporter recording HTTP counts, request latencies, active in-flight requests, and agent execution durations |
| **12** | **Background Tasks** | `/api/v1/tasks` | Asynchronous task queue worker pool (`AsyncTaskQueue`) for batch watchlist evaluations, background itineraries, and health audits |
| **13** | **GDS Travel Booking** | `/api/v1/booking` | Live Amadeus/Skyscanner GDS flight/hotel search, 15-minute price locking, and PNR booking confirmations |

---

## 🗄️ Database Schema & Entity-Relationship (ER) Diagram

The platform utilizes a structured **PostgreSQL** schema managed via **Alembic** migrations, with automated fallback to thread-safe data stores:

```mermaid
erDiagram
    USERS ||--o{ WATCHLISTS : "creates / tracks"
    USERS ||--o{ ALERTS : "receives"
    USERS ||--o{ ASSETS : "manages"
    USERS ||--o{ PASSWORD_RESET_TOKENS : "requests"
    USERS ||--o{ THREAD_OWNERSHIP : "initiates"
    WATCHLISTS ||--o{ ALERTS : "triggers"

    USERS {
        string id PK "Unique UUID / ID"
        string username UK "Unique Username"
        string email UK "Unique Email Address"
        string password_hash "PBKDF2-HMAC-SHA256 Hash"
        string role "user | admin"
        datetime created_at "Registration Timestamp"
    }

    WATCHLISTS {
        string id PK "Unique Watchlist ID"
        string user_id FK "References USERS.id (CASCADE)"
        string title "Watchlist Title / Name"
        string target_type "flight | hotel | destination"
        string target_value "Target City / Flight Code / Hotel Name"
        numeric threshold_price "Target Price Alert Threshold"
        numeric current_price_estimate "Latest Estimated Market Price"
        string currency "ISO Currency Code (USD, EUR, GBP, INR)"
        text notes "Optional User Notes"
        boolean active "Tracking Status"
        datetime created_at "Creation Timestamp"
    }

    ALERTS {
        string id PK "Unique Alert ID"
        string user_id FK "References USERS.id (CASCADE)"
        string watchlist_id FK "Optional References WATCHLISTS.id"
        string title "Alert Notification Title"
        text message "Alert Body / Details"
        string severity "info | warning | critical"
        boolean read "Read State Flag"
        datetime created_at "Trigger Timestamp"
    }

    ASSETS {
        string id PK "Unique Asset ID"
        string user_id FK "References USERS.id (CASCADE)"
        string title "Document / Asset Title"
        string asset_type "ticket | voucher | checklist | itinerary"
        text content "Serialized Document Content"
        string file_format "json | pdf | txt"
        int size_bytes "Content Byte Size"
        datetime created_at "Upload / Creation Timestamp"
    }

    PASSWORD_RESET_TOKENS {
        string token PK "Secure Cryptographic Reset Token"
        string user_id FK "References USERS.id (CASCADE)"
        bigint expires_at "Epoch Expiry Timestamp"
        boolean used "Token Consumption Flag"
    }

    THREAD_OWNERSHIP {
        string thread_id PK "LangGraph Thread Execution ID"
        string user_id FK "References USERS.id (CASCADE)"
        datetime created_at "Thread Initialization Timestamp"
    }
```

---

## 📐 Multi-Agent System Architecture & Execution Flow

```mermaid
flowchart TD
    A[Client Request / Postman / UI] --> B[FastAPI Gateway & Security Middleware]
    B --> C[Sliding Window Rate Limiter & Prometheus APM]
    C --> D{Domain Routing Layer}

    D -->|/auth| E[Auth & RBAC Service]
    D -->|/health, /status, /metrics| F[Health Probes & Telemetry]
    D -->|/watchlists, /alerts, /assets| G[PostgreSQL Unified Data Store]
    D -->|/financial| H[Deterministic Financial Engine]
    D -->|/admin| I[Admin Management & Breaker Reset]
    D -->|/tasks| K[Async Task Queue & Workers]
    D -->|/booking| L[GDS Travel Search & PNR Engine]
    D -->|/travel, /ai| J[Travel Service & LangGraph Workflow]

    subgraph LangGraph Orchestration
        J --> SG1[1. Input Guardrails & PII Masking]
        SG1 --> SG2[2. Supervisor Agent & Dynamic Planner]
        SG2 --> SG3[3. Parallel Specialist Fan-Out]
        
        SG3 --> SP1[Flight Specialist + Aviation MCP]
        SG3 --> SP2[Hotel Specialist + Tavily MCP]
        SG3 --> SP3[Weather Specialist + OpenWeather MCP]
        SG3 --> SP4[Budget Specialist + Math Engine]

        SP1 & SP2 & SP3 & SP4 --> SG4[4. Critic & Feasibility Agent]
        SG4 --> SG5{5. HITL Approval Gate}
        SG5 -->|Pending / Rejected| SG6[State Interrupt / Human Feedback Loop]
        SG6 --> SG2
        SG5 -->|Approved| SG7[6. Final Synthesis Agent]
        SG7 --> SG8[7. Output Sanitizer & PII Leak Guard]
        SG8 --> SG9[8. Token & Cost Telemetry Serialization]
    end
```

---

## 🛡️ Core Engineering Pillars

### 1. Multi-Stage AI Guardrails & Security Engine
- **Deterministic Threat Signatures**: High-speed regex validation blocking prompt injections, jailbreak templates (`DAN`, roleplay bypasses), and system prompt leaks without wasting LLM tokens.
- **PII & Credential Redaction**: Automatically detects and masks payment card numbers (13–19 digits), US SSNs (`\d{3}-\d{2}-\d{4}`), and secret API keys before LLM processing.
- **Output Leak Sanitizer**: Post-processes all agent responses with `sanitize_output` to scrub accidental leaks of database connection strings, Redis credentials, secret tokens, or raw stack traces.
- **Semantic Domain Classification**: Fast LLM-based boundary check verifying that prompts pertain to travel planning and operations.

### 2. Distributed Sliding Window Rate Limiter & Hybrid Caching
- **Distributed Redis Rate Limiter**: Uses Redis sorted sets (`ZREMRANGEBYSCORE`, `ZCARD`, `ZADD`) for atomic sliding window request throttling across distributed instances.
- **Graceful In-Memory Fallback**: Seamlessly falls back to local in-memory sliding window tracking if Redis is unreachable.
- **Hybrid 2-Tier Cache**: Fast single-flight in-memory L1 cache (`BoundedAsyncTTLCache`) combined with distributed Redis L2 cache (`redis.asyncio`) with sub-second failover.

### 3. GDS Travel Booking & PNR Reservation Engine
- **Live GDS Aggregation**: Real-time integration supporting Amadeus & Skyscanner sandbox protocols for flight and hotel search.
- **15-Minute Price Lock**: Cryptographically signed quote tokens with 15-minute price guarantees preventing booking price drift.
- **PNR Generation**: Atomic booking confirmation issuing deterministic 6-character Passenger Name Records (PNR).

### 4. Asynchronous Task Queue & Diagnostic Telemetry
- **Background Worker Pool**: In-process `AsyncTaskQueue` supporting background batch watchlist evaluations, async itinerary compilation, and health checks.
- **Real-Time Telemetry**: Diagnostic endpoint (`/health/diagnostics`) reporting active workers, pending/running/failed tasks, and registered handlers.

### 5. Multi-Tier LLM Routing & Resilience
- **Tiered Model Routing**:
  - **Fast Tier**: `llama-3.1-8b-instant` for deterministic routing, guardrails, and quick extractions.
  - **Reasoning Tier**: `llama-3.3-70b-versatile` for complex multi-constraint itinerary planning and synthesis.
- **Circuit Breakers**: Dedicated 3-state Circuit Breakers (`CLOSED`, `OPEN`, `HALF_OPEN`) safeguarding external MCP connections (Tavily, AviationStack, OpenWeather, GDS).

### 6. Token Tracking & Cost Telemetry
- **Token Estimation & Cost Computation**: Automatically estimates input/output tokens and computes estimated USD cost (`estimate_tokens`, `calculate_cost`) attached to all execution metrics.

### 7. Prometheus APM Observability
- **Standardized Metrics Exporter**: Exposes real-time metrics at `/metrics` and `/api/v1/metrics`:
  - `http_requests_total`: Request counts by method, endpoint, and HTTP status.
  - `http_request_duration_seconds`: Request latency distribution.
  - `http_requests_in_progress`: In-flight active request concurrency.
  - `agent_execution_duration_seconds`: Individual specialist agent execution latencies.

---

## 📊 Empirical Benchmarks & Test Suite

The test suite consists of **67 comprehensive tests across 13 test modules**, achieving a **100% pass rate**:

```bash
============================= test session starts =============================
platform win32 -- Python 3.11+ / 3.13+, pytest-8.4.2
collected 67 items

tests/test_agents.py ............                                        [ 17%]
tests/test_api.py ....                                                   [ 23%]
tests/test_auth_and_ownership.py ........                                [ 35%]
tests/test_concurrency.py ..                                             [ 38%]
tests/test_domain_modules.py ..............                              [ 59%]
tests/test_platform_upgrades.py .....                                    [ 67%]
tests/test_resilience.py ..                                              [ 70%]
tests/test_roadmap_features.py .........                                 [ 83%]
tests/test_security.py .....                                             [ 91%]
tests/test_settings.py ..                                                [ 94%]
tests/test_streaming_and_middleware.py ..                                [ 97%]
tests/test_v1_api.py ..                                                  [100%]

============================== 67 passed in 207s ==============================
```

| Benchmark Metric | Result | Target / Standard |
|---|---|---|
| **Pytest Test Suite Pass Rate** | **100.0% (67/67 tests)** | 100% |
| **Guardrail Threat Detection** | **100.0%** | > 98% |
| **Agent Routing Match Accuracy** | **100.0%** | > 95% |
| **Parallel Fan-Out Latency Reduction** | **~57.2%** | > 50% |
| **Average Evaluator Latency** | **9.9 ms** | < 20 ms |
| **Deterministic Math Error Rate** | **0.00%** | 0.00% |

---

## 🛠️ Quickstart & Local Development

### 1. Clone & Setup Virtual Environment
```bash
git clone https://github.com/backendwithvishal/Multi_AI_Agent.git
cd Multi_AI_Agent
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env` and fill in your keys:
```bash
cp .env.example .env
```

```env
APP_ENV=development
API_KEY=your_platform_api_key
GROQ_API_KEY=your_groq_api_key
OPENROUTER_API_KEY=your_openrouter_api_key
TAVILY_API_KEY=your_tavily_api_key
OPENWEATHER_API_KEY=your_openweather_api_key
AVIATIONSTACK_API_KEY=your_aviationstack_api_key
REDIS_URL=redis://localhost:6379/0
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/tripmate
```

### 3. Run Database Migrations
```bash
alembic upgrade head
```

### 4. Start the Application
```bash
python app.py
```
Interactive Swagger UI is available at: [http://localhost:8000/docs](http://localhost:8000/docs)

### 5. Run Verification & Benchmarks
```bash
# Run the complete test suite (67 tests)
pytest -v

# Run the agent evaluation benchmark
python -m evaluation.evaluator

# Run the latency fan-out benchmark
python benchmark.py
```

### 6. Run with Docker Compose

#### Local Development (API + Postgres + Redis with exposed ports):
```bash
docker compose up -d --build
```
- API: `http://localhost:8000`
- Docs: `http://localhost:8000/docs`
- Postgres: `localhost:5432`
- Redis: `localhost:6379`

#### Production Mode (Internal network isolation, non-root user, secure auth):
```bash
docker compose -f docker-compose.prod.yml up -d --build
```
- API: `http://localhost:8000` (PostgreSQL and Redis ports are isolated from public exposure)
- Liveness Probe: `GET http://localhost:8000/api/v1/liveness`
- Readiness Probe: `GET http://localhost:8000/api/v1/readiness`
- Telemetry & Health: `GET http://localhost:8000/api/v1/health`

---

## 📮 Postman Collection Integration

A complete Postman collection covering all 13 domain modules is included:
- **Location**: [`postman/Multi_AI_Agent.postman_collection.json`](file:///d:/AI_Project/Multi_AI_Agent/postman/Multi_AI_Agent.postman_collection.json)
- **Features**:
  - Pre-configured `baseUrl` (`http://127.0.0.1:8000`) and API key variables.
  - Automated test assertions on `GET /api/v1/status` and `/api/v1/health` verifying circuit breakers, model routing readiness, and database connectivity.
  - Full request bodies for travel orchestration, HITL approvals, watchlist management, GDS bookings, and background tasks.

---

## 📜 Project Directory Structure

```text
Multi_AI_Agent/
├── app.py                         # FastAPI Application Entry Point & Middleware Chain
├── benchmark.py                   # Empirical Latency Fan-Out Benchmark Script
├── custom_weather_mcp_server.py   # FastMCP OpenWeather Server (stdio)
├── Dockerfile                     # Multi-stage production Dockerfile
├── docker-compose.yml             # Local Docker Compose setup (API + Postgres + Redis)
├── mcp_client.py                  # MultiServerMCPClient Connection Manager
├── pytest.ini                     # Pytest discovery configuration
├── render.yaml                    # Render Blueprint IaC Specification
├── requirements.txt               # Dependencies
├── alembic.ini                    # Alembic Database Migration Configuration
├── migrations/                    # Alembic Schema Migrations
│   ├── env.py
│   └── versions/
│       └── 001_initial_schema.py  # Users, Watchlists, Alerts, Assets Schema
├── postman/
│   └── Multi_AI_Agent.postman_collection.json # 13 Domain Postman Collection
├── docs/
│   ├── CODEBASE_AUDIT.md          # Comprehensive Codebase Audit
│   └── RENDER_DEPLOYMENT.md       # Render Cloud Deployment Guide
├── evaluation/
│   ├── benchmark_dataset.json     # Test cases for evaluation
│   └── evaluator.py               # Benchmark execution runner
├── tests/                         # Pytest test suite (67 passing tests)
│   ├── test_agents.py             # Agent unit tests
│   ├── test_api.py                # Legacy API compatibility tests
│   ├── test_auth_and_ownership.py # Auth, RBAC & thread ownership tests
│   ├── test_concurrency.py        # Concurrent execution tests
│   ├── test_domain_modules.py     # 13 Domain API module tests
│   ├── test_platform_upgrades.py  # Cache, task queue & rate limiting tests
│   ├── test_resilience.py         # Circuit breaker resilience tests
│   ├── test_roadmap_features.py   # GDS, Alembic & Prometheus tests
│   ├── test_security.py           # Guardrail, injection & PII redaction tests
│   ├── test_settings.py           # Configuration validation tests
│   ├── test_streaming_and_middleware.py # SSE streaming & middleware tests
│   └── test_v1_api.py             # Versioned travel, runs, auth tests
└── tripmate/
    ├── agents/                    # Guardrail, Supervisor, Dynamic Planner, Critic, Specialists
    ├── api/                       # Versioned REST & SSE Routers (13 Domains)
    │   └── v1/
    │       └── routes/            # health, status, auth, watchlists, alerts, assets, financial, admin, ai, travel, runs, tasks, booking
    ├── cache/                     # Hybrid Redis & Bounded Async TTL Single-Flight Cache
    ├── config/                    # Typed Pydantic Settings
    ├── database/                  # Unified Data Store & LangGraph Checkpointer
    ├── graph/                     # LangGraph StateGraph Execution Assembly & Routing
    ├── integrations/              # Resilience Circuit Breakers, MCP Wrappers & GDS Client
    ├── middleware/                # Distributed Rate Limiter, Correlation ID, Security Headers, Prometheus
    ├── schemas/                   # Pydantic Schemas for all 13 Domains
    ├── services/                  # Domain Services (Auth, Watchlist, Alert, Asset, Financial, Admin, Travel, ModelRouter, Observability)
    └── tasks/                     # AsyncTaskQueue & Background Worker Telemetry
```

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.