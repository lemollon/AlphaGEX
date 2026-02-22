"""
IronForge Deployment Guide - Run as a Databricks Notebook
==========================================================

Copy this entire databricks/ folder to your Databricks workspace at:
    /Workspace/Users/<your-email>/ironforge/

Then open this file as a notebook and run each cell in order.

Prerequisites:
  - Azure Databricks workspace with Unity Catalog enabled
  - Catalog "alpha_prime" exists (you already have this)
  - A SQL warehouse or cluster running
  - Tradier API key (production, not sandbox)
"""

# COMMAND ----------

# STEP 1: Install Python dependencies
# =====================================
# Run this cell once. These packages will be available for the session.
# For persistent installs, add them to your cluster's Libraries tab.

%pip install databricks-sql-connector>=3.0.0 requests>=2.31.0 dash>=2.14.0 dash-bootstrap-components>=1.5.0 plotly>=5.18.0

# COMMAND ----------

# STEP 2: Set your environment variables
# ========================================
# Option A: Set them right here (quick start - NOT for production)
# Option B: Use Databricks Secrets (recommended for production)
#
# For Option A, uncomment and fill in these lines:

# import os
# os.environ["TRADIER_API_KEY"] = "your-tradier-production-api-key"
#
# The following are auto-detected when running inside Databricks,
# so you usually do NOT need to set them:
# os.environ["DATABRICKS_SERVER_HOSTNAME"] = "adb-xxxx.azuredatabricks.net"
# os.environ["DATABRICKS_HTTP_PATH"] = "/sql/1.0/warehouses/xxxx"
# os.environ["DATABRICKS_TOKEN"] = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()

# For Option B (Secrets), create a scope and secrets:
#   databricks secrets create-scope ironforge
#   databricks secrets put-secret ironforge tradier-api-key
# Then use:
# import os
# os.environ["TRADIER_API_KEY"] = dbutils.secrets.get("ironforge", "tradier-api-key")

print("Environment configured.")

# COMMAND ----------

# STEP 3: Verify your connection
# ================================
# This cell confirms your Databricks SQL connection works.

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(".")))

# Auto-detect Databricks connection if running inside a notebook
if not os.environ.get("DATABRICKS_SERVER_HOSTNAME"):
    try:
        ctx = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
        os.environ["DATABRICKS_SERVER_HOSTNAME"] = ctx.extraContext().apply("api_url").replace("https://", "")
        os.environ["DATABRICKS_TOKEN"] = ctx.apiToken().get()
        # You still need to set HTTP_PATH manually or via secrets
        print("Auto-detected hostname and token from notebook context.")
    except Exception as e:
        print(f"Could not auto-detect: {e}")
        print("Set DATABRICKS_SERVER_HOSTNAME and DATABRICKS_TOKEN manually in Step 2.")

from config import DatabricksConfig

valid, msg = DatabricksConfig.validate()
if valid:
    print(f"Connection config OK")
    print(f"  Catalog: {DatabricksConfig.CATALOG}")
    print(f"  Schema:  {DatabricksConfig.SCHEMA}")
    print(f"  Tradier: {'configured' if DatabricksConfig.TRADIER_API_KEY else 'MISSING'}")
else:
    print(f"CONFIG ERROR: {msg}")
    print("Fix the missing variables in Step 2 and re-run.")

# COMMAND ----------

# STEP 4: Create Delta Lake tables
# ===================================
# This creates 15 tables in alpha_prime.default:
#   - flame_positions, flame_signals, flame_daily_perf, flame_logs,
#     flame_equity_snapshots, flame_paper_account, flame_pdt_log
#   - spark_positions, spark_signals, spark_daily_perf, spark_logs,
#     spark_equity_snapshots, spark_paper_account, spark_pdt_log
#   - bot_heartbeats (shared)
#
# Safe to run multiple times - uses CREATE TABLE IF NOT EXISTS.

from setup_tables import setup_all_tables

setup_all_tables()
print("\nAll tables created in alpha_prime.default")

# COMMAND ----------

# STEP 5: Verify tables were created
# =====================================

display(spark.sql("SHOW TABLES IN alpha_prime.default LIKE '*flame*'"))

# COMMAND ----------

display(spark.sql("SHOW TABLES IN alpha_prime.default LIKE '*spark*'"))

# COMMAND ----------

display(spark.sql("SHOW TABLES IN alpha_prime.default LIKE 'bot_heartbeats'"))

# COMMAND ----------

# STEP 6: Initialize paper accounts
# ====================================
# Creates the starting paper accounts ($5,000 each) for both bots.

from trading.db import TradingDatabase

flame_db = TradingDatabase(bot_name="FLAME", dte_mode="2DTE")
spark_db = TradingDatabase(bot_name="SPARK", dte_mode="1DTE")

flame_db.initialize_paper_account(5000.0)
spark_db.initialize_paper_account(5000.0)

