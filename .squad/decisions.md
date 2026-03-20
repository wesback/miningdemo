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

## Governance

- All meaningful changes require team consensus
- Document architectural decisions here
- Keep history focused on work, decisions focused on direction
