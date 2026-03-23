# CI/CD Setup Guide

This guide walks you through setting up **automated deployment** of the Mining Real-Time Intelligence demo to Microsoft Fabric using **GitHub Actions**.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Create a Service Principal](#2-create-a-service-principal)
3. [Find Your Fabric IDs](#3-find-your-fabric-ids)
4. [Configure GitHub Secrets](#4-configure-github-secrets)
5. [Run the Deployment](#5-run-the-deployment)
6. [Post-Deployment Manual Steps](#6-post-deployment-manual-steps)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Prerequisites

Before you begin, ensure you have:

| Requirement | Description |
|-------------|-------------|
| **Azure Subscription** | With Microsoft Fabric capacity (F2+) or a Fabric Trial enabled |
| **Fabric Workspace** | A workspace with Fabric capacity assigned |
| **Azure Permissions** | Ability to create Microsoft Entra ID App Registrations (Application Developer or higher) |
| **Fabric Workspace Permissions** | Admin or Contributor role on the target workspace |
| **GitHub Repository** | This repo forked/cloned with Actions enabled |

> ⚠️ **Important**: The service principal must be added **both** to Microsoft Entra ID (for authentication) **and** to the Fabric workspace (for resource management).

---

## 2. Create a Service Principal

A **service principal** (enterprise application) allows GitHub Actions to authenticate to Azure and deploy Fabric resources without interactive login.

### Option A: Azure Portal (Recommended)

1. **Navigate to Microsoft Entra ID:**
   - Open the [Azure Portal](https://portal.azure.com)
   - Search for and select **Microsoft Entra ID**

2. **Create an App Registration:**
   - In the left menu, click **App registrations**
   - Click **+ New registration**
   - Configure:
     - **Name:** `mining-rti-deploy` (or your preferred name)
     - **Supported account types:** **Accounts in this organizational directory only (Single tenant)**
     - **Redirect URI:** Leave blank
   - Click **Register**

3. **Record the Tenant ID and Client ID:**
   - On the app's **Overview** page, copy and save:
     - **Directory (tenant) ID** → This is your `AZURE_TENANT_ID`
     - **Application (client) ID** → This is your `AZURE_CLIENT_ID`

4. **Create a Client Secret:**
   - In the left menu, click **Certificates & secrets**
   - Click **+ New client secret**
   - Add a description (e.g., `GitHub Actions deployment`)
   - Select an expiration period (6 months, 12 months, or custom)
   - Click **Add**
   - **Copy the secret VALUE immediately** → This is your `AZURE_CLIENT_SECRET`
   - ⚠️ **Warning:** The secret value is only shown once. If you lose it, you'll need to create a new secret.

5. **Grant API Permissions (Required for Fabric):**
   - In the left menu, click **API permissions**
   - Click **+ Add a permission**
   - Select **APIs my organization uses**
   - Search for `Power BI Service` or `Microsoft Fabric`
   - Select **Power BI Service**
   - Choose **Application permissions** (not Delegated permissions)
   - Add the Fabric/Power BI workspace permission your tenant requires, such as `Workspace.ReadWrite.All`
   - Click **Add permissions**
   - If required by your organization, click **Grant admin consent for [Your Organization]**

> **Note:** `https://api.fabric.microsoft.com/.default` is the OAuth scope used by the deployment script, not a portal permission you add in App registrations.

> **Tip:** Some organizations require admin consent for API permissions. If you see a warning icon, contact your Microsoft Entra ID administrator.

### Option B: Azure CLI

```bash
# Create the service principal
az ad sp create-for-rbac \
  --name "mining-rti-deploy" \
  --role Contributor \
  --scopes /subscriptions/<your-subscription-id>

# Output will look like:
# {
#   "appId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",        ← AZURE_CLIENT_ID
#   "displayName": "mining-rti-deploy",
#   "password": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",       ← AZURE_CLIENT_SECRET
#   "tenant": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"        ← AZURE_TENANT_ID
# }
```

Save the output — you'll need these values for GitHub Secrets.

> **Note:** The Azure CLI method automatically grants Contributor role at the subscription level, but you still need to add the service principal to your Fabric workspace (next step) and grant API permissions in the Azure Portal.

### Add Service Principal to Fabric Workspace

**Critical step:** The service principal must be added as a **member** of your Fabric workspace.

1. Open [app.fabric.microsoft.com](https://app.fabric.microsoft.com)
2. Navigate to your workspace (e.g., `MiningRTI-Demo`)
3. Click the **Manage access** button in the workspace toolbar
5. Click **+ Add people or groups**
6. Search for your service principal name (e.g., `mining-rti-deploy`)
7. Select the service principal
8. Assign the role: **Contributor** or **Admin**
9. Click **Add**

> **Tip:** If you can't find the service principal by name, search for the **Client ID** (Application ID) instead.

---

## 3. Find Your Fabric IDs

The deployment script and GitHub Actions workflow require specific identifiers from your Fabric environment.

### FABRIC_WORKSPACE_ID

The workspace GUID identifies where resources will be created.

**How to find it:**
1. Open [app.fabric.microsoft.com](https://app.fabric.microsoft.com)
2. Navigate to your workspace
3. Look at the URL in your browser:
   ```
   https://app.fabric.microsoft.com/groups/<WORKSPACE_ID>/list
                                            ^^^^^^^^^^^^
   ```
4. Copy the GUID between `/groups/` and `/list`

**Example:** `12345678-1234-1234-1234-123456789abc`

---

### FABRIC_CLUSTER_URI

The Kusto cluster URI is required **only for historical data ingestion** (optional workflow step).

**How to find it:**
1. Open your Fabric workspace
2. Navigate to your **Eventhouse** (if already created) or create a temporary one
3. Open the **KQL Database** inside the Eventhouse
4. In the database details panel, look for **Query URI** or **URI**
5. Copy the full URI

**Format:** `https://<cluster-guid>.kusto.fabric.microsoft.com`

**Example:** `https://abcd1234.kusto.fabric.microsoft.com`

> **Tip:** This URI is generated automatically when you create an Eventhouse. If you haven't deployed yet, you can add this secret after the first deployment.

> ⚠️ **Important:** No trailing slash, no path components (like `/MiningOps`). Just the base cluster URI.

---

### AZURE_TENANT_ID

Your Microsoft Entra ID tenant identifier.

**How to find it:**
1. Open the [Azure Portal](https://portal.azure.com)
2. Navigate to **Microsoft Entra ID**
3. Click **Overview** in the left menu
4. Copy the **Tenant ID** (under "Tenant information")

**Example:** `87654321-4321-4321-4321-210987654321`

---

### AZURE_CLIENT_ID and AZURE_CLIENT_SECRET

These were created in **Step 2** when you registered the service principal.

- **AZURE_CLIENT_ID**: The **Application (client) ID** from the app registration's Overview page
- **AZURE_CLIENT_SECRET**: The **secret value** you copied when creating the client secret

> ⚠️ **Warning:** If you lost the client secret value, you cannot retrieve it. You must create a new secret in the Azure Portal → App registrations → your app → Certificates & secrets.

---

## 4. Configure GitHub Secrets

GitHub Secrets allow you to securely store credentials for use in GitHub Actions workflows.

### Add Secrets to Your Repository

1. **Navigate to your GitHub repository**
2. Click **Settings** (in the top menu)
3. In the left sidebar, expand **Secrets and variables** → click **Actions**
4. Click **New repository secret**

**Create these five secrets with EXACT names:**

| Secret Name | Value | Required For |
|-------------|-------|--------------|
| `AZURE_TENANT_ID` | Your Microsoft Entra ID Tenant ID (from Step 3) | Both deploy and historical-data jobs |
| `AZURE_CLIENT_ID` | Your service principal's Application ID (from Step 2) | Both deploy and historical-data jobs |
| `AZURE_CLIENT_SECRET` | Your service principal's secret value (from Step 2) | Both deploy and historical-data jobs |
| `FABRIC_WORKSPACE_ID` | Your Fabric workspace GUID (from Step 3) | Deploy job |
| `FABRIC_CLUSTER_URI` | Your KQL Database cluster URI (from Step 3) | Historical-data job (optional) |

**For each secret:**
1. Click **New repository secret**
2. Enter the **Name** (exactly as shown above — names are case-sensitive)
3. Paste the **Value**
4. Click **Add secret**

### Verification Checklist

After adding all secrets, your Actions secrets page should show:

- ✅ `AZURE_TENANT_ID`
- ✅ `AZURE_CLIENT_ID`
- ✅ `AZURE_CLIENT_SECRET`
- ✅ `FABRIC_WORKSPACE_ID`
- ✅ `FABRIC_CLUSTER_URI` (optional — add after first deployment if needed)

> **Tip:** Secret values are automatically masked in workflow logs. You'll see `***` instead of the actual value.

> **Note:** The `FABRIC_CLUSTER_URI` secret is only required if you plan to use the **workflow_dispatch** option with **include_historical** enabled. If you're only doing automated deployment on push to `main`, you can skip this secret for now.

---

## 5. Run the Deployment

You have three options to deploy the Fabric resources.

### Option A: Automated CI/CD (Push to Main)

The GitHub Actions workflow automatically triggers when you push changes to the `main` branch that affect these paths:
- `deploy.py`
- `kql/**`
- `dashboard/**`
- `simulator/**`

**To deploy:**
```bash
git add .
git commit -m "Update Fabric configuration"
git push origin main
```

The workflow will:
1. Validate all required secrets are present
2. Authenticate using the service principal
3. Deploy all Fabric resources:
   - **Eventhouse:** `MiningRTI`
   - **KQL Database:** `MiningOps` (with tables, policies, and seed data)
   - **Eventstream:** `MiningSensorStream`
   - **KQL Queryset:** `MiningOps-Queries`
   - **Real-Time Dashboard:** `Mining Operations`

**View the workflow:**
- Go to the **Actions** tab in your GitHub repository
- Click on the workflow run to see detailed logs

---

### Option B: Manual Workflow Dispatch (with Optional Historical Data)

Trigger the deployment manually from the GitHub UI, with optional historical data generation.

**Steps:**
1. Navigate to the **Actions** tab in your repository
2. Click **Deploy to Microsoft Fabric** in the left sidebar
3. Click **Run workflow** (button on the right)
4. Configure options:
   - **Use workflow from:** `main` (or your branch)
   - **Generate and ingest historical data:** Check to enable (default: unchecked)
   - **Days of historical data to generate:** Enter a number (default: 31)
5. Click **Run workflow**

**With historical data enabled:**
- The workflow generates CSV files with realistic sensor data (31 days by default)
- Ingests the data into the `MiningOps` database via the Kusto API
- Provides dashboard tiles with richer trends and anomaly patterns

**What happens:**
1. **Deploy job:** Creates all Fabric resources (same as Option A)
2. **Historical-data job:** (only if enabled)
   - Generates `SensorReadings.csv` and `SafetyIncidents.csv`
   - Ingests the CSVs into the KQL Database
   - Uploads CSV artifacts (available for 7 days)

> **Tip:** Use historical data for demos that showcase trend analysis, anomaly detection, and shift-over-shift comparisons.

---

### Option C: Quick Queryset Update (Query-Only)

If you've already deployed once and only need to update the KQL queries (no schema changes), use the **Update KQL Queryset** workflow for fast iteration:

**When to use:**
- Fixed a query syntax error
- Updated query logic or filters
- Added/removed query tabs
- Database schema hasn't changed

**Triggers automatically on:**
- Push to `main` with changes to `kql/**`

**Manual trigger:**
1. Navigate to **Actions** tab
2. Click **Update KQL Queryset**
3. Click **Run workflow**
4. (Optional) Add a reason for the update
5. Click **Run workflow**

**What it does:**
- Finds existing `MiningOps-Queries` queryset
- Reads latest queries from `kql/` directory
- Updates queryset definition (bypasses full deploy)
- Completes in ~30 seconds

**Requirements:**
- Queryset must already exist (run full deploy first)
- Same secrets as full deploy (`FABRIC_WORKSPACE_ID`, etc.)

> **Note:** This workflow does NOT modify database schema or create tables. If you changed table structures, use the full deployment workflow instead.

---

### Option D: Local CLI Deployment

Run the deployment script directly from your local machine.

#### With Service Principal (CI/CD-style):

```bash
cd /path/to/miningdemo

# Install dependencies
pip install azure-identity requests

# Deploy with service principal auth
python deploy.py \
  --workspace-id $FABRIC_WORKSPACE_ID \
  --tenant-id $AZURE_TENANT_ID \
  --client-id $AZURE_CLIENT_ID \
  --client-secret $AZURE_CLIENT_SECRET
```

#### With Interactive Browser Auth (Simplest):

```bash
cd /path/to/miningdemo

# Install dependencies
pip install azure-identity requests

# Deploy with interactive browser login
python deploy.py --workspace-id <your-workspace-guid>
```

This will open a browser window for Microsoft Entra ID authentication.

**Quick queryset-only update (local):**
```bash
# Update only the KQL Queryset with latest queries from kql/
python update_queryset.py --workspace-id <your-workspace-guid>
```

**What gets deployed:**
- For a complete list of Fabric items and schema details, see the [README Deployment Guide](../README.md#deployment-guide)

---

## 6. Post-Deployment Manual Steps

Some Fabric features are **not yet available via REST API** and require manual configuration in the Fabric portal.

### Eventstream Configuration (Required)

The REST API creates the Eventstream item, but you must manually wire the **source** and **destination** in the Fabric UI.

**Steps:**
1. Open [app.fabric.microsoft.com](https://app.fabric.microsoft.com)
2. Navigate to your workspace
3. Open the **MiningSensorStream** Eventstream
4. **Add Source:**
   - Click **Add source** → **Custom endpoint**
   - Note the **connection string** and **Event Hub name** (you'll need these for the simulator)
   - Or use an existing Azure Event Hub as the source
5. **Add Destination:**
   - Click **Add destination** → **KQL Database**
   - Select:
     - **Database:** `MiningOps`
     - **Table:** `SensorReadings`
     - **Input data format:** `JSON`
     - **Mapping name:** `SensorReadingsJsonMapping`
6. Click **Activate** to start the Eventstream

> **Tip:** The `SensorReadingsJsonMapping` is created automatically by the deployment script as part of the KQL schema setup (`kql/01-schema-setup.kql`).

---

### Data Activator Alert Rules (Optional)

**Data Activator (Reflex)** is not yet available via REST API. Configure alert triggers manually:

**Steps:**
1. In your workspace, create a new **Reflex** item named `Mining Safety Alerts`
2. Connect it to the `MiningOps` KQL Database or the `MiningSensorStream` Eventstream
3. Create alert triggers following the specifications in [`activator/alert-rules.md`](../activator/alert-rules.md):
   - **Gas Breach — CO** (Critical) → Teams + Email
   - **Gas Breach — CH₄** (Critical) → Teams + Email
   - **High Temperature** (Warning) → Teams
   - **Vibration Anomaly** (Warning) → Teams + Email
   - **Hydraulic Pressure Low** (Critical) → Teams + Email
   - **Truck Health Critical** (Warning) → Teams
   - **Conveyor Stoppage** (Warning) → Teams
4. Activate each trigger

For detailed rule definitions, see [`activator/alert-rules.md`](../activator/alert-rules.md).

---

### Dashboard Customization (Optional)

The deployment script creates a basic dashboard structure. To fully configure it with tiles and visuals:

1. Open the **Mining Operations** dashboard in the Fabric portal
2. Follow the tile-by-tile configuration guide in [`dashboard/dashboard-config.md`](../dashboard/dashboard-config.md)
3. Add pages:
   - **Operations Overview** — stat cards, tonnage, map, active alerts
   - **Safety & Environment** — gas levels, temperature heat map, breach table
   - **Equipment Health** — vibration scatter, hydraulic trends, health scores
   - **Production** — conveyor throughput, cycle times, route efficiency

Each page includes KQL queries and visual type recommendations.

---

## 7. Troubleshooting

Common issues and their solutions:

| Issue | Possible Cause | Solution |
|-------|----------------|----------|
| **401 Unauthorized** | Service principal secret expired or incorrect | Regenerate the client secret in Azure Portal → App registrations → Certificates & secrets, then update the `AZURE_CLIENT_SECRET` GitHub secret |
| **403 Forbidden** | Service principal not added to Fabric workspace | Add the SP to the workspace: Click **Manage access** in the workspace toolbar → Add the SP as Contributor or Admin |
| **403 Forbidden (API permissions)** | Missing API consent for Fabric | In Azure Portal → App registrations → API permissions → Add `Power BI Service` permission → Grant admin consent |
| **Invalid tenant error** | Wrong `AZURE_TENANT_ID` | Verify the Tenant ID in Microsoft Entra ID Overview matches the secret value |
| **SP not in workspace** | Role assignment missing | SPs must be added via the **Manage access** button in the workspace toolbar, not just Azure RBAC |
| **Missing secrets in CI** | One or more GitHub secrets not configured | The workflow validation step will list missing secrets. Add them in Settings → Secrets and variables → Actions |
| **FABRIC_CLUSTER_URI format error** | Incorrect URI format | Must be `https://<guid>.kusto.fabric.microsoft.com` — no trailing slash, no path like `/MiningOps` |
| **Workspace not found** | Wrong `FABRIC_WORKSPACE_ID` or SP lacks access | Verify the workspace GUID from the URL and that the SP is a workspace member |
| **Eventstream destination errors** | Ingestion mapping missing | Ensure `SensorReadingsJsonMapping` exists by running `kql/01-schema-setup.kql` before configuring the destination |
| **Dashboard shows "No data"** | Eventstream not activated or time range too narrow | Activate the Eventstream in the Fabric portal and set dashboard time range to "Last 1 hour" or wider |
| **Historical data ingestion fails** | `FABRIC_CLUSTER_URI` incorrect or missing | Get the cluster URI from the KQL Database properties panel. Format: `https://<guid>.kusto.fabric.microsoft.com` |
| **Workflow fails with "azure-identity not found"** | Python dependencies not installed | The workflow installs dependencies automatically. Check the "Install dependencies" step logs for errors |
| **Secret values visible in logs** | GitHub secret name typo (not using secrets.<NAME>) | Verify workflow uses `${{ secrets.SECRET_NAME }}` syntax — typos expose the literal string, not the secret value |

### Debugging Tips

**Check workflow logs:**
- Go to **Actions** tab → click the workflow run → expand each step to see detailed output

**Validate secrets locally:**
```bash
# Test service principal authentication
az login --service-principal \
  --username $AZURE_CLIENT_ID \
  --password $AZURE_CLIENT_SECRET \
  --tenant $AZURE_TENANT_ID

# Verify workspace access
az rest --method get \
  --url "https://api.fabric.microsoft.com/v1/workspaces/$FABRIC_WORKSPACE_ID" \
  --resource "https://api.fabric.microsoft.com"
```

**Test deploy.py locally:**
```bash
python deploy.py \
  --workspace-id <GUID> \
  --tenant-id <GUID> \
  --client-id <GUID> \
  --client-secret <SECRET>
```

If it works locally but fails in CI, the issue is likely with the GitHub Secrets configuration.

---

## Additional Resources

- **README:** [../README.md](../README.md) — Main project documentation
- **Architecture:** [architecture.md](architecture.md) — System design and data flow
- **User Stories:** [user-stories.md](user-stories.md) — Persona-based requirements
- **Dashboard Config:** [../dashboard/dashboard-config.md](../dashboard/dashboard-config.md) — Tile layout and queries
- **Alert Rules:** [../activator/alert-rules.md](../activator/alert-rules.md) — Data Activator trigger definitions
- **Fabric REST API Docs:** [Microsoft Fabric REST API](https://learn.microsoft.com/en-us/rest/api/fabric/articles/)
- **Azure Identity Docs:** [Azure Identity Library](https://learn.microsoft.com/en-us/python/api/overview/azure/identity-readme)

---

## Next Steps

After successful deployment:

1. ✅ **Verify** all Fabric items exist in your workspace
2. ✅ **Configure** the Eventstream source and destination (see Step 6)
3. ✅ **Run the simulator** to generate live data:
   ```bash
   cd simulator/
   pip install -r requirements.txt
   export EVENT_HUB_CONNECTION_STRING="<from-eventstream>"
   export EVENT_HUB_NAME="<from-eventstream>"
   python simulator.py --interval 10
   ```
4. ✅ **Open the dashboard** and verify live data is flowing
5. ✅ **Set up Data Activator** alerts (optional)
6. ✅ **Load historical data** for richer demos (optional — via workflow_dispatch)

For demo scenarios and anomaly injection, see the [README Demo Scenarios section](../README.md#demo-scenarios).

---

**Questions or issues?** Open a GitHub issue or check the [Troubleshooting](#7-troubleshooting) section above.
