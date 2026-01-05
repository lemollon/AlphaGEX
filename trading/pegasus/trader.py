"""
PEGASUS - Main Trading Orchestrator
=====================================

SPX Iron Condor trading bot.
One trade per day with $10 spreads.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from .models import (
    IronCondorPosition, PositionStatus, PEGASUSConfig,
    TradingMode, DailySummary, CENTRAL_TZ
)
from .db import PEGASUSDatabase
from .signals import SignalGenerator
from .executor import OrderExecutor

logger = logging.getLogger(__name__)

try:
    from trading.circuit_breaker import is_trading_enabled, record_trade_pnl
    CIRCUIT_BREAKER_AVAILABLE = True
except ImportError:
    CIRCUIT_BREAKER_AVAILABLE = False
    is_trading_enabled = None

# Scan activity logging
try:
    from trading.scan_activity_logger import log_pegasus_scan, ScanOutcome, CheckResult
    SCAN_LOGGER_AVAILABLE = True
except ImportError:
    SCAN_LOGGER_AVAILABLE = False
    log_pegasus_scan = None
    ScanOutcome = None
    CheckResult = None

# Bot decision logging (for bot_decision_logs table)
try:
    from trading.bot_logger import (
        log_bot_decision, BotDecision, MarketContext as BotLogMarketContext,
        GEXContext, OracleContext, TradeDetails, RiskChecks, DecisionType
    )
    BOT_LOGGER_AVAILABLE = True
except ImportError:
    BOT_LOGGER_AVAILABLE = False
    log_bot_decision = None
    BotDecision = None

# Oracle for outcome recording and strategy recommendations
try:
    from quant.oracle_advisor import (
        OracleAdvisor, BotName as OracleBotName, TradeOutcome as OracleTradeOutcome,
        MarketContext as OracleMarketContext, GEXRegime, StrategyType, get_oracle
    )
    ORACLE_AVAILABLE = True
except ImportError:
    ORACLE_AVAILABLE = False
    OracleAdvisor = None
    OracleBotName = None
    OracleTradeOutcome = None
    OracleMarketContext = None
    GEXRegime = None
    StrategyType = None
    get_oracle = None

# Learning Memory for self-improvement tracking
try:
    from ai.gexis_learning_memory import get_learning_memory
    LEARNING_MEMORY_AVAILABLE = True
except ImportError:
    LEARNING_MEMORY_AVAILABLE = False
    get_learning_memory = None

# Math Optimizer integration for enhanced trading decisions
try:
    from trading.mixins.math_optimizer_mixin import MathOptimizerMixin
    MATH_OPTIMIZER_AVAILABLE = True
except ImportError:
    MATH_OPTIMIZER_AVAILABLE = False
    MathOptimizerMixin = object


class PEGASUSTrader(MathOptimizerMixin):
    """
    PEGASUS - SPX Iron Condor Trader

    Usage:
        trader = PEGASUSTrader()
        result = trader.run_cycle()

    MATH OPTIMIZER INTEGRATION:
    - HMM Regime Detection: Bayesian regime filtering
    - Thompson Sampling: Dynamic capital allocation
    - HJB Exit Optimizer: Optimal exit timing
    """

    def __init__(self, config: Optional[PEGASUSConfig] = None):
        self.db = PEGASUSDatabase(bot_name="PEGASUS")
        self.config = config or self.db.load_config()
        self.signals = SignalGenerator(self.config)
        self.executor = OrderExecutor(self.config)

        # Learning Memory prediction tracking (position_id -> prediction_id)
        self._prediction_ids: Dict[str, str] = {}

        # Initialize Math Optimizers (HMM, Thompson Sampling, HJB Exit)
        if MATH_OPTIMIZER_AVAILABLE:
            try:
                self._init_math_optimizers("PEGASUS", enabled=True)
                # PEGASUS positions strikes OUTSIDE the expected move, so trending regimes
                # should NOT block trades - the market can trend and still stay in profit zone
                # Allow ALL regimes - only avoid extreme gamma squeeze conditions
                self.math_set_config('favorable_regimes', [
                    'LOW_VOLATILITY', 'MEAN_REVERTING', 'TRENDING_BULLISH',
                    'TRENDING_BEARISH', 'HIGH_VOLATILITY'
                ])
                self.math_set_config('avoid_regimes', ['GAMMA_SQUEEZE'])  # Only avoid extreme squeeze
                self.math_set_config('min_regime_confidence', 0.40)  # Lower threshold
                logger.info("PEGASUS: Math optimizers initialized - regime gate relaxed for outside-EM positioning")
            except Exception as e:
                logger.warning(f"PEGASUS: Math optimizer init failed: {e}")

        logger.info(f"PEGASUS initialized: mode={self.config.mode.value}, preset={self.config.preset.value}")

    def run_cycle(self) -> Dict[str, Any]:
        """Run trading cycle"""
        now = datetime.now(CENTRAL_TZ)
        today = now.strftime("%Y-%m-%d")

        result = {
            'timestamp': now.isoformat(),
            'action': 'none',
            'trade_opened': False,
            'positions_closed': 0,
            'realized_pnl': 0.0,
            'errors': [],
            'details': {}
        }

        # Track context for scan activity logging
        scan_context = {
            'market_data': None,
            'gex_data': None,
            'signal': None,
            'checks': [],
            'position': None
        }

        try:
            self.db.update_heartbeat("SCANNING", f"Cycle at {now.strftime('%I:%M %p')}")

            can_trade, reason = self._check_conditions(now, today)
            if not can_trade:
                result['action'] = 'skip'
                result['errors'].append(reason)
                result['details']['skip_reason'] = reason
                self.db.log("INFO", f"Skipping: {reason}")

                # Log skip to scan activity
                self._log_scan_activity(result, scan_context, skip_reason=reason)
                self._log_bot_decision(result, scan_context, skip_reason=reason)
                return result

            # Check Oracle strategy recommendation
            # Oracle may suggest ATHENA (directional) instead of PEGASUS (IC) in high VIX
            strategy_rec = self._check_strategy_recommendation()
            if strategy_rec:
                scan_context['strategy_recommendation'] = {
                    'recommended': strategy_rec.recommended_strategy.value if hasattr(strategy_rec, 'recommended_strategy') else 'IRON_CONDOR',
                    'vix_regime': strategy_rec.vix_regime.value if hasattr(strategy_rec, 'vix_regime') else 'NORMAL',
                    'ic_suitability': strategy_rec.ic_suitability if hasattr(strategy_rec, 'ic_suitability') else 1.0,
                    'reasoning': strategy_rec.reasoning if hasattr(strategy_rec, 'reasoning') else ''
                }

                # If Oracle recommends SKIP or DIRECTIONAL, log and potentially skip
                if hasattr(strategy_rec, 'recommended_strategy'):
                    if strategy_rec.recommended_strategy == StrategyType.SKIP:
                        result['action'] = 'skip'
                        result['details']['skip_reason'] = f"Oracle recommends SKIP: {strategy_rec.reasoning}"
                        self.db.log("INFO", f"Oracle SKIP recommendation: {strategy_rec.reasoning}")
                        self._log_scan_activity(result, scan_context, skip_reason=f"Oracle SKIP: {strategy_rec.reasoning}")
                        return result
                    elif strategy_rec.recommended_strategy == StrategyType.DIRECTIONAL:
                        # Log that ATHENA would be better, but continue with reduced confidence
                        self.db.log("INFO", f"Oracle suggests ATHENA (directional): {strategy_rec.reasoning}")
                        result['details']['oracle_suggests_athena'] = True
                        # Apply size reduction based on IC suitability (use config threshold)
                        if strategy_rec.ic_suitability < self.config.min_ic_suitability:
                            result['action'] = 'skip'
                            result['details']['skip_reason'] = f"IC suitability too low ({strategy_rec.ic_suitability:.0%}), consider ATHENA"
                            self._log_scan_activity(result, scan_context, skip_reason=f"Low IC suitability, consider ATHENA")
                            return result

            # Manage positions
            closed, pnl = self._manage_positions()
            result['positions_closed'] = closed
            result['realized_pnl'] = pnl

            # Try new entry (position limits already checked in _check_conditions)
            position, signal = self._try_entry_with_context()
            if position:
                result['trade_opened'] = True
                result['action'] = 'opened'
                result['details']['position'] = position.to_dict()
                scan_context['position'] = position
            if signal:
                scan_context['signal'] = signal
                scan_context['market_data'] = {
                    'underlying_price': signal.spot_price,
                    'symbol': 'SPX',
                    'vix': signal.vix,
                    'expected_move': signal.expected_move,
                }
                scan_context['gex_data'] = {
                    'regime': signal.gex_regime,
                    'call_wall': signal.call_wall,
                    'put_wall': signal.put_wall,
                }

            if closed > 0:
                result['action'] = 'closed' if result['action'] == 'none' else 'both'

            # Update daily performance
            self._update_daily_summary(today, result)

            self.db.update_heartbeat("IDLE", f"Complete: {result['action']}")

            # Log scan activity
            self._log_scan_activity(result, scan_context)
            self._log_bot_decision(result, scan_context)

        except Exception as e:
            logger.error(f"Cycle error: {e}")
            result['errors'].append(str(e))
            result['action'] = 'error'

            # Log error to scan activity
            self._log_scan_activity(result, scan_context, error_msg=str(e))
            self._log_bot_decision(result, scan_context, error_msg=str(e))

        return result

    def _check_conditions(self, now: datetime, today: str) -> tuple[bool, str]:
        if now.weekday() >= 5:
            return False, "Weekend"

        start = self.config.entry_start.split(':')
        end = self.config.entry_end.split(':')
        start_time = now.replace(hour=int(start[0]), minute=int(start[1]), second=0)
        end_time = now.replace(hour=int(end[0]), minute=int(end[1]), second=0)

        if now < start_time:
            return False, f"Before {self.config.entry_start}"
        if now > end_time:
            return False, f"After {self.config.entry_end}"

        # Check position limits instead of once-per-day restriction
        open_count = self.db.get_position_count()
        if open_count >= self.config.max_open_positions:
            return False, f"Max open positions ({self.config.max_open_positions}) reached"

        if CIRCUIT_BREAKER_AVAILABLE and is_trading_enabled:
            try:
                can, cb_reason = is_trading_enabled(self.db.get_position_count(), 0)
                if not can:
                    return False, f"Circuit breaker: {cb_reason}"
            except Exception:
                pass

        return True, "Ready"

    def _check_strategy_recommendation(self):
        """
        Check Oracle for strategy recommendation.

        Oracle determines if current conditions favor:
        - IRON_CONDOR: Price will stay pinned (good for PEGASUS)
        - DIRECTIONAL: Price will move (better for ATHENA)
        - SKIP: Too risky to trade

        Returns:
            StrategyRecommendation or None if Oracle unavailable
        """
        if not ORACLE_AVAILABLE or not get_oracle:
            return None

        try:
            oracle = get_oracle()

            # Get current market data using SignalGenerator's method (proper SPX data)
            market_data = self.signals.get_market_data()
            if not market_data:
                logger.warning("Could not fetch market data for strategy check")
                return None

            spot_price = market_data.get('spot_price', 5900)
            vix = market_data.get('vix', 20)
            gex_regime_str = market_data.get('gex_regime', 'NEUTRAL')
            call_wall = market_data.get('call_wall', 0)
            put_wall = market_data.get('put_wall', 0)
            flip_point = market_data.get('flip_point', 0)
            net_gex = market_data.get('net_gex', 0)

            # Convert GEX regime string to enum
            try:
                gex_regime = GEXRegime[gex_regime_str.upper()]
            except (KeyError, AttributeError):
                gex_regime = GEXRegime.NEUTRAL

            # Build market context
            context = OracleMarketContext(
                spot_price=spot_price,
                vix=vix,
                gex_regime=gex_regime,
                gex_call_wall=call_wall,
                gex_put_wall=put_wall,
                gex_flip_point=flip_point,
                gex_net=net_gex,
                day_of_week=datetime.now(CENTRAL_TZ).weekday()
            )

            # Get strategy recommendation
            recommendation = oracle.get_strategy_recommendation(context)

            logger.info(
                f"Oracle strategy rec: {recommendation.recommended_strategy.value}, "
                f"VIX regime: {recommendation.vix_regime.value}, "
                f"IC suitability: {recommendation.ic_suitability:.0%}"
            )

            return recommendation

        except Exception as e:
            logger.warning(f"Oracle strategy check failed: {e}")
            return None

    def _manage_positions(self) -> tuple[int, float]:
        positions = self.db.get_open_positions()
        closed = 0
        total_pnl = 0.0

        now = datetime.now(CENTRAL_TZ)
        today = now.strftime("%Y-%m-%d")

        for pos in positions:
            should_close, reason = self._check_exit(pos, now, today)
            if should_close:
                success, price, pnl = self.executor.close_position(pos, reason)

                # Handle partial close (put closed but call failed)
                if success == 'partial_put':
                    self.db.partial_close_position(
                        position_id=pos.position_id,
                        close_price=price,
                        realized_pnl=pnl,
                        close_reason=reason,
                        closed_leg='put'
                    )
                    logger.error(
                        f"PARTIAL CLOSE: {pos.position_id} put leg closed but call failed. "
                        f"Manual intervention required to close call spread."
                    )
                    # Don't count as fully closed, but track the partial P&L
                    total_pnl += pnl
                    continue

                if success:
                    db_success = self.db.close_position(pos.position_id, price, pnl, reason)
                    if not db_success:
                        logger.error(f"CRITICAL: Position {pos.position_id} closed but DB update failed!")
                    closed += 1
                    total_pnl += pnl

                    if CIRCUIT_BREAKER_AVAILABLE and record_trade_pnl:
                        try:
                            record_trade_pnl(pnl)
                        except Exception:
                            pass

                    # Record outcome to Oracle for ML feedback loop
                    self._record_oracle_outcome(pos, reason, pnl)

                    # Record outcome to Learning Memory for self-improvement
                    if pos.position_id in self._prediction_ids:
                        self._record_learning_memory_outcome(
                            self._prediction_ids.pop(pos.position_id),
                            pnl,
                            reason
                        )

                    # MATH OPTIMIZER: Record outcome for Thompson Sampling
                    if MATH_OPTIMIZER_AVAILABLE and hasattr(self, 'math_record_outcome'):
                        try:
                            self.math_record_outcome(win=(pnl > 0), pnl=pnl)
                        except Exception as e:
                            logger.debug(f"Thompson outcome recording skipped: {e}")

        return closed, total_pnl

    def _record_oracle_outcome(self, pos: IronCondorPosition, close_reason: str, pnl: float):
        """Record trade outcome to Oracle for ML feedback loop"""
        if not ORACLE_AVAILABLE:
            return

        try:
            oracle = OracleAdvisor()

            # Determine outcome type based on close reason and P&L
            if pnl > 0:
                if 'PROFIT' in close_reason or 'MAX_PROFIT' in close_reason:
                    outcome = OracleTradeOutcome.MAX_PROFIT
                else:
                    outcome = OracleTradeOutcome.PARTIAL_PROFIT
            else:
                if 'STOP_LOSS' in close_reason:
                    outcome = OracleTradeOutcome.LOSS
                elif 'CALL' in close_reason.upper() and 'BREACH' in close_reason.upper():
                    outcome = OracleTradeOutcome.CALL_BREACHED
                elif 'PUT' in close_reason.upper() and 'BREACH' in close_reason.upper():
                    outcome = OracleTradeOutcome.PUT_BREACHED
                else:
                    outcome = OracleTradeOutcome.LOSS

            # Get trade date from position
            trade_date = pos.expiration if hasattr(pos, 'expiration') else datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")

            # Record to Oracle using PEGASUS bot name
            success = oracle.update_outcome(
                trade_date=trade_date,
                bot_name=OracleBotName.PEGASUS,
                outcome=outcome,
                actual_pnl=pnl,
                put_strike=pos.put_short_strike if hasattr(pos, 'put_short_strike') else None,
                call_strike=pos.call_short_strike if hasattr(pos, 'call_short_strike') else None,
            )

            if success:
                logger.info(f"PEGASUS: Recorded outcome to Oracle - {outcome.value}, P&L=${pnl:.2f}")
            else:
                logger.warning(f"PEGASUS: Failed to record outcome to Oracle")

        except Exception as e:
            logger.warning(f"PEGASUS: Oracle outcome recording failed: {e}")

    def _record_learning_memory_prediction(self, pos: IronCondorPosition, signal) -> Optional[str]:
        """Record trade prediction to Learning Memory for self-improvement tracking."""
        if not LEARNING_MEMORY_AVAILABLE or not get_learning_memory:
            return None

        try:
            memory = get_learning_memory()

            context = {
                "gex_regime": signal.gex_regime if hasattr(signal, 'gex_regime') else "unknown",
                "vix": signal.vix if hasattr(signal, 'vix') else 20.0,
                "spot_price": signal.spot_price if hasattr(signal, 'spot_price') else 5900.0,
                "call_wall": signal.call_wall if hasattr(signal, 'call_wall') else 0,
                "put_wall": signal.put_wall if hasattr(signal, 'put_wall') else 0,
                "flip_point": getattr(signal, 'flip_point', 0),
                "expected_move": signal.expected_move if hasattr(signal, 'expected_move') else 0,
                "day_of_week": datetime.now(CENTRAL_TZ).weekday()
            }

            # Note: signal.confidence is already 0-1 from Oracle, not 0-100
            prediction_id = memory.record_prediction(
                prediction_type="spx_iron_condor_outcome",
                prediction=f"SPX IC profitable: {pos.put_short_strike}/{pos.call_short_strike}",
                confidence=signal.confidence if hasattr(signal, 'confidence') else 0.7,
                context=context
            )

            logger.info(f"PEGASUS: Learning Memory prediction recorded: {prediction_id}")
            return prediction_id

        except Exception as e:
            logger.warning(f"PEGASUS: Learning Memory prediction failed: {e}")
            return None

    def _record_learning_memory_outcome(self, prediction_id: str, pnl: float, close_reason: str):
        """Record trade outcome to Learning Memory for accuracy tracking."""
        if not LEARNING_MEMORY_AVAILABLE or not get_learning_memory or not prediction_id:
            return

        try:
            memory = get_learning_memory()
            was_correct = pnl > 0

            memory.record_outcome(
                prediction_id=prediction_id,
                outcome=f"{close_reason}: ${pnl:.2f}",
                was_correct=was_correct,
                notes=f"P&L: ${pnl:.2f}, Reason: {close_reason}"
            )

            logger.info(f"PEGASUS: Learning Memory outcome recorded: correct={was_correct}, P&L=${pnl:.2f}")

        except Exception as e:
            logger.warning(f"PEGASUS: Learning Memory outcome recording failed: {e}")

    def _check_exit(self, pos: IronCondorPosition, now: datetime, today: str) -> tuple[bool, str]:
        if pos.expiration <= today:
            return True, "EXPIRED"

        force = self.config.force_exit.split(':')
        force_time = now.replace(hour=int(force[0]), minute=int(force[1]), second=0)
        if now >= force_time and pos.expiration == today:
            return True, "FORCE_EXIT"

        current = self.executor.get_position_current_value(pos)
        if current is None:
            return False, ""

        # Profit target
        target = pos.total_credit * (1 - self.config.profit_target_pct / 100)
        if current <= target:
            return True, f"PROFIT_{self.config.profit_target_pct:.0f}%"

        # Stop loss
        if self.config.use_stop_loss:
            stop = pos.total_credit * self.config.stop_loss_multiple
            if current >= stop:
                return True, "STOP_LOSS"

        return False, ""

    def _try_entry(self) -> Optional[IronCondorPosition]:
        """Try to open a new Iron Condor"""
        position, _ = self._try_entry_with_context()
        return position

    def _try_entry_with_context(self) -> tuple[Optional[IronCondorPosition], Optional[Any]]:
        """Try to open a new Iron Condor, returning both position and signal for logging"""
        from typing import Any

        # MATH OPTIMIZER: Check regime before generating signal
        if MATH_OPTIMIZER_AVAILABLE and hasattr(self, '_math_enabled') and self._math_enabled:
            try:
                # Use get_market_data() - the correct method name in SignalGenerator
                market_data = self.signals.get_market_data()
                if market_data:
                    should_trade, regime_reason = self.math_should_trade_regime(market_data)
                    if not should_trade:
                        self.db.log("INFO", f"Math optimizer regime gate: {regime_reason}")
                        return None, None
            except Exception as e:
                logger.debug(f"Regime check skipped: {e}")

        signal = self.signals.generate_signal()
        if not signal:
            self.db.log("INFO", "No valid signal generated")
            return None, None

        if not signal.is_valid:
            self.db.log("INFO", f"Signal invalid: {signal.reasoning}")
            return None, signal  # Return signal for logging even if invalid

        # Log the signal
        self.db.log_signal(
            spot_price=signal.spot_price,
            vix=signal.vix,
            expected_move=signal.expected_move,
            call_wall=signal.call_wall,
            put_wall=signal.put_wall,
            gex_regime=signal.gex_regime,
            put_short=signal.put_short,
            put_long=signal.put_long,
            call_short=signal.call_short,
            call_long=signal.call_long,
            total_credit=signal.total_credit,
            confidence=signal.confidence,
            was_executed=True,
            reasoning=signal.reasoning,
        )

        position = self.executor.execute_iron_condor(signal)
        if not position:
            self.db.log("ERROR", "Execution failed", {'signal': signal.reasoning})
            return None, signal

        if not self.db.save_position(position):
            self.db.log("ERROR", "Failed to save position", {'pos_id': position.position_id})
            logger.error(f"Position {position.position_id} executed but not saved!")

        self.db.log("INFO", f"Opened: {position.position_id}", position.to_dict())

        # Record prediction to Learning Memory for self-improvement tracking
        prediction_id = self._record_learning_memory_prediction(position, signal)
        if prediction_id:
            self._prediction_ids[position.position_id] = prediction_id

        return position, signal

    def _log_scan_activity(
        self,
        result: Dict,
        context: Dict,
        skip_reason: str = "",
        error_msg: str = ""
    ):
        """Log scan activity for visibility"""
        if not SCAN_LOGGER_AVAILABLE or not log_pegasus_scan:
            return

        try:
            # Determine outcome
            if error_msg:
                outcome = ScanOutcome.ERROR
                decision = f"Error: {error_msg}"
            elif result.get('trade_opened'):
                outcome = ScanOutcome.TRADED
                decision = "SPX Iron Condor opened"
            elif skip_reason:
                if 'Weekend' in skip_reason or 'CLOSED' in skip_reason:
                    outcome = ScanOutcome.MARKET_CLOSED
                elif 'Before' in skip_reason:
                    outcome = ScanOutcome.BEFORE_WINDOW
                elif 'After' in skip_reason:
                    outcome = ScanOutcome.AFTER_WINDOW
                elif 'Max open positions' in skip_reason:
                    outcome = ScanOutcome.SKIP
                else:
                    outcome = ScanOutcome.NO_TRADE
                decision = skip_reason
            else:
                outcome = ScanOutcome.NO_TRADE
                decision = "No valid signal"

            # Build signal context
            signal = context.get('signal')
            signal_source = ""
            signal_confidence = 0
            oracle_advice = ""
            oracle_reasoning = ""

            if signal:
                signal_source = signal.source
                signal_confidence = signal.confidence
                oracle_advice = "ENTER" if signal.is_valid else "SKIP"
                oracle_reasoning = signal.reasoning

            # Build trade details if position opened
            position = context.get('position')
            strike_selection = None
            contracts = 0
            premium = 0
            max_risk = 0

            if position:
                strike_selection = {
                    'put_long': position.put_long_strike,
                    'put_short': position.put_short_strike,
                    'call_short': position.call_short_strike,
                    'call_long': position.call_long_strike,
                }
                contracts = position.contracts
                premium = position.total_credit * 100 * contracts
                max_risk = position.max_loss

            log_pegasus_scan(
                outcome=outcome,
                decision_summary=decision,
                market_data=context.get('market_data'),
                gex_data=context.get('gex_data'),
                signal_source=signal_source,
                signal_confidence=signal_confidence,
                oracle_advice=oracle_advice,
                oracle_reasoning=oracle_reasoning,
                trade_executed=result.get('trade_opened', False),
                error_message=error_msg,
                generate_ai_explanation=False,
            )
        except Exception as e:
            logger.warning(f"Failed to log scan activity: {e}")

    def _log_bot_decision(
        self,
        result: Dict,
        context: Dict,
        decision_type: str = "SCAN",
        skip_reason: str = "",
        error_msg: str = ""
    ):
        """Log decision to bot_decision_logs table for full audit trail"""
        if not BOT_LOGGER_AVAILABLE or not log_bot_decision:
            return

        try:
            signal = context.get('signal')
            position = context.get('position')
            market = context.get('market_data') or {}
            gex = context.get('gex_data') or {}

            # Determine decision type
            if error_msg:
                dec_type = DecisionType.SKIP
                action = "ERROR"
                reason = error_msg
            elif result.get('trade_opened'):
                dec_type = DecisionType.ENTRY
                action = "OPEN_IC"
                reason = "SPX Iron Condor opened"
            elif skip_reason:
                dec_type = DecisionType.SKIP
                action = "SKIP"
                reason = skip_reason
            else:
                dec_type = DecisionType.SKIP
                action = "NO_TRADE"
                reason = "No valid signal"

            # Build market context
            market_ctx = BotLogMarketContext(
                symbol="SPX",
                spot_price=market.get('underlying_price', 0),
                vix=market.get('vix', 0),
            )

            # Build GEX context
            gex_ctx = GEXContext(
                regime=gex.get('regime', 'NEUTRAL'),
                call_wall=gex.get('call_wall', 0),
                put_wall=gex.get('put_wall', 0),
                net_gex=gex.get('net_gex', 0),
            )

            # Build Oracle context
            oracle_ctx = OracleContext(
                advice=signal.oracle_advice if signal else "",
                confidence=signal.confidence if signal else 0,
                win_probability=signal.oracle_win_probability if signal else 0,
                reasoning=signal.reasoning if signal else "",
            )

            # Build trade details if position opened
            trade_details = None
            if position:
                trade_details = TradeDetails(
                    contracts=position.contracts,
                    premium_collected=position.total_credit * 100 * position.contracts,
                    max_loss=position.max_loss,
                    expiration=position.expiration,
                )

            decision = BotDecision(
                bot_name="PEGASUS",
                decision_type=dec_type,
                action=action,
                symbol="SPX",
                what=f"PEGASUS {action}",
                why=reason,
                market_context=market_ctx,
                gex_context=gex_ctx,
                oracle_context=oracle_ctx,
                trade_details=trade_details,
            )

            log_bot_decision(decision)
            logger.debug(f"Logged PEGASUS decision: {action}")

        except Exception as e:
            logger.warning(f"Failed to log bot decision: {e}")

    def _update_daily_summary(self, today: str, cycle_result: Dict) -> None:
        """Update daily performance record"""
        try:
            traded = 1 if cycle_result.get('trade_opened') else 0
            if self.db.has_traded_today(today):
                traded = 1

            summary = DailySummary(
                date=today,
                trades_executed=traded,
                positions_closed=cycle_result.get('positions_closed', 0),
                realized_pnl=cycle_result.get('realized_pnl', 0),
                open_positions=self.db.get_position_count(),
            )

            self.db.update_daily_performance(summary)
        except Exception as e:
            logger.warning(f"Failed to update daily summary: {e}")

    def get_status(self) -> Dict[str, Any]:
        now = datetime.now(CENTRAL_TZ)
        positions = self.db.get_open_positions()

        unrealized = 0.0
        for pos in positions:
            val = self.executor.get_position_current_value(pos)
            if val:
                unrealized += (pos.total_credit - val) * 100 * pos.contracts

        return {
            'bot_name': 'PEGASUS',
            'version': 'V1',
            'mode': self.config.mode.value,
            'ticker': 'SPX',
            'preset': self.config.preset.value,
            'open_positions': len(positions),
            'unrealized_pnl': unrealized,
            'timestamp': now.isoformat(),
        }

    def get_positions(self) -> List[IronCondorPosition]:
        return self.db.get_open_positions()

    def force_close_all(self, reason: str = "MANUAL") -> Dict[str, Any]:
        positions = self.db.get_open_positions()
        results = []

        for pos in positions:
            success, price, pnl = self.executor.close_position(pos, reason)
            if success:
                self.db.close_position(pos.position_id, price, pnl, reason)
                # Record outcome to Oracle for ML feedback
                self._record_oracle_outcome(pos, reason, pnl)
                # Record outcome to Learning Memory for self-improvement
                if pos.position_id in self._prediction_ids:
                    self._record_learning_memory_outcome(
                        self._prediction_ids.pop(pos.position_id),
                        pnl,
                        reason
                    )
            results.append({'position_id': pos.position_id, 'success': success, 'pnl': pnl})

        return {
            'closed': len([r for r in results if r['success']]),
            'total_pnl': sum(r['pnl'] for r in results if r['success']),
        }


def run_pegasus(config: Optional[PEGASUSConfig] = None) -> PEGASUSTrader:
    """Factory function"""
    return PEGASUSTrader(config)
