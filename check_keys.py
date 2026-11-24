"""Ping the API keys in .env and print whether each one works.

Usage:
    python check_keys.py

Groq, OpenRouter, and Hugging Face use auth endpoints that do not bill.
OpenWeather and AviationStack use free-tier lookups.
Tavily has no auth-only endpoint, so that check runs a 1-result search and spends one credit when the key is good.
LangChain pings the LangSmith info endpoint (free).
"""

import json
import os
import ssl
import urllib.error
import urllib.request
from pathlib import Path

import certifi
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

# Use certifi SSL context to avoid certificate errors on Windows
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def _call(req, timeout=10, use_ssl=True):
    try:
        ctx = SSL_CONTEXT if use_ssl else None
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body, None
    except urllib.error.HTTPError as exc:
        err_body = ""
        try:
            err_body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return exc.code, err_body, f"HTTP {exc.code}: {exc.reason}"
    except Exception as exc:
        return None, None, str(exc)


def _clean_key(raw_key: str) -> str:
    """Strips surrounding quotes and whitespace from copied keys."""
    if not raw_key:
        return ""
    cleaned = raw_key.strip()
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (
        cleaned.startswith("'") and cleaned.endswith("'")
    ):
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _missing(api_key: str):
    if not api_key:
        return "NOT SET", "nothing in .env (empty)"
    cleaned = _clean_key(api_key)
    if not cleaned:
        return "NOT SET", "nothing in .env (empty)"
    if "your-" in cleaned or "-here" in cleaned or "your_key" in cleaned:
        return "PLACEHOLDER", f"value '{cleaned[:20]}...' is placeholder text"
    return None


def test_groq(api_key: str):
    missing = _missing(api_key)
    if missing:
        return missing
    key = _clean_key(api_key)
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/models",
        headers={"Authorization": f"Bearer {key}"},
    )
    status, body, err = _call(req)
    if err and status != 200:
        return ("INVALID", err) if str(status).startswith(("4", "5")) else ("ERROR", err)
    try:
        data = json.loads(body)
        model_ids = {m.get("id") for m in data.get("data", [])}
        models_str = ""
        if "llama-3.3-70b-versatile" in model_ids:
            models_str = " (llama-3.3-70b available)"
        elif "llama-3.1-8b-instant" in model_ids:
            models_str = " (llama-3.1-8b available)"
        return "VALID", f"{len(data.get('data', []))} models listed{models_str} (HTTP {status})"
    except Exception as exc:
        return "VALID", f"authenticated successfully (HTTP {status})"


def test_openrouter(api_key: str):
    missing = _missing(api_key)
    if missing:
        return missing
    key = _clean_key(api_key)
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/auth/key",
        headers={"Authorization": f"Bearer {key}"},
    )
    status, body, err = _call(req)
    if err and status != 200:
        return ("INVALID", err) if str(status).startswith(("4", "5")) else ("ERROR", err)
    try:
        data = json.loads(body).get("data", {})
        label = data.get("label") or "key accepted"
        limit = data.get("limit", "no limit")
        usage = data.get("usage", "0")
        return "VALID", f"{label}, usage: {usage}, limit: {limit} (HTTP {status})"
    except Exception:
        return "VALID", f"key accepted (HTTP {status})"


def test_huggingface(api_key: str):
    missing = _missing(api_key)
    if missing:
        return missing
    key = _clean_key(api_key)
    req = urllib.request.Request(
        "https://huggingface.co/api/whoami-v2",
        headers={"Authorization": f"Bearer {key}"},
    )
    status, body, err = _call(req)
    if err and status != 200:
        return ("INVALID", err) if str(status).startswith(("4", "5")) else ("ERROR", err)
    try:
        user = json.loads(body).get("name") or "authenticated"
        return "VALID", f"account: {user} (HTTP {status})"
    except Exception:
        return "VALID", f"authenticated (HTTP {status})"


def test_openweather(api_key: str):
    missing = _missing(api_key)
    if missing:
        return missing
    key = _clean_key(api_key)
    url = f"https://api.openweathermap.org/data/2.5/weather?q=London&appid={key}"
    status, body, err = _call(url)
    if err and status != 200:
        if status == 401:
            return "INVALID", "HTTP 401: Invalid API key (or new key not yet activated, takes ~10-30 mins)"
        return ("INVALID", err) if str(status).startswith(("4", "5")) else ("ERROR", err)
    return "VALID", f"London weather lookup ok (HTTP {status})"


