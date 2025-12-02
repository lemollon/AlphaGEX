"""
Automated Data Collection Scheduler
Runs all data collectors periodically during market hours

Schedule:
- GEX History: Every 15 minutes during market hours
- Liberation Outcomes: Every 30 minutes during market hours
- Forward Magnets: Every 15 minutes during market hours
- Gamma Expiration Timeline: Every hour during market hours
- Daily Performance: Once at market close (4:00 PM ET)

Market Hours: 9:30 AM - 4:00 PM ET (Mon-Fri)
"""

import schedule
import time
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo
import sys

# Timezone
ET = ZoneInfo("America/New_York")
CENTRAL_TZ = ZoneInfo("America/Chicago")


def is_market_hours() -> bool:
    """Check if current time is during market hours (9:30 AM - 4:00 PM ET, Mon-Fri)"""
    now = datetime.now(ET)

    # Check if weekday (0=Monday, 4=Friday)
    if now.weekday() > 4:  # Saturday=5, Sunday=6
        return False

    # Market hours: 9:30 AM - 4:00 PM ET
    market_open = dt_time(9, 30)
    market_close = dt_time(16, 0)
    current_time = now.time()

    return market_open <= current_time <= market_close


def is_after_market_close() -> bool:
    """Check if it's after market close (for end-of-day jobs)"""
    now = datetime.now(ET)

    if now.weekday() > 4:  # Weekend
        return False

    # Run daily jobs between 4:00 PM - 4:30 PM ET
    after_close = dt_time(16, 0)
    end_window = dt_time(16, 30)
    current_time = now.time()

    return after_close <= current_time <= end_window


def run_gex_history():
    """Run GEX history snapshot"""
    if not is_market_hours():
        print(f"⏸️  Skipping GEX History - Market closed")
        return

    print(f"\n{'='*70}")
    print(f"📊 Running GEX History Snapshot - {datetime.now(CENTRAL_TZ).strftime('%H:%M:%S')}")
    print(f"{'='*70}")

    try:
        from gamma.gex_history_snapshot_job import save_gex_snapshot
        save_gex_snapshot('SPY')
        print(f"✅ GEX History completed successfully")
    except Exception as e:
        print(f"❌ GEX History failed: {e}")


def run_liberation_outcomes():
    """Run liberation outcomes tracker"""
    if not is_market_hours():
        print(f"⏸️  Skipping Liberation Outcomes - Market closed")
        return

    print(f"\n{'='*70}")
    print(f"🎯 Running Liberation Outcomes - {datetime.now(CENTRAL_TZ).strftime('%H:%M:%S')}")
    print(f"{'='*70}")

    try:
        from gamma.liberation_outcomes_tracker import check_liberation_outcomes
        check_liberation_outcomes()
        print(f"✅ Liberation Outcomes completed successfully")
    except Exception as e:
        print(f"❌ Liberation Outcomes failed: {e}")


def run_forward_magnets():
    """Run forward magnets detector"""
    if not is_market_hours():
        print(f"⏸️  Skipping Forward Magnets - Market closed")
        return

    print(f"\n{'='*70}")
    print(f"🧲 Running Forward Magnets - {datetime.now(CENTRAL_TZ).strftime('%H:%M:%S')}")
    print(f"{'='*70}")

    try:
        from gamma.forward_magnets_detector import detect_forward_magnets
        detect_forward_magnets()
        print(f"✅ Forward Magnets completed successfully")
    except Exception as e:
        print(f"❌ Forward Magnets failed: {e}")


def run_gamma_expiration():
    """Run gamma expiration timeline"""
    if not is_market_hours():
        print(f"⏸️  Skipping Gamma Expiration - Market closed")
        return

    print(f"\n{'='*70}")
    print(f"📅 Running Gamma Expiration Timeline - {datetime.now(CENTRAL_TZ).strftime('%H:%M:%S')}")
    print(f"{'='*70}")

    try:
        from gamma.gamma_expiration_timeline import track_gamma_expiration_timeline
        track_gamma_expiration_timeline()
        print(f"✅ Gamma Expiration completed successfully")
    except Exception as e:
        print(f"❌ Gamma Expiration failed: {e}")


