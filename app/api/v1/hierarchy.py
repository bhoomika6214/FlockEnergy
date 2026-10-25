"""API router for Electrical Network Hierarchy and Anomaly Diagnostics."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.client.urja_client import UrjaClient
from app.models.hierarchy import HierarchyAnomalyReport, HierarchyTreeResponse
from app.services.index_service import index_service

router = APIRouter(prefix="/hierarchy", tags=["Network Hierarchy"])


def get_urja_client() -> UrjaClient:
    from app.main import urja_client
    return urja_client


@router.get(
    "/tree",
    response_model=HierarchyTreeResponse,
    summary="Get reconstructed network hierarchy tree",
    description=(
        "Retrieve the complete reconstructed electrical distribution hierarchy "
        "(Zone › Circle › Division › Subdivision › Substation › Feeder › DT) with subordinate meter counts."
    ),
)
async def get_hierarchy_tree(client: UrjaClient = Depends(get_urja_client)):
    if not index_service.is_cached:
        await index_service.sync(client)

    tree = index_service.get_hierarchy_tree()
    if not tree:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Network hierarchy has not yet been indexed.",
        )
    return tree


@router.get(
    "/anomalies",
    response_model=HierarchyAnomalyReport,
    summary="Get data quality & anomaly diagnostic report",
    description=(
        "Audit report detailing legacy data inconsistencies discovered in the Urja portal "
        "(aliased names like DT-007, blank codes, multi-parent feeder mappings) and the reconciliation strategy applied."
    ),
)
async def get_hierarchy_anomalies(client: UrjaClient = Depends(get_urja_client)):
    if not index_service.is_cached:
        await index_service.sync(client)

    report = index_service.get_hierarchy_anomalies()
    if not report:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Hierarchy anomaly diagnostics not yet available.",
        )
    return report
