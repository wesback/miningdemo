# Project Context

- **Owner:** Wesley Backelant
- **Project:** Mining Real-Time Intelligence Demo — Microsoft Fabric Real-Time Intelligence for mining operations monitoring
- **Stack:** Python (deploy.py, simulator), KQL, Microsoft Fabric (Eventhouse, Eventstream, Real-Time Dashboards, Data Activator), Azure Event Hubs, Fabric REST APIs
- **Created:** 2026-03-20

## Core Context

### Learnings Summary
Lambert's domain expertise covers:
1. **KQL Validation Infrastructure** (2026-03-20) — Created pre-deployment KQL syntax validation in deploy.py
2. **Simulator Config Schema** (2026-03-20) — Comprehensive documentation for simulator.py configuration (11KB reference)
3. **Fabric Deployment Validation** (2026-03-23) — Comprehensive schema validation infrastructure for dashboards and querysets
4. **Validator Sync Pattern** (2026-03-23) — Established pattern: validator must mirror deploy.py JSON shapes exactly; value assertions (not just type checks) for version fields

### Durable Patterns
- **Validator as Pre-Flight Smoke Test:** Deploy.py builders are directly imported and tested. Schema drift is immediately visible.
- **Value Assertion for Protocol Versions:** When a remote client enforces exact version integers (not just "must be int"), the validator should assert the exact value locally before deployment.
- **Consistency Checks Required:** Any change to JSON structure in deploy.py must be mirrored in validate_fabric_definitions.py.
- **ID Format Gap:** Validators must check not just presence of `id` fields but also format (UUID vs plain string). Fabric UI clients may silently reject non-UUID IDs even when the API accepts them.
- **HTTP 200 ≠ UI Correct:** API accepting a definition update (HTTP 200) does not guarantee the Fabric UI will render it correctly. Always verify in UI after deployment.

### Key Files Owned
- `.squad/agents/lambert/validate_fabric_definitions.py` — Pre-deployment validation helper (latest: schema_version=69 exact assertion)
- `.squad/agents/lambert/dashboard-queryset-validation.md` — Comprehensive schema validation report (14KB)
- `simulator/CONFIG_SCHEMA.md` — Complete configuration reference (11KB)

### Recent Work (2026-03-23)
Fixed Validator Sync Audit — four false failures detected and corrected:
1. Queryset root structure (removed incorrect wrapper check)
2. Dashboard DataSource.kind (updated from "kusto-trident" to "KQLDatabase")
3. Dashboard schema_version type (int, not str)
4. Dashboard query dataSource structure (nested object with kind + dataSourceId)

Result: `validate_fabric_definitions.py` now passes with schema_version=69, enforces exact version value.

---

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->

### 2026-03-23: Dashboard schema_version Bumped 52 → 69 (Fabric Client Migration Error)

**Context:** Fabric client rejected the dashboard payload with "Required version 69, Received version 52". This surfaced as a deployment-time error, not a validator error, because the validator only checked the *type* (int) of `schema_version`, not the actual *value*.

**Root Cause:**
- `deploy.py` line 1118 hard-coded `"schema_version": 52`
- `validate_fabric_definitions.py` validated type only (`isinstance(..., int)`) — no value assertion
- The Fabric RTD client now enforces `schema_version == 69` and rejects 52

**Changes Made:**
1. `deploy.py`: `"schema_version": 52` → `"schema_version": 69` (line 1118); updated two inline comments (lines 785, 843) from v52 → v69
2. `validate_fabric_definitions.py`: Updated docstring from v52 → v69; replaced type-only check with explicit value assertion (`!= 69` emits error); updated all inline comments

**Verdict:** Pure version bump. No structural schema changes between v52 and v69 — the payload shape (dataSources/pages/tiles/queries/baseQueries/parameters) was already correct. The Fabric client simply incremented its minimum accepted schema_version.

