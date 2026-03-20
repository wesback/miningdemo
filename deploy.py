"""
Fabric Real-Time Intelligence — Automated Deployment Script
=============================================================
Deploys the entire Mining RTI demo to a Microsoft Fabric workspace using
the Fabric REST APIs:

  1. Eventhouse
  2. KQL Database
  3. KQL schema (tables, mappings, functions, policies)
  4. Reference data
  5. Eventstream (custom endpoint → KQL Database)
  6. KQL Queryset
  7. Real-Time Dashboard

Prerequisites:
  - pip install azure-identity requests
  - A Fabric workspace with Contributor+ access
  - Either interactive browser auth or a service principal

Usage:
  python deploy.py --workspace-id <GUID>
  python deploy.py --workspace-id <GUID> --tenant-id <GUID> --client-id <GUID> --client-secret <SECRET>

Environment variables (alternative to CLI flags):
  FABRIC_WORKSPACE_ID, AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package required. Install: pip install requests")
    sys.exit(1)

try:
    from azure.identity import (
        ClientSecretCredential,
        DefaultAzureCredential,
        InteractiveBrowserCredential,
    )
except ImportError:
    print("ERROR: 'azure-identity' package required. Install: pip install azure-identity")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("fabric-deploy")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
FABRIC_API_BASE = "https://api.fabric.microsoft.com/v1"
FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"
KUSTO_SCOPE_SUFFIX = ".kusto.fabric.microsoft.com"

PROJECT_ROOT = Path(__file__).resolve().parent

# Names for Fabric items
EVENTHOUSE_NAME = "MiningRTI"
DATABASE_NAME = "MiningOps"
EVENTSTREAM_NAME = "MiningSensorStream"
QUERYSET_NAME = "MiningOps-Queries"
DASHBOARD_NAME = "Mining Operations"


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
def get_token(args: argparse.Namespace) -> str:
    """Acquire a bearer token for the Fabric REST API."""
    if args.client_id and args.client_secret and args.tenant_id:
        log.info("Authenticating with service principal…")
        credential = ClientSecretCredential(
            tenant_id=args.tenant_id,
            client_id=args.client_id,
            client_secret=args.client_secret,
        )
    else:
        log.info("Authenticating interactively (browser)…")
        try:
            credential = DefaultAzureCredential()
            # Test if default credential works
            credential.get_token(FABRIC_SCOPE)
        except Exception:
            log.info("DefaultAzureCredential failed, falling back to interactive browser…")
            credential = InteractiveBrowserCredential()

    token = credential.get_token(FABRIC_SCOPE)
    return token.token


def get_kusto_token(args: argparse.Namespace, cluster_uri: str) -> str:
    """Acquire a bearer token for KQL command execution."""
    scope = f"{cluster_uri}/.default"
    if args.client_id and args.client_secret and args.tenant_id:
        credential = ClientSecretCredential(
            tenant_id=args.tenant_id,
            client_id=args.client_id,
            client_secret=args.client_secret,
        )
    else:
        try:
            credential = DefaultAzureCredential()
            credential.get_token(scope)
        except Exception:
            credential = InteractiveBrowserCredential()

    return credential.get_token(scope).token


# ---------------------------------------------------------------------------
# Fabric REST API Helpers
# ---------------------------------------------------------------------------
class FabricClient:
    """Wrapper around the Fabric REST API."""

    def __init__(self, token: str, workspace_id: str) -> None:
        self.workspace_id = workspace_id
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })

    def _url(self, path: str) -> str:
        return f"{FABRIC_API_BASE}/workspaces/{self.workspace_id}/{path}"

    def _wait_for_operation(self, response: requests.Response, item_type: str) -> dict[str, Any] | None:
        """Handle long-running operations (202 Accepted)."""
        if response.status_code == 202:
            location = response.headers.get("Location")
            retry_after = int(response.headers.get("Retry-After", "5"))
            if not location:
                log.warning("  202 received but no Location header for %s", item_type)
                return None
            log.info("  Waiting for %s provisioning…", item_type)
            for _ in range(60):  # max 5 minutes
                time.sleep(retry_after)
                poll = self.session.get(location)
                if poll.status_code == 200:
                    body = poll.json()
                    status = body.get("status", "")
                    if status in ("Succeeded", "succeeded"):
                        log.info("  %s provisioning completed.", item_type)
                        return body
                    elif status in ("Failed", "failed"):
                        log.error("  %s provisioning FAILED: %s", item_type, body)
                        return None
                elif poll.status_code == 202:
                    continue
                else:
                    log.warning("  Unexpected poll status %d", poll.status_code)
            log.error("  Timed out waiting for %s", item_type)
            return None
        return None

    def create_item(self, item_type: str, display_name: str, payload: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Create a Fabric item (Eventhouse, KQL Database, Eventstream, etc.)."""
        body: dict[str, Any] = {"displayName": display_name}
        if payload:
            body.update(payload)

        url = self._url(item_type)
        log.info("Creating %s: '%s'…", item_type, display_name)
        resp = self.session.post(url, json=body)

        if resp.status_code == 201:
            result = resp.json()
            log.info("  Created %s: id=%s", item_type, result.get("id", "?"))
            return result
        elif resp.status_code == 202:
            op_result = self._wait_for_operation(resp, item_type)
            if op_result:
                return op_result
            # Try to find the item by name
            return self.get_item_by_name(item_type, display_name)
        elif resp.status_code == 409:
            log.warning("  %s '%s' already exists — looking up existing item.", item_type, display_name)
            return self.get_item_by_name(item_type, display_name)
        else:
            log.error("  Failed to create %s: %d %s", item_type, resp.status_code, resp.text[:500])
            return None

    def get_item_by_name(self, item_type: str, display_name: str) -> dict[str, Any] | None:
        """Find an existing item by display name."""
        url = self._url(item_type)
        resp = self.session.get(url)
        if resp.status_code == 200:
            for item in resp.json().get("value", []):
                if item.get("displayName") == display_name:
                    log.info("  Found existing %s: id=%s", item_type, item["id"])
                    return item
        return None

    def get_item_definition(self, item_type: str, item_id: str) -> dict[str, Any] | None:
        """Get the definition of an item (for Eventstream connection details)."""
        url = self._url(f"{item_type}/{item_id}/getDefinition")
        resp = self.session.post(url)
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 202:
            return self._wait_for_operation(resp, f"{item_type} definition")
        return None


