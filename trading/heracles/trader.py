"""
HERACLES - Main Trader
======================

MES Futures Scalping Bot using GEX signals.
Named after the legendary Greek hero known for strength and perseverance.

Orchestrates:
- Signal generation from GEX data
- Position management with trailing stops
- Tastytrade order execution
- Win probability tracking (Bayesian → ML)
- Oracle ML feedback loop (outcomes recorded for training)
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from zoneinfo import ZoneInfo

from .models import (
    FuturesPosition, FuturesSignal, TradeDirection, GammaRegime,
    PositionStatus, SignalSource, HERACLESConfig, TradingMode,
    BayesianWinTracker, MES_POINT_VALUE, CENTRAL_TZ
)
from .db import HERACLESDatabase
from .signals import HERACLESSignalGenerator, get_gex_data_for_heracles
from .executor import TastytradeExecutor

logger = logging.getLogger(__name__)

# Market calendar for holiday checking
try:
    from trading.market_calendar import MarketCalendar
    MARKET_CALENDAR = MarketCalendar()
    MARKET_CALENDAR_AVAILABLE = True
except ImportError:
    MARKET_CALENDAR = None
    MARKET_CALENDAR_AVAILABLE = False

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

# Solomon Enhanced for feedback loop recording
try:
    from quant.solomon_enhancements import get_solomon_enhanced
    SOLOMON_ENHANCED_AVAILABLE = True
except ImportError:
    SOLOMON_ENHANCED_AVAILABLE = False
    get_solomon_enhanced = None

# Auto-Validation System for Thompson Sampling capital allocation
try:
    from quant.auto_validation_system import get_auto_validation_system, record_bot_outcome
    AUTO_VALIDATION_AVAILABLE = True
except ImportError:
    AUTO_VALIDATION_AVAILABLE = False
    get_auto_validation_system = None
    record_bot_outcome = None


class HERACLESTrader:
    """
    HERACLES - MES Futures Scalping Bot

    Strategy:
    - POSITIVE GAMMA: Mean reversion - fade moves toward flip point
    - NEGATIVE GAMMA: Momentum - trade breakouts away from flip point

    Risk Management (tuned from 136-trade backtest):
    - Initial stop: 2.5 points ($12.50 per contract)
    - Profit target: 6 points ($30 per contract) - R/R = 2.4:1
    - Breakeven activation: +1.5 points ($7.50 profit)
    - Trailing stop: 0.75 point ($3.75 trail distance)

    Position Sizing:
    - Fixed Fractional with ATR Adjustment
    - Risk 1% per trade by default
    """

    def __init__(self, config: Optional[HERACLESConfig] = None):
        """Initialize HERACLES trader"""
        self.db = HERACLESDatabase()

        # Load config from DB or use provided/defaults
        self.config = config or self.db.get_config()

        # Initialize components
        self.win_tracker = self.db.get_win_tracker()
        self.signal_generator = HERACLESSignalGenerator(self.config, self.win_tracker)
        self.executor = TastytradeExecutor(self.config)

        # State
        self.last_scan_time: Optional[datetime] = None
        self.daily_trades: int = 0
        self.daily_pnl: float = 0.0
        self._scan_count: int = 0  # Track scan number for direction tracker

        # Initialize paper trading account if in paper mode
        if self.config.mode == TradingMode.PAPER:
            self.db.initialize_paper_account(self.config.capital)
            paper_account = self.db.get_paper_account()
            if paper_account:
                logger.info(
                    f"HERACLES Paper Account: ${paper_account['current_balance']:,.2f} "
                    f"(started: ${paper_account['starting_capital']:,.2f})"
                )

        logger.info(
            f"HERACLES initialized: mode={self.config.mode.value}, "
            f"symbol={self.config.symbol}, capital=${self.config.capital:,.2f}"
        )

    # ========================================================================
    # Main Trading Loop
    # ========================================================================

    def run_scan(self) -> Dict[str, Any]:
        """
        Run a single trading scan.

        This is called periodically (every minute) by the scheduler.
        CRITICAL: Logs EVERY scan for ML training data collection.
        """
        # Generate unique scan ID for ML tracking
        scan_id = f"HERACLES-SCAN-{uuid.uuid4().hex[:12]}"

        # Increment scan counter and update direction tracker
        self._scan_count += 1
        from .signals import get_direction_tracker
        direction_tracker = get_direction_tracker()
        direction_tracker.update_scan(self._scan_count)

        scan_result = {
            "timestamp": datetime.now(CENTRAL_TZ).isoformat(),
            "scan_id": scan_id,
            "status": "completed",
            "positions_checked": 0,
            "signals_generated": 0,
            "trades_executed": 0,
            "positions_closed": 0,
            "errors": []
        }

        # Scan context for ML data collection
        scan_context = {
            "scan_id": scan_id,
            "underlying_price": 0,
            "vix": 0,
            "atr": 0,
            "gex_data": {},
            "signal": None,
            "account_balance": 0,
            "is_overnight": False,
            "position_id": None,
        }

        try:
            # Check market hours
            if not self.executor.is_market_open():
                scan_result["status"] = "market_closed"
                self._log_scan_activity(scan_id, "MARKET_CLOSED", scan_result, scan_context,
                                       skip_reason="Futures market closed")
                return scan_result

            # Get current market data
            quote = self.executor.get_mes_quote()
            if not quote:
                scan_result["status"] = "no_quote"
                scan_result["errors"].append("Could not get MES quote")
                self._log_scan_activity(scan_id, "ERROR", scan_result, scan_context,
                                       error_msg="Could not get MES quote")
                return scan_result

            current_price = quote.get("last", 0)
            bid_price = quote.get("bid", 0)
            ask_price = quote.get("ask", 0)
            scan_context["underlying_price"] = current_price
            scan_context["bid_price"] = bid_price
            scan_context["ask_price"] = ask_price

            if current_price <= 0:
                scan_result["status"] = "invalid_price"
                self._log_scan_activity(scan_id, "ERROR", scan_result, scan_context,
                                       error_msg="Invalid price <= 0")
                return scan_result

            # Get GEX data from SPX (same price level as MES futures)
            # SPX requires Tradier production keys (sandbox doesn't support index options)
            gex_data = get_gex_data_for_heracles("SPX")
            scan_context["gex_data"] = gex_data

            # Get account balance (use paper balance in paper mode)
            if self.config.mode == TradingMode.PAPER:
                paper_account = self.db.get_paper_account()
                account_balance = paper_account.get('current_balance', self.config.capital) if paper_account else self.config.capital
            else:
                balance = self.executor.get_account_balance()
                account_balance = balance.get("net_liquidating_value", self.config.capital) if balance else self.config.capital
            scan_context["account_balance"] = account_balance

            # Get VIX from Tradier (more reliable than GEX data)
            vix = self._get_vix()
            scan_context["vix"] = vix

            # Calculate ATR from real data or estimate
            atr, atr_is_estimated = self._get_atr(current_price)
            scan_context["atr"] = atr
            scan_context["atr_is_estimated"] = atr_is_estimated

            # Determine if overnight session
            is_overnight = self._is_overnight_session()
            scan_context["is_overnight"] = is_overnight

            # 1. Manage existing positions (check stops, trailing)
            positions = self.db.get_open_positions()
            scan_result["positions_checked"] = len(positions)

            for position in positions:
                closed = self._manage_position(position, current_price)
                if closed:
                    scan_result["positions_closed"] += 1

            # 2. Check for new signals (if room for more positions)
            open_count = len([p for p in self.db.get_open_positions()])

            if open_count < self.config.max_open_positions:
                # Generate signal
                signal = self.signal_generator.generate_signal(
                    current_price=current_price,
                    gex_data=gex_data,
                    vix=vix,
                    atr=atr,
                    account_balance=account_balance,
                    is_overnight=is_overnight
                )
                scan_context["signal"] = signal

                if signal:
                    scan_result["signals_generated"] += 1

                    if signal.is_valid:
                        # Execute the signal with scan_id for ML tracking
                        success, position_id = self._execute_signal_with_id(signal, account_balance, scan_id)
                        if success:
                            scan_result["trades_executed"] += 1
                            scan_context["position_id"] = position_id

                            # Log signal
                            self.db.save_signal(signal, was_executed=True)

                            # Log scan activity with trade
                            self._log_scan_activity(scan_id, "TRADED", scan_result, scan_context,
                                                   action=f"Opened {signal.direction.value} position")
                        else:
                            self.db.save_signal(signal, was_executed=False, skip_reason="Execution failed")
                            self._log_scan_activity(scan_id, "NO_TRADE", scan_result, scan_context,
                                                   skip_reason="Execution failed")
                    else:
                        self.db.save_signal(signal, was_executed=False, skip_reason="Invalid signal")
                        self._log_scan_activity(scan_id, "NO_TRADE", scan_result, scan_context,
                                               skip_reason=f"Invalid signal: {signal.reasoning[:100] if signal.reasoning else 'No reason'}")
                else:
                    # No signal generated
                    self._log_scan_activity(scan_id, "NO_TRADE", scan_result, scan_context,
                                           skip_reason="No signal generated")
            else:
                # Max positions reached
                self._log_scan_activity(scan_id, "SKIP", scan_result, scan_context,
                                       skip_reason=f"Max positions ({self.config.max_open_positions}) reached")

            # 3. Save equity snapshot with CURRENT positions (refresh to include any new positions)
            current_positions = self.db.get_open_positions()
            self._save_equity_snapshot(account_balance, current_positions)

            self.last_scan_time = datetime.now(CENTRAL_TZ)

        except Exception as e:
            logger.error(f"Error in HERACLES scan: {e}")
            scan_result["status"] = "error"
            scan_result["errors"].append(str(e))
            self._log_scan_activity(scan_id, "ERROR", scan_result, scan_context,
                                   error_msg=str(e))

        return scan_result

    def monitor_positions(self) -> Dict[str, Any]:
        """
        Lightweight position monitor - checks stops/targets only.

        This is designed to be called MORE FREQUENTLY than run_scan()
        (e.g., every 15-30 seconds) to reduce stop slippage caused by
        the 1-minute scan interval.

        Does NOT:
        - Generate new signals
        - Log to scan_activity table
        - Check for new trade opportunities

        ONLY:
        - Gets current price
        - Checks all open positions against stops/targets
        - Closes positions if stop/target hit
        """
        result = {
            "timestamp": datetime.now(CENTRAL_TZ).isoformat(),
            "positions_checked": 0,
            "positions_closed": 0,
            "status": "completed",
            "errors": []
        }

        try:
            # Check market hours - no point monitoring if market is closed
            if not self.executor.is_market_open():
                result["status"] = "market_closed"
                return result

            # Get current price only (no GEX, no VIX - just price)
            quote = self.executor.get_mes_quote()
            if not quote:
                result["status"] = "no_quote"
                return result

            current_price = quote.get("last", 0)
            if current_price <= 0:
                result["status"] = "invalid_price"
                return result

            # Get open positions
            positions = self.db.get_open_positions()
            result["positions_checked"] = len(positions)

            # Periodic heartbeat log (every ~1 min = every 4th call at 15-sec intervals)
            if not hasattr(self, '_monitor_call_count'):
                self._monitor_call_count = 0
            self._monitor_call_count += 1
            if self._monitor_call_count % 4 == 1:
                logger.info(f"MONITOR HEARTBEAT: Price={current_price:.2f}, Open positions={len(positions)}")

            if not positions:
                return result

            # Log monitor check with position details
            for position in positions:
                distance_to_stop = abs(current_price - position.current_stop)
                distance_to_target = abs(current_price - (position.entry_price + self.config.profit_target_points if position.direction == TradeDirection.LONG else position.entry_price - self.config.profit_target_points))
                logger.debug(
                    f"MONITOR: {position.direction.value} @ {position.entry_price:.2f} | "
                    f"Price: {current_price:.2f} | Stop: {position.current_stop:.2f} ({distance_to_stop:.2f} away) | "
                    f"Target: {distance_to_target:.2f} away"
                )

            # Check each position
            for position in positions:
                closed = self._manage_position(position, current_price)
                if closed:
                    result["positions_closed"] += 1
                    logger.info(
                        f"MONITOR CLOSED: {position.position_id[:8]} | {position.direction.value} | "
                        f"Entry: {position.entry_price:.2f} | Exit: {current_price:.2f} | "
                        f"Stop was: {position.current_stop:.2f}"
                    )

        except Exception as e:
            logger.warning(f"Position monitor error: {e}")
            result["status"] = "error"
            result["errors"].append(str(e))

        return result

    def _log_scan_activity(
        self,
        scan_id: str,
        outcome: str,
        result: Dict,
        context: Dict,
        action: str = "",
        skip_reason: str = "",
        error_msg: str = ""
    ) -> None:
        """
        Log scan activity for ML training data collection.

        This captures EVERY scan - trades, skips, and errors - with full
        market context to enable supervised learning model training.
        """
        try:
            gex_data = context.get("gex_data", {})
            signal = context.get("signal")
            underlying_price = context.get("underlying_price", 0)

            # Calculate distances to GEX levels
            flip_point = gex_data.get("flip_point", 0)
            call_wall = gex_data.get("call_wall", 0)
            put_wall = gex_data.get("put_wall", 0)

            distance_to_flip_pct = 0
            distance_to_call_wall_pct = 0
            distance_to_put_wall_pct = 0

            if underlying_price > 0:
                if flip_point > 0:
                    distance_to_flip_pct = ((underlying_price - flip_point) / underlying_price) * 100
                if call_wall > 0:
                    distance_to_call_wall_pct = ((call_wall - underlying_price) / underlying_price) * 100
                if put_wall > 0:
                    distance_to_put_wall_pct = ((underlying_price - put_wall) / underlying_price) * 100

            # Get Bayesian tracker state
            tracker = self.win_tracker
            positive_gamma_total = tracker.positive_gamma_wins + tracker.positive_gamma_losses
            negative_gamma_total = tracker.negative_gamma_wins + tracker.negative_gamma_losses

            # Get gamma regime from signal if available, otherwise determine from net_gex
            gamma_regime = "NEUTRAL"
            if signal and hasattr(signal, 'gamma_regime'):
                gamma_regime = signal.gamma_regime.value
            else:
                # Determine regime from net_gex if no signal
                net_gex = gex_data.get("net_gex", 0)
                if net_gex > 0:
                    gamma_regime = "POSITIVE"
                elif net_gex < 0:
                    gamma_regime = "NEGATIVE"

            self.db.save_scan_activity(
                scan_id=scan_id,
                outcome=outcome,
                action_taken=action or result.get("status", ""),
                decision_summary=skip_reason or error_msg or f"Scan completed: {result.get('trades_executed', 0)} trades",
                full_reasoning=signal.reasoning if signal else "",
                underlying_price=underlying_price,
                bid_price=context.get("bid_price", 0),
                ask_price=context.get("ask_price", 0),
                underlying_symbol="MES",
                vix=context.get("vix", 0),
                atr=context.get("atr", 0),
                atr_is_estimated=context.get("atr_is_estimated", True),
                gamma_regime=gamma_regime,
                gex_value=gex_data.get("net_gex", 0),
                flip_point=flip_point,
                call_wall=call_wall,
                put_wall=put_wall,
                distance_to_flip_pct=distance_to_flip_pct,
                distance_to_call_wall_pct=distance_to_call_wall_pct,
                distance_to_put_wall_pct=distance_to_put_wall_pct,
                signal_direction=signal.direction.value if signal else "",
                signal_source=signal.source.value if signal else "",
                signal_confidence=signal.confidence if signal else 0,
                signal_win_probability=signal.win_probability if signal else 0,
                signal_reasoning=signal.reasoning if signal else "",
                bayesian_alpha=tracker.alpha,
                bayesian_beta=tracker.beta,
                bayesian_win_probability=tracker.win_probability,
                # Win rates must be 0-1 range for DECIMAL(5,4) fields
                positive_gamma_win_rate=(tracker.positive_gamma_wins / positive_gamma_total) if positive_gamma_total > 0 else 0.50,
                negative_gamma_win_rate=(tracker.negative_gamma_wins / negative_gamma_total) if negative_gamma_total > 0 else 0.50,
                contracts_calculated=signal.contracts if signal else 0,
                risk_amount=signal.risk_amount if signal and hasattr(signal, 'risk_amount') else 0,
                account_balance=context.get("account_balance", 0),
                is_overnight_session=context.get("is_overnight", False),
                session_type="OVERNIGHT" if context.get("is_overnight") else "RTH",
                trade_executed=outcome == "TRADED",
                position_id=context.get("position_id", ""),
                entry_price=signal.entry_price if signal else 0,
                stop_price=signal.stop_price if signal else 0,
                error_message=error_msg,
                skip_reason=skip_reason
            )
        except Exception as e:
            logger.warning(f"Failed to log scan activity: {e}")

    def _execute_signal_with_id(self, signal: FuturesSignal, account_balance: float, scan_id: str = "") -> Tuple[bool, str]:
        """Execute signal and return (success, position_id) for scan tracking."""
        position_id = f"HERACLES-{uuid.uuid4().hex[:8]}"
        success = self._execute_signal_internal(signal, account_balance, position_id, scan_id)
        return success, position_id if success else ""

    # ========================================================================
    # Position Management
    # ========================================================================

    def _manage_position(self, position: FuturesPosition, current_price: float) -> bool:
        """
        Manage an open position - check stops and trailing.

        NO-LOSS TRAILING STRATEGY (when enabled):
        1. No tight stop initially - only emergency stop (15 pts) for catastrophic moves
        2. Track high water mark price
        3. Once profitable by activation_pts (3 pts), set trailing stop at breakeven
        4. Continue trailing the stop as price moves favorably (trail_distance = 2 pts)
        5. Exit when trailing stop is hit

        This avoids small stop-outs that would have turned into winners.
        Backtest result: NL_ACT3_TRAIL2 = $18,005 P&L, 88% win rate vs baseline -$2,525

        Also tracks high/low price excursions for backtesting data quality.

        Returns True if position was closed.
        """
        try:
            # Track high/low prices for backtesting (do this BEFORE checking stops)
            # This ensures we capture the price that triggered the stop
            self._update_position_high_low(position, current_price)

            # ================================================================
            # NO-LOSS TRAILING STRATEGY
            # ================================================================
            if self.config.use_no_loss_trailing:
                return self._manage_position_no_loss_trailing(position, current_price)

            # ================================================================
            # ORIGINAL STRATEGY (fallback when no-loss trailing disabled)
            # ================================================================

            # Check if stopped out (stop takes priority over profit target)
            if self._check_stop_hit(position, current_price):
                return self._close_position(
                    position,
                    current_price,
                    PositionStatus.STOPPED,
                    "Stop loss triggered"
                )

            # Check if profit target hit (only if stop wasn't hit)
            if self._check_profit_target_hit(position, current_price):
                return self._close_position(
                    position,
                    current_price,
                    PositionStatus.PROFIT_TARGET,
                    "Profit target hit"
                )

            # Check for breakeven activation
            if not position.trailing_active:
                if position.should_move_to_breakeven(
                    current_price,
                    self.config.breakeven_activation_points
                ):
                    # Move stop to breakeven
                    new_stop = position.entry_price
                    position.current_stop = new_stop
                    position.trailing_active = True
                    self.db.update_stop(position.position_id, new_stop, trailing_active=True)
                    logger.info(f"Position {position.position_id}: Stop moved to breakeven at {new_stop:.2f}")

            # Check for trailing stop update
            if position.trailing_active:
                new_stop = position.should_trail_stop(
                    current_price,
                    self.config.trailing_stop_points
                )
                if new_stop:
                    position.current_stop = new_stop
                    self.db.update_stop(position.position_id, new_stop, trailing_active=True)
                    logger.info(f"Position {position.position_id}: Trailing stop updated to {new_stop:.2f}")

            # Update high water mark and MAE
            pnl = position.calculate_pnl(current_price)
            if pnl > position.high_water_mark:
                position.high_water_mark = pnl
            if pnl < 0 and abs(pnl) > position.max_adverse_excursion:
                position.max_adverse_excursion = abs(pnl)

            return False

        except Exception as e:
            logger.error(f"Error managing position {position.position_id}: {e}")
            return False

    def _manage_position_no_loss_trailing(self, position: FuturesPosition, current_price: float) -> bool:
        """
        NO-LOSS TRAILING POSITION MANAGEMENT

        Strategy from backtest (NL_ACT3_TRAIL2 = $18,005 P&L, 88% win rate):
        1. No tight stop initially - only emergency stop for catastrophic moves
        2. Wait for price to profit by activation_pts (3 pts)
        3. Once activated, set trailing stop at breakeven (entry price)
        4. As price continues in our favor, trail the stop to lock in profits
        5. Exit when trailing stop is hit

        Key insight: Many trades that hit tight stops would have been winners
        if given more room. This strategy lets winners run while limiting
        catastrophic losses.

        OVERNIGHT HYBRID: Uses the stored initial_stop which was calculated
        with overnight parameters (10 pts) vs RTH (15 pts) when position opened.

        Returns True if position was closed.
        """
        is_long = position.direction == TradeDirection.LONG

        # Get config values
        activation_pts = self.config.no_loss_activation_pts  # 3.0 pts
        trail_distance = self.config.no_loss_trail_distance  # 2.0 pts

        # OVERNIGHT HYBRID: Use the stored initial_stop distance since it was
        # calculated with correct overnight/RTH params when position was opened.
        # This ensures overnight positions use tighter emergency stop (10 pts)
        # while RTH positions use normal emergency stop (15 pts).
        emergency_stop_pts = abs(position.entry_price - position.initial_stop)

        # Calculate profit in points
        if is_long:
            profit_pts = current_price - position.entry_price
            high_water_price = position.high_price_since_entry
            max_profit_pts = high_water_price - position.entry_price if high_water_price > 0 else profit_pts
        else:
            profit_pts = position.entry_price - current_price
            high_water_price = position.low_price_since_entry  # For shorts, low is best
            max_profit_pts = position.entry_price - high_water_price if high_water_price > 0 else profit_pts

        # ================================================================
        # CHECK PROFIT TARGET (take profits instead of relying only on trail)
        # This ensures we don't let winners turn into losers
        # ================================================================
        profit_target_pts = getattr(self.config, 'no_loss_profit_target_pts', 4.0)  # Default 4 pts

        if profit_pts >= profit_target_pts:
            logger.info(
                f"Position {position.position_id}: PROFIT TARGET HIT at {current_price:.2f} "
                f"(entry={position.entry_price:.2f}, profit={profit_pts:.1f} pts >= {profit_target_pts:.1f} pts target)"
            )
            return self._close_position(
                position,
                current_price,
                PositionStatus.PROFIT_TARGET,
                f"No-loss trailing profit target hit (+{profit_pts:.1f} pts)"
            )

        # ================================================================
        # CHECK MAX UNREALIZED LOSS (intermediate safety net)
        # This triggers BEFORE emergency stop to cap losses at 5pts instead of 15pts
        # ================================================================
        max_loss_pts = self.config.max_unrealized_loss_pts  # 5.0 pts default

        if -profit_pts >= max_loss_pts:
            logger.warning(
                f"Position {position.position_id}: MAX LOSS RULE triggered at {current_price:.2f} "
                f"(entry={position.entry_price:.2f}, loss={-profit_pts:.1f} pts >= {max_loss_pts:.1f} pts limit)"
            )
            return self._close_position(
                position,
                current_price,
                PositionStatus.STOPPED,
                f"Max unrealized loss rule (-{-profit_pts:.1f} pts exceeded {max_loss_pts:.1f} pts limit)"
            )

        # ================================================================
        # CHECK EMERGENCY STOP (catastrophic loss protection - backup to max loss)
        # ================================================================
        emergency_stop_price = (position.entry_price - emergency_stop_pts if is_long
                               else position.entry_price + emergency_stop_pts)

        if is_long and current_price <= emergency_stop_price:
            logger.warning(
                f"Position {position.position_id}: EMERGENCY STOP hit at {current_price:.2f} "
                f"(entry={position.entry_price:.2f}, emergency={emergency_stop_price:.2f})"
            )
            return self._close_position(
                position,
                current_price,
                PositionStatus.STOPPED,
                f"Emergency stop triggered (-{emergency_stop_pts:.1f} pts)"
            )

        if not is_long and current_price >= emergency_stop_price:
            logger.warning(
                f"Position {position.position_id}: EMERGENCY STOP hit at {current_price:.2f} "
                f"(entry={position.entry_price:.2f}, emergency={emergency_stop_price:.2f})"
            )
            return self._close_position(
                position,
                current_price,
                PositionStatus.STOPPED,
                f"Emergency stop triggered (-{emergency_stop_pts:.1f} pts)"
            )

        # ================================================================
        # CHECK TRAILING STOP (if active)
        # ================================================================
        if position.trailing_active and position.current_stop > 0:
            if is_long and current_price <= position.current_stop:
                exit_pnl_pts = position.current_stop - position.entry_price
                logger.info(
                    f"Position {position.position_id}: TRAIL STOP hit at {position.current_stop:.2f} "
                    f"(locked in +{exit_pnl_pts:.1f} pts profit)"
                )
                return self._close_position(
                    position,
                    position.current_stop,  # Use stop price for P&L calc
                    PositionStatus.TRAILED,
                    f"No-loss trailing stop hit (+{exit_pnl_pts:.1f} pts)"
                )

            if not is_long and current_price >= position.current_stop:
                exit_pnl_pts = position.entry_price - position.current_stop
                logger.info(
                    f"Position {position.position_id}: TRAIL STOP hit at {position.current_stop:.2f} "
                    f"(locked in +{exit_pnl_pts:.1f} pts profit)"
                )
                return self._close_position(
                    position,
                    position.current_stop,
                    PositionStatus.TRAILED,
                    f"No-loss trailing stop hit (+{exit_pnl_pts:.1f} pts)"
                )

        # ================================================================
        # ACTIVATE TRAILING (once profitable enough)
        # ================================================================
        if not position.trailing_active and max_profit_pts >= activation_pts:
            # Set trailing stop at breakeven initially
            position.trailing_active = True
            position.current_stop = position.entry_price
            self.db.update_stop(position.position_id, position.entry_price, trailing_active=True)
            logger.info(
                f"Position {position.position_id}: NO-LOSS TRAIL ACTIVATED at +{max_profit_pts:.1f} pts | "
                f"Stop set to breakeven ({position.entry_price:.2f})"
            )

        # ================================================================
        # UPDATE TRAILING STOP (ratchet up as price improves)
        # ================================================================
        if position.trailing_active:
            if is_long:
                # Trail below high water mark
                new_stop = high_water_price - trail_distance
                if new_stop > position.current_stop and new_stop > position.entry_price:
                    position.current_stop = new_stop
                    self.db.update_stop(position.position_id, new_stop, trailing_active=True)
                    locked_profit = new_stop - position.entry_price
                    logger.info(
                        f"Position {position.position_id}: Trail raised to {new_stop:.2f} "
                        f"(locking +{locked_profit:.1f} pts, high water={high_water_price:.2f})"
                    )
            else:
                # Trail above low water mark (for shorts)
                new_stop = high_water_price + trail_distance
                if new_stop < position.current_stop and new_stop < position.entry_price:
                    position.current_stop = new_stop
                    self.db.update_stop(position.position_id, new_stop, trailing_active=True)
                    locked_profit = position.entry_price - new_stop
                    logger.info(
                        f"Position {position.position_id}: Trail lowered to {new_stop:.2f} "
                        f"(locking +{locked_profit:.1f} pts, low water={high_water_price:.2f})"
                    )

        # Update P&L tracking
        pnl = position.calculate_pnl(current_price)
        if pnl > position.high_water_mark:
            position.high_water_mark = pnl
        if pnl < 0 and abs(pnl) > position.max_adverse_excursion:
            position.max_adverse_excursion = abs(pnl)

        return False

    def _update_position_high_low(self, position: FuturesPosition, current_price: float) -> None:
        """
        Update high/low price tracking for a position.

        This is critical for backtesting to know the full price range
        experienced during the trade, enabling validation of:
        - Stop loss placement and whether it was truly hit
        - Profit target placement and whether it could have been reached
        - Maximum Adverse Excursion (MAE) analysis
        - Maximum Favorable Excursion (MFE) analysis

        Called on every scan to capture continuous price range.
        """
        try:
            # Update in-memory position values
            if position.high_price_since_entry == 0 or current_price > position.high_price_since_entry:
                position.high_price_since_entry = current_price

            if position.low_price_since_entry == 0 or current_price < position.low_price_since_entry:
                position.low_price_since_entry = current_price

            # Persist to database
            self.db.update_high_low_prices(
                position.position_id,
                high_price=current_price,
                low_price=current_price
            )

        except Exception as e:
            logger.warning(f"Error updating high/low prices for {position.position_id}: {e}")

    def _check_stop_hit(self, position: FuturesPosition, current_price: float) -> bool:
        """Check if position's stop has been hit"""
        if position.direction == TradeDirection.LONG:
            return current_price <= position.current_stop
        else:
            return current_price >= position.current_stop

    def _check_profit_target_hit(self, position: FuturesPosition, current_price: float) -> bool:
        """
        Check if position's profit target has been hit.

        Uses config.profit_target_points (default 6.0 points = $30/contract).
        Uses >= comparison to catch price gaps past target.

        Direction-aware:
        - LONG: target hit when current_price >= entry_price + target_points
        - SHORT: target hit when current_price <= entry_price - target_points
        """
        # Guard against missing entry price
        if not position.entry_price or position.entry_price <= 0:
            logger.warning(f"Position {position.position_id}: Invalid entry_price for profit target check")
            return False

        # Get profit target from config
        profit_target_points = self.config.profit_target_points

        if position.direction == TradeDirection.LONG:
            target_price = position.entry_price + profit_target_points
            return current_price >= target_price
        else:  # SHORT
            target_price = position.entry_price - profit_target_points
            return current_price <= target_price

    def _close_position(
        self,
        position: FuturesPosition,
        close_price: float,
        status: PositionStatus,
        reason: str
    ) -> bool:
        """Close a position"""
        try:
            # Execute close order
            success, message, fill_price = self.executor.close_position_order(position, reason)

            if success:
                # Use fill price if available, otherwise use provided close_price
                actual_close_price = fill_price if fill_price > 0 else close_price

                # Update database
                closed, realized_pnl = self.db.close_position(
                    position.position_id,
                    actual_close_price,
                    reason,
                    status
                )

                if closed:
                    # Update win tracker
                    won = realized_pnl > 0
                    self.win_tracker.update(won, position.gamma_regime)
                    self.db.save_win_tracker(self.win_tracker)

                    # Update direction tracker (for nimble direction switching)
                    from .signals import record_trade_outcome, get_direction_tracker
                    direction_tracker = get_direction_tracker()
                    record_trade_outcome(
                        direction=position.direction.value,
                        is_win=won,
                        scan_number=direction_tracker.current_scan
                    )
                    logger.info(
                        f"Direction tracker updated: {position.direction.value} {'WIN' if won else 'LOSS'}, "
                        f"status={direction_tracker.get_status()}"
                    )

                    # Record outcome to Oracle ML for feedback loop
                    self._record_oracle_outcome(position, reason, realized_pnl)

                    # Record outcome to Solomon Enhanced for feedback loops
                    trade_date = datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")
                    outcome_type = self._determine_outcome_type(reason, realized_pnl)
                    self._record_solomon_outcome(realized_pnl, trade_date, outcome_type)

                    # Record outcome to Thompson Sampling for capital allocation
                    self._record_thompson_outcome(realized_pnl)

                    # Update paper trading balance if in paper mode
                    if self.config.mode == TradingMode.PAPER:
                        # Calculate margin released (approximate MES margin per contract)
                        margin_per_contract = 1500.0  # Approx MES margin requirement
                        margin_released = -position.contracts * margin_per_contract
                        success, updated_account = self.db.update_paper_balance(
                            realized_pnl=realized_pnl,
                            margin_change=margin_released
                        )
                        if success:
                            logger.info(
                                f"Paper balance updated: ${updated_account['current_balance']:,.2f} "
                                f"(P&L: ${realized_pnl:+.2f}, Return: {updated_account['return_pct']:.2f}%)"
                            )

                    # Update daily stats
                    self.daily_pnl += realized_pnl
                    self.daily_trades += 1

                    # Log
                    self.db.log(
                        level="INFO",
                        action="CLOSE_POSITION",
                        message=f"Closed {position.direction.value} at {actual_close_price:.2f}",
                        details={
                            "position_id": position.position_id,
                            "realized_pnl": realized_pnl,
                            "reason": reason,
                            "status": status.value
                        }
                    )

                    logger.info(
                        f"Position {position.position_id} closed: "
                        f"P&L=${realized_pnl:.2f}, reason={reason}"
                    )
                    return True

            logger.error(f"Failed to close position {position.position_id}: {message}")
            return False

        except Exception as e:
            logger.error(f"Error closing position {position.position_id}: {e}")
            return False

    # ========================================================================
    # Signal Execution
    # ========================================================================

    def _execute_signal(self, signal: FuturesSignal, account_balance: float) -> bool:
        """Execute a trading signal (wrapper for backward compatibility)"""
        position_id = f"HERACLES-{uuid.uuid4().hex[:8]}"
        return self._execute_signal_internal(signal, account_balance, position_id)

    def _execute_signal_internal(self, signal: FuturesSignal, account_balance: float, position_id: str, scan_id: str = "") -> bool:
        """Execute a trading signal with specified position_id and scan_id for ML tracking"""
        try:
            # Validate order parameters
            valid, validation_msg = self.executor.validate_order_params(signal, account_balance)
            if not valid:
                logger.warning(f"Order validation failed: {validation_msg}")
                return False

            # Execute order
            success, message, order_id = self.executor.execute_signal(signal, position_id)

            if not success:
                logger.error(f"Order execution failed: {message}")
                return False

            # Create position object
            position = FuturesPosition(
                position_id=position_id,
                symbol=self.config.symbol,
                direction=signal.direction,
                contracts=signal.contracts,
                entry_price=signal.entry_price,
                entry_value=signal.entry_price * signal.contracts * MES_POINT_VALUE,
                initial_stop=signal.stop_price,
                current_stop=signal.stop_price,
                breakeven_price=signal.entry_price,
                trailing_active=False,
                gamma_regime=signal.gamma_regime,
                gex_value=signal.gex_value,
                flip_point=signal.flip_point,
                call_wall=signal.call_wall,
                put_wall=signal.put_wall,
                vix_at_entry=signal.vix,
                atr_at_entry=signal.atr,
                signal_source=signal.source,
                signal_confidence=signal.confidence,
                win_probability=signal.win_probability,
                trade_reasoning=signal.reasoning,
                order_id=order_id or "",
                scan_id=scan_id,  # Link to scan activity for ML training
                status=PositionStatus.OPEN,
                open_time=datetime.now(CENTRAL_TZ),
                # A/B Test tracking - copy from signal
                stop_type=signal.stop_type,
                stop_points_used=signal.stop_points_used
            )

            # Save to database
            self.db.save_position(position)

            # Update paper trading margin if in paper mode
            if self.config.mode == TradingMode.PAPER:
                # Calculate margin required (approximate MES margin per contract)
                margin_per_contract = 1500.0  # Approx MES margin requirement
                margin_required = signal.contracts * margin_per_contract
                success, updated_account = self.db.update_paper_balance(
                    realized_pnl=0,  # No P&L yet, just margin allocation
                    margin_change=margin_required
                )
                if success:
                    logger.info(
                        f"Paper margin allocated: ${margin_required:,.2f} for {signal.contracts} contracts "
                        f"(Available: ${updated_account['margin_available']:,.2f})"
                    )

            # Log
            self.db.log(
                level="INFO",
                action="OPEN_POSITION",
                message=f"Opened {signal.direction.value} {signal.contracts} contracts at {signal.entry_price:.2f}",
                details={
                    "position_id": position_id,
                    "signal_source": signal.source.value,
                    "gamma_regime": signal.gamma_regime.value,
                    "win_probability": signal.win_probability,
                    "stop_price": signal.stop_price,
                    "reasoning": signal.reasoning
                }
            )

            logger.info(
                f"Opened position {position_id}: {signal.direction.value} "
                f"{signal.contracts} @ {signal.entry_price:.2f}, "
                f"stop={signal.stop_price:.2f}, win_prob={signal.win_probability:.2%}"
            )

            return True

        except Exception as e:
            logger.error(f"Error executing signal: {e}")
            return False

    # ========================================================================
    # Utility Methods
    # ========================================================================

    def _is_overnight_session(self) -> bool:
        """Check if current time is overnight session (5 PM - 8 AM CT)"""
        now = datetime.now(CENTRAL_TZ)
        hour = now.hour

        # Overnight: 5 PM (17:00) to 8 AM (08:00)
        return hour >= 17 or hour < 8

    def _get_vix(self) -> float:
        """
        Get current VIX level from Tradier production API.

        VIX is critical for position sizing and signal confidence:
        - Low VIX (<15): Smaller moves, can trade more contracts
        - Normal VIX (15-22): Standard positioning
        - High VIX (>25): Wider stops, smaller size
        """
        try:
            from data.tradier_data_fetcher import TradierDataFetcher

            # Use production keys for VIX
            tradier = TradierDataFetcher(sandbox=False)
            quote = tradier.get_quote("VIX")

            if quote and hasattr(quote, 'price') and quote.price > 0:
                logger.debug(f"VIX from Tradier: {quote.price:.2f}")
                return float(quote.price)

            # Try getting from quote dict format
            if isinstance(quote, dict) and quote.get('last', 0) > 0:
                return float(quote['last'])

        except Exception as e:
            logger.warning(f"Could not get VIX from Tradier: {e}")

        # Fallback: Try Yahoo Finance
        try:
            import requests
            response = requests.get(
                "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX",
                params={"interval": "1m", "range": "1d"},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                result = data.get("chart", {}).get("result", [])
                if result:
                    price = result[0].get("meta", {}).get("regularMarketPrice", 0)
                    if price > 0:
                        logger.debug(f"VIX from Yahoo: {price:.2f}")
                        return float(price)
        except Exception as e:
            logger.warning(f"Could not get VIX from Yahoo: {e}")

        # Default VIX if all sources fail
        logger.warning("Using default VIX=16.0 (all sources failed)")
        return 16.0

    def _get_atr(self, current_price: float, period: int = 14) -> Tuple[float, bool]:
        """
        Get ATR (Average True Range) for MES position sizing.

        ATR is used for:
        - Stop loss placement
        - Position sizing (risk per trade / ATR = contracts)
        - Signal strength evaluation

        Returns:
            Tuple[float, bool]: (ATR value, is_estimated flag)
                - is_estimated=False means ATR was calculated from real historical data
                - is_estimated=True means ATR was estimated (fallback)
        """
        try:
            # Try to get historical data for real ATR calculation
            from data.unified_data_provider import get_historical_bars

            # Get 20 days of daily bars for ATR calculation
            bars = get_historical_bars("SPY", days=20, interval="day")

            if bars and len(bars) >= period:
                # Calculate True Range for each bar
                true_ranges = []
                for i in range(1, len(bars)):
                    high = bars[i].high * 10  # Scale to MES level
                    low = bars[i].low * 10
                    prev_close = bars[i-1].close * 10

                    tr = max(
                        high - low,
                        abs(high - prev_close),
                        abs(low - prev_close)
                    )
                    true_ranges.append(tr)

                # Calculate ATR as simple moving average of TR
                if len(true_ranges) >= period:
                    atr = sum(true_ranges[-period:]) / period
                    logger.debug(f"Calculated ATR from SPY data: {atr:.2f} (not estimated)")
                    return (atr, False)  # Real ATR, not estimated

        except Exception as e:
            logger.warning(f"Could not calculate real ATR: {e}")

        # Fallback: Estimate based on current price and VIX
        estimated_atr = self._estimate_atr(current_price)
        logger.debug(f"Using estimated ATR: {estimated_atr:.2f}")
        return (estimated_atr, True)  # Estimated ATR

    def _estimate_atr(self, current_price: float) -> float:
        """
        Estimate ATR when historical data unavailable.

        MES typically has ATR of 15-30 points depending on volatility.
        """
        # MES typically moves ~0.3-0.5% per day
        # ATR is roughly 15-25 points on average
        base_atr = current_price * 0.003

        # Typical range for MES
        return max(10.0, min(30.0, base_atr))

    def _save_equity_snapshot(
        self,
        account_balance: float,
        positions: List[FuturesPosition]
    ) -> None:
        """Save equity snapshot for equity curve"""
        try:
            # Get current quote for unrealized P&L
            quote = self.executor.get_mes_quote()
            current_price = quote.get("last", 0) if quote else 0

            unrealized_pnl = 0.0
            for position in positions:
                if position.is_open and current_price > 0:
                    unrealized_pnl += position.calculate_pnl(current_price)

            # Get today's stats
            summary = self.db.get_daily_summary()

            self.db.save_equity_snapshot(
                account_balance=account_balance,
                unrealized_pnl=unrealized_pnl,
                realized_pnl_today=summary.realized_pnl,
                open_positions=len([p for p in positions if p.is_open]),
                trades_today=summary.positions_closed,
                wins_today=0,  # Would track separately
                losses_today=0
            )

        except Exception as e:
            logger.warning(f"Error saving equity snapshot: {e}")

    # ========================================================================
    # ML Feedback Loop Integration
    # ========================================================================

    def _record_oracle_outcome(self, pos: FuturesPosition, close_reason: str, pnl: float):
        """
        Record trade outcome to Oracle for ML feedback loop.

        This enables Oracle to learn from HERACLES futures trades and
        improve future predictions.
        """
        if not ORACLE_AVAILABLE:
            return

        try:
            oracle = OracleAdvisor()

            # Determine outcome type based on close reason and P&L
            if pnl > 0:
                if 'PROFIT' in close_reason.upper() or 'TARGET' in close_reason.upper():
                    outcome = OracleTradeOutcome.MAX_PROFIT
                else:
                    outcome = OracleTradeOutcome.PARTIAL_PROFIT
            else:
                if 'STOP' in close_reason.upper():
                    outcome = OracleTradeOutcome.LOSS
                else:
                    outcome = OracleTradeOutcome.LOSS

            # Get trade date
            trade_date = datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")

            # Record to Oracle - use HERACLES bot name (might need to add to Oracle enum)
            # For now, log to info - Oracle integration for futures bot pending
            logger.info(
                f"HERACLES: Recording outcome to Oracle - {outcome.value if hasattr(outcome, 'value') else outcome}, "
                f"P&L=${pnl:.2f}, Regime={pos.gamma_regime.value}"
            )

            # Future: Call oracle.update_outcome() when BotName.HERACLES is added

        except Exception as e:
            logger.warning(f"HERACLES: Oracle outcome recording failed: {e}")

    def _record_solomon_outcome(
        self,
        pnl: float,
        trade_date: str,
        outcome_type: str = None
    ):
        """
        Record trade outcome to Solomon Enhanced for feedback loop tracking.

        This updates:
        - Consecutive loss tracking
        - Daily P&L monitoring
        - Performance tracking for version comparison
        """
        if not SOLOMON_ENHANCED_AVAILABLE or not get_solomon_enhanced:
            return

        try:
            enhanced = get_solomon_enhanced()
            alerts = enhanced.record_trade_outcome(
                bot_name='HERACLES',
                pnl=pnl,
                trade_date=trade_date,
                capital_base=self.config.capital,
                outcome_type=outcome_type,
                strategy_type='FUTURES_SCALPING'
            )

            if alerts:
                for alert in alerts:
                    logger.warning(f"HERACLES Solomon Alert: {alert}")

            logger.debug(f"HERACLES: Recorded outcome to Solomon Enhanced - P&L=${pnl:.2f}")

        except Exception as e:
            logger.warning(f"HERACLES: Solomon outcome recording failed: {e}")

    def _record_thompson_outcome(self, pnl: float):
        """
        Record trade outcome to Thompson Sampling for capital allocation.

        This updates the Beta distribution parameters for HERACLES,
        which affects future capital allocation across bots.
        """
        if not AUTO_VALIDATION_AVAILABLE or not record_bot_outcome:
            return

        try:
            record_bot_outcome('HERACLES', win=(pnl > 0), pnl=pnl)
            logger.debug(f"HERACLES: Recorded outcome to Thompson Sampling - P&L=${pnl:.2f}")
        except Exception as e:
            logger.warning(f"HERACLES: Thompson outcome recording failed: {e}")

    def _determine_outcome_type(self, close_reason: str, pnl: float) -> str:
        """
        Determine outcome type from close reason and P&L.

        Returns:
            str: Outcome type (PROFIT_TARGET, STOP_LOSS, TRAILING_STOP, EXPIRED, etc.)
        """
        close_reason_upper = close_reason.upper()
        if pnl > 0:
            if 'TARGET' in close_reason_upper or 'PROFIT' in close_reason_upper:
                return 'PROFIT_TARGET'
            elif 'TRAIL' in close_reason_upper:
                return 'TRAILING_STOP_PROFIT'
            else:
                return 'PARTIAL_PROFIT'
        else:
            if 'STOP' in close_reason_upper:
                return 'STOP_LOSS'
            elif 'EXPIRE' in close_reason_upper:
                return 'EXPIRED_LOSS'
            else:
                return 'LOSS'

    def process_expired_positions(self) -> Dict[str, Any]:
        """
        Process positions that need to be closed at EOD.

        For futures, this handles positions that should be closed during
        the daily maintenance break (4-5pm CT).

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
            # Get current quote for marking to market
            quote = self.executor.get_mes_quote()
            current_price = quote.get("last", 0) if quote else 0

            if current_price <= 0:
                logger.warning("HERACLES EOD: Could not get current price for expiration processing")
                result['errors'].append("No price available")
                return result

            # Get all open positions
            positions = self.db.get_open_positions()

            if not positions:
                logger.info("HERACLES EOD: No open positions to process")
                return result

            logger.info(f"HERACLES EOD: Processing {len(positions)} open position(s) at price {current_price:.2f}")

            for pos in positions:
                try:
                    # Close position at current market price
                    closed = self._close_position(
                        pos,
                        current_price,
                        PositionStatus.CLOSED,
                        "EOD_MAINTENANCE_BREAK"
                    )

                    if closed:
                        # Calculate P&L
                        pnl = pos.calculate_pnl(current_price)
                        result['processed_count'] += 1
                        result['total_pnl'] += pnl
                        result['positions'].append({
                            'position_id': pos.position_id,
                            'direction': pos.direction.value,
                            'pnl': pnl,
                            'status': 'closed'
                        })

                        logger.info(
                            f"HERACLES EOD: Closed {pos.position_id} - "
                            f"Final price: ${current_price:.2f}, P&L: ${pnl:.2f}"
                        )

                except Exception as e:
                    logger.error(f"HERACLES EOD: Failed to process {pos.position_id}: {e}")
                    result['errors'].append(str(e))

            self.db.log("INFO", "EOD_PROCESSING",
                f"Processed {result['processed_count']} positions, P&L: ${result['total_pnl']:.2f}")

        except Exception as e:
            logger.error(f"HERACLES EOD processing failed: {e}")
            result['errors'].append(str(e))

        return result

    def force_close_all(self, reason: str = "MANUAL_CLOSE") -> Dict[str, Any]:
        """Force close all open positions"""
        positions = self.db.get_open_positions()
        results = []
        total_pnl = 0.0

        # Get current price
        quote = self.executor.get_mes_quote()
        current_price = quote.get("last", 0) if quote else 0

        if current_price <= 0:
            return {'error': 'Could not get current price', 'closed': 0, 'failed': len(positions)}

        for pos in positions:
            closed = self._close_position(pos, current_price, PositionStatus.CLOSED, reason)
            pnl = pos.calculate_pnl(current_price) if closed else 0

            if closed:
                total_pnl += pnl

            results.append({
                'position_id': pos.position_id,
                'success': closed,
                'pnl': pnl
            })

        return {
            'closed': len([r for r in results if r['success']]),
            'failed': len([r for r in results if not r['success']]),
            'total_pnl': total_pnl,
            'details': results
        }

    # ========================================================================
    # Status & Reporting
    # ========================================================================

    def get_status(self) -> Dict[str, Any]:
        """Get current bot status"""
        positions = self.db.get_open_positions()
        config = self.config
        stats = self.db.get_performance_stats()
        summary = self.db.get_daily_summary()

        # Get paper account info if in paper mode
        paper_account = None
        if config.mode == TradingMode.PAPER:
            paper_account = self.db.get_paper_account()

        status_dict = {
            "bot_name": "HERACLES",
            "status": "active" if self.executor.is_market_open() else "market_closed",
            "mode": config.mode.value,
            "symbol": config.symbol,
            "timestamp": datetime.now(CENTRAL_TZ).isoformat(),
            "config": {
                "capital": config.capital,
                "risk_per_trade_pct": config.risk_per_trade_pct,
                "max_contracts": config.max_contracts,
                "max_open_positions": config.max_open_positions,
                "initial_stop_points": config.initial_stop_points,
                "breakeven_activation_points": config.breakeven_activation_points,
                "trailing_stop_points": config.trailing_stop_points,
                "profit_target_points": config.profit_target_points,
                # No-Loss Trailing Strategy params
                "use_no_loss_trailing": config.use_no_loss_trailing,
                "no_loss_activation_pts": config.no_loss_activation_pts,
                "no_loss_trail_distance": config.no_loss_trail_distance,
                "no_loss_emergency_stop": config.no_loss_emergency_stop,
                "max_unrealized_loss_pts": config.max_unrealized_loss_pts,
            },
            "positions": {
                "open_count": len(positions),
                "positions": [p.to_dict() for p in positions]
            },
            "performance": stats,
            "today": summary.to_dict(),
            "win_tracker": self.win_tracker.to_dict(),
            "last_scan": self.last_scan_time.isoformat() if self.last_scan_time else None,
            "market_open": self.executor.is_market_open()
        }

        # Add paper account info if available
        if paper_account:
            starting_cap = paper_account.get('starting_capital', 100000) or 100000  # Ensure non-zero
            cumulative_pnl = paper_account.get('cumulative_pnl', 0)
            status_dict["paper_account"] = {
                "starting_capital": paper_account.get('starting_capital', 0),
                "current_balance": paper_account.get('current_balance', 0),
                "cumulative_pnl": cumulative_pnl,
                "total_trades": paper_account.get('total_trades', 0),
                "margin_used": paper_account.get('margin_used', 0),
                "margin_available": paper_account.get('margin_available', 0),
                "high_water_mark": paper_account.get('high_water_mark', 0),
                "max_drawdown": paper_account.get('max_drawdown', 0),
                # BUG FIX: Protect against division by zero
                "return_pct": (cumulative_pnl / starting_cap) * 100 if starting_cap > 0 else 0.0
            }

        return status_dict

    def get_equity_curve(self, days: int = 30) -> List[Dict]:
        """Get equity curve data"""
        # Use paper equity curve for paper mode (calculates from trades)
        if self.config.mode == TradingMode.PAPER:
            return self.db.get_paper_equity_curve(days)
        return self.db.get_equity_curve(days)

    def get_paper_account(self) -> Optional[Dict]:
        """Get paper trading account status"""
        return self.db.get_paper_account()

    def reset_paper_account(self, starting_capital: float = 100000.0) -> bool:
        """Reset paper trading account with new starting capital"""
        return self.db.reset_paper_account(starting_capital)

    def get_intraday_equity(self) -> List[Dict]:
        """Get today's equity curve"""
        return self.db.get_intraday_equity()

    def get_closed_trades(self, limit: int = 50) -> List[Dict]:
        """Get recent closed trades"""
        return self.db.get_closed_trades(limit=limit)

    def get_recent_signals(self, limit: int = 50) -> List[Dict]:
        """Get recent signals"""
        return self.db.get_recent_signals(limit)

    def get_logs(self, limit: int = 100) -> List[Dict]:
        """Get recent logs"""
        return self.db.get_logs(limit)


# ============================================================================
# Singleton instance for scheduler
# ============================================================================

_trader_instance: Optional[HERACLESTrader] = None


def get_heracles_trader() -> HERACLESTrader:
    """Get or create HERACLES trader instance"""
    global _trader_instance
    if _trader_instance is None:
        _trader_instance = HERACLESTrader()
    return _trader_instance


def run_heracles_scan() -> Dict[str, Any]:
    """
    Entry point for scheduler.

    Called periodically to run HERACLES trading logic.
    """
    trader = get_heracles_trader()
    return trader.run_scan()
