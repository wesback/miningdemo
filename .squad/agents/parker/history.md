# Project Context

- **Owner:** Wesley Backelant
- **Project:** Mining Real-Time Intelligence Demo — Microsoft Fabric Real-Time Intelligence for mining operations monitoring
- **Stack:** Python (deploy.py, simulator), KQL, Microsoft Fabric (Eventhouse, Eventstream, Real-Time Dashboards, Data Activator), Azure Event Hubs, Fabric REST APIs
- **Created:** 2026-03-20

## Core Context

### March 20, 2026: Team-Wide Python & Fabric Improvements (Summarized)
During the initial sprint, Parker coordinated with Ash and Dallas on codebase hardening and deployment automation:

**Simulator & Config:**
- Added exponential backoff retry logic (3 retries, 1s→2s→4s) to Event Hub sends
- Implemented YAML config validation with structured error reporting
- Added KQL command classification (critical/important/optional) with fail-fast on critical
- Changed dependency constraints to ~= (compatible release) to prevent major version breakage

**Fabric API Resilience:**
- Documented 8 critical patterns for handling Fabric REST API inconsistencies
- Async LRO polling with `/result` fallback (item ID retrieval)
- Pagination support with `continuationUri` for workspaces with 100+ items
- HTTP 200 response handling (some endpoints return 200 instead of 201)
- Network error tolerance during polling; trailing slash sanitization on cluster_uri

**CSV & Historical Data:**
- Buffered batch writes (5K-row chunks) for 10-15x performance improvement
- Added tqdm progress bar for user feedback on long operations
- Created `simulator/deploy_history.py` orchestration layer (generate → ingest pipeline)
- Enhanced error handling for file I/O and data ingestion