# ---------------------------------------------------------------------------
# KQL Command Execution
# ---------------------------------------------------------------------------
def execute_kql_commands(cluster_uri: str, database: str, kusto_token: str, kql_file: Path) -> None:
    """Execute KQL control commands from a .kql file against the database."""
    log.info("Executing KQL commands from %s…", kql_file.name)

    content = kql_file.read_text()

    # Split on lines starting with '.' (control commands) — skip comment-only blocks
    commands: list[str] = []
    current_cmd: list[str] = []

    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("//"):
            # If we have an accumulated command and hit a comment block, flush it
            if current_cmd:
                commands.append("\n".join(current_cmd))
                current_cmd = []
            continue
        if stripped.startswith("."):
            # New command starts — flush previous
            if current_cmd:
                commands.append("\n".join(current_cmd))
            current_cmd = [line]
        elif stripped and current_cmd:
            # Continuation of current command
            current_cmd.append(line)
        elif not stripped and current_cmd:
            # Blank line — might be end of command
            # But multi-line function bodies have blank lines, so keep going
            # unless the command looks complete
            if any(current_cmd[-1].strip().endswith(c) for c in ("}", "'", ')')):
                commands.append("\n".join(current_cmd))
                current_cmd = []
            else:
                current_cmd.append(line)

    if current_cmd:
        commands.append("\n".join(current_cmd))

    # Execute each command
    endpoint = f"{cluster_uri}/v1/rest/mgmt"
    headers = {
        "Authorization": f"Bearer {kusto_token}",
        "Content-Type": "application/json",
    }

    success = 0
    failed = 0
    for i, cmd in enumerate(commands, 1):
        cmd_clean = cmd.strip()
        if not cmd_clean or cmd_clean.startswith("//"):
            continue

        # Log first 80 chars of command
        preview = cmd_clean.replace("\n", " ")[:80]
        log.info("  [%d/%d] %s…", i, len(commands), preview)

        payload = {
            "db": database,
            "csl": cmd_clean,
        }

        try:
            resp = requests.post(endpoint, headers=headers, json=payload, timeout=60)
            if resp.status_code == 200:
                success += 1
            else:
                # Some errors are OK (e.g., table already exists)
                body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                errors = body.get("error", {}).get("message", resp.text[:200])
                if "already exists" in str(errors).lower():
                    log.warning("    Already exists — skipping.")
                    success += 1
                else:
                    log.error("    FAILED (%d): %s", resp.status_code, str(errors)[:200])
                    failed += 1
        except Exception as e:
            log.error("    Exception: %s", e)
            failed += 1

    log.info("  KQL execution complete: %d succeeded, %d failed", success, failed)


