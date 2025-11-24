"""
Autonomous Trader Scheduler - Continuous Market Hours Operation
Runs AUTOMATICALLY during stock market hours: 8:30 AM - 3:00 PM Central Texas Time (Mon-Fri)
Checks every 5 minutes for trading opportunities
Auto-restarts on errors, guaranteed minimum 1 trade per day
"""

import time
import sys
import traceback
from datetime import datetime, time as dt_time, timedelta
from zoneinfo import ZoneInfo
from autonomous_paper_trader import AutonomousPaperTrader
from core_classes_and_engines import TradingVolatilityAPI

# Market hours in Central Time (Texas)
MARKET_OPEN_CT = dt_time(8, 30)   # 8:30 AM CT = 9:30 AM ET
MARKET_CLOSE_CT = dt_time(15, 0)  # 3:00 PM CT = 4:00 PM ET
CHECK_INTERVAL_SECONDS = 300      # 5 minutes


def get_central_time() -> datetime:
    """Get current time in Central Texas timezone"""
    try:
        return datetime.now(ZoneInfo("America/Chicago"))
    except Exception:
        # Fallback to UTC-6 (CST) if zoneinfo fails
        from datetime import timezone
        return datetime.now(timezone(timedelta(hours=-6)))


def is_market_hours() -> bool:
    """
    Check if it's currently market hours in Central Texas time
    Market Hours: 8:30 AM - 3:00 PM CT, Monday-Friday

    Returns:
        bool: True if market is open, False otherwise
    """
    ct_now = get_central_time()

    # Weekend check (0=Monday, 6=Sunday)
    if ct_now.weekday() >= 5:  # Saturday (5) or Sunday (6)
        return False

    # Time check
    current_time = ct_now.time()
    return MARKET_OPEN_CT <= current_time <= MARKET_CLOSE_CT


def time_until_market_open() -> int:
    """
    Calculate seconds until market opens

    Returns:
        int: Seconds until market opens (0 if market is open)
    """
    ct_now = get_central_time()

    # If market is currently open, return 0
    if is_market_hours():
        return 0

    # Calculate next market open
    current_date = ct_now.date()
    current_weekday = ct_now.weekday()

    # If it's after market close today, target tomorrow
    if ct_now.time() > MARKET_CLOSE_CT:
        days_ahead = 1
    else:
        days_ahead = 0

    # If weekend, skip to Monday
    if current_weekday == 5:  # Saturday
        days_ahead = 2
    elif current_weekday == 6:  # Sunday
        days_ahead = 1

    next_open_date = current_date + timedelta(days=days_ahead)
    next_open_time = datetime.combine(
        next_open_date,
        MARKET_OPEN_CT,
        tzinfo=ZoneInfo("America/Chicago")
    )

    seconds = int((next_open_time - ct_now).total_seconds())
    return max(0, seconds)


def format_time_until(seconds: int) -> str:
    """Format seconds as human-readable time"""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds//60}m"
    elif seconds < 86400:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"
    else:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        return f"{days}d {hours}h"


