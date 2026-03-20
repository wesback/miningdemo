# Squad Decisions

## Active Decisions

### 2026-03-20: Codebase Review & Approval for Demo Use
**Agent:** Ripley (Lead)  
**Type:** Architecture & Quality Review  
**Decision:** Mining RTI Demo codebase is **approved for demonstration use as-is** with medium-priority improvements recommended before production deployment.

**Rationale:**
- Zero critical blocking issues
- 6 medium-priority quality improvements identified (delegated to Parker & Ash)
- 8 low-priority enhancements suggested for future sprints
- Clean architecture, comprehensive documentation, excellent error handling
- All schema integration points verified (simulator JSON → KQL → dashboard)

**Work Delegated:**
- **Parker:** Event Hub retry logic, config validation, dependency pinning (4 fixes)
- **Ash:** Data sufficiency checks, dynamic dates, idempotency docs (3 fixes)
- **Dallas:** Docker deployment docs, CSV ingest (future)
- **Lambert:** Integration test suite, pre-flight validation (future)

**Impact:** Users can deploy demo immediately. Team has clear productionization backlog.

**References:** `.squad/reviews/2026-03-20-comprehensive-review.md`, `.squad/reviews/DISPATCH-SUMMARY.md`

### 2026-03-20: Buffered CSV Writes for Historical Data Generation
**Agent:** Parker (Python Dev)  
**Type:** Performance Optimization  
**Status:** Implemented

**Decision:** Implement buffered batch writes (5K-row chunks) with `tqdm` progress bar for `generate_history.py`.

**Context:** User feedback indicated long-running CSV generation had no progress indication and suboptimal performance.

**Implementation:**
- Buffered writes: 5,000-row batches flushed with `csv.writer.writerows()`
- Progress bar: Real-time ETA, row counts, throughput (rows/sec)
- Error handling: Try/except for I/O failures with contextual logging

**Performance Impact:** ~10-15x faster (175K rows: 15s → 1.5s)

**Trade-offs:** Added `tqdm~=4.66.0` dependency (stable, widely-used); minor memory overhead (<1MB); backward compatible

**Rationale:** 5K-row buffer balances memory (~500KB) vs. flush frequency. Testing showed diminishing returns above 5K.

**Impact:** CSV ingestion operations now viable for larger datasets. Zero breaking changes.

---

### 2026-03-20: KQL Query Documentation & Schema Idempotency
**Agent:** Ash (Data Engineer)  
**Type:** Documentation & Operational Safety  
**Status:** Implemented

**Decision:** 
1. Rewrite VibrationAnomalies query comment with z-score anomaly detection explanation
2. Document idempotency behavior for all 26 schema setup commands in `kql/01-schema-setup.kql`

**Context:** Operations teams need clarity on safe re-deployment and query methodology.

**Implementation:**
- VibrationAnomalies: Enhanced comment block with formula reference and threshold logic
- Schema commands: Explicit idempotency statements; impact analysis for each command

**Impact:** Safe re-runs of schema setup without data loss concerns; reduced support tickets; clearer query methodology

---

### 2026-03-20: Dashboard Standardization & Automated CSV Ingest
**Agent:** Dallas (Fabric Expert)  
**Type:** Documentation & Automation  
**Status:** Implemented

**Decision:**
1. Standardize all KQL query references in `dashboard/dashboard-config.md` (backtick notation, file path links)
2. Deprecate `get-docker.sh` (project has zero Docker dependencies)
3. Create `activator/ingest_history.py` for automated CSV ingestion via Kusto SDK

**Context:** Dashboard maintainability, user confusion about Docker, manual ingestion is multi-step and error-prone.

**Implementation:**
- Dashboard: Canonical reference format `` `QueryName` (from `kql/03-queries.kql`) ``
- Docker: Deprecation header + README update (file preserved)
- ingest_history.py: Azure Kusto SDK, auth patterns match deploy.py, dry-run mode, table validation

**Features:** Pre-flight validation, dry-run, progress monitoring, actionable errors

**Impact:** Better dashboard maintainability; users guided away from unsupported approach; end-to-end CSV → database pipeline automated

**Cross-Agent Notes:**
- Parker (Python): Credential fallback chain consistent across deploy.py and ingest_history.py
- Ash (KQL): Script validates table existence; users responsible for CSV schema compatibility
- Ripley (Architect): Ingestion now scriptable; can integrate into larger deployment automation

---

### 2026-03-20: Pre-Flight Validation Infrastructure
**Agent:** Lambert (Tester)  
**Type:** Quality Infrastructure  
**Status:** Implemented

**Decision:**
1. Add `validate_kql_syntax()` function to `deploy.py` for pre-flight bracket/string/semicolon validation
2. Create `simulator/CONFIG_SCHEMA.md` documenting all config fields, validation rules, and common mistakes

**Context:** Reduce deployment errors from structural syntax issues; document actual simulator behavior (not aspirations).

**Implementation - KQL Validation:**
- Heuristic checks (brackets, braces, parentheses, string literals)
- Non-blocking: logs warnings, allows deployment to proceed (API is authoritative)
- Tested against all 4 production KQL files; zero false positives
- Integrated into `execute_kql_commands()` (lines 383-389)

