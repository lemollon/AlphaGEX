#!/usr/bin/env python3
"""
Render Deployment Diagnostic Script
Run this in Render's shell to check database, tables, API connections, and data flow.

Usage: python scripts/render_diagnostic.py
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(project_root / '.env')

print("=" * 70)
print("🔍 ALPHAGEX RENDER DEPLOYMENT DIAGNOSTIC")
print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)

# Track issues
issues = []
warnings = []

# =============================================================================
# 1. ENVIRONMENT VARIABLES CHECK
# =============================================================================
print("\n" + "=" * 70)
print("1️⃣  ENVIRONMENT VARIABLES")
print("=" * 70)

env_vars = {
    'DATABASE_URL': {'required': True, 'sensitive': True},
    'TRADING_VOLATILITY_API_KEY': {'required': False, 'sensitive': True},
    'TV_USERNAME': {'required': False, 'sensitive': True},
    'TRADIER_API_KEY': {'required': False, 'sensitive': True},
    'TRADIER_ACCOUNT_ID': {'required': False, 'sensitive': True},
    'POLYGON_API_KEY': {'required': False, 'sensitive': True},
    'ANTHROPIC_API_KEY': {'required': False, 'sensitive': True},
}

for var, config in env_vars.items():
    value = os.getenv(var)
    if value:
        if config['sensitive']:
            display = f"{value[:8]}...{value[-4:]}" if len(value) > 12 else "***"
        else:
            display = value
        print(f"  ✅ {var}: {display}")
    else:
        if config['required']:
            print(f"  ❌ {var}: NOT SET (REQUIRED!)")
            issues.append(f"{var} environment variable is not set")
        else:
            print(f"  ⚠️  {var}: not set (optional)")
            warnings.append(f"{var} not set - some features may not work")

# Check for at least one GEX data source
has_gex_source = bool(os.getenv('TRADING_VOLATILITY_API_KEY') or os.getenv('TV_USERNAME') or os.getenv('TRADIER_API_KEY'))
if not has_gex_source:
    print("\n  ❌ NO GEX DATA SOURCE: Need TRADING_VOLATILITY_API_KEY, TV_USERNAME, or TRADIER_API_KEY")
    issues.append("No GEX data source configured")

# =============================================================================
# 2. DATABASE CONNECTION
# =============================================================================
print("\n" + "=" * 70)
print("2️⃣  DATABASE CONNECTION")
print("=" * 70)

db_connected = False
try:
    from database_adapter import get_connection, is_database_available

    if is_database_available():
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT version()")
        version = cursor.fetchone()[0]
        print(f"  ✅ PostgreSQL connected")
        print(f"     Version: {version[:50]}...")

        # Check connection details (without exposing credentials)
        cursor.execute("SELECT current_database(), current_user")
        db_info = cursor.fetchone()
        print(f"     Database: {db_info[0]}")
        print(f"     User: {db_info[1]}")

        conn.close()
        db_connected = True
    else:
        print("  ❌ Database not available")
        issues.append("Database connection failed")
except Exception as e:
    print(f"  ❌ Database connection failed: {type(e).__name__}: {e}")
    issues.append(f"Database error: {e}")

# =============================================================================
# 3. TABLE EXISTENCE CHECK
# =============================================================================
print("\n" + "=" * 70)
print("3️⃣  DATABASE TABLES")
print("=" * 70)

if db_connected:
    critical_tables = [
        'gex_history',
        'regime_signals',
        'market_data',
        'probability_outcomes',
        'greeks_snapshots',
        'vix_term_structure',
        'options_flow',
        'ai_analysis_history',
        'autonomous_open_positions',
        'autonomous_closed_trades',
        'data_collection_log',
    ]

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Get all existing tables
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        existing_tables = {row[0] for row in cursor.fetchall()}

        print(f"  Total tables in database: {len(existing_tables)}")
        print(f"\n  Critical tables status:")

        missing_tables = []
        for table in critical_tables:
            if table in existing_tables:
                print(f"    ✅ {table}")
            else:
                print(f"    ❌ {table} - MISSING!")
                missing_tables.append(table)

        if missing_tables:
            issues.append(f"Missing tables: {', '.join(missing_tables)}")
            print(f"\n  ⚠️  Run database initialization:")
            print(f"     python db/initialize_database.py")

        conn.close()
    except Exception as e:
        print(f"  ❌ Error checking tables: {e}")
        issues.append(f"Table check failed: {e}")

# =============================================================================
# 4. DATA STATUS CHECK
# =============================================================================
print("\n" + "=" * 70)
print("4️⃣  DATA STATUS (Record Counts)")
print("=" * 70)

if db_connected:
    tables_to_check = [
        ('gex_history', 'GEX snapshots'),
        ('regime_signals', 'Regime signals'),
        ('market_data', 'Market snapshots'),
        ('probability_outcomes', 'Probability predictions'),
        ('greeks_snapshots', 'Greeks data'),
        ('vix_term_structure', 'VIX curve'),
        ('ai_analysis_history', 'AI insights'),
        ('data_collection_log', 'Collection logs'),
    ]

    try:
        conn = get_connection()
        cursor = conn.cursor()

        empty_tables = []
        for table, description in tables_to_check:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]

                # Check for recent data (last 24 hours)
                try:
                    cursor.execute(f"""
                        SELECT COUNT(*) FROM {table}
                        WHERE timestamp >= NOW() - INTERVAL '24 hours'
                    """)
                    recent = cursor.fetchone()[0]
                except:
                    recent = "N/A"

                if count == 0:
                    print(f"    ❌ {table}: EMPTY")
                    empty_tables.append(table)
                elif recent == 0 or recent == "N/A":
                    print(f"    ⚠️  {table}: {count:,} total, no recent data")
                    warnings.append(f"{table} has no data from last 24h")
                else:
                    print(f"    ✅ {table}: {count:,} total, {recent} recent")
            except Exception as e:
                print(f"    ⚠️  {table}: Error - {e}")

        if empty_tables:
            warnings.append(f"Empty tables: {', '.join(empty_tables)}")

        conn.close()
    except Exception as e:
        print(f"  ❌ Error checking data: {e}")

# =============================================================================
# 5. RECENT GEX HISTORY CHECK
# =============================================================================
print("\n" + "=" * 70)
print("5️⃣  RECENT GEX DATA")
print("=" * 70)

if db_connected:
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT timestamp, symbol, net_gex, flip_point, spot_price, regime, data_source
            FROM gex_history
            ORDER BY timestamp DESC
            LIMIT 5
        """)
        rows = cursor.fetchall()

        if rows:
            print(f"  Last {len(rows)} GEX snapshots:")
            for row in rows:
                ts, symbol, net_gex, flip, spot, regime, source = row
                gex_b = net_gex / 1e9 if net_gex else 0
                print(f"    {ts} | {symbol} | ${gex_b:.2f}B | Flip: ${flip:.0f} | {regime} | {source}")

            # Check data freshness
            latest = rows[0][0]
            age = datetime.now() - latest if latest else timedelta(days=999)
            if age.total_seconds() > 3600:  # More than 1 hour old
                warnings.append(f"GEX data is {age.total_seconds()/3600:.1f}h old")
                print(f"\n  ⚠️  Data is {age.total_seconds()/3600:.1f} hours old")
        else:
            print("  ❌ No GEX history data found!")
            issues.append("gex_history table is empty")

        conn.close()
    except Exception as e:
        print(f"  ❌ Error checking GEX history: {e}")

