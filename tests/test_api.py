"""Integration tests for FastAPI REST API endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.index_service import index_service
from app.services.meter_service import MeterService

client = TestClient(app)


@pytest.fixture(autouse=True)
def populate_test_index():
    """Seed in-memory index with sample meters and transformers for API testing."""
    sample_meters = [
        MeterService.normalize_meter({
            "meterId": "J100000",
            "serialNo": "SE33962",
            "make": "HPL",
            "phaseType": "single",
            "installStatus": "Installed",
            "installType": "Whole Current",
            "build": "legacy",
            "dtCode": "DT-001",
            "geo": {"lat": 26.938961, "lng": 75.830957},
            "hierarchy": {
                "zone": {"code": "Z-01", "name": "Zone 1"},
                "circle": {"code": "C-01", "name": "Circle 1"},
                "division": {"code": "D-01", "name": "Division 1"},
                "subdivision": {"code": "SD-01", "name": "Subdivision 1"},
                "substation": {"code": "SS-01", "name": "Substation 1"},
                "feeder": {"code": "F-001", "name": "Feeder 1"},
                "dt": {"code": "DT-001", "name": "DT 1"},
            },
        }),
        MeterService.normalize_meter({
            "meterId": "J100001",
            "serialNo": "GE84132",
            "make": "L&T",
            "phaseType": "three",
            "installStatus": "Faulty",
            "installType": "CT Operated",
            "build": "v2",
            "dtCode": "DT-002",
            "geo": {"lat": 26.822136, "lng": 75.907182},
        }),
    ]

    index_service._meters_list = sample_meters
    index_service._meters_by_id = {m.meter_id: m for m in sample_meters}


def test_health_check_endpoint():
    """Verify GET /health returns service status and upstream config."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "Urja" in data["service"]


def test_list_meters_endpoint():
    """Verify GET /api/v1/meters pagination and filtering."""
    resp = client.get("/api/v1/meters?make=HPL")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["data"][0]["meter_id"] == "J100000"
    assert data["data"][0]["make"] == "HPL"


def test_get_meter_detail_endpoint():
    """Verify GET /api/v1/meters/{id} returns full detail."""
    resp = client.get("/api/v1/meters/J100000")
    assert resp.status_code == 200
    data = resp.json()
    assert data["meter_id"] == "J100000"
    assert data["dt_code"] == "DT-001"
    assert len(data["nameplate"]) > 0


def test_get_meter_nameplate_endpoint():
    """Verify GET /api/v1/meters/{id}/nameplate returns normalized parameters."""
    resp = client.get("/api/v1/meters/J100000/nameplate")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    param_names = [p["parameter_name"] for p in data]
    assert "Meter ID" in param_names
    assert "Make" in param_names


def test_nearby_meters_endpoint():
    """Verify GET /api/v1/meters/nearby performs distance sorting."""
    resp = client.get("/api/v1/meters/nearby?latitude=26.9389&longitude=75.8309&radius_km=5.0")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_found"] >= 1
    assert data["meters"][0]["meter_id"] == "J100000"
    assert data["meters"][0]["distance_km"] < 1.0


def test_stats_endpoint():
    """Verify GET /api/v1/stats calculates fleet KPIs."""
    resp = client.get("/api/v1/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_meters"] == 2
    assert data["installed_meters"] == 1
    assert data["faulty_meters"] == 1
