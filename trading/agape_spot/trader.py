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
    CapitalAllocator,
    PositionStatus,
    SignalAction,
    TradingMode,
    SPOT_TICKERS,
    BayesianWinTracker,
    FundingRegime,
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

        # Per-ticker Bayesian win trackers (loaded from DB)
        self._win_trackers: Dict[str, BayesianWinTracker] = {}
        for ticker in self.config.tickers:
            self._win_trackers[ticker] = self.db.get_win_tracker(ticker)

        self.signals = AgapeSpotSignalGenerator(self.config, self._win_trackers)
        self.executor = AgapeSpotExecutor(self.config, self.db)

        # Performance-based capital allocation for live accounts.
        # Ranks tickers by win rate, profit factor, and recent P&L, then
        # assigns each a proportional share of the available USD balance.
        # Paper accounts are unaffected — they always trade full config qty.
        self._capital_allocator = CapitalAllocator(self.config.live_tickers)
        self.executor.capital_allocator = self._capital_allocator
        self._refresh_allocator()  # initial ranking from DB

        self._cycle_count: int = 0
        self._enabled: bool = True

        # Per-ticker state
        self._loss_streaks: Dict[str, int] = {}
        self._loss_pause_until: Dict[str, Optional[datetime]] = {}
        self._direction_trackers: Dict[str, Any] = {}
        self._last_trade_scan: Dict[str, int] = {}  # Last scan cycle a trade was opened per ticker

        # Initialize per-ticker state for every configured ticker
        for ticker in self.config.tickers:
            self._loss_streaks[ticker] = 0
            self._loss_pause_until[ticker] = None
            self._direction_trackers[ticker] = get_spot_direction_tracker(ticker, self.config)
            self._last_trade_scan[ticker] = 0

        # Log tracker state at startup
        tracker_summary = {
            t: f"trades={tr.total_trades}, win_prob={tr.win_probability:.3f}"
            for t, tr in self._win_trackers.items()
        }
        self.db.log(
            "INFO", "INIT",
            f"AGAPE-SPOT trader initialized "
            f"(live_tickers={self.config.live_tickers}, "
            f"tickers={self.config.tickers}, 24/7 Coinbase spot, LONG-ONLY, "
            f"win_trackers={tracker_summary})",
        )
        logger.info(
            f"AGAPE-SPOT: Initialized "
            f"(live={self.config.live_tickers}, "
            f"paper={[t for t in self.config.tickers if t not in self.config.live_tickers]}, "
            f"max_pos_per_ticker={self.config.max_open_positions_per_ticker}, "
            f"prophet_required={self.config.require_prophet_approval})"
        )

    # ==================================================================
    # Capital allocator refresh
    # ==================================================================

    def _refresh_allocator(self) -> None:
        """Query DB for per-ticker performance and update the capital allocator rankings."""
        try:
            perf_data = self.db.get_ticker_performance_stats(self.config.live_tickers)
            self._capital_allocator.refresh(perf_data)
        except Exception as e:
            logger.warning(f"AGAPE-SPOT: Allocator refresh failed: {e}")

    # ==================================================================
    # Top-level cycle -- iterates ALL tickers
    # ==================================================================

    def run_cycle(self, close_only: bool = False) -> Dict[str, Any]:
        """Execute one trading cycle for ALL configured tickers."""
        self._cycle_count += 1
        now = datetime.now(CENTRAL_TZ)

        # Refresh capital allocation rankings every cycle so live accounts
        # always allocate based on the latest performance data.
        self._refresh_allocator()

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

            # Step 2: Get Prophet advice
            prophet_data = None
            if market_data:
                prophet_data = self.signals.get_prophet_advice(market_data)
                scan_context["prophet_data"] = prophet_data

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

            # Step 6a: Check min scan spacing between trades for this ticker
            entry_filters = self.config.get_entry_filters(ticker)
            min_scans = entry_filters.get("min_scans_between_trades", 0)
            if min_scans > 0:
                scans_since_last = self._cycle_count - self._last_trade_scan.get(ticker, 0)
                if scans_since_last < min_scans:
                    result["outcome"] = (
                        f"TRADE_SPACING_{scans_since_last}/{min_scans}_scans"
                    )
                    self._log_scan(ticker, result, scan_context)
                    return result

            # Step 6b: Get all accounts for this ticker and check position limits per-account
            # Uses per-ticker max_positions from entry filters (XRP/SHIB: 2, DOGE: 3, ETH: 5)
            max_positions = entry_filters.get("max_positions", self.config.max_open_positions_per_ticker)
            accounts = self.executor.get_all_accounts(ticker)
            all_open = self._get_open_positions_for_ticker(ticker)

            # Filter to accounts that still have capacity
            eligible_accounts = []
            for account_label, is_live in accounts:
                acct_open = [
                    p for p in all_open
                    if p.get("account_label", "default") == account_label
                ]
                if len(acct_open) < max_positions:
                    eligible_accounts.append((account_label, is_live))

            if not eligible_accounts:
                total_open = len(all_open)
                result["outcome"] = (
                    f"MAX_POSITIONS_{total_open}/"
                    f"{max_positions} (all accounts)"
                )
                self._log_scan(ticker, result, scan_context)
                return result

            # Step 7: Generate signal for this ticker
            signal = self._generate_signal(ticker, prophet_data)
            result["signal"] = signal.to_dict() if signal else None

            if not signal or not signal.is_valid:
                result["outcome"] = f"NO_SIGNAL_{signal.reasoning if signal else 'NONE'}"
                self._log_scan(ticker, result, scan_context, signal=signal)
                return result

            # Step 8: Execute trade on ALL eligible accounts
            traded_accounts = []
            for account_label, is_live in eligible_accounts:
                position = self.executor.execute_trade_on_account(
                    signal, account_label, is_live,
                )
                if position:
                    self.db.save_position(position)
                    traded_accounts.append(account_label)

                    mode_str = "LIVE" if is_live else "PAPER"
                    actual_qty = position.quantity
                    notional = actual_qty * position.entry_price
                    self.db.log(
                        "INFO", "NEW_TRADE",
                        f"[{mode_str}:{account_label}] LONG {ticker} "
                        f"{actual_qty} @ ${position.entry_price:.2f} "
                        f"(${notional:.2f})",
                        details=signal.to_dict(),
                        ticker=ticker,
                    )
                else:
                    if is_live:
                        # Live failed — execute paper fallback for this account
                        logger.warning(
                            f"AGAPE-SPOT: LIVE execution failed for {ticker} "
                            f"[{account_label}], falling back to PAPER"
                        )
                        fb_position = self.executor._execute_paper(
                            signal, account_label=f"{account_label}_fallback",
                        )
                        if fb_position:
                            self.db.save_position(fb_position)
                            traded_accounts.append(f"{account_label}_fb")
                            self.db.log(
                                "WARNING", "LIVE_EXEC_FAILED",
                                f"Live failed for {ticker} [{account_label}], "
                                f"paper fallback created.",
                                ticker=ticker,
                            )

            if traded_accounts:
                result["new_trade"] = True
                self._last_trade_scan[ticker] = self._cycle_count
                result["outcome"] = (
                    f"TRADED_LONG_{ticker}_"
                    f"{'_'.join(traded_accounts)}"
                )
            else:
                result["outcome"] = "EXECUTION_FAILED"
                self.db.log(
                    "ERROR", "EXEC_FAILED",
                    f"All account executions failed for {ticker} "
                    f"(qty={signal.quantity}, price=${signal.spot_price:.2f})",
                    ticker=ticker,
                )

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
        self, ticker: str, prophet_data: Optional[Dict],
    ) -> Optional[AgapeSpotSignal]:
        """Generate a trading signal for *ticker*."""
        try:
            return self.signals.generate_signal(ticker=ticker, prophet_data=prophet_data)
        except TypeError:
            return self.signals.generate_signal(prophet_data=prophet_data)

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

        Uses PER-TICKER exit parameters so altcoins (XRP, SHIB, DOGE) can
        use tight quick-scalp settings while ETH keeps wider parameters.

        profit_pct   = (current - entry) / entry * 100
        hwm          = highest price seen (only updates when price goes up)
        Trail stop   = hwm - trail_distance, ratchets UP only.
        Close when   current_price <= current_stop.
        """
        entry_price = pos["entry_price"]
        position_id = pos["position_id"]

        # Per-ticker exit params (altcoins: tight/fast, ETH: wide/patient)
        exit_params = self.config.get_exit_params(ticker)
        max_loss_pct = exit_params["max_unrealized_loss_pct"]
        emergency_pct = self.config.no_loss_emergency_stop_pct
        activation_pct = exit_params["no_loss_activation_pct"]
        trail_distance_pct = exit_params["no_loss_trail_distance_pct"]
        profit_target_pct = exit_params["no_loss_profit_target_pct"]
        max_hold = exit_params["max_hold_hours"]

        # Use per-ticker price decimals (SHIB=8, XRP/DOGE=4, ETH=2)
        pd = SPOT_TICKERS.get(ticker, {}).get("price_decimals", 2)

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
        if -profit_pct >= max_loss_pct:
            stop_price = entry_price * (1 - max_loss_pct / 100)
            return self._close_position(
                ticker, pos, stop_price, f"MAX_LOSS_{max_loss_pct}pct",
            )

        # ---- Emergency stop ----
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

        # ---- Profit target (altcoins: 1.0%, ETH: disabled) ----
        if profit_target_pct > 0 and profit_pct >= profit_target_pct:
            return self._close_position(
                ticker, pos, current_price,
                f"PROFIT_TARGET_+{profit_pct:.1f}pct",
            )

        # ---- Activate trailing ----
        if not trailing_active and max_profit_pct >= activation_pct:
            trail_distance = entry_price * (trail_distance_pct / 100)

            # Long-only: stop below HWM, never below entry
            initial_stop = max(entry_price, hwm - trail_distance)
            initial_stop = round(initial_stop, pd)

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
            trail_distance = entry_price * (trail_distance_pct / 100)

            new_stop = round(hwm - trail_distance, pd)
            if new_stop > (current_stop or 0) and new_stop >= entry_price:
                try:
                    self.db._execute(
                        "UPDATE agape_spot_positions SET current_stop = %s "
                        "WHERE position_id = %s AND status = 'open'",
                        (new_stop, position_id),
                    )
                except Exception:
                    pass

        # ---- Max hold time (altcoins: 2h, ETH: 6h) ----
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
                if hold_hours >= max_hold:
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
        """Close a position. LONG-ONLY: P&L = (current - entry) * quantity.

        For LIVE tickers, executes a real sell order on Coinbase via
        executor.sell_spot() and uses the actual fill price for P&L.
        """
        position_id = pos_dict["position_id"]
        entry_price = pos_dict["entry_price"]
        quantity = pos_dict.get("quantity", pos_dict.get("eth_quantity", 0))

        # ---- Execute LIVE sell on Coinbase for live tickers ----
        actual_close_price = current_price
        account_label = pos_dict.get("account_label", "default")
        is_live_account = account_label != "paper" and self.config.is_live(ticker)

        exec_details = None
        if is_live_account:
            sell_ok, fill_price, exec_details = self.executor.sell_spot(
                ticker, quantity, position_id, reason,
                account_label=account_label,
            )
            if sell_ok and fill_price is not None:
                actual_close_price = fill_price
            elif sell_ok:
                # Sell succeeded but fill lookup failed — use current_price
                pass
            else:
                # Sell failed — still close DB position to avoid stale state,
                # but warn loudly so the user can check their Coinbase account.
                logger.warning(
                    f"AGAPE-SPOT: LIVE SELL FAILED for {ticker} {position_id}. "
                    f"DB position will be closed but coins may still be in "
                    f"Coinbase account. Manual check recommended."
                )
                self.db.log(
                    "WARNING", "LIVE_SELL_FAILED",
                    f"Coinbase sell failed for {ticker} {position_id} "
                    f"(qty={quantity}). Position closed in DB at "
                    f"${current_price}. Coins may still be in account.",
                    ticker=ticker,
                )

        # Long-only P&L -- no direction multiplier
        realized_pnl = round((actual_close_price - entry_price) * quantity, 2)

        # Extract Coinbase sell execution details if available
        sell_order_id = exec_details.get("coinbase_sell_order_id") if exec_details else None
        exit_slippage = exec_details.get("exit_slippage_pct") if exec_details else None
        exit_fee = exec_details.get("exit_fee_usd") if exec_details else None

        if reason == "MAX_HOLD_TIME":
            success = self.db.expire_position(position_id, realized_pnl, actual_close_price)
        else:
            success = self.db.close_position(
                position_id, actual_close_price, realized_pnl, reason,
                coinbase_sell_order_id=sell_order_id,
                exit_slippage_pct=exit_slippage,
                exit_fee_usd=exit_fee,
            )

        if success:
            won = realized_pnl > 0

            # Update Bayesian win tracker (per-ticker)
            funding_regime_str = pos_dict.get("funding_regime_at_entry", "UNKNOWN")
            funding_regime = FundingRegime.from_funding_string(funding_regime_str)
            tracker = self._win_trackers.get(ticker)
            if tracker:
                tracker.update(won, funding_regime)
                self.db.save_win_tracker(tracker)

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
                ticker=ticker,
                direction="LONG",
                is_win=won,
                scan_number=self._cycle_count,
            )

            trade_mode = "LIVE" if self.config.is_live(ticker) else "PAPER"
            self.db.log(
                "INFO", "CLOSE_POSITION",
                f"[{trade_mode}] Closed {ticker} {position_id} "
                f"@ ${actual_close_price:.2f} "
                f"P&L=${realized_pnl:+.2f} ({reason})",
                details={
                    "position_id": position_id,
                    "ticker": ticker,
                    "realized_pnl": realized_pnl,
                    "reason": reason,
                    "close_price": actual_close_price,
                    "mode": trade_mode,
                },
                ticker=ticker,
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

            self.db.save_equity_snapshot(
                ticker=ticker,
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
        prophet = context.get("prophet_data", {})
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
            "oracle_advice": prophet.get("advice"),
            "oracle_win_prob": prophet.get("win_probability"),
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
            "mode": "mixed",
            "live_tickers": self.config.live_tickers,
            "paper_tickers": [
                t for t in self.config.tickers
                if t not in self.config.live_tickers
            ],
            "tickers": self.config.tickers,
            "side": "long",
            "instrument": "Multi-ticker spot",
            "exchange": "coinbase",
            "coinbase_connected": self.executor.has_any_client,
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
            "require_prophet": self.config.require_prophet_approval,
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
            "win_trackers": {
                t: tr.to_dict() for t, tr in self._win_trackers.items()
            },
            "capital_allocator": self._capital_allocator.to_dict(),
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

        dir_tracker = self._get_direction_tracker(ticker)
        loss_streak = self._loss_streaks.get(ticker, 0)
        pause_until = self._loss_pause_until.get(ticker)
        win_tracker = self._win_trackers.get(ticker)

        is_live = self.config.is_live(ticker)
        coinbase_ok = self.executor._get_client(ticker) is not None
        has_dedicated = ticker in self.executor._ticker_clients
        return {
            "bot_name": "AGAPE-SPOT",
            "status": "ACTIVE" if self._enabled else "DISABLED",
            "mode": "live" if is_live else "paper",
            "coinbase_connected": coinbase_ok,
            "coinbase_account": "dedicated" if has_dedicated else "default",
            "live_ready": is_live and coinbase_ok,
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
            "require_prophet": self.config.require_prophet_approval,
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
                "direction_tracker": dir_tracker.get_status(),
                "consecutive_losses": loss_streak,
                "loss_streak_paused": (
                    pause_until is not None and now < pause_until
                ),
            },
            "win_tracker": win_tracker.to_dict() if win_tracker else None,
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
                else None
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
                else None
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
