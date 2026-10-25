"""Unit tests for legacy vs v2 meter schema normalization and nameplate extraction."""

import pytest
from app.services.meter_service import MeterService


def test_normalize_legacy_meter():
    """Verify legacy meter dictionary is properly normalized."""
    raw = {
        "meterId": "J100000",
        "serialNo": "SE33962",
        "make": "HPL",
        "phaseType": "single",
        "installStatus": "Decommissioned",
        "installType": "Whole Current",
        "build": "legacy",
        "dtCode": "DT-001",
        "hierarchy": {
            "zone": {"name": "Jaipur Zone 1", "code": "Z-01"},
            "circle": {"name": "Circle 1", "code": "C-01"},
            "division": {"name": "Division 1", "code": "D-01"},
            "subdivision": {"name": "Subdivision 1", "code": "SD-01"},
            "substation": {"name": "Substation 1", "code": "SS-01"},
            "feeder": {"name": "Feeder 1", "code": "F-001"},
            "dt": {"name": "Malviya Nagar DT 1", "code": "DT-001"},
        },
        "geo": {"lat": 26.938961, "lng": 75.830957},
    }

    detail = MeterService.normalize_meter(raw)

    assert detail.meter_id == "J100000"
    assert detail.serial_no == "SE33962"
    assert detail.make == "HPL"
    assert detail.phase_type == "single"
    assert detail.install_status == "Decommissioned"
    assert detail.build == "legacy"
    assert detail.dt_code == "DT-001"
    assert detail.geo is not None
    assert detail.geo.latitude == 26.938961
    assert detail.geo.longitude == 75.830957

    # Check breadcrumb
    assert len(detail.hierarchy_breadcrumb) == 7
    assert detail.hierarchy_breadcrumb[0] == "Jaipur Zone 1"
    assert detail.hierarchy_breadcrumb[-1] == "Malviya Nagar DT 1"

    # Check nameplate dictionary
    assert detail.nameplate_dict["Meter ID"] == "J100000"
    assert detail.nameplate_dict["Make"] == "HPL"
    assert detail.nameplate_dict["Distribution Transformer"] == "DT-001"


def test_normalize_v2_meter():
    """Verify v2 meter with PascalCase and classData attributes is correctly normalized."""
    raw = {
        "MeterId": "J100004",
        "SerialNo": "SE65293",
        "Make": "Genus",
        "PhaseType": "single",
        "InstallationStatus": "Faulty",
        "InstallationType": "CT Operated",
        "build": "v2",
        "dtCode": "DT-005",
        "geo": {"lat": 26.907425, "lng": 75.725037},
    }

    detail = MeterService.normalize_meter(raw)

    assert detail.meter_id == "J100004"
    assert detail.serial_no == "SE65293"
    assert detail.make == "Genus"
    assert detail.install_status == "Faulty"
    assert detail.install_type == "CT Operated"
    assert detail.build == "v2"
    assert detail.dt_code == "DT-005"
