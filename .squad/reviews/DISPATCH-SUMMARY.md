# Codebase Review — Issue Dispatch Summary
**Review Date:** 2026-03-20  
**Status:** ✅ APPROVED FOR DEMO USE  
**Total Issues:** 14 (0 critical, 6 medium, 8 low)

---

## 🔧 Parker (Python Developer) — 5 Issues

### Medium Priority (Fix before production)
1. **simulator.py:308-324** — Add retry logic to Event Hub sends
   - Implement exponential backoff for transient failures
   - Prevent data loss during network issues

2. **simulator.py:391-435** — Add config.yaml validation
   - Validate required fields and value ranges
   - Provide clear error messages for invalid config

3. **deploy.py:226-311** — Improve KQL execution error recovery
   - Add checkpoint system or fail-fast on critical errors
   - Prevent partially deployed schemas

4. **requirements.txt:1-4** — Tighten version constraints
   - Change `>=` to `~=` for minor version compatibility
   - Example: `azure-eventhub~=5.11` instead of `>=5.11.0`

### Low Priority
5. **generate_history.py:274-326** — Optimize CSV writing
   - Use buffered writes or pandas for 10x speed
   - Add progress bar with tqdm

---

## 📊 Ash (KQL Expert) — 4 Issues

### Medium Priority
1. **04-predictive-queries.kql:97-145** — Add data sufficiency checks
   - Validate 7-day lookback has data before RUL queries
   - Return error if insufficient data for ML models

2. **02-reference-data.kql:54-57** — Provide dynamic incident dates
   - Add commented alternative using `ago()` for fresh dates
   - Example: `INC-001, ago(1d) + 9h15m, Zone-A, Medium, ...`

### Low Priority
3. **03-queries.kql:50-77** — Clarify VibrationAnomalies comment
   - Update comment to match actual bin-based implementation
   - Remove confusing `series_fir` placeholder reference

4. **01-schema-setup.kql** — Document idempotency behavior
   - Note that `.create` commands fail on re-run (expected)
   - Or use `.create-or-alter` where appropriate

---

## 🔬 Dallas (Fabric Platform) — 3 Issues

### Low Priority
1. **dashboard-config.md** — Standardize query references
   - Use named queries OR inline queries consistently
   - Currently mixed (functional but inconsistent style)

2. **README.md** — Document or remove Docker script
   - Add Docker deployment option to README
   - Or remove `get-docker.sh` if not intended path

3. **simulator/** — Add programmatic historical CSV ingest
   - Create `ingest_history.py` to stream CSV via Event Hub
   - Alternative for users without OneLake/Blob access

---

## 🧪 Lambert (Testing) — 2 Issues

### Low Priority
1. **deploy.py:226** — Add KQL syntax pre-validation
   - Parse `.kql` files before REST API deployment
   - Catch syntax errors early

2. **config.sample.yaml** — Document validation schema
   - Add inline comments: `# (required)`, `# (optional, default: X)`
   - Include valid ranges for numeric fields

---

## Quick Stats

| Component | Critical | Medium | Low | Total |
|-----------|----------|--------|-----|-------|
| Python (deploy.py, simulator) | 0 | 4 | 1 | 5 |
| KQL (queries, schema) | 0 | 2 | 2 | 4 |
| Documentation & Config | 0 | 0 | 5 | 5 |
| **TOTAL** | **0** | **6** | **8** | **14** |

---

## Recommended Work Sequence

1. **Sprint 1 (1-2 days):** Parker fixes medium-priority simulator issues
2. **Sprint 2 (1 day):** Ash adds data checks and dynamic dates
3. **Sprint 3 (1-2 days):** Parker addresses remaining medium issues
4. **Backlog:** Low-priority improvements (documentation, optimization)

**Demo Readiness:** ✅ Can demo NOW — no blocking issues  
**Production Readiness:** 🟡 Fix 6 medium issues first

---

Full review: `.squad/reviews/2026-03-20-comprehensive-review.md`
