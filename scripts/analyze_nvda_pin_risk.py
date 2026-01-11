#!/usr/bin/env python3
"""
NVDA Pin Risk Analysis Script

Analyzes NVDA options data to determine pinning risk for long call holders.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from zoneinfo import ZoneInfo

CENTRAL_TZ = ZoneInfo("America/Chicago")


def analyze_nvda_pin_risk():
    """Analyze NVDA for pinning risk"""
    print("=" * 70)
    print("NVDA PIN RISK ANALYSIS")
    print(f"Analysis Time: {datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d %H:%M:%S CT')}")
    print("=" * 70)

    # Try to get GEX data
    try:
        from data.gex_calculator import TradierGEXCalculator
        gex_calc = TradierGEXCalculator(sandbox=False)  # Use production for real data

        print("\n[1] Fetching NVDA GEX Data...")
        gex_data = gex_calc.get_gex('NVDA')

        if 'error' in gex_data:
            print(f"Error fetching GEX: {gex_data['error']}")
            return None

        print(f"\n[2] NVDA GAMMA EXPOSURE (GEX) ANALYSIS")
        print("-" * 50)
        print(f"Current Price:  ${gex_data.get('spot_price', 0):.2f}")
        print(f"Net GEX:        ${gex_data.get('net_gex', 0):.4f}B")
        print(f"Call GEX:       ${gex_data.get('call_gex', 0):.4f}B")
        print(f"Put GEX:        ${gex_data.get('put_gex', 0):.4f}B")
        print(f"Call Wall:      ${gex_data.get('call_wall', 0):.2f}")
        print(f"Put Wall:       ${gex_data.get('put_wall', 0):.2f}")
        print(f"Gamma Flip:     ${gex_data.get('gamma_flip', gex_data.get('flip_point', 0)):.2f}")
        print(f"Max Pain:       ${gex_data.get('max_pain', 0):.2f}")
        print(f"Data Source:    {gex_data.get('data_source', 'unknown')}")

        # Analyze pinning conditions
        spot = gex_data.get('spot_price', 0)
        max_pain = gex_data.get('max_pain', 0)
        call_wall = gex_data.get('call_wall', 0)
        put_wall = gex_data.get('put_wall', 0)
        flip_point = gex_data.get('gamma_flip', gex_data.get('flip_point', 0))
        net_gex = gex_data.get('net_gex', 0)

        print(f"\n[3] PIN RISK ASSESSMENT")
        print("-" * 50)

        # Distance calculations
        if max_pain > 0 and spot > 0:
            dist_to_max_pain = ((spot - max_pain) / spot) * 100
            print(f"Distance to Max Pain:  {dist_to_max_pain:+.2f}% (${spot - max_pain:+.2f})")

        if call_wall > 0 and spot > 0:
            dist_to_call_wall = ((call_wall - spot) / spot) * 100
            print(f"Distance to Call Wall: {dist_to_call_wall:+.2f}% (${call_wall - spot:+.2f})")

        if put_wall > 0 and spot > 0:
            dist_to_put_wall = ((spot - put_wall) / spot) * 100
            print(f"Distance to Put Wall:  {dist_to_put_wall:+.2f}% (${spot - put_wall:+.2f})")

        if flip_point > 0 and spot > 0:
            dist_to_flip = ((spot - flip_point) / spot) * 100
            print(f"Distance to Flip:      {dist_to_flip:+.2f}% (${spot - flip_point:+.2f})")

        print(f"\n[4] GAMMA REGIME ANALYSIS")
        print("-" * 50)

        # Determine gamma regime
        if flip_point > 0:
            if spot > flip_point:
                regime = "POSITIVE GAMMA (Above Flip)"
                regime_desc = "Dealers are LONG gamma - they BUY dips, SELL rallies. Price moves get DAMPENED."
            else:
                regime = "NEGATIVE GAMMA (Below Flip)"
                regime_desc = "Dealers are SHORT gamma - they SELL dips, BUY rallies. Price moves get AMPLIFIED."
        else:
            regime = "UNKNOWN"
            regime_desc = "Unable to determine gamma regime"

        print(f"Current Regime: {regime}")
        print(f"Meaning:        {regime_desc}")

        print(f"\n[5] PINNING PROBABILITY ASSESSMENT")
        print("-" * 50)

        # Calculate pin probability factors
        pin_factors = []
        pin_score = 0

        # Factor 1: Distance to max pain
        if max_pain > 0 and spot > 0:
            pct_from_max_pain = abs(spot - max_pain) / spot * 100
            if pct_from_max_pain < 1.0:
                pin_factors.append(f"VERY CLOSE to max pain ({pct_from_max_pain:.2f}%) - HIGH pin risk")
                pin_score += 30
            elif pct_from_max_pain < 2.0:
                pin_factors.append(f"Close to max pain ({pct_from_max_pain:.2f}%) - MODERATE pin risk")
                pin_score += 20
            elif pct_from_max_pain < 3.0:
                pin_factors.append(f"Near max pain ({pct_from_max_pain:.2f}%) - SOME pin risk")
                pin_score += 10
            else:
                pin_factors.append(f"Away from max pain ({pct_from_max_pain:.2f}%) - LOW pin risk from max pain")

        # Factor 2: Positive gamma = price compression
        if net_gex > 0:
            pin_factors.append(f"Positive GEX ({net_gex:.4f}B) - Dealers dampen moves = higher pin probability")
            pin_score += 25
        elif net_gex < 0:
            pin_factors.append(f"Negative GEX ({net_gex:.4f}B) - Dealers amplify moves = lower pin probability")
            pin_score -= 10

        # Factor 3: Between walls
        if put_wall > 0 and call_wall > 0 and spot > 0:
            if put_wall < spot < call_wall:
                wall_range = call_wall - put_wall
                wall_range_pct = (wall_range / spot) * 100
                pin_factors.append(f"Price BETWEEN walls (range: {wall_range_pct:.1f}%) - Contained environment")
                pin_score += 15
            elif spot >= call_wall:
                pin_factors.append(f"Price AT or ABOVE call wall - Resistance overhead")
                pin_score += 10
            elif spot <= put_wall:
                pin_factors.append(f"Price AT or BELOW put wall - Support below")
                pin_score += 10

        # Factor 4: Friday/expiration approaching
        today = datetime.now(CENTRAL_TZ)
        days_to_friday = (4 - today.weekday()) % 7
        if days_to_friday == 0:
            pin_factors.append("TODAY is expiration day - HIGHEST pin risk")
            pin_score += 30
        elif days_to_friday == 1:
            pin_factors.append("Tomorrow is expiration - HIGH pin gravity")
            pin_score += 20
        elif days_to_friday <= 2:
            pin_factors.append(f"{days_to_friday} days to weekly expiry - Increasing pin gravity")
            pin_score += 10

        for factor in pin_factors:
            print(f"  • {factor}")

        print(f"\n  PIN RISK SCORE: {pin_score}/100")

        if pin_score >= 60:
            pin_assessment = "HIGH PIN RISK"
            recommendation = "Long calls are DANGEROUS - price likely to stay range-bound near max pain"
        elif pin_score >= 40:
            pin_assessment = "MODERATE PIN RISK"
            recommendation = "Long calls face headwinds - need catalyst to break through gamma walls"
        elif pin_score >= 20:
            pin_assessment = "LOW-MODERATE PIN RISK"
            recommendation = "Some pin gravity but breakout possible with volume/news"
        else:
            pin_assessment = "LOW PIN RISK"
            recommendation = "Gamma positioning doesn't favor pinning - directional moves possible"

        print(f"  ASSESSMENT: {pin_assessment}")
        print(f"  RECOMMENDATION: {recommendation}")

        print(f"\n[6] TRADING IMPLICATIONS FOR LONG CALLS")
        print("-" * 50)

        # Specific advice for long call holders
        if call_wall > 0 and spot > 0:
            upside_to_wall = ((call_wall - spot) / spot) * 100
            print(f"• Upside to call wall (resistance): {upside_to_wall:+.2f}%")
            if upside_to_wall < 2:
                print(f"  WARNING: Very close to call wall - expect resistance")
            elif upside_to_wall < 5:
                print(f"  CAUTION: Approaching call wall resistance")

        if net_gex > 0:
            print(f"• Positive gamma environment = Dealers will SELL rallies")
            print(f"  This creates natural resistance to upward moves")

        if max_pain > 0 and spot > max_pain:
            print(f"• Price ABOVE max pain - gravitational pull DOWN toward ${max_pain:.2f}")
        elif max_pain > 0 and spot < max_pain:
            print(f"• Price BELOW max pain - gravitational pull UP toward ${max_pain:.2f}")

        print(f"\n[7] WHAT WOULD BREAK THE PIN")
        print("-" * 50)
        print("For long calls to work, NVDA needs:")
        if call_wall > 0:
            print(f"  1. Break above call wall at ${call_wall:.2f} with volume")
        print(f"  2. Significant news catalyst (earnings, product announcement)")
        print(f"  3. Broader market momentum (SPY/QQQ rallying)")
        if net_gex > 0:
            print(f"  4. GEX to flip negative (dealer short gamma = amplify moves)")
        print(f"  5. Decay of options expiring this week (reduces pin gravity)")

        return gex_data

    except ImportError as e:
        print(f"\nImport Error: {e}")
        print("Make sure you're running from the AlphaGEX project root")
        return None
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    analyze_nvda_pin_risk()