# ---------------------------------------------------------------------------
# Item Definitions (Base64-encoded JSON payloads)
# ---------------------------------------------------------------------------
def build_queryset_definition(cluster_uri: str, database: str) -> dict[str, Any]:
    """Build the KQL Queryset definition with all query tabs."""
    # Load queries from the KQL files
    queries_file = PROJECT_ROOT / "kql" / "03-queries.kql"
    predictive_file = PROJECT_ROOT / "kql" / "04-predictive-queries.kql"

    queries_content = queries_file.read_text() if queries_file.exists() else "// No queries found"
    predictive_content = predictive_file.read_text() if predictive_file.exists() else "// No predictive queries"

    queryset_json = {
        "queryset": {
            "version": "1.0.0",
            "dataSources": [
                {
                    "id": "mining-ops-source",
                    "clusterUri": cluster_uri,
                    "type": "AzureDataExplorer",
                    "databaseName": database,
                }
            ],
            "tabs": [
                {
                    "id": "tab-main-queries",
                    "content": queries_content,
                    "title": "Production Queries",
                    "dataSourceId": "mining-ops-source",
                },
                {
                    "id": "tab-predictive",
                    "content": predictive_content,
                    "title": "Predictive Analytics",
                    "dataSourceId": "mining-ops-source",
                },
            ],
        }
    }

    encoded = base64.b64encode(json.dumps(queryset_json).encode()).decode()
    return {
        "definition": {
            "parts": [
                {
                    "path": "RealTimeQueryset.json",
                    "payload": encoded,
                    "payloadType": "InlineBase64",
                }
            ]
        }
    }


