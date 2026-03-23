# Mining Real-Time Intelligence — User Stories

## Personas

| ID | Persona | Role Summary |
|----|---------|-------------|
| P1 | **Operations Manager** | Oversees site-wide production, fleet utilisation, and shift KPIs |
| P2 | **Safety Officer** | Monitors environmental hazards and enforces regulatory compliance |
| P3 | **Equipment Engineer** | Maintains drills, conveyors, and haul trucks; plans preventive maintenance |
| P4 | **Data Analyst** | Builds reports, investigates trends, and supports decision-making |

---

## Epic 1 — Equipment Telemetry & Health

### US-1.1  Real-Time Equipment Dashboard
**As an** Operations Manager,
**I want** a live dashboard showing the status of every major asset (drills, conveyors, haul trucks) with key metrics (engine RPM, hydraulic pressure, speed, load weight),
**so that** I can see at a glance which equipment is running, idle, or in fault and make real-time dispatch decisions.

**Acceptance Criteria**
- Dashboard refreshes ≤ 30 s.
- Each asset shows status badge (Running / Idle / Fault / Maintenance).
- Clicking an asset drills into a 1-hour trend chart.

### US-1.2  Vibration Anomaly Detection
**As an** Equipment Engineer,
**I want** the system to automatically flag when vibration readings on a conveyor bearing exceed the rolling 15-minute average by more than 3 standard deviations,
**so that** I can schedule inspection before a catastrophic bearing failure occurs.

**Acceptance Criteria**
- Anomaly detected within 60 s of threshold breach.
- Notification includes equipment ID, sensor location, current value, and baseline.

### US-1.3  Hydraulic Pressure Drop Alert
**As an** Equipment Engineer,
**I want** an alert when any drill's hydraulic pressure drops below 1 500 PSI for more than 30 consecutive seconds,
**so that** I can dispatch maintenance before the drill becomes non-operational.

**Acceptance Criteria**
- Alert fires within 45 s of sustained pressure drop.
- Alert auto-resolves when pressure recovers above 1 600 PSI.

### US-1.4  Predictive Maintenance Score
**As an** Equipment Engineer,
**I want** a daily health score (0-100) for each haul truck calculated from engine temperature trends, oil pressure variance, and cumulative operating hours,
**so that** I can prioritise the maintenance schedule and avoid unplanned downtime.

**Acceptance Criteria**
- Score recalculated every 4 hours.
- Trucks scoring < 40 appear in a "Critical" queue.

---

## Epic 2 — Environmental & Safety Monitoring

### US-2.1  Gas Level Threshold Breach
**As a** Safety Officer,
**I want** an immediate alert when CO or CH₄ concentrations exceed regulatory thresholds (CO > 35 ppm TWA, CH₄ > 1.0 % LEL) at any underground sensor station,
**so that** I can initiate evacuation or ventilation procedures within the mandated response window.

**Acceptance Criteria**
- Alert latency ≤ 15 s from reading.
- Alert sent via Teams, email, and SMS simultaneously.
- Includes zone ID, gas type, reading, and threshold.

### US-2.2  Temperature Exceedance Monitoring
**As a** Safety Officer,
**I want** to see a heat-map of ambient temperature readings across all zones, highlighting any zone exceeding 35 °C wet-bulb,
**so that** I can rotate crews or suspend work in overheated areas.

**Acceptance Criteria**
- Heat-map updated every 60 s.
- Zones above threshold shown in red with audible browser alert.

### US-2.3  Safety Incident Correlation
**As a** Data Analyst,
**I want** to query environmental conditions (gas, temperature, dust, humidity) in the 30-minute window before any recorded safety event,
**so that** I can identify environmental precursors to incidents and recommend control improvements.

**Acceptance Criteria**
- Query returns time-series data joined to incident records.
- Results exportable to CSV.

---

## Epic 3 — Production Throughput

### US-3.1  Real-Time Tonnage Tracking
**As an** Operations Manager,
**I want** a live counter showing tonnes mined, tonnes hauled, and tonnes processed per shift with comparison to the shift target,
**so that** I can identify shortfalls early and re-allocate resources during the shift.

**Acceptance Criteria**
- Counters update every 60 s.
- Red/amber/green colouring against target (< 80 % red, 80-95 % amber, ≥ 95 % green).

### US-3.2  Conveyor Throughput Analysis
**As a** Data Analyst,
**I want** to trend conveyor belt load (kg/m) and speed (m/s) over the past 7 days with overlaid production targets,
**so that** I can identify bottleneck periods and recommend conveyor tuning.

**Acceptance Criteria**
- 1-minute granularity available.
- Ability to filter by conveyor ID and shift.

### US-3.3  Haul Truck Cycle Time
**As an** Operations Manager,
**I want** to see average load-haul-dump cycle times per truck and per route,
**so that** I can optimise fleet routing and detect trucks operating below efficiency benchmarks.

**Acceptance Criteria**
- Cycle time broken into load, travel-loaded, dump, travel-empty segments.
- Trucks with cycle time > 120 % of route average flagged.

---

## Epic 4 — Operational Analytics

### US-4.1  Equipment Utilisation Report
**As a** Data Analyst,
**I want** a daily report showing utilisation rate (operating hours / available hours) for every major asset,
**so that** management can benchmark fleet efficiency and justify capital expenditure.

**Acceptance Criteria**
- Report available by 06:00 for previous day.
- Breakdown by equipment type and individual asset.

### US-4.2  Shift Handover Summary
**As an** Operations Manager,
**I want** an auto-generated shift summary including total production, active alerts, equipment faults, and top 5 anomalies,
**so that** the incoming shift supervisor has full situational awareness.

**Acceptance Criteria**
- Summary generated at each shift change (06:00, 14:00, 22:00).
- Delivered as a dashboard page and optional email.

### US-4.3  Active Alerts
**As a** Data Analyst,
**I want** a live table of current critical alerts from the last 15 minutes,
**so that** I can investigate active safety and equipment issues quickly.

**Acceptance Criteria**
- Table refreshes every 15 s.
- Includes timestamp, zone, sensor, value, threshold, and severity.
- Query is available in the Fabric workspace KQL Queryset.
