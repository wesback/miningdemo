"""
Mining Sensor Data Simulator
============================
Generates realistic streaming sensor events for the Fabric Real-Time Intelligence
mining demo. Publishes JSON events to an Azure Event Hub (or Fabric Eventstream
custom endpoint).

Usage:
    python simulator.py                         # Run with defaults
    python simulator.py --config config.yaml    # Run with custom config
    python simulator.py --inject-anomaly gas    # Inject a specific anomaly scenario

Environment variables (or pass via --connection-string):
    EVENT_HUB_CONNECTION_STRING  — Event Hub namespace connection string
    EVENT_HUB_NAME               — Event Hub / Eventstream topic name

Requirements:
    pip install azure-eventhub pyyaml
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import random
import signal
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

try:
    from azure.eventhub import EventData, EventHubProducerClient
except ImportError:
    EventHubProducerClient = None  # type: ignore[assignment,misc]

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("mining-simulator")

# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------
_shutdown = False


def _signal_handler(signum: int, frame: Any) -> None:
    global _shutdown
    logger.info("Shutdown signal received — finishing current batch…")
    _shutdown = True


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)

# ---------------------------------------------------------------------------
# Constants & Defaults
# ---------------------------------------------------------------------------
DEFAULT_INTERVAL_SEC = 10  # seconds between batches
DEFAULT_BATCH_SIZE = 50  # events per batch
ZONES = ["Zone-A", "Zone-B", "Zone-C"]

# GPS coordinates centred on a fictional Sudbury Basin (Ontario) mine site
ZONE_COORDS: dict[str, tuple[float, float]] = {
    "Zone-A": (46.4917, -80.9930),
    "Zone-B": (46.4885, -80.9865),
    "Zone-C": (46.4950, -80.9800),
}


# ---------------------------------------------------------------------------
# Sensor Profile Definitions
# ---------------------------------------------------------------------------
@dataclass
class SensorProfile:
    """Defines the statistical behaviour of a single sensor type."""

    sensor_type: str
    unit: str
    mean: float
    std: float
    min_val: float
    max_val: float
    anomaly_value: float | None = None  # value injected during anomaly mode
    drift_rate: float = 0.0  # per-hour drift for degradation simulation


# Haul truck sensors
HAUL_TRUCK_SENSORS = [
    SensorProfile("engine_temp_c", "°C", 85.0, 5.0, 60.0, 120.0, anomaly_value=112.0),
    SensorProfile("oil_pressure_kpa", "kPa", 400.0, 30.0, 100.0, 650.0, anomaly_value=130.0),
    SensorProfile("vibration_mm_s", "mm/s", 4.0, 1.0, 0.5, 18.0, anomaly_value=14.0),
    SensorProfile("load_tonnes", "t", 180.0, 25.0, 0.0, 400.0),
    SensorProfile("cycle_state", "", 2.0, 1.0, 1.0, 4.0),  # 1=load,2=travel-loaded,3=dump,4=travel-empty
]

# Conveyor sensors
CONVEYOR_SENSORS = [
    SensorProfile("belt_speed_m_s", "m/s", 4.5, 0.3, 0.0, 7.0, anomaly_value=0.0),
    SensorProfile("belt_load_kg_m", "kg/m", 500.0, 80.0, 0.0, 1100.0),
    SensorProfile("vibration_mm_s", "mm/s", 4.5, 1.2, 0.5, 20.0, anomaly_value=15.0),
]

# Drill sensors
DRILL_SENSORS = [
    SensorProfile("hydraulic_psi", "PSI", 3200.0, 300.0, 800.0, 5200.0, anomaly_value=1350.0),
    SensorProfile("vibration_mm_s", "mm/s", 5.0, 1.5, 0.5, 20.0, anomaly_value=16.0),
    SensorProfile("engine_temp_c", "°C", 82.0, 4.0, 55.0, 115.0),
]

# Environmental sensors
ENVIRONMENTAL_SENSORS = [
    SensorProfile("co_ppm", "ppm", 8.0, 3.0, 0.0, 100.0, anomaly_value=45.0),
    SensorProfile("ch4_pct", "%LEL", 0.2, 0.1, 0.0, 5.0, anomaly_value=1.5),
    SensorProfile("ambient_temp_c", "°C", 28.0, 3.0, 10.0, 50.0, anomaly_value=38.0),
    SensorProfile("humidity_pct", "%", 55.0, 10.0, 10.0, 100.0),
    SensorProfile("dust_mg_m3", "mg/m³", 2.5, 1.0, 0.0, 20.0),
]

# Equipment type → sensor profiles mapping
EQUIPMENT_PROFILES: dict[str, list[SensorProfile]] = {
    "haul_truck": HAUL_TRUCK_SENSORS,
    "conveyor": CONVEYOR_SENSORS,
    "drill": DRILL_SENSORS,
    "environmental_sensor": ENVIRONMENTAL_SENSORS,
}

# ---------------------------------------------------------------------------
# Equipment Fleet
# ---------------------------------------------------------------------------
@dataclass
class Equipment:
    equipment_id: str
    equipment_type: str
    zone: str
    sensors: list[SensorProfile] = field(default_factory=list)


DEFAULT_FLEET: list[Equipment] = [
    # Haul trucks
    Equipment("HT-001", "haul_truck", "Zone-A", HAUL_TRUCK_SENSORS),
    Equipment("HT-002", "haul_truck", "Zone-A", HAUL_TRUCK_SENSORS),
    Equipment("HT-003", "haul_truck", "Zone-B", HAUL_TRUCK_SENSORS),
    Equipment("HT-004", "haul_truck", "Zone-B", HAUL_TRUCK_SENSORS),
    Equipment("HT-005", "haul_truck", "Zone-C", HAUL_TRUCK_SENSORS),
    # Conveyors
    Equipment("CV-001", "conveyor", "Zone-A", CONVEYOR_SENSORS),
    Equipment("CV-002", "conveyor", "Zone-B", CONVEYOR_SENSORS),
    Equipment("CV-003", "conveyor", "Zone-C", CONVEYOR_SENSORS),
    # Drills
    Equipment("DR-001", "drill", "Zone-A", DRILL_SENSORS),
    Equipment("DR-002", "drill", "Zone-A", DRILL_SENSORS),
    Equipment("DR-003", "drill", "Zone-B", DRILL_SENSORS),
    Equipment("DR-004", "drill", "Zone-C", DRILL_SENSORS),
    # Environmental sensors
    Equipment("ES-001", "environmental_sensor", "Zone-A", ENVIRONMENTAL_SENSORS),
    Equipment("ES-002", "environmental_sensor", "Zone-B", ENVIRONMENTAL_SENSORS),
    Equipment("ES-003", "environmental_sensor", "Zone-C", ENVIRONMENTAL_SENSORS),
]


# ---------------------------------------------------------------------------
# Shift Resolver
# ---------------------------------------------------------------------------
def current_shift() -> str:
    """Return the current shift name based on UTC hour."""
    hour = datetime.now(timezone.utc).hour
    if 6 <= hour < 14:
        return "day"
    elif 14 <= hour < 22:
        return "afternoon"
    return "night"


# ---------------------------------------------------------------------------
# Sensor Value Generator
# ---------------------------------------------------------------------------
class SensorValueGenerator:
    """
    Generates realistic sensor values with optional:
    - Gaussian noise around a mean
    - Sinusoidal diurnal pattern (e.g., temperature)
    - Gradual drift (degradation simulation)
    - Anomaly injection (fixed or spike)
    """

    def __init__(self) -> None:
        self._start_time = time.time()
        self._anomaly_targets: dict[str, set[str]] = {}  # equipment_id → {sensor_type}
        self._drift_offsets: dict[str, float] = {}  # equipment_id:sensor_type → cumulative drift

    def inject_anomaly(self, equipment_id: str, sensor_type: str) -> None:
        """Mark a specific equipment+sensor pair for anomaly injection."""
        self._anomaly_targets.setdefault(equipment_id, set()).add(sensor_type)
        logger.warning("Anomaly injection enabled: %s / %s", equipment_id, sensor_type)

    def clear_anomalies(self) -> None:
        """Remove all anomaly injections."""
        self._anomaly_targets.clear()
        logger.info("All anomaly injections cleared.")

    def generate(self, equipment: Equipment, sensor: SensorProfile) -> float:
        """Generate a single sensor reading."""
        key = f"{equipment.equipment_id}:{sensor.sensor_type}"

        # Check for anomaly injection
        if (
            equipment.equipment_id in self._anomaly_targets
            and sensor.sensor_type in self._anomaly_targets[equipment.equipment_id]
            and sensor.anomaly_value is not None
        ):
            # Add slight noise around anomaly value for realism
            return max(sensor.min_val, min(sensor.max_val,
                       sensor.anomaly_value + random.gauss(0, sensor.std * 0.1)))

        # Cycle state is discrete (1-4)
        if sensor.sensor_type == "cycle_state":
            return float(random.randint(int(sensor.min_val), int(sensor.max_val)))

        # Base value: Gaussian around mean
        value = random.gauss(sensor.mean, sensor.std)

        # Diurnal sinusoidal pattern for temperature sensors
        if "temp" in sensor.sensor_type:
            elapsed_hours = (time.time() - self._start_time) / 3600.0
            diurnal_offset = 3.0 * math.sin(2 * math.pi * elapsed_hours / 24.0)
            value += diurnal_offset

        # Gradual drift for degradation simulation
        if sensor.drift_rate != 0:
            elapsed_hours = (time.time() - self._start_time) / 3600.0
            self._drift_offsets[key] = self._drift_offsets.get(key, 0.0) + (
                sensor.drift_rate * elapsed_hours / 360.0  # small incremental drift
            )
            value += self._drift_offsets[key]

        # Clamp to physical range
        return max(sensor.min_val, min(sensor.max_val, round(value, 2)))


# ---------------------------------------------------------------------------
# Event Builder
# ---------------------------------------------------------------------------
def build_event(
    equipment: Equipment,
    sensor: SensorProfile,
    value: float,
) -> dict[str, Any]:
    """Construct a single sensor event as a JSON-serialisable dict."""
    base_lat, base_lon = ZONE_COORDS.get(equipment.zone, (46.49, -80.99))
    # Add small GPS jitter for haul trucks (they move)
    if equipment.equipment_type == "haul_truck":
        lat = base_lat + random.uniform(-0.002, 0.002)
        lon = base_lon + random.uniform(-0.002, 0.002)
    else:
        lat = base_lat + random.uniform(-0.0005, 0.0005)
        lon = base_lon + random.uniform(-0.0005, 0.0005)

    return {
        "EventId": f"evt-{uuid.uuid4().hex[:8]}",
        "EquipmentId": equipment.equipment_id,
        "EquipmentType": equipment.equipment_type,
        "SensorType": sensor.sensor_type,
        "Value": value,
        "Unit": sensor.unit,
        "Zone": equipment.zone,
        "Latitude": round(lat, 6),
        "Longitude": round(lon, 6),
        "Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "Quality": random.choices(["good", "suspect"], weights=[98, 2])[0],
        "Shift": current_shift(),
    }


# ---------------------------------------------------------------------------
# Publisher — Azure Event Hub
# ---------------------------------------------------------------------------
class EventHubPublisher:
    """Publishes events to Azure Event Hub using batched sends."""

    def __init__(self, connection_string: str, eventhub_name: str) -> None:
        if EventHubProducerClient is None:
            raise ImportError(
                "azure-eventhub is required. Install with: pip install azure-eventhub"
            )
        self._producer = EventHubProducerClient.from_connection_string(
            conn_str=connection_string,
            eventhub_name=eventhub_name,
        )
        logger.info("Event Hub publisher initialised for hub '%s'", eventhub_name)

    def send_batch(self, events: list[dict[str, Any]]) -> int:
        """Send a list of events as a single batch. Returns count sent."""
        batch = self._producer.create_batch()
        count = 0
        for event in events:
            try:
                batch.add(EventData(json.dumps(event)))
                count += 1
            except ValueError:
                # Batch full — send what we have and start a new one
                self._send_batch_with_retry(batch)
                batch = self._producer.create_batch()
                batch.add(EventData(json.dumps(event)))
                count += 1
        if count > 0:
            self._send_batch_with_retry(batch)
        return count

    def _send_batch_with_retry(self, batch) -> None:
        """Send batch with exponential backoff retry on transient failures."""
        max_retries = 3
        delay = 1.0
        for attempt in range(max_retries):
            try:
                self._producer.send_batch(batch)
                return
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(
                        "Event Hub send failed (attempt %d/%d): %s. Retrying in %.1fs...",
                        attempt + 1, max_retries, e, delay
                    )
                    time.sleep(delay)
                    delay *= 2
                else:
                    logger.error(
                        "Event Hub send failed after %d attempts: %s", max_retries, e
                    )
                    raise

    def close(self) -> None:
        self._producer.close()


# ---------------------------------------------------------------------------
# Publisher — Console (for local testing without Event Hub)
# ---------------------------------------------------------------------------
class ConsolePublisher:
    """Prints events to stdout as JSON lines (for local testing)."""

    def send_batch(self, events: list[dict[str, Any]]) -> int:
        for event in events:
            print(json.dumps(event))
        return len(events)

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Anomaly Scenario Definitions
# ---------------------------------------------------------------------------
ANOMALY_SCENARIOS: dict[str, list[tuple[str, str]]] = {
    "gas": [
        ("ES-001", "co_ppm"),
        ("ES-002", "ch4_pct"),
    ],
    "vibration": [
        ("CV-001", "vibration_mm_s"),
        ("CV-002", "vibration_mm_s"),
    ],
    "hydraulic": [
        ("DR-001", "hydraulic_psi"),
        ("DR-003", "hydraulic_psi"),
    ],
    "overheat": [
        ("HT-003", "engine_temp_c"),
        ("HT-004", "engine_temp_c"),
    ],
    "conveyor_stop": [
        ("CV-003", "belt_speed_m_s"),
    ],
    "all": [],  # populated dynamically
}


# ---------------------------------------------------------------------------
# Config Validation
# ---------------------------------------------------------------------------
def _validate_yaml_config(raw: dict) -> list[str]:
    """Validate YAML config structure and value ranges. Returns list of error messages."""
    errors = []
    
    # Check for required fields when not using console mode
    if not raw.get("connection_string") and not raw.get("console_mode"):
        errors.append("Missing 'connection_string' (required unless console_mode: true)")
    if not raw.get("eventhub_name") and not raw.get("console_mode"):
        errors.append("Missing 'eventhub_name' (required unless console_mode: true)")
    
    # Validate numeric ranges
    if "interval_sec" in raw:
        val = raw["interval_sec"]
        if not isinstance(val, (int, float)) or val <= 0 or val > 3600:
            errors.append(f"'interval_sec' must be a positive number <= 3600, got: {val}")
    
    if "batch_size" in raw:
        val = raw["batch_size"]
        if not isinstance(val, int) or val <= 0 or val > 10000:
            errors.append(f"'batch_size' must be a positive integer <= 10000, got: {val}")
    
    if "max_iterations" in raw:
        val = raw["max_iterations"]
        if not isinstance(val, int) or val < 0:
            errors.append(f"'max_iterations' must be a non-negative integer, got: {val}")
    
    return errors


# ---------------------------------------------------------------------------
# Config Data Class
# ---------------------------------------------------------------------------
# "all" scenario combines every other scenario
for _scenario_targets in list(ANOMALY_SCENARIOS.values()):
    if _scenario_targets:
        ANOMALY_SCENARIOS["all"].extend(_scenario_targets)


# ---------------------------------------------------------------------------
# Configuration Loader
# ---------------------------------------------------------------------------
@dataclass
class SimulatorConfig:
    connection_string: str = ""
    eventhub_name: str = ""
    interval_sec: int = DEFAULT_INTERVAL_SEC
    batch_size: int = DEFAULT_BATCH_SIZE
    fleet: list[Equipment] = field(default_factory=lambda: list(DEFAULT_FLEET))
    anomaly_scenario: str | None = None
    console_mode: bool = False
    max_iterations: int = 0  # 0 = infinite


def load_config(args: argparse.Namespace) -> SimulatorConfig:
    """Build configuration from CLI args, env vars, and optional YAML file."""
    config = SimulatorConfig()

    # Load YAML config if provided
    if args.config:
        if yaml is None:
            logger.error("pyyaml is required for config files. Install: pip install pyyaml")
            sys.exit(1)
        with open(args.config) as f:
            raw = yaml.safe_load(f)
        
        # Validate YAML config
        validation_errors = _validate_yaml_config(raw)
        if validation_errors:
            logger.error("Config file validation failed:")
            for err in validation_errors:
                logger.error("  - %s", err)
            sys.exit(1)
        
        config.connection_string = raw.get("connection_string", "")
        config.eventhub_name = raw.get("eventhub_name", "")
        config.interval_sec = raw.get("interval_sec", DEFAULT_INTERVAL_SEC)
        config.batch_size = raw.get("batch_size", DEFAULT_BATCH_SIZE)
        config.max_iterations = raw.get("max_iterations", 0)

    # CLI / env overrides
    config.connection_string = (
        args.connection_string
        or config.connection_string
        or os.environ.get("EVENT_HUB_CONNECTION_STRING", "")
    )
    config.eventhub_name = (
        args.eventhub_name
        or config.eventhub_name
        or os.environ.get("EVENT_HUB_NAME", "")
    )
    config.interval_sec = args.interval or config.interval_sec
    config.anomaly_scenario = args.inject_anomaly
    config.console_mode = args.console or not config.connection_string
    config.max_iterations = args.max_iterations or config.max_iterations

    if config.console_mode:
        logger.info("Running in CONSOLE mode (no Event Hub connection).")
    elif not config.connection_string:
        logger.error(
            "No Event Hub connection string provided. "
            "Set EVENT_HUB_CONNECTION_STRING or use --console for local testing."
        )
        sys.exit(1)

    return config


# ---------------------------------------------------------------------------
# Main Simulation Loop
# ---------------------------------------------------------------------------
def run_simulation(config: SimulatorConfig) -> None:
    """Core simulation loop — generates and publishes sensor events."""
    generator = SensorValueGenerator()

    # Set up publisher
    if config.console_mode:
        publisher: ConsolePublisher | EventHubPublisher = ConsolePublisher()
    else:
        publisher = EventHubPublisher(config.connection_string, config.eventhub_name)

    # Apply anomaly scenario
    if config.anomaly_scenario:
        scenario = config.anomaly_scenario.lower()
        if scenario not in ANOMALY_SCENARIOS:
            logger.error(
                "Unknown anomaly scenario '%s'. Available: %s",
                scenario,
                ", ".join(ANOMALY_SCENARIOS.keys()),
            )
            sys.exit(1)
        for eq_id, sensor_type in ANOMALY_SCENARIOS[scenario]:
            generator.inject_anomaly(eq_id, sensor_type)

    iteration = 0
    total_events = 0
    logger.info(
        "Simulation started — interval=%ds, fleet=%d assets, anomaly=%s",
        config.interval_sec,
        len(config.fleet),
        config.anomaly_scenario or "none",
    )

    try:
        while not _shutdown:
            batch: list[dict[str, Any]] = []

            for equipment in config.fleet:
                for sensor in equipment.sensors:
                    value = generator.generate(equipment, sensor)
                    event = build_event(equipment, sensor, value)
                    batch.append(event)

            # Send batch
            sent = publisher.send_batch(batch)
            total_events += sent
            iteration += 1

            logger.info(
                "Batch %d: sent %d events (total: %d)",
                iteration,
                sent,
                total_events,
            )

            # Check iteration limit
            if 0 < config.max_iterations <= iteration:
                logger.info("Reached max iterations (%d). Stopping.", config.max_iterations)
                break

            # Wait for next interval
            time.sleep(config.interval_sec)

    except Exception:
        logger.exception("Simulation error")
        raise
    finally:
        publisher.close()
        logger.info("Simulation stopped. Total events sent: %d", total_events)


# ---------------------------------------------------------------------------
# CLI Argument Parser
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mining sensor data simulator for Fabric Real-Time Intelligence demo.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Anomaly scenarios:
  gas             Inject high CO (ES-001) and CH₄ (ES-002) readings
  vibration       Inject high vibration on conveyors CV-001, CV-002
  hydraulic       Inject low hydraulic pressure on drills DR-001, DR-003
  overheat        Inject high engine temp on trucks HT-003, HT-004
  conveyor_stop   Inject zero belt speed on CV-003
  all             Inject all anomaly scenarios simultaneously

Examples:
  python simulator.py --console                          # Local test, print to stdout
  python simulator.py --console --inject-anomaly gas     # Local test with gas anomaly
  python simulator.py --interval 5                       # Send every 5 seconds
  python simulator.py --inject-anomaly all               # Full demo with all anomalies
        """,
    )
    parser.add_argument(
        "--connection-string",
        help="Event Hub connection string (overrides EVENT_HUB_CONNECTION_STRING env var)",
    )
    parser.add_argument(
        "--eventhub-name",
        help="Event Hub name (overrides EVENT_HUB_NAME env var)",
    )
    parser.add_argument(
        "--config",
        help="Path to YAML configuration file",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL_SEC,
        help=f"Seconds between batches (default: {DEFAULT_INTERVAL_SEC})",
    )
    parser.add_argument(
        "--inject-anomaly",
        choices=list(ANOMALY_SCENARIOS.keys()),
        help="Inject a predefined anomaly scenario",
    )
    parser.add_argument(
        "--console",
        action="store_true",
        help="Print events to stdout instead of sending to Event Hub",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=0,
        help="Stop after N batches (0 = run indefinitely)",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
def main() -> None:
    args = parse_args()
    config = load_config(args)
    run_simulation(config)


if __name__ == "__main__":
    main()
