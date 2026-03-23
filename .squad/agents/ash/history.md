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

### 2026-03-20 — Critical Fabric Real-Time Intelligence API fixes
- **File:** `deploy.py` (lines 233-322, 638-720) — Fixed TWO critical bugs preventing KQL Queryset and Real-Time Dashboard creation via Fabric REST API.
- **Bug 1 — Invalid .platform metadata structure** (lines 694-711, 1077-1094): The `.platform` file was using an incorrect minimal structure `{"version": "1.0.0", "type": "..."}` instead of the required Fabric Git integration schema. Fixed to include:
  - `$schema`: Reference to official JSON schema (v2.0.0)
  - `metadata`: Wrapper object with `type`, `displayName`, and `description`
  - `config`: Object with `version: "2.0"` and deterministic `logicalId` (using uuid5)
  - Pattern: All Fabric item definitions created via API must follow the Git integration schema, even when not using Git sync
- **Bug 2 — Incorrect API endpoint and request structure** (lines 233-253): Items with definitions (KQLQueryset, KQLDashboard, Eventstream) must use the generic `/workspaces/{id}/items` endpoint with a `"type"` field in the request body, not item-specific endpoints like `/kqlQuerysets`. Fixed `create_item()`, `get_item_by_name()`, `update_item_definition()`, and `get_item_definition()` to:
  - Detect items with definitions (`payload` contains `"definition"` key)
  - Route to `/items` endpoint and include PascalCase `"type"` field (e.g., `"KQLQueryset"`, `"KQLDashboard"`)
  - Keep item-specific endpoints for items with creation payloads (e.g., `kqlDatabases`, `eventhouses`)
- **Key insight:** Fabric REST API uses TWO patterns:
  1. Generic `/items` endpoint + `"type"` field → for items with definitions (queryset, dashboard, eventstream, notebook, report)
  2. Specific `/itemType` endpoint + NO type field → for items with creation payloads (kqlDatabases with parentEventhouseItemId)
- **Root cause:** These bugs caused 400/409 errors when deploying querysets and dashboards. The API was rejecting invalid `.platform` structures and mismatched endpoint patterns. Fixing both issues enables successful automated deployment of complete Fabric RTI demos.
- **Testing recommendation:** Validate against official Fabric documentation: [KQL Queryset definition](https://learn.microsoft.com/rest/api/fabric/articles/item-management/definitions/kql-queryset-definition), [KQL Dashboard definition](https://learn.microsoft.com/rest/api/fabric/articles/item-management/definitions/kql-dashboard-definition), and [Item management overview](https://learn.microsoft.com/rest/api/fabric/articles/item-management/item-management-overview).

**Cross-team context:** Parker should re-test the full CI/CD deployment flow (`.github/workflows/deploy-fabric.yml`) after these fixes to verify end-to-end automation now succeeds. Dallas may need to update documentation to reflect the corrected API patterns if any internal guides reference the old approach.

### 2026-03-23: Fabric REST API Pattern Identification & Validation
**Files verified:**
- `kql/03-queries.kql` — All named queries validated and properly mapped
- `deploy.py` — Query reference handling verified; API pattern issues identified

**Changes:**
- Identified critical Fabric API endpoint routing issue: definition-based items must use `/items` endpoint with `type` field
- Validated that all 18 dashboard tiles have correct query sources
- Confirmed named-query parsing logic in deploy.py aligns with actual KQL definitions

**Key patterns:**
- Items with definitions (querysets, dashboards) require `/items` endpoint + `type` field
- Named queries must be inlined when referenced; Fabric API doesn't resolve `.create-or-alter function` definitions
- All query references in dashboard now validated end-to-end

**Cross-team context:**
- Parker implemented API endpoint routing fix based on this finding
- Dallas corrected complementary DataSource schema issue
- Lambert created validation infrastructure for future query reference checks
- Combined fixes resolve deployment blocker for queryset and dashboard creation

**Decision file:** `.squad/decisions.md` (merged 2026-03-23 entries)

