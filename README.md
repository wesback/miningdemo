# Mining Real-Time Intelligence Demo

End-to-end demo of **Microsoft Fabric Real-Time Intelligence** for a mining operation — streaming equipment telemetry, environmental monitoring, production tracking, and safety alerting.

---

## Repository Structure

```
miningdemo/
├── README.md                          ← You are here
├── deploy.py                          ← Automated Fabric deployment script
├── get-docker.sh                      ← [DEPRECATED] Docker install script (not required)
├── docs/
│   ├── user-stories.md                ← Phase 1: User stories by persona
│   └── architecture.md                ← Phase 2: Architecture design
├── kql/
│   ├── 01-schema-setup.kql            ← Table definitions, mappings, update policies
│   ├── 02-reference-data.kql          ← Seed data (equipment registry, thresholds)
│   ├── 03-queries.kql                 ← Production KQL queries for all user stories
│   └── 04-predictive-queries.kql      ← ML forecasting & anomaly scoring queries
├── dashboard/
│   └── dashboard-config.md            ← Tile layout and backing queries per visual
├── activator/
│   ├── alert-rules.md                 ← Data Activator alert rule definitions
│   └── ingest_history.py              ← Historical data ingestion (single CSV)
└── simulator/
    ├── simulator.py                   ← Live streaming data simulator
    ├── deploy_history.py              ← Automated pipeline: generate + ingest historical data
    ├── generate_history.py            ← 31-day historical data generator (CSV output)
    ├── requirements.txt               ← Python dependencies
    └── config.sample.yaml             ← Sample configuration
```

---

## Prerequisites

| Component | Requirement |
|-----------|------------|
| **Microsoft Fabric** | Fabric capacity (F2+ or Trial) with a workspace |
| **Python** | 3.10+ |
| **Azure Event Hub** | Namespace + Event Hub (or use Fabric Eventstream custom endpoint) |
| **azure-eventhub SDK** | `pip install azure-eventhub` |
| **Service Principal** | Required for CI/CD — see [CI/CD Setup Guide](docs/CICD_SETUP.md) |

### Fabric Items You Will Create

1. **Eventhouse** — `MiningRTI`
2. **KQL Database** — `MiningOps` (inside the Eventhouse)
3. **Eventstream** — `MiningSensorStream`
4. **Real-Time Dashboard** — `Mining Operations`
5. **Data Activator (Reflex)** — `Mining Safety Alerts`

---

## Deployment Guide

### Option A — Automated (Fabric REST API)

A single script deploys all Fabric items via the REST API:

```bash
cd /path/to/miningdemo
pip install azure-identity requests

# Interactive browser auth (simplest)
python deploy.py --workspace-id <your-workspace-guid>

# Service principal auth (for CI/CD)
python deploy.py \
  --workspace-id  xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \
  --tenant-id     xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \
  --client-id     xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \
  --client-secret <secret>
```

This creates: **Eventhouse → KQL Database → tables/policies/seed data → Eventstream → KQL Queryset → Real-Time Dashboard**.

After deployment, open the Eventstream in the Fabric portal to configure its **custom endpoint source** and **KQL Database destination** (the REST API creates the item but source/destination wiring requires the UI).

### Option B — Manual (Step-by-Step)

### Step 1 — Create Fabric Workspace

