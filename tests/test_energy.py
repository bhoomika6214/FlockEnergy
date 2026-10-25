"""Unit tests for energy time-series parsing, delta consumption, and voltage diagnostics."""

import pytest
from app.services.energy_service import EnergyService


def test_energy_reading_parsing():
    """Verify raw portal reading is parsed into clean ISO timestamp and numerical values."""
    raw = {
        "timestamp": "24/06/2026 00:00",
        "kwh": "48439.16",
        "kvah": "52314.29",
        "voltR": "229",
    }
    reading = EnergyService.parse_raw_reading(raw)

    assert reading.timestamp_raw == "24/06/2026 00:00"
    assert reading.timestamp_iso == "2026-06-24T00:00:00"
    assert reading.kwh == 48439.16
    assert reading.kvah == 52314.29
    assert reading.voltage_r == 229.0


def test_energy_consumption_deltas_and_stats():
    """Verify net consumption, power factor, and voltage bands calculation."""
    raw_readings = [
        {"timestamp": "24/06/2026 00:00", "kwh": "100.00", "kvah": "110.00", "voltR": "230"},
        {"timestamp": "24/06/2026 00:30", "kwh": "102.50", "kvah": "112.80", "voltR": "205"},  # undervoltage < 210
        {"timestamp": "24/06/2026 01:00", "kwh": "106.00", "kvah": "116.80", "voltR": "248"},  # overvoltage > 245
    ]

    resp = EnergyService.process_readings("TEST_METER", raw_readings)

    assert resp.total_readings == 3
    summary = resp.summary
    assert summary is not None
    assert summary.start_kwh == 100.00
    assert summary.end_kwh == 106.00
    assert summary.net_consumption_kwh == 6.00  # 106.00 - 100.00
    assert summary.net_consumption_kvah == 6.80  # 116.80 - 110.00
    assert summary.estimated_power_factor == round(6.00 / 6.80, 3)

    # Voltage checks
    diag = summary.voltage_diagnostics
    assert diag.min_volts == 205.0
    assert diag.max_volts == 248.0
    assert diag.avg_volts == round((230 + 205 + 248) / 3, 1)
    assert diag.undervoltage_count == 1
    assert diag.overvoltage_count == 1
    assert diag.nominal_count == 1
    assert summary.sampling_resolution == "30-minute interval profile"