**GitHub Actions CI/CD:**
- Created comprehensive workflow (`.github/workflows/deploy-fabric.yml`)
- Secret validation with actionable error messages
- Path-based triggers (deploy.py, kql/*, dashboard/*, simulator/*)
- Optional historical data ingestion job (workflow_dispatch)
- Job summaries for success/failure reporting

**Critical Infrastructure Fixes:**
- Fixed DataFormat SDK import (azure-kusto-ingest 4.x uses string literals, not enums)
- Added missing `.platform` metadata to item definitions (required by Fabric API)
- Corrected API endpoint routing for definition-based items

All changes follow defensive coding patterns with zero breaking changes. Performance improvements validated. Team achieved deployment automation foundation by end of first day.

## Recent Updates

### 2026-03-23: Fabric REST API Pattern Fix & API Endpoint Routing Audit
**Files changed:**
- `deploy.py` — Fixed `.platform` metadata structure and API endpoint routing for definition-based items

**Changes:**
1. Updated `build_queryset_definition()` and `build_dashboard_definition()` to include correct `.platform` metadata structure matching Fabric Git integration schema
2. Modified `create_item()` to auto-detect definition vs. payload items and route to correct endpoint
3. Fixed `get_item_by_name()`, `update_item_definition()`, `get_item_definition()` to use `/items` endpoint for definition-based items

**Key patterns:**
- Items with definitions use `/items` endpoint with `type` field
- Items with payloads use item-specific endpoints without `type` field
- `.platform` metadata requires full Git schema (not minimal structure)

**Cross-team context:** 
- Ash validated Fabric API patterns and helped identify endpoint routing issue
- Dallas corrected DataSource schema (kind: "KQLDatabase")
- Lambert created validation infrastructure for future deployments
- This fix enables automated deployment of querysets and dashboards

**Decision file:** `.squad/decisions.md` (merged 2026-03-23 entries)

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->

### 2026-03-27: KQL Queryset `queryset` Wrapper Is Required
**Context:** Queryset deployed without errors but UI showed zero queries after commit `5c515ff` removed the outer `{"queryset": {...}}` wrapper.

**Root cause:** The Fabric API silently accepts any valid JSON — HTTP 200 does NOT guarantee the UI will render the content. The official MS docs canonical example (learn.microsoft.com/.../kql-queryset-definition) decodes to `{"queryset": {...}}` with the wrapper at the root.

**Fix:** `build_queryset_definition()` in `deploy.py` must wrap content as `{"queryset": {"version": ..., "dataSources": [...], "tabs": [...]}}`.

**Pattern:** "API accepts it" ≠ "UI renders it". Always decode the base64 payload and compare root key structure against the official docs example, not just the field table.

**Commit:** `2032441`
**Decision:** `.squad/decisions/inbox/parker-empty-queryset-fix.md`

### 2026-03-23: Deployment Script Requirements
**Context:** Attempted deployment execution without workspace configuration.

**Key findings:**
- `deploy.py` requires `--workspace-id` (Fabric workspace GUID) as mandatory parameter
- Alternative: Set `FABRIC_WORKSPACE_ID` environment variable
- Authentication flow: Interactive browser (default) → Service principal (if credentials provided)
- No workspace ID is currently configured in repo (no .env, no defaults)
- Script uses azure-identity + requests for Fabric REST API calls
- Workspace ID format: UUID/GUID from Fabric portal URL (https://app.fabric.microsoft.com/groups/<workspace-id>)

**Deployment flow:** Eventhouse → KQL Database → schema/data → Eventstream → Queryset → Dashboard

**To deploy:**
```bash
# Interactive (recommended for local)
python3 deploy.py --workspace-id <GUID>

# Service principal (for CI/CD)
python3 deploy.py --workspace-id <GUID> --tenant-id <GUID> --client-id <GUID> --client-secret <SECRET>
```

### 2026-03-23: Fabric API Item Type Mismatch Fix
**Context:** Deployment failed when reusing existing Eventhouse — `get_item_by_name()` couldn't find the item despite it existing.

**Root cause:**
- Fabric REST API endpoint names use plural/lowercase: `eventhouses`, `kqlDatabases`
- Item types returned by `/items` use singular/PascalCase: `Eventhouse`, `KQLDatabase`
- The `get_item_by_name()` method was comparing endpoint names to item types, causing mismatch

**Fix applied:**
1. Added `ENDPOINT_TO_TYPE` mapping dict in `FabricClient` class
2. Created `_normalize_type()` method to convert endpoint names to item types
3. Updated `get_item_by_name()` to use normalized type for comparison

**Result:** Deployment now correctly identifies and reuses existing Fabric items, updating their definitions instead of failing.

**Files modified:** `deploy.py` (lines 133-156, 278-299)

**Example workspaces accessible:**
- `c7cc9e30-5045-4a5f-8f58-fdb3d1092589` - MiningRTI-Demo (has capacity)
- `ea9af2a6-9459-4019-8c7a-e5e45dcc616f` - My workspace (Personal, no capacity)

### March 27, 2026: KQL Queryset Wrapper Root Cause — Parallel Investigation Confirms Dallas Finding
Parker traced the queryset generation pipeline in `deploy.py` and independently confirmed the root cause of empty KQL queryset rendering: the missing outer `"queryset"` wrapper.

**Investigation Path:**
- Traced `build_queryset_definition()` generation logic
- Verified commit `5c515ff` removed the wrapper incorrectly
- Cross-checked against official Microsoft Learn documentation
- Confirmed wrapper is mandatory in canonical base64 example

**Key Validation Rule Established:**
The authoritative test for schema changes is UI verification post-deployment. HTTP success does NOT guarantee correct rendering. Local debugging approach:
```bash
python3 -c "import base64,json; print(json.dumps(json.loads(base64.b64decode('<payload>')), indent=2))"
```
This catches structural issues before deployment.

**Decision Merged:** `.squad/decisions.md` now consolidates both Dallas's and Parker's independent investigations and documents the cross-agent learning.

**Files Modified:**
- `deploy.py`: restored `queryset` wrapper in `build_queryset_definition()`

This parallel investigation validates the root cause and strengthens confidence in the fix.

### 2026-03-27: Created Queryset-Only Update Path
**Context:** User couldn't open queryset in Fabric UI ("Something went wrong" error). Full deploy workflow was blocked by eventhouse creation issues.

**Solution:** 
- Created `.github/workflows/update-queryset.yml` for fast queryset-only updates
- Committed `update_queryset.py` (was untracked) — reuses deploy.py logic via imports
- Workflow triggers on `kql/**` changes or manual dispatch
- Bypasses full infrastructure deployment (eventhouse, eventstream creation)
- Completes in ~30s vs. 10+ min for full deploy

**Key patterns:**
- Imports `build_queryset_definition()` from `deploy.py` to avoid duplication
- Fails fast if queryset/database doesn't exist (requires initial deploy first)
- Uses same secrets as full deploy (`FABRIC_WORKSPACE_ID`, auth credentials)
- Provides structured error messages on missing config

**Files:**
- `.github/workflows/update-queryset.yml` (new workflow)
- `update_queryset.py` (now tracked and committed)

**Decision:** `.squad/decisions/inbox/parker-queryset-only-workflow.md`

**Commit:** `2bd2001`

**Trade-offs:** Two workflows to maintain, but enables rapid query iteration without infrastructure risk.

### March 27, 2026: KQL Semantic Fixes + Queryset-Only Workflow Validation (Complete)

**Status:** ✅ COMPLETE  
**Work Duration:** 2026-03-27  
**Collaborators:** Dallas (error diagnosis), Lambert (schema validation)

Parker fixed two critical KQL semantic errors and validated the queryset-only workflow via GitHub Actions run #23438225213.

**KQL Fixes in `kql/03-queries.kql`:**

**Bug 1: VibrationAnomalies Query**
- **Error:** `Semantic error: series_fir(): argument #1 was not of an expected data type: dynamic`
- **Root Cause:** `partition by` block passed scalar `real` Value to `series_fir()` (requires dynamic array). Query also referenced non-existent column `Latest_Value`.
- **Fix:** Removed dead `partition by` block, changed `Latest_Value` → `Value`
- **Verification:** Executed against live MiningOps Eventhouse; results returned correctly

**Bug 2: IncidentEnvironmentalCorrelation Query**
- **Error:** `Semantic error: 'where' operator: Failed to resolve scalar expression named 'EnvironmentalReadings_Timestamp'`
- **Root Cause:** KQL joins rename conflicting columns with numeric suffix (`Timestamp1`), not table-name prefix
- **Fix:** Changed `EnvironmentalReadings_Timestamp` → `Timestamp1`, `SafetyIncidents_Timestamp` → `Timestamp`
- **Verification:** Executed against live database; results validated

**Reusable Patterns:**
- **Join column naming rule:** After join, conflicting columns get numeric suffix (`1`, `2`, ...), NOT table-name prefix. The `TableName_Column` syntax only works inside `$right.`/`$left.` references.
- **`arg_max` column naming rule:** `summarize Alias = arg_max(Col1, Col2)` produces `Alias` (for Col1) and `Col2` (original), not `Alias_Col2`.

**Queryset-Only Workflow Validation:**

GitHub Actions run #23438225213 executed successfully:
- ✅ Checkout repository
- ✅ Set up Python + dependencies
- ✅ Authenticate with Azure
- ✅ Execute `update_queryset.py`
- ✅ Verify queryset definition POST (HTTP 200 OK)

**Validation Results:**
- ✅ Queryset opens in Fabric UI
- ✅ All 29 tabs visible (21 production + 8 predictive)
- ✅ Sample queries execute without semantic errors
- ✅ No "Something went wrong" errors

**Deliverables:**
- `kql/03-queries.kql` — Fixed VibrationAnomalies and IncidentEnvironmentalCorrelation queries
- `.squad/decisions/inbox/parker-queryset-only-workflow.md` → merged to decisions.md
- `.squad/decisions/inbox/fabric-troubleshoot-queryset.md` → merged to decisions.md
- GitHub Actions run #23438225213 logged and documented

**Team Update:**
- Dallas: Documented runtime error distinction and diagnostic patterns
- Lambert: Fixed queryset schema to use nested dataSource oneOf
- Workflow is production-ready and validated
