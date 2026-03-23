# Copilot Instructions for Mining Real-Time Intelligence Demo

This repository is a Microsoft Fabric Real-Time Intelligence demo for mining telemetry, environmental monitoring, production tracking, and safety alerting.

## Project shape

- `deploy.py` is the main orchestration script. It provisions the Fabric Eventhouse, KQL database, schema, reference data, Eventstream, KQL Queryset, and Real-Time Dashboard.
- `simulator/` generates and publishes synthetic sensor data to Azure Event Hubs or a Fabric Eventstream custom endpoint.
- `kql/` contains the schema, seed data, production queries, and predictive queries that power the dashboard and alerts.
- `dashboard/dashboard-config.md` is the canonical source for dashboard pages, tiles, visuals, refresh cadence, and backing KQL queries.
- `activator/alert-rules.md` defines the Data Activator / Reflex rules for safety alerts.
- `docs/` contains the architecture and CI/CD setup guidance.

## Commands

### Install dependencies

```bash
pip install azure-identity requests
cd simulator
pip install -r requirements.txt
```

### Deploy Fabric resources

```bash
python deploy.py --workspace-id <workspace-guid>
python deploy.py \
  --workspace-id <workspace-guid> \
  --tenant-id <tenant-guid> \
  --client-id <client-guid> \
  --client-secret <client-secret>
```

### Run the simulator

```bash
cd simulator
python simulator.py --console --max-iterations 5
python simulator.py --config config.sample.yaml
python simulator.py --inject-anomaly gas
```

### Generate and ingest historical data

```bash
cd simulator
python generate_history.py
python generate_history.py --days 7 --interval 60
python deploy_history.py --cluster https://<cluster>.kusto.fabric.microsoft.com --database MiningOps
```

### Test and lint

There is currently no dedicated repo-wide test or lint command wired up in the repository.
Use the smoke-style script runs above when validating changes to deployment, simulator, or historical-data flows.

## High-level architecture

The flow is:

1. The simulator emits JSON sensor events.
2. Fabric Eventstream ingests the events into the `SensorReadings` landing table.
3. KQL update policies fan the landing table out into materialized tables for equipment, environmental, and production queries.
4. The Real-Time Dashboard reads named KQL queries from `kql/03-queries.kql`.
5. Data Activator rules consume the same Fabric data to trigger safety alerts.

Deployment order matters: Eventhouse -> KQL database -> schema/policies -> reference data -> Eventstream -> Queryset -> dashboard.

## Key conventions

- Keep the canonical item names stable unless you update every reference: `MiningRTI`, `MiningOps`, `MiningSensorStream`, `Mining Operations`, and `Mining Safety Alerts`.
- Dashboard definitions must keep `schema_version: 69` as an integer.
- Each dashboard query must include a nested `dataSource` object shaped like `{"kind": "inline", "dataSourceId": "<id>"}`.
- Queryset definitions use root fields `version`, `dataSources`, and `tabs` with no outer wrapper key.
- KQL Queryset and dashboard query names should stay aligned with `kql/03-queries.kql` and `dashboard/dashboard-config.md`.
- Several Fabric features still require manual portal wiring after REST deployment, especially Eventstream source/destination setup and Data Activator trigger activation.
- The GitHub Actions deployment workflow is path-based; changes under `deploy.py`, `kql/**`, `dashboard/**`, or `simulator/**` are what trigger the Fabric deploy job.
- KQL schema scripts are intended to be rerun safely, so prefer idempotent changes and preserve that behavior when editing them.
