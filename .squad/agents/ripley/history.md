# Project Context

- **Owner:** Wesley Backelant
- **Project:** Mining Real-Time Intelligence Demo — Microsoft Fabric Real-Time Intelligence for mining operations monitoring
- **Stack:** Python (deploy.py, simulator), KQL, Microsoft Fabric (Eventhouse, Eventstream, Real-Time Dashboards, Data Activator), Azure Event Hubs, Fabric REST APIs
- **Created:** 2026-03-20

## Learnings

### 2026-03-20 — Comprehensive Codebase Review Completed

**Architecture:**
- Clean 3-tier design: Data generation (Python simulator) → Ingestion (Eventstream) → Analytics (KQL/Eventhouse)
- Landing table pattern with update policies for materialized views is well-designed
- 15 equipment assets (5 haul trucks, 3 conveyors, 4 drills, 3 environmental sensors) across 3 zones
- Event schema consistent across simulator, KQL schema, and dashboard queries
- Anomaly injection system supports 5 predefined scenarios (gas, vibration, hydraulic, overheat, conveyor_stop, all)

**Key File Paths:**
- Deploy script: `/deploy.py` (596 lines) — full Fabric REST API automation
- Live simulator: `/simulator/simulator.py` (579 lines) — streaming event generation
- Historical generator: `/simulator/generate_history.py` (384 lines) — 31-day bulk data
- Schema: `/kql/01-schema-setup.kql`, `/kql/02-reference-data.kql`
- Queries: `/kql/03-queries.kql` (21 named queries), `/kql/04-predictive-queries.kql` (ML forecasting)
- Dashboard: `/dashboard/dashboard-config.md` (16 tiles across 4 pages)
- Alerts: `/activator/alert-rules.md` (7 Data Activator rules)

**Integration Points Verified:**
- Equipment IDs consistent: HT-001..005, CV-001..003, DR-001..004, ES-001..003
- Alert thresholds match: CO=35ppm, CH₄=1.0%, hydraulic=1500PSI, temp=105°C, vibration=11.2mm/s
- SensorReadings table schema matches simulator JSON output exactly (12 fields)
- Dashboard queries reference correct table names and materialized views
- Historical data generator uses same equipment fleet and sensor profiles as live simulator

**Quality Assessment:**
- Python code: No syntax errors, clean imports, good error handling patterns
- KQL: Well-structured with clear comments, named queries for reusability
- Documentation: Comprehensive README with deployment options, troubleshooting, customization guide
- No TODO/FIXME comments found (clean codebase)

**Known Patterns:**
- Shift logic: day (06:00-14:00), afternoon (14:00-22:00), night (22:00-06:00 UTC)
- Update policies use filter functions for table fan-out
- Simulator supports both Event Hub streaming and console mode for testing
- Historical data includes 17 pre-planned anomaly events with incidents table correlation
