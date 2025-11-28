"""
AlphaGEX Databricks Migration Guide

BEFORE YOU START: You probably don't need this. See BACKTEST_SYSTEM_README.md
for why PostgreSQL or TimescaleDB is likely a better choice.

If you still want Databricks, here's how:
"""

import pandas as pd
from databricks import sql
import sqlite3
import os
from datetime import datetime

# ============================================================================
# STEP 1: Setup Databricks
# ============================================================================

"""
1. Create Databricks account (databricks.com)
2. Create workspace
3. Create SQL Warehouse (or use existing cluster)
4. Get connection details:
   - Server hostname
   - HTTP path
   - Access token

Cost: Starts at $0.22/DBU, minimum ~100 DBUs/month = $22/month for smallest setup
Realistic usage: $200-2000/month
"""

# ============================================================================
# STEP 2: Databricks Connection Configuration
# ============================================================================

class DatabricksConfig:
    """Databricks connection configuration"""

    def __init__(self):
        # Get from environment variables or .env file
        self.server_hostname = os.getenv('DATABRICKS_SERVER_HOSTNAME')
        self.http_path = os.getenv('DATABRICKS_HTTP_PATH')
        self.access_token = os.getenv('DATABRICKS_ACCESS_TOKEN')
        self.catalog = os.getenv('DATABRICKS_CATALOG', 'alphagex')
        self.schema = os.getenv('DATABRICKS_SCHEMA', 'trading')

    def get_connection(self):
        """Create Databricks SQL connection"""
        return sql.connect(
            server_hostname=self.server_hostname,
            http_path=self.http_path,
            access_token=self.access_token
        )


# ============================================================================
# STEP 3: Schema Migration
# ============================================================================

def create_databricks_tables(connection):
    """Create tables in Databricks (Delta Lake format)"""

    cursor = connection.cursor()

    # Backtest results table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS backtest_results (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
            strategy_name STRING,
            symbol STRING,
            start_date DATE,
            end_date DATE,
            total_trades INT,
            winning_trades INT,
            losing_trades INT,
            win_rate DOUBLE,
            avg_win_pct DOUBLE,
            avg_loss_pct DOUBLE,
            largest_win_pct DOUBLE,
            largest_loss_pct DOUBLE,
            expectancy_pct DOUBLE,
            total_return_pct DOUBLE,
            max_drawdown_pct DOUBLE,
            sharpe_ratio DOUBLE,
            avg_trade_duration_days DOUBLE
        ) USING DELTA
        PARTITIONED BY (strategy_name)  -- Partition by strategy for faster queries
    """)

    # Regime signals table (psychology traps)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS regime_signals (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            timestamp TIMESTAMP,
            spy_price DOUBLE,
            primary_regime_type STRING,
            confidence_score DOUBLE,
            trade_direction STRING,
            risk_level STRING,
            description STRING,
            psychology_trap STRING,
            vix_current DOUBLE,
            vix_spike_detected BOOLEAN,
            volatility_regime STRING,
            at_flip_point BOOLEAN,
            signal_correct INT,
            price_change_1d DOUBLE,
            price_change_5d DOUBLE
        ) USING DELTA
        PARTITIONED BY (DATE(timestamp))  -- Partition by date for time-series queries
    """)

    # GEX history table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gex_history (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
            symbol STRING,
            net_gex DOUBLE,
            flip_point DOUBLE,
            call_wall DOUBLE,
            put_wall DOUBLE,
            spot_price DOUBLE,
            mm_state STRING,
            regime STRING
        ) USING DELTA
        PARTITIONED BY (symbol, DATE(timestamp))
    """)

    # Trade history table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trade_history (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
            symbol STRING,
            strategy STRING,
            direction STRING,
            entry_price DOUBLE,
            exit_price DOUBLE,
            quantity DOUBLE,
            pnl DOUBLE,
            pnl_pct DOUBLE,
            status STRING,
            notes STRING
        ) USING DELTA
        PARTITIONED BY (strategy, DATE(timestamp))
    """)

    cursor.close()
    print("✓ Created Databricks tables (Delta Lake format)")


# ============================================================================
# STEP 4: Data Migration from SQLite
# ============================================================================

