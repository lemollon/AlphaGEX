# Databricks notebook source
# MAGIC %md
# MAGIC # IronForge Setup
# MAGIC **Run this notebook ONCE to create all tables and initialize paper accounts.**
# MAGIC
# MAGIC This creates 15 Delta Lake tables in `alpha_prime.default` for the FLAME (2DTE) and SPARK (1DTE) Iron Condor paper trading bots.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1: Create Tables

# COMMAND ----------

CATALOG = "alpha_prime"
SCHEMA = "default"

# Catalog already exists — skip CREATE CATALOG to avoid storage root error
# spark.sql(f"CREATE CATALOG IF NOT EXISTS {CATALOG}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")

print(f"Catalog: {CATALOG}")
print(f"Schema:  {SCHEMA}")

# COMMAND ----------

def _t(table_name):
    return f"{CATALOG}.{SCHEMA}.{table_name}"

# COMMAND ----------

# MAGIC %md
# MAGIC ### Positions tables (FLAME + SPARK)

# COMMAND ----------

for bot in ["flame", "spark"]:
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {_t(f'{bot}_positions')} (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            position_id STRING NOT NULL,
            ticker STRING NOT NULL,
            expiration DATE NOT NULL,

            put_short_strike DECIMAL(10, 2) NOT NULL,
            put_long_strike DECIMAL(10, 2) NOT NULL,
            put_credit DECIMAL(10, 4) NOT NULL,

            call_short_strike DECIMAL(10, 2) NOT NULL,
            call_long_strike DECIMAL(10, 2) NOT NULL,
            call_credit DECIMAL(10, 4) NOT NULL,

            contracts INT NOT NULL,
            spread_width DECIMAL(10, 2) NOT NULL,
            total_credit DECIMAL(10, 4) NOT NULL,
            max_loss DECIMAL(10, 2) NOT NULL,
            max_profit DECIMAL(10, 2) NOT NULL,
            collateral_required DECIMAL(10, 2),

            underlying_at_entry DECIMAL(10, 2) NOT NULL,
            vix_at_entry DECIMAL(6, 2),
            expected_move DECIMAL(10, 2),
            call_wall DECIMAL(10, 2),
            put_wall DECIMAL(10, 2),
            gex_regime STRING,
            flip_point DECIMAL(10, 2),
            net_gex DECIMAL(15, 2),

            oracle_confidence DECIMAL(5, 4),
            oracle_win_probability DECIMAL(8, 4),
            oracle_advice STRING,
            oracle_reasoning STRING,
            oracle_top_factors STRING,
            oracle_use_gex_walls BOOLEAN,

            wings_adjusted BOOLEAN,
            original_put_width DECIMAL(10, 2),
            original_call_width DECIMAL(10, 2),

            put_order_id STRING,
            call_order_id STRING,

            status STRING NOT NULL,
            open_time TIMESTAMP NOT NULL,
            open_date DATE,
            close_time TIMESTAMP,
            close_price DECIMAL(10, 4),
            close_reason STRING,
            realized_pnl DECIMAL(10, 2),

            dte_mode STRING,

            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
    """)
    print(f"  {bot}_positions OK")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Signals tables

# COMMAND ----------

for bot in ["flame", "spark"]:
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {_t(f'{bot}_signals')} (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            signal_time TIMESTAMP,
            spot_price DECIMAL(10, 2),
            vix DECIMAL(6, 2),
            expected_move DECIMAL(10, 2),
            call_wall DECIMAL(10, 2),
            put_wall DECIMAL(10, 2),
            gex_regime STRING,
            put_short DECIMAL(10, 2),
            put_long DECIMAL(10, 2),
            call_short DECIMAL(10, 2),
            call_long DECIMAL(10, 2),
            total_credit DECIMAL(10, 4),
            confidence DECIMAL(5, 4),
            was_executed BOOLEAN,
            skip_reason STRING,
            reasoning STRING,
            wings_adjusted BOOLEAN,
            dte_mode STRING
        )
    """)
    print(f"  {bot}_signals OK")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Daily performance, logs, equity snapshots, paper accounts, PDT tracking

# COMMAND ----------

