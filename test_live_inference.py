"""Live Inference Test Script for TripMate AI

Usage:
    python test_live_inference.py

Validates that:
1. ModelRouter correctly detects configured LLM provider (Groq / OpenRouter / HuggingFace).
2. Fast LLM generates a prompt response (used by Guardrails & Supervisor).
3. Reasoning LLM generates a prompt response (used by Specialists, Critic & Itinerary synthesis).
"""

import asyncio
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

from tripmate.services.model_router import ModelTier, model_router
from langchain_core.messages import HumanMessage, SystemMessage


async def test_inference():
    print("=" * 70)
    print("TripMate AI - Live LLM Inference Diagnostic")
    print("=" * 70)

    active_provider = model_router.get_active_provider_name()
    if not active_provider:
        print("[!] No LLM provider found in .env.")
        print("    Please set GEMINI_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY, or HUGGINGFACE_API_KEY in .env.")
        print("    Then re-run this script: python test_live_inference.py")
        print("=" * 70)
        return

    print(f"[+] Active LLM Provider Strategy: {active_provider.upper()}")
    print("-" * 70)

    # 1. Test Fast Model
    print("1. Testing Fast Model (Tier: FAST)...")
    t0 = time.time()
    try:
        fast_llm = model_router.get_model(ModelTier.FAST)
        if fast_llm is None:
            print("   [!] Could not initialize Fast model.")
        else:
            resp = await fast_llm.ainvoke([HumanMessage(content="Hello! Respond in 5 words or fewer.")])
            latency = (time.time() - t0) * 1000
            print(f"   [OK] Response ({latency:.0f}ms): {resp.content.strip()}")
    except Exception as exc:
        print(f"   [FAIL] Fast model error: {exc}")

    print("-" * 70)

    # 2. Test Reasoning Model
    print("2. Testing Reasoning Model (Tier: REASONING)...")
    t0 = time.time()
    try:
        reasoning_llm = model_router.get_model(ModelTier.REASONING)
        if reasoning_llm is None:
            print("   [!] Could not initialize Reasoning model.")
        else:
            resp = await reasoning_llm.ainvoke([HumanMessage(content="Plan a 1-day trip to Paris in 1 sentence.")])
            latency = (time.time() - t0) * 1000
            print(f"   [OK] Response ({latency:.0f}ms): {resp.content.strip()}")
    except Exception as exc:
        print(f"   [FAIL] Reasoning model error: {exc}")

    print("=" * 70)
    print("[+] Model testing complete. If both passed, your AI agents are ready to run!")
    print("    Start server with: python app.py")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_inference())

