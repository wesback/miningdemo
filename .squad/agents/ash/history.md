# Project Context

- **Owner:** Wesley Backelant
- **Project:** Mining Real-Time Intelligence Demo — Microsoft Fabric Real-Time Intelligence for mining operations monitoring
- **Stack:** Python (deploy.py, simulator), KQL, Microsoft Fabric (Eventhouse, Eventstream, Real-Time Dashboards, Data Activator), Azure Event Hubs, Fabric REST APIs
- **Created:** 2026-03-20

## Learnings

### 2026-03-20 — Code quality improvements to KQL queries
- **File:** `kql/04-predictive-queries.kql` — Added data sufficiency checks to RUL estimation (Query 4, lines ~97-145) and belt wear detection (Query 7, lines ~207-234). Both queries now validate minimum data points and timespan before executing ML functions, returning clear warning messages if insufficient data exists in fresh environments.
- **Pattern:** Use `let data_check` with `count()` and `datetime_diff()`, then wrap ML logic in `iff(has_sufficient_data, ..., datatable()[])` union pattern. This prevents empty/misleading results and provides actionable feedback.
- **File:** `kql/02-reference-data.kql` — Added dynamic incident date alternative (lines ~54-66) using `ago()` for relative timestamps. Maintains backward-compatible hardcoded dates as default; dynamic version available as commented code block for fresh demos.
- **File:** `kql/01-schema-setup.kql` — Documented idempotency behavior in header (lines ~1-12) and inline comments on first `.create table` and `.create-or-alter function`. Clarifies re-run expectations and safe alternatives (.create-merge, .create-or-alter).
- **Key insight:** KQL queries should be self-documenting about data requirements. Time-series ML functions (series_decompose_anomalies, series_fit_line, series_periods_detect) need sufficient historical data to produce meaningful results — checking this upfront improves demo reliability.

**Cross-team context:** Parker simultaneously hardened Python deployment logic (Event Hub retries, config validation, error recovery). Combined improvements ensure the demo is resilient from data generation through deployment.
