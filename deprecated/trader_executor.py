"""
Trade Execution Module for Autonomous Trading
==============================================

Extracted from autonomous_paper_trader.py to reduce class complexity.

This module handles:
- Iron Condor execution
- Bull Put Spread execution
- Bear Call Spread execution
- Cash Secured Put execution
- ATM Straddle fallback (guaranteed daily trade)
- Core trade execution with validation

Author: AlphaGEX
Date: 2025-11-27
"""

import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, Optional, Protocol, Tuple
from zoneinfo import ZoneInfo
from dataclasses import dataclass

from database_adapter import get_connection

logger = logging.getLogger(__name__)

# Central Time timezone for all timestamps
CENTRAL_TZ = ZoneInfo("America/Chicago")

# Thread lock to prevent duplicate trades from race conditions
_trade_execution_lock = threading.Lock()


class TraderInterface(Protocol):
    """Protocol defining methods required from the parent trader."""
    def log_action(self, action: str, details: str, position_id: int = None, success: bool = True) -> None: ...
    def set_config(self, key: str, value: str) -> None: ...
    def get_available_capital(self) -> float: ...
    def get_backtest_validation_for_pattern(self, pattern: str, min_trades: int = 5) -> Dict: ...
    def update_live_status(self, status: str, action: str, analysis: str = None, decision: str = None) -> None: ...
    def _get_vix(self) -> float: ...
    def _log_trade_activity(self, action_type: str, symbol: str, details: str,
                            position_id: int, pnl: float, success: bool, error: str) -> None: ...
    def _log_strike_and_greeks_performance(self, trade: Dict, option_data: Dict,
                                           gex_data: Dict, exp_date: str,
                                           vix_current: float, regime_result: Dict) -> None: ...
    def _get_expiration_string(self, dte: int) -> str: ...
    def _get_expiration_string_monthly(self, dte: int) -> str: ...
    @property
    def db_logger(self): ...
    @property
    def costs_calculator(self): ...


@dataclass
class ExecutionResult:
    """Result of a trade execution attempt."""
    success: bool
    position_id: Optional[int]
    error_message: Optional[str] = None
    strategy: Optional[str] = None
    net_credit: float = 0
    contracts: int = 0


