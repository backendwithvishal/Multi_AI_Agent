# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versions are single-sourced in [pyproject.toml](pyproject.toml).

---

## [Unreleased]

## [3.1.0] — 2026-11-13

### Added
- **Migration 004**: `004_durability_and_async_persistence.py` creating relational tables:
  - `trips` and `itineraries` with foreign keys and cascade deletion on user/trip delete.
  - `bookings`, `price_locks`, `audit_logs`, `workflow_runs` with `SET NULL` on user delete for GDPR anonymization compliance.
  - Partial unique index on active price locks (`uq_price_locks_active_offer_user`) allowing re-locking after expiry.
  - Schema extensions for `watchlists` (`last_checked_at`), `alerts` (`channel`), and `assets` (`storage_key`, `scan_status` defaulting to `pending` with `clean` backfill).
- **Trips CRUD API**: New owner-scoped endpoints under `/api/v1/trips` and `/api/v1/trips/{trip_id}/itineraries`.
- **SQLAlchemy 2.0 Async Repositories**: Integrated async repositories and session factories with in-memory fallbacks for dev/test environments.
- **CI Postgres Container**: Added PostgreSQL service container to GitHub Actions test workflow to run live database integration tests.


### Removed
- Removed outdated audit archive logs from `docs/archive/` (`AUDIT.md`, `CODEBASE_AUDIT.md`, `OPERATIONS.md`, `THREAT_MODEL.md`).
- Removed synthetic latency simulation script `benchmark.py` and unused evaluation framework `evaluation/`.
- Removed redundant shell wrapper `scripts/verify_pins.sh`.
- Purged local temporary caches, coverage binaries, and scratch files.

## [3.0.0] — 2026-11-03

### Added
- **pyproject.toml** — version now single-sourced; `settings.APP_VERSION` reads from it via `importlib.metadata`.
- **One canonical product name** (`Multi-AI-Agent`) applied to README, FastAPI app title, health output, `.env.example`.
- **SECURITY.md** — verified security controls table with named test references and realistic SLAs.
- **CONTRIBUTING.md** — development setup, PR guidelines, commit message conventions.
- **CODE_OF_CONDUCT.md** — Contributor Covenant v2.1 adaptation.
- **CHANGELOG.md** — this file.
- **docs/ARCHITECTURE.md** — detailed component diagram, data flow, design pattern inventory.
- **docs/RUNBOOK.md** — operations playbook: startup, scaling, incident response, circuit breaker management.
- **docs/THREAT_MODEL.md** — STRIDE threat model for the API surface and AI pipeline.
- **tests/test_docs.py** — doc-accuracy test suite: env var coverage, endpoint coverage, version consistency, SECURITY.md control mapping.
- **tests/test_link_checker.py** — Markdown internal link checker; fails on broken relative paths.
- **tests/test_doc_examples.py** — runs every documented curl/Python example against the TestClient; asserts HTTP status and response fields.

### Changed
- **README.md** — complete rewrite: accurate description, Mermaid architecture diagram, real-features-only quick start (Windows / macOS-Linux / Docker), full env table, API reference with request/response examples and documented error codes, SSE event schema, troubleshooting section, known limitations.
- **LICENSE** — copyright holder updated to `backendwithvishal`.
- **Settings** — `APP_NAME` default updated to `Multi-AI-Agent`; `APP_VERSION` now resolved from `pyproject.toml`.

### Removed
- Unsubstantiated performance claims ("~60% latency reduction", "~40% fewer API calls", "enterprise-grade") — no load-test data or methodology existed to support them.
- Broken `RESUME_HIGHLIGHTS.md` link — file did not exist; link removed.

---

## [2.x and earlier]

Legacy development iterations. No formal changelog maintained.

