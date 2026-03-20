# Data Activator — Alert Rule Definitions
# Import these as Reflex items in the Fabric Data Activator experience.
# Each rule maps to a safety-critical user story.

## Rule 1 — Gas Breach: Carbon Monoxide (US-2.1)

```yaml
name: "Gas Breach — CO"
description: "CO concentration exceeds 35 ppm TWA at any sensor station"
source:
  type: eventstream
  object: EnvironmentalReadings
filter:
  conditions:
    - field: SensorType
      operator: equals
      value: "co_ppm"
    - field: Quality
      operator: equals
      value: "good"
trigger:
  type: threshold
  field: Value
  operator: greaterThan
  value: 35
  aggregation: none          # per-event evaluation
  sustained_duration: null   # fire immediately
  cooldown_minutes: 5        # suppress duplicate alerts for 5 min
severity: critical
actions:
  - type: teams_message
    target: "Mining Safety Channel"
    template: |
      🚨 **CRITICAL: CO Level Breach**
      - **Zone:** {{Zone}}
      - **Sensor:** {{EquipmentId}}
      - **Reading:** {{Value}} ppm (Threshold: 35 ppm)
      - **Time:** {{Timestamp}}
      - **Action Required:** Initiate ventilation check / evacuation protocol
  - type: email
    recipients:
      - safety-officer@miningcorp.com
      - shift-supervisor@miningcorp.com
    subject: "🚨 CRITICAL: CO Level Breach in {{Zone}}"
```

## Rule 2 — Gas Breach: Methane (US-2.1)

```yaml
name: "Gas Breach — CH₄"
description: "Methane exceeds 1.0% LEL at any sensor station"
source:
  type: eventstream
  object: EnvironmentalReadings
filter:
  conditions:
    - field: SensorType
      operator: equals
      value: "ch4_pct"
    - field: Quality
      operator: equals
      value: "good"
trigger:
  type: threshold
  field: Value
  operator: greaterThan
  value: 1.0
  aggregation: none
  sustained_duration: null
  cooldown_minutes: 5
severity: critical
actions:
  - type: teams_message
    target: "Mining Safety Channel"
    template: |
      🚨 **CRITICAL: Methane Level Breach**
      - **Zone:** {{Zone}}
      - **Sensor:** {{EquipmentId}}
      - **Reading:** {{Value}} %LEL (Threshold: 1.0%)
      - **Time:** {{Timestamp}}
      - **Action Required:** Shut down ignition sources / initiate evacuation
  - type: email
    recipients:
      - safety-officer@miningcorp.com
      - shift-supervisor@miningcorp.com
    subject: "🚨 CRITICAL: CH₄ Level Breach in {{Zone}}"
```

## Rule 3 — High Temperature Zone (US-2.2)

```yaml
name: "High Temperature Zone"
description: "Ambient temperature exceeds 35°C wet-bulb in any zone"
source:
  type: eventstream
  object: EnvironmentalReadings
filter:
  conditions:
    - field: SensorType
      operator: equals
      value: "ambient_temp_c"
    - field: Quality
      operator: equals
      value: "good"
trigger:
  type: threshold
  field: Value
  operator: greaterThan
  value: 35
  aggregation: average
  window_minutes: 5
  sustained_duration: null
  cooldown_minutes: 15
severity: warning
actions:
  - type: teams_message
    target: "Mining Ops Channel"
    template: |
      ⚠️ **WARNING: High Temperature Zone**
      - **Zone:** {{Zone}}
      - **Reading:** {{Value}} °C (Threshold: 35°C)
      - **Time:** {{Timestamp}}
      - **Action:** Consider crew rotation or work suspension
  - type: email
    recipients:
      - safety-officer@miningcorp.com
    subject: "⚠️ High Temperature Alert — {{Zone}}"
```

## Rule 4 — Vibration Anomaly (US-1.2)

```yaml
name: "Vibration Anomaly"
description: "Conveyor vibration exceeds 3σ above 15-min rolling average"
source:
  type: kql_query
  database: MiningOps
  query: |
    EquipmentTelemetry
    | where SensorType == "vibration_mm_s"
        and EquipmentType == "conveyor"
        and Timestamp > ago(15m)
        and Quality == "good"
    | summarize Avg = avg(Value), Std = stdev(Value), Latest = arg_max(Timestamp, Value)
      by EquipmentId
    | where Latest_Value > (Avg + 3 * Std)
    | project EquipmentId, LatestValue = Latest_Value,
              Avg = round(Avg, 2), UpperBound = round(Avg + 3 * Std, 2),
              Deviation = round((Latest_Value - Avg) / Std, 1),
              Timestamp = Latest_Timestamp
  evaluation_interval_minutes: 1
trigger:
  type: row_count
  operator: greaterThan
  value: 0
  cooldown_minutes: 10
severity: warning
actions:
  - type: teams_message
    target: "Equipment Engineering Channel"
    template: |
      ⚠️ **Vibration Anomaly Detected**
      - **Equipment:** {{EquipmentId}}
      - **Latest Reading:** {{LatestValue}} mm/s
      - **15-min Avg:** {{Avg}} mm/s | **Upper Bound (3σ):** {{UpperBound}} mm/s
      - **Deviation:** {{Deviation}}σ
      - **Time:** {{Timestamp}}
      - **Action:** Schedule bearing inspection
  - type: email
    recipients:
      - equipment-engineer@miningcorp.com
    subject: "⚠️ Vibration Anomaly — {{EquipmentId}}"
```

