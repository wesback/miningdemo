---
name: "Fabric Doc Parity"
description: "Keeps Fabric README, tutorial, CI/CD, simulator, and user-story docs aligned on canonical names and setup semantics."
domain: "documentation"
confidence: "high"
source: "earned"
tools:
  # No special tools required; use repo views and searches.
---

## Context

Use this skill when reviewing or editing documentation that describes the same Fabric workflow in multiple places. It applies to README, tutorial, CI/CD, simulator config, user stories, and any doc that repeats item names or setup steps.

## Patterns

- Treat `deploy.py` as the source of truth for Fabric item names and deployment sequence.
- Keep KQL query/story IDs aligned with `kql/03-queries.kql` and dashboard tile labels.
- Document Fabric Eventstream custom endpoint names as system-generated `es_...` values, not the display name.
- Keep geography, coordinates, and scenario framing consistent across simulator code and docs.
- Use the same terminology for Eventhouse, KQL Database, Eventstream, and KQL Queryset in every doc.

## Examples

- `deploy.py` defines `MiningRTI`, `MiningOps`, `MiningSensorStream`, `MiningOps-Queries`, and `Mining Operations`.
- `docs/mining-rti-tutorial.md` and `README.md` should both describe the same Eventstream destination and simulator Event Hub naming.
- `docs/user-stories.md` should match the implemented query/tile names in `kql/03-queries.kql`.

## Anti-Patterns

- Using different names for the same Fabric item in different docs.
- Mixing the Eventstream display name with the generated Event Hub name.
- Leaving the tutorial geography different from the simulator or architecture.
- Letting user stories drift away from the KQL queries and dashboard labels they describe.
