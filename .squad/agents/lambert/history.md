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
4. Dashboard query dataSourceId structure (flat field, not nested object)

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
