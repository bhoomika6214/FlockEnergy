"""Pydantic models for Meters, Details, Nameplate, and Geolocation."""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class GeoCoordinates(BaseModel):
    """Geographic coordinates for a smart meter."""

    latitude: float = Field(..., description="Latitude coordinate", examples=[26.938961])
    longitude: float = Field(..., description="Longitude coordinate", examples=[75.830957])


class HierarchyTier(BaseModel):
    """A single tier element in the network hierarchy."""

    code: Optional[str] = Field(None, description="Tier code (e.g., Z-01, DT-001)")
    name: Optional[str] = Field(None, description="Tier human-readable name")


class MeterHierarchy(BaseModel):
    """Complete network hierarchy placement for a meter."""

    zone: Optional[HierarchyTier] = None
    circle: Optional[HierarchyTier] = None
    division: Optional[HierarchyTier] = None
    subdivision: Optional[HierarchyTier] = None
    substation: Optional[HierarchyTier] = None
    feeder: Optional[HierarchyTier] = None
    dt: Optional[HierarchyTier] = None


class NameplateItem(BaseModel):
    """A single normalized nameplate attribute."""

    parameter_name: str = Field(..., description="Parameter key/name", examples=["Make"])
    parameter_value: str = Field(..., description="Parameter value", examples=["HPL"])


class MeterSummary(BaseModel):
    """Concise meter summary used in list/search results."""

    meter_id: str = Field(..., description="Unique Meter identifier", examples=["J100000"])
    serial_no: str = Field(..., description="Manufacturer serial number", examples=["SE33962"])
    make: str = Field(..., description="Meter manufacturer (e.g. HPL, Genus, L&T)", examples=["HPL"])
    phase_type: str = Field(..., description="Phase configuration (single / three)", examples=["single"])
    install_status: str = Field(..., description="Installation status (Installed / Faulty / Decommissioned)", examples=["Installed"])
    install_type: Optional[str] = Field(None, description="Installation type (Whole Current / CT Operated)", examples=["Whole Current"])
    build: Optional[str] = Field(None, description="Meter build architecture (legacy / v2)", examples=["legacy"])
    dt_code: Optional[str] = Field(None, description="Connected Distribution Transformer code", examples=["DT-001"])
    geo: Optional[GeoCoordinates] = Field(None, description="Geographic coordinates if available")


class MeterDetail(MeterSummary):
    """Full meter information including nameplate parameters and network hierarchy."""

    hierarchy: Optional[MeterHierarchy] = Field(None, description="Full electrical network hierarchy")
    hierarchy_breadcrumb: List[str] = Field(
        default_factory=list,
        description="Formatted linear path (Zone › Circle › Division › Subdivision › Substation › Feeder › DT)",
    )
    nameplate: List[NameplateItem] = Field(
        default_factory=list,
        description="Clean, normalized list of nameplate parameters",
    )
    nameplate_dict: Dict[str, str] = Field(
        default_factory=dict,
        description="Key-value dictionary of normalized nameplate parameters for easy lookup",
    )
    has_energy_profile: bool = Field(
        default=True,
        description="Indicates whether energy time-series readings are available",
    )
