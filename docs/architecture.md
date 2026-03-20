# Architecture — Fabric Real-Time Intelligence for Mining

## High-Level Data Flow

```
┌──────────────┐    ┌───────────────────┐    ┌──────────────────┐
│   Python      │    │  Fabric            │    │  KQL Database     │
│   Simulator   │───▶│  Eventstream       │───▶│  (Eventhouse)     │
│  (Event Hub)  │    │  (Ingestion)       │    │                  │
└──────────────┘    └───────────────────┘    └────────┬─────────┘
                                                       │
                          ┌────────────────────────────┼──────────────────┐
                          │                            │                  │
                    ┌─────▼──────┐            ┌───────▼────────┐  ┌─────▼──────┐
                    │ Real-Time   │            │  Data Activator │  │ KQL        │
                    │ Dashboard   │            │  (Alerts)       │  │ Queryset   │
                    └────────────┘            └────────────────┘  └────────────┘
```

## 1. Eventstream — Ingestion Pipeline

### Source
The Python simulator publishes JSON events to an **Azure Event Hub** (or Fabric Eventstream custom endpoint). Each message is a single sensor reading:

```json
{
  "EventId": "evt-a7f3c1",
  "EquipmentId": "HT-003",
  "EquipmentType": "haul_truck",
  "SensorType": "engine_temp_c",
  "Value": 92.4,
  "Unit": "°C",
  "Zone": "Zone-B",
  "Latitude": -23.7011,
  "Longitude": 119.8045,
  "Timestamp": "2026-03-11T08:15:32.441Z",
  "Quality": "good",
  "Shift": "day"
}
```

### Eventstream Configuration
| Setting | Value |
|---------|-------|
| Source type | Azure Event Hubs / Custom endpoint |
| Consumer group | `$Default` |
| Data format | JSON |
| Destination | KQL Database — `SensorReadings` table |
| Ingestion mapping | `SensorReadingsJsonMapping` (defined below) |

### Routing
A single Eventstream routes all sensor data into the `SensorReadings` landing table. KQL **update policies** fan out records into type-specific materialised tables for optimised querying.

---

## 2. KQL Database Schema

### Eventhouse / Database
- **Eventhouse name:** `MiningRTI`
- **Database name:** `MiningOps`
- **Hot cache:** 90 days
- **Retention:** 365 days

### Tables

#### 2.1 Landing Table — `SensorReadings`
All raw sensor events land here via Eventstream.

| Column | Type | Description |
|--------|------|-------------|
| EventId | `string` | Unique event identifier |
| EquipmentId | `string` | Asset tag (e.g., HT-003, CV-012) |
| EquipmentType | `string` | haul_truck, conveyor, drill, environmental_sensor |
| SensorType | `string` | engine_temp_c, vibration_mm_s, hydraulic_psi, co_ppm, ch4_pct, etc. |
| Value | `real` | Sensor reading |
| Unit | `string` | Unit of measure |
| Zone | `string` | Mine zone identifier |
| Latitude | `real` | GPS latitude |
| Longitude | `real` | GPS longitude |
| Timestamp | `datetime` | Event timestamp (UTC) |
| Quality | `string` | good, suspect, bad |
| Shift | `string` | day, afternoon, night |

#### 2.2 Materialised Tables (populated via update policies)

| Table | Filter Condition | Purpose |
|-------|-----------------|---------|
| `EquipmentTelemetry` | EquipmentType in (haul_truck, conveyor, drill) | Equipment-centric queries |
| `EnvironmentalReadings` | EquipmentType == environmental_sensor | Gas, temp, humidity queries |
| `ProductionMetrics` | SensorType in (load_tonnes, belt_load_kg_m, belt_speed_m_s, cycle_state) | Production throughput |

#### 2.3 Reference Tables

**`EquipmentRegistry`** — Static asset master data.

| Column | Type |
|--------|------|
| EquipmentId | `string` |
| EquipmentType | `string` |
| Make | `string` |
| Model | `string` |
| YearCommissioned | `int` |
| Zone | `string` |
| Status | `string` |

**`AlertThresholds`** — Configurable thresholds per sensor type.

| Column | Type |
|--------|------|
| SensorType | `string` |
| WarningLow | `real` |
| WarningHigh | `real` |
| CriticalLow | `real` |
| CriticalHigh | `real` |
| Unit | `string` |
| Description | `string` |

