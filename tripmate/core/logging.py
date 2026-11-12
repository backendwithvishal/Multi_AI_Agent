"""
Structured JSON Logging & Data Privacy Redaction Module

Features:
- Deterministic redaction of API keys (Groq, OpenRouter, Tavily, HuggingFace, OpenAI).
- Redaction of Bearer tokens, Authorization headers, and JWTs.
- Redaction of PII (Emails, Phone numbers, Credit cards, SSNs).
- Redaction and masking of raw user prompts by default to prevent data leakage.
- Structured JSON output formatter with request_id, hashed thread_id, user_id, route, status, latency.
- Log level configurable from environment variable (`LOG_LEVEL`).
"""

import json
import logging
import os
import re
import sys
import time
from typing import Any, Dict, Optional

from tripmate.config.settings import settings
from tripmate.core.context import (
    get_request_id,
    get_thread_id,
    get_user_id,
    hash_thread_id,
)

# Regex compilation for sensitive pattern masking
RE_GROQ_KEY = re.compile(r"gsk_[a-zA-Z0-9_\-]{16,}")
RE_OPENROUTER_KEY = re.compile(r"sk-or-v1-[a-zA-Z0-9_\-]{16,}")
RE_OPENAI_KEY = re.compile(r"sk-[a-zA-Z0-9_\-]{20,}")
RE_TRIPMATE_KEY = re.compile(r"tm_live_[a-zA-Z0-9_\-]{16,}")
RE_TAVILY_KEY = re.compile(r"tvly-[a-zA-Z0-9_\-]{10,}")
RE_HF_KEY = re.compile(r"hf_[a-zA-Z0-9_\-]{16,}")
RE_GENERIC_KEY = re.compile(r'(?i)(api[_-]?key\s*[:=]\s*["\']?)([a-zA-Z0-9_\-]{10,})(["\']?)')

# Auth & Tokens
RE_AUTH_HEADER = re.compile(r"(?i)(Authorization\s*:\s*(?:Bearer|Basic|Token)?\s*)([a-zA-Z0-9_\-\.=]+)")
RE_BEARER_TOKEN = re.compile(r"(?i)(Bearer\s+)([a-zA-Z0-9_\-\.=]{10,})")
RE_TOKEN_PARAM = re.compile(r'(?i)(token\s*[:=]\s*["\']?)([a-zA-Z0-9_\-\.]{8,})(["\']?)')
RE_JWT = re.compile(r"eyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}")

# PII
RE_EMAIL = re.compile(r"\b[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+\b")
RE_PHONE = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
RE_CREDIT_CARD = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")
RE_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

# Prompt capture redaction pattern
RE_PROMPT_PREFIX = re.compile(r"(?i)(prompt\s*[:=]\s*)([^\n\r,{}]+)")


