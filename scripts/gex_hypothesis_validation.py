#!/usr/bin/env python3
"""
GEX Hypothesis Validation

Validates gamma structure hypotheses before ML training:
1. Positive gamma = mean-reverting (smaller range)
2. Negative gamma = trending (larger moves)
3. Pin zone = price closes between magnets
4. Flip point acts as gravity/support-resistance
5. Multi-magnet oscillation behavior

Also fetches and stores VIX data for additional features.

Usage:
    python scripts/gex_hypothesis_validation.py
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import statistics

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')


def get_connection():
    """Get PostgreSQL connection"""
    import psycopg2
    from urllib.parse import urlparse

    database_url = os.getenv('ORAT_DATABASE_URL') or os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL or ORAT_DATABASE_URL not set")

    result = urlparse(database_url)
    return psycopg2.connect(
        host=result.hostname,
        port=result.port or 5432,
        user=result.username,
        password=result.password,
        database=result.path[1:],
        connect_timeout=30
    )


def create_vix_table(conn):
    """Create table for VIX data"""
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vix_daily (
            id SERIAL PRIMARY KEY,
            trade_date DATE NOT NULL UNIQUE,
            vix_open NUMERIC(10,4),
            vix_high NUMERIC(10,4),
            vix_low NUMERIC(10,4),
            vix_close NUMERIC(10,4),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vix_date ON vix_daily(trade_date)")
    conn.commit()
    print("✓ Created vix_daily table")


def fetch_and_store_vix(conn, start_date: str = '2020-01-01', end_date: str = None):
    """Fetch VIX data from Yahoo Finance and store in database"""
    import yfinance as yf

    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')

    print(f"Fetching VIX data from {start_date} to {end_date}...")

    vix = yf.download('^VIX', start=start_date, end=end_date, progress=False)

    if len(vix) == 0:
        print("  No VIX data returned from Yahoo Finance")
        return 0

    cursor = conn.cursor()
    inserted = 0

    for date, row in vix.iterrows():
        trade_date = date.strftime('%Y-%m-%d')
        try:
            cursor.execute("""
                INSERT INTO vix_daily (trade_date, vix_open, vix_high, vix_low, vix_close)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (trade_date) DO UPDATE SET
                    vix_open = EXCLUDED.vix_open,
                    vix_high = EXCLUDED.vix_high,
                    vix_low = EXCLUDED.vix_low,
                    vix_close = EXCLUDED.vix_close
            """, (
                trade_date,
                float(row['Open']) if not row.isna()['Open'] else None,
                float(row['High']) if not row.isna()['High'] else None,
                float(row['Low']) if not row.isna()['Low'] else None,
                float(row['Close']) if not row.isna()['Close'] else None,
            ))
            inserted += 1
        except Exception as e:
            print(f"  Error inserting VIX for {trade_date}: {e}")
            conn.rollback()

    conn.commit()
    print(f"✓ Stored {inserted} days of VIX data")
    return inserted


def load_gex_data(conn) -> List[Dict]:
    """Load all GEX structure data from database"""
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            g.trade_date,
            g.symbol,
            g.spot_open,
            g.spot_close,
            g.spot_high,
            g.spot_low,
            g.net_gamma,
            g.total_call_gamma,
            g.total_put_gamma,
            g.flip_point,
            g.magnet_1_strike,
            g.magnet_1_gamma,
            g.magnet_2_strike,
            g.magnet_2_gamma,
            g.call_wall,
            g.put_wall,
            g.gamma_above_spot,
            g.gamma_below_spot,
            g.gamma_imbalance_pct,
            g.num_magnets_above,
            g.num_magnets_below,
            g.nearest_magnet_strike,
            g.nearest_magnet_distance_pct,
            g.open_to_flip_distance_pct,
            g.open_in_pin_zone,
            g.price_change_pct,
            g.price_range_pct,
            g.close_distance_to_flip_pct,
            g.close_distance_to_magnet1_pct,
            g.close_distance_to_magnet2_pct,
            v.vix_close
        FROM gex_structure_daily g
        LEFT JOIN vix_daily v ON g.trade_date = v.trade_date
        ORDER BY g.trade_date, g.symbol
    """)

    columns = [
        'trade_date', 'symbol', 'spot_open', 'spot_close', 'spot_high', 'spot_low',
        'net_gamma', 'total_call_gamma', 'total_put_gamma', 'flip_point',
        'magnet_1_strike', 'magnet_1_gamma', 'magnet_2_strike', 'magnet_2_gamma',
        'call_wall', 'put_wall', 'gamma_above_spot', 'gamma_below_spot',
        'gamma_imbalance_pct', 'num_magnets_above', 'num_magnets_below',
        'nearest_magnet_strike', 'nearest_magnet_distance_pct',
        'open_to_flip_distance_pct', 'open_in_pin_zone', 'price_change_pct',
        'price_range_pct', 'close_distance_to_flip_pct', 'close_distance_to_magnet1_pct',
        'close_distance_to_magnet2_pct', 'vix_close'
    ]

    data = []
    for row in cursor.fetchall():
        record = dict(zip(columns, row))
        # Convert Decimal to float
        for key, value in record.items():
            if hasattr(value, '__float__'):
                record[key] = float(value)
        data.append(record)

    return data


