"""API router for Smart Meters: query, detail, nameplate, and spatial nearby search."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.client.urja_client import UrjaClient
from app.models.meter import MeterDetail, MeterSummary, NameplateItem
from app.models.query import NearbyMetersResponse, PaginatedResponse
from app.services.index_service import IndexService, index_service
from app.services.meter_service import MeterService

router = APIRouter(prefix="/meters", tags=["Meters"])


# Dependency to access UrjaClient instance
def get_urja_client() -> UrjaClient:
    from app.main import urja_client
    return urja_client


@router.get(
    "",
    response_model=PaginatedResponse[MeterSummary],
    summary="List and search smart meters",
    description=(
        "Search and filter smart meters across multiple attributes: manufacturer, "
        "phase type, installation status, DT code, feeder code, and free-text search."
    ),
)
async def list_meters(
    q: Optional[str] = Query(None, description="Free-text search across meterId, serial, make, DT, feeder, zone"),
    make: Optional[str] = Query(None, description="Filter by manufacturer (HPL, Genus, L&T, Secure, Allied)"),
    phase_type: Optional[str] = Query(None, description="Filter by phase (single, three)"),
    install_status: Optional[str] = Query(None, description="Filter by status (Installed, Faulty, Decommissioned)"),
    install_type: Optional[str] = Query(None, description="Filter by install type (Whole Current, CT Operated)"),
    build: Optional[str] = Query(None, description="Filter by build architecture (legacy, v2)"),
    dt_code: Optional[str] = Query(None, description="Filter by Distribution Transformer code (e.g. DT-001)"),
    feeder_code: Optional[str] = Query(None, description="Filter by Feeder code (e.g. F-001)"),
    substation_code: Optional[str] = Query(None, description="Filter by Substation code (e.g. SS-01)"),
    sort_by: str = Query("meter_id", description="Field to sort by (meter_id, serial_no, make, install_status, phase_type, dt_code)"),
    sort_order: str = Query("asc", description="Sort order (asc, desc)"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    client: UrjaClient = Depends(get_urja_client),
):
    # Ensure cache is warm
    if not index_service.is_cached:
        await index_service.sync(client)

    return index_service.query_meters(
        q=q,
        make=make,
        phase_type=phase_type,
        install_status=install_status,
        install_type=install_type,
        build=build,
        dt_code=dt_code,
        feeder_code=feeder_code,
        substation_code=substation_code,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/nearby",
    response_model=NearbyMetersResponse,
    summary="Find smart meters near coordinates",
    description="Calculate distance and return smart meters within radius_km using Great Circle (Haversine) calculation.",
)
async def find_nearby_meters(
    latitude: float = Query(..., ge=-90.0, le=90.0, description="Origin latitude coordinate"),
    longitude: float = Query(..., ge=-180.0, le=180.0, description="Origin longitude coordinate"),
    radius_km: float = Query(5.0, gt=0.0, le=50.0, description="Search radius in kilometers"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of meters to return"),
    client: UrjaClient = Depends(get_urja_client),
):
    if not index_service.is_cached:
        await index_service.sync(client)

    return index_service.find_nearby_meters(
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        limit=limit,
    )


@router.get(
    "/{meter_id}",
    response_model=MeterDetail,
    summary="Get meter detail",
    description="Retrieve comprehensive smart meter detail including normalized nameplate and full electrical network hierarchy.",
)
async def get_meter(
    meter_id: str,
    client: UrjaClient = Depends(get_urja_client),
):
    if not index_service.is_cached:
        await index_service.sync(client)

    meter = index_service.get_meter_by_id(meter_id)
    if meter:
        return meter

    # If not in cache, fallback to live upstream check
    try:
        geo = await client.get_meter_geo(meter_id)
        if not geo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Meter '{meter_id}' not found in Urja Meter Ops.",
            )
        # Search upstream for basic meter properties
        search_res = await client.search_meters(query=meter_id, page=1)
        data = search_res.get("data", [])
        matched = next((m for m in data if m.get("meterId") == meter_id), None)
        if not matched:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Meter '{meter_id}' not found.")
        matched["geo"] = geo
        return MeterService.normalize_meter(matched)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to query upstream portal for meter {meter_id}: {exc}",
        )


@router.get(
    "/{meter_id}/nameplate",
    response_model=List[NameplateItem],
    summary="Get meter nameplate",
    description="Retrieve normalized nameplate technical specifications, harmonized across legacy and v2 meter models.",
)
async def get_meter_nameplate(
    meter_id: str,
    client: UrjaClient = Depends(get_urja_client),
):
    meter = await get_meter(meter_id, client=client)
    return meter.nameplate