def run_daily_performance():
    """Run daily performance aggregator (end of day only)"""
    if not is_after_market_close():
        print(f"⏸️  Skipping Daily Performance - Not after market close")
        return

    print(f"\n{'='*70}")
    print(f"📈 Running Daily Performance - {datetime.now(CENTRAL_TZ).strftime('%H:%M:%S')}")
    print(f"{'='*70}")

    try:
        from daily_performance_aggregator import aggregate_daily_performance
        aggregate_daily_performance()
        print(f"✅ Daily Performance completed successfully")
    except Exception as e:
        print(f"❌ Daily Performance failed: {e}")


def run_option_chain_collection():
    """
    Run option chain snapshot collection.

    Collects real option chain data for future backtesting with REAL prices.
    Stores bid/ask/greeks for strikes within 10% of spot, up to 60 DTE.
    """
    if not is_market_hours():
        print(f"⏸️  Skipping Option Chain Collection - Market closed")
        return

    print(f"\n{'='*70}")
    print(f"📋 Running Option Chain Collection - {datetime.now(CENTRAL_TZ).strftime('%H:%M:%S')}")
    print(f"{'='*70}")

    try:
        from data.option_chain_collector import collect_all_symbols
        results = collect_all_symbols()

        total_contracts = sum(r.get('contracts', 0) for r in results)
        successful = sum(1 for r in results if r.get('status') == 'SUCCESS')

        print(f"✅ Option Chain Collection completed: {total_contracts} contracts across {successful} symbols")
    except Exception as e:
        print(f"❌ Option Chain Collection failed: {e}")


def setup_schedule():
    """Set up the collection schedule"""

    # GEX History: Every 5 minutes (increased from 15)
    schedule.every(5).minutes.do(run_gex_history)

    # Liberation Outcomes: Every 10 minutes (increased from 30)
    schedule.every(10).minutes.do(run_liberation_outcomes)

    # Forward Magnets: Every 5 minutes (increased from 15)
    schedule.every(5).minutes.do(run_forward_magnets)

    # Gamma Expiration: Every 30 minutes (increased from 60)
    schedule.every(30).minutes.do(run_gamma_expiration)

    # Option Chain Collection: Every 15 minutes for backtesting data
    schedule.every(15).minutes.do(run_option_chain_collection)

    # Daily Performance: Every 5 minutes (will only run after market close)
    schedule.every(5).minutes.do(run_daily_performance)

    print("="*70)
    print("🚀 ALPHAGEX AUTOMATED DATA COLLECTION")
    print("="*70)
    print("\n📅 Schedule Configuration (INCREASED FREQUENCY):")
    print("  • GEX History: Every 5 minutes (market hours) 📊")
    print("  • Liberation Outcomes: Every 10 minutes (market hours) 🎯")
    print("  • Forward Magnets: Every 5 minutes (market hours) 🧲")
    print("  • Gamma Expiration: Every 30 minutes (market hours) 📅")
    print("  • Option Chain Snapshots: Every 15 minutes (market hours) 📋")
    print("  • Daily Performance: Once at 4:00 PM ET (after close) 📈")
    print("\n⏰ Market Hours: 9:30 AM - 4:00 PM ET (Mon-Fri)")
    print("💡 Option chain data collected for REAL backtesting")
    print("\n✅ Scheduler started. Press Ctrl+C to stop.\n")
    print("="*70)


def run_scheduler():
    """Main scheduler loop"""
    setup_schedule()

    # Run initial collection immediately if market is open
    if is_market_hours():
        print("\n🔥 Market is open! Running initial data collection...\n")
        run_gex_history()
        run_liberation_outcomes()
        run_forward_magnets()
        run_gamma_expiration()
        run_option_chain_collection()
    else:
        print("\n⏸️  Market is closed. Waiting for market open...\n")

    # Main loop
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute

    except KeyboardInterrupt:
        print("\n\n⚠️  Scheduler stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    run_scheduler()
