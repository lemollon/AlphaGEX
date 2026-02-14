"""
AGAPE Trader - Main orchestrator for ETH Micro Futures trading.

AGGRESSIVE MODE (matching VALOR/Valor):
  - No-loss trailing: Let winners run, only trail after profitable
  - Stop-and-Reverse (SAR): Reverse losing positions to capture momentum
  - Direction Tracker: Nimble reversal detection, cooldown after losses
  - Loss streak protection: Pause after consecutive losses
  - Low barriers to entry: No Prophet blocking, low confidence threshold

Runs on a 5-minute cycle (configurable), trading /MET contracts
via tastytrade based on crypto market microstructure signals.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from zoneinfo import ZoneInfo

from trading.agape.models import (
    AgapeConfig,
    AgapeSignal,
    AgapePosition,
    PositionSide,
    PositionStatus,
    SignalAction,
    TradingMode,
)
from trading.agape.db import AgapeDatabase
from trading.agape.signals import (
    AgapeSignalGenerator,
    get_agape_direction_tracker,
    record_agape_trade_outcome,
)
from trading.agape.executor import AgapeExecutor

logger = logging.getLogger(__name__)

# Bayesian Crypto Tracker for choppy-market edge feedback
_bayesian_tracker_mod = None
try:
    from quant.bayesian_crypto_tracker import (
        TradeOutcome as BayesianTradeOutcome,
        get_tracker as get_bayesian_tracker,
    )
    _bayesian_tracker_mod = True
    logger.info("AGAPE Trader: BayesianCryptoTracker loaded")
except ImportError:
    pass

_bayesian_db_mod = None
try:
    from quant.bayesian_crypto_db import BayesianCryptoDatabase
    _bayesian_db_mod = True
except ImportError:
    pass

CENTRAL_TZ = ZoneInfo("America/Chicago")

# Singleton instance
_agape_trader: Optional["AgapeTrader"] = None


def get_agape_trader() -> Optional["AgapeTrader"]:
    """Get the global AGAPE trader instance."""
    return _agape_trader


def create_agape_trader(config: Optional[AgapeConfig] = None) -> "AgapeTrader":
    """Create and register the global AGAPE trader instance."""
    global _agape_trader
    _agape_trader = AgapeTrader(config)
    return _agape_trader


class AgapeTrader:
    """Main AGAPE trading bot orchestrator.

    AGGRESSIVE MODE - Matches VALOR/Valor aggressiveness:
    - No-loss trailing strategy (let winners run)
    - SAR (Stop-and-Reverse) for losing positions
    - Direction tracker for nimble reversal detection
    - Loss streak protection (pause after 3 consecutive losses)
    - 20 max open positions (was 2)
    - 5 min cooldown (was 30)
    - Prophet advisory only (was blocking)
    """

    def __init__(self, config: Optional[AgapeConfig] = None):
        self.db = AgapeDatabase()

        if config:
            self.config = config
        else:
            self.config = AgapeConfig.load_from_db(self.db)

        self.signals = AgapeSignalGenerator(self.config)

        # AGAPE uses tastytrade CME /MET executor
        # For 24/7 Coinbase spot, use AGAPE-SPOT bot instead
        self.executor = AgapeExecutor(self.config, self.db)
        exchange_label = "tastytrade CME /MET"

        self._last_scan_time: Optional[datetime] = None
        self._cycle_count: int = 0
        self._enabled: bool = True

        # Loss streak tracking (from VALOR)
        self.consecutive_losses: int = 0
        self.loss_streak_pause_until: Optional[datetime] = None

        # Direction tracker (from VALOR)
        self._direction_tracker = get_agape_direction_tracker(self.config)

        self.db.log("INFO", "INIT", f"AGAPE trader initialized AGGRESSIVE (mode={self.config.mode.value}, exchange={exchange_label})")
        logger.info(
            f"AGAPE Trader: Initialized AGGRESSIVE (mode={self.config.mode.value}, "
            f"exchange={exchange_label}, "
            f"max_pos={self.config.max_open_positions}, cooldown={self.config.cooldown_minutes}m, "
            f"oracle_required={self.config.require_oracle_approval}, "
            f"no_loss_trailing={self.config.use_no_loss_trailing}, "
            f"sar={self.config.use_sar})"
        )

    def run_cycle(self, close_only: bool = False) -> Dict[str, Any]:
        """Execute one trading cycle.

        This is called by the scheduler every 5 minutes.
        Returns a dict with the cycle result for monitoring.
        """
        self._cycle_count += 1
        now = datetime.now(CENTRAL_TZ)

        # Update direction tracker scan count
        self._direction_tracker.update_scan(self._cycle_count)

        result = {
            "cycle": self._cycle_count,
            "timestamp": now.isoformat(),
            "outcome": "UNKNOWN",
            "positions_managed": 0,
            "positions_closed": 0,
            "new_trade": False,
            "signal": None,
            "error": None,
        }

        scan_context: Dict[str, Any] = {}

        try:
            # Step 1: Fetch market data early (for both management and entry)
            market_data = self.signals.get_market_data()
            if market_data:
                scan_context["market_data"] = market_data
                scan_context["eth_price"] = market_data.get("spot_price")

            # Step 2: Get Prophet advice early (avoid double-fetching)
            prophet_data = None
            if market_data:
                prophet_data = self.signals.get_prophet_advice(market_data)
                scan_context["prophet_data"] = prophet_data

            # Step 3: Manage existing positions FIRST (includes no-loss trailing + SAR)
            managed, closed = self._manage_positions(market_data)
            result["positions_managed"] = managed
            result["positions_closed"] = closed

            # Save equity snapshot EVERY cycle (not just after trades)
            # This ensures intraday curve always has data
            self._save_equity_snapshot(market_data)

            # If close_only mode, stop here
            if close_only:
                result["outcome"] = "CLOSE_ONLY"
                self._log_scan(result, scan_context)
                return result

            # Step 4: Check loss streak pause
            if self.loss_streak_pause_until:
                if now < self.loss_streak_pause_until:
                    remaining = (self.loss_streak_pause_until - now).total_seconds() / 60
                    result["outcome"] = f"LOSS_STREAK_PAUSE_{remaining:.1f}min"
                    self._log_scan(result, scan_context)
                    return result
                else:
                    logger.info(f"AGAPE: Loss streak pause expired (was {self.consecutive_losses} losses)")
                    self.loss_streak_pause_until = None

            # Step 5: Check basic entry conditions
            skip_reason = self._check_entry_conditions(now)
            if skip_reason:
                result["outcome"] = skip_reason
                self._log_scan(result, scan_context)
                return result

            # Step 6: Generate signal with pre-fetched Prophet data
            signal = self.signals.generate_signal(prophet_data=prophet_data)
            result["signal"] = signal.to_dict() if signal else None

            if not signal or not signal.is_valid:
                result["outcome"] = f"NO_SIGNAL_{signal.reasoning if signal else 'NONE'}"
                self._log_scan(result, scan_context, signal=signal)
                return result

            # Step 7: Execute the trade
            position = self.executor.execute_trade(signal)
            if position:
                self.db.save_position(position)
                result["new_trade"] = True
                result["outcome"] = f"TRADED_{signal.side.upper()}"
                result["position_id"] = position.position_id
                scan_context["position_id"] = position.position_id

                self.db.log(
                    "INFO", "NEW_TRADE",
                    f"{signal.side.upper()} {signal.contracts}x /MET @ ${position.entry_price:.2f}",
                    details=signal.to_dict(),
                )
            else:
                result["outcome"] = "EXECUTION_FAILED"

            self._log_scan(result, scan_context, signal=signal)
            return result

        except Exception as e:
            logger.error(f"AGAPE Trader: Cycle failed: {e}", exc_info=True)
            result["outcome"] = "ERROR"
            result["error"] = str(e)
            self.db.log("ERROR", "CYCLE_ERROR", str(e))
            self._log_scan(result, scan_context)
            return result

    # ==================================================================
    # Position Management (with No-Loss Trailing + SAR)
    # ==================================================================

    def _manage_positions(self, market_data: Optional[Dict]) -> tuple:
        """Check and manage all open positions.

        Includes:
        - No-loss trailing strategy (let winners run)
        - SAR (Stop-and-Reverse) for losing positions
        - Max hold time enforcement
        - Emergency stop for catastrophic moves

        Returns (positions_checked, positions_closed).
        """
        open_positions = self.db.get_open_positions()
        if not open_positions:
            return (0, 0)

        current_price = self.executor.get_current_price()
        if not current_price and market_data:
            current_price = market_data.get("spot_price")
        if not current_price:
            return (len(open_positions), 0)

        closed = 0
        now = datetime.now(CENTRAL_TZ)

        for pos_dict in open_positions:
            try:
                if self.config.use_no_loss_trailing:
                    did_close = self._manage_position_no_loss_trailing(
                        pos_dict, current_price, now
                    )
                else:
                    should_close, reason = self._check_exit_conditions(
                        pos_dict, current_price, now
                    )
                    did_close = False
                    if should_close:
                        did_close = self._close_position(pos_dict, current_price, reason)

                if did_close:
                    closed += 1
                else:
                    # Update high water mark for trailing stop
                    self._update_hwm(pos_dict, current_price)
            except Exception as e:
                logger.error(f"AGAPE Trader: Position management error: {e}")

        return (len(open_positions), closed)

    def _manage_position_no_loss_trailing(
        self, pos: Dict, current_price: float, now: datetime
    ) -> bool:
        """No-loss trailing position management (ported from VALOR).

        Strategy:
        1. Check SAR conditions first (reverse clearly wrong trades)
        2. Check max unrealized loss (safety net)
        3. Check emergency stop (catastrophic protection)
        4. Check trailing stop (if activated)
        5. Activate trailing once profitable enough
        6. Update trailing stop as price improves
        7. Check max hold time

        Returns True if position was closed.
        """
        entry_price = pos["entry_price"]
        side = pos["side"]
        contracts = pos.get("contracts", 1)
        is_long = side == "long"

        # Calculate profit as percentage
        if is_long:
            profit_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            profit_pct = ((entry_price - current_price) / entry_price) * 100

        # Track high water mark for MFE
        # Guard: HWM of 0 or None means DB default wasn't updated yet - use entry_price
        hwm = pos.get("high_water_mark") or entry_price
        if hwm <= 0:
            hwm = entry_price
        if is_long:
            max_profit_pct = ((hwm - entry_price) / entry_price) * 100 if hwm > entry_price else 0
        else:
            max_profit_pct = ((entry_price - hwm) / entry_price) * 100 if hwm < entry_price else 0

        # ================================================================
        # 1. STOP-AND-REVERSE (SAR) - Reverse clearly wrong trades
        # ================================================================
        if self.config.use_sar:
            sar_trigger = self.config.sar_trigger_pct
            sar_mfe = self.config.sar_mfe_threshold_pct

            if -profit_pct >= sar_trigger and max_profit_pct < sar_mfe:
                logger.info(
                    f"AGAPE SAR: {pos['position_id']} down {-profit_pct:.1f}% "
                    f"(MFE={max_profit_pct:.2f}%) -> Reversing"
                )
                return self._execute_sar(pos, current_price)

        # ================================================================
        # 2. MAX UNREALIZED LOSS (safety net)
        # ================================================================
        max_loss_pct = self.config.max_unrealized_loss_pct
        if -profit_pct >= max_loss_pct:
            # Calculate simulated stop price
            if is_long:
                stop_price = entry_price * (1 - max_loss_pct / 100)
            else:
                stop_price = entry_price * (1 + max_loss_pct / 100)
            logger.warning(
                f"AGAPE: MAX LOSS {pos['position_id']} at {-profit_pct:.1f}% "
                f"(limit={max_loss_pct}%)"
            )
            return self._close_position(pos, stop_price, f"MAX_LOSS_{max_loss_pct}pct")

        # ================================================================
        # 3. EMERGENCY STOP (catastrophic protection)
        # ================================================================
        emergency_pct = self.config.no_loss_emergency_stop_pct
        if -profit_pct >= emergency_pct:
            if is_long:
                stop_price = entry_price * (1 - emergency_pct / 100)
            else:
                stop_price = entry_price * (1 + emergency_pct / 100)
            logger.warning(
                f"AGAPE: EMERGENCY STOP {pos['position_id']} at {-profit_pct:.1f}%"
            )
            return self._close_position(pos, stop_price, "EMERGENCY_STOP")

        # ================================================================
        # 4. CHECK TRAILING STOP (if active)
        # ================================================================
        trailing_active = pos.get("trailing_active", False)
        current_stop = pos.get("current_stop")

        if trailing_active and current_stop:
            if is_long and current_price <= current_stop:
                exit_pnl_pct = ((current_stop - entry_price) / entry_price) * 100
                logger.info(
                    f"AGAPE: TRAIL STOP {pos['position_id']} at {current_stop:.2f} "
                    f"(locked +{exit_pnl_pct:.1f}%)"
                )
                return self._close_position(pos, current_stop, f"TRAIL_STOP_+{exit_pnl_pct:.1f}pct")

            if not is_long and current_price >= current_stop:
                exit_pnl_pct = ((entry_price - current_stop) / entry_price) * 100
                logger.info(
                    f"AGAPE: TRAIL STOP {pos['position_id']} at {current_stop:.2f} "
                    f"(locked +{exit_pnl_pct:.1f}%)"
                )
                return self._close_position(pos, current_stop, f"TRAIL_STOP_+{exit_pnl_pct:.1f}pct")

        # ================================================================
        # 5. CHECK PROFIT TARGET (if enabled)
        # ================================================================
        profit_target_pct = self.config.no_loss_profit_target_pct
        if profit_target_pct > 0 and profit_pct >= profit_target_pct:
            logger.info(
                f"AGAPE: PROFIT TARGET {pos['position_id']} at +{profit_pct:.1f}%"
            )
            return self._close_position(pos, current_price, f"PROFIT_TARGET_+{profit_pct:.1f}pct")

        # ================================================================
        # 6. ACTIVATE TRAILING (once profitable enough)
        # ================================================================
        activation_pct = self.config.no_loss_activation_pct
        if not trailing_active and max_profit_pct >= activation_pct:
            # Calculate initial trailing stop using trail formula, floored at breakeven
            trail_distance_pct = self.config.no_loss_trail_distance_pct
            trail_distance = entry_price * (trail_distance_pct / 100)

            if is_long:
                # Trail below the current best price, but never below breakeven
                initial_stop = max(entry_price, hwm - trail_distance)
            else:
                # Trail above the current best price, but never above breakeven
                initial_stop = min(entry_price, hwm + trail_distance)

            initial_stop = round(initial_stop, 2)
            locked_pct = abs(initial_stop - entry_price) / entry_price * 100

            # Update HWM to current best price (NOT entry_price!)
            self.db.update_high_water_mark(pos["position_id"], hwm)
            try:
                self.db._execute(
                    """UPDATE agape_positions
                       SET trailing_active = TRUE, current_stop = %s
                       WHERE position_id = %s AND status = 'open'""",
                    (initial_stop, pos["position_id"])
                )
            except Exception:
                pass  # Best effort
            logger.info(
                f"AGAPE: TRAIL ACTIVATED {pos['position_id']} at +{max_profit_pct:.1f}% "
                f"(stop={initial_stop:.2f}, locking +{locked_pct:.2f}%, hwm={hwm:.2f})"
            )
            # Mark as active for the ratchet step below
            trailing_active = True
            current_stop = initial_stop

        # ================================================================
        # 7. UPDATE TRAILING STOP (ratchet as price improves)
        # ================================================================
        if trailing_active:
            trail_distance_pct = self.config.no_loss_trail_distance_pct
            trail_distance = entry_price * (trail_distance_pct / 100)

            if is_long:
                new_stop = round(hwm - trail_distance, 2)
                # Only require: better than current stop AND at or above breakeven
                if new_stop > (current_stop or 0) and new_stop >= entry_price:
                    try:
                        self.db._execute(
                            """UPDATE agape_positions SET current_stop = %s
                               WHERE position_id = %s AND status = 'open'""",
                            (new_stop, pos["position_id"])
                        )
                    except Exception:
                        pass
                    locked = ((new_stop - entry_price) / entry_price) * 100
                    logger.info(
                        f"AGAPE: Trail raised {pos['position_id']} to {new_stop:.2f} "
                        f"(locking +{locked:.1f}%, hwm={hwm:.2f})"
                    )
            else:
                new_stop = round(hwm + trail_distance, 2)
                # Only require: better than current stop AND at or below breakeven
                if current_stop and new_stop < current_stop and new_stop <= entry_price:
                    try:
                        self.db._execute(
                            """UPDATE agape_positions SET current_stop = %s
                               WHERE position_id = %s AND status = 'open'""",
                            (new_stop, pos["position_id"])
                        )
                    except Exception:
                        pass
                    locked = ((entry_price - new_stop) / entry_price) * 100
                    logger.info(
                        f"AGAPE: Trail lowered {pos['position_id']} to {new_stop:.2f} "
                        f"(locking +{locked:.1f}%, hwm={hwm:.2f})"
                    )

        # ================================================================
        # 8. MAX HOLD TIME
        # ================================================================
        open_time_str = pos.get("open_time")
        if open_time_str:
            try:
                if isinstance(open_time_str, str):
                    open_time = datetime.fromisoformat(open_time_str)
                else:
                    open_time = open_time_str
                if open_time.tzinfo is None:
                    open_time = open_time.replace(tzinfo=CENTRAL_TZ)
                hold_hours = (now - open_time).total_seconds() / 3600
                if hold_hours >= self.config.max_hold_hours:
                    return self._close_position(pos, current_price, "MAX_HOLD_TIME")
            except (ValueError, TypeError):
                pass

        return False

    def _execute_sar(self, pos: Dict, current_price: float) -> bool:
        """Execute Stop-and-Reverse: close losing position and open reversal.

        Ported from VALOR SAR strategy.
        """
        position_id = pos["position_id"]
        entry_price = pos["entry_price"]
        side = pos["side"]
        contracts = pos.get("contracts", 1)

        # Close original position at SAR trigger price
        is_long = side == "long"
        sar_pct = self.config.sar_trigger_pct
        if is_long:
            sar_close_price = entry_price * (1 - sar_pct / 100)
        else:
            sar_close_price = entry_price * (1 + sar_pct / 100)

        success = self._close_position(pos, sar_close_price, f"SAR_CLOSED_{sar_pct}pct")
        if not success:
            return False

        # Open reversal position
        reversal_side = "short" if is_long else "long"
        reversal_id = f"SAR-{uuid.uuid4().hex[:8]}"

        # Calculate emergency stop for reversal
        emergency_pct = self.config.no_loss_emergency_stop_pct
        if reversal_side == "long":
            stop_loss = current_price * (1 - emergency_pct / 100)
            take_profit = current_price * (1 + emergency_pct / 100)
        else:
            stop_loss = current_price * (1 + emergency_pct / 100)
            take_profit = current_price * (1 - emergency_pct / 100)

        # Create reversal signal
        reversal_signal = AgapeSignal(
            spot_price=current_price,
            timestamp=datetime.now(CENTRAL_TZ),
            funding_rate=0,
            funding_regime="SAR_REVERSAL",
            action=SignalAction.LONG if reversal_side == "long" else SignalAction.SHORT,
            confidence="HIGH",
            reasoning=f"SAR_REVERSAL from {side.upper()} {position_id}",
            side=reversal_side,
            entry_price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            contracts=contracts,
            max_risk_usd=0,
        )

        reversal_pos = self.executor.execute_trade(reversal_signal)
        if reversal_pos:
            self.db.save_position(reversal_pos)
            self.db.log(
                "INFO", "SAR_EXECUTED",
                f"SAR: Closed {side.upper()} {position_id}, "
                f"Opened {reversal_side.upper()} {reversal_pos.position_id} @ ${current_price:.2f}",
            )
            logger.info(
                f"AGAPE SAR COMPLETE: Closed {side.upper()} {position_id}, "
                f"Opened {reversal_side.upper()} {reversal_pos.position_id}"
            )
            return True

        logger.error(f"AGAPE SAR: Reversal execution failed for {position_id}")
        return True  # Original was still closed

    # ==================================================================
    # Original exit conditions (fallback when no-loss trailing disabled)
    # ==================================================================

    def _check_exit_conditions(
        self, pos: Dict, current_price: float, now: datetime
    ) -> tuple:
        """Check if a position should be closed (fallback, non-trailing mode).

        Returns (should_close: bool, reason: str).
        """
        entry_price = pos["entry_price"]
        side = pos["side"]
        stop_loss = pos.get("stop_loss")
        take_profit = pos.get("take_profit")
        open_time_str = pos.get("open_time")

        # 1. Stop Loss
        if stop_loss:
            if side == "long" and current_price <= stop_loss:
                return (True, "STOP_LOSS")
            elif side == "short" and current_price >= stop_loss:
                return (True, "STOP_LOSS")

        # 2. Take Profit
        if take_profit:
            if side == "long" and current_price >= take_profit:
                return (True, "TAKE_PROFIT")
            elif side == "short" and current_price <= take_profit:
                return (True, "TAKE_PROFIT")

        # 3. Max hold time
        if open_time_str:
            try:
                if isinstance(open_time_str, str):
                    open_time = datetime.fromisoformat(open_time_str)
                else:
                    open_time = open_time_str
                if open_time.tzinfo is None:
                    open_time = open_time.replace(tzinfo=CENTRAL_TZ)
                hold_hours = (now - open_time).total_seconds() / 3600
                if hold_hours >= self.config.max_hold_hours:
                    return (True, "MAX_HOLD_TIME")
            except (ValueError, TypeError):
                pass

        return (False, "")

    # ==================================================================
    # Position Close + Feedback Loops
    # ==================================================================

    def _close_position(
        self, pos_dict: Dict, current_price: float, reason: str
    ) -> bool:
        """Close a position and record the outcome with feedback loops."""
        position_id = pos_dict["position_id"]
        entry_price = pos_dict["entry_price"]
        side = pos_dict["side"]
        contracts = pos_dict.get("contracts", 1)

        # Calculate P&L
        direction = 1 if side == "long" else -1
        pnl_per_contract = (current_price - entry_price) * self.config.contract_size * direction
        realized_pnl = round(pnl_per_contract * contracts, 2)

        # Use expire_position for time-based exits, close_position for P&L exits
        if reason == "MAX_HOLD_TIME":
            success = self.db.expire_position(position_id, realized_pnl, current_price)
        else:
            success = self.db.close_position(
                position_id, current_price, realized_pnl, reason
            )

        if success:
            won = realized_pnl > 0

            # Update loss streak tracking
            if won:
                if self.consecutive_losses > 0:
                    logger.info(f"AGAPE: Loss streak reset (was {self.consecutive_losses})")
                self.consecutive_losses = 0
                self.loss_streak_pause_until = None
            else:
                self.consecutive_losses += 1
                logger.warning(f"AGAPE: Consecutive losses: {self.consecutive_losses}")
                if self.consecutive_losses >= self.config.max_consecutive_losses:
                    pause_min = self.config.loss_streak_pause_minutes
                    self.loss_streak_pause_until = datetime.now(CENTRAL_TZ) + timedelta(minutes=pause_min)
                    logger.warning(
                        f"AGAPE: LOSS STREAK PAUSE - {self.consecutive_losses} losses, "
                        f"pausing until {self.loss_streak_pause_until.strftime('%H:%M:%S')} CT"
                    )

            # Update direction tracker
            record_agape_trade_outcome(
                direction=side.upper(),
                is_win=won,
                scan_number=self._cycle_count,
            )

            # Feed outcome to Bayesian Crypto Tracker for choppy-market edge detection
            if _bayesian_tracker_mod and self.config.enable_bayesian_choppy:
                try:
                    now = datetime.now(CENTRAL_TZ)
                    open_time_raw = pos_dict.get("open_time")
                    if isinstance(open_time_raw, str):
                        entry_time = datetime.fromisoformat(open_time_raw)
                    elif isinstance(open_time_raw, datetime):
                        entry_time = open_time_raw
                    else:
                        entry_time = now - timedelta(minutes=5)
                    if entry_time.tzinfo is None:
                        entry_time = entry_time.replace(tzinfo=CENTRAL_TZ)

                    hold_minutes = (now - entry_time).total_seconds() / 60

                    bt_outcome = BayesianTradeOutcome(
                        trade_id=position_id,
                        symbol=self.config.ticker,
                        side=side,
                        entry_price=entry_price,
                        exit_price=current_price,
                        pnl=realized_pnl,
                        contracts=contracts,
                        entry_time=entry_time,
                        exit_time=now,
                        hold_duration_minutes=hold_minutes,
                        funding_regime=pos_dict.get("funding_regime_at_entry", "UNKNOWN"),
                        leverage_regime=pos_dict.get("leverage_regime", "UNKNOWN"),
                        volatility_state=pos_dict.get("volatility_regime", "NORMAL"),
                        ls_bias=pos_dict.get("ls_ratio_at_entry", "NEUTRAL"),
                    )

                    tracker = get_bayesian_tracker(
                        strategy_name="agape_choppy",
                        starting_capital=self.config.starting_capital,
                    )
                    estimate = tracker.record_trade(bt_outcome)

                    # Persist to DB if available
                    if _bayesian_db_mod:
                        bdb = BayesianCryptoDatabase()
                        bdb.save_trade("agape_choppy", bt_outcome)
                        bdb.save_tracker_state(tracker)

                    logger.info(
                        f"AGAPE BAYESIAN: Recorded {position_id} "
                        f"win={won} → win_rate={estimate.mean:.4f} "
                        f"edge_prob={estimate.edge_probability:.4f} "
                        f"verdict={estimate.verdict.value}"
                    )
                except Exception as e:
                    logger.warning(f"AGAPE BAYESIAN: Failed to record outcome: {e}")

            self.db.log(
                "INFO", "CLOSE_POSITION",
                f"Closed {position_id} @ ${current_price:.2f} P&L=${realized_pnl:+.2f} ({reason})",
                details={
                    "position_id": position_id,
                    "realized_pnl": realized_pnl,
                    "reason": reason,
                    "consecutive_losses": self.consecutive_losses,
                },
            )
            logger.info(
                f"AGAPE Trader: Closed {position_id} "
                f"P&L=${realized_pnl:+.2f} ({reason})"
            )

        return success

    def _update_hwm(self, pos_dict: Dict, current_price: float):
        """Update high water mark for trailing stop."""
        side = pos_dict["side"]
        hwm = pos_dict.get("high_water_mark", pos_dict["entry_price"])

        if side == "long" and current_price > hwm:
            self.db.update_high_water_mark(pos_dict["position_id"], current_price)
        elif side == "short" and current_price < hwm:
            self.db.update_high_water_mark(pos_dict["position_id"], current_price)

    # ==================================================================
    # Entry Conditions
    # ==================================================================

    def _check_entry_conditions(self, now: datetime) -> Optional[str]:
        """Check if conditions allow new entries.

        Matches VALOR pattern: no time-based cooldown.
        Entry gating is handled by loss streak pause, market hours,
        and signal quality only.

        Returns skip reason string, or None if conditions are met.
        """
        if not self._enabled:
            return "BOT_DISABLED"

        # No cooldown - matches VALOR pattern
        # Entry frequency is controlled by:
        # 1. Loss streak pause (checked in run_cycle before this)
        # 2. Signal quality (generate_signal returns WAIT if no opportunity)
        # 3. Market hours (CME schedule below)

        # CME Micro Ether trades Sun 5PM - Fri 4PM CT
        weekday = now.weekday()  # 0=Mon, 6=Sun
        hour = now.hour
        minute = now.minute

        # Saturday: market closed all day
        if weekday == 5:
            return "MARKET_CLOSED_SATURDAY"

        # Sunday: market opens at 5 PM CT
        if weekday == 6 and hour < 17:
            return "MARKET_CLOSED_SUNDAY_EARLY"

        # Friday: market closes at 4 PM CT (4:00:00 = closed)
        if weekday == 4 and hour >= 16:
            return "MARKET_CLOSED_FRIDAY_LATE"

        # Daily maintenance break: 4 PM - 5 PM CT (Mon-Thu)
        if 0 <= weekday <= 3 and hour == 16:
            return "DAILY_MAINTENANCE"

        return None

    # ==================================================================
    # Logging
    # ==================================================================

    def _log_scan(
        self,
        result: Dict,
        context: Dict,
        signal: Optional[AgapeSignal] = None,
    ):
        """Log the scan cycle for visibility."""
        market = context.get("market_data", {})
        prophet = context.get("prophet_data", {})

        scan_data = {
            "outcome": result.get("outcome", "UNKNOWN"),
            "eth_price": market.get("spot_price"),
            "funding_rate": market.get("funding_rate"),
            "funding_regime": market.get("funding_regime"),
            "ls_ratio": market.get("ls_ratio"),
            "ls_bias": market.get("ls_bias"),
            "squeeze_risk": market.get("squeeze_risk"),
            "leverage_regime": market.get("leverage_regime"),
            "max_pain": market.get("max_pain"),
            "crypto_gex": market.get("crypto_gex"),
            "crypto_gex_regime": market.get("crypto_gex_regime"),
            "combined_signal": market.get("combined_signal"),
            "combined_confidence": market.get("combined_confidence"),
            "oracle_advice": prophet.get("advice"),
            "oracle_win_prob": prophet.get("win_probability"),
            "signal_action": signal.action.value if signal else None,
            "signal_reasoning": signal.reasoning if signal else None,
            "position_id": context.get("position_id"),
            "error_message": result.get("error"),
        }
        self.db.log_scan(scan_data)

    def _save_equity_snapshot(self, market_data: Optional[Dict]):
        """Save an equity snapshot for intraday tracking."""
        try:
            open_positions = self.db.get_open_positions()
            current_price = self.executor.get_current_price()
            if not current_price and market_data:
                current_price = market_data.get("spot_price")

            # Calculate unrealized P&L from open positions
            unrealized = 0.0
            if current_price and open_positions:
                for pos in open_positions:
                    direction = 1 if pos["side"] == "long" else -1
                    pnl = (current_price - pos["entry_price"]) * self.config.contract_size * direction * pos.get("contracts", 1)
                    unrealized += pnl

            # Get cumulative realized P&L from all closed trades
            closed = self.db.get_closed_trades(limit=10000)
            realized_cum = sum(t.get("realized_pnl", 0) for t in closed) if closed else 0.0

            equity = self.config.starting_capital + realized_cum + unrealized
            funding_rate = market_data.get("funding_rate") if market_data else None

            self.db.save_equity_snapshot(
                equity=round(equity, 2),
                unrealized_pnl=round(unrealized, 2),
                realized_cumulative=round(realized_cum, 2),
                open_positions=len(open_positions),
                eth_price=current_price,
                funding_rate=funding_rate,
            )
        except Exception as e:
            logger.warning(f"AGAPE Trader: Snapshot save failed: {e}")

    # ------------------------------------------------------------------
    # CME Market Status
    # ------------------------------------------------------------------

    def get_cme_market_status(self, now: Optional[datetime] = None) -> Dict[str, Any]:
        """Get CME Micro Ether market status.

        CME /MET: Sunday 5:00 PM CT - Friday 4:00 PM CT
          with daily maintenance break 4:00-5:00 PM CT (Mon-Thu).
        """
        if now is None:
            now = datetime.now(CENTRAL_TZ)

        weekday = now.weekday()  # 0=Mon, 6=Sun
        hour = now.hour

        # Determine CME crypto market status
        if weekday == 5:
            # Saturday: closed all day, reopens Sunday 5 PM CT
            next_open = now + timedelta(days=1)
            next_open = next_open.replace(hour=17, minute=0, second=0, microsecond=0)
            return {
                "cme_market_open": False,
                "status": "CLOSED_SATURDAY",
                "reason": "CME closed Saturday. Reopens Sunday 5:00 PM CT.",
                "next_open": next_open.strftime("%Y-%m-%d %H:%M CT"),
                "schedule": "Sun 5:00 PM - Fri 4:00 PM CT (daily 4-5 PM break Mon-Thu)",
            }
        elif weekday == 6 and hour < 17:
            # Sunday before 5 PM: still closed
            next_open = now.replace(hour=17, minute=0, second=0, microsecond=0)
            return {
                "cme_market_open": False,
                "status": "CLOSED_SUNDAY_EARLY",
                "reason": "CME opens at 5:00 PM CT today (Sunday).",
                "next_open": next_open.strftime("%Y-%m-%d %H:%M CT"),
                "schedule": "Sun 5:00 PM - Fri 4:00 PM CT (daily 4-5 PM break Mon-Thu)",
            }
        elif weekday == 4 and hour >= 16:
            # Friday 4 PM+: closed for the weekend
            next_open = now + timedelta(days=2)
            next_open = next_open.replace(hour=17, minute=0, second=0, microsecond=0)
            return {
                "cme_market_open": False,
                "status": "CLOSED_FRIDAY_LATE",
                "reason": "CME closed for the weekend. Reopens Sunday 5:00 PM CT.",
                "next_open": next_open.strftime("%Y-%m-%d %H:%M CT"),
                "schedule": "Sun 5:00 PM - Fri 4:00 PM CT (daily 4-5 PM break Mon-Thu)",
            }
        elif 0 <= weekday <= 3 and hour == 16:
            # Mon-Thu 4-5 PM: daily maintenance
            next_open = now.replace(hour=17, minute=0, second=0, microsecond=0)
            return {
                "cme_market_open": False,
                "status": "DAILY_MAINTENANCE",
                "reason": "CME daily maintenance break (4:00-5:00 PM CT). Reopens at 5:00 PM CT.",
                "next_open": next_open.strftime("%Y-%m-%d %H:%M CT"),
                "schedule": "Sun 5:00 PM - Fri 4:00 PM CT (daily 4-5 PM break Mon-Thu)",
            }
        else:
            return {
                "cme_market_open": True,
                "status": "OPEN",
                "reason": "CME Micro Ether Futures market is open.",
                "schedule": "Sun 5:00 PM - Fri 4:00 PM CT (daily 4-5 PM break Mon-Thu)",
            }

    # ------------------------------------------------------------------
    # Status & Performance (for API routes)
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Get bot status for API."""
        now = datetime.now(CENTRAL_TZ)
        open_positions = self.db.get_open_positions()
        current_price = self.executor.get_current_price()

        # Calculate unrealized P&L
        total_unrealized = 0.0
        if current_price and open_positions:
            for pos in open_positions:
                direction = 1 if pos["side"] == "long" else -1
                pnl = (current_price - pos["entry_price"]) * self.config.contract_size * direction * pos.get("contracts", 1)
                total_unrealized += pnl

        # Direction tracker status
        dt_status = self._direction_tracker.get_status()

        # Calculate cumulative realized P&L from all closed trades
        closed_trades = self.db.get_closed_trades(limit=10000)
        realized_pnl = sum(t.get("realized_pnl", 0) for t in closed_trades) if closed_trades else 0.0
        total_pnl = realized_pnl + total_unrealized
        current_balance = self.config.starting_capital + total_pnl
        return_pct = (total_pnl / self.config.starting_capital * 100) if self.config.starting_capital else 0

        # Win rate
        wins = [t for t in closed_trades if (t.get("realized_pnl") or 0) > 0] if closed_trades else []
        win_rate = round(len(wins) / len(closed_trades) * 100, 1) if closed_trades else None

        # CME market status (separate from equity market status in nav bar)
        cme_status = self.get_cme_market_status(now)

        return {
            "bot_name": "AGAPE",
            "status": "ACTIVE" if self._enabled else "DISABLED",
            "mode": self.config.mode.value,
            "ticker": self.config.ticker,
            "instrument": self.config.instrument,
            "exchange": "tastytrade",
            "cycle_count": self._cycle_count,
            "open_positions": len(open_positions),
            "max_positions": None,  # Unlimited
            "current_eth_price": current_price,
            "total_unrealized_pnl": round(total_unrealized, 2),
            "starting_capital": self.config.starting_capital,
            "risk_per_trade_pct": self.config.risk_per_trade_pct,
            "max_contracts": self.config.max_contracts,
            "cooldown_minutes": 0,  # No cooldown - matches VALOR
            "require_oracle": self.config.require_oracle_approval,
            # CME Micro Ether Futures market status
            # NOTE: This is DIFFERENT from the equity "Market Open/Closed" in the nav bar.
            # CME /MET trades Sun 5PM - Fri 4PM CT (nearly 24/7), not just 8:30AM-3PM.
            "market": cme_status,
            # Paper account summary (matches VALOR pattern)
            "paper_account": {
                "starting_capital": self.config.starting_capital,
                "current_balance": round(current_balance, 2),
                "cumulative_pnl": round(total_pnl, 2),
                "realized_pnl": round(realized_pnl, 2),
                "unrealized_pnl": round(total_unrealized, 2),
                "return_pct": round(return_pct, 2),
                "total_trades": len(closed_trades) if closed_trades else 0,
                "win_rate": win_rate,
            },
            "aggressive_features": {
                "use_no_loss_trailing": self.config.use_no_loss_trailing,
                "use_sar": self.config.use_sar,
                "direction_tracker": dt_status,
                "consecutive_losses": self.consecutive_losses,
                "loss_streak_paused": self.loss_streak_pause_until is not None and now < self.loss_streak_pause_until,
            },
            "positions": open_positions,
        }

    def get_performance(self) -> Dict[str, Any]:
        """Get performance statistics for API.

        Includes both realized P&L (from closed trades) and unrealized P&L
        (from open positions) so Total P&L reflects reality.
        """
        closed_trades = self.db.get_closed_trades(limit=10000)

        # Calculate unrealized P&L from open positions
        open_positions = self.db.get_open_positions()
        current_price = self.executor.get_current_price()
        unrealized_pnl = 0.0
        if current_price and open_positions:
            for pos in open_positions:
                direction = 1 if pos["side"] == "long" else -1
                pnl = (current_price - pos["entry_price"]) * self.config.contract_size * direction * pos.get("contracts", 1)
                unrealized_pnl += pnl

        if not closed_trades:
            return {
                "total_trades": 0,
                "open_positions": len(open_positions),
                "win_rate": None,
                "total_pnl": round(unrealized_pnl, 2),
                "realized_pnl": 0,
                "unrealized_pnl": round(unrealized_pnl, 2),
                "avg_win": 0,
                "avg_loss": 0,
                "best_trade": 0,
                "worst_trade": 0,
                "profit_factor": 0,
                "return_pct": round(unrealized_pnl / self.config.starting_capital * 100, 2),
            }

        wins = [t for t in closed_trades if (t.get("realized_pnl") or 0) > 0]
        losses = [t for t in closed_trades if (t.get("realized_pnl") or 0) <= 0]
        realized_pnl = sum(t.get("realized_pnl", 0) for t in closed_trades)
        total_pnl = realized_pnl + unrealized_pnl
        total_wins = sum(t.get("realized_pnl", 0) for t in wins) if wins else 0
        total_losses = abs(sum(t.get("realized_pnl", 0) for t in losses)) if losses else 0

        return {
            "total_trades": len(closed_trades),
            "open_positions": len(open_positions),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(closed_trades) * 100, 1) if closed_trades else None,
            "total_pnl": round(total_pnl, 2),
            "realized_pnl": round(realized_pnl, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "avg_win": round(total_wins / len(wins), 2) if wins else 0,
            "avg_loss": round(total_losses / len(losses), 2) if losses else 0,
            "best_trade": max((t.get("realized_pnl", 0) for t in closed_trades), default=0),
            "worst_trade": min((t.get("realized_pnl", 0) for t in closed_trades), default=0),
            "profit_factor": round(total_wins / total_losses, 2) if total_losses > 0 else float("inf"),
            "return_pct": round(total_pnl / self.config.starting_capital * 100, 2),
        }

    def force_close_all(self, reason: str = "MANUAL_CLOSE") -> Dict[str, Any]:
        """Force close all open positions."""
        open_positions = self.db.get_open_positions()
        current_price = self.executor.get_current_price()
        results = []
        total_pnl = 0.0

        if not current_price:
            return {"error": "No price available", "closed": 0}

        for pos in open_positions:
            closed = self._close_position(pos, current_price, reason)
            if closed:
                direction = 1 if pos["side"] == "long" else -1
                pnl = (current_price - pos["entry_price"]) * self.config.contract_size * direction * pos.get("contracts", 1)
                total_pnl += pnl
                results.append({"position_id": pos["position_id"], "pnl": round(pnl, 2)})

        return {
            "closed": len(results),
            "total_pnl": round(total_pnl, 2),
            "details": results,
        }

    def enable(self):
        self._enabled = True
        self.db.log("INFO", "ENABLE", "AGAPE bot enabled (AGGRESSIVE MODE)")

    def disable(self):
        self._enabled = False
        self.db.log("INFO", "DISABLE", "AGAPE bot disabled")
