#!/usr/bin/env python3
"""
Pin Risk Analysis CLI Script

Analyzes options data for any symbol to determine pinning risk.
Uses the same PinRiskAnalyzer engine integrated into Discernment.

Usage:
    python scripts/analyze_nvda_pin_risk.py NVDA
    python scripts/analyze_nvda_pin_risk.py SPY AAPL TSLA
    python scripts/analyze_nvda_pin_risk.py --batch SPY,QQQ,NVDA,AAPL,TSLA
"""

import sys
import os
import argparse

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from zoneinfo import ZoneInfo

CENTRAL_TZ = ZoneInfo("America/Chicago")


def print_separator(char: str = "=", width: int = 70):
    print(char * width)


def print_section(title: str, char: str = "-", width: int = 50):
    print(f"\n[{title}]")
    print(char * width)


def format_pct(value: float, include_sign: bool = True) -> str:
    """Format percentage with sign"""
    if include_sign:
        return f"{value:+.2f}%"
    return f"{value:.2f}%"


def analyze_symbol(symbol: str, verbose: bool = True) -> dict:
    """Analyze pin risk for a single symbol"""
    try:
        from core.pin_risk_analyzer import get_pin_risk_analyzer

        analyzer = get_pin_risk_analyzer()
        analysis = analyzer.analyze(symbol)

        if verbose:
            print_full_analysis(analysis)

        return analysis.to_dict()

    except ImportError as e:
        print(f"\nImport Error: {e}")
        print("Make sure you're running from the AlphaGEX project root")
        print("Required: pip install pandas scipy aiohttp python-dotenv")
        return None
    except Exception as e:
        print(f"\nError analyzing {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return None


def print_full_analysis(analysis):
    """Print comprehensive pin risk analysis"""
    from core.pin_risk_analyzer import PinRiskLevel

    print_separator()
    print(f"{analysis.symbol} PIN RISK ANALYSIS")
    print(f"Analysis Time: {analysis.timestamp.strftime('%Y-%m-%d %H:%M:%S CT')}")
    print_separator()

    # Current State
    print_section("CURRENT MARKET STATE")
    print(f"Spot Price:       ${analysis.spot_price:.2f}")
    print(f"Data Sources:     {', '.join(analysis.data_sources)}")

    # Gamma Levels
    gl = analysis.gamma_levels
    print_section("GAMMA LEVELS (GEX)")
    print(f"Net GEX:          ${gl.net_gex:.4f}B")
    print(f"Call GEX:         ${gl.call_gex:.4f}B")
    print(f"Put GEX:          ${gl.put_gex:.4f}B")
    print(f"Gamma Flip:       ${gl.flip_point:.2f}")
    print(f"Call Wall:        ${gl.call_wall:.2f}")
    print(f"Put Wall:         ${gl.put_wall:.2f}")
    print(f"Max Pain:         ${gl.max_pain:.2f}")

    # Distance Metrics
    print_section("DISTANCE FROM KEY LEVELS")
    print(f"To Max Pain:      {format_pct(analysis.distance_to_max_pain_pct)} (${analysis.spot_price - gl.max_pain:+.2f})")
    print(f"To Gamma Flip:    {format_pct(analysis.distance_to_flip_pct)} (${analysis.spot_price - gl.flip_point:+.2f})")
    print(f"To Call Wall:     {format_pct(analysis.distance_to_call_wall_pct)} (${gl.call_wall - analysis.spot_price:+.2f})")
    print(f"To Put Wall:      {format_pct(analysis.distance_to_put_wall_pct)} (${analysis.spot_price - gl.put_wall:+.2f})")

    # Gamma Regime
    print_section("GAMMA REGIME ANALYSIS")
    regime_color = {
        'positive': '🟢 POSITIVE (Dampening)',
        'negative': '🔴 NEGATIVE (Amplifying)',
        'neutral': '🟡 NEUTRAL (Unstable)',
        'unknown': '⚪ UNKNOWN'
    }
    print(f"Regime:           {regime_color.get(analysis.gamma_regime.value, analysis.gamma_regime.value)}")
    print(f"\n{analysis.gamma_regime_description}")

    # Pin Risk Score
    print_section("PIN RISK ASSESSMENT")
    score = analysis.pin_risk_score
    level = analysis.pin_risk_level

    # Visual score bar
    bar_filled = int(score / 5)
    bar_empty = 20 - bar_filled
    bar = "█" * bar_filled + "░" * bar_empty

    level_emoji = {
        PinRiskLevel.HIGH: "🔴 HIGH",
        PinRiskLevel.MODERATE: "🟠 MODERATE",
        PinRiskLevel.LOW_MODERATE: "🟡 LOW-MODERATE",
        PinRiskLevel.LOW: "🟢 LOW"
    }

    print(f"Score:            [{bar}] {score}/100")
    print(f"Risk Level:       {level_emoji.get(level, level.value.upper())}")

    # Pin Factors
    print("\nContributing Factors:")
    for factor in analysis.pin_factors:
        print(f"  • {factor.description} (+{factor.score} pts)")

    # Expected Range
    print_section("EXPECTED PRICE RANGE")
    print(f"Range:            ${analysis.expected_range_low:.2f} - ${analysis.expected_range_high:.2f}")
    print(f"Range Width:      {analysis.expected_range_pct:.1f}%")

    # Expiration Timing
    print_section("EXPIRATION CONTEXT")
    if analysis.is_expiration_day:
        print("⚠️  TODAY IS EXPIRATION DAY - Maximum gamma effect")
    else:
        print(f"Days to Weekly Expiry: {analysis.days_to_weekly_expiry}")

    # Trading Implications
    print_section("TRADING IMPLICATIONS")
    for impl in analysis.trading_implications:
        outlook_emoji = {
            'favorable': '✅',
            'unfavorable': '❌',
            'neutral': '➖'
        }
        emoji = outlook_emoji.get(impl.outlook, '❓')
        print(f"\n{emoji} {impl.position_type.upper().replace('_', ' ')}: {impl.outlook.upper()}")
        print(f"   {impl.reasoning}")
        if impl.recommendation:
            print(f"   → {impl.recommendation}")

    # Long Call Specific
    print_section("LONG CALL ASSESSMENT")
    outlook_desc = {
        'dangerous': "🔴 DANGEROUS - High pin risk, dealers selling rallies",
        'challenging': "🟠 CHALLENGING - Moderate headwinds from gamma positioning",
        'favorable': "🟢 FAVORABLE - Gamma supports directional moves",
        'neutral': "🟡 NEUTRAL - No strong gamma bias"
    }
    print(outlook_desc.get(analysis.long_call_outlook, analysis.long_call_outlook))

    # What Would Break the Pin
    print_section("WHAT WOULD BREAK THE PIN")
    for i, breaker in enumerate(analysis.pin_breakers, 1):
        print(f"  {i}. {breaker}")

    # Summary
    print_section("SUMMARY", "=", 70)
    print(f"\n{analysis.summary}")

    # Warnings
    if analysis.warnings:
        print_section("WARNINGS")
        for warning in analysis.warnings:
            print(f"  ⚠️  {warning}")

    print_separator()


def analyze_batch(symbols: list, verbose: bool = False):
    """Analyze multiple symbols and display summary"""
    from core.pin_risk_analyzer import get_pin_risk_analyzer

    analyzer = get_pin_risk_analyzer()
    results = []

    print_separator()
    print("BATCH PIN RISK ANALYSIS")
    print(f"Symbols: {', '.join(symbols)}")
    print(f"Time: {datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d %H:%M:%S CT')}")
    print_separator()

    for symbol in symbols:
        try:
            analysis = analyzer.analyze(symbol)
            results.append({
                'symbol': symbol,
                'score': analysis.pin_risk_score,
                'level': analysis.pin_risk_level.value,
                'gamma': analysis.gamma_regime.value,
                'outlook': analysis.long_call_outlook,
                'price': analysis.spot_price,
                'max_pain': analysis.gamma_levels.max_pain,
                'summary': analysis.summary[:100] + '...' if len(analysis.summary) > 100 else analysis.summary
            })
            print(f"  ✓ {symbol} analyzed")
        except Exception as e:
            results.append({
                'symbol': symbol,
                'error': str(e)
            })
            print(f"  ✗ {symbol} failed: {e}")

    # Sort by score (highest first)
    results.sort(key=lambda x: x.get('score', 0), reverse=True)

    # Print summary table
    print_section("RESULTS (sorted by pin risk)")
    print(f"{'Symbol':<8} {'Score':>6} {'Level':<15} {'Gamma':<10} {'Calls':<12} {'Price':>10} {'Max Pain':>10}")
    print("-" * 85)

    for r in results:
        if 'error' in r:
            print(f"{r['symbol']:<8} {'ERROR':<60} {r['error']}")
        else:
            level_short = r['level'].replace('_', ' ').title()
            gamma_short = r['gamma'].title()
            outlook_short = r['outlook'].title() if r['outlook'] else 'N/A'
            print(f"{r['symbol']:<8} {r['score']:>5}/100 {level_short:<15} {gamma_short:<10} {outlook_short:<12} ${r['price']:>8.2f} ${r['max_pain']:>8.2f}")

    print_separator()

    # Print detailed analysis for highest risk symbol
    if results and 'error' not in results[0]:
        highest_risk = results[0]['symbol']
        print(f"\n🔍 DETAILED ANALYSIS FOR HIGHEST RISK: {highest_risk}")
        analyze_symbol(highest_risk, verbose=True)


def main():
    parser = argparse.ArgumentParser(
        description="Analyze options pin risk for stocks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/analyze_nvda_pin_risk.py NVDA
  python scripts/analyze_nvda_pin_risk.py SPY AAPL TSLA
  python scripts/analyze_nvda_pin_risk.py --batch SPY,QQQ,NVDA,AAPL,TSLA
  python scripts/analyze_nvda_pin_risk.py --batch SPY,QQQ,NVDA --quiet
        """
    )

    parser.add_argument(
        'symbols',
        nargs='*',
        help='Stock symbol(s) to analyze'
    )

    parser.add_argument(
        '--batch',
        type=str,
        help='Comma-separated list of symbols for batch analysis'
    )

    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Quiet mode - only show summary for batch analysis'
    )

    args = parser.parse_args()

    # Determine symbols to analyze
    if args.batch:
        symbols = [s.strip().upper() for s in args.batch.split(',')]
        analyze_batch(symbols, verbose=not args.quiet)
    elif args.symbols:
        symbols = [s.upper() for s in args.symbols]
        if len(symbols) == 1:
            analyze_symbol(symbols[0], verbose=True)
        else:
            analyze_batch(symbols, verbose=not args.quiet)
    else:
        # Default to NVDA if no symbol specified
        print("No symbol specified, analyzing NVDA...")
        analyze_symbol('NVDA', verbose=True)


if __name__ == "__main__":
    main()
