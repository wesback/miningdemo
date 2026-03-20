# Consolidated Squad Decisions Log

**Last Updated:** 2026-03-20T14:02:19Z  
**Canonical Source:** All squad decisions, deduplicated and consolidated

---

## Cycle 2 — Full Code Review

**Reviewer:** Ripley (Lead)  
**Date:** 2026-03-20  
**Scope:** All 15 deliverables across both work cycles

### Verdict: APPROVE WITH CONDITIONS

| Severity | Count |
|----------|-------|
| 🔴 Critical (must fix) | 1 |
| 🟡 Important (should fix) | 4 |
| 🟢 Minor (nice to fix) | 5 |
| ✅ Praised | 12 |

**Merge Blocker:**
- CI/CD workflow (deploy-fabric.yml) invokes ingest_history.py with wrong arguments. Lines 195–200 pass `--workspace-id` and `--csv-path` (not accepted) while missing `--cluster` and `--table`. Historical data ingestion would fail at runtime.

### Critical Issues

1. **deploy-fabric.yml — ingest_history.py argument mismatch** [CRITICAL]
   - **Issue:** Wrong argument names; missing required `--table` argument
   - **Impact:** Entire historical data ingestion step fails at runtime with argparse error
   - **Fix Options:** 
     - (A) Correct argument names to `--csv`, `--cluster`, `--database`, `--table`; add `FABRIC_CLUSTER_URI` secret
     - (B) Replace with `deploy_history.py --skip-generate --csv ... --cluster ...` (correct implementation exists in simulator/)
   - **Owner:** Parker (CI/CD) or Lambert (testing)
   - **Priority:** MUST FIX before merge

### Important Issues

2. **deploy.py — tile count docstring** [IMPORTANT]
   - **Issue:** Line 570 says "18 tiles" but dashboard has 16 tiles (4 × 4 grid)
   - **Fix:** Change to "16 tiles"
   - **Owner:** Dallas
   - **Priority:** Next commit

3. **ingest_history.py — premature success detection** [IMPORTANT]
   - **Issue:** Lines 258–265: Checks `if row_count > 0` without tracking delta. If table already contains data, reports "Ingestion completed!" before new data is ingested.
   - **Fix:** Store initial row count before ingestion, check for `row_count > initial_count` in poll loop
   - **Owner:** Dallas
   - **Priority:** Should fix — causes false success on re-runs

4. **deploy-fabric.yml — workspace ID in step summary** [IMPORTANT]
   - **Issue:** Line 104 writes `secrets.FABRIC_WORKSPACE_ID` into persistent `$GITHUB_STEP_SUMMARY`, visible to all with repo access
   - **Fix:** Mask the value (`***`) or omit from summary
   - **Owner:** Parker or Lambert
   - **Priority:** Security hygiene

5. **CONFIG_SCHEMA.md — incorrect scenario names** [IMPORTANT]
   - **Issue:** Line 126 documents `engine`, `hydraulics` but code uses `overheat`, `hydraulic`; missing `conveyor_stop`
   - **Impact:** Users following docs get argparse errors when running simulator
   - **Fix:** Update to `overheat`, `hydraulic`, `vibration`, `gas`, `conveyor_stop`, `all`
   - **Owner:** Lambert
   - **Priority:** Next commit

### Minor Issues

6. **kql/04-predictive-queries.kql — nested let fragility** [MINOR]
   - **Issue:** Queries 4 & 7 embed multiple `let` statements inside `iff()` tabular expressions
   - **Risk:** May fail on some Kusto engine versions
   - **Status:** Works in testing; acceptable; worth documenting fragility

7. **deploy-fabric.yml — dead exit code capture** [MINOR]
   - **Issue:** Lines 84–93: `deploy_exit=$?` is unreachable (bash -eo pipefail exits on error)
   - **Impact:** No functional bug, but misleading code
   - **Fix:** Remove or document why it's there

8. **deploy-fabric.yml — version drift risk** [MINOR]
   - **Issue:** Line 50 pins azure-identity/requests directly instead of using simulator/requirements.txt
   - **Risk:** Deps may drift from requirements.txt updates
   - **Fix:** Source deps from requirements.txt

9. **ingest_history.py — logging style inconsistency** [MINOR]
   - **Issue:** Uses f-strings (`log.info(f"...")`) vs rest of codebase using `%s` format
   - **Impact:** Functionally fine; minor style cleanup

10. **CONFIG_SCHEMA.md — line number references** [MINOR]
    - **Issue:** Lines 366–370 reference specific line numbers in simulator.py
    - **Risk:** References go stale with code changes
    - **Fix:** Use symbolic refs or remove specific line numbers

