"""
ATHENA V2 - Order Executor
===========================

Clean order execution via Tradier (paper or live).

Design principles:
1. Single responsibility - only handles order execution
2. Clear separation between paper and live modes
3. Returns execution results, doesn't manage state
"""

import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from zoneinfo import ZoneInfo

from .models import (
    SpreadPosition, SpreadType, PositionStatus,
    TradeSignal, ATHENAConfig, TradingMode, CENTRAL_TZ
)

logger = logging.getLogger(__name__)

# Tradier import with fallback
try:
    from data.tradier_data_fetcher import TradierDataFetcher
    TRADIER_AVAILABLE = True
except ImportError:
    TRADIER_AVAILABLE = False
    TradierDataFetcher = None

# Data provider for quotes
try:
    from data.unified_data_provider import get_quote, get_price
    DATA_AVAILABLE = True
except ImportError:
    DATA_AVAILABLE = False


class OrderExecutor:
    """
    Executes spread orders via Tradier.

    Handles both paper (simulated) and live execution.
    Returns SpreadPosition on success, None on failure.

    MATH OPTIMIZER INTEGRATION:
    - Thompson Sampling weight scales position size based on bot performance
    - Higher allocation = larger positions when bot is performing well
    """

    def __init__(self, config: ATHENAConfig):
        self.config = config
        self.tradier = None

        if TRADIER_AVAILABLE and config.mode != TradingMode.PAPER:
            try:
                self.tradier = TradierDataFetcher()
                logger.info("OrderExecutor: Tradier initialized for LIVE trading")
            except Exception as e:
                logger.error(f"OrderExecutor: Tradier init failed: {e}")

    def execute_spread(
        self,
        signal: TradeSignal,
        thompson_weight: float = 1.0
    ) -> Optional[SpreadPosition]:
        """
        Execute a spread trade based on the signal.

        Args:
            signal: The trade signal to execute
            thompson_weight: Thompson Sampling allocation weight (0.5-2.0)

        Returns SpreadPosition on success, None on failure.
        """
        if self.config.mode == TradingMode.PAPER:
            return self._execute_paper(signal, thompson_weight)
        else:
            return self._execute_live(signal, thompson_weight)

    def _execute_paper(self, signal: TradeSignal, thompson_weight: float = 1.0) -> Optional[SpreadPosition]:
        """
        Execute paper trade (simulation).

        Uses signal's estimated pricing.
        """
        try:
            now = datetime.now(CENTRAL_TZ)
            position_id = f"ATHENA-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

            # Calculate contracts based on risk, scaled by Thompson allocation
            contracts = self._calculate_position_size(signal.max_loss, thompson_weight)

            # Recalculate P&L based on contracts
            max_loss = signal.max_loss * contracts
            max_profit = signal.max_profit * contracts

            position = SpreadPosition(
                position_id=position_id,
                spread_type=signal.spread_type,
                ticker=self.config.ticker,
                long_strike=signal.long_strike,
                short_strike=signal.short_strike,
                expiration=signal.expiration,
                entry_debit=signal.estimated_debit,
                contracts=contracts,
                max_profit=max_profit,
                max_loss=max_loss,
                underlying_at_entry=signal.spot_price,
                call_wall=signal.call_wall,
                put_wall=signal.put_wall,
                gex_regime=signal.gex_regime,
                vix_at_entry=signal.vix,
                # Kronos GEX context (FULL audit trail)
                flip_point=signal.flip_point,
                net_gex=signal.net_gex,
                # ML context (FULL audit trail)
                oracle_confidence=signal.confidence,
                ml_direction=signal.direction,
                ml_confidence=signal.confidence,
                ml_model_name=signal.ml_model_name,
                ml_win_probability=signal.ml_win_probability,
                ml_top_features=signal.ml_top_features,
                # Wall proximity context
                wall_type=signal.wall_type,
                wall_distance_pct=signal.wall_distance_pct,
                # Full trade reasoning for audit
                trade_reasoning=signal.reasoning,
                order_id="PAPER",
                status=PositionStatus.OPEN,
                open_time=now,
            )

            logger.info(
                f"PAPER TRADE: {signal.spread_type.value} "
                f"{signal.long_strike}/{signal.short_strike} "
                f"x{contracts} @ ${signal.estimated_debit:.2f}"
            )

            return position

        except Exception as e:
            logger.error(f"Paper execution failed: {e}")
            return None

    def _execute_live(self, signal: TradeSignal, thompson_weight: float = 1.0) -> Optional[SpreadPosition]:
        """
        Execute live trade via Tradier.

        Gets real quotes and places actual orders.
        """
        if not self.tradier:
            logger.error("Live execution requested but Tradier not available")
            return None

        try:
            now = datetime.now(CENTRAL_TZ)

            # Determine option type
            option_type = "call" if signal.spread_type == SpreadType.BULL_CALL else "put"

            # Get real quotes for the spread
            spread_quote = self._get_spread_quote(
                signal.long_strike,
                signal.short_strike,
                signal.expiration,
                option_type
            )

            if not spread_quote:
                logger.error("Failed to get spread quotes")
                return None

            actual_debit = spread_quote['mid_price']

            # Calculate contracts with Thompson allocation weight
            contracts = self._calculate_position_size(actual_debit * 100, thompson_weight)

            # Place the order
            order_result = self.tradier.place_vertical_spread(
                symbol=self.config.ticker,
                expiration=signal.expiration,
                long_strike=signal.long_strike,
                short_strike=signal.short_strike,
                option_type=option_type,
                quantity=contracts,
                limit_price=round(actual_debit, 2)
            )

            if not order_result or not order_result.get('order'):
                logger.error(f"Order placement failed: {order_result}")
                return None

            order_info = order_result['order']
            order_id = str(order_info.get('id', 'UNKNOWN'))

            # Calculate P&L
            spread_width = abs(signal.short_strike - signal.long_strike)
            max_profit = (spread_width - actual_debit) * 100 * contracts
            max_loss = actual_debit * 100 * contracts

            position = SpreadPosition(
                position_id=f"ATHENA-LIVE-{order_id}",
                spread_type=signal.spread_type,
                ticker=self.config.ticker,
                long_strike=signal.long_strike,
                short_strike=signal.short_strike,
                expiration=signal.expiration,
                entry_debit=actual_debit,
                contracts=contracts,
                max_profit=max_profit,
                max_loss=max_loss,
                underlying_at_entry=signal.spot_price,
                call_wall=signal.call_wall,
                put_wall=signal.put_wall,
                gex_regime=signal.gex_regime,
                vix_at_entry=signal.vix,
                # Kronos GEX context (FULL audit trail)
                flip_point=signal.flip_point,
                net_gex=signal.net_gex,
                # ML context (FULL audit trail)
                oracle_confidence=signal.confidence,
                ml_direction=signal.direction,
                ml_confidence=signal.confidence,
                ml_model_name=signal.ml_model_name,
                ml_win_probability=signal.ml_win_probability,
                ml_top_features=signal.ml_top_features,
                # Wall proximity context
                wall_type=signal.wall_type,
                wall_distance_pct=signal.wall_distance_pct,
                # Full trade reasoning for audit
                trade_reasoning=signal.reasoning,
                order_id=order_id,
                status=PositionStatus.OPEN,
                open_time=now,
            )

            logger.info(
                f"LIVE TRADE: {signal.spread_type.value} "
                f"{signal.long_strike}/{signal.short_strike} "
                f"x{contracts} @ ${actual_debit:.2f} "
                f"[Order: {order_id}]"
            )

            return position

        except Exception as e:
            logger.error(f"Live execution failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    def close_position(
        self,
        position: SpreadPosition,
        reason: str
    ) -> Tuple[bool, float, float]:
        """
        Close a position.

        Returns: (success, close_price, realized_pnl)
        """
        if self.config.mode == TradingMode.PAPER:
            return self._close_paper(position, reason)
        else:
            return self._close_live(position, reason)

    def _close_paper(
        self,
        position: SpreadPosition,
        reason: str
    ) -> Tuple[bool, float, float]:
        """Close paper position with simulated pricing"""
        try:
            # Get current underlying price
            current_price = self._get_current_price()
            if not current_price:
                current_price = position.underlying_at_entry

            # Estimate current spread value
            close_price = self._estimate_spread_value(position, current_price)

            # Calculate P&L
            # For debit spreads: P&L = (close_value - entry_debit) * 100 * contracts
            pnl_per_contract = (close_price - position.entry_debit) * 100
            realized_pnl = pnl_per_contract * position.contracts

            logger.info(
                f"PAPER CLOSE: {position.position_id} "
                f"@ ${close_price:.2f} "
                f"P&L: ${realized_pnl:.2f} [{reason}]"
            )

            return True, close_price, realized_pnl

        except Exception as e:
            logger.error(f"Paper close failed: {e}")
            return False, 0, 0

    def _close_live(
        self,
        position: SpreadPosition,
        reason: str
    ) -> Tuple[bool, float, float]:
        """Close live position via Tradier"""
        if not self.tradier:
            logger.error("Cannot close live position - Tradier not available")
            return False, 0, 0

        try:
            option_type = "call" if position.spread_type == SpreadType.BULL_CALL else "put"

            # Get current spread quote
            spread_quote = self._get_spread_quote(
                position.long_strike,
                position.short_strike,
                position.expiration,
                option_type
            )

            if not spread_quote:
                logger.error("Failed to get closing quotes")
                return False, 0, 0

            close_price = spread_quote['mid_price']

            # Place closing order (sell the spread)
            order_result = self.tradier.place_vertical_spread(
                symbol=self.config.ticker,
                expiration=position.expiration,
                long_strike=position.long_strike,
                short_strike=position.short_strike,
                option_type=option_type,
                quantity=position.contracts,
                limit_price=round(close_price, 2),
                is_closing=True
            )

            if not order_result or not order_result.get('order'):
                logger.error(f"Close order failed: {order_result}")
                return False, 0, 0

            # Calculate P&L
            pnl_per_contract = (close_price - position.entry_debit) * 100
            realized_pnl = pnl_per_contract * position.contracts

            logger.info(
                f"LIVE CLOSE: {position.position_id} "
                f"@ ${close_price:.2f} "
                f"P&L: ${realized_pnl:.2f} [{reason}]"
            )

            return True, close_price, realized_pnl

        except Exception as e:
            logger.error(f"Live close failed: {e}")
            return False, 0, 0

    def _calculate_position_size(self, max_loss_per_contract: float, thompson_weight: float = 1.0) -> int:
        """
        Calculate position size based on risk settings and Thompson allocation.

        Args:
            max_loss_per_contract: Maximum loss per contract in dollars
            thompson_weight: Thompson Sampling allocation weight (0.5-2.0)
                            - 1.0 = neutral (standard sizing)
                            - 1.5 = bot is performing well, increase size 50%
                            - 0.7 = bot is underperforming, reduce size 30%

        Returns:
            Number of contracts to trade (minimum 1)
        """
        # This should use current capital, but for simplicity using default
        max_risk = 100_000 * (self.config.risk_per_trade_pct / 100)

        if max_loss_per_contract <= 0:
            return 1

        # Base position size from risk calculation
        base_contracts = max_risk / max_loss_per_contract

        # Apply Thompson Sampling weight (clamped to reasonable bounds)
        clamped_weight = max(0.5, min(2.0, thompson_weight))
        adjusted_contracts = int(base_contracts * clamped_weight)

        # Log if Thompson made a difference
        if abs(thompson_weight - 1.0) > 0.05:
            logger.info(f"Thompson allocation: weight={thompson_weight:.2f}, base={base_contracts:.1f}, adjusted={adjusted_contracts}")

        return max(1, min(adjusted_contracts, 50))  # Min 1, max 50

    def _get_current_price(self) -> Optional[float]:
        """Get current underlying price"""
        if DATA_AVAILABLE:
            try:
                return get_price(self.config.ticker)
            except Exception:
                pass
        return None

    def _get_spread_quote(
        self,
        long_strike: float,
        short_strike: float,
        expiration: str,
        option_type: str
    ) -> Optional[Dict[str, float]]:
        """Get quote for the spread"""
        if not self.tradier:
            return None

        try:
            # Build option symbols
            long_symbol = self._build_option_symbol(
                self.config.ticker, expiration, long_strike, option_type
            )
            short_symbol = self._build_option_symbol(
                self.config.ticker, expiration, short_strike, option_type
            )

            # Get quotes
            long_quote = self.tradier.get_option_quote(long_symbol)
            short_quote = self.tradier.get_option_quote(short_symbol)

            if long_quote and short_quote:
                long_mid = (long_quote.get('bid', 0) + long_quote.get('ask', 0)) / 2
                short_mid = (short_quote.get('bid', 0) + short_quote.get('ask', 0)) / 2

                # For debit spread: pay for long, receive for short
                mid_price = long_mid - short_mid

                return {
                    'long_bid': long_quote.get('bid', 0),
                    'long_ask': long_quote.get('ask', 0),
                    'short_bid': short_quote.get('bid', 0),
                    'short_ask': short_quote.get('ask', 0),
                    'mid_price': max(0.01, mid_price),  # Min 1 cent
                }
        except Exception as e:
            logger.warning(f"Failed to get spread quote: {e}")

        return None

    def _build_option_symbol(
        self,
        ticker: str,
        expiration: str,
        strike: float,
        option_type: str
    ) -> str:
        """Build OCC option symbol"""
        # Format: SPY250103C00600000
        exp_date = datetime.strptime(expiration, "%Y-%m-%d")
        exp_str = exp_date.strftime("%y%m%d")
        opt_char = "C" if option_type.lower() == "call" else "P"
        strike_str = f"{int(strike * 1000):08d}"
        return f"{ticker}{exp_str}{opt_char}{strike_str}"

    def _estimate_spread_value(
        self,
        position: SpreadPosition,
        current_price: float
    ) -> float:
        """Estimate current spread value for paper trading"""
        spread_width = abs(position.short_strike - position.long_strike)

        if position.spread_type == SpreadType.BULL_CALL:
            # Bull call spread value increases as price goes up
            if current_price >= position.short_strike:
                # Max profit - spread is fully ITM
                return spread_width
            elif current_price <= position.long_strike:
                # Max loss - spread is OTM
                return 0
            else:
                # Partial - linear interpolation
                pct_itm = (current_price - position.long_strike) / spread_width
                return spread_width * pct_itm
        else:
            # Bear put spread value increases as price goes down
            if current_price <= position.short_strike:
                # Max profit
                return spread_width
            elif current_price >= position.long_strike:
                # Max loss
                return 0
            else:
                pct_itm = (position.long_strike - current_price) / spread_width
                return spread_width * pct_itm

    def get_position_current_value(
        self,
        position: SpreadPosition
    ) -> Optional[float]:
        """Get current value of a position"""
        if self.config.mode == TradingMode.PAPER:
            current_price = self._get_current_price()
            if current_price:
                return self._estimate_spread_value(position, current_price)
            return None
        else:
            option_type = "call" if position.spread_type == SpreadType.BULL_CALL else "put"
            spread_quote = self._get_spread_quote(
                position.long_strike,
                position.short_strike,
                position.expiration,
                option_type
            )
            if spread_quote:
                return spread_quote['mid_price']
            return None
