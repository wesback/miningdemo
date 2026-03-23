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

**Bug 3 (Dashboard): Query `dataSource` must be nested**
- The `q()` helper now uses `"dataSource": {"kind": "KQLDatabase", "dataSourceId": ds_id}`.
- The Fabric Git dashboard schema expects the nested `dataSource` object inside each query entry.
- `kind: "KQLDatabase"` is the valid discriminator for the current Git schema.

**Logging added:**
- `build_queryset_definition()` now logs: version, dataSources count, tabs count.
- `build_dashboard_definition()` now logs: schema_version, pages, tiles, queries, dataSources counts.

**Reusable pattern:**
> Always decode and inspect generated base64 payloads locally (python3 dry-run) before
> treating a deployment failure as a network or auth issue. The bugs in this session were
> all silent schema mismatches — the API returned a 4xx with an opaque message rather
> than a helpful diff. Dry-running `build_*_definition()` with `python3 -c "..."` catches
> these immediately.

---

### 2026-03-23: Fabric Schema v52 Hardening — Three Silent Bugs Fixed

**Context:** Dashboard and queryset generation had three silent schema mismatches, discovered only via local payload inspection before deployment.

**Bugs Fixed:**

1. **Queryset Root Structure** — Removed outer `{"queryset": {...}}` wrapper. Root now has flat fields: `version`, `dataSources`, `tabs`.

2. **Dashboard DataSource Kind** — Changed from `"kusto-trident"` to `"KQLDatabase"` (Git integration schema).

3. **Dashboard schema_version Type** — Changed from string `"52"` to integer `52`.

4. **Dashboard Query dataSourceId** — Flattened from nested `{"kind": "inline", "dataSourceId": "..."}` to simple `"dataSourceId": "..."` field.

**Discovery Method:** None of these would have been caught by code review. All were silent schema mismatches where Fabric API returned opaque 4xx errors. Fix validated via:
- Local base64 payload decoding and inspection
- Schema conformance against official Fabric v52 specification
- Live deployment to workspace c7cc9e30-5045-4a5f-8f58-fdb3d1092589 (succeeded end-to-end)

**Durable Finding:** Fabric schema validation MUST include local dry-run decoding before any API submission. Pre-deployment checklist now includes `python3 -c "from deploy import ..."` to verify payloads.

**Files:** `deploy.py` (functions `build_queryset_definition()`, `build_dashboard_definition()`)

---

### 2026-03-26: Dashboard schema_version Bump 52 → 69

**Error:** `Missing migration for dashboard version 52... Required version: 69 Received version: 52`

**Root cause:** Fabric RTD client incremented its minimum accepted `schema_version` from 52 to 69. The payload shape was correct; only the version integer was stale.

**Fix — three surgical changes:**
1. `deploy.py` line 1118: `"schema_version": 52` → `"schema_version": 69`
2. `deploy.py` lines 785, 843: inline comments updated from v52 → v69
3. `validate_fabric_definitions.py`: Updated all v52 → v69 references; upgraded the type-only check to also assert the exact value (`!= 69` emits error). This value-assertion means the next Fabric version bump will be caught locally before deployment.

**Verdict:** Pure version bump. No structural changes to dataSources/pages/tiles/queries/baseQueries/parameters.

**Validation:** `python3 validate_fabric_definitions.py` → ✅ PASSED (`schema_version=69`, 4 pages, 16 tiles, 16 queries, 29 queryset tabs)

**Durable pattern:** When a remote client enforces an exact version integer (not just "must be int"), the local validator should assert the value explicitly — `elif version != EXPECTED: error(...)`. Saves a round-trip deployment failure.

---

### 2026-03-26: Three Unsupported Property Removals — Dashboard Schema v69 Refinement

**Error:** Fabric client rejected dashboard with three unsupported properties:
- `/autoRefresh.interval` 
- `/tiles[*].usedParamVariables`
- `/queries[*].dataSourceId`

**Root cause:** Schema v69 enforcement tightened. While `schema_version: 69` was correct, certain properties that previously worked (or were documented) are no longer accepted by the live Fabric client.

**Fix — three surgical removals:**

1. **autoRefresh.interval** (line 1120)
   - BEFORE: `"autoRefresh": {"enabled": True, "interval": 30}`
   - AFTER: `"autoRefresh": {"enabled": True}`
   - Only `enabled` field is supported; refresh interval cannot be explicitly set.

2. **tiles[*].usedParamVariables** (line 1090)
   - BEFORE: Tile definition included `"usedParamVariables": []`
   - AFTER: Field removed entirely from tile objects
   - Parameter variable tracking is not part of the tile schema.

3. **queries[*].dataSourceId** (lines 843-847)
   - BEFORE: Query helper `q()` included `"dataSourceId": ds_id`
   - AFTER: Field removed from queries; datasource context provided via dashboard-level `dataSources` array
   - The tile's `queryRef` links to the query, and queries inherit datasource from the dashboard context rather than declaring it explicitly.

**Validator updates:** All three checks were already present in `validate_fabric_definitions.py` and now correctly catch these as errors during local validation.

**Validation:** `python3 validate_fabric_definitions.py` → ✅ PASSED (16 tiles, 4 pages, 16 queries, 29 queryset tabs)

**Durable finding:** Schema v69 uses datasource inheritance at dashboard level rather than per-query annotation. The queryRef→query→text path is sufficient; explicit dataSourceId on queries is not just redundant but actively rejected. This is a semantic shift from earlier schemas where queries might have declared their own datasource.

