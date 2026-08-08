import asyncio
import time
from typing import Dict, Any


async def mock_specialist_agent(name: str, delay_seconds: float) -> Dict[str, Any]:
    """Simulate specialist agent API work with realistic latency."""
    await asyncio.sleep(delay_seconds)
    return {name: f"Results for {name}"}


async def run_sequential_benchmark(agents: dict) -> float:
    t0 = time.time()
    for name, delay in agents.items():
        await mock_specialist_agent(name, delay)
    return time.time() - t0


async def run_parallel_benchmark(agents: dict) -> float:
    t0 = time.time()
    tasks = [mock_specialist_agent(name, delay) for name, delay in agents.items()]
    await asyncio.gather(*tasks)
    return time.time() - t0


async def main():
    print("=" * 60)
    print("      TripMate AI Multi-Agent Execution Benchmark")
    print("=" * 60)

    specialist_delays = {
        "flight_agent": 0.40,
        "hotel_agent": 0.55,
        "weather_agent": 0.35,
    }

    print("\nRunning Sequential Specialist Benchmark...")
    seq_time = await run_sequential_benchmark(specialist_delays)
    print(f"-> Sequential Latency: {seq_time:.3f} seconds")

    print("\nRunning Parallel Specialist Fan-Out Benchmark...")
    par_time = await run_parallel_benchmark(specialist_delays)
    print(f"-> Parallel Fan-Out Latency: {par_time:.3f} seconds")

    speedup_pct = ((seq_time - par_time) / seq_time) * 100
    print("\n" + "-" * 60)
    print(f"Empirical Time Savings: {seq_time - par_time:.3f} seconds ({speedup_pct:.1f}% reduction)")
    print("-" * 60)


if __name__ == "__main__":
    asyncio.run(main())