**`SafetyIncidents`** — Manual / external incident records for correlation.

| Column | Type |
|--------|------|
| IncidentId | `string` |
| Timestamp | `datetime` |
| Zone | `string` |
| Severity | `string` |
| Description | `string` |
| EquipmentId | `string` |

---

## 3. Real-Time Dashboard Layout

### Page 1 — Operations Overview
| Tile | Type | KQL Source | Refresh |
|------|------|-----------|---------|
| Active Equipment Count | Stat card | `EquipmentStatusSummary` | 30 s |
| Shift Tonnage vs Target | Bar chart | `ShiftTonnageProgress` | 60 s |
| Equipment Status Map | Map visual | `EquipmentCurrentPosition` | 30 s |
| Active Alerts | Table | `ActiveAlerts` | 15 s |

### Page 2 — Safety & Environment
| Tile | Type | KQL Source | Refresh |
|------|------|-----------|---------|
| Gas Levels by Zone | Multi-line chart | `GasLevelsByZone` | 15 s |
| Temperature Heat Map | Heat map | `ZoneTemperatures` | 60 s |
| Threshold Breaches (24 h) | Table | `RecentBreaches` | 30 s |
| Safety Incident Timeline | Timeline | `SafetyIncidentTimeline` | 5 min |

### Page 3 — Equipment Health
| Tile | Type | KQL Source | Refresh |
|------|------|-----------|---------|
| Vibration Anomaly Trend | Scatter | `VibrationAnomalies` | 30 s |
| Hydraulic Pressure (Drills) | Line chart | `DrillHydraulicTrend` | 30 s |
| Equipment Health Scores | Table (conditional) | `EquipmentHealthScores` | 4 hr |
| Equipment Utilisation | Bar chart | `EquipmentUtilisation` | 5 min |

### Page 4 — Production
| Tile | Type | KQL Source | Refresh |
|------|------|-----------|---------|
| Conveyor Throughput Trend | Area chart | `ConveyorThroughput` | 60 s |
| Haul Truck Cycle Times | Grouped bar | `TruckCycleTimes` | 5 min |
| Route Efficiency | Table | `RouteEfficiency` | 5 min |
| 7-Day Production Trend | Line chart | `ProductionTrend7d` | 15 min |

---

## 4. Data Activator — Alert Rules

| Rule Name | Source | Condition | Severity | Action |
|-----------|--------|-----------|----------|--------|
| Gas Breach — CO | `EnvironmentalReadings` | `SensorType == "co_ppm" and Value > 35` | Critical | Teams + Email + SMS |
| Gas Breach — CH₄ | `EnvironmentalReadings` | `SensorType == "ch4_pct" and Value > 1.0` | Critical | Teams + Email + SMS |
| High Temperature Zone | `EnvironmentalReadings` | `SensorType == "ambient_temp_c" and Value > 35` | Warning | Teams + Email |
| Vibration Anomaly | `EquipmentTelemetry` | Value > rolling 15-min avg + 3σ | Warning | Teams + Email |
| Hydraulic Pressure Low | `EquipmentTelemetry` | `SensorType == "hydraulic_psi" and Value < 1500` sustained 30 s | Critical | Teams + Email |
| Truck Health Critical | `EquipmentHealthScores` | `HealthScore < 40` | Warning | Teams |
| Conveyor Stoppage | `ProductionMetrics` | `SensorType == "belt_speed_m_s" and Value == 0` sustained 60 s | Warning | Teams |

---

## 5. Deployment Sequence

1. **Create Fabric Workspace** — `MiningRTI-Demo`
2. **Create Eventhouse** — `MiningRTI` with database `MiningOps`
3. **Run KQL schema scripts** — Tables, mappings, functions, update policies
4. **Load reference data** — `EquipmentRegistry`, `AlertThresholds`
5. **Create Eventstream** — Connect custom endpoint → `SensorReadings`
6. **Create Real-Time Dashboard** — Add pages & tiles with KQL queries
7. **Create Data Activator** — Define alert rules from Eventstream/KQL
8. **Run Python simulator** — Start streaming data
9. **Trigger demo scenarios** — Inject anomalies via simulator flags
