#!/usr/bin/env python3
"""
Generate Placeholder Data for AlphaGEX UI Pages

This script populates the database with realistic historical data
so users can see pages working while real data accumulates.
"""

import random
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path to import modules
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from database_adapter import get_connection

def generate_regime_signals(conn, days=30):
    """Generate realistic psychology regime signals"""
    print(f"Generating {days} days of regime signals...")

    c = conn.cursor()

    # Regime types and their characteristics
    regimes = {
        'LIBERATION_SETUP': {
            'confidence_range': (75, 95),
            'trade_direction': 'BULLISH',
            'risk_level': 'MEDIUM',
            'win_rate': 0.72,
            'avg_move': 2.5
        },
        'FALSE_FLOOR': {
            'confidence_range': (70, 88),
            'trade_direction': 'BEARISH',
            'risk_level': 'MEDIUM',
            'win_rate': 0.65,
            'avg_move': -1.8
        },
        'GAMMA_SQUEEZE_CASCADE': {
            'confidence_range': (85, 98),
            'trade_direction': 'BULLISH',
            'risk_level': 'HIGH',
            'win_rate': 0.78,
            'avg_move': 4.2
        },
        'FLIP_POINT_CRITICAL': {
            'confidence_range': (80, 95),
            'trade_direction': 'VOLATILE',
            'risk_level': 'HIGH',
            'win_rate': 0.68,
            'avg_move': 3.1
        },
        'VOLATILITY_CRUSH_IMMINENT': {
            'confidence_range': (72, 90),
            'trade_direction': 'NEUTRAL',
            'risk_level': 'LOW',
            'win_rate': 0.70,
            'avg_move': 0.8
        },
        'DEALER_CAPITULATION': {
            'confidence_range': (88, 98),
            'trade_direction': 'BULLISH',
            'risk_level': 'HIGH',
            'win_rate': 0.82,
            'avg_move': 5.5
        }
    }

    # Base SPY price
    spy_price = 450.0
    vix = 15.0

    # Generate 2-5 signals per day
    total_signals = 0
    for day in range(days):
        num_signals = random.randint(2, 5)
        timestamp = datetime.now() - timedelta(days=days-day)

        for _ in range(num_signals):
            # Random regime
            regime_type = random.choice(list(regimes.keys()))
            regime = regimes[regime_type]

            # Generate signal characteristics
            confidence = random.uniform(*regime['confidence_range'])

            # Simulate outcome based on win rate
            is_winner = random.random() < regime['win_rate']

            if is_winner:
                price_change_1d = abs(regime['avg_move']) * random.uniform(0.7, 1.3)
                if regime['trade_direction'] == 'BEARISH':
                    price_change_1d *= -1
            else:
                # Loser moves opposite direction
                price_change_1d = -abs(regime['avg_move']) * random.uniform(0.3, 0.8)
                if regime['trade_direction'] == 'BEARISH':
                    price_change_1d *= -1

            # Cumulative price changes
            price_change_5d = price_change_1d * random.uniform(1.2, 2.5)
            price_change_10d = price_change_5d * random.uniform(1.1, 1.8)

            # RSI values
            rsi_values = {
                '5m': random.uniform(30, 70),
                '15m': random.uniform(30, 70),
                '1h': random.uniform(30, 70),
                '4h': random.uniform(30, 70),
                '1d': random.uniform(30, 70)
            }

            # Gamma walls
            call_wall = spy_price * random.uniform(1.01, 1.03)
            put_wall = spy_price * random.uniform(0.97, 0.99)

            # Insert signal
            c.execute('''
                INSERT INTO regime_signals (
                    timestamp, spy_price, vix_current,
                    primary_regime_type, secondary_regime_type,
                    confidence_score, trade_direction, risk_level,
                    description, psychology_trap,
                    rsi_5m, rsi_15m, rsi_1h, rsi_4h, rsi_1d,
                    nearest_call_wall, call_wall_distance_pct,
                    nearest_put_wall, put_wall_distance_pct,
                    net_gamma, gamma_expiring_this_week,
                    price_change_1d, price_change_5d, price_change_10d,
                    signal_correct, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                spy_price + random.uniform(-5, 5),
                vix + random.uniform(-2, 2),
                regime_type,
                random.choice(['VIX_SPIKE', 'GAMMA_WALL', 'RSI_EXTREME', None]),
                confidence,
                regime['trade_direction'],
                regime['risk_level'],
                f"{regime_type.replace('_', ' ').title()} detected at ${spy_price:.2f}",
                f"Market makers {random.choice(['trapped', 'defending', 'hunting', 'panicking'])}",
                rsi_values['5m'], rsi_values['15m'], rsi_values['1h'],
                rsi_values['4h'], rsi_values['1d'],
                call_wall, ((call_wall - spy_price) / spy_price * 100),
                put_wall, ((spy_price - put_wall) / spy_price * 100),
                random.uniform(-2e9, 2e9),
                random.uniform(0.5e9, 5e9),
                price_change_1d, price_change_5d, price_change_10d,
                1 if is_winner else 0,
                timestamp.strftime('%Y-%m-%d %H:%M:%S')
            ))

            total_signals += 1

            # Slightly adjust base prices for next iteration
            spy_price += random.uniform(-2, 2)
            vix += random.uniform(-0.5, 0.5)
            vix = max(12, min(30, vix))  # Keep VIX realistic

    conn.commit()
    print(f"✓ Generated {total_signals} regime signals")


def generate_gex_history(conn, days=30):
    """Generate GEX history snapshots"""
    print(f"Generating {days} days of GEX history...")

    c = conn.cursor()

    spy_price = 450.0
    total_snapshots = 0

    mm_states = ['TRAPPED', 'DEFENDING', 'HUNTING', 'NEUTRAL']
    regimes = ['NEGATIVE_GEX', 'POSITIVE_GEX', 'NEUTRAL']

    for day in range(days):
        # 4 snapshots per day (market open, noon, close, after hours)
        for hour in [9.5, 12, 16, 20]:
            timestamp = datetime.now() - timedelta(days=days-day, hours=24-hour)

            net_gex = random.uniform(-3e9, 3e9)
            current_price = spy_price + random.uniform(-10, 10)

            c.execute('''
                INSERT INTO gex_history (
                    timestamp, symbol, net_gex, flip_point,
                    call_wall, put_wall, spot_price, mm_state,
                    regime, data_source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                'SPY',
                net_gex,
                current_price * random.uniform(0.98, 1.02),
                current_price * random.uniform(1.01, 1.04),
                current_price * random.uniform(0.96, 0.99),
                current_price,
                random.choice(mm_states),
                random.choice(regimes),
                'HISTORICAL_PLACEHOLDER'
            ))

            total_snapshots += 1
            spy_price += random.uniform(-1, 1)

    conn.commit()
    print(f"✓ Generated {total_snapshots} GEX snapshots")


