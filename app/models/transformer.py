"""Pydantic models for Distribution Transformers (DTs)."""

from typing import List, Optional
from pydantic import BaseModel, Field
from app.models.meter import MeterSummary


class DistributionTransformer(BaseModel):
    """Distribution transformer entity."""

    code: str = Field(..., description="Unique DT code", examples=["DT-001"])
    name: str = Field(..., description="Transformer station name", examples=["Malviya Nagar DT 1"])
    feeder_code: str = Field(..., description="Parent 11kV Feeder code", examples=["F-001"])
    capacity_kva: float = Field(..., description="Rated transformer capacity in kVA", examples=[100.0])
    connected_meters_count: int = Field(0, description="Total smart meters fed by this transformer")


class DistributionTransformerDetail(DistributionTransformer):
    """Transformer with connected meter details."""

    connected_meters: List[MeterSummary] = Field(
        default_factory=list,
        description="List of meters connected under this distribution transformer",
    )
