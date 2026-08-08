"""
Observability & Token / Cost Tracking Layer

This module estimates token usage and LLM costs per agent, provider, and workflow run.
Exposes telemetry helper functions for run metric aggregation.
"""

from typing import Any, Dict

# Standard token pricing estimates per 1,000 tokens (USD)
PRICING_CATALOG = {
    "llama-3.3-70b-versatile": {"input": 0.00059, "output": 0.00079},
    "llama-3.1-8b-instant": {"input": 0.00005, "output": 0.00008},
    "default": {"input": 0.00050, "output": 0.00050},
}


def estimate_tokens(text: str) -> int:
    """Fast rule-of-thumb estimate (~4 characters per token)."""
    return max(1, len(text) // 4)


def calculate_cost(model_name: str, input_tokens: int, output_tokens: int) -> float:
    """Calculates estimated cost in USD."""
    rates = PRICING_CATALOG.get(model_name, PRICING_CATALOG["default"])
    input_cost = (input_tokens / 1000.0) * rates["input"]
    output_cost = (output_tokens / 1000.0) * rates["output"]
    return round(input_cost + output_cost, 6)


def summarize_run_observability(run_data: Dict[str, Any]) -> Dict[str, Any]:
    """Generates execution telemetry summary for a workflow run."""
    metrics = run_data.get("metrics", {})
    query = run_data.get("user_query", "") or run_data.get("answer", "")
    answer = run_data.get("answer", "")

    est_input_tokens = estimate_tokens(query)
    est_output_tokens = estimate_tokens(answer)
    total_tokens = est_input_tokens + est_output_tokens

    cost = calculate_cost("llama-3.3-70b-versatile", est_input_tokens, est_output_tokens)

    return {
        "run_id": run_data.get("run_id"),
        "thread_id": run_data.get("thread_id"),
        "status": run_data.get("status"),
        "selected_agents": run_data.get("selected_agents", []),
        "agent_latencies_ms": metrics.get("agent_latencies", {}),
        "total_latency_ms": metrics.get("total_latency_ms", 0.0),
        "token_usage": {
            "estimated_input_tokens": est_input_tokens,
            "estimated_output_tokens": est_output_tokens,
            "total_estimated_tokens": total_tokens,
        },
        "estimated_cost_usd": cost,
        "guardrail_allowed": run_data.get("guardrail_allowed", True),
        "requires_approval": run_data.get("requires_approval", False),
    }