def build_dashboard_definition(cluster_uri: str, database: str) -> dict[str, Any]:
    """Build a Real-Time Dashboard definition with pages and tiles."""
    # Define data source
    data_source = {
        "id": "ds-mining-ops",
        "kind": "kusto",
        "clusterUri": cluster_uri,
        "database": database,
    }

    # Define queries used by tiles
    queries = [
        {"id": "q-status", "text": 'let cutoff = ago(2m);\nEquipmentTelemetry\n| where Timestamp > cutoff and Quality == "good"\n| summarize arg_max(Timestamp, Value, SensorType) by EquipmentId\n| extend Status = case(\n    SensorType == "engine_temp_c" and Value > 105, "Fault",\n    SensorType == "engine_temp_c" and Value < 30, "Idle",\n    SensorType == "belt_speed_m_s" and Value == 0, "Idle",\n    SensorType == "hydraulic_psi" and Value < 500, "Idle",\n    "Running")\n| summarize Count = count() by Status', "dataSourceId": "ds-mining-ops"},
        {"id": "q-gas", "text": 'EnvironmentalReadings\n| where SensorType in ("co_ppm", "ch4_pct")\n    and Timestamp > ago(2h) and Quality == "good"\n| summarize AvgValue = round(avg(Value), 2)\n  by Zone, SensorType, bin(Timestamp, 1m)\n| order by Timestamp asc', "dataSourceId": "ds-mining-ops"},
        {"id": "q-alerts", "text": 'let cutoff = ago(15m);\nEnvironmentalReadings\n| where Timestamp > cutoff and Quality == "good"\n| join kind=inner (AlertThresholds) on SensorType\n| where Value > CriticalHigh or Value < CriticalLow\n| project Timestamp, Zone, SensorType, Value, Unit,\n          Threshold = iff(Value > CriticalHigh, strcat("> ", tostring(CriticalHigh)), strcat("< ", tostring(CriticalLow))),\n          Severity = "Critical"\n| order by Timestamp desc\n| take 20', "dataSourceId": "ds-mining-ops"},
        {"id": "q-tonnage", "text": 'let shift_start = bin(now(), 8h);\nlet shift_target = 5000.0;\nProductionMetrics\n| where SensorType == "load_tonnes" and Timestamp > shift_start and Quality == "good"\n| summarize TotalTonnes = round(sum(Value), 0) by EquipmentType\n| extend Target = shift_target\n| extend PctOfTarget = round(TotalTonnes / Target * 100, 1)', "dataSourceId": "ds-mining-ops"},
        {"id": "q-vibration", "text": 'let sigma_threshold = 3.0;\nEquipmentTelemetry\n| where SensorType == "vibration_mm_s" and Timestamp > ago(4h) and Quality == "good"\n| summarize AvgValue = avg(Value), StdValue = stdev(Value),\n            MaxValue = max(Value)\n  by EquipmentId, Bin = bin(Timestamp, 1m)\n| extend UpperBound = AvgValue + (sigma_threshold * StdValue)\n| extend IsAnomaly = MaxValue > UpperBound\n| project Bin, EquipmentId, AvgValue = round(AvgValue, 2),\n          MaxValue = round(MaxValue, 2), UpperBound = round(UpperBound, 2), IsAnomaly', "dataSourceId": "ds-mining-ops"},
        {"id": "q-temp-zones", "text": 'EnvironmentalReadings\n| where SensorType == "ambient_temp_c" and Timestamp > ago(5m) and Quality == "good"\n| summarize AvgTemp = round(avg(Value), 1), MaxTemp = round(max(Value), 1) by Zone\n| extend Status = case(MaxTemp > 35, "CRITICAL", MaxTemp > 32, "WARNING", "NORMAL")\n| order by MaxTemp desc', "dataSourceId": "ds-mining-ops"},
    ]

    # Define pages and tiles
    pages = [
        {
            "id": "page-ops",
            "name": "Operations Overview",
            "tiles": [
                {"id": "tile-status", "title": "Equipment Status", "queryId": "q-status", "visualType": "stat"},
                {"id": "tile-tonnage", "title": "Shift Tonnage vs Target", "queryId": "q-tonnage", "visualType": "bar"},
                {"id": "tile-alerts", "title": "Active Alerts", "queryId": "q-alerts", "visualType": "table"},
            ],
        },
        {
            "id": "page-safety",
            "name": "Safety & Environment",
            "tiles": [
                {"id": "tile-gas", "title": "Gas Levels by Zone", "queryId": "q-gas", "visualType": "line"},
                {"id": "tile-temp", "title": "Zone Temperatures", "queryId": "q-temp-zones", "visualType": "table"},
            ],
        },
        {
            "id": "page-equipment",
            "name": "Equipment Health",
            "tiles": [
                {"id": "tile-vibration", "title": "Vibration Anomalies", "queryId": "q-vibration", "visualType": "scatter"},
            ],
        },
    ]

    dashboard_json = {
        "autoRefresh": {"enabled": True, "defaultRefreshRate": "30s"},
        "dataSources": [data_source],
        "queries": queries,
        "pages": pages,
        "schema_version": "52",
        "title": DASHBOARD_NAME,
    }

    encoded = base64.b64encode(json.dumps(dashboard_json).encode()).decode()
    return {
        "definition": {
            "parts": [
                {
                    "path": "RealTimeDashboard.json",
                    "payload": encoded,
                    "payloadType": "InlineBase64",
                }
            ]
        }
    }


