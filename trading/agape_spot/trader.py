"""
AGAPE-SPOT Trader - Main orchestrator for 24/7 Coinbase Spot ETH-USD trading.

Always-on: No CME market hours restrictions, no maintenance breaks.
Spot-native P&L: (exit - entry) * eth_quantity * direction.
Separate equity curve, positions, and performance from AGAPE (futures).

Runs on a 5-minute cycle called by the scheduler.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from zoneinfo import ZoneInfo

from trading.agape_spot.models import (
    AgapeSpotConfig,
    AgapeSpotSignal,
    AgapeSpotPosition,
    PositionSide,
    PositionStatus,
    SignalAction,
    TradingMode,
)
from trading.agape_spot.db import AgapeSpotDatabase
from trading.agape_spot.signals import (
    AgapeSpotSignalGenerator,
    get_spot_direction_tracker,
    record_spot_trade_outcome,
)
from trading.agape_spot.executor import AgapeSpotExecutor

logger = logging.getLogger(__name__)

CENTRAL_TZ = ZoneInfo("America/Chicago")

# Singleton
_agape_spot_trader: Optional["AgapeSpotTrader"] = None


def get_agape_spot_trader() -> Optional["AgapeSpotTrader"]:
    return _agape_spot_trader


def create_agape_spot_trader(config: Optional[AgapeSpotConfig] = None) -> "AgapeSpotTrader":
    global _agape_spot_trader
    _agape_spot_trader = AgapeSpotTrader(config)
    return _agape_spot_trader


class AgapeSpotTrader:
    """24/7 Coinbase Spot ETH-USD trading bot.

    AGGRESSIVE MODE:
    - No-loss trailing (let winners run)
    - SAR (Stop-and-Reverse) for losing positions
    - Direction Tracker for nimble reversals
    - Loss streak protection
    - 24/7/365 - no market hours restrictions
    """

    def __init__(self, config: Optional[AgapeSpotConfig] = None):
        self.db = AgapeSpotDatabase()

        if config:
            self.config = config
        else:
            self.config = AgapeSpotConfig.load_from_db(self.db)

        self.signals = AgapeSpotSignalGenerator(self.config)
        self.executor = AgapeSpotExecutor(self.config, self.db)

        self._last_scan_time: Optional[datetime] = None
        self._cycle_count: int = 0
        self._enabled: bool = True

        # Loss streak tracking
        self.consecutive_losses: int = 0
        self.loss_streak_pause_until: Optional[datetime] = None

        # Direction tracker
        self._direction_tracker = get_spot_direction_tracker(self.config)

        self.db.log("INFO", "INIT", f"AGAPE-SPOT trader initialized (mode={self.config.mode.value}, 24/7 Coinbase spot)")
        logger.info(
            f"AGAPE-SPOT: Initialized (mode={self.config.mode.value}, "
            f"max_pos={self.config.max_open_positions}, "
            f"oracle_required={self.config.require_oracle_approval})"
        )

    def run_cycle(self, close_only: bool = False) -> Dict[str, Any]:
        """Execute one trading cycle. Called every 5 minutes by scheduler."""
        self._cycle_count += 1
        now = datetime.now(CENTRAL_TZ)

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
            # Step 1: Fetch market data
            market_data = self.signals.get_market_data()
            if market_data:
                scan_context["market_data"] = market_data
                scan_context["eth_price"] = market_data.get("spot_price")

            # Step 2: Get Oracle advice
            oracle_data = None
            if market_data:
                oracle_data = self.signals.get_oracle_advice(market_data)
                scan_context["oracle_data"] = oracle_data

            # Step 3: Manage existing positions
            managed, closed = self._manage_positions(market_data)
            result["positions_managed"] = managed
            result["positions_closed"] = closed

            # Save equity snapshot every cycle
            self._save_equity_snapshot(market_data)

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
                    self.loss_streak_pause_until = None

            # Step 5: Check entry conditions (24/7 - mostly just enabled check)
            skip_reason = self._check_entry_conditions(now)
            if skip_reason:
                result["outcome"] = skip_reason
                self._log_scan(result, scan_context)
                return result

            # Step 6: Generate signal
            signal = self.signals.generate_signal(oracle_data=oracle_data)
            result["signal"] = signal.to_dict() if signal else None

            if not signal or not signal.is_valid:
                result["outcome"] = f"NO_SIGNAL_{signal.reasoning if signal else 'NONE'}"
                self._log_scan(result, scan_context, signal=signal)
                return result

            # Step 7: Execute trade
            position = self.executor.execute_trade(signal)
            if position:
                self.db.save_position(position)
                result["new_trade"] = True
                result["outcome"] = f"TRADED_{signal.side.upper()}"
                result["position_id"] = position.position_id
                scan_context["position_id"] = position.position_id

                notional = signal.eth_quantity * position.entry_price
                self.db.log(
                    "INFO", "NEW_TRADE",
                    f"{signal.side.upper()} {signal.eth_quantity:.4f} ETH (${notional:.2f}) @ ${position.entry_price:.2f}",
                    details=signal.to_dict(),
                )
            else:
                result["outcome"] = "EXECUTION_FAILED"

            self._log_scan(result, scan_context, signal=signal)
            return result

        except Exception as e:
            logger.error(f"AGAPE-SPOT: Cycle failed: {e}", exc_info=True)
            result["outcome"] = "ERROR"
            result["error"] = str(e)
            self.db.log("ERROR", "CYCLE_ERROR", str(e))
            self._log_scan(result, scan_context)
            return result

    # ------------------------------------------------------------------
    # Position Management
    # ------------------------------------------------------------------

    def _manage_positions(self, market_data: Optional[Dict]) -> tuple:
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
                    did_close = self._manage_position_no_loss_trailing(pos_dict, current_price, now)
                else:
                    should_close, reason = self._check_exit_conditions(pos_dict, current_price, now)
                    did_close = False
                    if should_close:
                        did_close = self._close_position(pos_dict, current_price, reason)

                if did_close:
                    closed += 1
                else:
                    self._update_hwm(pos_dict, current_price)
            except Exception as e:
                logger.error(f"AGAPE-SPOT: Position management error: {e}")

        return (len(open_positions), closed)

    def _manage_position_no_loss_trailing(self, pos, current_price, now):
        entry_price = pos["entry_price"]
        side = pos["side"]
        is_long = side == "long"

        if is_long:
            profit_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            profit_pct = ((entry_price - current_price) / entry_price) * 100

        hwm = pos.get("high_water_mark") or entry_price
        if hwm <= 0:
            hwm = entry_price
        if is_long:
            max_profit_pct = ((hwm - entry_price) / entry_price) * 100 if hwm > entry_price else 0
        else:
            max_profit_pct = ((entry_price - hwm) / entry_price) * 100 if hwm < entry_price else 0

        # SAR
        if self.config.use_sar:
            sar_trigger = self.config.sar_trigger_pct
            sar_mfe = self.config.sar_mfe_threshold_pct
            if -profit_pct >= sar_trigger and max_profit_pct < sar_mfe:
                return self._execute_sar(pos, current_price)

        # Max unrealized loss
        max_loss_pct = self.config.max_unrealized_loss_pct
        if -profit_pct >= max_loss_pct:
            if is_long:
                stop_price = entry_price * (1 - max_loss_pct / 100)
            else:
                stop_price = entry_price * (1 + max_loss_pct / 100)
            return self._close_position(pos, stop_price, f"MAX_LOSS_{max_loss_pct}pct")

        # Emergency stop
        emergency_pct = self.config.no_loss_emergency_stop_pct
        if -profit_pct >= emergency_pct:
            if is_long:
                stop_price = entry_price * (1 - emergency_pct / 100)
            else:
                stop_price = entry_price * (1 + emergency_pct / 100)
            return self._close_position(pos, stop_price, "EMERGENCY_STOP")

        # Trailing stop check
        trailing_active = pos.get("trailing_active", False)
        current_stop = pos.get("current_stop")

        if trailing_active and current_stop:
            if is_long and current_price <= current_stop:
                exit_pnl_pct = ((current_stop - entry_price) / entry_price) * 100
                return self._close_position(pos, current_stop, f"TRAIL_STOP_+{exit_pnl_pct:.1f}pct")
            if not is_long and current_price >= current_stop:
                exit_pnl_pct = ((entry_price - current_stop) / entry_price) * 100
                return self._close_position(pos, current_stop, f"TRAIL_STOP_+{exit_pnl_pct:.1f}pct")

        # Profit target
        profit_target_pct = self.config.no_loss_profit_target_pct
        if profit_target_pct > 0 and profit_pct >= profit_target_pct:
            return self._close_position(pos, current_price, f"PROFIT_TARGET_+{profit_pct:.1f}pct")

        # Activate trailing
        activation_pct = self.config.no_loss_activation_pct
        if not trailing_active and max_profit_pct >= activation_pct:
            trail_distance_pct = self.config.no_loss_trail_distance_pct
            trail_distance = entry_price * (trail_distance_pct / 100)

            if is_long:
                initial_stop = max(entry_price, hwm - trail_distance)
            else:
                initial_stop = min(entry_price, hwm + trail_distance)

            initial_stop = round(initial_stop, 2)
            self.db.update_high_water_mark(pos["position_id"], hwm)
            try:
                self.db._execute(
                    """UPDATE agape_spot_positions
                       SET trailing_active = TRUE, current_stop = %s
                       WHERE position_id = %s AND status = 'open'""",
                    (initial_stop, pos["position_id"])
                )
            except Exception:
                pass
            trailing_active = True
            current_stop = initial_stop

        # Ratchet trailing
        if trailing_active:
            trail_distance_pct = self.config.no_loss_trail_distance_pct
            trail_distance = entry_price * (trail_distance_pct / 100)

            if is_long:
                new_stop = round(hwm - trail_distance, 2)
                if new_stop > (current_stop or 0) and new_stop >= entry_price:
                    try:
                        self.db._execute(
                            "UPDATE agape_spot_positions SET current_stop = %s WHERE position_id = %s AND status = 'open'",
                            (new_stop, pos["position_id"])
                        )
                    except Exception:
                        pass
            else:
                new_stop = round(hwm + trail_distance, 2)
                if current_stop and new_stop < current_stop and new_stop <= entry_price:
                    try:
                        self.db._execute(
                            "UPDATE agape_spot_positions SET current_stop = %s WHERE position_id = %s AND status = 'open'",
                            (new_stop, pos["position_id"])
                        )
                    except Exception:
                        pass

        # Max hold time
        open_time_str = pos.get("open_time")
        if open_time_str:
            try:
                if isinstance(open_time_str, str):
                    open_time = datetime.fromisoformat(open_time_str)
                else:
                    open_time = open_time_str
                if open_time.tzinfo is None:
                    open_time = open_time.replace(tzinfo=CENTRAL_TZ)
                hold_hours = (datetime.now(CENTRAL_TZ) - open_time).total_seconds() / 3600
                if hold_hours >= self.config.max_hold_hours:
                    return self._close_position(pos, current_price, "MAX_HOLD_TIME")
            except (ValueError, TypeError):
                pass

        return False

    def _execute_sar(self, pos, current_price):
        position_id = pos["position_id"]
        entry_price = pos["entry_price"]
        side = pos["side"]
        eth_quantity = pos.get("eth_quantity", self.config.default_eth_size)
        is_long = side == "long"

        sar_pct = self.config.sar_trigger_pct
        if is_long:
            sar_close_price = entry_price * (1 - sar_pct / 100)
        else:
            sar_close_price = entry_price * (1 + sar_pct / 100)

        success = self._close_position(pos, sar_close_price, f"SAR_CLOSED_{sar_pct}pct")
        if not success:
            return False

        reversal_side = "short" if is_long else "long"
        emergency_pct = self.config.no_loss_emergency_stop_pct
        if reversal_side == "long":
            stop_loss = current_price * (1 - emergency_pct / 100)
            take_profit = current_price * (1 + emergency_pct / 100)
        else:
            stop_loss = current_price * (1 + emergency_pct / 100)
            take_profit = current_price * (1 - emergency_pct / 100)

        reversal_signal = AgapeSpotSignal(
            spot_price=current_price,
            timestamp=datetime.now(CENTRAL_TZ),
            action=SignalAction.LONG if reversal_side == "long" else SignalAction.SHORT,
            confidence="HIGH",
            reasoning=f"SAR_REVERSAL from {side.upper()} {position_id}",
            side=reversal_side,
            entry_price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            eth_quantity=eth_quantity,
            max_risk_usd=0,
        )

        reversal_pos = self.executor.execute_trade(reversal_signal)
        if reversal_pos:
            self.db.save_position(reversal_pos)
            self.db.log("INFO", "SAR_EXECUTED",
                        f"SAR: Closed {side.upper()} {position_id}, Opened {reversal_side.upper()} {reversal_pos.position_id}")
        return True

    def _check_exit_conditions(self, pos, current_price, now):
        entry_price = pos["entry_price"]
        side = pos["side"]
        stop_loss = pos.get("stop_loss")
        take_profit = pos.get("take_profit")

        if stop_loss:
            if side == "long" and current_price <= stop_loss:
                return (True, "STOP_LOSS")
            elif side == "short" and current_price >= stop_loss:
                return (True, "STOP_LOSS")

        if take_profit:
            if side == "long" and current_price >= take_profit:
                return (True, "TAKE_PROFIT")
            elif side == "short" and current_price <= take_profit:
                return (True, "TAKE_PROFIT")

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
                    return (True, "MAX_HOLD_TIME")
            except (ValueError, TypeError):
                pass

        return (False, "")

    def _close_position(self, pos_dict, current_price, reason):
        position_id = pos_dict["position_id"]
        entry_price = pos_dict["entry_price"]
        side = pos_dict["side"]
        eth_quantity = pos_dict.get("eth_quantity", self.config.default_eth_size)

        # Spot P&L
        direction = 1 if side == "long" else -1
        realized_pnl = round((current_price - entry_price) * eth_quantity * direction, 2)

        if reason == "MAX_HOLD_TIME":
            success = self.db.expire_position(position_id, realized_pnl, current_price)
        else:
            success = self.db.close_position(position_id, current_price, realized_pnl, reason)

        if success:
            won = realized_pnl > 0

            if won:
                if self.consecutive_losses > 0:
                    logger.info(f"AGAPE-SPOT: Loss streak reset (was {self.consecutive_losses})")
                self.consecutive_losses = 0
                self.loss_streak_pause_until = None
            else:
                self.consecutive_losses += 1
                if self.consecutive_losses >= self.config.max_consecutive_losses:
                    pause_min = self.config.loss_streak_pause_minutes
                    self.loss_streak_pause_until = datetime.now(CENTRAL_TZ) + timedelta(minutes=pause_min)

            record_spot_trade_outcome(
                direction=side.upper(), is_win=won, scan_number=self._cycle_count,
            )

            self.db.log("INFO", "CLOSE_POSITION",
                        f"Closed {position_id} @ ${current_price:.2f} P&L=${realized_pnl:+.2f} ({reason})",
                        details={"position_id": position_id, "realized_pnl": realized_pnl, "reason": reason})

        return success

    def _update_hwm(self, pos_dict, current_price):
        side = pos_dict["side"]
        hwm = pos_dict.get("high_water_mark", pos_dict["entry_price"])
        if side == "long" and current_price > hwm:
            self.db.update_high_water_mark(pos_dict["position_id"], current_price)
        elif side == "short" and current_price < hwm:
            self.db.update_high_water_mark(pos_dict["position_id"], current_price)

    def _check_entry_conditions(self, now) -> Optional[str]:
        """24/7 bot - minimal entry checks."""
        if not self._enabled:
            return "BOT_DISABLED"
        # No market hours check - 24/7/365
        return None

    # ------------------------------------------------------------------
    # Equity Snapshot
    # ------------------------------------------------------------------

    def _save_equity_snapshot(self, market_data):
        try:
            open_positions = self.db.get_open_positions()
            current_price = self.executor.get_current_price()
            if not current_price and market_data:
                current_price = market_data.get("spot_price")

            unrealized = 0.0
            if current_price and open_positions:
                for pos in open_positions:
                    direction = 1 if pos["side"] == "long" else -1
                    pnl = (current_price - pos["entry_price"]) * pos.get("eth_quantity", self.config.default_eth_size) * direction
                    unrealized += pnl

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
            logger.warning(f"AGAPE-SPOT: Snapshot save failed: {e}")

    def _log_scan(self, result, context, signal=None):
        market = context.get("market_data", {})
        oracle = context.get("oracle_data", {})
        self.db.log_scan({
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
            "oracle_advice": oracle.get("advice"),
            "oracle_win_prob": oracle.get("win_probability"),
            "signal_action": signal.action.value if signal else None,
            "signal_reasoning": signal.reasoning if signal else None,
            "position_id": context.get("position_id"),
            "error_message": result.get("error"),
        })

    # ------------------------------------------------------------------
    # Status & Performance
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        now = datetime.now(CENTRAL_TZ)
        open_positions = self.db.get_open_positions()
        current_price = self.executor.get_current_price()

        total_unrealized = 0.0
        if current_price and open_positions:
            for pos in open_positions:
                direction = 1 if pos["side"] == "long" else -1
                pnl = (current_price - pos["entry_price"]) * pos.get("eth_quantity", self.config.default_eth_size) * direction
                total_unrealized += pnl

        dt_status = self._direction_tracker.get_status()

        closed_trades = self.db.get_closed_trades(limit=10000)
        realized_pnl = sum(t.get("realized_pnl", 0) for t in closed_trades) if closed_trades else 0.0
        total_pnl = realized_pnl + total_unrealized
        current_balance = self.config.starting_capital + total_pnl
        return_pct = (total_pnl / self.config.starting_capital * 100) if self.config.starting_capital else 0

        wins = [t for t in closed_trades if (t.get("realized_pnl") or 0) > 0] if closed_trades else []
        win_rate = round(len(wins) / len(closed_trades) * 100, 1) if closed_trades else None

        return {
            "bot_name": "AGAPE-SPOT",
            "status": "ACTIVE" if self._enabled else "DISABLED",
            "mode": self.config.mode.value,
            "ticker": self.config.ticker,
            "instrument": "ETH-USD spot",
            "exchange": "coinbase",
            "market": {"status": "OPEN", "reason": "Coinbase spot trades 24/7/365."},
            "cycle_count": self._cycle_count,
            "open_positions": len(open_positions),
            "max_positions": None,
            "current_eth_price": current_price,
            "total_unrealized_pnl": round(total_unrealized, 2),
            "starting_capital": self.config.starting_capital,
            "risk_per_trade_pct": self.config.risk_per_trade_pct,
            "max_eth_per_trade": self.config.max_eth_per_trade,
            "cooldown_minutes": 0,
            "require_oracle": self.config.require_oracle_approval,
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
        closed_trades = self.db.get_closed_trades(limit=10000)

        open_positions = self.db.get_open_positions()
        current_price = self.executor.get_current_price()
        unrealized_pnl = 0.0
        if current_price and open_positions:
            for pos in open_positions:
                direction = 1 if pos["side"] == "long" else -1
                pnl = (current_price - pos["entry_price"]) * pos.get("eth_quantity", self.config.default_eth_size) * direction
                unrealized_pnl += pnl

        if not closed_trades:
            return {
                "total_trades": 0, "open_positions": len(open_positions),
                "win_rate": None, "total_pnl": round(unrealized_pnl, 2),
                "realized_pnl": 0, "unrealized_pnl": round(unrealized_pnl, 2),
                "avg_win": 0, "avg_loss": 0, "best_trade": 0, "worst_trade": 0,
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
            "wins": len(wins), "losses": len(losses),
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

    def force_close_all(self, reason="MANUAL_CLOSE"):
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
                pnl = (current_price - pos["entry_price"]) * pos.get("eth_quantity", self.config.default_eth_size) * direction
                total_pnl += pnl
                results.append({"position_id": pos["position_id"], "pnl": round(pnl, 2)})

        return {"closed": len(results), "total_pnl": round(total_pnl, 2), "details": results}

    def enable(self):
        self._enabled = True
        self.db.log("INFO", "ENABLE", "AGAPE-SPOT bot enabled")

    def disable(self):
        self._enabled = False
        self.db.log("INFO", "DISABLE", "AGAPE-SPOT bot disabled")
