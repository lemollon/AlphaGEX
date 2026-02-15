"""
AGAPE-BTC-PERP Trader - Main orchestrator for BTC Perpetual Contract trading.

Key differences from AGAPE-BTC (CME futures):
  - get_market_status(): always open 24/7/365 (no CME schedule)
  - No _check_entry_conditions time restrictions (perpetual never closes)
  - P&L = (current - entry) * quantity * direction (no contract_size multiplier)
  - Status includes bot_name="AGAPE_BTC_PERP", ticker="BTC", instrument="BTC-PERP",
    exchange="perpetual"
  - btc_price included in snapshots and scans
  - Singletons: _agape_btc_perp_trader, get_agape_btc_perp_trader(),
    create_agape_btc_perp_trader()
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from zoneinfo import ZoneInfo

from trading.agape_btc_perp.models import (
    AgapeBtcPerpConfig,
    AgapeBtcPerpSignal,
    AgapeBtcPerpPosition,
    PositionSide,
    PositionStatus,
    SignalAction,
    TradingMode,
)
from trading.agape_btc_perp.db import AgapeBtcPerpDatabase
from trading.agape_btc_perp.signals import (
    AgapeBtcPerpSignalGenerator,
    get_agape_btc_perp_direction_tracker,
    record_agape_btc_perp_trade_outcome,
)
from trading.agape_btc_perp.executor import AgapeBtcPerpExecutor

logger = logging.getLogger(__name__)

CENTRAL_TZ = ZoneInfo("America/Chicago")

_agape_btc_perp_trader: Optional["AgapeBtcPerpTrader"] = None


def get_agape_btc_perp_trader() -> Optional["AgapeBtcPerpTrader"]:
    return _agape_btc_perp_trader


def create_agape_btc_perp_trader(config: Optional[AgapeBtcPerpConfig] = None) -> "AgapeBtcPerpTrader":
    global _agape_btc_perp_trader
    _agape_btc_perp_trader = AgapeBtcPerpTrader(config)
    return _agape_btc_perp_trader


class AgapeBtcPerpTrader:
    """Main AGAPE-BTC-PERP trading bot orchestrator.

    Trades BTC perpetual contracts 24/7/365 with no market hours restrictions.
    Uses quantity-based sizing (float BTC) instead of integer contracts.
    P&L = (current - entry) * quantity * direction.
    """

    def __init__(self, config: Optional[AgapeBtcPerpConfig] = None):
        self.db = AgapeBtcPerpDatabase()
        if config:
            self.config = config
        else:
            self.config = AgapeBtcPerpConfig.load_from_db(self.db)
        self.signals = AgapeBtcPerpSignalGenerator(self.config)
        self.executor = AgapeBtcPerpExecutor(self.config, self.db)
        self._last_scan_time: Optional[datetime] = None
        self._cycle_count: int = 0
        self._enabled: bool = True
        self.consecutive_losses: int = 0
        self.loss_streak_pause_until: Optional[datetime] = None
        self._direction_tracker = get_agape_btc_perp_direction_tracker(self.config)
        self.db.log("INFO", "INIT", f"AGAPE-BTC-PERP trader initialized AGGRESSIVE (mode={self.config.mode.value})")
        logger.info(f"AGAPE-BTC-PERP Trader: Initialized AGGRESSIVE (mode={self.config.mode.value})")

    def run_cycle(self, close_only: bool = False) -> Dict[str, Any]:
        self._cycle_count += 1
        now = datetime.now(CENTRAL_TZ)
        self._direction_tracker.update_scan(self._cycle_count)
        result = {
            "cycle": self._cycle_count, "timestamp": now.isoformat(),
            "outcome": "UNKNOWN", "positions_managed": 0,
            "positions_closed": 0, "new_trade": False, "signal": None, "error": None,
        }
        scan_context: Dict[str, Any] = {}
        try:
            market_data = self.signals.get_market_data()
            if market_data:
                scan_context["market_data"] = market_data
                scan_context["btc_price"] = market_data.get("spot_price")
            prophet_data = None
            if market_data:
                prophet_data = self.signals.get_prophet_advice(market_data)
                scan_context["prophet_data"] = prophet_data

            managed, closed = self._manage_positions(market_data)
            result["positions_managed"] = managed
            result["positions_closed"] = closed
            self._save_equity_snapshot(market_data)

            if close_only:
                result["outcome"] = "CLOSE_ONLY"
                self._log_scan(result, scan_context)
                return result

            if self.loss_streak_pause_until:
                if now < self.loss_streak_pause_until:
                    remaining = (self.loss_streak_pause_until - now).total_seconds() / 60
                    result["outcome"] = f"LOSS_STREAK_PAUSE_{remaining:.1f}min"
                    self._log_scan(result, scan_context)
                    return result
                else:
                    self.loss_streak_pause_until = None

            skip_reason = self._check_entry_conditions(now)
            if skip_reason:
                result["outcome"] = skip_reason
                self._log_scan(result, scan_context)
                return result

            signal = self.signals.generate_signal(prophet_data=prophet_data)
            result["signal"] = signal.to_dict() if signal else None

            if not signal or not signal.is_valid:
                result["outcome"] = f"NO_SIGNAL_{signal.reasoning if signal else 'NONE'}"
                self._log_scan(result, scan_context, signal=signal)
                return result

            position = self.executor.execute_trade(signal)
            if position:
                self.db.save_position(position)
                result["new_trade"] = True
                result["outcome"] = f"TRADED_{signal.side.upper()}"
                result["position_id"] = position.position_id
                scan_context["position_id"] = position.position_id
                self.db.log("INFO", "NEW_TRADE",
                    f"{signal.side.upper()} {signal.quantity:.5f} BTC-PERP @ ${position.entry_price:.2f}",
                    details=signal.to_dict())
            else:
                result["outcome"] = "EXECUTION_FAILED"

            self._log_scan(result, scan_context, signal=signal)
            return result
        except Exception as e:
            logger.error(f"AGAPE-BTC-PERP Trader: Cycle failed: {e}", exc_info=True)
            result["outcome"] = "ERROR"
            result["error"] = str(e)
            self.db.log("ERROR", "CYCLE_ERROR", str(e))
            self._log_scan(result, scan_context)
            return result

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
                logger.error(f"AGAPE-BTC-PERP Trader: Position management error: {e}")
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
            if -profit_pct >= self.config.sar_trigger_pct and max_profit_pct < self.config.sar_mfe_threshold_pct:
                return self._execute_sar(pos, current_price)

        # Max unrealized loss
        if -profit_pct >= self.config.max_unrealized_loss_pct:
            if is_long:
                stop_price = entry_price * (1 - self.config.max_unrealized_loss_pct / 100)
            else:
                stop_price = entry_price * (1 + self.config.max_unrealized_loss_pct / 100)
            return self._close_position(pos, stop_price, f"MAX_LOSS_{self.config.max_unrealized_loss_pct}pct")

        # Emergency stop
        if -profit_pct >= self.config.no_loss_emergency_stop_pct:
            if is_long:
                stop_price = entry_price * (1 - self.config.no_loss_emergency_stop_pct / 100)
            else:
                stop_price = entry_price * (1 + self.config.no_loss_emergency_stop_pct / 100)
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
            trail_distance = entry_price * (self.config.no_loss_trail_distance_pct / 100)
            if is_long:
                initial_stop = max(entry_price, hwm - trail_distance)
            else:
                initial_stop = min(entry_price, hwm + trail_distance)
            initial_stop = round(initial_stop, 2)
            self.db.update_high_water_mark(pos["position_id"], hwm)
            try:
                self.db._execute(
                    "UPDATE agape_btc_perp_positions SET trailing_active = TRUE, current_stop = %s WHERE position_id = %s AND status = 'open'",
                    (initial_stop, pos["position_id"]))
            except Exception:
                pass
            trailing_active = True
            current_stop = initial_stop

        # Update trailing stop
        if trailing_active:
            trail_distance = entry_price * (self.config.no_loss_trail_distance_pct / 100)
            if is_long:
                new_stop = round(hwm - trail_distance, 2)
                if new_stop > (current_stop or 0) and new_stop >= entry_price:
                    try:
                        self.db._execute(
                            "UPDATE agape_btc_perp_positions SET current_stop = %s WHERE position_id = %s AND status = 'open'",
                            (new_stop, pos["position_id"]))
                    except Exception:
                        pass
            else:
                new_stop = round(hwm + trail_distance, 2)
                if current_stop and new_stop < current_stop and new_stop <= entry_price:
                    try:
                        self.db._execute(
                            "UPDATE agape_btc_perp_positions SET current_stop = %s WHERE position_id = %s AND status = 'open'",
                            (new_stop, pos["position_id"]))
                    except Exception:
                        pass

        # Max hold time
        open_time_str = pos.get("open_time")
        if open_time_str:
            try:
                open_time = datetime.fromisoformat(open_time_str) if isinstance(open_time_str, str) else open_time_str
                if open_time.tzinfo is None:
                    open_time = open_time.replace(tzinfo=CENTRAL_TZ)
                if (now - open_time).total_seconds() / 3600 >= self.config.max_hold_hours:
                    return self._close_position(pos, current_price, "MAX_HOLD_TIME")
            except (ValueError, TypeError):
                pass
        return False

    def _execute_sar(self, pos, current_price):
        position_id = pos["position_id"]
        entry_price = pos["entry_price"]
        side = pos["side"]
        quantity = pos.get("quantity", self.config.default_quantity)
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

        reversal_signal = AgapeBtcPerpSignal(
            spot_price=current_price, timestamp=datetime.now(CENTRAL_TZ),
            funding_rate=0, funding_regime="SAR_REVERSAL",
            action=SignalAction.LONG if reversal_side == "long" else SignalAction.SHORT,
            confidence="HIGH", reasoning=f"SAR_REVERSAL from {side.upper()} {position_id}",
            side=reversal_side, entry_price=current_price,
            stop_loss=stop_loss, take_profit=take_profit, quantity=quantity, max_risk_usd=0,
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
                open_time = datetime.fromisoformat(open_time_str) if isinstance(open_time_str, str) else open_time_str
                if open_time.tzinfo is None:
                    open_time = open_time.replace(tzinfo=CENTRAL_TZ)
                if (now - open_time).total_seconds() / 3600 >= self.config.max_hold_hours:
                    return (True, "MAX_HOLD_TIME")
            except (ValueError, TypeError):
                pass
        return (False, "")

    def _close_position(self, pos_dict, current_price, reason):
        position_id = pos_dict["position_id"]
        entry_price = pos_dict["entry_price"]
        side = pos_dict["side"]
        quantity = pos_dict.get("quantity", self.config.default_quantity)
        direction = 1 if side == "long" else -1

        # P&L = (current - entry) * quantity * direction (no contract_size multiplier)
        realized_pnl = round((current_price - entry_price) * quantity * direction, 2)

        if reason == "MAX_HOLD_TIME":
            success = self.db.expire_position(position_id, realized_pnl, current_price)
        else:
            success = self.db.close_position(position_id, current_price, realized_pnl, reason)

        if success:
            won = realized_pnl > 0
            if won:
                self.consecutive_losses = 0
                self.loss_streak_pause_until = None
            else:
                self.consecutive_losses += 1
                if self.consecutive_losses >= self.config.max_consecutive_losses:
                    pause_min = self.config.loss_streak_pause_minutes
                    self.loss_streak_pause_until = datetime.now(CENTRAL_TZ) + timedelta(minutes=pause_min)

            record_agape_btc_perp_trade_outcome(direction=side.upper(), is_win=won, scan_number=self._cycle_count)
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

    def _get_available_balance(self, open_pos=None):
        """Calculate current account balance (starting capital + realized + unrealized)."""
        try:
            closed = self.db.get_closed_trades(limit=10000)
            realized = sum(t.get("realized_pnl", 0) for t in closed) if closed else 0.0
            if open_pos is None:
                open_pos = self.db.get_open_positions()
            unrealized = 0.0
            cp = self.executor.get_current_price()
            if cp and open_pos:
                for p in open_pos:
                    d = 1 if p["side"] == "long" else -1
                    qty = p.get("quantity", self.config.default_quantity)
                    unrealized += (cp - p["entry_price"]) * qty * d
            return self.config.starting_capital + realized + unrealized
        except Exception:
            return self.config.starting_capital

    def _check_entry_conditions(self, now):
        """Check entry conditions for perpetual contract.

        BTC-PERP trades 24/7/365 - no market hours restrictions.
        Checks: bot enabled, max positions, sufficient capital.
        """
        if not self._enabled:
            return "BOT_DISABLED"

        open_pos = self.db.get_open_positions()
        if len(open_pos) >= self.config.max_open_positions:
            return f"MAX_POSITIONS_{len(open_pos)}/{self.config.max_open_positions}"

        balance = self._get_available_balance(open_pos)
        min_required = self.config.starting_capital * (self.config.risk_per_trade_pct / 100)
        if balance <= min_required:
            logger.warning(f"AGAPE-BTC-PERP: Insufficient capital ${balance:.2f} (need ${min_required:.2f})")
            return f"INSUFFICIENT_CAPITAL_${balance:.2f}"

        return None

    def _log_scan(self, result, context, signal=None):
        market = context.get("market_data", {})
        prophet = context.get("prophet_data", {})
        scan_data = {
            "outcome": result.get("outcome", "UNKNOWN"),
            "btc_price": market.get("spot_price"),
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
                    # P&L = (current - entry) * quantity * direction
                    pnl = (current_price - pos["entry_price"]) * pos.get("quantity", self.config.default_quantity) * direction
                    unrealized += pnl

            closed = self.db.get_closed_trades(limit=10000)
            realized_cum = sum(t.get("realized_pnl", 0) for t in closed) if closed else 0.0
            equity = self.config.starting_capital + realized_cum + unrealized
            self.db.save_equity_snapshot(
                equity=round(equity, 2), unrealized_pnl=round(unrealized, 2),
                realized_cumulative=round(realized_cum, 2),
                open_positions=len(open_positions),
                btc_price=current_price,
                funding_rate=market_data.get("funding_rate") if market_data else None,
            )
        except Exception as e:
            logger.warning(f"AGAPE-BTC-PERP Trader: Snapshot save failed: {e}")

    def get_market_status(self, now=None):
        """Get market status for BTC-PERP.

        Perpetual contracts trade 24/7/365 - always open.
        """
        if now is None:
            now = datetime.now(CENTRAL_TZ)
        return {
            "market_open": True,
            "status": "OPEN_24_7",
            "reason": "BTC perpetual contracts trade 24/7/365. No market hours restrictions.",
            "schedule": "24/7/365 - Always Open",
        }

    def get_status(self):
        now = datetime.now(CENTRAL_TZ)
        open_positions = self.db.get_open_positions()
        current_price = self.executor.get_current_price()

        total_unrealized = 0.0
        if current_price and open_positions:
            for pos in open_positions:
                direction = 1 if pos["side"] == "long" else -1
                # P&L = (current - entry) * quantity * direction
                pnl = (current_price - pos["entry_price"]) * pos.get("quantity", self.config.default_quantity) * direction
                total_unrealized += pnl

        dt_status = self._direction_tracker.get_status()
        closed_trades = self.db.get_closed_trades(limit=10000)
        realized_pnl = sum(t.get("realized_pnl", 0) for t in closed_trades) if closed_trades else 0.0
        total_pnl = realized_pnl + total_unrealized
        current_balance = self.config.starting_capital + total_pnl
        return_pct = (total_pnl / self.config.starting_capital * 100) if self.config.starting_capital else 0
        wins = [t for t in closed_trades if (t.get("realized_pnl") or 0) > 0] if closed_trades else []
        win_rate = round(len(wins) / len(closed_trades) * 100, 1) if closed_trades else None

        market_status = self.get_market_status(now)

        return {
            "bot_name": "AGAPE_BTC_PERP", "status": "ACTIVE" if self._enabled else "DISABLED",
            "mode": self.config.mode.value, "ticker": self.config.ticker,
            "instrument": self.config.instrument, "exchange": "perpetual",
            "cycle_count": self._cycle_count, "open_positions": len(open_positions),
            "max_positions": self.config.max_open_positions,
            "current_btc_price": current_price,
            "total_unrealized_pnl": round(total_unrealized, 2),
            "starting_capital": self.config.starting_capital,
            "risk_per_trade_pct": self.config.risk_per_trade_pct,
            "default_quantity": self.config.default_quantity,
            "min_quantity": self.config.min_quantity,
            "max_quantity": self.config.max_quantity,
            "cooldown_minutes": 0, "require_oracle": self.config.require_oracle_approval,
            "market": market_status,
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

    def get_performance(self):
        closed_trades = self.db.get_closed_trades(limit=10000)
        open_positions = self.db.get_open_positions()
        current_price = self.executor.get_current_price()

        unrealized_pnl = 0.0
        if current_price and open_positions:
            for pos in open_positions:
                direction = 1 if pos["side"] == "long" else -1
                # P&L = (current - entry) * quantity * direction
                pnl = (current_price - pos["entry_price"]) * pos.get("quantity", self.config.default_quantity) * direction
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
            "total_trades": len(closed_trades), "open_positions": len(open_positions),
            "wins": len(wins), "losses": len(losses),
            "win_rate": round(len(wins) / len(closed_trades) * 100, 1) if closed_trades else None,
            "total_pnl": round(total_pnl, 2), "realized_pnl": round(realized_pnl, 2),
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
                # P&L = (current - entry) * quantity * direction
                pnl = (current_price - pos["entry_price"]) * pos.get("quantity", self.config.default_quantity) * direction
                total_pnl += pnl
                results.append({"position_id": pos["position_id"], "pnl": round(pnl, 2)})
        return {"closed": len(results), "total_pnl": round(total_pnl, 2), "details": results}

    def enable(self):
        self._enabled = True
        self.db.log("INFO", "ENABLE", "AGAPE-BTC-PERP bot enabled")

    def disable(self):
        self._enabled = False
        self.db.log("INFO", "DISABLE", "AGAPE-BTC-PERP bot disabled")
