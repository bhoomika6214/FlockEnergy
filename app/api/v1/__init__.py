"""API v1 router assembly."""

from fastapi import APIRouter

from app.api.v1.energy import router as energy_router
from app.api.v1.hierarchy import router as hierarchy_router
from app.api.v1.meters import router as meters_router
from app.api.v1.system import router as system_router
from app.api.v1.transformers import router as transformers_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(meters_router)
api_v1_router.include_router(energy_router)
api_v1_router.include_router(transformers_router)
api_v1_router.include_router(hierarchy_router)
api_v1_router.include_router(system_router)

__all__ = ["api_v1_router"]
