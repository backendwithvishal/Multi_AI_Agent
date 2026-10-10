# Postman Testing Guide — TripMate AI Multi-Agent Backend

This directory contains everything you need to test the entire TripMate AI Multi-Agent API in Postman.

---

## 1. Files Included

| File | Description |
|---|---|
| [`Multi_AI_Agent.postman_collection.json`](file:///d:/AI_Project/Multi_AI_Agent/postman/Multi_AI_Agent.postman_collection.json) | Complete collection containing all **15 domain modules**, **40+ endpoints**, integration tests, and auto-chaining scripts. |
| [`TripMate_Local.postman_environment.json`](file:///d:/AI_Project/Multi_AI_Agent/postman/TripMate_Local.postman_environment.json) | Local environment variables (`baseUrl = http://127.0.0.1:8000`, auth tokens, dynamic IDs). |

---

## 2. Quick Start

### Step 1: Start the Backend Server
Open your terminal and run:
```bash
python app.py
```
*The server will start on `http://127.0.0.1:8000` (or `http://localhost:8000`).*

Alternatively, start via Docker Compose:
```bash
docker compose up -d
```

### Step 2: Import into Postman
1. Open **Postman**.
2. Click the **Import** button in the top-left corner.
3. Drag and drop both files:
   - `postman/Multi_AI_Agent.postman_collection.json`
   - `postman/TripMate_Local.postman_environment.json`
4. In the top-right environment selector dropdown, choose **TripMate AI - Local Environment**.

---

## 3. Recommended Testing Workflow

All requests feature **automated variable capture** (auto-chaining) into both Environment and Collection variables, meaning tokens and IDs flow seamlessly into subsequent requests without manual copy-pasting.

### Workflow Sequence:

1. **Verify Connectivity**:
   - `0. Root & Entrypoints` ➔ `GET / (API Information & Navigation Metadata)`
   - `1. Health & Diagnostics` ➔ `GET /api/v1/health`

2. **User Authentication**:
   - `4. Authentication & Identity` ➔ `POST /api/v1/auth/register` (or `POST /api/v1/auth/login (User Login)`)
   - *Automatically captures and sets `accessToken` and `userId`.*

3. **Admin Authentication (for RBAC endpoints)**:
   - `4. Authentication & Identity` ➔ `POST /api/v1/auth/login (Admin Login)`
   - *Pre-filled with `admin / Admin@12345`. Automatically captures and sets `adminAccessToken`.*

4. **Multi-Agent Travel Planning**:
   - `10. AI Orchestration & Travel Planning` ➔ `POST /api/v1/travel (Full Workflow Execution)`
   - *Executes the multi-agent graph (Supervisor ➔ Flight/Hotel/Weather/Budget ➔ Critic ➔ Itinerary). Automatically captures `runId` and `threadId`.*
   - Test Human-in-the-Loop review: `POST /api/v1/travel/approve (HITL Approval)`
   - Test streaming: `POST /api/v1/travel/stream (SSE Event Streaming)`

5. **Observability & Runs**:
   - `11. Workflow Observability, Runs & Replay` ➔ `GET /api/v1/runs/{run_id}`
   - `GET /api/v1/runs/{run_id}/metrics` (Token usage, latency, and estimated cost breakdown)
   - `GET /api/v1/runs/{run_id}/agents` (Specialist outputs & evidence items)

6. **Domain Services**:
   - `5. Travel Watchlists`: Create (`POST`), List (`GET`), Detail (`GET`), Delete (`DELETE`)
   - `6. Alerts & Notifications`: Create (`POST`), List (`GET`), Mark Read (`PUT`), Delete (`DELETE`)
   - `7. Travel Assets & Documents`: Register (`POST`), List (`GET`), Detail (`GET`), Delete (`DELETE`)
   - `8. Financial Engine (Deterministic)`: Cost breakdown (`/calculate`), Currency conversion (`/convert`), Budget variance (`/budget-analysis`)
   - `13. Background Tasks & Queue`: Submit job (`/submit`), Poll status (`/{task_id}`)
   - `14. GDS Travel Booking & Search`: Flight search (`/booking/flights/search`), Hotel search (`/booking/hotels/search`), 15-minute price lock (`/booking/price-lock`), PNR reservation (`/booking/reserve`)
   - `9. Platform Administration (RBAC)`: System stats (`/stats`), Registered users (`/users`), Reset circuit breakers (`/circuit-breakers/{name}/reset`), Cache clear (`/cache/clear`)

---

## 4. Default Seeded Credentials

| Account | Username | Email | Password | Role |
|---|---|---|---|---|
| **Admin** | `admin` | `admin@tripmate.ai` | `Admin@12345` | `admin` |
| **Demo User** | `demouser` | `user@tripmate.ai` | `User@12345` | `user` |
| **Jane Traveler** | `jane_traveler` | `jane@example.com` | `SecurePass123!` | `user` |
