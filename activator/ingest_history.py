"""
Historical Data Ingestion Script for Fabric KQL Database
==========================================================
Automates the ingestion of CSV historical data into a Fabric Eventhouse/KQL Database
using the Azure Kusto Python SDK.

Replaces the manual CSV upload + KQL .ingest command workflow described in README.md.

Prerequisites:
    pip install azure-identity azure-kusto-data azure-kusto-ingest

Usage:
    # Ingest from local CSV file
    python ingest_history.py \
        --csv simulator/historical_data/SensorReadings.csv \
        --cluster https://<cluster>.kusto.fabric.microsoft.com \
        --database MiningOps \
        --table SensorReadings

    # Ingest SafetyIncidents table
    python ingest_history.py \
        --csv simulator/historical_data/SafetyIncidents.csv \
        --cluster https://<cluster>.kusto.fabric.microsoft.com \
        --database MiningOps \
        --table SafetyIncidents

    # Use service principal authentication
    python ingest_history.py \
        --csv data.csv \
        --cluster https://<cluster>.kusto.fabric.microsoft.com \
        --database MiningOps \
        --table SensorReadings \
        --tenant-id <GUID> \
        --client-id <GUID> \
        --client-secret <SECRET>

Environment Variables (alternative to CLI flags):
    FABRIC_CLUSTER_URI, FABRIC_DATABASE, AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

try:
    from azure.identity import DefaultAzureCredential, InteractiveBrowserCredential, ClientSecretCredential
except ImportError:
    print("ERROR: azure-identity package required. Install: pip install azure-identity")
    sys.exit(1)

try:
    from azure.kusto.data import KustoClient, KustoConnectionStringBuilder
    from azure.kusto.ingest import (
        QueuedIngestClient,
        IngestionProperties,
        DataFormat,
    )
except ImportError:
    print("ERROR: azure-kusto-data and azure-kusto-ingest packages required.")
    print("Install: pip install azure-kusto-data azure-kusto-ingest")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Ingest historical CSV data into Fabric KQL Database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--csv",
        required=True,
        help="Path to the CSV file to ingest (e.g., SensorReadings.csv)",
    )
    parser.add_argument(
        "--cluster",
        default=os.getenv("FABRIC_CLUSTER_URI"),
        help="Kusto cluster URI (e.g., https://cluster.kusto.fabric.microsoft.com). Default: FABRIC_CLUSTER_URI env var",
    )
    parser.add_argument(
        "--database",
        default=os.getenv("FABRIC_DATABASE", "MiningOps"),
        help="KQL database name. Default: MiningOps or FABRIC_DATABASE env var",
    )
    parser.add_argument(
        "--table",
        required=True,
        help="Target table name (e.g., SensorReadings, SafetyIncidents)",
    )
    parser.add_argument(
        "--tenant-id",
        default=os.getenv("AZURE_TENANT_ID"),
        help="Microsoft Entra ID tenant ID (for service principal auth). Default: AZURE_TENANT_ID env var",
    )
    parser.add_argument(
        "--client-id",
        default=os.getenv("AZURE_CLIENT_ID"),
        help="Microsoft Entra ID client/application ID (for service principal auth). Default: AZURE_CLIENT_ID env var",
    )
    parser.add_argument(
        "--client-secret",
        default=os.getenv("AZURE_CLIENT_SECRET"),
        help="Microsoft Entra ID client secret (for service principal auth). Default: AZURE_CLIENT_SECRET env var",
    )
    parser.add_argument(
        "--mapping",
        help="Optional ingestion mapping name (e.g., SensorReadingsJsonMapping). If not specified, assumes CSV columns match table schema.",
    )
    parser.add_argument(
        "--ignore-first-record",
        action="store_true",
        default=True,
        help="Ignore the first row (CSV header). Default: True",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration but do not ingest data",
    )

    args = parser.parse_args()

    # Validation
    if not args.cluster:
        parser.error("--cluster is required (or set FABRIC_CLUSTER_URI environment variable)")
    if not args.csv:
        parser.error("--csv is required")
    if not Path(args.csv).exists():
        parser.error(f"CSV file not found: {args.csv}")

    return args


def get_credential(args: argparse.Namespace) -> Any:
    """Create Azure credential for Kusto authentication."""
    if args.client_id and args.client_secret and args.tenant_id:
        log.info("Using service principal authentication")
        return ClientSecretCredential(
            tenant_id=args.tenant_id,
            client_id=args.client_id,
            client_secret=args.client_secret,
        )
    else:
        try:
            log.info("Attempting DefaultAzureCredential (Azure CLI / managed identity)…")
            credential = DefaultAzureCredential()
            # Test the credential
            credential.get_token(f"{args.cluster}/.default")
            return credential
        except Exception as e:
            log.warning(f"DefaultAzureCredential failed: {e}")
            log.info("Falling back to interactive browser authentication…")
            return InteractiveBrowserCredential()


def verify_table_exists(client: KustoClient, database: str, table: str) -> bool:
    """Verify that the target table exists in the database."""
    try:
        query = f".show table {table} schema as json"
        result = client.execute(database, query)
        if result.primary_results and len(result.primary_results) > 0:
            log.info(f"✓ Table '{table}' exists in database '{database}'")
            return True
        else:
            log.error(f"✗ Table '{table}' not found in database '{database}'")
            return False
    except Exception as e:
        log.error(f"✗ Failed to verify table existence: {e}")
        return False


def ingest_csv(args: argparse.Namespace) -> None:
    """Ingest CSV file into KQL Database using queued ingestion."""
    csv_path = Path(args.csv)
    file_size_mb = csv_path.stat().st_size / (1024 * 1024)

    log.info("=" * 80)
    log.info("Fabric KQL Historical Data Ingestion")
    log.info("=" * 80)
    log.info(f"Cluster:   {args.cluster}")
    log.info(f"Database:  {args.database}")
    log.info(f"Table:     {args.table}")
    log.info(f"CSV File:  {csv_path.absolute()}")
    log.info(f"File Size: {file_size_mb:.2f} MB")
    log.info(f"Mapping:   {args.mapping or '(auto-detect from CSV columns)'}")
    log.info(f"Dry Run:   {args.dry_run}")
    log.info("=" * 80)

    # Authenticate
    credential = get_credential(args)

    # Build Kusto connection string
    kcsb = KustoConnectionStringBuilder.with_azure_token_credential(args.cluster, credential)

    # Create Kusto clients
    log.info("Connecting to Kusto cluster…")
    kusto_client = KustoClient(kcsb)
    ingest_client = QueuedIngestClient(kcsb)

    # Verify table exists
    if not verify_table_exists(kusto_client, args.database, args.table):
        log.error("Aborting: target table does not exist.")
        log.error(f"Create the table first using kql/01-schema-setup.kql or the deploy.py script.")
        sys.exit(1)

    if args.dry_run:
        log.info("✓ Dry run successful — configuration is valid.")
        log.info("Remove --dry-run flag to perform actual ingestion.")
        return

    # Configure ingestion properties
    ingestion_props = IngestionProperties(
        database=args.database,
        table=args.table,
        data_format=DataFormat.CSV,
        ingestion_mapping_reference=args.mapping if args.mapping else None,
        additional_properties={
            "ignoreFirstRecord": "true" if args.ignore_first_record else "false",
        },
    )

    # Capture baseline row count BEFORE ingestion
    try:
        count_query = f"{args.table} | count"
        count_result = kusto_client.execute(args.database, count_query)
        baseline_count = 0
        if count_result.primary_results:
            baseline_count = count_result.primary_results[0][0]["Count"]
        log.info(f"Baseline row count before ingestion: {baseline_count:,}")
    except Exception as e:
        log.warning(f"Could not get baseline row count: {e}")
        baseline_count = 0

    # Ingest the CSV file
    log.info(f"Starting ingestion of {csv_path.name}…")
    log.info(f"This may take several minutes for large files (current: {file_size_mb:.1f} MB).")

    try:
        result = ingest_client.ingest_from_file(str(csv_path), ingestion_properties=ingestion_props)
        log.info(f"✓ Ingestion request submitted successfully.")
        log.info(f"  Ingestion source ID: {result.source_id}")

        # Kusto ingestion is asynchronous. Poll for status.
        log.info("Waiting for ingestion to complete (checking every 10 seconds)…")
        max_wait = 600  # 10 minutes
        elapsed = 0
        while elapsed < max_wait:
            time.sleep(10)
            elapsed += 10

            # Check if new rows were added by comparing to baseline
            try:
                count_query = f"{args.table} | count"
                count_result = kusto_client.execute(args.database, count_query)
                if count_result.primary_results:
                    row_count = count_result.primary_results[0][0]["Count"]
                    log.info(f"  [{elapsed}s] Current table row count: {row_count:,}")
                    if row_count > baseline_count:
                        log.info("✓ Ingestion completed successfully!")
                        log.info(f"  Total rows in table '{args.table}': {row_count:,}")
                        log.info(f"  Rows added: {row_count - baseline_count:,}")
                        return
            except Exception as e:
                log.warning(f"Could not check table row count: {e}")

        log.warning("Ingestion request submitted but row count did not increase within 10 minutes.")
        log.warning("The ingestion may still be in progress. Check the Fabric portal for status.")
        log.warning(f"Or run this query in KQL Queryset: .show ingestion failures | where Table == '{args.table}'")

    except Exception as e:
        log.error(f"✗ Ingestion failed: {e}")
        log.error("Check that:")
        log.error("  1. The CSV file is valid and not corrupt")
        log.error("  2. The table schema matches the CSV columns")
        log.error("  3. You have 'Ingestor' permissions on the database")
        log.error("  4. The cluster URI is correct and reachable")
        sys.exit(1)


def main() -> None:
    """Main entry point."""
    args = parse_args()
    try:
        ingest_csv(args)
    except KeyboardInterrupt:
        log.warning("\nIngestion interrupted by user.")
        sys.exit(1)
    except Exception as e:
        log.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
