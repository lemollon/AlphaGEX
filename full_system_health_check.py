#!/usr/bin/env python3
"""
COMPLETE ALPHAGEX SYSTEM HEALTH CHECK
Verifies all components: Frontend, Backend API, Data Pipelines, Trading Systems
"""

from database_adapter import get_connection
from datetime import datetime, timedelta
import os
import sys
import subprocess

def print_header(title):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")

def check_backend_api():
    """Check FastAPI backend"""
    print_header("🌐 BACKEND API (FastAPI)")

    # Check if backend process is running
    try:
        result = subprocess.run(['pgrep', '-f', 'uvicorn'], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Backend Process Running")
            print(f"   └─ PIDs: {result.stdout.strip()}")
        else:
            print("❌ Backend Not Running")
            print("   └─ Run: python backend/main.py")
    except:
        print("⚠️  Cannot check backend process")

    print()

    # Check API routes
    conn = get_connection()
    c = conn.cursor()

    checks = {
        'GEX Data API': "SELECT COUNT(*) FROM gex_history",
        'Market Data': "SELECT COUNT(*) FROM autonomous_trader_logs WHERE symbol = 'SPY'",
        'Position Management': "SELECT COUNT(*) FROM autonomous_positions",
        'Trade History': "SELECT COUNT(*) FROM autonomous_positions WHERE status = 'CLOSED'"
    }

    for name, query in checks.items():
        try:
            c.execute(query)
            count = c.fetchone()[0]
            if count > 0:
                print(f"✅ {name}: {count} records")
            else:
                print(f"⚠️  {name}: No data yet")
        except Exception as e:
            print(f"❌ {name}: {e}")

    conn.close()

def check_gex_engine():
    """Check GEX calculation and gamma exposure tracking"""
    print_header("📊 GEX CALCULATION ENGINE")

    conn = get_connection()
    c = conn.cursor()

    # Check GEX history
    try:
        c.execute("SELECT COUNT(*) FROM gex_history")
        count = c.fetchone()[0]

        if count > 0:
            c.execute("SELECT MAX(timestamp) FROM gex_history")
            latest = c.fetchone()[0]
            print(f"✅ GEX History: {count} records")
            print(f"   └─ Latest: {latest}")
        else:
            print("⚠️  GEX History: Empty")
            print("   └─ Will populate as autonomous trader runs")
    except Exception as e:
        print(f"❌ GEX History: {e}")

    print()

    # Check gamma tracking
    try:
        c.execute("SELECT COUNT(*) FROM gamma_history")
        count = c.fetchone()[0]

        if count > 0:
            print(f"✅ Gamma History: {count} records")
        else:
            print("⚠️  Gamma History: Empty")
            print("   └─ Populated by data collection jobs")
    except Exception as e:
        print(f"❌ Gamma History: {e}")

    print()

    # Check if GEX data is being logged by autonomous trader
    try:
        c.execute("""
            SELECT COUNT(*)
            FROM autonomous_trader_logs
            WHERE net_gex IS NOT NULL
            AND timestamp > NOW() - INTERVAL '24 hours'
        """)
        count = c.fetchone()[0]

        if count > 0:
            print(f"✅ Real-time GEX Tracking: {count} readings (24h)")
        else:
            print("⚠️  No recent GEX readings")
    except Exception as e:
        print(f"❌ Real-time GEX: {e}")

    conn.close()

def check_pattern_detection():
    """Check psychology trap and pattern detection"""
    print_header("🧠 PATTERN DETECTION & PSYCHOLOGY TRAPS")

    conn = get_connection()
    c = conn.cursor()

    # Check pattern detection logs
    try:
        c.execute("""
            SELECT COUNT(*)
            FROM autonomous_trader_logs
            WHERE pattern_detected IS NOT NULL
            AND timestamp > NOW() - INTERVAL '24 hours'
        """)
        count = c.fetchone()[0]

        if count > 0:
            print(f"✅ Pattern Detection: {count} patterns detected (24h)")

            # Show pattern types
            c.execute("""
                SELECT pattern_detected, COUNT(*) as cnt
                FROM autonomous_trader_logs
                WHERE pattern_detected IS NOT NULL
                AND timestamp > NOW() - INTERVAL '7 days'
                GROUP BY pattern_detected
                ORDER BY cnt DESC
                LIMIT 5
            """)
            patterns = c.fetchall()
            if patterns:
                print("   └─ Top patterns:")
                for pattern, cnt in patterns:
                    print(f"      • {pattern}: {cnt} times")
        else:
            print("⚠️  No patterns detected recently")
    except Exception as e:
        print(f"❌ Pattern Detection: {e}")

    print()

    # Check liberation setups
    try:
        c.execute("""
            SELECT COUNT(*)
            FROM autonomous_trader_logs
            WHERE liberation_setup = TRUE
        """)
        count = c.fetchone()[0]
        print(f"{'✅' if count > 0 else '⚠️ '} Liberation Setups: {count} detected")
    except:
        print("⚠️  Liberation tracking not available")

    # Check false floors
    try:
        c.execute("""
            SELECT COUNT(*)
            FROM autonomous_trader_logs
            WHERE false_floor_detected = TRUE
        """)
        count = c.fetchone()[0]
        print(f"{'✅' if count > 0 else '⚠️ '} False Floors: {count} detected")
    except:
        print("⚠️  False floor tracking not available")

    conn.close()

def check_data_feeds():
    """Check external data feed integrations"""
    print_header("📡 EXTERNAL DATA FEEDS")

    # Check Polygon.io
    polygon_key = os.getenv('POLYGON_API_KEY')
    if polygon_key:
        print(f"✅ Polygon.io API Key: {'*' * 20}{polygon_key[-4:]}")
    else:
        print("❌ Polygon.io API Key: Not set")

    # Check Trading Volatility API
    tv_key = os.getenv('TRADING_VOLATILITY_API_KEY')
    if tv_key:
        print(f"✅ Trading Volatility Key: {'*' * 20}{tv_key[-4:]}")
    else:
        print("❌ Trading Volatility Key: Not set")

    # Check Claude API
    claude_key = os.getenv('CLAUDE_API_KEY') or os.getenv('ANTHROPIC_API_KEY')
    if claude_key:
        print(f"✅ Claude API Key: {'*' * 20}{claude_key[-4:]}")
    else:
        print("❌ Claude API Key: Not set")

    print()

    # Check recent data from feeds
    conn = get_connection()
    c = conn.cursor()

    try:
        c.execute("""
            SELECT COUNT(*)
            FROM historical_open_interest
            WHERE date = CURRENT_DATE
        """)
        today_oi = c.fetchone()[0]

        if today_oi > 0:
            print(f"✅ Polygon.io OI Data: {today_oi} contracts today")
        else:
            print("⚠️  No OI data for today (may update after market close)")
    except:
        pass

    conn.close()

def check_backtest_engine():
    """Check backtesting system"""
    print_header("📈 BACKTEST ENGINE")

    conn = get_connection()
    c = conn.cursor()

    # Check backtest results
    try:
        c.execute("SELECT COUNT(*) FROM backtest_results")
        count = c.fetchone()[0]

        if count > 0:
            c.execute("SELECT strategy_name, total_trades, win_rate, total_return_pct FROM backtest_results ORDER BY total_return_pct DESC LIMIT 3")
            results = c.fetchall()

            print(f"✅ Backtest Results: {count} strategies tested")
            print("   └─ Top performers:")
            for strategy, trades, win_rate, returns in results:
                print(f"      • {strategy}: {win_rate:.1f}% win rate, {returns:+.1f}% return")
        else:
            print("⚠️  No backtest results yet")
            print("   └─ Run: python run_all_backtests.py")
    except Exception as e:
        print(f"❌ Backtest Results: {e}")

    conn.close()

def check_strategy_optimizer():
    """Check strategy optimization tables"""
    print_header("🎯 STRATEGY OPTIMIZER")

    conn = get_connection()
    c = conn.cursor()

    tables = {
        'Strike Performance': 'strike_performance',
        'DTE Optimization': 'dte_performance',
        'Greeks Analysis': 'greeks_performance',
        'Spread Width': 'spread_width_performance'
    }

    all_empty = True

    for name, table in tables.items():
        try:
            c.execute(f"SELECT COUNT(*) FROM {table}")
            count = c.fetchone()[0]

            if count > 0:
                print(f"✅ {name}: {count} records")
                all_empty = False
            else:
                print(f"⚠️  {name}: Empty")
        except Exception as e:
            print(f"❌ {name}: {e}")

    if all_empty:
        print("\n💡 Action: Run ./run_optimizer.sh to populate these tables")

    conn.close()

def check_ai_features():
    """Check AI/ML features"""
    print_header("🤖 AI/ML FEATURES")

    conn = get_connection()
    c = conn.cursor()

    # Check AI decision logs
    try:
        c.execute("""
            SELECT COUNT(*)
            FROM autonomous_trader_logs
            WHERE ai_thought_process IS NOT NULL
        """)
        count = c.fetchone()[0]

        if count > 0:
            print(f"✅ AI Decision Making: {count} decisions logged")
        else:
            print("⚠️  No AI decisions logged yet")
    except:
        print("⚠️  AI decision tracking not available")

    # Check probability predictions
    try:
        c.execute("SELECT COUNT(*) FROM probability_predictions")
        count = c.fetchone()[0]

        if count > 0:
            print(f"✅ Probability Engine: {count} predictions")
        else:
            print("⚠️  Probability Engine: Not trained yet")
    except:
        print("⚠️  Probability engine not available")

    # Check ML pattern learning
    try:
        c.execute("""
            SELECT COUNT(*)
            FROM autonomous_trader_logs
            WHERE pattern_detected IS NOT NULL
        """)
        count = c.fetchone()[0]

        if count > 0:
            print(f"✅ ML Pattern Learning: {count} patterns for training")
        else:
            print("⚠️  No pattern data for ML training")
    except:
        pass

    conn.close()

def check_frontend():
    """Check React frontend"""
    print_header("⚛️  FRONTEND (React)")

    # Check if frontend files exist
    frontend_path = "frontend/build"
    if os.path.exists(frontend_path):
        print(f"✅ Production Build: {frontend_path}")

        # Count files
        file_count = sum(len(files) for _, _, files in os.walk(frontend_path))
        print(f"   └─ {file_count} static files")
    else:
        print("⚠️  Production build not found")
        print("   └─ Run: cd frontend && npm run build")

    # Check frontend source
    if os.path.exists("frontend/src"):
        print("✅ Source Code: frontend/src")
    else:
        print("❌ Frontend source not found")

def check_scheduled_jobs():
    """Check scheduled background jobs"""
    print_header("⏰ SCHEDULED JOBS")

    # Check if cron is configured
    try:
        result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
        cron_jobs = result.stdout

        if 'historical_oi_snapshot_job' in cron_jobs:
            print("✅ Daily OI Snapshot: Scheduled")
        else:
            print("⚠️  Daily OI Snapshot: Not scheduled")
            print("   └─ Add: 30 16 * * 1-5 python3 historical_oi_snapshot_job.py")

        if 'autonomous' in cron_jobs:
            print("✅ Autonomous Trader: Scheduled")
        else:
            print("⚠️  Autonomous Trader: Not in cron (may run as service)")
    except:
        print("⚠️  Cannot check crontab (may use systemd/render)")

    print()

    # Check if autonomous trader is running
    try:
        result = subprocess.run(['pgrep', '-f', 'autonomous_scheduler'], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Autonomous Trader Process: Running")
        else:
            print("⚠️  Autonomous Trader: Not running as standalone process")
            print("   └─ May be integrated in main backend")
    except:
        pass

def generate_report_card():
    """Generate overall system health score"""
    print_header("📊 SYSTEM HEALTH REPORT CARD")

    conn = get_connection()
    c = conn.cursor()

    scores = []

    # Score 1: Data Pipeline (25 points)
    try:
        c.execute("SELECT COUNT(*) FROM historical_open_interest")
        oi_count = c.fetchone()[0]
        if oi_count > 20000:
            scores.append(('Data Pipeline', 25, 25))
        elif oi_count > 5000:
            scores.append(('Data Pipeline', 25, 20))
        else:
            scores.append(('Data Pipeline', 25, 10))
    except:
        scores.append(('Data Pipeline', 25, 0))

    # Score 2: Autonomous Trading (25 points)
    try:
        c.execute("SELECT COUNT(*) FROM autonomous_positions")
        trades = c.fetchone()[0]
        if trades > 10:
            scores.append(('Autonomous Trading', 25, 25))
        elif trades > 0:
            scores.append(('Autonomous Trading', 25, 15))
        else:
            scores.append(('Autonomous Trading', 25, 5))
    except:
        scores.append(('Autonomous Trading', 25, 0))

    # Score 3: Pattern Detection (20 points)
    try:
        c.execute("SELECT COUNT(*) FROM autonomous_trader_logs WHERE pattern_detected IS NOT NULL")
        patterns = c.fetchone()[0]
        if patterns > 50:
            scores.append(('Pattern Detection', 20, 20))
        elif patterns > 10:
            scores.append(('Pattern Detection', 20, 15))
        else:
            scores.append(('Pattern Detection', 20, 5))
    except:
        scores.append(('Pattern Detection', 20, 0))

    # Score 4: Strategy Optimization (15 points)
    try:
        c.execute("SELECT COUNT(*) FROM strike_performance")
        opt_data = c.fetchone()[0]
        if opt_data > 100:
            scores.append(('Strategy Optimization', 15, 15))
        elif opt_data > 0:
            scores.append(('Strategy Optimization', 15, 10))
        else:
            scores.append(('Strategy Optimization', 15, 0))
    except:
        scores.append(('Strategy Optimization', 15, 0))

    # Score 5: Backtesting (15 points)
    try:
        c.execute("SELECT COUNT(*) FROM backtest_results")
        backtests = c.fetchone()[0]
        if backtests > 5:
            scores.append(('Backtesting', 15, 15))
        elif backtests > 0:
            scores.append(('Backtesting', 15, 10))
        else:
            scores.append(('Backtesting', 15, 0))
    except:
        scores.append(('Backtesting', 15, 0))

    conn.close()

    # Calculate total
    total_possible = sum(s[1] for s in scores)
    total_earned = sum(s[2] for s in scores)
    percentage = (total_earned / total_possible) * 100

    # Print scores
    for name, possible, earned in scores:
        status = '✅' if earned == possible else '⚠️' if earned > 0 else '❌'
        print(f"{status} {name:<25} {earned}/{possible} points")

    print(f"\n{'='*80}")
    print(f"OVERALL SCORE: {total_earned}/{total_possible} ({percentage:.0f}%)")

    if percentage >= 90:
        print("GRADE: A+ 🏆 - Excellent! Production Ready")
    elif percentage >= 80:
        print("GRADE: A 🎉 - Great! Fully operational")
    elif percentage >= 70:
        print("GRADE: B 👍 - Good, minor improvements needed")
    elif percentage >= 60:
        print("GRADE: C ⚠️  - Functional, needs optimization")
    else:
        print("GRADE: D ❌ - Needs significant work")

    print(f"{'='*80}")

def main():
    """Run complete system health check"""
    print("\n" + "="*80)
    print("  🏥 ALPHAGEX COMPLETE SYSTEM HEALTH CHECK")
    print("="*80)
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)

    check_backend_api()
    check_gex_engine()
    check_pattern_detection()
    check_data_feeds()
    check_backtest_engine()
    check_strategy_optimizer()
    check_ai_features()
    check_frontend()
    check_scheduled_jobs()
    generate_report_card()

    print("\n" + "="*80)
    print("  ✅ COMPLETE SYSTEM CHECK FINISHED")
    print("="*80 + "\n")

if __name__ == "__main__":
    main()
