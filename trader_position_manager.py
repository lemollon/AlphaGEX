"""
Position Management Module for Autonomous Trading
==================================================

Extracted from autonomous_paper_trader.py to reduce class complexity.

This module handles:
- Auto-management of open positions
- Position updates (price, P&L)
- Exit condition checking (AI-powered and fallback rules)
- Position closing and trade logging

Author: AlphaGEX
Date: 2025-11-27
"""

import os
import logging
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Protocol
from zoneinfo import ZoneInfo

from database_adapter import get_connection
from trading_costs import OrderSide, SymbolType

logger = logging.getLogger(__name__)

# Central Time timezone for all timestamps
CENTRAL_TZ = ZoneInfo("America/Chicago")


class TraderInterface(Protocol):
    """Protocol defining methods required from the parent trader."""
    def log_action(self, action: str, details: str, position_id: int = None, success: bool = True) -> None: ...
    def _get_vix(self) -> float: ...
    @property
    def costs_calculator(self): ...


class PositionManager:
    """
    Manages open positions for autonomous trading.

    Responsibilities:
    - Monitor and update open positions with current prices
    - Check exit conditions (AI-powered with fallback rules)
    - Close positions and record to closed_trades table
    - Log spread width performance for optimization
    """

    def __init__(self, trader: TraderInterface, get_real_option_price_func):
        """
        Initialize position manager.

        Args:
            trader: Reference to parent trader for helper methods
            get_real_option_price_func: Function to get real option prices
        """
        self.trader = trader
        self.get_real_option_price = get_real_option_price_func

    def auto_manage_positions(self, api_client) -> List[Dict]:
        """
        AUTONOMOUS: Automatically manage and close positions based on conditions.
        Runs every time the system checks.

        Args:
            api_client: API client for market data

        Returns:
            List of actions taken (closes, updates, etc.)
        """
        conn = get_connection()
        try:
            positions = pd.read_sql_query("""
                SELECT * FROM autonomous_open_positions
                LIMIT 100
            """, conn)
        except Exception as e:
            logger.warning(f"Failed to fetch open positions: {e}")
            conn.close()
            return []
        finally:
            conn.close()

        if positions.empty:
            return []

        actions_taken = []

        for _, pos in positions.iterrows():
            try:
                # Get current SPY price
                gex_data = api_client.get_net_gamma('SPY')
                if not gex_data or gex_data.get('error'):
                    logger.warning(f"Failed to get GEX data for position {pos['id']}, skipping")
                    continue

                current_spot = gex_data.get('spot_price', 0)

                # Get current option price
                option_data = self.get_real_option_price(
                    pos['symbol'],
                    pos['strike'],
                    pos['option_type'],
                    pos['expiration_date']
                )

                if option_data.get('error'):
                    continue

                current_bid = option_data.get('bid', 0) or 0
                current_ask = option_data.get('ask', 0) or 0
                current_mid = option_data.get('mid', 0)
                if current_mid == 0 or current_mid is None:
                    current_mid = option_data.get('last', pos['entry_price']) or pos['entry_price']

                # Apply exit slippage for realistic P&L
                if current_bid > 0 and current_ask > 0:
                    exit_price, exit_slippage = self.trader.costs_calculator.calculate_entry_price(
                        bid=current_bid,
                        ask=current_ask,
                        contracts=int(pos['contracts']),
                        side=OrderSide.SELL,
                        symbol_type=SymbolType.ETF
                    )
                else:
                    exit_price = current_mid
                    exit_slippage = {}

                # Calculate P&L with exit slippage and commission
                entry_value = pos['entry_price'] * pos['contracts'] * 100
                gross_exit_value = exit_price * pos['contracts'] * 100
                exit_commission = self.trader.costs_calculator.calculate_commission(int(pos['contracts']))
                net_exit_value = gross_exit_value - exit_commission['total_commission']

                unrealized_pnl = net_exit_value - entry_value
                pnl_pct = (unrealized_pnl / entry_value * 100) if entry_value > 0 else 0

                # Update position
                self._update_position(pos['id'], exit_price, current_spot, unrealized_pnl, pnl_pct)

                # Check exit conditions
                should_exit, reason = self._check_exit_conditions(
                    pos, pnl_pct, exit_price, current_spot, gex_data
                )

                if should_exit:
                    self._close_position(pos['id'], exit_price, unrealized_pnl, reason)

                    actions_taken.append({
                        'position_id': pos['id'],
                        'strategy': pos['strategy'],
                        'action': 'CLOSE',
                        'reason': reason,
                        'pnl': unrealized_pnl,
                        'pnl_pct': pnl_pct
                    })

                    self.trader.log_action(
                        'CLOSE',
                        f"Closed {pos['strategy']}: P&L ${unrealized_pnl:+.2f} ({pnl_pct:+.1f}%) | Expiration: {pos['expiration_date']} - {reason}",
                        position_id=pos['id'],
                        success=True
                    )

            except Exception as e:
                logger.error(f"Error managing position {pos['id']}: {e}")
                continue

        return actions_taken

    def _update_position(self, position_id: int, current_price: float, current_spot: float,
                         unrealized_pnl: float, pnl_pct: float = 0) -> None:
        """
        Update position with current values in autonomous_open_positions.

        Args:
            position_id: Position ID to update
            current_price: Current option price
            current_spot: Current spot price
            unrealized_pnl: Unrealized P&L in dollars
            pnl_pct: Unrealized P&L percentage
        """
        if current_price is None or current_price < 0:
            logger.warning(f"Invalid current_price {current_price} for position {position_id}, skipping update")
            return

        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute("""
                UPDATE autonomous_open_positions
                SET current_price = %s, current_spot_price = %s, unrealized_pnl = %s,
                    unrealized_pnl_pct = %s, last_updated = NOW()
                WHERE id = %s
            """, (current_price, current_spot, unrealized_pnl, pnl_pct, position_id))
            conn.commit()
        except Exception as e:
            logger.warning(f"Failed to update position {position_id}: {e}")
        finally:
            conn.close()

    def _check_exit_conditions(self, pos: Dict, pnl_pct: float, current_price: float,
                                current_spot: float, gex_data: Dict) -> Tuple[bool, str]:
        """
        AI-POWERED EXIT STRATEGY: Flexible intelligent decision making.
        Uses Claude AI to analyze market conditions, not rigid rules.

        Args:
            pos: Position dict (from DataFrame row)
            pnl_pct: Current P&L percentage
            current_price: Current option price
            current_spot: Current spot price
            gex_data: GEX data dict

        Returns:
            Tuple of (should_exit: bool, reason: str)
        """
        # HARD STOP: -50% loss (protect capital)
        if pnl_pct <= -50:
            return True, f"HARD STOP: {pnl_pct:.1f}% loss - protecting capital"

        # EXPIRATION SAFETY: Close on expiration day
        exp_date = datetime.strptime(pos['expiration_date'], '%Y-%m-%d').replace(tzinfo=CENTRAL_TZ)
        dte = (exp_date - datetime.now(CENTRAL_TZ)).days
        if dte <= 0:
            return True, f"EXPIRATION: {dte} DTE - closing to avoid assignment"

        # AI DECISION: Everything else goes to Claude
        try:
            ai_decision = self._ai_should_close_position(pos, pnl_pct, current_price, current_spot, gex_data, dte)

            if ai_decision['should_close']:
                return True, f"AI: {ai_decision['reason']}"

            return False, ""

        except Exception as e:
            logger.warning(f"AI decision failed: {e}, using fallback rules")
            return self._fallback_exit_rules(pos, pnl_pct, dte, gex_data)

    def _ai_should_close_position(self, pos: Dict, pnl_pct: float, current_price: float,
                                   current_spot: float, gex_data: Dict, dte: int) -> Dict:
        """
        AI-POWERED DECISION: Ask Claude whether to close position.

        Args:
            pos: Position dict
            pnl_pct: Current P&L percentage
            current_price: Current option price
            current_spot: Current spot price
            gex_data: GEX data dict
            dte: Days to expiration

        Returns:
            Dict with 'should_close' (bool) and 'reason' (str)
        """
        claude_api_key = os.getenv("CLAUDE_API_KEY") or os.getenv("claude_api_key", "")

        if not claude_api_key:
            return {'should_close': False, 'reason': 'AI unavailable'}

        entry_gex = pos['entry_net_gex']
        current_gex = gex_data.get('net_gex', 0)
        entry_flip = pos['entry_flip_point']
        current_flip = gex_data.get('flip_point', 0)

        prompt = f"""You are an expert options trader managing a position. Analyze this position and decide: HOLD or CLOSE?

POSITION DETAILS:
- Strategy: {pos['strategy']}
- Action: {pos['action']}
- Strike: ${pos['strike']:.0f} {pos['option_type'].upper()}
- Entry: ${pos['entry_price']:.2f} | Current: ${current_price:.2f}
- P&L: {pnl_pct:+.1f}%
- Days to Expiration: {dte} DTE
- Contracts: {pos['contracts']}

MARKET CONDITIONS (THEN vs NOW):
Entry GEX: ${entry_gex/1e9:.2f}B | Current GEX: ${current_gex/1e9:.2f}B
Entry Flip: ${entry_flip:.2f} | Current Flip: ${current_flip:.2f}
SPY Entry: ${pos['entry_spot_price']:.2f} | Current SPY: ${current_spot:.2f}

TRADE THESIS:
{pos['trade_reasoning']}

THINK LIKE A PROFESSIONAL TRADER:
- Is the original thesis still valid?
- Has GEX regime changed significantly?
- Is this a good profit to take given time left?
- Could we let it run more?
- Is risk/reward still favorable?

RESPOND WITH EXACTLY:
DECISION: HOLD or CLOSE
REASON: [one concise sentence explaining why]

Examples:
"DECISION: CLOSE
REASON: GEX flipped from -$8B to +$2B - thesis invalidated, take +15% profit now"

"DECISION: HOLD
REASON: Thesis intact, only 2 DTE left but still 20% from profit target, let theta work"

Now analyze this position:"""

        try:
            from intelligence_and_strategies import ClaudeIntelligence
            claude = ClaudeIntelligence()

            messages = [{"role": "user", "content": prompt}]
            response = claude._call_claude_api(messages)

            if 'DECISION: CLOSE' in response.upper():
                reason_start = response.upper().find('REASON:') + 7
                reason = response[reason_start:].strip()
                reason = reason.split('\n')[0].strip()
                if len(reason) > 100:
                    reason = reason[:100] + "..."

                return {'should_close': True, 'reason': reason}
            else:
                return {'should_close': False, 'reason': 'AI recommends holding'}

        except Exception as e:
            logger.error(f"Claude API error: {e}")
            return {'should_close': False, 'reason': f'AI error: {str(e)}'}

    def _fallback_exit_rules(self, pos: Dict, pnl_pct: float, dte: int, gex_data: Dict) -> Tuple[bool, str]:
        """
        Fallback rules if AI is unavailable.

        Args:
            pos: Position dict
            pnl_pct: Current P&L percentage
            dte: Days to expiration
            gex_data: GEX data dict

        Returns:
            Tuple of (should_exit: bool, reason: str)
        """
        # Big profit
        if pnl_pct >= 40:
            return True, f"PROFIT: +{pnl_pct:.1f}% (fallback rule)"

        # Stop loss
        if pnl_pct <= -30:
            return True, f"STOP: {pnl_pct:.1f}% (fallback rule)"

        # Expiration
        if dte <= 1:
            return True, f"EXPIRING: {dte} DTE (fallback rule)"

        # GEX flip
        entry_gex = pos['entry_net_gex']
        current_gex = gex_data.get('net_gex', 0)
        if (entry_gex > 0 and current_gex < 0) or (entry_gex < 0 and current_gex > 0):
            return True, "GEX FLIP: Thesis changed (fallback rule)"

        return False, ""

    def _close_position(self, position_id: int, exit_price: float, realized_pnl: float, reason: str) -> None:
        """
        Close a position - move from open_positions to closed_trades.

        Args:
            position_id: Position ID to close
            exit_price: Exit price
            realized_pnl: Realized P&L in dollars
            reason: Exit reason
        """
        conn = get_connection()
        position_data = None

        try:
            c = conn.cursor()
            now = datetime.now(CENTRAL_TZ)

            # Get the full position data
            c.execute("""
                SELECT symbol, strategy, action, strike, option_type, expiration_date,
                       contracts, contract_symbol, entry_date, entry_time, entry_price,
                       entry_bid, entry_ask, entry_spot_price, confidence, gex_regime,
                       entry_net_gex, entry_flip_point, trade_reasoning, current_spot_price
                FROM autonomous_open_positions
                WHERE id = %s
            """, (position_id,))

            pos = c.fetchone()
            if not pos:
                logger.warning(f"Position {position_id} not found in open_positions")
                return

            (symbol, strategy, action, strike, option_type, expiration_date,
             contracts, contract_symbol, entry_date, entry_time, entry_price,
             entry_bid, entry_ask, entry_spot_price, confidence, gex_regime,
             entry_net_gex, entry_flip_point, trade_reasoning, exit_spot_price) = pos

            # Calculate P&L percentage
            entry_value = float(entry_price) * contracts * 100 if entry_price else 0
            realized_pnl_pct = (realized_pnl / entry_value * 100) if entry_value > 0 else 0

            # Calculate hold duration
            try:
                entry_dt = datetime.strptime(f"{entry_date} {entry_time}", '%Y-%m-%d %H:%M:%S')
                hold_minutes = int((now.replace(tzinfo=None) - entry_dt).total_seconds() / 60)
            except (ValueError, TypeError, AttributeError):
                logger.warning(f"Could not calculate hold duration for position {position_id}")
                hold_minutes = 0

            # Insert into closed_trades
            c.execute("""
                INSERT INTO autonomous_closed_trades (
                    symbol, strategy, action, strike, option_type, expiration_date,
                    contracts, contract_symbol, entry_date, entry_time, entry_price,
                    entry_bid, entry_ask, entry_spot_price, exit_date, exit_time,
                    exit_price, exit_spot_price, exit_reason, realized_pnl,
                    realized_pnl_pct, confidence, gex_regime, entry_net_gex,
                    entry_flip_point, trade_reasoning, hold_duration_minutes
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                symbol, strategy, action, strike, option_type, expiration_date,
                contracts, contract_symbol, entry_date, entry_time, entry_price,
                entry_bid, entry_ask, entry_spot_price,
                now.strftime('%Y-%m-%d'),
                now.strftime('%H:%M:%S'),
                exit_price,
                exit_spot_price,
                reason,
                realized_pnl,
                realized_pnl_pct,
                confidence, gex_regime, entry_net_gex, entry_flip_point,
                trade_reasoning, hold_minutes
            ))

            # Delete from open_positions
            c.execute("DELETE FROM autonomous_open_positions WHERE id = %s", (position_id,))

            conn.commit()

            position_data = {
                'symbol': symbol,
                'strategy': strategy,
                'action': action,
                'strike': strike,
                'contracts': contracts,
                'exit_price': exit_price,
                'realized_pnl': realized_pnl,
                'realized_pnl_pct': realized_pnl_pct,
                'reason': reason
            }

            # Log spread width performance if iron condor
            if action == 'IRON_CONDOR':
                self._log_spread_width_performance(position_id, pos, realized_pnl, exit_price)

        except Exception as e:
            logger.error(f"Failed to close position {position_id}: {e}")
            try:
                conn.rollback()
            except:
                pass
            return
        finally:
            conn.close()

        if position_data:
            logger.info(f"Position {position_id} closed: {position_data['strategy']} "
                       f"P&L ${position_data['realized_pnl']:+.2f} ({position_data['realized_pnl_pct']:+.1f}%)")

    def _log_spread_width_performance(self, position_id: int, pos: tuple, realized_pnl: float, exit_price: float) -> None:
        """
        Log spread width performance for iron condors.

        Args:
            position_id: Position ID
            pos: Position tuple from database
            realized_pnl: Realized P&L
            exit_price: Exit price
        """
        conn = None
        try:
            (symbol, strategy, action, strike, option_type, expiration_date,
             contracts, contract_symbol, entry_date, entry_time, entry_price,
             entry_bid, entry_ask, entry_spot_price, confidence, gex_regime,
             entry_net_gex, entry_flip_point, trade_reasoning, exit_spot_price) = pos

            if action != 'IRON_CONDOR':
                return

            conn = get_connection()
            c = conn.cursor()

            # Calculate iron condor strikes
            spot = entry_spot_price if entry_spot_price else strike
            wing_width = 5
            range_width = spot * 0.06

            call_sell_strike = round((spot + range_width) / 5) * 5
            call_buy_strike = call_sell_strike + wing_width
            put_sell_strike = round((spot - range_width) / 5) * 5
            put_buy_strike = put_sell_strike - wing_width

            # Calculate distances
            short_call_distance_pct = ((call_sell_strike - spot) / spot) * 100
            long_call_distance_pct = ((call_buy_strike - spot) / spot) * 100
            short_put_distance_pct = ((put_sell_strike - spot) / spot) * 100
            long_put_distance_pct = ((put_buy_strike - spot) / spot) * 100

            # Calculate hold time
            entry_dt = datetime.strptime(f"{entry_date} {entry_time}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=CENTRAL_TZ)
            exit_dt = datetime.now(CENTRAL_TZ)
            hold_time_hours = int((exit_dt - entry_dt).total_seconds() / 3600)

            # Calculate DTE
            exp_dt = datetime.strptime(expiration_date, "%Y-%m-%d").replace(tzinfo=CENTRAL_TZ)
            dte = (exp_dt - entry_dt).days

            # Calculate P&L metrics
            pnl_dollars = realized_pnl * contracts
            entry_credit_total = entry_price * contracts * 100
            pnl_pct = (pnl_dollars / entry_credit_total * 100) if entry_credit_total > 0 else 0

            vix = self.trader._get_vix() if hasattr(self.trader, '_get_vix') else None
            win = 1 if realized_pnl > 0 else 0

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
            logger.info(f"Logged spread width performance for position {position_id}: Wing=${wing_width}, P&L=${pnl_dollars:.2f}")

        except Exception as e:
            logger.warning(f"Failed to log spread width performance: {e}")
        finally:
            if conn:
                conn.close()

    def get_open_positions_summary(self) -> Dict:
        """
        Get summary of all open positions.

        Returns:
            Dict with position count, total unrealized P&L, etc.
        """
        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute("""
                SELECT
                    COUNT(*) as position_count,
                    COALESCE(SUM(unrealized_pnl), 0) as total_unrealized_pnl,
                    COALESCE(AVG(unrealized_pnl_pct), 0) as avg_pnl_pct,
                    COALESCE(SUM(contracts), 0) as total_contracts
                FROM autonomous_open_positions
            """)
            row = c.fetchone()

            return {
                'position_count': row[0] or 0,
                'total_unrealized_pnl': float(row[1] or 0),
                'avg_pnl_pct': float(row[2] or 0),
                'total_contracts': row[3] or 0
            }
        except Exception as e:
            logger.error(f"Error getting positions summary: {e}")
            return {
                'position_count': 0,
                'total_unrealized_pnl': 0,
                'avg_pnl_pct': 0,
                'total_contracts': 0
            }
        finally:
            conn.close()
