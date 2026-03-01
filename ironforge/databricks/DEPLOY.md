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
                               │  Quartz: 0/5 8-15 MF │
                               └──────────────────────┘
                                          │
                               ┌──────────▼───────────┐
                               │  Tradier API          │
                               │  Production (quotes)  │
                               │  Sandbox (3 accounts) │
                               └──────────────────────┘
```

### Scanner Modes

| Mode | `SCANNER_MODE` | Behavior | Use Case |
|------|----------------|----------|----------|
| **Single scan** (default) | `single` | Runs one scan cycle, exits | Databricks Job (cron) |
| **Loop** | `loop` | Infinite loop, 5-min sleep | Notebook testing |

### Data Flow

- **FLAME (2DTE)**: Paper trades + mirrors to 3 Tradier sandbox accounts
- **SPARK (1DTE)**: Paper trades only (no sandbox mirroring)

### PDT Rules

- Paper accounts **ARE** subject to PDT (3 day trades per rolling 5 business days)
- If PDT blocked → **both** paper AND sandbox are skipped (sandbox mirrors paper)
- A day trade = position opened AND closed on the same calendar day
- PDT log entry created on OPEN, `is_day_trade` calculated on CLOSE

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

## Step 3: Deploy Scanner as Databricks Scheduled Job

The scanner runs in **single-scan mode** by default: it scans once, then exits.
The Databricks Job scheduler fires it every 5 minutes via cron.

### 3a. Upload the scanner

Upload `ironforge_scanner.py` to your workspace. Options:
- Databricks Repos (Git integration)
- Workspace Files via UI
- DBFS upload:
  ```bash
  databricks fs cp ironforge_scanner.py dbfs:/ironforge/ironforge_scanner.py
  ```

### 3b. Create the Job

**In Databricks UI:**

1. Go to **Workflows** > **Jobs** > **Create Job**

2. **Job name**: `IronForge Scanner`

3. **Task**:
   - **Task name**: `ironforge-scanner`
   - **Type**: **Notebook** (NOT "Python script")
   - **Source**: Workspace (or Git provider if using Repos)
   - **Path**: Browse to `ironforge_scanner.py`

   > **Why Notebook, not Python script?** The scanner uses `spark.sql()` for
   > all database operations. The Databricks runtime injects the `spark` session
   > automatically for Notebook tasks. Python script tasks do NOT get `spark`.

4. **Cluster**:
   - **Single node** (no workers needed — scanner is lightweight)
   - **Compute type**: Jobs Compute (cheaper than All-Purpose)
   - Instance type: smallest available (e.g., `Standard_DS3_v2` on Azure)
   - Databricks Runtime: **14.3 LTS** or later

5. **Environment variables** (set in **Advanced** > **Environment variables**):
   ```
   TRADIER_API_KEY=<your-production-tradier-key>
   TRADIER_SANDBOX_KEY_USER=<sandbox-key-user>
   TRADIER_SANDBOX_KEY_MATT=<sandbox-key-matt>
   TRADIER_SANDBOX_KEY_LOGAN=<sandbox-key-logan>
   DATABRICKS_CATALOG=alpha_prime
   DATABRICKS_SCHEMA=ironforge
   SCANNER_MODE=single
   ```

   **7 env vars total.** API keys come from Job config, NOT hardcoded in code.

6. **Schedule**:
   - **Trigger type**: Scheduled
   - **Cron expression**: `0 0/5 8-15 ? * MON-FRI` (Quartz format: every 5 min, 8AM-3PM CT, weekdays)
   - **Timezone**: `America/Chicago`

   > **Cluster warm-up**: The cron starts at 8:00 AM, and the scanner has a
   > built-in warm-up window (8:20-8:29 CT). When triggered during this window,
   > instead of exiting immediately, the scanner sleeps until 8:30 AM and then
   > runs the first scan. This eliminates the 5-10 minute cold-start delay at
   > market open. Runs before 8:20 and after 3:00 PM exit immediately (< 1 sec).
   >
   > The previous `*/5 * * * *` cron (24/7/365) works too but wastes cluster
   > spin-ups overnight and on weekends.

7. **Retries**: 1 retry on failure, 60 second delay

8. **Alerts** (optional): Email on failure

9. Click **Save** > **Run Now** (to test)

### 3c. Verify It's Running

```sql
-- Check heartbeat is updating (should show last_heartbeat within 5-10 min)
SELECT * FROM alpha_prime.ironforge.bot_heartbeats;

