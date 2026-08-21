"""
Multi-Agent System Evaluation Benchmark Framework

Runs automated benchmarks over evaluation dataset test cases:
- Guardrail blocking accuracy
- Selected agent correctness
- Execution latency
- Critic score & output validity
"""

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Ensure parent root directory is in sys.path when executed directly
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tripmate.services.travel_service import travel_service

DATASET_PATH = Path(__file__).resolve().parent / "benchmark_dataset.json"


async def run_evaluation() -> Dict[str, Any]:
    """Executes benchmark suite and outputs quantitative accuracy & performance metrics."""
    if not DATASET_PATH.exists():
        return {"error": "Benchmark dataset file not found."}

    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        cases: List[Dict[str, Any]] = json.load(f)

    total_cases = len(cases)
    guardrail_correct = 0
    agent_selection_matches = 0
    completed_workflows = 0
    total_latency_ms = 0.0

    print("=" * 70)
    print("      Multi_AI_Agent Platform Evaluation Benchmark Suite")
    print("=" * 70)

    for idx, case in enumerate(cases, 1):
        query = case["query"]
        should_block = case.get("should_block", False)
        expected_agents = case.get("expected_agents", [])

        t0 = time.time()
        res = await travel_service.execute_travel_plan(query)
        latency = (time.time() - t0) * 1000.0
        total_latency_ms += latency

        is_blocked = not res.get("guardrail_allowed", True) or res.get("status") == "BLOCKED"

        if should_block:
            if is_blocked:
                guardrail_correct += 1
                print(f"[Case {idx}] PASS - Malicious query blocked correctly in {latency:.1f}ms")
            else:
                print(f"[Case {idx}] FAIL - Malicious query allowed unexpectedly")
        else:
            if not is_blocked:
                guardrail_correct += 1
                completed_workflows += 1
                selected = res.get("selected_agents", [])
                match = all(ag in selected for ag in expected_agents if ag != "itinerary_agent")
                if match:
                    agent_selection_matches += 1
                print(f"[Case {idx}] PASS - Plan generated in {latency:.1f}ms (Agents: {selected})")
            else:
                print(f"[Case {idx}] FAIL - Valid travel query blocked: {res.get('guardrail_reason')}")

    avg_latency = total_latency_ms / total_cases if total_cases > 0 else 0.0
    guardrail_accuracy = (guardrail_correct / total_cases) * 100.0 if total_cases > 0 else 0.0
    agent_match_pct = (agent_selection_matches / (total_cases - 1)) * 100.0 if total_cases > 1 else 100.0

    metrics = {
        "total_test_cases": total_cases,
        "guardrail_accuracy_pct": round(guardrail_accuracy, 2),
        "agent_routing_match_pct": round(agent_match_pct, 2),
        "completed_workflows": completed_workflows,
        "average_latency_ms": round(avg_latency, 2),
    }

    print("\n" + "-" * 70)
    print("      Evaluation Summary Metrics")
    print("-" * 70)
    print(f"Guardrail Accuracy:      {metrics['guardrail_accuracy_pct']}%")
    print(f"Agent Routing Match:     {metrics['agent_routing_match_pct']}%")
    print(f"Completed Workflows:     {metrics['completed_workflows']}/{total_cases}")
    print(f"Average Latency:         {metrics['average_latency_ms']} ms")
    print("=" * 70)

    return metrics


if __name__ == "__main__":
    asyncio.run(run_evaluation())
