"""
AlphaGEX PostgreSQL Migration Guide

RECOMMENDED: Migrate to PostgreSQL instead of Databricks
- 10x cheaper ($10-50/month vs $200-2000/month)
- Easier to setup (2 hours vs 2 days)
- Handles your data scale perfectly (good up to 100M+ rows)
- Battle-tested and reliable

This is what 95% of trading systems use. Save Databricks for when you're institutional scale.
"""

import sqlite3
import psycopg2
from psycopg2.extras import execute_values
import os
from urllib.parse import urlparse

# ============================================================================
# STEP 1: Setup PostgreSQL (Choose One)
# ============================================================================

"""
Option 1: Supabase (Recommended - Easy + Free Tier)
- Go to supabase.com
- Create project (free tier: 500MB, upgrade to $25/month for 8GB)
- Get connection string from Settings → Database
- Connection string format:
  postgresql://postgres:[PASSWORD]@db.[PROJECT].supabase.co:5432/postgres

Option 2: Railway.app
- railway.app
- Add PostgreSQL plugin
- $5/month minimum (scales with usage)
- Connection string in variables

Option 3: Render
- render.com
- Create PostgreSQL database
- $7/month for 1GB (plenty for you)

Option 4: Self-hosted (Docker)
- docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=mypassword postgres:15
- Free but you manage it
"""

# ============================================================================
# STEP 2: Configuration
# ============================================================================

class PostgreSQLConfig:
    """PostgreSQL connection configuration"""

    def __init__(self, database_url: str = None):
        # Get from environment or parameter
        self.database_url = database_url or os.getenv('DATABASE_URL')

        if not self.database_url:
            raise ValueError("DATABASE_URL not provided")

        # Parse URL
        result = urlparse(self.database_url)
        self.user = result.username
        self.password = result.password
        self.host = result.hostname
        self.port = result.port or 5432
        self.database = result.path[1:]  # Remove leading /

    def get_connection(self):
        """Create PostgreSQL connection"""
        return psycopg2.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database
        )


# ============================================================================
# STEP 3: Create Tables in PostgreSQL
# ============================================================================