# Verify
flame_acct = flame_db.get_paper_account()
spark_acct = spark_db.get_paper_account()
print(f"FLAME account: ${flame_acct.balance:,.2f} (active={flame_acct.is_active})")
print(f"SPARK account: ${spark_acct.balance:,.2f} (active={spark_acct.is_active})")

# COMMAND ----------

# STEP 7: Test Tradier connection
# ==================================
# Verifies your Tradier API key works and can pull live market data.

from trading.tradier_client import TradierClient

client = TradierClient()
spy = client.get_quote("SPY")
vix_val = client.get_vix()

if spy and spy.get("last"):
    print(f"Tradier API connected!")
    print(f"  SPY:  ${spy['last']:.2f}")
    print(f"  VIX:  {vix_val:.1f}" if vix_val else "  VIX:  unavailable")
else:
    print("Tradier API FAILED - check your TRADIER_API_KEY")

# COMMAND ----------

# STEP 8: Test a single FLAME trading cycle (dry run)
# =====================================================
# This runs one scan cycle. During market hours it will:
#   - Check trading window (8:30-14:45 CT)
#   - Look for open positions
#   - Generate a signal (if no position exists)
#   - Open a paper trade (if signal is valid)
#
# Outside market hours, it will just report "outside_window".

from trading.trader import create_flame_trader

flame = create_flame_trader()
result = flame.run_cycle()

print(f"Action:  {result['action']}")
print(f"Traded:  {result['traded']}")
print(f"Details: {result.get('details', {})}")

# COMMAND ----------

# STEP 9: Test a single SPARK trading cycle (dry run)
# =====================================================

from trading.trader import create_spark_trader

spark_trader = create_spark_trader()
result = spark_trader.run_cycle()

print(f"Action:  {result['action']}")
print(f"Traded:  {result['traded']}")
print(f"Details: {result.get('details', {})}")

# COMMAND ----------

"""
STEP 10: Set up scheduled Workflows (manual steps in the UI)
==============================================================

Now that everything works, create two Workflows to run automatically.

A. CREATE FLAME WORKFLOW:
   1. Go to: Workflows > Create Job
   2. Name: "FLAME Trading"
   3. Task:
      - Task name: run_flame_cycle
      - Type: Python script
      - Source: Workspace
      - Path: /Workspace/Users/<your-email>/ironforge/jobs/run_flame.py
      - Cluster: your running cluster (or Serverless)
   4. Schedule:
      - Click "Add schedule"
      - Schedule type: Scheduled
      - Every 5 minutes
      - Days: Monday-Friday only
      - Time range: roughly 8:30 AM - 2:45 PM Central
        (or in UTC: 14:30 - 20:45)
      - Timezone: America/Chicago (or UTC)
   5. Advanced > Timeout: 120 seconds
   6. Click "Create"

B. CREATE SPARK WORKFLOW:
   - Same as above but:
     - Name: "SPARK Trading"
     - Path: /Workspace/Users/<your-email>/ironforge/jobs/run_spark.py

C. ENVIRONMENT VARIABLES for the jobs:
   - In each job's task settings, under "Environment variables" add:
     TRADIER_API_KEY = <your key>
   - Or use the Databricks Secrets approach from Step 2.


STEP 11: Deploy the IronForge Dashboard (manual steps)
========================================================

Option A: Databricks App (recommended)
  1. Go to: Compute > Apps > Create App
  2. Name: "ironforge"
  3. Source: /Workspace/Users/<your-email>/ironforge/webapp/app.py
  4. Framework: Dash
  5. Environment variables:
     - TRADIER_API_KEY (or use secrets)
     - DATABRICKS_SERVER_HOSTNAME
     - DATABRICKS_HTTP_PATH
     - DATABRICKS_TOKEN
  6. Deploy

Option B: Run from a notebook (quick testing)
  Just run this cell to start the dashboard locally:
"""

# Uncomment to run the dashboard right here (blocks the cell):
# from webapp.app import app
# app.run(debug=False, host="0.0.0.0", port=8050)

# COMMAND ----------

"""
DONE! Your IronForge deployment checklist:

  [x] Step 1:  Dependencies installed
  [x] Step 2:  Environment variables configured
  [x] Step 3:  Connection verified
  [x] Step 4:  Delta Lake tables created
  [x] Step 5:  Tables verified
  [x] Step 6:  Paper accounts initialized ($5,000 each)
  [x] Step 7:  Tradier API connected
  [x] Step 8:  FLAME test cycle ran
  [x] Step 9:  SPARK test cycle ran
  [ ] Step 10: Workflows created (do in UI)
  [ ] Step 11: Dashboard deployed (do in UI)

Both bots will trade SPY Iron Condors automatically during market hours:
  - FLAME: 2DTE, scans every 5 min, max 1 trade/day
  - SPARK: 1DTE, scans every 5 min, max 1 trade/day

Monitor at: https://<your-workspace>.azuredatabricks.net/apps/ironforge
"""
