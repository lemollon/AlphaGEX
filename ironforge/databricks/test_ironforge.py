# Databricks notebook source

# COMMAND ----------

# MAGIC %md
# MAGIC # IronForge System Test
# MAGIC Run All to verify: DB tables, Tradier keys, sandbox accounts, and dashboard data.

# COMMAND ----------

# Cell 1: Setup
import os, json, requests
from datetime import datetime

os.environ["TRADIER_API_KEY"] = "HbOM7HNC6Ibs6QAE6hYgr02rpx2K"
os.environ["TRADIER_SANDBOX_KEY_USER"] = "iPidGGnYrhzjp6vGBBQw8HyqF0xj"
os.environ["TRADIER_SANDBOX_KEY_MATT"] = "AGoNTv6o6GKMKT8uc7ooVNOct0e0"
os.environ["TRADIER_SANDBOX_KEY_LOGAN"] = "GSpjmwhuvY4tPNRYLJoH7f7UYT"

PROD_URL = "https://api.tradier.com/v1"
SANDBOX_URL = "https://sandbox.tradier.com/v1"
SANDBOX_ACCOUNTS = {
    "USER":  {"key": os.environ["TRADIER_SANDBOX_KEY_USER"],  "account_id": "VA39284047"},
    "MATT":  {"key": os.environ["TRADIER_SANDBOX_KEY_MATT"],  "account_id": "VA55391129"},
    "LOGAN": {"key": os.environ["TRADIER_SANDBOX_KEY_LOGAN"], "account_id": "VA59240884"},
}

print("Keys and account IDs loaded")

# COMMAND ----------

# Cell 2: Test database tables
tables = ["bot_heartbeats", "flame_paper_account", "spark_paper_account", "flame_positions", "spark_positions", "flame_logs", "spark_logs", "flame_config", "spark_config"]
for t in tables:
    try:
        cnt = spark.sql(f"SELECT COUNT(*) AS c FROM alpha_prime.ironforge.{t}").collect()[0].c
        print(f"  {t}: {cnt} rows")
    except Exception as e:
        print(f"  {t}: ERROR - {e}")

# COMMAND ----------

# Cell 3: Paper account balances
print("FLAME:")
display(spark.sql("SELECT * FROM alpha_prime.ironforge.flame_paper_account"))
print("SPARK:")
display(spark.sql("SELECT * FROM alpha_prime.ironforge.spark_paper_account"))

# COMMAND ----------

# Cell 4: Test production Tradier key (SPY + VIX quotes)
r = requests.get(f"{PROD_URL}/markets/quotes", params={"symbols": "SPY,VIX"}, headers={"Authorization": f"Bearer {os.environ['TRADIER_API_KEY']}", "Accept": "application/json"}, timeout=10)
print(f"Status: {r.status_code}")
if r.ok:
    quotes = r.json().get("quotes", {}).get("quote", [])
    if isinstance(quotes, dict): quotes = [quotes]
    for q in quotes:
        print(f"  {q['symbol']}: ${q.get('last', 'N/A')}")
    SPY_PRICE = float([q for q in quotes if q["symbol"] == "SPY"][0]["last"])
else:
    print(f"FAILED: {r.text[:300]}")
    SPY_PRICE = 0

# COMMAND ----------

# Cell 5: Verify all 3 sandbox accounts
# For each account: use hardcoded account_id if available, otherwise try auto-discover
for name, info in SANDBOX_ACCOUNTS.items():
    acct_id = info["account_id"]

    if not acct_id:
        # Try auto-discover via /user/profile
        r = requests.get(f"{SANDBOX_URL}/user/profile", headers={"Authorization": f"Bearer {info['key']}", "Accept": "application/json"}, timeout=10)
        if r.ok:
            acct = r.json().get("profile", {}).get("account", {})
            if isinstance(acct, list): acct = acct[0]
            acct_id = acct.get("account_number", "")
            info["account_id"] = acct_id
            print(f"  {name}: Auto-discovered account {acct_id}")
        else:
            print(f"  {name}: No account ID and auto-discover failed ({r.status_code}) {r.text[:200]}")
            print(f"         Get the account ID from Render env var TRADIER_FORTRESS_SANDBOX_ACCOUNT_ID_{{2,3}}")
            continue

    # Balance check
    r = requests.get(f"{SANDBOX_URL}/accounts/{acct_id}/balances", headers={"Authorization": f"Bearer {info['key']}", "Accept": "application/json"}, timeout=10)
    if r.ok:
        bal = r.json().get("balances", {})
        equity = bal.get("total_equity", bal.get("equity", "?"))
        print(f"  {name}: Account {acct_id} — equity ${equity}")
    else:
        print(f"  {name}: Account {acct_id} — FAILED ({r.status_code}) {r.text[:200]}")

