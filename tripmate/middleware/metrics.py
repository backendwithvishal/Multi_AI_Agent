"""
Prometheus Metrics Middleware & Instrumentation Registry

Zero-overhead, pure-Python Prometheus metric collector that tracks:
1. HTTP request counts, status codes, and latency histograms.
2. Concurrent in-flight HTTP requests and workflow runs.
3. Per-agent execution counts, runtimes, and failures.
4. Cache hits and misses across Redis and in-memory tiers.
5. Rate-limiting rejections by route.
6. LLM token consumption (prompt/completion/total) and estimated cost in USD.
7. Checkpoint DB operation latencies.
8. Circuit breaker operational states (CLOSED=0, HALF_OPEN=1, OPEN=2).
"""

import threading
import time
from typing import Dict, List, Optional, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Standard Prometheus histogram duration buckets (in seconds)
DEFAULT_LATENCY_BUCKETS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)

# Reference LLM estimated token costs per 1,000,000 tokens
MODEL_PRICING_PER_MILLION = {
    "llama-3.3-70b-versatile": {"prompt": 0.59, "completion": 0.79},
    "llama-3.1-8b-instant": {"prompt": 0.05, "completion": 0.08},
    "meta-llama/llama-3.3-70b-instruct:free": {"prompt": 0.0, "completion": 0.0},
    "meta-llama/llama-3.1-8b-instruct:free": {"prompt": 0.0, "completion": 0.0},
}
DEFAULT_PRICING = {"prompt": 0.30, "completion": 0.60}