def generate_recommendations_history(conn, days=30):
    """Generate AI recommendation history"""
    print(f"Generating {days} days of recommendations...")

    c = conn.cursor()

    strategies = [
        'BULLISH_CALL_SPREAD',
        'BEARISH_PUT_SPREAD',
        'BULL_PUT_SPREAD',
        'BEAR_CALL_SPREAD',
        'IRON_CONDOR',
        'LONG_STRADDLE'
    ]

    total_recs = 0
    for day in range(days):
        # 1-3 recommendations per day
        num_recs = random.randint(1, 3)

        for _ in range(num_recs):
            timestamp = datetime.now() - timedelta(days=days-day, hours=random.randint(9, 16))
            strategy = random.choice(strategies)
            confidence = random.uniform(60, 95)

            # Win rate correlates with confidence
            is_winner = random.random() < (confidence / 100 * 0.9)

            entry_price = 450 + random.uniform(-10, 10)
            strike = round(entry_price * random.uniform(0.98, 1.02), 0)

            if is_winner:
                pnl = random.uniform(50, 500)
            else:
                pnl = -random.uniform(30, 200)

            c.execute('''
                INSERT INTO recommendations (
                    timestamp, symbol, strategy, confidence,
                    reasoning, entry_price, target_price, stop_price,
                    option_strike, option_type, dte, mm_behavior,
                    outcome, pnl
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                'SPY',
                strategy,
                confidence,
                f"Strong {strategy.replace('_', ' ').lower()} setup based on gamma positioning",
                entry_price,
                entry_price * random.uniform(1.02, 1.08),
                entry_price * random.uniform(0.92, 0.98),
                strike,
                random.choice(['CALL', 'PUT']),
                random.randint(1, 21),
                random.choice(['TRAPPED', 'DEFENDING', 'HUNTING']),
                'WIN' if is_winner else 'LOSS',
                pnl
            ))

            total_recs += 1

    conn.commit()
    print(f"✓ Generated {total_recs} recommendations")


def generate_conversation_history(conn, days=7):
    """Generate AI conversation history"""
    print(f"Generating {days} days of conversations...")

    c = conn.cursor()

    questions = [
        "What's the current GEX regime?",
        "Should I buy calls or puts right now?",
        "Explain the liberation setup",
        "What are the key gamma walls?",
        "Is this a good time to enter a trade?",
        "What's your confidence on this signal?",
        "How does the VIX affect this strategy?",
        "What's the path of least resistance?",
        "Analyze SPY options flow",
        "What strikes should I target?"
    ]

    total_convos = 0
    for day in range(days):
        # 3-8 conversations per day
        num_convos = random.randint(3, 8)

        for _ in range(num_convos):
            timestamp = datetime.now() - timedelta(days=days-day, hours=random.randint(9, 20))
            question = random.choice(questions)

            c.execute('''
                INSERT INTO conversations (
                    timestamp, user_message, ai_response, context_data,
                    confidence_score
                ) VALUES (?, ?, ?, ?, ?)
            ''', (
                timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                question,
                f"Based on current market conditions, {question.lower()} shows interesting setup. Current GEX: ${random.uniform(-2e9, 2e9):.2e}, confidence {random.randint(70, 95)}%.",
                '{"regime": "LIBERATION", "spy": 450.25, "vix": 15.3}',
                random.uniform(70, 95)
            ))

            total_convos += 1

    conn.commit()
    print(f"✓ Generated {total_convos} conversations")


def generate_liberation_outcomes(conn, days=14):
    """Generate liberation outcome tracking data"""
    print(f"Generating {days} days of liberation outcomes...")

    c = conn.cursor()

    total_outcomes = 0
    for day in range(days):
        # 2-4 liberation setups per day
        num_outcomes = random.randint(2, 4)

        for _ in range(num_outcomes):
            signal_date = (datetime.now() - timedelta(days=days-day)).date()
            liberation_date = signal_date + timedelta(days=random.randint(0, 3))

            strike = round(450 + random.uniform(-20, 20), 0)
            price_at_signal = strike * random.uniform(0.97, 1.03)

            # 72% chance of successful breakout
            breakout = random.random() < 0.72

            if breakout:
                price_at_lib = price_at_signal * random.uniform(1.01, 1.04)
                price_1d = price_at_lib * random.uniform(1.00, 1.03)
                price_5d = price_1d * random.uniform(1.00, 1.05)
                max_move = random.uniform(3, 8)
            else:
                price_at_lib = price_at_signal * random.uniform(0.99, 1.01)
                price_1d = price_at_lib * random.uniform(0.98, 1.01)
                price_5d = price_1d * random.uniform(0.97, 1.02)
                max_move = random.uniform(0.5, 2)

            c.execute('''
                INSERT INTO liberation_outcomes (
                    signal_date, liberation_date, strike, expiry_ratio,
                    price_at_signal, price_at_liberation,
                    price_1d_after, price_5d_after,
                    breakout_occurred, max_move_pct, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                signal_date.strftime('%Y-%m-%d'),
                liberation_date.strftime('%Y-%m-%d'),
                strike,
                random.uniform(0.15, 0.35),
                price_at_signal,
                price_at_lib,
                price_1d,
                price_5d,
                1 if breakout else 0,
                max_move,
                datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            ))

            total_outcomes += 1

    conn.commit()
    print(f"✓ Generated {total_outcomes} liberation outcomes")


