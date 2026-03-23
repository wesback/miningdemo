"""
Historical Data Generator — Mining RTI Demo
=============================================
Generates 31 days of realistic sensor data as CSV files, ready for bulk
ingestion into the KQL database via .ingest commands or Fabric upload.

Features:
  - Diurnal temperature cycles (hotter midday, cooler at night)
  - Shift patterns (day/afternoon/night) with varying production rates
  - Gradual equipment degradation trends on select assets
  - Embedded anomaly events matching real-world incident patterns
  - Weekend production dips
  - Consistent with the live simulator's sensor profiles

Output:
  simulator/historical_data/SensorReadings.csv       (all events)
  simulator/historical_data/SafetyIncidents.csv      (correlated incidents)

Usage:
  python generate_history.py                     # 31 days, default settings
  python generate_history.py --days 7            # 7 days only (faster)
  python generate_history.py --interval 60       # 1 reading/min (smaller file)

Ingestion (run in KQL Queryset after uploading CSV to lakehouse or blob):
  // Option 1: Direct paste for small datasets
  // Option 2: Ingest from blob storage
  .ingest into table SensorReadings (
    h@'https://<storage>.blob.core.windows.net/.../SensorReadings.csv'
  ) with (format='csv', ignoreFirstRecord=true)
"""

from __future__ import annotations

import argparse
import csv
import logging
import math
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("history-gen")

# ---------------------------------------------------------------------------
# Equipment & Sensor Definitions (mirrors simulator.py)
# ---------------------------------------------------------------------------
ZONES = ["Zone-A", "Zone-B", "Zone-C"]
ZONE_COORDS = {
    "Zone-A": (46.4917, -80.9930),
    "Zone-B": (46.4885, -80.9865),
    "Zone-C": (46.4950, -80.9800),
}

EQUIPMENT = [
    # (id, type, zone, sensors)
    # Haul trucks
    ("HT-001", "haul_truck", "Zone-A"),
    ("HT-002", "haul_truck", "Zone-A"),
    ("HT-003", "haul_truck", "Zone-B"),
    ("HT-004", "haul_truck", "Zone-B"),
    ("HT-005", "haul_truck", "Zone-C"),
    # Conveyors
    ("CV-001", "conveyor", "Zone-A"),
    ("CV-002", "conveyor", "Zone-B"),
    ("CV-003", "conveyor", "Zone-C"),
    # Drills
    ("DR-001", "drill", "Zone-A"),
    ("DR-002", "drill", "Zone-A"),
    ("DR-003", "drill", "Zone-B"),
    ("DR-004", "drill", "Zone-C"),
    # Environmental sensors
    ("ES-001", "environmental_sensor", "Zone-A"),
    ("ES-002", "environmental_sensor", "Zone-B"),
    ("ES-003", "environmental_sensor", "Zone-C"),
]

# sensor_type, unit, mean, std, min, max
SENSOR_PROFILES = {
    "haul_truck": [
        ("engine_temp_c", "°C", 85.0, 5.0, 60.0, 120.0),
        ("oil_pressure_kpa", "kPa", 400.0, 30.0, 100.0, 650.0),
        ("vibration_mm_s", "mm/s", 4.0, 1.0, 0.5, 18.0),
        ("load_tonnes", "t", 180.0, 25.0, 0.0, 400.0),
        ("cycle_state", "", 2.0, 1.0, 1.0, 4.0),
    ],
    "conveyor": [
        ("belt_speed_m_s", "m/s", 4.5, 0.3, 0.0, 7.0),
        ("belt_load_kg_m", "kg/m", 500.0, 80.0, 0.0, 1100.0),
        ("vibration_mm_s", "mm/s", 4.5, 1.2, 0.5, 20.0),
    ],
    "drill": [
        ("hydraulic_psi", "PSI", 3200.0, 300.0, 800.0, 5200.0),
        ("vibration_mm_s", "mm/s", 5.0, 1.5, 0.5, 20.0),
        ("engine_temp_c", "°C", 82.0, 4.0, 55.0, 115.0),
    ],
    "environmental_sensor": [
        ("co_ppm", "ppm", 8.0, 3.0, 0.0, 100.0),
        ("ch4_pct", "%LEL", 0.2, 0.1, 0.0, 5.0),
        ("ambient_temp_c", "°C", 28.0, 3.0, 10.0, 50.0),
        ("humidity_pct", "%", 55.0, 10.0, 10.0, 100.0),
        ("dust_mg_m3", "mg/m³", 2.5, 1.0, 0.0, 20.0),
    ],
}

