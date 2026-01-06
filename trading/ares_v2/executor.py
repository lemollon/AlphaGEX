"""
ARES V2 - Order Executor
=========================

Clean order execution for Iron Condors via Tradier.

Iron Condor = Bull Put Spread + Bear Call Spread
Both are credit spreads (receive premium).
"""

import logging
import uuid
import time
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, Callable, TypeVar
from zoneinfo import ZoneInfo
from functools import wraps

from .models import (
    IronCondorPosition, PositionStatus,
    IronCondorSignal, ARESConfig, TradingMode, CENTRAL_TZ
)

# Monte Carlo Kelly for intelligent position sizing
KELLY_AVAILABLE = False
try:
    from quant.monte_carlo_kelly import get_safe_position_size
    KELLY_AVAILABLE = True
except ImportError:
    pass

logger = logging.getLogger(__name__)

T = TypeVar('T')


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    exceptions: tuple = (Exception,)
) -> Callable:
    """
    Decorator for retrying Tradier API calls with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exceptions: Tuple of exceptions to catch and retry
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        logger.warning(
                            f"API call failed (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                            f"Retrying in {delay:.1f}s..."
                        )
                        time.sleep(delay)
                    else:
                        logger.error(f"API call failed after {max_retries + 1} attempts: {e}")
            raise last_exception
        return wrapper
    return decorator

# Tradier import
try:
    from data.tradier_data_fetcher import TradierDataFetcher
    TRADIER_AVAILABLE = True
except ImportError:
    TRADIER_AVAILABLE = False
    TradierDataFetcher = None

# Data provider
try:
    from data.unified_data_provider import get_price
    DATA_AVAILABLE = True
except ImportError:
    DATA_AVAILABLE = False


class OrderExecutor:
    """
    Executes Iron Condor orders via Tradier.

    Handles both paper (simulated) and live execution.

    MATH OPTIMIZER INTEGRATION:
    - Thompson Sampling weight scales position size based on bot performance
    - Higher allocation = larger positions when bot is performing well
    """

    def __init__(self, config: ARESConfig, db=None):
        self.config = config
        self.tradier = None
        self.db = db  # Optional DB reference for orphaned order tracking

        if TRADIER_AVAILABLE and config.mode == TradingMode.LIVE:
            try:
                # ARES uses SANDBOX Tradier account (not production)
                self.tradier = TradierDataFetcher(sandbox=True)
                logger.info("ARES OrderExecutor: Tradier initialized for LIVE trading (SANDBOX account)")
            except Exception as e:
                logger.error(f"Tradier init failed: {e}")

    def _tradier_place_spread_with_retry(
        self,
        max_retries: int = 3,
        **kwargs
    ) -> Optional[Dict]:
        """
        Place a vertical spread order with retry logic.

        Retries on network errors and transient API failures.

        Args:
            max_retries: Number of retry attempts
            **kwargs: All arguments passed to tradier.place_vertical_spread()
        """
        if not self.tradier:
            return None

        last_error = None
        for attempt in range(max_retries):
            try:
                result = self.tradier.place_vertical_spread(**kwargs)
                if result:
                    return result
                # If result is None/falsy but no exception, don't retry
                logger.warning(f"Tradier returned empty result on attempt {attempt + 1}")
                return None
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    delay = 1.0 * (2 ** attempt)  # 1s, 2s, 4s
                    logger.warning(
                        f"Tradier API error (attempt {attempt + 1}/{max_retries}): {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                else:
                    logger.error(f"Tradier API failed after {max_retries} attempts: {e}")

        # If we exhausted retries, raise the last error
        if last_error:
            raise last_error
        return None

    def _tradier_get_quote_with_retry(
        self,
        symbol: str,
        max_retries: int = 2
    ) -> Optional[Dict]:
        """
        Get option quote with retry logic.

        Uses fewer retries than order placement since quotes are less critical.
        """
        if not self.tradier:
            return None

        for attempt in range(max_retries):
            try:
                result = self.tradier.get_option_quote(symbol)
                if result:
                    return result
                return None
            except Exception as e:
                if attempt < max_retries - 1:
                    delay = 0.5 * (2 ** attempt)  # 0.5s, 1s
                    logger.debug(f"Quote fetch error (attempt {attempt + 1}): {e}. Retrying...")
                    time.sleep(delay)
                else:
                    logger.warning(f"Quote fetch failed after {max_retries} attempts: {e}")

        return None

    def execute_iron_condor(
        self,
        signal: IronCondorSignal,
        thompson_weight: float = 1.0
    ) -> Optional[IronCondorPosition]:
        """
        Execute an Iron Condor trade.

        Args:
            signal: The trade signal to execute
            thompson_weight: Thompson Sampling allocation weight (0.5-2.0)
                            Values > 1.0 increase position size for hot bots
                            Values < 1.0 decrease position size for cold bots

        Returns IronCondorPosition on success, None on failure.
        """
        if self.config.mode == TradingMode.PAPER:
            return self._execute_paper(signal, thompson_weight)
        else:
            return self._execute_live(signal, thompson_weight)

    def _execute_paper(self, signal: IronCondorSignal, thompson_weight: float = 1.0) -> Optional[IronCondorPosition]:
        """Execute paper trade (simulation)"""
        try:
            now = datetime.now(CENTRAL_TZ)
            position_id = f"ARES-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

            # Calculate contracts based on risk, scaled by Thompson allocation
            contracts = self._calculate_position_size(signal.max_loss, thompson_weight)

            # Calculate actual P&L values
            spread_width = signal.put_short - signal.put_long
            max_profit = signal.total_credit * 100 * contracts
            max_loss = (spread_width - signal.total_credit) * 100 * contracts

            # Convert Oracle top_factors to JSON string for DB storage
            import json
            oracle_factors_json = json.dumps(signal.oracle_top_factors) if signal.oracle_top_factors else ""

            position = IronCondorPosition(
                position_id=position_id,
                ticker=self.config.ticker,
                expiration=signal.expiration,
                put_short_strike=signal.put_short,
                put_long_strike=signal.put_long,
                put_credit=signal.estimated_put_credit,
                call_short_strike=signal.call_short,
                call_long_strike=signal.call_long,
                call_credit=signal.estimated_call_credit,
                contracts=contracts,
                spread_width=spread_width,
                total_credit=signal.total_credit,
                max_profit=max_profit,
                max_loss=max_loss,
                underlying_at_entry=signal.spot_price,
                vix_at_entry=signal.vix,
                expected_move=signal.expected_move,
                call_wall=signal.call_wall,
                put_wall=signal.put_wall,
                gex_regime=signal.gex_regime,
                # Kronos context
                flip_point=signal.flip_point,
                net_gex=signal.net_gex,
                # Oracle context (FULL audit trail)
                oracle_confidence=signal.confidence,
                oracle_win_probability=signal.oracle_win_probability,
                oracle_advice=signal.oracle_advice,
                oracle_reasoning=signal.reasoning,
                oracle_top_factors=oracle_factors_json,
                oracle_use_gex_walls=signal.oracle_use_gex_walls,
                # Order tracking
                put_order_id="PAPER",
                call_order_id="PAPER",
                status=PositionStatus.OPEN,
                open_time=now,
            )

            logger.info(
                f"PAPER IC: {signal.put_long}/{signal.put_short}-{signal.call_short}/{signal.call_long} "
                f"x{contracts} @ ${signal.total_credit:.2f} credit"
            )

            return position

        except Exception as e:
            logger.error(f"Paper execution failed: {e}")
            return None

    def _execute_live(self, signal: IronCondorSignal, thompson_weight: float = 1.0) -> Optional[IronCondorPosition]:
        """Execute live Iron Condor via Tradier"""
        if not self.tradier:
            logger.error("Live execution requested but Tradier not available")
            return None

        try:
            now = datetime.now(CENTRAL_TZ)

            # Get real quotes for the IC
            ic_quote = self._get_iron_condor_quote(signal)
            if not ic_quote:
                logger.error("Failed to get IC quotes")
                return None

            actual_credit = ic_quote['total_credit']
            # Apply Thompson allocation weight to position size
            contracts = self._calculate_position_size(ic_quote['max_loss_per_contract'] * 100, thompson_weight)

            # Execute as two spreads (put spread + call spread)
            # Bull Put Spread (credit) - Note: place_vertical_spread auto-detects credit/debit from strikes
            # Using retry wrapper for network resilience
            put_result = self._tradier_place_spread_with_retry(
                symbol=self.config.ticker,
                expiration=signal.expiration,
                long_strike=signal.put_long,
                short_strike=signal.put_short,
                option_type="put",
                quantity=contracts,
                limit_price=round(ic_quote['put_credit'], 2),
            )

            if not put_result or not put_result.get('order'):
                logger.error(f"Put spread order failed: {put_result}")
                return None

            put_order_id = str(put_result['order'].get('id', 'UNKNOWN'))

            # Bear Call Spread (credit) - with retry
            call_result = self._tradier_place_spread_with_retry(
                symbol=self.config.ticker,
                expiration=signal.expiration,
                long_strike=signal.call_long,
                short_strike=signal.call_short,
                option_type="call",
                quantity=contracts,
                limit_price=round(ic_quote['call_credit'], 2),
            )

            if not call_result or not call_result.get('order'):
                logger.error(f"Call spread order failed: {call_result}")
                # CRITICAL: Put spread was already placed - attempt to close it
                logger.warning(f"Attempting to rollback put spread order {put_order_id}")
                rollback_failed = False
                rollback_error_msg = None
                try:
                    # Close put spread by reversing the order (swap long/short to create debit)
                    # Using retry wrapper for rollback - critical to succeed
                    rollback_result = self._tradier_place_spread_with_retry(
                        max_retries=4,  # Extra retries for critical rollback
                        symbol=self.config.ticker,
                        expiration=signal.expiration,
                        long_strike=signal.put_short,  # Buy back short
                        short_strike=signal.put_long,   # Sell long
                        option_type="put",
                        quantity=contracts,
                        limit_price=round(ic_quote['put_credit'] * 1.1, 2),  # Allow slippage for rollback
                    )
                    if rollback_result and rollback_result.get('order'):
                        logger.info(f"Successfully rolled back put spread order {put_order_id}")
                    else:
                        rollback_failed = True
                        rollback_error_msg = f"Rollback returned: {rollback_result}"
                        logger.error(f"CRITICAL: Failed to rollback put spread {put_order_id} - MANUAL INTERVENTION REQUIRED")
                except Exception as rollback_error:
                    rollback_failed = True
                    rollback_error_msg = str(rollback_error)
                    logger.error(f"CRITICAL: Rollback exception for {put_order_id}: {rollback_error} - MANUAL INTERVENTION REQUIRED")

                # Log orphaned order if rollback failed
                if rollback_failed and self.db:
                    self.db.log_orphaned_order(
                        order_id=put_order_id,
                        order_type='put_spread',
                        ticker=self.config.ticker,
                        expiration=signal.expiration,
                        strikes={
                            'put_long': signal.put_long,
                            'put_short': signal.put_short
                        },
                        contracts=contracts,
                        reason='ROLLBACK_FAILED_AFTER_CALL_SPREAD_ERROR',
                        error_details=rollback_error_msg
                    )
                return None

            call_order_id = str(call_result['order'].get('id', 'UNKNOWN'))

            # Calculate P&L
            spread_width = signal.put_short - signal.put_long
            max_profit = actual_credit * 100 * contracts
            max_loss = (spread_width - actual_credit) * 100 * contracts

            # Convert Oracle top_factors to JSON string for DB storage
            import json
            oracle_factors_json = json.dumps(signal.oracle_top_factors) if signal.oracle_top_factors else ""

            position = IronCondorPosition(
                position_id=f"ARES-LIVE-{put_order_id}",
                ticker=self.config.ticker,
                expiration=signal.expiration,
                put_short_strike=signal.put_short,
                put_long_strike=signal.put_long,
                put_credit=ic_quote['put_credit'],
                call_short_strike=signal.call_short,
                call_long_strike=signal.call_long,
                call_credit=ic_quote['call_credit'],
                contracts=contracts,
                spread_width=spread_width,
                total_credit=actual_credit,
                max_profit=max_profit,
                max_loss=max_loss,
                underlying_at_entry=signal.spot_price,
                vix_at_entry=signal.vix,
                expected_move=signal.expected_move,
                call_wall=signal.call_wall,
                put_wall=signal.put_wall,
                gex_regime=signal.gex_regime,
                # Kronos context
                flip_point=signal.flip_point,
                net_gex=signal.net_gex,
                # Oracle context (FULL audit trail)
                oracle_confidence=signal.confidence,
                oracle_win_probability=signal.oracle_win_probability,
                oracle_advice=signal.oracle_advice,
                oracle_reasoning=signal.reasoning,
                oracle_top_factors=oracle_factors_json,
                oracle_use_gex_walls=signal.oracle_use_gex_walls,
                # Order tracking
                put_order_id=put_order_id,
                call_order_id=call_order_id,
                status=PositionStatus.OPEN,
                open_time=now,
            )

            logger.info(
                f"LIVE IC: {signal.put_long}/{signal.put_short}-{signal.call_short}/{signal.call_long} "
                f"x{contracts} @ ${actual_credit:.2f} [Put: {put_order_id}, Call: {call_order_id}]"
            )

            return position

        except Exception as e:
            logger.error(f"Live execution failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    def close_position(
        self,
        position: IronCondorPosition,
        reason: str
    ) -> Tuple[bool, float, float]:
        """
        Close an Iron Condor position.

        Returns: (success, close_price, realized_pnl)
        """
        if self.config.mode == TradingMode.PAPER:
            return self._close_paper(position, reason)
        else:
            return self._close_live(position, reason)

    def _close_paper(
        self,
        position: IronCondorPosition,
        reason: str
    ) -> Tuple[bool, float, float]:
        """Close paper position with simulated pricing"""
        try:
            current_price = self._get_current_price()
            if not current_price:
                current_price = position.underlying_at_entry

            # Estimate current IC value
            close_price = self._estimate_ic_value(position, current_price)

            # P&L = credit received - debit to close
            # For IC: we received total_credit, now we pay close_price to close
            pnl_per_contract = (position.total_credit - close_price) * 100
            realized_pnl = pnl_per_contract * position.contracts

            logger.info(
                f"PAPER CLOSE: {position.position_id} "
                f"@ ${close_price:.2f}, P&L: ${realized_pnl:.2f} [{reason}]"
            )

            return True, close_price, realized_pnl

        except Exception as e:
            logger.error(f"Paper close failed: {e}")
            return False, 0, 0

    def _close_live(
        self,
        position: IronCondorPosition,
        reason: str
    ) -> Tuple[bool, float, float]:
        """Close live IC position via Tradier"""
        if not self.tradier:
            logger.error("Cannot close - Tradier not available")
            return False, 0, 0

        try:
            # Get current IC quote
            ic_quote = self._get_position_quote(position)
            if not ic_quote:
                logger.error("Failed to get closing quotes")
                return False, 0, 0

            close_price = ic_quote['total_value']

            # Close put spread by reversing (buy back short, sell long = debit spread)
            # Using retry wrapper for network resilience
            put_result = self._tradier_place_spread_with_retry(
                symbol=position.ticker,
                expiration=position.expiration,
                long_strike=position.put_short_strike,  # Buy back what we sold
                short_strike=position.put_long_strike,   # Sell what we bought
                option_type="put",
                quantity=position.contracts,
                limit_price=round(ic_quote['put_value'], 2),
            )

            if not put_result or not put_result.get('order'):
                logger.error(f"Failed to close put spread: {put_result}")
                return False, 0, 0

            # Close call spread by reversing - with retry
            call_result = self._tradier_place_spread_with_retry(
                symbol=position.ticker,
                expiration=position.expiration,
                long_strike=position.call_short_strike,  # Buy back what we sold
                short_strike=position.call_long_strike,   # Sell what we bought
                option_type="call",
                quantity=position.contracts,
                limit_price=round(ic_quote['call_value'], 2),
            )

            if not call_result or not call_result.get('order'):
                logger.error(f"Failed to close call spread (put was closed!): {call_result}")
                # Partial close - put side closed but call failed
                partial_pnl = (position.put_credit - ic_quote['put_value']) * 100 * position.contracts
                logger.warning(f"PARTIAL CLOSE: Put side closed, P&L=${partial_pnl:.2f}")
                # Return special tuple indicating partial close (success=False but with 'partial' marker)
                # Caller should handle this by marking position as partial_close in DB
                return 'partial_put', ic_quote['put_value'], partial_pnl

            # P&L calculation
            pnl_per_contract = (position.total_credit - close_price) * 100
            realized_pnl = pnl_per_contract * position.contracts

            logger.info(
                f"LIVE CLOSE: {position.position_id} "
                f"@ ${close_price:.2f}, P&L: ${realized_pnl:.2f} [{reason}]"
            )

            return True, close_price, realized_pnl

        except Exception as e:
            logger.error(f"Live close failed: {e}")
            return False, 0, 0

    def _get_kelly_position_size(self, max_loss_per_contract: float) -> Optional[Dict]:
        """
        Get Monte Carlo Kelly-based position sizing recommendation.

        Uses historical win rate and avg win/loss to calculate safe position size
        that survives 95% of Monte Carlo simulations.

        Returns:
            Dict with kelly recommendation or None if not available
        """
        if not KELLY_AVAILABLE:
            return None

        try:
            # Get historical performance from database
            from database_adapter import DatabaseAdapter
            db = DatabaseAdapter()

            # Query closed ARES trades for win rate calculation
            trades = db.execute_query("""
                SELECT pnl_realized, entry_credit, max_loss
                FROM autonomous_closed_trades
                WHERE bot_name = 'ARES'
                AND closed_at > NOW() - INTERVAL '90 days'
                ORDER BY closed_at DESC
                LIMIT 100
            """)

            if not trades or len(trades) < 20:
                logger.debug("[KELLY] Insufficient trade history for Kelly sizing (<20 trades)")
                return None

            # Calculate win rate and payoffs
            wins = [t for t in trades if t['pnl_realized'] > 0]
            losses = [t for t in trades if t['pnl_realized'] <= 0]

            win_rate = len(wins) / len(trades)
            avg_win_pct = sum(t['pnl_realized'] for t in wins) / len(wins) / self.config.capital * 100 if wins else 0
            avg_loss_pct = abs(sum(t['pnl_realized'] for t in losses) / len(losses) / self.config.capital * 100) if losses else 10

            # Get Kelly-safe position size
            kelly_result = get_safe_position_size(
                win_rate=win_rate,
                avg_win=avg_win_pct,
                avg_loss=avg_loss_pct,
                sample_size=len(trades),
                account_size=self.config.capital,
                max_risk_pct=self.config.risk_per_trade_pct * 2  # Allow up to 2x config as ceiling
            )

            logger.info(f"[ARES KELLY] Win Rate: {win_rate:.1%}, Safe Kelly: {kelly_result['kelly_safe']:.1f}%, "
                       f"Ruin Prob: {kelly_result['prob_ruin']:.1f}%")

            return kelly_result

        except Exception as e:
            logger.debug(f"[KELLY] Error calculating Kelly size: {e}")
            return None

    def _calculate_position_size(self, max_loss_per_contract: float, thompson_weight: float = 1.0) -> int:
        """
        Calculate position size based on risk settings, Kelly criterion, and Thompson allocation.

        Uses Monte Carlo Kelly sizing when available (survives 95% of simulations),
        falls back to fixed risk_per_trade_pct otherwise.

        Args:
            max_loss_per_contract: Maximum loss per contract in dollars
            thompson_weight: Thompson Sampling allocation weight (0.5-2.0)
                            - 1.0 = neutral (standard sizing)
                            - 1.5 = bot is performing well, increase size 50%
                            - 0.7 = bot is underperforming, reduce size 30%

        Returns:
            Number of contracts to trade (minimum 1)
        """
        capital = self.config.capital

        if max_loss_per_contract <= 0:
            return 1

        # Try Kelly-based sizing first (Monte Carlo stress-tested)
        kelly_result = self._get_kelly_position_size(max_loss_per_contract)

        if kelly_result and kelly_result.get('kelly_safe', 0) > 0:
            # Use Kelly-safe percentage (survives 95% of Monte Carlo scenarios)
            kelly_risk_pct = kelly_result['kelly_safe']
            max_risk = capital * (kelly_risk_pct / 100)
            sizing_source = "KELLY"
            logger.info(f"[ARES] Using Kelly-safe sizing: {kelly_risk_pct:.1f}% risk")
        else:
            # Fallback to config-based fixed risk
            max_risk = capital * (self.config.risk_per_trade_pct / 100)
            sizing_source = "CONFIG"

        # Base position size from risk calculation
        base_contracts = max_risk / max_loss_per_contract

        # Apply Thompson Sampling weight (clamped to reasonable bounds)
        # Weight is normalized so 20% allocation (1/5 bots) = 1.0
        # Higher allocation = larger positions, lower = smaller
        clamped_weight = max(0.5, min(2.0, thompson_weight))
        adjusted_contracts = int(base_contracts * clamped_weight)

        # Log sizing decision
        if abs(thompson_weight - 1.0) > 0.05:
            logger.info(f"[ARES {sizing_source}] Thompson: weight={thompson_weight:.2f}, base={base_contracts:.1f}, adjusted={adjusted_contracts}")

        return max(1, min(adjusted_contracts, self.config.max_contracts))

    def _get_current_price(self) -> Optional[float]:
        """Get current underlying price"""
        if DATA_AVAILABLE:
            try:
                return get_price(self.config.ticker)
            except Exception:
                pass
        return None

    def _get_iron_condor_quote(self, signal: IronCondorSignal) -> Optional[Dict[str, float]]:
        """Get real quotes for IC"""
        if not self.tradier:
            return None

        try:
            # Get quotes for all 4 legs
            put_long_quote = self._get_option_quote(signal.put_long, signal.expiration, "put")
            put_short_quote = self._get_option_quote(signal.put_short, signal.expiration, "put")
            call_short_quote = self._get_option_quote(signal.call_short, signal.expiration, "call")
            call_long_quote = self._get_option_quote(signal.call_long, signal.expiration, "call")

            if not all([put_long_quote, put_short_quote, call_short_quote, call_long_quote]):
                return None

            # Bull Put Spread credit = short bid - long ask
            put_credit = put_short_quote['bid'] - put_long_quote['ask']

            # Bear Call Spread credit = short bid - long ask
            call_credit = call_short_quote['bid'] - call_long_quote['ask']

            total_credit = put_credit + call_credit
            spread_width = signal.put_short - signal.put_long
            max_loss = spread_width - total_credit

            return {
                'put_credit': max(0.01, put_credit),
                'call_credit': max(0.01, call_credit),
                'total_credit': max(0.02, total_credit),
                'max_loss_per_contract': max_loss,
            }
        except Exception as e:
            logger.warning(f"IC quote error: {e}")
            return None

    def _get_position_quote(self, position: IronCondorPosition) -> Optional[Dict[str, float]]:
        """Get current quote for an open position"""
        if not self.tradier:
            return None

        try:
            put_long = self._get_option_quote(position.put_long_strike, position.expiration, "put")
            put_short = self._get_option_quote(position.put_short_strike, position.expiration, "put")
            call_short = self._get_option_quote(position.call_short_strike, position.expiration, "call")
            call_long = self._get_option_quote(position.call_long_strike, position.expiration, "call")

            if not all([put_long, put_short, call_short, call_long]):
                return None

            # To close, we buy back what we sold (ask) and sell what we bought (bid)
            put_value = put_short['ask'] - put_long['bid']  # Cost to close put spread
            call_value = call_short['ask'] - call_long['bid']  # Cost to close call spread

            return {
                'put_value': max(0, put_value),
                'call_value': max(0, call_value),
                'total_value': put_value + call_value,
            }
        except Exception as e:
            logger.warning(f"Position quote error: {e}")
            return None

    def _get_option_quote(self, strike: float, expiration: str, option_type: str) -> Optional[Dict]:
        """Get quote for a single option - with retry for network resilience"""
        if not self.tradier:
            return None

        try:
            symbol = self._build_option_symbol(strike, expiration, option_type)
            # Use retry wrapper for quote fetches
            quote = self._tradier_get_quote_with_retry(symbol)
            if quote:
                return {
                    'bid': quote.get('bid', 0),
                    'ask': quote.get('ask', 0),
                    'mid': (quote.get('bid', 0) + quote.get('ask', 0)) / 2,
                }
        except Exception:
            pass
        return None

    def _build_option_symbol(self, strike: float, expiration: str, option_type: str) -> str:
        """Build OCC option symbol"""
        ticker = self.config.ticker
        exp_date = datetime.strptime(expiration, "%Y-%m-%d")
        exp_str = exp_date.strftime("%y%m%d")
        opt_char = "C" if option_type.lower() == "call" else "P"
        strike_str = f"{int(strike * 1000):08d}"
        return f"{ticker}{exp_str}{opt_char}{strike_str}"

    def _estimate_ic_value(self, position: IronCondorPosition, current_price: float) -> float:
        """Estimate current IC value for paper trading"""
        # Simplified estimation based on how close price is to strikes

        # If price is in the "safe zone" (between short strikes), IC is worth less
        if position.put_short_strike < current_price < position.call_short_strike:
            # Calculate how centered we are
            put_dist = (current_price - position.put_short_strike) / position.spread_width
            call_dist = (position.call_short_strike - current_price) / position.spread_width

            # IC loses value as it approaches expiration while in safe zone
            # Simple decay model: value = credit * (time_factor + proximity_factor)
            proximity_factor = min(put_dist, call_dist) / 2
            return position.total_credit * max(0.1, 0.5 - proximity_factor * 0.3)

        # If price breaches a short strike, IC gains value (loss for us)
        elif current_price <= position.put_short_strike:
            # Put side is ITM
            intrinsic = position.put_short_strike - current_price
            return min(position.spread_width, intrinsic + position.total_credit * 0.2)
        else:
            # Call side is ITM
            intrinsic = current_price - position.call_short_strike
            return min(position.spread_width, intrinsic + position.total_credit * 0.2)

    def get_position_current_value(self, position: IronCondorPosition) -> Optional[float]:
        """Get current value of an IC position"""
        if self.config.mode == TradingMode.PAPER:
            current_price = self._get_current_price()
            if current_price:
                return self._estimate_ic_value(position, current_price)
            return None
        else:
            quote = self._get_position_quote(position)
            return quote['total_value'] if quote else None
