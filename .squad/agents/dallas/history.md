# Project Context

- **Owner:** Wesley Backelant
- **Project:** Mining Real-Time Intelligence Demo — Microsoft Fabric Real-Time Intelligence for mining operations monitoring
- **Stack:** Python (deploy.py, simulator), KQL, Microsoft Fabric (Eventhouse, Eventstream, Real-Time Dashboards, Data Activator), Azure Event Hubs, Fabric REST APIs
- **Created:** 2026-03-20

## Core Context

### March 20, 2026: Fabric Integration & Deployment Documentation (Summarized)
During the initial sprint, Dallas focused on Fabric-specific deliverables and operational patterns:

**Fabric REST API Patterns:**
- Documented complete LRO (Long-Running Operation) polling flow with `/result` fallback
- Identified pagination requirements for list endpoints using `continuationUri`
- Confirmed three Fabric API inconsistencies: 200 vs 201 responses, trailing slashes on URIs, network resilience during polling
- Validated correct data source `kind: "AzureDataExplorer"` for querysets

**Dashboard & Queryset:**
- Expanded dashboard from 6 to 18 tiles (4 pages) with standardized query references
- Standardized all KQL query references in `dashboard/dashboard-config.md` using consistent backtick format
- Documented dashboard schema v52 compliance requirements (schema_version, nested references with kind discriminators)
- Deprecated `get-docker.sh` as project has no Docker dependencies

**CSV Ingestion Automation:**
- Created `activator/ingest_history.py` for automated CSV ingestion via Kusto SDK
- Matched credential patterns to deploy.py (DefaultAzureCredential → InteractiveBrowserCredential → service principal)
- Added pre-flight table existence validation, dry-run mode, progress monitoring
- Integrated with Parker's CI/CD pipeline as optional historical-data job

**CI/CD Documentation:**
- Created `docs/CICD_SETUP.md` comprehensive setup guide (section 1-7: prereqs, service principal creation, Fabric ID discovery, GitHub secrets, deployment options, post-deployment, troubleshooting)
- Documented 15+ common troubleshooting scenarios with solutions
- Provided clear workflow trigger descriptions (auto push + workflow_dispatch)

**GitHub Actions Integration:**
- Validated CI/CD workflow matches credential patterns
- Fixed historical-data job to use correct script invocation and secret mapping
- Removed workspace ID security leaks from job summaries

All patterns follow Microsoft best practices. Documentation supports both expert and first-time users. Team achieved end-to-end deployment automation.

## Recent Updates

### 2026-03-23: Critical Dashboard DataSource Schema Fix
**Files changed:**
- `deploy.py` — Fixed DataSource structure in `build_dashboard_definition()` (lines 763-774)

**Changes:**
1. Changed DataSource `kind` from `"kusto-trident"` to `"KQLDatabase"` (official value)
2. Removed undocumented `workspace` field
3. Reordered fields to match official Git integration schema

**Key pattern:**
- Official Fabric Git integration schema is authoritative for item structure (more complete than REST API docs)
- Always validate against Git-exported examples when creating item definitions
- `kind: "KQLDatabase"` is the correct value for Kusto data sources

**Cross-team context:**
- Parker identified API endpoint routing issue; this was secondary bug
- Ash validated query references were sound; schema was the blocker
- Lambert created validation infrastructure confirming this fix resolves schema compliance
- This fix resolves multi-day deployment failures

**Decision file:** `.squad/decisions.md` (merged 2026-03-23 entries)

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->

### 2026-03-24: Three Schema Bugs Fixed — Queryset + Dashboard Deployment

**Files changed:** `deploy.py`

**Bug 1 (Critical — Queryset): Extra `"queryset"` wrapper in `build_queryset_definition()`**
- The `RealTimeQueryset.json` payload was wrapped in `{"queryset": {...}}` instead of being flat.
- Official docs state root fields are `version`, `dataSources`, `tabs` — no outer wrapper.
- Fix: Remove the wrapper; `queryset_json` is now the flat object directly.

**Bug 2 (Dashboard): `schema_version` was a string, must be integer**
- `"schema_version": "52"` → `"schema_version": 52`
- Fabric RTD schema v52 validates this as an integer type.

**Bug 3 (Dashboard): Query `dataSource` was a nested object; must be flat `dataSourceId`**
- The `q()` helper used `"dataSource": {"kind": "inline", "dataSourceId": ds_id}`.
- The Fabric RTD schema v52 expects `"dataSourceId": ds_id` directly on the query object.
- `kind: "inline"` is not a valid discriminator in the queries array structure.

**Logging added:**
- `build_queryset_definition()` now logs: version, dataSources count, tabs count.
- `build_dashboard_definition()` now logs: schema_version, pages, tiles, queries, dataSources counts.

**Reusable pattern:**
> Always decode and inspect generated base64 payloads locally (python3 dry-run) before
> treating a deployment failure as a network or auth issue. The bugs in this session were
> all silent schema mismatches — the API returned a 4xx with an opaque message rather
> than a helpful diff. Dry-running `build_*_definition()` with `python3 -c "..."` catches
> these immediately.