# ---------------------------------------------------------------------------
# Anomaly Schedule — pre-planned incidents over the 31-day window
# Each: (day_offset, hour, duration_minutes, equipment_id, sensor_type, anomaly_value, incident_desc)
# ---------------------------------------------------------------------------
ANOMALY_EVENTS = [
    # Week 1
    (2, 10, 15, "ES-002", "co_ppm", 42.0, "Elevated CO in Zone-B; ventilation adjusted"),
    (3, 14, 8, "CV-001", "vibration_mm_s", 14.5, "Conveyor bearing vibration spike; inspected next shift"),
    (5, 22, 20, "DR-001", "hydraulic_psi", 1380.0, "Drill hydraulic pressure drop; seal replaced"),
    # Week 2
    (8, 9, 12, "HT-003", "engine_temp_c", 108.0, "Haul truck engine overheat; coolant topped up"),
    (10, 16, 30, "ES-001", "ch4_pct", 1.3, "Methane spike Zone-A; partial evacuation 30 min"),
    (11, 6, 45, "CV-003", "belt_speed_m_s", 0.0, "Conveyor stoppage — belt splice failure"),
    (13, 20, 10, "DR-003", "vibration_mm_s", 16.0, "Drill vibration anomaly; bit replaced"),
    # Week 3
    (15, 11, 25, "HT-004", "oil_pressure_kpa", 145.0, "Oil pressure critical; truck returned to workshop"),
    (17, 3, 15, "ES-003", "co_ppm", 38.0, "Night-shift CO elevation Zone-C; ventilation boosted"),
    (19, 13, 60, "CV-002", "vibration_mm_s", 13.8, "Sustained vibration — roller replacement scheduled"),
    (20, 8, 10, "HT-001", "engine_temp_c", 110.0, "Brief overheat during loaded climb"),
    # Week 4
    (22, 15, 20, "DR-002", "hydraulic_psi", 1420.0, "Hydraulic pressure warning; filter changed"),
    (24, 10, 8, "ES-002", "ch4_pct", 1.1, "Minor methane reading; monitoring increased"),
    (26, 19, 90, "CV-001", "belt_speed_m_s", 0.0, "Major conveyor stoppage — motor fault"),
    (27, 7, 15, "HT-005", "vibration_mm_s", 13.0, "Truck vibration during haul; suspension inspected"),
    # Week 5 (days 28-30)
    (29, 12, 20, "ES-001", "co_ppm", 40.0, "CO spike during blasting activity"),
    (30, 14, 30, "HT-002", "engine_temp_c", 106.0, "Gradual overheat; thermostat replaced"),
]

# Equipment with gradual degradation over the 31 days
DEGRADATION_PROFILES = {
    "HT-003": {"engine_temp_c": 0.15},      # +0.15°C per day
    "HT-004": {"oil_pressure_kpa": -1.5},    # -1.5 kPa per day
    "CV-001": {"vibration_mm_s": 0.08},      # +0.08 mm/s per day
    "DR-001": {"hydraulic_psi": -8.0},        # -8 PSI per day
}


# ---------------------------------------------------------------------------
# Value Generation
# ---------------------------------------------------------------------------
def get_shift(hour: int) -> str:
    if 6 <= hour < 14:
        return "day"
    elif 14 <= hour < 22:
        return "afternoon"
    return "night"


def is_weekend(dt: datetime) -> bool:
    return dt.weekday() >= 5  # Saturday=5, Sunday=6


