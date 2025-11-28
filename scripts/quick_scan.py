#!/usr/bin/env python3
"""
Quick Scanner - Run scanner from command line without any web UI

Usage:
    python quick_scan.py SPY QQQ IWM AAPL
"""

import sys
from core_classes_and_engines import TradingVolatilityAPI
from config_and_database import STRATEGIES

def quick_scan(symbols):
    """Scan symbols and print results"""

    print(f"\n🔍 Scanning {len(symbols)} symbols...")
    print("=" * 60)

    api = TradingVolatilityAPI()
    results = []

    for symbol in symbols:
        print(f"\n📊 {symbol}...", end=" ", flush=True)

        try:
            gex_data = api.get_net_gamma(symbol)

            if not gex_data or gex_data.get('error'):
                print(f"❌ Error: {gex_data.get('error', 'No data')}")
                continue

            net_gex = gex_data.get('net_gex') or 0
            spot_price = gex_data.get('spot_price') or 0
            flip_point = gex_data.get('flip_point') or 0

            print(f"✅ ${spot_price:.2f} | GEX: ${net_gex/1e9:.1f}B")

            # Check each strategy
            for strategy_name, config in STRATEGIES.items():

                if strategy_name == 'NEGATIVE_GEX_SQUEEZE':
                    if net_gex < config['conditions']['net_gex_threshold']:
                        distance = abs(spot_price - flip_point) / spot_price * 100 if spot_price else 0
                        if distance < config['conditions']['distance_to_flip']:
                            confidence = 75 if spot_price < flip_point else 85
                            results.append({
                                'symbol': symbol,
                                'strategy': 'NEGATIVE GEX SQUEEZE',
                                'confidence': confidence,
                                'action': f"BUY {symbol} CALL near ${flip_point:.2f}",
                                'reasoning': f"Negative GEX creates upside squeeze. {distance:.1f}% from flip."
                            })

                elif strategy_name == 'IRON_CONDOR':
                    if net_gex > config['conditions']['net_gex_threshold']:
                        results.append({
                            'symbol': symbol,
                            'strategy': 'IRON CONDOR',
                            'confidence': 72,
                            'action': f"SELL Iron Condor on {symbol}",
                            'reasoning': f"Positive GEX pins price. Range-bound expected."
                        })

        except Exception as e:
            print(f"❌ Error: {e}")

    # Print results
    print("\n" + "=" * 60)
    print(f"\n💰 FOUND {len(results)} OPPORTUNITIES:\n")

    if not results:
        print("No trading opportunities found.")
        print("Try different symbols or check if market is open.")
    else:
        for i, result in enumerate(results, 1):
            print(f"{i}. {result['symbol']} - {result['strategy']}")
            print(f"   Confidence: {result['confidence']}%")
            print(f"   Action: {result['action']}")
            print(f"   Why: {result['reasoning']}")
            print()

    print("=" * 60)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python quick_scan.py SPY QQQ IWM AAPL")
        print("\nOr use default symbols:")
        symbols = ['SPY', 'QQQ', 'IWM']
    else:
        symbols = sys.argv[1:]

    quick_scan(symbols)
