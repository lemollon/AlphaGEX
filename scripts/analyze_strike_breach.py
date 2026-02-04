#!/usr/bin/env python3
"""
Strike Breach Analysis Script
=============================

Analyze whether strikes were breached and by how much.
Helps understand if IC widths were sufficient.

Usage:
    python scripts/analyze_strike_breach.py [--date YYYY-MM-DD]

Example:
    python scripts/analyze_strike_breach.py --date 2026-02-03
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from decimal import Decimal

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


def get_losing_trades(conn, target_date: str) -> list:
    """Get all losing trades from both bots"""
    trades = []

    # ARES losses
    c = conn.cursor()
    c.execute("""
        SELECT
            'ARES' as bot,
            position_id,
            ticker,
            underlying_at_entry,
            expected_move,
            vix_at_entry,
            put_short_strike,
            put_long_strike,
            call_short_strike,
            call_long_strike,
            put_wall,
            call_wall,
            gex_regime,
            realized_pnl,
            close_reason,
            open_time,
            close_time,
            contracts,
            total_credit,
            spread_width
        FROM ares_positions
        WHERE DATE(open_time::timestamptz AT TIME ZONE 'America/Chicago') = %s
          AND realized_pnl < 0
        ORDER BY realized_pnl ASC
    """, (target_date,))

    columns = [
        'bot', 'position_id', 'ticker', 'underlying_at_entry', 'expected_move',
        'vix_at_entry', 'put_short_strike', 'put_long_strike', 'call_short_strike',
        'call_long_strike', 'put_wall', 'call_wall', 'gex_regime', 'realized_pnl',
        'close_reason', 'open_time', 'close_time', 'contracts', 'total_credit', 'spread_width'
    ]

    for row in c.fetchall():
        trade = dict(zip(columns, row))
        trades.append(trade)

    # PEGASUS losses
    c.execute("""
        SELECT
            'PEGASUS' as bot,
            position_id,
            ticker,
            underlying_at_entry,
            expected_move,
            vix_at_entry,
            put_short_strike,
            put_long_strike,
            call_short_strike,
            call_long_strike,
            put_wall,
            call_wall,
            gex_regime,
            realized_pnl,
            close_reason,
            open_time,
            close_time,
            contracts,
            total_credit,
            spread_width
        FROM pegasus_positions
        WHERE DATE(open_time::timestamptz AT TIME ZONE 'America/Chicago') = %s
          AND realized_pnl < 0
        ORDER BY realized_pnl ASC
    """, (target_date,))

    for row in c.fetchall():
        trade = dict(zip(columns, row))
        trades.append(trade)

    return trades


def get_winning_trades(conn, target_date: str) -> list:
    """Get all winning trades from both bots for comparison"""
    trades = []

    # ARES wins
    c = conn.cursor()
    c.execute("""
        SELECT
            'ARES' as bot,
            position_id,
            underlying_at_entry,
            expected_move,
            put_short_strike,
            call_short_strike,
            realized_pnl
        FROM ares_positions
        WHERE DATE(open_time::timestamptz AT TIME ZONE 'America/Chicago') = %s
          AND realized_pnl >= 0
    """, (target_date,))

    for row in c.fetchall():
        trades.append({
            'bot': row[0],
            'position_id': row[1],
            'underlying_at_entry': float(row[2] or 0),
            'expected_move': float(row[3] or 0),
            'put_short_strike': float(row[4] or 0),
            'call_short_strike': float(row[5] or 0),
            'realized_pnl': float(row[6] or 0),
        })

    # PEGASUS wins
    c.execute("""
        SELECT
            'PEGASUS' as bot,
            position_id,
            underlying_at_entry,
            expected_move,
            put_short_strike,
            call_short_strike,
            realized_pnl
        FROM pegasus_positions
        WHERE DATE(open_time::timestamptz AT TIME ZONE 'America/Chicago') = %s
          AND realized_pnl >= 0
    """, (target_date,))

    for row in c.fetchall():
        trades.append({
            'bot': row[0],
            'position_id': row[1],
            'underlying_at_entry': float(row[2] or 0),
            'expected_move': float(row[3] or 0),
            'put_short_strike': float(row[4] or 0),
            'call_short_strike': float(row[5] or 0),
            'realized_pnl': float(row[6] or 0),
        })

    return trades


def float_val(v):
    """Safely convert to float"""
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    return float(v)


def analyze_loss(trade: dict) -> dict:
    """Analyze a losing trade"""
    spot = float_val(trade['underlying_at_entry'])
    em = float_val(trade['expected_move'])
    put_short = float_val(trade['put_short_strike'])
    call_short = float_val(trade['call_short_strike'])
    put_wall = float_val(trade['put_wall'])
    call_wall = float_val(trade['call_wall'])
    loss = float_val(trade['realized_pnl'])
    credit = float_val(trade['total_credit'])
    width = float_val(trade['spread_width'])
    contracts = trade['contracts'] or 1

    analysis = {
        'bot': trade['bot'],
        'position_id': trade['position_id'],
        'ticker': trade['ticker'],
        'spot_at_entry': spot,
        'expected_move': em,
        'vix': float_val(trade['vix_at_entry']),
        'loss': loss,
        'close_reason': trade['close_reason'],
    }

    if spot > 0 and em > 0:
        # Calculate SD multipliers used
        put_sd = (spot - put_short) / em if put_short > 0 else 0
        call_sd = (call_short - spot) / em if call_short > 0 else 0

        analysis['put_short'] = put_short
        analysis['call_short'] = call_short
        analysis['put_sd'] = round(put_sd, 2)
        analysis['call_sd'] = round(call_sd, 2)
        analysis['avg_sd'] = round((put_sd + call_sd) / 2, 2)

        # Determine which side was breached
        close_reason = (trade['close_reason'] or '').upper()
        if 'PUT' in close_reason or put_sd < call_sd:
            analysis['breached_side'] = 'PUT'
            # Estimate how far past the strike price went
            if loss < 0 and width > 0:
                # Max loss would be (width - credit) * 100 * contracts
                max_loss = (width - credit) * 100 * contracts
                loss_ratio = abs(loss) / max_loss if max_loss > 0 else 0
                analysis['loss_ratio'] = round(loss_ratio, 2)
                analysis['max_loss'] = max_loss
        elif 'CALL' in close_reason:
            analysis['breached_side'] = 'CALL'
            if loss < 0 and width > 0:
                max_loss = (width - credit) * 100 * contracts
                loss_ratio = abs(loss) / max_loss if max_loss > 0 else 0
                analysis['loss_ratio'] = round(loss_ratio, 2)
                analysis['max_loss'] = max_loss
        else:
            analysis['breached_side'] = 'UNKNOWN'
            analysis['loss_ratio'] = 0

        # GEX wall analysis
        if put_wall > 0:
            analysis['put_wall_sd'] = round((spot - put_wall) / em, 2)
            analysis['put_vs_wall'] = 'INSIDE' if put_short > put_wall else 'OUTSIDE'
        else:
            analysis['put_wall_sd'] = None
            analysis['put_vs_wall'] = 'NO_WALL'

        if call_wall > 0:
            analysis['call_wall_sd'] = round((call_wall - spot) / em, 2)
            analysis['call_vs_wall'] = 'INSIDE' if call_short < call_wall else 'OUTSIDE'
        else:
            analysis['call_wall_sd'] = None
            analysis['call_vs_wall'] = 'NO_WALL'

        # What SD would have been needed to avoid this loss?
        # If put was breached and market moved down, we need wider puts
        if analysis['breached_side'] == 'PUT':
            # The put side needed to be wider
            needed_sd = put_sd + (1 - analysis.get('loss_ratio', 0.5))  # Rough estimate
            analysis['needed_put_sd'] = round(needed_sd, 2)
            analysis['recommendation'] = f"Use {analysis['needed_put_sd']} SD or wider for puts"
        elif analysis['breached_side'] == 'CALL':
            needed_sd = call_sd + (1 - analysis.get('loss_ratio', 0.5))
            analysis['needed_call_sd'] = round(needed_sd, 2)
            analysis['recommendation'] = f"Use {analysis['needed_call_sd']} SD or wider for calls"

    return analysis


def main():
    parser = argparse.ArgumentParser(description='Analyze strike breaches')
    parser.add_argument('--date', type=str, help='Date to analyze (YYYY-MM-DD)')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    args = parser.parse_args()

    if args.date:
        target_date = args.date
    else:
        yesterday = datetime.now(CENTRAL_TZ) - timedelta(days=1)
        target_date = yesterday.strftime('%Y-%m-%d')

    print(f"\n{'='*80}")
    print(f" STRIKE BREACH ANALYSIS - {target_date}")
    print(f"{'='*80}")

    conn = get_connection()

    try:
        losing_trades = get_losing_trades(conn, target_date)
        winning_trades = get_winning_trades(conn, target_date)

        loss_analyses = [analyze_loss(t) for t in losing_trades]

        if args.json:
            output = {
                'date': target_date,
                'losing_trades': losing_trades,
                'loss_analyses': loss_analyses,
                'winning_trades': winning_trades,
            }
            print(json.dumps(output, indent=2, default=str))
            return

        print(f"\n  Total Losing Trades: {len(losing_trades)}")
        print(f"  Total Winning Trades: {len(winning_trades)}")

        if not losing_trades:
            print(f"\n  ✅ No losing trades on {target_date}")
        else:
            # Summary stats
            total_loss = sum(float_val(t['realized_pnl']) for t in losing_trades)
            ares_losses = [a for a in loss_analyses if a['bot'] == 'ARES']
            pegasus_losses = [a for a in loss_analyses if a['bot'] == 'PEGASUS']

            print(f"\n  Total Loss: ${total_loss:,.2f}")
            print(f"  ARES Losses: {len(ares_losses)}")
            print(f"  PEGASUS Losses: {len(pegasus_losses)}")

            # Detailed analysis
            for analysis in loss_analyses:
                print(f"\n  {'─'*76}")
                print(f"  🔴 {analysis['bot']} LOSS: {analysis['position_id']}")
                print(f"  {'─'*76}")

                print(f"  Ticker: {analysis['ticker']}")
                print(f"  Spot at Entry: ${analysis['spot_at_entry']:,.2f}")
                print(f"  VIX: {analysis['vix']:.1f}")
                print(f"  Expected Move (1 SD): ${analysis['expected_move']:.2f}")
                print(f"  Loss: ${analysis['loss']:,.2f}")
                print(f"  Close Reason: {analysis['close_reason']}")

                if analysis.get('put_sd'):
                    print(f"\n  STRIKE ANALYSIS:")
                    print(f"    Put Short: ${analysis['put_short']:.2f} ({analysis['put_sd']} SD from spot)")
                    print(f"    Call Short: ${analysis['call_short']:.2f} ({analysis['call_sd']} SD from spot)")
                    print(f"    Average SD: {analysis['avg_sd']}")

                if analysis.get('breached_side'):
                    print(f"\n  BREACH ANALYSIS:")
                    print(f"    Breached Side: {analysis['breached_side']}")
                    if analysis.get('loss_ratio'):
                        print(f"    Loss Ratio: {analysis['loss_ratio']*100:.0f}% of max loss")

                if analysis.get('put_wall_sd'):
                    print(f"\n  GEX WALL COMPARISON:")
                    print(f"    Put Wall: {analysis['put_wall_sd']} SD ({analysis['put_vs_wall']} GEX wall)")
                    print(f"    Call Wall: {analysis.get('call_wall_sd', 'N/A')} SD ({analysis.get('call_vs_wall', 'N/A')})")

                if analysis.get('recommendation'):
                    print(f"\n  💡 RECOMMENDATION: {analysis['recommendation']}")

            # Compare winning vs losing SD multipliers
            print(f"\n  {'='*76}")
            print(f"  SD MULTIPLIER COMPARISON")
            print(f"  {'='*76}")

            if winning_trades:
                win_sds = []
                for t in winning_trades:
                    spot = float_val(t['underlying_at_entry'])
                    em = float_val(t['expected_move'])
                    put_s = float_val(t['put_short_strike'])
                    call_s = float_val(t['call_short_strike'])
                    if spot > 0 and em > 0 and put_s > 0 and call_s > 0:
                        avg_sd = ((spot - put_s) / em + (call_s - spot) / em) / 2
                        win_sds.append(avg_sd)

                if win_sds:
                    avg_win_sd = sum(win_sds) / len(win_sds)
                    print(f"\n  Winning Trades Average SD: {avg_win_sd:.2f}")

            if loss_analyses:
                loss_sds = [a['avg_sd'] for a in loss_analyses if a.get('avg_sd')]
                if loss_sds:
                    avg_loss_sd = sum(loss_sds) / len(loss_sds)
                    print(f"  Losing Trades Average SD: {avg_loss_sd:.2f}")

                    if winning_trades and win_sds:
                        if avg_loss_sd < avg_win_sd:
                            print(f"\n  ⚠️  INSIGHT: Losing trades had TIGHTER strikes ({avg_loss_sd:.2f} SD)")
                            print(f"              than winning trades ({avg_win_sd:.2f} SD)")
                            print(f"              Consider using minimum {avg_win_sd:.1f} SD for safety")

    finally:
        conn.close()

    print(f"\n{'='*80}")
    print(f" END OF ANALYSIS")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
