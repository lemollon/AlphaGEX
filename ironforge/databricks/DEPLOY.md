# IronForge Databricks Deployment Guide

## Architecture

```
┌────────────────────────┐     ┌──────────────────────┐
│  Next.js Dashboard     │────▶│  FastAPI (ironforge_  │
│  (Vercel / Render)     │     │  api.py)              │
│  Same frontend code    │     │  Deployed anywhere    │
└────────────────────────┘     └──────────┬───────────┘
                                          │
                               ┌──────────▼───────────┐
                               │  Databricks SQL       │
                               │  ironforge.trading.*  │
                               └──────────┬───────────┘
                                          │
                               ┌──────────▼───────────┐
                               │  Databricks Job       │
                               │  ironforge_scanner.py │
                               │  Continuous mode      │
                               └──────────────────────┘
                                          │
                               ┌──────────▼───────────┐
                               │  Tradier API          │
                               │  Production + Sandbox │
                               └──────────────────────┘
```

## Step 1: Create Tables

Upload `01_setup_tables.sql` to a Databricks notebook and run it.
This creates the `ironforge` catalog, `trading` schema, and all 15 tables.

## Step 2: Deploy Scanner

### Option A: Databricks Job (Recommended)

1. Upload `ironforge_scanner.py` to DBFS:
   ```bash
   databricks fs cp ironforge_scanner.py dbfs:/ironforge/ironforge_scanner.py
   ```

2. Create the job using the CLI:
   ```bash
   databricks jobs create --json @databricks_job_config.json
   ```

3. Set environment variables on the cluster:
   - `DATABRICKS_HOST` — your workspace hostname
   - `DATABRICKS_HTTP_PATH` — SQL warehouse HTTP path
   - `DATABRICKS_TOKEN` — personal access token
   - `TRADIER_API_KEY` — production key for live quotes
   - `TRADIER_SANDBOX_KEY_USER` — (optional)
   - `TRADIER_SANDBOX_KEY_MATT` — (optional)
   - `TRADIER_SANDBOX_KEY_LOGAN` — (optional)

The job runs in continuous mode — it starts, runs the scan loop forever
(sleeping 5 minutes between scans), and auto-restarts on failure.

### Option B: Run as Notebook

Create a notebook that imports and runs the scanner:
```python
# %pip install databricks-sql-connector requests
import os
os.environ["DATABRICKS_HOST"] = spark.conf.get("spark.databricks.workspaceUrl")
os.environ["DATABRICKS_HTTP_PATH"] = "/sql/1.0/warehouses/YOUR_WAREHOUSE_ID"
os.environ["DATABRICKS_TOKEN"] = dbutils.secrets.get("ironforge", "databricks_token")
os.environ["TRADIER_API_KEY"] = dbutils.secrets.get("ironforge", "tradier_api_key")

from ironforge_scanner import main
main()
```

## Step 3: Deploy FastAPI

### Option A: External server (Recommended)

Deploy `ironforge_api.py` on any server (Render, AWS, fly.io):

```bash
pip install -r requirements.txt
export DATABRICKS_HOST=your-workspace.cloud.databricks.com
export DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/YOUR_ID
export DATABRICKS_TOKEN=your-token
export TRADIER_API_KEY=your-key
uvicorn ironforge_api:app --host 0.0.0.0 --port 8000
```

### Option B: Databricks Model Serving

Use Databricks Model Serving to host the FastAPI app as an endpoint.

## Step 4: Connect Dashboard

The existing Next.js dashboard can point to the FastAPI backend.

Set the environment variable on your frontend deployment:
```
NEXT_PUBLIC_API_URL=https://your-api-server.com
```

Then update `src/lib/fetcher.ts` to use this base URL:
```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_URL || ''

export const fetcher = (url: string) =>
  fetch(`${API_BASE}${url}`).then(r => r.json())
```

**Recommended approach:** Deploy FastAPI as the backend on any server,
and the Next.js frontend on Vercel pointed at it. This is cleaner than
trying to serve static files from FastAPI.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABRICKS_HOST` | Yes | Workspace hostname (e.g. `adb-123.4.azuredatabricks.net`) |
| `DATABRICKS_HTTP_PATH` | Yes | SQL warehouse path (e.g. `/sql/1.0/warehouses/abc123`) |
| `DATABRICKS_TOKEN` | Yes | Personal access token or service principal token |
| `DATABRICKS_CATALOG` | No | Catalog name (default: `ironforge`) |
| `DATABRICKS_SCHEMA` | No | Schema name (default: `trading`) |
| `TRADIER_API_KEY` | Yes | Production API key for live market quotes |
| `TRADIER_BASE_URL` | No | Override Tradier URL (default: production) |
| `TRADIER_SANDBOX_KEY_USER` | No | Sandbox key for User account |
| `TRADIER_SANDBOX_KEY_MATT` | No | Sandbox key for Matt account |
| `TRADIER_SANDBOX_KEY_LOGAN` | No | Sandbox key for Logan account |
| `CORS_ORIGINS` | No | Comma-separated allowed origins for CORS |

## Testing

### Verify tables exist:
```sql
USE CATALOG ironforge;
USE SCHEMA trading;
SHOW TABLES;
```

### Verify paper accounts are seeded:
```sql
SELECT * FROM flame_paper_account;
SELECT * FROM spark_paper_account;
```

### Test scanner manually:
```python
from ironforge_scanner import run_scan_cycle
run_scan_cycle()
```

### Test API:
```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/flame/status
curl http://localhost:8000/api/spark/status
```
