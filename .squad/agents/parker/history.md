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
