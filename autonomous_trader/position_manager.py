"""
Position Manager Mixin - Exit Logic and Position Updates

This module handles all position management including:
- Automatic position monitoring and closing
- Exit condition checking (profit targets, stop losses, expiration)
- AI-powered exit decisions using Claude
- Fallback rules when AI is unavailable
- Position database updates
"""

import os
import pandas as pd
import logging
from datetime import datetime
from typing import Dict, Tuple
from zoneinfo import ZoneInfo
from database_adapter import get_connection
from trading_costs import OrderSide, SymbolType

logger = logging.getLogger('autonomous_paper_trader.position_manager')

# Central Time timezone for all timestamps
CENTRAL_TZ = ZoneInfo("America/Chicago")


class PositionManagerMixin:
    """
    Mixin class providing position management functionality.

    Requires the following attributes from the main class:
    - costs_calculator: TradingCostsCalculator instance
    - log_action(action, details, position_id, success): Logging method
    - _get_vix(): Method to get current VIX
    - _create_equity_snapshot(): Method to snapshot equity
    - _log_trade_activity(): Method to log trade activity
    - _update_strategy_stats_from_trade(): Method to update strategy stats
    """

    def auto_manage_positions(self, api_client):
        """
        AUTONOMOUS: Automatically manage and close positions based on conditions
        Runs every time the system checks
        """
        # Import here to avoid circular imports
        from autonomous_paper_trader import get_real_option_price

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
                option_data = get_real_option_price(
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
                # When selling to close a long position, we receive below mid
                if current_bid > 0 and current_ask > 0:
                    exit_price, exit_slippage = self.costs_calculator.calculate_entry_price(
                        bid=current_bid,
                        ask=current_ask,
                        contracts=int(pos['contracts']),
                        side=OrderSide.SELL,  # Selling to close
                        symbol_type=SymbolType.ETF
                    )
                else:
                    exit_price = current_mid
                    exit_slippage = {}

                # Calculate P&L with exit slippage and commission
                entry_value = pos['entry_price'] * pos['contracts'] * 100
                gross_exit_value = exit_price * pos['contracts'] * 100
                exit_commission = self.costs_calculator.calculate_commission(int(pos['contracts']))
                net_exit_value = gross_exit_value - exit_commission['total_commission']

                # P&L = Exit proceeds - Entry cost
                unrealized_pnl = net_exit_value - entry_value
                pnl_pct = (unrealized_pnl / entry_value * 100) if entry_value > 0 else 0

                # Update position with pnl_pct
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

                    self.log_action(
                        'CLOSE',
                        f"Closed {pos['strategy']}: P&L ${unrealized_pnl:+.2f} ({pnl_pct:+.1f}%) | Expiration: {pos['expiration_date']} - {reason}",
                        position_id=pos['id'],
                        success=True
                    )

            except Exception as e:
                print(f"Error managing position {pos['id']}: {e}")
                continue

        return actions_taken

    def _update_position(self, position_id: int, current_price: float, current_spot: float,
                         unrealized_pnl: float, pnl_pct: float = 0):
        """Update position with current values in autonomous_open_positions"""
        # Validate inputs
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
        AI-POWERED EXIT STRATEGY: Flexible intelligent decision making
        Uses Claude AI to analyze market conditions, not rigid rules
        """

        # HARD STOP: -50% loss (protect capital)
        if pnl_pct <= -50:
            return True, f"HARD STOP: {pnl_pct:.1f}% loss - protecting capital"

        # EXPIRATION SAFETY: Close on expiration day
        exp_date = datetime.strptime(str(pos['expiration_date']), '%Y-%m-%d').replace(tzinfo=CENTRAL_TZ)
        dte = (exp_date - datetime.now(CENTRAL_TZ)).days
        if dte <= 0:
            return True, f"EXPIRATION: {dte} DTE - closing to avoid assignment"

        # AI DECISION: Everything else goes to Claude
        try:
            ai_decision = self._ai_should_close_position(pos, pnl_pct, current_price, current_spot, gex_data, dte)

            if ai_decision['should_close']:
                return True, f"AI: {ai_decision['reason']}"

            # AI says HOLD
            return False, ""

        except Exception as e:
            # If AI fails, fall back to simple rules
            logger.warning(f"AI decision failed: {e}, using fallback rules")
            return self._fallback_exit_rules(pos, pnl_pct, dte, gex_data)

    def _ai_should_close_position(self, pos: Dict, pnl_pct: float, current_price: float,
                                   current_spot: float, gex_data: Dict, dte: int) -> Dict:
        """
        AI-POWERED DECISION: Ask Claude whether to close position
        Returns: {'should_close': bool, 'reason': str}
        """
        # Check if Claude API is available from environment variables
        claude_api_key = os.getenv("CLAUDE_API_KEY") or os.getenv("claude_api_key", "")

        if not claude_api_key:
            # No AI available, use fallback
            return {'should_close': False, 'reason': 'AI unavailable'}

        # Build context for Claude
        entry_gex = pos.get('entry_net_gex', 0) or pos.get('entry_net_gex', 0)
        current_gex = gex_data.get('net_gex', 0)
        entry_flip = pos.get('entry_flip_point', 0) or pos.get('entry_flip_point', 0)
        current_flip = gex_data.get('flip_point', 0)

        prompt = f"""You are an expert options trader managing a position. Analyze this position and decide: HOLD or CLOSE?

POSITION DETAILS:
- Strategy: {pos['strategy']}
- Action: {pos['action']}
- Strike: ${pos['strike']:.0f} {pos['option_type'].upper() if pos['option_type'] else 'OPTION'}
- Entry: ${pos['entry_price']:.2f} | Current: ${current_price:.2f}
- P&L: {pnl_pct:+.1f}%
- Days to Expiration: {dte} DTE
- Contracts: {pos['contracts']}

MARKET CONDITIONS (THEN vs NOW):
Entry GEX: ${entry_gex/1e9:.2f}B | Current GEX: ${current_gex/1e9:.2f}B
Entry Flip: ${entry_flip:.2f} | Current Flip: ${current_flip:.2f}
SPY Entry: ${pos['entry_spot_price']:.2f} | Current SPY: ${current_spot:.2f}

TRADE THESIS:
{pos.get('trade_reasoning', 'N/A')}

THINK LIKE A PROFESSIONAL TRADER:
- Is the original thesis still valid?
- Has GEX regime changed significantly?
- Is this a good profit to take given time left?
- Could we let it run more?
- Is risk/reward still favorable?

RESPOND WITH EXACTLY:
DECISION: HOLD or CLOSE
REASON: [one concise sentence explaining why]"""

        try:
            # Call Claude API using the ClaudeIntelligence class
            from intelligence_and_strategies import ClaudeIntelligence
            claude = ClaudeIntelligence()

            messages = [{"role": "user", "content": prompt}]
            response = claude._call_claude_api(messages)

            # Parse response
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
            print(f"Claude API error: {e}")
            return {'should_close': False, 'reason': f'AI error: {str(e)}'}

    def _fallback_exit_rules(self, pos: Dict, pnl_pct: float, dte: int, gex_data: Dict) -> Tuple[bool, str]:
        """
        Fallback rules if AI is unavailable.

        Regime-Based Targets (from market_regime_classifier):
        - High confidence (>=80%): 20% stop, 50% profit
        - Medium confidence (60-80%): 25% stop, 40% profit
        - Low confidence (<60%): 30% stop, 30% profit
        """
        # Get regime-based targets from position, or calculate from confidence
        profit_target_pct = pos.get('profit_target_pct')
        stop_loss_pct = pos.get('stop_loss_pct')

        if profit_target_pct is None or stop_loss_pct is None:
            # Calculate from confidence if not stored
            confidence = pos.get('confidence', 50)
            if confidence >= 80:
                profit_target_pct = 50
                stop_loss_pct = 20
            elif confidence >= 60:
                profit_target_pct = 40
                stop_loss_pct = 25
            else:
                profit_target_pct = 30
                stop_loss_pct = 30

            logger.debug(f"Exit rules: Calculated from confidence {confidence}% -> "
                        f"profit={profit_target_pct}%, stop={stop_loss_pct}%")
        else:
            # Convert from decimal to percentage if stored as decimal
            if profit_target_pct < 1:
                profit_target_pct = profit_target_pct * 100
            if stop_loss_pct < 1:
                stop_loss_pct = stop_loss_pct * 100
            logger.debug(f"Exit rules: Using stored targets -> "
                        f"profit={profit_target_pct}%, stop={stop_loss_pct}%")

        # Profit target hit
        if pnl_pct >= profit_target_pct:
            return True, f"PROFIT TARGET: +{pnl_pct:.1f}% (target: {profit_target_pct}%)"

        # Stop loss hit
        if pnl_pct <= -stop_loss_pct:
            return True, f"STOP LOSS: {pnl_pct:.1f}% (limit: -{stop_loss_pct}%)"

        # Expiration safety
        if dte <= 1:
            return True, f"EXPIRING: {dte} DTE (safety rule)"

        # GEX flip - regime change indicator
        entry_gex = pos.get('entry_net_gex', 0)
        current_gex = gex_data.get('net_gex', 0)
        if entry_gex and current_gex:
            if (entry_gex > 0 and current_gex < 0) or (entry_gex < 0 and current_gex > 0):
                return True, "GEX FLIP: Thesis changed (regime reversal)"

        return False, ""

    def _close_position(self, position_id: int, exit_price: float, realized_pnl: float, reason: str):
        """Close a position - move from open_positions to closed_trades"""
        conn = get_connection()
        position_data = None  # For logging after commit

        try:
            c = conn.cursor()
            now = datetime.now(CENTRAL_TZ)

            # First, get the full position data from open_positions
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
                print(f"Position {position_id} not found in open_positions")
                return

            (symbol, strategy, action, strike, option_type, expiration_date,
             contracts, contract_symbol, entry_date, entry_time, entry_price,
             entry_bid, entry_ask, entry_spot_price, confidence, gex_regime,
             entry_net_gex, entry_flip_point, trade_reasoning, exit_spot_price) = pos

            # Calculate proper P&L percentage
            entry_value = float(entry_price) * contracts * 100 if entry_price else 0
            realized_pnl_pct = (realized_pnl / entry_value * 100) if entry_value > 0 else 0

            # Calculate hold duration
            try:
                entry_dt = datetime.strptime(f"{entry_date} {entry_time}", '%Y-%m-%d %H:%M:%S')
                hold_minutes = int((now.replace(tzinfo=None) - entry_dt).total_seconds() / 60)
            except (ValueError, TypeError, AttributeError):
                logger.warning(f"Could not calculate hold duration for position {position_id}")
                hold_minutes = 0

            # Insert into closed_trades table
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

            # Commit both operations atomically
            conn.commit()

            # Store data for logging after successful commit
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

        except Exception as e:
            logger.error(f"Failed to close position {position_id}: {e}")
            try:
                conn.rollback()
            except:
                pass
            return
        finally:
            conn.close()

        # Post-commit logging (uses separate connections)
        if position_data:
            # Log to trade activity
            self._log_trade_activity(
                'EXIT',
                position_data['symbol'],
                f"Closed {position_data['strategy']}: {position_data['action']} ${position_data['strike']} x{position_data['contracts']} @ ${position_data['exit_price']:.2f} | P&L: ${position_data['realized_pnl']:+.2f} ({position_data['realized_pnl_pct']:+.1f}%) | Reason: {position_data['reason']}",
                position_id,
                position_data['realized_pnl'],
                True,
                None
            )

            # Create equity snapshot after closing
            self._create_equity_snapshot()

            # Log spread width performance if this is an iron condor
            self._log_spread_width_performance(position_id)

            # Update centralized strategy_stats for feedback loop
            self._update_strategy_stats_from_trade(
                strategy_name=position_data['strategy'],
                pnl_pct=position_data['realized_pnl_pct'],
                is_win=(position_data['realized_pnl'] > 0)
            )
