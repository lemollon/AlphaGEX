"""
Master Data Collection Runner
Runs all data collection jobs to populate empty tables

Jobs included:
1. GEX History Snapshot - Historical gamma exposure
2. Liberation Outcomes - Validate psychology trap predictions
3. Forward Magnets - Detect gamma price magnets
4. Gamma Expiration Timeline - Track gamma decay patterns
5. Daily Performance - Calculate Sharpe ratio and metrics
"""

from datetime import datetime
from zoneinfo import ZoneInfo
import sys

CENTRAL_TZ = ZoneInfo("America/Chicago")


def run_all_collectors():
    """Run all data collection jobs"""

    print("="*70)
    print("🚀 ALPHAGEX DATA COLLECTION SUITE")
    print("="*70)
    print(f"Started: {datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d %H:%M:%S %Z')}\n")

    results = {
        'successful': [],
        'failed': []
    }

    # Job 1: GEX History Snapshot
    print("\n" + "="*70)
    print("📊 JOB 1/5: GEX History Snapshot")
    print("="*70)
    try:
        from gamma.gex_history_snapshot_job import save_gex_snapshot
        save_gex_snapshot('SPY')
        results['successful'].append('GEX History')
    except Exception as e:
        print(f"❌ Failed: {e}")
        results['failed'].append(('GEX History', str(e)))

    # Job 2: Liberation Outcomes
    print("\n" + "="*70)
    print("🎯 JOB 2/5: Liberation Outcomes Tracker")
    print("="*70)
    try:
        from gamma.liberation_outcomes_tracker import check_liberation_outcomes
        check_liberation_outcomes()
        results['successful'].append('Liberation Outcomes')
    except Exception as e:
        print(f"❌ Failed: {e}")
        results['failed'].append(('Liberation Outcomes', str(e)))

    # Job 3: Forward Magnets
    print("\n" + "="*70)
    print("🧲 JOB 3/5: Forward Magnets Detector")
    print("="*70)
    try:
        from gamma.forward_magnets_detector import detect_forward_magnets
        detect_forward_magnets()
        results['successful'].append('Forward Magnets')
    except Exception as e:
        print(f"❌ Failed: {e}")
        results['failed'].append(('Forward Magnets', str(e)))

    # Job 4: Gamma Expiration Timeline
    print("\n" + "="*70)
    print("📅 JOB 4/5: Gamma Expiration Timeline")
    print("="*70)
    try:
        from gamma.gamma_expiration_timeline import track_gamma_expiration_timeline
        track_gamma_expiration_timeline()
        results['successful'].append('Gamma Expiration Timeline')
    except Exception as e:
        print(f"❌ Failed: {e}")
        results['failed'].append(('Gamma Expiration Timeline', str(e)))

    # Job 5: Daily Performance
    print("\n" + "="*70)
    print("📈 JOB 5/5: Daily Performance Aggregator")
    print("="*70)
    try:
        from monitoring.daily_performance_aggregator import aggregate_daily_performance
        aggregate_daily_performance()
        results['successful'].append('Daily Performance')
    except Exception as e:
        print(f"❌ Failed: {e}")
        results['failed'].append(('Daily Performance', str(e)))

    # Final Summary
    print("\n" + "="*70)
    print("📋 DATA COLLECTION SUMMARY")
    print("="*70)

    print(f"\n✅ Successful ({len(results['successful'])}):")
    for job in results['successful']:
        print(f"   • {job}")

    if results['failed']:
        print(f"\n❌ Failed ({len(results['failed'])}):")
        for job, error in results['failed']:
            print(f"   • {job}: {error[:60]}")

    success_rate = len(results['successful']) / (len(results['successful']) + len(results['failed'])) * 100
    print(f"\nSuccess Rate: {success_rate:.0f}%")

    print(f"\nCompleted: {datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print("="*70)

    # Return exit code
    return 0 if not results['failed'] else 1


if __name__ == '__main__':
    try:
        exit_code = run_all_collectors()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️ Data collection interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
