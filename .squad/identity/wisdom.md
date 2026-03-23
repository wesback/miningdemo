---
last_updated: 2026-03-20T11:46:55.723Z
---

# Team Wisdom

Reusable patterns and heuristics learned through work. NOT transcripts — each entry is a distilled, actionable insight.

## Patterns

<!-- Append entries below. Format: **Pattern:** description. **Context:** when it applies. -->

**Pattern:** When Fabric UI shows nothing instead of an error for a queryset/dashboard item, suspect a field *format* mismatch (not just a *presence* mismatch) that the API accepts but the UI client enforces at render time. Compare every ID field type/format against the official MS docs example payload — UUIDs everywhere is the expected convention. **Context:** Applies to KQL Queryset data source IDs, tab IDs, dashboard dataSource IDs, query IDs.
