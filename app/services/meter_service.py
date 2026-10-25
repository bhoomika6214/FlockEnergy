"""Meter domain logic: normalization of legacy vs v2 schemas, breadcrumb generation."""

from typing import Any, Dict, List, Optional
from app.models.meter import (
    GeoCoordinates,
    HierarchyTier,
    MeterHierarchy,
    MeterSummary,
    MeterDetail,
    NameplateItem,
)


class MeterService:
    """Handles parsing, normalization, and enrichment of smart meter data."""

    @staticmethod
    def normalize_meter(raw: Dict[str, Any]) -> MeterDetail:
        """Transform raw portal/export meter dictionary into a clean MeterDetail model."""
        meter_id = raw.get("meterId") or raw.get("MeterId") or ""
        serial_no = raw.get("serialNo") or raw.get("SerialNo") or ""
        make = raw.get("make") or raw.get("Make") or "Unknown"
        phase_type = raw.get("phaseType") or raw.get("PhaseType") or "single"
        install_status = raw.get("installStatus") or raw.get("InstallationStatus") or "Unknown"
        install_type = raw.get("installType") or raw.get("InstallationType") or "Whole Current"
        build = raw.get("build") or ("v2" if "classData" in raw else "legacy")
        dt_code = raw.get("dtCode") or raw.get("dt_code")

        # Parse Geolocation
        geo = None
        raw_geo = raw.get("geo")
        if raw_geo and isinstance(raw_geo, dict):
            lat = raw_geo.get("lat") or raw_geo.get("latitude")
            lng = raw_geo.get("lng") or raw_geo.get("longitude")
            if lat is not None and lng is not None:
                try:
                    geo = GeoCoordinates(latitude=float(lat), longitude=float(lng))
                except (ValueError, TypeError):
                    geo = None

        # Parse Hierarchy
        hierarchy = None
        raw_h = raw.get("hierarchy")
        if raw_h and isinstance(raw_h, dict):
            def make_tier(tier_key: str) -> Optional[HierarchyTier]:
                t = raw_h.get(tier_key)
                if isinstance(t, dict):
                    code = t.get("code") or ""
                    name = t.get("name") or ""
                    if code or name:
                        return HierarchyTier(code=code or None, name=name or None)
                elif isinstance(t, str) and t.strip():
                    return HierarchyTier(code=None, name=t.strip())
                return None

            hierarchy = MeterHierarchy(
                zone=make_tier("zone") or make_tier("Zone"),
                circle=make_tier("circle") or make_tier("Circle"),
                division=make_tier("division") or make_tier("Division"),
                subdivision=make_tier("subdivision") or make_tier("Subdivision"),
                substation=make_tier("substation") or make_tier("Sub Station") or make_tier("Substation"),
                feeder=make_tier("feeder") or make_tier("Feeder"),
                dt=make_tier("dt") or make_tier("DT"),
            )

        # Build Hierarchy Breadcrumb
        breadcrumb = []
        if hierarchy:
            for tier_obj in [
                hierarchy.zone,
                hierarchy.circle,
                hierarchy.division,
                hierarchy.subdivision,
                hierarchy.substation,
                hierarchy.feeder,
                hierarchy.dt,
            ]:
                if tier_obj:
                    label = tier_obj.name or tier_obj.code
                    if label:
                        breadcrumb.append(label)

        # Build Normalized Nameplate
        nameplate_items: List[NameplateItem] = [
            NameplateItem(parameter_name="Meter ID", parameter_value=str(meter_id)),
            NameplateItem(parameter_name="Serial No", parameter_value=str(serial_no)),
            NameplateItem(parameter_name="Make", parameter_value=str(make)),
            NameplateItem(parameter_name="Phase Type", parameter_value=str(phase_type)),
            NameplateItem(parameter_name="Installation Status", parameter_value=str(install_status)),
            NameplateItem(parameter_name="Installation Type", parameter_value=str(install_type)),
            NameplateItem(parameter_name="Build Architecture", parameter_value=str(build)),
        ]

        if dt_code:
            nameplate_items.append(NameplateItem(parameter_name="Distribution Transformer", parameter_value=str(dt_code)))

        nameplate_dict = {item.parameter_name: item.parameter_value for item in nameplate_items}

        return MeterDetail(
            meter_id=meter_id,
            serial_no=serial_no,
            make=make,
            phase_type=phase_type,
            install_status=install_status,
            install_type=install_type,
            build=build,
            dt_code=dt_code,
            geo=geo,
            hierarchy=hierarchy,
            hierarchy_breadcrumb=breadcrumb,
            nameplate=nameplate_items,
            nameplate_dict=nameplate_dict,
            has_energy_profile=True,
        )

    @staticmethod
    def to_summary(detail: MeterDetail) -> MeterSummary:
        """Convert a MeterDetail model into a lightweight MeterSummary."""
        return MeterSummary(
            meter_id=detail.meter_id,
            serial_no=detail.serial_no,
            make=detail.make,
            phase_type=detail.phase_type,
            install_status=detail.install_status,
            install_type=detail.install_type,
            build=detail.build,
            dt_code=detail.dt_code,
            geo=detail.geo,
        )