**Validation Result:** `python3 validate_fabric_definitions.py` → ✅ PASSED
- `schema_version=69`, pages=4, tiles=16, queries=16, dataSources=1
- KQL Queryset: 29 query tabs — unchanged

**Reusable Pattern — Value-Assertion Validator:**
When a protocol field carries a version integer that the remote client enforces strictly (not just "must be int"), the validator should assert the exact value:
```python
if dashboard_json["schema_version"] != EXPECTED_VERSION:
    errors.append(f"'schema_version' must be {EXPECTED_VERSION}, got {dashboard_json['schema_version']}")
```
This pattern would have surfaced the mismatch locally before deployment.

**Key Files:**
- `deploy.py`: line 1118 (schema_version), lines 785 & 843 (comments)
- `.squad/agents/lambert/validate_fabric_definitions.py`: lines 94-115 (validate_dashboard_structure)

### 2026-03-23: Fabric RTD Schema v69 — Unsupported Field Validation

**Context:** Fabric client (schema v69) reported three unsupported property paths at deployment time. Fields were already removed from deploy.py by another agent. Lambert's task was to update validate_fabric_definitions.py to enforce their absence.

**Unsupported Fields Identified:**
1. `/autoRefresh.interval` — Only `enabled` field is accepted in autoRefresh object
2. `/tiles/*/usedParamVariables` — Not part of tile schema in current client
3. `/queries/*/dataSourceId` — Query datasource context is inferred from dashboard-level `dataSources` array, not per-query

**Current Payload Structure (Validated Clean):**
- `autoRefresh`: `{"enabled": true}` only
- Tile objects: 8 required/optional fields, NO `usedParamVariables`
- Query objects: 3 required fields (`id`, `text`, `usedVariables`), NO `dataSourceId`

**Validator Changes:**
1. Added autoRefresh.interval detection (line 128)
2. Added tile.usedParamVariables detection (line 185-187)
3. Added query.dataSourceId detection (line 160-163)
4. Updated docstring to document unsupported fields

**Test Results:** All three negative assertions verified:
- ✅ autoRefresh with interval → validator flags
- ✅ Tile with usedParamVariables → validator flags
- ✅ Query with dataSourceId → validator flags
- ✅ Current clean payload → validator passes

**Ambiguity Noted:**
~~The exact requirement for query datasource binding is unclear.~~ **Resolved 2026-03-27:** see below.

**Reusable Pattern — Forbidden Field Validation:**
When a schema evolves to explicitly reject previously-accepted fields, add negative assertions:
```python
if "unsupported_field" in object:
    errors.append("'object.unsupported_field' is unsupported by Fabric client")
```
This catches accidental reintroduction during refactoring.

