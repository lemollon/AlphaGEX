#!/usr/bin/env python3
"""
LIVE BOT DIAGNOSTIC - Run during market hours to identify why bots aren't trading

This script checks:
1. Are bots actually running (scheduler heartbeats)?
2. Are scans being logged to scan_activity?
3. What's blocking trades (thresholds, open positions, etc)?
4. Is the database accessible?

RUN THIS ON RENDER API SERVICE:
  python scripts/live_bot_diagnostic.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

CENTRAL_TZ = ZoneInfo("America/Chicago")


def run_diagnostic():
    print("=" * 80)
    print("LIVE BOT DIAGNOSTIC")
    now = datetime.now(CENTRAL_TZ)
    print(f"Current Time: {now.strftime('%Y-%m-%d %H:%M:%S CT')} ({now.strftime('%A')})")
    print("=" * 80)

    # Check market hours
    market_open = now.replace(hour=8, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=0, second=0, microsecond=0)
    is_weekday = now.weekday() < 5

    if not is_weekday:
        print("\n[WARNING] Today is a weekend - bots won't trade")
    elif now < market_open:
        print(f"\n[INFO] Market opens at 8:30 AM CT ({market_open - now} from now)")
    elif now >= market_close:
        print(f"\n[INFO] Market closed at 3:00 PM CT ({now - market_close} ago)")
    else:
        print(f"\n[OK] Market is OPEN (closes in {market_close - now})")

    # Database connection
    print("\n" + "-" * 60)
    print("DATABASE CONNECTION")
    print("-" * 60)

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        print("[OK] Database connected successfully")
    except Exception as e:
        print(f"[FAIL] Database connection failed: {e}")
        return

    today = now.strftime("%Y-%m-%d")

    def safe_execute(query, params=None):
        """Execute query with automatic rollback on error"""
        try:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            return cursor.fetchall()
        except Exception as e:
            conn.rollback()  # Critical: rollback to clear aborted transaction
            raise e

    def ensure_position_tables():
        """Ensure all bot position tables exist - auto-create if missing"""
        tables_created = []

        def table_exists(table_name):
            """Check if a table exists"""
            try:
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = %s
                    )
                """, (table_name,))
                result = cursor.fetchone()
                return result[0] if result else False
            except Exception:
                conn.rollback()
                return False

        # ARES positions table
        try:
            existed = table_exists('ares_positions')
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ares_positions (
                    id SERIAL PRIMARY KEY,
                    position_id VARCHAR(50) UNIQUE NOT NULL,
                    ticker VARCHAR(10) NOT NULL DEFAULT 'SPY',
                    expiration DATE NOT NULL,
                    put_short_strike DECIMAL(10, 2) NOT NULL,
                    put_long_strike DECIMAL(10, 2) NOT NULL,
                    put_credit DECIMAL(10, 4) NOT NULL DEFAULT 0,
                    call_short_strike DECIMAL(10, 2) NOT NULL,
                    call_long_strike DECIMAL(10, 2) NOT NULL,
                    call_credit DECIMAL(10, 4) NOT NULL DEFAULT 0,
                    contracts INTEGER NOT NULL DEFAULT 1,
                    spread_width DECIMAL(10, 2) NOT NULL DEFAULT 2,
                    total_credit DECIMAL(10, 4) NOT NULL DEFAULT 0,
                    max_loss DECIMAL(10, 2) NOT NULL DEFAULT 0,
                    max_profit DECIMAL(10, 2) NOT NULL DEFAULT 0,
                    underlying_at_entry DECIMAL(10, 2) NOT NULL,
                    vix_at_entry DECIMAL(6, 2),
                    expected_move DECIMAL(10, 2),
                    call_wall DECIMAL(10, 2),
                    put_wall DECIMAL(10, 2),
                    gex_regime VARCHAR(30),
                    oracle_confidence DECIMAL(5, 4),
                    oracle_reasoning TEXT,
                    status VARCHAR(20) NOT NULL DEFAULT 'open',
                    open_time TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    close_time TIMESTAMP WITH TIME ZONE,
                    close_reason VARCHAR(100),
                    realized_pnl DECIMAL(10, 2),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
            conn.commit()
            if not existed:
                tables_created.append('ares_positions')
        except Exception as e:
            conn.rollback()

        # ATHENA positions table
        try:
            existed = table_exists('athena_positions')
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS athena_positions (
                    id SERIAL PRIMARY KEY,
                    position_id VARCHAR(50) UNIQUE NOT NULL,
                    ticker VARCHAR(10) NOT NULL DEFAULT 'SPY',
                    expiration DATE NOT NULL,
                    strategy VARCHAR(50) NOT NULL,
                    direction VARCHAR(20) NOT NULL,
                    long_strike DECIMAL(10, 2) NOT NULL,
                    short_strike DECIMAL(10, 2) NOT NULL,
                    contracts INTEGER NOT NULL DEFAULT 1,
                    entry_credit DECIMAL(10, 4) NOT NULL DEFAULT 0,
                    max_loss DECIMAL(10, 2) NOT NULL DEFAULT 0,
                    max_profit DECIMAL(10, 2) NOT NULL DEFAULT 0,
                    underlying_at_entry DECIMAL(10, 2) NOT NULL,
                    vix_at_entry DECIMAL(6, 2),
                    gex_regime VARCHAR(30),
                    oracle_confidence DECIMAL(5, 4),
                    status VARCHAR(20) NOT NULL DEFAULT 'open',
                    open_time TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    close_time TIMESTAMP WITH TIME ZONE,
                    close_reason VARCHAR(100),
                    realized_pnl DECIMAL(10, 2),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
            conn.commit()
            if not existed:
                tables_created.append('athena_positions')
        except Exception as e:
            conn.rollback()

        # PEGASUS positions table (SPX Iron Condors)
        try:
            existed = table_exists('pegasus_positions')
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pegasus_positions (
                    id SERIAL PRIMARY KEY,
                    position_id VARCHAR(50) UNIQUE NOT NULL,
                    ticker VARCHAR(10) NOT NULL DEFAULT 'SPX',
                    expiration DATE NOT NULL,
                    put_short_strike DECIMAL(10, 2) NOT NULL,
                    put_long_strike DECIMAL(10, 2) NOT NULL,
                    call_short_strike DECIMAL(10, 2) NOT NULL,
                    call_long_strike DECIMAL(10, 2) NOT NULL,
                    contracts INTEGER NOT NULL DEFAULT 1,
                    total_credit DECIMAL(10, 4) NOT NULL DEFAULT 0,
                    max_loss DECIMAL(10, 2) NOT NULL DEFAULT 0,
                    underlying_at_entry DECIMAL(10, 2) NOT NULL,
                    vix_at_entry DECIMAL(6, 2),
                    status VARCHAR(20) NOT NULL DEFAULT 'open',
                    open_time TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    close_time TIMESTAMP WITH TIME ZONE,
                    realized_pnl DECIMAL(10, 2),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
            conn.commit()
            if not existed:
                tables_created.append('pegasus_positions')
        except Exception as e:
            conn.rollback()

        # ICARUS positions table (Aggressive directional)
        try:
            existed = table_exists('icarus_positions')
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS icarus_positions (
                    id SERIAL PRIMARY KEY,
                    position_id VARCHAR(50) UNIQUE NOT NULL,
                    ticker VARCHAR(10) NOT NULL DEFAULT 'SPY',
                    expiration DATE NOT NULL,
                    strategy VARCHAR(50) NOT NULL,
                    direction VARCHAR(20) NOT NULL,
                    long_strike DECIMAL(10, 2) NOT NULL,
                    short_strike DECIMAL(10, 2) NOT NULL,
                    contracts INTEGER NOT NULL DEFAULT 1,
                    entry_credit DECIMAL(10, 4) NOT NULL DEFAULT 0,
                    max_loss DECIMAL(10, 2) NOT NULL DEFAULT 0,
                    underlying_at_entry DECIMAL(10, 2) NOT NULL,
                    vix_at_entry DECIMAL(6, 2),
                    status VARCHAR(20) NOT NULL DEFAULT 'open',
                    open_time TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    close_time TIMESTAMP WITH TIME ZONE,
                    realized_pnl DECIMAL(10, 2),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
            conn.commit()
            if not existed:
                tables_created.append('icarus_positions')
        except Exception as e:
            conn.rollback()

        # TITAN positions table (Aggressive SPX IC)
        try:
            existed = table_exists('titan_positions')
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS titan_positions (
                    id SERIAL PRIMARY KEY,
                    position_id VARCHAR(50) UNIQUE NOT NULL,
                    ticker VARCHAR(10) NOT NULL DEFAULT 'SPX',
                    expiration DATE NOT NULL,
                    put_short_strike DECIMAL(10, 2) NOT NULL,
                    put_long_strike DECIMAL(10, 2) NOT NULL,
                    call_short_strike DECIMAL(10, 2) NOT NULL,
                    call_long_strike DECIMAL(10, 2) NOT NULL,
                    contracts INTEGER NOT NULL DEFAULT 1,
                    total_credit DECIMAL(10, 4) NOT NULL DEFAULT 0,
                    max_loss DECIMAL(10, 2) NOT NULL DEFAULT 0,
                    underlying_at_entry DECIMAL(10, 2) NOT NULL,
                    vix_at_entry DECIMAL(6, 2),
                    status VARCHAR(20) NOT NULL DEFAULT 'open',
                    open_time TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    close_time TIMESTAMP WITH TIME ZONE,
                    realized_pnl DECIMAL(10, 2),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
            conn.commit()
            if not existed:
                tables_created.append('titan_positions')
        except Exception as e:
            conn.rollback()

        return tables_created

    # Ensure position tables exist before checking them
    created = ensure_position_tables()
    if created:
        print(f"\n[AUTO-FIX] Created missing tables: {', '.join(created)}")

    # 1. Bot Heartbeats (are bots running?)
    print("\n" + "-" * 60)
    print("BOT HEARTBEATS (Last 30 minutes)")
    print("-" * 60)

    try:
        rows = safe_execute("""
            SELECT bot_name, status, scan_count, last_heartbeat, details
            FROM bot_heartbeats
            ORDER BY last_heartbeat DESC
        """)
        if rows:
            recent_count = 0
            for row in rows:
                bot, status, scans, last_hb, details = row
                # Handle timezone-aware timestamps from database (stored as UTC)
                if last_hb:
                    if last_hb.tzinfo is None:
                        # Assume UTC if no timezone
                        from zoneinfo import ZoneInfo
                        last_hb = last_hb.replace(tzinfo=ZoneInfo("UTC"))
                    # Convert to Central Time for comparison
                    last_hb_ct = last_hb.astimezone(CENTRAL_TZ)
                    age = (now - last_hb_ct).total_seconds()
                    if age < 1800:  # 30 minutes
                        recent_count += 1
                else:
                    age = 99999
                age_str = f"{int(age)}s ago" if age < 3600 else f"{int(age/3600)}h ago"
                status_flag = "🟢" if age < 600 else "🟡" if age < 1800 else "🔴"
                print(f"  {status_flag} {bot:10} | {status:15} | Scans: {scans:5} | {age_str}")
            if recent_count == 0:
                print("\n  [WARNING] No heartbeats in last 30 minutes - bots may not be running!")
        else:
            print("  [WARNING] No heartbeats found - scheduler has never run!")
    except Exception as e:
        print(f"  [ERROR] Could not check heartbeats: {e}")

    # 2. Scan Activity (are scans being logged?)
    print("\n" + "-" * 60)
    print("SCAN ACTIVITY TODAY")
    print("-" * 60)

    try:
        rows = safe_execute("""
            SELECT
                bot_name,
                outcome,
                COUNT(*) as count,
                MAX(timestamp) as last_scan
            FROM scan_activity
            WHERE date = %s
            GROUP BY bot_name, outcome
            ORDER BY bot_name, count DESC
        """, (today,))
        if rows:
            current_bot = None
            for row in rows:
                bot, outcome, count, last_scan = row
                if bot != current_bot:
                    if current_bot is not None:
                        print()
                    current_bot = bot
                    print(f"  {bot}:")
                # Convert timestamp to CT for display
                if last_scan:
                    if last_scan.tzinfo is None:
                        last_scan = last_scan.replace(tzinfo=ZoneInfo("UTC"))
                    last_ct = last_scan.astimezone(CENTRAL_TZ).strftime('%I:%M %p CT')
                else:
                    last_ct = 'N/A'
                print(f"    {outcome:15} : {count:4} scans (last: {last_ct})")
        else:
            print("  [WARNING] No scan activity logged today!")
    except Exception as e:
        print(f"  [ERROR] Could not check scan activity: {e}")

    # 3. Open Positions (blocking new trades?)
    print("\n" + "-" * 60)
    print("OPEN POSITIONS")
    print("-" * 60)

    # Correct table names matching actual database schema
    position_tables = [
        ('ares_positions', 'ARES'),
        ('athena_positions', 'ATHENA'),
        ('pegasus_positions', 'PEGASUS'),
        ('icarus_positions', 'ICARUS'),
        ('titan_positions', 'TITAN'),
    ]

    for table, bot in position_tables:
        try:
            # First just get count - this is the most important check
            # Use UPPER() for case-insensitive matching since some tables use 'open' vs 'OPEN'
            rows = safe_execute(f"""
                SELECT COUNT(*) FROM {table} WHERE UPPER(status) = 'OPEN'
            """)
            count = rows[0][0] if rows and rows[0] else 0

            if count > 0:
                # Try to get additional details with flexible column names
                # Different tables use different column names (open_time vs entry_time, total_credit vs entry_credit)
                try:
                    detail_rows = safe_execute(f"""
                        SELECT
                            COALESCE(open_time, entry_time, created_at) as entry,
                            COALESCE(total_credit, entry_credit, 0) as credit
                        FROM {table}
                        WHERE UPPER(status) = 'OPEN'
                        ORDER BY COALESCE(open_time, entry_time, created_at) DESC
                        LIMIT 1
                    """)
                    if detail_rows and detail_rows[0]:
                        entry_time = detail_rows[0][0]
                        credit = detail_rows[0][1] or 0
                        # Convert entry_time to CT for display
                        if entry_time and entry_time.tzinfo is None:
                            entry_time = entry_time.replace(tzinfo=ZoneInfo("UTC"))
                        entry_ct = entry_time.astimezone(CENTRAL_TZ).strftime('%I:%M %p CT') if entry_time else 'N/A'
                        print(f"  {bot:10} : {count} open | Entry: {entry_ct} | Credit: ${float(credit):.2f}")
                    else:
                        print(f"  {bot:10} : {count} open positions")
                except Exception:
                    print(f"  {bot:10} : {count} open positions")
            else:
                print(f"  {bot:10} : No open positions")
        except Exception as e:
            conn.rollback()  # Rollback on error to clear transaction
            if 'does not exist' in str(e).lower():
                print(f"  {bot:10} : Table not found ({table})")
            else:
                print(f"  {bot:10} : Error - {e}")

    # 4. Recent Oracle Predictions
    print("\n" + "-" * 60)
    print("ORACLE PREDICTIONS TODAY")
    print("-" * 60)

    try:
        rows = safe_execute("""
            SELECT bot_name, COUNT(*),
                   AVG(win_probability::numeric),
                   AVG(confidence::numeric),
                   MAX(prediction_time)
            FROM oracle_predictions
            WHERE trade_date = %s
            GROUP BY bot_name
            ORDER BY bot_name
        """, (today,))
        if rows:
            for row in rows:
                bot, count, avg_wp, avg_conf, last = row
                avg_wp = float(avg_wp) if avg_wp else 0
                avg_conf = float(avg_conf) if avg_conf else 0
                print(f"  {bot:10} : {count:3} predictions | Avg WP: {avg_wp:.0%} | Avg Conf: {avg_conf:.0%}")
        else:
            print("  [INFO] No Oracle predictions stored today")
    except Exception as e:
        print(f"  [ERROR] Could not check Oracle predictions: {e}")

    # 5. Latest NO_TRADE Reasons
    print("\n" + "-" * 60)
    print("RECENT NO_TRADE REASONS (Last 20)")
    print("-" * 60)

    try:
        rows = safe_execute("""
            SELECT
                bot_name,
                timestamp,
                decision_summary,
                oracle_win_probability,
                quant_ml_win_probability,
                min_win_probability_threshold
            FROM scan_activity
            WHERE date = %s AND outcome = 'NO_TRADE'
            ORDER BY timestamp DESC
            LIMIT 20
        """, (today,))
        if rows:
            for row in rows:
                bot, ts, decision, oracle_wp, ml_wp, threshold = row
                # Convert timestamp to CT
                if ts and ts.tzinfo is None:
                    ts = ts.replace(tzinfo=ZoneInfo("UTC"))
                time_ct = ts.astimezone(CENTRAL_TZ).strftime('%I:%M %p') if ts else 'N/A'
                oracle_wp = float(oracle_wp) if oracle_wp else 0
                ml_wp = float(ml_wp) if ml_wp else 0
                threshold = float(threshold) if threshold else 0
                print(f"  {bot:8} @ {time_ct:>10} | Oracle:{oracle_wp:.0%} ML:{ml_wp:.0%} Thresh:{threshold:.0%}")
                if decision:
                    print(f"           Reason: {decision[:60]}")
        else:
            print("  [INFO] No NO_TRADE scans logged today")
    except Exception as e:
        print(f"  [ERROR] Could not check NO_TRADE reasons: {e}")

    # 6. Check config thresholds in database
    print("\n" + "-" * 60)
    print("BOT CONFIGURATION THRESHOLDS")
    print("-" * 60)

    try:
        rows = safe_execute("""
            SELECT bot_name, config_key, config_value
            FROM autonomous_config
            WHERE config_key LIKE '%min_win%' OR config_key LIKE '%confidence%' OR config_key LIKE '%threshold%'
            ORDER BY bot_name, config_key
        """)
        if rows:
            current_bot = None
            for row in rows:
                bot, key, value = row
                if bot != current_bot:
                    current_bot = bot
                    print(f"\n  {bot}:")
                print(f"    {key}: {value}")
        else:
            print("  [INFO] No config thresholds in database (using code defaults)")
    except Exception as e:
        if 'does not exist' in str(e).lower():
            print("  [INFO] autonomous_config table not found (using code defaults)")
        else:
            print(f"  [ERROR] {e}")

    # 7. Check if scheduler is running
    print("\n" + "-" * 60)
    print("SCHEDULER STATUS")
    print("-" * 60)

    try:
        rows = safe_execute("""
            SELECT bot_name,
                   COUNT(*) FILTER (WHERE timestamp >= NOW() - INTERVAL '1 hour') as last_hour,
                   COUNT(*) FILTER (WHERE timestamp >= NOW() - INTERVAL '5 minutes') as last_5min,
                   MAX(timestamp) as last_scan
            FROM scan_activity
            WHERE date = %s
            GROUP BY bot_name
        """, (today,))
        if rows:
            for row in rows:
                bot, last_hour, last_5min, last_scan = row
                status = "🟢 ACTIVE" if last_5min > 0 else ("🟡 SLOW" if last_hour > 0 else "🔴 STALE")
                # Convert last_scan to CT
                if last_scan and last_scan.tzinfo is None:
                    last_scan = last_scan.replace(tzinfo=ZoneInfo("UTC"))
                last_ct = last_scan.astimezone(CENTRAL_TZ).strftime('%I:%M %p CT') if last_scan else 'N/A'
                print(f"  {bot:10} | Last hour: {last_hour:3} | Last 5min: {last_5min:2} | {status} | Last: {last_ct}")
        else:
            print("  [WARNING] No scans today - scheduler may not be running")
    except Exception as e:
        print(f"  [ERROR] {e}")

    # 8. Circuit Breaker Status
    print("\n" + "-" * 60)
    print("CIRCUIT BREAKER / KILL SWITCH")
    print("-" * 60)

    try:
        from trading.circuit_breaker import get_circuit_breaker, is_trading_enabled
        cb = get_circuit_breaker()
        can_trade, reason = is_trading_enabled(current_positions=0, margin_used=0)
        state = cb.state.value if hasattr(cb, 'state') else 'UNKNOWN'
        daily_pnl = getattr(cb, 'daily_pnl', 0)
        consec_losses = getattr(cb, 'consecutive_losses', 0)

        status_icon = "🟢" if can_trade else "🔴"
        print(f"  {status_icon} State: {state}")
        print(f"     Can Trade: {can_trade}")
        if not can_trade:
            print(f"     Reason: {reason}")
        print(f"     Daily P&L: ${daily_pnl:,.2f}")
        print(f"     Consecutive Losses: {consec_losses}")
    except ImportError:
        print("  [INFO] Circuit breaker module not available")
    except Exception as e:
        print(f"  [ERROR] {e}")

    # 9. Solomon Kill Switch
    print("\n" + "-" * 60)
    print("SOLOMON FEEDBACK LOOP")
    print("-" * 60)

    try:
        from quant.solomon_feedback_loop import get_solomon
        solomon = get_solomon()
        for bot in ['ARES', 'ATHENA', 'PEGASUS', 'ICARUS', 'TITAN']:
            # Check if bot is killed via kill switch
            is_killed = solomon.is_bot_killed(bot) if hasattr(solomon, 'is_bot_killed') else False
            status_icon = "🔴" if is_killed else "🟢"
            print(f"  {status_icon} {bot:10} : {'KILLED' if is_killed else 'Active'}")
    except ImportError:
        print("  [INFO] Solomon module not available")
    except Exception as e:
        print(f"  [ERROR] {e}")

    # 10. Current Market Data (VIX, Spot)
    print("\n" + "-" * 60)
    print("CURRENT MARKET CONDITIONS")
    print("-" * 60)

    try:
        from data.unified_data_provider import get_vix, get_price
        vix = get_vix()
        spy_price = get_price('SPY')

        vix_status = "🟢 Normal" if vix and vix < 20 else "🟡 Elevated" if vix and vix < 30 else "🔴 High" if vix and vix < 40 else "🔴 EXTREME" if vix else "❓ Unknown"
        vix_str = f"{vix:.2f}" if vix else "N/A"
        spy_str = f"${spy_price:.2f}" if spy_price else "N/A"
        print(f"  VIX: {vix_str} ({vix_status})")
        print(f"  SPY: {spy_str}")

        if vix and vix >= 40:
            print(f"  ⚠️ VIX > 40 - ALL IRON CONDOR TRADES BLOCKED")
        elif vix and vix >= 30:
            print(f"  ⚠️ VIX > 30 - Mon/Fri trades may be blocked")
    except ImportError:
        print("  [INFO] Data provider not available")
    except Exception as e:
        print(f"  [ERROR] {e}")

    # 11. Market Calendar Checks
    print("\n" + "-" * 60)
    print("MARKET CALENDAR")
    print("-" * 60)

    try:
        from trading.market_calendar import MarketCalendar
        cal = MarketCalendar()

        is_trading_day = cal.is_trading_day(today)
        is_open = cal.is_market_open()

        print(f"  Trading Day: {'✅ Yes' if is_trading_day else '❌ No (Holiday)'}")
        print(f"  Market Open: {'✅ Yes' if is_open else '❌ No'}")

        # Check early close (wrap in try/except for timezone issues)
        try:
            is_early_close = cal.is_early_close_day(today) if hasattr(cal, 'is_early_close_day') else False
            if is_early_close:
                print(f"  ⚠️ Early Close Day (12:00 PM CT)")
        except:
            pass

        # Check FOMC (wrap in try/except for timezone issues)
        try:
            if hasattr(cal, 'is_fomc_week'):
                is_fomc = cal.is_fomc_week()
                if is_fomc:
                    print(f"  ⚠️ FOMC Week - Trading may be restricted")
        except:
            pass

        # Check earnings
        try:
            if hasattr(cal, 'has_major_earnings_soon'):
                has_earnings = cal.has_major_earnings_soon(days_ahead=2)
                if has_earnings:
                    print(f"  ⚠️ Major Earnings Soon - Trading may be restricted")
        except:
            pass
    except ImportError:
        print("  [INFO] Market calendar not available")
    except Exception as e:
        print(f"  [ERROR] {e}")

    # Summary
    print("\n" + "=" * 80)
    print("DIAGNOSTIC SUMMARY")
    print("=" * 80)

    # Check for common issues
    issues = []

    # Check heartbeats
    try:
        rows = safe_execute("""
            SELECT COUNT(*) FROM bot_heartbeats
            WHERE last_heartbeat >= NOW() - INTERVAL '10 minutes'
        """)
        if rows and rows[0][0] == 0:
            issues.append("No bot heartbeats in last 10 minutes - scheduler may be down")
    except:
        pass

    # Check scan activity during market hours
    if is_weekday and market_open <= now < market_close:
        try:
            rows = safe_execute("""
                SELECT COUNT(*) FROM scan_activity
                WHERE date = %s
                AND outcome NOT IN ('BEFORE_WINDOW', 'AFTER_WINDOW', 'MARKET_CLOSED')
            """, (today,))
            if rows and rows[0][0] == 0:
                issues.append("No market-hours scans logged today - bots may not be scanning")
        except:
            pass

    # Check circuit breaker
    try:
        from trading.circuit_breaker import is_trading_enabled
        can_trade, reason = is_trading_enabled(current_positions=0, margin_used=0)
        if not can_trade:
            issues.append(f"Circuit breaker BLOCKING trades: {reason}")
    except:
        pass

    # Check VIX level
    try:
        from data.unified_data_provider import get_vix
        vix = get_vix()
        if vix and vix >= 40:
            issues.append(f"VIX at {vix:.1f} - EXTREME level blocking all IC trades")
    except:
        pass

    # Check for low win probability in recent scans
    try:
        rows = safe_execute("""
            SELECT AVG(oracle_win_probability::numeric), AVG(min_win_probability_threshold::numeric)
            FROM scan_activity
            WHERE date = %s AND outcome = 'NO_TRADE'
            AND oracle_win_probability IS NOT NULL
        """, (today,))
        if rows and rows[0][0] is not None:
            avg_wp = float(rows[0][0])
            avg_thresh = float(rows[0][1]) if rows[0][1] else 0.42
            if avg_wp < avg_thresh:
                issues.append(f"Avg Oracle win prob ({avg_wp:.0%}) below threshold ({avg_thresh:.0%})")
    except:
        pass

    if issues:
        print("\n[ISSUES FOUND]:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("\n[OK] No critical issues detected")

    print("\n[TIP] Run this script during market hours (8:30 AM - 3:00 PM CT) for best results")

    conn.close()


if __name__ == "__main__":
    run_diagnostic()
