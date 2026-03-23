# Fabric Real-Time Intelligence — Mining Operations Tutorial

> **Based on:** [github.com/wesback/miningdemo](https://github.com/wesback/miningdemo)

---

## Scenario

You are a **mining operations engineer** at a fictional Pilbara (Western Australia) iron ore mine.
The operation runs 24/7 across three zones — **Zone-A, Zone-B, Zone-C** — with a fleet of:

| Equipment | IDs | What we monitor |
|---|---|---|
| 5 Haul Trucks | HT-001 → HT-005 | Engine temp, oil pressure, vibration, load, cycle state |
| 3 Conveyors | CV-001 → CV-003 | Belt speed, belt load, vibration |
| 4 Drill Rigs | DR-001 → DR-004 | Hydraulic pressure, vibration, engine temp |
| 3 Environmental Sensors | ES-001 → ES-003 | CO (ppm), CH₄ (%LEL), ambient temp, humidity, dust |

Every sensor publishes a **JSON event every 10 seconds** to an Event Hub / Eventstream.
The goal is: ingest → store → query → visualise → alert — entirely in Microsoft Fabric.

---

## Architecture

```
Python Simulator (or real IoT hardware)
         │  JSON events every 10s
         ▼
┌─────────────────────────┐
│  Eventstream             │   MiningSensorStream
│  (source: custom EP)     │   No-code pipeline
│  (dest:   KQL Database)  │
└─────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  Eventhouse: MiningRTI   /   KQL Database: MiningOps        │
│                                                              │
│  SensorReadings  (raw landing table, JSON mapping)          │
│       │                                                      │
│       ├─→ EquipmentTelemetry   (update policy, fan-out)     │
│       ├─→ EnvironmentalReadings (update policy)             │
│       └─→ ProductionMetrics    (update policy)              │
│                                                              │
│  EquipmentRegistry   AlertThresholds   SafetyIncidents      │
│  (reference tables seeded once)                             │
└─────────────────────────────────────────────────────────────┘
         │
         ├──────────────────────────────────┐
         ▼                                  ▼
┌─────────────────────┐         ┌──────────────────────────┐
│  Real-Time Dashboard │         │  Data Activator (Reflex) │
│  4 pages             │         │  7 alert rules           │
│  Auto-refresh 15-60s │         │  Teams + Email actions   │
└─────────────────────┘         └──────────────────────────┘
```

---

## Prerequisites

- A Fabric workspace with **F2 capacity or Trial** (F4 recommended for production Eventstreams)
- Python 3.10+ on your local machine
- The repo cloned: `git clone https://github.com/wesback/miningdemo`
- Fabric admin settings enabled: **Maps** and **Anomaly Detector** (admin portal → tenant settings)

---

## Step 1 — Create the Workspace and Eventhouse

1. Open [app.fabric.microsoft.com](https://app.fabric.microsoft.com) and create a new workspace
   named **MiningRTI-Demo** with your Fabric capacity assigned.
2. Inside the workspace: **+ New → Eventhouse** → name it **MiningRTI**.
3. A KQL database named `MiningRTI` is created automatically — rename it to **MiningOps**.
4. Note the **Query URI** shown on the database overview page (you'll need it for the Eventstream
   destination).

> **Quick deployment option:** The repo includes `deploy.py` — a single script that creates all
> Fabric items via the REST API. Run it if you want to skip the manual steps:
>
> ```bash
> pip install azure-identity requests
> python3 deploy.py --workspace-id <your-workspace-guid>
> ```
>
> After it completes, you still need to wire up the Eventstream source and destination in the
> portal UI.

---

## Step 2 — Set Up the KQL Schema

Open `kql/01-schema-setup.kql` in your editor and run each command block **one at a time** in a
KQL Queryset connected to `MiningOps`.

> **Important:** KQL Querysets execute one control command per run. Select from the `.` to the end
> of the block, then click **Run**.

### Raw landing table

Every sensor event arrives here first:

```kql
.create table SensorReadings (
    EventId: string, EquipmentId: string, EquipmentType: string,
    SensorType: string, Value: real, Unit: string,
    Zone: string, Latitude: real, Longitude: real,
    Timestamp: datetime, Quality: string, Shift: string
)
```

### JSON ingestion mapping

Tells Fabric how to parse incoming Event Hub messages:

```kql
.create-or-alter table SensorReadings ingestion json mapping "SensorReadingsJsonMapping"
'[
  {"column":"EventId",       "path":"$.EventId",       "datatype":"string"},
  {"column":"EquipmentId",   "path":"$.EquipmentId",   "datatype":"string"},
  {"column":"SensorType",    "path":"$.SensorType",    "datatype":"string"},
  {"column":"Value",         "path":"$.Value",         "datatype":"real"},
  {"column":"Timestamp",     "path":"$.Timestamp",     "datatype":"datetime"}
]'
```

### Three materialised tables (update policy fan-out)

| Table | Filter logic | Data it holds |
|---|---|---|
| `EquipmentTelemetry` | `EquipmentType in ("haul_truck","conveyor","drill")` | Vibration, temp, pressure |
| `EnvironmentalReadings` | `EquipmentType == "environmental_sensor"` | CO, CH₄, temperature, dust |
| `ProductionMetrics` | `SensorType in ("load_tonnes","belt_load_kg_m","belt_speed_m_s","cycle_state")` | Tonnage, throughput |

The update policy pattern — data lands in `SensorReadings` once; Fabric automatically routes
copies to the right table with zero code:

```kql
// Function that defines the filter
.create-or-alter function EquipmentTelemetryFilter() {
    SensorReadings
    | where EquipmentType in ("haul_truck", "conveyor", "drill")
    | where SensorType !in ("load_tonnes", "belt_load_kg_m", "belt_speed_m_s", "cycle_state")
}

// Policy that attaches the function to the target table
.alter table EquipmentTelemetry policy update
'[{"IsEnabled":true, "Source":"SensorReadings",
   "Query":"EquipmentTelemetryFilter()", "IsTransactional":true}]'
```

### Reference tables (seeded once from `kql/02-reference-data.kql`)

```kql
.create table EquipmentRegistry (
    EquipmentId: string, EquipmentType: string,
    Make: string, Model: string, YearCommissioned: int,
    Zone: string, Status: string
)

.create table AlertThresholds (
    SensorType: string,
    WarningLow: real, WarningHigh: real,
    CriticalLow: real, CriticalHigh: real,
    Unit: string, Description: string
)

.create table SafetyIncidents (
    IncidentId: string, Timestamp: datetime,
    Zone: string, Severity: string,
    Description: string, EquipmentId: string
)
```

### Enable streaming ingestion

So data is available in queries within seconds (not minutes):

```kql
.alter table SensorReadings      policy streamingingestion '{"IsEnabled": true}'
.alter table EquipmentTelemetry  policy streamingingestion '{"IsEnabled": true}'
.alter table EnvironmentalReadings policy streamingingestion '{"IsEnabled": true}'
.alter table ProductionMetrics   policy streamingingestion '{"IsEnabled": true}'
```

---

## Step 3 — Create the Eventstream

1. **+ New → Eventstream** → name it **MiningSensorStream**. Enable **Enhanced capabilities**.

2. **Add Source:**
   - Choose **Custom endpoint** (provisions an Event Hub-compatible endpoint inside Fabric — no
     separate Azure subscription needed)
   - Copy the **connection string** and **Event Hub name** for the simulator

3. **Add Destination:**
   - Type: **Eventhouse**
   - Database: `MiningOps`
   - Table: `SensorReadings`
   - Data format: `JSON`
   - Ingestion mapping: `SensorReadingsJsonMapping`
   - Ingestion mode: **Direct ingestion**

4. Click **Activate** to start the pipeline.

> No transformations are needed in the Eventstream itself — the update policies in the Eventhouse
> handle all fan-out and routing automatically.

---

## Step 4 — Start the Simulator

The simulator (`simulator/simulator.py`) generates realistic sensor events for all 15 devices in
the fleet.

### Install and test locally

```bash
cd simulator/
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Dry run — prints events to console without sending
python3 simulator.py --console --max-iterations 5
```

Sample output event:

```json
{
  "EventId": "a3f1b2c4-...",
  "EquipmentId": "HT-002",
  "EquipmentType": "haul_truck",
  "SensorType": "engine_temp_c",
  "Value": 87.4,
  "Unit": "°C",
  "Zone": "Zone-A",
  "Latitude": -23.7011,
  "Longitude": 119.8045,
  "Timestamp": "2026-03-23T09:12:05Z",
  "Quality": "good",
  "Shift": "day"
}
```

### Stream live to your Eventstream

Both values come from the **Custom endpoint source** in your Eventstream. Open the source in the
Fabric portal and copy the connection string and the Event Hub name — the name is a system-assigned
**GUID** (e.g. `es_xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`), not a human-readable label.

```bash
export EVENT_HUB_CONNECTION_STRING="Endpoint=sb://..."   # from Eventstream → source → connection string
export EVENT_HUB_NAME="es_xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"  # GUID from Eventstream → source → Event Hub name

python3 simulator.py --interval 10   # one batch every 10 seconds
```

### Verify data is flowing

In your KQL Queryset, run:

```kql
SensorReadings | take 10
```

After 30–60 seconds, rows should appear. Check the materialised tables too:

```kql
EquipmentTelemetry     | count
EnvironmentalReadings  | count
ProductionMetrics      | count
```

### Load 31 days of historical data (recommended)

For a richer demo with trends, degradation patterns, and seeded anomaly events:

```bash
python3 generate_history.py             # 5.4M rows, ~632 MB
python3 generate_history.py --days 7    # lighter option: ~146 MB
python3 generate_history.py --interval 60  # 1-min intervals: ~316 MB
```

This generates `historical_data/SensorReadings.csv` and `SafetyIncidents.csv`
(17 pre-correlated incidents). Ingest them via KQL:

```kql
// From a Fabric Lakehouse (upload CSVs via drag & drop first)
.ingest into table SensorReadings
    (h@'abfss://<workspace>@onelake.dfs.fabric.microsoft.com/<lakehouse>/Files/SensorReadings.csv')
with (format='csv', ignoreFirstRecord=true)

.ingest into table SafetyIncidents
    (h@'abfss://.../<lakehouse>/Files/SafetyIncidents.csv')
with (format='csv', ignoreFirstRecord=true)
```

The historical data includes:

- Diurnal temperature cycles (hotter midday, cooler at night)
- Night-shift reduced production (85% of day shift)
- Weekend production dips (60%)
- Gradual degradation trends on HT-003, HT-004, CV-001, DR-001
- 17 anomaly events (gas spikes, pressure drops, conveyor stoppages)

---

## Step 5 — Query the Data with KQL

Open a KQL Queryset connected to `MiningOps`. All named queries below are defined in
`kql/03-queries.kql`.

### Equipment status summary

```kql
let cutoff = ago(2m);
EquipmentTelemetry
| where Timestamp > cutoff and Quality == "good"
| summarize arg_max(Timestamp, Value, SensorType) by EquipmentId
| extend Status = case(
    SensorType == "engine_temp_c"  and Value > 105, "Fault",
    SensorType == "engine_temp_c"  and Value < 30,  "Idle",
    SensorType == "belt_speed_m_s" and Value == 0,  "Idle",
    SensorType == "hydraulic_psi"  and Value < 500, "Idle",
    "Running")
| summarize Count = count() by Status
```

### Vibration anomaly detection (3σ rule)

```kql
let sigma_threshold = 3.0;
EquipmentTelemetry
| where SensorType == "vibration_mm_s" and Timestamp > ago(1h) and Quality == "good"
| summarize Avg = avg(Value), Std = stdev(Value), Latest = arg_max(Timestamp, Value)
    by EquipmentId
| where Latest_Value > (Avg + sigma_threshold * Std)
| project EquipmentId,
    LatestReading  = round(Latest_Value, 2),
    Avg            = round(Avg, 2),
    UpperBound     = round(Avg + sigma_threshold * Std, 2),
    DeviationSigma = round((Latest_Value - Avg) / Std, 1)
```

### Gas threshold breaches (joined against reference table)

```kql
let cutoff = ago(15m);
EnvironmentalReadings
| where Timestamp > cutoff and Quality == "good"
| join kind=inner (AlertThresholds) on SensorType
| where Value > CriticalHigh or Value < CriticalLow
| project Timestamp, Zone, SensorType, Value, Unit,
    Threshold = iff(Value > CriticalHigh,
                    strcat("> ", tostring(CriticalHigh)),
                    strcat("< ", tostring(CriticalLow))),
    Severity = "Critical"
| order by Timestamp desc
```

### Shift tonnage progress

```kql
let shift_start  = bin(now(), 8h);
let shift_target = 5000.0;
ProductionMetrics
| where SensorType == "load_tonnes" and Timestamp > shift_start and Quality == "good"
| summarize TotalTonnes = round(sum(Value), 0) by EquipmentType
| extend Target      = shift_target
| extend PctOfTarget = round(TotalTonnes / Target * 100, 1)
```

### Equipment health scoring (composite score)

```kql
let temp_weight = 0.35;
let oil_weight  = 0.35;
let age_weight  = 0.30;

let TempScores = EquipmentTelemetry
    | where SensorType == "engine_temp_c" and EquipmentType == "haul_truck"
        and Timestamp > ago(4h) and Quality == "good"
    | summarize AvgTemp = avg(Value) by EquipmentId
    | extend TempScore = max_of(0.0, min_of(100.0, (110.0 - AvgTemp) / 0.3));

let OilScores = EquipmentTelemetry
    | where SensorType == "oil_pressure_kpa" and EquipmentType == "haul_truck"
        and Timestamp > ago(4h) and Quality == "good"
    | summarize AvgOil = avg(Value), StdOil = stdev(Value) by EquipmentId
    | extend OilScore = max_of(0.0, min_of(100.0, 100.0 - (StdOil / AvgOil) * 200.0));

let AgeScores = EquipmentRegistry
    | where EquipmentType == "haul_truck"
    | extend YearsOld = 2026 - YearCommissioned
    | extend AgeScore = max_of(0.0, 100.0 - (YearsOld * 10.0));

TempScores
| join kind=leftouter OilScores on EquipmentId
| join kind=leftouter AgeScores on EquipmentId
| extend HealthScore = round(
    (coalesce(TempScore, 50) * temp_weight) +
    (coalesce(OilScore,  50) * oil_weight)  +
    (coalesce(AgeScore,  50) * age_weight), 0)
| extend Status = case(HealthScore < 40, "Critical",
                       HealthScore < 70, "Warning",
                       "Healthy")
| project EquipmentId, HealthScore, Status
| order by HealthScore asc
```

### 7-day production trend

```kql
ProductionMetrics
| where SensorType == "load_tonnes" and Timestamp > ago(7d) and Quality == "good"
| summarize DailyTonnes = round(sum(Value), 0) by Day = startofday(Timestamp)
| order by Day asc
| render timechart
```

---

## Step 6 — Build the Real-Time Dashboard (4 pages)

**+ New → Real-Time Dashboard** → name it **Mining Operations**. Connect `MiningOps` as a data
source. Set base auto-refresh to **30 seconds**.

Full tile configuration is in `dashboard/dashboard-config.md`.

---

### Page 1: Operations Overview

| # | Tile | Visual | Refresh |
|---|---|---|---|
| 1.1 | Active Equipment Count | Multi-stat card (Running / Idle / Fault) | 30 s |
| 1.2 | Shift Tonnage vs Target | Grouped bar chart | 60 s |
| 1.3 | Equipment Status Map | Map bubble (GA — FabCon March 2026) | 30 s |
| 1.4 | Active Alerts | Table (red rows) | 15 s |

**Tile 1.3 — Map query:**

```kql
let cutoff = ago(5m);
EquipmentTelemetry
| where Timestamp > cutoff and Quality == "good"
| summarize arg_max(Timestamp, *) by EquipmentId
| join kind=leftouter (EquipmentRegistry | project EquipmentId, Make, Model) on EquipmentId
| project EquipmentId, EquipmentType, Latitude, Longitude, Zone, Make, Model
```

Set **Latitude field** → `Latitude`, **Longitude field** → `Longitude`,
**Bubble colour** → by `EquipmentType`.
Tooltip: `EquipmentId`, `Make`, `Model`, `Zone`.

**Tile 1.4 — Active alerts query:**

```kql
let cutoff = ago(15m);
EnvironmentalReadings
| where Timestamp > cutoff and Quality == "good"
| join kind=inner (AlertThresholds) on SensorType
| where Value > CriticalHigh or Value < CriticalLow
| project Timestamp, Zone, SensorType, Value, Unit,
    Threshold = iff(Value > CriticalHigh,
                    strcat("> ", tostring(CriticalHigh)),
                    strcat("< ", tostring(CriticalLow))),
    Severity = "Critical"
| union (
    EquipmentTelemetry
    | where Timestamp > cutoff and Quality == "good"
    | where (SensorType == "hydraulic_psi" and Value < 1500)
         or (SensorType == "engine_temp_c"  and Value > 105)
    | project Timestamp, Zone, SensorType, Value,
        Unit      = iff(SensorType == "hydraulic_psi", "PSI", "°C"),
        Threshold = iff(SensorType == "hydraulic_psi", "< 1500", "> 105"),
        Severity  = "Critical"
)
| order by Timestamp desc
| take 20
```

---

### Page 2: Safety & Environment

| # | Tile | Visual | Refresh |
|---|---|---|---|
| 2.1 | Gas Levels by Zone | Multi-line chart | 15 s |
| 2.2 | Temperature Heat Map | Table with conditional formatting | 60 s |
| 2.3 | Threshold Breaches (24 h) | Table | 30 s |
| 2.4 | Safety Incident Timeline | Sorted table | 5 min |

**Tile 2.1 — Gas levels (add reference lines: CO = 35 ppm red dashed, CH₄ = 1.0% red dashed):**

```kql
EnvironmentalReadings
| where SensorType in ("co_ppm", "ch4_pct")
    and Timestamp > ago(2h) and Quality == "good"
| summarize AvgValue = round(avg(Value), 2)
    by Zone, SensorType, bin(Timestamp, 1m)
| order by Timestamp asc
```

**Tile 2.2 — Temperature heat map:**

```kql
EnvironmentalReadings
| where SensorType == "ambient_temp_c" and Timestamp > ago(5m) and Quality == "good"
| summarize AvgTemp = round(avg(Value), 1), MaxTemp = round(max(Value), 1) by Zone
| extend Status = case(MaxTemp > 35, "CRITICAL", MaxTemp > 32, "WARNING", "NORMAL")
| order by MaxTemp desc
```

Conditional formatting: `CRITICAL` → red background, `WARNING` → amber, `NORMAL` → green.

---

### Page 3: Equipment Health

| # | Tile | Visual | Refresh |
|---|---|---|---|
| 3.1 | Vibration Anomaly Trend | Scatter chart | 30 s |
| 3.2 | Drill Hydraulic Pressure | Line chart | 30 s |
| 3.3 | Equipment Health Scores | Conditional table | 4 h |
| 3.4 | Equipment Utilisation | Horizontal bar | 5 min |

**Tile 3.1 — Vibration scatter (anomalies in red):**

```kql
let sigma_threshold = 3.0;
EquipmentTelemetry
| where SensorType == "vibration_mm_s" and Timestamp > ago(4h) and Quality == "good"
| summarize AvgValue = avg(Value), StdValue = stdev(Value),
    MaxValue = max(Value) by EquipmentId, Bin = bin(Timestamp, 1m)
| extend UpperBound = AvgValue + (sigma_threshold * StdValue)
| extend IsAnomaly  = MaxValue > UpperBound
| project Bin, EquipmentId,
    MaxValue   = round(MaxValue, 2),
    UpperBound = round(UpperBound, 2),
    IsAnomaly
```

Set **Colour** → `IsAnomaly` (`true` = red, `false` = blue). Series → `EquipmentId`.

**Tile 3.2 — Hydraulic pressure (add reference line: 1,500 PSI red dashed):**

```kql
EquipmentTelemetry
| where SensorType == "hydraulic_psi" and EquipmentType == "drill"
    and Timestamp > ago(1h) and Quality == "good"
| summarize AvgPressure = round(avg(Value), 0) by EquipmentId, bin(Timestamp, 30s)
| order by Timestamp asc
```

---

### Page 4: Production

| # | Tile | Visual | Refresh |
|---|---|---|---|
| 4.1 | Conveyor Throughput | Area chart (7-day) | 60 s |
| 4.2 | Haul Truck Cycle Times | Grouped bar by phase | 5 min |
| 4.3 | Route Efficiency | Conditional table | 5 min |
| 4.4 | 7-Day Production Trend | Line chart | 15 min |

**Tile 4.2 — Cycle time breakdown:**

```kql
ProductionMetrics
| where SensorType == "cycle_state" and EquipmentType == "haul_truck"
    and Timestamp > ago(24h) and Quality == "good"
| extend CyclePhase = case(
    Value == 1, "Loading",        Value == 2, "Travel-Loaded",
    Value == 3, "Dumping",        Value == 4, "Travel-Empty", "Unknown")
| where CyclePhase != "Unknown"
| summarize PhaseDuration_min =
    round(datetime_diff('second', max(Timestamp), min(Timestamp)) / 60.0, 1)
    by EquipmentId, CyclePhase, bin(Timestamp, 1h)
| summarize AvgDuration_min = round(avg(PhaseDuration_min), 1) by EquipmentId, CyclePhase
```

---

## Step 7 — Configure Data Activator Alerts

**+ New → Reflex** → name it **Mining Safety Alerts**.
Full rule definitions are in `activator/alert-rules.md`.

### Rule 1 — CO Gas Breach (Critical, per-event)

- **Source:** Eventstream → `EnvironmentalReadings`
- **Filter:** `SensorType == "co_ppm"` AND `Quality == "good"`
- **Trigger:** `Value > 35` — fires immediately per event, no aggregation
- **Cooldown:** 5 minutes
- **Actions:**
  - Teams message to `#Mining Safety Channel`:
    `"🚨 CRITICAL: CO Level Breach — Zone: {{Zone}}, Reading: {{Value}} ppm"`
  - Email to `safety-officer@` and `shift-supervisor@`

### Rule 2 — Methane Breach (Critical, per-event)

Same pattern as Rule 1. `SensorType == "ch4_pct"` with threshold `> 1.0% LEL`.

### Rule 3 — High Temperature Zone (Warning, 5-min average)

- **Trigger:** 5-minute average `ambient_temp_c > 35°C`
- **Cooldown:** 15 minutes
- **Action:** Teams message to `#Mining Ops Channel`

### Rule 4 — Vibration Anomaly (KQL-based, evaluated every minute)

Uses a KQL query as the data source for statistical conditions:

```kql
EquipmentTelemetry
| where SensorType == "vibration_mm_s" and EquipmentType == "conveyor"
    and Timestamp > ago(15m) and Quality == "good"
| summarize Avg = avg(Value), Std = stdev(Value),
    Latest = arg_max(Timestamp, Value) by EquipmentId
| where Latest_Value > (Avg + 3 * Std)
| project EquipmentId,
    LatestValue = Latest_Value,
    Avg         = round(Avg, 2),
    UpperBound  = round(Avg + 3 * Std, 2),
    Deviation   = round((Latest_Value - Avg) / Std, 1),
    Timestamp   = Latest_Timestamp
```

- **Trigger:** `row_count > 0`
- **Evaluation:** every 1 minute
- **Action:** Teams message to `#Equipment Engineering Channel` with EquipmentId, deviation in σ

### Rule 5 — Hydraulic Pressure Drop (Critical, sustained 30 s)

Fires only if pressure is **continuously** below 1,500 PSI for at least 30 seconds:

```kql
EquipmentTelemetry
| where SensorType == "hydraulic_psi" and EquipmentType == "drill"
    and Timestamp > ago(2m) and Quality == "good"
| summarize MinPressure = min(Value), BelowCount = countif(Value < 1500),
    TotalCount = count(),
    Duration_s = datetime_diff('second', max(Timestamp), min(Timestamp)) by EquipmentId
| where BelowCount == TotalCount and Duration_s >= 30
```

**Action:** Teams + Email + "Dispatch maintenance immediately".

### Rules 6 & 7

- **Rule 6 — Truck Health Critical:** fires when `HealthScore < 40` (uses the composite score
  query from Step 5).
- **Rule 7 — Conveyor Stoppage:** detects `belt_speed_m_s == 0` for 60+ continuous seconds.

---

## Step 8 — Anomaly Detection (No-Code ML)

1. Enable the **Python plugin** on your Eventhouse:
   Eventhouse → **Plugins** → enable **Python 3.11.7 DL**.
   > Allow up to 1 hour for the plugin to activate the first time.

2. Open **Real-Time Hub** → find `EquipmentTelemetry` → **Anomaly detection**.

3. Configure:
   - **Value to watch:** `Value`
   - **Group by:** `EquipmentId`
   - **Timestamp column:** `Timestamp`
   - Add a pre-filter: `SensorType == "vibration_mm_s"`

4. Click **Run analysis** — the system tests multiple algorithms and ranks them (up to 4 minutes).

5. Review recommended models, adjust sensitivity (**Low / Medium / High**), and **Publish** to
   Real-Time Hub.

6. Connect the anomaly detector to **Activator** so an alert fires whenever a new anomaly is
   detected.

For power users, the underlying KQL functions are also directly available
(`kql/04-predictive-queries.kql`):

```kql
// series_decompose_anomalies — detects spikes, dips, trend shifts
EquipmentTelemetry
| where SensorType == "vibration_mm_s" and EquipmentId == "CV-001"
    and Timestamp > ago(7d) and Quality == "good"
| make-series AvgVibration = avg(Value)
    on Timestamp from ago(7d) to now() step 1h
| extend (anomalies, score, baseline) = series_decompose_anomalies(AvgVibration, 1.5)
| mv-expand Timestamp, AvgVibration, anomalies, score, baseline
| where anomalies != 0
| project Timestamp, AvgVibration, score, baseline
| render anomalychart
```

---

## Step 9 — Demo Scenarios (Anomaly Injection)

The simulator has built-in anomaly injection to demonstrate real-time alerting.

| Scenario | Command | What happens |
|---|---|---|
| Gas breach | `python3 simulator.py --inject-anomaly gas` | ES-001 CO spikes to ~45 ppm; ES-002 CH₄ to ~1.5% LEL |
| Vibration spike | `python3 simulator.py --inject-anomaly vibration` | CV bearing vibration → ~15 mm/s |
| Hydraulic drop | `python3 simulator.py --inject-anomaly hydraulic` | DR-001 pressure → ~1,350 PSI |
| Engine overheat | `python3 simulator.py --inject-anomaly overheat` | HT truck temp → ~112°C |
| Conveyor stop | `python3 simulator.py --inject-anomaly conveyor_stop` | Belt speed → 0 m/s |
| All at once | `python3 simulator.py --inject-anomaly all` | Full multi-alert scenario |

### Recommended live demo flow

1. **Start normal:**
   ```bash
   python3 simulator.py --interval 10
   ```
   Show the dashboard in a healthy green state.

2. **Inject gas:**
   ```bash
   python3 simulator.py --interval 10 --inject-anomaly gas
   ```
   Safety page lights up red — Activator fires a Teams alert within ~15 seconds.

3. **Inject vibration:**
   ```bash
   python3 simulator.py --interval 10 --inject-anomaly vibration
   ```
   Equipment Health scatter shows red dots — vibration alert fires.

4. **Inject hydraulic:**
   ```bash
   python3 simulator.py --interval 10 --inject-anomaly hydraulic
   ```
   Drill pressure line drops below the reference line — critical alert fires.

5. **Inject all:**
   ```bash
   python3 simulator.py --interval 10 --inject-anomaly all
   ```
   Demonstrate multi-alert scenario and dashboard under real incident conditions.

6. **Return to normal:**
   ```bash
   python3 simulator.py --interval 10
   ```
   Alerts auto-resolve on the dashboard.

---

## What This Demo Covers End-to-End

| RTI Capability | Where it appears in this demo |
|---|---|
| Eventstream (custom endpoint source) | `MiningSensorStream` receiving from simulator |
| KQL Database schema + JSON mapping | `SensorReadings` table, `SensorReadingsJsonMapping` |
| Update policies (fan-out pattern) | Raw → `EquipmentTelemetry`, `EnvironmentalReadings`, `ProductionMetrics` |
| Streaming ingestion | Sub-second data availability in queries |
| Reference table joins | `AlertThresholds`, `EquipmentRegistry` |
| KQL time-series analysis | `make-series`, `summarize`, `arg_max`, windowed aggregations |
| Statistical anomaly detection | 3σ vibration rule, `series_decompose_anomalies` |
| Real-Time Dashboard (4 pages) | Operations, Safety, Equipment Health, Production |
| Map visual (GA — March 2026) | Equipment position map on Page 1 |
| Activator — threshold alerts | CO, CH₄, temperature |
| Activator — KQL-based alerts | Vibration anomaly, hydraulic pressure, health score, conveyor stop |
| Historical data ingestion | 31-day CSV load via `.ingest` |
| Automated deployment | `deploy.py` via Fabric REST API |

---

## Repository File Reference

| File | Purpose |
|---|---|
| `deploy.py` | Automated Fabric deployment via REST API |
| `docs/architecture.md` | Architecture design document |
| `docs/user-stories.md` | User stories by persona |
| `kql/01-schema-setup.kql` | Table definitions, mappings, update policies |
| `kql/02-reference-data.kql` | Seed data (equipment registry, thresholds) |
| `kql/03-queries.kql` | Production KQL queries for all user stories |
| `kql/04-predictive-queries.kql` | ML forecasting & anomaly scoring queries |
| `dashboard/dashboard-config.md` | Tile layout and backing queries per visual |
| `activator/alert-rules.md` | Data Activator alert rule definitions |
| `simulator/simulator.py` | Live streaming data simulator |
| `simulator/generate_history.py` | 31-day historical data generator |
| `simulator/requirements.txt` | Python dependencies |
| `simulator/config.sample.yaml` | Sample configuration |

---

*Tutorial based on [github.com/wesback/miningdemo](https://github.com/wesback/miningdemo) —
Microsoft Fabric Real-Time Intelligence, March 2026.*