### Praised Items (12 items)

✅ **KQL Error Recovery** (deploy.py) — Three-tier severity classification (critical/important/optional) with proper error recovery. Production-grade pattern.

✅ **Event Hub Retry Logic** (simulator.py) — Exponential backoff (1s → 2s → 4s), proper per-attempt logging, clean re-raise on final failure.

✅ **Auth Pattern Consistency** — All files follow same credential chain: Service principal → DefaultAzureCredential → InteractiveBrowserCredential.

✅ **deploy_history.py Integration** — Correct argument passing to both generate and ingest scripts. Model of proper CLI integration.

✅ **Schema Idempotency Docs** (kql/01) — Every command block documents re-run behavior. Clear distinction between .create / .create-or-alter / .alter.

✅ **Query Name Alignment** — Named queries (EquipmentHealthScores, RouteEfficiency) correctly defined and referenced across KQL, config, and deploy.py.

✅ **Grid Layout Validation** (deploy.py) — All 4 dashboard pages verified with no overlaps on 12-column grid.

✅ **File Validation Logic** (deploy_history.py) — SensorReadings.csv checked for >1KB (catches headers-only), SafetyIncidents.csv checked for existence (correct for small datasets).

✅ **Graceful Shutdown** (simulator.py) — SIGINT/SIGTERM handlers set _shutdown flag for clean batch completion.

✅ **Buffered Writes** (generate_history.py) — 5K-row buffer with proper flush on threshold and EOF. Clean buffer.clear() after each flush.

✅ **Data Sufficiency Checks** (kql/04) — Queries 4 & 7 verify `DataPoints >= 100 and TimeSpan >= 1 day` before ML. Helpful warning messages with actual counts.

✅ **Dynamic/Fixed Data Alternatives** (kql/02) — Commented-out dynamic version (ago(1d)) with clear instructions for fresh demos; fixed version (2026-03-10) for reproducible reference data.

### Cross-Cutting Concerns — All Verified

| Concern | Status |
|---------|--------|
| Authentication chain | ✅ Consistent across all files |
| Error handling patterns | ✅ Appropriate variation per tool purpose |
| KQL query name alignment | ✅ Defined, documented, used consistently |
| Style (logging format) | 🟢 Minor f-string vs %s inconsistency (not blocking) |
| Secrets handling | ✅ Validated upfront; one hygiene issue (step summary) |

---

## Files Reviewed

### Code Files
1. deploy.py — Dashboard expansion, KQL error recovery
2. .github/workflows/deploy-fabric.yml — CI/CD pipeline (CRITICAL ISSUE)
3. simulator/deploy_history.py — Unified pipeline wrapper
4. simulator/simulator.py — Event Hub publishing with retry
5. simulator/generate_history.py — Historical data generation
6. activator/ingest_history.py — Historical data ingestion
7. simulator/requirements.txt — Python dependencies

### KQL Files
8. kql/01-schema-setup.kql — Database and table schema
9. kql/02-reference-data.kql — Equipment, route, incident reference data
10. kql/03-queries.kql — Named queries and functions
11. kql/04-predictive-queries.kql — Predictive analytics with data sufficiency checks

### Configuration & Documentation
12. dashboard/dashboard-config.md — Dashboard tile specifications
13. simulator/CONFIG_SCHEMA.md — Simulator configuration documentation (IMPORTANT ISSUE)
14. get-docker.sh — Docker utility (deprecated, clearly marked)

---

## Next Steps

**Before Merge:**
1. Fix critical CI/CD argument mismatch (deploy-fabric.yml, lines 195–200)

**In Next Commit:**
1. Fix deploy.py docstring tile count
2. Fix CONFIG_SCHEMA.md anomaly scenario names
3. Fix ingest_history.py delta tracking logic
4. Mask workspace ID in deploy-fabric.yml step summary

**Consider:**
1. Clean up deploy-fabric.yml dead code
2. Align deploy-fabric.yml deps with requirements.txt
3. Standardize logging style in ingest_history.py
4. Document or replace CONFIG_SCHEMA.md line number references
5. Document KQL fragility in nested let statements (if not yet tested)

---

**Review Completed By:** Ripley (Lead Code Reviewer)  
**Review Date:** 2026-03-20  
**Session Log:** .squad/log/2026-03-20T14:02:19Z-code-review.md  
**Orchestration Log:** .squad/orchestration-log/2026-03-20T14:02:19Z-ripley.md
