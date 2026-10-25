"""Local in-memory index, search, spatial proximity, and caching layer."""

import asyncio
import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.client.urja_client import UrjaClient
from app.config import settings
from app.models.hierarchy import HierarchyAnomalyReport, HierarchyTreeResponse
from app.models.meter import MeterDetail, MeterSummary
from app.models.query import (
    FleetStats,
    NearbyMeterResult,
    NearbyMetersResponse,
    PaginatedResponse,
)
from app.models.transformer import DistributionTransformerDetail
from app.services.hierarchy_service import HierarchyService
from app.services.meter_service import MeterService

logger = logging.getLogger(__name__)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the Great Circle distance between two points on Earth in kilometers."""
    r = 6371.0  # Earth radius in kilometers
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2.0) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(r * c, 3)


class IndexService:
    """In-memory indexing and query layer providing advanced filtering, spatial proximity,

    and caching over the Urja Meter Ops legacy dataset.
    """

    def __init__(self):
        self._meters_by_id: Dict[str, MeterDetail] = {}
        self._meters_list: List[MeterDetail] = []
        self._transformers_by_code: Dict[str, DistributionTransformerDetail] = {}
        self._hierarchy_tree: Optional[HierarchyTreeResponse] = None
        self._anomaly_report: Optional[HierarchyAnomalyReport] = None
        self._last_synced: Optional[datetime] = None
        self._lock = asyncio.Lock()

    @property
    def is_cached(self) -> bool:
        """Check whether local index contains populated records."""
        return len(self._meters_by_id) > 0

    @property
    def cache_age_seconds(self) -> Optional[float]:
        """Age of current cache in seconds."""
        if not self._last_synced:
            return None
        return (datetime.now(timezone.utc) - self._last_synced).total_seconds()

    @property
    def is_stale(self) -> bool:
        """Check whether cache exceeded configured TTL."""
        age = self.cache_age_seconds
        if age is None:
            return True
        return age > settings.cache_ttl_seconds

    async def sync(self, client: UrjaClient, force: bool = False) -> Dict[str, Any]:
        """Fetch full dataset from Urja portal and update index.

        Uses the high-performance HMAC-signed /portal/export bulk path and DT crawling.
        """
        async with self._lock:
            if not force and self.is_cached and not self.is_stale:
                return {
                    "status": "cached",
                    "meters_count": len(self._meters_by_id),
                    "cache_age_seconds": self.cache_age_seconds,
                }

            logger.info("Syncing Urja portal dataset into local index...")
            start_t = datetime.now()

            # 1. Fetch Transformers
            raw_dts = await client.get_all_transformers()
            dts_map: Dict[str, Dict[str, Any]] = {}
            for dt in raw_dts:
                code = dt.get("code")
                if code:
                    dts_map[code.strip()] = dt

            # 2. Fetch Bulk Meters via HMAC export
            raw_meters = await client.export_all_meters()
            logger.info(f"Retrieved {len(raw_meters)} raw meter records and {len(raw_dts)} DT records.")

            # 3. Normalize Meters
            meters_by_id: Dict[str, MeterDetail] = {}
            meters_list: List[MeterDetail] = []
            for raw_m in raw_meters:
                m_detail = MeterService.normalize_meter(raw_m)
                meters_by_id[m_detail.meter_id] = m_detail
                meters_list.append(m_detail)

            # 4. Build Transformers with Connected Meters
            transformers_by_code: Dict[str, DistributionTransformerDetail] = {}
            dt_meters_map: Dict[str, List[MeterSummary]] = {}
            for m in meters_list:
                dt_c = m.dt_code
                if dt_c:
                    dt_meters_map.setdefault(dt_c, []).append(MeterService.to_summary(m))

            for code, raw_dt in dts_map.items():
                conn_meters = dt_meters_map.get(code, [])
                transformers_by_code[code] = DistributionTransformerDetail(
                    code=code,
                    name=raw_dt.get("name", f"DT {code}"),
                    feeder_code=raw_dt.get("feederCode", "Unknown"),
                    capacity_kva=float(raw_dt.get("capacityKva", 0.0)),
                    connected_meters_count=len(conn_meters),
                    connected_meters=conn_meters,
                )

            # 5. Build Hierarchy Tree & Anomaly Report
            tree_resp, anomaly_rep = HierarchyService.analyze_and_build(meters_list)

            # 6. Commit to in-memory state
            self._meters_by_id = meters_by_id
            self._meters_list = meters_list
            self._transformers_by_code = transformers_by_code
            self._hierarchy_tree = tree_resp
            self._anomaly_report = anomaly_rep
            self._last_synced = datetime.now(timezone.utc)

            elapsed = (datetime.now() - start_t).total_seconds()
            logger.info(
                f"Sync completed in {elapsed:.2f}s: {len(meters_by_id)} meters, "
                f"{len(transformers_by_code)} DTs, {tree_resp.anomalies_count} anomalies."
            )

            return {
                "status": "synced",
                "meters_count": len(meters_by_id),
                "transformers_count": len(transformers_by_code),
                "anomalies_count": tree_resp.anomalies_count,
                "elapsed_seconds": round(elapsed, 2),
            }

    # -------------------------------------------------------------------------
    # Query & Search Engine
    # -------------------------------------------------------------------------

    def query_meters(
        self,
        q: Optional[str] = None,
        make: Optional[str] = None,
        phase_type: Optional[str] = None,
        install_status: Optional[str] = None,
        install_type: Optional[str] = None,
        build: Optional[str] = None,
        dt_code: Optional[str] = None,
        feeder_code: Optional[str] = None,
        substation_code: Optional[str] = None,
        sort_by: str = "meter_id",
        sort_order: str = "asc",
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse[MeterSummary]:
        """Perform multi-attribute filtering, free-text search, and pagination."""
        results = self._meters_list

        # Attribute Filters
        if make:
            m_lower = make.lower()
            results = [m for m in results if m.make.lower() == m_lower]

        if phase_type:
            p_lower = phase_type.lower()
            results = [m for m in results if m.phase_type.lower() == p_lower]

        if install_status:
            s_lower = install_status.lower()
            results = [m for m in results if m.install_status.lower() == s_lower]

        if install_type:
            it_lower = install_type.lower()
            results = [m for m in results if m.install_type and m.install_type.lower() == it_lower]

        if build:
            b_lower = build.lower()
            results = [m for m in results if m.build and m.build.lower() == b_lower]

        if dt_code:
            dt_upper = dt_code.strip().upper()
            results = [m for m in results if m.dt_code and m.dt_code.upper() == dt_upper]

        if feeder_code:
            f_upper = feeder_code.strip().upper()
            results = [
                m for m in results
                if m.hierarchy and m.hierarchy.feeder and m.hierarchy.feeder.code and m.hierarchy.feeder.code.upper() == f_upper
            ]

        if substation_code:
            ss_upper = substation_code.strip().upper()
            results = [
                m for m in results
                if m.hierarchy and m.hierarchy.substation and m.hierarchy.substation.code and m.hierarchy.substation.code.upper() == ss_upper
            ]

        # Free-Text Multi-Field Search
        if q and q.strip():
            query_str = q.strip().lower()
            filtered = []
            for m in results:
                searchable = [
                    m.meter_id,
                    m.serial_no,
                    m.make,
                    m.dt_code or "",
                ]
                if m.hierarchy:
                    for tier in [m.hierarchy.feeder, m.hierarchy.substation, m.hierarchy.division, m.hierarchy.zone]:
                        if tier:
                            if tier.name: searchable.append(tier.name)
                            if tier.code: searchable.append(tier.code)
                # Check if any searchable term contains query_str
                if any(query_str in s.lower() for s in searchable):
                    filtered.append(m)
            results = filtered

        # Sorting
        reverse = (sort_order.lower() == "desc")
        if sort_by == "serial_no":
            results = sorted(results, key=lambda x: x.serial_no, reverse=reverse)
        elif sort_by == "make":
            results = sorted(results, key=lambda x: x.make, reverse=reverse)
        elif sort_by == "install_status":
            results = sorted(results, key=lambda x: x.install_status, reverse=reverse)
        elif sort_by == "phase_type":
            results = sorted(results, key=lambda x: x.phase_type, reverse=reverse)
        elif sort_by == "dt_code":
            results = sorted(results, key=lambda x: x.dt_code or "", reverse=reverse)
        else:
            results = sorted(results, key=lambda x: x.meter_id, reverse=reverse)

        # Pagination
        total = len(results)
        page_size = max(1, min(page_size, 100))
        total_pages = max(1, math.ceil(total / page_size))
        page = max(1, min(page, total_pages)) if total > 0 else 1

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        slice_items = results[start_idx:end_idx]

        summaries = [MeterService.to_summary(m) for m in slice_items]

        return PaginatedResponse[MeterSummary](
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=(page < total_pages),
            has_prev=(page > 1),
            data=summaries,
        )

    # -------------------------------------------------------------------------
    # Spatial Proximity Engine
    # -------------------------------------------------------------------------

    def find_nearby_meters(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 5.0,
        limit: int = 50,
    ) -> NearbyMetersResponse:
        """Find smart meters within radius_km using Haversine great-circle calculation."""
        matches: List[Tuple[float, MeterDetail]] = []

        for m in self._meters_list:
            if m.geo:
                dist = haversine_km(latitude, longitude, m.geo.latitude, m.geo.longitude)
                if dist <= radius_km:
                    matches.append((dist, m))

        # Sort by distance ascending
        matches.sort(key=lambda x: x[0])
        limit = max(1, min(limit, 200))
        selected = matches[:limit]

        results = [
            NearbyMeterResult(
                meter_id=m.meter_id,
                serial_no=m.serial_no,
                make=m.make,
                phase_type=m.phase_type,
                install_status=m.install_status,
                install_type=m.install_type,
                build=m.build,
                dt_code=m.dt_code,
                geo=m.geo,
                distance_km=dist,
            )
            for dist, m in selected
        ]

        return NearbyMetersResponse(
            origin_latitude=latitude,
            origin_longitude=longitude,
            radius_km=radius_km,
            total_found=len(matches),
            meters=results,
        )

    # -------------------------------------------------------------------------
    # Single Meter Lookup
    # -------------------------------------------------------------------------

    def get_meter_by_id(self, meter_id: str) -> Optional[MeterDetail]:
        """Fetch full meter detail from local index."""
        return self._meters_by_id.get(meter_id)

    # -------------------------------------------------------------------------
    # Transformers
    # -------------------------------------------------------------------------

    def get_all_transformers(self) -> List[DistributionTransformerDetail]:
        """Return all distribution transformers."""
        return sorted(self._transformers_by_code.values(), key=lambda x: x.code)

    def get_transformer_by_code(self, code: str) -> Optional[DistributionTransformerDetail]:
        """Look up DT by its unique code."""
        return self._transformers_by_code.get(code.strip().upper())

    # -------------------------------------------------------------------------
    # Hierarchy
    # -------------------------------------------------------------------------

    def get_hierarchy_tree(self) -> Optional[HierarchyTreeResponse]:
        """Return reconstructed hierarchical tree."""
        return self._hierarchy_tree

    def get_hierarchy_anomalies(self) -> Optional[HierarchyAnomalyReport]:
        """Return detected anomaly diagnostics."""
        return self._anomaly_report

    # -------------------------------------------------------------------------
    # Fleet Statistics
    # -------------------------------------------------------------------------

    def get_fleet_stats(self) -> FleetStats:
        """Compute fleet KPIs across the indexed meters and transformers."""
        meters = self._meters_list
        total = len(meters)

        installed = sum(1 for m in meters if m.install_status.lower() == "installed")
        faulty = sum(1 for m in meters if m.install_status.lower() == "faulty")
        decom = sum(1 for m in meters if m.install_status.lower() == "decommissioned")

        makes: Dict[str, int] = {}
        phases: Dict[str, int] = {}
        builds: Dict[str, int] = {}
        install_types: Dict[str, int] = {}

        feeders: Set[str] = set()
        substations: Set[str] = set()

        for m in meters:
            makes[m.make] = makes.get(m.make, 0) + 1
            phases[m.phase_type] = phases.get(m.phase_type, 0) + 1
            if m.build: builds[m.build] = builds.get(m.build, 0) + 1
            if m.install_type: install_types[m.install_type] = install_types.get(m.install_type, 0) + 1

            if m.hierarchy:
                if m.hierarchy.feeder and m.hierarchy.feeder.code:
                    feeders.add(m.hierarchy.feeder.code)
                if m.hierarchy.substation and m.hierarchy.substation.code:
                    substations.add(m.hierarchy.substation.code)

        dts = list(self._transformers_by_code.values())
        total_kva = sum(dt.capacity_kva for dt in dts)

        return FleetStats(
            total_meters=total,
            installed_meters=installed,
            faulty_meters=faulty,
            decommissioned_meters=decom,
            total_transformers=len(dts),
            total_feeders=len(feeders),
            total_substations=len(substations),
            total_capacity_kva=round(total_kva, 1),
            make_distribution=makes,
            phase_distribution=phases,
            build_distribution=builds,
            install_type_distribution=install_types,
            cache_freshness_seconds=self.cache_age_seconds,
            last_synced_at=self._last_synced.isoformat() if self._last_synced else None,
        )


index_service = IndexService()
