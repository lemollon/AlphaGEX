# Databricks notebook source
# MAGIC %md
# MAGIC # IronForge Secrets Configuration
# MAGIC **Run this notebook ONCE to store and verify your Tradier API key.**
# MAGIC
# MAGIC ## How to store your Tradier API key in Databricks Secrets
# MAGIC
# MAGIC Run these commands in a terminal (Databricks CLI) or use the Secrets API:
# MAGIC
# MAGIC ```bash
# MAGIC # 1. Create a secret scope (one-time)
# MAGIC databricks secrets create-scope ironforge
# MAGIC
# MAGIC # 2. Store your Tradier SANDBOX API key
# MAGIC databricks secrets put-secret ironforge tradier-api-key
# MAGIC #    (paste your sandbox key when prompted)
# MAGIC
# MAGIC # 3. (Optional) Store sandbox account ID
# MAGIC databricks secrets put-secret ironforge tradier-account-id
# MAGIC
# MAGIC # 4. (Optional) Store your SQL warehouse HTTP path
# MAGIC databricks secrets put-secret ironforge databricks-http-path
# MAGIC ```
# MAGIC
# MAGIC **Alternative**: Use the Databricks UI:
# MAGIC 1. Go to **Settings > Secret Management**
# MAGIC 2. Create scope: `ironforge`
# MAGIC 3. Add secret: `tradier-api-key` with your Tradier sandbox API key

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1: Load the secret and set environment variable

# COMMAND ----------

import os

# Load Tradier API key from Databricks secrets
# Tries multiple possible secret names for flexibility
tradier_key = ""
for secret_name in ["tradier-api-key", "tradier-sandbox-api-key"]:
    try:
        tradier_key = dbutils.secrets.get("ironforge", secret_name)
        if tradier_key:
            os.environ["TRADIER_API_KEY"] = tradier_key
            print(f"Tradier API key loaded from secrets (ironforge/{secret_name})")
            break
    except Exception:
        pass

if not tradier_key:
    print("ERROR: Could not load Tradier API key from secrets.")
    print("")
    print("You need to create the secret first. Run in a terminal:")
    print('  databricks secrets create-scope ironforge')
    print('  databricks secrets put-secret ironforge tradier-api-key')
    print("")
    print("Or set it directly in this notebook:")
    print('  os.environ["TRADIER_API_KEY"] = "your-key-here"')

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2: Verify the key works with Tradier Sandbox API

# COMMAND ----------

import requests

api_key = os.environ.get("TRADIER_API_KEY", "")
if not api_key:
    print("ERROR: TRADIER_API_KEY not set. Run Step 1 first.")
else:
    # Test against SANDBOX API (what the bots currently use)
    resp = requests.get(
        "https://sandbox.tradier.com/v1/markets/quotes",
        params={"symbols": "SPY"},
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        timeout=10,
    )
    if resp.ok:
        data = resp.json()
        quote = data.get("quotes", {}).get("quote", {})
        last = quote.get("last", "N/A")
        print(f"Tradier SANDBOX API connected!")
        print(f"  SPY last price: ${last}")
        print(f"  API key: ...{api_key[-4:]}")
        print("")
        print("Your Tradier sandbox key is working. You can now run:")
        print("  - 02_flame_bot (FLAME 2DTE Iron Condor)")
        print("  - 03_spark_bot (SPARK 1DTE Iron Condor)")
    else:
        print(f"ERROR: Tradier sandbox API returned {resp.status_code}")
        print(f"  Response: {resp.text[:200]}")
        print("")
        print("Make sure you're using a SANDBOX API key.")
        print("  Get one at: https://developer.tradier.com")
        print("  Sandbox base URL: https://sandbox.tradier.com/v1")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3: Verify Databricks tables exist

# COMMAND ----------

tables = spark.sql("SHOW TABLES IN alpha_prime.default").collect()
ironforge_tables = [t.tableName for t in tables if "flame" in t.tableName or "spark" in t.tableName or "heartbeat" in t.tableName]

if ironforge_tables:
    print(f"Found {len(ironforge_tables)} IronForge tables:")
    for t in sorted(ironforge_tables):
        print(f"  - {t}")
else:
    print("No IronForge tables found!")
    print("Run 01_ironforge_setup first to create the tables.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Done!
# MAGIC
# MAGIC If everything above shows green:
# MAGIC - Tradier API key is stored in secrets
# MAGIC - API key connects to Tradier sandbox successfully
# MAGIC - Delta Lake tables exist
# MAGIC
# MAGIC **Next steps:**
# MAGIC 1. Run **02_flame_bot** to test a FLAME trading cycle
# MAGIC 2. Run **03_spark_bot** to test a SPARK trading cycle
# MAGIC 3. Set up **Scheduled Workflows** to run them every 5 minutes during market hours