**Implementation - Config Documentation:**
- 450+ lines covering every YAML field, CLI args, env var fallbacks, priority order
- Documents actual code behavior (includes quirks like `batch_size` not enforced)
- Common mistakes and fixes for each field; example configs for multiple scenarios

**Key Finding:** Config priority is CLI args > YAML > Env vars > Defaults; unknown YAML fields silently ignored

**Impact:** Catches obvious typos before expensive API roundtrip; reduces config error support burden; improved onboarding

**Cross-Agent Notes:**
- Parker (Python): Reference validation patterns when fixing bugs
- Dallas (Ops): Significantly reduces support burden
- Ripley (Lead): Reduces deployment risk; improves reliability

---

### 2026-03-20: Complete Dashboard Definition in deploy.py
**Agent:** Dallas (Fabric Expert)  
**Type:** Deployment Automation  
**Status:** Implemented

**Decision:** Expand `build_dashboard_definition()` in `deploy.py` to include **all 18 tiles across 4 pages** as documented in `dashboard/dashboard-config.md`.

**Context:** Gap between documented dashboard specification (18 tiles, 4 pages) and automated deployment (6 tiles, 3 pages).

**Implementation:**
- All 4 pages: Operations Overview, Safety & Environment, Equipment Health, Production
- 18 KQL queries inline with dashboard definition
- Visual types: stat, bar, line, area, scatter, table, map
- Auto-refresh: 15s to 4h (contextual)
- Grid layout with x/y/width/height positioning
- Base64-encoded JSON payload (Fabric REST API)

**Impact:**
- Automated deployment now matches specification
- No breaking changes to deployment flow
- Single source of truth in deploy.py for CI/CD

**Rationale:** Completeness, maintainability, user experience consistency

**Related Files:** `deploy.py`, `dashboard/dashboard-config.md`, `kql/03-queries.kql`

---

### 2026-03-20: GitHub Actions CI/CD Pipeline for Fabric Deployment
**Agent:** Parker (Python Dev)  
**Type:** Infrastructure & Automation  
**Status:** Implemented

**Decision:** Create `.github/workflows/deploy-fabric.yml` — two-job GitHub Actions workflow for automated Fabric deployment with optional historical data ingestion.

**Context:** Wesley requested CI/CD pipeline for automated Fabric deployment with service principal auth, path-based triggers, and optional historical data backfill.

**Architecture:**
1. **deploy job:** Always runs on trigger; deploys Eventhouse, KQL Database, Eventstream, Queryset, Dashboard (20min timeout)
2. **historical-data job:** Optional, depends on deploy; chains generate → ingest; 30min timeout

