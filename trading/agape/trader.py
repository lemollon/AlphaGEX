"""
AGAPE Trader - Main orchestrator for ETH Micro Futures trading.

Follows the ARES V2 pattern:
  scan → signal → oracle → execute → log → manage positions

Runs on a 5-minute cycle (configurable), trading /MET contracts
via tastytrade based on crypto market microstructure signals.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
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
from trading.agape.signals import AgapeSignalGenerator
from trading.agape.executor import AgapeExecutor

logger = logging.getLogger(__name__)

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

    Lifecycle:
      1. Init: Load config → create DB → create signal generator → create executor
      2. Run Cycle: Called every 5 min by scheduler
         a. Manage existing positions (check exits)
         b. Check entry conditions (time, cooldown, position limits)
         c. Generate signal (crypto microstructure analysis)
         d. Consult Oracle (if enabled)
         e. Execute trade (if signal valid)
         f. Log everything (scan activity)
      3. Record outcomes for ML feedback loop
    """

    def __init__(self, config: Optional[AgapeConfig] = None):
        self.db = AgapeDatabase()

        if config:
            self.config = config
        else:
            self.config = AgapeConfig.load_from_db(self.db)

        self.signals = AgapeSignalGenerator(self.config)
        self.executor = AgapeExecutor(self.config, self.db)

        self._last_scan_time: Optional[datetime] = None
        self._cycle_count: int = 0
        self._enabled: bool = True

        self.db.log("INFO", "INIT", f"AGAPE trader initialized (mode={self.config.mode.value})")
        logger.info(f"AGAPE Trader: Initialized (mode={self.config.mode.value})")

    def run_cycle(self, close_only: bool = False) -> Dict[str, Any]:
        """Execute one trading cycle.

        This is called by the scheduler every 5 minutes.
        Returns a dict with the cycle result for monitoring.
        """
        self._cycle_count += 1
        now = datetime.now(CENTRAL_TZ)
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

            # Step 2: Get Oracle advice early (avoid double-fetching)
            oracle_data = None
            if market_data:
                oracle_data = self.signals.get_oracle_advice(market_data)
                scan_context["oracle_data"] = oracle_data

            # Step 3: Manage existing positions FIRST
            managed, closed = self._manage_positions(market_data)
            result["positions_managed"] = managed
            result["positions_closed"] = closed

            # If close_only mode, stop here
            if close_only:
                result["outcome"] = "CLOSE_ONLY"
                self._log_scan(result, scan_context)
                return result

            # Step 4: Check basic entry conditions
            skip_reason = self._check_entry_conditions(now)
            if skip_reason:
                result["outcome"] = skip_reason
                self._log_scan(result, scan_context)
                return result

            # Step 5: Generate signal with pre-fetched Oracle data
            signal = self.signals.generate_signal(oracle_data=oracle_data)
            result["signal"] = signal.to_dict() if signal else None

            if not signal or not signal.is_valid:
                result["outcome"] = f"NO_SIGNAL_{signal.reasoning if signal else 'NONE'}"
                self._log_scan(result, scan_context, signal=signal)
                return result

            # Step 6: Execute the trade
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

    def _manage_positions(self, market_data: Optional[Dict]) -> tuple:
        """Check and manage all open positions.

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
                should_close, reason = self._check_exit_conditions(
                    pos_dict, current_price, now
                )
                if should_close:
                    success = self._close_position(pos_dict, current_price, reason)
                    if success:
                        closed += 1
                else:
                    # Update high water mark for trailing stop
                    self._update_hwm(pos_dict, current_price)
            except Exception as e:
                logger.error(f"AGAPE Trader: Position management error: {e}")

        return (len(open_positions), closed)

    def _check_exit_conditions(
        self, pos: Dict, current_price: float, now: datetime
    ) -> tuple:
        """Check if a position should be closed.

        Returns (should_close: bool, reason: str).
        """
        entry_price = pos["entry_price"]
        side = pos["side"]
        stop_loss = pos.get("stop_loss")
        take_profit = pos.get("take_profit")
        open_time_str = pos.get("open_time")

        # Direction multiplier
        if side == "long":
            direction = 1
        else:
            direction = -1

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

        # 4. Trailing stop (if configured)
        if self.config.trailing_stop_pct > 0:
            hwm = pos.get("high_water_mark", entry_price)
            trail_distance = hwm * (self.config.trailing_stop_pct / 100)
            if side == "long" and current_price < (hwm - trail_distance):
                return (True, "TRAILING_STOP")
            elif side == "short" and current_price > (hwm + trail_distance):
                return (True, "TRAILING_STOP")

        return (False, "")

    def _close_position(
        self, pos_dict: Dict, current_price: float, reason: str
    ) -> bool:
        """Close a position and record the outcome."""
        position_id = pos_dict["position_id"]
        entry_price = pos_dict["entry_price"]
        side = pos_dict["side"]
        contracts = pos_dict.get("contracts", 1)

        # Calculate P&L
        direction = 1 if side == "long" else -1
        pnl_per_contract = (current_price - entry_price) * 0.1 * direction
        realized_pnl = round(pnl_per_contract * contracts, 2)

        # Simulate close via executor
        success = self.db.close_position(
            position_id, current_price, realized_pnl, reason
        )

        if success:
            self.db.log(
                "INFO", "CLOSE_POSITION",
                f"Closed {position_id} @ ${current_price:.2f} P&L=${realized_pnl:+.2f} ({reason})",
                details={"position_id": position_id, "realized_pnl": realized_pnl, "reason": reason},
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

    def _check_entry_conditions(self, now: datetime) -> Optional[str]:
        """Check if conditions allow new entries.

        Returns skip reason string, or None if conditions are met.
        """
        if not self._enabled:
            return "BOT_DISABLED"

        # Check position limits
        open_count = self.db.get_position_count()
        if open_count >= self.config.max_open_positions:
            return f"MAX_POSITIONS_{open_count}"

        # Check cooldown
        if self.db.has_traded_recently(self.config.cooldown_minutes):
            return "COOLDOWN"

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

        # Friday: market closes at 4 PM CT
        if weekday == 4 and (hour > 16 or (hour == 16 and minute > 0)):
            return "MARKET_CLOSED_FRIDAY_LATE"

        # Daily maintenance break: 4 PM - 5 PM CT (Mon-Thu)
        if 0 <= weekday <= 3 and hour == 16:
            return "DAILY_MAINTENANCE"

        return None

    def _log_scan(
        self,
        result: Dict,
        context: Dict,
        signal: Optional[AgapeSignal] = None,
    ):
        """Log the scan cycle for visibility."""
        market = context.get("market_data", {})
        oracle = context.get("oracle_data", {})

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
            "oracle_advice": oracle.get("advice"),
            "oracle_win_prob": oracle.get("win_probability"),
            "signal_action": signal.action.value if signal else None,
            "signal_reasoning": signal.reasoning if signal else None,
            "position_id": context.get("position_id"),
            "error_message": result.get("error"),
        }
        self.db.log_scan(scan_data)

    # ------------------------------------------------------------------
    # Status & Performance (for API routes)
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Get bot status for API."""
        open_positions = self.db.get_open_positions()
        current_price = self.executor.get_current_price()

        # Calculate unrealized P&L
        total_unrealized = 0.0
        if current_price and open_positions:
            for pos in open_positions:
                direction = 1 if pos["side"] == "long" else -1
                pnl = (current_price - pos["entry_price"]) * 0.1 * direction * pos.get("contracts", 1)
                total_unrealized += pnl

        return {
            "bot_name": "AGAPE",
            "status": "ACTIVE" if self._enabled else "DISABLED",
            "mode": self.config.mode.value,
            "ticker": self.config.ticker,
            "instrument": self.config.instrument,
            "cycle_count": self._cycle_count,
            "open_positions": len(open_positions),
            "max_positions": self.config.max_open_positions,
            "current_eth_price": current_price,
            "total_unrealized_pnl": round(total_unrealized, 2),
            "starting_capital": self.config.starting_capital,
            "risk_per_trade_pct": self.config.risk_per_trade_pct,
            "max_contracts": self.config.max_contracts,
            "cooldown_minutes": self.config.cooldown_minutes,
            "require_oracle": self.config.require_oracle_approval,
            "positions": open_positions,
        }

    def get_performance(self) -> Dict[str, Any]:
        """Get performance statistics for API."""
        closed_trades = self.db.get_closed_trades(limit=1000)
        if not closed_trades:
            return {
                "total_trades": 0,
                "win_rate": 0,
                "total_pnl": 0,
                "avg_win": 0,
                "avg_loss": 0,
                "best_trade": 0,
                "worst_trade": 0,
                "profit_factor": 0,
            }

        wins = [t for t in closed_trades if (t.get("realized_pnl") or 0) > 0]
        losses = [t for t in closed_trades if (t.get("realized_pnl") or 0) <= 0]
        total_pnl = sum(t.get("realized_pnl", 0) for t in closed_trades)
        total_wins = sum(t.get("realized_pnl", 0) for t in wins) if wins else 0
        total_losses = abs(sum(t.get("realized_pnl", 0) for t in losses)) if losses else 0

        return {
            "total_trades": len(closed_trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(closed_trades) * 100, 1) if closed_trades else 0,
            "total_pnl": round(total_pnl, 2),
            "avg_win": round(total_wins / len(wins), 2) if wins else 0,
            "avg_loss": round(total_losses / len(losses), 2) if losses else 0,
            "best_trade": max((t.get("realized_pnl", 0) for t in closed_trades), default=0),
            "worst_trade": min((t.get("realized_pnl", 0) for t in closed_trades), default=0),
            "profit_factor": round(total_wins / total_losses, 2) if total_losses > 0 else float("inf"),
            "return_pct": round(total_pnl / self.config.starting_capital * 100, 2),
        }

    def get_equity_curve(self) -> List[Dict]:
        """Build historical equity curve from closed trades."""
        closed_trades = self.db.get_closed_trades(limit=10000)
        if not closed_trades:
            return []

        starting_capital = self.db.get_starting_capital()
        cumulative_pnl = 0
        curve = []

        # Trades come DESC, reverse for chronological
        for trade in reversed(closed_trades):
            pnl = trade.get("realized_pnl", 0)
            cumulative_pnl += pnl
            equity = starting_capital + cumulative_pnl

            curve.append({
                "timestamp": trade.get("close_time"),
                "equity": round(equity, 2),
                "cumulative_pnl": round(cumulative_pnl, 2),
                "trade_pnl": round(pnl, 2),
                "return_pct": round(cumulative_pnl / starting_capital * 100, 2),
            })

        return curve

    def enable(self):
        self._enabled = True
        self.db.log("INFO", "ENABLE", "AGAPE bot enabled")

    def disable(self):
        self._enabled = False
        self.db.log("INFO", "DISABLE", "AGAPE bot disabled")
