# Render Deployment Guide — Multi_AI_Agent Platform

This guide outlines step-by-step instructions to deploy **Multi_AI_Agent** on [Render](https://render.com).

**Live Production Deployment**: `https://multi-ai-agent-m4g6.onrender.com/`  
**Live Swagger Documentation**: `https://multi-ai-agent-m4g6.onrender.com/docs`

---

## 1. Prerequisites

1. A Render account ([render.com](https://render.com)).
2. Forked or pushed repository on GitHub: `https://github.com/backendwithvishal/Multi_AI_Agent`.
3. Required API Keys:
   - `GROQ_API_KEY` (Required for LLM inference)
   - `TAVILY_API_KEY` (Required for live web hotel searches)
   - `OPENWEATHER_API_KEY` (Required for weather MCP metrics)
   - `AVIATIONSTACK_API_KEY` (Optional for flight queries)

---

## 2. Recommended Render Architecture

```text
                               Render Web Service
                            (Python 3.11 / Docker)
                                     │
                 ┌───────────────────┴───────────────────┐
                 │                                       │
                 v                                       v
      Render Managed PostgreSQL               Render Managed Redis
    (DATABASE_URL for state saver)           (REDIS_URL for cache)
```

---

## 3. Deployment Option A: Using `render.yaml` (Blueprints)

1. Log into your Render Dashboard and navigate to **Blueprints**.
2. Click **New Blueprint Instance**.
3. Connect your GitHub repository `backendwithvishal/Multi_AI_Agent`.
4. Render will automatically detect `render.yaml` and configure the Web Service.
5. In the Render Dashboard, fill in your secret environment variables (`GROQ_API_KEY`, `TAVILY_API_KEY`, etc.).
6. Click **Apply**. Render will build and launch your containerized service.

---

## 4. Deployment Option B: Manual Web Service Setup

1. Click **New +** -> **Web Service** in Render.
2. Select **Build and deploy from a Git repository**.
3. Select `backendwithvishal/Multi_AI_Agent`.
4. Configure service parameters:
   - **Name**: `tripmate-ai-agent-platform`
   - **Environment**: `Python` (or `Docker`)
   - **Region**: Select closest region (e.g. Singapore / Oregon / Frankfurt)
   - **Branch**: `main`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app:app --host 0.0.0.0 --port $PORT`
5. Add Environment Variables:
   - `APP_ENV` = `production`
   - `GROQ_API_KEY` = `<your-groq-key>`
   - `TAVILY_API_KEY` = `<your-tavily-key>`
   - `OPENWEATHER_API_KEY` = `<your-openweather-key>`
   - `DATABASE_URL` = `<your-render-postgres-url>` (Optional)
   - `REDIS_URL` = `<your-render-redis-url>` (Optional)
6. Click **Create Web Service**.

---

## 5. Environment Variable Verification

Render automatically injects the `$PORT` variable into the container. The application binds to `0.0.0.0:$PORT` automatically.

Verify active endpoints once deployed:
- Health probe: `GET https://<your-render-app>.onrender.com/health`
- Liveness probe: `GET https://<your-render-app>.onrender.com/api/v1/liveness`
- Readiness probe: `GET https://<your-render-app>.onrender.com/api/v1/readiness`
- Interactive API Docs: `https://<your-render-app>.onrender.com/docs`
