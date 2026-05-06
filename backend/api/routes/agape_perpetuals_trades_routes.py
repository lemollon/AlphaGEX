"""
AGAPE Perpetuals/Futures aggregated trade history.

Single endpoint that fans out across all 10 perp/futures bots, merges
their closed trades by close_time DESC, and paginates with a stable
keyset cursor on (close_time, bot_id, position_id).

Powers the cross-bot Recent Trades feed on /perpetuals-crypto, the
per-coin History tab on the same page, and the History tab on each
bot's individual page.
"""

from __future__ import annotations

import base64
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agape-perpetuals", tags=["AGAPE-PERPETUALS"])


def _trader_factory(import_path: str, attr: str) -> Callable[[], Optional[object]]:
    """Build a lazy trader factory. Failures return None so the aggregator stays up."""
    def _factory() -> Optional[object]:
        try:
            mod = __import__(import_path, fromlist=[attr])
            getter = getattr(mod, attr)
            return getter()
        except Exception as e:
            logger.warning(
                f"agape-perpetuals trades: registry factory {import_path}.{attr} failed: {e}"
            )
            return None
    return _factory


_BOT_REGISTRY: Dict[str, Dict] = {
    "eth":          {"label": "ETH-PERP",  "factory": _trader_factory("trading.agape_eth_perp.trader",  "get_agape_eth_perp_trader")},
    "sol":          {"label": "SOL-PERP",  "factory": _trader_factory("trading.agape_sol_perp.trader",  "get_agape_sol_perp_trader")},
    "avax":         {"label": "AVAX-PERP", "factory": _trader_factory("trading.agape_avax_perp.trader", "get_agape_avax_perp_trader")},
    "btc":          {"label": "BTC-PERP",  "factory": _trader_factory("trading.agape_btc_perp.trader",  "get_agape_btc_perp_trader")},
    "xrp":          {"label": "XRP-PERP",  "factory": _trader_factory("trading.agape_xrp_perp.trader",  "get_agape_xrp_perp_trader")},
    "doge":         {"label": "DOGE-PERP", "factory": _trader_factory("trading.agape_doge_perp.trader", "get_agape_doge_perp_trader")},
    "shib_futures": {"label": "SHIB-FUT",  "factory": _trader_factory("trading.agape_shib_futures.trader", "get_agape_shib_futures_trader")},
    "link_futures": {"label": "LINK-FUT",  "factory": _trader_factory("trading.agape_link_futures.trader", "get_agape_link_futures_trader")},
    "ltc_futures":  {"label": "LTC-FUT",   "factory": _trader_factory("trading.agape_ltc_futures.trader",  "get_agape_ltc_futures_trader")},
    "bch_futures":  {"label": "BCH-FUT",   "factory": _trader_factory("trading.agape_bch_futures.trader",  "get_agape_bch_futures_trader")},
}

ALL_BOT_IDS: List[str] = list(_BOT_REGISTRY.keys())


def _fetch_bot_trades(
    bot_id: str,
    *,
    limit: int,
    since: Optional[str],
    until: Optional[str],
    before_close_time: Optional[str],
    before_position_id: Optional[str],
) -> List[Dict]:
    """Pull closed trades for one bot via its db handle. Module-level for test patching."""
    entry = _BOT_REGISTRY.get(bot_id)
    if not entry:
        return []
    trader = entry["factory"]()
    if trader is None or not getattr(trader, "db", None):
        return []
    try:
        return trader.db.get_closed_trades(
            limit=limit,
            since=since,
            until=until,
            before_close_time=before_close_time,
            before_position_id=before_position_id,
        )
    except Exception as e:
        logger.error(f"agape-perpetuals trades: fetch {bot_id} failed: {e}")
        return []


def _encode_cursor(close_time: str, bot_id: str, position_id: str) -> str:
    return base64.urlsafe_b64encode(
        json.dumps(
            {"close_time": close_time, "bot_id": bot_id, "position_id": position_id}
        ).encode("utf-8")
    ).decode("ascii")


def _decode_cursor(cursor: str) -> Optional[Dict]:
    try:
        return json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8"))
    except Exception:
        return None


def _compute_pnl_pct(t: Dict) -> Optional[float]:
    pnl = t.get("realized_pnl")
    if pnl is None:
        return None
    risk = t.get("max_risk_usd")
    if risk and risk > 0:
        return float(pnl) / float(risk) * 100.0
    qty = t.get("quantity") or 0
    entry = t.get("entry_price") or 0
    notional = qty * entry
    if notional > 0:
        return float(pnl) / float(notional) * 100.0
    return None


def _parse_bots_param(bots: str) -> List[str]:
    if bots.strip() == "*":
        return list(ALL_BOT_IDS)
    requested = [b.strip().lower() for b in bots.split(",") if b.strip()]
    unknown = [b for b in requested if b not in _BOT_REGISTRY]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown bot ids: {unknown}")
    return requested


@router.get("/trades")
async def get_aggregated_trades(
    bots: str = Query(..., description="Comma-separated bot ids, or '*' for all 10"),
    since: Optional[str] = Query(None, description="ISO-8601 lower bound on close_time"),
    until: Optional[str] = Query(None, description="ISO-8601 upper bound on close_time"),
    before: Optional[str] = Query(None, description="Opaque keyset cursor from a prior response"),
    limit: int = Query(100, ge=1, le=500),
):
    bot_ids = _parse_bots_param(bots)

    cursor = _decode_cursor(before) if before else None
    before_close_time = cursor["close_time"] if cursor else None
    before_position_id = cursor["position_id"] if cursor else None

    if not since and not cursor:
        since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    per_bot_limit = limit + 1

    def _worker(bid: str) -> List[Dict]:
        rows = _fetch_bot_trades(
            bid,
            limit=per_bot_limit,
            since=since,
            until=until,
            before_close_time=before_close_time,
            before_position_id=before_position_id,
        )
        for r in rows:
            r["bot_id"] = bid
            r["bot_label"] = _BOT_REGISTRY[bid]["label"]
            r["realized_pnl_pct"] = _compute_pnl_pct(r)
        return rows

    pool_size = max(1, min(len(bot_ids), 10))
    with ThreadPoolExecutor(max_workers=pool_size) as ex:
        per_bot = list(ex.map(_worker, bot_ids))

    merged: List[Dict] = []
    for rows in per_bot:
        merged.extend(rows)

    # Sort: close_time DESC, then bot_id ASC, then position_id ASC.
    merged.sort(key=lambda t: (t.get("bot_id") or "", t.get("position_id") or ""))
    merged.sort(key=lambda t: (t.get("close_time") or ""), reverse=True)

    has_more = len(merged) > limit
    page = merged[:limit]
    next_cursor: Optional[str] = None
    if has_more and page:
        # Keyset cursor = LAST element of returned page. Next page predicate
        # is strictly older than this in (close_time DESC, position_id ASC).
        last = page[-1]
        next_cursor = _encode_cursor(
            last.get("close_time") or "",
            last.get("bot_id") or "",
            last.get("position_id") or "",
        )

    return {
        "trades": page,
        "has_more": has_more,
        "next_cursor": next_cursor,
        "window": {"since": since, "until": until},
    }
