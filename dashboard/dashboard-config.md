# Real-Time Dashboard — Tile Configuration
# This file documents every dashboard tile, its visual type, data source query,
# and configuration. Use it as a blueprint when building in the Fabric portal.

## Dashboard: Mining Operations — Real-Time Intelligence

---

## Page 1: Operations Overview

### Tile 1.1 — Active Equipment Count (Stat Cards)
- **Visual type:** Multi-stat card (3 cards: Running / Idle / Fault)
- **Auto-refresh:** 30 seconds
- **KQL Query:**
```kql
let cutoff = ago(2m);
EquipmentTelemetry
| where Timestamp > cutoff and Quality == "good"
| summarize arg_max(Timestamp, Value, SensorType) by EquipmentId
| extend Status = case(
    SensorType == "engine_temp_c" and Value > 105, "Fault",
    SensorType == "engine_temp_c" and Value < 30,  "Idle",
    SensorType == "belt_speed_m_s" and Value == 0,  "Idle",
    SensorType == "hydraulic_psi" and Value < 500,  "Idle",
    "Running")
| summarize Count = count() by Status
```
- **Conditional formatting:** Running = green, Idle = amber, Fault = red

### Tile 1.2 — Shift Tonnage vs Target (Bar Chart)
- **Visual type:** Grouped bar chart
- **Auto-refresh:** 60 seconds
- **KQL Query:**
```kql
let shift_start = bin(now(), 8h);
let shift_target = 5000.0;
ProductionMetrics
| where SensorType == "load_tonnes" and Timestamp > shift_start and Quality == "good"
| summarize TotalTonnes = round(sum(Value), 0) by EquipmentType
| extend Target = shift_target
| extend PctOfTarget = round(TotalTonnes / Target * 100, 1)
```
- **X-axis:** EquipmentType
- **Y-axis:** TotalTonnes, Target (dual series)
- **Conditional formatting:** < 80% red bar, 80-95% amber, ≥ 95% green

### Tile 1.3 — Equipment Status Map (Map Visual)
- **Visual type:** Map (bubble)
- **Auto-refresh:** 30 seconds
- **KQL Query:**
```kql
let cutoff = ago(5m);
EquipmentTelemetry
| where Timestamp > cutoff and Quality == "good"
| summarize arg_max(Timestamp, *) by EquipmentId
| join kind=leftouter (EquipmentRegistry | project EquipmentId, Make, Model) on EquipmentId
| project EquipmentId, EquipmentType, Latitude, Longitude, Zone, Make, Model, Value, SensorType
```
- **Latitude field:** Latitude
- **Longitude field:** Longitude
- **Bubble size:** fixed
- **Bubble colour:** by EquipmentType
- **Tooltip:** EquipmentId, Make, Model, Zone, SensorType, Value

### Tile 1.4 — Active Alerts (Table)
- **Visual type:** Table
- **Auto-refresh:** 15 seconds
- **KQL Query:**
```kql
let cutoff = ago(15m);
EnvironmentalReadings
| where Timestamp > cutoff and Quality == "good"
| join kind=inner (AlertThresholds) on SensorType
| where Value > CriticalHigh or Value < CriticalLow
| project Timestamp, Zone, SensorType, Value, Unit,
          Threshold = iff(Value > CriticalHigh, strcat("> ", tostring(CriticalHigh)),
                                                  strcat("< ", tostring(CriticalLow))),
          Severity = "Critical"
| union (
    EquipmentTelemetry
    | where Timestamp > cutoff and Quality == "good"
    | where (SensorType == "hydraulic_psi" and Value < 1500)
         or (SensorType == "engine_temp_c" and Value > 105)
    | project Timestamp, Zone, SensorType, Value,
              Unit = iff(SensorType == "hydraulic_psi", "PSI", "°C"),
              Threshold = iff(SensorType == "hydraulic_psi", "< 1500", "> 105"),
              Severity = "Critical"
)
| order by Timestamp desc
| take 20
```
- **Row highlight:** All rows red background (critical only table)

