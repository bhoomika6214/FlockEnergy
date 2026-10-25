"""Unit tests for hierarchy reconstruction and anomaly detection (e.g. DT-007 alias)."""

import pytest
from app.services.hierarchy_service import HierarchyService
from app.services.meter_service import MeterService


def test_hierarchy_anomaly_detection_and_reconciliation():
    """Verify that conflicting names (like DT-007) are flagged as naming_alias anomalies."""
    meters_raw = [
        # Meter 1 with DT-007 as 'Sanganer DT 7'
        {
            "meterId": "M1",
            "serialNo": "S1",
            "make": "HPL",
            "phaseType": "single",
            "installStatus": "Installed",
            "dtCode": "DT-007",
            "hierarchy": {
                "zone": {"code": "Z-01", "name": "Zone 1"},
                "circle": {"code": "C-01", "name": "Circle 1"},
                "division": {"code": "D-01", "name": "Division 1"},
                "subdivision": {"code": "SD-01", "name": "Subdivision 1"},
                "substation": {"code": "SS-01", "name": "Substation 1"},
                "feeder": {"code": "F-001", "name": "Feeder 1"},
                "dt": {"code": "DT-007", "name": "Sanganer DT 7"},
            },
        },
        # Meter 2 with DT-007 as 'Old Malviya Nagar Xfmr'
        {
            "meterId": "M2",
            "serialNo": "S2",
            "make": "HPL",
            "phaseType": "single",
            "installStatus": "Installed",
            "dtCode": "DT-007",
            "hierarchy": {
                "zone": {"code": "Z-01", "name": "Zone 1"},
                "circle": {"code": "C-01", "name": "Circle 1"},
                "division": {"code": "D-01", "name": "Division 1"},
                "subdivision": {"code": "SD-01", "name": "Subdivision 1"},
                "substation": {"code": "SS-01", "name": "Substation 1"},
                "feeder": {"code": "F-001", "name": "Feeder 1"},
                "dt": {"code": "DT-007", "name": "Old Malviya Nagar Xfmr"},
            },
        },
    ]

    meters = [MeterService.normalize_meter(m) for m in meters_raw]
    tree, report = HierarchyService.analyze_and_build(meters)

    assert tree.total_meters_indexed == 2
    assert tree.total_zones == 1
    assert tree.total_dts == 1

    # Anomaly report should detect DT-007 naming conflict
    dt_anomalies = [a for a in report.anomalies if a.entity_code == "DT-007"]
    assert len(dt_anomalies) == 1
    assert dt_anomalies[0].anomaly_type == "naming_alias"
    assert "Sanganer DT 7" in dt_anomalies[0].variants
    assert "Old Malviya Nagar Xfmr" in dt_anomalies[0].variants