def create_postgresql_tables(conn):
    """Create tables in PostgreSQL (same schema as SQLite)"""

    cursor = conn.cursor()

    # Backtest results
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS backtest_results (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            strategy_name TEXT,
            symbol TEXT,
            start_date TEXT,
            end_date TEXT,
            total_trades INTEGER,
            winning_trades INTEGER,
            losing_trades INTEGER,
            win_rate REAL,
            avg_win_pct REAL,
            avg_loss_pct REAL,
            largest_win_pct REAL,
            largest_loss_pct REAL,
            expectancy_pct REAL,
            total_return_pct REAL,
            max_drawdown_pct REAL,
            sharpe_ratio REAL,
            avg_trade_duration_days REAL
        );

        -- Add indexes for faster queries
        CREATE INDEX IF NOT EXISTS idx_backtest_strategy ON backtest_results(strategy_name);
        CREATE INDEX IF NOT EXISTS idx_backtest_timestamp ON backtest_results(timestamp DESC);
    """)

    # Backtest summary
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS backtest_summary (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            symbol TEXT,
            start_date TEXT,
            end_date TEXT,
            psychology_trades INTEGER,
            psychology_win_rate REAL,
            psychology_expectancy REAL,
            gex_trades INTEGER,
            gex_win_rate REAL,
            gex_expectancy REAL,
            options_trades INTEGER,
            options_win_rate REAL,
            options_expectancy REAL
        );
    """)

    # Regime signals (psychology traps)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS regime_signals (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP,
            spy_price REAL,
            primary_regime_type TEXT,
            confidence_score REAL,
            trade_direction TEXT,
            risk_level TEXT,
            description TEXT,
            psychology_trap TEXT,
            rsi_5m REAL,
            rsi_15m REAL,
            rsi_1h REAL,
            rsi_4h REAL,
            rsi_1d REAL,
            rsi_score REAL,
            gamma_exposure REAL,
            flip_point REAL,
            vix_current REAL,
            vix_change_pct REAL,
            vix_spike_detected INTEGER DEFAULT 0,
            zero_gamma_level REAL,
            volatility_regime TEXT,
            at_flip_point INTEGER DEFAULT 0,
            signal_correct INTEGER,
            price_change_1d REAL,
            price_change_5d REAL
        );

        -- Add indexes
        CREATE INDEX IF NOT EXISTS idx_regime_timestamp ON regime_signals(timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_regime_type ON regime_signals(primary_regime_type);
        CREATE INDEX IF NOT EXISTS idx_regime_correct ON regime_signals(signal_correct);
    """)

    # GEX history
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gex_history (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            symbol TEXT,
            net_gex REAL,
            flip_point REAL,
            call_wall REAL,
            put_wall REAL,
            spot_price REAL,
            mm_state TEXT,
            regime TEXT,
            data_source TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_gex_symbol ON gex_history(symbol, timestamp DESC);
    """)

    # Trade history
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trade_history (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            symbol TEXT,
            strategy TEXT,
            direction TEXT,
            entry_price REAL,
            exit_price REAL,
            quantity REAL,
            pnl REAL,
            pnl_pct REAL,
            status TEXT,
            notes TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_trade_timestamp ON trade_history(timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_trade_strategy ON trade_history(strategy);
    """)

    # Autonomous trader status
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS autonomous_trader_status (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT,
            action TEXT,
            analysis TEXT,
            positions_count INTEGER,
            daily_pnl REAL
        );
    """)

    conn.commit()
    cursor.close()

    print("✓ Created PostgreSQL tables with indexes")


# ============================================================================
# STEP 4: Migrate Data from SQLite to PostgreSQL
# ============================================================================

def migrate_sqlite_to_postgresql(sqlite_db_path: str, pg_config: PostgreSQLConfig):
    """Migrate all tables from SQLite to PostgreSQL"""

    print(f"\n🔄 Migrating from SQLite ({sqlite_db_path}) to PostgreSQL...")

    # Connect to both databases
    sqlite_conn = sqlite3.connect(sqlite_db_path)
    sqlite_conn.row_factory = sqlite3.Row
    pg_conn = pg_config.get_connection()

    # Create tables in PostgreSQL first
    create_postgresql_tables(pg_conn)

    # Get list of tables
    sqlite_cursor = sqlite_conn.cursor()
    sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in sqlite_cursor.fetchall()]

    print(f"Found {len(tables)} tables: {tables}\n")

    # Migrate each table
    total_rows = 0
    for table in tables:
        print(f"Migrating table: {table}")

        # Read all rows from SQLite
        sqlite_cursor.execute(f"SELECT * FROM {table}")
        rows = sqlite_cursor.fetchall()

        if not rows:
            print(f"  ⚠️  Empty table, skipping\n")
            continue

        # Get column names
        column_names = [description[0] for description in sqlite_cursor.description]
        # Exclude 'id' if it's auto-increment
        insert_columns = [col for col in column_names if col != 'id']

        # Prepare PostgreSQL insert
        pg_cursor = pg_conn.cursor()
        columns_str = ', '.join(insert_columns)
        placeholders = ', '.join(['%s' for _ in insert_columns])
        insert_query = f"INSERT INTO {table} ({columns_str}) VALUES ({placeholders})"

        # Convert rows to tuples (excluding id)
        data = []
        for row in rows:
            row_dict = dict(row)
            row_data = tuple(row_dict[col] for col in insert_columns)
            data.append(row_data)

        # Batch insert (PostgreSQL handles this well)
        try:
            execute_values(pg_cursor, f"INSERT INTO {table} ({columns_str}) VALUES %s", data)
            pg_conn.commit()
            print(f"  ✓ Migrated {len(data)} rows\n")
            total_rows += len(data)
        except Exception as e:
            print(f"  ❌ Error: {e}\n")
            pg_conn.rollback()

        pg_cursor.close()

    sqlite_conn.close()
    pg_conn.close()

    print(f"✅ Migration complete! Migrated {total_rows} total rows")


# ============================================================================
# STEP 5: Update AlphaGEX to Use PostgreSQL
# ============================================================================

