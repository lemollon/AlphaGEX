"""
Trade Executor Mixin - Strategy Execution

This module handles all trade execution including:
- Finding and executing daily trades
- Strategy-specific execution (iron condor, spreads, etc.)
- Entry signal generation
- Trade analysis and psychology conversion
- Thread-safe execution with duplicate prevention

Note: This is a large module due to the complexity of option strategy execution.
Each strategy has specific strike selection, pricing validation, and position sizing logic.
"""

import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo
from database_adapter import get_connection

logger = logging.getLogger('autonomous_paper_trader.trade_executor')

# Central Time timezone
CENTRAL_TZ = ZoneInfo("America/Chicago")

# Thread lock to prevent duplicate trades from race conditions
_trade_execution_lock = threading.Lock()


class TradeExecutorMixin:
    """
    Mixin class providing trade execution functionality.

    Requires the following attributes from the main class:
    - costs_calculator: TradingCostsCalculator instance
    - log_action(action, details, position_id, success): Logging method
    - get_config(key): Config retrieval
    - set_config(key, value): Config update
    - get_available_capital(): Capital calculation
    - calculate_kelly_position_size(): Position sizing
    - get_backtest_validation_for_pattern(): Backtest validation
    - _get_vix(): VIX retrieval
    - _get_momentum(): Momentum data
    - _get_time_context(): Time context
    - _log_trade_activity(): Trade activity logging
    - _log_strike_and_greeks_performance(): Performance logging
    - db_logger: Database logger instance
    - competition: Strategy competition instance
    """

    def _get_expiration_string(self, dte: int) -> str:
        """Get expiration date string for given DTE (weekly options)"""
        target = datetime.now(CENTRAL_TZ) + timedelta(days=dte)
        # Find nearest Friday
        days_until_friday = (4 - target.weekday()) % 7
        if days_until_friday == 0 and target.hour > 16:
            days_until_friday = 7
        friday = target + timedelta(days=days_until_friday)
        return friday.strftime('%Y-%m-%d')

    def _get_expiration_string_monthly(self, dte: int) -> str:
        """Get expiration date string for given DTE (monthly options - 3rd Friday)"""
        target = datetime.now(CENTRAL_TZ) + timedelta(days=dte)
        year = target.year
        month = target.month

        # If we're past the 3rd Friday, move to next month
        third_friday = self._get_third_friday(year, month)
        if target.date() > third_friday.date():
            month += 1
            if month > 12:
                month = 1
                year += 1

        return self._get_third_friday(year, month).strftime('%Y-%m-%d')

    def _get_third_friday(self, year: int, month: int) -> datetime:
        """Get the third Friday of a given month"""
        first_day = datetime(year, month, 1)
        days_until_friday = (4 - first_day.weekday()) % 7
        first_friday = first_day + timedelta(days=days_until_friday)
        third_friday = first_friday + timedelta(days=14)
        return third_friday

    def _execute_trade(self, trade: Dict, option_data: Dict, contracts: int,
                       entry_price: float, exp_date: str, gex_data: Dict,
                       vix_current: float = 18.0, regime_result: Dict = None) -> Optional[int]:
        """Execute the trade with thread safety"""

        # Acquire lock to prevent duplicate trades from race conditions
        with _trade_execution_lock:
            return self._execute_trade_locked(trade, option_data, contracts,
                                              entry_price, exp_date, gex_data,
                                              vix_current, regime_result)

    def _execute_trade_locked(self, trade: Dict, option_data: Dict, contracts: int,
                              entry_price: float, exp_date: str, gex_data: Dict,
                              vix_current: float = 18.0, regime_result: Dict = None) -> Optional[int]:
        """Execute the trade - MUST be called with _trade_execution_lock held"""

        # CRITICAL: Entry price must be > 0
        abs_entry_price = abs(entry_price) if entry_price else 0
        if abs_entry_price <= 0:
            self.log_action(
                'ERROR',
                f"REJECTED: Cannot execute trade with $0 entry price. Strategy: {trade['strategy']}",
                success=False
            )
            return None

        # BACKTEST VALIDATION: Check historical performance before trading
        strategy_name = trade.get('strategy', '')
        backtest_validation = self.get_backtest_validation_for_pattern(strategy_name)

        if not backtest_validation['should_trade']:
            self.log_action(
                'SKIP',
                f"Pattern '{strategy_name}' blocked by backtest validation: {backtest_validation['reason']}",
                success=True
            )
            logger.info(f"Trade blocked by backtest validation: {strategy_name} - {backtest_validation['reason']}")
            return None

        # Check for duplicate trades
        now = datetime.now(CENTRAL_TZ)
        today = now.strftime('%Y-%m-%d')
        conn = get_connection()
        c = conn.cursor()
        try:
            c.execute("""
                SELECT id FROM autonomous_open_positions
                WHERE symbol = %s AND strike = %s AND option_type = %s
                AND expiration_date = %s AND entry_date = %s
                LIMIT 1
            """, (trade['symbol'], trade['strike'], trade['option_type'], exp_date, today))
            existing = c.fetchone()
            if existing:
                conn.close()
                logger.warning(f"Duplicate trade prevented: {trade['symbol']} ${trade['strike']} {trade['option_type']} exp {exp_date}")
                return None
        except Exception as e:
            logger.error(f"Error checking for duplicate trade: {e}")
        finally:
            conn.close()

        # Log trade decision to database
        if hasattr(self, 'db_logger') and self.db_logger:
            self.db_logger.log_trade_decision(
                symbol=trade['symbol'],
                action=trade['action'],
                strategy=trade['strategy'],
                reasoning=trade.get('reasoning', 'See trade details'),
                confidence=trade.get('confidence', 0)
            )

        # Log strike and Greeks performance
        self._log_strike_and_greeks_performance(
            trade, option_data, gex_data, exp_date, vix_current, regime_result
        )

        conn = get_connection()
        c = conn.cursor()

        # Calculate regime-based exit targets
        confidence = trade.get('confidence', 50)
        if confidence >= 80:
            profit_target_pct = 50.0
            stop_loss_pct = 20.0
        elif confidence >= 60:
            profit_target_pct = 40.0
            stop_loss_pct = 25.0
        else:
            profit_target_pct = 30.0
            stop_loss_pct = 30.0

        # Insert into autonomous_open_positions table
        c.execute("""
            INSERT INTO autonomous_open_positions (
                symbol, strategy, action, entry_date, entry_time, strike, option_type,
                expiration_date, contracts, entry_price, entry_bid, entry_ask,
                entry_spot_price, current_price, current_spot_price, unrealized_pnl,
                unrealized_pnl_pct, confidence, gex_regime, entry_net_gex, entry_flip_point,
                trade_reasoning, contract_symbol,
                theoretical_price, theoretical_bid, theoretical_ask, recommended_entry,
                price_adjustment, price_adjustment_pct, is_delayed, data_confidence,
                entry_iv, entry_delta, current_iv, current_delta,
                profit_target_pct, stop_loss_pct
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                      %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            trade['symbol'],
            trade['strategy'],
            trade['action'],
            now.strftime('%Y-%m-%d'),
            now.strftime('%H:%M:%S'),
            trade['strike'],
            trade['option_type'],
            exp_date,
            contracts,
            abs_entry_price,
            option_data.get('bid', 0),
            option_data.get('ask', 0),
            gex_data.get('spot_price', 0),
            abs_entry_price,
            gex_data.get('spot_price', 0),
            0.0, 0.0,  # unrealized P&L starts at 0
            trade['confidence'],
            f"GEX: ${gex_data.get('net_gex', 0)/1e9:.2f}B",
            gex_data.get('net_gex', 0),
            gex_data.get('flip_point', 0),
            trade['reasoning'],
            option_data.get('contract_symbol', ''),
            option_data.get('theoretical_price'),
            option_data.get('theoretical_bid'),
            option_data.get('theoretical_ask'),
            option_data.get('recommended_entry'),
            option_data.get('price_adjustment'),
            option_data.get('price_adjustment_pct'),
            option_data.get('is_delayed', False),
            option_data.get('confidence', 'unknown'),
            option_data.get('iv') or option_data.get('implied_volatility'),
            option_data.get('delta'),
            option_data.get('iv') or option_data.get('implied_volatility'),
            option_data.get('delta'),
            profit_target_pct,
            stop_loss_pct
        ))

        result = c.fetchone()
        position_id = result[0] if result else None
        conn.commit()

        # Log to trade activity
        total_cost = abs_entry_price * contracts * 100
        self._log_trade_activity(
            'ENTRY',
            trade['symbol'],
            f"Opened {trade['strategy']}: {trade['action']} ${trade['strike']} x{contracts} @ ${abs_entry_price:.2f}",
            position_id,
            -total_cost,
            True,
            None
        )

        conn.close()

        # Record trade in strategy competition if available
        if hasattr(self, 'competition') and self.competition:
            try:
                regime = trade.get('regime', {})
                if regime:
                    for strategy_id in self.competition.strategies.keys():
                        should_trade = self.competition.should_trade_for_strategy(strategy_id, regime)
                        if should_trade:
                            self.log_action('COMPETITION', f'Strategy {strategy_id} participating', success=True)
            except Exception as e:
                self.log_action('COMPETITION_ERROR', f'Failed: {e}', success=False)

        # Send push notification for high-confidence trades
        if trade['confidence'] >= 80:
            self._send_trade_notification(trade, contracts, entry_price, position_id)

        return position_id

    def _send_trade_notification(self, trade: Dict, contracts: int, entry_price: float, position_id: int):
        """Send push notification when autonomous trader executes trade"""
        try:
            from backend.push_notification_service import get_push_service
            push_service = get_push_service()

            alert_level = 'CRITICAL' if trade['confidence'] >= 90 else 'HIGH'

            action_emoji = '(up)' if 'CALL' in trade['action'] else '(down)'
            title = f"{action_emoji} {trade['action']} - {trade['strategy'][:30]}"
            body = f"Strike: ${trade['strike']:.0f} | {contracts} contracts @ ${abs(entry_price):.2f}"

            stats = push_service.broadcast_notification(
                title=title,
                body=body,
                alert_type='trade_alert',
                alert_level=alert_level
            )

            print(f"Push notification sent: {stats['sent']} delivered, {stats['failed']} failed")

        except Exception as e:
            print(f"Push notification failed: {e}")

    def _execute_iron_condor(self, spot: float, gex_data: Dict, api_client) -> Optional[int]:
        """Execute Iron Condor - collect premium in range-bound market"""
        # Import here to avoid circular imports
        from autonomous_paper_trader import get_real_option_price

        try:
            dte = 35
            exp_date = self._get_expiration_string_monthly(dte)

            wing_width = 10
            range_width = spot * 0.05

            call_sell_strike = round((spot + range_width) / 5) * 5
            call_buy_strike = call_sell_strike + wing_width
            put_sell_strike = round((spot - range_width) / 5) * 5
            put_buy_strike = put_sell_strike - wing_width

            call_sell = get_real_option_price('SPY', call_sell_strike, 'call', exp_date)
            call_buy = get_real_option_price('SPY', call_buy_strike, 'call', exp_date)
            put_sell = get_real_option_price('SPY', put_sell_strike, 'put', exp_date)
            put_buy = get_real_option_price('SPY', put_buy_strike, 'put', exp_date)

            if any(opt.get('error') for opt in [call_sell, call_buy, put_sell, put_buy]):
                self.log_action('ERROR', 'Failed to get Iron Condor option prices', success=False)
                return None

            if (call_sell.get('mid', 0) <= 0 or call_buy.get('mid', 0) <= 0 or
                put_sell.get('mid', 0) <= 0 or put_buy.get('mid', 0) <= 0):
                self.log_action('ERROR', 'Iron Condor: Invalid option prices', success=False)
                return None

            credit = (call_sell['mid'] - call_buy['mid']) + (put_sell['mid'] - put_buy['mid'])

            if credit <= 0:
                self.log_action('ERROR', f'Iron Condor has no credit (${credit:.2f})', success=False)
                return None

            available = self.get_available_capital()
            max_risk = wing_width * 100
            max_position = available * 0.20
            contracts = max(1, min(100, int(max_position / max_risk)))

            net_credit = credit * contracts * 100

            trade = {
                'symbol': 'SPY',
                'strategy': f'Iron Condor (Collect ${net_credit:.0f} premium)',
                'action': 'IRON_CONDOR',
                'option_type': 'iron_condor',
                'strike': spot,
                'dte': dte,
                'confidence': 85,
                'reasoning': f"IRON CONDOR: Range-bound market. Strikes: {put_buy_strike}/{put_sell_strike}/{call_sell_strike}/{call_buy_strike}"
            }

            ic_bid = (call_sell.get('bid', 0) - call_buy.get('ask', 0)) + (put_sell.get('bid', 0) - put_buy.get('ask', 0))
            ic_ask = (call_sell.get('ask', 0) - call_buy.get('bid', 0)) + (put_sell.get('ask', 0) - put_buy.get('bid', 0))
            vix = self._get_vix()

            position_id = self._execute_trade(
                trade,
                {'mid': credit, 'bid': ic_bid, 'ask': ic_ask, 'contract_symbol': 'IRON_CONDOR'},
                contracts, credit, exp_date, gex_data, vix
            )

            if position_id:
                self.set_config('last_trade_date', datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d'))
                self.log_action('EXECUTE', f"Opened Iron Condor: ${net_credit:.0f} credit", position_id=position_id, success=True)

            return position_id

        except Exception as e:
            self.log_action('ERROR', f'Iron Condor execution failed: {str(e)}', success=False)
            return None

    def _execute_bull_put_spread(self, spot: float, gex_data: Dict, api_client, regime=None) -> Optional[int]:
        """Execute Bull Put Spread - bullish credit spread"""
        from autonomous_paper_trader import get_real_option_price

        try:
            dte = 30
            exp_date = self._get_expiration_string_monthly(dte)

            wing_width = 10
            otm_distance = spot * 0.04

            put_sell_strike = round((spot - otm_distance) / 5) * 5
            put_buy_strike = put_sell_strike - wing_width

            put_sell = get_real_option_price('SPY', put_sell_strike, 'put', exp_date)
            put_buy = get_real_option_price('SPY', put_buy_strike, 'put', exp_date)

            if put_sell.get('error') or put_buy.get('error'):
                return None

            if put_sell.get('mid', 0) <= 0 or put_buy.get('mid', 0) <= 0:
                return None

            credit = put_sell['mid'] - put_buy['mid']
            if credit <= 0:
                return None

            available = self.get_available_capital()
            max_risk = wing_width * 100
            max_position = available * 0.15
            contracts = max(1, min(50, int(max_position / max_risk)))

            net_credit = credit * contracts * 100

            trade = {
                'symbol': 'SPY',
                'strategy': f'Bull Put Spread (Collect ${net_credit:.0f} premium)',
                'action': 'BULL_PUT_SPREAD',
                'option_type': 'bull_put_spread',
                'strike': put_sell_strike,
                'dte': dte,
                'confidence': regime.confidence if regime else 80,
                'reasoning': f"BULL PUT SPREAD: Bullish. Strikes: {put_buy_strike}/{put_sell_strike}"
            }

            vix = self._get_vix()
            bp_bid = put_sell.get('bid', 0) - put_buy.get('ask', 0)
            bp_ask = put_sell.get('ask', 0) - put_buy.get('bid', 0)

            position_id = self._execute_trade(
                trade,
                {'mid': credit, 'bid': bp_bid, 'ask': bp_ask, 'contract_symbol': 'BULL_PUT_SPREAD'},
                contracts, credit, exp_date, gex_data, vix
            )

            if position_id:
                self.set_config('last_trade_date', datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d'))

            return position_id

        except Exception as e:
            self.log_action('ERROR', f'Bull Put Spread failed: {str(e)}', success=False)
            return None

    def _execute_bear_call_spread(self, spot: float, gex_data: Dict, api_client, regime=None) -> Optional[int]:
        """Execute Bear Call Spread - bearish credit spread"""
        from autonomous_paper_trader import get_real_option_price

        try:
            dte = 30
            exp_date = self._get_expiration_string_monthly(dte)

            wing_width = 10
            otm_distance = spot * 0.04

            call_sell_strike = round((spot + otm_distance) / 5) * 5
            call_buy_strike = call_sell_strike + wing_width

            call_sell = get_real_option_price('SPY', call_sell_strike, 'call', exp_date)
            call_buy = get_real_option_price('SPY', call_buy_strike, 'call', exp_date)

            if call_sell.get('error') or call_buy.get('error'):
                return None

            if call_sell.get('mid', 0) <= 0 or call_buy.get('mid', 0) <= 0:
                return None

            credit = call_sell['mid'] - call_buy['mid']
            if credit <= 0:
                return None

            available = self.get_available_capital()
            max_risk = wing_width * 100
            max_position = available * 0.15
            contracts = max(1, min(50, int(max_position / max_risk)))

            net_credit = credit * contracts * 100

            trade = {
                'symbol': 'SPY',
                'strategy': f'Bear Call Spread (Collect ${net_credit:.0f} premium)',
                'action': 'BEAR_CALL_SPREAD',
                'option_type': 'bear_call_spread',
                'strike': call_sell_strike,
                'dte': dte,
                'confidence': regime.confidence if regime else 80,
                'reasoning': f"BEAR CALL SPREAD: Bearish. Strikes: {call_sell_strike}/{call_buy_strike}"
            }

            vix = self._get_vix()
            bc_bid = call_sell.get('bid', 0) - call_buy.get('ask', 0)
            bc_ask = call_sell.get('ask', 0) - call_buy.get('bid', 0)

            position_id = self._execute_trade(
                trade,
                {'mid': credit, 'bid': bc_bid, 'ask': bc_ask, 'contract_symbol': 'BEAR_CALL_SPREAD'},
                contracts, credit, exp_date, gex_data, vix
            )

            if position_id:
                self.set_config('last_trade_date', datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d'))

            return position_id

        except Exception as e:
            self.log_action('ERROR', f'Bear Call Spread failed: {str(e)}', success=False)
            return None

    def _execute_cash_secured_put(self, spot: float, gex_data: Dict, api_client, regime=None) -> Optional[int]:
        """Execute Cash Secured Put - sell naked put with cash to cover"""
        from autonomous_paper_trader import get_real_option_price

        try:
            dte = 45
            exp_date = self._get_expiration_string_monthly(dte)

            otm_distance = spot * 0.06
            put_strike = round((spot - otm_distance) / 5) * 5

            put_option = get_real_option_price('SPY', put_strike, 'put', exp_date)

            if put_option.get('error') or put_option.get('mid', 0) <= 0:
                return None

            premium = put_option['mid']

            available = self.get_available_capital()
            cash_per_contract = put_strike * 100
            max_position = available * 0.25
            contracts = max(1, min(10, int(max_position / cash_per_contract)))

            total_premium = premium * contracts * 100

            trade = {
                'symbol': 'SPY',
                'strategy': f'Cash Secured Put (Collect ${total_premium:.0f} premium)',
                'action': 'CASH_SECURED_PUT',
                'option_type': 'csp',
                'strike': put_strike,
                'dte': dte,
                'confidence': regime.confidence if regime else 85,
                'reasoning': f"CASH SECURED PUT: Strong uptrend. Strike: {put_strike}"
            }

            vix = self._get_vix()

            position_id = self._execute_trade(
                trade,
                {'mid': premium, 'bid': put_option.get('bid', 0), 'ask': put_option.get('ask', 0), 'contract_symbol': 'CASH_SECURED_PUT'},
                contracts, premium, exp_date, gex_data, vix
            )

            if position_id:
                self.set_config('last_trade_date', datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d'))

            return position_id

        except Exception as e:
            self.log_action('ERROR', f'Cash Secured Put failed: {str(e)}', success=False)
            return None
