"""JOSHUA entry-cycle orchestrator.

Runs every 60 seconds during market hours. Pulls a GexSnapshot from
gex_client, runs the setup-stack dispatcher, and opens a paper position
if a setup fires. Not pure — talks to /api/gex/SPY, Tradier (for chain),
and Postgres.
"""
from __future__ import annotations

import datetime as dt
import logging
import os
from typing import Optional

from trading.helios.db import HeliosDatabase
from trading.helios.executor import open_paper
from trading.helios.gex_client import GexClient, GexStaleError, GexSnapshot
from trading.helios.models import HeliosConfig, JoshuaConfig, SetupType, SpreadType
from trading.helios.setups.base import SetupAction
from trading.helios.setups.flip_cross import FlipBuffer
from trading.helios.signals import dispatch

logger = logging.getLogger(__name__)


class HeliosTrader:
    """Entry-cycle orchestrator. One instance per worker process."""

    def __init__(
        self,
        db: HeliosDatabase,
        tradier,
        config: JoshuaConfig,
        gex_client: Optional[GexClient] = None,
    ):
        self.db = db
        self.tradier = tradier
        self.config = config
        self.gex_client = gex_client or GexClient(
            base_url=os.environ.get("ALPHAGEX_API_BASE", "http://localhost:8000"),
            stale_max_seconds=config.gex_stale_max_seconds,
        )
        self._flip_buffer = FlipBuffer(max_minutes=config.flip_buffer_minutes)

    def run_cycle(self) -> None:
        now_ct = self._now_ct()
        if not self._is_market_hours(now_ct):
            return

        try:
            snapshot = self.gex_client.get_spy()
        except GexStaleError as e:
            logger.info("HELIOS: gex stale (%s) — skip", e)
            self.db.insert_scan_activity(outcome="SKIP", detail=f"gex_stale:{e}")
            return
        except Exception as e:
            logger.warning("HELIOS: gex fetch failed: %s", e)
            self.db.insert_scan_activity(outcome="ERROR", detail=f"gex_fetch:{e}")
            return

        self._flip_buffer.add(snapshot)

        trade_date = now_ct.date()
        state = self.db.load_daily_state(trade_date)

        action = dispatch(
            snapshot,
            state=state,
            buffer=self._flip_buffer,
            config=self.config,
        )

        if action is None:
            self.db.insert_scan_activity(outcome="NO_TRADE", detail=f"regime={snapshot.regime}")
            return

        if self.db.get_open_position() is not None:
            self.db.insert_scan_activity(outcome="SKIP", detail="position_already_open")
            return

        self._open(action, snapshot, now_ct)

    def _open(self, action: SetupAction, snap: GexSnapshot, now_ct: dt.datetime) -> None:
        expiration_date = self._next_trading_day(now_ct.date())
        try:
            long_sym, long_mid, short_sym, short_mid = self._pull_vertical_mids(
                long_strike=action.long_strike,
                short_strike=action.short_strike,
                expiration=expiration_date,
                is_call=(action.direction == "call"),
            )
        except Exception as e:
            logger.warning("HELIOS: chain fetch failed: %s", e)
            self.db.insert_scan_activity(outcome="ERROR", detail=f"chain:{e}")
            return

        spread_type = SpreadType.BULL_CALL if action.direction == "call" else SpreadType.BEAR_PUT
        opened = open_paper(
            db=self.db,
            spread_type=spread_type,
            long_symbol=long_sym,
            short_symbol=short_sym,
            long_strike=action.long_strike,
            short_strike=action.short_strike,
            long_mid=long_mid,
            short_mid=short_mid,
            expiration_date=expiration_date,
            config=self._executor_config(),
        )
        if opened is None:
            self.db.insert_scan_activity(outcome="SKIP", detail="open_paper:invalid")
            return

        self.db.upsert_daily_state(
            now_ct.date(),
            fired=action.setup,
            signal_minute=_minutes_since_open(now_ct),
        )
        self.db.insert_scan_activity(outcome="TRADE", detail=f"{action.setup.value}:{action.direction}")

    def _executor_config(self) -> HeliosConfig:
        balance = max(self.db.get_starting_capital() + self.db.get_realized_pnl(), 0.0)
        risk = balance * self.config.risk_per_trade_pct * self.config.buying_power_usage_pct
        return HeliosConfig(
            ticker=self.config.ticker,
            spread_width=self.config.spread_width,
            risk_per_trade=max(risk, 0.0),
            profit_target_pct=self.config.profit_target_pct,
            stop_loss_pct=self.config.stop_loss_pct,
        )

    def _pull_vertical_mids(self, *, long_strike, short_strike, expiration, is_call):
        chain = self.tradier.get_option_chain(self.config.ticker, expiration)
        side = "call" if is_call else "put"
        long_q = _find_strike(chain, long_strike, side)
        short_q = _find_strike(chain, short_strike, side)
        return (
            long_q["symbol"],
            (float(long_q["bid"]) + float(long_q["ask"])) / 2.0,
            short_q["symbol"],
            (float(short_q["bid"]) + float(short_q["ask"])) / 2.0,
        )

    def _next_trading_day(self, today: dt.date) -> dt.date:
        d = today + dt.timedelta(days=1)
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
        return d

    def _now_ct(self) -> dt.datetime:
        return dt.datetime.utcnow() - dt.timedelta(hours=5)

    def _is_market_hours(self, now_ct: dt.datetime) -> bool:
        if now_ct.weekday() >= 5:
            return False
        if now_ct.hour < 8 or (now_ct.hour == 8 and now_ct.minute < 30):
            return False
        if now_ct.hour > 15:
            return False
        if now_ct.hour == 15 and now_ct.minute >= 55:
            return False
        return True


def _find_strike(chain, strike, side):
    for q in chain:
        if abs(float(q["strike"]) - strike) < 1e-3 and str(q.get("option_type", "")).lower() == side:
            return q
    raise KeyError(f"strike {strike} {side} not in chain")


def _minutes_since_open(now_ct: dt.datetime) -> int:
    open_time = now_ct.replace(hour=8, minute=30, second=0, microsecond=0)
    return max(int((now_ct - open_time).total_seconds() // 60), 0)
