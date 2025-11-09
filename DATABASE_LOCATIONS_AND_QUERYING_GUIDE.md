# AlphaGEX Database Locations & Querying Guide

## 🗄️ Where Are Your Databases?

You have **TWO database environments**:

### 1. **Local Development** (This Machine)
**Database**: SQLite
**Location**: `/home/user/AlphaGEX/gex_copilot.db`
**Current Size**: 0 bytes (empty - no backtests run yet)
**Use**: Development and backtesting

### 2. **Production on Render** (Cloud)
**Database**: PostgreSQL
**Name**: `alphagex-db`
**Region**: Oregon
**Plan**: Starter (Free tier)
**Use**: Production app data
**URL**: Configured in `render.yaml` (lines 77-83)

**Status**: Deployed but probably empty (unless you've run production services)

---

## 🔍 How to Query Your Databases

### Option 1: Local SQLite Database (Development)

#### **Method 1A: Command Line (Fastest)**
```bash
# Open SQLite shell
cd /home/user/AlphaGEX
sqlite3 gex_copilot.db

# Inside SQLite shell:
.tables                    # List all tables
.schema backtest_results   # Show table schema
.schema                    # Show all schemas

# Query data
SELECT * FROM backtest_results LIMIT 10;
SELECT * FROM regime_signals ORDER BY timestamp DESC LIMIT 10;

# Exit
.quit
```

#### **Method 1B: Python (Programmatic)**
```python
import sqlite3
import pandas as pd

# Connect
conn = sqlite3.connect('/home/user/AlphaGEX/gex_copilot.db')

# List all tables
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
print("Tables:", tables)

# Query as DataFrame
df = pd.read_sql_query("SELECT * FROM backtest_results", conn)
print(df)

# Close
conn.close()
```

#### **Method 1C: DB Browser for SQLite (GUI)**
```bash
# Install (if not already installed)
sudo apt-get install sqlitebrowser

# Open database
sqlitebrowser /home/user/AlphaGEX/gex_copilot.db
```

---

### Option 2: Render PostgreSQL Database (Production)

#### **Step 1: Get Connection String**

**Option A: Via Render Dashboard**
1. Go to: https://dashboard.render.com
2. Login to your account
3. Navigate to: Databases → `alphagex-db`
4. Click "Connect" tab
5. Copy "External Connection String"

**Format**:
```
postgresql://alphagex:PASSWORD@dpg-xxx-oregon-postgres.render.com/alphagex
```

**Option B: Via Render CLI**
```bash
# Install Render CLI
npm install -g @render/cli

# Login
render login

# Get database info
render postgres info alphagex-db
```

#### **Step 2: Connect to Render Database**

**Method 2A: psql (PostgreSQL CLI)**
```bash
# Install psql if not already installed
sudo apt-get install postgresql-client

# Connect (replace with your actual connection string)
psql "postgresql://alphagex:PASSWORD@dpg-xxx.oregon-postgres.render.com/alphagex"

# Inside psql:
\dt                        # List all tables
\d backtest_results        # Describe table schema
\d+                        # List all tables with details
\l                         # List all databases

# Query data
SELECT * FROM backtest_results LIMIT 10;
SELECT table_name FROM information_schema.tables WHERE table_schema='public';

# Exit
\q
```

**Method 2B: Python (Programmatic)**
```python
import psycopg2
import pandas as pd
import os

# Get connection string from Render
DATABASE_URL = os.getenv('DATABASE_URL')
# Or hardcode (not recommended for production):
# DATABASE_URL = "postgresql://alphagex:PASSWORD@dpg-xxx.render.com/alphagex"

# Connect
conn = psycopg2.connect(DATABASE_URL)

# List all tables
cursor = conn.cursor()
cursor.execute("""
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema='public'
""")
tables = cursor.fetchall()
print("Tables:", tables)

# Query as DataFrame
df = pd.read_sql_query("SELECT * FROM backtest_results", conn)
print(df)

# Close
cursor.close()
conn.close()
```

**Method 2C: DBeaver (Universal Database Tool)**
```bash
# Download DBeaver Community Edition
wget https://dbeaver.io/files/dbeaver-ce-latest-linux.gtk.x86_64.tar.gz
tar -xzf dbeaver-ce-latest-linux.gtk.x86_64.tar.gz
./dbeaver/dbeaver

# In DBeaver:
# 1. New Database Connection → PostgreSQL
# 2. Enter Render connection details
# 3. Click "Test Connection"
# 4. Save and explore
```

---

## 📊 View Database Catalog & Schemas

### For SQLite (Local):

```bash
sqlite3 /home/user/AlphaGEX/gex_copilot.db <<EOF
-- List all tables
.tables

-- Show schema for all tables
.schema

-- Table sizes
SELECT
    name as table_name,
    (SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=m.name) as row_count
FROM sqlite_master m
WHERE type='table';

-- Detailed table info
PRAGMA table_info(backtest_results);
PRAGMA table_info(regime_signals);

-- Indexes
SELECT name, tbl_name FROM sqlite_master WHERE type='index';
EOF
```

### For PostgreSQL (Render):

```sql
-- Connect first (see Step 2A above), then run:

-- List all schemas
SELECT schema_name
FROM information_schema.schemata;

-- List all tables
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'public';

-- Table details with row counts
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public';

-- Column details for a table
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'backtest_results'
ORDER BY ordinal_position;

-- Indexes
SELECT
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public';

-- Database size
SELECT pg_size_pretty(pg_database_size('alphagex'));
```

---

## 🔧 Quick Query Script (Run Right Now)

Save this as `query_databases.py`:

```python
#!/usr/bin/env python3
"""
AlphaGEX Database Query Tool
Quickly inspect both local and production databases
"""

import sqlite3
import os
from datetime import datetime

def query_local_sqlite():
    """Query local SQLite database"""
    db_path = '/home/user/AlphaGEX/gex_copilot.db'

    print("\n" + "="*80)
    print("LOCAL SQLITE DATABASE")
    print("="*80)
    print(f"Location: {db_path}")

    if not os.path.exists(db_path):
        print("❌ Database file not found!")
        return

    size = os.path.getsize(db_path)
    print(f"Size: {size:,} bytes ({size/1024:.2f} KB)")

    if size == 0:
        print("⚠️  Database is empty (no data yet)")
        return

    # Connect and query
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # List tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print(f"\nTables ({len(tables)}):")
    for table in tables:
        table_name = table[0]
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        print(f"  - {table_name}: {count:,} rows")

    # Show sample data from each table
    for table in tables:
        table_name = table[0]
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]

        if count > 0:
            print(f"\n{table_name} (sample 3 rows):")
            cursor.execute(f"SELECT * FROM {table_name} LIMIT 3")
            rows = cursor.fetchall()

            # Get column names
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [col[1] for col in cursor.fetchall()]

            print("  Columns:", ", ".join(columns[:5]), "..." if len(columns) > 5 else "")
            for row in rows:
                print("  ", row[:5], "..." if len(row) > 5 else "")

    conn.close()

def query_render_postgres():
    """Query Render PostgreSQL database"""
    print("\n" + "="*80)
    print("RENDER POSTGRESQL DATABASE (Production)")
    print("="*80)

    database_url = os.getenv('DATABASE_URL')

    if not database_url:
        print("⚠️  DATABASE_URL not set in environment")
        print("\nTo connect:")
        print("1. Get connection string from: https://dashboard.render.com")
        print("2. Navigate to: Databases → alphagex-db → Connect")
        print("3. Copy 'External Connection String'")
        print("4. Run: export DATABASE_URL='postgresql://...'")
        print("5. Run this script again")
        return

    try:
        import psycopg2
    except ImportError:
        print("❌ psycopg2 not installed")
        print("Install: pip install psycopg2-binary")
        return

    try:
        # Connect
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()

        # List tables
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema='public'
        """)
        tables = cursor.fetchall()

        print(f"Tables ({len(tables)}):")
        for table in tables:
            table_name = table[0]
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            print(f"  - {table_name}: {count:,} rows")

        # Database size
        cursor.execute("SELECT pg_size_pretty(pg_database_size('alphagex'))")
        size = cursor.fetchone()[0]
        print(f"\nDatabase size: {size}")

        conn.close()
        print("✅ Connected to Render PostgreSQL successfully")

    except Exception as e:
        print(f"❌ Error connecting to Render: {e}")
        print("\nCheck:")
        print("1. DATABASE_URL is correct")
        print("2. Database is running on Render")
        print("3. Network connection is available")

if __name__ == "__main__":
    print("\n🗄️  ALPHAGEX DATABASE QUERY TOOL")
    print("=" * 80)

    query_local_sqlite()
    query_render_postgres()

    print("\n" + "="*80)
    print("✅ Query complete!")
    print("="*80 + "\n")
```

**Run it**:
```bash
cd /home/user/AlphaGEX
python query_databases.py
```

---

## 🎯 Quick Commands Cheat Sheet

### Local SQLite
```bash
# Open database
sqlite3 gex_copilot.db

# List tables
.tables

# Show schema
.schema backtest_results

# Query all backtest results
SELECT strategy_name, win_rate, expectancy_pct FROM backtest_results;

# Recent psychology signals
SELECT timestamp, primary_regime_type, confidence_score
FROM regime_signals
ORDER BY timestamp DESC LIMIT 10;

# Export to CSV
.mode csv
.output results.csv
SELECT * FROM backtest_results;
.output stdout
```

### Render PostgreSQL
```bash
# Get connection string from Render dashboard
export DATABASE_URL="postgresql://alphagex:PASSWORD@dpg-xxx.render.com/alphagex"

# Connect
psql $DATABASE_URL

# Or one-liner
psql "postgresql://alphagex:PASSWORD@dpg-xxx.render.com/alphagex" \
    -c "SELECT * FROM backtest_results;"
```

---

## 🔐 Getting Render Database Credentials

### Method 1: Render Dashboard (Easiest)
1. Go to: https://dashboard.render.com
2. Login
3. Click: Databases (left sidebar)
4. Click: `alphagex-db`
5. Click: "Connect" tab
6. Copy "External Connection String"

### Method 2: Render Environment Variables
Your services already have `DATABASE_URL` set automatically via `render.yaml`:
```yaml
envVars:
  - key: DATABASE_URL
    fromDatabase:
      name: alphagex-db
      property: connectionString
```

This means your backend and trader services can already access the database.

### Method 3: Render CLI
```bash
# Install Render CLI
npm install -g @render/cli

# Login
render login

# List databases
render postgres list

# Get connection info
render postgres info alphagex-db
```

---

## 📋 Common Queries

### Get all profitable strategies:
```sql
-- SQLite
SELECT strategy_name, win_rate, expectancy_pct, total_return_pct
FROM backtest_results
WHERE expectancy_pct > 0.5
  AND win_rate > 55
ORDER BY expectancy_pct DESC;
```

### Get recent psychology signals:
```sql
SELECT
    timestamp,
    primary_regime_type,
    confidence_score,
    trade_direction,
    psychology_trap
FROM regime_signals
WHERE timestamp > datetime('now', '-30 days')
ORDER BY timestamp DESC
LIMIT 20;
```

### Get pattern performance:
```sql
SELECT
    primary_regime_type,
    COUNT(*) as total_signals,
    SUM(CASE WHEN signal_correct = 1 THEN 1 ELSE 0 END) as wins,
    ROUND(AVG(CASE WHEN signal_correct = 1 THEN 1.0 ELSE 0.0 END) * 100, 1) as win_rate
FROM regime_signals
WHERE signal_correct IS NOT NULL
GROUP BY primary_regime_type
ORDER BY win_rate DESC;
```

---

## 🚀 Next Steps

### 1. Query Your Local Database
```bash
cd /home/user/AlphaGEX
python query_databases.py
```

### 2. Run Backtests (Populate Database)
```bash
python run_all_backtests.py --symbol SPY --start 2022-01-01 --end 2024-12-31
```

### 3. Query Results
```bash
sqlite3 gex_copilot.db "SELECT * FROM backtest_results;"
```

### 4. Connect to Render (If Needed)
```bash
# Get connection string from dashboard
export DATABASE_URL="postgresql://..."

# Connect
psql $DATABASE_URL
```

---

## ❓ FAQ

### Q: Where is my data stored?
**A**:
- **Local development**: `gex_copilot.db` (SQLite file)
- **Production (Render)**: PostgreSQL in Oregon region

### Q: How do I see what tables exist?
**A**:
```bash
# SQLite
sqlite3 gex_copilot.db ".tables"

# PostgreSQL (Render)
psql $DATABASE_URL -c "\dt"
```

### Q: How do I backup my database?
**A**:
```bash
# SQLite (copy the file)
cp gex_copilot.db gex_copilot.backup.db

# PostgreSQL (use pg_dump)
pg_dump $DATABASE_URL > backup.sql
```

### Q: Can I migrate local data to Render?
**A**: Yes! Use `postgresql_migration_guide.py`:
```bash
export DATABASE_URL="postgresql://..."
python postgresql_migration_guide.py
```

### Q: Why is my database empty?
**A**: You haven't run backtests yet. Run:
```bash
python run_all_backtests.py
```

---

## 📚 Resources

**SQLite Documentation**:
- https://www.sqlite.org/cli.html
- https://sqlite.org/lang.html

**PostgreSQL Documentation**:
- https://www.postgresql.org/docs/current/
- https://www.postgresql.org/docs/current/app-psql.html

**Render Database Docs**:
- https://render.com/docs/databases
- https://render.com/docs/postgresql

**Database Tools**:
- DB Browser for SQLite: https://sqlitebrowser.org/
- DBeaver (Universal): https://dbeaver.io/
- pgAdmin (PostgreSQL): https://www.pgadmin.org/

---

**Current Status**:
- ✅ Local SQLite: Empty (ready for backtests)
- ✅ Render PostgreSQL: Configured (ready to use)
- ⏳ Data: None yet (run backtests to populate)

**What to do RIGHT NOW**:
```bash
# 1. Check your local database
python query_databases.py

# 2. Run backtests to populate it
python run_all_backtests.py

# 3. Query results
sqlite3 gex_copilot.db "SELECT * FROM backtest_results;"
```
