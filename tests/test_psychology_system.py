#!/usr/bin/env python3
"""
Test script for Psychology Trap Detection System
"""

import sqlite3
from db.config_and_database import DB_PATH, init_database

def test_database_tables():
    """Verify all psychology tables were created"""
    print("=" * 80)
    print("Testing Database Tables")
    print("=" * 80)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Get all tables
    c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in c.fetchall()]

    psychology_tables = [
        'regime_signals',
        'gamma_expiration_timeline',
        'historical_open_interest',
        'forward_magnets',
        'sucker_statistics',
        'liberation_outcomes'
    ]

    print(f"\n📊 Found {len(tables)} total tables in database")
    print(f"🧠 Psychology tables to verify: {len(psychology_tables)}")

    all_good = True
    for table in psychology_tables:
        exists = table in tables
        status = "✅" if exists else "❌"
        print(f"  {status} {table}")
        if not exists:
            all_good = False

    if all_good:
        print("\n✅ All psychology tables created successfully!")
    else:
        print("\n❌ Some tables missing!")

    # Show table schemas
    print("\n" + "=" * 80)
    print("Table Schemas")
    print("=" * 80)

    for table in psychology_tables:
        if table in tables:
            c.execute(f"PRAGMA table_info({table})")
            columns = c.fetchall()
            print(f"\n📋 {table} ({len(columns)} columns):")
            for col in columns[:5]:  # Show first 5 columns
                print(f"   - {col[1]} ({col[2]})")
            if len(columns) > 5:
                print(f"   ... and {len(columns) - 5} more columns")

    conn.close()
    return all_good


def test_psychology_detector():
    """Test the psychology trap detector module"""
    print("\n" + "=" * 80)
    print("Testing Psychology Trap Detector Module")
    print("=" * 80)

    try:
        from core.psychology_trap_detector import (
            calculate_rsi,
            calculate_mtf_rsi_score,
            analyze_current_gamma_walls,
            analyze_gamma_expiration,
            analyze_forward_gex,
            detect_market_regime_complete
        )

        print("✅ All imports successful")

        # Test RSI calculation
        print("\n📊 Testing RSI calculation...")
        import numpy as np
        test_prices = np.random.uniform(400, 450, 50)
        rsi = calculate_rsi(test_prices)
        print(f"✅ RSI calculated: {rsi:.2f}")

        # Test multi-timeframe RSI
        print("\n📊 Testing multi-timeframe RSI...")
        price_data = {
            '5m': [{'close': 445 + i * 0.1, 'high': 446, 'low': 444, 'volume': 1000000} for i in range(100)],
            '15m': [{'close': 445 + i * 0.2, 'high': 446, 'low': 444, 'volume': 2000000} for i in range(100)],
            '1h': [{'close': 445 + i * 0.5, 'high': 447, 'low': 443, 'volume': 5000000} for i in range(100)],
            '4h': [{'close': 445 + i, 'high': 450, 'low': 440, 'volume': 10000000} for i in range(50)],
            '1d': [{'close': 445 + i * 2, 'high': 455, 'low': 435, 'volume': 50000000} for i in range(50)]
        }
        rsi_analysis = calculate_mtf_rsi_score(price_data)
        print(f"✅ Multi-TF RSI score: {rsi_analysis['score']:.2f}")
        print(f"   Overbought timeframes: {rsi_analysis['aligned_count']['overbought']}")
        print(f"   Oversold timeframes: {rsi_analysis['aligned_count']['oversold']}")
        print(f"   Coiling detected: {rsi_analysis['coiling_detected']}")

        # Test gamma wall analysis
        print("\n🛡️  Testing gamma wall analysis...")
        from datetime import datetime, timedelta
        gamma_data = {
            'net_gamma': -1.5e9,
            'expirations': [
                {
                    'expiration_date': datetime.now() + timedelta(days=2),
                    'dte': 2,
                    'expiration_type': 'weekly',
                    'call_strikes': [
                        {'strike': 450, 'gamma_exposure': -500e6, 'open_interest': 10000},
                        {'strike': 455, 'gamma_exposure': -800e6, 'open_interest': 15000}
                    ],
                    'put_strikes': [
                        {'strike': 440, 'gamma_exposure': -600e6, 'open_interest': 12000},
                        {'strike': 435, 'gamma_exposure': -400e6, 'open_interest': 8000}
                    ]
                }
            ]
        }
        current_price = 445.0
        walls = analyze_current_gamma_walls(current_price, gamma_data)
        print(f"✅ Gamma walls analyzed:")
        if walls['call_wall']:
            print(f"   Call wall at ${walls['call_wall']['strike']:.2f} ({walls['call_wall']['distance_pct']:.2f}% away)")
        if walls['put_wall']:
            print(f"   Put wall at ${walls['put_wall']['strike']:.2f} ({walls['put_wall']['distance_pct']:.2f}% away)")
        print(f"   Net gamma regime: {walls['net_gamma_regime']}")

        # Test expiration analysis
        print("\n⏰ Testing gamma expiration analysis...")
        exp_analysis = analyze_gamma_expiration(gamma_data, current_price)
        print(f"✅ Expiration analysis completed:")
        print(f"   Expirations tracked: {len(exp_analysis['expiration_timeline'])}")
        print(f"   Liberation setups: {len(exp_analysis['liberation_candidates'])}")
        print(f"   False floors: {len(exp_analysis['false_floor_candidates'])}")

        # Test complete regime detection
        print("\n🎯 Testing complete regime detection...")
        regime = detect_market_regime_complete(
            rsi_analysis=rsi_analysis,
            current_walls=walls,
            expiration_analysis=exp_analysis,
            forward_gex=None,
            volume_ratio=1.2,
            net_gamma=-1.5e9
        )
        print(f"✅ Regime detected: {regime['primary_type']}")
        print(f"   Confidence: {regime['confidence']:.0f}%")
        print(f"   Risk level: {regime['risk_level']}")
        print(f"   Direction: {regime['trade_direction']}")
        print(f"   Description: {regime['description']}")

        print("\n✅ All psychology trap detector tests passed!")
        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("\n" + "=" * 80)
    print("🧠 AlphaGEX Psychology Trap Detection System - Test Suite")
    print("=" * 80)

    # Initialize database
    print("\n📦 Initializing database...")
    init_database()
    print("✅ Database initialized")

    # Test database tables
    db_ok = test_database_tables()

    # Test psychology detector
    detector_ok = test_psychology_detector()

    # Final summary
    print("\n" + "=" * 80)
    print("Test Summary")
    print("=" * 80)
    print(f"Database tables: {'✅ PASS' if db_ok else '❌ FAIL'}")
    print(f"Psychology detector: {'✅ PASS' if detector_ok else '❌ FAIL'}")

    if db_ok and detector_ok:
        print("\n🎉 All tests passed! System ready to use.")
        print("\n🚀 Next steps:")
        print("  1. Start the backend: cd backend && python main.py")
        print("  2. Start the frontend: cd frontend && npm run dev")
        print("  3. Visit: http://localhost:3000/psychology")
    else:
        print("\n❌ Some tests failed. Please review errors above.")

    print("=" * 80)


if __name__ == "__main__":
    main()