def test_tavily(api_key: str):
    missing = _missing(api_key)
    if missing:
        return missing
    key = _clean_key(api_key)
    req = urllib.request.Request(
        "https://api.tavily.com/search",
        data=json.dumps({"api_key": key, "query": "ping", "max_results": 1}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
    )
    status, body, err = _call(req)
    if err and status != 200:
        return ("INVALID", err) if str(status).startswith(("4", "5")) else ("ERROR", err)
    return "VALID", f"search ok, 1 credit used (HTTP {status})"


def test_aviationstack(api_key: str):
    missing = _missing(api_key)
    if missing:
        return missing
    key = _clean_key(api_key)
    # Note: AviationStack free tier uses HTTP
    url = f"http://api.aviationstack.com/v1/airports?access_key={key}&limit=1"
    status, body, err = _call(url, use_ssl=False)
    if err and status != 200:
        return ("INVALID", err) if str(status).startswith(("4", "5")) else ("ERROR", err)
    try:
        data = json.loads(body)
        if "error" in data:
            err_info = data["error"].get("info") or data["error"].get("code") or "error"
            return "INVALID", f"{err_info} (HTTP {status})"
        if "data" in data:
            return "VALID", f"airports lookup ok (HTTP {status})"
    except Exception:
        pass
    return "VALID", f"airports endpoint reached (HTTP {status})"


def test_langchain(api_key: str):
    missing = _missing(api_key)
    if missing:
        return missing
    key = _clean_key(api_key)
    req = urllib.request.Request(
        "https://api.smith.langchain.com/info",
        headers={"x-api-key": key},
    )
    status, body, err = _call(req)
    if err and status != 200:
        return ("INVALID", err) if str(status).startswith(("4", "5")) else ("ERROR", err)
    return "VALID", f"LangSmith connected (HTTP {status})"


def main():
    print("=" * 80)
    print("TripMate AI - API Key Verification & Diagnostic Tool")
    print("=" * 80)
    print("Free auth endpoints: Groq, OpenRouter, HuggingFace, LangChain")
    print("Free lookup: OpenWeather, AviationStack | 1 credit: Tavily")
    print("-" * 80)

    checks = [
        ("GROQ_API_KEY", test_groq),
        ("OPENROUTER_API_KEY", test_openrouter),
        ("HUGGINGFACE_API_KEY", test_huggingface),
        ("OPENWEATHER_API_KEY", test_openweather),
        ("TAVILY_API_KEY", test_tavily),
        ("AVIATIONSTACK_API_KEY", test_aviationstack),
        ("LANGCHAIN_API_KEY", test_langchain),
    ]

    labels = {
        "VALID": "[ OK ]",
        "INVALID": "[FAIL]",
        "NOT SET": "[EMPTY]",
        "PLACEHOLDER": "[DUMMY]",
        "ERROR": "[ERR ]",
    }

    results = []
    for name, fn in checks:
        # Check canonical and alternative variable names
        raw_val = os.getenv(name, "")
        if not raw_val and name == "AVIATIONSTACK_API_KEY":
            raw_val = os.getenv("AVIATION_STACK_API_KEY", "")

        status, detail = fn(raw_val)
        label = labels.get(status, f"[{status}]")
        print(f"  {label:<9} {name:<24} {detail}")
        results.append((name, status))

    print("-" * 80)
    valid_count = sum(1 for _, st in results if st == "VALID")
    print(f"Summary: {valid_count} of {len(checks)} keys verified successfully.")
    
    # Practical guidance
    groq_ok = any(name == "GROQ_API_KEY" and st == "VALID" for name, st in results)
    openrouter_ok = any(name == "OPENROUTER_API_KEY" and st == "VALID" for name, st in results)
    
    if not groq_ok and not openrouter_ok:
        print("\n[!] NOTICE: At least one LLM provider (GROQ_API_KEY or OPENROUTER_API_KEY)")
        print("    is required for the travel planner and specialist agents to run.")
        print("    Get free keys at: https://console.groq.com/keys or https://openrouter.ai/keys")
    else:
        print("\n[+] Core LLM provider is active and ready for travel planning!")
    print("=" * 80)


if __name__ == "__main__":
    main()
