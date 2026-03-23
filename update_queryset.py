#!/usr/bin/env python3
"""
Quick script to update the KQL Queryset with the latest fixed queries.
This is faster than running the full deploy.py when only queries have changed.

Usage:
    python3 update_queryset.py --workspace-id <GUID>
    python3 update_queryset.py --workspace-id <GUID> --tenant-id <GUID> --client-id <GUID> --client-secret <SECRET>
"""

import argparse
import logging
import sys
from pathlib import Path

# Import the deployment functions
sys.path.insert(0, str(Path(__file__).parent))
from deploy import (
    FabricClient,
    get_token,
    build_queryset_definition,
    QUERYSET_NAME,
    DATABASE_NAME,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("update-queryset")

def main():
    parser = argparse.ArgumentParser(description="Update KQL Queryset with latest queries")
    parser.add_argument("--workspace-id", required=True, help="Fabric workspace ID")
    parser.add_argument("--tenant-id", help="Azure tenant ID (for service principal auth)")
    parser.add_argument("--client-id", help="Azure client ID (for service principal auth)")
    parser.add_argument("--client-secret", help="Azure client secret (for service principal auth)")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("UPDATE KQL QUERYSET")
    log.info("=" * 60)

    # Get authentication token
    token = get_token(args)
    client = FabricClient(args.workspace_id, token)

    # Find the existing queryset
    log.info("Finding existing KQL Queryset '%s'...", QUERYSET_NAME)
    existing = client.find_item("KQLQueryset", QUERYSET_NAME)
    if not existing:
        log.error("❌ Queryset '%s' not found in workspace. Run deploy.py first.", QUERYSET_NAME)
        sys.exit(1)

    queryset_id = existing["id"]
    log.info("  Found queryset: id=%s", queryset_id)

    # Find the database to get query URI
    log.info("Finding KQL Database '%s' to get query URI...", DATABASE_NAME)
    database = client.find_item("KQLDatabase", DATABASE_NAME)
    if not database:
        log.error("❌ Database '%s' not found in workspace. Run deploy.py first.", DATABASE_NAME)
        sys.exit(1)

    query_uri = database.get("properties", {}).get("queryServiceUri", "")
    if not query_uri:
        # Try to get it from database details
        from deploy import FABRIC_API_BASE
        db_detail_url = f"{FABRIC_API_BASE}/workspaces/{args.workspace_id}/kqlDatabases/{database['id']}"
        resp = client.session.get(db_detail_url)
        if resp.status_code == 200:
            query_uri = resp.json().get("properties", {}).get("queryServiceUri", "")
    
    if not query_uri:
        log.error("❌ Could not retrieve query URI from database. Cannot update queryset.")
        sys.exit(1)

    log.info("  Query URI: %s", query_uri)

    # Build the updated queryset definition with latest queries
    log.info("Building updated queryset definition with latest queries from kql/...")
    queryset_payload = build_queryset_definition(query_uri, DATABASE_NAME, QUERYSET_NAME)

    # Update the queryset
    log.info("Updating queryset definition...")
    success = client.update_item_definition("KQLQueryset", queryset_id, queryset_payload)

    if success:
        log.info("=" * 60)
        log.info("✅ QUERYSET UPDATE COMPLETE")
        log.info("=" * 60)
        log.info("The KQL Queryset now contains the latest fixed queries.")
        log.info("Open it in Fabric to verify all tabs load correctly.")
        log.info("=" * 60)
    else:
        log.error("❌ Failed to update queryset.")
        sys.exit(1)

if __name__ == "__main__":
    main()
