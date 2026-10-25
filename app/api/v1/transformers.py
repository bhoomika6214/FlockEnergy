"""API router for Distribution Transformers (DTs)."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status

from app.client.urja_client import UrjaClient
from app.models.transformer import DistributionTransformer, DistributionTransformerDetail
from app.services.index_service import index_service

router = APIRouter(prefix="/transformers", tags=["Transformers"])


def get_urja_client() -> UrjaClient:
    from app.main import urja_client
    return urja_client


@router.get(
    "",
    response_model=List[DistributionTransformer],
    summary="List all distribution transformers",
    description="Retrieve all distribution transformers in the utility network with rated capacity, parent feeder, and connected meter counts.",
)
async def list_transformers(client: UrjaClient = Depends(get_urja_client)):
    if not index_service.is_cached:
        await index_service.sync(client)

    return index_service.get_all_transformers()


@router.get(
    "/{code}",
    response_model=DistributionTransformerDetail,
    summary="Get transformer detail",
    description="Retrieve distribution transformer detail along with the list of smart meters connected to it.",
)
async def get_transformer(code: str, client: UrjaClient = Depends(get_urja_client)):
    if not index_service.is_cached:
        await index_service.sync(client)

    dt = index_service.get_transformer_by_code(code)
    if not dt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Distribution Transformer '{code}' not found.",
        )
    return dt
