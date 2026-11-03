# Security Policy — Multi-AI-Agent

**Repository:** https://github.com/backendwithvishal/Multi_AI_Agent  
**Maintainer:** [@backendwithvishal](https://github.com/backendwithvishal)

---

## Reporting a Vulnerability

If you discover a security vulnerability, **do not open a public issue.**

Please report it privately:

1. **GitHub Security Advisory** (preferred): [Report a vulnerability](https://github.com/backendwithvishal/Multi_AI_Agent/security/advisories/new)
2. **Email:** Open a GitHub advisory and add a private note with contact details.

We aim to acknowledge reports within **72 hours** and to publish a patch or advisory within **14 days** of a confirmed critical issue.

> [!IMPORTANT]
> This is a personal/portfolio project. There is no paid security team or 24/7 on-call. SLAs are best-effort.

---

## Supported Versions

| Version | Supported |
|---------|-----------|
| 3.0.x   | ✅ Yes — current development branch |
| < 3.0   | ❌ No — no backport patches planned |

---

## Verified Security Controls

Each control below is verified by the named automated test. The build fails if any listed test name does not exist in the test suite (enforced by `tests/test_docs.py::TestSecurityControlMapping`).

### Authentication & Authorization

| Control | Description | Verified by |
|---------|-------------|-------------|
| API key authentication | Bearer token required when `AUTH_REQUIRED=true` | `test_v1_authentication_enforcement` |
| JWT validation | Invalid or forged tokens rejected with 401 | `test_auth_enforcement_invalid_token` |
| Admin role enforcement | Admin endpoints require `role=admin`; regular users receive 403 | `test_admin_module_rbac` |
| Thread ownership isolation | Users can only access their own workflow threads | `test_idor_cross_tenant_thread_ownership` |
| Password recovery flow | Token-based password recovery and reset validation | `test_password_recovery_flow` |

### Input Validation & Injection Prevention

| Control | Description | Verified by |
|---------|-------------|-------------|
| Prompt injection detection | Deterministic input guardrail blocks known injection patterns | `test_deterministic_guardrail_checks` |
| Message length limit | `MAX_MESSAGE_LENGTH` (default 2 000 chars) enforced on travel requests | `test_validation_input_length_limit` |
| Request body size limit | `MAX_REQUEST_BODY_BYTES` (default 1 MB) enforced by middleware | `test_request_body_size_limit_middleware` |
| Thread ID validation | Thread IDs validated against `THREAD_ID_REGEX` | `test_validation_thread_id_regex` |
| PII redaction | Sensitive fields masked before downstream processing | `test_pii_masking_engine` |

### Network & SSRF Prevention

| Control | Description | Verified by |
|---------|-------------|-------------|
| SSRF tool protection | Outbound tool calls restricted and guarded against localhost/private IPs | `test_ssrf_protection_in_weather_tool` |
| Trusted proxy headers | `X-Forwarded-For` only trusted from configured proxy IPs | `test_client_ip_from_trusted_proxy` |

### Rate Limiting & Abuse Control

| Control | Description | Verified by |
|---------|-------------|-------------|
| Sliding window rate limiter | `RATE_LIMIT_REQUESTS` / `RATE_LIMIT_WINDOW_SECONDS` enforced per IP | `test_sliding_window_rate_limiter_exceeded` |
| Emergency in-memory fallback | When Redis is unavailable, an emergency cap on LLM routes applies | `test_redis_down_emergency_cap_on_llm_routes` |
| Token / budget validation | Trip cost and budgets checked against feasibility boundaries | `test_financial_budget_check` |

### Data & Secrets Hygiene

| Control | Description | Verified by |
|---------|-------------|-------------|
| Telemetry privacy default | Distributed telemetry and tracing off by default | `test_opentelemetry_off_by_default_and_toggled_via_env` |
| Health endpoints leak no secrets | `/api/v1/health` and `/health/ready` responses contain no API keys | `test_health_ready_response_has_no_secrets` |
| Production secret validation | Startup rejects missing mandatory configuration in production | `test_settings_validate_production` |

### Security Headers

| Control | Description | Verified by |
|---------|-------------|-------------|
| Security headers middleware | `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Content-Security-Policy` set on every response | `test_security_headers_present` |

---

## Out of Scope

The following are **not** in scope for security reports on this project:

- Vulnerabilities in third-party dependencies not directly in this codebase (report upstream)
- Social engineering attacks against maintainers
- Physical security issues
- Denial of service via network flooding (rate limiting is in-process; no WAF is deployed)
- Issues only reproducible on unsupported versions (< 3.0)

---

## Realistic SLA

| Severity | Acknowledgement | Target Patch |
|----------|----------------|--------------|
| Critical (RCE, auth bypass) | 72 hours | 14 days |
| High (data exposure, privilege escalation) | 1 week | 30 days |
| Medium/Low | 2 weeks | Next release cycle |

> [!WARNING]
> This project has no formal SLA or uptime guarantee. Response times are best-effort by a single maintainer.