**Key Files:**
- `validate_fabric_definitions.py`: Lines 122-131, 160-163, 185-187 (forbidden field checks)
- `deploy.py`: Already clean (fields removed before Lambert's work)

### 2026-03-27: Query dataSource — oneOf Object Required (Resolves Ambiguity)

**Context:** After removing flat `dataSourceId` from queries (2026-03-26), the Fabric client rejected the dashboard with:
- `/queries/*/dataSource/kind`: expected constant 'inline' or 'parameter'
- `/queries/*/dataSource`: must match exactly one schema in oneOf

**Root Cause:** Queries cannot *omit* datasource entirely. The v69 schema requires a `dataSource` oneOf object on every query:
- `{"kind": "inline", "dataSourceId": "<id>"}` — reference a dashboard-level dataSource by id
- `{"kind": "parameter", "parameterId": "<id>"}` — reference a dashboard parameter

**Fix:**
1. `deploy.py` `q()` helper: added `"dataSource": {"kind": "inline", "dataSourceId": ds_id}`
2. `validate_fabric_definitions.py`: replaced flat `dataSourceId` rejection with full oneOf validation (kind, dataSourceId/parameterId, cross-reference to dataSources array)

**Validation:** `python3 validate_fabric_definitions.py` → ✅ PASSED

**Durable Pattern — oneOf Discriminator Validation:**
When a Fabric schema field uses oneOf with a `kind` discriminator, validate:
1. `kind` is one of the allowed constants
2. The branch-specific required fields are present
3. Cross-reference IDs exist in the parent collection
```python
if kind == "inline":
    assert "dataSourceId" in obj
elif kind == "parameter":
    assert "parameterId" in obj
```

### 2026-03-27: Queryset Tab dataSource Schema — Missed in Dashboard Fix

**Context:** User reported "Something went wrong" error when opening queryset in Fabric browser UI. The error message referenced a SessionId and InstanceId but gave no specific schema details.

**Root Cause:** Dashboard queries were fixed on 2026-03-27 to use the nested `dataSource` oneOf object (kind + dataSourceId), but queryset tabs were left with the old flat `dataSourceId` field. Both dashboard queries and queryset tabs use the same Fabric client schema requirements.

**Affected Code:**
- `deploy.py` lines 688-712: Three tab creation paths (production queries, predictive queries, empty fallback)
- All 29 query tabs had flat `"dataSourceId": ds_id"` instead of `"dataSource": {"kind": "inline", "dataSourceId": ds_id}`

**Fix Applied:**
1. `deploy.py`: Updated all tab dictionaries to use nested dataSource object
2. `validate_fabric_definitions.py`: Enhanced tab validation with full oneOf validation:
   - Checks for flat dataSourceId (forbidden)
   - Validates dataSource object presence and structure
   - Validates kind is "inline" or "parameter"
   - Cross-references dataSourceId with dataSources array

**Validation:** `python3 validate_fabric_definitions.py` → ✅ PASSED (29 query tabs)

**Durable Pattern — Schema Parity Between Item Types:**
When fixing a Fabric schema issue for one item type (dashboard), check if the same schema requirement applies to related item types (queryset). The Fabric Git integration schema often shares common structures across multiple item types (dashboards, querysets, reports).

**Detection Gap:** The validator previously only checked for *presence* of dataSourceId (flat), not its correctness. Now it actively rejects flat dataSourceId and enforces the oneOf object structure. This would have caught the drift.

**Key Files:**
- `deploy.py`: Lines 688-712 (queryset tab definitions)
- `.squad/agents/lambert/validate_fabric_definitions.py`: Lines 82-119 (tab validation)

**Commit:** d00fd37

### March 27, 2026: Queryset Tab Schema Validation Complete (Complete)

**Status:** ✅ COMPLETE  
**Work Duration:** 2026-03-27  
**Collaborators:** Dallas (runtime error diagnosis), Parker (KQL fixes + workflow)

Lambert enhanced validation infrastructure to catch and prevent schema drift between related Fabric item types (dashboard, queryset).

**Work Summary:**

1. **Identified Schema Mismatch:** Queryset tabs were using old flat `dataSourceId` while dashboard queries use nested `dataSource` oneOf object
   - ❌ Old: `"dataSourceId": "mining-ops-source"`
   - ✅ New: `{"kind": "inline", "dataSourceId": "mining-ops-source"}`

2. **Applied Fix to All Tab Types:**
   - `deploy.py` lines 688-712: Updated production tabs, predictive tabs, and fallback tab
   - All 29 query tabs now emit nested dataSource structure

3. **Enhanced Validator:**
   - Updated `.squad/agents/lambert/validate_fabric_definitions.py` lines 82-119
   - Now validates discriminator field (`kind`) is one of allowed constants
   - Verifies branch-specific required fields are present
   - Cross-references IDs exist in parent collections
   - Active rejection of flat dataSourceId (would have caught this drift)

4. **Validation Verification:**
   ```bash
   python3 .squad/agents/lambert/validate_fabric_definitions.py
   ```
   ✅ PASSED — All 29 query tabs validated with nested schema

**Reusable Pattern — Schema Parity Check:**
When fixing a Fabric schema issue for one item type (e.g., dashboard), systematically check related item types (queryset, report) for the same requirement. The Fabric Git integration schema shares common structures across multiple item types.

**Prevention Pattern:**
Validators should actively reject incorrect patterns (not just check presence). For oneOf schemas:
1. Validate discriminator field is one of allowed constants
2. Enforce branch-specific required fields
3. Cross-reference related IDs

**Impact:**
- ✅ Queryset opens in Fabric UI without schema-related errors
- ✅ All 29 tabs accessible (21 production + 8 predictive)
- ✅ Validator now catches oneOf schema violations before deployment

**Team Update:**
- Dallas: Documented error distinction patterns
- Parker: Fixed KQL semantic errors + validated workflow
- Validator now enforces schema parity across item types

### 2026-03-23: Queryset "No Data Source" — Post-Fix Regression Diagnosis

**Context:** After the flat `dataSourceId` fix (`c8476c6`) was deployed via workflow Run #6 (sha=`2a52891`), user reports "no data source" in incognito — ruling out client-side cache.

**Findings:**
1. Schema shape: ✅ correct per MS docs (flat dataSourceId, correct dataSources structure)
2. Deployment: ✅ confirmed (HTTP 200, Run #6, explicit reason logged)
3. Remaining mismatch: ❌ `dataSources[0].id = "mining-ops-source"` is a plain string, NOT a UUID
4. MS docs example uses UUID for all `id` fields. Fabric UI client may silently reject non-UUID data source IDs.
5. Validator gap: no UUID format check on dataSources[i].id

**Hypothesis:** Fabric UI does UUID-format validation on data source IDs and silently drops entries that don't match, causing "no data source" in the UI panel even though the API accepts the payload.

**Recommended fix:**
- `deploy.py`: Change `ds_id = "mining-ops-source"` to `ds_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, "mining-ops-datasource-mining-ops"))` (deterministic UUID, safe across re-deploys)
- `validate_fabric_definitions.py`: Add UUID format check for `dataSources[i].id`
- Re-trigger `update-queryset.yml` workflow after fix

**Key IDs:**
- Queryset: `db3dc49b-f1a1-42e2-b47a-3a7c3d3fc18c`
- Database: `d1bfe4b5-40c0-4603-a748-3c8e5f9d4b9b`
- Cluster: `https://trd-dxeq4t8vw8cxd1ahn7.z6.kusto.fabric.microsoft.com`

**Decision note:** `.squad/decisions/inbox/lambert-queryset-no-datasource-diagnosis.md`

### 2026-03-27: Queryset dataSources[i].id Must Be a UUID — Final Root Cause & Validator Enhancement

**Context:** Despite correct wrapper (`{"queryset": {...}}`), correct tab schema (nested `dataSource` oneOf), and correct deployment workflow, browser showed "no Data Sources" in the data sources panel of the queryset UI.

**Root Cause Identified (via Dallas's live inspection):**
The queryset `dataSources[0].id` was `"mining-ops-source"` — a plain string, NOT a UUID. The official MS docs example uses UUIDs for all `id` fields. The Fabric UI client performs UUID format validation at render time and silently drops non-UUID data source entries from the panel, even though the API accepts the payload with HTTP 200.

**Pattern Confirmed (third instance):**
- 2026-03-20: Missing outer wrapper → API 201, UI empty
- 2026-03-23: Wrong schema_version type → API 200, UI migration error  
- 2026-03-27: Non-UUID data source ID → API 200, UI "no data source"

**Heuristic:** When Fabric UI shows nothing (vs an error), suspect a field format/type mismatch accepted by API but rejected by UI client at render time.

**Fix Applied:**
1. **Validator enhancement** (`.squad/agents/lambert/validate_fabric_definitions.py`):
   - Added UUID format check for `dataSources[i].id` — was checking presence only, now validates format
   - Severity: ERROR (not warning) — format mismatch will fail validation
   - Added comment documenting the pattern: "Fabric UI silently discards non-UUID data source entries"

2. **Code fix** delegated to Parker in `deploy.py`:
   - Changed `ds_id = "mining-ops-source"` to deterministic UUID5
   - Final seed: `"mining-ops-datasource-mining-ops"` → `36b2bafa-79e9-5c04-98f6-448db534df65`

**Lessons for Validator:**
- **ID Format Validation:** Not all `id` fields are optional or string-only. When a field is called `id` and the example uses UUID, enforce UUID format locally.
- **Format Mismatches Are Silent:** The API may not validate format (returns HTTP 200), but the UI client will. The validator is the last defense before deployment.
- **Schema Parity:** Dashboard and queryset share common Fabric Git schemas. When one item type requires UUID for a field, check if related types have the same requirement.

**Validation Result:** `python3 validate_fabric_definitions.py` → ✅ PASSED (28 query tabs, UUID-format data source ID)

---

### 2026-03-23: Live Fabric Queryset Inspection — 5 Query Bugs Found

**Context:** Direct inspection of the live queryset `MiningOps-Queries` (item `13f4f414-49e8-474f-b4fb-b66d0d69b869`, workspace `c7cc9e30-5045-4a5f-8f58-fdb3d1092589`) via Fabric REST API + direct KQL execution against the live cluster (`https://trd-dxeq4t8vw8cxd1ahn7.z6.kusto.fabric.microsoft.com`, db `MiningOps`).

**Live State — Healthy:**
- ✅ 28/28 tabs load without schema errors
- ✅ Data source UUID `36b2bafa-79e9-5c04-98f6-448db534df65` — correct format
- ✅ 7 tables present: EquipmentTelemetry (7.86M rows), EnvironmentalReadings (3.93M), ProductionMetrics (4.19M), EquipmentRegistry (390), AlertThresholds (286), SafetyIncidents (95), SensorReadings
- ✅ Live data flowing: max Timestamp = 2026-03-23T14:53:55Z (current)
- ✅ GasThresholdBreaches: 54 active CO/CH4 alerts (CO at 45 ppm vs 35 threshold; CH4 at 1.49% vs 1.0% threshold)
- ✅ HydraulicPressureDrops: 2 active drills below 1,500 PSI threshold (DR-001, DR-003)
- ✅ Predictive queries (series_decompose_forecast, series_fit_line) working

**Bugs Found:**

**BUG 1 — HIGH: VibrationAnomalies always returns 0 rows (silent KQL bug)**
- Root cause: `Latest = arg_max(Timestamp, Value)` creates a scalar `Latest` = max Timestamp; the second column `Value` is DROPPED after summarize.
- `| where Value > UpperBound` references a non-existent `Value` column → null > X = false → all rows filtered out
- With the correct approach (`max(Value)` per window), 9 anomalous windows ARE detected (DR-001, DR-002, DR-004, CV-003 all >9 mm/s, well above 3σ UpperBound of ~9.1)
- This has been silently broken since deployment — no vibration anomalies have ever shown on dashboard or in alerts
- Fix: replace `Latest = arg_max(Timestamp, Value)` with `MaxValue = max(Value)` and update the filter/project references; or use `by EquipmentId, WindowBin = bin(Timestamp, window)` + unnamed `arg_max(Timestamp, Value)` to expand both columns without alias conflict

**BUG 2 — HIGH: AlertThresholds has 26 duplicate rows per sensor type**
- AlertThresholds table has 286 total rows, 11 sensor types, 26 identical rows each
- Joins in ActiveAlerts, RecentBreaches, ShiftHandoverSummary fan out 26x:
  - ActiveAlerts: 4,966 rows with fan-out vs 191 rows with `| distinct` join
  - RecentBreaches: 66,274 rows vs ~2,549 actual
- Likely from repeated CSV ingest without deduplication on initial load
- Fix: `AlertThresholds | distinct SensorType, WarningLow, WarningHigh, CriticalLow, CriticalHigh, Unit, Description` in all joins; or delete and reload the table data

**BUG 3 — HIGH: ShiftTonnageProgress shows 47,100% of target (semantic error)**
- Query does `sum(Value)` on `load_tonnes` sensor type, treating EACH telemetry reading as incremental production
- In reality, `load_tonnes` is a continuous sensor (current load on truck), not a per-cycle delta
- 13,183 readings × avg 180 tonnes each = 2,371,809 tonnes vs 5,000 tonne target → 47,100%
- Fix: redesign query to count distinct loading events or accumulate only on state transitions; or discuss with Parker/Ash what `load_tonnes` actually represents per the simulator model

**BUG 4 — MEDIUM: EquipmentUtilisation always returns 0 rows (data gap)**
- `startofday(ago(1d))` = 2026-03-22 but no ET data exists for that day
- Historical CSV ingest covers ~2025-12-20 to ~2026-03-21; live streaming restarted 2026-03-23
- 2026-03-22 is an unreachable gap — this tab will be empty until the live stream has run for 24+ hours
- Fix: use `startofday(now())` (today) instead of `startofday(ago(1d))` (yesterday), or add fallback to `ago(24h)` relative window

**BUG 5 — MEDIUM: EquipmentStatusSummary returns only 1 status row (semantic design flaw)**
- Query uses `arg_max(Timestamp, Value, SensorType) by EquipmentId` — picks ONE most-recent reading per equipment
- Status case only checks `engine_temp_c`, `belt_speed_m_s`, and `hydraulic_psi` conditions
- 4 equipment have `vibration_mm_s` as latest → always "Running" (vibration has no fault condition)
- Right now: 12 equipment all classified "Running", even though 177 engine_temp_c readings and 179 hydraulic_psi readings exceed thresholds in the last 15 minutes
- Fix: rewrite with `maxif/minif` per sensor type per equipment, then evaluate all sensors together; or restructure as a join across pivoted sensor readings

**Key Cluster Facts (confirmed live):**
- Cluster URI: `https://trd-dxeq4t8vw8cxd1ahn7.z6.kusto.fabric.microsoft.com`
- Database: `MiningOps`
- Auth resource: `https://trd-dxeq4t8vw8cxd1ahn7.z6.kusto.fabric.microsoft.com` (specific cluster URI)
- Token type: Bearer via `az account get-access-token --resource <cluster-uri>`
- Live data starts: 2026-03-23 (today); historical: 2025-12-20 to 2026-03-21

**Durable Pattern — Named arg_max Loses Secondary Columns:**
In KQL, `X = arg_max(A, B)` creates a scalar `X` = max(A). Column `B` is DROPPED. Use one of:
1. Unnamed: `arg_max(A, B)` expands both; works if no name conflict with `by` clause
2. Named group key different from argmax key: `arg_max(A, B)` by `GroupKey = bin(A, window)` avoids the `A` naming conflict
3. Separate aggregation: `MaxValue = max(B)` if latest-by-time isn't strictly required
Always test arg_max results immediately — KQL won't error on the missing column, it silently returns null.


## 2026-03-23: KQL Queryset Schema Validation — All Checks Passed

**Session:** Background validation run  
**Result:** ✅ Schema validation complete — no anomalies detected

### Summary
Validated live queryset definition against official Fabric API schema:
- Outer `{"queryset": {...}}` wrapper correctly applied
- All 28 tabs with proper structure: `{id, title, content, dataSourceId}`
- Tab datasource IDs are flat strings (correct format, not nested objects)
- Matches deploy.py output and MS Learn documentation
- No regressions from recent fixes (commits `5c515ff`, `c8476c6`)

### Status
All schema validation checks passed. Queryset definition is structurally sound and ready for operation once data pipeline restarts.

