---
name: "Fabric Queryset Diagnostics"
description: "Diagnose Fabric queryset browser errors by comparing parsed KQL tab counts with workflow update evidence before changing query content."
domain: "diagnostics"
confidence: "medium"
source: "earned"
tools:
  - name: "bash"
    description: "Inspect workflow logs, parse query counts, and compare them with the committed KQL surface"
    when: "A queryset updates successfully but Fabric still shows a browser/runtime error"
  - name: "view"
    description: "Review KQL files and deployment scripts"
    when: "Validating committed query content against the update workflow"
---

## Context

Use this skill when Fabric reports a browser error on a KQL Queryset even though the queryset update workflow completed successfully. The first step is to verify whether the repository's parsed tab count matches the workflow's logged tab count; if they match, the issue is usually stale browser/session state rather than a live query-count problem.

## Patterns

- Parse `kql/03-queries.kql` and `kql/04-predictive-queries.kql` together; the queryset should include both production and predictive tabs.
- Compare the parsed count against the workflow log line that reports `KQL Queryset: <n> individual query tabs`.
- Treat matching counts plus a successful workflow run as evidence that the live queryset is already up to date.
- Prefer a hard refresh or reopening the queryset before editing more KQL when the live update already succeeded.
- If a single tab still fails after refresh, inspect tabs that emit multiple result sets or unusual output shapes first.

## Examples

- `deploy.py` logs `KQL Queryset: 28 individual query tabs` when the parsed repo content matches the live update.
- `.github/workflows/update-queryset.yml` tells users to hard refresh Fabric after a successful update because the UI caches queryset definitions aggressively.

## Anti-Patterns

- Chasing query syntax changes when the live workflow already succeeded on the same commit.
- Ignoring browser cache/session state after a successful deployment.
- Assuming a query-count mismatch without checking the parser and workflow log first.

## Live Inspection via API (added 2026-03-23)

To inspect the actual live queryset definition (not just what's in the repo), use the Fabric REST API:

```python
import subprocess, json, requests, base64

result = subprocess.run(['az', 'account', 'get-access-token', '--resource', 'https://api.fabric.microsoft.com'],
    capture_output=True, text=True)
token = json.loads(result.stdout)['accessToken']
headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

resp = requests.post(
    f'https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items/{qs_id}/getDefinition',
    headers=headers)
parts = resp.json()['definition']['parts']
for p in parts:
    if p['path'] == 'RealTimeQueryset.json':
        qs = json.loads(base64.b64decode(p['payload']))
        tabs = qs['queryset']['tabs']
        print(f'{len(tabs)} tabs, datasources: {qs["queryset"]["dataSources"]}')
```

For running KQL against the live cluster, use the cluster-specific resource token:
```python
result = subprocess.run(['az', 'account', 'get-access-token', '--resource', '<cluster-uri>'], ...)
# Then POST to /v1/rest/query with {"db": "MiningOps", "csl": "<query>"}
```

Note: `.show tables` requires the `/v1/rest/mgmt` endpoint, not `/v1/rest/query`.
