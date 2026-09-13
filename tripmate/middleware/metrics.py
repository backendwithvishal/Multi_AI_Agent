"""
Prometheus Metrics Middleware & Instrumentation Registry

Zero-overhead, pure-Python Prometheus metric collector that tracks:
- HTTP request counts, status codes, and latencies
- Concurrent in-flight HTTP requests
- AI specialist agent execution counts and runtimes
- Platform uptime and memory usage metrics
"""

import time
import threading
from typing import Dict, Tuple, Any
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class PrometheusMetricsRegistry:
    """Thread-safe Prometheus in-memory metric collector."""

    def __init__(self):
        self._lock = threading.Lock()
        self._start_time = time.time()
        # {(method, path, status_code): count}
        self._http_requests_total: Dict[Tuple[str, str, int], int] = {}
        # {(method, path): [sum_seconds, count]}
        self._http_request_duration_seconds: Dict[Tuple[str, str], List_Duration] = {}
        self._active_requests: int = 0
        # {(agent_name, status): count}
        self._agent_executions_total: Dict[Tuple[str, str], int] = {}
        # {agent_name: [sum_seconds, count]}
        self._agent_duration_seconds: Dict[str, List_Duration] = {}

    def inc_active_requests(self) -> None:
        with self._lock:
            self._active_requests += 1

    def dec_active_requests(self) -> None:
        with self._lock:
            self._active_requests = max(0, self._active_requests - 1)

    def record_http_request(self, method: str, path: str, status_code: int, duration_seconds: float) -> None:
        # Normalize dynamic path segments (e.g. UUIDs / IDs) to prevent high cardinality
        normalized_path = self._normalize_path(path)
        with self._lock:
            key = (method.upper(), normalized_path, status_code)
            self._http_requests_total[key] = self._http_requests_total.get(key, 0) + 1

            dur_key = (method.upper(), normalized_path)
            if dur_key not in self._http_request_duration_seconds:
                self._http_request_duration_seconds[dur_key] = [0.0, 0]
            self._http_request_duration_seconds[dur_key][0] += duration_seconds
            self._http_request_duration_seconds[dur_key][1] += 1

    def record_agent_execution(self, agent_name: str, status: str, duration_seconds: float) -> None:
        with self._lock:
            key = (agent_name, status)
            self._agent_executions_total[key] = self._agent_executions_total.get(key, 0) + 1

            if agent_name not in self._agent_duration_seconds:
                self._agent_duration_seconds[agent_name] = [0.0, 0]
            self._agent_duration_seconds[agent_name][0] += duration_seconds
            self._agent_duration_seconds[agent_name][1] += 1

    def _normalize_path(self, path: str) -> str:
        """Sanitizes high-cardinality ID parameters in metric path labels."""
        parts = path.strip("/").split("/")
        normalized = []
        for p in parts:
            if p.startswith("user_") or p.startswith("wl_") or p.startswith("alert_") or p.startswith("ast_") or p.startswith("rst_") or p.startswith("bk_") or p.startswith("task_"):
                normalized.append(":id")
            elif len(p) >= 20 and not p.isalpha():
                normalized.append(":id")
            else:
                normalized.append(p)
        return "/" + "/".join(normalized) if normalized else "/"

    def generate_prometheus_text(self) -> str:
        """Formats collected metrics in official Prometheus Text Format (v0.0.4)."""
        lines = []
        
        # 1. System Uptime Gauge
        uptime = time.time() - self._start_time
        lines.append("# HELP tripmate_uptime_seconds Total runtime of the TripMate application in seconds.")
        lines.append("# TYPE tripmate_uptime_seconds gauge")
        lines.append(f"tripmate_uptime_seconds {uptime:.2f}")
        lines.append("")

        # 2. Active In-flight Requests Gauge
        with self._lock:
            active = self._active_requests
        lines.append("# HELP tripmate_http_active_requests Current number of active in-flight HTTP requests.")
        lines.append("# TYPE tripmate_http_active_requests gauge")
        lines.append(f"tripmate_http_active_requests {active}")
        lines.append("")

        # 3. HTTP Total Requests Counter
        lines.append("# HELP tripmate_http_requests_total Total number of HTTP requests processed.")
        lines.append("# TYPE tripmate_http_requests_total counter")
        with self._lock:
            req_items = list(self._http_requests_total.items())
        for (method, path, status_code), count in req_items:
            lines.append(f'tripmate_http_requests_total{{method="{method}",path="{path}",status="{status_code}"}} {count}')
        lines.append("")

        # 4. HTTP Request Duration Summary
        lines.append("# HELP tripmate_http_request_duration_seconds Summary of HTTP request durations in seconds.")
        lines.append("# TYPE tripmate_http_request_duration_seconds summary")
        with self._lock:
            dur_items = list(self._http_request_duration_seconds.items())
        for (method, path), (total_dur, count) in dur_items:
            lines.append(f'tripmate_http_request_duration_seconds_sum{{method="{method}",path="{path}"}} {total_dur:.6f}')
            lines.append(f'tripmate_http_request_duration_seconds_count{{method="{method}",path="{path}"}} {count}')
        lines.append("")

        # 5. Agent Execution Metrics
        lines.append("# HELP tripmate_agent_executions_total Total number of AI agent executions.")
        lines.append("# TYPE tripmate_agent_executions_total counter")
        with self._lock:
            agent_items = list(self._agent_executions_total.items())
        for (agent_name, status), count in agent_items:
            lines.append(f'tripmate_agent_executions_total{{agent="{agent_name}",status="{status}"}} {count}')
        lines.append("")

        lines.append("# HELP tripmate_agent_duration_seconds Total execution time of AI agents in seconds.")
        lines.append("# TYPE tripmate_agent_duration_seconds summary")
        with self._lock:
            agent_dur_items = list(self._agent_duration_seconds.items())
        for agent_name, (total_dur, count) in agent_dur_items:
            lines.append(f'tripmate_agent_duration_seconds_sum{{agent="{agent_name}"}} {total_dur:.6f}')
            lines.append(f'tripmate_agent_duration_seconds_count{{agent="{agent_name}"}} {count}')
        lines.append("")

        return "\n".join(lines)


# Type alias helper
List_Duration = Any

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
