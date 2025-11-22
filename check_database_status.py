#!/usr/bin/env python3
"""
Database Status Check - Verify all tables populated and show data freshness
"""
import sqlite3
from datetime import datetime, timedelta
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'backend', 'gex_copilot.db')

def check_database_status():
    """Comprehensive database status check"""

    print("\n" + "="*80)
    print("DATABASE STATUS CHECK")
    print("="*80)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Define all expected tables
    tables = {
        # Core GEX Data
        'gex_history': 'Core GEX snapshots',
        'gex_levels': 'Strike-level gamma data',
        'flip_points': 'GEX flip points history',
        'gamma_walls': 'Call/put wall tracking',

        # Gamma Analysis
        'gamma_history': 'Gamma regime tracking',
        'gamma_daily_summary': 'Daily gamma summaries',
        'gamma_expiration_breakdown': 'Gamma by DTE',

        # Forward Analysis
        'forward_magnet_detections': 'Price magnet detection',
        'liberation_outcomes': 'Psychology trap outcomes',

        # Market Regime
        'regime_signals': 'Market regime signals',
        'psychology_traps': 'Psychology trap detections',

        # Trading
        'positions': 'Active positions',
        'autonomous_positions': 'Autonomous trader positions',
        'trade_recommendations': 'AI trade ideas',

        # Performance
        'performance': 'Daily P&L tracking',
        'backtest_results': 'Backtest results',
        'probability_predictions': 'Probability forecasts',
        'probability_outcomes': 'Prediction outcomes',

        # Signal Analysis
        'signal_confluence': 'Multi-signal confluence',
        'signal_backtests': 'Signal backtest results',

        # Options Greeks
        'options_greeks_history': 'Historical options Greeks',
        'vix_history': 'VIX historical data',

        # Experimental
        'experimental_signals': 'Experimental signals',
        'model_predictions': 'ML model predictions',
        'feature_importance': 'ML feature importance',

        # Market Context
        'market_events': 'Market events log',
        'news_sentiment': 'News sentiment data',
        'economic_calendar': 'Economic events',
    }

    print(f"\n📊 TABLE POPULATION STATUS\n")
    print(f"{'Table':<35} {'Records':>10} {'Latest Data':>25} {'Status'}")
    print("-" * 80)

    total_tables = len(tables)
    populated_tables = 0
    empty_tables = []

    for table, description in tables.items():
        try:
            # Get row count
            c.execute(f"SELECT COUNT(*) FROM {table}")
            count = c.fetchone()[0]

            # Get latest timestamp if available
            latest = "N/A"
            try:
                c.execute(f"SELECT timestamp FROM {table} ORDER BY timestamp DESC LIMIT 1")
                result = c.fetchone()
                if result:
                    ts = result[0]
                    # Try parsing different timestamp formats
                    try:
                        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                        latest = dt.strftime('%Y-%m-%d %H:%M')
                    except:
                        latest = str(ts)[:19]
            except:
                pass

            status = "✅" if count > 0 else "⚠️ EMPTY"
            if count > 0:
                populated_tables += 1
            else:
                empty_tables.append(table)

            print(f"{table:<35} {count:>10,} {latest:>25} {status}")

        except sqlite3.OperationalError:
            print(f"{table:<35} {'N/A':>10} {'N/A':>25} ❌ MISSING")

    print("-" * 80)
    print(f"\n📈 SUMMARY: {populated_tables}/{total_tables} tables populated ({populated_tables/total_tables*100:.1f}%)\n")

    # Show data freshness for key tables
    print("\n⏰ DATA FRESHNESS CHECK\n")
    print(f"{'Table':<35} {'Latest Record':>25} {'Age':>15}")
    print("-" * 80)

    key_tables = ['gex_history', 'gamma_history', 'forward_magnet_detections',
                  'liberation_outcomes', 'regime_signals']

    for table in key_tables:
        try:
            c.execute(f"SELECT timestamp FROM {table} ORDER BY timestamp DESC LIMIT 1")
            result = c.fetchone()
            if result:
                ts = result[0]
                try:
                    dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    age = datetime.now(dt.tzinfo) - dt if dt.tzinfo else datetime.now() - dt
                    age_str = f"{age.days}d {age.seconds//3600}h" if age.days > 0 else f"{age.seconds//3600}h {(age.seconds%3600)//60}m"
                    latest_str = dt.strftime('%Y-%m-%d %H:%M')
                except:
                    latest_str = str(ts)[:19]
                    age_str = "Unknown"

                print(f"{table:<35} {latest_str:>25} {age_str:>15}")
            else:
                print(f"{table:<35} {'No data':>25} {'-':>15}")
        except:
            print(f"{table:<35} {'Error':>25} {'-':>15}")

    # Show date range for historical data
    print("\n📅 HISTORICAL DATA COVERAGE\n")

    try:
        c.execute("""
            SELECT
                MIN(timestamp) as earliest,
                MAX(timestamp) as latest,
                COUNT(*) as total_records,
                COUNT(DISTINCT DATE(timestamp)) as unique_days
            FROM gex_history
            WHERE symbol = 'SPY'
        """)
        result = c.fetchone()
        if result and result[0]:
            earliest = datetime.fromisoformat(result[0].replace('Z', '+00:00'))
            latest = datetime.fromisoformat(result[1].replace('Z', '+00:00'))
            total_records = result[2]
            unique_days = result[3]

            print(f"  Symbol: SPY")
            print(f"  Date Range: {earliest.strftime('%Y-%m-%d')} to {latest.strftime('%Y-%m-%d')}")
            print(f"  Total Days: {unique_days}")
            print(f"  Total Records: {total_records:,}")
            print(f"  Avg Records/Day: {total_records/unique_days:.1f}")
    except Exception as e:
        print(f"  Error checking historical coverage: {e}")

    # Show empty tables that need attention
    if empty_tables:
        print(f"\n⚠️  EMPTY TABLES ({len(empty_tables)}):\n")
        for table in empty_tables:
            print(f"  - {table}: {tables[table]}")

        print("\n💡 Note: Some tables populate during operation:")
        print("   - positions/autonomous_positions: When trades are made")
        print("   - backtest_results: When backtests run")
        print("   - performance: As trades complete")
        print("   - trade_recommendations: When AI generates ideas")

    conn.close()

    print("\n" + "="*80 + "\n")

if __name__ == "__main__":
    check_database_status()
