"""
Autonomous Trader Scheduler
Runs the autonomous trader automatically on a schedule
Perfect for Render deployment or background tasks
"""

import time
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo
from autonomous_paper_trader import AutonomousPaperTrader
from core_classes_and_engines import TradingVolatilityAPI


def is_market_hours() -> bool:
    """
    Check if it's market hours (9:30 AM - 4:00 PM ET, Mon-Fri)
    Market times in different US zones:
    - Eastern (ET): 9:30 AM - 4:00 PM
    - Central (CT): 8:30 AM - 3:00 PM  (Texas time)
    - Mountain (MT): 7:30 AM - 2:00 PM
    - Pacific (PT): 6:30 AM - 1:00 PM
    """
    # Get current time in Eastern Time (where market operates)
    try:
        et_now = datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        # Fallback to UTC-5 if zoneinfo fails
        from datetime import timezone, timedelta
        et_now = datetime.now(timezone(timedelta(hours=-5)))

    # Weekend check
    if et_now.weekday() >= 5:  # Saturday or Sunday
        return False

    # Time check (9:30 AM - 4:00 PM ET)
    market_open_time = dt_time(9, 30)
    market_close_time = dt_time(16, 0)
    current_time = et_now.time()

    return market_open_time <= current_time <= market_close_time