def generate_value(
    sensor_type: str,
    mean: float,
    std: float,
    min_val: float,
    max_val: float,
    hour: int,
    day_offset: int,
    equipment_id: str,
    is_anomaly: bool,
    anomaly_value: float | None,
    weekend: bool,
) -> float:
    """Generate a single sensor value with realistic patterns."""

    # Anomaly override
    if is_anomaly and anomaly_value is not None:
        return max(min_val, min(max_val, anomaly_value + random.gauss(0, std * 0.08)))

    # Cycle state is discrete
    if sensor_type == "cycle_state":
        return float(random.randint(int(min_val), int(max_val)))

    value = random.gauss(mean, std)

    # Diurnal pattern for temperature sensors
    if "temp" in sensor_type:
        # Peak at 14:00, trough at 04:00
        diurnal = 4.0 * math.sin(2 * math.pi * (hour - 4) / 24.0)
        value += diurnal

    # Night shift: slightly lower production, temperatures
    if get_shift(hour) == "night":
        if sensor_type in ("load_tonnes", "belt_load_kg_m"):
            value *= 0.85

    # Weekend: reduced production
    if weekend and sensor_type in ("load_tonnes", "belt_load_kg_m", "belt_speed_m_s"):
        value *= 0.6

    # Gradual degradation
    if equipment_id in DEGRADATION_PROFILES:
        drift = DEGRADATION_PROFILES[equipment_id].get(sensor_type, 0)
        value += drift * day_offset

    return max(min_val, min(max_val, round(value, 2)))


def gps_jitter(base_lat: float, base_lon: float, eq_type: str) -> tuple[float, float]:
    if eq_type == "haul_truck":
        return (
            round(base_lat + random.uniform(-0.002, 0.002), 6),
            round(base_lon + random.uniform(-0.002, 0.002), 6),
        )
    return (
        round(base_lat + random.uniform(-0.0005, 0.0005), 6),
        round(base_lon + random.uniform(-0.0005, 0.0005), 6),
    )