class TraderExecutor:
    """
    Handles trade execution for various strategies.

    Strategies:
    - Iron Condor: Neutral, collect premium in range-bound market
    - Bull Put Spread: Bullish credit spread
    - Bear Call Spread: Bearish credit spread
    - Cash Secured Put: Strong bullish, willing to own underlying
    - ATM Straddle: Fallback guaranteed daily trade
    """

    def __init__(self, trader: TraderInterface, get_real_option_price_func):
        """
        Initialize trade executor.

        Args:
            trader: Reference to parent trader for helper methods
            get_real_option_price_func: Function to get real option prices
        """
        self.trader = trader
        self.get_real_option_price = get_real_option_price_func

    def execute_iron_condor(self, spot: float, gex_data: Dict, api_client) -> Optional[int]:
        """
        Execute Iron Condor - collect premium in range-bound market.
        Used when no clear directional setup exists.

        Args:
            spot: Current spot price
            gex_data: GEX data dict
            api_client: API client for market data

        Returns:
            Position ID if successful, None otherwise
        """
        try:
            # Iron Condor parameters for $1M account
            dte = 35  # ~5 weeks out
            exp_date = self.trader._get_expiration_string_monthly(dte)

            # Set strikes: +/-5% from spot for safety
            wing_width = 10  # $10 wings for $1M account
            range_width = spot * 0.05  # 5% from spot

            # Round to nearest $5
            call_sell_strike = round((spot + range_width) / 5) * 5
            call_buy_strike = call_sell_strike + wing_width
            put_sell_strike = round((spot - range_width) / 5) * 5
            put_buy_strike = put_sell_strike - wing_width

            # Get option prices for all 4 legs
            call_sell = self.get_real_option_price('SPY', call_sell_strike, 'call', exp_date)
            call_buy = self.get_real_option_price('SPY', call_buy_strike, 'call', exp_date)
            put_sell = self.get_real_option_price('SPY', put_sell_strike, 'put', exp_date)
            put_buy = self.get_real_option_price('SPY', put_buy_strike, 'put', exp_date)

            # Check for errors
            if any(opt.get('error') for opt in [call_sell, call_buy, put_sell, put_buy]):
                self.trader.log_action('ERROR', 'Failed to get Iron Condor option prices', success=False)
                return None

            # Validate all prices are > 0
            if (call_sell.get('mid', 0) <= 0 or call_buy.get('mid', 0) <= 0 or
                put_sell.get('mid', 0) <= 0 or put_buy.get('mid', 0) <= 0):
                self.trader.log_action('ERROR',
                    f'Iron Condor: Invalid option prices (zero or negative) - '
                    f'Call Sell: ${call_sell.get("mid", 0):.2f}, Call Buy: ${call_buy.get("mid", 0):.2f}, '
                    f'Put Sell: ${put_sell.get("mid", 0):.2f}, Put Buy: ${put_buy.get("mid", 0):.2f}',
                    success=False)
                return None

            # Calculate net credit
            credit = (call_sell['mid'] - call_buy['mid']) + (put_sell['mid'] - put_buy['mid'])

            if credit <= 0:
                call_spread = call_sell['mid'] - call_buy['mid']
                put_spread = put_sell['mid'] - put_buy['mid']
                self.trader.log_action('ERROR',
                    f'Iron Condor has no credit (total=${credit:.2f}). '
                    f'Call spread: ${call_spread:.2f}, Put spread: ${put_spread:.2f}. '
                    f'Strikes: {put_buy_strike}/{put_sell_strike}/{call_sell_strike}/{call_buy_strike}',
                    success=False)
                return None

            # Position sizing: use conservative 20% of capital for spreads
            available = self.trader.get_available_capital()
            max_risk = wing_width * 100  # $10 wing = $1000 risk per spread
            max_position = available * 0.20
            contracts = max(1, int(max_position / max_risk))
            contracts = min(contracts, 100)  # Max 100 Iron Condors

            net_credit = credit * contracts * 100

            # Build trade dict
            trade = {
                'symbol': 'SPY',
                'strategy': f'Iron Condor (Collect ${net_credit:.0f} premium)',
                'action': 'IRON_CONDOR',
                'option_type': 'iron_condor',
                'strike': spot,
                'dte': dte,
                'confidence': 85,
                'reasoning': f"""IRON CONDOR: No clear directional GEX setup. Market range-bound.

STRATEGY: Collect premium betting SPY stays between ${put_sell_strike:.0f} - ${call_sell_strike:.0f}
- Sell {call_sell_strike} Call @ ${call_sell['mid']:.2f}
- Buy {call_buy_strike} Call @ ${call_buy['mid']:.2f}
- Sell {put_sell_strike} Put @ ${put_sell['mid']:.2f}
- Buy {put_buy_strike} Put @ ${put_buy['mid']:.2f}

NET CREDIT: ${credit:.2f} per spread x {contracts} contracts = ${net_credit:.0f}
MAX RISK: ${max_risk * contracts:,.0f}
EXPIRATION: {dte} DTE (monthly) for theta decay
RANGE: +/-5% from ${spot:.2f} ($1M account)"""
            }

            # Calculate bid/ask for execution
            ic_bid = (call_sell.get('bid', 0) - call_buy.get('ask', 0)) + (put_sell.get('bid', 0) - put_buy.get('ask', 0))
            ic_ask = (call_sell.get('ask', 0) - call_buy.get('bid', 0)) + (put_sell.get('ask', 0) - put_buy.get('bid', 0))

            vix = self.trader._get_vix()
            position_id = self._execute_trade(
                trade,
                {'mid': credit, 'bid': ic_bid, 'ask': ic_ask, 'contract_symbol': 'IRON_CONDOR'},
                contracts,
                credit,
                exp_date,
                gex_data,
                vix
            )

            if position_id:
                self.trader.set_config('last_trade_date', datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d'))
                self.trader.log_action(
                    'EXECUTE',
                    f"Opened Iron Condor: ${net_credit:.0f} credit ({contracts} contracts) | Expiration: {exp_date} ({dte} DTE)",
                    position_id=position_id,
                    success=True
                )
                return position_id

            return None

        except Exception as e:
            self.trader.log_action('ERROR', f'Iron Condor execution failed: {str(e)}', success=False)
            import traceback
            traceback.print_exc()
            return None

    def execute_bull_put_spread(self, spot: float, gex_data: Dict, api_client, regime=None) -> Optional[int]:
        """
        Execute Bull Put Spread - bullish credit spread.
        Sell higher strike put, buy lower strike put.
        Profit if SPY stays above short put strike.
        """
        try:
            dte = 30
            exp_date = self.trader._get_expiration_string_monthly(dte)

            wing_width = 10
            otm_distance = spot * 0.04

            put_sell_strike = round((spot - otm_distance) / 5) * 5
            put_buy_strike = put_sell_strike - wing_width

            put_sell = self.get_real_option_price('SPY', put_sell_strike, 'put', exp_date)
            put_buy = self.get_real_option_price('SPY', put_buy_strike, 'put', exp_date)

            if put_sell.get('error') or put_buy.get('error'):
                self.trader.log_action('ERROR', 'Failed to get Bull Put Spread option prices', success=False)
                return None

            if put_sell.get('mid', 0) <= 0 or put_buy.get('mid', 0) <= 0:
                self.trader.log_action('ERROR',
                    f'Bull Put Spread: Invalid option prices - '
                    f'Sell Put: ${put_sell.get("mid", 0):.2f}, Buy Put: ${put_buy.get("mid", 0):.2f}',
                    success=False)
                return None

            credit = put_sell['mid'] - put_buy['mid']

            if credit <= 0:
                self.trader.log_action('ERROR',
                    f'Bull Put Spread has no credit (${credit:.2f}). '
                    f'Strikes: {put_buy_strike}/{put_sell_strike}',
                    success=False)
                return None

            available = self.trader.get_available_capital()
            max_risk = wing_width * 100
            max_position = available * 0.15
            contracts = max(1, int(max_position / max_risk))
            contracts = min(contracts, 50)

            net_credit = credit * contracts * 100

            trade = {
                'symbol': 'SPY',
                'strategy': f'Bull Put Spread (Collect ${net_credit:.0f} premium)',
                'action': 'BULL_PUT_SPREAD',
                'option_type': 'bull_put_spread',
                'strike': put_sell_strike,
                'dte': dte,
                'confidence': regime.confidence if regime else 80,
                'reasoning': f"""BULL PUT SPREAD: Bullish credit spread in uptrend.

STRATEGY: Collect premium betting SPY stays above ${put_sell_strike:.0f}
- Sell {put_sell_strike} Put @ ${put_sell['mid']:.2f}
- Buy {put_buy_strike} Put @ ${put_buy['mid']:.2f}

NET CREDIT: ${credit:.2f} per spread x {contracts} contracts = ${net_credit:.0f}
MAX RISK: ${max_risk * contracts:,.0f}
BREAKEVEN: ${put_sell_strike - credit:.2f}
EXPIRATION: {dte} DTE"""
            }

            vix = self.trader._get_vix()
            bp_bid = put_sell.get('bid', 0) - put_buy.get('ask', 0)
            bp_ask = put_sell.get('ask', 0) - put_buy.get('bid', 0)

            position_id = self._execute_trade(
                trade,
                {'mid': credit, 'bid': bp_bid, 'ask': bp_ask, 'contract_symbol': 'BULL_PUT_SPREAD'},
                contracts,
                credit,
                exp_date,
                gex_data,
                vix
            )

            if position_id:
                self.trader.set_config('last_trade_date', datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d'))
                self.trader.log_action(
                    'EXECUTE',
                    f"Opened Bull Put Spread: ${net_credit:.0f} credit ({contracts} contracts) "
                    f"| Strikes: {put_buy_strike}/{put_sell_strike} | Exp: {exp_date}",
                    position_id=position_id,
                    success=True
                )
                return position_id

            return None

        except Exception as e:
            self.trader.log_action('ERROR', f'Bull Put Spread execution failed: {str(e)}', success=False)
            import traceback
            traceback.print_exc()
            return None

    def execute_bear_call_spread(self, spot: float, gex_data: Dict, api_client, regime=None) -> Optional[int]:
        """
        Execute Bear Call Spread - bearish credit spread.
        Sell lower strike call, buy higher strike call.
        Profit if SPY stays below short call strike.
        """
        try:
            dte = 30
            exp_date = self.trader._get_expiration_string_monthly(dte)

            wing_width = 10
            otm_distance = spot * 0.04

            call_sell_strike = round((spot + otm_distance) / 5) * 5
            call_buy_strike = call_sell_strike + wing_width

            call_sell = self.get_real_option_price('SPY', call_sell_strike, 'call', exp_date)
            call_buy = self.get_real_option_price('SPY', call_buy_strike, 'call', exp_date)

            if call_sell.get('error') or call_buy.get('error'):
                self.trader.log_action('ERROR', 'Failed to get Bear Call Spread option prices', success=False)
                return None

            if call_sell.get('mid', 0) <= 0 or call_buy.get('mid', 0) <= 0:
                self.trader.log_action('ERROR',
                    f'Bear Call Spread: Invalid option prices - '
                    f'Sell Call: ${call_sell.get("mid", 0):.2f}, Buy Call: ${call_buy.get("mid", 0):.2f}',
                    success=False)
                return None

            credit = call_sell['mid'] - call_buy['mid']

            if credit <= 0:
                self.trader.log_action('ERROR',
                    f'Bear Call Spread has no credit (${credit:.2f}). '
                    f'Strikes: {call_sell_strike}/{call_buy_strike}',
                    success=False)
                return None

            available = self.trader.get_available_capital()
            max_risk = wing_width * 100
            max_position = available * 0.15
            contracts = max(1, int(max_position / max_risk))
            contracts = min(contracts, 50)

            net_credit = credit * contracts * 100

            trade = {
                'symbol': 'SPY',
                'strategy': f'Bear Call Spread (Collect ${net_credit:.0f} premium)',
                'action': 'BEAR_CALL_SPREAD',
                'option_type': 'bear_call_spread',
                'strike': call_sell_strike,
                'dte': dte,
                'confidence': regime.confidence if regime else 80,
                'reasoning': f"""BEAR CALL SPREAD: Bearish credit spread in downtrend.

STRATEGY: Collect premium betting SPY stays below ${call_sell_strike:.0f}
- Sell {call_sell_strike} Call @ ${call_sell['mid']:.2f}
- Buy {call_buy_strike} Call @ ${call_buy['mid']:.2f}

NET CREDIT: ${credit:.2f} per spread x {contracts} contracts = ${net_credit:.0f}
MAX RISK: ${max_risk * contracts:,.0f}
BREAKEVEN: ${call_sell_strike + credit:.2f}
EXPIRATION: {dte} DTE"""
            }

            vix = self.trader._get_vix()
            bc_bid = call_sell.get('bid', 0) - call_buy.get('ask', 0)
            bc_ask = call_sell.get('ask', 0) - call_buy.get('bid', 0)

            position_id = self._execute_trade(
                trade,
                {'mid': credit, 'bid': bc_bid, 'ask': bc_ask, 'contract_symbol': 'BEAR_CALL_SPREAD'},
                contracts,
                credit,
                exp_date,
                gex_data,
                vix
            )

            if position_id:
                self.trader.set_config('last_trade_date', datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d'))
                self.trader.log_action(
                    'EXECUTE',
                    f"Opened Bear Call Spread: ${net_credit:.0f} credit ({contracts} contracts) "
                    f"| Strikes: {call_sell_strike}/{call_buy_strike} | Exp: {exp_date}",
                    position_id=position_id,
                    success=True
                )
                return position_id

            return None

        except Exception as e:
            self.trader.log_action('ERROR', f'Bear Call Spread execution failed: {str(e)}', success=False)
            import traceback
            traceback.print_exc()
            return None

    def execute_cash_secured_put(self, spot: float, gex_data: Dict, api_client, regime=None) -> Optional[int]:
        """
        Execute Cash Secured Put - sell naked put with cash to cover assignment.
        Most bullish premium selling strategy - willing to own SPY at lower price.
        Requires significant capital (~$60K per contract at SPY $600).
        """
        try:
            dte = 45
            exp_date = self.trader._get_expiration_string_monthly(dte)

            otm_distance = spot * 0.06
            put_strike = round((spot - otm_distance) / 5) * 5

            put_option = self.get_real_option_price('SPY', put_strike, 'put', exp_date)

            if put_option.get('error'):
                self.trader.log_action('ERROR', 'Failed to get CSP option price', success=False)
                return None

            if put_option.get('mid', 0) <= 0:
                self.trader.log_action('ERROR',
                    f'Cash Secured Put: Invalid option price - Put: ${put_option.get("mid", 0):.2f}',
                    success=False)
                return None

            premium = put_option['mid']

            available = self.trader.get_available_capital()
            cash_per_contract = put_strike * 100
            max_position = available * 0.25
            contracts = max(1, int(max_position / cash_per_contract))
            contracts = min(contracts, 10)

            total_premium = premium * contracts * 100
            total_collateral = cash_per_contract * contracts

            trade = {
                'symbol': 'SPY',
                'strategy': f'Cash Secured Put (Collect ${total_premium:.0f} premium)',
                'action': 'CASH_SECURED_PUT',
                'option_type': 'csp',
                'strike': put_strike,
                'dte': dte,
                'confidence': regime.confidence if regime else 85,
                'reasoning': f"""CASH SECURED PUT: Strong uptrend + high IV = sell naked put.

STRATEGY: Collect premium, willing to own SPY at ${put_strike:.0f}
- Sell {put_strike} Put @ ${premium:.2f}

PREMIUM COLLECTED: ${premium:.2f} x {contracts} contracts = ${total_premium:.0f}
COLLATERAL REQUIRED: ${total_collateral:,.0f} ({contracts} x ${cash_per_contract:,.0f})
BREAKEVEN: ${put_strike - premium:.2f}
YIELD: {(total_premium / total_collateral) * 100:.2f}% in {dte} days
EXPIRATION: {dte} DTE

If assigned: Own SPY at ${put_strike:.0f} (effective cost ${put_strike - premium:.2f})"""
            }

            vix = self.trader._get_vix()

            position_id = self._execute_trade(
                trade,
                {'mid': premium, 'bid': put_option.get('bid', 0), 'ask': put_option.get('ask', 0), 'contract_symbol': 'CASH_SECURED_PUT'},
                contracts,
                premium,
                exp_date,
                gex_data,
                vix
            )

            if position_id:
                self.trader.set_config('last_trade_date', datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d'))
                self.trader.log_action(
                    'EXECUTE',
                    f"Opened Cash Secured Put: ${total_premium:.0f} premium ({contracts} contracts) "
                    f"| Strike: {put_strike} | Collateral: ${total_collateral:,.0f} | Exp: {exp_date}",
                    position_id=position_id,
                    success=True
                )
                return position_id

            return None

        except Exception as e:
            self.trader.log_action('ERROR', f'Cash Secured Put execution failed: {str(e)}', success=False)
            import traceback
            traceback.print_exc()
            return None

    def execute_atm_straddle_fallback(self, spot: float, api_client) -> Optional[int]:
        """
        FINAL FALLBACK - GUARANTEED TRADE.
        Execute simple ATM straddle to ensure MINIMUM one trade per day.
        This is intentionally simple with minimal failure points.
        """
        try:
            self.trader.log_action('GUARANTEE', 'Executing GUARANTEED daily trade - ATM Straddle')

            strike = round(spot)
            dte = 7
            exp_date = self.trader._get_expiration_string(dte)

            call_price = self.get_real_option_price('SPY', strike, 'call', exp_date)
            put_price = self.get_real_option_price('SPY', strike, 'put', exp_date)

            if call_price.get('error') or put_price.get('error'):
                self.trader.log_action('WARNING', 'Could not fetch real prices - using estimated prices')
                estimated_premium = spot * 0.015
                call_price = {'mid': estimated_premium, 'bid': estimated_premium * 0.95, 'ask': estimated_premium * 1.05,
                             'contract_symbol': f'SPY{datetime.now(CENTRAL_TZ).strftime("%y%m%d")}C{strike}'}
                put_price = {'mid': estimated_premium, 'bid': estimated_premium * 0.95, 'ask': estimated_premium * 1.05,
                            'contract_symbol': f'SPY{datetime.now(CENTRAL_TZ).strftime("%y%m%d")}P{strike}'}

            total_cost = (call_price['mid'] + put_price['mid']) * 100

            if total_cost <= 0:
                self.trader.log_action('ERROR', f'ATM Straddle: Invalid option prices (total cost = ${total_cost:.2f})', success=False)
                estimated_cost = spot * 0.02 * 100
                if estimated_cost > 0:
                    total_cost = estimated_cost
                    self.trader.log_action('WARNING', f'Using estimated straddle cost: ${estimated_cost:.2f}')
                else:
                    self.trader.log_action('CRITICAL', 'Cannot estimate straddle cost - spot price may be zero', success=False)
                    return None

            available = self.trader.get_available_capital()
            max_position = available * 0.15
            contracts = max(1, int(max_position / total_cost))
            contracts = min(contracts, 3)

            total_debit = (call_price['mid'] + put_price['mid']) * contracts * 100

            trade = {
                'symbol': 'SPY',
                'strategy': 'ATM Straddle (GUARANTEED Daily Trade)',
                'action': 'LONG_STRADDLE',
                'option_type': 'straddle',
                'strike': strike,
                'dte': dte,
                'confidence': 100,
                'reasoning': f"""ATM STRADDLE - GUARANTEED MINIMUM ONE TRADE PER DAY

STRATEGY: Buy ATM Call + Put to ensure daily trade execution
- Buy {strike} Call @ ${call_price['mid']:.2f}
- Buy {strike} Put @ ${put_price['mid']:.2f}

TOTAL COST: ${total_debit:.0f} for {contracts} straddle(s)
EXPIRATION: {dte} DTE
RATIONALE: Failsafe execution to guarantee MINIMUM one trade per day"""
            }

            straddle_bid = call_price.get('bid', 0) + put_price.get('bid', 0)
            straddle_ask = call_price.get('ask', 0) + put_price.get('ask', 0)
            straddle_mid = call_price['mid'] + put_price['mid']

            vix = self.trader._get_vix()
            position_id = self._execute_trade(
                trade,
                {'mid': straddle_mid, 'bid': straddle_bid, 'ask': straddle_ask, 'contract_symbol': 'STRADDLE_FALLBACK'},
                contracts,
                -straddle_mid,  # Negative because we're buying (debit)
                exp_date,
                {'net_gex': 0, 'flip_point': strike, 'spot_price': spot},
                vix
            )

            if position_id:
                self.trader.set_config('last_trade_date', datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d'))
                self.trader.log_action(
                    'EXECUTE',
                    f"GUARANTEED TRADE: ATM Straddle @ ${strike} ({contracts} contracts) | Expiration: {exp_date} ({dte} DTE)",
                    position_id=position_id,
                    success=True
                )
                self.trader.update_live_status(
                    status='ACTIVE',
                    action='Executed guaranteed daily trade',
                    decision=f'ATM Straddle @ ${strike} - MINIMUM one trade requirement met'
                )
                return position_id

            self.trader.log_action('CRITICAL', 'Guaranteed trade execution failed', success=False)
            return None

        except Exception as e:
            self.trader.log_action('CRITICAL', f'GUARANTEED TRADE FAILED: {str(e)}', success=False)
            import traceback
            traceback.print_exc()
            return None

    def _execute_trade(self, trade: Dict, option_data: Dict, contracts: int,
                       entry_price: float, exp_date: str, gex_data: Dict,
                       vix_current: float = 18.0, regime_result: Dict = None) -> Optional[int]:
        """Execute the trade with thread lock to prevent duplicates."""
        with _trade_execution_lock:
            return self._execute_trade_locked(trade, option_data, contracts,
                                              entry_price, exp_date, gex_data,
                                              vix_current, regime_result)

    def _execute_trade_locked(self, trade: Dict, option_data: Dict, contracts: int,
                              entry_price: float, exp_date: str, gex_data: Dict,
                              vix_current: float = 18.0, regime_result: Dict = None) -> Optional[int]:
        """Execute the trade - MUST be called with lock held."""

        # Validate entry price
        abs_entry_price = abs(entry_price) if entry_price else 0
        if abs_entry_price <= 0:
            self.trader.log_action(
                'ERROR',
                f"REJECTED: Cannot execute trade with $0 entry price. Strategy: {trade['strategy']}",
                success=False
            )
            self.trader._log_trade_activity('ERROR', 'SPY', f"Trade rejected - entry price is $0 for {trade['strategy']}", None, None, False, "Entry price validation failed")
            return None

        # Backtest validation
        strategy_name = trade.get('strategy', '')
        backtest_validation = self.trader.get_backtest_validation_for_pattern(strategy_name)

        if not backtest_validation['should_trade']:
            self.trader.log_action(
                'SKIP',
                f"Pattern '{strategy_name}' blocked by backtest validation: {backtest_validation['reason']}",
                success=True
            )
            self.trader._log_trade_activity(
                'RISK_CHECK', 'SPY',
                f"Trade blocked - {backtest_validation['reason']} (Source: {backtest_validation['source']})",
                None, None, True, None
            )
            logger.info(f"Trade blocked by backtest validation: {strategy_name} - {backtest_validation['reason']}")
            return None

        if backtest_validation['is_validated']:
            logger.info(f"Pattern validated: {strategy_name} - {backtest_validation['reason']} (win_rate: {backtest_validation['win_rate']:.1f}%, expectancy: {backtest_validation['expectancy']:.2f}%)")

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

        # Log trade decision
        if self.trader.db_logger:
            self.trader.db_logger.log_trade_decision(
                symbol=trade['symbol'],
                action=trade['action'],
                strategy=trade['strategy'],
                reasoning=trade.get('reasoning', 'See trade details'),
                confidence=trade.get('confidence', 0)
            )

        # Log strike and Greeks performance
        self.trader._log_strike_and_greeks_performance(
            trade, option_data, gex_data, exp_date, vix_current, regime_result
        )

        conn = get_connection()
        c = conn.cursor()

        try:
            # Insert into autonomous_open_positions
            c.execute("""
                INSERT INTO autonomous_open_positions (
                    symbol, strategy, action, entry_date, entry_time, strike, option_type,
                    expiration_date, contracts, entry_price, entry_bid, entry_ask,
                    entry_spot_price, current_price, current_spot_price, unrealized_pnl,
                    unrealized_pnl_pct, confidence, gex_regime, entry_net_gex, entry_flip_point,
                    trade_reasoning, contract_symbol
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                trade['symbol'],
                trade['strategy'],
                trade['action'],
                today,
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
                0,  # unrealized_pnl
                0,  # unrealized_pnl_pct
                trade.get('confidence', 0),
                'NEUTRAL',  # gex_regime
                gex_data.get('net_gex', 0),
                gex_data.get('flip_point', 0),
                trade.get('reasoning', ''),
                option_data.get('contract_symbol', '')
            ))

            position_id = c.fetchone()[0]
            conn.commit()

            logger.info(f"Trade executed: Position #{position_id} - {trade['strategy']}")
            return position_id

        except Exception as e:
            logger.error(f"Failed to insert position: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()
