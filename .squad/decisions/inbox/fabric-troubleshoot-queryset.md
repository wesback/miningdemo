# Decision: KQL Queryset — Two Semantic Errors Fixed

**Date:** 2026-03-27  
**Owner:** Parker (Azure/Fabric Troubleshooting)  
**Status:** Implemented  
**Impact:** KQL Queryset, Dashboard queries, Data quality

## Problem

The KQL queryset deployed via `deploy.py` contains 29 query tabs (21 production + 8 predictive). Two of the 21 production queries fail with KQL semantic errors when executed against the live MiningOps Eventhouse database.

## Root Causes (verified against live Fabric Eventhouse)

### Bug 1: VibrationAnomalies — `series_fir()` type mismatch + phantom column name

**Error:** `Semantic error: series_fir(): argument #1 was not of an expected data type: dynamic`

The `partition by EquipmentId` block calls `series_fir(Value, ...)` but `Value` is a scalar `real`, not a `dynamic` array. `series_fir()` is a time-series function that requires a dynamic array (from `make-series`). Additionally, the downstream code references `Latest_Value` which doesn't exist — `arg_max(Timestamp, Value)` with alias `Latest` produces columns `Latest` (datetime) and `Value` (real), not `Latest_Value`.

The entire `partition by` block was dead code: its output columns (`RollingAvg`, `RollingStd`) are never consumed by the subsequent `summarize`.

**Fix:** Removed the broken `partition by` block. Changed `Latest_Value` → `Value` in `where`, `project`, and expression references.

### Bug 2: IncidentEnvironmentalCorrelation — wrong join column naming

**Error:** `Semantic error: 'where' operator: Failed to resolve scalar expression named 'EnvironmentalReadings_Timestamp'`

When KQL joins two tables and both have a `Timestamp` column, the right-side column is renamed with a numeric suffix (`Timestamp1`), not a table-name prefix (`EnvironmentalReadings_Timestamp`). The table-name prefix form only works with explicit `$left.` / `$right.` syntax.

**Fix:** Changed `EnvironmentalReadings_Timestamp` → `Timestamp1`, `SafetyIncidents_Timestamp` → `Timestamp`.

## Verification

Both fixes validated by executing corrected queries against the live MiningOps database (cluster `trd-dxeq4t8vw8cxd1ahn7.z6.kusto.fabric.microsoft.com`). Results returned correctly with real data.

## Files Changed

- `kql/03-queries.kql` — VibrationAnomalies query (lines ~74-101) and IncidentEnvironmentalCorrelation query (lines ~255-271)

## Reusable Pattern

**KQL join column naming rule:** After a join, conflicting column names from the right side get a numeric suffix (`1`, `2`, ...), NOT a table-name prefix. The `TableName_Column` syntax only applies inside `$right.`/`$left.` references. Always run `| getschema` after a join to verify actual column names.

**`arg_max` column naming rule:** `summarize Alias = arg_max(Col1, Col2)` produces `Alias` (for Col1) and `Col2` (original name), not `Alias_Col2`. Only multi-column arg_max with 3+ extra columns uses the `Alias_ColN` naming pattern.
