"""
Gunicorn Configuration for Production Deployment
"""
import multiprocessing
import os
from tripmate.config.settings import settings

# Bind host and port
bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"

# Worker processes and concurrency
# Default to WEB_CONCURRENCY, WORKERS, or settings.WEB_CONCURRENCY (default 2)
default_workers = getattr(settings, "WEB_CONCURRENCY", 2) or 2
workers = int(os.getenv("WEB_CONCURRENCY", os.getenv("WORKERS", str(default_workers))))
worker_class = "uvicorn.workers.UvicornWorker"

# Timeouts & Keep-Alive
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))
graceful_timeout = int(os.getenv("GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.getenv("KEEP_ALIVE", "5"))

# Reverse Proxy Headers (forwarded_allow_ips)
trusted = settings.TRUSTED_PROXIES
if isinstance(trusted, list):
    forwarded_allow_ips = ",".join(trusted)
else:
    forwarded_allow_ips = str(trusted)

# Logging
accesslog = "-"
errorlog = "-"
loglevel = settings.LOG_LEVEL.lower()

# Security & Limits
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

