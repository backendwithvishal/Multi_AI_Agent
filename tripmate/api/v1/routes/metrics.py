"""
Prometheus Metrics Route

Exposes standard Prometheus scrape endpoint for APM monitoring tools.
"""

from fastapi import APIRouter, Response
from tripmate.middleware.metrics import metrics_registry

router = APIRouter(tags=["Monitoring & Metrics"])


@router.get(
    "/metrics",
    summary="Scrape Prometheus APM Metrics",
    description="Returns application and agent performance metrics in Prometheus text exposition format.",
    response_class=Response,
)
async def get_metrics():
    content = metrics_registry.generate_prometheus_text()
    return Response(
        content=content,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
