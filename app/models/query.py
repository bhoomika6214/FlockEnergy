"""Pydantic models for Search, Proximity Queries, Pagination, and Fleet Statistics."""

from typing import Generic, List, Optional, TypeVar, Dict, Any
from pydantic import BaseModel, Field
from app.models.meter import MeterSummary

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Standard generic pagination wrapper."""

    total: int = Field(..., description="Total matching items across all pages", examples=[403])
    page: int = Field(..., description="Current page number (1-indexed)", examples=[1])
    page_size: int = Field(..., description="Items per page", examples=[20])
    total_pages: int = Field(..., description="Total pages available", examples=[21])
    has_next: bool = Field(..., description="Whether a next page exists")
    has_prev: bool = Field(..., description="Whether a previous page exists")
    data: List[T] = Field(..., description="Array of items on the current page")


class NearbyMeterResult(MeterSummary):
    """Meter with calculated distance from target coordinate."""

    distance_km: float = Field(..., description="Great-circle distance in kilometers", examples=[1.42])


class NearbyMetersResponse(BaseModel):
    """Response containing proximity query results."""

    origin_latitude: float = Field(..., description="Query latitude")
    origin_longitude: float = Field(..., description="Query longitude")
    radius_km: float = Field(..., description="Search radius in kilometers")
    total_found: int = Field(..., description="Count of meters within radius")
    meters: List[NearbyMeterResult] = Field(default_factory=list, description="Meters sorted by distance ascending")


class FleetStats(BaseModel):
    """High-level utility fleet metrics and KPIs."""

    total_meters: int = Field(..., description="Total smart meters in network", examples=[403])
    installed_meters: int = Field(..., description="Count of active Installed meters", examples=[238])
    faulty_meters: int = Field(..., description="Count of meters flagged Faulty", examples=[90])
    decommissioned_meters: int = Field(..., description="Count of Decommissioned meters", examples=[75])
    total_transformers: int = Field(..., description="Count of Distribution Transformers", examples=[40])
    total_feeders: int = Field(..., description="Count of primary Feeders", examples=[35])
    total_substations: int = Field(..., description="Count of Substations", examples=[21])
    total_capacity_kva: float = Field(..., description="Aggregated transformer capacity in kVA", examples=[3450.0])
    make_distribution: Dict[str, int] = Field(default_factory=dict, description="Count of meters by manufacturer")
    phase_distribution: Dict[str, int] = Field(default_factory=dict, description="Count by phase configuration")
    build_distribution: Dict[str, int] = Field(default_factory=dict, description="Count by build type (legacy vs v2)")
    install_type_distribution: Dict[str, int] = Field(default_factory=dict, description="Count by install type")
    cache_freshness_seconds: Optional[float] = Field(None, description="Age of current local index in seconds")
    last_synced_at: Optional[str] = Field(None, description="ISO timestamp of last full sync from portal")
