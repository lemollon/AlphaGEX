#!/usr/bin/env python3
"""
Predict Market Direction from Current GEX Structure
====================================================

Usage:
    # Get prediction for current GEX
    python scripts/predict_direction.py

    # Use specific VIX level
    python scripts/predict_direction.py --vix 25

    # Use custom model
    python scripts/predict_direction.py --model models/my_model.joblib
"""

import os
import sys
import argparse
from datetime import datetime

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


def get_current_gex(ticker: str = 'SPY') -> dict:
    """Fetch current GEX from database or calculate from ORAT"""
    from quant.chronicles_gex_calculator import KronosGEXCalculator

    calc = KronosGEXCalculator(ticker)
    today = datetime.now().strftime('%Y-%m-%d')

    gex = calc.calculate_gex_for_date(today, dte_max=7)

    if gex:
        return {
            'spot_price': gex.spot_price,
            'net_gex': gex.net_gex,
            'gex_normalized': gex.gex_normalized,
            'gex_regime': gex.gex_regime,
            'call_wall': gex.call_wall,
            'put_wall': gex.put_wall,
            'flip_point': gex.flip_point,
            'distance_to_flip_pct': gex.distance_to_flip_pct,
            'between_walls': gex.between_walls,
            'above_call_wall': gex.above_call_wall,
            'below_put_wall': gex.below_put_wall,
        }
    else:
        print(f"Warning: No GEX data for today ({today})")
        return None


def main():
    parser = argparse.ArgumentParser(description='Predict market direction from GEX')
    parser.add_argument('--ticker', type=str, default='SPY', help='Ticker symbol')
    parser.add_argument('--vix', type=float, default=20.0, help='Current VIX level')
    parser.add_argument('--model', type=str, default='models/gex_directional_model.joblib',
                        help='Path to trained model')
    parser.add_argument('--prev-close', type=float, default=None, help='Previous day close')
    args = parser.parse_args()

    print("=" * 60)
    print("GEX DIRECTIONAL PREDICTION")
    print("=" * 60)

    # Load model
    from quant.gex_directional_ml import GEXDirectionalPredictor

    predictor = GEXDirectionalPredictor(ticker=args.ticker)

    try:
        predictor.load_model(args.model)
    except FileNotFoundError:
        print(f"\nModel not found at: {args.model}")
        print("Train a model first with: python scripts/train_gex_directional.py")
        return

    # Get current GEX
    print(f"\nFetching GEX data for {args.ticker}...")
    gex_data = get_current_gex(args.ticker)

    if not gex_data:
        print("Could not fetch GEX data. Using sample data for demo...")
        gex_data = {
            'spot_price': 590.0,
            'net_gex': 2.5e9,
            'gex_normalized': 7200,
            'gex_regime': 'POSITIVE',
            'call_wall': 595.0,
            'put_wall': 585.0,
            'flip_point': 588.0,
            'distance_to_flip_pct': 0.34,
            'between_walls': True,
            'above_call_wall': False,
            'below_put_wall': False,
        }

    # Display GEX structure
    print("\n" + "-" * 60)
    print("CURRENT GEX STRUCTURE")
    print("-" * 60)
    print(f"  Spot Price:     ${gex_data['spot_price']:.2f}")
    print(f"  GEX Regime:     {gex_data['gex_regime']}")
    print(f"  Net GEX:        ${gex_data['net_gex']/1e9:.2f}B")
    print(f"  Call Wall:      ${gex_data['call_wall']:.2f}")
    print(f"  Put Wall:       ${gex_data['put_wall']:.2f}")
    print(f"  Flip Point:     ${gex_data['flip_point']:.2f}")
    print(f"  Between Walls:  {gex_data['between_walls']}")
    print(f"  VIX:            {args.vix}")

    # Make prediction
    prediction = predictor.predict(
        gex_data=gex_data,
        vix=args.vix,
        prev_close=args.prev_close
    )

    # Display prediction
    print("\n" + "=" * 60)
    print("PREDICTION")
    print("=" * 60)

    direction_emoji = {
        'BULLISH': '🟢',
        'BEARISH': '🔴',
        'FLAT': '⚪'
    }

    emoji = direction_emoji.get(prediction.direction.value, '')
    print(f"\n  Direction:   {emoji} {prediction.direction.value}")
    print(f"  Confidence:  {prediction.confidence:.1%}")

    print("\n  Probabilities:")
    for direction, prob in sorted(prediction.probabilities.items(), key=lambda x: -x[1]):
        bar = '█' * int(prob * 20)
        print(f"    {direction:<10} {prob:>5.1%} {bar}")

    # Trading signal
    print("\n" + "-" * 60)
    print("TRADING SIGNAL")
    print("-" * 60)

    if prediction.confidence > 0.6:
        if prediction.direction.value == 'BULLISH':
            print("  Signal: LONG (High confidence bullish pattern)")
        elif prediction.direction.value == 'BEARISH':
            print("  Signal: SHORT (High confidence bearish pattern)")
        else:
            print("  Signal: NEUTRAL (High confidence flat pattern)")
    else:
        print("  Signal: NO TRADE (Low confidence - pattern unclear)")

    print("\n" + "=" * 60)


if __name__ == '__main__':
    main()