---

## Page 2: Safety & Environment

### Tile 2.1 — Gas Levels by Zone (Multi-Line Chart)
- **Visual type:** Line chart (multi-series)
- **Auto-refresh:** 15 seconds
- **KQL Query:**
```kql
EnvironmentalReadings
| where SensorType in ("co_ppm", "ch4_pct")
    and Timestamp > ago(2h) and Quality == "good"
| summarize AvgValue = round(avg(Value), 2)
  by Zone, SensorType, bin(Timestamp, 1m)
| order by Timestamp asc
```
- **X-axis:** Timestamp
- **Y-axis:** AvgValue
- **Series:** Zone + SensorType
- **Reference lines:** CO = 35 ppm (red dashed), CH₄ = 1.0% (red dashed)

### Tile 2.2 — Temperature Heat Map
- **Visual type:** Table with conditional formatting (acts as heat map)
- **Auto-refresh:** 60 seconds
- **KQL Query:**
```kql
EnvironmentalReadings
| where SensorType == "ambient_temp_c" and Timestamp > ago(5m) and Quality == "good"
| summarize AvgTemp = round(avg(Value), 1), MaxTemp = round(max(Value), 1) by Zone
| extend Status = case(MaxTemp > 35, "CRITICAL", MaxTemp > 32, "WARNING", "NORMAL")
| order by MaxTemp desc
```
- **Conditional formatting:** CRITICAL = red bg, WARNING = amber bg, NORMAL = green bg

### Tile 2.3 — Threshold Breaches 24h (Table)
- **Visual type:** Table
- **Auto-refresh:** 30 seconds
- **KQL Query:**
```kql
EnvironmentalReadings
| where Timestamp > ago(24h) and Quality == "good"
| join kind=inner (AlertThresholds) on SensorType
| where Value > CriticalHigh or Value < CriticalLow
| project Timestamp, Zone, SensorType, Value, Unit,
          Threshold = iff(Value > CriticalHigh, CriticalHigh, CriticalLow),
          Direction = iff(Value > CriticalHigh, "ABOVE", "BELOW")
| order by Timestamp desc
| take 50
```

### Tile 2.4 — Safety Incident Timeline
- **Visual type:** Table (timeline not native; use sorted table)
- **Auto-refresh:** 5 minutes
- **KQL Query:**
```kql
SafetyIncidents
| order by Timestamp desc
| project Timestamp, Zone, Severity, Description, EquipmentId
| take 20
```

---

## Page 3: Equipment Health

### Tile 3.1 — Vibration Anomaly Trend (Scatter Chart)
- **Visual type:** Scatter
- **Auto-refresh:** 30 seconds
- **KQL Query:**
```kql
let sigma_threshold = 3.0;
EquipmentTelemetry
| where SensorType == "vibration_mm_s" and Timestamp > ago(4h) and Quality == "good"
| summarize AvgValue = avg(Value), StdValue = stdev(Value),
            MaxValue = max(Value), MinValue = min(Value)
  by EquipmentId, Bin = bin(Timestamp, 1m)
| extend UpperBound = AvgValue + (sigma_threshold * StdValue)
| extend IsAnomaly = MaxValue > UpperBound
| project Bin, EquipmentId, AvgValue = round(AvgValue, 2),
          MaxValue = round(MaxValue, 2), UpperBound = round(UpperBound, 2), IsAnomaly
```
- **X-axis:** Bin (time)
- **Y-axis:** MaxValue
- **Colour:** IsAnomaly (true = red, false = blue)
- **Series:** EquipmentId

