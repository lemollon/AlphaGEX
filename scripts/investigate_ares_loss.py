#!/usr/bin/env python3
"""
ARES Loss Investigation Script
==============================

Run this script on the Render server to pull yesterday's ARES and PEGASUS trades
for comparative analysis of IC widths and outcomes.

Usage:
    python scripts/investigate_ares_loss.py [--date YYYY-MM-DD]

Example:
    python scripts/investigate_ares_loss.py --date 2026-02-03
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CENTRAL_TZ = ZoneInfo("America/Chicago")

def get_connection():
    """Get database connection"""
    try:
        from database_adapter import get_connection
        return get_connection()
    except Exception as e:
        print(f"ERROR: Could not connect to database: {e}")
        sys.exit(1)


def get_ares_trades(conn, target_date: str) -> list:
    """Get all ARES trades for a specific date"""
    c = conn.cursor()

    # Try with all columns first, fall back to basic if migration columns missing
    try:
        c.execute("""
            SELECT
                position_id,
                ticker,
                expiration,
                underlying_at_entry,
                vix_at_entry,
                expected_move,
                put_short_strike,
                put_long_strike,
                call_short_strike,
                call_long_strike,
                spread_width,
                total_credit,
                put_wall,
                call_wall,
                gex_regime,
                oracle_advice,
                oracle_win_probability,
                oracle_confidence,
                status,
                close_reason,
                realized_pnl,
                open_time,
                close_time,
                contracts,
                max_loss
            FROM ares_positions
            WHERE DATE(open_time::timestamptz AT TIME ZONE 'America/Chicago') = %s
            ORDER BY open_time
        """, (target_date,))

        columns = [
            'position_id', 'ticker', 'expiration', 'underlying_at_entry', 'vix_at_entry',
            'expected_move', 'put_short_strike', 'put_long_strike', 'call_short_strike',
            'call_long_strike', 'spread_width', 'total_credit', 'put_wall', 'call_wall',
            'gex_regime', 'oracle_advice', 'oracle_win_probability', 'oracle_confidence',
            'status', 'close_reason', 'realized_pnl', 'open_time', 'close_time',
            'contracts', 'max_loss'
        ]
    except Exception as e:
        print(f"  Note: Using basic columns (extended columns not migrated): {e}")
        conn.rollback()  # Reset transaction after error
        c.execute("""
            SELECT
                position_id,
                ticker,
                expiration,
                underlying_at_entry,
                vix_at_entry,
                expected_move,
                put_short_strike,
                put_long_strike,
                call_short_strike,
                call_long_strike,
                spread_width,
                total_credit,
                put_wall,
                call_wall,
                gex_regime,
                NULL as oracle_advice,
                oracle_confidence as oracle_win_probability,
                oracle_confidence,
                status,
                close_reason,
                realized_pnl,
                open_time,
                close_time,
                contracts,
                max_loss
            FROM ares_positions
            WHERE DATE(open_time::timestamptz AT TIME ZONE 'America/Chicago') = %s
            ORDER BY open_time
        """, (target_date,))

        columns = [
            'position_id', 'ticker', 'expiration', 'underlying_at_entry', 'vix_at_entry',
            'expected_move', 'put_short_strike', 'put_long_strike', 'call_short_strike',
            'call_long_strike', 'spread_width', 'total_credit', 'put_wall', 'call_wall',
            'gex_regime', 'oracle_advice', 'oracle_win_probability', 'oracle_confidence',
            'status', 'close_reason', 'realized_pnl', 'open_time', 'close_time',
            'contracts', 'max_loss'
        ]

    trades = []
    for row in c.fetchall():
        trade = dict(zip(columns, row))
        # Convert datetime to string for JSON serialization
        if trade['open_time']:
            trade['open_time'] = trade['open_time'].isoformat()
        if trade['close_time']:
            trade['close_time'] = trade['close_time'].isoformat()
        if trade['expiration']:
            trade['expiration'] = str(trade['expiration'])
        trades.append(trade)

    return trades


def get_pegasus_trades(conn, target_date: str) -> list:
    """Get all PEGASUS trades for a specific date"""
    c = conn.cursor()

    # Try with all columns first, fall back to basic if migration columns missing
    try:
        c.execute("""
            SELECT
                position_id,
                ticker,
                expiration,
                underlying_at_entry,
                vix_at_entry,
                expected_move,
                put_short_strike,
                put_long_strike,
                call_short_strike,
                call_long_strike,
                spread_width,
                total_credit,
                put_wall,
                call_wall,
                gex_regime,
                oracle_advice,
                oracle_win_probability,
                oracle_confidence,
                status,
                close_reason,
                realized_pnl,
                open_time,
                close_time,
                contracts,
                max_loss
            FROM pegasus_positions
            WHERE DATE(open_time::timestamptz AT TIME ZONE 'America/Chicago') = %s
            ORDER BY open_time
        """, (target_date,))

        columns = [
            'position_id', 'ticker', 'expiration', 'underlying_at_entry', 'vix_at_entry',
            'expected_move', 'put_short_strike', 'put_long_strike', 'call_short_strike',
            'call_long_strike', 'spread_width', 'total_credit', 'put_wall', 'call_wall',
            'gex_regime', 'oracle_advice', 'oracle_win_probability', 'oracle_confidence',
            'status', 'close_reason', 'realized_pnl', 'open_time', 'close_time',
            'contracts', 'max_loss'
        ]
    except Exception as e:
        print(f"  Note: Using basic columns for PEGASUS: {e}")
        conn.rollback()
        c.execute("""
            SELECT
                position_id,
                ticker,
                expiration,
                underlying_at_entry,
                vix_at_entry,
                expected_move,
                put_short_strike,
                put_long_strike,
                call_short_strike,
                call_long_strike,
                spread_width,
                total_credit,
                put_wall,
                call_wall,
                gex_regime,
                NULL as oracle_advice,
                oracle_confidence as oracle_win_probability,
                oracle_confidence,
                status,
                close_reason,
                realized_pnl,
                open_time,
                close_time,
                contracts,
                max_loss
            FROM pegasus_positions
            WHERE DATE(open_time::timestamptz AT TIME ZONE 'America/Chicago') = %s
            ORDER BY open_time
        """, (target_date,))

        columns = [
            'position_id', 'ticker', 'expiration', 'underlying_at_entry', 'vix_at_entry',
            'expected_move', 'put_short_strike', 'put_long_strike', 'call_short_strike',
            'call_long_strike', 'spread_width', 'total_credit', 'put_wall', 'call_wall',
            'gex_regime', 'oracle_advice', 'oracle_win_probability', 'oracle_confidence',
            'status', 'close_reason', 'realized_pnl', 'open_time', 'close_time',
            'contracts', 'max_loss'
        ]

    trades = []
    for row in c.fetchall():
        trade = dict(zip(columns, row))
        if trade['open_time']:
            trade['open_time'] = trade['open_time'].isoformat()
        if trade['close_time']:
            trade['close_time'] = trade['close_time'].isoformat()
        if trade['expiration']:
            trade['expiration'] = str(trade['expiration'])
        trades.append(trade)

    return trades


def get_market_high_low(conn, target_date: str, ticker: str = "SPY") -> dict:
    """Get market high/low for context (from equity snapshots if available)"""
    # This is a placeholder - we may not have intraday high/low in DB
    # But we can calculate the range from expected_move
    return {"high": None, "low": None}


def analyze_trade(trade: dict) -> dict:
    """Calculate key metrics for a trade"""
    spot = float(trade['underlying_at_entry'] or 0)
    expected_move = float(trade['expected_move'] or 0)
    put_short = float(trade['put_short_strike'] or 0)
    call_short = float(trade['call_short_strike'] or 0)
    put_wall = float(trade['put_wall'] or 0)
    call_wall = float(trade['call_wall'] or 0)

    analysis = {
        'position_id': trade['position_id'],
        'ticker': trade['ticker'],
        'spot_at_entry': spot,
        'expected_move': expected_move,
        'vix_at_entry': float(trade['vix_at_entry'] or 0),
    }

    if spot > 0 and expected_move > 0:
        # Calculate how many SDs away each strike is
        put_distance = spot - put_short
        call_distance = call_short - spot

        analysis['put_sd_multiplier'] = round(put_distance / expected_move, 2) if expected_move > 0 else 0
        analysis['call_sd_multiplier'] = round(call_distance / expected_move, 2) if expected_move > 0 else 0
        analysis['avg_sd_multiplier'] = round((analysis['put_sd_multiplier'] + analysis['call_sd_multiplier']) / 2, 2)

        # Calculate percentage distance from spot
        analysis['put_distance_pct'] = round((put_distance / spot) * 100, 2)
        analysis['call_distance_pct'] = round((call_distance / spot) * 100, 2)

        # Compare with GEX walls if available
        if put_wall > 0:
            wall_put_distance = spot - put_wall
            analysis['put_wall_sd'] = round(wall_put_distance / expected_move, 2) if expected_move > 0 else 0
            analysis['put_vs_wall'] = 'WIDER' if put_short < put_wall else 'TIGHTER'
        else:
            analysis['put_wall_sd'] = None
            analysis['put_vs_wall'] = 'NO_WALL'

        if call_wall > 0:
            wall_call_distance = call_wall - spot
            analysis['call_wall_sd'] = round(wall_call_distance / expected_move, 2) if expected_move > 0 else 0
            analysis['call_vs_wall'] = 'WIDER' if call_short > call_wall else 'TIGHTER'
        else:
            analysis['call_wall_sd'] = None
            analysis['call_vs_wall'] = 'NO_WALL'
    else:
        analysis['put_sd_multiplier'] = None
        analysis['call_sd_multiplier'] = None
        analysis['avg_sd_multiplier'] = None
        analysis['put_distance_pct'] = None
        analysis['call_distance_pct'] = None

    # Outcome
    analysis['status'] = trade['status']
    analysis['close_reason'] = trade['close_reason']
    analysis['realized_pnl'] = float(trade['realized_pnl'] or 0)
    analysis['max_loss'] = float(trade['max_loss'] or 0)
    analysis['contracts'] = trade['contracts']
    analysis['is_loss'] = analysis['realized_pnl'] < 0

    # Oracle context
    analysis['oracle_advice'] = trade['oracle_advice']
    analysis['oracle_win_prob'] = float(trade['oracle_win_probability'] or 0)
    analysis['gex_regime'] = trade['gex_regime']

    return analysis


def print_analysis(bot_name: str, trades: list, analyses: list):
    """Print analysis results"""
    print(f"\n{'='*80}")
    print(f" {bot_name} TRADES ANALYSIS")
    print(f"{'='*80}")

    if not trades:
        print(f"\n  No trades found for {bot_name}")
        return

    print(f"\n  Total trades: {len(trades)}")

    total_pnl = sum(a['realized_pnl'] for a in analyses)
    winning = sum(1 for a in analyses if a['realized_pnl'] > 0)
    losing = sum(1 for a in analyses if a['realized_pnl'] < 0)

    print(f"  Total P&L: ${total_pnl:,.2f}")
    print(f"  Winners: {winning}, Losers: {losing}")

    for i, (trade, analysis) in enumerate(zip(trades, analyses), 1):
        print(f"\n  {'─'*76}")
        print(f"  Trade #{i}: {analysis['position_id']}")
        print(f"  {'─'*76}")

        print(f"  Ticker: {analysis['ticker']}")
        print(f"  Spot at Entry: ${analysis['spot_at_entry']:,.2f}")
        print(f"  VIX: {analysis['vix_at_entry']:.1f}")
        print(f"  Expected Move (1 SD): ${analysis['expected_move']:.2f}")

        print(f"\n  STRIKES:")
        print(f"    Put Short: ${float(trade['put_short_strike'] or 0):.2f} ({analysis['put_sd_multiplier']} SD away)")
        print(f"    Call Short: ${float(trade['call_short_strike'] or 0):.2f} ({analysis['call_sd_multiplier']} SD away)")
        print(f"    Average SD Multiplier: {analysis['avg_sd_multiplier']}")

        if analysis.get('put_wall_sd'):
            print(f"\n  GEX WALLS:")
            print(f"    Put Wall: ${float(trade['put_wall'] or 0):.2f} ({analysis['put_wall_sd']} SD) - Strike is {analysis['put_vs_wall']}")
            print(f"    Call Wall: ${float(trade['call_wall'] or 0):.2f} ({analysis['call_wall_sd']} SD) - Strike is {analysis['call_vs_wall']}")

        print(f"\n  ORACLE:")
        print(f"    Advice: {analysis['oracle_advice']}")
        print(f"    Win Probability: {analysis['oracle_win_prob']*100:.1f}%")
        print(f"    GEX Regime: {analysis['gex_regime']}")

        print(f"\n  OUTCOME:")
        print(f"    Status: {analysis['status']}")
        print(f"    Close Reason: {analysis['close_reason']}")
        print(f"    Contracts: {analysis['contracts']}")
        print(f"    Realized P&L: ${analysis['realized_pnl']:,.2f}")

        if analysis['is_loss']:
            print(f"    ⚠️  THIS WAS A LOSING TRADE")
            if analysis['avg_sd_multiplier'] and analysis['avg_sd_multiplier'] < 1.0:
                print(f"    🔴 ISSUE: SD multiplier {analysis['avg_sd_multiplier']} < 1.0 (strikes too tight!)")
            elif analysis['avg_sd_multiplier'] and analysis['avg_sd_multiplier'] < 1.2:
                print(f"    🟡 WARNING: SD multiplier {analysis['avg_sd_multiplier']} < 1.2 (recommend wider)")


def main():
    parser = argparse.ArgumentParser(description='Investigate ARES loss')
    parser.add_argument('--date', type=str, help='Date to analyze (YYYY-MM-DD)')
    parser.add_argument('--json', action='store_true', help='Output as JSON for further analysis')
    args = parser.parse_args()

    # Default to yesterday
    if args.date:
        target_date = args.date
    else:
        yesterday = datetime.now(CENTRAL_TZ) - timedelta(days=1)
        target_date = yesterday.strftime('%Y-%m-%d')

    print(f"\n{'='*80}")
    print(f" ARES LOSS INVESTIGATION - {target_date}")
    print(f"{'='*80}")

    conn = get_connection()

    try:
        # Get trades
        ares_trades = get_ares_trades(conn, target_date)
        pegasus_trades = get_pegasus_trades(conn, target_date)

        # Analyze
        ares_analyses = [analyze_trade(t) for t in ares_trades]
        pegasus_analyses = [analyze_trade(t) for t in pegasus_trades]

        if args.json:
            output = {
                'date': target_date,
                'ares': {
                    'trades': ares_trades,
                    'analyses': ares_analyses,
                },
                'pegasus': {
                    'trades': pegasus_trades,
                    'analyses': pegasus_analyses,
                }
            }
            print(json.dumps(output, indent=2, default=str))
        else:
            print_analysis("ARES", ares_trades, ares_analyses)
            print_analysis("PEGASUS", pegasus_trades, pegasus_analyses)

            # Summary comparison
            print(f"\n{'='*80}")
            print(f" COMPARISON SUMMARY")
            print(f"{'='*80}")

            if ares_analyses and pegasus_analyses:
                ares_avg_sd = sum(a['avg_sd_multiplier'] or 0 for a in ares_analyses) / len(ares_analyses) if ares_analyses else 0
                pegasus_avg_sd = sum(a['avg_sd_multiplier'] or 0 for a in pegasus_analyses) / len(pegasus_analyses) if pegasus_analyses else 0

                print(f"\n  ARES Average SD Multiplier: {ares_avg_sd:.2f}")
                print(f"  PEGASUS Average SD Multiplier: {pegasus_avg_sd:.2f}")

                ares_pnl = sum(a['realized_pnl'] for a in ares_analyses)
                pegasus_pnl = sum(a['realized_pnl'] for a in pegasus_analyses)

                print(f"\n  ARES Total P&L: ${ares_pnl:,.2f}")
                print(f"  PEGASUS Total P&L: ${pegasus_pnl:,.2f}")

                if ares_avg_sd < pegasus_avg_sd and ares_pnl < pegasus_pnl:
                    print(f"\n  💡 INSIGHT: ARES had tighter strikes ({ares_avg_sd:.2f} SD) than PEGASUS ({pegasus_avg_sd:.2f} SD)")
                    print(f"              and ARES lost while PEGASUS won. This suggests ARES needs WIDER strikes.")

            # Detailed strike analysis for losses
            ares_losses = [a for a in ares_analyses if a['is_loss']]
            if ares_losses:
                print(f"\n  {'─'*76}")
                print(f"  ARES LOSS ANALYSIS:")
                print(f"  {'─'*76}")
                for loss in ares_losses:
                    print(f"\n  Position: {loss['position_id']}")
                    print(f"  - Spot: ${loss['spot_at_entry']:.2f}, EM: ${loss['expected_move']:.2f}")
                    print(f"  - Put Strike SD: {loss['put_sd_multiplier']}")
                    print(f"  - Call Strike SD: {loss['call_sd_multiplier']}")
                    print(f"  - Loss: ${loss['realized_pnl']:.2f}")

                    # Calculate what strike would have been safe
                    if loss['expected_move'] and loss['spot_at_entry']:
                        safe_put = loss['spot_at_entry'] - (1.5 * loss['expected_move'])
                        safe_call = loss['spot_at_entry'] + (1.5 * loss['expected_move'])
                        print(f"  - At 1.5 SD, strikes would be: Put ${safe_put:.0f}, Call ${safe_call:.0f}")

    finally:
        conn.close()

    print(f"\n{'='*80}")
    print(f" END OF ANALYSIS")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
