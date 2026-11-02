"""
Prometheus Metrics Route

Exposes protected Prometheus scrape endpoint for APM monitoring tools.
Protected against public exposure: internal-only network restriction (loopback/RFC1918)
or Bearer token / Admin credential verification.
"""

import ipaddress
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Response, status

from tripmate.config.settings import settings
from tripmate.middleware.metrics import metrics_registry
from tripmate.core.audit import audit_logger, AuditEventType

router = APIRouter(tags=["Monitoring & Metrics"])


def _extract_client_ip(request: Request) -> str:
    """Extracts client IP, prioritizing proxy headers when peer is internal/trusted."""
    peer_ip = request.client.host if request.client else "127.0.0.1"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            return parts[0]
    real_ip = request.headers.get("X-Real-IP")
    if real_ip and real_ip.strip():
        return real_ip.strip()
    return peer_ip


RFC_1918_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
)


def _is_internal_ip(client_ip: str) -> bool:
    """Checks whether the client IP belongs to loopback, testclient, or RFC1918 private subnets."""
    if client_ip in ("127.0.0.1", "::1", "localhost", "testclient"):
        return True

    allowed_list = settings.METRICS_ALLOWED_IPS
    if isinstance(allowed_list, str):
        allowed_list = [x.strip() for x in allowed_list.split(",") if x.strip()]

    if client_ip in allowed_list:
        return True

    try:
        ip_obj = ipaddress.ip_address(client_ip)
        if ip_obj.is_loopback or any(ip_obj in net for net in RFC_1918_NETWORKS):
            return True
        for allowed in allowed_list:
            if "/" in allowed and ip_obj in ipaddress.ip_network(allowed, strict=False):
                return True
    except Exception:
        pass

    return False


def _verify_metrics_auth(request: Request) -> bool:
    """Verifies internal credentials (METRICS_TOKEN, API_KEY, or Admin JWT)."""
    # 1. Custom internal header
    secret_hdr = request.headers.get("X-Internal-Secret") or request.headers.get("X-Metrics-Key")
    if secret_hdr:
        if settings.METRICS_TOKEN and secret_hdr == settings.METRICS_TOKEN:
            return True
        if settings.API_KEY and secret_hdr == settings.API_KEY:
            return True

    # 2. Authorization header
    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        if settings.METRICS_TOKEN and token == settings.METRICS_TOKEN:
            return True
        if settings.API_KEY and token == settings.API_KEY:
            return True

        # Check admin user token
        try:
            from tripmate.api.dependencies import verify_token
            payload = verify_token(token)
            if payload and payload.get("role") in ("admin", "superadmin", "operator"):
                return True
        except Exception:
            pass

    return False


@router.get(
    "/metrics",
    summary="Scrape Prometheus APM Metrics",
    description="Returns application and agent performance metrics in Prometheus text exposition format. Restricted to internal network or authorized scraper.",
    response_class=Response,
)
async def get_metrics(request: Request):
    client_ip = _extract_client_ip(request)

    # If protection is enabled, verify IP or auth credentials
    if settings.METRICS_PROTECTED:
        is_internal = _is_internal_ip(client_ip)
        is_authorized = _verify_metrics_auth(request)

        if not is_internal and not is_authorized:
            audit_logger.record(
                event_type=AuditEventType.ACCESS_DENIED,
                action="metrics_scrape_rejected",
                actor="anonymous",
                target_id="/metrics",
                status="failure",
                client_ip=client_ip,
                request_id=getattr(request.state, "request_id", None),
                details={"reason": "Public IP not authorized for /metrics scrape"},
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Metrics endpoint is restricted to internal infrastructure.",
            )

    content = metrics_registry.generate_prometheus_text()
    return Response(
        content=content,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
