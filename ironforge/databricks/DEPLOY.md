# IronForge Databricks Deployment Guide

## Architecture

```
┌────────────────────────┐     ┌──────────────────────┐
│  Next.js Dashboard     │────▶│  Databricks SQL       │
│  (Vercel)              │     │  REST API (direct)    │
│  databricks/webapp/    │     │                       │
└────────────────────────┘     └──────────┬───────────┘
                                          │
                               ┌──────────▼───────────┐
                               │  Databricks Tables    │
                               │  alpha_prime.ironforge│
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
                               │  Production (quotes)  │
                               │  Sandbox (3 accounts) │
                               └──────────────────────┘
```

### Data Flow

- **FLAME (2DTE)**: Paper trades + mirrors to 3 Tradier sandbox accounts
- **SPARK (1DTE)**: Paper trades only (no sandbox mirroring)

---

## Step 1: Create Tables

Upload `01_setup_tables.sql` to a Databricks notebook and run it.
This creates the `alpha_prime` catalog, `ironforge` schema, and all 15 tables.

Verify tables exist:
```sql
USE CATALOG alpha_prime;
USE SCHEMA ironforge;
SHOW TABLES;
```

Verify paper accounts are seeded:
```sql
SELECT * FROM alpha_prime.ironforge.flame_paper_account;
SELECT * FROM alpha_prime.ironforge.spark_paper_account;
```

---

## Step 2: Verify Tradier API Keys

### Key Types Required