def run_autonomous_trader_cycle():
    """
    Run one full cycle of the autonomous trader

    What it does:
    - Checks for new trade opportunities ALL DAY during market hours (9:30 AM - 4:00 PM ET)
    - Executes MINIMUM ONE trade per day GUARANTEED (multi-level fallback system)
    - Manages existing positions continuously
    - Updates live status for UI monitoring

    GUARANTEE: Multi-level fallback ensures at least one trade executes daily:
    1. Directional GEX trade (preferred)
    2. Iron Condor fallback (if no directional setup)
    3. ATM Straddle final fallback (if Iron Condor fails)

    This should be called:
    - Every 5 minutes during market hours (recommended)
    - OR triggered by Render's cron schedule
    - OR as a background task in Streamlit
    """

    print(f"\n{'='*60}")
    print(f"AUTONOMOUS TRADER CYCLE - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    # Initialize with comprehensive error handling
    try:
        trader = AutonomousPaperTrader()
        print(f"✅ Trader initialized successfully")
        print(f"   Database: {trader.db_path}")

        # CRITICAL: Update heartbeat immediately so UI knows worker is alive
        trader.update_live_status(
            status='RUNNING',
            action='Worker is alive and checking market conditions',
            analysis='System healthy, checking for trading opportunities'
        )
    except Exception as e:
        print(f"❌ FATAL: Failed to initialize trader: {e}")
        import traceback
        traceback.print_exc()
        return

    # Use shared API client - class-level rate limiting automatically applies
    try:
        api_client = TradingVolatilityAPI()
        print(f"✅ API client initialized")
    except Exception as e:
        print(f"❌ ERROR: Failed to initialize API client: {e}")
        trader.update_live_status(
            status='ERROR',
            action='Failed to initialize API client',
            analysis=str(e)
        )
        return

    # Step 1: Check for new trade opportunity (ALL DAY during market hours)
    # Note: find_and_execute_daily_trade() has built-in protection to only execute ONE trade per day
    if is_market_hours():
        print("🔍 MARKET HOURS - Checking for new trade opportunity...")

        # Log the check cycle start
        trader.log_action(
            'CHECK_START',
            f'Starting trade search cycle at {datetime.now().strftime("%I:%M:%S %p ET")}. '
            f'Market is open. Analyzing SPY GEX structure and looking for high-probability setups.',
            success=True
        )

        try:
            position_id = trader.find_and_execute_daily_trade(api_client)

            if position_id:
                print(f"✅ SUCCESS: Opened position #{position_id}")
                trader.log_action(
                    'TRADE_EXECUTED',
                    f'Successfully opened new position #{position_id}. Trade met confidence threshold. '
                    f'Position details logged separately.',
                    position_id=position_id,
                    success=True
                )
            else:
                print("ℹ️ INFO: No new trade (already traded today or no high-confidence setup)")
                # Log why no trade was made
                today = datetime.now().strftime('%Y-%m-%d')
                last_trade_date = trader.get_config('last_trade_date')

                if last_trade_date == today:
                    trader.log_action(
                        'CHECK_COMPLETE',
                        f'Already executed today\'s trade (last trade: {last_trade_date}). '
                        f'Daily trade limit reached. Bot will continue monitoring open positions.',
                        success=True
                    )
                else:
                    trader.log_action(
                        'CHECK_COMPLETE',
                        f'No trade executed this cycle. Either market conditions did not meet minimum '
                        f'confidence threshold (70%+) or waiting for better setup. Will check again in 5 minutes.',
                        success=True
                    )
        except Exception as e:
            print(f"❌ ERROR: Failed to find/execute trade: {e}")
            trader.log_action(
                'ERROR',
                f'Trade search encountered error: {str(e)[:200]}. Will retry on next cycle.',
                success=False
            )
            import traceback
            traceback.print_exc()

    else:
        print(f"ℹ️ Market closed - skipping new trade search")
        trader.log_action(
            'CHECK_SKIPPED',
            f'Market is currently closed. Next check will occur during market hours (9:30 AM - 4:00 PM ET). '
            f'Open positions are not actively managed outside market hours.',
            success=True
        )

    # Step 2: Always manage existing positions (during market hours)
    if is_market_hours():
        print("\n🔄 Checking open positions for exit conditions...")

        try:
            actions = trader.auto_manage_positions(api_client)

            if actions:
                print(f"✅ SUCCESS: Closed {len(actions)} position(s):")
                for action in actions:
                    print(f"   - {action['strategy']}: P&L ${action['pnl']:+,.2f} ({action['pnl_pct']:+.1f}%) - {action['reason']}")
            else:
                print("ℹ️ INFO: All positions look good - no exits needed")
        except Exception as e:
            print(f"❌ ERROR: Failed to manage positions: {e}")
            import traceback
            traceback.print_exc()

    else:
        print("ℹ️ Market closed - skipping position management")

    # Step 3: Display performance summary
    print("\n📊 PERFORMANCE SUMMARY:")
    perf = trader.get_performance()
    print(f"   Starting Capital: ${perf['starting_capital']:,.0f}")
    print(f"   Current Value: ${perf['current_value']:,.2f}")
    print(f"   Total P&L: ${perf['total_pnl']:+,.2f} ({perf['return_pct']:+.2f}%)")
    print(f"   Total Trades: {perf['total_trades']}")
    print(f"   Open Positions: {perf['open_positions']}")
    print(f"   Win Rate: {perf['win_rate']:.1f}%")

    print(f"\n{'='*60}")
    print(f"CYCLE COMPLETE")
    print(f"{'='*60}\n")


def run_continuous_scheduler(check_interval_minutes: int = 5):
    """
    Run the autonomous trader continuously

    Args:
        check_interval_minutes: How often to check (default: 5 minutes for maximum data freshness)

    Usage:
        # In a separate Python process or background task:
        run_continuous_scheduler(check_interval_minutes=5)

    Note:
        - Trading Volatility API limit: 20 calls/min
        - Per cycle: ~3-5 calls (GEX data + skew + positions)
        - Checking every 5 min = 12 cycles/hour = 36-60 calls/hour = ~0.6-1 call/min average
        - This is WELL within API limits and provides maximum responsiveness
    """

    print("🤖 AUTONOMOUS TRADER SCHEDULER STARTED")
    print(f"⏰ Check interval: {check_interval_minutes} minutes")
    print(f"📅 Checks ALL DAY during market hours (9:30 AM - 4:00 PM ET / 8:30 AM - 3:00 PM CT)")
    print(f"✅ GUARANTEE: MINIMUM ONE trade per day (multi-level fallback system)")
    print(f"📊 Manages positions continuously every {check_interval_minutes} minutes\n")

    while True:
        try:
            # Run a cycle
            run_autonomous_trader_cycle()

            # Wait for next cycle
            print(f"⏳ Waiting {check_interval_minutes} minutes until next cycle...\n")
            time.sleep(check_interval_minutes * 60)

        except KeyboardInterrupt:
            print("\n🛑 Scheduler stopped by user")
            break
        except Exception as e:
            print(f"❌ CRITICAL ERROR in scheduler: {e}")
            import traceback
            traceback.print_exc()

            # Wait a bit before retrying
            print("⏳ Waiting 5 minutes before retry...")
            time.sleep(300)


# For Render.com or other cloud deployments
def render_scheduled_task():
    """
    Single execution for cron-based scheduling (Render, Heroku, etc.)

    Add to your Render.com cron job:

    Schedule: "0 9-16 * * 1-5"  (Every hour, 9 AM - 4 PM ET, Mon-Fri)
    Command: python autonomous_scheduler.py
    """
    run_autonomous_trader_cycle()


# For Streamlit background task (experimental)
def streamlit_background_task():
    """
    Run as a Streamlit background task

    Add to your main app:

    import threading
    from autonomous_scheduler import streamlit_background_task

    # Start background thread
    if 'autonomous_thread_started' not in st.session_state:
        thread = threading.Thread(target=streamlit_background_task, daemon=True)
        thread.start()
        st.session_state.autonomous_thread_started = True
    """

    print("🤖 Streamlit background task started")

    while True:
        try:
            # Only run during market hours to save resources
            if is_market_hours():
                run_autonomous_trader_cycle()
                time.sleep(300)  # 5 minutes for maximum responsiveness
            else:
                # Outside market hours, check less frequently
                print("ℹ️ Market closed - sleeping for 30 minutes")
                time.sleep(1800)  # 30 minutes when market closed

        except Exception as e:
            print(f"❌ Error in background task: {e}")
            time.sleep(300)  # Wait 5 minutes on error


if __name__ == "__main__":
    """
    Run this script directly for standalone operation:

    python autonomous_scheduler.py
    """

    import argparse

    parser = argparse.ArgumentParser(description='Autonomous Paper Trader Scheduler')
    parser.add_argument(
        '--mode',
        choices=['once', 'continuous', 'render'],
        default='once',
        help='Execution mode: once (single run), continuous (loop), render (cron-friendly)'
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=5,
        help='Check interval in minutes (default: 5 for max data freshness within API limits)'
    )

    args = parser.parse_args()

    if args.mode == 'once':
        print("Running single cycle...")
        run_autonomous_trader_cycle()

    elif args.mode == 'continuous':
        print(f"Running continuous scheduler with {args.interval}-minute interval...")
        run_continuous_scheduler(check_interval_minutes=args.interval)

    elif args.mode == 'render':
        print("Running Render.com scheduled task...")
        render_scheduled_task()