class PrometheusMetricsRegistry:
    """Thread-safe Prometheus in-memory metric collector."""

    def __init__(self):
        self._lock = threading.Lock()
        self._start_time = time.time()

        # HTTP metrics
        # {(method, path, status_code): count}
        self._http_requests_total: Dict[Tuple[str, str, int], int] = {}
        # {(method, path): [sum_seconds, count]}
        self._http_request_duration_seconds: Dict[Tuple[str, str], List[float]] = {}
        # {(method, path, bucket_le): count}
        self._http_request_duration_buckets: Dict[Tuple[str, str, float], int] = {}
        self._active_requests: int = 0
        self._inflight_runs: int = 0

        # Agent execution metrics
        # {(agent_name, status): count}
        self._agent_executions_total: Dict[Tuple[str, str], int] = {}
        # {agent_name: count}
        self._agent_failures_total: Dict[str, int] = {}
        # {agent_name: [sum_seconds, count]}
        self._agent_duration_seconds: Dict[str, List[float]] = {}

        # Cache metrics
        # {cache_type: count}
        self._cache_hits_total: Dict[str, int] = {}
        self._cache_misses_total: Dict[str, int] = {}

        # Rate limiter rejections
        # {route: count}
        self._rate_limit_rejections_total: Dict[str, int] = {}

        # LLM token and cost tracking
        # {(model, type): count}
        self._llm_tokens_total: Dict[Tuple[str, str], int] = {}
        # {model: cost_usd}
        self._llm_cost_dollars_total: Dict[str, float] = {}

        # Checkpoint DB latencies
        self._checkpoint_db_latencies: List[float] = [0.0, 0]  # [sum, count]
        self._checkpoint_db_buckets: Dict[float, int] = {}

        # Circuit breaker states
        # {service_name: state_code}
        self._circuit_breaker_states: Dict[str, int] = {}

    def inc_active_requests(self) -> None:
        with self._lock:
            self._active_requests += 1

    def dec_active_requests(self) -> None:
        with self._lock:
            self._active_requests = max(0, self._active_requests - 1)

    def inc_inflight_runs(self) -> None:
        with self._lock:
            self._inflight_runs += 1

    def dec_inflight_runs(self) -> None:
        with self._lock:
            self._inflight_runs = max(0, self._inflight_runs - 1)

    def set_inflight_runs(self, count: int) -> None:
        with self._lock:
            self._inflight_runs = max(0, count)

    def record_http_request(self, method: str, path: str, status_code: int, duration_seconds: float) -> None:
        normalized_path = self._normalize_path(path)
        with self._lock:
            # 1. Total count
            key = (method.upper(), normalized_path, status_code)
            self._http_requests_total[key] = self._http_requests_total.get(key, 0) + 1

            # 2. Duration summary
            dur_key = (method.upper(), normalized_path)
            if dur_key not in self._http_request_duration_seconds:
                self._http_request_duration_seconds[dur_key] = [0.0, 0]
            self._http_request_duration_seconds[dur_key][0] += duration_seconds
            self._http_request_duration_seconds[dur_key][1] += 1

            # 3. Histogram buckets
            for bucket in DEFAULT_LATENCY_BUCKETS:
                bkey = (method.upper(), normalized_path, bucket)
                if duration_seconds <= bucket:
                    self._http_request_duration_buckets[bkey] = self._http_request_duration_buckets.get(bkey, 0) + 1

    def record_agent_execution(self, agent_name: str, status: str, duration_seconds: float) -> None:
        with self._lock:
            key = (agent_name, status)
            self._agent_executions_total[key] = self._agent_executions_total.get(key, 0) + 1

            if status in ("failure", "degraded", "error"):
                self._agent_failures_total[agent_name] = self._agent_failures_total.get(agent_name, 0) + 1

            if agent_name not in self._agent_duration_seconds:
                self._agent_duration_seconds[agent_name] = [0.0, 0]
            self._agent_duration_seconds[agent_name][0] += duration_seconds
            self._agent_duration_seconds[agent_name][1] += 1

    def record_cache_hit(self, cache_type: str = "memory") -> None:
        with self._lock:
            self._cache_hits_total[cache_type] = self._cache_hits_total.get(cache_type, 0) + 1

    def record_cache_miss(self, cache_type: str = "memory") -> None:
        with self._lock:
            self._cache_misses_total[cache_type] = self._cache_misses_total.get(cache_type, 0) + 1

    def record_rate_limit_rejection(self, route: str) -> None:
        normalized_route = self._normalize_path(route)
        with self._lock:
            self._rate_limit_rejections_total[normalized_route] = (
                self._rate_limit_rejections_total.get(normalized_route, 0) + 1
            )

    def record_llm_tokens(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_dollars: Optional[float] = None,
    ) -> None:
        total_tokens = prompt_tokens + completion_tokens
        with self._lock:
            self._llm_tokens_total[(model, "prompt")] = self._llm_tokens_total.get((model, "prompt"), 0) + prompt_tokens
            self._llm_tokens_total[(model, "completion")] = (
                self._llm_tokens_total.get((model, "completion"), 0) + completion_tokens
            )
            self._llm_tokens_total[(model, "total")] = self._llm_tokens_total.get((model, "total"), 0) + total_tokens

            # Calculate estimated cost
            if cost_dollars is not None:
                est_cost = cost_dollars
            else:
                pricing = MODEL_PRICING_PER_MILLION.get(model, DEFAULT_PRICING)
                est_cost = (prompt_tokens * pricing["prompt"] / 1_000_000.0) + (
                    completion_tokens * pricing["completion"] / 1_000_000.0
                )

            self._llm_cost_dollars_total[model] = self._llm_cost_dollars_total.get(model, 0.0) + est_cost

    def record_checkpoint_db_latency(self, duration_seconds: float) -> None:
        with self._lock:
            self._checkpoint_db_latencies[0] += duration_seconds
            self._checkpoint_db_latencies[1] += 1
            for bucket in DEFAULT_LATENCY_BUCKETS:
                if duration_seconds <= bucket:
                    self._checkpoint_db_buckets[bucket] = self._checkpoint_db_buckets.get(bucket, 0) + 1

    def set_circuit_breaker_state(self, service: str, state: int) -> None:
        with self._lock:
            self._circuit_breaker_states[service] = state

    def _normalize_path(self, path: str) -> str:
        """Sanitizes dynamic path parameters to prevent high-cardinality metric explosion."""
        parts = path.strip("/").split("/")
        normalized = []
        for p in parts:
            if p.startswith(("user_", "wl_", "alert_", "ast_", "rst_", "bk_", "task_", "thread_")):
                normalized.append(":id")
            elif len(p) >= 20 and not p.isalpha():
                normalized.append(":id")
            else:
                normalized.append(p)
        return "/" + "/".join(normalized) if normalized else "/"

    def _sync_circuit_breakers(self) -> None:
        """Dynamically syncs circuit breaker states from the global registry."""
        try:
            from tripmate.integrations.circuit_breaker import (
                CircuitState,
                circuit_breaker_registry,
            )

            breakers = circuit_breaker_registry.get_all()
            for name, breaker in breakers.items():
                if breaker.state == CircuitState.CLOSED:
                    code = 0
                elif breaker.state == CircuitState.HALF_OPEN:
                    code = 1
                else:
                    code = 2
                self._circuit_breaker_states[name] = code
        except Exception:
            pass

    def generate_prometheus_text(self) -> str:
        """Formats all collected APM metrics into official Prometheus Text Exposition Format (v0.0.4)."""
        self._sync_circuit_breakers()
        lines = []

        # 1. System Uptime Gauge
        uptime = time.time() - self._start_time
        lines.append("# HELP tripmate_uptime_seconds Total runtime of the TripMate application in seconds.")
        lines.append("# TYPE tripmate_uptime_seconds gauge")
        lines.append(f"tripmate_uptime_seconds {uptime:.2f}\n")

        # 2. In-flight requests & runs Gauges
        with self._lock:
            active_req = self._active_requests
            inflight_runs = self._inflight_runs

        lines.append("# HELP tripmate_http_active_requests Current number of active in-flight HTTP requests.")
        lines.append("# TYPE tripmate_http_active_requests gauge")
        lines.append(f"tripmate_http_active_requests {active_req}\n")

        lines.append("# HELP tripmate_inflight_runs Current number of active in-flight workflow runs.")
        lines.append("# TYPE tripmate_inflight_runs gauge")
        lines.append(f"tripmate_inflight_runs {inflight_runs}\n")

        # 3. HTTP Request Counts & Histograms
        lines.append("# HELP tripmate_http_requests_total Total number of HTTP requests processed.")
        lines.append("# TYPE tripmate_http_requests_total counter")
        with self._lock:
            req_items = list(self._http_requests_total.items())
            dur_items = list(self._http_request_duration_seconds.items())
            bucket_items = dict(self._http_request_duration_buckets)

        for (method, path, status_code), count in req_items:
            lines.append(
                f'tripmate_http_requests_total{{method="{method}",path="{path}",status="{status_code}"}} {count}'
            )
        lines.append("")

        lines.append("# HELP tripmate_http_request_duration_seconds Latency histogram of HTTP requests in seconds.")
        lines.append("# TYPE tripmate_http_request_duration_seconds histogram")
        for (method, path), (total_dur, count) in dur_items:
            for b in DEFAULT_LATENCY_BUCKETS:
                bcount = bucket_items.get((method, path, b), 0)
                lines.append(
                    f'tripmate_http_request_duration_seconds_bucket{{le="{b}",method="{method}",path="{path}"}} {bcount}'
                )
            lines.append(
                f'tripmate_http_request_duration_seconds_bucket{{le="+Inf",method="{method}",path="{path}"}} {count}'
            )
            lines.append(
                f'tripmate_http_request_duration_seconds_sum{{method="{method}",path="{path}"}} {total_dur:.6f}'
            )
            lines.append(f'tripmate_http_request_duration_seconds_count{{method="{method}",path="{path}"}} {count}')
        lines.append("")

        # 4. Agent Executions, Duration & Failures
        lines.append("# HELP tripmate_agent_executions_total Total number of AI agent executions.")
        lines.append("# TYPE tripmate_agent_executions_total counter")
        with self._lock:
            agent_items = list(self._agent_executions_total.items())
            agent_failures = list(self._agent_failures_total.items())
            agent_durs = list(self._agent_duration_seconds.items())

        for (agent_name, status), count in agent_items:
            lines.append(f'tripmate_agent_executions_total{{agent="{agent_name}",status="{status}"}} {count}')
        lines.append("")

        lines.append("# HELP tripmate_agent_failures_total Total number of failed AI agent executions.")
        lines.append("# TYPE tripmate_agent_failures_total counter")
        for agent_name, count in agent_failures:
            lines.append(f'tripmate_agent_failures_total{{agent="{agent_name}"}} {count}')
        lines.append("")

        lines.append("# HELP tripmate_agent_duration_seconds Total execution time of AI agents in seconds.")
        lines.append("# TYPE tripmate_agent_duration_seconds summary")
        for agent_name, (total_dur, count) in agent_durs:
            lines.append(f'tripmate_agent_duration_seconds_sum{{agent="{agent_name}"}} {total_dur:.6f}')
            lines.append(f'tripmate_agent_duration_seconds_count{{agent="{agent_name}"}} {count}')
        lines.append("")

        # 5. Cache Hits & Misses
        lines.append("# HELP tripmate_cache_hits_total Total cache hits by backend tier.")
        lines.append("# TYPE tripmate_cache_hits_total counter")
        with self._lock:
            hits = list(self._cache_hits_total.items())
            misses = list(self._cache_misses_total.items())

        for ctype, count in hits:
            lines.append(f'tripmate_cache_hits_total{{cache_type="{ctype}"}} {count}')
        lines.append("")

        lines.append("# HELP tripmate_cache_misses_total Total cache misses by backend tier.")
        lines.append("# TYPE tripmate_cache_misses_total counter")
        for ctype, count in misses:
            lines.append(f'tripmate_cache_misses_total{{cache_type="{ctype}"}} {count}')
        lines.append("")

        # 6. Rate Limit Rejections
        lines.append("# HELP tripmate_rate_limit_rejections_total Total rate limit 429 rejections by route.")
        lines.append("# TYPE tripmate_rate_limit_rejections_total counter")
        with self._lock:
            rl_items = list(self._rate_limit_rejections_total.items())
        for route, count in rl_items:
            lines.append(f'tripmate_rate_limit_rejections_total{{route="{route}"}} {count}')
        lines.append("")

        # 7. LLM Tokens & Cost
        lines.append("# HELP tripmate_llm_tokens_total Total LLM tokens consumed by model and type.")
        lines.append("# TYPE tripmate_llm_tokens_total counter")
        with self._lock:
            tokens_items = list(self._llm_tokens_total.items())
            cost_items = list(self._llm_cost_dollars_total.items())

        for (model, token_type), count in tokens_items:
            lines.append(f'tripmate_llm_tokens_total{{model="{model}",type="{token_type}"}} {count}')
        lines.append("")

        lines.append("# HELP tripmate_llm_cost_dollars_total Estimated cumulative LLM inference spend in USD.")
        lines.append("# TYPE tripmate_llm_cost_dollars_total counter")
        for model, cost in cost_items:
            lines.append(f'tripmate_llm_cost_dollars_total{{model="{model}"}} {cost:.6f}')
        lines.append("")

        # 8. Checkpoint DB Latency
        lines.append("# HELP tripmate_checkpoint_db_latency_seconds Latency of checkpoint database operations.")
        lines.append("# TYPE tripmate_checkpoint_db_latency_seconds summary")
        with self._lock:
            db_sum, db_cnt = self._checkpoint_db_latencies
        lines.append(f"tripmate_checkpoint_db_latency_seconds_sum {db_sum:.6f}")
        lines.append(f"tripmate_checkpoint_db_latency_seconds_count {db_cnt}")
        lines.append("")

        # 9. Circuit Breaker States
        lines.append(
            "# HELP tripmate_circuit_breaker_state Current state of circuit breakers (0=CLOSED, 1=HALF_OPEN, 2=OPEN)."
        )
        lines.append("# TYPE tripmate_circuit_breaker_state gauge")
        with self._lock:
            cb_items = list(self._circuit_breaker_states.items())
        for service, state_code in cb_items:
            lines.append(f'tripmate_circuit_breaker_state{{service="{service}"}} {state_code}')
        lines.append("")

        return "\n".join(lines)


# Global metrics registry singleton
metrics_registry = PrometheusMetricsRegistry()


class PrometheusMetricsMiddleware(BaseHTTPMiddleware):
    """FastAPI/Starlette middleware collecting per-request execution metrics."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Avoid recording metrics for the scrape endpoint itself
        if request.url.path in ("/metrics", "/api/v1/metrics"):
            return await call_next(request)

        metrics_registry.inc_active_requests()
        t0 = time.time()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            status_code = 500
            raise
        finally:
            duration = time.time() - t0
            metrics_registry.dec_active_requests()
            metrics_registry.record_http_request(
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                duration_seconds=duration,
            )