## Rule 5 — Hydraulic Pressure Drop (US-1.3)

```yaml
name: "Hydraulic Pressure Low"
description: "Drill hydraulic pressure < 1500 PSI sustained for 30+ seconds"
source:
  type: kql_query
  database: MiningOps
  query: |
    EquipmentTelemetry
    | where SensorType == "hydraulic_psi"
        and EquipmentType == "drill"
        and Timestamp > ago(2m)
        and Quality == "good"
    | summarize
        MinPressure = min(Value),
        AvgPressure = round(avg(Value), 0),
        BelowCount = countif(Value < 1500),
        TotalCount = count(),
        Duration_s = datetime_diff('second', max(Timestamp), min(Timestamp))
      by EquipmentId
    | where BelowCount == TotalCount and Duration_s >= 30
    | project EquipmentId, MinPressure, AvgPressure, Duration_s
  evaluation_interval_minutes: 1
trigger:
  type: row_count
  operator: greaterThan
  value: 0
  cooldown_minutes: 5
severity: critical
actions:
  - type: teams_message
    target: "Equipment Engineering Channel"
    template: |
      🚨 **CRITICAL: Hydraulic Pressure Drop**
      - **Equipment:** {{EquipmentId}}
      - **Min Pressure:** {{MinPressure}} PSI (Threshold: 1500 PSI)
      - **Avg Pressure:** {{AvgPressure}} PSI
      - **Duration:** {{Duration_s}} seconds
      - **Action Required:** Dispatch maintenance immediately
  - type: email
    recipients:
      - equipment-engineer@miningcorp.com
      - shift-supervisor@miningcorp.com
    subject: "🚨 Hydraulic Pressure Drop — {{EquipmentId}}"
```

## Rule 6 — Truck Health Critical (US-1.4)

```yaml
name: "Truck Health Critical"
description: "Haul truck composite health score drops below 40"
source:
  type: kql_query
  database: MiningOps
  query: |
    // Reuses the EquipmentHealthScores query logic (see 03-queries.kql)
    let temp_weight = 0.35; let oil_weight = 0.35; let age_weight = 0.30;
    let TempScores = EquipmentTelemetry
        | where SensorType == "engine_temp_c" and EquipmentType == "haul_truck"
            and Timestamp > ago(4h) and Quality == "good"
        | summarize AvgTemp = avg(Value) by EquipmentId
        | extend TempScore = max_of(0.0, min_of(100.0, (110.0 - AvgTemp) / 0.3));
    let OilScores = EquipmentTelemetry
        | where SensorType == "oil_pressure_kpa" and EquipmentType == "haul_truck"
            and Timestamp > ago(4h) and Quality == "good"
        | summarize AvgOil = avg(Value), StdOil = stdev(Value) by EquipmentId
        | extend OilScore = max_of(0.0, min_of(100.0, 100.0 - (StdOil / AvgOil) * 200.0));
    let AgeScores = EquipmentRegistry
        | where EquipmentType == "haul_truck"
        | extend YearsOld = 2026 - YearCommissioned
        | extend AgeScore = max_of(0.0, 100.0 - (YearsOld * 10.0));
    TempScores
    | join kind=leftouter OilScores on EquipmentId
    | join kind=leftouter AgeScores on EquipmentId
    | extend HealthScore = round(
        (coalesce(TempScore,50) * temp_weight) +
        (coalesce(OilScore,50) * oil_weight) +
        (coalesce(AgeScore,50) * age_weight), 0)
    | where HealthScore < 40
    | project EquipmentId, HealthScore
  evaluation_interval_minutes: 60
trigger:
  type: row_count
  operator: greaterThan
  value: 0
  cooldown_minutes: 240
severity: warning
actions:
  - type: teams_message
    target: "Equipment Engineering Channel"
    template: |
      ⚠️ **Truck Health Score Critical**
      - **Truck:** {{EquipmentId}}
      - **Health Score:** {{HealthScore}} / 100
      - **Action:** Prioritise for maintenance queue
```

## Rule 7 — Conveyor Stoppage (US-3.2)

```yaml
name: "Conveyor Stoppage"
description: "Conveyor belt speed at 0 m/s for 60+ consecutive seconds"
source:
  type: kql_query
  database: MiningOps
  query: |
    ProductionMetrics
    | where SensorType == "belt_speed_m_s"
        and Timestamp > ago(2m)
        and Quality == "good"
    | summarize
        MinSpeed = min(Value),
        MaxSpeed = max(Value),
        Duration_s = datetime_diff('second', max(Timestamp), min(Timestamp))
      by EquipmentId
    | where MaxSpeed == 0 and Duration_s >= 60
    | project EquipmentId, Duration_s
  evaluation_interval_minutes: 1
trigger:
  type: row_count
  operator: greaterThan
  value: 0
  cooldown_minutes: 10
severity: warning
actions:
  - type: teams_message
    target: "Mining Ops Channel"
    template: |
      ⚠️ **Conveyor Stoppage Detected**
      - **Conveyor:** {{EquipmentId}}
      - **Stopped for:** {{Duration_s}} seconds
      - **Action:** Investigate cause — potential belt jam or motor fault
```
