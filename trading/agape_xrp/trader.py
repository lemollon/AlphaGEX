"""
AGAPE-XRP Trader - Main orchestrator for XRP Futures trading.

Same logic as AGAPE (ETH) trader but for /XRP contracts.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from zoneinfo import ZoneInfo

from trading.agape_xrp.models import (
    AgapeXrpConfig, AgapeXrpSignal, AgapeXrpPosition,
    PositionSide, PositionStatus, SignalAction, TradingMode,
)
from trading.agape_xrp.db import AgapeXrpDatabase
from trading.agape_xrp.signals import (
    AgapeXrpSignalGenerator, get_agape_xrp_direction_tracker,
    record_agape_xrp_trade_outcome,
)
from trading.agape_xrp.executor import AgapeXrpExecutor

logger = logging.getLogger(__name__)
CENTRAL_TZ = ZoneInfo("America/Chicago")

_agape_xrp_trader: Optional["AgapeXrpTrader"] = None


def get_agape_xrp_trader():
    return _agape_xrp_trader


def create_agape_xrp_trader(config=None):
    global _agape_xrp_trader
    _agape_xrp_trader = AgapeXrpTrader(config)
    return _agape_xrp_trader


class AgapeXrpTrader:
    """Main AGAPE-XRP trading bot orchestrator."""

    def __init__(self, config=None):
        self.db = AgapeXrpDatabase()
        self.config = config or AgapeXrpConfig.load_from_db(self.db)
        self.signals = AgapeXrpSignalGenerator(self.config)
        self.executor = AgapeXrpExecutor(self.config, self.db)
        self._last_scan_time = None
        self._cycle_count = 0
        self._enabled = True
        self.consecutive_losses = 0
        self.loss_streak_pause_until = None
        self._direction_tracker = get_agape_xrp_direction_tracker(self.config)
        self.db.log("INFO", "INIT", f"AGAPE-XRP initialized AGGRESSIVE (mode={self.config.mode.value})")
        logger.info(f"AGAPE-XRP Trader: Initialized AGGRESSIVE (mode={self.config.mode.value})")

    def run_cycle(self, close_only=False):
        self._cycle_count += 1
        now = datetime.now(CENTRAL_TZ)
        self._direction_tracker.update_scan(self._cycle_count)
        result = {"cycle": self._cycle_count, "timestamp": now.isoformat(), "outcome": "UNKNOWN",
                  "positions_managed": 0, "positions_closed": 0, "new_trade": False, "signal": None, "error": None}
        scan_ctx = {}
        try:
            market_data = self.signals.get_market_data()
            if market_data:
                scan_ctx["market_data"] = market_data
                scan_ctx["xrp_price"] = market_data.get("spot_price")
            prophet_data = self.signals.get_prophet_advice(market_data) if market_data else None
            if prophet_data:
                scan_ctx["prophet_data"] = prophet_data
            managed, closed = self._manage_positions(market_data)
            result["positions_managed"] = managed
            result["positions_closed"] = closed
            self._save_equity_snapshot(market_data)
            if close_only:
                result["outcome"] = "CLOSE_ONLY"
                self._log_scan(result, scan_ctx)
                return result
            if self.loss_streak_pause_until and now < self.loss_streak_pause_until:
                result["outcome"] = "LOSS_STREAK_PAUSE"
                self._log_scan(result, scan_ctx)
                return result
            elif self.loss_streak_pause_until:
                self.loss_streak_pause_until = None
            skip = self._check_entry_conditions(now)
            if skip:
                result["outcome"] = skip
                self._log_scan(result, scan_ctx)
                return result
            signal = self.signals.generate_signal(prophet_data=prophet_data)
            result["signal"] = signal.to_dict() if signal else None
            if not signal or not signal.is_valid:
                result["outcome"] = f"NO_SIGNAL_{signal.reasoning if signal else 'NONE'}"
                self._log_scan(result, scan_ctx, signal=signal)
                return result
            position = self.executor.execute_trade(signal)
            if position:
                self.db.save_position(position)
                result["new_trade"] = True
                result["outcome"] = f"TRADED_{signal.side.upper()}"
                scan_ctx["position_id"] = position.position_id
                self.db.log("INFO", "NEW_TRADE",
                    f"{signal.side.upper()} {signal.contracts}x /XRP @ ${position.entry_price:.4f}",
                    details=signal.to_dict())
            else:
                result["outcome"] = "EXECUTION_FAILED"
            self._log_scan(result, scan_ctx, signal=signal)
            return result
        except Exception as e:
            logger.error(f"AGAPE-XRP Trader: Cycle failed: {e}", exc_info=True)
            result["outcome"] = "ERROR"
            result["error"] = str(e)
            self._log_scan(result, scan_ctx)
            return result

    def _manage_positions(self, market_data):
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
        for pos in open_positions:
            try:
                if self.config.use_no_loss_trailing:
                    did_close = self._manage_no_loss_trailing(pos, current_price, now)
                else:
                    should_close, reason = self._check_exit(pos, current_price, now)
                    did_close = self._close_position(pos, current_price, reason) if should_close else False
                if did_close:
                    closed += 1
                else:
                    self._update_hwm(pos, current_price)
            except Exception as e:
                logger.error(f"AGAPE-XRP: Position mgmt error: {e}")
        return (len(open_positions), closed)

    def _manage_no_loss_trailing(self, pos, current_price, now):
        entry = pos["entry_price"]
        is_long = pos["side"] == "long"
        profit_pct = ((current_price - entry) / entry * 100) if is_long else ((entry - current_price) / entry * 100)
        hwm = pos.get("high_water_mark") or entry
        if hwm <= 0:
            hwm = entry
        max_profit_pct = ((hwm - entry) / entry * 100) if is_long and hwm > entry else ((entry - hwm) / entry * 100) if not is_long and hwm < entry else 0
        if self.config.use_sar and -profit_pct >= self.config.sar_trigger_pct and max_profit_pct < self.config.sar_mfe_threshold_pct:
            return self._execute_sar(pos, current_price)
        if -profit_pct >= self.config.max_unrealized_loss_pct:
            return self._close_position(pos, current_price, f"MAX_LOSS_{self.config.max_unrealized_loss_pct}pct")
        if -profit_pct >= self.config.no_loss_emergency_stop_pct:
            return self._close_position(pos, current_price, "EMERGENCY_STOP")
        trailing_active = pos.get("trailing_active", False)
        current_stop = pos.get("current_stop")
        if trailing_active and current_stop:
            if (is_long and current_price <= current_stop) or (not is_long and current_price >= current_stop):
                return self._close_position(pos, current_stop, f"TRAIL_STOP_+{profit_pct:.1f}pct")
        if self.config.no_loss_profit_target_pct > 0 and profit_pct >= self.config.no_loss_profit_target_pct:
            return self._close_position(pos, current_price, f"PROFIT_TARGET_+{profit_pct:.1f}pct")
        if not trailing_active and max_profit_pct >= self.config.no_loss_activation_pct:
            trail_dist = entry * (self.config.no_loss_trail_distance_pct / 100)
            initial_stop = max(entry, hwm - trail_dist) if is_long else min(entry, hwm + trail_dist)
            self.db._execute("UPDATE agape_xrp_positions SET trailing_active = TRUE, current_stop = %s WHERE position_id = %s AND status = 'open'",
                             (round(initial_stop, 4), pos["position_id"]))
            trailing_active = True
            current_stop = initial_stop
        if trailing_active:
            trail_dist = entry * (self.config.no_loss_trail_distance_pct / 100)
            if is_long:
                new_stop = round(hwm - trail_dist, 4)
                if new_stop > (current_stop or 0) and new_stop >= entry:
                    self.db._execute("UPDATE agape_xrp_positions SET current_stop = %s WHERE position_id = %s AND status = 'open'", (new_stop, pos["position_id"]))
            else:
                new_stop = round(hwm + trail_dist, 4)
                if current_stop and new_stop < current_stop and new_stop <= entry:
                    self.db._execute("UPDATE agape_xrp_positions SET current_stop = %s WHERE position_id = %s AND status = 'open'", (new_stop, pos["position_id"]))
        open_time_str = pos.get("open_time")
        if open_time_str:
            try:
                ot = datetime.fromisoformat(open_time_str) if isinstance(open_time_str, str) else open_time_str
                if ot.tzinfo is None:
                    ot = ot.replace(tzinfo=CENTRAL_TZ)
                if (now - ot).total_seconds() / 3600 >= self.config.max_hold_hours:
                    return self._close_position(pos, current_price, "MAX_HOLD_TIME")
            except (ValueError, TypeError):
                pass
        return False

    def _execute_sar(self, pos, current_price):
        entry = pos["entry_price"]
        is_long = pos["side"] == "long"
        sar_pct = self.config.sar_trigger_pct
        close_price = entry * (1 - sar_pct / 100) if is_long else entry * (1 + sar_pct / 100)
        if not self._close_position(pos, close_price, f"SAR_CLOSED_{sar_pct}pct"):
            return False
        rev_side = "short" if is_long else "long"
        ep = self.config.no_loss_emergency_stop_pct
        sl = current_price * (1 - ep / 100) if rev_side == "long" else current_price * (1 + ep / 100)
        tp = current_price * (1 + ep / 100) if rev_side == "long" else current_price * (1 - ep / 100)
        sig = AgapeXrpSignal(
            spot_price=current_price, timestamp=datetime.now(CENTRAL_TZ),
            action=SignalAction.LONG if rev_side == "long" else SignalAction.SHORT,
            confidence="HIGH", reasoning=f"SAR_REVERSAL from {pos['side'].upper()}",
            side=rev_side, entry_price=current_price, stop_loss=sl, take_profit=tp,
            contracts=pos.get("contracts", 1), max_risk_usd=0,
        )
        rev_pos = self.executor.execute_trade(sig)
        if rev_pos:
            self.db.save_position(rev_pos)
            self.db.log("INFO", "SAR_EXECUTED", f"SAR: Reversed to {rev_side.upper()} {rev_pos.position_id}")
        return True

    def _check_exit(self, pos, current_price, now):
        entry, side = pos["entry_price"], pos["side"]
        sl, tp = pos.get("stop_loss"), pos.get("take_profit")
        if sl:
            if (side == "long" and current_price <= sl) or (side == "short" and current_price >= sl):
                return (True, "STOP_LOSS")
        if tp:
            if (side == "long" and current_price >= tp) or (side == "short" and current_price <= tp):
                return (True, "TAKE_PROFIT")
        ot_str = pos.get("open_time")
        if ot_str:
            try:
                ot = datetime.fromisoformat(ot_str) if isinstance(ot_str, str) else ot_str
                if ot.tzinfo is None:
                    ot = ot.replace(tzinfo=CENTRAL_TZ)
                if (now - ot).total_seconds() / 3600 >= self.config.max_hold_hours:
                    return (True, "MAX_HOLD_TIME")
            except (ValueError, TypeError):
                pass
        return (False, "")

    def _close_position(self, pos, current_price, reason):
        pid = pos["position_id"]
        direction = 1 if pos["side"] == "long" else -1
        pnl = round((current_price - pos["entry_price"]) * self.config.contract_size * direction * pos.get("contracts", 1), 2)
        success = self.db.expire_position(pid, pnl, current_price) if reason == "MAX_HOLD_TIME" else self.db.close_position(pid, current_price, pnl, reason)
        if success:
            won = pnl > 0
            if won:
                self.consecutive_losses = 0
                self.loss_streak_pause_until = None
            else:
                self.consecutive_losses += 1
                if self.consecutive_losses >= self.config.max_consecutive_losses:
                    self.loss_streak_pause_until = datetime.now(CENTRAL_TZ) + timedelta(minutes=self.config.loss_streak_pause_minutes)
            record_agape_xrp_trade_outcome(pos["side"].upper(), won, self._cycle_count)
            self.db.log("INFO", "CLOSE", f"Closed {pid} P&L=${pnl:+.2f} ({reason})")
        return success

    def _update_hwm(self, pos, current_price):
        hwm = pos.get("high_water_mark", pos["entry_price"])
        if (pos["side"] == "long" and current_price > hwm) or (pos["side"] == "short" and current_price < hwm):
            self.db.update_high_water_mark(pos["position_id"], current_price)

    def _check_entry_conditions(self, now):
        if not self._enabled:
            return "BOT_DISABLED"
        wd, hr = now.weekday(), now.hour
        if wd == 5:
            return "MARKET_CLOSED_SATURDAY"
        if wd == 6 and hr < 17:
            return "MARKET_CLOSED_SUNDAY_EARLY"
        if wd == 4 and hr >= 16:
            return "MARKET_CLOSED_FRIDAY_LATE"
        if 0 <= wd <= 3 and hr == 16:
            return "DAILY_MAINTENANCE"
        return None

    def _log_scan(self, result, ctx, signal=None):
        md = ctx.get("market_data", {})
        pd = ctx.get("prophet_data", {})
        self.db.log_scan({
            "outcome": result.get("outcome"), "xrp_price": md.get("spot_price"),
            "funding_rate": md.get("funding_rate"), "funding_regime": md.get("funding_regime"),
            "ls_ratio": md.get("ls_ratio"), "ls_bias": md.get("ls_bias"),
            "squeeze_risk": md.get("squeeze_risk"), "leverage_regime": md.get("leverage_regime"),
            "max_pain": md.get("max_pain"), "crypto_gex": md.get("crypto_gex"),
            "crypto_gex_regime": md.get("crypto_gex_regime"),
            "combined_signal": md.get("combined_signal"), "combined_confidence": md.get("combined_confidence"),
            "oracle_advice": pd.get("advice"), "oracle_win_prob": pd.get("win_probability"),
            "signal_action": signal.action.value if signal else None,
            "signal_reasoning": signal.reasoning if signal else None,
            "position_id": ctx.get("position_id"), "error_message": result.get("error"),
        })

    def _save_equity_snapshot(self, market_data):
        try:
            open_pos = self.db.get_open_positions()
            cp = self.executor.get_current_price()
            if not cp and market_data:
                cp = market_data.get("spot_price")
            unrealized = 0.0
            if cp and open_pos:
                for p in open_pos:
                    d = 1 if p["side"] == "long" else -1
                    unrealized += (cp - p["entry_price"]) * self.config.contract_size * d * p.get("contracts", 1)
            closed = self.db.get_closed_trades(limit=10000)
            realized_cum = sum(t.get("realized_pnl", 0) for t in closed) if closed else 0.0
            equity = self.config.starting_capital + realized_cum + unrealized
            self.db.save_equity_snapshot(equity=round(equity, 2), unrealized_pnl=round(unrealized, 2),
                                          realized_cumulative=round(realized_cum, 2), open_positions=len(open_pos),
                                          xrp_price=cp, funding_rate=market_data.get("funding_rate") if market_data else None)
        except Exception as e:
            logger.warning(f"AGAPE-XRP: Snapshot failed: {e}")

    def get_cme_market_status(self, now=None):
        if now is None:
            now = datetime.now(CENTRAL_TZ)
        wd, hr = now.weekday(), now.hour
        sched = "Sun 5:00 PM - Fri 4:00 PM CT (daily 4-5 PM break Mon-Thu)"
        if wd == 5:
            return {"cme_market_open": False, "status": "CLOSED_SATURDAY", "reason": "CME closed Saturday.", "schedule": sched}
        if wd == 6 and hr < 17:
            return {"cme_market_open": False, "status": "CLOSED_SUNDAY_EARLY", "reason": "CME opens at 5:00 PM CT today.", "schedule": sched}
        if wd == 4 and hr >= 16:
            return {"cme_market_open": False, "status": "CLOSED_FRIDAY_LATE", "reason": "CME closed for the weekend.", "schedule": sched}
        if 0 <= wd <= 3 and hr == 16:
            return {"cme_market_open": False, "status": "DAILY_MAINTENANCE", "reason": "CME daily maintenance.", "schedule": sched}
        return {"cme_market_open": True, "status": "OPEN", "reason": "CME XRP Futures market is open.", "schedule": sched}

    def get_status(self):
        now = datetime.now(CENTRAL_TZ)
        open_pos = self.db.get_open_positions()
        cp = self.executor.get_current_price()
        total_unr = 0.0
        if cp and open_pos:
            for p in open_pos:
                d = 1 if p["side"] == "long" else -1
                total_unr += (cp - p["entry_price"]) * self.config.contract_size * d * p.get("contracts", 1)
        closed = self.db.get_closed_trades(limit=10000)
        realized = sum(t.get("realized_pnl", 0) for t in closed) if closed else 0.0
        total_pnl = realized + total_unr
        balance = self.config.starting_capital + total_pnl
        ret = (total_pnl / self.config.starting_capital * 100) if self.config.starting_capital else 0
        wins = [t for t in closed if (t.get("realized_pnl") or 0) > 0] if closed else []
        wr = round(len(wins) / len(closed) * 100, 1) if closed else None
        return {
            "bot_name": "AGAPE_XRP", "status": "ACTIVE" if self._enabled else "DISABLED",
            "mode": self.config.mode.value, "ticker": "XRP", "instrument": "/XRP",
            "exchange": "tastytrade", "cycle_count": self._cycle_count,
            "open_positions": len(open_pos), "current_xrp_price": cp,
            "total_unrealized_pnl": round(total_unr, 2),
            "starting_capital": self.config.starting_capital,
            "risk_per_trade_pct": self.config.risk_per_trade_pct,
            "max_contracts": self.config.max_contracts, "cooldown_minutes": 0,
            "require_oracle": self.config.require_oracle_approval,
            "market": self.get_cme_market_status(now),
            "paper_account": {
                "starting_capital": self.config.starting_capital,
                "current_balance": round(balance, 2), "cumulative_pnl": round(total_pnl, 2),
                "realized_pnl": round(realized, 2), "unrealized_pnl": round(total_unr, 2),
                "return_pct": round(ret, 2), "total_trades": len(closed) if closed else 0, "win_rate": wr,
            },
            "aggressive_features": {
                "use_no_loss_trailing": self.config.use_no_loss_trailing,
                "use_sar": self.config.use_sar,
                "direction_tracker": self._direction_tracker.get_status(),
                "consecutive_losses": self.consecutive_losses,
                "loss_streak_paused": self.loss_streak_pause_until is not None and now < self.loss_streak_pause_until,
            },
            "positions": open_pos,
        }

    def get_performance(self):
        closed = self.db.get_closed_trades(limit=10000)
        open_pos = self.db.get_open_positions()
        cp = self.executor.get_current_price()
        unr = 0.0
        if cp and open_pos:
            for p in open_pos:
                d = 1 if p["side"] == "long" else -1
                unr += (cp - p["entry_price"]) * self.config.contract_size * d * p.get("contracts", 1)
        if not closed:
            return {"total_trades": 0, "open_positions": len(open_pos), "win_rate": None,
                    "total_pnl": round(unr, 2), "realized_pnl": 0, "unrealized_pnl": round(unr, 2),
                    "avg_win": 0, "avg_loss": 0, "best_trade": 0, "worst_trade": 0, "profit_factor": 0,
                    "return_pct": round(unr / self.config.starting_capital * 100, 2)}
        wins = [t for t in closed if (t.get("realized_pnl") or 0) > 0]
        losses = [t for t in closed if (t.get("realized_pnl") or 0) <= 0]
        realized = sum(t.get("realized_pnl", 0) for t in closed)
        tw = sum(t.get("realized_pnl", 0) for t in wins) if wins else 0
        tl = abs(sum(t.get("realized_pnl", 0) for t in losses)) if losses else 0
        return {
            "total_trades": len(closed), "open_positions": len(open_pos),
            "wins": len(wins), "losses": len(losses),
            "win_rate": round(len(wins) / len(closed) * 100, 1),
            "total_pnl": round(realized + unr, 2), "realized_pnl": round(realized, 2),
            "unrealized_pnl": round(unr, 2),
            "avg_win": round(tw / len(wins), 2) if wins else 0,
            "avg_loss": round(tl / len(losses), 2) if losses else 0,
            "best_trade": max((t.get("realized_pnl", 0) for t in closed), default=0),
            "worst_trade": min((t.get("realized_pnl", 0) for t in closed), default=0),
            "profit_factor": round(tw / tl, 2) if tl > 0 else float("inf"),
            "return_pct": round((realized + unr) / self.config.starting_capital * 100, 2),
        }

    def force_close_all(self, reason="MANUAL_CLOSE"):
        cp = self.executor.get_current_price()
        if not cp:
            return {"error": "No price", "closed": 0}
        results = []
        for pos in self.db.get_open_positions():
            if self._close_position(pos, cp, reason):
                d = 1 if pos["side"] == "long" else -1
                pnl = (cp - pos["entry_price"]) * self.config.contract_size * d * pos.get("contracts", 1)
                results.append({"position_id": pos["position_id"], "pnl": round(pnl, 2)})
        return {"closed": len(results), "total_pnl": round(sum(r["pnl"] for r in results), 2), "details": results}

    def enable(self):
        self._enabled = True
        self.db.log("INFO", "ENABLE", "AGAPE-XRP enabled")

    def disable(self):
        self._enabled = False
        self.db.log("INFO", "DISABLE", "AGAPE-XRP disabled")
