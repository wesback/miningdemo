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
import uuid
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
    cluster_uri = cluster_uri.rstrip("/")
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
        """Handle long-running operations (202 Accepted).

        Polls the operation status URL until the operation reaches a terminal
        state, then fetches the result via the /result endpoint so callers
        receive the created-item body (with 'id') rather than the bare status
        object.

        Terminal statuses recognised: Succeeded, Failed, Cancelled, Undefined.
        Any status that is not Running / NotStarted is treated as terminal.
        """
        if response.status_code != 202:
            return None

        location = response.headers.get("Location")
        if not location:
            log.warning("  202 received but no Location header for %s", item_type)
            return None

        # Honour the Retry-After from the initial response; re-read on each poll.
        retry_after = int(response.headers.get("Retry-After", "5"))

        log.info("  Waiting for %s provisioning…", item_type)
        for _ in range(60):  # max 5 minutes (60 × retry_after seconds)
            time.sleep(retry_after)

            try:
                poll = self.session.get(location)
            except Exception as exc:
                log.warning("  Poll request failed (%s) — retrying…", exc)
                continue

            if poll.status_code == 200:
                body = poll.json()
                status = body.get("status", "")

                if status.lower() == "succeeded":
                    log.info("  %s provisioning completed.", item_type)
                    # Fetch the actual created-item from the /result endpoint.
                    # This gives us the item body with 'id', which is more
                    # reliable than the bare status object.
                    try:
                        result_resp = self.session.get(f"{location}/result")
                        if result_resp.status_code == 200:
                            result_body = result_resp.json()
                            if result_body.get("id"):
                                return result_body
                    except Exception as exc:
                        log.debug("  Could not fetch /result for %s: %s", item_type, exc)
                    # Fall back to returning the status body; create_item() will
                    # call get_item_by_name() when 'id' is absent.
                    return body

                elif status.lower() == "failed":
                    error = body.get("error", {})
                    log.error(
                        "  %s provisioning FAILED: code=%s msg=%s",
                        item_type,
                        error.get("errorCode", error.get("code", "unknown")),
                        error.get("message", str(body))[:300],
                    )
                    return None

                elif status.lower() in ("running", "notstarted", ""):
                    # Operation still in progress — re-read Retry-After and continue.
                    retry_after = int(poll.headers.get("Retry-After", str(retry_after)))
                    continue

                else:
                    # Unexpected terminal status (e.g. Cancelled, Undefined).
                    log.warning("  %s: unexpected operation status '%s' — aborting poll.", item_type, status)
                    return None

            elif poll.status_code == 202:
                # Still accepted — update retry interval and keep polling.
                retry_after = int(poll.headers.get("Retry-After", str(retry_after)))
                continue

            else:
                log.warning("  Unexpected poll HTTP status %d for %s", poll.status_code, item_type)
                # Don't bail immediately — one bad response may be transient.
                retry_after = int(poll.headers.get("Retry-After", str(retry_after)))

        log.error("  Timed out waiting for %s", item_type)
        return None

    def create_item(self, item_type: str, display_name: str, payload: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Create a Fabric item (Eventhouse, KQL Database, Eventstream, etc.)."""
        body: dict[str, Any] = {"displayName": display_name}
        if payload:
            body.update(payload)

        url = self._url(item_type)
        log.info("Creating %s: '%s'…", item_type, display_name)
        resp = self.session.post(url, json=body)

        if resp.status_code in (200, 201):
            result = resp.json()
            log.info("  Created %s: id=%s", item_type, result.get("id", "?"))
            return result
        elif resp.status_code == 202:
            op_result = self._wait_for_operation(resp, item_type)
            if op_result and op_result.get("id"):
                return op_result
            # Operation succeeded but response lacks item details — look up by name
            return self.get_item_by_name(item_type, display_name)
        elif resp.status_code == 409 or (
            resp.status_code == 400 and "ItemDisplayNameAlreadyInUse" in resp.text
        ):
            log.warning("  %s '%s' already exists — looking up existing item.", item_type, display_name)
            existing = self.get_item_by_name(item_type, display_name)
            if existing and payload and "definition" in payload:
                self.update_item_definition(item_type, existing["id"], payload)
            return existing
        else:
            log.error("  Failed to create %s: %d %s", item_type, resp.status_code, resp.text[:500])
            return None

    def get_item_by_name(self, item_type: str, display_name: str) -> dict[str, Any] | None:
        """Find an existing item by display name, following pagination."""
        url: str | None = self._url(item_type)
        page = 0
        while url:
            page += 1
            resp = self.session.get(url)
            if resp.status_code != 200:
                log.warning("  Could not list %s (HTTP %d)", item_type, resp.status_code)
                break
            data = resp.json()
            for item in data.get("value", []):
                if item.get("displayName") == display_name:
                    log.info("  Found existing %s: id=%s", item_type, item.get("id", "?"))
                    return item
            # Follow continuationUri for next page; fall back to None to stop.
            url = data.get("continuationUri") or None
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

    def update_item_definition(self, item_type: str, item_id: str, payload: dict[str, Any]) -> bool:
        """Update the definition of an existing item (dashboard, queryset, etc.)."""
        url = self._url(f"{item_type}/{item_id}/updateDefinition")
        log.info("  Updating %s definition (id=%s)…", item_type, item_id)
        resp = self.session.post(url, json=payload)
        if resp.status_code == 200:
            log.info("  ✓ Definition updated successfully.")
            return True
        elif resp.status_code == 202:
            self._wait_for_operation(resp, f"{item_type} definition update")
            log.info("  ✓ Definition updated successfully.")
            return True
        else:
            log.error("  Failed to update definition: %d %s", resp.status_code, resp.text[:500])
            return False


# ---------------------------------------------------------------------------
# KQL Syntax Validation
# ---------------------------------------------------------------------------
def validate_kql_syntax(kql_content: str, filename: str) -> list[str]:
    """Pre-validate KQL syntax for common issues before sending to API.
    
    This is a heuristic validation — NOT a full KQL parser. It catches common
    structural errors that would fail immediately on the server:
    - Mismatched parentheses, brackets, curly braces
    - Unclosed string literals (single quotes in KQL)
    - Empty command blocks (bare .create/.alter with no body)
    
    Args:
        kql_content: The KQL script content to validate
        filename: Name of the file being validated (for error messages)
    
    Returns:
        List of warning messages. Empty list if no issues found.
        These are warnings, not errors — deployment continues regardless.
    
    Limitations:
        - Does NOT validate KQL semantics (table names, column types, etc.)
        - Does NOT parse nested expressions or complex query logic
        - May produce false positives for edge cases (comments, string escapes)
        - Does NOT validate KQL-specific keywords or operators
        - Does NOT validate pipe operators (too many false positives in valid KQL)
    """
    warnings = []
    
    # Track bracket/paren/brace counts
    paren_count = 0
    bracket_count = 0
    brace_count = 0
    in_string = False
    
    lines = kql_content.split('\n')
    
    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()
        
        # Skip comment lines
        if stripped.startswith('//'):
            continue
        
        # Check for empty command blocks (command with no body)
        # Only flag single-word dot commands that look suspicious
        if stripped.startswith('.') and len(stripped.split()) == 1 and len(stripped) < 20:
            # Short single-word command — might be incomplete
            # Longer ones like ".create" with complex args are fine
            if not any(x in stripped.lower() for x in ['create', 'alter', 'set', 'delete']):
                warnings.append(f"Line {line_num}: Possibly incomplete command '{stripped}'")
        
        # Character-by-character analysis for brackets and strings
        i = 0
        while i < len(line):
            char = line[i]
            
            # Handle comments
            if i < len(line) - 1 and line[i:i+2] == '//':
                break  # Rest of line is comment
            
            # Handle string literals (single quotes in KQL)
            if char == "'" and (i == 0 or line[i-1] != '\\'):
                in_string = not in_string
            
            # Only count brackets if not in string
            if not in_string:
                if char == '(':
                    paren_count += 1
                elif char == ')':
                    paren_count -= 1
                    if paren_count < 0:
                        warnings.append(f"Line {line_num}: Unmatched closing parenthesis ')'")
                elif char == '[':
                    bracket_count += 1
                elif char == ']':
                    bracket_count -= 1
                    if bracket_count < 0:
                        warnings.append(f"Line {line_num}: Unmatched closing bracket ']'")
                elif char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count < 0:
                        warnings.append(f"Line {line_num}: Unmatched closing brace '}}'")
            
            i += 1
    
    # Check for unclosed strings
    if in_string:
        warnings.append(f"{filename}: Unclosed string literal (unmatched single quote)")
    
    # Check for unmatched brackets at end of file
    if paren_count > 0:
        warnings.append(f"{filename}: {paren_count} unclosed parenthesis(es) '('")
    elif paren_count < 0:
        warnings.append(f"{filename}: {abs(paren_count)} extra closing parenthesis(es) ')'")
    
    if bracket_count > 0:
        warnings.append(f"{filename}: {bracket_count} unclosed bracket(s) '['")
    elif bracket_count < 0:
        warnings.append(f"{filename}: {abs(bracket_count)} extra closing bracket(s) ']'")
    
    if brace_count > 0:
        warnings.append(f"{filename}: {brace_count} unclosed brace(s) '{{'")
    elif brace_count < 0:
        warnings.append(f"{filename}: {abs(brace_count)} extra closing brace(s) '}}'")
    
    return warnings


# ---------------------------------------------------------------------------
# KQL Command Execution
# ---------------------------------------------------------------------------
def _classify_kql_command(cmd: str) -> str:
    """Classify KQL command as 'critical', 'important', or 'optional'."""
    cmd_lower = cmd.lower().strip()
    
    # Critical: table/function creation, data mapping
    if any(keyword in cmd_lower for keyword in [
        ".create table",
        ".create-merge table", 
        ".create function",
        ".create-or-alter function",
        ".create ingestion mapping"
    ]):
        return "critical"
    
    # Important: reference data, table settings
    if any(keyword in cmd_lower for keyword in [
        ".set-or-append",
        ".set-or-replace",
        ".alter table"
    ]):
        return "important"
    
    # Optional: policies, caching
    if any(keyword in cmd_lower for keyword in [
        ".alter-merge policy",
        ".alter policy",
        ".delete policy"
    ]):
        return "optional"
    
    return "important"  # Default to important


def execute_kql_commands(cluster_uri: str, database: str, kusto_token: str, kql_file: Path) -> None:
    """Execute KQL control commands from a .kql file against the database.
    
    Raises:
        RuntimeError: If any critical command fails.
    """
    log.info("Executing KQL commands from %s…", kql_file.name)

    content = kql_file.read_text()
    # Normalise cluster URI — a stray trailing slash breaks the mgmt endpoint URL.
    cluster_uri = cluster_uri.rstrip("/")

    # Pre-validate KQL syntax (heuristic checks)
    syntax_warnings = validate_kql_syntax(content, kql_file.name)
    if syntax_warnings:
        log.warning("  ⚠️  KQL syntax pre-validation found %d potential issue(s):", len(syntax_warnings))
        for warning in syntax_warnings:
            log.warning("     • %s", warning)
        log.warning("  These are heuristic checks — deployment will continue.")

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
    critical_failures = []
    important_failures = []
    optional_failures = []
    
    for i, cmd in enumerate(commands, 1):
        cmd_clean = cmd.strip()
        if not cmd_clean or cmd_clean.startswith("//"):
            continue

        # Classify command severity
        severity = _classify_kql_command(cmd_clean)

        # Log first 80 chars of command
        preview = cmd_clean.replace("\n", " ")[:80]
        log.info("  [%d/%d] [%s] %s…", i, len(commands), severity.upper(), preview)

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
                    error_msg = f"{preview[:60]}... | Error: {str(errors)[:150]}"
                    log.error("    FAILED (%d): %s", resp.status_code, str(errors)[:200])
                    failed += 1
                    
                    # Track failure by severity
                    if severity == "critical":
                        critical_failures.append(error_msg)
                    elif severity == "important":
                        important_failures.append(error_msg)
                    else:
                        optional_failures.append(error_msg)
        except Exception as e:
            error_msg = f"{preview[:60]}... | Exception: {str(e)[:150]}"
            log.error("    Exception: %s", e)
            failed += 1
            
            # Track exception by severity
            if severity == "critical":
                critical_failures.append(error_msg)
            elif severity == "important":
                important_failures.append(error_msg)
            else:
                optional_failures.append(error_msg)

    # Summary report
    log.info("  KQL execution complete: %d succeeded, %d failed", success, failed)
    
    if critical_failures:
        log.error("  ❌ CRITICAL FAILURES (%d) — deployment may be incomplete:", len(critical_failures))
        for failure in critical_failures:
            log.error("     • %s", failure)
        raise RuntimeError(f"KQL deployment failed: {len(critical_failures)} critical command(s) failed")
    
    if important_failures:
        log.warning("  ⚠️  IMPORTANT FAILURES (%d) — some features may not work:", len(important_failures))
        for failure in important_failures:
            log.warning("     • %s", failure)
    
    if optional_failures:
        log.info("  ℹ️  OPTIONAL FAILURES (%d) — non-critical issues:", len(optional_failures))
        for failure in optional_failures:
            log.info("     • %s", failure)


# ---------------------------------------------------------------------------
# Item Definitions (Base64-encoded JSON payloads)
# ---------------------------------------------------------------------------
def _parse_production_queries(text: str) -> list[tuple[str, str]]:
    """Parse 03-queries.kql into (name, body) pairs using ``// Query: Name`` markers."""
    import re as _re
    pattern = r'// Query:\s*(\w+)\s*\n'
    markers = [(m.group(1), m.end()) for m in _re.finditer(pattern, text)]
    queries: list[tuple[str, str]] = []
    for i, (name, start) in enumerate(markers):
        if i + 1 < len(markers):
            next_section = text.rfind('// ----', start, markers[i + 1][1])
            end = next_section if next_section > 0 else markers[i + 1][1]
        else:
            end = len(text)
        body = text[start:end].strip()
        body = _re.split(r'\n// ╔[═]+╗', body)[0].strip()
        body = _re.split(r'\n// [-]{10,}\n// US-', body)[0].strip()
        body = body.rstrip(';').strip()
        if body and not all(ln.strip().startswith('//') or not ln.strip() for ln in body.splitlines()):
            queries.append((name, body))
    return queries


def _parse_predictive_queries(text: str) -> list[tuple[str, str]]:
    """Parse 04-predictive-queries.kql using box-drawing headers."""
    import re as _re
    blocks = _re.split(r'// ╔[═]+╗', text)
    queries: list[tuple[str, str]] = []
    for block in blocks[1:]:
        title_match = _re.search(r'║\s+\d+\.\s+(.+?)(?:\s+║)', block)
        if not title_match:
            continue
        title = title_match.group(1).strip()
        body_match = _re.search(r'// ╚[═]+╝\s*\n(.*)', block, _re.DOTALL)
        body = body_match.group(1).strip() if body_match else ''
        if body:
            queries.append((title, body))
    return queries


def build_queryset_definition(cluster_uri: str, database: str) -> dict[str, Any]:
    """Build the KQL Queryset definition with one tab per named query.

    Parses individual queries from the KQL files so each gets its own
    tab in the Fabric KQL Queryset — easier to navigate during demos.
    """
    queries_file = PROJECT_ROOT / "kql" / "03-queries.kql"
    predictive_file = PROJECT_ROOT / "kql" / "04-predictive-queries.kql"

    tabs: list[dict[str, str]] = []
    ds_id = "mining-ops-source"

    if queries_file.exists():
        for name, body in _parse_production_queries(queries_file.read_text()):
            tabs.append({
                "id": f"tab-{name}",
                "content": body,
                "title": name,
                "dataSourceId": ds_id,
            })

    if predictive_file.exists():
        for title, body in _parse_predictive_queries(predictive_file.read_text()):
            slug = title.split("(")[0].strip().replace(" ", "")
            tabs.append({
                "id": f"tab-pred-{slug}",
                "content": body,
                "title": f"[Predictive] {title}",
                "dataSourceId": ds_id,
            })

    if not tabs:
        tabs.append({
            "id": "tab-empty",
            "content": "// No queries found — check kql/ directory",
            "title": "Empty",
            "dataSourceId": ds_id,
        })

    log.info("  KQL Queryset: %d individual query tabs", len(tabs))

    queryset_json = {
        "queryset": {
            "version": "1.0.0",
            "dataSources": [
                {
                    "id": ds_id,
                    "clusterUri": cluster_uri,
                    "type": "AzureDataExplorer",
                    "databaseName": database,
                }
            ],
            "tabs": tabs,
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
    """
    Build a Real-Time Dashboard definition with all pages and tiles.

    Implements the complete dashboard specification from dashboard/dashboard-config.md:
      - Page 1: Operations Overview (4 tiles)
      - Page 2: Safety & Environment (4 tiles)
      - Page 3: Equipment Health (4 tiles)
      - Page 4: Production (4 tiles)
    Total: 16 tiles across 4 pages

    All IDs are deterministic RFC 4122 UUIDs (uuid5) so re-deploys never
    create duplicates.  Tiles live at the ROOT level with a ``pageId``
    back-reference — NOT nested inside pages.  dataSources.kind is
    ``kusto-trident`` as required by the Fabric RTD schema.
    """
    # ------------------------------------------------------------------
    # Deterministic UUIDs — same inputs always produce the same UUIDs so
    # re-running deploy does not create duplicate dashboard items.
    # ------------------------------------------------------------------
    NS = uuid.NAMESPACE_DNS

    def uid(name: str) -> str:
        return str(uuid.uuid5(NS, f"mining-rti-{name}"))

    ds_id = uid("datasource")

    page_id = {
        "ops":        uid("page-ops"),
        "safety":     uid("page-safety"),
        "equipment":  uid("page-equipment"),
        "production": uid("page-production"),
    }

    q_id = {
        "active-equipment":       uid("q-active-equipment"),
        "shift-tonnage":          uid("q-shift-tonnage"),
        "equipment-map":          uid("q-equipment-map"),
        "active-alerts":          uid("q-active-alerts"),
        "gas-levels":             uid("q-gas-levels"),
        "temp-heatmap":           uid("q-temp-heatmap"),
        "threshold-breaches":     uid("q-threshold-breaches"),
        "safety-incidents":       uid("q-safety-incidents"),
        "vibration-anomaly":      uid("q-vibration-anomaly"),
        "drill-hydraulic":        uid("q-drill-hydraulic"),
        "equipment-health-scores":uid("q-equipment-health-scores"),
        "equipment-utilisation":  uid("q-equipment-utilisation"),
        "conveyor-throughput":    uid("q-conveyor-throughput"),
        "truck-cycle-times":      uid("q-truck-cycle-times"),
        "route-efficiency":       uid("q-route-efficiency"),
        "production-7d":          uid("q-production-7d"),
    }

    t_id = {k: uid(f"tile-{k}") for k in q_id}

    # ------------------------------------------------------------------
    # Data source — kind MUST be "kusto-trident"; workspace can be "".
    # ------------------------------------------------------------------
    data_source = {
        "id":         ds_id,
        "name":       "MiningOps",
        "scopeId":    "cluster",
        "kind":       "kusto-trident",
        "clusterUri": cluster_uri,
        "database":   database,
        "workspace":  "",
    }

    # ------------------------------------------------------------------
    # Queries — every entry MUST include "usedVariables" (even if empty).
    # ------------------------------------------------------------------
    def q(key: str, text: str) -> dict[str, Any]:
        return {
            "id":            q_id[key],
            "dataSource":    {"kind": "inline", "dataSourceId": ds_id},
            "text":          text,
            "usedVariables": [],
        }

    queries = [
        # ── Page 1: Operations Overview ───────────────────────────────
        q("active-equipment", '''\
let cutoff = ago(2m);
EquipmentTelemetry
| where Timestamp > cutoff and Quality == "good"
| summarize arg_max(Timestamp, Value, SensorType) by EquipmentId
| extend Status = case(
    SensorType == "engine_temp_c" and Value > 105, "Fault",
    SensorType == "engine_temp_c" and Value < 30,  "Idle",
    SensorType == "belt_speed_m_s" and Value == 0,  "Idle",
    SensorType == "hydraulic_psi" and Value < 500,  "Idle",
    "Running")
| summarize Count = count() by Status'''),

        q("shift-tonnage", '''\
let shift_start = bin(now(), 8h);
let shift_target = 5000.0;
ProductionMetrics
| where SensorType == "load_tonnes" and Timestamp > shift_start and Quality == "good"
| summarize TotalTonnes = round(sum(Value), 0) by EquipmentType
| extend Target = shift_target
| extend PctOfTarget = round(TotalTonnes / Target * 100, 1)'''),

        q("equipment-map", '''\
let cutoff = ago(5m);
EquipmentTelemetry
| where Timestamp > cutoff and Quality == "good"
| summarize arg_max(Timestamp, *) by EquipmentId
| join kind=leftouter (EquipmentRegistry | project EquipmentId, Make, Model) on EquipmentId
| project EquipmentId, EquipmentType, Latitude, Longitude, Zone, Make, Model, Value, SensorType'''),

        q("active-alerts", '''\
let cutoff = ago(15m);
EnvironmentalReadings
| where Timestamp > cutoff and Quality == "good"
| join kind=inner (AlertThresholds) on SensorType
| where Value > CriticalHigh or Value < CriticalLow
| project Timestamp, Zone, SensorType, Value, Unit,
          Threshold = iff(Value > CriticalHigh, strcat("> ", tostring(CriticalHigh)),
                                                strcat("< ", tostring(CriticalLow))),
          Severity = "Critical"
| union (
    EquipmentTelemetry
    | where Timestamp > cutoff and Quality == "good"
    | where (SensorType == "hydraulic_psi" and Value < 1500)
         or (SensorType == "engine_temp_c" and Value > 105)
    | project Timestamp, Zone, SensorType, Value,
              Unit = iff(SensorType == "hydraulic_psi", "PSI", "°C"),
              Threshold = iff(SensorType == "hydraulic_psi", "< 1500", "> 105"),
              Severity = "Critical"
)
| order by Timestamp desc
| take 20'''),

        # ── Page 2: Safety & Environment ──────────────────────────────
        q("gas-levels", '''\
EnvironmentalReadings
| where SensorType in ("co_ppm", "ch4_pct")
    and Timestamp > ago(2h) and Quality == "good"
| summarize AvgValue = round(avg(Value), 2)
  by Zone, SensorType, bin(Timestamp, 1m)
| order by Timestamp asc'''),

        q("temp-heatmap", '''\
EnvironmentalReadings
| where SensorType == "ambient_temp_c" and Timestamp > ago(5m) and Quality == "good"
| summarize AvgTemp = round(avg(Value), 1), MaxTemp = round(max(Value), 1) by Zone
| extend Status = case(MaxTemp > 35, "CRITICAL", MaxTemp > 32, "WARNING", "NORMAL")
| order by MaxTemp desc'''),

        q("threshold-breaches", '''\
EnvironmentalReadings
| where Timestamp > ago(24h) and Quality == "good"
| join kind=inner (AlertThresholds) on SensorType
| where Value > CriticalHigh or Value < CriticalLow
| project Timestamp, Zone, SensorType, Value, Unit,
          Threshold = iff(Value > CriticalHigh, CriticalHigh, CriticalLow),
          Direction = iff(Value > CriticalHigh, "ABOVE", "BELOW")
| order by Timestamp desc
| take 50'''),

        q("safety-incidents", '''\
SafetyIncidents
| order by Timestamp desc
| project Timestamp, Zone, Severity, Description, EquipmentId
| take 20'''),

        # ── Page 3: Equipment Health ───────────────────────────────────
        q("vibration-anomaly", '''\
let sigma_threshold = 3.0;
EquipmentTelemetry
| where SensorType == "vibration_mm_s" and Timestamp > ago(4h) and Quality == "good"
| summarize AvgValue = avg(Value), StdValue = stdev(Value),
            MaxValue = max(Value), MinValue = min(Value)
  by EquipmentId, Bin = bin(Timestamp, 1m)
| extend UpperBound = AvgValue + (sigma_threshold * StdValue)
| extend IsAnomaly = MaxValue > UpperBound
| project Bin, EquipmentId, AvgValue = round(AvgValue, 2),
          MaxValue = round(MaxValue, 2), UpperBound = round(UpperBound, 2), IsAnomaly'''),

        q("drill-hydraulic", '''\
EquipmentTelemetry
| where SensorType == "hydraulic_psi" and EquipmentType == "drill"
    and Timestamp > ago(1h) and Quality == "good"
| summarize AvgPressure = round(avg(Value), 0) by EquipmentId, bin(Timestamp, 30s)
| order by Timestamp asc'''),

        q("equipment-health-scores", '''\
let scoring_window = 4h;
let temp_weight = 0.35;
let oil_weight  = 0.35;
let age_weight  = 0.30;
// Temperature score: 100 at 80°C, decreasing linearly to 0 at 110°C
let TempScores = EquipmentTelemetry
    | where SensorType == "engine_temp_c" and EquipmentType == "haul_truck"
        and Timestamp > ago(scoring_window) and Quality == "good"
    | summarize AvgTemp = avg(Value) by EquipmentId
    | extend TempScore = max_of(0.0, min_of(100.0, (110.0 - AvgTemp) / 0.3));
// Oil pressure score: 100 at 400 kPa, decreasing toward limits
let OilScores = EquipmentTelemetry
    | where SensorType == "oil_pressure_kpa" and EquipmentType == "haul_truck"
        and Timestamp > ago(scoring_window) and Quality == "good"
    | summarize AvgOil = avg(Value), StdOil = stdev(Value) by EquipmentId
    | extend OilScore = max_of(0.0, min_of(100.0, 100.0 - (StdOil / AvgOil) * 200.0));
// Age score: based on year commissioned from registry
let AgeScores = EquipmentRegistry
    | where EquipmentType == "haul_truck"
    | extend YearsOld = datetime_diff('year', now(), datetime(2026-01-01)) + (2026 - YearCommissioned)
    | extend AgeScore = max_of(0.0, 100.0 - (YearsOld * 10.0));
TempScores
| join kind=leftouter OilScores  on EquipmentId
| join kind=leftouter AgeScores  on EquipmentId
| extend HealthScore = round(
    (coalesce(TempScore, 50.0) * temp_weight) +
    (coalesce(OilScore, 50.0)  * oil_weight) +
    (coalesce(AgeScore, 50.0)  * age_weight), 0)
| extend Tier = case(
    HealthScore < 40, "Critical",
    HealthScore < 70, "Warning",
    "Healthy")
| project EquipmentId, HealthScore, TempScore = round(coalesce(TempScore, 50.0), 0),
          OilScore = round(coalesce(OilScore, 50.0), 0),
          AgeScore = round(coalesce(AgeScore, 50.0), 0), Tier
| order by HealthScore asc'''),

        q("equipment-utilisation", '''\
let report_day = startofday(ago(1d));
EquipmentTelemetry
| where Timestamp between (report_day .. (report_day + 1d)) and Quality == "good"
| summarize ActiveMinutes = dcount(bin(Timestamp, 1m)) by EquipmentId, EquipmentType
| extend UtilisationPct = round(ActiveMinutes / 1440.0 * 100, 1)
| order by UtilisationPct desc'''),

        # ── Page 4: Production ─────────────────────────────────────────
        q("conveyor-throughput", '''\
ProductionMetrics
| where SensorType in ("belt_load_kg_m", "belt_speed_m_s")
    and Timestamp > ago(7d) and Quality == "good"
| summarize AvgValue = round(avg(Value), 2)
  by EquipmentId, SensorType, bin(Timestamp, 1m)
| order by Timestamp asc'''),

        q("truck-cycle-times", '''\
ProductionMetrics
| where SensorType == "cycle_state" and EquipmentType == "haul_truck"
    and Timestamp > ago(24h) and Quality == "good"
| extend CyclePhase = case(
    Value == 1, "Loading", Value == 2, "Travel-Loaded",
    Value == 3, "Dumping", Value == 4, "Travel-Empty", "Unknown")
| where CyclePhase != "Unknown"
| summarize PhaseDuration_min = round(
    datetime_diff('second', max(Timestamp), min(Timestamp)) / 60.0, 1)
  by EquipmentId, CyclePhase, bin(Timestamp, 1h)
| summarize AvgDuration_min = round(avg(PhaseDuration_min), 1)
  by EquipmentId, CyclePhase'''),

        q("route-efficiency", '''\
ProductionMetrics
| where SensorType == "cycle_state"
    and EquipmentType == "haul_truck"
    and Timestamp > ago(24h)
    and Quality == "good"
| summarize CycleTime_min = datetime_diff('second', max(Timestamp), min(Timestamp)) / 60.0
  by EquipmentId, Zone, CycleBin = bin(Timestamp, 2h)
| summarize AvgCycle = avg(CycleTime_min), Cycles = count() by EquipmentId, Zone
| extend OverallAvg = toscalar(
    ProductionMetrics
    | where SensorType == "cycle_state" and EquipmentType == "haul_truck"
        and Timestamp > ago(24h) and Quality == "good"
    | summarize CycleTime_min = datetime_diff('second', max(Timestamp), min(Timestamp)) / 60.0
      by EquipmentId, CycleBin = bin(Timestamp, 2h)
    | summarize avg(CycleTime_min)
)
| extend Efficiency = round(AvgCycle / OverallAvg * 100, 1)
| extend Flagged = Efficiency > 120
| order by Efficiency desc'''),

        q("production-7d", '''\
ProductionMetrics
| where SensorType == "load_tonnes" and Timestamp > ago(7d) and Quality == "good"
| summarize DailyTonnes = round(sum(Value), 0) by Day = startofday(Timestamp)
| order by Day asc'''),
    ]

    # ------------------------------------------------------------------
    # Pages — NO "tiles" key; tiles are at root level with a pageId ref.
    # All page IDs must be RFC 4122 UUIDs.
    # ------------------------------------------------------------------
    pages = [
        {"id": page_id["ops"],        "name": "Operations Overview"},
        {"id": page_id["safety"],     "name": "Safety & Environment"},
        {"id": page_id["equipment"],  "name": "Equipment Health"},
        {"id": page_id["production"], "name": "Production"},
    ]

    # ------------------------------------------------------------------
    # Tiles — at ROOT level.  Each tile carries:
    #   • id         – UUID
    #   • pageId     – UUID of the owning page
    #   • queryId    – UUID of the backing query
    #   • visualType – chart kind
    #   • layout     – {x, y, width, height}
    # ------------------------------------------------------------------
    def tile(
        key: str,
        title: str,
        pg: str,
        visual: str,
        x: int, y: int, w: int, h: int,
    ) -> dict[str, Any]:
        return {
            "id":         t_id[key],
            "title":      title,
            "pageId":     page_id[pg],
            "queryRef":   {"kind": "query", "queryId": q_id[key]},
            "visualType": visual,
            "layout":     {"x": x, "y": y, "width": w, "height": h},
            "usedParamVariables": [],
            "visualOptions": {},
        }

    tiles = [
        # ── Page 1: Operations Overview ───────────────────────────────
        tile("active-equipment",   "Active Equipment Count",      "ops",        "stat",    0,  0, 10, 7),
        tile("shift-tonnage",      "Shift Tonnage vs Target",     "ops",        "bar",    10,  0, 10, 7),
        tile("equipment-map",      "Equipment Status Map",        "ops",        "map",     0,  7, 10, 8),
        tile("active-alerts",      "Active Alerts",               "ops",        "table",  10,  7, 10, 8),
        # ── Page 2: Safety & Environment ──────────────────────────────
        tile("gas-levels",         "Gas Levels by Zone",          "safety",     "line",    0,  0, 12, 8),
        tile("temp-heatmap",       "Temperature Heat Map",        "safety",     "table",   12, 0,  8, 8),
        tile("threshold-breaches", "Threshold Breaches 24h",      "safety",     "table",   0,  8, 10, 8),
        tile("safety-incidents",   "Safety Incident Timeline",    "safety",     "table",  10,  8, 10, 8),
        # ── Page 3: Equipment Health ───────────────────────────────────
        tile("vibration-anomaly",      "Vibration Anomaly Trend",  "equipment",  "scatter", 0,  0, 10, 8),
        tile("drill-hydraulic",        "Drill Hydraulic Pressure", "equipment",  "line",   10,  0, 10, 8),
        tile("equipment-health-scores","Equipment Health Scores",  "equipment",  "table",   0,  8, 10, 8),
        tile("equipment-utilisation",  "Equipment Utilisation",    "equipment",  "bar",    10,  8, 10, 8),
        # ── Page 4: Production ─────────────────────────────────────────
        tile("conveyor-throughput", "Conveyor Throughput Trend",  "production", "area",    0,  0, 12, 8),
        tile("truck-cycle-times",   "Haul Truck Cycle Times",     "production", "bar",    12,  0,  8, 8),
        tile("route-efficiency",    "Route Efficiency",           "production", "table",   0,  8, 10, 8),
        tile("production-7d",       "7-Day Production Trend",     "production", "line",   10,  8, 10, 8),
    ]

    dashboard_json = {
        "schema_version": "52",
        "title":        "Mining Operations",
        "autoRefresh":  {"enabled": True, "interval": 30},
        "dataSources":  [data_source],
        "pages":        pages,
        "tiles":        tiles,        # root-level; NOT inside pages
        "queries":      queries,
        "baseQueries":  [],           # required by schema; empty is valid
        "parameters":   [],           # required by schema; empty is valid
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
        help="Microsoft Entra ID tenant ID (for service principal auth). Env: AZURE_TENANT_ID",
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
