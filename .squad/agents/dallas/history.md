# Project Context

- **Owner:** Wesley Backelant
- **Project:** Mining Real-Time Intelligence Demo — Microsoft Fabric Real-Time Intelligence for mining operations monitoring
- **Stack:** Python (deploy.py, simulator), KQL, Microsoft Fabric (Eventhouse, Eventstream, Real-Time Dashboards, Data Activator), Azure Event Hubs, Fabric REST APIs
- **Created:** 2026-03-20

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->

### 2026-03-20 — Dashboard Query Standardization
- **Pattern:** Dashboard tile configurations in `dashboard/dashboard-config.md` now explicitly reference named queries from `kql/03-queries.kql` using consistent backtick-quoted format
- **Files:** All query references standardized — inline KQL queries included for ad-hoc tiles, named queries referenced by name (e.g., `EquipmentHealthScores`, `RouteEfficiency`)
- **Header note added:** Top of dashboard-config.md now links to source query file and explains naming convention

### 2026-03-20 — Docker Script Deprecation
- **Decision:** `get-docker.sh` is a standard Docker convenience installer that is NOT required for this demo
- **Action:** Added deprecation notice to script header explaining it's not needed (all components run in Fabric or as Python scripts)
- **Documentation:** Updated README.md repository structure to note script as [DEPRECATED]
- **Rationale:** Demo has no Docker containerization dependency — Fabric handles hosting, Python simulator runs natively

### 2026-03-20 — Automated Historical Data Ingestion
- **New Tool:** `activator/ingest_history.py` — Python script automating CSV ingestion into KQL Database
- **Stack:** Uses `azure-kusto-data` and `azure-kusto-ingest` SDKs with credential patterns matching `deploy.py`
- **Authentication:** Supports DefaultAzureCredential (Azure CLI/managed identity), InteractiveBrowserCredential fallback, and service principal (tenant/client/secret)
- **Features:** 
  - Command-line arguments for CSV path, cluster URI, database, table, mapping
  - Pre-flight table existence validation
  - Dry-run mode for config testing
  - Progress monitoring via table row count polling
  - Error handling with actionable troubleshooting hints
- **README Updated:** Step 5b now presents automated script as Option A (recommended), manual Lakehouse/Blob upload as Option B
- **User Benefit:** Eliminates manual Lakehouse upload + KQL `.ingest` command workflow — single Python command ingests local CSV directly to Fabric