def classify_gamma_regime(net_gamma: float, data: List[Dict]) -> str:
    """Classify gamma regime based on net_gamma percentile"""
    if net_gamma is None:
        return 'UNKNOWN'

    # Use percentiles to classify
    all_net_gamma = [d['net_gamma'] for d in data if d['net_gamma'] is not None]
    p25 = sorted(all_net_gamma)[len(all_net_gamma) // 4]
    p75 = sorted(all_net_gamma)[3 * len(all_net_gamma) // 4]

    if net_gamma > p75:
        return 'POSITIVE'  # Top 25% = strongly positive gamma
    elif net_gamma < p25:
        return 'NEGATIVE'  # Bottom 25% = strongly negative gamma
    else:
        return 'NEUTRAL'


def test_hypothesis_1_positive_gamma_mean_reverting(data: List[Dict]) -> Dict:
    """
    Hypothesis 1: Positive gamma = mean-reverting (smaller range)

    Test: Compare price_range_pct when net_gamma > 0 vs < 0
    """
    print("\n" + "="*70)
    print("HYPOTHESIS 1: Positive Gamma = Mean-Reverting (Smaller Range)")
    print("="*70)

    positive_gamma_ranges = []
    negative_gamma_ranges = []

    for d in data:
        if d['net_gamma'] is None or d['price_range_pct'] is None:
            continue

        if d['net_gamma'] > 0:
            positive_gamma_ranges.append(d['price_range_pct'])
        else:
            negative_gamma_ranges.append(d['price_range_pct'])

    if not positive_gamma_ranges or not negative_gamma_ranges:
        print("  Insufficient data for analysis")
        return {'valid': False}

    pos_mean = statistics.mean(positive_gamma_ranges)
    neg_mean = statistics.mean(negative_gamma_ranges)
    pos_median = statistics.median(positive_gamma_ranges)
    neg_median = statistics.median(negative_gamma_ranges)

    # Statistical significance using t-test approximation
    pos_std = statistics.stdev(positive_gamma_ranges)
    neg_std = statistics.stdev(negative_gamma_ranges)
    n_pos = len(positive_gamma_ranges)
    n_neg = len(negative_gamma_ranges)

    # Welch's t-test (approximate)
    se = ((pos_std**2 / n_pos) + (neg_std**2 / n_neg)) ** 0.5
    t_stat = (pos_mean - neg_mean) / se if se > 0 else 0

    confirmed = pos_mean < neg_mean

    print(f"\n  Positive Gamma Days (n={n_pos}):")
    print(f"    Mean Range:   {pos_mean:.3f}%")
    print(f"    Median Range: {pos_median:.3f}%")
    print(f"    Std Dev:      {pos_std:.3f}%")

    print(f"\n  Negative Gamma Days (n={n_neg}):")
    print(f"    Mean Range:   {neg_mean:.3f}%")
    print(f"    Median Range: {neg_median:.3f}%")
    print(f"    Std Dev:      {neg_std:.3f}%")

    print(f"\n  Difference: {neg_mean - pos_mean:.3f}% (negative gamma has {'larger' if neg_mean > pos_mean else 'smaller'} range)")
    print(f"  T-statistic: {t_stat:.2f}")

    if confirmed:
        print(f"\n  ✓ CONFIRMED: Positive gamma has smaller range (mean-reverting)")
    else:
        print(f"\n  ✗ NOT CONFIRMED: Positive gamma does NOT have smaller range")

    return {
        'valid': True,
        'confirmed': confirmed,
        'pos_mean_range': pos_mean,
        'neg_mean_range': neg_mean,
        'difference': neg_mean - pos_mean,
        't_stat': t_stat,
        'n_positive': n_pos,
        'n_negative': n_neg
    }


def test_hypothesis_2_negative_gamma_trending(data: List[Dict]) -> Dict:
    """
    Hypothesis 2: Negative gamma = trending (larger directional moves)

    Test: Compare abs(price_change_pct) when net_gamma < 0 vs > 0
    """
    print("\n" + "="*70)
    print("HYPOTHESIS 2: Negative Gamma = Trending (Larger Directional Moves)")
    print("="*70)

    positive_gamma_moves = []
    negative_gamma_moves = []

    for d in data:
        if d['net_gamma'] is None or d['price_change_pct'] is None:
            continue

        abs_move = abs(d['price_change_pct'])

        if d['net_gamma'] > 0:
            positive_gamma_moves.append(abs_move)
        else:
            negative_gamma_moves.append(abs_move)

    if not positive_gamma_moves or not negative_gamma_moves:
        print("  Insufficient data for analysis")
        return {'valid': False}

    pos_mean = statistics.mean(positive_gamma_moves)
    neg_mean = statistics.mean(negative_gamma_moves)

    confirmed = neg_mean > pos_mean

    print(f"\n  Positive Gamma Days:")
    print(f"    Mean |Move|: {pos_mean:.3f}%")
    print(f"    Sample Size: {len(positive_gamma_moves)}")

    print(f"\n  Negative Gamma Days:")
    print(f"    Mean |Move|: {neg_mean:.3f}%")
    print(f"    Sample Size: {len(negative_gamma_moves)}")

    print(f"\n  Difference: {neg_mean - pos_mean:.3f}%")

    if confirmed:
        print(f"\n  ✓ CONFIRMED: Negative gamma has larger directional moves (trending)")
    else:
        print(f"\n  ✗ NOT CONFIRMED: Negative gamma does NOT have larger moves")

    return {
        'valid': True,
        'confirmed': confirmed,
        'pos_mean_move': pos_mean,
        'neg_mean_move': neg_mean,
        'difference': neg_mean - pos_mean
    }


def test_hypothesis_3_pin_zone_closes_between(data: List[Dict]) -> Dict:
    """
    Hypothesis 3: When in pin zone, price closes BETWEEN the two magnets

    Test: When open_in_pin_zone = True, what % of days close between magnet 1 and 2?
    """
    print("\n" + "="*70)
    print("HYPOTHESIS 3: Pin Zone = Price Closes Between Magnets")
    print("="*70)

    pin_zone_days = []
    closed_between = 0
    closed_outside = 0

    for d in data:
        if not d['open_in_pin_zone']:
            continue
        if d['magnet_1_strike'] is None or d['magnet_2_strike'] is None:
            continue
        if d['spot_close'] is None:
            continue

        m1 = d['magnet_1_strike']
        m2 = d['magnet_2_strike']
        close = d['spot_close']

        low_magnet = min(m1, m2)
        high_magnet = max(m1, m2)

        pin_zone_days.append({
            'date': d['trade_date'],
            'close': close,
            'low_magnet': low_magnet,
            'high_magnet': high_magnet,
            'between': low_magnet <= close <= high_magnet
        })

        if low_magnet <= close <= high_magnet:
            closed_between += 1
        else:
            closed_outside += 1

    total = closed_between + closed_outside

    if total == 0:
        print("  No pin zone days found")
        return {'valid': False}

    pct_between = closed_between / total * 100
    confirmed = pct_between > 50  # More than half close between

    print(f"\n  Pin Zone Days Analyzed: {total}")
    print(f"  Closed Between Magnets: {closed_between} ({pct_between:.1f}%)")
    print(f"  Closed Outside Magnets: {closed_outside} ({100 - pct_between:.1f}%)")

    if confirmed:
        print(f"\n  ✓ CONFIRMED: Price closes between magnets {pct_between:.1f}% of the time")
    else:
        print(f"\n  ✗ NOT CONFIRMED: Only {pct_between:.1f}% close between magnets")

    return {
        'valid': True,
        'confirmed': confirmed,
        'total_pin_days': total,
        'closed_between': closed_between,
        'pct_between': pct_between
    }


def test_hypothesis_4_flip_point_gravity(data: List[Dict]) -> Dict:
    """
    Hypothesis 4: Price gravitates toward flip point

    Test: When price opens away from flip, does it move toward flip more than 50%?
    """
    print("\n" + "="*70)
    print("HYPOTHESIS 4: Flip Point Acts as Gravity/Support-Resistance")
    print("="*70)

    moved_toward_flip = 0
    moved_away_from_flip = 0

    for d in data:
        if d['flip_point'] is None or d['spot_open'] is None or d['spot_close'] is None:
            continue

        flip = d['flip_point']
        open_price = d['spot_open']
        close_price = d['spot_close']

        # Distance from flip at open vs close
        dist_at_open = abs(open_price - flip)
        dist_at_close = abs(close_price - flip)

        if dist_at_close < dist_at_open:
            moved_toward_flip += 1
        else:
            moved_away_from_flip += 1

    total = moved_toward_flip + moved_away_from_flip

    if total == 0:
        print("  No data with flip points")
        return {'valid': False}

    pct_toward = moved_toward_flip / total * 100
    confirmed = pct_toward > 50

    print(f"\n  Days Analyzed: {total}")
    print(f"  Moved TOWARD Flip: {moved_toward_flip} ({pct_toward:.1f}%)")
    print(f"  Moved AWAY from Flip: {moved_away_from_flip} ({100 - pct_toward:.1f}%)")

    if confirmed:
        print(f"\n  ✓ CONFIRMED: Price gravitates toward flip {pct_toward:.1f}% of the time")
    else:
        print(f"\n  ✗ NOT CONFIRMED: Only {pct_toward:.1f}% move toward flip")

    return {
        'valid': True,
        'confirmed': confirmed,
        'total_days': total,
        'moved_toward': moved_toward_flip,
        'pct_toward': pct_toward
    }


def test_hypothesis_5_multi_magnet_oscillation(data: List[Dict]) -> Dict:
    """
    Hypothesis 5: Price touches both magnets intraday when two large magnets exist

    Test: When in pin zone, does high/low span both magnets?
    """
    print("\n" + "="*70)
    print("HYPOTHESIS 5: Multi-Magnet Oscillation (Price Touches Both)")
    print("="*70)

    touched_both = 0
    touched_one = 0
    touched_neither = 0

    for d in data:
        if not d['open_in_pin_zone']:
            continue
        if d['magnet_1_strike'] is None or d['magnet_2_strike'] is None:
            continue
        if d['spot_high'] is None or d['spot_low'] is None:
            continue

        m1 = d['magnet_1_strike']
        m2 = d['magnet_2_strike']
        high = d['spot_high']
        low = d['spot_low']

        low_magnet = min(m1, m2)
        high_magnet = max(m1, m2)

        # Check if price range touched both magnets (within 0.1%)
        tolerance = d['spot_open'] * 0.001  # 0.1%

        touched_low = low <= low_magnet + tolerance
        touched_high = high >= high_magnet - tolerance

        if touched_low and touched_high:
            touched_both += 1
        elif touched_low or touched_high:
            touched_one += 1
        else:
            touched_neither += 1

    total = touched_both + touched_one + touched_neither

    if total == 0:
        print("  No pin zone days found")
        return {'valid': False}

    pct_both = touched_both / total * 100
    pct_at_least_one = (touched_both + touched_one) / total * 100

    print(f"\n  Pin Zone Days Analyzed: {total}")
    print(f"  Touched BOTH Magnets:     {touched_both} ({pct_both:.1f}%)")
    print(f"  Touched ONE Magnet:       {touched_one} ({touched_one/total*100:.1f}%)")
    print(f"  Touched NEITHER:          {touched_neither} ({touched_neither/total*100:.1f}%)")
    print(f"  Touched At Least One:     {touched_both + touched_one} ({pct_at_least_one:.1f}%)")

    confirmed = pct_at_least_one > 60

    if confirmed:
        print(f"\n  ✓ CONFIRMED: Price interacts with magnets {pct_at_least_one:.1f}% of pin zone days")
    else:
        print(f"\n  ✗ NOT CONFIRMED: Only {pct_at_least_one:.1f}% interact with magnets")

    return {
        'valid': True,
        'confirmed': confirmed,
        'total_days': total,
        'touched_both': touched_both,
        'touched_one': touched_one,
        'pct_both': pct_both,
        'pct_at_least_one': pct_at_least_one
    }


def test_hypothesis_6_vix_correlation(data: List[Dict]) -> Dict:
    """
    Additional: VIX correlation with gamma regime effectiveness

    Test: Does gamma regime prediction work better in high vs low VIX?
    """
    print("\n" + "="*70)
    print("ADDITIONAL: VIX Correlation with Gamma Effects")
    print("="*70)

    high_vix_pos_gamma_ranges = []
    high_vix_neg_gamma_ranges = []
    low_vix_pos_gamma_ranges = []
    low_vix_neg_gamma_ranges = []

    vix_values = [d['vix_close'] for d in data if d['vix_close'] is not None]

    if not vix_values:
        print("  No VIX data available")
        return {'valid': False}

    vix_median = statistics.median(vix_values)

    for d in data:
        if d['vix_close'] is None or d['net_gamma'] is None or d['price_range_pct'] is None:
            continue

        is_high_vix = d['vix_close'] > vix_median
        is_pos_gamma = d['net_gamma'] > 0

        if is_high_vix:
            if is_pos_gamma:
                high_vix_pos_gamma_ranges.append(d['price_range_pct'])
            else:
                high_vix_neg_gamma_ranges.append(d['price_range_pct'])
        else:
            if is_pos_gamma:
                low_vix_pos_gamma_ranges.append(d['price_range_pct'])
            else:
                low_vix_neg_gamma_ranges.append(d['price_range_pct'])

    print(f"\n  VIX Median: {vix_median:.2f}")

    print(f"\n  HIGH VIX Environment (VIX > {vix_median:.1f}):")
    if high_vix_pos_gamma_ranges and high_vix_neg_gamma_ranges:
        hv_pos_mean = statistics.mean(high_vix_pos_gamma_ranges)
        hv_neg_mean = statistics.mean(high_vix_neg_gamma_ranges)
        print(f"    Positive Gamma Mean Range: {hv_pos_mean:.3f}% (n={len(high_vix_pos_gamma_ranges)})")
        print(f"    Negative Gamma Mean Range: {hv_neg_mean:.3f}% (n={len(high_vix_neg_gamma_ranges)})")
        print(f"    Gamma Effect: {hv_neg_mean - hv_pos_mean:.3f}%")

    print(f"\n  LOW VIX Environment (VIX <= {vix_median:.1f}):")
    if low_vix_pos_gamma_ranges and low_vix_neg_gamma_ranges:
        lv_pos_mean = statistics.mean(low_vix_pos_gamma_ranges)
        lv_neg_mean = statistics.mean(low_vix_neg_gamma_ranges)
        print(f"    Positive Gamma Mean Range: {lv_pos_mean:.3f}% (n={len(low_vix_pos_gamma_ranges)})")
        print(f"    Negative Gamma Mean Range: {lv_neg_mean:.3f}% (n={len(low_vix_neg_gamma_ranges)})")
        print(f"    Gamma Effect: {lv_neg_mean - lv_pos_mean:.3f}%")

    return {
        'valid': True,
        'vix_median': vix_median,
        'high_vix_gamma_effect': hv_neg_mean - hv_pos_mean if high_vix_pos_gamma_ranges and high_vix_neg_gamma_ranges else None,
        'low_vix_gamma_effect': lv_neg_mean - lv_pos_mean if low_vix_pos_gamma_ranges and low_vix_neg_gamma_ranges else None
    }


def print_summary(results: Dict):
    """Print summary of all hypothesis tests"""
    print("\n" + "="*70)
    print("SUMMARY OF HYPOTHESIS VALIDATION")
    print("="*70)

    hypotheses = [
        ("H1: Positive Gamma = Mean-Reverting", results.get('h1', {})),
        ("H2: Negative Gamma = Trending", results.get('h2', {})),
        ("H3: Pin Zone = Closes Between Magnets", results.get('h3', {})),
        ("H4: Flip Point = Gravity", results.get('h4', {})),
        ("H5: Multi-Magnet Oscillation", results.get('h5', {})),
    ]

    confirmed_count = 0

    for name, result in hypotheses:
        if result.get('valid'):
            status = "✓ CONFIRMED" if result.get('confirmed') else "✗ NOT CONFIRMED"
            if result.get('confirmed'):
                confirmed_count += 1
        else:
            status = "? INSUFFICIENT DATA"
        print(f"\n  {name}")
        print(f"    Status: {status}")

    print(f"\n" + "-"*70)
    print(f"  TOTAL: {confirmed_count}/5 hypotheses confirmed")
    print("="*70)


def main():
    print("="*70)
    print("GEX HYPOTHESIS VALIDATION")
    print("="*70)

    print("\nConnecting to database...")
    conn = get_connection()

    # Create VIX table and fetch data
    print("\n--- VIX DATA ---")
    create_vix_table(conn)
    fetch_and_store_vix(conn)

    # Load all GEX data
    print("\n--- LOADING GEX DATA ---")
    data = load_gex_data(conn)
    print(f"✓ Loaded {len(data)} records")

    # Count by symbol
    spx_count = sum(1 for d in data if d['symbol'] == 'SPX')
    spy_count = sum(1 for d in data if d['symbol'] == 'SPY')
    print(f"  SPX: {spx_count} days")
    print(f"  SPY: {spy_count} days")

    # Run hypothesis tests
    results = {}
    results['h1'] = test_hypothesis_1_positive_gamma_mean_reverting(data)
    results['h2'] = test_hypothesis_2_negative_gamma_trending(data)
    results['h3'] = test_hypothesis_3_pin_zone_closes_between(data)
    results['h4'] = test_hypothesis_4_flip_point_gravity(data)
    results['h5'] = test_hypothesis_5_multi_magnet_oscillation(data)
    results['vix'] = test_hypothesis_6_vix_correlation(data)

    # Print summary
    print_summary(results)

    conn.close()
    print("\n✓ Done!")

    return results


if __name__ == "__main__":
    main()
