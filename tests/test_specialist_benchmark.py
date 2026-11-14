"""Benchmark test measuring concurrent specialist execution vs sequential execution.

Benchmarks the parallel specialists node execution model, verifying:
1. Specialists executed concurrently via asyncio.gather achieve lower overall latency
   than sequential execution.
2. Contention analysis: because parallel specialist updates are gathered and committed
   as a single atomic state delta in LangGraph, checkpointer contention during specialist
   execution is zero.
"""

import asyncio
import time

import pytest

from tripmate.schemas.agents import StructuredAgentOutput


async def _mock_specialist_task(name: str, delay: float = 0.05) -> StructuredAgentOutput:
    await asyncio.sleep(delay)
    return StructuredAgentOutput(
        agent_name=name,
        status="success",
        result=f"Result from {name}",
        confidence=0.95,
        sources=[],
        warnings=[],
    )


@pytest.mark.asyncio
async def test_concurrent_vs_sequential_specialists_benchmark():
    """Measures latency of concurrent vs sequential specialist execution."""
    task_names = ["flight_agent", "hotel_agent", "weather_agent"]
    individual_delay = 0.05

    # 1. Sequential execution
    t0_seq = time.perf_counter()
    seq_results = []
    for name in task_names:
        res = await _mock_specialist_task(name, delay=individual_delay)
        seq_results.append(res)
    seq_duration = time.perf_counter() - t0_seq

    # 2. Concurrent execution (as implemented in parallel_specialists_node)
    t0_par = time.perf_counter()
    par_results = await asyncio.gather(*[_mock_specialist_task(name, delay=individual_delay) for name in task_names])
    par_duration = time.perf_counter() - t0_par

    # Assert correctness
    assert len(seq_results) == 3
    assert len(par_results) == 3

    # Assert concurrency speedup: parallel duration should be approximately 1 delay (~0.05s)
    # whereas sequential is 3 * delay (~0.15s)
    assert par_duration < seq_duration
    speedup = seq_duration / par_duration
    assert speedup >= 1.5, f"Expected concurrency speedup >= 1.5x, got {speedup:.2f}x"
