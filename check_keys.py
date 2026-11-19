"""Standalone diagnostic tool to check and validate all API keys in .env.

Usage:
    python check_keys.py
"""

import os
import urllib.request
import urllib.error
import json
from dotenv import load_dotenv

load_dotenv(".env")

def test_groq(api_key: str):
    if not api_key:
        return "NOT SET", "No key provided in .env"
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/models",
        headers={"Authorization": f"Bearer {api_key}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            count = len(data.get("data", []))
            return "VALID", f"Active ({count} models available)"
    except urllib.error.HTTPError as e:
        return "INVALID", f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        return "ERROR", str(e)

def test_openrouter(api_key: str):
    if not api_key:
        return "NOT SET", "No key provided in .env"
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/auth/key",
        headers={"Authorization": f"Bearer {api_key}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode()).get("data", {})
            label = data.get("label", "Key active")
            limit = data.get("limit", "No limit")
            return "VALID", f"{label} (Limit: {limit})"
    except urllib.error.HTTPError as e:
        return "INVALID", f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        return "ERROR", str(e)

def test_huggingface(api_key: str):
    if not api_key:
        return "NOT SET", "No key provided in .env"
    req = urllib.request.Request(
        "https://huggingface.co/api/whoami-v2",
        headers={"Authorization": f"Bearer {api_key}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            user = data.get("name", "Authenticated")
            return "VALID", f"Account: {user}"
    except urllib.error.HTTPError as e:
        return "INVALID", f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        return "ERROR", str(e)

def test_tavily(api_key: str):
    if not api_key:
        return "NOT SET", "No key provided in .env"
    req = urllib.request.Request(
        "https://api.tavily.com/search",
        data=json.dumps({"query": "test", "max_results": 1}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return "VALID", "Active (Search successful)"
    except urllib.error.HTTPError as e:
        return "INVALID", f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        return "ERROR", str(e)

def test_openweather(api_key: str):
    if not api_key:
        return "NOT SET", "No key provided in .env"
    url = f"https://api.openweathermap.org/data/2.5/weather?q=London&appid={api_key}"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return "VALID", "Active (Weather lookup successful)"
    except urllib.error.HTTPError as e:
        return "INVALID", f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        return "ERROR", str(e)

def main():
    print("=" * 70)
    print("  TripMate AI — API Key Diagnostic Validator")
    print("  Cost / Toll: $0.00 (Free validation endpoints)")
    print("=" * 70)

    checks = [
        ("GROQ_API_KEY", test_groq),
        ("OPENROUTER_API_KEY", test_openrouter),
        ("HUGGINGFACE_API_KEY", test_huggingface),
        ("TAVILY_API_KEY", test_tavily),
        ("OPENWEATHER_API_KEY", test_openweather),
    ]

    for key_name, test_fn in checks:
        key_val = os.getenv(key_name, "").strip()
        status, details = test_fn(key_val)
        
        status_display = {
            "VALID": "[OK - ACTIVE]",
            "INVALID": "[FAIL - BAD KEY]",
            "NOT SET": "[SKIPPED - EMPTY]",
            "ERROR": "[ERROR]"
        }.get(status, f"[{status}]")
        
        print(f" {key_name:<24} : {status_display:<18} | {details}")

    print("=" * 70)
    print(" Tip: Paste your keys into .env and rerun: python check_keys.py\n")

if __name__ == "__main__":
    main()