# COMMAND ----------

# Cell 6: Place test IC orders on sandbox (won't fill — $0.10 limit)
if SPY_PRICE > 0 and len(SANDBOX_ACCOUNTS) > 0:
    # Get expiration 2+ days out
    r = requests.get(f"{PROD_URL}/markets/options/expirations", params={"symbol": "SPY", "includeAllRoots": "true"}, headers={"Authorization": f"Bearer {os.environ['TRADIER_API_KEY']}", "Accept": "application/json"}, timeout=10)
    exps = r.json().get("expirations", {}).get("date", [])
    today = datetime.now().date()
    exp = next((e for e in exps if (datetime.strptime(e, "%Y-%m-%d").date() - today).days >= 2), None)

    if exp:
        exp_fmt = datetime.strptime(exp, "%Y-%m-%d").strftime("%y%m%d")
        ps = round((SPY_PRICE - 10) / 5) * 5
        pl = ps - 5
        cs = round((SPY_PRICE + 10) / 5) * 5
        cl = cs + 5
        print(f"Exp: {exp} | Put {pl}/{ps} - Call {cs}/{cl}")

        def occ(strike, t): return f"SPY{exp_fmt}{t}{int(strike*1000):08d}"

        for name, info in SANDBOX_ACCOUNTS.items():
            if not info.get("account_id"):
                print(f"  {name}: SKIP (no account ID)")
                continue
            order_data = {"class": "multileg", "symbol": "SPY", "type": "credit", "duration": "day", "price": "0.10",
                          "option_symbol[0]": occ(ps,"P"), "side[0]": "sell_to_open", "quantity[0]": "1",
                          "option_symbol[1]": occ(pl,"P"), "side[1]": "buy_to_open", "quantity[1]": "1",
                          "option_symbol[2]": occ(cs,"C"), "side[2]": "sell_to_open", "quantity[2]": "1",
                          "option_symbol[3]": occ(cl,"C"), "side[3]": "buy_to_open", "quantity[3]": "1"}
            r = requests.post(f"{SANDBOX_URL}/accounts/{info['account_id']}/orders", data=order_data, headers={"Authorization": f"Bearer {info['key']}", "Accept": "application/json"}, timeout=10)
            if r.ok:
                oid = r.json().get("order", {}).get("id", "?")
                print(f"  {name}: Order #{oid}")
            else:
                print(f"  {name}: FAILED ({r.status_code}) {r.text[:200]}")
    else:
        print("No expiration found 2+ DTE")
else:
    print("SKIP: No SPY price or sandbox accounts")

# COMMAND ----------

# Cell 7: Write test heartbeats so dashboard shows data
for bot in ["FLAME", "SPARK"]:
    spark.sql(f"""
        MERGE INTO alpha_prime.ironforge.bot_heartbeats AS t
        USING (SELECT '{bot}' AS bot_name) AS s
        ON t.bot_name = s.bot_name
        WHEN MATCHED THEN UPDATE SET last_heartbeat = CURRENT_TIMESTAMP(), status = 'ok', scan_count = COALESCE(t.scan_count, 0) + 1, details = '{{"action":"test","spy":{SPY_PRICE}}}'
        WHEN NOT MATCHED THEN INSERT (bot_name, last_heartbeat, status, scan_count, details) VALUES ('{bot}', CURRENT_TIMESTAMP(), 'ok', 1, '{{"action":"test","spy":{SPY_PRICE}}}')
    """)
    print(f"  {bot} heartbeat written")

spark.sql(f"""
    INSERT INTO alpha_prime.ironforge.flame_logs (log_time, level, message, details, dte_mode)
    VALUES (CURRENT_TIMESTAMP(), 'INFO', 'Test notebook: system verified', '{{"spy":{SPY_PRICE}}}', '2DTE')
""")
print("  Test log written")

# COMMAND ----------

# Cell 8: Verify — show what the dashboard will see
print("Heartbeats:")
display(spark.sql("SELECT * FROM alpha_prime.ironforge.bot_heartbeats"))
print("Recent logs:")
display(spark.sql("SELECT * FROM alpha_prime.ironforge.flame_logs ORDER BY log_time DESC LIMIT 5"))
