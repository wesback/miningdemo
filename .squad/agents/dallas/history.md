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

### 2026-03-20 — Complete Dashboard Definition Expansion
- **Change:** Expanded `deploy.py` dashboard definition from 6 tiles (3 pages) to **18 tiles across 4 pages**
- **Source:** All tiles extracted from `dashboard/dashboard-config.md` specification
- **Pages Implemented:**
  - **Page 1: Operations Overview** — 4 tiles (Active Equipment Count, Shift Tonnage vs Target, Equipment Status Map, Active Alerts)
  - **Page 2: Safety & Environment** — 4 tiles (Gas Levels by Zone, Temperature Heat Map, Threshold Breaches 24h, Safety Incident Timeline)
  - **Page 3: Equipment Health** — 4 tiles (Vibration Anomaly Trend, Drill Hydraulic Pressure, Equipment Health Scores, Equipment Utilisation)
  - **Page 4: Production** — 4 tiles (Conveyor Throughput Trend, Haul Truck Cycle Times, Route Efficiency, 7-Day Production Trend)
- **Implementation Details:**
  - Each tile includes proper visual type (stat, bar, line, area, scatter, table, map)
  - Auto-refresh intervals matched to spec (15s to 4h depending on tile criticality)
  - KQL queries embedded inline (matches dashboard-config.md exactly)
  - Named queries referenced where specified (EquipmentHealthScores, RouteEfficiency)
  - Tile layout positioning added (x/y/width/height grid system)
- **Pattern:** Dashboard definition remains base64-encoded JSON payload in `build_dashboard_definition()` function
- **Validation:** Python syntax verified, ready for deployment
- **CI/CD Integration:** GitHub Actions workflow (`.github/workflows/deploy-fabric.yml`) created by Parker now automatically deploys this complete 18-tile dashboard on every push to main (with path filters for deploy.py, kql/, dashboard/, simulator/)
- **Key Files:** `deploy.py` (modified), `dashboard/dashboard-config.md` (reference), `kql/03-queries.kql` (named query source)

**Cross-team context:** Parker's CI/CD pipeline ensures Dallas's expanded dashboard definition is deployed automatically. Path filters trigger deployment when dashboard-related files change, reducing manual deployment steps.

### 2026-03-20 — Corrected Tile Count Documentation & Fixed Baseline Ingestion Verification
- **Fix 1:** Corrected docstring in `deploy.py` line 570 — tile count updated from "18 tiles" to "16 tiles" (accurate count verified via code inspection)
- **Fix 2:** Implemented baseline row count comparison in `activator/ingest_history.py` for reliable ingestion verification
- **Problem:** Original success check used `row_count > 0` which immediately passed true if table had any prior data, even if new ingestion added zero rows
- **Solution:** Capture baseline row count BEFORE ingestion starts, compare post-ingestion count against baseline, success only if `row_count > baseline_count`
- **Implementation:** Added baseline capture at line 237, updated success check at line 273, added "Rows added" delta logging at line 276
- **Benefit:** Ingestion verification now correctly detects failed ingestions even when table already has historical rows; better observability with row delta reporting
- **Pattern:** Baseline-then-compare pattern applicable to any incremental operation verification (table updates, queue processing, batch jobs)
- **Key Files:** `deploy.py` (docstring fix), `activator/ingest_history.py` (baseline verification logic)

### 2026-03-20 — Comprehensive CI/CD Setup Documentation
- **Created:** `docs/CICD_SETUP.md` — Comprehensive guide for automated deployment via GitHub Actions
- **Scope:** Covers full setup lifecycle from Azure AD app registration through successful deployment
- **Key Sections:**
  1. **Prerequisites:** Azure subscription, Fabric workspace, permissions needed
  2. **Service Principal Creation:** Azure Portal and Azure CLI methods with API permissions setup
  3. **Fabric IDs Discovery:** FABRIC_WORKSPACE_ID, FABRIC_CLUSTER_URI, tenant/client IDs
  4. **GitHub Secrets Configuration:** 5 secrets required with exact names and validation checklist
  5. **Deployment Options:** CI/CD push triggers, workflow_dispatch with historical data, local CLI
  6. **Post-Deployment Steps:** Eventstream wiring, Data Activator setup (both UI-only, not REST API)
  7. **Troubleshooting:** Table of 15+ common issues with solutions (401/403 errors, secret problems, URI formats)
- **Workflow Details:**
  - **Secrets Used:** AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, FABRIC_WORKSPACE_ID, FABRIC_CLUSTER_URI
  - **FABRIC_CLUSTER_URI:** Only required for historical-data job (workflow_dispatch with include_historical=true)
  - **Main Deploy Job:** Validates secrets, runs deploy.py, creates all 5 Fabric items
  - **Historical-Data Job:** Conditional on workflow_dispatch + include_historical flag, generates CSVs then ingests via deploy_history.py
  - **Triggers:** Auto on push to main (paths: deploy.py, kql/**, dashboard/**, simulator/**), manual via workflow_dispatch
- **Fabric Items Deployed:** Eventhouse (MiningRTI), KQL Database (MiningOps), Eventstream (MiningSensorStream), KQL Queryset (MiningOps-Queries), Dashboard (Mining Operations)
- **README Integration:** Added CI/CD Setup section after "Option B — Manual" and before "Demo Scenarios", plus table row in Prerequisites linking to guide
- **Format:** Professional markdown with code blocks, callout boxes (Tip/Warning), tables, numbered steps, troubleshooting matrix
- **Audience:** First-time setup users — clear enough for non-experts, detailed enough for CI/CD best practices
- **Key Files:** `docs/CICD_SETUP.md` (new), `README.md` (updated with link + prereq row)