def migrate_sqlite_to_databricks(sqlite_db_path: str, databricks_config: DatabricksConfig):
    """Migrate all data from SQLite to Databricks"""

    print(f"Starting migration from {sqlite_db_path} to Databricks...")

    # Connect to both databases
    sqlite_conn = sqlite3.connect(sqlite_db_path)
    databricks_conn = databricks_config.get_connection()

    # Get list of tables from SQLite
    sqlite_cursor = sqlite_conn.cursor()
    sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in sqlite_cursor.fetchall()]

    print(f"Found {len(tables)} tables to migrate: {tables}")

    # Migrate each table
    for table in tables:
        print(f"\nMigrating table: {table}")

        # Read from SQLite as DataFrame
        df = pd.read_sql_query(f"SELECT * FROM {table}", sqlite_conn)

        if df.empty:
            print(f"  ⚠️  Table {table} is empty, skipping")
            continue

        print(f"  → Read {len(df)} rows from SQLite")

        # Write to Databricks using Spark
        # Note: This requires PySpark and Databricks Connect
        # Simplified version using SQL INSERT (slower but works)

        databricks_cursor = databricks_conn.cursor()

        # Create INSERT statements
        columns = ', '.join(df.columns)
        placeholders = ', '.join(['?' for _ in df.columns])
        insert_sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"

        # Batch insert (Databricks recommends batches of 1000)
        batch_size = 1000
        for i in range(0, len(df), batch_size):
            batch = df.iloc[i:i+batch_size]
            data = [tuple(row) for row in batch.values]
            databricks_cursor.executemany(insert_sql, data)
            print(f"  → Inserted batch {i//batch_size + 1} ({len(data)} rows)")

        databricks_cursor.close()
        print(f"  ✓ Migrated {len(df)} rows to Databricks")

    sqlite_conn.close()
    databricks_conn.close()

    print("\n✅ Migration complete!")


# ============================================================================
# STEP 5: Dual-Write Strategy (Write to both SQLite and Databricks)
# ============================================================================

class DualDatabaseWriter:
    """Write to both SQLite (local) and Databricks (cloud)"""

    def __init__(self, sqlite_path: str, databricks_config: DatabricksConfig):
        self.sqlite_conn = sqlite3.connect(sqlite_path)
        self.databricks_conn = databricks_config.get_connection()

    def insert_backtest_result(self, data: dict):
        """Insert to both databases"""

        # Insert to SQLite
        sqlite_cursor = self.sqlite_conn.cursor()
        sqlite_cursor.execute("""
            INSERT INTO backtest_results (
                strategy_name, symbol, start_date, end_date,
                total_trades, winning_trades, losing_trades, win_rate,
                avg_win_pct, avg_loss_pct, expectancy_pct, total_return_pct,
                max_drawdown_pct, sharpe_ratio
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, tuple(data.values()))
        self.sqlite_conn.commit()

        # Insert to Databricks
        databricks_cursor = self.databricks_conn.cursor()
        databricks_cursor.execute("""
            INSERT INTO backtest_results (
                strategy_name, symbol, start_date, end_date,
                total_trades, winning_trades, losing_trades, win_rate,
                avg_win_pct, avg_loss_pct, expectancy_pct, total_return_pct,
                max_drawdown_pct, sharpe_ratio
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, tuple(data.values()))
        databricks_cursor.close()

        print("✓ Wrote to both SQLite and Databricks")


# ============================================================================
# STEP 6: Databricks-Optimized Queries
# ============================================================================

def query_databricks_backtest_results(databricks_config: DatabricksConfig,
                                     strategy_name: str = None):
    """Query Databricks with optimizations"""

    conn = databricks_config.get_connection()
    cursor = conn.cursor()

    # Use Delta Lake time travel and partitioning
    if strategy_name:
        # Partition pruning - only scans relevant partitions
        query = """
            SELECT *
            FROM backtest_results
            WHERE strategy_name = ?
            ORDER BY timestamp DESC
            LIMIT 100
        """
        cursor.execute(query, (strategy_name,))
    else:
        query = """
            SELECT
                strategy_name,
                AVG(win_rate) as avg_win_rate,
                AVG(expectancy_pct) as avg_expectancy,
                COUNT(*) as backtest_count
            FROM backtest_results
            GROUP BY strategy_name
            ORDER BY avg_expectancy DESC
        """
        cursor.execute(query)

    results = cursor.fetchall()
    cursor.close()
    conn.close()

    return results


# ============================================================================
# STEP 7: Example Usage
# ============================================================================

if __name__ == "__main__":
    # Setup
    config = DatabricksConfig()

    # Create tables
    conn = config.get_connection()
    create_databricks_tables(conn)
    conn.close()

    # Migrate existing data
    migrate_sqlite_to_databricks('gex_copilot.db', config)

    # Query results
    results = query_databricks_backtest_results(config)
    for row in results:
        print(row)


# ============================================================================
# COST ESTIMATE
# ============================================================================

"""
Databricks Pricing (as of 2024):
- SQL Warehouse (Serverless): $0.22/DBU
- Typical usage: 100-500 DBUs/month for small workload
- Monthly cost: $22-110 for compute
- Storage: $0.20/GB/month (Delta Lake)

Your estimated cost:
- Compute: $50-200/month (minimal usage)
- Storage: $1-5/month (50GB data)
- Total: $50-200/month

vs. PostgreSQL:
- Supabase Pro: $25/month (8GB RAM, 100GB storage)
- Railway: $20/month (8GB RAM, 100GB storage)

You're paying 2-10x more for Databricks with minimal benefit at your scale.
"""
