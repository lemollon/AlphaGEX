#!/usr/bin/env python3
"""
AlphaGEX System Verification Script
====================================
Verifies the entire system is working end-to-end:
- Database connectivity
- Table data integrity
- Trade flow verification
- Feedback loop status

Run: python scripts/verify_system.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Colors
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def ok(msg):
    print(f"  {GREEN}✓{RESET} {msg}")

def fail(msg, detail=None):
    print(f"  {RED}✗{RESET} {msg}")
    if detail:
        print(f"    {RED}→ {detail[:100]}{RESET}")

def warn(msg):
    print(f"  {YELLOW}⚠{RESET} {msg}")

def section(title):
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE} {title}{RESET}")
    print(f"{BLUE}{'='*60}{RESET}")


def main():
    print(f"\n{BLUE}AlphaGEX System Verification{RESET}")
    print(f"{'='*60}")

    # =========================================================================
    # 1. DATABASE CONNECTION
    # =========================================================================
    section("1. DATABASE CONNECTION")

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        ok("PostgreSQL connected successfully")
    except Exception as e:
        fail("Database connection failed", str(e))
        print("\n⚠️  Cannot verify system without database connection.")
        print("   Ensure DATABASE_URL is set correctly.")
        sys.exit(1)

    # =========================================================================
    # 2. TABLE DATA COUNTS
    # =========================================================================
    section("2. TABLE DATA COUNTS")

    tables = [
        ('regime_signals', 'Regime detection signals'),
        ('backtest_results', 'Backtest results'),
        ('autonomous_open_positions', 'Open positions'),
        ('autonomous_closed_trades', 'Closed trades'),
        ('autonomous_trade_log', 'Trade log entries'),
        ('gamma_history', 'Gamma history'),
        ('gex_history', 'GEX history'),
    ]

    table_counts = {}
    for table, desc in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            table_counts[table] = count
            if count > 0:
                ok(f"{desc}: {count} records")
            else:
                warn(f"{desc}: EMPTY")
        except Exception as e:
            fail(f"{desc}", str(e))
            table_counts[table] = 0

    # =========================================================================
    # 3. OPEN POSITIONS DETAIL
    # =========================================================================
    section("3. CURRENT OPEN POSITIONS")

    try:
        cursor.execute("""
            SELECT id, timestamp, symbol, strategy, entry_price,
                   current_price, quantity, unrealized_pnl, status
            FROM autonomous_open_positions
            WHERE status = 'open'
            ORDER BY timestamp DESC
            LIMIT 10
        """)
        positions = cursor.fetchall()

        if positions:
            print(f"\n  {'ID':<4} {'Symbol':<6} {'Strategy':<25} {'Entry':>8} {'Qty':>5} {'PnL':>10}")
            print(f"  {'-'*4} {'-'*6} {'-'*25} {'-'*8} {'-'*5} {'-'*10}")
            for pos in positions:
                pid, ts, sym, strat, entry, curr, qty, pnl, status = pos
                entry_str = f"${entry:.2f}" if entry else "N/A"
                pnl_str = f"${pnl:.2f}" if pnl else "N/A"
                qty_str = str(qty) if qty else "N/A"
                strat_short = strat[:25] if strat else "N/A"
                print(f"  {pid:<4} {sym or 'N/A':<6} {strat_short:<25} {entry_str:>8} {qty_str:>5} {pnl_str:>10}")
            ok(f"Found {len(positions)} open positions")
        else:
            warn("No open positions currently")
    except Exception as e:
        fail("Open positions query", str(e))

    # =========================================================================
    # 4. RECENT CLOSED TRADES
    # =========================================================================
    section("4. RECENT CLOSED TRADES")

    try:
        cursor.execute("""
            SELECT id, close_timestamp, symbol, strategy,
                   entry_price, exit_price, quantity, realized_pnl, outcome
            FROM autonomous_closed_trades
            ORDER BY close_timestamp DESC
            LIMIT 5
        """)
        trades = cursor.fetchall()

        if trades:
            total_pnl = 0
            winners = 0
            for trade in trades:
                tid, ts, sym, strat, entry, exit_p, qty, pnl, outcome = trade
                if pnl:
                    total_pnl += pnl
                    if pnl > 0:
                        winners += 1
                ts_str = ts.strftime("%m/%d %H:%M") if ts else "N/A"
                pnl_str = f"${pnl:.2f}" if pnl else "N/A"
                color = GREEN if (pnl and pnl > 0) else RED if pnl else RESET
                print(f"  {color}{ts_str}: {sym or 'N/A'} - {strat[:20] if strat else 'N/A'} → {pnl_str}{RESET}")

            print(f"\n  Recent 5 trades: {GREEN}{winners}W{RESET}/{RED}{len(trades)-winners}L{RESET}, Total PnL: ${total_pnl:.2f}")
            ok(f"Found {table_counts.get('autonomous_closed_trades', 0)} total closed trades")
        else:
            warn("No closed trades yet")
    except Exception as e:
        fail("Closed trades query", str(e))

    # =========================================================================
    # 5. RECENT TRADE LOG
    # =========================================================================
    section("5. RECENT TRADE LOG ACTIVITY")

    try:
        cursor.execute("""
            SELECT timestamp, action, symbol, details, success
            FROM autonomous_trade_log
            ORDER BY timestamp DESC
            LIMIT 10
        """)
        logs = cursor.fetchall()

        if logs:
            for log in logs[:5]:
                ts, action, sym, details, success = log
                ts_str = ts.strftime("%m/%d %H:%M") if ts else "N/A"
                status = GREEN + "✓" + RESET if success else RED + "✗" + RESET
                details_short = (details[:40] + "...") if details and len(details) > 40 else (details or "")
                print(f"  {status} {ts_str}: [{action}] {sym or ''} {details_short}")

            ok(f"Found {table_counts.get('autonomous_trade_log', 0)} total log entries")
        else:
            warn("No trade log activity")
    except Exception as e:
        fail("Trade log query", str(e))

    # =========================================================================
    # 6. REGIME SIGNAL STATUS
    # =========================================================================
    section("6. RECENT REGIME SIGNALS")

    try:
        cursor.execute("""
            SELECT timestamp, symbol, spy_price, net_gamma,
                   primary_regime_type, confidence_score, trade_direction
            FROM regime_signals
            ORDER BY timestamp DESC
            LIMIT 5
        """)
        signals = cursor.fetchall()

        if signals:
            for sig in signals:
                ts, sym, price, gamma, regime, conf, direction = sig
                ts_str = ts.strftime("%m/%d %H:%M") if ts else "N/A"
                price_str = f"${price:.2f}" if price else "N/A"
                conf_str = f"{conf:.0f}%" if conf else "N/A"
                regime_short = regime[:20] if regime else "N/A"
                print(f"  {ts_str}: SPY {price_str} | {regime_short} ({conf_str}) → {direction or 'N/A'}")

            ok(f"Found {table_counts.get('regime_signals', 0)} total signals")
        else:
            warn("No regime signals recorded")
    except Exception as e:
        fail("Regime signals query", str(e))

    # =========================================================================
    # 7. STRATEGY STATS (Feedback Loop)
    # =========================================================================
    section("7. STRATEGY STATS (Feedback Loop)")

    try:
        from core.strategy_stats import get_strategy_stats
        stats = get_strategy_stats()

        backtest_count = sum(1 for s in stats.values() if s.get('source') == 'backtest')
        initial_count = sum(1 for s in stats.values() if s.get('source') == 'initial_estimate')

        print(f"\n  Total strategies: {len(stats)}")
        print(f"  From backtest:    {GREEN}{backtest_count}{RESET}")
        print(f"  Initial estimates: {YELLOW}{initial_count}{RESET}")

        if backtest_count > 0:
            ok("Feedback loop is ACTIVE - backtest data flowing to strategy stats")
        else:
            warn("Feedback loop NOT YET ACTIVE - run backtests to update stats")
            print("      Run: POST /api/backtests/run")
    except Exception as e:
        fail("Strategy stats check", str(e))

    # =========================================================================
    # 8. BACKTEST RESULTS
    # =========================================================================
    section("8. LATEST BACKTEST RESULTS")

    try:
        cursor.execute("""
            SELECT pattern_name, win_rate, total_signals, kelly_fraction
            FROM backtest_results
            ORDER BY timestamp DESC
            LIMIT 5
        """)
        results = cursor.fetchall()

        if results:
            for r in results:
                pattern, wr, signals, kelly = r
                wr_str = f"{wr:.1f}%" if wr else "N/A"
                kelly_str = f"{kelly:.2f}" if kelly else "N/A"
                signals_str = str(signals) if signals else "0"
                print(f"  {pattern[:25]:<25} | Win: {wr_str:>6} | Signals: {signals_str:>4} | Kelly: {kelly_str}")

            ok(f"Found {table_counts.get('backtest_results', 0)} total backtest records")
        else:
            warn("No backtest results yet")
    except Exception as e:
        fail("Backtest results query", str(e))

    # =========================================================================
    # SUMMARY
    # =========================================================================
    section("SYSTEM STATUS SUMMARY")

    has_data = table_counts.get('regime_signals', 0) > 0
    has_positions = table_counts.get('autonomous_open_positions', 0) > 0
    has_trades = table_counts.get('autonomous_closed_trades', 0) > 0 or table_counts.get('autonomous_trade_log', 0) > 0
    has_backtests = table_counts.get('backtest_results', 0) > 0

    status_items = [
        (has_data, "Data Pipeline", "Regime signals being generated"),
        (has_positions or has_trades, "Trade Execution", "Trades being opened/closed"),
        (has_backtests, "Backtesting", "Backtest results available"),
    ]

    all_working = True
    for working, name, desc in status_items:
        if working:
            ok(f"{name}: {desc}")
        else:
            warn(f"{name}: Not yet active")
            all_working = False

    if all_working:
        print(f"\n{GREEN}{'='*60}")
        print(f" ✓ SYSTEM IS OPERATIONAL")
        print(f"{'='*60}{RESET}\n")
    else:
        print(f"\n{YELLOW}{'='*60}")
        print(f" ⚠ SYSTEM PARTIALLY OPERATIONAL")
        print(f"   Some components may need initialization")
        print(f"{'='*60}{RESET}\n")

    conn.close()
    return 0 if all_working else 1


if __name__ == "__main__":
    sys.exit(main())