"""
To switch your entire system to PostgreSQL:

1. Install dependencies:
   pip install psycopg2-binary sqlalchemy

2. Update config_and_database.py:

   # Replace this:
   DB_PATH = Path(os.path.join(os.getcwd(), 'gex_copilot.db'))

   # With this:
   DATABASE_URL = os.getenv('DATABASE_URL')

   if DATABASE_URL:
       # Use PostgreSQL
       from sqlalchemy import create_engine
       engine = create_engine(DATABASE_URL)
       # Use engine.connect() instead of sqlite3.connect()
   else:
       # Fallback to SQLite
       DB_PATH = Path(os.path.join(os.getcwd(), 'gex_copilot.db'))

3. Set environment variable:
   export DATABASE_URL="postgresql://user:pass@host:5432/dbname"

   Or in .env file:
   DATABASE_URL=postgresql://user:pass@host:5432/dbname

4. Update database calls:

   # Old SQLite code:
   conn = sqlite3.connect(DB_PATH)

   # New PostgreSQL code (using SQLAlchemy):
   from sqlalchemy import create_engine
   engine = create_engine(DATABASE_URL)
   conn = engine.connect()

   # Or raw psycopg2:
   import psycopg2
   conn = psycopg2.connect(DATABASE_URL)

That's it! Your system now uses PostgreSQL.
"""


# ============================================================================
# STEP 6: Example PostgreSQL Queries (Better Performance)
# ============================================================================

def example_queries(pg_config: PostgreSQLConfig):
    """Example queries optimized for PostgreSQL"""

    conn = pg_config.get_connection()
    cursor = conn.cursor()

    # Query 1: Best strategies with aggregation
    cursor.execute("""
        SELECT
            strategy_name,
            COUNT(*) as backtest_count,
            AVG(win_rate) as avg_win_rate,
            AVG(expectancy_pct) as avg_expectancy,
            AVG(sharpe_ratio) as avg_sharpe
        FROM backtest_results
        WHERE expectancy_pct > 0.5
          AND win_rate > 55
        GROUP BY strategy_name
        ORDER BY avg_expectancy DESC
        LIMIT 10
    """)

    results = cursor.fetchall()
    print("\n📊 Best Performing Strategies:")
    for row in results:
        print(f"  {row[0]}: {row[2]:.1f}% win rate, {row[3]:.2f}% expectancy")

    # Query 2: Recent signals with window function
    cursor.execute("""
        SELECT
            timestamp,
            primary_regime_type,
            confidence_score,
            signal_correct,
            price_change_1d,
            ROW_NUMBER() OVER (PARTITION BY primary_regime_type ORDER BY timestamp DESC) as rn
        FROM regime_signals
        WHERE timestamp > NOW() - INTERVAL '30 days'
        ORDER BY timestamp DESC
        LIMIT 20
    """)

    print("\n📈 Recent Signals (Last 30 Days):")
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]} ({row[2]:.0f}% confidence)")

    cursor.close()
    conn.close()


# ============================================================================
# STEP 7: Usage Example
# ============================================================================

if __name__ == "__main__":
    # Configuration
    DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://localhost:5432/alphagex')
    pg_config = PostgreSQLConfig(DATABASE_URL)

    # Option 1: Just create tables in PostgreSQL (fresh start)
    print("\n📦 Creating PostgreSQL tables...")
    conn = pg_config.get_connection()
    create_postgresql_tables(conn)
    conn.close()

    # Option 2: Migrate existing SQLite data
    sqlite_path = '/home/user/AlphaGEX/gex_copilot.db'
    if os.path.exists(sqlite_path) and os.path.getsize(sqlite_path) > 0:
        migrate_sqlite_to_postgresql(sqlite_path, pg_config)
    else:
        print("No SQLite data to migrate (database is empty)")

    # Run example queries
    example_queries(pg_config)


# ============================================================================
# COST COMPARISON
# ============================================================================

"""
PostgreSQL Managed Services Pricing:

Supabase:
- Free: 500MB database, 2GB bandwidth
- Pro: $25/month - 8GB database, 250GB bandwidth, daily backups
- Team: $599/month - 100GB database (you'll never need this)

Railway:
- Pay as you go: ~$5-20/month for small database
- Scales automatically

Render:
- Starter: $7/month - 1GB RAM, 1GB storage
- Standard: $15/month - 4GB RAM, 10GB storage

Your realistic needs:
- Database size: 100MB-1GB
- Queries: <1000/day
- Recommended: Supabase Free tier (try first) or Pro ($25/month)

Total cost: $0-25/month vs $200-2000/month for Databricks

VERDICT: Save $2,400-24,000/year by using PostgreSQL instead of Databricks.
"""
