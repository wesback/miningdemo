# Skill: KQL arg_max Patterns and Continuous-Sensor Aggregation

## Problem
Two classes of KQL aggregation mistakes produce silent empty results or wildly inflated numbers in real-time dashboards.

## Pattern 1: Named arg_max drops secondary columns

### Bug
```kql
| summarize Latest = arg_max(Timestamp, Value) by EquipmentId, bin(Timestamp, 15m)
| where Value > Threshold  -- Value doesn't exist! It's Latest_Value
```
When arg_max is aliased (`Latest = arg_max(...)`), secondary columns are prefixed with the alias. `Value` becomes `Latest_Value`. Any reference to `Value` silently resolves to null → 0 rows returned.

### Fix
```kql
| summarize (LastTs, LatestValue) = arg_max(Timestamp, Value) by EquipmentId, bin(Timestamp, 15m)
| where LatestValue > Threshold  -- explicit, unambiguous
```

### Rule
**Always use tuple form** for named arg_max. Audit every `Alias = arg_max(X, Y)` in the codebase.

---

## Pattern 2: Summing continuous sensor readings for business totals

### Bug
```kql
| where SensorType == "load_tonnes"
| summarize TotalTonnes = sum(Value) by EquipmentType
-- A truck carrying 80 t reporting every second = 288,000 t/hr in the sum
```
`load_tonnes` is a point-in-time reading (current weight on the truck), not an event. Summing it multiplies by reporting frequency, not by load count.

### Fix — count discrete events
```kql
// cycle_state 3 = Dumping = one completed load delivery
let dump_events = ProductionMetrics
    | where SensorType == "cycle_state" and Value == 3.0
    | summarize DumpCount = count() by EquipmentType;
let avg_payload = ProductionMetrics
    | where SensorType == "load_tonnes" and Value > 5
    | summarize AvgPayload = avg(Value) by EquipmentType;
dump_events
| join kind=leftouter avg_payload on EquipmentType
| extend TotalTonnes = round(DumpCount * coalesce(AvgPayload, 50.0), 0)
```

### Rule
For business metrics (shift target, daily trend), identify the **discrete event** that represents "one unit of work completed" and count those, not the continuous readings.

---

## Pattern 3: Single-key arg_max misses sensor type diversity

### Bug
```kql
| summarize arg_max(Timestamp, Value, SensorType) by EquipmentId
| extend Status = case(SensorType == "engine_temp_c" and Value > 105, "Fault", ...)
-- Only checks whichever sensor fired most recently per equipment
```

### Fix — get latest per sensor type, then aggregate
```kql
| summarize (LastTs, LastValue) = arg_max(Timestamp, Value) by EquipmentId, EquipmentType, SensorType
| extend SensorStatus = case(SensorType == "engine_temp_c" and LastValue > 105, "Fault", ...)
| summarize Status = case(
    countif(SensorStatus == "Fault") > 0, "Fault",
    countif(SensorStatus == "Idle") > 0, "Idle",
    "Running"
) by EquipmentId, EquipmentType
```

---

## Pattern 4: Calendar-day windows in fresh demo environments

### Bug
```kql
let report_day = startofday(ago(1d));  -- yesterday = empty gap in demo data
| where Timestamp between (report_day .. (report_day + 1d))
```

### Fix
```kql
let window_start = ago(24h);  -- rolling, spans CSV history + live stream
| where Timestamp between (window_start .. now())
```

## Context
Applies to: KQL queries against Fabric Eventhouse, Azure Data Explorer, or any streaming telemetry pipeline where sensors emit continuous point-in-time readings (not discrete events).
