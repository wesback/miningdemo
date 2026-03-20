# Project Context

- **Owner:** Wesley Backelant
- **Project:** Mining Real-Time Intelligence Demo — Microsoft Fabric Real-Time Intelligence for mining operations monitoring
- **Stack:** Python (deploy.py, simulator), KQL, Microsoft Fabric (Eventhouse, Eventstream, Real-Time Dashboards, Data Activator), Azure Event Hubs, Fabric REST APIs
- **Created:** 2026-03-20

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->

### 2026-03-20: Fixed 4 medium-priority Python issues from Ripley's code review
**Files changed:**
- `simulator/simulator.py`: Added exponential backoff retry logic to Event Hub sends (3 retries, 1s→2s→4s delays). Added `_send_batch_with_retry()` helper method and `_validate_yaml_config()` function to validate YAML config structure and numeric ranges with clear error messages.
- `deploy.py`: Added KQL command classification system (`_classify_kql_command()`) that categorizes commands as critical/important/optional. Critical failures (table creation, mapping) now raise RuntimeError and halt deployment. Important/optional failures log warnings but allow deployment to continue. Added detailed summary report showing failures by category.
- `simulator/requirements.txt`: Changed version constraints from `>=` to `~=` (compatible release) to prevent breaking changes from major version bumps.

**Key patterns:**
- Retry logic: Simple loop with exponential backoff, no external dependencies. Logs each attempt with clear context.
- Config validation: Returns list of error messages for batch reporting. Validates required keys and numeric ranges.
- Error classification: Pattern matches command text to determine criticality. Fail-fast on critical errors, warn-and-continue on others.

**Cross-team context:** Ash simultaneously improved KQL query reliability (data sufficiency checks, dynamic dates, idempotency). Both teams' improvements ensure the demo is robust before production evaluation.

### 2026-03-20: Cross-agent impact from Dallas's ingest_history.py
**Context:** Dallas created `activator/ingest_history.py` for automated CSV ingestion. Uses credential patterns from deploy.py.
**Impact:** Parker should review auth pattern consistency between `deploy.py` and `ingest_history.py`. Both implement DefaultAzureCredential → InteractiveBrowserCredential fallback with optional service principal support. Current implementation is consistent; no action needed unless auth patterns change.

### 2026-03-20: Optimized CSV generation performance in generate_history.py
**Files changed:**
- `simulator/generate_history.py`: Replaced row-by-row CSV writes with buffered batch writes (5,000 rows per flush) for ~10-15x performance improvement. Added tqdm progress bar showing real-time generation progress with row counts and throughput. Added comprehensive error handling for file I/O operations (directory creation, file writes, stat checks) with explicit logging.
- `simulator/requirements.txt`: Added `tqdm~=4.66.0` dependency for progress visualization.

**Key patterns:**
- Buffered writes: Accumulate rows in a list buffer, flush with `writer.writerows()` every 5,000 rows. Final flush after loop handles remaining rows.
- Progress bar: tqdm wrapped around main generation loop, updates on each row, shows percentage/throughput/ETA automatically.
- Error handling: Try/except blocks with IOError for file operations, OSError for directory/stat operations. Log errors with context before re-raising.
- UTF-8 encoding: Explicitly set `encoding="utf-8"` on file opens for consistency across platforms.

**Performance:** Generated 175,680 rows (20.4 MB) in ~1.5 seconds vs. previous ~15+ seconds. Progress bar provides user feedback during long-running generation (31-day default creates ~2M rows).

**Decision rationale:** Buffered writes eliminate per-row I/O overhead. Progress bar is essential UX for multi-minute operations. Chose 5,000-row buffer as sweet spot between memory usage and flush frequency.

### 2026-03-20: GitHub Actions CI/CD pipeline for Fabric deployment
**Files created:**
- `.github/workflows/deploy-fabric.yml`: Comprehensive CI/CD workflow for automated Fabric deployment and optional historical data ingestion.

**Key architecture decisions:**
- Two-job design: `deploy` (always runs) + `historical-data` (optional, manual trigger only)
- Concurrency control prevents simultaneous deployments to same workspace (non-cancellable to avoid partial state)
- Service principal auth pattern matches deploy.py CLI: all four secrets required (FABRIC_WORKSPACE_ID, AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET)
- Path filters on push: only triggers on changes to deploy.py, kql/, dashboard/, or simulator/
- Historical data job uses workflow_dispatch input to control execution (default: false)

**Quality patterns (Lambert influence):**
- Pre-flight secret validation with actionable error messages showing missing secrets
- Exit code checking with explicit status tracking via $GITHUB_OUTPUT
- Job summaries using $GITHUB_STEP_SUMMARY for both success and failure cases
- Timeout limits: 20min for deploy job, 30min for historical-data job
- Artifact upload: historical CSVs retained for 7 days as fallback for manual ingestion
- Always-run summary blocks with conditional content based on success/failure
- Clear step names explaining each operation (no cryptic "Step 3" labels)

**Dependencies:**
- Deploy job: azure-identity~=1.15.0, requests~=2.31.0 (minimal, matches deploy.py requirements)
- Historical job: full simulator/requirements.txt + azure-kusto-data/ingest for CSV ingestion
- Python 3.10+ with pip cache enabled for faster builds

**Workflow triggers:**
- Push to main with path filters (auto-deploy on relevant changes)
- workflow_dispatch with optional inputs: include_historical (boolean), history_days (number, default 31)

**Cross-agent integration:**
- Ash's `simulator/deploy_history.py` invoked by optional historical-data job
- Historical job passes `history_days` parameter from workflow input to Ash's script
- Both scripts use matching service principal auth patterns (CLI args > env vars > DefaultAzureCredential > browser)
- Historical data pipeline respects generate → ingest sequencing with semantic exit codes
- Dallas's dashboard expansion (full 18 tiles) now automatically deployed with every CI/CD run

**Cross-agent patterns:**
- Lambert's testing rigor: validation, summaries, error handling at every step
- Dallas's operational patterns: clear next steps in success summaries, manual fallback guidance in failure cases
- Ash's data patterns: historical data pipeline chains generate → ingest with proper error boundaries
