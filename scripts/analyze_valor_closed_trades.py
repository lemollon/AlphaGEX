#!/usr/bin/env python3
"""
VALOR Closed Trade Analysis
============================

Pulls real closed trades from the database and analyzes:
1. Why losses are bigger than wins
2. What patterns lead to losses
3. MFE/MAE analysis (how much profit we had before losing)
4. Stop type performance comparison

Run: python scripts/analyze_valor_closed_trades.py
"""

import sys
import os
from datetime import datetime, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from database_adapter import get_connection
except ImportError:
    print("ERROR: Cannot import database_adapter. Run from project root.")
    sys.exit(1)


def analyze_closed_trades():
    """Pull and analyze all HERACLES closed trades."""

    print("\n" + "="*80)
    print("VALOR (HERACLES) CLOSED TRADE ANALYSIS")
    print("="*80)

    try:
        conn = get_connection()
        c = conn.cursor()

        # Get all closed trades
        c.execute("""
            SELECT
                position_id,
                direction,
                contracts,
                entry_price,
                exit_price,
                realized_pnl,
                gamma_regime,
                close_reason,
                open_time,
                close_time,
                hold_duration_minutes,
                high_price_since_entry,
                low_price_since_entry,
                stop_type,
                stop_points_used,
                vix_at_entry,
                atr_at_entry,
                win_probability,
                signal_confidence,
                trade_reasoning
            FROM heracles_closed_trades
            ORDER BY close_time DESC
            LIMIT 100
        """)

        trades = c.fetchall()

        if not trades:
            print("\n❌ No closed trades found in heracles_closed_trades table")
            return

        print(f"\n📊 Found {len(trades)} closed trades\n")

        # Analysis containers
        wins = []
        losses = []
        loss_details = []

        for trade in trades:
            (position_id, direction, contracts, entry_price, exit_price,
             realized_pnl, gamma_regime, close_reason, open_time, close_time,
             hold_duration, high_price, low_price, stop_type, stop_points_used,
             vix, atr, win_prob, confidence, reasoning) = trade

            # Convert Decimals to float
            entry_price = float(entry_price) if entry_price else 0
            exit_price = float(exit_price) if exit_price else 0
            realized_pnl = float(realized_pnl) if realized_pnl else 0
            high_price = float(high_price) if high_price else entry_price
            low_price = float(low_price) if low_price else entry_price
            vix = float(vix) if vix else 0
            atr = float(atr) if atr else 0
            win_prob = float(win_prob) if win_prob else 0
            stop_points_used = float(stop_points_used) if stop_points_used else 0

            # Calculate MFE/MAE (Maximum Favorable/Adverse Excursion)
            if direction == 'LONG':
                mfe_pts = high_price - entry_price  # Best profit we had
                mae_pts = entry_price - low_price   # Worst drawdown
                exit_pts = exit_price - entry_price  # Final result in points
            else:  # SHORT
                mfe_pts = entry_price - low_price   # Best profit we had
                mae_pts = high_price - entry_price  # Worst drawdown
                exit_pts = entry_price - exit_price  # Final result in points

            trade_data = {
                'position_id': position_id,
                'direction': direction,
                'contracts': contracts,
                'entry_price': entry_price,
                'exit_price': exit_price,
                'realized_pnl': realized_pnl,
                'gamma_regime': gamma_regime,
                'close_reason': close_reason,
                'open_time': open_time,
                'close_time': close_time,
                'hold_duration': hold_duration,
                'mfe_pts': mfe_pts,
                'mae_pts': mae_pts,
                'exit_pts': exit_pts,
                'stop_type': stop_type,
                'stop_points_used': stop_points_used,
                'vix': vix,
                'atr': atr,
                'win_prob': win_prob,
            }

            if realized_pnl > 0:
                wins.append(trade_data)
            else:
                losses.append(trade_data)

                # Detailed loss analysis
                loss_analysis = analyze_loss(trade_data)
                loss_details.append({**trade_data, 'analysis': loss_analysis})

        # Print summary
        print("-" * 80)
        print("SUMMARY")
        print("-" * 80)
        total_wins = len(wins)
        total_losses = len(losses)
        total_trades = total_wins + total_losses
        win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0

        total_win_pnl = sum(t['realized_pnl'] for t in wins)
        total_loss_pnl = sum(t['realized_pnl'] for t in losses)
        net_pnl = total_win_pnl + total_loss_pnl

        avg_win = total_win_pnl / total_wins if total_wins > 0 else 0
        avg_loss = total_loss_pnl / total_losses if total_losses > 0 else 0

        print(f"Total Trades: {total_trades}")
        print(f"Wins: {total_wins} ({win_rate:.1f}%)")
        print(f"Losses: {total_losses} ({100-win_rate:.1f}%)")
        print(f"")
        print(f"Total Win P&L: ${total_win_pnl:,.2f}")
        print(f"Total Loss P&L: ${total_loss_pnl:,.2f}")
        print(f"Net P&L: ${net_pnl:,.2f}")
        print(f"")
        print(f"Avg Win: ${avg_win:.2f}")
        print(f"Avg Loss: ${avg_loss:.2f}")
        print(f"Win/Loss Ratio: {abs(avg_win/avg_loss):.2f}x" if avg_loss != 0 else "N/A")

        # Loss analysis detail
        print("\n" + "-" * 80)
        print("LOSS ANALYSIS DETAIL")
        print("-" * 80)

        for i, loss in enumerate(loss_details[:10], 1):  # Show last 10 losses
            print(f"\n🔴 LOSS #{i}: ${loss['realized_pnl']:.2f}")
            print(f"   Position: {loss['position_id'][:12]}...")
            print(f"   Direction: {loss['direction']} | Regime: {loss['gamma_regime']}")
            print(f"   Entry: {loss['entry_price']:.2f} | Exit: {loss['exit_price']:.2f}")
            print(f"   Stop Type: {loss['stop_type']} | Stop Distance: {loss['stop_points_used']:.1f} pts")
            print(f"   Close Reason: {loss['close_reason']}")
            print(f"   Hold Duration: {loss['hold_duration']} min")
            print(f"   MFE: {loss['mfe_pts']:.2f} pts (${loss['mfe_pts'] * 5 * loss['contracts']:.2f})")
            print(f"   MAE: {loss['mae_pts']:.2f} pts (${loss['mae_pts'] * 5 * loss['contracts']:.2f})")
            print(f"   VIX: {loss['vix']:.1f} | ATR: {loss['atr']:.2f}")
            print(f"   Win Prob at Entry: {loss['win_prob']*100:.1f}%")
            print(f"   📋 ANALYSIS: {loss['analysis']}")

        # MFE/MAE Summary for losses
        print("\n" + "-" * 80)
        print("MFE/MAE ANALYSIS (Losses Only)")
        print("-" * 80)

        if losses:
            # How many losses were profitable before losing?
            profitable_before_loss = [l for l in loss_details if l['mfe_pts'] > 0.5]
            pct_profitable = len(profitable_before_loss) / len(losses) * 100

            avg_mfe = sum(l['mfe_pts'] for l in loss_details) / len(losses)
            avg_mae = sum(l['mae_pts'] for l in loss_details) / len(losses)

            print(f"Losses that were profitable first: {len(profitable_before_loss)}/{len(losses)} ({pct_profitable:.1f}%)")
            print(f"Avg MFE before loss: {avg_mfe:.2f} pts (${avg_mfe * 5:.2f}/contract)")
            print(f"Avg MAE (max drawdown): {avg_mae:.2f} pts (${avg_mae * 5:.2f}/contract)")

            if profitable_before_loss:
                print(f"\n⚠️  {len(profitable_before_loss)} trades were WINNERS that turned into LOSERS!")
                print("   These could have been saved with tighter trailing stops.")
                for l in profitable_before_loss[:5]:
                    print(f"   - {l['direction']} @ {l['entry_price']:.2f}: MFE=+{l['mfe_pts']:.2f}pts, Final={l['exit_pts']:.2f}pts, P&L=${l['realized_pnl']:.2f}")

        # Stop type analysis
        print("\n" + "-" * 80)
        print("STOP TYPE PERFORMANCE")
        print("-" * 80)

        stop_types = {}
        for t in wins + losses:
            st = t['stop_type'] or 'UNKNOWN'
            if st not in stop_types:
                stop_types[st] = {'wins': 0, 'losses': 0, 'win_pnl': 0, 'loss_pnl': 0}
            if t['realized_pnl'] > 0:
                stop_types[st]['wins'] += 1
                stop_types[st]['win_pnl'] += t['realized_pnl']
            else:
                stop_types[st]['losses'] += 1
                stop_types[st]['loss_pnl'] += t['realized_pnl']

        for st, data in sorted(stop_types.items()):
            total = data['wins'] + data['losses']
            wr = data['wins'] / total * 100 if total > 0 else 0
            net = data['win_pnl'] + data['loss_pnl']
            print(f"{st}: {total} trades, {wr:.1f}% win rate, Net P&L: ${net:,.2f}")

        # Gamma regime analysis
        print("\n" + "-" * 80)
        print("GAMMA REGIME PERFORMANCE")
        print("-" * 80)

        regimes = {}
        for t in wins + losses:
            regime = t['gamma_regime'] or 'UNKNOWN'
            if regime not in regimes:
                regimes[regime] = {'wins': 0, 'losses': 0, 'win_pnl': 0, 'loss_pnl': 0}
            if t['realized_pnl'] > 0:
                regimes[regime]['wins'] += 1
                regimes[regime]['win_pnl'] += t['realized_pnl']
            else:
                regimes[regime]['losses'] += 1
                regimes[regime]['loss_pnl'] += t['realized_pnl']

        for regime, data in sorted(regimes.items()):
            total = data['wins'] + data['losses']
            wr = data['wins'] / total * 100 if total > 0 else 0
            net = data['win_pnl'] + data['loss_pnl']
            avg_loss = data['loss_pnl'] / data['losses'] if data['losses'] > 0 else 0
            print(f"{regime}: {total} trades, {wr:.1f}% win rate, Net: ${net:,.2f}, Avg Loss: ${avg_loss:.2f}")

        # Time-based analysis
        print("\n" + "-" * 80)
        print("SESSION ANALYSIS (based on close time)")
        print("-" * 80)

        overnight_trades = []
        rth_trades = []

        for t in wins + losses:
            if t['close_time']:
                hour = t['close_time'].hour
                # Overnight: 5 PM - 4 AM CT (17:00 - 04:00)
                if hour >= 17 or hour < 4:
                    overnight_trades.append(t)
                else:
                    rth_trades.append(t)

        for session, trades in [('OVERNIGHT (5PM-4AM)', overnight_trades), ('RTH (4AM-5PM)', rth_trades)]:
            if trades:
                session_wins = [t for t in trades if t['realized_pnl'] > 0]
                session_losses = [t for t in trades if t['realized_pnl'] <= 0]
                wr = len(session_wins) / len(trades) * 100
                net = sum(t['realized_pnl'] for t in trades)
                avg_loss = sum(t['realized_pnl'] for t in session_losses) / len(session_losses) if session_losses else 0
                print(f"{session}: {len(trades)} trades, {wr:.1f}% win rate, Net: ${net:,.2f}, Avg Loss: ${avg_loss:.2f}")

        conn.close()

        # Recommendations
        print("\n" + "="*80)
        print("RECOMMENDATIONS")
        print("="*80)

        if losses:
            avg_loss_pts = sum(l['mae_pts'] for l in loss_details) / len(losses)
            profitable_before = len([l for l in loss_details if l['mfe_pts'] > 0.5])

            print(f"\n1. STOP LOSS ANALYSIS:")
            print(f"   - Average loss magnitude: {avg_loss_pts:.2f} pts (${avg_loss_pts * 5:.2f}/contract)")
            print(f"   - {profitable_before} of {len(losses)} losses ({profitable_before/len(losses)*100:.0f}%) were profitable before losing")

            if profitable_before > len(losses) * 0.3:
                print(f"   ⚠️  PROBLEM: Too many winners turning into losers!")
                print(f"   💡 SOLUTION: Consider tighter trailing activation (current: 3 pts)")

            if avg_loss > avg_win * 1.5:
                print(f"\n2. WIN/LOSS RATIO:")
                print(f"   - Avg loss (${abs(avg_loss):.2f}) is {abs(avg_loss/avg_win):.1f}x avg win (${avg_win:.2f})")
                print(f"   ⚠️  PROBLEM: Losses are too big relative to wins")
                print(f"   💡 SOLUTION: Tighter emergency stop or faster exit on reversals")

    except Exception as e:
        print(f"\n❌ Error analyzing trades: {e}")
        import traceback
        traceback.print_exc()