# ---------------------------------------------------------------------------
# Deployment Steps
# ---------------------------------------------------------------------------
def deploy(args: argparse.Namespace) -> None:
    """Main deployment orchestrator."""
    token = get_token(args)
    client = FabricClient(token, args.workspace_id)

    # -----------------------------------------------------------------------
    # Step 1: Create Eventhouse
    # -----------------------------------------------------------------------
    eventhouse = client.create_item("eventhouses", EVENTHOUSE_NAME)
    if not eventhouse:
        log.error("Failed to create Eventhouse. Aborting.")
        sys.exit(1)
    eventhouse_id = eventhouse["id"]

    # -----------------------------------------------------------------------
    # Step 2: Create KQL Database
    # -----------------------------------------------------------------------
    db_payload = {
        "creationPayload": {
            "databaseType": "ReadWrite",
            "parentEventhouseItemId": eventhouse_id,
        }
    }
    database = client.create_item("kqlDatabases", DATABASE_NAME, db_payload)
    if not database:
        log.error("Failed to create KQL Database. Aborting.")
        sys.exit(1)
    database_id = database["id"]

    # Extract the query URI from the database properties
    query_uri = database.get("properties", {}).get("queryServiceUri", "")
    if not query_uri:
        # Try to get it from the database details
        db_detail_url = f"{FABRIC_API_BASE}/workspaces/{args.workspace_id}/kqlDatabases/{database_id}"
        resp = client.session.get(db_detail_url)
        if resp.status_code == 200:
            query_uri = resp.json().get("properties", {}).get("queryServiceUri", "")

    if not query_uri:
        log.warning("Could not auto-detect KQL query URI. You may need to provide it manually.")
        log.warning("Check the database properties in the Fabric portal.")
    else:
        log.info("KQL Query URI: %s", query_uri)

    # -----------------------------------------------------------------------
    # Step 3: Execute KQL schema + reference data
    # -----------------------------------------------------------------------
    if query_uri:
        kusto_token = get_kusto_token(args, query_uri)

        schema_file = PROJECT_ROOT / "kql" / "01-schema-setup.kql"
        ref_data_file = PROJECT_ROOT / "kql" / "02-reference-data.kql"

        if schema_file.exists():
            execute_kql_commands(query_uri, DATABASE_NAME, kusto_token, schema_file)
        if ref_data_file.exists():
            execute_kql_commands(query_uri, DATABASE_NAME, kusto_token, ref_data_file)
    else:
        log.warning("Skipping KQL execution — no query URI available.")
        log.warning("Run the KQL scripts manually in the Fabric portal.")

    # -----------------------------------------------------------------------
    # Step 4: Create Eventstream
    # -----------------------------------------------------------------------
    eventstream = client.create_item("eventstreams", EVENTSTREAM_NAME)
    if eventstream:
        eventstream_id = eventstream["id"]
        log.info("Eventstream created: %s", eventstream_id)
        log.info("NOTE: Open the Eventstream in Fabric to:")
        log.info("  1. Add a 'Custom endpoint' source")
        log.info("  2. Add a 'KQL Database' destination → %s.%s", EVENTHOUSE_NAME, DATABASE_NAME)
        log.info("  3. Copy the connection string for the simulator")

    # -----------------------------------------------------------------------
    # Step 5: Create KQL Queryset
    # -----------------------------------------------------------------------
    if query_uri:
        queryset_payload = build_queryset_definition(query_uri, DATABASE_NAME)
        client.create_item("kqlQuerysets", QUERYSET_NAME, queryset_payload)

    # -----------------------------------------------------------------------
    # Step 6: Create Real-Time Dashboard
    # -----------------------------------------------------------------------
    if query_uri:
        dashboard_payload = build_dashboard_definition(query_uri, DATABASE_NAME)
        client.create_item("kqlDashboards", DASHBOARD_NAME, dashboard_payload)

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    log.info("=" * 60)
    log.info("DEPLOYMENT COMPLETE")
    log.info("=" * 60)
    log.info("Workspace:  %s", args.workspace_id)
    log.info("Eventhouse: %s (id: %s)", EVENTHOUSE_NAME, eventhouse_id)
    log.info("Database:   %s (id: %s)", DATABASE_NAME, database_id)
    if query_uri:
        log.info("Query URI:  %s", query_uri)
    log.info("")
    log.info("NEXT STEPS:")
    log.info("  1. Open the Eventstream and configure source + destination")
    log.info("  2. Copy the Eventstream connection string")
    log.info("  3. Run: python simulator/simulator.py --interval 10")
    log.info("  4. Open the Real-Time Dashboard to see live data")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deploy the Mining RTI demo to Microsoft Fabric.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive browser auth
  python deploy.py --workspace-id xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

  # Service principal auth
  python deploy.py \\
    --workspace-id xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \\
    --tenant-id    xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \\
    --client-id    xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \\
    --client-secret <secret>
        """,
    )
    parser.add_argument(
        "--workspace-id",
        default=os.environ.get("FABRIC_WORKSPACE_ID"),
        help="Fabric workspace ID (GUID). Env: FABRIC_WORKSPACE_ID",
    )
    parser.add_argument(
        "--tenant-id",
        default=os.environ.get("AZURE_TENANT_ID"),
        help="Azure AD tenant ID (for service principal auth). Env: AZURE_TENANT_ID",
    )
    parser.add_argument(
        "--client-id",
        default=os.environ.get("AZURE_CLIENT_ID"),
        help="Service principal client ID. Env: AZURE_CLIENT_ID",
    )
    parser.add_argument(
        "--client-secret",
        default=os.environ.get("AZURE_CLIENT_SECRET"),
        help="Service principal client secret. Env: AZURE_CLIENT_SECRET",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.workspace_id:
        log.error("--workspace-id is required. Get it from the Fabric portal URL.")
        log.error("URL format: https://app.fabric.microsoft.com/groups/<workspace-id>")
        sys.exit(1)
    deploy(args)


if __name__ == "__main__":
    main()