# =============================================================================
# 6. API CONNECTION TESTS
# =============================================================================
print("\n" + "=" * 70)
print("6️⃣  API CONNECTION TESTS")
print("=" * 70)

# Test TradingVolatility API
print("\n  Testing TradingVolatility API...")
try:
    from core_classes_and_engines import TradingVolatilityAPI
    api = TradingVolatilityAPI()
    data = api.get_net_gamma('SPY')
    if data and 'error' not in data:
        print(f"    ✅ TradingVolatility API working")
        print(f"       Net GEX: ${data.get('net_gex', 0)/1e9:.2f}B")
        print(f"       Flip Point: ${data.get('flip_point', 0):.2f}")
    else:
        print(f"    ⚠️  TradingVolatility API returned error: {data.get('error', 'unknown')}")
        warnings.append("TradingVolatility API not working")
except ImportError:
    print("    ⚠️  TradingVolatility module not available")
except Exception as e:
    print(f"    ⚠️  TradingVolatility API error: {type(e).__name__}: {e}")
    warnings.append(f"TradingVolatility API: {e}")

# Test Tradier API
print("\n  Testing Tradier API...")
if os.getenv('TRADIER_API_KEY'):
    try:
        from data.gex_calculator import get_gex_calculator
        calc = get_gex_calculator()
        data = calc.get_gex('SPY')
        if data and 'error' not in data:
            print(f"    ✅ Tradier GEX calculation working")
            print(f"       Net GEX: ${data.get('net_gex', 0)/1e9:.2f}B")
        else:
            print(f"    ⚠️  Tradier returned error: {data.get('error', 'unknown')}")
    except Exception as e:
        print(f"    ⚠️  Tradier API error: {type(e).__name__}: {e}")
