"""API router for Meter Energy Consumption time-series and diagnostics."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.client.urja_client import UrjaClient
from app.models.energy import EnergySummary, MeterEnergyResponse
from app.services.energy_service import EnergyService

router = APIRouter(prefix="/meters", tags=["Energy Consumption"])


def get_urja_client() -> UrjaClient:
    from app.main import urja_client
    return urja_client


@router.get(
    "/{meter_id}/energy",
    response_model=MeterEnergyResponse,
    summary="Get meter energy readings",
    description=(
        "Retrieve time-series consumption readings (active kWh, apparent kVAh, and R-phase voltage) "
        "with optional date window filtering ('from_date' and 'to_date')."
    ),
)
async def get_meter_energy(
    meter_id: str,
    from_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD or DD/MM/YYYY)"),
    to_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD or DD/MM/YYYY)"),
    client: UrjaClient = Depends(get_urja_client),
):
    try:
        raw_readings = await client.get_meter_energy(
            meter_id=meter_id,
            from_date=from_date,
            to_date=to_date,
        )
        if not raw_readings:
            # Check if meter exists at all
            geo = await client.get_meter_geo(meter_id)
            if not geo:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Meter '{meter_id}' not found.",
                )

        return EnergyService.process_readings(meter_id=meter_id, raw_readings=raw_readings)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch energy readings from Urja portal: {exc}",
        )


@router.get(
    "/{meter_id}/energy/summary",
    response_model=EnergySummary,
    summary="Get consumption analytics summary",
    description="Retrieve aggregated consumption KPIs: net kWh delta, estimated power factor, and voltage quality stats.",
)
async def get_meter_energy_summary(
    meter_id: str,
    from_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD or DD/MM/YYYY)"),
    to_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD or DD/MM/YYYY)"),
    client: UrjaClient = Depends(get_urja_client),
):
    full_resp = await get_meter_energy(
        meter_id=meter_id,
        from_date=from_date,
        to_date=to_date,
        client=client,
    )
    if not full_resp.summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No consumption readings found for meter '{meter_id}' in the requested window.",
        )
    return full_resp.summary
