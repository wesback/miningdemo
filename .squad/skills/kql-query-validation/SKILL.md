---
name: "KQL Query Semantic Validation"
description: "Detect silent KQL semantic bugs that return 0 rows or wrong data without throwing errors — arg_max column loss, join fan-out, sensor accumulation errors."
domain: "kql"
confidence: "high"
source: "earned"
tools:
  - name: "bash"
    description: "Execute live KQL queries against the Kusto cluster to validate query output"
    when: "Verifying that a query returns expected data (not just executes without error)"
  - name: "view"
    description: "Read KQL files to inspect query logic"
    when: "Auditing KQL query design for semantic correctness"
---

## Context

KQL queries can execute successfully and return 0 rows (or wildly wrong numbers) without throwing any errors. These are the most dangerous query bugs — they silently pass syntax checks, pass schema validation, and deploy successfully, but produce incorrect results at runtime.

This skill covers the 3 most common patterns found in the Mining RTI Demo live queryset inspection (2026-03-23).

---

## Pattern 1: Named arg_max Loses Secondary Columns

**The Bug:**
```kql
| summarize
    Avg = avg(Value),
    Latest = arg_max(Timestamp, Value)  // ← WRONG: Value is DROPPED
  by EquipmentId, bin(Timestamp, 15m)
| where Value > Avg  // ← Value is null here → always false → 0 rows
```

When you write `Name = arg_max(A, B)`, the result `Name` is a scalar containing the max value of `A`. Column `B` is silently dropped. `| where B > X` then evaluates null > X = false for every row.

**The Fix:**
```kql
// Option 1: max(Value) per window (slightly different semantics — max not latest)
| summarize
    Avg = avg(Value),
    MaxValue = max(Value)
  by EquipmentId, WindowBin = bin(Timestamp, 15m)
| where MaxValue > Avg

// Option 2: Unnamed arg_max with distinct group key (avoids Timestamp name conflict)
| summarize
    Avg = avg(Value),
    arg_max(Timestamp, Value)    // ← expands both Timestamp and Value columns
  by EquipmentId, WindowBin = bin(Timestamp, 15m)  // ← 'WindowBin' avoids conflict
| where Value > Avg
```

**Detection:** Run the query and if row count = 0, add `| project` to inspect all columns after summarize. A null column where you expect a value confirms this bug.

---

## Pattern 2: Reference Table Fan-Out from Duplicate Rows

**The Bug:**
```kql
EnvironmentalReadings
| join kind=inner (AlertThresholds) on SensorType  // ← AlertThresholds has 26 rows per SensorType
| where Value > CriticalHigh
```

If a reference table has N duplicate rows per key, every join produces N × actual_rows output rows. The query appears to work (returns data) but results are wildly inflated.

**Detection:** 
```kql
AlertThresholds | summarize count() by SensorType  // ← should be 1 per type
```
If count > 1, you have duplicates.

**Fix (preferred — fix at source):**
```kql
// Use .set-or-replace with a canonical datatable to atomically replace the entire table.
// This is the production fix — it's idempotent, atomic, and eliminates the root cause.
// Run directly against the live database in a KQL Queryset.
.set-or-replace AlertThresholds <|
datatable(SensorType:string, WarningLow:real, WarningHigh:real, CriticalLow:real, CriticalHigh:real, Unit:string, Description:string) [
  // ... canonical rows ...
]
```

**Verify after fix:**
```kql
AlertThresholds
| summarize TotalRows = count(), UniqueSensorTypes = dcount(SensorType)
| extend IsClean = (TotalRows == UniqueSensorTypes)
// Expected: TotalRows == UniqueSensorTypes == IsClean == true
```

**Fix (query-level workaround only — use when you can't touch the table):**
```kql
| join kind=inner (AlertThresholds | distinct SensorType, CriticalLow, CriticalHigh) on SensorType
```

**Note:** `.set-or-replace` is safe to run on a live table — it is atomic. Queries will see either the old full set or the new clean set; no partial state. Applied live to MiningOps AlertThresholds on 2026-03-23: reduced from 286 rows (26 duplicates × 11 types) to 11 canonical rows.

---

## Pattern 3: Continuous Sensor Treated as Accumulating Delta

**The Bug:**
```kql
ProductionMetrics
| where SensorType == "load_tonnes" and Timestamp > shift_start
| summarize TotalTonnes = sum(Value)  // ← summing continuous load readings, not events
```

If `load_tonnes` emits the truck's CURRENT payload (e.g., 180 tonnes) every 5 seconds, then:
- 7 hours × 720 readings × 180 tonnes = 907,200 tonnes — clearly wrong

**Detection:** Check `avg(Value)` and `count()` together. If avg >> expected per-event value OR count × avg >> physical max, it's a continuous sensor.

**Fix:** Redesign to count state transitions (empty→loaded events) rather than accumulating raw values.

---

## Validation Checklist for KQL Queries

Run these checks before deploying or signing off on any KQL query:

1. **arg_max check:** Any `arg_max` that is NAMED (`X = arg_max(A, B)`) — verify `B` columns are accessible after summarize. Test by projecting all columns.
2. **Reference table row count:** Any join on a reference/lookup table — verify `| summarize count() by <join_key>` returns 1 per key.
3. **Aggregation semantics:** Any `sum(Value)` — verify the sensor is a delta (per-event) not a continuous reading. Check: does avg × count make physical sense?
4. **Time window returns data:** For any `| where Timestamp > ago(Xh)` or `between` — verify data actually exists in that window: `| where ... | count`.
5. **Case/switch completeness:** Any `case()` status classification — verify all possible input values are handled. Especially important when joining sensor types that don't appear in any `case` branch.

---

## Examples from Mining RTI Demo

| Tab | Bug | Fix |
|-----|-----|-----|
| VibrationAnomalies | `Latest = arg_max(Timestamp, Value)` → Value null → 0 rows always | Replace with `MaxValue = max(Value)` |
| ActiveAlerts/RecentBreaches | AlertThresholds has 26x duplicate rows → 26x fan-out | `| distinct SensorType, CriticalLow, CriticalHigh` in join |
| ShiftTonnageProgress | `sum(load_tonnes)` accumulates continuous readings → 47,100% of target | Redesign around loading events |
