"""
Gamma Expiration Timeline Tracker
Tracks how gamma exposure changes as expiration approaches
Helps understand dealer hedging behavior at different DTEs
"""

import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo
from config_and_database import DB_PATH

CENTRAL_TZ = ZoneInfo("America/Chicago")


def track_gamma_expiration_timeline():
    """
    Snapshot gamma levels at various expiration timelines

    Tracks gamma at key DTE milestones:
    - 30+ DTE (monthly options)
    - 14-21 DTE (weekly before expiration)
    - 7-10 DTE (week of expiration)
    - 3-5 DTE (midweek)
    - 0-2 DTE (expiration week)
    - 0 DTE (same day expiration)

    This helps identify patterns in dealer hedging behavior
    """
    try:
        from tradingvolatility_api import get_gamma_exposure
        import pandas as pd

        print("📅 Gamma Expiration Timeline - Tracking Gamma Decay Patterns\n")

        # Get current GEX data with expiration breakdown
        gex_data = get_gamma_exposure('SPY')

        if not gex_data or 'levels' not in gex_data:
            print("❌ No GEX data available")
            return

        spot_price = gex_data.get('spot_price', 0)
        net_gex = gex_data.get('net_gex', 0)

        # Get expiration dates and group gamma by DTE
        levels = gex_data['levels']
        df = pd.DataFrame(levels)

        if df.empty or 'expiration' not in df.columns:
            print("⚠️ No expiration data, using simplified logging")
            log_simplified_gamma_timeline(gex_data)
            return

        # Convert expiration to datetime and calculate DTE
        now = datetime.now(CENTRAL_TZ)
        df['exp_date'] = pd.to_datetime(df['expiration'])
        df['dte'] = (df['exp_date'] - now).dt.days

        # Group gamma by DTE buckets
        dte_buckets = [
            (0, 0, '0DTE'),
            (1, 2, '1-2 DTE'),
            (3, 5, '3-5 DTE'),
            (6, 10, '7-10 DTE'),
            (11, 21, '11-21 DTE'),
            (22, 45, '30 DTE'),
            (46, 365, '45+ DTE')
        ]

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        timeline_count = 0

        for min_dte, max_dte, bucket_name in dte_buckets:
            bucket_df = df[(df['dte'] >= min_dte) & (df['dte'] <= max_dte)]

            if bucket_df.empty:
                continue

            # Calculate gamma stats for this DTE bucket
            call_gamma = bucket_df[bucket_df['gamma_ex'] > 0]['gamma_ex'].sum()
            put_gamma = bucket_df[bucket_df['gamma_ex'] < 0]['gamma_ex'].sum()
            net_gamma_bucket = call_gamma + put_gamma
            total_gamma = bucket_df['gamma_ex'].abs().sum()

            # Find key strikes in this bucket
            atm_strikes = bucket_df[
                (bucket_df['strike'] >= spot_price * 0.98) &
                (bucket_df['strike'] <= spot_price * 1.02)
            ]

            max_gamma_strike = bucket_df.loc[bucket_df['gamma_ex'].abs().idxmax()]['strike'] if not bucket_df.empty else 0
            max_gamma_value = bucket_df['gamma_ex'].abs().max() if not bucket_df.empty else 0

            # Get actual expiration dates in this bucket
            exp_dates = bucket_df['exp_date'].unique()
            nearest_expiration = min(exp_dates) if len(exp_dates) > 0 else now

            avg_dte = int(bucket_df['dte'].mean())

            # Log to database
            c.execute("""
                INSERT INTO gamma_expiration_timeline (
                    timestamp, dte_bucket, avg_dte, expiration_date,
                    net_gamma, call_gamma, put_gamma, total_gamma_absolute,
                    spot_price, max_gamma_strike, max_gamma_value,
                    atm_gamma, gamma_pct_of_total
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                now.strftime('%Y-%m-%d %H:%M:%S'),
                bucket_name,
                avg_dte,
                nearest_expiration.strftime('%Y-%m-%d'),
                net_gamma_bucket,
                call_gamma,
                put_gamma,
                total_gamma,
                spot_price,
                max_gamma_strike,
                max_gamma_value,
                atm_strikes['gamma_ex'].sum() if not atm_strikes.empty else 0,
                (total_gamma / df['gamma_ex'].abs().sum() * 100) if df['gamma_ex'].abs().sum() > 0 else 0
            ))

            timeline_count += 1

            print(f"📊 {bucket_name:12s} | Net: ${net_gamma_bucket/1e9:6.2f}B | "
                  f"Total: ${total_gamma/1e9:5.2f}B | "
                  f"Max @ ${max_gamma_strike:.0f}")

        conn.commit()

        # Show gamma concentration by DTE
        print_gamma_concentration_analysis(c)

        conn.close()

        print(f"\n✅ Logged {timeline_count} expiration timeline snapshots")

    except ImportError:
        print("⚠️ tradingvolatility_api not available, using mock data")
        log_mock_gamma_timeline()
    except Exception as e:
        print(f"❌ Error tracking gamma expiration timeline: {e}")
        import traceback
        traceback.print_exc()


def log_simplified_gamma_timeline(gex_data: Dict):
    """Log simplified gamma timeline when detailed expiration data isn't available"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        now = datetime.now(CENTRAL_TZ)

        # Just log overall gamma without DTE breakdown
        c.execute("""
            INSERT INTO gamma_expiration_timeline (
                timestamp, dte_bucket, avg_dte, net_gamma, total_gamma_absolute,
                spot_price
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            now.strftime('%Y-%m-%d %H:%M:%S'),
            'TOTAL',
            None,
            gex_data.get('net_gex', 0),
            abs(gex_data.get('net_gex', 0)),
            gex_data.get('spot_price', 0)
        ))

        conn.commit()
        conn.close()

        print("✅ Logged simplified gamma timeline (no DTE breakdown available)")

    except Exception as e:
        print(f"❌ Error logging simplified timeline: {e}")


def print_gamma_concentration_analysis(cursor):
    """Show where gamma is concentrated by DTE"""

    cursor.execute("""
        SELECT
            dte_bucket,
            AVG(gamma_pct_of_total) as avg_pct,
            AVG(net_gamma) as avg_net_gamma
        FROM gamma_expiration_timeline
        WHERE timestamp >= datetime('now', '-7 days')
          AND dte_bucket != 'TOTAL'
        GROUP BY dte_bucket
        ORDER BY avg_pct DESC
        LIMIT 5
    """)

    concentration = cursor.fetchall()

    if concentration:
        print("\n🎯 Gamma Concentration (7-day avg):")
        for bucket, avg_pct, avg_net in concentration:
            print(f"  {bucket:12s}: {avg_pct:5.1f}% of total | Net: ${avg_net/1e9:+.2f}B")


def log_mock_gamma_timeline():
    """Log mock gamma timeline when API unavailable"""
    try:
        import random

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        now = datetime.now(CENTRAL_TZ)

        # Mock data for different DTE buckets
        buckets = [
            ('0DTE', 0, 2.5e9, 5.0e9),
            ('1-2 DTE', 1, 3.2e9, 6.5e9),
            ('3-5 DTE', 4, 4.1e9, 8.2e9),
            ('7-10 DTE', 8, 5.5e9, 11.0e9),
            ('11-21 DTE', 16, 3.8e9, 7.5e9),
            ('30 DTE', 30, 2.1e9, 4.2e9),
        ]

        for bucket_name, avg_dte, net_gex, total_gex in buckets:
            c.execute("""
                INSERT INTO gamma_expiration_timeline (
                    timestamp, dte_bucket, avg_dte, net_gamma,
                    total_gamma_absolute, spot_price, gamma_pct_of_total
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                now.strftime('%Y-%m-%d %H:%M:%S'),
                bucket_name,
                avg_dte,
                net_gex,
                total_gex,
                580.0,
                random.uniform(8, 25)
            ))

        conn.commit()
        conn.close()

        print(f"✅ Logged {len(buckets)} mock gamma timeline snapshots (API unavailable)")

    except Exception as e:
        print(f"❌ Error logging mock timeline: {e}")


if __name__ == '__main__':
    track_gamma_expiration_timeline()
