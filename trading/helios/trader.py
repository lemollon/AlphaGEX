"""HELIOS entry-cycle orchestrator.

Runs every 5 minutes during market hours. Pulls live data, generates a
signal via trading.helios.signals.generate_signal, and opens a paper
position if a TRADE signal emerges.

This module is NOT pure - it talks to Tradier, TradingVolatility (for
VIX), Prophet (advisory), and Postgres. The signal logic itself stays
pure inside helios.signals.generate_signal.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Optional

from quant.gex_walls import GammaStrike
from trading.helios.db import HeliosDatabase
from trading.helios.executor import open_paper
from trading.helios.models import HeliosConfig, SpreadType
from trading.helios.signals import generate_signal

logger = logging.getLogger(__name__)


class HeliosTrader:
    """Entry-cycle orchestrator. One instance per worker process."""

    def __init__(
        self,
        db: HeliosDatabase,
        tradier,        # data.tradier_data_fetcher.TradierDataFetcher (or compatible)
        config: HeliosConfig,
        gex_calculator=None,    # data.gex_calculator.GexCalculator (or compatible)
        vix_fetcher=None,       # callable() -> Optional[float]
        prophet_advisor=None,   # callable(bot_name) -> Optional[dict]
    ):
        self.db = db
        self.tradier = tradier
        self.config = config
        self.gex_calculator = gex_calculator
        self.vix_fetcher = vix_fetcher
        self.prophet_advisor = prophet_advisor

    # ----------------- Cycle -----------------

    def run_cycle(self) -> None:
        """Run one entry cycle. Idempotent within a 5-min window."""
        now_ct = self._now_ct()
        if not self._is_market_hours(now_ct):
            logger.debug("HELIOS: outside market hours; skipping cycle")
            return

        try:
            strikes, spot = self._fetch_strikes_and_spot()
        except Exception as e:
            logger.warning("HELIOS: gex/spot fetch failed: %s", e)
            self.db.insert_scan_activity(outcome="ERROR", detail=f"gex/spot: {e}")
            return

        vix = self._fetch_vix()
        prophet_advice = self._fetch_prophet()
        trades_today = self.db.count_trades_today()
        has_open = self.db.get_open_position() is not None

        sig = generate_signal(
            strikes=strikes,
            spot=spot,
            vix=vix if vix is not None else float("nan"),
            prophet_advice=prophet_advice,
            trades_today=trades_today,
            has_open_position=has_open,
            config=self.config,
        )
        self.db.insert_signal(sig, spot=spot, vix=vix)

        if sig.action == "SKIP":
            self.db.insert_scan_activity(
                outcome="SKIP",
                detail=sig.skip_reason.value if sig.skip_reason else "",
            )
            self._snapshot_equity()
            return

        # TRADE
        try:
            expiration = self._next_trading_day(now_ct.date())
            long_right = "C" if sig.spread_type == SpreadType.BULL_CALL else "P"
            long_sym = self._build_occ(
                self.config.ticker, expiration, sig.long_strike, long_right
            )
            short_sym = self._build_occ(
                self.config.ticker, expiration, sig.short_strike, long_right
            )

            quotes = self.tradier.get_option_quotes_batch([long_sym, short_sym])
            long_q = quotes.get(long_sym) if quotes else None
            short_q = quotes.get(short_sym) if quotes else None
            if long_q is None or short_q is None:
                logger.warning("HELIOS: TRADE signal but quotes unavailable")
                self.db.insert_scan_activity(outcome="QUOTE_UNAVAILABLE")
                self._snapshot_equity()
                return

            long_mid = (float(long_q["bid"]) + float(long_q["ask"])) / 2.0
            short_mid = (float(short_q["bid"]) + float(short_q["ask"])) / 2.0

            opened = open_paper(
                db=self.db,
                spread_type=sig.spread_type,
                long_symbol=long_sym,
                short_symbol=short_sym,
                long_strike=sig.long_strike,
                short_strike=sig.short_strike,
                long_mid=long_mid,
                short_mid=short_mid,
                expiration_date=expiration,
                config=self.config,
            )
            if opened is None:
                self.db.insert_scan_activity(
                    outcome="OPEN_FAILED",
                    detail="debit_invalid_or_undersized",
                )
            else:
                self.db.insert_scan_activity(
                    outcome="TRADE",
                    detail=f"pid={opened.position_id}",
                )
                self.db.log(
                    "INFO",
                    "HELIOS opened position",
                    {
                        "position_id": opened.position_id,
                        "spread_type": sig.spread_type.value,
                        "debit": opened.debit,
                        "contracts": opened.contracts,
                        "long_strike": sig.long_strike,
                        "short_strike": sig.short_strike,
                        "expiration": expiration.isoformat(),
                    },
                )
        except Exception:
            logger.exception("HELIOS: TRADE execution error")
            self.db.insert_scan_activity(outcome="ERROR", detail="trade_execution")
        finally:
            self._snapshot_equity()

    # ----------------- Helpers -----------------

    @staticmethod
    def _now_ct() -> dt.datetime:
        # Same CDT approximation used in monitor.py - fine for entry hours
        return dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=-5)

    def _is_market_hours(self, now_ct: dt.datetime) -> bool:
        if now_ct.weekday() >= 5:  # Sat/Sun
            return False
        # Entry window: 8:30 - 14:30 CT (per spec)
        start = now_ct.replace(hour=8, minute=30, second=0, microsecond=0)
        end = now_ct.replace(hour=14, minute=30, second=0, microsecond=0)
        return start <= now_ct <= end

    @staticmethod
    def _next_trading_day(d: dt.date) -> dt.date:
        c = d + dt.timedelta(days=1)
        while c.weekday() >= 5:
            c += dt.timedelta(days=1)
        return c

    def _fetch_strikes_and_spot(self):
        """Returns (List[GammaStrike], spot: float). Caller handles exceptions."""
        if self.gex_calculator is not None:
            # Adapt to whatever the existing GexCalculator returns.
            data = self.gex_calculator.get_gex_strikes(self.config.ticker)
            spot = self.gex_calculator.get_spot(self.config.ticker)
            strikes = [
                GammaStrike(
                    strike=float(s["strike"]),
                    gamma=float(s.get("net_gamma", s.get("gamma", 0.0))),
                )
                for s in data
            ]
            return strikes, float(spot)
        # Fallback: pull chain from Tradier and compute net gamma here.
        # (Implementation deferred - return empty list, signal will skip
        # NO_LOCAL_GAMMA / NO_MAJOR_WALL.)
        return [], 0.0

    def _fetch_vix(self) -> Optional[float]:
        if self.vix_fetcher is None:
            return None
        try:
            return float(self.vix_fetcher())
        except Exception as e:
            logger.warning("HELIOS: VIX fetch failed: %s", e)
            return None

    def _fetch_prophet(self) -> Optional[dict]:
        if self.prophet_advisor is None:
            return None
        try:
            return self.prophet_advisor("HELIOS")
        except Exception:
            return None

    def _build_occ(
        self,
        ticker: str,
        expiration: dt.date,
        strike: float,
        right: str,
    ) -> str:
        """Adapter - uses Tradier client's helper if available, else builds manually."""
        if hasattr(self.tradier, "build_occ_symbol"):
            return self.tradier.build_occ_symbol(ticker, expiration, strike, right)
        # Manual OCC: ROOT + YYMMDD + C/P + 8-digit strike (1/1000 dollars)
        return f"{ticker}{expiration.strftime('%y%m%d')}{right}{int(strike * 1000):08d}"

    def _snapshot_equity(self) -> None:
        try:
            starting = self.db.get_starting_capital()
            realized = self.db.get_realized_pnl()
            cash = starting + realized  # paper account approximation
            unrealized = 0.0  # could MTM open position; deferred until monitor proves stable
            open_count = 1 if self.db.get_open_position() else 0
            self.db.insert_equity_snapshot(
                equity=cash + unrealized,
                cash=cash,
                unrealized_pnl=unrealized,
                open_position_count=open_count,
            )
        except Exception:
            logger.exception("HELIOS: equity snapshot failed (non-fatal)")