| Key | Purpose | Base URL | Required? |
|-----|---------|----------|-----------|
| `TRADIER_API_KEY` | Live SPY/VIX quotes, options chains | `api.tradier.com` | **YES** (scanner won't trade without it) |
| `TRADIER_SANDBOX_KEY_USER` | Mirror FLAME orders to User sandbox | `sandbox.tradier.com` | Optional (FLAME trades still paper-record without it) |
| `TRADIER_SANDBOX_KEY_MATT` | Mirror FLAME orders to Matt sandbox | `sandbox.tradier.com` | Optional |
| `TRADIER_SANDBOX_KEY_LOGAN` | Mirror FLAME orders to Logan sandbox | `sandbox.tradier.com` | Optional |

### Test a Key

```python
import requests

KEY = "your-key-here"

# Test production
r = requests.get(
    "https://api.tradier.com/v1/markets/quotes",
    params={"symbols": "SPY"},
    headers={"Authorization": f"Bearer {KEY}", "Accept": "application/json"},
)
print(f"Production: {r.status_code}")  # 200 = production key, 401 = not

# Test sandbox
r = requests.get(
    "https://sandbox.tradier.com/v1/markets/quotes",
    params={"symbols": "SPY"},
    headers={"Authorization": f"Bearer {KEY}", "Accept": "application/json"},
)
print(f"Sandbox: {r.status_code}")  # 200 = sandbox key, 401 = not
```

### Test Sandbox Account Discovery

Each sandbox key auto-discovers its account ID:
```python
r = requests.get(
    "https://sandbox.tradier.com/v1/user/profile",
    headers={"Authorization": f"Bearer {KEY}", "Accept": "application/json"},
)
print(r.json())  # Look for profile.account.account_number
```

### CRITICAL: Production Key for Quotes

The scanner uses **production** Tradier (`api.tradier.com`) for all quote functions:
- `get_quote()` — SPY/VIX prices
- `get_option_quote()` — individual option leg prices
- `get_option_expirations()` — available expirations
- `get_ic_entry_credit()` — entry credit from real bid/ask
- `get_ic_mark_to_market()` — MTM for position monitoring

Sandbox quotes (`sandbox.tradier.com`) are stale/unreliable — **never** use them
for quotes. This was the bb9773c bug.

The scanner uses **sandbox** Tradier for order execution only (FLAME only):
- `place_ic_order_all_accounts()` — open IC in all 3 sandbox accounts
- `close_ic_order_all_accounts()` — close IC in all 3 sandbox accounts
- `_get_account_id_for_key()` — auto-discover account ID from profile

---

## Step 3: Deploy Scanner as Databricks Job

### Option A: Databricks Job (Recommended)

#### 3a. Upload the scanner

Upload `ironforge_scanner.py` to your workspace. Options:
- Databricks Repos (Git integration)
- DBFS upload:
  ```bash
  databricks fs cp ironforge_scanner.py dbfs:/ironforge/ironforge_scanner.py
  ```
- Workspace Files via UI

#### 3b. Create the Job

**In Databricks UI:**

1. Go to **Workflows** > **Jobs** > **Create Job**
2. Name: `IronForge Scanner`
3. Task type: **Python script**
4. Source: path to `ironforge_scanner.py`
5. Cluster:
   - **Single node** (no workers needed)
   - Instance type: smallest available (e.g., `Standard_DS3_v2` on Azure)
   - Databricks Runtime: **15.4 LTS** or latest LTS
   - Install libraries: `databricks-sql-connector`, `requests`
     (via cluster Libraries tab or `%pip install` in init script)

6. Environment variables (set in **Advanced** > **Environment variables**):
   ```
   DATABRICKS_HOST=adb-3765346025813768.8.azuredatabricks.net
   DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/4970853897f5a656
   DATABRICKS_TOKEN=<your-databricks-pat>
   DATABRICKS_CATALOG=alpha_prime
   DATABRICKS_SCHEMA=ironforge
   TRADIER_API_KEY=<production-key-for-quotes>
   TRADIER_SANDBOX_KEY_USER=<customer-1-sandbox-key>
   TRADIER_SANDBOX_KEY_MATT=<customer-2-sandbox-key>
   TRADIER_SANDBOX_KEY_LOGAN=<customer-3-sandbox-key>
   ```

7. Schedule: **Continuous** (the scanner has its own 5-minute sleep loop)
   - OR: Cron `*/5 * * * *` (every 5 min) if you want Databricks to manage the schedule
   - If using cron, change `main()` to call `run_scan_cycle()` once (no loop)

8. Retries: Enable **auto-restart on failure** (max retries: unlimited)

9. Alerts: Set email/Slack notification on failure

#### 3c. Verify It's Running

```sql
-- Check heartbeat (updated every scan cycle)
SELECT * FROM alpha_prime.ironforge.bot_heartbeats;

-- Check recent logs
SELECT * FROM alpha_prime.ironforge.flame_logs
ORDER BY log_time DESC LIMIT 10;

SELECT * FROM alpha_prime.ironforge.spark_logs
ORDER BY log_time DESC LIMIT 10;
```

Healthy output: heartbeat `last_heartbeat` within last 5-10 minutes,
status = `active` during market hours or `idle` outside.

### Option B: Run as Notebook

```python
# %pip install databricks-sql-connector requests
import os
os.environ["DATABRICKS_HOST"] = spark.conf.get("spark.databricks.workspaceUrl")
os.environ["DATABRICKS_HTTP_PATH"] = "/sql/1.0/warehouses/4970853897f5a656"
os.environ["DATABRICKS_TOKEN"] = dbutils.secrets.get("ironforge", "databricks_token")
os.environ["TRADIER_API_KEY"] = dbutils.secrets.get("ironforge", "tradier_api_key")
# Add sandbox keys from secrets if needed:
# os.environ["TRADIER_SANDBOX_KEY_USER"] = dbutils.secrets.get("ironforge", "sandbox_user")

from ironforge_scanner import main
main()
```

---

## Step 4: Connect Dashboard (Vercel)

The Next.js dashboard at `databricks/webapp/` connects directly to Databricks SQL
via the REST Statement Execution API — no FastAPI needed.

### Vercel Environment Variables

```
DATABRICKS_SERVER_HOSTNAME=adb-3765346025813768.8.azuredatabricks.net
DATABRICKS_WAREHOUSE_ID=4970853897f5a656
DATABRICKS_TOKEN=<databricks-pat>
DATABRICKS_CATALOG=alpha_prime
DATABRICKS_SCHEMA=ironforge
TRADIER_API_KEY=<production-key-for-force-trade-and-close-buttons>
```

### Optional: FastAPI Backend

If you want to deploy the FastAPI layer (`ironforge_api.py`) instead:

```bash
pip install -r requirements.txt
export DATABRICKS_HOST=adb-3765346025813768.8.azuredatabricks.net
export DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/4970853897f5a656
export DATABRICKS_TOKEN=your-token
export TRADIER_API_KEY=your-production-key
uvicorn ironforge_api:app --host 0.0.0.0 --port 8000
```

---

## Environment Variables — Complete Reference

### Databricks Job (Scanner)

| Variable | Required | Value |
|----------|----------|-------|
| `DATABRICKS_HOST` | Yes | `adb-3765346025813768.8.azuredatabricks.net` |
| `DATABRICKS_HTTP_PATH` | Yes | `/sql/1.0/warehouses/4970853897f5a656` |
| `DATABRICKS_TOKEN` | Yes | Personal access token |
| `DATABRICKS_CATALOG` | No | `alpha_prime` (default) |
| `DATABRICKS_SCHEMA` | No | `ironforge` (default) |
| `TRADIER_API_KEY` | **Yes** | Production key for live SPY/VIX quotes |
| `TRADIER_SANDBOX_KEY_USER` | No | Customer 1 sandbox key (FLAME mirror) |
| `TRADIER_SANDBOX_KEY_MATT` | No | Customer 2 sandbox key (FLAME mirror) |
| `TRADIER_SANDBOX_KEY_LOGAN` | No | Customer 3 sandbox key (FLAME mirror) |

### Vercel Dashboard

| Variable | Required | Value |
|----------|----------|-------|
| `DATABRICKS_SERVER_HOSTNAME` | Yes | `adb-3765346025813768.8.azuredatabricks.net` |
| `DATABRICKS_WAREHOUSE_ID` | Yes | `4970853897f5a656` |
| `DATABRICKS_TOKEN` | Yes | Personal access token |
| `DATABRICKS_CATALOG` | No | `alpha_prime` (default) |
| `DATABRICKS_SCHEMA` | No | `ironforge` (default) |
| `TRADIER_API_KEY` | No | Production key (only for force-trade/close buttons) |

### FastAPI Backend (Optional)

| Variable | Required | Value |
|----------|----------|-------|
| `DATABRICKS_HOST` | Yes | Workspace hostname |
| `DATABRICKS_HTTP_PATH` | Yes | SQL warehouse HTTP path |
| `DATABRICKS_TOKEN` | Yes | Personal access token |
| `DATABRICKS_CATALOG` | No | `alpha_prime` (default) |
| `DATABRICKS_SCHEMA` | No | `ironforge` (default) |
| `TRADIER_API_KEY` | Yes | Production key for quotes + force-trade |
| `TRADIER_SANDBOX_KEY_*` | No | Sandbox keys for mirroring |
| `CORS_ORIGINS` | No | Comma-separated allowed origins |

---

## Troubleshooting

### Scanner not trading
1. Check `TRADIER_API_KEY` is set and is a **production** key (not sandbox)
2. Check market is open (8:30 AM - 3:30 PM CT, weekdays)
3. Check heartbeats: `SELECT * FROM alpha_prime.ironforge.bot_heartbeats`
4. Check logs: `SELECT * FROM alpha_prime.ironforge.flame_logs ORDER BY log_time DESC LIMIT 20`

### Dashboard showing empty data
1. Verify `DATABRICKS_TOKEN` is valid
2. Verify `DATABRICKS_SERVER_HOSTNAME` matches your workspace
3. Check tables have data: `SELECT COUNT(*) FROM alpha_prime.ironforge.flame_paper_account`

### Sandbox orders not filling
1. Sandbox orders use **market** type (should fill instantly)
2. Check sandbox key is valid: test profile endpoint
3. Check scanner logs for "Sandbox IC order failed" warnings

### Paper account balance stuck
1. Paper starts at $10,000
2. Check if collateral_in_use is blocking: `SELECT * FROM alpha_prime.ironforge.flame_paper_account`
3. Reset if needed: `UPDATE alpha_prime.ironforge.flame_paper_account SET buying_power = current_balance - collateral_in_use`