def analyze_loss(trade: dict) -> str:
    """Generate detailed analysis of why a trade lost."""

    reasons = []

    # Check if it was profitable before losing
    if trade['mfe_pts'] > 1.0:
        reasons.append(f"Was +{trade['mfe_pts']:.1f}pts profitable before reversing")

    # Check if stop was too wide
    if trade['mae_pts'] > 10:
        reasons.append(f"Large drawdown ({trade['mae_pts']:.1f}pts) - emergency stop hit?")

    # Check hold duration
    if trade['hold_duration'] and trade['hold_duration'] > 120:
        reasons.append(f"Held too long ({trade['hold_duration']}min)")
    elif trade['hold_duration'] and trade['hold_duration'] < 5:
        reasons.append(f"Stopped out quickly ({trade['hold_duration']}min)")

    # Check VIX conditions
    if trade['vix'] > 25:
        reasons.append(f"High VIX ({trade['vix']:.1f}) - volatile conditions")

    # Check close reason
    close_reason = trade['close_reason'] or ''
    if 'emergency' in close_reason.lower():
        reasons.append("Hit emergency stop - catastrophic move")
    elif 'trail' in close_reason.lower():
        reasons.append("Trailing stop triggered after profit")
    elif 'stop' in close_reason.lower():
        reasons.append("Regular stop hit")

    # Check regime
    if trade['gamma_regime'] == 'NEGATIVE':
        reasons.append("NEGATIVE gamma (momentum) - higher risk regime")

    if not reasons:
        reasons.append("Standard stop-out")

    return " | ".join(reasons)


if __name__ == '__main__':
    analyze_closed_trades()