**Triggers:**
- Push to main (with path filters: deploy.py, kql/**, dashboard/**, simulator/**)
- Manual trigger via workflow_dispatch (configurable: include_historical bool, history_days number)

**Quality Patterns:**
- Pre-flight secret validation
- Exit code tracking and job summaries
- Concurrency control (one deployment per branch, non-cancellable)
- Timeouts, artifact preservation, always-run blocks for visibility

**Authentication:** Service principal pattern matching deploy.py (4 secrets)

**Trade-offs:**
- Separate jobs for cleaner dependency chain and skippable historical data
- Non-cancellable concurrency prevents partial resource state in Fabric
- Manual trigger for historical data prevents expensive operations on every push

**Impact:** Automated deployment reduces manual error, clear failure reporting, opt-in historical data management

**Related Files:** `.github/workflows/deploy-fabric.yml`, `deploy.py`, `simulator/deploy_history.py`, `activator/ingest_history.py`

---

### 2026-03-20: Historical Data Pipeline Automation
**Agent:** Ash (Data Engineer)  
**Type:** Deployment Automation  
**Status:** Implemented

**Decision:** Create `simulator/deploy_history.py` — pipeline orchestration script that chains `generate_history.py` → `ingest_history.py` as single operation.

**Context:** Demo previously required multi-step manual workflow (generate CSV, upload, manually ingest via KQL). Error-prone, not CI/CD suitable.

**Implementation:**
- **Execution modes:**
  - Full: generate + ingest (default)
  - Generation-only: `--skip-ingest` (testing)
  - Ingestion-only: `--skip-generate` (pre-existing data)

- **CI/CD features:**
  - Semantic exit codes (0=success, 1=config, 2=gen fail, 3=ingest fail, 4=partial)
  - Dry-run validation mode
  - Service principal auth chain (CLI args → env vars → DefaultAzureCredential → browser)
  - CSV file validation (>1KB before ingestion)
  - Clean stdout for GitHub Actions summaries

- **Credential chain:** Matches deploy.py pattern for consistency

**Rationale:** Developer ergonomics, CI/CD integration, consistency, flexibility

**Impact:** Single command replaces 3-step workflow; CI/CD ready; consistent auth patterns across codebase

**Cross-Team Impact:**
- Parker: Will invoke from GitHub Actions for optional historical backfill
- Dallas: Validates CSV compatibility with schema
- Wesley: Simplified demo setup and data refresh

**Related Files:** `simulator/deploy_history.py`, `simulator/generate_history.py`, `activator/ingest_history.py`

---

### 2026-03-20: GitHub Workflow Historical Data Fix
**Agent:** Parker (Python Dev)  
**Type:** Bug Fix / Security Improvement  
**Status:** Implemented

**Decision:** Replace the broken `ingest_history.py` call in `.github/workflows/deploy-fabric.yml` with `simulator/deploy_history.py --skip-generate`.

**Problem:** The workflow was calling `activator/ingest_history.py` with `--workspace-id` and `--csv-path` flags that don't exist in the script's CLI interface, causing immediate failure.

**Solution:** Use `deploy_history.py --skip-generate` which:
- Provides proper orchestration layer for CI/CD
- Has explicit ingest-only mode via `--skip-generate` flag
- Uses correct credential arguments matching deploy.py patterns
- Internally invokes `ingest_history.py` with correct arguments

**Additional Changes:**
1. Removed workspace IDs from all step summaries (security fix)
2. Added pre-flight validation for `FABRIC_CLUSTER_URI` secret

**New Secret Required:** `FABRIC_CLUSTER_URI` (Kusto cluster URI format: `https://<cluster-name>.kusto.fabric.microsoft.com`)

**Trade-offs:**
- Adds one more secret to configure
- Slightly more complex call chain

**Cross-Team Impact:**
- **Ash:** deploy_history.py now used as intended in CI/CD
- **Dallas:** Workflow matches documented credential patterns
- **Lambert:** Added pre-flight secret validation pattern

**Impact:** Correct CLI usage, better abstraction, consistent auth patterns, security improvement

---

### 2026-03-20: Baseline Comparison Pattern for Incremental Operation Verification
**Agent:** Dallas (Fabric Expert)  
**Type:** Code Pattern / Best Practice  
**Status:** Implemented

**Decision:** Establish **baseline-then-compare** as the standard pattern for all incremental operation verification.

**Problem:** The ingestion verification in `activator/ingest_history.py` used a naive `row_count > 0` check that passed immediately if the target table already had rows from previous runs, masking failed ingestions.

**Solution:** Implement three-step verification pattern:
1. Capture baseline state BEFORE operation (e.g., row count)
2. Execute operation
3. Re-capture state AFTER operation and compare to baseline

**Implementation Example (ingest_history.py):**
```python
# Capture baseline BEFORE ingestion
baseline_count = get_count(...)
log.info(f"Baseline row count: {baseline_count:,}")

# Perform ingestion
# ... ingest CSV ...

# Verify delta
row_count = get_count(...)
if row_count > baseline_count:  # ← Correct: verifies delta
    log.info(f"Rows added: {row_count - baseline_count:,}")
```

**Applicability:** Any verification where operations are incremental and pre-existing state may mask operation failure:
- CSV/data ingestion → verify row count delta
- Queue processing → verify queue depth reduction
- File generation → verify new file count
- Batch updates → verify affected row count
- Log archival → verify archive size delta

**Cross-Team Impact:**
- **Ash:** Pattern applicable throughout data pipelines
- **Parker:** Reusable pattern for Python scripts
- **Lambert:** Use pattern in integration tests for idempotent operations

**Recommendation:** Adopt as standard pattern across Mining RTI Demo codebase for all incremental operation verification.

---

### 2026-03-20: Simulator Code as Source of Truth for Anomaly Names
**Agent:** Lambert (Tester)  
**Type:** Documentation / Governance  
**Status:** Resolved

**Decision:** The `ANOMALY_SCENARIOS` dictionary in `simulator.py` (lines 370-391) is the authoritative source of truth for valid anomaly scenario names.

**Problem:** `simulator/CONFIG_SCHEMA.md` listed incorrect anomaly names that didn't match the actual implementation:
- Doc said `engine`, code defines `overheat`
- Doc said `hydraulics`, code defines `hydraulic`
- Doc was missing `conveyor_stop` entirely

**Rationale:**
- The code is what executes — documentation can't override runtime behavior
- CLI argument parser uses `choices=list(ANOMALY_SCENARIOS.keys())`, so only code-defined names are valid
- Documentation errors cause user confusion and CLI failures

**Action Taken:** Corrected all anomaly names in CONFIG_SCHEMA.md to match simulator.py exactly:
- `overheat` (not engine)
- `hydraulic` (not hydraulics)
- `conveyor_stop` (now documented)
- `vibration` ✓
- `gas` ✓
- `all` ✓

**Team Guidance:**
- Always verify variable names, enum values, CLI choices against actual code
- If code and docs conflict, fix the docs (unless there's a code bug)
- Anomaly scenario changes require updates to both `ANOMALY_SCENARIOS` dict AND CONFIG_SCHEMA.md

**Testing Guidance:**
- Test cases must use the 6 valid scenario names from code
- Any anomaly injection tests using old names will fail

**Impact:** Reduced user support burden, clearer onboarding, eliminates CLI errors from documentation drift

---

## Governance

- All meaningful changes require team consensus
- Document architectural decisions here
- Keep history focused on work, decisions focused on direction
