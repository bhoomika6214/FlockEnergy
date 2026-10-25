"""Energy domain logic: parsing, unit conversion, and consumption analytics."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from app.models.energy import (
    EnergyReading,
    EnergySummary,
    MeterEnergyResponse,
    VoltageStats,
)


class EnergyService:
    """Processes raw time-series energy records into standardized readings and metrics."""

    @classmethod
    def parse_raw_reading(cls, raw: Dict[str, Any]) -> EnergyReading:
        """Parse raw portal record into a typed EnergyReading."""
        raw_ts = raw.get("timestamp", "").strip()
        iso_ts = None
        if raw_ts:
            try:
                # Format: DD/MM/YYYY HH:MM
                dt = datetime.strptime(raw_ts, "%d/%m/%Y %H:%M")
                iso_ts = dt.isoformat()
            except ValueError:
                iso_ts = None

        def to_float(val: Any) -> Optional[float]:
            if val is None or val == "" or val == "—":
                return None
            try:
                return float(val)
            except (ValueError, TypeError):
                return None

        kwh = to_float(raw.get("kwh"))
        kvah = to_float(raw.get("kvah"))
        volts = to_float(raw.get("voltR"))

        return EnergyReading(
            timestamp_raw=raw_ts,
            timestamp_iso=iso_ts,
            kwh=kwh,
            kvah=kvah,
            voltage_r=volts,
        )

    @classmethod
    def process_readings(
        cls,
        meter_id: str,
        raw_readings: List[Dict[str, Any]],
    ) -> MeterEnergyResponse:
        """Parse raw readings, sort chronologically, and compute analytical summaries."""
        if not raw_readings:
            return MeterEnergyResponse(
                meter_id=meter_id,
                total_readings=0,
                summary=None,
                readings=[],
            )

        parsed: List[EnergyReading] = [cls.parse_raw_reading(r) for r in raw_readings]

        # Filter and sort by ISO timestamp if available, else keep portal order
        readings = sorted(
            parsed,
            key=lambda x: x.timestamp_iso or x.timestamp_raw,
        )

        total_count = len(readings)
        first_r = readings[0]
        last_r = readings[-1]

        # Calculate Energy Deltas
        start_kwh = first_r.kwh
        end_kwh = last_r.kwh
        net_kwh = None
        if start_kwh is not None and end_kwh is not None:
            net_kwh = round(max(0.0, end_kwh - start_kwh), 2)

        start_kvah = first_r.kvah
        end_kvah = last_r.kvah
        net_kvah = None
        if start_kvah is not None and end_kvah is not None:
            net_kvah = round(max(0.0, end_kvah - start_kvah), 2)

        # Estimate Power Factor (kWh / kVAh)
        pf = None
        if net_kwh is not None and net_kvah is not None and net_kvah > 0:
            pf = round(min(1.0, max(0.0, net_kwh / net_kvah)), 3)

        # Detect Sampling Resolution
        resolution = "Variable / Unknown"
        if len(readings) >= 2 and first_r.timestamp_iso and readings[1].timestamp_iso:
            try:
                t0 = datetime.fromisoformat(first_r.timestamp_iso)
                t1 = datetime.fromisoformat(readings[1].timestamp_iso)
                diff_min = abs((t1 - t0).total_seconds()) / 60
                if 25 <= diff_min <= 35:
                    resolution = "30-minute interval profile"
                elif 1400 <= diff_min <= 1480:
                    resolution = "Daily midnight billing read"
                else:
                    resolution = f"{int(diff_min)}-minute interval"
            except Exception:
                pass

        # Voltage Quality Diagnostics
        volt_vals = [r.voltage_r for r in readings if r.voltage_r is not None]
        v_min = min(volt_vals) if volt_vals else None
        v_max = max(volt_vals) if volt_vals else None
        v_avg = round(sum(volt_vals) / len(volt_vals), 1) if volt_vals else None

        undervolts = sum(1 for v in volt_vals if v < 210.0)
        overvolts = sum(1 for v in volt_vals if v > 245.0)
        nominal = len(volt_vals) - undervolts - overvolts

        volt_stats = VoltageStats(
            min_volts=v_min,
            max_volts=v_max,
            avg_volts=v_avg,
            undervoltage_count=undervolts,
            overvoltage_count=overvolts,
            nominal_count=nominal,
        )

        summary = EnergySummary(
            meter_id=meter_id,
            reading_count=total_count,
            sampling_resolution=resolution,
            start_time=first_r.timestamp_iso or first_r.timestamp_raw,
            end_time=last_r.timestamp_iso or last_r.timestamp_raw,
            start_kwh=start_kwh,
            end_kwh=end_kwh,
            net_consumption_kwh=net_kwh,
            net_consumption_kvah=net_kvah,
            estimated_power_factor=pf,
            voltage_diagnostics=volt_stats,
        )

        return MeterEnergyResponse(
            meter_id=meter_id,
            total_readings=total_count,
            summary=summary,
            readings=readings,
        )
