"""
ZEPHYR Trader - orchestration for the Kalshi live-sports scalper.

Runtime model
-------------
Production: a persistent async worker (`run_forever`) that reacts to the Kalshi
order-book + game-event feeds in ~milliseconds (its own Render worker,
`alphagex-zephyr`). The WebSocket consumers are the P2/P3 build.

P0/P1 (this file's `run_cycle`): a synchronous measure-and-(optionally-)act
pass usable from a fast scheduler or a script. It:
  1. for each tracked market: pull orderbook + fair value, log the gap,
  2. manage exits on open positions (score-kill / time / revert / stop),
  3. evaluate the scalp signal; act only if live_enabled AND fee gate passed,
  4. save an equity snapshot.

With no Kalshi creds and no tracked markets it degrades to logging scans - it
never crashes. This keeps reads/endpoints alive even when trading can't run
(common-mistakes #3).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from .models import (
    CENTRAL_TZ,
    ScalpPosition,
    PositionStatus,
    Side,
    ExitReason,
    market_config,
)
from . import signals as signals_mod
from . import risk as risk_mod
from .db import ZephyrDatabase
from .executor import ZephyrExecutor
from .fairvalue import get_provider

logger = logging.getLogger(__name__)


@dataclass
class TrackedMarket:
    """A Kalshi market mapped to its fair-value context."""
    market_id: str           # Kalshi market ticker
    sport: str
    espn_event_id: Optional[str] = None
    team_id: Optional[str] = None     # team the YES side resolves on


class ZephyrTrader:
    def __init__(self, kalshi_client=None, provider_name: Optional[str] = None):
        self.db = ZephyrDatabase()
        self._init_config()
        self.provider = get_provider(provider_name or self.fair_value_provider)
        if kalshi_client is None:
            try:
                from data.kalshi_client import create_kalshi_client
                kalshi_client = create_kalshi_client()
            except Exception as e:
                logger.warning("Kalshi client unavailable: %s", e)
                kalshi_client = None
        self.kalshi = kalshi_client
        self.executor = ZephyrExecutor(kalshi_client, live_enabled=self.live_enabled)
        self.tracked: List[TrackedMarket] = []
        self._open: Dict[str, ScalpPosition] = {}
        self._cycle_count = 0
        self._reload_open_positions()

    # ------------------------------------------------------------- config
    def _init_config(self) -> None:
        # Defaults are conservative: paper-locked until explicitly unlocked.
        if self.db.get_config("starting_capital") is None:
            self.db.set_config("starting_capital", "500.0")
        if self.db.get_config("live_enabled") is None:
            self.db.set_config("live_enabled", "false")
        if self.db.get_config("paper_locked") is None:
            self.db.set_config("paper_locked", "true")
        if self.db.get_config("fair_value_provider") is None:
            self.db.set_config("fair_value_provider", "espn")

    @property
    def live_enabled(self) -> bool:
        # Live requires BOTH the live flag on AND the paper lock explicitly off.
        live = (self.db.get_config("live_enabled", "false") or "false").lower() == "true"
        locked = (self.db.get_config("paper_locked", "true") or "true").lower() == "true"
        return live and not locked

    @property
    def fair_value_provider(self) -> str:
        return self.db.get_config("fair_value_provider", "espn") or "espn"

    # ----------------------------------------------------------- tracking
    def track_market(self, market: TrackedMarket) -> None:
        if not any(m.market_id == market.market_id for m in self.tracked):
            self.tracked.append(market)

    def _reload_open_positions(self) -> None:
        for row in self.db.get_open_positions():
            pos = ScalpPosition(
                position_id=row["position_id"], market_id=row["market_id"],
                sport=row["sport"], side=Side(row["side"]), contracts=row["contracts"],
                entry_cents=float(row["entry_cents"]),
                fair_at_entry_cents=float(row["fair_at_entry_cents"]) if row["fair_at_entry_cents"] is not None else None,
                is_maker=row["is_maker"], is_paper=row["is_paper"],
                open_time=row["open_time_ct"], status=PositionStatus.OPEN,
            )
            self._open[pos.position_id] = pos

    # ------------------------------------------------------------- helpers
    def _orderbook_yes_bid_ask(self, market_id: str) -> Optional[tuple[float, float]]:
        if self.kalshi is None:
            return None
        try:
            ob = self.kalshi.get_orderbook(market_id)
        except Exception as e:
            logger.debug("orderbook fetch failed %s: %s", market_id, e)
            return None
        # Kalshi orderbook: yes = bids to BUY yes; no = bids to BUY no.
        # Best yes bid = highest yes price; best yes ask = 100 - highest no price.
        yes = ob.get("yes") or []
        no = ob.get("no") or []
        if not yes or not no:
            return None
        best_yes_bid = max(float(level[0]) for level in yes)
        best_no_bid = max(float(level[0]) for level in no)
        best_yes_ask = 100.0 - best_no_bid
        if best_yes_ask <= best_yes_bid:
            return None
        return best_yes_bid, best_yes_ask

    # ------------------------------------------------------------- cycle
    def run_cycle(self, close_only: bool = False) -> Dict[str, Any]:
        self._cycle_count += 1
        acted, scanned, errors = 0, 0, 0

        if not self.tracked:
            self.db.log_scan(market_id=None, sport=None, outcome="NO_MARKETS",
                             reason="no live markets tracked this cycle")

        for m in self.tracked:
            try:
                scanned += 1
                ba = self._orderbook_yes_bid_ask(m.market_id)
                fair = self.provider.fair(m.market_id, sport=m.sport,
                                          espn_event_id=m.espn_event_id, team_id=m.team_id)
                yes_mid = (ba[0] + ba[1]) / 2.0 if ba else None
                if fair is not None:
                    self.db.log_fair_value(m.market_id, fair.source, fair.fair_cents,
                                           yes_mid, fair.confidence)

                # 1) manage exits on any open positions for this market
                self._manage_exits(m, ba, fair)

                # 2) consider a new scalp
                if close_only or ba is None or fair is None:
                    self.db.log_scan(market_id=m.market_id, sport=m.sport,
                                     outcome="NO_TRADE",
                                     fair_cents=fair.fair_cents if fair else None,
                                     kalshi_mid_cents=yes_mid,
                                     reason="close_only or missing book/fair")
                    continue

                sig = signals_mod.evaluate(m.market_id, m.sport, ba[0], ba[1], fair)
                self.db.log_scan(
                    market_id=m.market_id, sport=m.sport,
                    outcome=("SIGNAL" if sig.is_trade else "NO_TRADE"),
                    fair_cents=sig.fair_cents, kalshi_mid_cents=sig.kalshi_mid_cents,
                    edge_cents=sig.edge_cents, required_edge_cents=sig.required_edge_cents,
                    reason=sig.reason,
                )
                if sig.is_trade and self._capacity_ok(m):
                    if self.live_enabled:
                        pos = self.executor.open_scalp(sig)
                        if pos is not None:
                            self.db.insert_position(pos)
                            self._open[pos.position_id] = pos
                            acted += 1
                    else:
                        # paper-locked: shadow-log the would-be scalp
                        self._shadow(sig)
            except Exception as e:
                errors += 1
                logger.error("zephyr cycle error on %s: %s", m.market_id, e)

        self._save_snapshot()
        return {"cycle": self._cycle_count, "scanned": scanned,
                "acted": acted, "errors": errors, "live": self.live_enabled,
                "open_positions": len(self._open)}

    def _capacity_ok(self, m: TrackedMarket) -> bool:
        cfg = market_config(m.sport)
        per_market = sum(1 for p in self._open.values() if p.market_id == m.market_id)
        total = len(self._open)
        if per_market >= int(cfg.get("max_open_scalps", 2)):
            return False
        if total >= int(self.db.get_config("max_total_open_scalps", "3") or 3):
            return False
        return True

    def _manage_exits(self, m: TrackedMarket, ba, fair) -> None:
        if ba is None:
            return
        for pid, pos in list(self._open.items()):
            if pos.market_id != m.market_id:
                continue
            reason = risk_mod.evaluate_exit(pos, ba[0], ba[1], fair, game_events=[])
            if reason is None:
                continue
            exit_px = risk_mod.current_side_price(pos, ba[0], ba[1])
            closed = self.executor.close_scalp(pos, exit_px, reason)
            self.db.close_position(closed.position_id, exit_px, reason,
                                   closed.realized_pnl or 0.0, closed.exit_fee)
            self._open.pop(pid, None)

    def _shadow(self, sig) -> None:
        try:
            with __import__("trading.zephyr.db", fromlist=["db_connection"]).db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT INTO zephyr_ml_shadow
                        (market_id, sport, action, edge_cents, required_edge_cents, would_have_traded)
                    VALUES (%s,%s,%s,%s,%s,%s)
                """, (sig.market_id, sig.sport, sig.action.value, sig.edge_cents,
                      sig.required_edge_cents, True))
                conn.commit()
        except Exception as e:
            logger.debug("zephyr shadow log failed: %s", e)

    def _save_snapshot(self) -> None:
        cap = self.db.get_starting_capital()
        closed = self.db.get_closed_trades()
        realized = sum(float(t["realized_pnl"]) for t in closed)
        self.db.save_equity_snapshot(equity=cap + realized, realized=realized,
                                     unrealized=0.0, open_positions=len(self._open))

    # --------------------------------------------------------- status
    def status(self) -> Dict[str, Any]:
        return {
            "bot": "ZEPHYR", "display_name": "ASAHEL",
            "live_enabled": self.live_enabled,
            "paper_locked": (self.db.get_config("paper_locked", "true") or "true").lower() == "true",
            "provider": self.fair_value_provider,
            "kalshi_can_trade": bool(self.kalshi and self.kalshi.can_trade),
            "tracked_markets": len(self.tracked),
            "open_positions": len(self._open),
            "starting_capital": self.db.get_starting_capital(),
            "cycle_count": self._cycle_count,
        }


def create_zephyr_trader(*args, **kwargs) -> ZephyrTrader:
    return ZephyrTrader(*args, **kwargs)
