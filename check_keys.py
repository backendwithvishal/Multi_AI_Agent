"""Ping the API keys in .env and print whether each one works.

    python check_keys.py

Groq, OpenRouter, and Hugging Face use auth endpoints that do not bill.
OpenWeather uses one free-tier lookup. Tavily has no auth-only endpoint,
so that check runs a 1-result search and spends one credit when the key is good.
"""

import json
import os
import urllib.error
import urllib.request

from dotenv import load_dotenv

load_dotenv(".env")


def _call(req, timeout=8):
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
            return resp.status, body, None
    except urllib.error.HTTPError as exc:
        return None, None, f"HTTP {exc.code}: {exc.reason}"
    except Exception as exc:
        return None, None, str(exc)


def _missing(api_key):
    if api_key:
        return None
    return "NOT SET", "nothing in .env"


def test_groq(api_key):
    missing = _missing(api_key)
    if missing:
        return missing
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    status, body, err = _call(req)
    if err:
        return ("INVALID", err) if err.startswith("HTTP") else ("ERROR", err)
    data = json.loads(body)
    return "VALID", f"{len(data.get('data', []))} models listed (HTTP {status})"


def test_openrouter(api_key):
    missing = _missing(api_key)
    if missing:
        return missing
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/auth/key",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    status, body, err = _call(req)
    if err:
        return ("INVALID", err) if err.startswith("HTTP") else ("ERROR", err)
    data = json.loads(body).get("data", {})
    label = data.get("label") or "key accepted"
    limit = data.get("limit", "no limit")
    return "VALID", f"{label}, limit {limit} (HTTP {status})"


def test_huggingface(api_key):
    missing = _missing(api_key)
    if missing:
        return missing
    req = urllib.request.Request(
        "https://huggingface.co/api/whoami-v2",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    status, body, err = _call(req)
    if err:
        return ("INVALID", err) if err.startswith("HTTP") else ("ERROR", err)
    user = json.loads(body).get("name") or "authenticated"
    return "VALID", f"account {user} (HTTP {status})"


def test_openweather(api_key):
    missing = _missing(api_key)
    if missing:
        return missing
    url = "https://api.openweathermap.org/data/2.5/weather?q=London&appid=" + api_key
    status, _body, err = _call(url)
    if err:
        return ("INVALID", err) if err.startswith("HTTP") else ("ERROR", err)
    return "VALID", f"London lookup ok (HTTP {status})"


def test_tavily(api_key):
    missing = _missing(api_key)
    if missing:
        return missing
    req = urllib.request.Request(
        "https://api.tavily.com/search",
        data=json.dumps({"query": "ping", "max_results": 1}).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    status, _body, err = _call(req)
    if err:
        return ("INVALID", err) if err.startswith("HTTP") else ("ERROR", err)
    return "VALID", f"search ok, 1 credit used (HTTP {status})"


def main():
    print("API key check")
    print("Groq / OpenRouter / Hugging Face: free auth calls")
    print("OpenWeather: one free-tier call. Tavily: one credit if the key works.")
    print("-" * 72)

    checks = [
        ("GROQ_API_KEY", test_groq),
        ("OPENROUTER_API_KEY", test_openrouter),
        ("HUGGINGFACE_API_KEY", test_huggingface),
        ("OPENWEATHER_API_KEY", test_openweather),
        ("TAVILY_API_KEY", test_tavily),
    ]
    labels = {
        "VALID": "ok",
        "INVALID": "bad key",
        "NOT SET": "empty",
        "ERROR": "error",
    }

    for name, fn in checks:
        value = os.getenv(name, "").strip()
        status, detail = fn(value)
        print(f"{name:<24} {labels.get(status, status):<8} {detail}")

    print("-" * 72)


if __name__ == "__main__":
    main()
