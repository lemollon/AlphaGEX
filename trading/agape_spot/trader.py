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

        # One-time cleanup: close any legacy fallback positions that were
        # created before the fallback-creation code was removed. These
        # positions were never placed on Coinbase, have 0% win rate and
        # $0 P&L, and block position slots without providing any value.
        self._cleanup_fallback_positions()

    # ==================================================================
    # Legacy fallback position cleanup (one-time at init)
    # ==================================================================

    def _cleanup_fallback_positions(self) -> None:
        """Close any remaining open positions with '_fallback' account labels.

        These were created by old code that auto-created paper positions
        when live Coinbase orders failed. That fallback logic was removed
        because fallback positions:
        - Never execute real Coinbase sells (sell_spot returns False)
        - Accumulate with 0% win rate and $0 P&L
        - Pollute statistics and capacity counts
        - The parallel 'paper' account already tracks what-if performance

        This runs once at init to clean up any remaining orphans.
        """
        try:
            all_open = self.db.get_open_positions()
            fallback_positions = [
                p for p in all_open
                if p.get("account_label", "").endswith("_fallback")
            ]

            if not fallback_positions:
                return

            logger.info(
                f"AGAPE-SPOT: Cleaning up {len(fallback_positions)} legacy "
                f"fallback positions"
            )

            for pos in fallback_positions:
                position_id = pos["position_id"]
                entry_price = pos["entry_price"]
                ticker = pos.get("ticker", "ETH-USD")
                account_label = pos.get("account_label", "unknown_fallback")

                # Close at entry price (0 P&L) since these were never real trades
                success = self.db.close_position(
                    position_id, entry_price, 0.0,
                    "LEGACY_FALLBACK_CLEANUP",
                )
                if success:
                    logger.info(
                        f"AGAPE-SPOT: Cleaned up fallback position "
                        f"{position_id} ({ticker} [{account_label}])"
                    )

            self.db.log(
                "INFO", "FALLBACK_CLEANUP",
                f"Closed {len(fallback_positions)} legacy fallback positions "
                f"at entry price ($0 P&L). These were never real Coinbase trades.",
            )

        except Exception as e:
            logger.error(f"AGAPE-SPOT: Fallback cleanup failed: {e}", exc_info=True)

    # ==================================================================
    # Capital allocator refresh + alpha computation
    # ==================================================================

    def _refresh_allocator(self) -> None:
        """Query DB for per-ticker performance and update the capital allocator rankings.

        Passes active tickers (those currently in market hours) so the allocator
        can redistribute inactive tickers' capital (e.g. MSTU on weekends) to
        crypto tickers that trade 24/7.

        Also computes per-ticker alpha (active trading return vs buy-and-hold)
        and passes it to the allocator for alpha-aware scoring.
        """
        try:
            perf_data = self.db.get_ticker_performance_stats(self.config.live_tickers)
            active = self.config.get_active_tickers()
            alpha_data = self._compute_alpha_data(perf_data)
            self._capital_allocator.refresh(
                perf_data, active_tickers=active, alpha_data=alpha_data,
            )
            # Feed perf stats (avg_win, avg_loss) to signal generator for EV gating
            self.signals.update_perf_stats(perf_data)
        except Exception as e:
            logger.warning(f"AGAPE-SPOT: Allocator refresh failed: {e}")

    def _compute_alpha_data(
        self, perf_data: Dict[str, Dict[str, Any]],
    ) -> Dict[str, float]:
        """Compute per-ticker alpha: trading return minus buy-and-hold return.

        alpha_pct = trading_return_pct - buyhold_return_pct

        Positive alpha means active trading is outperforming just holding.
        Negative alpha means you would have been better off just holding.
        """
        alpha: Dict[str, float] = {}
        try:
            # Get the earliest recorded price for each ticker
            base_prices = self.db.get_buyhold_base_prices(self.config.live_tickers)

            for ticker in self.config.live_tickers:
                d = perf_data.get(ticker, {})
                starting_capital = self.config.get_starting_capital(ticker)

                # Trading return
                total_pnl = d.get("total_pnl", 0.0)
                trading_return_pct = (total_pnl / starting_capital * 100) if starting_capital else 0.0

                # Buy-and-hold return
                base_price = base_prices.get(ticker)
                current_price = self._get_current_price(ticker, None)

                if base_price and base_price > 0 and current_price and current_price > 0:
                    buyhold_return_pct = ((current_price / base_price) - 1.0) * 100
                else:
                    buyhold_return_pct = 0.0

                alpha[ticker] = round(trading_return_pct - buyhold_return_pct, 2)

        except Exception as e:
            logger.warning(f"AGAPE-SPOT: Alpha computation failed: {e}")

        return alpha

    # ==================================================================
    # Exchange reconciliation — detect DB vs Coinbase drift
    # ==================================================================

    def _reconcile_exchange(self) -> None:
        """Compare DB open positions against actual Coinbase holdings.

        Runs periodically (every 10 cycles) to detect orphaned coins
        (DB says closed but Coinbase still has holdings) and ghost
        positions (DB says open but Coinbase has no coins).

        AUTO-SELLS orphaned coins: if Coinbase has coins but DB shows
        0 open positions, sells them via market order. This reclaims
        capital from failed sells that left coins stranded.
        """
        try:
            # Gather DB open positions grouped by ticker + account
            all_open = self.db.get_open_positions()
            db_qty_by_ticker: Dict[str, float] = {}
            for pos in all_open:
                ticker = pos.get("ticker", "ETH-USD")
                qty = float(pos.get("quantity", 0))
                db_qty_by_ticker[ticker] = db_qty_by_ticker.get(ticker, 0) + qty

            # Query actual Coinbase balances from all accounts
            exchange_balances = self.executor.get_all_account_balances()
            if not exchange_balances:
                return

            # Aggregate Coinbase holdings across all accounts, track which
            # account holds each ticker so we can auto-sell from the right one
            coinbase_qty_by_ticker: Dict[str, float] = {}
            ticker_account_map: Dict[str, str] = {}  # ticker -> account_label
            for acct_label, acct_data in exchange_balances.items():
                if isinstance(acct_data, dict) and "error" not in acct_data:
                    for ticker in self.config.tickers:
                        symbol = SPOT_TICKERS.get(ticker, {}).get("symbol", "")
                        bal_key = symbol.lower() + "_balance"
                        bal = float(acct_data.get(bal_key, 0))
                        if bal > 0:
                            coinbase_qty_by_ticker[ticker] = (
                                coinbase_qty_by_ticker.get(ticker, 0) + bal
                            )
                            ticker_account_map[ticker] = acct_label

            # Compare and log mismatches
            all_tickers = set(list(db_qty_by_ticker.keys()) + list(coinbase_qty_by_ticker.keys()))
            mismatches = []

            for ticker in all_tickers:
                db_qty = db_qty_by_ticker.get(ticker, 0)
                cb_qty = coinbase_qty_by_ticker.get(ticker, 0)

                # Skip tiny differences (dust from rounding)
                min_notional = SPOT_TICKERS.get(ticker, {}).get("min_notional_usd", 2.0)
                price = self.executor.get_current_price(ticker) or 0
                diff_usd = abs(db_qty - cb_qty) * price if price else 0

                if diff_usd < min_notional:
                    continue

                if cb_qty > 0 and db_qty == 0:
                    # ORPHANED COINS: DB says no open positions, but Coinbase
                    # still has coins. Auto-sell to reclaim capital.
                    orphan_usd = cb_qty * price
                    acct = ticker_account_map.get(ticker, "dedicated")
                    mismatches.append(
                        f"ORPHANED COINS: {ticker} has {cb_qty:.6f} on Coinbase "
                        f"(~${orphan_usd:.2f}) but 0 open positions in DB — "
                        f"AUTO-SELLING from [{acct}]"
                    )
                    self._auto_sell_orphaned(ticker, cb_qty, acct, price)

                elif db_qty > 0 and cb_qty == 0:
                    mismatches.append(
                        f"GHOST POSITIONS: {ticker} has {db_qty:.6f} in DB "
                        f"but 0 on Coinbase — sells may have succeeded but DB not updated"
                    )
                elif abs(db_qty - cb_qty) / max(db_qty, cb_qty, 0.0001) > 0.1:
                    mismatches.append(
                        f"QTY MISMATCH: {ticker} DB={db_qty:.6f} vs "
                        f"Coinbase={cb_qty:.6f} (diff ~${diff_usd:.2f})"
                    )

            if mismatches:
                msg = "RECONCILIATION DRIFT DETECTED:\n" + "\n".join(mismatches)
                logger.warning(f"AGAPE-SPOT: {msg}")
                self.db.log(
                    "WARNING", "RECONCILIATION_DRIFT", msg,
                    details={"db_qty": db_qty_by_ticker, "coinbase_qty": coinbase_qty_by_ticker},
                )
            else:
                logger.debug("AGAPE-SPOT: Reconciliation OK — DB matches Coinbase")

        except Exception as e:
            logger.error(f"AGAPE-SPOT: Reconciliation check failed: {e}", exc_info=True)

    def _auto_sell_orphaned(
        self, ticker: str, quantity: float, account_label: str, price: float,
    ) -> None:
        """Auto-sell orphaned coins that have no matching DB position.

        Uses market order via executor.sell_spot(). Logs result but does
        not create DB position records (there's nothing to close).
        """
        try:
            notional = quantity * price
            logger.info(
                f"AGAPE-SPOT: AUTO-SELL ORPHAN {ticker} {quantity:.6f} "
                f"(~${notional:.2f}) from [{account_label}]"
            )
            sell_ok, fill_price, exec_details = self.executor.sell_spot(
                ticker, quantity, f"ORPHAN-{ticker}", "RECONCILIATION_AUTO_SELL",
                account_label=account_label,
            )
            if sell_ok:
                fill = fill_price or price
                proceeds = quantity * fill
                self.db.log(
                    "INFO", "ORPHAN_AUTO_SOLD",
                    f"Auto-sold orphaned {ticker} {quantity:.6f} @ ${fill:.4f} "
                    f"(~${proceeds:.2f}) from [{account_label}]",
                    ticker=ticker,
                )
                logger.info(
                    f"AGAPE-SPOT: ORPHAN SOLD OK {ticker} ~${proceeds:.2f}"
                )
            else:
                self.db.log(
                    "ERROR", "ORPHAN_SELL_FAILED",
                    f"Failed to auto-sell orphaned {ticker} {quantity:.6f} "
                    f"(~${notional:.2f}) from [{account_label}]. "
                    f"Manual intervention required.",
                    ticker=ticker,
                )
                logger.error(
                    f"AGAPE-SPOT: ORPHAN SELL FAILED {ticker} — manual sell required"
                )
        except Exception as e:
            logger.error(f"AGAPE-SPOT: Auto-sell orphan failed for {ticker}: {e}")

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

        # Run exchange reconciliation every 10 cycles (~50 min at 5-min intervals)
        if self._cycle_count % 10 == 0:
            self._reconcile_exchange()

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

            # Step 2b: Get volatility context (ATR + chop detection)
            vol_context = self.executor.get_volatility_context(ticker)
            scan_context["volatility"] = vol_context

            # Step 3: Manage existing positions for this ticker
            # vol_context contains RSI(14) on 1-min candles for exit signals
            managed, closed = self._manage_positions(ticker, market_data, vol_context=vol_context)
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
            all_open = [
                p for p in self._get_open_positions_for_ticker(ticker)
                if not p.get("account_label", "").endswith("_fallback")
            ]

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

            # Chop detection is handled by the signal-level choppy EV gate
            # (signals.py _detect_choppy_market + _get_choppy_ev_threshold).
            # The old trader-level chop_index > 0.80 filter was a blunt
            # instrument that blocked ~80% of crypto scans because 5-min
            # Kaufman ER is almost always choppy.  The signal-level gate
            # checks whether we have EDGE in chop, not just whether chop
            # exists — validated by backtest ($87 saved, 34% DD reduction).

            # Step 7: Generate signal for this ticker
            signal = self._generate_signal(ticker, prophet_data, vol_context)
            result["signal"] = signal.to_dict() if signal else None

            if not signal or not signal.is_valid:
                result["outcome"] = f"NO_SIGNAL_{signal.reasoning if signal else 'NONE'}"
                self._log_scan(ticker, result, scan_context, signal=signal)
                return result

            # Step 8: Execute trade — live first, then paper mirrors live fill.
            #
            # ONE AGENT, ONE RESULT: Paper must use the exact same fill price
            # and quantity as the live order so all accounts track identical
            # performance.  Paper-only tickers (no live accounts) still get
            # simulated fills via _execute_paper().
            traded_accounts = []
            live_accounts = [(a, l) for a, l in eligible_accounts if l]
            paper_accounts = [(a, l) for a, l in eligible_accounts if not l]

            # Track the first successful live fill to mirror on paper
            live_fill_price = None
            live_fill_qty = None

            # Execute LIVE accounts first
            for account_label, is_live in live_accounts:
                position = self.executor.execute_trade_on_account(
                    signal, account_label, is_live,
                )
                if position:
                    self.db.save_position(position)
                    traded_accounts.append(account_label)
                    # Capture first live fill for paper mirroring
                    if live_fill_price is None:
                        live_fill_price = position.entry_price
                        live_fill_qty = position.quantity

                    actual_qty = position.quantity
                    notional = actual_qty * position.entry_price
                    self.db.log(
                        "INFO", "NEW_TRADE",
                        f"[LIVE:{account_label}] LONG {ticker} "
                        f"{actual_qty} @ ${position.entry_price:.2f} "
                        f"(${notional:.2f})",
                        details=signal.to_dict(),
                        ticker=ticker,
                    )
                else:
                    logger.warning(
                        f"AGAPE-SPOT: LIVE execution failed for {ticker} "
                        f"[{account_label}], skipping (no fallback)"
                    )
                    self.db.log(
                        "WARNING", "LIVE_EXEC_FAILED",
                        f"Live order failed for {ticker} [{account_label}]. "
                        f"No fallback position created.",
                        ticker=ticker,
                    )

            # Execute PAPER accounts — mirror the live fill when available
            for account_label, is_live in paper_accounts:
                if live_fill_price is not None and live_fill_qty is not None:
                    # Mirror: use exact live fill price and quantity
                    position = self.executor.execute_paper_mirror(
                        signal, live_fill_price, live_fill_qty,
                        account_label=account_label,
                    )
                else:
                    # Paper-only ticker (no live accounts) — simulated fill
                    position = self.executor.execute_trade_on_account(
                        signal, account_label, is_live,
                    )

                if position:
                    self.db.save_position(position)
                    traded_accounts.append(account_label)
                    mode_str = "PAPER_MIRROR" if live_fill_price else "PAPER"
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

            # Log ML shadow prediction when a trade is opened
            if traded_accounts and hasattr(self.signals, '_last_ml_prob'):
                ml_prob = self.signals._last_ml_prob
                bayes_prob = self.signals._last_bayesian_prob
                if ml_prob is not None and bayes_prob is not None:
                    funding_regime = signal.funding_regime if signal else "UNKNOWN"
                    # Use the first traded account's position_id
                    shadow_pos_id = signal.position_id if hasattr(signal, 'position_id') else None
                    if not shadow_pos_id and traded_accounts:
                        shadow_pos_id = f"spot_{ticker}_{self._cycle_count}"
                    try:
                        self.db.log_shadow_prediction(
                            ticker=ticker,
                            position_id=shadow_pos_id,
                            ml_prob=ml_prob,
                            bayesian_prob=bayes_prob,
                            funding_regime=str(funding_regime),
                        )
                    except Exception as e:
                        logger.debug(f"AGAPE-SPOT: Shadow prediction log failed: {e}")

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
        self,
        ticker: str,
        prophet_data: Optional[Dict],
        vol_context: Optional[Dict] = None,
    ) -> Optional[AgapeSpotSignal]:
        """Generate a trading signal for *ticker*."""
        try:
            return self.signals.generate_signal(
                ticker=ticker, prophet_data=prophet_data, vol_context=vol_context,
            )
        except TypeError:
            # Fallback for older signal generator without vol_context
            try:
                return self.signals.generate_signal(ticker=ticker, prophet_data=prophet_data)
            except TypeError:
                return self.signals.generate_signal(prophet_data=prophet_data)

    # ==================================================================
    # Position management (LONG-ONLY)
    # ==================================================================

    def _manage_positions(
        self, ticker: str, market_data: Optional[Dict],
        vol_context: Optional[Dict] = None,
    ) -> tuple:
        """Manage open positions for a specific ticker. Long-only."""
        open_positions = self._get_open_positions_for_ticker(ticker)
        if not open_positions:
            return (0, 0)

        current_price = self._get_current_price(ticker, market_data)
        closed = 0
        now = datetime.now(CENTRAL_TZ)

        # BUG FIX: When price is unavailable, still expire stale positions.
        # Previously, no-price → early return → positions pile up forever
        # (93 open BTC positions observed). Now we force-expire positions
        # past 2× max_hold_hours even without a price.
        if not current_price:
            exit_params = self.config.get_exit_params(ticker)
            max_hold = exit_params["max_hold_hours"]
            stale_threshold = max_hold * 2  # 2× max hold = definitely stale

            for pos_dict in open_positions:
                try:
                    open_time_raw = pos_dict.get("open_time")
                    if open_time_raw:
                        if isinstance(open_time_raw, str):
                            open_time = datetime.fromisoformat(open_time_raw)
                        else:
                            open_time = open_time_raw
                        if open_time.tzinfo is None:
                            open_time = open_time.replace(tzinfo=CENTRAL_TZ)
                        hold_hours = (now - open_time).total_seconds() / 3600
                        if hold_hours >= stale_threshold:
                            # Force expire at entry price (0 P&L) to unblock slots
                            entry = pos_dict["entry_price"]
                            self._close_position(
                                ticker, pos_dict, entry,
                                f"STALE_NO_PRICE_{hold_hours:.0f}h",
                            )
                            closed += 1
                except Exception as e:
                    logger.error(
                        f"AGAPE-SPOT: Stale position cleanup error ({ticker}): {e}"
                    )
            return (len(open_positions), closed)

        # ONE AGENT: Live positions drive exits.  When a live position
        # closes, its paper sibling closes at the same price so all
        # accounts record identical performance.
        #
        # Paper-only tickers (no live accounts) still manage paper
        # positions independently.
        is_live_ticker = self.config.is_live(ticker)

        # Separate live vs paper positions
        live_positions = [
            p for p in open_positions
            if p.get("account_label", "default") != "paper"
            and not p.get("account_label", "").endswith("_fallback")
        ]
        paper_positions = [
            p for p in open_positions
            if p.get("account_label") == "paper"
        ]

        # Track which paper positions were already closed by live mirror
        paper_closed_ids = set()

        # Step 1: Manage LIVE positions first
        for pos_dict in live_positions:
            try:
                if self.config.use_no_loss_trailing:
                    did_close = self._manage_no_loss_trailing(
                        ticker, pos_dict, current_price, now,
                        vol_context=vol_context,
                    )
                else:
                    should_close, reason = self._check_exit_conditions(
                        pos_dict, current_price, now, ticker=ticker,
                    )
                    did_close = False
                    if should_close:
                        did_close = self._close_position(
                            ticker, pos_dict, current_price, reason,
                        )

                if did_close:
                    closed += 1
                    # Mirror close to paper sibling:
                    # Match by entry_price (mirror positions) or open_time
                    # (legacy positions opened within 5 seconds of each other).
                    live_open = pos_dict.get("open_time")
                    live_entry = pos_dict.get("entry_price")
                    paper_close_price = pos_dict.get(
                        "_actual_close_price", current_price,
                    )
                    best_match = None
                    for pp in paper_positions:
                        if pp["position_id"] in paper_closed_ids:
                            continue
                        pp_entry = pp.get("entry_price")
                        # Exact entry match = mirror position (preferred)
                        if pp_entry == live_entry:
                            best_match = pp
                            break
                        # Fuzzy time match for legacy pre-mirror positions
                        if live_open and pp.get("open_time"):
                            try:
                                lo = live_open if not isinstance(live_open, str) else datetime.fromisoformat(live_open)
                                po = pp["open_time"] if not isinstance(pp["open_time"], str) else datetime.fromisoformat(pp["open_time"])
                                if abs((lo - po).total_seconds()) < 5:
                                    best_match = pp
                            except (ValueError, TypeError):
                                pass
                    if best_match:
                        self._close_position(
                            ticker, best_match, paper_close_price, reason,
                        )
                        paper_closed_ids.add(best_match["position_id"])
                        closed += 1
                else:
                    self._update_hwm(pos_dict, current_price)
            except Exception as e:
                logger.error(
                    f"AGAPE-SPOT: Position management error ({ticker}): {e}"
                )

        # Step 2: Manage PAPER positions that were NOT closed by a live mirror
        for pos_dict in paper_positions:
            if pos_dict["position_id"] in paper_closed_ids:
                continue  # Already closed by live mirror above

            # If this is a live ticker, paper is driven by live —
            # only update HWM, don't independently trigger exits.
            # The live position's exit will drive paper's exit.
            if is_live_ticker and live_positions:
                self._update_hwm(pos_dict, current_price)
                continue

            # Paper-only ticker: manage independently (no live sibling)
            try:
                if self.config.use_no_loss_trailing:
                    did_close = self._manage_no_loss_trailing(
                        ticker, pos_dict, current_price, now,
                        vol_context=vol_context,
                    )
                else:
                    should_close, reason = self._check_exit_conditions(
                        pos_dict, current_price, now, ticker=ticker,
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
    # Benchmark-aware trend detection
    # ------------------------------------------------------------------

    # Per-ticker trend strength cache: {ticker: (trend_pct, updated_at)}
    _trend_cache: Dict[str, tuple] = {}

    # Trend thresholds: if 24h price change exceeds these, we're in a strong trend
    TREND_THRESHOLD_MAJOR = 1.5   # BTC/ETH: 1.5% in 24h = strong trend
    TREND_THRESHOLD_ALT = 2.5     # Altcoins: 2.5% in 24h = strong trend

    def _get_trend_strength(self, ticker: str, current_price: float) -> float:
        """Calculate 24h price change percentage for trend detection.

        Uses the signal generator's price history and equity snapshots.
        Returns the percentage change (positive = uptrend, negative = downtrend).
        Cached for 5 minutes to avoid repeated DB queries.
        """
        now = datetime.now(CENTRAL_TZ)

        # Check cache
        cached = self._trend_cache.get(ticker)
        if cached:
            trend_pct, updated_at = cached
            if (now - updated_at).total_seconds() < 300:  # 5-min cache
                return trend_pct

        trend_pct = 0.0
        try:
            # Try to get price from 24h ago via equity snapshots
            conn = self.db._get_conn()
            if conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT eth_price FROM agape_spot_equity_snapshots
                    WHERE ticker = %s
                      AND eth_price IS NOT NULL AND eth_price > 0
                      AND timestamp < NOW() - INTERVAL '20 hours'
                    ORDER BY timestamp DESC LIMIT 1
                """, (ticker,))
                row = cursor.fetchone()
                cursor.close()
                conn.close()
                if row and row[0] and float(row[0]) > 0:
                    old_price = float(row[0])
                    trend_pct = ((current_price / old_price) - 1.0) * 100
        except Exception:
            pass

        self._trend_cache[ticker] = (trend_pct, now)
        return trend_pct

    def _is_strong_trend(self, ticker: str, trend_pct: float) -> bool:
        """Check if the trend is strong enough to warrant wider exits."""
        is_major = ticker in ("ETH-USD", "BTC-USD")
        threshold = self.TREND_THRESHOLD_MAJOR if is_major else self.TREND_THRESHOLD_ALT
        return abs(trend_pct) >= threshold

    # ------------------------------------------------------------------
    # No-loss trailing (LONG-ONLY -- simplified)
    # ------------------------------------------------------------------

    def _manage_no_loss_trailing(
        self,
        ticker: str,
        pos: Dict,
        current_price: float,
        now: datetime,
        vol_context: Optional[Dict] = None,
    ) -> bool:
        """No-loss trailing stop management. LONG-ONLY.

        ATR-ADAPTIVE: When the position has atr_at_entry, stops and trail
        distances are sized to actual volatility instead of fixed percentages.
        This prevents normal market noise from stopping out positions early.

        BENCHMARK-AWARE: In strong uptrends, trail distance and max hold time
        are widened so positions ride the trend instead of exiting too early.

        RSI EXIT: When RSI(14) on 1-min candles crosses above 70 (overbought)
        and the position is in profit, take profit. The trailing stop may not
        fire fast enough when price spikes then reverses — RSI catches the
        overbought condition at the top of the range.

        profit_pct   = (current - entry) / entry * 100
        hwm          = highest price seen (only updates when price goes up)
        Trail stop   = hwm - trail_distance, ratchets UP only.
        Close when   current_price <= current_stop.
        """
        entry_price = pos["entry_price"]
        position_id = pos["position_id"]

        # Per-ticker exit params (baseline)
        exit_params = self.config.get_exit_params(ticker)
        max_loss_pct = exit_params["max_unrealized_loss_pct"]
        emergency_pct = self.config.no_loss_emergency_stop_pct
        activation_pct = exit_params["no_loss_activation_pct"]
        trail_distance_pct = exit_params["no_loss_trail_distance_pct"]
        profit_target_pct = exit_params["no_loss_profit_target_pct"]
        max_hold = exit_params["max_hold_hours"]

        # ----- Minimum hold time gate -----
        # Block all exits during the first N minutes unless RSI is overbought.
        # Crypto 5-min ATR is 0.3-0.5%, so a normal dip can trigger MAX_LOSS
        # before the trade develops.  RSI > 70 override lets us exit overbought
        # spikes immediately even during the grace period.
        min_hold_min = self.config.min_hold_minutes
        rsi_override_thresh = self.config.rsi_exit_override_threshold
        open_time_raw = pos.get("open_time")
        hold_minutes = None
        if open_time_raw:
            try:
                if isinstance(open_time_raw, str):
                    ot = datetime.fromisoformat(open_time_raw)
                else:
                    ot = open_time_raw
                if ot.tzinfo is None:
                    ot = ot.replace(tzinfo=CENTRAL_TZ)
                hold_minutes = (now - ot).total_seconds() / 60.0
            except (ValueError, TypeError):
                pass

        if hold_minutes is not None and hold_minutes < min_hold_min:
            # Check RSI override: allow exit if overbought
            rsi = (vol_context or {}).get("rsi") if vol_context else None
            if rsi is not None and rsi > rsi_override_thresh:
                profit_pct_check = ((current_price - entry_price) / entry_price) * 100
                if profit_pct_check > 0:
                    logger.info(
                        f"AGAPE-SPOT MIN_HOLD OVERRIDE: {ticker} {position_id} "
                        f"RSI={rsi:.1f} > {rsi_override_thresh} at {hold_minutes:.1f}min "
                        f"— allowing early exit (in profit +{profit_pct_check:.2f}%)"
                    )
                    return self._close_position(
                        ticker, pos, current_price,
                        f"RSI_OVERBOUGHT_{rsi:.0f}_EARLY_+{profit_pct_check:.1f}pct",
                    )

            # Emergency stop still fires during min hold (can't let 5%+ losses run)
            profit_pct_check = ((current_price - entry_price) / entry_price) * 100
            if -profit_pct_check >= emergency_pct:
                logger.info(
                    f"AGAPE-SPOT MIN_HOLD EMERGENCY: {ticker} {position_id} "
                    f"at {hold_minutes:.1f}min but loss={profit_pct_check:.2f}% "
                    f">= emergency {emergency_pct}%"
                )
                stop_price = entry_price * (1 - emergency_pct / 100)
                return self._close_position(ticker, pos, stop_price, "EMERGENCY_STOP")

            # Otherwise: skip all exit checks, let the trade develop
            # Still update HWM so trailing stop is ready when grace period ends
            self._update_hwm(position_id, current_price, pos.get("high_water_mark") or entry_price)
            return False

        # Dynamic trend-aware exits: scale hold time and trail with trend strength
        # Stronger trends get wider exits so positions ride momentum
        trend_pct = self._get_trend_strength(ticker, current_price)
        is_major = ticker in ("ETH-USD", "BTC-USD")
        trend_threshold = self.TREND_THRESHOLD_MAJOR if is_major else self.TREND_THRESHOLD_ALT
        if trend_pct > 0 and self._is_strong_trend(ticker, trend_pct):
            # Scale factor: min 1.5x at threshold, up to 3.0x at 2× threshold
            # e.g. BTC threshold=1.5%, at 3% trend → scale = 1 + min(3.0/1.5, 2.0) = 3.0
            trend_scale = 1.0 + min(trend_pct / trend_threshold, 2.0)
            trail_distance_pct *= min(trend_scale, 2.5)  # cap trail widening at 2.5x
            activation_pct *= min(trend_scale * 0.8, 2.0)  # activation scales less aggressively
            # NOTE: max_hold is NOT scaled with trend. Trail widening already
            # extends holds naturally in strong trends. Scaling max_hold on top
            # of that was double-dipping — BTC (4h config) was being pushed to
            # 12h during mild uptrends, defeating the purpose of the tight config.
            # max_hold is a safety ceiling, not a trend-riding parameter.

        # ATR-adaptive: override fixed percentages when ATR data exists.
        # Primary source: atr_at_entry (stored when position was opened).
        # Fallback: current vol_context ATR (computed this scan cycle).
        # This ensures ATR-adaptive exits work even when entry ATR was
        # unavailable (e.g., candle API was down at entry time).
        atr = pos.get("atr_at_entry")
        chop = pos.get("chop_index_at_entry")
        atr_source = "entry"
        if (not atr or atr <= 0) and vol_context:
            atr = (vol_context or {}).get("atr")
            chop = (vol_context or {}).get("chop_index")
            atr_source = "current"
        if atr and atr > 0 and entry_price > 0:
            atr_pct = (atr / entry_price) * 100  # ATR as % of entry price

            # Stop: 1.5 × ATR (or 2.0 × ATR if entered in choppy market)
            atr_mult = 2.0 if (chop and chop > 0.65) else 1.5
            atr_stop_pct = atr_pct * atr_mult

            # Trail activation: 1.0 × ATR profit before starting trail
            atr_activation_pct = atr_pct * 1.0

            # Trail distance: 1.0 × ATR behind HWM
            atr_trail_pct = atr_pct * 1.0

            # Use the WIDER of ATR-based or config (never tighter than ATR)
            old_max_loss = max_loss_pct
            max_loss_pct = max(max_loss_pct, atr_stop_pct)
            activation_pct = max(activation_pct, atr_activation_pct)
            trail_distance_pct = max(trail_distance_pct, atr_trail_pct)

            if max_loss_pct > old_max_loss:
                logger.info(
                    f"AGAPE-SPOT ATR-ADAPTIVE: {ticker} {position_id} "
                    f"stop widened {old_max_loss:.2f}% -> {max_loss_pct:.2f}% "
                    f"(ATR=${atr:.4f}, atr_pct={atr_pct:.2f}%, "
                    f"chop={chop or 'N/A'}, mult={atr_mult}x, "
                    f"source={atr_source})"
                )

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
                ticker, pos, stop_price, f"MAX_LOSS_{max_loss_pct:.2f}pct",
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

        # ---- RSI overbought take profit (1-min RSI > 70 while in profit) ----
        # When RSI spikes above 70, the coin is overbought at the top of the
        # range. Take profit now — the trailing stop may lag behind a spike
        # that reverses quickly.  Only fires when position is in profit.
        rsi = (vol_context or {}).get("rsi") if vol_context else None
        if (
            rsi is not None
            and self.config.enable_rsi_choppy_override
            and rsi > self.config.rsi_overbought_threshold
            and profit_pct > 0
        ):
            logger.info(
                f"AGAPE-SPOT RSI EXIT: {ticker} RSI={rsi:.1f} > "
                f"{self.config.rsi_overbought_threshold} while +{profit_pct:.1f}% "
                f"— taking profit"
            )
            return self._close_position(
                ticker, pos, current_price,
                f"RSI_OVERBOUGHT_{rsi:.0f}_+{profit_pct:.1f}pct",
            )

        # ---- Profit target (disabled for all tickers) ----
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
        ticker: str = None,
    ) -> tuple:
        """Check basic stop / target / time exits. LONG-ONLY."""
        stop_loss = pos.get("stop_loss")
        take_profit = pos.get("take_profit")

        # Long-only: stop loss below entry, take profit above entry
        if stop_loss and current_price <= stop_loss:
            return (True, "STOP_LOSS")

        if take_profit and current_price >= take_profit:
            return (True, "TAKE_PROFIT")

        # Max hold time — use per-ticker config, not global default.
        # BTC has max_hold_hours=4, global default is 6. Using the global
        # meant BTC positions held 6h instead of 4h.
        max_hold = self.config.max_hold_hours  # fallback to global
        if ticker:
            max_hold = self.config.get_exit_params(ticker)["max_hold_hours"]

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
                if hold_hours >= max_hold:
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
        is_live_account = (
            account_label != "paper"
            and not account_label.endswith("_fallback")
            and self.config.is_live(ticker)
        )

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
                # Sell FAILED — keep position OPEN so we retry next cycle.
                # Increment fail counter; after 3 failures, force-close DB
                # position to prevent infinite retries (coins stay on Coinbase
                # as orphans, but slots free up).
                fail_count = self.db.increment_sell_fail_count(position_id)
                max_sell_retries = 3

                if fail_count >= max_sell_retries:
                    logger.error(
                        f"AGAPE-SPOT: SELL FAILED {fail_count}x for {ticker} "
                        f"{position_id} — force-closing DB position. "
                        f"Coins may still be in Coinbase. Manual check required."
                    )
                    self.db.log(
                        "ERROR", "SELL_FAILED_FORCE_CLOSE",
                        f"Coinbase sell failed {fail_count}x for {ticker} "
                        f"{position_id} (qty={quantity}). Force-closing DB "
                        f"position at ${current_price}. MANUAL CHECK REQUIRED: "
                        f"coins may still be in Coinbase account.",
                        ticker=ticker,
                    )
                    # Fall through to close the DB position below
                else:
                    logger.warning(
                        f"AGAPE-SPOT: LIVE SELL FAILED for {ticker} "
                        f"{position_id} (attempt {fail_count}/{max_sell_retries}). "
                        f"Keeping position OPEN for retry next cycle."
                    )
                    self.db.log(
                        "WARNING", "LIVE_SELL_RETRY",
                        f"Coinbase sell failed for {ticker} {position_id} "
                        f"(qty={quantity}, attempt {fail_count}/{max_sell_retries}). "
                        f"Position stays open — will retry next scan.",
                        ticker=ticker,
                    )
                    return False  # Position stays open, retry next cycle

        # Stash actual close price on pos_dict so the mirror logic in
        # _manage_positions can read it for paper sibling closes.
        pos_dict["_actual_close_price"] = actual_close_price

        # Long-only P&L -- no direction multiplier
        realized_pnl = round((actual_close_price - entry_price) * quantity, 2)

        # Diagnostic logging: trace every exit with full price context
        price_change_pct = ((actual_close_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
        logger.info(
            f"AGAPE-SPOT EXIT: {ticker} {position_id} [{account_label}] "
            f"reason={reason} entry=${entry_price:.4f} exit=${actual_close_price:.4f} "
            f"qty={quantity} pnl=${realized_pnl:+.4f} "
            f"price_chg={price_change_pct:+.3f}%"
        )

        # Extract Coinbase sell execution details if available
        sell_order_id = exec_details.get("coinbase_sell_order_id") if exec_details else None
        exit_slippage = exec_details.get("exit_slippage_pct") if exec_details else None
        exit_fee = exec_details.get("exit_fee_usd") if exec_details else None

        if reason == "MAX_HOLD_TIME":
            success = self.db.expire_position(
                position_id, realized_pnl, actual_close_price,
                coinbase_sell_order_id=sell_order_id,
                exit_slippage_pct=exit_slippage,
                exit_fee_usd=exit_fee,
            )
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
                tracker.update_ewma(realized_pnl)
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

            # Resolve ML shadow prediction with actual outcome
            try:
                self.db.resolve_shadow_prediction(position_id, won)
            except Exception as e:
                logger.debug(f"AGAPE-SPOT: Shadow prediction resolve failed: {e}")

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
        """24/7 for crypto, market-hours-only for equity tickers (MSTU)."""
        if not self._enabled:
            return "BOT_DISABLED"
        # Market hours restriction for equity-based tickers (e.g. MSTU)
        if not self.config.is_ticker_in_market_hours(ticker, now):
            return "OUTSIDE_MARKET_HOURS"
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

        # Include ML shadow prediction data if available
        ml_prob = getattr(self.signals, '_last_ml_prob', None)
        bayesian_prob = getattr(self.signals, '_last_bayesian_prob', None)

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
            "ml_probability": ml_prob,
            "bayesian_probability": bayesian_prob,
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
        has_dedicated = self.executor._dedicated_client is not None
        accounts_active = []
        if self.executor._client is not None:
            accounts_active.append("default")
        if has_dedicated:
            accounts_active.append("dedicated")
        return {
            "bot_name": "AGAPE-SPOT",
            "status": "ACTIVE" if self._enabled else "DISABLED",
            "mode": "live" if is_live else "paper",
            "coinbase_connected": coinbase_ok,
            "coinbase_accounts": accounts_active,
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
            "expected_value": self._get_ticker_ev(ticker, win_tracker),
            "positions": open_positions,
        }

    def _get_ticker_ev(self, ticker: str, win_tracker) -> Dict[str, Any]:
        """Calculate expected value per trade for a ticker.

        Used by the status endpoint to display EV on the dashboard.
        """
        perf = self.signals._perf_stats.get(ticker, {})
        avg_win = perf.get("avg_win", 0.0)
        avg_loss = abs(perf.get("avg_loss", 0.0))
        total_trades = perf.get("total_trades", 0)
        win_prob = win_tracker.win_probability if win_tracker else 0.5

        # Choppy EWMA gate info
        ema_mag = win_tracker.ema_magnitude if win_tracker else 0.0
        choppy_threshold = self.signals._get_choppy_ev_threshold(ticker)
        choppy_gate = {
            "active": self.config.enable_bayesian_choppy,
            "ema_magnitude": round(ema_mag, 4) if ema_mag > 0 else None,
            "threshold": round(choppy_threshold, 4),
            "ema_win": round(win_tracker.ema_win, 4) if win_tracker and win_tracker.ema_win > 0 else None,
            "ema_loss": round(win_tracker.ema_loss, 4) if win_tracker and win_tracker.ema_loss > 0 else None,
        }

        if total_trades >= 5 and avg_win > 0 and avg_loss > 0:
            ev = (win_prob * avg_win) - ((1.0 - win_prob) * avg_loss)
            return {
                "ev_per_trade": round(ev, 2),
                "avg_win": round(avg_win, 2),
                "avg_loss": round(avg_loss, 2),
                "win_prob": round(win_prob, 4),
                "has_data": True,
                "gate": "EV",
                "gate_status": "PASS" if ev > 0 else "BLOCKED",
                "choppy_gate": choppy_gate,
            }
        return {
            "ev_per_trade": None,
            "avg_win": round(avg_win, 2) if avg_win > 0 else None,
            "avg_loss": round(avg_loss, 2) if avg_loss > 0 else None,
            "win_prob": round(win_prob, 4),
            "has_data": False,
            "gate": "COLD_START_WIN_PROB",
            "gate_status": "PASS" if win_prob >= 0.50 else "BLOCKED",
            "choppy_gate": choppy_gate,
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

    # ==================================================================
    # Alpha Intelligence (for API endpoint)
    # ==================================================================

    def _generate_alpha_insight(
        self,
        ticker: str,
        status: str,
        alpha_pct: float,
        trading_return_pct: float,
        buyhold_return_pct: float,
        trend_pct: float,
        trend_boost: bool,
        win_rate: float,
        total_trades: int,
    ) -> tuple:
        """Generate human-readable insight and system action for a ticker.

        Returns (insight, system_action) tuple:
        - insight: WHY the ticker is in its current state
        - system_action: WHAT the system is automatically doing about it
        """
        symbol = ticker.replace("-USD", "")
        wr_pct = round(win_rate * 100) if win_rate <= 1.0 else round(win_rate)

        # --- Build the WHY insight ---
        if total_trades == 0:
            insight = f"No trades yet for {symbol}. Waiting for entry signals."
            system_action = "Equal capital allocation until trade history is established."
            return insight, system_action

        if status == "OUTPERFORMING":
            if trend_boost:
                insight = (
                    f"{symbol} trading is beating buy-and-hold by {abs(alpha_pct):.1f}%. "
                    f"Active trading returned {trading_return_pct:+.1f}% vs holding at {buyhold_return_pct:+.1f}%. "
                    f"Strong 24h trend ({trend_pct:+.1f}%) detected."
                )
            else:
                insight = (
                    f"{symbol} trading is beating buy-and-hold by {abs(alpha_pct):.1f}%. "
                    f"Active trading returned {trading_return_pct:+.1f}% vs holding at {buyhold_return_pct:+.1f}%. "
                    f"Win rate: {wr_pct}% across {total_trades} trades."
                )
            system_action = (
                "Rewarding with increased capital allocation (alpha adds 20% to score). "
            )
            if trend_boost:
                system_action += (
                    "Trend boost ON: trailing stop widened 1.5x and hold time extended 1.5x to ride momentum."
                )
            return insight, system_action

        if status == "UNDERPERFORMING":
            gap = abs(alpha_pct)
            if buyhold_return_pct > 0 and trading_return_pct > 0:
                # Both positive but holding won
                insight = (
                    f"{symbol} price rose {buyhold_return_pct:+.1f}% but trading only captured {trading_return_pct:+.1f}%. "
                    f"Holding would have earned {gap:.1f}% more. "
                    f"Win rate: {wr_pct}% across {total_trades} trades."
                )
            elif buyhold_return_pct > 0 and trading_return_pct <= 0:
                # Price went up but trading lost money
                insight = (
                    f"{symbol} price rose {buyhold_return_pct:+.1f}% but trading lost {trading_return_pct:+.1f}%. "
                    f"Exits may be too tight, cutting winners short. "
                    f"Win rate: {wr_pct}% across {total_trades} trades."
                )
            elif buyhold_return_pct <= 0 and trading_return_pct < buyhold_return_pct:
                # Price dropped and trading lost more than holding
                insight = (
                    f"{symbol} dropped {buyhold_return_pct:+.1f}% but trading lost more at {trading_return_pct:+.1f}%. "
                    f"Trades entered at bad times or stopped out poorly. "
                    f"Win rate: {wr_pct}% across {total_trades} trades."
                )
            else:
                insight = (
                    f"{symbol} is {gap:.1f}% behind buy-and-hold. "
                    f"Trading: {trading_return_pct:+.1f}% vs Hold: {buyhold_return_pct:+.1f}%. "
                    f"Win rate: {wr_pct}% across {total_trades} trades."
                )

            system_action = (
                f"Reducing capital allocation (negative alpha penalises score by 20%). "
                f"Capital shifted to better-performing tickers."
            )
            if trend_boost:
                system_action += (
                    " Trend boost ON: widening exits 1.5x to let current positions recover."
                )
            return insight, system_action

        # PARITY
        insight = (
            f"{symbol} is tracking close to buy-and-hold ({alpha_pct:+.1f}% difference). "
            f"Trading: {trading_return_pct:+.1f}% vs Hold: {buyhold_return_pct:+.1f}%. "
            f"Win rate: {wr_pct}% across {total_trades} trades."
        )
        system_action = "Neutral allocation — performing in line with the market."
        if trend_boost:
            system_action += " Trend boost ON: exits widened 1.5x for strong momentum."
        return insight, system_action

    def _generate_strategy_edge(
        self,
        per_ticker: Dict[str, Any],
        perf_data: Dict[str, Dict[str, Any]],
        combined_trading_return: float,
        btc_buyhold: float,
        eth_buyhold: float,
        trend_boost_count: int,
    ) -> Dict[str, Any]:
        """Generate portfolio-level strategy edge explanation.

        Explains WHY active trading is beating (or losing to) buy-and-hold
        and WHAT specific mechanisms are creating/destroying alpha.
        """
        outperformers = [t for t, d in per_ticker.items() if d["status"] == "OUTPERFORMING"]
        underperformers = [t for t, d in per_ticker.items() if d["status"] == "UNDERPERFORMING"]
        active_tickers = [t for t, d in per_ticker.items() if d.get("total_trades", 0) > 0]

        total_trades = sum(d.get("total_trades", 0) for d in per_ticker.values())
        total_wins = sum(perf_data.get(t, {}).get("wins", 0) for t in per_ticker)
        overall_wr = (total_wins / total_trades * 100) if total_trades > 0 else 0

        avg_win_all = [perf_data.get(t, {}).get("avg_win", 0) for t in active_tickers if perf_data.get(t, {}).get("avg_win", 0) > 0]
        avg_loss_all = [perf_data.get(t, {}).get("avg_loss", 0) for t in active_tickers if perf_data.get(t, {}).get("avg_loss", 0) < 0]
        mean_win = sum(avg_win_all) / len(avg_win_all) if avg_win_all else 0
        mean_loss = abs(sum(avg_loss_all) / len(avg_loss_all)) if avg_loss_all else 0

        beating_btc = combined_trading_return > btc_buyhold
        beating_eth = combined_trading_return > eth_buyhold

        # --- Build the strategy edge sections ---
        edge_sources: list = []
        headwinds: list = []

        # 1. Trailing stops as alpha source
        if mean_loss > 0 and mean_win > mean_loss:
            edge_sources.append({
                "name": "Trailing Stops Cut Losses",
                "detail": (
                    f"Average win (${mean_win:.2f}) is larger than average loss "
                    f"(${mean_loss:.2f}). Trailing stops prevent holding through "
                    f"drawdowns that buy-and-hold must endure."
                ),
            })
        elif mean_loss > 0:
            headwinds.append({
                "name": "Win/Loss Size Ratio",
                "detail": (
                    f"Average loss (${mean_loss:.2f}) exceeds average win "
                    f"(${mean_win:.2f}). Stops may be too tight, locking in "
                    f"small gains but taking full losses."
                ),
            })

        # 2. Win rate
        if overall_wr >= 55:
            edge_sources.append({
                "name": "Signal Accuracy",
                "detail": (
                    f"{overall_wr:.0f}% win rate across {total_trades} trades. "
                    f"The system enters more winning trades than losing ones, "
                    f"generating steady returns that compound."
                ),
            })
        elif overall_wr < 45 and total_trades > 10:
            headwinds.append({
                "name": "Low Win Rate",
                "detail": (
                    f"{overall_wr:.0f}% win rate across {total_trades} trades. "
                    f"More losses than wins means the system needs large winners "
                    f"to overcome the loss frequency."
                ),
            })

        # 3. Capital rotation
        if len(outperformers) > 0 and len(underperformers) > 0:
            out_syms = ", ".join(t.replace("-USD", "") for t in outperformers[:3])
            under_syms = ", ".join(t.replace("-USD", "") for t in underperformers[:3])
            edge_sources.append({
                "name": "Capital Rotation",
                "detail": (
                    f"Capital is shifting away from {under_syms} toward {out_syms}. "
                    f"Buy-and-hold has fixed allocation — it can't move money to "
                    f"what's working."
                ),
            })

        # 4. Trend riding
        if trend_boost_count > 0:
            boosted = [t.replace("-USD", "") for t, d in per_ticker.items() if d.get("trend_boost_active")]
            edge_sources.append({
                "name": "Trend Riding",
                "detail": (
                    f"{', '.join(boosted)} {'have' if len(boosted) > 1 else 'has'} widened exits "
                    f"(1.5x trailing stop, 1.5x hold time) to capture momentum. "
                    f"Buy-and-hold gets 100% of trends but also 100% of crashes."
                ),
            })

        # 5. Drawdown avoidance
        if mean_loss > 0:
            edge_sources.append({
                "name": "Drawdown Protection",
                "detail": (
                    f"Max loss per trade is capped at ~${mean_loss:.2f} via stops. "
                    f"Buy-and-hold has no downside protection — a 20% crash means "
                    f"a 20% portfolio loss."
                ),
            })

        # 6. Compounding from re-entry
        if total_trades > 20:
            edge_sources.append({
                "name": "Re-Entry After Dips",
                "detail": (
                    f"After exiting losing positions, the system re-enters at lower "
                    f"prices. {total_trades} trades means multiple entries at various "
                    f"price levels instead of one buy-and-hold entry."
                ),
            })

        # --- Build combined narrative ---
        if beating_btc and beating_eth:
            headline = "Active trading is outperforming buy-and-hold"
            summary = (
                f"Your system returned {combined_trading_return:+.1f}% vs "
                f"BTC hold at {btc_buyhold:+.1f}% and ETH hold at {eth_buyhold:+.1f}%. "
                f"The alpha is coming from {len(edge_sources)} active edge{'s' if len(edge_sources) != 1 else ''}."
            )
            verdict = "WINNING"
        elif beating_btc or beating_eth:
            better = "BTC" if beating_btc else "ETH"
            worse = "ETH" if beating_btc else "BTC"
            headline = f"Beating {better} hold, trailing {worse} hold"
            summary = (
                f"Your system returned {combined_trading_return:+.1f}% — ahead of "
                f"{better} ({btc_buyhold:+.1f}% / {eth_buyhold:+.1f}%) but behind "
                f"{worse}. The system is adapting."
            )
            verdict = "MIXED"
        else:
            headline = "Buy-and-hold is currently ahead"
            summary = (
                f"Your system returned {combined_trading_return:+.1f}% vs "
                f"BTC hold at {btc_buyhold:+.1f}% and ETH hold at {eth_buyhold:+.1f}%. "
                f"Strong price appreciation is hard to beat with active trading. "
                f"The system is automatically adjusting."
            )
            verdict = "TRAILING"

        return {
            "headline": headline,
            "summary": summary,
            "verdict": verdict,
            "edge_sources": edge_sources,
            "headwinds": headwinds,
            "stats": {
                "total_trades": total_trades,
                "overall_win_rate": round(overall_wr, 1),
                "avg_win": round(mean_win, 2),
                "avg_loss": round(mean_loss, 2),
                "outperforming_count": len(outperformers),
                "underperforming_count": len(underperformers),
                "trend_boost_active": trend_boost_count,
            },
        }

    def get_alpha_intelligence(self) -> Dict[str, Any]:
        """Return full alpha intelligence dashboard data.

        Includes per-ticker alpha, combined alpha vs BTC/ETH, and system
        status for all three intelligence modules:
        1. Alpha Tracker - rolling alpha calculation
        2. Adaptive Allocation - alpha-weighted capital scoring
        3. Benchmark-Aware Signals - trend-adjusted exits
        """
        perf_data = self.db.get_ticker_performance_stats(self.config.tickers)
        alpha_data = self._compute_alpha_data(perf_data)
        base_prices = self.db.get_buyhold_base_prices(self.config.tickers)

        per_ticker: Dict[str, Any] = {}
        for ticker in self.config.tickers:
            d = perf_data.get(ticker, {})
            starting_capital = self.config.get_starting_capital(ticker)
            total_pnl = d.get("total_pnl", 0.0)
            trading_return_pct = (total_pnl / starting_capital * 100) if starting_capital else 0.0

            base_price = base_prices.get(ticker)
            current_price = self._get_current_price(ticker, None)
            buyhold_return_pct = 0.0
            if base_price and base_price > 0 and current_price and current_price > 0:
                buyhold_return_pct = ((current_price / base_price) - 1.0) * 100

            ticker_alpha = alpha_data.get(ticker, 0.0)
            trend_pct = self._get_trend_strength(ticker, current_price) if current_price else 0.0

            status = "OUTPERFORMING" if ticker_alpha > 0.5 else (
                "UNDERPERFORMING" if ticker_alpha < -0.5 else "PARITY"
            )
            trend_boost = self._is_strong_trend(ticker, trend_pct) and trend_pct > 0
            win_rate = d.get("win_rate", 0.0)
            total_trades = d.get("total_trades", 0)

            # Generate human-readable insight + system action
            insight, system_action = self._generate_alpha_insight(
                ticker, status, ticker_alpha, trading_return_pct,
                buyhold_return_pct, trend_pct, trend_boost, win_rate,
                total_trades,
            )

            per_ticker[ticker] = {
                "trading_return_pct": round(trading_return_pct, 2),
                "buyhold_return_pct": round(buyhold_return_pct, 2),
                "alpha_pct": round(ticker_alpha, 2),
                "status": status,
                "base_price": round(base_price, 2) if base_price else None,
                "current_price": round(current_price, 2) if current_price else None,
                "total_trades": total_trades,
                "trend_24h_pct": round(trend_pct, 2),
                "trend_boost_active": trend_boost,
                "insight": insight,
                "system_action": system_action,
            }

        # Combined metrics (sum across all tickers)
        total_starting = sum(
            self.config.get_starting_capital(t) for t in self.config.tickers
        )
        total_trading_pnl = sum(
            perf_data.get(t, {}).get("total_pnl", 0.0) for t in self.config.tickers
        )
        combined_trading_return = (total_trading_pnl / total_starting * 100) if total_starting else 0.0

        # BTC and ETH buy-and-hold from combined perspective
        btc_base = base_prices.get("BTC-USD")
        btc_current = self._get_current_price("BTC-USD", None)
        btc_buyhold = ((btc_current / btc_base) - 1.0) * 100 if (btc_base and btc_base > 0 and btc_current) else 0.0

        eth_base = base_prices.get("ETH-USD")
        eth_current = self._get_current_price("ETH-USD", None)
        eth_buyhold = ((eth_current / eth_base) - 1.0) * 100 if (eth_base and eth_base > 0 and eth_current) else 0.0

        # Count active systems
        trend_boost_count = sum(
            1 for t in per_ticker.values() if t.get("trend_boost_active")
        )
        outperforming_count = sum(
            1 for t in per_ticker.values() if t.get("status") == "OUTPERFORMING"
        )

        # Portfolio-level strategy edge analysis
        strategy_edge = self._generate_strategy_edge(
            per_ticker, perf_data,
            combined_trading_return, btc_buyhold, eth_buyhold,
            trend_boost_count,
        )

        return {
            "systems": {
                "alpha_tracker": {
                    "active": True,
                    "description": "Rolling alpha vs buy-and-hold per ticker",
                    "outperforming_tickers": outperforming_count,
                    "total_tickers": len(self.config.tickers),
                },
                "adaptive_allocation": {
                    "active": True,
                    "description": "Alpha-weighted capital scoring (20% weight)",
                    "effect": "Tickers with positive alpha get more capital",
                },
                "benchmark_signals": {
                    "active": True,
                    "description": "Trend-aware exits widen in strong uptrends",
                    "tickers_with_trend_boost": trend_boost_count,
                    "trail_multiplier": "1.5x in strong trends",
                    "hold_multiplier": "1.5x in strong trends",
                },
            },
            "strategy_edge": strategy_edge,
            "per_ticker": per_ticker,
            "combined": {
                "trading_return_pct": round(combined_trading_return, 2),
                "btc_buyhold_pct": round(btc_buyhold, 2),
                "eth_buyhold_pct": round(eth_buyhold, 2),
                "alpha_vs_btc": round(combined_trading_return - btc_buyhold, 2),
                "alpha_vs_eth": round(combined_trading_return - eth_buyhold, 2),
                "total_starting_capital": total_starting,
                "total_trading_pnl": round(total_trading_pnl, 2),
            },
        }

    def enable(self):
        self._enabled = True
        self.db.log("INFO", "ENABLE", "AGAPE-SPOT bot enabled")

    def disable(self):
        self._enabled = False
        self.db.log("INFO", "DISABLE", "AGAPE-SPOT bot disabled")
