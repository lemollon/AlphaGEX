"""
TITAN - Order Executor
=======================

SPX Iron Condor execution via Tradier for aggressive trading.
Uses SPXW symbols with $12 spread widths.
"""

import logging
import uuid
import time
from datetime import datetime
from typing import Optional, Dict, Tuple, Union

from .models import (
    IronCondorPosition, PositionStatus,
    IronCondorSignal, TITANConfig, TradingMode, CENTRAL_TZ
)

# Monte Carlo Kelly for intelligent position sizing
KELLY_AVAILABLE = False
try:
    from quant.monte_carlo_kelly import get_safe_position_size
    KELLY_AVAILABLE = True
except ImportError:
    pass

# Position Management Agent - tracks entry conditions and alerts on regime changes
POSITION_MGMT_AVAILABLE = False
try:
    from ai.position_management_agent import PositionManagementAgent
    POSITION_MGMT_AVAILABLE = True
except ImportError:
    PositionManagementAgent = None

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
    """Executes aggressive SPX Iron Condors for TITAN"""

    def __init__(self, config: TITANConfig, db=None):
        self.config = config
        self.tradier = None
        self.db = db  # Optional DB reference for orphaned order tracking

        if TRADIER_AVAILABLE and config.mode == TradingMode.LIVE:
            try:
                # CRITICAL: Pass sandbox=False for LIVE mode to use production Tradier account
                self.tradier = TradierDataFetcher(sandbox=False)
                logger.info("TITAN: Tradier initialized (PRODUCTION)")
            except Exception as e:
                logger.error(f"Tradier init failed: {e}")

        # Position Management Agent - tracks entry conditions for exit timing
        self.position_mgmt = None
        if POSITION_MGMT_AVAILABLE:
            try:
                self.position_mgmt = PositionManagementAgent()
                logger.info("TITAN OrderExecutor: Position Management Agent initialized")
            except Exception as e:
                logger.debug(f"Position Management Agent init failed: {e}")

    def _tradier_place_spread_with_retry(
        self,
        max_retries: int = 3,
        **kwargs
    ) -> Optional[Dict]:
        """
        Place a vertical spread order with retry logic.
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
                    delay = 1.0 * (2 ** attempt)
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
            position_id = f"TITAN-{now.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"

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
                f"TITAN PAPER SPX IC: {signal.put_long}/{signal.put_short}-{signal.call_short}/{signal.call_long} "
                f"x{contracts} @ ${signal.total_credit:.2f}"
            )
            logger.info(f"Context: Oracle={signal.oracle_advice} ({signal.oracle_win_probability:.0%}), GEX Regime={signal.gex_regime}")

            return position
        except Exception as e:
            logger.error(f"Paper execution failed: {e}")
            return None

    def _execute_live(self, signal: IronCondorSignal) -> Optional[IronCondorPosition]:
        """Live SPX execution with FULL Oracle/Kronos context"""
        if not self.tradier:
            logger.error("Tradier not available")
            return None

        try:
            import json
            now = datetime.now(CENTRAL_TZ)
            contracts = self._calculate_position_size(signal.max_loss)

            # Execute put spread with retry
            put_result = self._tradier_place_spread_with_retry(
                symbol="SPXW",
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

            # Execute call spread with retry
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
                # Attempt to rollback put spread
                logger.warning(f"Attempting to rollback put spread order {put_order_id}")
                rollback_failed = False
                rollback_error_msg = None
                try:
                    rollback_result = self._tradier_place_spread_with_retry(
                        max_retries=4,
                        symbol="SPXW",
                        expiration=signal.expiration,
                        long_strike=signal.put_short,
                        short_strike=signal.put_long,
                        option_type="put",
                        quantity=contracts,
                        limit_price=round(signal.estimated_put_credit * 1.1, 2),
                    )
                    if rollback_result and rollback_result.get('order'):
                        logger.info(f"Successfully rolled back put spread order {put_order_id}")
                    else:
                        rollback_failed = True
                        rollback_error_msg = f"Rollback returned: {rollback_result}"
                        logger.error(f"CRITICAL: Failed to rollback put spread {put_order_id}")
                except Exception as rollback_error:
                    rollback_failed = True
                    rollback_error_msg = str(rollback_error)
                    logger.error(f"CRITICAL: Rollback exception for {put_order_id}: {rollback_error}")

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

            oracle_factors_json = json.dumps(signal.oracle_top_factors) if signal.oracle_top_factors else ""

            position = IronCondorPosition(
                position_id=f"TITAN-LIVE-{put_order_id}",
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
                # Kronos GEX context
                flip_point=signal.flip_point,
                net_gex=signal.net_gex,
                # Oracle context
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

            logger.info(f"TITAN LIVE SPX IC: {signal.put_long}/{signal.put_short}-{signal.call_short}/{signal.call_long} x{contracts}")
            logger.info(f"Context: Oracle={signal.oracle_advice} ({signal.oracle_win_probability:.0%}), GEX Regime={signal.gex_regime}")
            return position
        except Exception as e:
            logger.error(f"Live execution failed: {e}")
            return None

    def close_position(self, position: IronCondorPosition, reason: str) -> Tuple[Union[bool, str], float, float]:
        """Close SPX IC position"""
        if self.config.mode == TradingMode.PAPER:
            return self._close_paper(position, reason)
        else:
            return self._close_live(position, reason)

    def _close_paper(self, position: IronCondorPosition, reason: str) -> Tuple[Union[bool, str], float, float]:
        try:
            is_expiration = reason in ['EXPIRED', 'FORCE_EXIT']

            if is_expiration:
                settlement_price = self._get_spx_settlement_price(position.expiration)
                if not settlement_price:
                    settlement_price = self._get_current_spx_price() or position.underlying_at_entry
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

            logger.info(f"TITAN PAPER CLOSE: {position.position_id} @ ${close_value:.2f}, P&L=${pnl:.2f}")
            return True, close_value, pnl
        except Exception as e:
            logger.error(f"Close failed: {e}")
            return False, 0, 0

    def _get_spx_settlement_price(self, expiration: str) -> Optional[float]:
        """Get SPX settlement price for European-style cash settlement."""
        try:
            if DATA_AVAILABLE:
                from data.unified_data_provider import get_ohlcv
                ohlcv = get_ohlcv("SPX", "1D")
                if ohlcv and len(ohlcv) > 0:
                    return ohlcv[-1].get('open')
        except Exception as e:
            logger.debug(f"Could not get SPX settlement price: {e}")
        return self._get_current_spx_price()

    def _calculate_cash_settlement_value(
        self,
        position: IronCondorPosition,
        settlement_price: float
    ) -> float:
        """Calculate cash settlement value for SPX Iron Condor at expiration."""
        put_short = position.put_short_strike
        put_long = position.put_long_strike
        call_short = position.call_short_strike
        call_long = position.call_long_strike
        spread_width = position.spread_width

        # If within short strikes - max profit
        if put_short < settlement_price < call_short:
            return 0.0

        # If below put short strike
        if settlement_price <= put_short:
            put_intrinsic = put_short - settlement_price
            return min(put_intrinsic, spread_width)

        # If above call short strike
        if settlement_price >= call_short:
            call_intrinsic = settlement_price - call_short
            return min(call_intrinsic, spread_width)

        return 0.0

    def _close_live(self, position: IronCondorPosition, reason: str) -> Tuple[Union[bool, str], float, float]:
        if not self.tradier:
            return False, 0, 0

        try:
            current_price = self._get_current_spx_price()
            if not current_price:
                current_price = position.underlying_at_entry

            close_value = self._estimate_ic_value(position, current_price)

            # Close put spread
            put_result = self._tradier_place_spread_with_retry(
                symbol="SPXW",
                expiration=position.expiration,
                long_strike=position.put_short_strike,
                short_strike=position.put_long_strike,
                option_type="put",
                quantity=position.contracts,
                limit_price=round(close_value / 2, 2),
            )

            if not put_result or not put_result.get('order'):
                logger.error(f"Failed to close put spread: {put_result}")
                return False, 0, 0

            # Close call spread
            call_result = self._tradier_place_spread_with_retry(
                symbol="SPXW",
                expiration=position.expiration,
                long_strike=position.call_short_strike,
                short_strike=position.call_long_strike,
                option_type="call",
                quantity=position.contracts,
                limit_price=round(close_value / 2, 2),
            )

            if not call_result or not call_result.get('order'):
                logger.error(f"Failed to close call spread (put was closed!): {call_result}")
                partial_pnl = (position.put_credit - close_value / 2) * 100 * position.contracts
                logger.warning(f"PARTIAL CLOSE: Put side closed, P&L=${partial_pnl:.2f}")
                return 'partial_put', close_value / 2, partial_pnl

            pnl = (position.total_credit - close_value) * 100 * position.contracts

            logger.info(f"TITAN LIVE CLOSE: {position.position_id} @ ${close_value:.2f}, P&L=${pnl:.2f} [{reason}]")
            return True, close_value, pnl
        except Exception as e:
            logger.error(f"Live close failed: {e}")
            import traceback
            traceback.print_exc()
            return False, 0, 0

    def _get_kelly_position_size(self) -> Optional[Dict]:
        """Get Monte Carlo Kelly-based position sizing for TITAN."""
        if not KELLY_AVAILABLE:
            return None

        try:
            from database_adapter import DatabaseAdapter
            db = DatabaseAdapter()

            trades = db.execute_query("""
                SELECT pnl_realized, entry_credit, max_loss
                FROM autonomous_closed_trades
                WHERE bot_name = 'TITAN'
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

            logger.info(f"[TITAN KELLY] Win Rate: {win_rate:.1%}, Safe Kelly: {kelly_result['kelly_safe']:.1f}%")
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
            logger.info(f"[TITAN] Using Kelly-safe sizing: {kelly_risk_pct:.1f}% risk")
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

    def store_entry_conditions(self, position_id: int, gex_data: Dict) -> bool:
        """
        Store entry conditions when position is opened.

        This enables the Position Management Agent to detect when market
        conditions change significantly from entry (GEX regime flip, etc.)
        """
        if not self.position_mgmt:
            return False

        try:
            self.position_mgmt.store_entry_conditions(position_id, gex_data)
            logger.info(f"[TITAN] Entry conditions stored for position {position_id}")
            return True
        except Exception as e:
            logger.debug(f"Failed to store entry conditions: {e}")
            return False

    def check_position_conditions(self, position: Dict, current_gex: Dict) -> Dict:
        """
        Check if current conditions differ from entry conditions.

        Returns alerts if GEX regime flipped, flip point moved significantly, etc.
        This helps with exit timing - exit early if thesis is invalidated.
        """
        if not self.position_mgmt:
            return {'alerts': [], 'severity': 'info', 'should_exit_early': False}

        try:
            result = self.position_mgmt.check_position_conditions(position, current_gex)

            # Add should_exit_early flag for critical alerts
            should_exit = result.get('severity') == 'critical'
            result['should_exit_early'] = should_exit

            if result.get('alerts'):
                for alert in result['alerts']:
                    logger.info(f"[TITAN CONDITION ALERT] {alert['type']}: {alert['message']}")
                    if alert.get('suggestion'):
                        logger.info(f"  Suggestion: {alert['suggestion']}")

            return result

        except Exception as e:
            logger.debug(f"Failed to check position conditions: {e}")
            return {'alerts': [], 'severity': 'info', 'should_exit_early': False}