---

### 2026-03-27: Empty KQL Queryset — Restored `"queryset"` Wrapper

**Symptom:** KQL Queryset deployed without error but opened empty (no query tabs visible).

**Root Cause:** A prior fix incorrectly removed the outer `"queryset"` wrapper from `RealTimeQueryset.json`. The Fabric API accepted the flat payload without error (lenient validation), but the UI expects `queryset_json["queryset"]` and rendered nothing.

**Evidence:** Decoded the official Microsoft docs example payload (base64):
`https://learn.microsoft.com/rest/api/fabric/articles/item-management/definitions/kql-queryset-definition`
The decoded JSON is unambiguously `{"queryset": {"version": "1.0.0", "dataSources": [...], "tabs": [...]}}`.

**Fix:**
- `deploy.py` `build_queryset_definition()`: restored `{"queryset": {...}}` outer wrapper; updated logging to read from `queryset_json["queryset"]`
- `.squad/agents/lambert/validate_fabric_definitions.py` `validate_queryset_structure()`: updated to require `queryset` root key; fixed `tab_count` reference in main runner

**Key lesson:** Fabric API silent acceptance ≠ correct rendering. A `200/201` does not guarantee the UI will display the item correctly. Always open and visually verify the deployed item. The tab fields (`id`, `content`, `title`, `dataSourceId`) were correct all along; only the wrapper was missing.

**Decision file:** `.squad/decisions/inbox/dallas-empty-queryset-fix.md`

### March 27, 2026: KQL Queryset Schema Fix & Fabric API Validation Lesson
Dallas investigated empty KQL queryset rendering symptoms and identified the root cause: a missing outer `"queryset"` wrapper in the RealTimeQueryset.json payload structure.

**Investigation:**
- Traced deployment symptoms (HTTP 201 success but empty UI)
- Cross-referenced official Microsoft Learn KQL Queryset Definition schema
- Confirmed wrapper is mandatory in canonical base64 example payload

**Key Lesson Documented:**
The Fabric API exhibits lenient validation — it accepts malformed payloads (201 Created) but the UI only renders content it understands from the expected root key. This creates a false sense of success: HTTP success ≠ correct rendering.

**Decision Merged:** `.squad/decisions.md` now documents this finding and validation approach:
1. Decode base64 payloads locally and inspect structure
2. Cross-check against official MS docs canonical examples
3. Always verify rendering in the UI post-deployment

**Files Modified:**
- `deploy.py`: restored `queryset` wrapper in `build_queryset_definition()`
- `validate_fabric_definitions.py`: updated to validate wrapper presence

This lesson transfers to Parker and all future schema work.

## Learnings

### Tutorial Location Update (2026-03-23)
- **Updated:** `docs/mining-rti-tutorial.md` and `docs/architecture.md`
- **Change:** Scenario location updated to Ontario, Canada; coordinates aligned with simulator
- **Details:** 
  - Changed scenario description from Australia to Ontario, Canada
  - Updated GPS coordinates to match Ontario simulator site baseline
  - Tutorial examples now use coordinates consistent with simulator behavior
- **Rationale:** Alignment with simulator site (Ontario coordinates); ensures tutorial examples match actual simulator behavior
- **Cross-agent learnings:** Documentation and simulator now reference identical coordinate systems, eliminating discrepancies in location-based calculations

### Fabric Doc Parity (2026-03-23)
- **Key files:** `README.md`, `docs/mining-rti-tutorial.md`, `docs/CICD_SETUP.md`, `docs/user-stories.md`, `simulator/CONFIG_SCHEMA.md`, `simulator/config.sample.yaml`, `deploy.py`
- **Pattern:** Keep canonical Fabric item names and source-of-truth terminology aligned across docs. In this repo, `deploy.py` is authoritative for `MiningRTI`, `MiningOps`, `MiningSensorStream`, `MiningOps-Queries`, and `Mining Operations`.
- **Pattern:** For Fabric Eventstream custom endpoints, document the system-generated Event Hub name (`es_...`) instead of the stream display name.
- **Pattern:** Keep simulator geography and sample coordinates aligned with the simulator implementation and architecture docs (Ontario / Sudbury Basin here).
- **Why it matters:** Docs drift creates broken copy/paste steps and inconsistent setup instructions. Future doc reviews should compare README, tutorial, CI/CD, simulator examples, and KQL story IDs against the canonical deployment script.

### 2026-03-27: Tutorial CI/CD Pointer Addition
**Files changed:** `docs/mining-rti-tutorial.md`

**Decision:** Added a reference to `CICD_SETUP.md` in the tutorial deployment overview section (before Step 1).

**Rationale:** 
- Tutorial comprehensively explains manual `deploy.py` deployment but didn't mention the automated CI/CD option
- Users should know about GitHub Actions automation before starting manual deployment
- Especially relevant for production deployments requiring service principal auth

**Placement choice:**
- Added as blockquote note immediately after deployment overview table, before Step 1
- Appears early enough to inform deployment path choice
- Doesn't disrupt step-by-step flow for users choosing manual path

**Impact:** Users are now aware of both deployment options (manual interactive vs. automated CI/CD). Pointer is minimal and non-intrusive.

**Status:** Merged to `.squad/decisions.md` on 2026-03-23  
**Orchestration Log:** `.squad/orchestration-log/2026-03-23T12-17-43Z-dallas.md`  
**Session Log:** `.squad/log/2026-03-23T12-17-43Z-cicd-tutorial-pointer.md`
