# Project Context

- **Owner:** Wesley Backelant
- **Project:** Mining Real-Time Intelligence Demo — Microsoft Fabric Real-Time Intelligence for mining operations monitoring
- **Stack:** Python (deploy.py, simulator), KQL, Microsoft Fabric (Eventhouse, Eventstream, Real-Time Dashboards, Data Activator), Azure Event Hubs, Fabric REST APIs
- **Created:** 2026-03-20

## Core Context

### March 20, 2026: Team-Wide Python & Fabric Improvements (Summarized)
During the initial sprint, Parker coordinated with Ash and Dallas on codebase hardening and deployment automation:

**Simulator & Config:**
- Added exponential backoff retry logic (3 retries, 1s→2s→4s) to Event Hub sends
- Implemented YAML config validation with structured error reporting
- Added KQL command classification (critical/important/optional) with fail-fast on critical
- Changed dependency constraints to ~= (compatible release) to prevent major version breakage

**Fabric API Resilience:**
- Documented 8 critical patterns for handling Fabric REST API inconsistencies
- Async LRO polling with `/result` fallback (item ID retrieval)
- Pagination support with `continuationUri` for workspaces with 100+ items
- HTTP 200 response handling (some endpoints return 200 instead of 201)
- Network error tolerance during polling; trailing slash sanitization on cluster_uri

**CSV & Historical Data:**
- Buffered batch writes (5K-row chunks) for 10-15x performance improvement
- Added tqdm progress bar for user feedback on long operations
- Created `simulator/deploy_history.py` orchestration layer (generate → ingest pipeline)
- Enhanced error handling for file I/O and data ingestion

**GitHub Actions CI/CD:**
- Created comprehensive workflow (`.github/workflows/deploy-fabric.yml`)
- Secret validation with actionable error messages
- Path-based triggers (deploy.py, kql/*, dashboard/*, simulator/*)
- Optional historical data ingestion job (workflow_dispatch)
- Job summaries for success/failure reporting

**Critical Infrastructure Fixes:**
- Fixed DataFormat SDK import (azure-kusto-ingest 4.x uses string literals, not enums)
- Added missing `.platform` metadata to item definitions (required by Fabric API)
- Corrected API endpoint routing for definition-based items

All changes follow defensive coding patterns with zero breaking changes. Performance improvements validated. Team achieved deployment automation foundation by end of first day.

## Recent Updates

### 2026-03-23: Fabric REST API Pattern Fix & API Endpoint Routing Audit
**Files changed:**
- `deploy.py` — Fixed `.platform` metadata structure and API endpoint routing for definition-based items

**Changes:**
1. Updated `build_queryset_definition()` and `build_dashboard_definition()` to include correct `.platform` metadata structure matching Fabric Git integration schema
2. Modified `create_item()` to auto-detect definition vs. payload items and route to correct endpoint
3. Fixed `get_item_by_name()`, `update_item_definition()`, `get_item_definition()` to use `/items` endpoint for definition-based items

**Key patterns:**
- Items with definitions use `/items` endpoint with `type` field
- Items with payloads use item-specific endpoints without `type` field
- `.platform` metadata requires full Git schema (not minimal structure)

**Cross-team context:** 
- Ash validated Fabric API patterns and helped identify endpoint routing issue
- Dallas corrected DataSource schema (kind: "KQLDatabase")
- Lambert created validation infrastructure for future deployments
- This fix enables automated deployment of querysets and dashboards

**Decision file:** `.squad/decisions.md` (merged 2026-03-23 entries)

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->
