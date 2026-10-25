"""Pydantic models for Network Hierarchy and Anomaly Reporting."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class HierarchyNode(BaseModel):
    """A node in the reconstructed electrical network hierarchy tree."""

    id: str = Field(..., description="Unique node identifier (tier:code)", examples=["zone:Z-01"])
    tier: str = Field(..., description="Hierarchy tier (zone, circle, division, subdivision, substation, feeder, dt)", examples=["zone"])
    code: str = Field(..., description="Canonical tier code", examples=["Z-01"])
    name: str = Field(..., description="Canonical tier name", examples=["Jaipur Zone 1"])
    meter_count: int = Field(0, description="Total meters subordinate to this node")
    children: List["HierarchyNode"] = Field(default_factory=list, description="Subordinate child nodes")


class HierarchyAnomaly(BaseModel):
    """A detected anomaly or quirk in the legacy portal hierarchy data."""

    anomaly_type: str = Field(
        ...,
        description="Type of quirk (e.g., naming_alias, empty_code, empty_name, multi_parent_feeder)",
        examples=["naming_alias"],
    )
    tier: str = Field(..., description="Hierarchy tier where quirk occurred", examples=["dt"])
    entity_code: str = Field(..., description="Affected entity identifier", examples=["DT-007"])
    details: str = Field(..., description="Human explanation of the data inconsistency")
    variants: List[str] = Field(default_factory=list, description="Observed conflicting variations in the dataset")
    meter_ids: List[str] = Field(default_factory=list, description="Sample meter IDs exhibiting this anomaly")


class HierarchyAnomalyReport(BaseModel):
    """Comprehensive data quality report for the electrical network hierarchy."""

    total_anomalies: int = Field(..., description="Count of distinct data quirks discovered")
    anomalies: List[HierarchyAnomaly] = Field(..., description="List of detected anomalies")
    reconciliation_strategy: str = Field(
        ...,
        description="Explanation of how the API reconciled and resolved these anomalies",
    )


class HierarchyTreeResponse(BaseModel):
    """Network hierarchy tree root container."""

    total_meters_indexed: int
    total_zones: int
    total_circles: int
    total_feeders: int
    total_dts: int
    anomalies_count: int
    tree: List[HierarchyNode]
