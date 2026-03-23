# Project Context

- **Owner:** Wesley Backelant
- **Project:** Mining Real-Time Intelligence Demo — Microsoft Fabric Real-Time Intelligence for mining operations monitoring
- **Stack:** Python (deploy.py, simulator), KQL, Microsoft Fabric (Eventhouse, Eventstream, Real-Time Dashboards, Data Activator), Azure Event Hubs, Fabric REST APIs
- **Created:** 2026-03-20

## Core Context

Agent Scribe initialized and ready for work.

## Recent Updates

📌 Team initialized on 2026-03-20

### 2026-03-23: Dallas CI/CD Tutorial Pointer Orchestration
- **Timestamp:** 2026-03-23T12:17:43Z
- **Agent:** Dallas
- **Work:** Tutorial CI/CD pointer addition orchestration logged
- **Tasks Completed:**
  1. ✅ Orchestration log: `.squad/orchestration-log/2026-03-23T12-17-43Z-dallas.md`
  2. ✅ Session log: `.squad/log/2026-03-23T12-17-43Z-cicd-tutorial-pointer.md`
  3. ✅ Decision merge: Merged `.squad/decisions/inbox/dallas-cicd-tutorial-pointer.md` → `decisions.md`
  4. ✅ Cross-agent update: Dallas history.md updated with decision and links
  5. ✅ Git commit: `.squad/` changes committed

## Learnings

Initial setup complete.

### 2026-03-23: KQL Query Fixes & AlertThresholds Live Cleanup — Session Orchestration
- **Timestamp:** 2026-03-23T16:15:42Z
- **Agents:** Ash (KQL fixes), Dallas (AlertThresholds dedup)
- **Work:** Recorded orchestration logs, session log, merged decision inbox, updated agent histories

**Deliverables:**
1. ✅ Orchestration logs: `.squad/orchestration-log/20260323-161542-ash.md`, `.squad/orchestration-log/20260323-161542-dallas.md`
2. ✅ Session log: `.squad/log/20260323-161542-kql-fix-and-cleanup.md` (summarized fix work, patterns, verification)
3. ✅ Decision merge: Merged 3 decision inbox files (`ash-kql-argmax-continuous-sensor-bugs.md`, `dallas-alertthresholds-dedup-fix.md`, `dallas-alertthresholds-live-cleanup-complete.md`) into `.squad/decisions.md`
4. ✅ Deleted merged inbox files (4 files removed from `.squad/decisions/inbox/`)
5. ✅ Cross-agent updates: Appended to Ash history (KQL anti-patterns), Dallas history (AlertThresholds dedup/cleanup)
6. ⏳ Git commit: `.squad/` changes staged

**Key Findings Recorded:**
- Ash fixed 5 KQL query bugs in `kql/03-queries.kql` (commit db3eae9) with 3 documented anti-patterns
- Dallas eliminated AlertThresholds 26x fanout via `.set-or-replace` idempotent pattern (repo) + live cleanup (Fabric)
- Live data flow confirmed healthy; simulator stalled at 2026-03-23T14:53:25Z (separate issue)
- Production system now data-correct

**Cross-Agent Context Propagated:**
- Ash history: Lambert's bug discovery context, Dallas's parallel work
- Dallas history: Lambert's bug discovery context, Ash's parallel KQL fixes

**Next Session Task:**
- Commit `.squad/` changes with `git add .squad/ && git commit`
