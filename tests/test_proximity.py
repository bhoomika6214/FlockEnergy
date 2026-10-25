"""Unit tests for Great-Circle (Haversine) distance and nearby search."""

import pytest
from app.services.index_service import haversine_km, IndexService
from app.services.meter_service import MeterService


def test_haversine_distance_calculation():
    """Verify Haversine formula against known coordinates."""
    # Jaipur Hawa Mahal: 26.9239, 75.8267
    # Jaipur Jal Mahal: 26.9656, 75.8458
    # Actual distance ~ 5.0 km
    dist = haversine_km(26.9239, 75.8267, 26.9656, 75.8458)
    assert 4.5 <= dist <= 5.5


def test_find_nearby_meters():
    """Verify spatial index returns meters sorted by proximity within radius."""
    index = IndexService()
    # Add two meters
    m1_raw = {
        "meterId": "M_NEAR",
        "serialNo": "SN1",
        "make": "HPL",
        "phaseType": "single",
        "installStatus": "Installed",
        "geo": {"lat": 26.9124, "lng": 75.7873},  # ~0 km from center
    }
    m2_raw = {
        "meterId": "M_FAR",
        "serialNo": "SN2",
        "make": "HPL",
        "phaseType": "single",
        "installStatus": "Installed",
        "geo": {"lat": 27.5000, "lng": 75.7873},  # ~65 km away
    }

    m1 = MeterService.normalize_meter(m1_raw)
    m2 = MeterService.normalize_meter(m2_raw)

    index._meters_list = [m1, m2]
    index._meters_by_id = {m1.meter_id: m1, m2.meter_id: m2}

    # Search within 10 km
    res = index.find_nearby_meters(latitude=26.9124, longitude=75.7873, radius_km=10.0)

    assert res.total_found == 1
    assert res.meters[0].meter_id == "M_NEAR"
    assert res.meters[0].distance_km < 0.1