for bot in ["flame", "spark"]:
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {_t(f'{bot}_daily_perf')} (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            trade_date DATE NOT NULL,
            trades_executed INT,
            positions_closed INT,
            realized_pnl DECIMAL(10, 2),
            updated_at TIMESTAMP
        )
    """)
    print(f"  {bot}_daily_perf OK")

    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {_t(f'{bot}_logs')} (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            log_time TIMESTAMP,
            level STRING,
            message STRING,
            details STRING,
            dte_mode STRING
        )
    """)
    print(f"  {bot}_logs OK")

    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {_t(f'{bot}_equity_snapshots')} (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            snapshot_time TIMESTAMP,
            balance DECIMAL(12, 2) NOT NULL,
            unrealized_pnl DECIMAL(12, 2),
            realized_pnl DECIMAL(12, 2),
            open_positions INT,
            note STRING,
            dte_mode STRING,
            created_at TIMESTAMP
        )
    """)
    print(f"  {bot}_equity_snapshots OK")

    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {_t(f'{bot}_paper_account')} (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            starting_capital DECIMAL(12, 2) NOT NULL,
            current_balance DECIMAL(12, 2) NOT NULL,
            cumulative_pnl DECIMAL(12, 2),
            total_trades INT,
            collateral_in_use DECIMAL(12, 2),
            buying_power DECIMAL(12, 2) NOT NULL,
            high_water_mark DECIMAL(12, 2) NOT NULL,
            max_drawdown DECIMAL(12, 2),
            is_active BOOLEAN,
            dte_mode STRING,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
    """)
    print(f"  {bot}_paper_account OK")

    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {_t(f'{bot}_pdt_log')} (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            trade_date DATE NOT NULL,
            symbol STRING NOT NULL,
            position_id STRING NOT NULL,
            opened_at TIMESTAMP NOT NULL,
            closed_at TIMESTAMP,
            is_day_trade BOOLEAN,
            contracts INT NOT NULL,
            entry_credit DECIMAL(10, 4),
            exit_cost DECIMAL(10, 4),
            pnl DECIMAL(10, 2),
            close_reason STRING,
            dte_mode STRING,
            created_at TIMESTAMP
        )
    """)
    print(f"  {bot}_pdt_log OK")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Heartbeats table (shared)

# COMMAND ----------

spark.sql(f"""
    CREATE TABLE IF NOT EXISTS {_t('bot_heartbeats')} (
        bot_name STRING NOT NULL,
        last_heartbeat TIMESTAMP,
        status STRING,
        scan_count BIGINT,
        details STRING
    )
""")
print("  bot_heartbeats OK")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2: Initialize Paper Accounts ($5,000 each)

# COMMAND ----------

from datetime import datetime
from zoneinfo import ZoneInfo

now_str = datetime.now(ZoneInfo("America/Chicago")).strftime("%Y-%m-%d %H:%M:%S")

for bot, dte_mode in [("flame", "2DTE"), ("spark", "1DTE")]:
    existing = spark.sql(f"""
        SELECT id FROM {_t(f'{bot}_paper_account')}
        WHERE is_active = TRUE AND dte_mode = '{dte_mode}'
        LIMIT 1
    """).collect()

    if existing:
        print(f"  {bot.upper()} account already exists")
    else:
        spark.sql(f"""
            INSERT INTO {_t(f'{bot}_paper_account')}
            (starting_capital, current_balance, cumulative_pnl, total_trades,
             collateral_in_use, buying_power, high_water_mark, max_drawdown,
             is_active, dte_mode, created_at, updated_at)
            VALUES (5000.0, 5000.0, 0, 0, 0, 5000.0, 5000.0, 0,
                    TRUE, '{dte_mode}', '{now_str}', '{now_str}')
        """)
        print(f"  {bot.upper()} account initialized: $5,000")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3: Verify Everything

# COMMAND ----------

print("=== TABLES ===")
tables = spark.sql(f"SHOW TABLES IN {CATALOG}.{SCHEMA}").collect()
for t in tables:
    print(f"  {t.tableName}")

print(f"\nTotal: {len(tables)} tables")

# COMMAND ----------

print("=== PAPER ACCOUNTS ===")
for bot in ["flame", "spark"]:
    row = spark.sql(f"""
        SELECT starting_capital, current_balance, is_active, dte_mode
        FROM {_t(f'{bot}_paper_account')}
        WHERE is_active = TRUE
        LIMIT 1
    """).collect()
    if row:
        r = row[0]
        print(f"  {bot.upper()}: ${r.current_balance:,.2f} (mode={r.dte_mode}, active={r.is_active})")
    else:
        print(f"  {bot.upper()}: NO ACCOUNT FOUND")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Done!
# MAGIC
# MAGIC Tables are created and accounts are initialized. Now import and run:
# MAGIC - **`02_flame_bot`** - FLAME (2DTE) trading bot
# MAGIC - **`03_spark_bot`** - SPARK (1DTE) trading bot