# ---------------------------------------------------------------------------
# Main Generator
# ---------------------------------------------------------------------------
def generate_history(days: int, interval_sec: int, output_dir: Path) -> None:
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        log.error("Failed to create output directory %s: %s", output_dir, e)
        raise

    sensor_file = output_dir / "SensorReadings.csv"
    incidents_file = output_dir / "SafetyIncidents.csv"

    # Build anomaly lookup: (day, hour, minute) → set of active anomalies
    anomaly_windows: dict[tuple[str, str], tuple[float, str]] = {}
    incidents: list[dict] = []

    end_time = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start_time = end_time - timedelta(days=days)

    # Pre-compute anomaly active periods
    for day_off, hour, duration_min, eq_id, sensor, anom_val, desc in ANOMALY_EVENTS:
        if day_off >= days:
            continue
        anom_start = start_time + timedelta(days=day_off, hours=hour)
        anom_end = anom_start + timedelta(minutes=duration_min)

        # Record as incident
        severity = "High" if sensor in ("co_ppm", "ch4_pct", "hydraulic_psi") else "Medium"
        incidents.append({
            "IncidentId": f"INC-{day_off:02d}-{hour:02d}",
            "Timestamp": anom_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "Zone": next(z for eid, _, z in EQUIPMENT if eid == eq_id),
            "Severity": severity,
            "Description": desc,
            "EquipmentId": eq_id,
        })

        # Mark every interval step in the window
        t = anom_start
        while t < anom_end:
            key = (eq_id + ":" + sensor, t.strftime("%Y-%m-%dT%H:%M"))
            anomaly_windows[key] = (anom_val, desc)
            t += timedelta(seconds=interval_sec)

    # Estimate total rows for progress bar
    steps_per_day = (24 * 3600) // interval_sec
    sensors_per_step = sum(len(SENSOR_PROFILES[eq_type]) for _, eq_type, _ in EQUIPMENT)
    total_rows = days * steps_per_day * sensors_per_step
    log.info("Generating %d days of data (%s estimated rows)…", days, f"{total_rows:,}")
    log.info("Interval: %d seconds | Output: %s", interval_sec, sensor_file)

    # Buffered write configuration
    BUFFER_SIZE = 5000  # Write every 5000 rows
    row_buffer: list[list] = []
    row_count = 0

    try:
        with open(sensor_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "EventId", "EquipmentId", "EquipmentType", "SensorType",
                "Value", "Unit", "Zone", "Latitude", "Longitude",
                "Timestamp", "Quality", "Shift",
            ])

            current = start_time

            # Progress bar for sensor data generation
            with tqdm(total=total_rows, desc="Generating sensor data", unit="rows") as pbar:
                while current < end_time:
                    day_offset = (current - start_time).days
                    hour = current.hour
                    minute_key = current.strftime("%Y-%m-%dT%H:%M")
                    shift = get_shift(hour)
                    weekend = is_weekend(current)

                    for eq_id, eq_type, zone in EQUIPMENT:
                        base_lat, base_lon = ZONE_COORDS[zone]
                        sensors = SENSOR_PROFILES[eq_type]

                        for sensor_type, unit, mean, std, min_v, max_v in sensors:
                            # Check if this is an anomaly window
                            anom_key = (eq_id + ":" + sensor_type, minute_key)
                            is_anom = anom_key in anomaly_windows
                            anom_val = anomaly_windows[anom_key][0] if is_anom else None

                            value = generate_value(
                                sensor_type, mean, std, min_v, max_v,
                                hour, day_offset, eq_id, is_anom, anom_val, weekend,
                            )

                            lat, lon = gps_jitter(base_lat, base_lon, eq_type)
                            quality = "good" if random.random() < 0.98 else "suspect"

                            row_buffer.append([
                                f"evt-{uuid.uuid4().hex[:8]}",
                                eq_id, eq_type, sensor_type,
                                value, unit, zone, lat, lon,
                                current.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                                quality, shift,
                            ])
                            row_count += 1
                            pbar.update(1)

                            # Flush buffer when it reaches BUFFER_SIZE
                            if len(row_buffer) >= BUFFER_SIZE:
                                writer.writerows(row_buffer)
                                row_buffer.clear()

                    current += timedelta(seconds=interval_sec)

                # Write any remaining buffered rows
                if row_buffer:
                    writer.writerows(row_buffer)
                    row_buffer.clear()

    except IOError as e:
        log.error("Failed to write sensor data to %s: %s", sensor_file, e)
        raise
    except Exception as e:
        log.error("Unexpected error during sensor data generation: %s", e)
        raise

    log.info("Sensor data complete: %s rows written to %s", f"{row_count:,}", sensor_file)
    
    try:
        file_size_mb = sensor_file.stat().st_size / (1024 * 1024)
        log.info("File size: %.1f MB", file_size_mb)
    except OSError as e:
        log.warning("Could not determine file size: %s", e)

    # Write incidents CSV
    try:
        with open(incidents_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "IncidentId", "Timestamp", "Zone", "Severity", "Description", "EquipmentId",
            ])
            writer.writeheader()
            writer.writerows(incidents)
    except IOError as e:
        log.error("Failed to write incidents data to %s: %s", incidents_file, e)
        raise

    log.info("Safety incidents: %d events written to %s", len(incidents), incidents_file)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate historical mining sensor data for bulk KQL ingestion.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
After generating, ingest into KQL with one of:

  1. Upload CSV to a Fabric Lakehouse, then:
     .ingest into table SensorReadings (
       h@'abfss://...@onelake.dfs.fabric.microsoft.com/.../SensorReadings.csv'
     ) with (format='csv', ignoreFirstRecord=true)

  2. Upload to Azure Blob Storage, then:
     .ingest into table SensorReadings (
       h@'https://<account>.blob.core.windows.net/<container>/SensorReadings.csv<SAS>'
     ) with (format='csv', ignoreFirstRecord=true)

  3. For SafetyIncidents.csv, use the same pattern against the SafetyIncidents table.
        """,
    )
    parser.add_argument(
        "--days", type=int, default=31,
        help="Number of days of history to generate (default: 31)",
    )
    parser.add_argument(
        "--interval", type=int, default=30,
        help="Seconds between readings (default: 30; use 60 for smaller files)",
    )
    parser.add_argument(
        "--output-dir", type=str, default=None,
        help="Output directory (default: simulator/historical_data/)",
    )

    args = parser.parse_args()
    output = Path(args.output_dir) if args.output_dir else Path(__file__).parent / "historical_data"
    generate_history(args.days, args.interval, output)


if __name__ == "__main__":
    main()
