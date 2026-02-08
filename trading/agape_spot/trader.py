"""
AGAPE-SPOT Trader - Multi-ticker, long-only 24/7 Coinbase Spot trading.

MULTI-TICKER: Iterates config.tickers each cycle (ETH-USD, XRP-USD, SHIB-USD, DOGE-USD).
LONG-ONLY: Coinbase spot doesn't support shorting for US retail.
P&L = (exit - entry) * quantity. No direction multiplier.

Per-ticker state: loss streak counters, direction trackers, equity tracking.
No SAR logic (can't reverse to short on spot).

Runs on a 5-minute cycle called by the scheduler.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from zoneinfo import ZoneInfo

from trading.agape_spot.models import (
    AgapeSpotConfig,
    AgapeSpotSignal,
    AgapeSpotPosition,
    PositionStatus,
    SignalAction,
    TradingMode,
    SPOT_TICKERS,
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

# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_agape_spot_trader: Optional["AgapeSpotTrader"] = None


def get_agape_spot_trader() -> Optional["AgapeSpotTrader"]:
    return _agape_spot_trader


def create_agape_spot_trader(config: Optional[AgapeSpotConfig] = None) -> "AgapeSpotTrader":
    global _agape_spot_trader
    _agape_spot_trader = AgapeSpotTrader(config)
    return _agape_spot_trader


# ---------------------------------------------------------------------------
# Trader
# ---------------------------------------------------------------------------

class AgapeSpotTrader:
    """Multi-ticker, long-only 24/7 Coinbase Spot trading bot.

    LONG-ONLY: Coinbase spot doesn't support shorting for US retail.
    MULTI-TICKER: Iterates config.tickers each cycle.
    No-loss trailing, loss-streak protection, direction tracker -- all per-ticker.
    No SAR (can't reverse to short on spot).
    """

    def __init__(self, config: Optional[AgapeSpotConfig] = None):
        self.db = AgapeSpotDatabase()

        if config:
            self.config = config
        else:
            self.config = AgapeSpotConfig.load_from_db(self.db)

        self.signals = AgapeSpotSignalGenerator(self.config)
        self.executor = AgapeSpotExecutor(self.config, self.db)

        self._cycle_count: int = 0
        self._enabled: bool = True

        # Per-ticker state
        self._loss_streaks: Dict[str, int] = {}
        self._loss_pause_until: Dict[str, Optional[datetime]] = {}
        self._direction_trackers: Dict[str, Any] = {}

        # Initialize per-ticker state for every configured ticker
        for ticker in self.config.tickers:
            self._loss_streaks[ticker] = 0
            self._loss_pause_until[ticker] = None
            self._direction_trackers[ticker] = get_spot_direction_tracker(ticker, self.config)

        self.db.log(
            "INFO", "INIT",
            f"AGAPE-SPOT trader initialized (mode={self.config.mode.value}, "
            f"tickers={self.config.tickers}, 24/7 Coinbase spot, LONG-ONLY)",
        )
        logger.info(
            f"AGAPE-SPOT: Initialized (mode={self.config.mode.value}, "
            f"tickers={self.config.tickers}, "
            f"max_pos_per_ticker={self.config.max_open_positions_per_ticker}, "
            f"oracle_required={self.config.require_oracle_approval})"
        )

    # ==================================================================
    # Top-level cycle -- iterates ALL tickers
    # ==================================================================

    def run_cycle(self, close_only: bool = False) -> Dict[str, Any]:
        """Execute one trading cycle for ALL configured tickers."""
        self._cycle_count += 1
        now = datetime.now(CENTRAL_TZ)

        results: Dict[str, Any] = {
            "cycle": self._cycle_count,
            "timestamp": now.isoformat(),
            "tickers": {},
            "total_positions_managed": 0,
            "total_positions_closed": 0,
            "total_new_trades": 0,
            "errors": [],
        }

        for ticker in self.config.tickers:
            try:
                ticker_result = self._run_ticker_cycle(ticker, close_only)
                results["tickers"][ticker] = ticker_result
                results["total_positions_managed"] += ticker_result.get("positions_managed", 0)
                results["total_positions_closed"] += ticker_result.get("positions_closed", 0)
                if ticker_result.get("new_trade"):
                    results["total_new_trades"] += 1
            except Exception as e:
                logger.error(f"AGAPE-SPOT: Cycle failed for {ticker}: {e}", exc_info=True)
                results["tickers"][ticker] = {"outcome": "ERROR", "error": str(e)}
                results["errors"].append(f"{ticker}: {e}")
                self.db.log("ERROR", "CYCLE_ERROR", f"{ticker}: {e}")

        return results

    # ==================================================================
    # Per-ticker cycle
    # ==================================================================

    def _run_ticker_cycle(self, ticker: str, close_only: bool = False) -> Dict[str, Any]:
        """Execute one trading cycle for a single ticker."""
        now = datetime.now(CENTRAL_TZ)

        # Update direction tracker for this ticker
        tracker = self._get_direction_tracker(ticker)
        tracker.update_scan(self._cycle_count)

        result: Dict[str, Any] = {
            "ticker": ticker,
            "cycle": self._cycle_count,
            "timestamp": now.isoformat(),
            "outcome": "UNKNOWN",
            "positions_managed": 0,
            "positions_closed": 0,
            "new_trade": False,
            "signal": None,
            "error": None,
        }

        scan_context: Dict[str, Any] = {"ticker": ticker}

        try:
            # Step 1: Fetch market data for this ticker
            market_data = self._get_market_data(ticker)
            if market_data:
                scan_context["market_data"] = market_data
                scan_context["spot_price"] = market_data.get("spot_price")

            # Step 2: Get Oracle advice
            oracle_data = None
            if market_data:
                oracle_data = self.signals.get_oracle_advice(market_data)
                scan_context["oracle_data"] = oracle_data

            # Step 3: Manage existing positions for this ticker
            managed, closed = self._manage_positions(ticker, market_data)
            result["positions_managed"] = managed
            result["positions_closed"] = closed

            # Save equity snapshot for this ticker
            self._save_equity_snapshot(ticker, market_data)

            if close_only:
                result["outcome"] = "CLOSE_ONLY"
                self._log_scan(ticker, result, scan_context)
                return result

            # Step 4: Check loss streak pause for this ticker
            pause_until = self._loss_pause_until.get(ticker)
            if pause_until:
                if now < pause_until:
                    remaining = (pause_until - now).total_seconds() / 60
                    result["outcome"] = f"LOSS_STREAK_PAUSE_{remaining:.1f}min"
                    self._log_scan(ticker, result, scan_context)
                    return result
                else:
                    self._loss_pause_until[ticker] = None

            # Step 5: Check entry conditions (24/7 -- mostly just enabled check)
            skip_reason = self._check_entry_conditions(ticker, now)
            if skip_reason:
                result["outcome"] = skip_reason
                self._log_scan(ticker, result, scan_context)
                return result

            # Step 6: Check max positions for this ticker
            open_positions = self._get_open_positions_for_ticker(ticker)
            if len(open_positions) >= self.config.max_open_positions_per_ticker:
                result["outcome"] = f"MAX_POSITIONS_{len(open_positions)}"
                self._log_scan(ticker, result, scan_context)
                return result

            # Step 7: Generate signal for this ticker
            signal = self._generate_signal(ticker, oracle_data)
            result["signal"] = signal.to_dict() if signal else None

            if not signal or not signal.is_valid:
                result["outcome"] = f"NO_SIGNAL_{signal.reasoning if signal else 'NONE'}"
                self._log_scan(ticker, result, scan_context, signal=signal)
                return result

            # Step 8: Execute trade (always LONG)
            position = self.executor.execute_trade(signal)
            if position:
                self.db.save_position(position)
                result["new_trade"] = True
                result["outcome"] = f"TRADED_LONG_{ticker}"
                result["position_id"] = position.position_id
                scan_context["position_id"] = position.position_id

                notional = signal.quantity * position.entry_price
                self.db.log(
                    "INFO", "NEW_TRADE",
                    f"LONG {ticker} {signal.quantity} @ ${position.entry_price:.2f} "
                    f"(${notional:.2f})",
                    details=signal.to_dict(),
                )
            else:
                result["outcome"] = "EXECUTION_FAILED"

            self._log_scan(ticker, result, scan_context, signal=signal)
            return result

        except Exception as e:
            logger.error(f"AGAPE-SPOT: Ticker cycle failed ({ticker}): {e}", exc_info=True)
            result["outcome"] = "ERROR"
            result["error"] = str(e)
            self.db.log("ERROR", "CYCLE_ERROR", f"{ticker}: {e}")
            self._log_scan(ticker, result, scan_context)
            return result

    # ==================================================================
    # Per-ticker state helpers
    # ==================================================================

    def _get_direction_tracker(self, ticker: str):
        """Get or create a direction tracker for a given ticker."""
        if ticker not in self._direction_trackers:
            self._direction_trackers[ticker] = get_spot_direction_tracker(ticker, self.config)
        return self._direction_trackers[ticker]

    def _get_open_positions_for_ticker(self, ticker: str) -> List[Dict]:
        """Get open positions filtered to a single ticker."""
        try:
            return self.db.get_open_positions(ticker=ticker)
        except TypeError:
            # DB layer does not yet accept ticker keyword -- filter in Python
            all_positions = self.db.get_open_positions()
            return [p for p in all_positions if p.get("ticker") == ticker]

    def _get_closed_trades_for_ticker(
        self, ticker: str, limit: int = 10000,
    ) -> List[Dict]:
        """Get closed trades filtered to a single ticker."""
        try:
            return self.db.get_closed_trades(ticker=ticker, limit=limit)
        except TypeError:
            all_trades = self.db.get_closed_trades(limit=limit)
            return [t for t in all_trades if t.get("ticker") == ticker]

    def _get_current_price(
        self, ticker: str, market_data: Optional[Dict],
    ) -> Optional[float]:
        """Get the current spot price for *ticker*."""
        try:
            price = self.executor.get_current_price(ticker)
            if price:
                return price
        except TypeError:
            # Executor does not yet accept ticker keyword
            price = self.executor.get_current_price()
            if price:
                return price

        if market_data:
            return market_data.get("spot_price")
        return None

    def _get_market_data(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Get market data for *ticker* via the signal generator."""
        try:
            return self.signals.get_market_data(ticker)
        except TypeError:
            # Signal generator does not yet accept ticker keyword
            return self.signals.get_market_data()

    def _generate_signal(
        self, ticker: str, oracle_data: Optional[Dict],
    ) -> Optional[AgapeSpotSignal]:
        """Generate a trading signal for *ticker*."""
        try:
            return self.signals.generate_signal(ticker=ticker, oracle_data=oracle_data)
        except TypeError:
            return self.signals.generate_signal(oracle_data=oracle_data)

    # ==================================================================
    # Position management (LONG-ONLY)
    # ==================================================================

    def _manage_positions(
        self, ticker: str, market_data: Optional[Dict],
    ) -> tuple:
        """Manage open positions for a specific ticker. Long-only."""
        open_positions = self._get_open_positions_for_ticker(ticker)
        if not open_positions:
            return (0, 0)

        current_price = self._get_current_price(ticker, market_data)
        if not current_price:
            return (len(open_positions), 0)

        closed = 0
        now = datetime.now(CENTRAL_TZ)

        for pos_dict in open_positions:
            try:
                if self.config.use_no_loss_trailing:
                    did_close = self._manage_no_loss_trailing(
                        ticker, pos_dict, current_price, now,
                    )
                else:
                    should_close, reason = self._check_exit_conditions(
                        pos_dict, current_price, now,
                    )
                    did_close = False
                    if should_close:
                        did_close = self._close_position(
                            ticker, pos_dict, current_price, reason,
                        )

                if did_close:
                    closed += 1
                else:
                    self._update_hwm(pos_dict, current_price)
            except Exception as e:
                logger.error(
                    f"AGAPE-SPOT: Position management error ({ticker}): {e}"
                )

        return (len(open_positions), closed)

    # ------------------------------------------------------------------
    # No-loss trailing (LONG-ONLY -- simplified)
    # ------------------------------------------------------------------

    def _manage_no_loss_trailing(
        self,
        ticker: str,
        pos: Dict,
        current_price: float,
        now: datetime,
    ) -> bool:
        """No-loss trailing stop management. LONG-ONLY.

        profit_pct   = (current - entry) / entry * 100
        hwm          = highest price seen (only updates when price goes up)
        Trail stop   = hwm - trail_distance, ratchets UP only.
        Close when   current_price <= current_stop.
        """
        entry_price = pos["entry_price"]
        position_id = pos["position_id"]

        # Long-only profit
        profit_pct = ((current_price - entry_price) / entry_price) * 100

        hwm = pos.get("high_water_mark") or entry_price
        if hwm <= 0:
            hwm = entry_price

        # Max profit from HWM (long-only: hwm > entry means profit)
        max_profit_pct = (
            ((hwm - entry_price) / entry_price) * 100
            if hwm > entry_price
            else 0
        )

        # ---- Max unrealized loss ----
        max_loss_pct = self.config.max_unrealized_loss_pct
        if -profit_pct >= max_loss_pct:
            stop_price = entry_price * (1 - max_loss_pct / 100)
            return self._close_position(
                ticker, pos, stop_price, f"MAX_LOSS_{max_loss_pct}pct",
            )

        # ---- Emergency stop ----
        emergency_pct = self.config.no_loss_emergency_stop_pct
        if -profit_pct >= emergency_pct:
            stop_price = entry_price * (1 - emergency_pct / 100)
            return self._close_position(ticker, pos, stop_price, "EMERGENCY_STOP")

        # ---- Trailing stop hit? ----
        trailing_active = pos.get("trailing_active", False)
        current_stop = pos.get("current_stop")

        if trailing_active and current_stop:
            if current_price <= current_stop:
                exit_pnl_pct = ((current_stop - entry_price) / entry_price) * 100
                return self._close_position(
                    ticker, pos, current_stop,
                    f"TRAIL_STOP_+{exit_pnl_pct:.1f}pct",
                )

        # ---- Profit target ----
        profit_target_pct = self.config.no_loss_profit_target_pct
        if profit_target_pct > 0 and profit_pct >= profit_target_pct:
            return self._close_position(
                ticker, pos, current_price,
                f"PROFIT_TARGET_+{profit_pct:.1f}pct",
            )

        # ---- Activate trailing ----
        activation_pct = self.config.no_loss_activation_pct
        if not trailing_active and max_profit_pct >= activation_pct:
            trail_distance_pct = self.config.no_loss_trail_distance_pct
            trail_distance = entry_price * (trail_distance_pct / 100)

            # Long-only: stop below HWM, never below entry
            initial_stop = max(entry_price, hwm - trail_distance)
            initial_stop = round(initial_stop, 2)

            self.db.update_high_water_mark(position_id, hwm)
            try:
                self.db._execute(
                    """UPDATE agape_spot_positions
                       SET trailing_active = TRUE, current_stop = %s
                       WHERE position_id = %s AND status = 'open'""",
                    (initial_stop, position_id),
                )
            except Exception:
                pass
            trailing_active = True
            current_stop = initial_stop

        # ---- Ratchet trailing stop UP (long-only: only moves up) ----
        if trailing_active:
            trail_distance_pct = self.config.no_loss_trail_distance_pct
            trail_distance = entry_price * (trail_distance_pct / 100)

            new_stop = round(hwm - trail_distance, 2)
            if new_stop > (current_stop or 0) and new_stop >= entry_price:
                try:
                    self.db._execute(
                        "UPDATE agape_spot_positions SET current_stop = %s "
                        "WHERE position_id = %s AND status = 'open'",
                        (new_stop, position_id),
                    )
                except Exception:
                    pass

        # ---- Max hold time ----
        open_time_str = pos.get("open_time")
        if open_time_str:
            try:
                if isinstance(open_time_str, str):
                    open_time = datetime.fromisoformat(open_time_str)
                else:
                    open_time = open_time_str
                if open_time.tzinfo is None:
                    open_time = open_time.replace(tzinfo=CENTRAL_TZ)
                hold_hours = (
                    datetime.now(CENTRAL_TZ) - open_time
                ).total_seconds() / 3600
                if hold_hours >= self.config.max_hold_hours:
                    return self._close_position(
                        ticker, pos, current_price, "MAX_HOLD_TIME",
                    )
            except (ValueError, TypeError):
                pass

        return False

    # ------------------------------------------------------------------
    # Basic exit conditions (non-trailing mode, LONG-ONLY)
    # ------------------------------------------------------------------

    def _check_exit_conditions(
        self, pos: Dict, current_price: float, now: datetime,
    ) -> tuple:
        """Check basic stop / target / time exits. LONG-ONLY."""
        stop_loss = pos.get("stop_loss")
        take_profit = pos.get("take_profit")

        # Long-only: stop loss below entry, take profit above entry
        if stop_loss and current_price <= stop_loss:
            return (True, "STOP_LOSS")

        if take_profit and current_price >= take_profit:
            return (True, "TAKE_PROFIT")

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
                hold_hours = (now - open_time).total_seconds() / 3600
                if hold_hours >= self.config.max_hold_hours:
                    return (True, "MAX_HOLD_TIME")
            except (ValueError, TypeError):
                pass

        return (False, "")

    # ------------------------------------------------------------------
    # Close position (LONG-ONLY P&L)
    # ------------------------------------------------------------------

    def _close_position(
        self,
        ticker: str,
        pos_dict: Dict,
        current_price: float,
        reason: str,
    ) -> bool:
        """Close a position. LONG-ONLY: P&L = (current - entry) * quantity."""
        position_id = pos_dict["position_id"]
        entry_price = pos_dict["entry_price"]
        quantity = pos_dict.get("quantity", pos_dict.get("eth_quantity", 0))

        # Long-only P&L -- no direction multiplier
        realized_pnl = round((current_price - entry_price) * quantity, 2)

        if reason == "MAX_HOLD_TIME":
            success = self.db.expire_position(position_id, realized_pnl, current_price)
        else:
            success = self.db.close_position(
                position_id, current_price, realized_pnl, reason,
            )

        if success:
            won = realized_pnl > 0

            # Per-ticker loss streak tracking
            if won:
                prev_streak = self._loss_streaks.get(ticker, 0)
                if prev_streak > 0:
                    logger.info(
                        f"AGAPE-SPOT: Loss streak reset for {ticker} "
                        f"(was {prev_streak})"
                    )
                self._loss_streaks[ticker] = 0
                self._loss_pause_until[ticker] = None
            else:
                self._loss_streaks[ticker] = self._loss_streaks.get(ticker, 0) + 1
                if self._loss_streaks[ticker] >= self.config.max_consecutive_losses:
                    pause_min = self.config.loss_streak_pause_minutes
                    self._loss_pause_until[ticker] = (
                        datetime.now(CENTRAL_TZ) + timedelta(minutes=pause_min)
                    )
                    logger.warning(
                        f"AGAPE-SPOT: {ticker} loss streak "
                        f"{self._loss_streaks[ticker]} -- "
                        f"pausing for {pause_min} minutes"
                    )

            record_spot_trade_outcome(
                direction="LONG",
                is_win=won,
                scan_number=self._cycle_count,
            )

            self.db.log(
                "INFO", "CLOSE_POSITION",
                f"Closed {ticker} {position_id} @ ${current_price:.2f} "
                f"P&L=${realized_pnl:+.2f} ({reason})",
                details={
                    "position_id": position_id,
                    "ticker": ticker,
                    "realized_pnl": realized_pnl,
                    "reason": reason,
                },
            )

        return success

    # ------------------------------------------------------------------
    # HWM update (LONG-ONLY: only when price goes UP)
    # ------------------------------------------------------------------

    def _update_hwm(self, pos_dict: Dict, current_price: float):
        """Update high water mark. Long-only: only when current > hwm."""
        hwm = pos_dict.get("high_water_mark", pos_dict["entry_price"])
        if current_price > hwm:
            self.db.update_high_water_mark(pos_dict["position_id"], current_price)

    # ------------------------------------------------------------------
    # Entry conditions
    # ------------------------------------------------------------------

    def _check_entry_conditions(
        self, ticker: str, now: datetime,
    ) -> Optional[str]:
        """24/7 bot -- minimal entry checks."""
        if not self._enabled:
            return "BOT_DISABLED"
        # No market hours restriction -- 24/7/365
        return None

    # ==================================================================
    # Equity snapshot (per-ticker)
    # ==================================================================

    def _save_equity_snapshot(
        self, ticker: str, market_data: Optional[Dict],
    ):
        """Save equity snapshot for a specific ticker."""
        try:
            open_positions = self._get_open_positions_for_ticker(ticker)
            current_price = self._get_current_price(ticker, market_data)

            unrealized = 0.0
            if current_price and open_positions:
                for pos in open_positions:
                    quantity = pos.get("quantity", pos.get("eth_quantity", 0))
                    # Long-only P&L
                    pnl = (current_price - pos["entry_price"]) * quantity
                    unrealized += pnl

            closed = self._get_closed_trades_for_ticker(ticker)
            realized_cum = (
                sum(t.get("realized_pnl", 0) for t in closed) if closed else 0.0
            )

            starting_capital = self.config.get_starting_capital(ticker)
            equity = starting_capital + realized_cum + unrealized
            funding_rate = market_data.get("funding_rate") if market_data else None

            # Try passing ticker; fall back if DB doesn't accept it yet
            try:
                self.db.save_equity_snapshot(
                    equity=round(equity, 2),
                    unrealized_pnl=round(unrealized, 2),
                    realized_cumulative=round(realized_cum, 2),
                    open_positions=len(open_positions),
                    eth_price=current_price,
                    funding_rate=funding_rate,
                    ticker=ticker,
                )
            except TypeError:
                self.db.save_equity_snapshot(
                    equity=round(equity, 2),
                    unrealized_pnl=round(unrealized, 2),
                    realized_cumulative=round(realized_cum, 2),
                    open_positions=len(open_positions),
                    eth_price=current_price,
                    funding_rate=funding_rate,
                )
        except Exception as e:
            logger.warning(f"AGAPE-SPOT: Snapshot save failed for {ticker}: {e}")

    # ==================================================================
    # Scan logging (includes ticker)
    # ==================================================================

    def _log_scan(
        self,
        ticker: str,
        result: Dict,
        context: Dict,
        signal: Optional[AgapeSpotSignal] = None,
    ):
        """Log scan activity with ticker information."""
        market = context.get("market_data", {})
        oracle = context.get("oracle_data", {})
        self.db.log_scan({
            "ticker": ticker,
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

    # ==================================================================
    # Status (per-ticker or summary of all)
    # ==================================================================

    def get_status(self, ticker: str = None) -> Dict[str, Any]:
        """Return bot status.

        If *ticker* is specified, return status for that single ticker.
        If ``None``, return an aggregate summary across ALL tickers.
        """
        if ticker:
            return self._get_ticker_status(ticker)

        # -- Summary across all tickers --
        now = datetime.now(CENTRAL_TZ)
        per_ticker: Dict[str, Any] = {}
        total_unrealized = 0.0
        total_realized = 0.0
        total_open = 0
        total_closed_count = 0

        for t in self.config.tickers:
            t_status = self._get_ticker_status(t)
            per_ticker[t] = t_status
            acct = t_status.get("paper_account", {})
            total_unrealized += acct.get("unrealized_pnl", 0)
            total_realized += acct.get("realized_pnl", 0)
            total_open += t_status.get("open_positions", 0)
            total_closed_count += acct.get("total_trades", 0)

        total_starting = sum(
            self.config.get_starting_capital(t) for t in self.config.tickers
        )
        total_pnl = total_realized + total_unrealized
        return_pct = (
            (total_pnl / total_starting * 100) if total_starting else 0
        )

        return {
            "bot_name": "AGAPE-SPOT",
            "status": "ACTIVE" if self._enabled else "DISABLED",
            "mode": self.config.mode.value,
            "tickers": self.config.tickers,
            "side": "long",
            "instrument": "Multi-ticker spot",
            "exchange": "coinbase",
            "market": {"status": "OPEN", "reason": "Coinbase spot trades 24/7/365."},
            "cycle_count": self._cycle_count,
            "total_open_positions": total_open,
            "total_starting_capital": total_starting,
            "total_realized_pnl": round(total_realized, 2),
            "total_unrealized_pnl": round(total_unrealized, 2),
            "total_pnl": round(total_pnl, 2),
            "total_return_pct": round(return_pct, 2),
            "total_closed_trades": total_closed_count,
            "risk_per_trade_pct": self.config.risk_per_trade_pct,
            "cooldown_minutes": self.config.cooldown_minutes,
            "require_oracle": self.config.require_oracle_approval,
            "paper_account": {
                "starting_capital": total_starting,
                "current_balance": round(total_starting + total_pnl, 2),
                "cumulative_pnl": round(total_pnl, 2),
                "realized_pnl": round(total_realized, 2),
                "unrealized_pnl": round(total_unrealized, 2),
                "return_pct": round(return_pct, 2),
                "total_trades": total_closed_count,
                "win_rate": None,
            },
            "aggressive_features": {
                "use_no_loss_trailing": self.config.use_no_loss_trailing,
                "consecutive_losses": {
                    t: self._loss_streaks.get(t, 0) for t in self.config.tickers
                },
                "loss_streak_paused": {
                    t: bool(
                        self._loss_pause_until.get(t)
                        and now < self._loss_pause_until[t]
                    )
                    for t in self.config.tickers
                },
            },
            "per_ticker": per_ticker,
        }

    def _get_ticker_status(self, ticker: str) -> Dict[str, Any]:
        """Get status for a single ticker."""
        now = datetime.now(CENTRAL_TZ)
        open_positions = self._get_open_positions_for_ticker(ticker)
        current_price = self._get_current_price(ticker, None)
        ticker_config = self.config.get_ticker_config(ticker)
        starting_capital = self.config.get_starting_capital(ticker)

        total_unrealized = 0.0
        if current_price and open_positions:
            for pos in open_positions:
                quantity = pos.get("quantity", pos.get("eth_quantity", 0))
                pnl = (current_price - pos["entry_price"]) * quantity
                total_unrealized += pnl

        closed_trades = self._get_closed_trades_for_ticker(ticker)
        realized_pnl = (
            sum(t.get("realized_pnl", 0) for t in closed_trades)
            if closed_trades
            else 0.0
        )
        total_pnl = realized_pnl + total_unrealized
        current_balance = starting_capital + total_pnl
        return_pct = (
            (total_pnl / starting_capital * 100) if starting_capital else 0
        )

        wins = (
            [t for t in closed_trades if (t.get("realized_pnl") or 0) > 0]
            if closed_trades
            else []
        )
        win_rate = (
            round(len(wins) / len(closed_trades) * 100, 1)
            if closed_trades
            else None
        )

        tracker = self._get_direction_tracker(ticker)
        loss_streak = self._loss_streaks.get(ticker, 0)
        pause_until = self._loss_pause_until.get(ticker)

        return {
            "bot_name": "AGAPE-SPOT",
            "status": "ACTIVE" if self._enabled else "DISABLED",
            "mode": self.config.mode.value,
            "ticker": ticker,
            "display_name": ticker_config.get("display_name", ticker),
            "side": "long",
            "instrument": f"{ticker} spot",
            "exchange": "coinbase",
            "market": {"status": "OPEN", "reason": "Coinbase spot trades 24/7/365."},
            "cycle_count": self._cycle_count,
            "open_positions": len(open_positions),
            "max_positions_per_ticker": self.config.max_open_positions_per_ticker,
            "current_price": current_price,
            "total_unrealized_pnl": round(total_unrealized, 2),
            "starting_capital": starting_capital,
            "risk_per_trade_pct": self.config.risk_per_trade_pct,
            "cooldown_minutes": self.config.cooldown_minutes,
            "require_oracle": self.config.require_oracle_approval,
            "paper_account": {
                "starting_capital": starting_capital,
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
                "direction_tracker": tracker.get_status(),
                "consecutive_losses": loss_streak,
                "loss_streak_paused": (
                    pause_until is not None and now < pause_until
                ),
            },
            "positions": open_positions,
        }

    # ==================================================================
    # Performance (per-ticker or aggregate)
    # ==================================================================

    def get_performance(self, ticker: str = None) -> Dict[str, Any]:
        """Return performance metrics.

        If *ticker* is specified, return for that single ticker.
        If ``None``, return aggregate across ALL tickers with per_ticker breakdown.
        """
        if ticker:
            return self._get_ticker_performance(ticker)

        # -- Aggregate across all tickers --
        per_ticker: Dict[str, Any] = {}
        all_closed: List[Dict] = []
        all_unrealized = 0.0
        total_starting = 0.0
        all_open_count = 0

        for t in self.config.tickers:
            t_perf = self._get_ticker_performance(t)
            per_ticker[t] = t_perf
            all_unrealized += t_perf.get("unrealized_pnl", 0)
            total_starting += self.config.get_starting_capital(t)
            all_open_count += t_perf.get("open_positions", 0)
            all_closed.extend(self._get_closed_trades_for_ticker(t))

        if not all_closed:
            return {
                "total_trades": 0,
                "open_positions": all_open_count,
                "win_rate": None,
                "total_pnl": round(all_unrealized, 2),
                "realized_pnl": 0,
                "unrealized_pnl": round(all_unrealized, 2),
                "avg_win": 0, "avg_loss": 0,
                "best_trade": 0, "worst_trade": 0,
                "profit_factor": 0,
                "return_pct": (
                    round(all_unrealized / total_starting * 100, 2)
                    if total_starting
                    else 0
                ),
                "per_ticker": per_ticker,
            }

        wins = [t for t in all_closed if (t.get("realized_pnl") or 0) > 0]
        losses = [t for t in all_closed if (t.get("realized_pnl") or 0) <= 0]
        realized_pnl = sum(t.get("realized_pnl", 0) for t in all_closed)
        total_pnl = realized_pnl + all_unrealized
        total_wins = sum(t.get("realized_pnl", 0) for t in wins) if wins else 0
        total_losses = (
            abs(sum(t.get("realized_pnl", 0) for t in losses)) if losses else 0
        )

        return {
            "total_trades": len(all_closed),
            "open_positions": all_open_count,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": (
                round(len(wins) / len(all_closed) * 100, 1)
                if all_closed
                else None
            ),
            "total_pnl": round(total_pnl, 2),
            "realized_pnl": round(realized_pnl, 2),
            "unrealized_pnl": round(all_unrealized, 2),
            "avg_win": round(total_wins / len(wins), 2) if wins else 0,
            "avg_loss": round(total_losses / len(losses), 2) if losses else 0,
            "best_trade": max(
                (t.get("realized_pnl", 0) for t in all_closed), default=0,
            ),
            "worst_trade": min(
                (t.get("realized_pnl", 0) for t in all_closed), default=0,
            ),
            "profit_factor": (
                round(total_wins / total_losses, 2) if total_losses > 0
                else float("inf")
            ),
            "return_pct": (
                round(total_pnl / total_starting * 100, 2)
                if total_starting
                else 0
            ),
            "per_ticker": per_ticker,
        }

    def _get_ticker_performance(self, ticker: str) -> Dict[str, Any]:
        """Get performance metrics for a single ticker."""
        closed_trades = self._get_closed_trades_for_ticker(ticker)
        starting_capital = self.config.get_starting_capital(ticker)

        open_positions = self._get_open_positions_for_ticker(ticker)
        current_price = self._get_current_price(ticker, None)
        unrealized_pnl = 0.0
        if current_price and open_positions:
            for pos in open_positions:
                quantity = pos.get("quantity", pos.get("eth_quantity", 0))
                # Long-only
                pnl = (current_price - pos["entry_price"]) * quantity
                unrealized_pnl += pnl

        if not closed_trades:
            return {
                "ticker": ticker,
                "total_trades": 0,
                "open_positions": len(open_positions),
                "win_rate": None,
                "total_pnl": round(unrealized_pnl, 2),
                "realized_pnl": 0,
                "unrealized_pnl": round(unrealized_pnl, 2),
                "avg_win": 0, "avg_loss": 0,
                "best_trade": 0, "worst_trade": 0,
                "profit_factor": 0,
                "return_pct": (
                    round(unrealized_pnl / starting_capital * 100, 2)
                    if starting_capital
                    else 0
                ),
            }

        wins = [t for t in closed_trades if (t.get("realized_pnl") or 0) > 0]
        losses = [t for t in closed_trades if (t.get("realized_pnl") or 0) <= 0]
        realized_pnl = sum(t.get("realized_pnl", 0) for t in closed_trades)
        total_pnl = realized_pnl + unrealized_pnl
        total_wins = sum(t.get("realized_pnl", 0) for t in wins) if wins else 0
        total_losses = (
            abs(sum(t.get("realized_pnl", 0) for t in losses)) if losses else 0
        )

        return {
            "ticker": ticker,
            "total_trades": len(closed_trades),
            "open_positions": len(open_positions),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": (
                round(len(wins) / len(closed_trades) * 100, 1)
                if closed_trades
                else None
            ),
            "total_pnl": round(total_pnl, 2),
            "realized_pnl": round(realized_pnl, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "avg_win": round(total_wins / len(wins), 2) if wins else 0,
            "avg_loss": round(total_losses / len(losses), 2) if losses else 0,
            "best_trade": max(
                (t.get("realized_pnl", 0) for t in closed_trades), default=0,
            ),
            "worst_trade": min(
                (t.get("realized_pnl", 0) for t in closed_trades), default=0,
            ),
            "profit_factor": (
                round(total_wins / total_losses, 2) if total_losses > 0
                else float("inf")
            ),
            "return_pct": (
                round(total_pnl / starting_capital * 100, 2)
                if starting_capital
                else 0
            ),
        }

    # ==================================================================
    # Force close & enable / disable
    # ==================================================================

    def force_close_all(
        self, ticker: str = None, reason: str = "MANUAL_CLOSE",
    ) -> Dict[str, Any]:
        """Close all positions for a specific ticker, or ALL tickers if None."""
        tickers_to_close = [ticker] if ticker else self.config.tickers
        all_results: List[Dict] = []
        total_pnl = 0.0
        total_closed = 0

        for t in tickers_to_close:
            open_positions = self._get_open_positions_for_ticker(t)
            current_price = self._get_current_price(t, None)

            if not current_price:
                all_results.append({
                    "ticker": t,
                    "error": "No price available",
                    "closed": 0,
                })
                continue

            ticker_details: List[Dict] = []
            for pos in open_positions:
                closed = self._close_position(t, pos, current_price, reason)
                if closed:
                    quantity = pos.get("quantity", pos.get("eth_quantity", 0))
                    pnl = (current_price - pos["entry_price"]) * quantity
                    total_pnl += pnl
                    total_closed += 1
                    ticker_details.append({
                        "position_id": pos["position_id"],
                        "pnl": round(pnl, 2),
                    })

            all_results.append({
                "ticker": t,
                "closed": len(ticker_details),
                "details": ticker_details,
            })

        return {
            "closed": total_closed,
            "total_pnl": round(total_pnl, 2),
            "tickers": all_results,
        }

    def enable(self):
        self._enabled = True
        self.db.log("INFO", "ENABLE", "AGAPE-SPOT bot enabled")

    def disable(self):
        self._enabled = False
        self.db.log("INFO", "DISABLE", "AGAPE-SPOT bot disabled")
