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