def run_autonomous_trader_cycle():
    """
    Run one full cycle of the autonomous trader

    What it does:
    - Checks for new trade opportunities during market hours (8:30 AM - 3:00 PM CT)
    - Executes MINIMUM ONE trade per day GUARANTEED (multi-level fallback system)
    - Manages existing positions continuously
    - Updates live status for UI monitoring

    GUARANTEE: Multi-level fallback ensures at least one trade executes daily:
    1. Directional GEX trade (preferred)
    2. Iron Condor fallback (if no directional setup)
    3. ATM Straddle final fallback (if Iron Condor fails)
    """

    ct_now = get_central_time()
    print(f"\n{'='*60}")
    print(f"AUTONOMOUS TRADER CYCLE - {ct_now.strftime('%Y-%m-%d %I:%M:%S %p CT')}")
    print(f"{'='*60}\n")

    # Initialize with comprehensive error handling
    try:
        trader = AutonomousPaperTrader()
        print(f"✅ Trader initialized successfully")
        print(f"   Database: PostgreSQL via DATABASE_URL")

        # CRITICAL: Update heartbeat immediately so UI knows worker is alive
        trader.update_live_status(
            status='RUNNING',
            action='Worker is alive and checking market conditions',
            analysis=f'System healthy. Current time: {ct_now.strftime("%I:%M %p CT")}'
        )
    except Exception as e:
        print(f"❌ FATAL: Failed to initialize trader: {e}")
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

    # Step 1: Check for new trade opportunity (ONLY during market hours)
    if is_market_hours():
        print("🔍 MARKET HOURS - Checking for new trade opportunity...")

        # Log the check cycle start
        trader.log_action(
            'CHECK_START',
            f'Starting trade search cycle at {ct_now.strftime("%I:%M:%S %p CT")}. '
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
            traceback.print_exc()

    else:
        print(f"ℹ️ Market closed - skipping new trade search")
        trader.log_action(
            'CHECK_SKIPPED',
            f'Market is currently closed. Next check will occur during market hours (8:30 AM - 3:00 PM CT). '
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
    Run the autonomous trader continuously during market hours
    Automatically waits until market opens, then checks at specified interval

    Args:
        check_interval_minutes: How often to check for trades (default: 5 minutes)

    This is the MAIN mode for production deployment.
    """

    check_interval_seconds = check_interval_minutes * 60

    print("=" * 70)
    print("🤖 AUTONOMOUS TRADER - CONTINUOUS MODE")
    print("=" * 70)
    print(f"⏰ Runs AUTOMATICALLY during market hours: 8:30 AM - 3:00 PM CT")
    print(f"📅 Active days: Monday - Friday")
    print(f"🔄 Check interval: Every {check_interval_minutes} minutes")
    print(f"✅ GUARANTEE: MINIMUM ONE trade per day (multi-level fallback)")
    print(f"🛡️ Auto-restarts on errors")
    print("=" * 70)
    print()

    cycle_count = 0

    while True:
        try:
            ct_now = get_central_time()

            # Check if market is open
            if is_market_hours():
                cycle_count += 1
                print(f"\n🟢 MARKET OPEN - Running cycle #{cycle_count}")

                # Run trading cycle
                run_autonomous_trader_cycle()

                # Wait specified interval before next check
                print(f"⏳ Waiting {check_interval_minutes} minutes until next cycle...")
                print(f"   Next check at: {(ct_now + timedelta(seconds=check_interval_seconds)).strftime('%I:%M %p CT')}")
                time.sleep(check_interval_seconds)

            else:
                # Market is closed - calculate wait time
                seconds_until_open = time_until_market_open()

                if seconds_until_open > 0:
                    next_open = ct_now + timedelta(seconds=seconds_until_open)
                    print(f"\n🔴 MARKET CLOSED")
                    print(f"   Current time: {ct_now.strftime('%I:%M %p CT, %A %B %d')}")
                    print(f"   Next market open: {next_open.strftime('%I:%M %p CT, %A %B %d')}")
                    print(f"   Waiting: {format_time_until(seconds_until_open)}")

                    # Sleep until just before market opens
                    # Wake up 1 minute before to ensure we're ready
                    sleep_seconds = max(60, seconds_until_open - 60)
                    time.sleep(sleep_seconds)
                else:
                    # Edge case - should never happen
                    time.sleep(60)

        except KeyboardInterrupt:
            print("\n🛑 Scheduler stopped by user (Ctrl+C)")
            print("   To restart: python autonomous_scheduler.py")
            break

        except Exception as e:
            print(f"\n❌ CRITICAL ERROR in scheduler: {e}")
            traceback.print_exc()

            # Wait 5 minutes before retrying
            print("⏳ Auto-restart in 5 minutes...")
            time.sleep(300)


# For Render.com or other cron-based deployments
def render_scheduled_task():
    """
    Single execution for cron-based scheduling (Render, Heroku, etc.)

    Add to your Render.com cron job:
    Schedule: "*/5 8-15 * * 1-5"  (Every 5 min, 8:30 AM - 3:00 PM CT, Mon-Fri)
    Command: python autonomous_scheduler.py --mode render
    """
    run_autonomous_trader_cycle()


if __name__ == "__main__":
    """
    Run this script directly for standalone operation

    Modes:
    - continuous (default): Runs forever, auto-starts/stops with market hours
    - once: Single cycle then exit
    - render: Single cycle for cron jobs
    """

    import argparse

    parser = argparse.ArgumentParser(
        description='Autonomous Trader Scheduler - Runs during market hours (8:30 AM - 3:00 PM CT)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python autonomous_scheduler.py                    # Continuous mode (runs forever)
  python autonomous_scheduler.py --mode once        # Single test run
  python autonomous_scheduler.py --mode render      # For cron jobs

Production deployment:
  sudo ./deploy_autonomous_trader.sh                # Sets up systemd service
        """
    )

    parser.add_argument(
        '--mode',
        choices=['continuous', 'once', 'render'],
        default='continuous',
        help='Execution mode (default: continuous)'
    )

    args = parser.parse_args()

    if args.mode == 'once':
        print("Running single cycle...\n")
        run_autonomous_trader_cycle()

    elif args.mode == 'continuous':
        run_continuous_scheduler()

    elif args.mode == 'render':
        print("Running Render.com scheduled task...\n")
        render_scheduled_task()
