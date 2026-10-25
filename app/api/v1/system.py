"""API router for System Health, Synchronization, and Fleet Statistics."""

from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.client.urja_client import UrjaClient
from app.config import settings
from app.models.query import FleetStats
from app.services.index_service import index_service

router = APIRouter(tags=["System"])


def get_urja_client() -> UrjaClient:
    from app.main import urja_client
    return urja_client


class HealthCheckResponse(BaseModel):
    status: str
    service: str
    upstream_portal: str
    upstream_session_active: bool
    cache_indexed: bool
    cache_age_seconds: Optional[float] = None
    indexed_meters_count: int


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    summary="Health check and upstream connectivity status",
    description="Inspect API operational status, upstream Urja portal session validity, and local cache index freshness.",
)
async def health_check(client: UrjaClient = Depends(get_urja_client)):
    return HealthCheckResponse(
        status="healthy",
        service="Flock Energy - Urja Meter Ops API Service",
        upstream_portal=settings.urja_portal_url,
        upstream_session_active=client.session_manager.is_authenticated,
        cache_indexed=index_service.is_cached,
        cache_age_seconds=index_service.cache_age_seconds,
        indexed_meters_count=len(index_service._meters_by_id),
    )


@router.get(
    "/stats",
    response_model=FleetStats,
    summary="Get utility fleet statistics and KPIs",
    description="High-level dashboard KPIs: active vs faulty meters, manufacturer distribution, total transformer kVA, and feeder totals.",
)
async def get_fleet_stats(client: UrjaClient = Depends(get_urja_client)):
    if not index_service.is_cached:
        await index_service.sync(client)

    return index_service.get_fleet_stats()


@router.post(
    "/sync",
    summary="Force upstream cache refresh",
    description="Trigger an immediate crawl and bulk export from the Urja portal to refresh the local in-memory index.",
)
async def trigger_sync(client: UrjaClient = Depends(get_urja_client)) -> Dict[str, Any]:
    try:
        res = await index_service.sync(client, force=True)
        return {"message": "Sync completed successfully", "details": res}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to sync with upstream Urja portal: {exc}",
        )
