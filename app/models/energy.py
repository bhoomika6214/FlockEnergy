"""Pydantic models for Meter Energy and Consumption Time-Series."""

from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class EnergyReading(BaseModel):
    """Normalized single consumption interval record."""

    timestamp_raw: str = Field(..., description="Original raw timestamp from portal (DD/MM/YYYY HH:MM)", examples=["24/06/2026 00:00"])
    timestamp_iso: Optional[str] = Field(None, description="Standard ISO-8601 formatted timestamp", examples=["2026-06-24T00:00:00"])
    kwh: Optional[float] = Field(None, description="Cumulative active energy in kilowatt-hours (kWh)", examples=[48439.16])
    kvah: Optional[float] = Field(None, description="Cumulative apparent energy in kilovolt-ampere-hours (kVAh)", examples=[52314.29])
    voltage_r: Optional[float] = Field(None, description="R-phase voltage in Volts (V)", examples=[229.0])


class VoltageStats(BaseModel):
    """Voltage quality diagnostics."""

    min_volts: Optional[float] = Field(None, description="Minimum recorded voltage (V)")
    max_volts: Optional[float] = Field(None, description="Maximum recorded voltage (V)")
    avg_volts: Optional[float] = Field(None, description="Mean recorded voltage (V)")
    undervoltage_count: int = Field(0, description="Readings with voltage < 210V")
    overvoltage_count: int = Field(0, description="Readings with voltage > 245V")
    nominal_count: int = Field(0, description="Readings within standard nominal band [210V, 245V]")


class EnergySummary(BaseModel):
    """Statistical summary of consumption and power quality across the requested window."""

    meter_id: str = Field(..., description="Meter ID")
    reading_count: int = Field(..., description="Total readings in window")
    sampling_resolution: str = Field(..., description="Detected sampling frequency (e.g. 30-minute interval, daily)")
    start_time: Optional[str] = Field(None, description="Earliest reading timestamp")
    end_time: Optional[str] = Field(None, description="Latest reading timestamp")
    start_kwh: Optional[float] = Field(None, description="Initial kWh register reading")
    end_kwh: Optional[float] = Field(None, description="Final kWh register reading")
    net_consumption_kwh: Optional[float] = Field(None, description="Net active energy consumed (end_kwh - start_kwh)")
    net_consumption_kvah: Optional[float] = Field(None, description="Net apparent energy consumed")
    estimated_power_factor: Optional[float] = Field(None, description="Estimated average power factor (kWh/kVAh)")
    voltage_diagnostics: VoltageStats = Field(default_factory=VoltageStats)


class MeterEnergyResponse(BaseModel):
    """Full response wrapper for meter energy readings."""

    meter_id: str = Field(..., description="Meter ID")
    total_readings: int = Field(..., description="Total readings returned")
    summary: Optional[EnergySummary] = Field(None, description="Aggregated analytics summary")
    readings: List[EnergyReading] = Field(default_factory=list, description="Chronological energy readings")