def generate_forward_magnets(conn, days=14):
    """Generate forward magnet detection data"""
    print(f"Generating {days} days of forward magnets...")

    c = conn.cursor()

    total_magnets = 0
    for day in range(days):
        # 1-3 magnet detections per day
        num_magnets = random.randint(1, 3)

        for _ in range(num_magnets):
            snapshot_date = (datetime.now() - timedelta(days=days-day)).date()

            strike = round(450 + random.uniform(-20, 20), 0)
            dte = random.randint(0, 21)
            expiration_date = snapshot_date + timedelta(days=dte)

            c.execute('''
                INSERT INTO forward_magnets (
                    snapshot_date, strike, expiration_date, dte,
                    magnet_strength_score, total_gamma, total_oi,
                    distance_from_spot_pct, direction
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                snapshot_date.strftime('%Y-%m-%d'),
                strike,
                expiration_date.strftime('%Y-%m-%d'),
                dte,
                random.uniform(0.6, 1.0),
                random.uniform(0.5e9, 3e9),
                random.randint(10000, 100000),
                random.uniform(-5, 5),
                random.choice(['UP', 'DOWN', 'NEUTRAL'])
            ))

            total_magnets += 1

    conn.commit()
    print(f"✓ Generated {total_magnets} forward magnets")


def main():
    """Generate all placeholder data"""
    print("=" * 60)
    print("AlphaGEX Placeholder Data Generator")
    print("=" * 60)
    print()

    # Connect to database (uses database adapter for PostgreSQL/SQLite)
    conn = get_connection()

    try:
        # Generate all data types
        generate_regime_signals(conn, days=30)
        generate_gex_history(conn, days=30)
        generate_recommendations_history(conn, days=30)
        generate_conversation_history(conn, days=7)
        generate_liberation_outcomes(conn, days=14)
        generate_forward_magnets(conn, days=14)

        print()
        print("=" * 60)
        print("✅ SUCCESS! All placeholder data generated")
        print("=" * 60)
        print()
        print("Next steps:")
        print("1. Refresh your browser to see the data")
        print("2. Pages will now show charts and trends")
        print("3. Real data will accumulate alongside this placeholder data")
        print()

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()


if __name__ == '__main__':
    main()
