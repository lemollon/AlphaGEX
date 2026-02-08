#!/usr/bin/env python3
"""
JUBILEE IC Trading Diagnostic Script

Run this script to understand why JUBILEE (Jubilee) isn't trading today.
It checks all the conditions that must be met before a trade can be placed.

Usage:
    python scripts/debug_prometheus_ic.py
"""

import os
import sys
from datetime import datetime, date, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Central timezone
try:
    from zoneinfo import ZoneInfo
    CENTRAL_TZ = ZoneInfo("America/Chicago")
except ImportError:
    import pytz
    CENTRAL_TZ = pytz.timezone("America/Chicago")

def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def check_result(name, passed, details=""):
    status = "[PASS]" if passed else "[FAIL]"
    color = "\033[92m" if passed else "\033[91m"
    reset = "\033[0m"
    print(f"{color}{status}{reset} {name}")
    if details:
        print(f"       {details}")
    return passed

def main():
    print("\n" + "="*60)
    print("   JUBILEE IC Trading Diagnostic")
    print("   (Why Jubilee isn't trading)")
    print("="*60)

    now = datetime.now(CENTRAL_TZ)
    print(f"\nCurrent Time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"Day of Week: {now.strftime('%A')}")

    all_checks_passed = True

    # =====================================================
    # SECTION 1: Basic Prerequisites
    # =====================================================
    print_section("1. BASIC PREREQUISITES")

    # Check if JUBILEE modules can be imported
    try:
        from trading.jubilee.trader import JubileeICTrader
        from trading.jubilee.models import PrometheusICConfig, TradingMode
        from trading.jubilee.db import JubileeDatabase
        check_result("JUBILEE IC modules import", True)
    except ImportError as e:
        check_result("JUBILEE IC modules import", False, str(e))
        print("\nCannot proceed without JUBILEE modules!")
        return

    # Check database connection
    try:
        from database_adapter import get_connection
        conn = get_connection()
        if conn:
            conn.close()
            check_result("Database connection", True)
        else:
            check_result("Database connection", False, "No connection returned")
            all_checks_passed = False
    except Exception as e:
        check_result("Database connection", False, str(e))
        all_checks_passed = False

    # Check Tradier API
    try:
        from data.tradier_data_fetcher import TradierClient
        tradier = TradierClient(sandbox=False)
        quote = tradier.get_quote("SPX")
        if quote and quote.get('last', 0) > 0:
            check_result("Tradier API (SPX quote)", True, f"SPX = ${quote.get('last'):.2f}")
        else:
            check_result("Tradier API (SPX quote)", False, "No valid quote returned")
            all_checks_passed = False
    except Exception as e:
        check_result("Tradier API (SPX quote)", False, str(e))
        all_checks_passed = False

    # =====================================================
    # SECTION 2: Configuration Check
    # =====================================================
    print_section("2. IC CONFIGURATION")

    try:
        db = JubileeDatabase(bot_name="PROMETHEUS_IC")
        config = db.load_ic_config()

        if config:
            check_result("IC Config loaded", True)
            print(f"       enabled: {config.enabled}")
            print(f"       mode: {config.mode.value}")
            print(f"       ticker: {config.ticker}")
            print(f"       max_positions: {config.max_positions}")
            print(f"       max_trades_per_day: {config.max_trades_per_day} (0=unlimited)")
            print(f"       entry_start: {config.entry_start}")
            print(f"       entry_end: {config.entry_end}")
            print(f"       require_oracle_approval: {config.require_oracle_approval}")
            print(f"       min_oracle_confidence: {config.min_oracle_confidence}")
            print(f"       min_win_probability: {config.min_win_probability}")
            print(f"       min_vix: {config.min_vix}")
            print(f"       max_vix: {config.max_vix}")

            if not config.enabled:
                check_result("IC Trading Enabled", False, "IC trading is DISABLED in config!")
                all_checks_passed = False
            else:
                check_result("IC Trading Enabled", True)
        else:
            check_result("IC Config loaded", False, "Config is None - using defaults")
            config = PrometheusICConfig()
    except Exception as e:
        check_result("IC Config loaded", False, str(e))
        config = PrometheusICConfig()

    # =====================================================
    # SECTION 3: Trading Window Check
    # =====================================================
    print_section("3. TRADING WINDOW")

    # Check if weekend
    is_weekend = now.weekday() >= 5
    check_result("Not weekend", not is_weekend,
                 f"Today is {now.strftime('%A')}" + (" - MARKET CLOSED!" if is_weekend else ""))
    if is_weekend:
        all_checks_passed = False

    # Check trading hours
    try:
        current_time = now.time()
        start = datetime.strptime(config.entry_start, '%H:%M').time()
        end = datetime.strptime(config.entry_end, '%H:%M').time()

        in_window = start <= current_time <= end
        check_result("Within trading window", in_window,
                     f"Current: {current_time.strftime('%H:%M')}, Window: {config.entry_start}-{config.entry_end} CT")
        if not in_window:
            all_checks_passed = False
    except Exception as e:
        check_result("Trading window check", False, str(e))
        all_checks_passed = False

    # =====================================================
    # SECTION 4: Box Spread Position Check
    # =====================================================
    print_section("4. BOX SPREAD POSITIONS (Capital Source)")

    try:
        box_positions = db.get_open_positions()
        if box_positions:
            check_result("Box spread positions exist", True, f"Found {len(box_positions)} open box position(s)")
            for pos in box_positions:
                print(f"       - {pos.position_id}: ${pos.total_cash_deployed:,.0f} deployed, DTE={pos.current_dte}")
        else:
            check_result("Box spread positions exist", False,
                        "No box positions! PAPER mode should auto-create one.")
            print("       In PAPER mode, a synthetic box spread should be auto-created.")
            print("       Check if mode=PAPER in config.")
            all_checks_passed = False
    except Exception as e:
        check_result("Box spread check", False, str(e))
        all_checks_passed = False

    # =====================================================
    # SECTION 5: Open IC Positions Check
    # =====================================================
    print_section("5. IC POSITIONS")

    try:
        ic_positions = db.get_open_ic_positions()
        check_result(f"IC positions check", True, f"Found {len(ic_positions)} open IC position(s)")

        if len(ic_positions) >= config.max_positions:
            check_result("Below max positions", False,
                        f"At max! {len(ic_positions)}/{config.max_positions}")
            all_checks_passed = False
        else:
            check_result("Below max positions", True,
                        f"{len(ic_positions)}/{config.max_positions}")

        for pos in ic_positions:
            pnl_color = "\033[92m" if pos.unrealized_pnl >= 0 else "\033[91m"
            reset = "\033[0m"
            print(f"       - {pos.position_id}: {pnl_color}${pos.unrealized_pnl:+,.2f}{reset} "
                  f"({pos.put_short_strike}/{pos.call_short_strike}), DTE={pos.current_dte}")
    except Exception as e:
        check_result("IC positions check", False, str(e))

    # =====================================================
    # SECTION 6: Daily Trade Limit
    # =====================================================
    print_section("6. DAILY TRADE LIMIT")

    try:
        daily_count = db.get_daily_ic_trades_count()
        max_daily = config.max_trades_per_day

        if max_daily == 0:
            check_result("Daily trade limit", True, f"Unlimited (0 = no limit), {daily_count} trades today")
        elif daily_count >= max_daily:
            check_result("Daily trade limit", False, f"LIMIT REACHED: {daily_count}/{max_daily}")
            all_checks_passed = False
        else:
            check_result("Daily trade limit", True, f"{daily_count}/{max_daily}")
    except Exception as e:
        check_result("Daily trade limit check", False, str(e))

    # =====================================================
    # SECTION 7: Cooldown Check
    # =====================================================
    print_section("7. COOLDOWN PERIOD")

    try:
        last_trade_time = db.get_last_ic_trade_time()
        if last_trade_time:
            # Get last result for win/loss specific cooldown
            last_result = db.get_last_ic_trade_result()
            if last_result and last_result.get('close_time'):
                if last_result.get('was_winner'):
                    cooldown_mins = config.cooldown_after_win_minutes
                    cooldown_type = "post-WIN"
                else:
                    cooldown_mins = config.cooldown_after_loss_minutes
                    cooldown_type = "post-LOSS"
            else:
                cooldown_mins = config.cooldown_minutes_after_trade
                cooldown_type = "generic"

            # Make timezone-aware comparison
            if last_trade_time.tzinfo is None:
                last_trade_time = last_trade_time.replace(tzinfo=CENTRAL_TZ)

            cooldown_end = last_trade_time + timedelta(minutes=cooldown_mins)

            if now < cooldown_end:
                remaining = (cooldown_end - now).total_seconds() / 60
                check_result("Cooldown period", False,
                            f"In {cooldown_type} cooldown! {remaining:.0f} min remaining "
                            f"(last: {last_trade_time.strftime('%H:%M')}, cooldown: {cooldown_mins}min)")
                all_checks_passed = False
            else:
                check_result("Cooldown period", True,
                            f"Cooldown complete (last: {last_trade_time.strftime('%H:%M')}, {cooldown_type}: {cooldown_mins}min)")
        else:
            check_result("Cooldown period", True, "No previous trades - no cooldown")
    except Exception as e:
        check_result("Cooldown check", False, str(e))

    # =====================================================
    # SECTION 8: Prophet Check
    # =====================================================
    print_section("8. PROPHET APPROVAL")

    if not config.require_oracle_approval:
        check_result("Prophet approval", True, "Not required (require_oracle_approval=False)")
    else:
        try:
            from quant.prophet_advisor import ProphetAdvisor, MarketContext, GEXRegime

            prophet = ProphetAdvisor()
            check_result("Prophet initialized", True)

            # Get market data for Prophet
            try:
                from data.tradier_data_fetcher import TradierClient
                tradier = TradierClient(sandbox=False)
                quote = tradier.get_quote("SPX")
                vix_quote = tradier.get_quote("VIX")

                spot = quote.get('last', 0)
                vix = vix_quote.get('last', 20.0) if vix_quote else 20.0

                context = MarketContext(
                    spot_price=spot,
                    vix=vix,
                    gex_call_wall=0,
                    gex_put_wall=0,
                    gex_regime=GEXRegime.NEUTRAL,
                    gex_flip_point=0,
                    gex_net=0,
                    expected_move_pct=0,
                )

                # Get Prophet advice
                prediction = prophet.get_anchor_advice(
                    context=context,
                    use_gex_walls=True,
                    use_claude_validation=False,
                    spread_width=25,
                )

                if prediction:
                    advice = prediction.advice.value if prediction.advice else 'UNKNOWN'
                    confidence = prediction.confidence
                    win_prob = prediction.win_probability

                    oracle_approved = advice in ('TRADE_FULL', 'TRADE_REDUCED', 'ENTER')

                    print(f"       Prophet Advice: {advice}")
                    print(f"       Confidence: {confidence:.0%}")
                    print(f"       Win Probability: {win_prob:.0%}")
                    print(f"       Reasoning: {prediction.reasoning[:100] if prediction.reasoning else 'N/A'}...")

                    if not oracle_approved:
                        check_result("Prophet says TRADE", False, f"Prophet says {advice}")
                        all_checks_passed = False
                    else:
                        check_result("Prophet says TRADE", True, f"Prophet says {advice}")

                    if confidence < config.min_oracle_confidence:
                        check_result("Prophet confidence", False,
                                    f"{confidence:.0%} < min {config.min_oracle_confidence:.0%}")
                        all_checks_passed = False
                    else:
                        check_result("Prophet confidence", True,
                                    f"{confidence:.0%} >= min {config.min_oracle_confidence:.0%}")

                    if win_prob < config.min_win_probability:
                        check_result("Win probability", False,
                                    f"{win_prob:.0%} < min {config.min_win_probability:.0%}")
                        all_checks_passed = False
                    else:
                        check_result("Win probability", True,
                                    f"{win_prob:.0%} >= min {config.min_win_probability:.0%}")
                else:
                    check_result("Prophet prediction", False, "No prediction returned")
                    all_checks_passed = False

            except Exception as e:
                check_result("Prophet market data", False, str(e))
                all_checks_passed = False

        except ImportError as e:
            check_result("Prophet module", False, str(e))
            all_checks_passed = False
        except Exception as e:
            check_result("Prophet check", False, str(e))
            all_checks_passed = False

    # =====================================================
    # SECTION 9: VIX Filter
    # =====================================================
    print_section("9. VIX FILTER")

    try:
        from data.tradier_data_fetcher import TradierClient
        tradier = TradierClient(sandbox=False)
        vix_quote = tradier.get_quote("VIX")

        if vix_quote:
            vix = vix_quote.get('last', 0)
            print(f"       Current VIX: {vix:.2f}")
            print(f"       Acceptable range: {config.min_vix} - {config.max_vix}")

            if vix < config.min_vix:
                check_result("VIX within range", False, f"VIX {vix:.1f} < min {config.min_vix} (premiums too thin)")
                all_checks_passed = False
            elif vix > config.max_vix:
                check_result("VIX within range", False, f"VIX {vix:.1f} > max {config.max_vix} (too risky)")
                all_checks_passed = False
            else:
                check_result("VIX within range", True, f"VIX {vix:.1f} is acceptable")
        else:
            check_result("VIX quote", False, "Could not get VIX quote")
    except Exception as e:
        check_result("VIX check", False, str(e))

    # =====================================================
    # SECTION 10: Recent Signals
    # =====================================================
    print_section("10. RECENT IC SIGNALS (Scan Activity)")

    try:
        # Get recent signals from jubilee_ic_signals table
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT signal_id, signal_time, is_valid, skip_reason, oracle_confidence
            FROM jubilee_ic_signals
            ORDER BY signal_time DESC
            LIMIT 5
        """)
        signals = cur.fetchall()
        cur.close()
        conn.close()

        if signals:
            print("       Last 5 signals:")
            for sig in signals:
                sig_id, sig_time, is_valid, skip_reason, oracle_conf = sig
                status = "VALID" if is_valid else "SKIPPED"
                reason = f" - {skip_reason}" if skip_reason else ""
                conf = f" (Prophet: {oracle_conf:.0%})" if oracle_conf else ""
                print(f"       - {sig_time.strftime('%Y-%m-%d %H:%M')}: {status}{reason}{conf}")
        else:
            print("       No recent signals found")
    except Exception as e:
        print(f"       Error fetching signals: {e}")

    # =====================================================
    # SECTION 11: Recent Closed Trades
    # =====================================================
    print_section("11. RECENT CLOSED IC TRADES")

    try:
        trades = db.get_ic_closed_trades(limit=5)
        if trades:
            print("       Last 5 closed trades:")
            for trade in trades:
                close_time = trade.get('close_time', 'N/A')
                pnl = trade.get('realized_pnl', 0)
                reason = trade.get('close_reason', 'N/A')
                pnl_color = "\033[92m" if pnl >= 0 else "\033[91m"
                reset = "\033[0m"
                print(f"       - {close_time}: {pnl_color}${pnl:+,.2f}{reset} ({reason})")
        else:
            print("       No closed trades found")
    except Exception as e:
        print(f"       Error fetching trades: {e}")

    # =====================================================
    # SUMMARY
    # =====================================================
    print_section("DIAGNOSTIC SUMMARY")

    if all_checks_passed:
        print("\033[92m")
        print("  ALL CHECKS PASSED!")
        print("  JUBILEE should be able to trade.")
        print("  If it's still not trading, check scheduler logs.")
        print("\033[0m")
    else:
        print("\033[91m")
        print("  SOME CHECKS FAILED!")
        print("  Review the [FAIL] items above to understand why")
        print("  JUBILEE is not opening positions.")
        print("\033[0m")

    print("\nFor more details, check these logs:")
    print("  - Render dashboard: alphagex-trader worker logs")
    print("  - Or run: heroku logs --app alphagex-api --tail")
    print("")

if __name__ == "__main__":
    main()