-- Check scan count is incrementing
SELECT bot_name, scan_count, last_heartbeat
FROM alpha_prime.ironforge.bot_heartbeats;

-- Check logs are being written
SELECT * FROM alpha_prime.ironforge.flame_logs
ORDER BY log_time DESC LIMIT 10;

SELECT * FROM alpha_prime.ironforge.spark_logs
ORDER BY log_time DESC LIMIT 10;
```

**Healthy output during market hours:**
- `last_heartbeat` within last 5-10 minutes
- `status` = `active`
- `scan_count` incrementing

**Healthy output outside market hours:**
- Job runs succeed quickly (< 5 seconds)
- No new heartbeat updates (scanner exits before scanning)
- Log shows "Market closed — exiting"

### 3d. Alternative: Run as Notebook (Testing Only)

For interactive testing, open the scanner in a notebook and set loop mode:

```python
import os
os.environ["SCANNER_MODE"] = "loop"  # Override to loop mode
os.environ["TRADIER_API_KEY"] = dbutils.secrets.get("ironforge", "tradier_api_key")
# Set other env vars as needed...

# Then click "Run All" — it will loop every 5 minutes until you stop it
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
| `TRADIER_API_KEY` | **Yes** | Production key for live SPY/VIX quotes |
| `TRADIER_SANDBOX_KEY_USER` | No | Customer 1 sandbox key (FLAME mirror) |
| `TRADIER_SANDBOX_KEY_MATT` | No | Customer 2 sandbox key (FLAME mirror) |
| `TRADIER_SANDBOX_KEY_LOGAN` | No | Customer 3 sandbox key (FLAME mirror) |
| `DATABRICKS_CATALOG` | No | `alpha_prime` (default) |
| `DATABRICKS_SCHEMA` | No | `ironforge` (default) |
| `SCANNER_MODE` | No | `single` (default) or `loop` for notebook testing |

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

## Market Hours Reference

All times in **Central Time (America/Chicago)**.

| Window | Time | Purpose |
|--------|------|---------|
| Warm-up window | 8:20 - 8:29 AM CT | Cluster warm-up, scanner waits for open |
| Entry window | 8:30 AM - 2:00 PM CT | New trades can be opened |
| Monitoring window | 8:30 AM - 3:00 PM CT | Open positions are monitored |
| EOD cutoff | 2:45 PM CT | All positions force-closed |
| Weekends | Skipped | Scanner exits immediately |

The cron fires during market hours only (`0 0/5 8-15 ? * MON-FRI`). During the warm-up
window (8:20-8:29), the scanner holds the cluster alive until 8:30 so the first
real scan has zero cold-start delay. Outside market hours, the scanner exits in
under 1 second.

---

## Troubleshooting

### Scanner not trading
1. Check `TRADIER_API_KEY` is set and is a **production** key (not sandbox)
2. Check market is open (8:30 AM - 3:00 PM CT, weekdays)
3. Check heartbeats: `SELECT * FROM alpha_prime.ironforge.bot_heartbeats`
4. Check logs: `SELECT * FROM alpha_prime.ironforge.flame_logs ORDER BY log_time DESC LIMIT 20`
5. Check PDT status: `SELECT * FROM alpha_prime.ironforge.flame_pdt_log WHERE trade_date >= CURRENT_DATE - 8 ORDER BY opened_at DESC`

### Scanner shows "spark not available"
The Job task type must be **Notebook**, not "Python script". Python script tasks
don't get the `spark` session injected by the Databricks runtime.

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

### PDT blocked when it shouldn't be
```sql
-- Check rolling 5-day window
SELECT trade_date, symbol, position_id, is_day_trade, opened_at, closed_at
FROM alpha_prime.ironforge.flame_pdt_log
WHERE is_day_trade = TRUE
AND trade_date >= CURRENT_DATE - 8
ORDER BY trade_date DESC;
```
Day trades drop off after 5 business days. If all 3 slots are used, wait for the
oldest one to age out.