1. Open [app.fabric.microsoft.com](https://app.fabric.microsoft.com).
2. Create a new workspace: **`MiningRTI-Demo`**.
3. Assign a Fabric capacity (F2 or Trial).

### Step 2 — Create the Eventhouse and KQL Database

1. In the workspace, click **+ New → Eventhouse**.
2. Name it **`MiningRTI`**. A KQL database named `MiningRTI` is created automatically — rename it to **`MiningOps`**.
3. Open the database and note the **Query URI** (you'll need this for Eventstream).

### Step 3 — Run KQL Schema Scripts

1. In the workspace, click **+ New → KQL Queryset**.
2. Name it **`MiningOps-Setup`** and connect it to the `MiningOps` database.
3. Open `kql/01-schema-setup.kql` and execute **each command block** sequentially:
   - Creates landing table `SensorReadings` with JSON ingestion mapping
   - Creates materialised tables: `EquipmentTelemetry`, `EnvironmentalReadings`, `ProductionMetrics`
   - Creates filter functions and attaches update policies
   - Creates reference tables: `EquipmentRegistry`, `AlertThresholds`, `SafetyIncidents`
   - Enables streaming ingestion and sets retention/caching policies

4. Open `kql/02-reference-data.kql` and run it to seed the reference tables.

> **Tip:** Run each `.create` / `.alter` command individually — KQL Querysets execute one control command at a time.

### Step 4 — Create the Eventstream

1. In the workspace, click **+ New → Eventstream**.
2. Name it **`MiningSensorStream`**.
3. **Add Source:**
   - Type: **Custom endpoint** (creates an Event Hub-compatible endpoint)
   - Or: **Azure Event Hubs** (if using an existing namespace)
   - Note the **connection string** and **Event Hub name** for the simulator.
4. **Add Destination:**
   - Type: **KQL Database**
   - Database: `MiningOps`
   - Table: `SensorReadings`
   - Input data format: **JSON**
   - Ingestion mapping: `SensorReadingsJsonMapping`
5. Activate the Eventstream.

### Step 5 — Start the Simulator

```bash
cd simulator/

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate      # Linux / macOS
# .venv\Scripts\activate       # Windows PowerShell

# Install dependencies
pip install -r requirements.txt

# Option A: Console mode (local testing — prints events to stdout)
python simulator.py --console --max-iterations 5

# Option B: Stream to Event Hub / Eventstream
export EVENT_HUB_CONNECTION_STRING="Endpoint=sb://..."
export EVENT_HUB_NAME="mining-sensor-stream"
python simulator.py --interval 10
```

Verify data is flowing by running in the KQL Queryset:
```kql
SensorReadings | take 10
```

### Step 5b — Load Historical Data (Optional but Recommended)

For a richer demo with 31 days of trends, anomalies, and degradation patterns:

```bash
cd simulator/

# Generate 31 days of historical data (5.4M rows, ~632 MB)
python generate_history.py

# Smaller options:
python generate_history.py --days 7             # 7 days (~146 MB)
python generate_history.py --interval 60        # 1-min intervals (~316 MB)
```

This creates:
- `simulator/historical_data/SensorReadings.csv` — All sensor readings
- `simulator/historical_data/SafetyIncidents.csv` — 17 correlated safety incidents

**To ingest into your KQL database:**

#### Option A — Automated Python Script (Recommended)

```bash
cd activator/

# Install dependencies
pip install azure-identity azure-kusto-data azure-kusto-ingest

# Ingest SensorReadings (interactive auth)
python ingest_history.py \
  --csv ../simulator/historical_data/SensorReadings.csv \
  --cluster https://<your-cluster>.kusto.fabric.microsoft.com \
  --database MiningOps \
  --table SensorReadings

# Ingest SafetyIncidents
python ingest_history.py \
  --csv ../simulator/historical_data/SafetyIncidents.csv \
  --cluster https://<your-cluster>.kusto.fabric.microsoft.com \
  --database MiningOps \
  --table SafetyIncidents

# For service principal auth (CI/CD):
python ingest_history.py \
  --csv ../simulator/historical_data/SensorReadings.csv \
  --cluster https://<cluster>.kusto.fabric.microsoft.com \
  --database MiningOps \
  --table SensorReadings \
  --tenant-id <GUID> --client-id <GUID> --client-secret <SECRET>
```

#### Option B — Manual Upload via KQL Queryset

1. Upload the CSVs to a **Fabric Lakehouse** (drag & drop into the Files section) or to **Azure Blob Storage**.

2. Run in a KQL Queryset:
```kql
// From Lakehouse (OneLake path)
.ingest into table SensorReadings (
  h@'abfss://<workspace>@onelake.dfs.fabric.microsoft.com/<lakehouse>/Files/SensorReadings.csv'
) with (format='csv', ignoreFirstRecord=true)

// Or from Azure Blob Storage (with SAS token)
.ingest into table SensorReadings (
  h@'https://<account>.blob.core.windows.net/<container>/SensorReadings.csv?<SAS>'
) with (format='csv', ignoreFirstRecord=true)

// Load incidents too
.ingest into table SafetyIncidents (
  h@'<same-path>/SafetyIncidents.csv'
) with (format='csv', ignoreFirstRecord=true)
```

**What the historical data includes:**
- 🌡️ Diurnal temperature cycles (hotter midday, cooler at night)
- 🌙 Night-shift reduced production (85% of day shift)
- 📅 Weekend production dips (60%)
- 📈 Gradual degradation trends on HT-003, HT-004, CV-001, DR-001
- ⚠️ 17 anomaly events (gas spikes, pressure drops, conveyor stoppages)

### Step 6 — Build the Real-Time Dashboard

1. In the workspace, click **+ New → Real-Time Dashboard**.
2. Name it **`Mining Operations`**.
3. Connect to the `MiningOps` database.
4. Create 4 pages following the layout in `dashboard/dashboard-config.md`:
   - **Operations Overview** — stat cards, tonnage bar chart, map, active alerts
   - **Safety & Environment** — gas levels, temperature heat map, breaches table
   - **Equipment Health** — vibration scatter, hydraulic trend, health scores, utilisation
   - **Production** — conveyor throughput, cycle times, route efficiency, 7-day trend
5. For each tile, paste the KQL query from `dashboard/dashboard-config.md` and configure the visual type and auto-refresh interval as documented.

### Step 7 — Configure Data Activator Alerts

1. In the workspace, click **+ New → Reflex** (Data Activator).
2. Name it **`Mining Safety Alerts`**.
3. **Connect a data source:**
   - From the Eventstream (for per-event triggers like gas breach)
   - Or from the KQL Database (for query-based triggers like vibration anomaly)
4. Create triggers following `activator/alert-rules.md`:
   - **Gas Breach — CO** (Critical) → Teams + Email
   - **Gas Breach — CH₄** (Critical) → Teams + Email
   - **High Temperature** (Warning) → Teams
   - **Vibration Anomaly** (Warning) → Teams + Email
   - **Hydraulic Pressure Low** (Critical) → Teams + Email
   - **Truck Health Critical** (Warning) → Teams
   - **Conveyor Stoppage** (Warning) → Teams
5. Activate each trigger.

---

### CI/CD Setup

For automated deployment via GitHub Actions (including service principal setup, GitHub Secrets configuration, and workflow triggers), see the **[CI/CD Setup Guide](docs/CICD_SETUP.md)**.

The CI/CD pipeline deploys all Fabric resources on push to `main` or via manual trigger, with optional historical data generation.

---

## Demo Scenarios

The simulator supports **anomaly injection** to trigger alerts and demonstrate dashboard behaviour:

| Scenario | Command | What Happens |
|----------|---------|-------------|
| **Gas breach** | `--inject-anomaly gas` | CO spikes to ~45 ppm (ES-001), CH₄ to ~1.5% (ES-002) |
| **Vibration** | `--inject-anomaly vibration` | Conveyor bearing vibration spikes to ~15 mm/s |
| **Hydraulic drop** | `--inject-anomaly hydraulic` | Drill pressure drops to ~1350 PSI |
| **Engine overheat** | `--inject-anomaly overheat` | Truck engine temp rises to ~112°C |
| **Conveyor stop** | `--inject-anomaly conveyor_stop` | Belt speed drops to 0 m/s |
| **All at once** | `--inject-anomaly all` | All anomaly scenarios simultaneously |

### Recommended Demo Flow

1. **Start normal:** `python simulator.py --interval 10` — show live dashboard with green/healthy status.
2. **Inject gas anomaly:** Stop and restart with `--inject-anomaly gas` — watch the Safety page light up, Data Activator alerts fire.
3. **Inject vibration:** `--inject-anomaly vibration` — show the anomaly scatter chart on Equipment Health page.
4. **Inject all:** `--inject-anomaly all` — demonstrate multi-alert scenario and shift handover summary.
5. **Return to normal:** Restart without anomaly flag — show alerts auto-resolve.

---

## Key KQL Queries Reference

| Query Name | User Story | File Location |
|-----------|------------|---------------|
| `EquipmentStatusSummary` | US-1.1 | `kql/03-queries.kql` |
| `VibrationAnomalies` | US-1.2 | `kql/03-queries.kql` |
| `HydraulicPressureDrops` | US-1.3 | `kql/03-queries.kql` |
| `EquipmentHealthScores` | US-1.4 | `kql/03-queries.kql` |
| `GasThresholdBreaches` | US-2.1 | `kql/03-queries.kql` |
| `ZoneTemperatures` | US-2.2 | `kql/03-queries.kql` |
| `IncidentEnvironmentalCorrelation` | US-2.3 | `kql/03-queries.kql` |
| `ShiftTonnageProgress` | US-3.1 | `kql/03-queries.kql` |
| `ConveyorThroughput` | US-3.2 | `kql/03-queries.kql` |
| `TruckCycleTimes` | US-3.3 | `kql/03-queries.kql` |
| `EquipmentUtilisation` | US-4.1 | `kql/03-queries.kql` |
| `ShiftHandoverSummary` | US-4.2 | `kql/03-queries.kql` |
| `ActiveAlerts` | US-4.3 | `kql/03-queries.kql` |

---

## Customisation

### Adding Equipment
Edit `DEFAULT_FLEET` in `simulator/simulator.py` to add or remove assets. Each `Equipment` object needs an ID, type, zone, and list of sensor profiles.

### Adjusting Thresholds
Modify the `AlertThresholds` table in KQL (`kql/02-reference-data.kql`) or update directly:
```kql
.set-or-replace AlertThresholds <|
    AlertThresholds
    | where SensorType != "co_ppm"
    | union (print SensorType="co_ppm", WarningLow=0, WarningHigh=20,
                   CriticalLow=0, CriticalHigh=30, Unit="ppm",
                   Description="Tightened CO limit")
```

### Changing Sensor Characteristics
Edit the `SensorProfile` dataclasses in `simulator.py` to adjust mean, standard deviation, anomaly injection values, and drift rates.

---

## Troubleshooting

| Issue | Resolution |
|-------|-----------|
| No data in KQL tables | Verify Eventstream is active and destination mapping uses `SensorReadingsJsonMapping` |
| Update policy tables empty | Run `.show table EquipmentTelemetry policy update` to verify the policy is enabled |
| Simulator connection error | Check `EVENT_HUB_CONNECTION_STRING` includes the `EntityPath` or use `--eventhub-name` |
| Dashboard tiles show "No data" | Ensure auto-refresh is enabled and time range is set to "Last 1 hour" or wider |
| Data Activator not firing | Verify trigger is activated (not in draft) and cooldown period has elapsed |

---

## License

This is a demo project for educational and demonstration purposes.
