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

## Governance

- All meaningful changes require team consensus
- Document architectural decisions here
- Keep history focused on work, decisions focused on direction
