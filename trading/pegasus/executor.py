"""
PEGASUS - Order Executor
=========================

SPX Iron Condor execution via Tradier.
Uses SPXW symbols for weekly options.
"""

import logging
import uuid
import time
from datetime import datetime
from typing import Optional, Dict, Tuple

from .models import (
    IronCondorPosition, PositionStatus,
    IronCondorSignal, PEGASUSConfig, TradingMode, CENTRAL_TZ
)

# Monte Carlo Kelly for intelligent position sizing
KELLY_AVAILABLE = False
try:
    from quant.monte_carlo_kelly import get_safe_position_size
    KELLY_AVAILABLE = True
except ImportError:
    pass

logger = logging.getLogger(__name__)

try:
    from data.tradier_data_fetcher import TradierDataFetcher
    TRADIER_AVAILABLE = True
except ImportError:
    TRADIER_AVAILABLE = False
    TradierDataFetcher = None

try:
    from data.unified_data_provider import get_price
    DATA_AVAILABLE = True
except ImportError:
    DATA_AVAILABLE = False


class OrderExecutor:
    """Executes SPX Iron Condors"""

    def __init__(self, config: PEGASUSConfig, db=None):
        self.config = config
        self.tradier = None
        self.db = db  # Optional DB reference for orphaned order tracking

        if TRADIER_AVAILABLE and config.mode == TradingMode.LIVE:
            try:
                # CRITICAL: Pass sandbox=False for LIVE mode to use production Tradier account
                self.tradier = TradierDataFetcher(sandbox=False)
                logger.info("PEGASUS: Tradier initialized (PRODUCTION)")
            except Exception as e:
                logger.error(f"Tradier init failed: {e}")

    def _tradier_place_spread_with_retry(
        self,
        max_retries: int = 3,
        **kwargs
    ) -> Optional[Dict]:
        """
        Place a vertical spread order with retry logic.

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

        if last_error:
            raise last_error
        return None

    def _tradier_get_quote_with_retry(
        self,
        symbol: str,
        max_retries: int = 2
    ) -> Optional[Dict]:
        """Get option quote with retry logic."""
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
                    delay = 0.5 * (2 ** attempt)
                    logger.debug(f"Quote fetch error (attempt {attempt + 1}): {e}. Retrying...")
                    time.sleep(delay)
                else:
                    logger.warning(f"Quote fetch failed after {max_retries} attempts: {e}")

        return None

    def execute_iron_condor(self, signal: IronCondorSignal) -> Optional[IronCondorPosition]:
        """Execute SPX Iron Condor"""
        if self.config.mode == TradingMode.PAPER:
            return self._execute_paper(signal)
        else:
            return self._execute_live(signal)

    def _execute_paper(self, signal: IronCondorSignal) -> Optional[IronCondorPosition]:
        """Paper trade execution with FULL Oracle/Kronos context"""
        try:
            import json
            now = datetime.now(CENTRAL_TZ)
            position_id = f"PEGASUS-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

            contracts = self._calculate_position_size(signal.max_loss)
            max_profit = signal.total_credit * 100 * contracts
            max_loss = (self.config.spread_width - signal.total_credit) * 100 * contracts

            # Convert Oracle top_factors to JSON string for DB storage
            oracle_factors_json = json.dumps(signal.oracle_top_factors) if signal.oracle_top_factors else ""

            position = IronCondorPosition(
                position_id=position_id,
                ticker="SPX",
                expiration=signal.expiration,
                put_short_strike=signal.put_short,
                put_long_strike=signal.put_long,
                put_credit=signal.estimated_put_credit,
                call_short_strike=signal.call_short,
                call_long_strike=signal.call_long,
                call_credit=signal.estimated_call_credit,
                contracts=contracts,
                spread_width=self.config.spread_width,
                total_credit=signal.total_credit,
                max_profit=max_profit,
                max_loss=max_loss,
                underlying_at_entry=signal.spot_price,
                vix_at_entry=signal.vix,
                expected_move=signal.expected_move,
                call_wall=signal.call_wall,
                put_wall=signal.put_wall,
                gex_regime=signal.gex_regime,
                # Kronos GEX context (FULL audit trail)
                flip_point=signal.flip_point,
                net_gex=signal.net_gex,
                # Oracle context (FULL audit trail)
                oracle_confidence=signal.confidence,
                oracle_win_probability=signal.oracle_win_probability,
                oracle_advice=signal.oracle_advice,
                oracle_reasoning=signal.reasoning,
                oracle_top_factors=oracle_factors_json,
                oracle_use_gex_walls=signal.oracle_use_gex_walls,
                put_order_id="PAPER",
                call_order_id="PAPER",
                status=PositionStatus.OPEN,
                open_time=now,
            )

            logger.info(
                f"PAPER SPX IC: {signal.put_long}/{signal.put_short}-{signal.call_short}/{signal.call_long} "
                f"x{contracts} @ ${signal.total_credit:.2f}"
            )
            logger.info(f"Context: Oracle={signal.oracle_advice} ({signal.oracle_win_probability:.0%}), GEX Regime={signal.gex_regime}")

            return position
        except Exception as e:
            logger.error(f"Paper execution failed: {e}")
            return None

    def _execute_live(self, signal: IronCondorSignal) -> Optional[IronCondorPosition]:
        """Live SPX execution with FULL Oracle/Kronos context - uses SPXW symbols"""
        if not self.tradier:
            logger.error("Tradier not available")
            return None

        try:
            import json
            now = datetime.now(CENTRAL_TZ)
            contracts = self._calculate_position_size(signal.max_loss)

            # Execute put spread (credit spread: short > long for bull put)
            # Note: place_vertical_spread automatically determines credit/debit from strikes
            # Using retry wrapper for network resilience
            put_result = self._tradier_place_spread_with_retry(
                symbol="SPXW",  # Weekly SPX options
                expiration=signal.expiration,
                long_strike=signal.put_long,
                short_strike=signal.put_short,
                option_type="put",
                quantity=contracts,
                limit_price=round(signal.estimated_put_credit, 2),
            )

            if not put_result or not put_result.get('order'):
                logger.error(f"Put spread failed: {put_result}")
                return None

            put_order_id = str(put_result['order'].get('id', 'UNKNOWN'))

            # Execute call spread (credit spread: short < long for bear call)
            # Note: place_vertical_spread automatically determines credit/debit from strikes
            # Using retry wrapper
            call_result = self._tradier_place_spread_with_retry(
                symbol="SPXW",
                expiration=signal.expiration,
                long_strike=signal.call_long,
                short_strike=signal.call_short,
                option_type="call",
                quantity=contracts,
                limit_price=round(signal.estimated_call_credit, 2),
            )

            if not call_result or not call_result.get('order'):
                logger.error(f"Call spread failed: {call_result}")
                # CRITICAL: Put spread was already placed - attempt to close it
                logger.warning(f"Attempting to rollback put spread order {put_order_id}")
                rollback_failed = False
                rollback_error_msg = None
                try:
                    # Close put spread by reversing the order (swap long/short to create debit)
                    # Extra retries for critical rollback
                    rollback_result = self._tradier_place_spread_with_retry(
                        max_retries=4,
                        symbol="SPXW",
                        expiration=signal.expiration,
                        long_strike=signal.put_short,  # Buy back short
                        short_strike=signal.put_long,   # Sell long
                        option_type="put",
                        quantity=contracts,
                        limit_price=round(signal.estimated_put_credit * 1.1, 2),  # Allow slippage for rollback
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
                        ticker='SPX',
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

            max_profit = signal.total_credit * 100 * contracts
            max_loss = (self.config.spread_width - signal.total_credit) * 100 * contracts

            # Convert Oracle top_factors to JSON string for DB storage
            oracle_factors_json = json.dumps(signal.oracle_top_factors) if signal.oracle_top_factors else ""

            position = IronCondorPosition(
                position_id=f"PEGASUS-LIVE-{put_order_id}",
                ticker="SPX",
                expiration=signal.expiration,
                put_short_strike=signal.put_short,
                put_long_strike=signal.put_long,
                put_credit=signal.estimated_put_credit,
                call_short_strike=signal.call_short,
                call_long_strike=signal.call_long,
                call_credit=signal.estimated_call_credit,
                contracts=contracts,
                spread_width=self.config.spread_width,
                total_credit=signal.total_credit,
                max_profit=max_profit,
                max_loss=max_loss,
                underlying_at_entry=signal.spot_price,
                vix_at_entry=signal.vix,
                expected_move=signal.expected_move,
                call_wall=signal.call_wall,
                put_wall=signal.put_wall,
                gex_regime=signal.gex_regime,
                # Kronos GEX context (FULL audit trail)
                flip_point=signal.flip_point,
                net_gex=signal.net_gex,
                # Oracle context (FULL audit trail)
                oracle_confidence=signal.confidence,
                oracle_win_probability=signal.oracle_win_probability,
                oracle_advice=signal.oracle_advice,
                oracle_reasoning=signal.reasoning,
                oracle_top_factors=oracle_factors_json,
                oracle_use_gex_walls=signal.oracle_use_gex_walls,
                put_order_id=put_order_id,
                call_order_id=call_order_id,
                status=PositionStatus.OPEN,
                open_time=now,
            )

            logger.info(f"LIVE SPX IC: {signal.put_long}/{signal.put_short}-{signal.call_short}/{signal.call_long} x{contracts}")
            logger.info(f"Context: Oracle={signal.oracle_advice} ({signal.oracle_win_probability:.0%}), GEX Regime={signal.gex_regime}")
            return position
        except Exception as e:
            logger.error(f"Live execution failed: {e}")
            return None

    def close_position(self, position: IronCondorPosition, reason: str) -> Tuple[bool, float, float]:
        """Close SPX IC position"""
        if self.config.mode == TradingMode.PAPER:
            return self._close_paper(position, reason)
        else:
            return self._close_live(position, reason)

    def _close_paper(self, position: IronCondorPosition, reason: str) -> Tuple[bool, float, float]:
        try:
            # For SPX European-style cash-settled options at expiration,
            # use the settlement price (opening price) not the current intraday price
            is_expiration = reason in ['EXPIRED', 'FORCE_EXIT']

            if is_expiration:
                # SPX options are cash-settled using AM settlement price (opening price)
                # At expiration, the intrinsic value is calculated based on where SPX opened
                settlement_price = self._get_spx_settlement_price(position.expiration)
                if not settlement_price:
                    logger.warning(
                        f"Could not get SPX settlement price for {position.expiration}, "
                        f"using current price instead"
                    )
                    settlement_price = self._get_current_spx_price() or position.underlying_at_entry

                # Calculate intrinsic value at settlement for European-style cash settlement
                close_value = self._calculate_cash_settlement_value(position, settlement_price)
                logger.info(
                    f"SPX CASH SETTLEMENT: {position.position_id} @ SPX {settlement_price:.2f}, "
                    f"IC value=${close_value:.2f}"
                )
            else:
                current_price = self._get_current_spx_price()
                if not current_price:
                    current_price = position.underlying_at_entry
                close_value = self._estimate_ic_value(position, current_price)

            pnl = (position.total_credit - close_value) * 100 * position.contracts

            logger.info(f"PAPER CLOSE: {position.position_id} @ ${close_value:.2f}, P&L=${pnl:.2f}")
            return True, close_value, pnl
        except Exception as e:
            logger.error(f"Close failed: {e}")
            return False, 0, 0

    def _get_spx_settlement_price(self, expiration: str) -> Optional[float]:
        """
        Get SPX settlement price (AM opening price) for European-style cash settlement.

        For SPX weekly options (SPXW), settlement is based on the Special Opening Quotation (SOQ)
        which is calculated from the opening prices of SPX component stocks.
        """
        try:
            # For paper trading, we use the SPX open price as settlement
            # In production, this would come from CBOE settlement data
            if DATA_AVAILABLE:
                from data.unified_data_provider import get_ohlcv
                ohlcv = get_ohlcv("SPX", "1D")
                if ohlcv and len(ohlcv) > 0:
                    # Return today's opening price
                    return ohlcv[-1].get('open')
        except Exception as e:
            logger.debug(f"Could not get SPX settlement price: {e}")

        # Fallback to current price
        return self._get_current_spx_price()

    def _calculate_cash_settlement_value(
        self,
        position: IronCondorPosition,
        settlement_price: float
    ) -> float:
        """
        Calculate cash settlement value for SPX Iron Condor at expiration.

        SPX options are European-style and cash-settled:
        - If settlement price is between short strikes: All legs expire worthless (max profit)
        - If settlement breaches put side: Loss = (put_short - settlement) capped at spread width
        - If settlement breaches call side: Loss = (settlement - call_short) capped at spread width
        """
        put_short = position.put_short_strike
        put_long = position.put_long_strike
        call_short = position.call_short_strike
        call_long = position.call_long_strike
        spread_width = position.spread_width

        # If within short strikes - max profit (IC expires worthless)
        if put_short < settlement_price < call_short:
            return 0.0

        # If below put short strike - put spread has intrinsic value
        if settlement_price <= put_short:
            put_intrinsic = put_short - settlement_price
            # Cap at spread width minus any value from call spread
            return min(put_intrinsic, spread_width)

        # If above call short strike - call spread has intrinsic value
        if settlement_price >= call_short:
            call_intrinsic = settlement_price - call_short
            # Cap at spread width
            return min(call_intrinsic, spread_width)

        return 0.0

    def _close_live(self, position: IronCondorPosition, reason: str) -> Tuple[bool, float, float]:
        if not self.tradier:
            return False, 0, 0

        try:
            # Get current quotes for closing
            current_price = self._get_current_spx_price()
            if not current_price:
                current_price = position.underlying_at_entry

            close_value = self._estimate_ic_value(position, current_price)

            # Close put spread by reversing the order (buy to close short, sell to close long)
            # We swap long/short so the spread becomes a debit (we pay to close)
            # Using retry wrapper for network resilience
            put_result = self._tradier_place_spread_with_retry(
                symbol="SPXW",
                expiration=position.expiration,
                long_strike=position.put_short_strike,  # Buy back short
                short_strike=position.put_long_strike,   # Sell long
                option_type="put",
                quantity=position.contracts,
                limit_price=round(close_value / 2, 2),  # Half of total close value
            )

            if not put_result or not put_result.get('order'):
                logger.error(f"Failed to close put spread: {put_result}")
                return False, 0, 0

            # Close call spread by reversing the order - with retry
            call_result = self._tradier_place_spread_with_retry(
                symbol="SPXW",
                expiration=position.expiration,
                long_strike=position.call_short_strike,  # Buy back short
                short_strike=position.call_long_strike,   # Sell long
                option_type="call",
                quantity=position.contracts,
                limit_price=round(close_value / 2, 2),  # Half of total close value
            )

            if not call_result or not call_result.get('order'):
                logger.error(f"Failed to close call spread (put was closed!): {call_result}")
                # Note: Put spread was already closed - this is a partial close situation
                # Calculate partial P&L for the put side only
                partial_pnl = (position.put_credit - close_value / 2) * 100 * position.contracts
                logger.warning(f"PARTIAL CLOSE: Put side closed, P&L=${partial_pnl:.2f}")
                # Return special tuple indicating partial close (success='partial_put')
                # Caller should handle this by marking position as partial_close in DB
                return 'partial_put', close_value / 2, partial_pnl

            # P&L = credit received - debit to close
            pnl = (position.total_credit - close_value) * 100 * position.contracts

            logger.info(f"LIVE CLOSE: {position.position_id} @ ${close_value:.2f}, P&L=${pnl:.2f} [{reason}]")
            return True, close_value, pnl
        except Exception as e:
            logger.error(f"Live close failed: {e}")
            import traceback
            traceback.print_exc()
            return False, 0, 0

    def _get_kelly_position_size(self) -> Optional[Dict]:
        """Get Monte Carlo Kelly-based position sizing for PEGASUS."""
        if not KELLY_AVAILABLE:
            return None

        try:
            from database_adapter import DatabaseAdapter
            db = DatabaseAdapter()

            trades = db.execute_query("""
                SELECT pnl_realized, entry_credit, max_loss
                FROM autonomous_closed_trades
                WHERE bot_name = 'PEGASUS'
                AND closed_at > NOW() - INTERVAL '90 days'
                ORDER BY closed_at DESC
                LIMIT 100
            """)

            if not trades or len(trades) < 20:
                return None

            wins = [t for t in trades if t['pnl_realized'] > 0]
            losses = [t for t in trades if t['pnl_realized'] <= 0]

            win_rate = len(wins) / len(trades)
            avg_win_pct = sum(t['pnl_realized'] for t in wins) / len(wins) / self.config.capital * 100 if wins else 0
            avg_loss_pct = abs(sum(t['pnl_realized'] for t in losses) / len(losses) / self.config.capital * 100) if losses else 10

            kelly_result = get_safe_position_size(
                win_rate=win_rate,
                avg_win=avg_win_pct,
                avg_loss=avg_loss_pct,
                sample_size=len(trades),
                account_size=self.config.capital,
                max_risk_pct=self.config.risk_per_trade_pct * 2
            )

            logger.info(f"[PEGASUS KELLY] Win Rate: {win_rate:.1%}, Safe Kelly: {kelly_result['kelly_safe']:.1f}%")
            return kelly_result

        except Exception as e:
            logger.debug(f"[KELLY] Error: {e}")
            return None

    def _calculate_position_size(self, max_loss_per_contract: float) -> int:
        """Calculate position size using Monte Carlo Kelly criterion."""
        capital = self.config.capital

        if max_loss_per_contract <= 0:
            return 1

        # Try Kelly-based sizing first
        kelly_result = self._get_kelly_position_size()

        if kelly_result and kelly_result.get('kelly_safe', 0) > 0:
            kelly_risk_pct = kelly_result['kelly_safe']
            max_risk = capital * (kelly_risk_pct / 100)
            logger.info(f"[PEGASUS] Using Kelly-safe sizing: {kelly_risk_pct:.1f}% risk")
        else:
            max_risk = capital * (self.config.risk_per_trade_pct / 100)

        contracts = int(max_risk / max_loss_per_contract)
        return max(1, min(contracts, self.config.max_contracts))

    def _get_current_spx_price(self) -> Optional[float]:
        if DATA_AVAILABLE:
            try:
                spx = get_price("SPX")
                if spx:
                    return spx
                spy = get_price("SPY")
                if spy:
                    return spy * 10
            except Exception as e:
                logger.debug(f"Failed to get SPX price: {e}")
        return None

    def _estimate_ic_value(self, position: IronCondorPosition, current_price: float) -> float:
        """Estimate current IC value"""
        if position.put_short_strike < current_price < position.call_short_strike:
            put_dist = (current_price - position.put_short_strike) / position.spread_width
            call_dist = (position.call_short_strike - current_price) / position.spread_width
            factor = min(put_dist, call_dist) / 2
            return position.total_credit * max(0.1, 0.5 - factor * 0.3)
        elif current_price <= position.put_short_strike:
            intrinsic = position.put_short_strike - current_price
            return min(position.spread_width, intrinsic + position.total_credit * 0.2)
        else:
            intrinsic = current_price - position.call_short_strike
            return min(position.spread_width, intrinsic + position.total_credit * 0.2)

    def get_position_current_value(self, position: IronCondorPosition) -> Optional[float]:
        current_price = self._get_current_spx_price()
        if current_price:
            return self._estimate_ic_value(position, current_price)
        return None
