"""
FORTRESS V2 - Main Trading Orchestrator
=====================================

Clean, simple orchestration for Iron Condor trading.

FORTRESS trades SPY Iron Condors:
- One trade per day (0DTE)
- Bull Put + Bear Call spread
- GEX-protected or SD-based strikes
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from zoneinfo import ZoneInfo

from .models import (
    IronCondorPosition, PositionStatus, FortressConfig,
    TradingMode, DailySummary, CENTRAL_TZ
)
from .db import FortressDatabase
from .signals import SignalGenerator
from .executor import OrderExecutor

logger = logging.getLogger(__name__)

# Market calendar for holiday checking
try:
    from trading.market_calendar import MarketCalendar
    MARKET_CALENDAR = MarketCalendar()
    MARKET_CALENDAR_AVAILABLE = True
except ImportError:
    MARKET_CALENDAR = None
    MARKET_CALENDAR_AVAILABLE = False

# Scan activity logging
try:
    from trading.scan_activity_logger import log_fortress_scan, ScanOutcome, CheckResult
    SCAN_LOGGER_AVAILABLE = True
    print("✅ FORTRESS: Scan activity logger loaded")
except ImportError as e:
    SCAN_LOGGER_AVAILABLE = False
    log_fortress_scan = None
    ScanOutcome = None
    CheckResult = None
    print(f"❌ FORTRESS: Scan activity logger FAILED to load: {e}")
    print("   FORTRESS scans will NOT be logged during market hours!")

# ML Data Gatherer for comprehensive ML analysis logging
try:
    from trading.ml_data_gatherer import gather_ml_data
    ML_GATHERER_AVAILABLE = True
    print("✅ FORTRESS: ML Data Gatherer loaded")
except ImportError as e:
    ML_GATHERER_AVAILABLE = False
    gather_ml_data = None
    print(f"⚠️ FORTRESS: ML Data Gatherer not available: {e}")

# Prophet for outcome recording and strategy recommendations
try:
    from quant.prophet_advisor import (
        ProphetAdvisor, BotName as ProphetBotName, TradeOutcome as ProphetTradeOutcome,
        MarketContext as ProphetMarketContext, GEXRegime, StrategyType, get_prophet
    )
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False
    ProphetAdvisor = None
    ProphetBotName = None
    ProphetTradeOutcome = None
    ProphetMarketContext = None
    GEXRegime = None
    StrategyType = None
    get_prophet = None

# Learning Memory for self-improvement tracking
try:
    from ai.counselor_learning_memory import get_learning_memory
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
    MathOptimizerMixin = object  # Fallback to empty base class

# Proverbs Enhanced for feedback loop recording
try:
    from quant.proverbs_enhancements import get_proverbs_enhanced
    PROVERBS_ENHANCED_AVAILABLE = True
except ImportError:
    PROVERBS_ENHANCED_AVAILABLE = False
    get_proverbs_enhanced = None

# Auto-Validation System for Thompson Sampling capital allocation
try:
    from quant.auto_validation_system import get_auto_validation_system, record_bot_outcome
    AUTO_VALIDATION_AVAILABLE = True
except ImportError:
    AUTO_VALIDATION_AVAILABLE = False
    get_auto_validation_system = None
    record_bot_outcome = None


class FortressTrader(MathOptimizerMixin):
    """
    FORTRESS V2 - Clean, modular Iron Condor trader for SPY.

    Usage:
        trader = FortressTrader()
        result = trader.run_cycle()
    """

    def __init__(self, config: Optional[FortressConfig] = None):
        """Initialize FORTRESS trader"""
        # Database layer FIRST
        self.db = FortressDatabase(bot_name="FORTRESS")

        # Load config from DB or use provided
        self.config = config or self.db.load_config()

        # Validate configuration at startup
        is_valid, error = self.config.validate()
        if not is_valid:
            logger.error(f"FORTRESS config validation failed: {error}")
            raise ValueError(f"Invalid FORTRESS configuration: {error}")

        # Initialize components
        self.signals = SignalGenerator(self.config)
        self.executor = OrderExecutor(self.config, db=self.db)

        # Learning Memory prediction tracking (position_id -> prediction_id)
        self._prediction_ids: Dict[str, str] = {}

        # Proverbs consecutive loss cooldown (5-minute pause, then resume)
        self._loss_streak_pause_until: Optional[datetime] = None

        # Math Optimizers DISABLED - Prophet is the sole decision maker
        # The regime gate was blocking trades even when Prophet said TRADE_FULL
        if MATH_OPTIMIZER_AVAILABLE:
            self._init_math_optimizers("FORTRESS", enabled=False)
            logger.info("FORTRESS: Math optimizers DISABLED - Prophet controls all trading decisions")

        logger.info(
            f"FORTRESS V2 initialized: mode={self.config.mode.value}, "
            f"ticker={self.config.ticker}, preset={self.config.preset.value}"
        )

    def run_cycle(self, close_only: bool = False) -> Dict[str, Any]:
        """
        Run a single trading cycle.

        FORTRESS can trade up to max_trades_per_day (default: 3).
        Allows re-entry after a position closes profitably.
        This method is called by the scheduler every 5 minutes.

        Args:
            close_only: If True, only manage existing positions (close expiring ones),
                       don't check conditions or try new entries. Used after market close.
        """
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
            'prophet_data': None,
            'position': None
        }

        try:
            self.db.update_heartbeat("SCANNING", f"Cycle at {now.strftime('%I:%M %p')}" + (" [CLOSE_ONLY]" if close_only else ""))

            # In close_only mode, skip market data fetch and conditions check
            # Just manage existing positions
            if close_only:
                logger.info("FORTRESS running in CLOSE_ONLY mode - managing positions only")
                closed_count, close_pnl = self._manage_positions()
                result['positions_closed'] = closed_count
                result['realized_pnl'] = close_pnl
                result['action'] = 'close_only'
                result['details']['mode'] = 'close_only'

                if closed_count > 0:
                    self.db.log("INFO", f"CLOSE_ONLY: Closed {closed_count} position(s), P&L: ${close_pnl:.2f}")
                else:
                    self.db.log("INFO", "CLOSE_ONLY: No positions to close")

                self._log_scan_activity(result, scan_context, "Close-only mode after market")
                return result

            # Check Proverbs kill switch — blocks NEW entries but allows close_only
            if PROVERBS_ENHANCED_AVAILABLE and get_proverbs_enhanced:
                try:
                    enhanced = get_proverbs_enhanced()
                    if enhanced and enhanced.proverbs.is_bot_killed('FORTRESS'):
                        logger.warning("[FORTRESS] Kill switch ACTIVE — skipping cycle (no new entries)")
                        result['action'] = 'kill_switch_active'
                        self._log_scan_activity(result, scan_context, "Kill switch active")
                        return result
                except Exception as e:
                    logger.debug(f"[FORTRESS] Kill switch check failed (fail-open): {e}")

            # CRITICAL: Fetch market data FIRST for ALL scans
            # This ensures we log comprehensive data even for skipped scans
            try:
                # Use get_market_data() which includes expected_move (required for Prophet)
                market_data = self.signals.get_market_data() if hasattr(self, 'signals') else None
                gex_data = self.signals.get_gex_data() if hasattr(self, 'signals') else None

                if not gex_data and hasattr(self, 'gex_calculator'):
                    gex_data = self.gex_calculator.calculate_gex(self.config.ticker)
                if gex_data:
                    scan_context['market_data'] = {
                        'underlying_price': gex_data.get('spot_price', gex_data.get('underlying_price', 0)),
                        'symbol': self.config.ticker,
                        'vix': gex_data.get('vix', 0),
                        'expected_move': market_data.get('expected_move', 0) if market_data else 0,
                    }
                    scan_context['gex_data'] = {
                        'regime': gex_data.get('gex_regime', gex_data.get('regime', 'UNKNOWN')),
                        'net_gex': gex_data.get('net_gex', 0),
                        'call_wall': gex_data.get('call_wall', gex_data.get('major_call_wall', 0)),
                        'put_wall': gex_data.get('put_wall', gex_data.get('major_put_wall', 0)),
                        'flip_point': gex_data.get('flip_point', gex_data.get('gamma_flip', 0)),
                    }
                    # Fetch Prophet advice using FULL market_data (includes expected_move)
                    # This ensures Prophet gets the same data as generate_signal() uses
                    try:
                        if hasattr(self, 'signals') and hasattr(self.signals, 'get_prophet_advice'):
                            oracle_advice = self.signals.get_prophet_advice(market_data if market_data else gex_data)
                            if oracle_advice:
                                scan_context['prophet_data'] = oracle_advice
                    except Exception as e:
                        logger.debug(f"Prophet fetch skipped: {e}")
            except Exception as e:
                logger.warning(f"Market data fetch failed: {e}")

            # Step 1: ALWAYS check and manage existing positions FIRST
            # This ensures we monitor positions even if we can't open new ones
            closed_count, close_pnl = self._manage_positions()
            result['positions_closed'] = closed_count
            result['realized_pnl'] = close_pnl

            if closed_count > 0:
                result['action'] = 'closed'
                self.db.log("INFO", f"Closed {closed_count} position(s), P&L: ${close_pnl:.2f}")

            # Step 2: Check basic trading conditions (time window, weekend, holidays)
            can_trade, reason = self._check_basic_conditions(now)
            if not can_trade:
                if result['action'] == 'none':
                    result['action'] = 'skip'
                result['details']['skip_reason'] = reason
                self.db.log("INFO", f"Entry skipped: {reason}")
                self._log_scan_activity(result, scan_context, reason)
                self._update_daily_summary(today, result)
                self.db.update_heartbeat("IDLE", f"Cycle complete: {result['action']}")
                return result

            # No max position limit - always look for new entries

            # Step 3.5: Check Proverbs consecutive loss cooldown (5-min pause after 3 losses)
            # Check if we're in a cooldown pause
            if self._loss_streak_pause_until:
                if now < self._loss_streak_pause_until:
                    remaining = (self._loss_streak_pause_until - now).total_seconds()
                    reason = f'Proverbs: Loss streak cooldown ({remaining:.0f}s remaining)'
                    if result['action'] == 'none':
                        result['action'] = 'skip'
                    result['details']['skip_reason'] = reason
                    self.db.log("INFO", f"FORTRESS: {reason}")
                    self._log_scan_activity(result, scan_context, reason)
                    self._update_daily_summary(today, result)
                    self.db.update_heartbeat("COOLDOWN", reason)
                    return result
                else:
                    # Cooldown expired — reset and resume trading
                    self.db.log("INFO", "FORTRESS: Loss streak cooldown expired, resuming trading")
                    self._loss_streak_pause_until = None
                    # Reset the Proverbs tracker so it needs 3 more losses to trigger again
                    if PROVERBS_ENHANCED_AVAILABLE and get_proverbs_enhanced:
                        try:
                            proverbs = get_proverbs_enhanced()
                            if proverbs:
                                proverbs.consecutive_loss_monitor.reset('FORTRESS')
                        except Exception:
                            pass

            # Check if Proverbs detected 3 consecutive losses (triggers new 5-min cooldown)
            if PROVERBS_ENHANCED_AVAILABLE and get_proverbs_enhanced:
                try:
                    proverbs = get_proverbs_enhanced()
                    if proverbs:
                        consec_status = proverbs.consecutive_loss_monitor.get_status('FORTRESS')
                        if consec_status and consec_status.get('triggered_kill') and self._loss_streak_pause_until is None:
                            self._loss_streak_pause_until = now + timedelta(minutes=5)
                            reason = f'Proverbs: {consec_status.get("consecutive_losses", 3)} consecutive losses — pausing 5 min (until {self._loss_streak_pause_until.strftime("%H:%M:%S")})'
                            if result['action'] == 'none':
                                result['action'] = 'skip'
                            result['details']['skip_reason'] = reason
                            self.db.log("WARNING", f"FORTRESS: {reason}")
                            self._log_scan_activity(result, scan_context, reason)
                            self._update_daily_summary(today, result)
                            self.db.update_heartbeat("COOLDOWN", reason)
                            return result
                except Exception as e:
                    logger.warning(f"Proverbs guardrail check failed (non-blocking): {e}")

            # Step 4: Check Prophet strategy recommendation
            strategy_rec = self._check_strategy_recommendation()
            if strategy_rec:
                scan_context['strategy_recommendation'] = {
                    'recommended': strategy_rec.recommended_strategy.value if hasattr(strategy_rec, 'recommended_strategy') else 'IRON_CONDOR',
                    'vix_regime': strategy_rec.vix_regime.value if hasattr(strategy_rec, 'vix_regime') else 'NORMAL',
                    'ic_suitability': strategy_rec.ic_suitability if hasattr(strategy_rec, 'ic_suitability') else 1.0,
                    'reasoning': strategy_rec.reasoning if hasattr(strategy_rec, 'reasoning') else ''
                }

                # NOTE: Strategy recommendation is INFORMATIONAL ONLY
                # Prophet's final trade advice in signals.py is the ONLY decision maker
                if hasattr(strategy_rec, 'recommended_strategy'):
                    if strategy_rec.recommended_strategy == StrategyType.SKIP:
                        # Log but DON'T block - let signals.py Prophet check decide
                        self.db.log("INFO", f"Prophet strategy suggests SKIP: {strategy_rec.reasoning} (proceeding to trade check)")
                        result['details']['strategy_suggestion'] = f"SKIP: {strategy_rec.reasoning}"
                    elif strategy_rec.recommended_strategy == StrategyType.DIRECTIONAL:
                        self.db.log("INFO", f"Prophet suggests SOLOMON: {strategy_rec.reasoning} (FORTRESS will still check)")
                        result['details']['oracle_suggests_solomon'] = True
                        result['details']['ic_suitability'] = strategy_rec.ic_suitability

            # Step 6: Try to open new position
            # Pass early-fetched prophet_data to avoid double Prophet call (bug fix)
            position, signal = self._try_new_entry_with_context(prophet_data=scan_context.get('prophet_data'))
            if position:
                result['trade_opened'] = True
                result['action'] = 'opened' if result['action'] == 'none' else 'both'
                result['details']['position'] = position.to_dict()
                scan_context['position'] = position
                self.db.log("INFO", f"Opened new FORTRESS position: {position.position_id}")
            if signal:
                scan_context['signal'] = signal
                scan_context['market_data'] = {
                    'underlying_price': signal.spot_price,
                    'symbol': 'SPY',
                    'vix': signal.vix,
                    'expected_move': signal.expected_move,
                }
                scan_context['gex_data'] = {
                    'regime': signal.gex_regime,
                    'call_wall': signal.call_wall,
                    'put_wall': signal.put_wall,
                }

            # Step 7: Update daily summary
            self._update_daily_summary(today, result)

            self.db.update_heartbeat("IDLE", f"Cycle complete: {result['action']}")

            # Log scan activity
            self._log_scan_activity(result, scan_context)

        except Exception as e:
            logger.error(f"Cycle error: {e}")
            import traceback
            traceback.print_exc()
            result['errors'].append(str(e))
            result['action'] = 'error'

            # CRITICAL: Log scan activity FIRST, before any other DB operations
            # This ensures we always have visibility into what happened, even if
            # subsequent database operations fail (which could cause silent scan stoppage)
            try:
                self._log_scan_activity(result, scan_context, error_msg=str(e))
            except Exception as log_err:
                logger.error(f"CRITICAL: Failed to log scan activity: {log_err}")

            # Then try to log to bot's own log (non-critical)
            try:
                self.db.log("ERROR", f"Cycle error: {e}")
            except Exception as db_err:
                logger.error(f"Failed to log to bot DB: {db_err}")

        return result

    def _log_scan_activity(
        self,
        result: Dict,
        context: Dict,
        skip_reason: str = "",
        error_msg: str = ""
    ):
        """Log scan activity for visibility"""
        print(f"[FORTRESS DEBUG] _log_scan_activity called at {datetime.now(CENTRAL_TZ).strftime('%I:%M:%S %p CT')}")
        if not SCAN_LOGGER_AVAILABLE or not log_fortress_scan:
            print(f"[FORTRESS DEBUG] Scan logging SKIPPED: SCAN_LOGGER_AVAILABLE={SCAN_LOGGER_AVAILABLE}, log_fortress_scan={log_fortress_scan is not None}")
            logger.warning(f"[FORTRESS] Scan logging SKIPPED: SCAN_LOGGER_AVAILABLE={SCAN_LOGGER_AVAILABLE}, log_fortress_scan={log_fortress_scan is not None}")
            return
        print(f"[FORTRESS DEBUG] Proceeding with scan logging...")

        try:
            # Determine outcome
            if error_msg:
                outcome = ScanOutcome.ERROR
                decision = f"Error: {error_msg}"
            elif result.get('trade_opened'):
                outcome = ScanOutcome.TRADED
                decision = "Iron Condor opened"
            elif skip_reason:
                if 'Weekend' in skip_reason or 'CLOSED' in skip_reason:
                    outcome = ScanOutcome.MARKET_CLOSED
                elif 'Before' in skip_reason:
                    outcome = ScanOutcome.BEFORE_WINDOW
                elif 'After' in skip_reason:
                    outcome = ScanOutcome.AFTER_WINDOW
                elif 'Already traded' in skip_reason:
                    outcome = ScanOutcome.SKIP
                else:
                    outcome = ScanOutcome.NO_TRADE
                decision = skip_reason
            else:
                outcome = ScanOutcome.NO_TRADE
                decision = "No valid signal"

            # Build signal context with FULL Prophet data
            signal = context.get('signal')
            prophet_data = context.get('prophet_data', {})
            signal_source = ""
            signal_confidence = 0
            signal_win_probability = 0
            oracle_advice = ""
            oracle_reasoning = ""
            oracle_win_probability = 0
            oracle_confidence = 0
            oracle_top_factors = None
            oracle_probabilities = None
            oracle_suggested_strikes = None
            oracle_thresholds = None
            min_win_prob_threshold = self.config.min_win_probability

            # ALWAYS set thresholds - this should never be 0
            oracle_thresholds = {
                'min_win_probability': min_win_prob_threshold,
                'vix_skip': getattr(self.config, 'vix_skip', 32.0),
                'vix_monday_friday_skip': getattr(self.config, 'vix_monday_friday_skip', 30.0),
                'vix_streak_skip': getattr(self.config, 'vix_streak_skip', 28.0),
            }

            # Extract Prophet data from context FIRST (fetched early for all scans)
            # This ensures we always have Prophet data even if signal doesn't have it
            # Extract NEUTRAL regime analysis fields
            neutral_derived_direction = ""
            neutral_confidence = 0
            neutral_reasoning = ""
            ic_suitability = 0
            bullish_suitability = 0
            bearish_suitability = 0
            trend_direction = ""
            trend_strength = 0
            position_in_range_pct = 50.0

            if prophet_data:
                oracle_advice = prophet_data.get('advice', prophet_data.get('recommendation', ''))
                oracle_reasoning = prophet_data.get('reasoning', prophet_data.get('full_reasoning', ''))
                oracle_win_probability = prophet_data.get('win_probability', 0)
                oracle_confidence = prophet_data.get('confidence', 0)
                oracle_top_factors = prophet_data.get('top_factors', prophet_data.get('factors', []))
                # Extract NEUTRAL regime analysis fields
                neutral_derived_direction = prophet_data.get('neutral_derived_direction', '')
                neutral_confidence = prophet_data.get('neutral_confidence', 0)
                neutral_reasoning = prophet_data.get('neutral_reasoning', '')
                ic_suitability = prophet_data.get('ic_suitability', 0)
                bullish_suitability = prophet_data.get('bullish_suitability', 0)
                bearish_suitability = prophet_data.get('bearish_suitability', 0)
                trend_direction = prophet_data.get('trend_direction', '')
                trend_strength = prophet_data.get('trend_strength', 0)
                position_in_range_pct = prophet_data.get('position_in_range_pct', 50.0)
                # wall_filter removed - not applicable to FORTRESS Iron Condors (only for directional bots)

            # If we have a signal, use signal data (but don't override Prophet data with zeros)
            if signal:
                signal_source = signal.source
                signal_confidence = signal.confidence
                signal_win_probability = getattr(signal, 'oracle_win_probability', 0)

                # Only override Prophet data if signal has it (don't replace with zeros)
                if hasattr(signal, 'oracle_advice') and signal.oracle_advice:
                    oracle_advice = signal.oracle_advice
                elif not oracle_advice:  # Fallback if we don't have advice yet
                    oracle_advice = "ENTER" if signal.is_valid else "SKIP"

                if signal.reasoning:
                    oracle_reasoning = signal.reasoning

                # Only override win probability if signal has a non-zero value
                signal_oracle_wp = getattr(signal, 'oracle_win_probability', 0)
                if signal_oracle_wp > 0:
                    oracle_win_probability = signal_oracle_wp

                signal_oracle_conf = getattr(signal, 'oracle_confidence', 0)
                if signal_oracle_conf > 0:
                    oracle_confidence = signal_oracle_conf
                elif oracle_confidence == 0:  # Fallback to signal confidence
                    oracle_confidence = signal.confidence

                # Get top factors (may be JSON string or list) - only if signal has them
                top_factors_raw = getattr(signal, 'oracle_top_factors', None)
                if top_factors_raw:
                    if isinstance(top_factors_raw, str):
                        try:
                            import json
                            oracle_top_factors = json.loads(top_factors_raw)
                        except Exception:
                            pass  # Keep existing oracle_top_factors
                    elif isinstance(top_factors_raw, list):
                        oracle_top_factors = top_factors_raw

                # Get probabilities
                signal_probs = getattr(signal, 'oracle_probabilities', None)
                if signal_probs:
                    oracle_probabilities = signal_probs

                # Get suggested strikes
                if hasattr(signal, 'oracle_suggested_sd'):
                    oracle_suggested_strikes = {
                        'sd_multiplier': getattr(signal, 'oracle_suggested_sd', 1.0),
                        'use_gex_walls': getattr(signal, 'oracle_use_gex_walls', False)
                    }

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

            # Gather comprehensive ML data for logging
            ml_kwargs = {}
            if ML_GATHERER_AVAILABLE and gather_ml_data:
                try:
                    market_data = context.get('market_data', {})
                    gex_data = context.get('gex_data', {})
                    ml_kwargs = gather_ml_data(
                        symbol=self.config.ticker,  # FortressConfig uses 'ticker' not 'symbol'
                        spot_price=market_data.get('spot_price', 0) if market_data else 0,
                        vix=market_data.get('vix', 0) if market_data else 0,
                        gex_data=gex_data,
                        market_data=market_data,
                        bot_name="FORTRESS",
                        win_rate=0.70,  # FORTRESS historical win rate
                        avg_win=150,
                        avg_loss=350,
                    )
                except Exception as ml_err:
                    logger.debug(f"ML data gathering failed (non-critical): {ml_err}")

            scan_id = log_fortress_scan(
                outcome=outcome,
                decision_summary=decision,
                action_taken=result.get('action', 'none'),
                market_data=context.get('market_data'),
                gex_data=context.get('gex_data'),
                signal_source=signal_source,
                signal_confidence=signal_confidence,
                signal_win_probability=signal_win_probability,
                oracle_advice=oracle_advice,
                oracle_reasoning=oracle_reasoning,
                oracle_win_probability=oracle_win_probability,
                oracle_confidence=oracle_confidence,
                oracle_top_factors=oracle_top_factors,
                oracle_probabilities=oracle_probabilities,
                oracle_suggested_strikes=oracle_suggested_strikes,
                oracle_thresholds=oracle_thresholds,
                min_win_probability_threshold=min_win_prob_threshold,
                trade_executed=result.get('trade_opened', False),
                position_id=position.position_id if position else "",
                strike_selection=strike_selection,
                contracts=contracts,
                premium_collected=premium,
                max_risk=max_risk,
                error_message=error_msg,
                generate_ai_explanation=False,  # Keep it simple for now
                # NEUTRAL Regime Analysis fields
                neutral_derived_direction=neutral_derived_direction,
                neutral_confidence=neutral_confidence,
                neutral_reasoning=neutral_reasoning,
                ic_suitability=ic_suitability,
                bullish_suitability=bullish_suitability,
                bearish_suitability=bearish_suitability,
                trend_direction=trend_direction,
                trend_strength=trend_strength,
                position_in_range_pct=position_in_range_pct,
                # wall_filter removed - not applicable to FORTRESS
                **ml_kwargs,  # Include all ML analysis data
            )
            if scan_id:
                print(f"[FORTRESS DEBUG] ✅ Scan logged successfully: {scan_id}")
                logger.info(f"[FORTRESS] Scan logged: {scan_id}")
            else:
                print(f"[FORTRESS DEBUG] ❌ Scan logging returned None - check database!")
                logger.warning("[FORTRESS] Scan logging returned None - possible DB issue")

            # Migration 023 (Option C): NO LONGER store Prophet predictions for non-traded scans.
            # Predictions are ONLY stored when a position is actually opened.
            # This ensures 1:1 prediction-to-position mapping for accurate feedback loop.
            # Scan activity is still logged to fortress_scan_activity for debugging visibility.
            # (Removed call to _store_oracle_prediction_for_scan)

        except Exception as e:
            print(f"[FORTRESS DEBUG] ❌ EXCEPTION in _log_scan_activity: {e}")
            import traceback
            print(traceback.format_exc())
            logger.error(f"[FORTRESS] CRITICAL: Failed to log scan activity: {e}")
            logger.error(traceback.format_exc())
            # FALLBACK: Try simple logging without ML kwargs
            try:
                fallback_scan_id = log_fortress_scan(
                    outcome=outcome,
                    decision_summary=f"{decision} [FALLBACK - ML data excluded]",
                    action_taken=result.get('action', 'none'),
                    market_data=context.get('market_data'),
                    gex_data=context.get('gex_data'),
                    trade_executed=result.get('trade_opened', False),
                    error_message=error_msg or f"Original logging failed: {str(e)[:100]}",
                    generate_ai_explanation=False,
                )
                if fallback_scan_id:
                    logger.info(f"[FORTRESS] Fallback scan logged: {fallback_scan_id}")
                else:
                    logger.error("[FORTRESS] FALLBACK scan logging also failed!")
            except Exception as fallback_err:
                logger.error(f"[FORTRESS] FALLBACK logging failed: {fallback_err}")

    def _check_basic_conditions(self, now: datetime) -> tuple[bool, str]:
        """Check basic trading conditions (time window, weekend, holidays)"""
        # Weekend check
        if now.weekday() >= 5:
            return False, "Weekend"

        # Market holiday check
        if MARKET_CALENDAR_AVAILABLE and MARKET_CALENDAR:
            today_str = now.strftime("%Y-%m-%d")
            if not MARKET_CALENDAR.is_trading_day(today_str):
                return False, "Market holiday"

        # Trading window
        start_parts = self.config.entry_start.split(':')
        end_parts = self.config.entry_end.split(':')
        start_time = now.replace(hour=int(start_parts[0]), minute=int(start_parts[1]), second=0)
        end_time = now.replace(hour=int(end_parts[0]), minute=int(end_parts[1]), second=0)

        if now < start_time:
            return False, f"Before trading window ({self.config.entry_start})"
        if now > end_time:
            return False, f"After trading window ({self.config.entry_end})"

        return True, "Ready"

    def _check_strategy_recommendation(self):
        """
        Check Prophet for strategy recommendation.

        Prophet determines if current conditions favor:
        - IRON_CONDOR: Price will stay pinned (good for FORTRESS)
        - DIRECTIONAL: Price will move (better for SOLOMON)
        - SKIP: Too risky to trade

        Returns:
            StrategyRecommendation or None if Prophet unavailable
        """
        if not PROPHET_AVAILABLE or not get_prophet:
            return None

        try:
            prophet = get_prophet()

            # Get current market data
            try:
                from core_classes_and_engines import TradingVolatilityAPI
                api = TradingVolatilityAPI()
                gex_data = api.get_gex_levels('SPY')

                spot_price = gex_data.get('spot_price', 590)
                vix = gex_data.get('vix', 20)
                gex_regime_str = gex_data.get('gex_regime', 'NEUTRAL')
                call_wall = gex_data.get('call_wall', 0)
                put_wall = gex_data.get('put_wall', 0)
                flip_point = gex_data.get('flip_point', 0)
                net_gex = gex_data.get('net_gex', 0)
            except Exception as e:
                logger.warning(f"Could not fetch market data for strategy check: {e}")
                # Use defaults - let FORTRESS proceed
                return None

            # Convert GEX regime string to enum
            try:
                gex_regime = GEXRegime[gex_regime_str.upper()]
            except (KeyError, AttributeError):
                gex_regime = GEXRegime.NEUTRAL

            # Build market context
            context = ProphetMarketContext(
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
            recommendation = prophet.get_strategy_recommendation(context)

            logger.info(
                f"Prophet strategy rec: {recommendation.recommended_strategy.value}, "
                f"VIX regime: {recommendation.vix_regime.value}, "
                f"IC suitability: {recommendation.ic_suitability:.0%}"
            )

            return recommendation

        except Exception as e:
            logger.warning(f"Prophet strategy check failed: {e}")
            return None

    def _manage_positions(self) -> tuple[int, float]:
        """Check open positions for exit conditions"""
        positions = self.db.get_open_positions()
        closed_count = 0
        total_pnl = 0.0

        now = datetime.now(CENTRAL_TZ)
        today = now.strftime("%Y-%m-%d")

        for pos in positions:
            should_close, reason = self._check_exit_conditions(pos, now, today)

            if should_close:
                success, close_price, pnl = self.executor.close_position(pos, reason)

                # Handle partial close (put closed but call failed) with RETRY LOGIC
                if success == 'partial_put':
                    logger.warning(f"[FORTRESS] Partial close detected for {pos.position_id} - attempting retry for call leg")

                    # Retry closing the call leg up to 3 times with exponential backoff
                    call_closed = False
                    for attempt in range(3):
                        import time
                        time.sleep(2 ** attempt)  # 1s, 2s, 4s backoff

                        logger.info(f"[FORTRESS] Retry {attempt + 1}/3 for call leg of {pos.position_id}")
                        call_result = self.executor.close_call_spread_only(pos, reason)

                        if call_result and call_result[0]:  # (success, close_price, pnl)
                            call_closed = True
                            call_pnl = call_result[2]
                            pnl += call_pnl  # Add call leg P&L to total
                            logger.info(f"[FORTRESS] Call leg closed on retry {attempt + 1}, total P&L: ${pnl:.2f}")
                            break

                    if call_closed:
                        # Successfully recovered - mark as fully closed
                        db_success = self.db.close_position(
                            position_id=pos.position_id,
                            close_price=close_price,
                            realized_pnl=pnl,
                            close_reason=f"{reason}_RECOVERED_RETRY"
                        )
                        if db_success:
                            closed_count += 1
                            total_pnl += pnl
                            self.db.log("INFO", f"Position {pos.position_id} recovered via retry: P&L=${pnl:.2f}")
                        continue
                    else:
                        # All retries failed - mark as partial close
                        self.db.partial_close_position(
                            position_id=pos.position_id,
                            close_price=close_price,
                            realized_pnl=pnl,
                            close_reason=reason,
                            closed_leg='put'
                        )
                        logger.error(
                            f"PARTIAL CLOSE FAILED RECOVERY: {pos.position_id} put leg closed but call failed after 3 retries. "
                            f"Manual intervention required to close call spread."
                        )
                        # Send alert for manual intervention
                        self.db.log("CRITICAL", f"Manual intervention needed: {pos.position_id} call leg open", {
                            'position_id': pos.position_id,
                            'call_short': pos.call_short_strike,
                            'call_long': pos.call_long_strike,
                            'contracts': pos.contracts
                        })
                        # Don't count as fully closed, but track the partial P&L
                        total_pnl += pnl
                        continue

                if success:
                    db_success = self.db.close_position(
                        position_id=pos.position_id,
                        close_price=close_price,
                        realized_pnl=pnl,
                        close_reason=reason
                    )
                    if not db_success:
                        logger.error(f"CRITICAL: Position {pos.position_id} closed in Tradier but DB update failed!")
                        # Still count it as closed since Tradier position is closed
                    closed_count += 1
                    total_pnl += pnl

                    # Record outcome to Prophet for ML feedback loop
                    self._record_oracle_outcome(pos, reason, pnl)

                    # Record outcome to Proverbs Enhanced for feedback loops
                    trade_date = pos.expiration if hasattr(pos, 'expiration') else datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")
                    # Migration 023: Pass outcome_type and oracle_prediction_id for feedback loop
                    outcome_type = self._determine_outcome_type(reason, pnl)
                    prediction_id = self.db.get_oracle_prediction_id(pos.position_id)
                    self._record_proverbs_outcome(pnl, trade_date, outcome_type, prediction_id)

                    # Record outcome to Thompson Sampling for capital allocation
                    self._record_thompson_outcome(pnl)

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

                    self.db.log("INFO", f"Closed {pos.position_id}: {reason}, P&L=${pnl:.2f}")

                    # Save equity snapshot after closing position (for real-time equity curve)
                    self.db.save_equity_snapshot(
                        balance=self.db.get_current_balance(),
                        realized_pnl=pnl,
                        open_positions=self.db.get_position_count(),
                        note=f"Closed {pos.position_id}: {reason}"
                    )

        return closed_count, total_pnl

    def _record_oracle_outcome(self, pos: IronCondorPosition, close_reason: str, pnl: float):
        """
        Record trade outcome to Prophet for ML feedback loop.

        Migration 023: Enhanced to pass prediction_id and outcome_type for
        accurate feedback loop tracking.
        """
        if not PROPHET_AVAILABLE:
            return

        try:
            prophet = ProphetAdvisor()

            # Determine outcome type based on close reason and P&L
            if pnl > 0:
                if 'PROFIT_TARGET' in close_reason or 'MAX_PROFIT' in close_reason:
                    outcome = ProphetTradeOutcome.MAX_PROFIT
                    outcome_type = 'MAX_PROFIT'
                else:
                    outcome = ProphetTradeOutcome.PARTIAL_PROFIT
                    outcome_type = 'PARTIAL_PROFIT'
            else:
                if 'STOP_LOSS' in close_reason:
                    outcome = ProphetTradeOutcome.LOSS
                    outcome_type = 'STOP_LOSS'
                elif 'CALL' in close_reason.upper() and 'BREACH' in close_reason.upper():
                    outcome = ProphetTradeOutcome.CALL_BREACHED
                    outcome_type = 'CALL_BREACHED'
                elif 'PUT' in close_reason.upper() and 'BREACH' in close_reason.upper():
                    outcome = ProphetTradeOutcome.PUT_BREACHED
                    outcome_type = 'PUT_BREACHED'
                else:
                    outcome = ProphetTradeOutcome.LOSS
                    outcome_type = 'LOSS'

            # Get trade date from position
            trade_date = pos.expiration if hasattr(pos, 'expiration') else datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")

            # Migration 023: Get prediction_id from database for accurate linking
            prediction_id = self.db.get_oracle_prediction_id(pos.position_id)

            # Record to Prophet with enhanced feedback loop data
            success = prophet.update_outcome(
                trade_date=trade_date,
                bot_name=ProphetBotName.FORTRESS,
                outcome=outcome,
                actual_pnl=pnl,
                put_strike=pos.put_short_strike if hasattr(pos, 'put_short_strike') else None,
                call_strike=pos.call_short_strike if hasattr(pos, 'call_short_strike') else None,
                prediction_id=prediction_id,  # Migration 023: Direct linking
                outcome_type=outcome_type,  # Migration 023: Specific outcome classification
            )

            if success:
                logger.info(f"FORTRESS: Recorded outcome to Prophet - {outcome.value}, P&L=${pnl:.2f}, prediction_id={prediction_id}")
            else:
                logger.warning(f"FORTRESS: Failed to record outcome to Prophet")

        except Exception as e:
            logger.warning(f"FORTRESS: Prophet outcome recording failed: {e}")

    def _record_proverbs_outcome(
        self,
        pnl: float,
        trade_date: str,
        outcome_type: str = None,
        oracle_prediction_id: int = None
    ):
        """
        Record trade outcome to Proverbs Enhanced for feedback loop tracking.

        Migration 023: Enhanced to pass strategy-level data for feedback loop analysis.

        This updates:
        - Consecutive loss tracking (triggers kill if threshold reached)
        - Daily P&L monitoring (triggers kill if max loss reached)
        - Performance tracking for version comparison
        - Strategy-level analysis (IC effectiveness)
        """
        if not PROVERBS_ENHANCED_AVAILABLE or not get_proverbs_enhanced:
            return

        try:
            enhanced = get_proverbs_enhanced()
            alerts = enhanced.record_trade_outcome(
                bot_name='FORTRESS',
                pnl=pnl,
                trade_date=trade_date,
                capital_base=getattr(self, 'config', {}).get('capital', 100000.0)
                if hasattr(self.config, 'get') else 100000.0,
                # Migration 023: Enhanced feedback loop parameters
                outcome_type=outcome_type,
                strategy_type='IRON_CONDOR',  # FORTRESS is an Iron Condor bot
                oracle_prediction_id=oracle_prediction_id
            )

            if alerts:
                for alert in alerts:
                    logger.warning(f"FORTRESS Proverbs Alert: {alert}")

            logger.debug(f"FORTRESS: Recorded outcome to Proverbs Enhanced - P&L=${pnl:.2f}")

        except Exception as e:
            logger.warning(f"FORTRESS: Proverbs outcome recording failed: {e}")

    def _determine_outcome_type(self, close_reason: str, pnl: float) -> str:
        """
        Determine outcome type from close reason and P&L.

        Migration 023: Helper for feedback loop outcome classification.

        Returns:
            str: Outcome type (MAX_PROFIT, PARTIAL_PROFIT, STOP_LOSS, CALL_BREACHED, PUT_BREACHED, LOSS)
        """
        if pnl > 0:
            if 'PROFIT_TARGET' in close_reason or 'MAX_PROFIT' in close_reason or 'EXPIRED_PROFIT' in close_reason:
                return 'MAX_PROFIT'
            else:
                return 'PARTIAL_PROFIT'
        else:
            if 'STOP_LOSS' in close_reason:
                return 'STOP_LOSS'
            elif 'CALL' in close_reason.upper() and 'BREACH' in close_reason.upper():
                return 'CALL_BREACHED'
            elif 'PUT' in close_reason.upper() and 'BREACH' in close_reason.upper():
                return 'PUT_BREACHED'
            else:
                return 'LOSS'

    def _record_thompson_outcome(self, pnl: float):
        """
        Record trade outcome to Thompson Sampling for capital allocation.

        This updates the Beta distribution parameters for FORTRESS,
        which affects future capital allocation across bots.
        """
        if not AUTO_VALIDATION_AVAILABLE or not record_bot_outcome:
            return

        try:
            record_bot_outcome('FORTRESS', win=(pnl > 0), pnl=pnl)
            logger.debug(f"FORTRESS: Recorded outcome to Thompson Sampling - P&L=${pnl:.2f}")
        except Exception as e:
            logger.warning(f"FORTRESS: Thompson outcome recording failed: {e}")

    def _record_learning_memory_prediction(self, pos: IronCondorPosition, signal) -> Optional[str]:
        """
        Record trade prediction to Learning Memory for self-improvement tracking.

        Returns prediction_id if recorded, None otherwise.
        """
        if not LEARNING_MEMORY_AVAILABLE or not get_learning_memory:
            return None

        try:
            memory = get_learning_memory()

            # Build context from signal and position
            context = {
                "gex_regime": signal.gex_regime if hasattr(signal, 'gex_regime') else "unknown",
                "vix": signal.vix if hasattr(signal, 'vix') else 20.0,
                "spot_price": signal.spot_price if hasattr(signal, 'spot_price') else 590.0,
                "call_wall": signal.call_wall if hasattr(signal, 'call_wall') else 0,
                "put_wall": signal.put_wall if hasattr(signal, 'put_wall') else 0,
                "flip_point": getattr(signal, 'flip_point', 0),
                "expected_move": signal.expected_move if hasattr(signal, 'expected_move') else 0,
                "day_of_week": datetime.now(CENTRAL_TZ).weekday()
            }

            # Record prediction: IC will be profitable (price stays within wings)
            # Note: signal.confidence is already 0-1 from Prophet, not 0-100
            prediction_id = memory.record_prediction(
                prediction_type="iron_condor_outcome",
                prediction=f"IC profitable: {pos.put_short_strike}/{pos.call_short_strike}",
                confidence=signal.confidence if hasattr(signal, 'confidence') else 0.7,
                context=context
            )

            logger.info(f"FORTRESS: Learning Memory prediction recorded: {prediction_id}")
            return prediction_id

        except Exception as e:
            logger.warning(f"FORTRESS: Learning Memory prediction failed: {e}")
            return None

    def _record_learning_memory_outcome(self, prediction_id: str, pnl: float, close_reason: str):
        """Record trade outcome to Learning Memory for accuracy tracking."""
        if not LEARNING_MEMORY_AVAILABLE or not get_learning_memory or not prediction_id:
            return

        try:
            memory = get_learning_memory()

            # Determine if prediction was correct (profitable = correct for IC)
            was_correct = pnl > 0

            memory.record_outcome(
                prediction_id=prediction_id,
                outcome=f"{close_reason}: ${pnl:.2f}",
                was_correct=was_correct,
                notes=f"P&L: ${pnl:.2f}, Reason: {close_reason}"
            )

            logger.info(f"FORTRESS: Learning Memory outcome recorded: correct={was_correct}, P&L=${pnl:.2f}")

        except Exception as e:
            logger.warning(f"FORTRESS: Learning Memory outcome recording failed: {e}")

    def _store_oracle_prediction(self, signal, position: IronCondorPosition) -> int | None:
        """
        Store Prophet prediction to database AFTER position opens.

        Migration 023 (Option C): This is called ONLY when a position is opened,
        not during every scan. This ensures 1:1 prediction-to-position mapping.

        This is CRITICAL for the ML feedback loop:
        1. store_prediction() creates the record in prophet_predictions table
        2. We link the prediction to this position via position_id
        3. After trade closes, update_outcome() updates that record with actual results
        4. Prophet uses this data for continuous model improvement

        Returns:
            int: The oracle_prediction_id for linking, or None if storage failed
        """
        if not PROPHET_AVAILABLE:
            return None

        try:
            prophet = ProphetAdvisor()

            # Build MarketContext from signal
            gex_regime_str = signal.gex_regime.upper() if signal.gex_regime else 'NEUTRAL'
            try:
                gex_regime = GEXRegime[gex_regime_str]
            except (KeyError, AttributeError):
                gex_regime = GEXRegime.NEUTRAL

            context = ProphetMarketContext(
                spot_price=signal.spot_price,
                vix=signal.vix,
                gex_regime=gex_regime,
                gex_call_wall=signal.call_wall,
                gex_put_wall=signal.put_wall,
                gex_flip_point=getattr(signal, 'flip_point', 0),
                gex_net=getattr(signal, 'net_gex', 0),
                day_of_week=datetime.now(CENTRAL_TZ).weekday(),
                expected_move_pct=(signal.expected_move / signal.spot_price * 100) if signal.spot_price else 0,
            )

            # Build ProphetPrediction from signal's Prophet context
            from quant.prophet_advisor import ProphetPrediction, TradingAdvice, BotName

            # Determine advice from signal
            advice_str = getattr(signal, 'oracle_advice', 'TRADE_FULL')
            try:
                advice = TradingAdvice[advice_str] if advice_str else TradingAdvice.TRADE_FULL
            except (KeyError, ValueError):
                advice = TradingAdvice.TRADE_FULL

            prediction = ProphetPrediction(
                bot_name=BotName.FORTRESS,
                advice=advice,
                win_probability=getattr(signal, 'oracle_win_probability', 0.7),
                confidence=signal.confidence,
                suggested_risk_pct=10.0,
                suggested_sd_multiplier=getattr(signal, 'oracle_suggested_sd', 1.0),
                use_gex_walls=getattr(signal, 'oracle_use_gex_walls', False),
                suggested_put_strike=signal.put_short,
                suggested_call_strike=signal.call_short,
                top_factors=[(f['factor'], f['impact']) for f in getattr(signal, 'oracle_top_factors', [])],
                reasoning=signal.reasoning,
                probabilities=getattr(signal, 'oracle_probabilities', {}),
            )

            # Store to database with position_id and strategy_recommendation (Migration 023)
            trade_date = position.expiration if hasattr(position, 'expiration') else datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")
            prediction_id = prophet.store_prediction(
                prediction,
                context,
                trade_date,
                position_id=position.position_id,  # Migration 023: Link to specific position
                strategy_recommendation='IRON_CONDOR'  # Migration 023: FORTRESS uses Iron Condor strategy
            )

            if prediction_id and isinstance(prediction_id, int):
                logger.info(f"FORTRESS: Prophet prediction stored for {trade_date} (id={prediction_id}, Win Prob: {prediction.win_probability:.0%})")
                # Update position in database with the oracle_prediction_id
                self.db.update_oracle_prediction_id(position.position_id, prediction_id)
                return prediction_id
            elif prediction_id:  # True (backward compatibility)
                logger.info(f"FORTRESS: Prophet prediction stored for {trade_date} (Win Prob: {prediction.win_probability:.0%})")
                return None
            else:
                logger.warning(f"FORTRESS: Failed to store Prophet prediction for {trade_date}")
                return None

        except Exception as e:
            logger.warning(f"FORTRESS: Prophet prediction storage failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _store_oracle_prediction_for_scan(
        self,
        signal,
        prophet_data: Dict[str, Any],
        market_data: Dict[str, Any],
        decision: str
    ):
        """
        Store Prophet prediction to database for ALL scans (not just traded).

        This provides visibility into Prophet decisions even when no trade is executed.
        Critical for debugging "why isn't the bot trading?" scenarios.

        Args:
            signal: The generated signal (may be invalid)
            prophet_data: Prophet advice dict from get_prophet_advice()
            market_data: Market conditions at scan time
            decision: The decision made (TRADED, NO_TRADE, SKIP, etc.)
        """
        if not PROPHET_AVAILABLE:
            return

        try:
            prophet = ProphetAdvisor()
            from quant.prophet_advisor import ProphetPrediction, TradingAdvice, BotName

            # Build MarketContext
            gex_regime_str = market_data.get('gex_regime', market_data.get('regime', 'NEUTRAL'))
            if isinstance(gex_regime_str, str):
                gex_regime_str = gex_regime_str.upper()
            else:
                gex_regime_str = 'NEUTRAL'
            try:
                gex_regime = GEXRegime[gex_regime_str]
            except (KeyError, AttributeError):
                gex_regime = GEXRegime.NEUTRAL

            spot_price = market_data.get('underlying_price', market_data.get('spot_price', 0))
            context = ProphetMarketContext(
                spot_price=spot_price,
                vix=market_data.get('vix', 0),
                gex_regime=gex_regime,
                gex_call_wall=market_data.get('call_wall', 0),
                gex_put_wall=market_data.get('put_wall', 0),
                gex_flip_point=market_data.get('flip_point', 0),
                gex_net=market_data.get('net_gex', 0),
                day_of_week=datetime.now(CENTRAL_TZ).weekday(),
                expected_move_pct=(market_data.get('expected_move', 0) / spot_price * 100) if spot_price else 0,
            )

            # Get advice from prophet_data or signal
            advice_str = prophet_data.get('advice', 'SKIP_TODAY') if prophet_data else 'SKIP_TODAY'
            if signal and hasattr(signal, 'oracle_advice') and signal.oracle_advice:
                advice_str = signal.oracle_advice
            try:
                advice = TradingAdvice[advice_str] if advice_str else TradingAdvice.SKIP_TODAY
            except (KeyError, ValueError):
                advice = TradingAdvice.SKIP_TODAY

            # Get win probability
            win_prob = 0
            if prophet_data:
                win_prob = prophet_data.get('win_probability', 0)
            if signal and hasattr(signal, 'oracle_win_probability') and signal.oracle_win_probability > win_prob:
                win_prob = signal.oracle_win_probability

            # Get confidence
            confidence = 0
            if prophet_data:
                confidence = prophet_data.get('confidence', 0)
            if signal and hasattr(signal, 'confidence') and signal.confidence > confidence:
                confidence = signal.confidence

            # Get top factors
            top_factors = []
            if prophet_data and prophet_data.get('top_factors'):
                factors = prophet_data['top_factors']
                if isinstance(factors, list):
                    for f in factors:
                        if isinstance(f, dict):
                            top_factors.append((f.get('factor', 'unknown'), f.get('impact', 0)))
                        elif isinstance(f, tuple):
                            top_factors.append(f)

            # Build reasoning
            reasoning = f"Decision: {decision}"
            if prophet_data and prophet_data.get('reasoning'):
                reasoning = prophet_data['reasoning']
            if signal and signal.reasoning:
                reasoning = signal.reasoning

            prediction = ProphetPrediction(
                bot_name=BotName.FORTRESS,
                advice=advice,
                win_probability=win_prob,
                confidence=confidence,
                suggested_risk_pct=prophet_data.get('suggested_risk_pct', 0) if prophet_data else 0,
                suggested_sd_multiplier=prophet_data.get('suggested_sd_multiplier', 1.0) if prophet_data else 1.0,
                use_gex_walls=prophet_data.get('use_gex_walls', False) if prophet_data else False,
                suggested_put_strike=signal.put_short if signal else None,
                suggested_call_strike=signal.call_short if signal else None,
                top_factors=top_factors,
                reasoning=reasoning,
                probabilities=prophet_data.get('probabilities', {}) if prophet_data else {},
            )

            # Store to database - use today's date for non-traded scans
            trade_date = datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")
            success = prophet.store_prediction(prediction, context, trade_date)

            if success:
                logger.debug(f"FORTRESS: Prophet scan prediction stored (Win Prob: {win_prob:.0%}, Decision: {decision})")
            else:
                logger.debug(f"FORTRESS: Prophet scan prediction storage returned False")

        except Exception as e:
            logger.debug(f"FORTRESS: Prophet scan prediction storage skipped: {e}")

    def _get_force_exit_time(self, now: datetime, today: str) -> datetime:
        """
        Get the effective force exit time, accounting for early close days.

        On early close days (Christmas Eve, day after Thanksgiving), market closes at 12:00 PM CT.
        We should force exit 5 minutes before market close instead of using the normal config.
        """
        # Default force exit from config
        force_parts = self.config.force_exit.split(':')
        config_force_time = now.replace(hour=int(force_parts[0]), minute=int(force_parts[1]), second=0)

        # Check if today is an early close day
        if MARKET_CALENDAR_AVAILABLE and MARKET_CALENDAR:
            close_hour, close_minute = MARKET_CALENDAR.get_market_close_time(today)
            # Early close: force exit 10 min before market close
            early_close_force = now.replace(hour=close_hour, minute=close_minute, second=0) - timedelta(minutes=10)

            # Use the earlier of config time and early close time
            if early_close_force < config_force_time:
                logger.info(f"FORTRESS: Early close day - adjusting force exit from {self.config.force_exit} to {early_close_force.strftime('%H:%M')}")
                return early_close_force

        return config_force_time

    def _check_exit_conditions(
        self,
        pos: IronCondorPosition,
        now: datetime,
        today: str
    ) -> tuple[bool, str]:
        """
        Check if IC should be closed.

        Exit conditions (in priority order):
        1. FORCE_EXIT: Current time >= force exit time on expiration day
        2. EXPIRED: Position's expiration date is BEFORE today (past expiration)
        3. PROFIT_TARGET / STOP_LOSS: P&L targets

        NOTE: On expiration day, we use FORCE_EXIT (not EXPIRED) to ensure positions are
        closed at the proper time (10 min before market close), not at market open.
        """
        # Get force exit time (handles early close days)
        force_time = self._get_force_exit_time(now, today)

        # FORCE_EXIT: On expiration day, close at force exit time (10 min before market close)
        if pos.expiration == today and now >= force_time:
            return True, "FORCE_EXIT_TIME"

        # EXPIRED: Position is PAST expiration (should have been closed yesterday)
        if pos.expiration < today:
            logger.warning(f"Position {pos.position_id} is PAST expiration ({pos.expiration}) - closing immediately")
            return True, "EXPIRED"

        # Get current value with fallback handling
        current_value = self.executor.get_position_current_value(pos)
        if current_value is None:
            # PRICING FALLBACK: Don't silently block exits when pricing fails
            logger.warning(f"[FORTRESS EXIT] Pricing unavailable for {pos.position_id}")

            # If we're within 30 minutes of force exit time, force close anyway
            force_time = self._get_force_exit_time(now, today)
            minutes_to_force = (force_time - now).total_seconds() / 60
            if minutes_to_force <= 30 and pos.expiration == today:
                logger.warning(f"[FORTRESS EXIT] Force closing {pos.position_id} - pricing failed but {minutes_to_force:.0f}min to force exit")
                return True, "PRICING_FAILURE_NEAR_EXPIRY"

            # Log but don't block - we'll retry next cycle
            self.db.log("WARNING", f"Pricing unavailable for exit check: {pos.position_id}")
            return False, "PRICING_UNAVAILABLE"

        # MATH OPTIMIZER: Use HJB for dynamic exit timing
        if MATH_OPTIMIZER_AVAILABLE and hasattr(self, '_math_enabled') and self._math_enabled:
            try:
                # Calculate current P&L
                current_pnl = pos.total_credit - current_value
                max_profit = pos.total_credit

                # Get expiry time (end of day)
                expiry_time = now.replace(hour=16, minute=0, second=0)  # Market close

                # Get entry time from position (field is 'open_time' not 'entry_time')
                entry_time = pos.open_time if hasattr(pos, 'open_time') and pos.open_time else now - timedelta(hours=2)

                # Check HJB exit signal
                hjb_result = self.math_should_exit(
                    current_pnl=current_pnl,
                    max_profit=max_profit,
                    entry_time=entry_time,
                    expiry_time=expiry_time,
                    current_volatility=0.15  # Could get from VIX
                )

                if hjb_result.get('should_exit') and hjb_result.get('optimized'):
                    # Use reason from HJB if available and non-empty, otherwise construct one
                    raw_reason = hjb_result.get('reason', '')
                    pnl_pct = hjb_result.get('pnl_pct', 0)
                    reason = raw_reason if raw_reason else f"HJB_OPTIMAL_{pnl_pct*100:.0f}%"
                    self.db.log("INFO", f"HJB exit signal: {reason}")
                    return True, reason

            except Exception as e:
                logger.debug(f"HJB exit check skipped: {e}")

        # Fallback: Standard profit target (50% of credit received)
        profit_target_value = pos.total_credit * (1 - self.config.profit_target_pct / 100)
        if current_value <= profit_target_value:
            return True, f"PROFIT_TARGET_{self.config.profit_target_pct:.0f}%"

        # Stop loss (if enabled)
        if self.config.use_stop_loss:
            stop_loss_value = pos.total_credit * self.config.stop_loss_multiple
            if current_value >= stop_loss_value:
                return True, f"STOP_LOSS_{self.config.stop_loss_multiple}X"

        return False, ""

    def _try_new_entry_with_context(self, prophet_data: dict = None) -> tuple[Optional[IronCondorPosition], Optional[Any]]:
        """Try to open a new Iron Condor, returning both position and signal for logging

        Args:
            prophet_data: Pre-fetched Prophet advice from run_cycle(). Passed to generate_signal()
                        to ensure consistency between scan logs and trade decision.
        """
        from .signals import IronCondorSignal

        # MATH OPTIMIZER: Check regime before generating signal
        if MATH_OPTIMIZER_AVAILABLE and hasattr(self, '_math_enabled') and self._math_enabled:
            # Get market data for regime check (VIX from signal generator)
            try:
                # BUG FIX: Use get_gex_data() - get_market_snapshot doesn't exist
                market_data = self.signals.get_gex_data() if hasattr(self.signals, 'get_gex_data') else {}
                if market_data:
                    should_trade, regime_reason = self.math_should_trade_regime(market_data)
                    if not should_trade:
                        self.db.log("INFO", f"Math optimizer regime gate: {regime_reason}")
                        return None, None
            except Exception as e:
                logger.debug(f"Regime check skipped: {e}")

        # Generate signal - pass pre-fetched prophet_data to avoid double Prophet call
        signal = self.signals.generate_signal(prophet_data=prophet_data)
        if not signal:
            self.db.log("INFO", "No valid signal generated")
            return None, None

        if not signal.is_valid:
            self.db.log("INFO", f"Signal invalid: {signal.reasoning}")
            return None, signal  # Return signal for logging even if invalid

        # MATH OPTIMIZER: Smooth Greeks if available
        if MATH_OPTIMIZER_AVAILABLE and hasattr(self, '_math_enabled') and self._math_enabled:
            try:
                if hasattr(signal, 'greeks') and signal.greeks:
                    smoothed = self.math_smooth_greeks(signal.greeks)
                    logger.debug(f"FORTRESS: Smoothed Greeks applied")
            except Exception as e:
                logger.debug(f"Greeks smoothing skipped: {e}")

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

        # MATH OPTIMIZER: Get Thompson Sampling allocation weight
        thompson_weight = 1.0  # Default neutral weight
        if MATH_OPTIMIZER_AVAILABLE and hasattr(self, 'math_get_allocation'):
            try:
                allocation = self.math_get_allocation()
                # Convert allocation percentage to weight (20% baseline = 1.0)
                # So 30% = 1.5x, 10% = 0.5x
                fortress_alloc = allocation.get('allocations', {}).get('FORTRESS', 0.2)
                thompson_weight = fortress_alloc / 0.2  # Normalize to 20% baseline
                logger.info(f"FORTRESS Thompson weight: {thompson_weight:.2f} (allocation: {fortress_alloc:.1%})")
            except Exception as e:
                logger.debug(f"Thompson allocation skipped: {e}")

        # Execute the trade with Thompson-adjusted position sizing
        position = self.executor.execute_iron_condor(signal, thompson_weight=thompson_weight)
        if not position:
            self.db.log("ERROR", "Execution failed", {'signal': signal.reasoning})
            return None, signal

        # Save to database - CRITICAL: Only return position if save succeeds
        if not self.db.save_position(position):
            self.db.log("ERROR", "Failed to save position to database", {'pos_id': position.position_id})
            logger.error(f"Position {position.position_id} executed but not saved to database!")
            # Return None to indicate trade did NOT complete successfully
            # This prevents scan activity from showing "TRADED" when position isn't persisted
            return None, signal

        self.db.log("INFO", f"Opened: {position.position_id}", position.to_dict())

        # Save equity snapshot after opening position (for real-time equity curve)
        self.db.save_equity_snapshot(
            balance=self.db.get_current_balance(),
            realized_pnl=0,
            open_positions=self.db.get_position_count(),
            note=f"Opened {position.position_id}"
        )

        # CRITICAL: Store Prophet prediction for ML feedback loop
        # This enables update_outcome to find and update the prediction record
        self._store_oracle_prediction(signal, position)

        # Record prediction to Learning Memory for self-improvement tracking
        prediction_id = self._record_learning_memory_prediction(position, signal)
        if prediction_id:
            self._prediction_ids[position.position_id] = prediction_id

        return position, signal

    def _update_daily_summary(self, today: str, cycle_result: Dict) -> None:
        """Update daily performance"""
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

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def get_status(self) -> Dict[str, Any]:
        """Get current bot status"""
        now = datetime.now(CENTRAL_TZ)
        today = now.strftime("%Y-%m-%d")

        positions = self.db.get_open_positions()
        has_traded = self.db.has_traded_today(today)

        # Calculate unrealized P&L (only if live pricing available)
        unrealized_pnl = 0.0
        has_live_pricing = False
        for pos in positions:
            current_value = self.executor.get_position_current_value(pos)
            if current_value is not None:
                has_live_pricing = True
                pnl = (pos.total_credit - current_value) * 100 * pos.contracts
                unrealized_pnl += pnl

        # Get execution capability status
        execution_status = self.executor.get_execution_status() if hasattr(self.executor, 'get_execution_status') else {}

        return {
            'bot_name': 'FORTRESS',
            'version': 'V2',
            'mode': self.config.mode.value,
            'ticker': self.config.ticker,
            'preset': self.config.preset.value,
            'status': 'active',
            'timestamp': now.isoformat(),
            'open_positions': len(positions),
            'traded_today': has_traded,
            'unrealized_pnl': unrealized_pnl if has_live_pricing else None,
            'has_live_pricing': has_live_pricing,
            'positions': [p.to_dict() for p in positions],
            # Execution capability - CRITICAL for knowing if trades can actually execute
            'can_execute_trades': execution_status.get('can_execute', False),
            'execution_error': execution_status.get('init_error'),
        }

    def get_positions(self) -> List[IronCondorPosition]:
        """Get all open positions"""
        return self.db.get_open_positions()

    def force_close_all(self, reason: str = "MANUAL_CLOSE") -> Dict[str, Any]:
        """Force close all open positions"""
        positions = self.db.get_open_positions()
        results = []

        for pos in positions:
            success, close_price, pnl = self.executor.close_position(pos, reason)

            # Handle partial close (put closed but call failed)
            if success == 'partial_put':
                self.db.partial_close_position(
                    position_id=pos.position_id,
                    close_price=close_price,
                    realized_pnl=pnl,
                    close_reason=reason,
                    closed_leg='put'
                )
                results.append({
                    'position_id': pos.position_id,
                    'success': 'partial',
                    'pnl': pnl,
                    'note': 'Put leg closed, call leg requires manual close'
                })
                continue

            if success:
                # BUG FIX: Check DB return value - don't silently ignore failures
                db_success = self.db.close_position(pos.position_id, close_price, pnl, reason)
                if not db_success:
                    logger.error(f"CRITICAL: Position {pos.position_id} closed but DB update failed!")
                # Record outcome to Prophet for ML feedback
                self._record_oracle_outcome(pos, reason, pnl)
                # Record outcome to Proverbs Enhanced for feedback loops
                trade_date = pos.expiration if hasattr(pos, 'expiration') else datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")
                # Migration 023: Pass outcome_type and oracle_prediction_id for feedback loop
                outcome_type = self._determine_outcome_type(reason, pnl)
                prediction_id = self.db.get_oracle_prediction_id(pos.position_id)
                self._record_proverbs_outcome(pnl, trade_date, outcome_type, prediction_id)
                # Record outcome to Thompson Sampling for capital allocation
                self._record_thompson_outcome(pnl)
                # Record outcome to Learning Memory for self-improvement
                if pos.position_id in self._prediction_ids:
                    self._record_learning_memory_outcome(
                        self._prediction_ids.pop(pos.position_id),
                        pnl,
                        reason
                    )
            results.append({
                'position_id': pos.position_id,
                'success': success,
                'pnl': pnl
            })

        return {
            'closed': len([r for r in results if r['success'] == True]),
            'partial': len([r for r in results if r['success'] == 'partial']),
            'failed': len([r for r in results if r['success'] == False]),
            'total_pnl': sum(r['pnl'] for r in results),
            'details': results
        }

    def process_expired_positions(self) -> Dict[str, Any]:
        """
        Process expired positions at end of day.

        Called by scheduler at 3:05 PM CT to handle positions that expired
        today or earlier. For expired options:
        - If price stayed within IC wings → max profit (credit received)
        - If price breached a wing → calculate loss based on final price

        Returns dict with processing results for logging.
        """
        now = datetime.now(CENTRAL_TZ)
        today = now.strftime("%Y-%m-%d")

        result = {
            'processed_count': 0,
            'total_pnl': 0.0,
            'positions': [],
            'errors': []
        }

        try:
            # Get all open positions expiring today
            positions = self.db.get_open_positions()
            expired_positions = [p for p in positions if p.expiration <= today]

            if not expired_positions:
                logger.info("FORTRESS EOD: No expired positions to process")
                return result

            logger.info(f"FORTRESS EOD: Processing {len(expired_positions)} expired position(s)")

            for pos in expired_positions:
                try:
                    # Get final underlying price for P&L calculation
                    current_price = self.executor._get_current_price()
                    if not current_price:
                        current_price = pos.underlying_at_entry
                        logger.warning(f"Could not get current price, using entry: ${current_price}")

                    # Calculate final P&L based on where price ended
                    final_pnl = self._calculate_expiration_pnl(pos, current_price)

                    # Calculate IC close price (value at expiration)
                    # For Iron Condor: close_price = 0 if max profit, or intrinsic value if breached
                    close_price = pos.total_credit - (final_pnl / (100 * pos.contracts)) if pos.contracts > 0 else 0

                    # Mark position as expired in database with close price for audit
                    # CRITICAL: Check return value - if DB update fails, position P&L won't be recorded!
                    db_success = self.db.expire_position(pos.position_id, final_pnl, close_price)
                    if not db_success:
                        logger.error(
                            f"CRITICAL: Failed to expire {pos.position_id} in database! "
                            f"P&L ${final_pnl:.2f} will NOT be recorded. Position may be stuck in 'open' status."
                        )
                        result['errors'].append(f"DB update failed for {pos.position_id}")
                        # Still continue to record the outcome for ML (position is effectively expired)
                    else:
                        logger.info(f"FORTRESS: Successfully expired {pos.position_id} with P&L ${final_pnl:.2f}")

                    # Record outcome for ML feedback
                    # Zero P&L is breakeven, not a loss
                    close_reason = "EXPIRED_PROFIT" if final_pnl >= 0 else "EXPIRED_LOSS"
                    self._record_oracle_outcome(pos, close_reason, final_pnl)

                    # Record outcome to Proverbs Enhanced for feedback loops
                    trade_date = pos.expiration if hasattr(pos, 'expiration') else datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")
                    # Migration 023: Pass outcome_type and oracle_prediction_id for feedback loop
                    outcome_type = self._determine_outcome_type(close_reason, final_pnl)
                    prediction_id = self.db.get_oracle_prediction_id(pos.position_id)
                    self._record_proverbs_outcome(final_pnl, trade_date, outcome_type, prediction_id)

                    # Record outcome to Thompson Sampling for capital allocation
                    self._record_thompson_outcome(final_pnl)

                    # Record to Learning Memory
                    if pos.position_id in self._prediction_ids:
                        self._record_learning_memory_outcome(
                            self._prediction_ids.pop(pos.position_id),
                            final_pnl,
                            close_reason
                        )

                    result['processed_count'] += 1
                    result['total_pnl'] += final_pnl
                    result['positions'].append({
                        'position_id': pos.position_id,
                        'final_price': current_price,
                        'pnl': final_pnl,
                        'status': 'expired'
                    })

                    logger.info(
                        f"FORTRESS EOD: Expired {pos.position_id} - "
                        f"Final price: ${current_price:.2f}, P&L: ${final_pnl:.2f}"
                    )

                except Exception as e:
                    logger.error(f"FORTRESS EOD: Failed to process {pos.position_id}: {e}")
                    result['errors'].append(str(e))

            self.db.log("INFO", f"EOD processed {result['processed_count']} positions, P&L: ${result['total_pnl']:.2f}")

        except Exception as e:
            logger.error(f"FORTRESS EOD processing failed: {e}")
            result['errors'].append(str(e))

        return result

    def _calculate_expiration_pnl(self, pos: IronCondorPosition, final_price: float) -> float:
        """
        Calculate P&L at expiration based on final underlying price.

        For 0DTE Iron Condors:
        - If price between short strikes → max profit (keep full credit)
        - If price outside long strikes → max loss
        - If price between short and long → partial loss
        """
        contracts = pos.contracts
        credit_received = pos.total_credit * 100 * contracts

        # Check if price stayed in the "safe zone"
        if pos.put_short_strike <= final_price <= pos.call_short_strike:
            # Max profit - IC expired worthless
            return credit_received

        # Check put side breach
        if final_price < pos.put_short_strike:
            if final_price <= pos.put_long_strike:
                # Max loss on put side
                put_loss = pos.spread_width * 100 * contracts
            else:
                # Partial loss on put side
                put_loss = (pos.put_short_strike - final_price) * 100 * contracts
            return credit_received - put_loss

        # Check call side breach
        if final_price > pos.call_short_strike:
            if final_price >= pos.call_long_strike:
                # Max loss on call side
                call_loss = pos.spread_width * 100 * contracts
            else:
                # Partial loss on call side
                call_loss = (final_price - pos.call_short_strike) * 100 * contracts
            return credit_received - call_loss

        # Should not reach here
        return credit_received


def run_fortress_v2(config: Optional[FortressConfig] = None) -> FortressTrader:
    """Factory function to create FORTRESS trader"""
    return FortressTrader(config)