else:
    print("    ⚠️  TRADIER_API_KEY not set")

# Test Anthropic API (for AI features)
print("\n  Testing Anthropic API...")
if os.getenv('ANTHROPIC_API_KEY'):
    try:
        import anthropic
        client = anthropic.Anthropic()
        # Just verify the client can be created
        print(f"    ✅ Anthropic client initialized")
    except Exception as e:
        print(f"    ⚠️  Anthropic API error: {e}")
else:
    print("    ⚠️  ANTHROPIC_API_KEY not set (AI features disabled)")

# =============================================================================
# 7. DATA COLLECTOR STATUS
# =============================================================================
print("\n" + "=" * 70)
print("7️⃣  DATA COLLECTOR STATUS")
print("=" * 70)

if db_connected:
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Check recent collection logs
        cursor.execute("""
            SELECT collection_type, success, error_message, timestamp
            FROM data_collection_log
            ORDER BY timestamp DESC
            LIMIT 10
        """)
        logs = cursor.fetchall()

        if logs:
            print(f"  Last {len(logs)} collection events:")
            success_count = sum(1 for log in logs if log[1])
            fail_count = len(logs) - success_count
            print(f"    Success: {success_count}, Failed: {fail_count}")

            for log in logs[:5]:
                ctype, success, error, ts = log
                status = "✅" if success else "❌"
                error_msg = f" - {error[:50]}..." if error else ""
                print(f"    {status} {ts} | {ctype}{error_msg}")
        else:
            print("  ⚠️  No collection logs found")
            print("     Data collector may not be running")
            warnings.append("No data collection logs - collector may not be running")

        conn.close()
    except Exception as e:
        print(f"  ⚠️  Could not check collection logs: {e}")

# =============================================================================
# 8. FRONTEND API ENDPOINTS TEST
# =============================================================================
print("\n" + "=" * 70)
print("8️⃣  BACKEND API IMPORT TEST")
print("=" * 70)

try:
    from backend.api.main import app
    print("  ✅ FastAPI app imports successfully")

    # List routes
    routes = [route.path for route in app.routes if hasattr(route, 'path')]
    api_routes = [r for r in routes if r.startswith('/api')]
    print(f"  Total API routes: {len(api_routes)}")

    key_routes = ['/api/health', '/api/gamma', '/api/regime', '/api/ai']
    for route in key_routes:
        matching = [r for r in api_routes if r.startswith(route)]
        if matching:
            print(f"    ✅ {route}* ({len(matching)} endpoints)")
        else:
            print(f"    ⚠️  {route}* not found")

except Exception as e:
    print(f"  ❌ FastAPI app import failed: {e}")
    issues.append(f"Backend API import error: {e}")

# =============================================================================
# SUMMARY
# =============================================================================
print("\n" + "=" * 70)
print("📊 DIAGNOSTIC SUMMARY")
print("=" * 70)

if issues:
    print(f"\n❌ CRITICAL ISSUES ({len(issues)}):")
    for i, issue in enumerate(issues, 1):
        print(f"   {i}. {issue}")

if warnings:
    print(f"\n⚠️  WARNINGS ({len(warnings)}):")
    for i, warning in enumerate(warnings, 1):
        print(f"   {i}. {warning}")

if not issues and not warnings:
    print("\n✅ All checks passed! System is healthy.")
elif not issues:
    print("\n✅ No critical issues. Check warnings above.")
else:
    print("\n❌ Critical issues found. Please fix before deployment.")

# =============================================================================
# RECOMMENDED ACTIONS
# =============================================================================
print("\n" + "=" * 70)
print("🔧 RECOMMENDED ACTIONS")
print("=" * 70)

if 'gex_history table is empty' in str(issues) or 'Empty tables' in str(warnings):
    print("""
  📥 To populate data, run the data collector:
     python data/automated_data_collector.py

  Or manually take a GEX snapshot:
     python -c "from gamma.gex_history_snapshot_job import save_gex_snapshot; save_gex_snapshot('SPY')"
""")

if 'Missing tables' in str(issues):
    print("""
  🗄️  To initialize database tables:
     python db/initialize_database.py
""")

if 'No GEX data source' in str(issues):
    print("""
  🔑 Add at least one GEX data source in Render Environment:
     - TRADING_VOLATILITY_API_KEY (preferred)
     - Or: TV_USERNAME + TV_PASSWORD
     - Or: TRADIER_API_KEY + TRADIER_ACCOUNT_ID
""")

print("\n" + "=" * 70)
print("✅ Diagnostic complete")
print("=" * 70)
