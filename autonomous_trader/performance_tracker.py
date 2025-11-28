"""
Performance Tracker Mixin - Equity Snapshots and Statistics

This module handles all performance tracking including:
- Equity snapshots for P&L time series
- Strategy stats updates from live trades
- Trade activity logging
- Strike and Greeks performance logging
- Spread width performance logging
- Performance reporting
"""

import pandas as pd
import logging
from datetime import datetime
from typing import Dict
from zoneinfo import ZoneInfo
from database_adapter import get_connection

logger = logging.getLogger('autonomous_paper_trader.performance_tracker')

# Central Time timezone
CENTRAL_TZ = ZoneInfo("America/Chicago")

# Import strategy stats if available
try:
    from strategy_stats import update_strategy_stats, log_change
    STRATEGY_STATS_AVAILABLE = True
except ImportError:
    STRATEGY_STATS_AVAILABLE = False
    logger.warning("Strategy Stats not available for feedback loop")


class PerformanceTrackerMixin:
    """
    Mixin class providing performance tracking functionality.

    Requires the following attributes from the main class:
    - get_config(key): Method to get configuration values
    - _get_vix(): Method to get current VIX
    """

    def _update_strategy_stats_from_trade(
        self,
        strategy_name: str,
        pnl_pct: float,
        is_win: bool
    ):
        """
        Update centralized strategy_stats.json from live trading results.

        This creates a FEEDBACK LOOP:
        1. Live trade closes -> results recorded in autonomous_closed_trades
        2. This method queries all trades for the strategy
        3. Calculates updated win rate, expectancy, etc.
        4. Updates strategy_stats.json
        5. Future trades use updated stats for Kelly sizing
        """
        if not STRATEGY_STATS_AVAILABLE:
            logger.debug("Strategy stats not available, skipping feedback loop")
            return

        try:
            # Need at least 5 trades to update stats
            conn = get_connection()
            c = conn.cursor()

            # Normalize strategy name for matching
            core_strategy = strategy_name.upper().replace(' ', '_')
            if ':' in core_strategy:
                core_strategy = core_strategy.split(':')[-1].strip()

            # Query all closed trades for this strategy
            c.execute("""
                SELECT realized_pnl_pct
                FROM autonomous_closed_trades
                WHERE UPPER(REPLACE(strategy, ' ', '_')) LIKE %s
                ORDER BY exit_date DESC, exit_time DESC
            """, (f'%{core_strategy}%',))

            results = c.fetchall()
            conn.close()

            if len(results) < 5:
                logger.debug(f"Strategy stats not updated - only {len(results)} trades (need 5+)")
                return

            # Calculate stats from closed trades
            pnl_pcts = [float(r[0] or 0) for r in results]
            wins = [p for p in pnl_pcts if p > 0]
            losses = [p for p in pnl_pcts if p <= 0]

            total_trades = len(pnl_pcts)
            win_rate = len(wins) / total_trades if total_trades > 0 else 0.5
            avg_win = sum(wins) / len(wins) if wins else 0
            avg_loss = abs(sum(losses) / len(losses)) if losses else 0

            # Calculate expectancy
            expectancy = (win_rate * avg_win) + ((1 - win_rate) * -avg_loss)

            # Calculate Sharpe (simplified)
            if len(pnl_pcts) > 1:
                avg_return = sum(pnl_pcts) / len(pnl_pcts)
                variance = sum((p - avg_return) ** 2 for p in pnl_pcts) / len(pnl_pcts)
                std_dev = variance ** 0.5
                sharpe = (avg_return / std_dev * (252 ** 0.5)) if std_dev > 0 else 0
            else:
                sharpe = 0

            # Create backtest-compatible results dict
            live_results = {
                'strategy_name': f"SPY_{core_strategy}",
                'start_date': 'live_trading',
                'end_date': datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d'),
                'total_trades': total_trades,
                'winning_trades': len(wins),
                'losing_trades': len(losses),
                'win_rate': win_rate * 100,
                'avg_win_pct': avg_win,
                'avg_loss_pct': -avg_loss,
                'expectancy_pct': expectancy,
                'sharpe_ratio': sharpe,
                'total_return_pct': sum(pnl_pcts)
            }

            # Update using strategy_stats system
            update_strategy_stats(f"SPY_{core_strategy}", live_results)

            # Log the change
            log_change(
                category='SPY_LIVE_TRADING_FEEDBACK',
                item=f"SPY_{core_strategy}",
                old_value=f"trades={total_trades-1}",
                new_value=f"trades={total_trades}, WR={win_rate:.1%}, expectancy={expectancy:.2f}%",
                reason=f"Updated from SPY live trade (P&L: {pnl_pct:+.1f}%)"
            )

            logger.info(f"Strategy stats updated for {core_strategy}: "
                       f"{total_trades} trades, {win_rate:.1%} WR, {expectancy:.2f}% expectancy")

        except Exception as e:
            logger.warning(f"Failed to update strategy stats from trade: {e}")

    def _log_trade_activity(self, action_type: str, symbol: str, details: str,
                            position_id: int = None, pnl_impact: float = None,
                            success: bool = True, error_message: str = None):
        """Log activity to autonomous_trade_activity table"""
        try:
            conn = get_connection()
            c = conn.cursor()
            now = datetime.now(CENTRAL_TZ)

            c.execute("""
                INSERT INTO autonomous_trade_activity (
                    activity_date, activity_time, activity_timestamp,
                    action_type, symbol, details, position_id,
                    pnl_impact, success, error_message
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                now.strftime('%Y-%m-%d'),
                now.strftime('%H:%M:%S'),
                now.strftime('%Y-%m-%d %H:%M:%S'),
                action_type,
                symbol,
                details,
                position_id,
                pnl_impact,
                success,
                error_message
            ))

            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Failed to log trade activity: {e}")

    def _create_equity_snapshot(self):
        """Create a snapshot of current equity for P&L time series graphing"""
        try:
            conn = get_connection()
            c = conn.cursor()
            now = datetime.now(CENTRAL_TZ)

            # Get performance data
            perf = self.get_performance()

            # Get daily returns for Sharpe calculation
            c.execute("""
                SELECT snapshot_date, account_value
                FROM autonomous_equity_snapshots
                ORDER BY snapshot_date DESC, snapshot_time DESC
                LIMIT 30
            """)
            snapshots = c.fetchall()

            # Calculate Sharpe ratio (annualized)
            sharpe_ratio = 0.0
            if len(snapshots) >= 2:
                daily_returns = []
                for i in range(len(snapshots) - 1):
                    if snapshots[i+1][1] and snapshots[i+1][1] > 0:
                        ret = (float(snapshots[i][1]) - float(snapshots[i+1][1])) / float(snapshots[i+1][1])
                        daily_returns.append(ret)

                if daily_returns:
                    import numpy as np
                    avg_return = np.mean(daily_returns)
                    std_return = np.std(daily_returns)
                    if std_return > 0:
                        sharpe_ratio = (avg_return / std_return) * np.sqrt(252)

            # Calculate max drawdown
            max_drawdown_pct = 0.0
            if snapshots:
                peak = float(perf.get('starting_capital', 1000000))
                for s in reversed(snapshots):
                    val = float(s[1]) if s[1] else peak
                    if val > peak:
                        peak = val
                    drawdown = (peak - val) / peak * 100 if peak > 0 else 0
                    if drawdown > max_drawdown_pct:
                        max_drawdown_pct = drawdown

            # Get today's P&L
            today_str = now.strftime('%Y-%m-%d')
            c.execute("""
                SELECT COALESCE(SUM(realized_pnl), 0)
                FROM autonomous_closed_trades
                WHERE exit_date = %s
            """, (today_str,))
            daily_realized = c.fetchone()[0] or 0

            c.execute("""
                SELECT COALESCE(SUM(unrealized_pnl), 0)
                FROM autonomous_open_positions
            """)
            daily_unrealized = c.fetchone()[0] or 0
            daily_pnl = float(daily_realized) + float(daily_unrealized)

            # Calculate daily return %
            starting = float(perf.get('starting_capital', 1000000))
            daily_return_pct = (daily_pnl / starting * 100) if starting > 0 else 0

            # Insert snapshot
            c.execute("""
                INSERT INTO autonomous_equity_snapshots (
                    snapshot_date, snapshot_time, snapshot_timestamp,
                    starting_capital, total_realized_pnl, total_unrealized_pnl,
                    account_value, daily_pnl, daily_return_pct, total_return_pct,
                    max_drawdown_pct, sharpe_ratio, open_positions_count,
                    total_trades, winning_trades, losing_trades, win_rate
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                now.strftime('%Y-%m-%d'),
                now.strftime('%H:%M:%S'),
                now.strftime('%Y-%m-%d %H:%M:%S'),
                perf.get('starting_capital', 1000000),
                perf.get('realized_pnl', 0),
                perf.get('unrealized_pnl', 0),
                perf.get('current_value', 1000000),
                daily_pnl,
                daily_return_pct,
                perf.get('return_pct', 0),
                max_drawdown_pct,
                sharpe_ratio,
                perf.get('open_positions', 0),
                perf.get('total_trades', 0),
                perf.get('winning_trades', 0),
                perf.get('losing_trades', 0),
                perf.get('win_rate', 0)
            ))

            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Failed to create equity snapshot: {e}")

    def get_performance(self) -> Dict:
        """Get trading performance stats from tables"""
        conn = get_connection()

        # Get closed trades from dedicated table
        closed = pd.read_sql_query("""
            SELECT * FROM autonomous_closed_trades
            ORDER BY exit_date DESC, exit_time DESC
        """, conn)

        # Get open positions from dedicated table
        open_pos = pd.read_sql_query("""
            SELECT * FROM autonomous_open_positions
        """, conn)

        conn.close()

        capital = float(self.get_config('capital') or 1000000)
        total_realized = closed['realized_pnl'].fillna(0).sum() if not closed.empty else 0
        total_unrealized = open_pos['unrealized_pnl'].fillna(0).sum() if not open_pos.empty else 0
        total_realized = float(total_realized) if not pd.isna(total_realized) else 0
        total_unrealized = float(total_unrealized) if not pd.isna(total_unrealized) else 0
        total_pnl = total_realized + total_unrealized
        current_value = capital + total_pnl

        win_rate = 0
        winning_trades = 0
        losing_trades = 0
        if not closed.empty:
            winners = closed[closed['realized_pnl'] > 0]
            losers = closed[closed['realized_pnl'] <= 0]
            winning_trades = len(winners)
            losing_trades = len(losers)
            win_rate = (winning_trades / len(closed) * 100)

        total_trades = len(closed) + len(open_pos)

        return {
            'starting_capital': capital,
            'current_value': current_value,
            'total_pnl': total_pnl,
            'realized_pnl': float(total_realized),
            'unrealized_pnl': float(total_unrealized),
            'return_pct': (total_pnl / capital * 100) if capital > 0 else 0,
            'total_trades': total_trades,
            'closed_trades': len(closed),
            'open_positions': len(open_pos),
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate
        }

    def _log_spread_width_performance(self, position_id: int):
        """
        Log spread width performance for iron condors and other multi-leg strategies
        Called when a spread position is closed to track effectiveness of different wing widths
        """
        conn = None
        try:
            conn = get_connection()
            c = conn.cursor()

            # Get position details from closed trades
            c.execute("""
                SELECT action, strategy, entry_date, entry_time, entry_price,
                       entry_spot_price, exit_date, exit_time, exit_price,
                       realized_pnl, strike, expiration_date, contracts,
                       entry_net_gex, gex_regime
                FROM autonomous_closed_trades
                WHERE id = %s
            """, (position_id,))

            pos = c.fetchone()
            if not pos:
                return

            (action, strategy, entry_date, entry_time, entry_price, entry_spot,
             exit_date, exit_time, exit_price, realized_pnl, strike,
             expiration_date, contracts, entry_net_gex, gex_regime) = pos

            # Only log for iron condors
            if action != 'IRON_CONDOR':
                return

            # Calculate iron condor strikes based on standard parameters
            spot = entry_spot if entry_spot else strike
            wing_width = 5  # Standard wing width from code
            range_width = spot * 0.06  # 6% from spot

            # Round to nearest $5
            call_sell_strike = round((spot + range_width) / 5) * 5
            call_buy_strike = call_sell_strike + wing_width
            put_sell_strike = round((spot - range_width) / 5) * 5
            put_buy_strike = put_sell_strike - wing_width

            # Calculate distances from spot
            short_call_distance_pct = ((call_sell_strike - spot) / spot) * 100
            long_call_distance_pct = ((call_buy_strike - spot) / spot) * 100
            short_put_distance_pct = ((put_sell_strike - spot) / spot) * 100
            long_put_distance_pct = ((put_buy_strike - spot) / spot) * 100

            # Calculate hold time
            entry_dt = datetime.strptime(f"{entry_date} {entry_time}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=CENTRAL_TZ)
            exit_dt = datetime.strptime(f"{exit_date} {exit_time}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=CENTRAL_TZ)
            hold_time_hours = int((exit_dt - entry_dt).total_seconds() / 3600)

            # Calculate DTE
            exp_dt = datetime.strptime(str(expiration_date), "%Y-%m-%d").replace(tzinfo=CENTRAL_TZ)
            dte = (exp_dt - entry_dt).days

            # Calculate performance metrics
            pnl_dollars = realized_pnl * contracts
            entry_credit_total = entry_price * contracts * 100
            pnl_pct = (pnl_dollars / entry_credit_total * 100) if entry_credit_total > 0 else 0

            # Get current VIX if available
            vix = self._get_vix() if hasattr(self, '_get_vix') else None

            # Determine win/loss
            win = 1 if realized_pnl > 0 else 0

            # Insert into spread_width_performance table
            c.execute("""
                INSERT INTO spread_width_performance (
                    timestamp, strategy_name, spread_type,
                    short_strike_call, long_strike_call, short_strike_put, long_strike_put,
                    call_spread_width_points, put_spread_width_points,
                    short_call_distance_pct, long_call_distance_pct,
                    short_put_distance_pct, long_put_distance_pct,
                    spot_price, dte, vix_current, net_gex,
                    entry_credit, exit_cost, pnl_pct, pnl_dollars,
                    win, hold_time_hours
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d %H:%M:%S'),
                strategy,
                'iron_condor',
                call_sell_strike,
                call_buy_strike,
                put_sell_strike,
                put_buy_strike,
                wing_width,
                wing_width,
                short_call_distance_pct,
                long_call_distance_pct,
                short_put_distance_pct,
                long_put_distance_pct,
                spot,
                dte,
                vix,
                entry_net_gex,
                entry_price,
                exit_price,
                pnl_pct,
                pnl_dollars,
                win,
                hold_time_hours
            ))

            conn.commit()

            print(f"Logged spread width performance for position {position_id}: "
                  f"Wing Width=${wing_width}, P&L=${pnl_dollars:.2f}, Win={bool(win)}")

        except Exception as e:
            print(f"Failed to log spread width performance: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if conn:
                conn.close()

    def _log_strike_and_greeks_performance(self, trade: Dict, option_data: Dict, gex_data: Dict,
                                          exp_date: str, vix_current: float, regime_result: Dict = None):
        """
        Log detailed strike and Greeks performance data for optimizer intelligence
        """
        try:
            conn = get_connection()
            c = conn.cursor()
            now = datetime.now(CENTRAL_TZ)

            spot_price = gex_data.get('spot_price', 0)
            strike = trade['strike']

            # Calculate strike distance percentage
            strike_distance_pct = ((strike - spot_price) / spot_price) * 100

            # Determine moneyness
            option_type = trade['option_type']
            if option_type == 'CALL':
                if abs(strike - spot_price) / spot_price < 0.005:
                    moneyness = 'ATM'
                elif strike > spot_price:
                    moneyness = 'OTM'
                else:
                    moneyness = 'ITM'
            else:  # PUT
                if abs(strike - spot_price) / spot_price < 0.005:
                    moneyness = 'ATM'
                elif strike < spot_price:
                    moneyness = 'OTM'
                else:
                    moneyness = 'ITM'

            # Calculate DTE
            try:
                exp_datetime = datetime.strptime(exp_date, '%Y-%m-%d').replace(tzinfo=CENTRAL_TZ)
                dte = (exp_datetime - now).days
            except (ValueError, TypeError):
                dte = 0

            # Determine VIX regime
            if vix_current < 15:
                vix_regime = 'low'
            elif vix_current < 25:
                vix_regime = 'normal'
            else:
                vix_regime = 'high'

            # Get Greeks from option_data (if available)
            delta = option_data.get('delta', option_data.get('greeks', {}).get('delta', 0))
            gamma = option_data.get('gamma', option_data.get('greeks', {}).get('gamma', 0))
            theta = option_data.get('theta', option_data.get('greeks', {}).get('theta', 0))
            vega = option_data.get('vega', option_data.get('greeks', {}).get('vega', 0))

            # Get pattern type from regime or trade
            pattern_type = 'NONE'
            if regime_result:
                pattern_type = regime_result.get('pattern_type', 'NONE')
            elif 'liberation' in trade.get('strategy', '').lower():
                pattern_type = 'LIBERATION'
            elif 'false floor' in trade.get('reasoning', '').lower():
                pattern_type = 'FALSE_FLOOR'

            # Get gamma regime
            net_gex = gex_data.get('net_gex', 0)
            if net_gex > 0:
                gamma_regime = 'positive'
            elif net_gex < 0:
                gamma_regime = 'negative'
            else:
                gamma_regime = 'neutral'

            # Log strike performance
            c.execute("""
                INSERT INTO strike_performance (
                    timestamp, strategy_name, strike_distance_pct, strike_absolute,
                    spot_price, strike_type, moneyness, delta, gamma, theta, vega,
                    dte, vix_current, vix_regime, net_gex, gamma_regime,
                    pnl_pct, win, pattern_type, confidence_score
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                now.strftime('%Y-%m-%d %H:%M:%S'),
                trade['strategy'],
                strike_distance_pct,
                strike,
                spot_price,
                option_type,
                moneyness,
                delta,
                gamma,
                theta,
                vega,
                dte,
                vix_current,
                vix_regime,
                net_gex,
                gamma_regime,
                0.0,  # P&L will be updated on exit
                0,    # Win will be updated on exit
                pattern_type,
                trade.get('confidence', 0)
            ))

            # Log Greeks performance
            c.execute("""
                INSERT INTO greeks_performance (
                    timestamp, strategy_name, vix_regime,
                    entry_delta, entry_gamma, entry_theta, entry_vega,
                    exit_delta, exit_gamma, exit_theta, exit_vega,
                    delta_pnl, gamma_pnl, theta_pnl, vega_pnl,
                    total_pnl_pct, win, dte, net_gex
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                now.strftime('%Y-%m-%d %H:%M:%S'),
                trade['strategy'],
                vix_regime,
                delta,
                gamma,
                theta,
                vega,
                0.0, 0.0, 0.0, 0.0,  # Exit Greeks will be updated on exit
                0.0, 0.0, 0.0, 0.0,  # Greek contributions will be calculated on exit
                0.0,  # Total P&L will be updated on exit
                0,    # Win will be updated on exit
                dte,
                net_gex
            ))

            # Determine DTE bucket
            if dte <= 3:
                dte_bucket = '0-3'
            elif dte <= 7:
                dte_bucket = '4-7'
            elif dte <= 14:
                dte_bucket = '8-14'
            elif dte <= 30:
                dte_bucket = '15-30'
            else:
                dte_bucket = '30+'

            # Log DTE performance
            c.execute("""
                INSERT INTO dte_performance (
                    timestamp, strategy_name, dte, dte_bucket,
                    vix_regime, entry_price, exit_price, pnl_pct, win,
                    entry_theta, exit_theta, theta_decay_efficiency,
                    entry_time, exit_time, holding_hours
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                now.strftime('%Y-%m-%d %H:%M:%S'),
                trade['strategy'],
                dte,
                dte_bucket,
                vix_regime,
                option_data.get('ask', 0),
                0.0,  # Exit price will be updated on exit
                0.0,  # P&L will be updated on exit
                0,    # Win will be updated on exit
                theta,
                0.0,  # Exit theta will be updated on exit
                0.0,  # Theta efficiency will be calculated on exit
                now.strftime('%Y-%m-%d %H:%M:%S'),
                None,  # Exit time will be updated on exit
                0.0    # Holding hours will be calculated on exit
            ))

            conn.commit()
            conn.close()

            print(f"Strike & Greeks performance logged: {moneyness} {strike_distance_pct:.1f}% strike, delta={delta:.3f}, DTE={dte}")

        except Exception as e:
            print(f"Failed to log strike/Greeks performance: {e}")
