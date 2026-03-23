---
name: "Fabric API getDefinition Endpoint"
description: "Use the generic items getDefinition endpoint — not the resource-specific one — to retrieve KQL Queryset definitions."
domain: "fabric-api"
confidence: "high"
source: "earned"
tools:
  - name: "bash"
    description: "curl with Bearer token to POST /items/{id}/getDefinition"
    when: "Retrieving any Fabric item definition via REST API"
---

## Context

The Fabric REST API has two apparent routes for getting a KQL Queryset definition:
1. `GET /v1/workspaces/{wsId}/kqlQuerysets/{itemId}/getDefinition` — returns `EntityNotFound` even for valid items
2. `POST /v1/workspaces/{wsId}/items/{itemId}/getDefinition` with body `{}` — works correctly

Always use option 2. This is an undocumented inconsistency in the preview API surface.

## Pattern

```bash
FABRIC_TOKEN=$(az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv)
WORKSPACE_ID="<guid>"
ITEM_ID="<guid>"

curl -s -X POST \
  -H "Authorization: Bearer $FABRIC_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' \
  "https://api.fabric.microsoft.com/v1/workspaces/$WORKSPACE_ID/items/$ITEM_ID/getDefinition"
```

The response contains `definition.parts[]`, each with a `path` and base64 `payload`. For KQL Querysets:
- `RealTimeQueryset.json` — the queryset content (base64 → JSON)
- `.platform` — item metadata (base64 → JSON)

## Decoding the Payload

```python
import base64, json
decoded = base64.b64decode(part['payload']).decode()
obj = json.loads(decoded)
# For queryset: obj['queryset']['tabs'], obj['queryset']['dataSources']
```

## Anti-Patterns

- Using `GET` instead of `POST` for getDefinition — returns 404/EntityNotFound for most item types
- Missing `Content-Type: application/json` header — returns HTTP 411 Length Required
- Using the resource-specific `kqlQuerysets` route — broken in current API version
