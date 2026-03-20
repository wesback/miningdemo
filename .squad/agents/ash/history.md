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

### 2026-03-20 — Historical data pipeline automation
- **File:** `simulator/deploy_history.py` — Created unified pipeline script that chains `generate_history.py` → `ingest_history.py` as a single operation. Supports configurable history depth (`--days N`, default 30), interval (`--interval SEC`, default 30), and three execution modes: full pipeline (generate + ingest), generation-only (`--skip-ingest`), and ingestion-only (`--skip-generate`).
- **Auth pattern:** Follows deploy.py credential chain: CLI args → env vars → DefaultAzureCredential → interactive browser. Service principal support via `--tenant-id`, `--client-id`, `--client-secret` for CI/CD workflows.
- **CI/CD integration:** Returns semantic exit codes (0=success, 1=config error, 2=generation failure, 3=ingestion failure, 4=partial failure). Dry-run mode (`--dry-run`) validates config and generates data without ingestion.
- **Pipeline orchestration:** Uses subprocess.run() with check=True for robust error propagation. File validation checks CSV existence and size before ingestion. Clean stdout suitable for GitHub Actions job summaries.
- **Key insight:** Chaining generation + ingestion removes the manual "generate CSV → upload to portal → run .ingest command" workflow. Parker's GitHub Actions workflow (`.github/workflows/deploy-fabric.yml`) invokes this script on-demand for historical data backfill as optional job triggered via workflow_dispatch.

**Cross-team context:** Integration point with Parker's CI/CD pipeline:
- Parker's historical-data job calls `simulator/deploy_history.py` with `--days` parameter from workflow input
- Ash's script matches deploy.py service principal auth pattern (CLI args > env vars > DefaultAzureCredential > browser)
- Semantic exit codes enable Parker's job summaries to distinguish generation vs. ingestion failures
- Both teams' work enables automated historical data provisioning during demo environment setup

### 2026-03-20 — Documentation enhancements for query clarity and schema idempotency
- **File:** `kql/03-queries.kql` — Rewrote VibrationAnomalies query comment (lines ~46-74) with comprehensive documentation explaining the z-score anomaly detection method, output format, and use case. Replaced terse one-liner with structured technical explanation covering: what it does, detection method (3σ threshold on 15-min rolling stats), output columns, and when to use for real-time monitoring.
- **File:** `kql/01-schema-setup.kql` — Completed idempotency documentation for ALL 26 commands. Added inline NOTE comments to every create/alter statement specifying idempotency behavior: `.create` (fails on re-run, suggests `.create-merge`), `.create-or-alter` (safe to re-run), `.alter` policy commands (idempotent), ingestion mappings (implicit create-or-alter). Header already documented overall behavior (lines 6-12).
- **Pattern:** KQL schema scripts should document re-run semantics inline at each command — this prevents confusion during iterative development and makes manual execution safer. Query comments should explain the statistical/analytical method, not just the business use case.
- **Key insight:** Idempotency documentation serves two audiences: automated deployment (deploy.py) and manual operators. Inline comments clarify which failures are expected vs. problematic, and guide safe manual re-execution strategies.