### Tile 3.2 — Drill Hydraulic Pressure (Line Chart)
- **Visual type:** Line chart
- **Auto-refresh:** 30 seconds
- **KQL Query:**
```kql
EquipmentTelemetry
| where SensorType == "hydraulic_psi" and EquipmentType == "drill"
    and Timestamp > ago(1h) and Quality == "good"
| summarize AvgPressure = round(avg(Value), 0) by EquipmentId, bin(Timestamp, 30s)
| order by Timestamp asc
```
- **Reference line:** 1500 PSI (red dashed — critical low)

### Tile 3.3 — Equipment Health Scores (Conditional Table)
- **Visual type:** Table with conditional formatting
- **Auto-refresh:** 4 hours (manual or scheduled)
- **KQL Query:** (full EquipmentHealthScores query from 03-queries.kql)
- **Conditional formatting:** Critical (< 40) = red, Warning (40-69) = amber, Healthy (≥ 70) = green

### Tile 3.4 — Equipment Utilisation (Bar Chart)
- **Visual type:** Horizontal bar
- **Auto-refresh:** 5 minutes
- **KQL Query:**
```kql
let report_day = startofday(ago(1d));
EquipmentTelemetry
| where Timestamp between (report_day .. (report_day + 1d)) and Quality == "good"
| summarize ActiveMinutes = dcount(bin(Timestamp, 1m)) by EquipmentId, EquipmentType
| extend UtilisationPct = round(ActiveMinutes / 1440.0 * 100, 1)
| order by UtilisationPct desc
```
- **X-axis:** EquipmentId
- **Y-axis:** UtilisationPct
- **Reference line:** 80% target (green dashed)

---

## Page 4: Production

### Tile 4.1 — Conveyor Throughput Trend (Area Chart)
- **Visual type:** Area chart
- **Auto-refresh:** 60 seconds
- **KQL Query:**
```kql
ProductionMetrics
| where SensorType in ("belt_load_kg_m", "belt_speed_m_s")
    and Timestamp > ago(7d) and Quality == "good"
| summarize AvgValue = round(avg(Value), 2)
  by EquipmentId, SensorType, bin(Timestamp, 1m)
| order by Timestamp asc
```
- **X-axis:** Timestamp
- **Y-axis:** AvgValue
- **Series:** EquipmentId + SensorType

### Tile 4.2 — Haul Truck Cycle Times (Grouped Bar)
- **Visual type:** Grouped bar chart
- **Auto-refresh:** 5 minutes
- **KQL Query:**
```kql
ProductionMetrics
| where SensorType == "cycle_state" and EquipmentType == "haul_truck"
    and Timestamp > ago(24h) and Quality == "good"
| extend CyclePhase = case(
    Value == 1, "Loading", Value == 2, "Travel-Loaded",
    Value == 3, "Dumping", Value == 4, "Travel-Empty", "Unknown")
| where CyclePhase != "Unknown"
| summarize PhaseDuration_min = round(
    datetime_diff('second', max(Timestamp), min(Timestamp)) / 60.0, 1)
  by EquipmentId, CyclePhase, bin(Timestamp, 1h)
| summarize AvgDuration_min = round(avg(PhaseDuration_min), 1)
  by EquipmentId, CyclePhase
```
- **X-axis:** EquipmentId
- **Y-axis:** AvgDuration_min
- **Group by:** CyclePhase

### Tile 4.3 — Route Efficiency (Table)
- **Visual type:** Table
- **Auto-refresh:** 5 minutes
- **KQL Query:** (RouteEfficiency from 03-queries.kql)
- **Conditional formatting:** Flagged = true → red row highlight

### Tile 4.4 — 7-Day Production Trend (Line Chart)
- **Visual type:** Line chart
- **Auto-refresh:** 15 minutes
- **KQL Query:**
```kql
ProductionMetrics
| where SensorType == "load_tonnes" and Timestamp > ago(7d) and Quality == "good"
| summarize DailyTonnes = round(sum(Value), 0) by Day = startofday(Timestamp)
| order by Day asc
```
- **X-axis:** Day
- **Y-axis:** DailyTonnes
- **Reference line:** Daily target (dotted)