def redact_sensitive_data(val: Any, capture_prompts: Optional[bool] = None) -> Any:
    """
    Recursively scans and sanitizes sensitive data from strings, lists, and dictionaries.
    Redacts API keys, tokens, Authorization headers, and PII.
    By default, prompts are also redacted unless capture_prompts is True.
    """
    if val is None:
        return None

    if capture_prompts is None:
        capture_prompts = getattr(settings, "CAPTURE_PROMPTS", False)

    if isinstance(val, str):
        text = val

        # 1. API Keys
        text = RE_GROQ_KEY.sub("[REDACTED_GROQ_KEY]", text)
        text = RE_OPENROUTER_KEY.sub("[REDACTED_OPENROUTER_KEY]", text)
        text = RE_OPENAI_KEY.sub("[REDACTED_API_KEY]", text)
        text = RE_TRIPMATE_KEY.sub("[REDACTED_API_KEY]", text)
        text = RE_TAVILY_KEY.sub("[REDACTED_TAVILY_KEY]", text)
        text = RE_HF_KEY.sub("[REDACTED_HF_KEY]", text)
        text = RE_GENERIC_KEY.sub(r"\1[REDACTED_API_KEY]\3", text)

        # 2. Authorization & Tokens
        text = RE_AUTH_HEADER.sub(r"\1[REDACTED_AUTH_TOKEN]", text)
        text = RE_BEARER_TOKEN.sub(r"\1[REDACTED_TOKEN]", text)
        text = RE_TOKEN_PARAM.sub(r"\1[REDACTED_TOKEN]\3", text)
        text = RE_JWT.sub("[REDACTED_JWT]", text)

        # 3. PII
        text = RE_EMAIL.sub("[REDACTED_EMAIL]", text)
        text = RE_PHONE.sub("[REDACTED_PHONE]", text)
        text = RE_CREDIT_CARD.sub("[REDACTED_CREDIT_CARD]", text)
        text = RE_SSN.sub("[REDACTED_SSN]", text)

        # 4. Prompts (if prompt capture is off)
        if not capture_prompts:
            text = RE_PROMPT_PREFIX.sub(r"\1[REDACTED_PROMPT]", text)

        return text

    elif isinstance(val, dict):
        sanitized_dict = {}
        prompt_keys = {
            "prompt",
            "messages",
            "user_query",
            "query",
            "user_message",
            "input",
        }
        for k, v in val.items():
            key_str = str(k).lower()
            if not capture_prompts and key_str in prompt_keys:
                sanitized_dict[k] = "[REDACTED_PROMPT]"
            elif any(s in key_str for s in ("password", "secret", "token", "auth", "api_key", "apikey")):
                sanitized_dict[k] = "[REDACTED_CREDENTIAL]"
            else:
                sanitized_dict[k] = redact_sensitive_data(v, capture_prompts=capture_prompts)
        return sanitized_dict

    elif isinstance(val, (list, tuple)):
        sanitized_list = [redact_sensitive_data(item, capture_prompts=capture_prompts) for item in val]
        return type(val)(sanitized_list)

    return val


class RedactingJsonFormatter(logging.Formatter):
    """
    Standard production JSON log formatter.
    Guarantees that log records:
    1. Output strictly valid structured JSON.
    2. Include request_id, hashed thread_id, user_id, route, status, latency.
    3. Never leak credentials, tokens, or PII.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def format(self, record: logging.LogRecord) -> str:
        # Resolve correlation context
        req_id = getattr(record, "request_id", None) or get_request_id() or "unknown"
        user_id = getattr(record, "user_id", None) or get_user_id()
        raw_thread_id = getattr(record, "thread_id", None) or get_thread_id()
        th_hash = getattr(record, "thread_id_hash", None) or hash_thread_id(raw_thread_id)
        route = getattr(record, "route", None) or getattr(record, "path", None)
        status_val = getattr(record, "status", None) or getattr(record, "status_code", None)
        latency = (
            getattr(record, "latency", None)
            or getattr(record, "latency_ms", None)
            or getattr(record, "duration_ms", None)
        )

        # Format message and apply redaction
        try:
            raw_msg = record.getMessage()
        except Exception:
            raw_msg = str(record.msg)

        safe_msg = redact_sensitive_data(raw_msg)

        log_payload: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt)
            if self.datefmt
            else time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": safe_msg,
            "request_id": req_id,
            "thread_id_hash": th_hash,
            "user_id": user_id,
            "route": route,
            "status": status_val,
            "latency_ms": latency,
        }

        # Include any additional extra attributes attached to record
        if hasattr(record, "extra_fields") and isinstance(record.extra_fields, dict):
            for k, v in record.extra_fields.items():
                if k not in log_payload:
                    log_payload[k] = redact_sensitive_data(v)

        # Include exception traceback if present (sanitized)
        if record.exc_info:
            log_payload["exception"] = redact_sensitive_data(self.formatException(record.exc_info))

        return json.dumps(log_payload, default=str)


def get_structured_logger(name: str) -> logging.Logger:
    """Returns a configured logger with RedactingJsonFormatter and environment log level."""
    logger = logging.getLogger(name)
    level_name = os.getenv("LOG_LEVEL", getattr(settings, "LOG_LEVEL", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)

    # Avoid duplicate handlers
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(RedactingJsonFormatter())
        logger.addHandler(handler)
        logger.propagate = False

    return logger
