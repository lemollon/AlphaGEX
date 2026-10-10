"""
AGAPE perpetuals data-health check.

Single lightweight endpoint the /perpetuals-crypto page polls to decide
whether to show the amber "data feed degraded" bar. Reads each bot's own
scan_activity table directly (same pattern as agape_perpetuals_trades_routes)
so this never has to spin up a full Trader / Coinbase executor.

A bot counts as unhealthy when either:
  - it has no scan_activity row in the last STALE_AFTER_MINUTES minutes, or
  - its latest scan recorded funding_regime = 'UNKNOWN' (the crypto-GEX
    equivalent of "CoinGlass feed down" — the bot fell back to dealer
    gamma / price-momentum signals only).
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agape-perpetuals", tags=["AGAPE-PERPETUALS"])

STALE_AFTER_MINUTES = 15


def _db_factory(import_path: str, class_name: str) -> Callable[[], Optional[object]]:
    """Memoized db factory — mirrors agape_perpetuals_trades_routes._db_factory."""
    cached: Dict[str, object] = {}

    def _factory() -> Optional[object]:
        if "db" in cached:
            return cached["db"]
        try:
            mod = __import__(import_path, fromlist=[class_name])
            cls = getattr(mod, class_name)
            db = cls()
            cached["db"] = db
            return db
        except Exception as e:
            logger.warning(
                f"agape-perpetuals data-health: db factory {import_path}.{class_name} failed: {e}"
            )
            return None

    return _factory


_BOT_REGISTRY: Dict[str, Dict] = {
    "btc":  {"label": "BTC-PERP",  "factory": _db_factory("trading.agape_btc_perp.db",  "AgapeBtcPerpDatabase")},
    "eth":  {"label": "ETH-PERP",  "factory": _db_factory("trading.agape_eth_perp.db",  "AgapeEthPerpDatabase")},
    "xrp":  {"label": "XRP-PERP",  "factory": _db_factory("trading.agape_xrp_perp.db",  "AgapeXrpPerpDatabase")},
    "sol":  {"label": "SOL-PERP",  "factory": _db_factory("trading.agape_sol_perp.db",  "AgapeSolPerpDatabase")},
    "doge": {"label": "DOGE-PERP", "factory": _db_factory("trading.agape_doge_perp.db", "AgapeDogePerpDatabase")},
    "avax": {"label": "AVAX-PERP", "factory": _db_factory("trading.agape_avax_perp.db", "AgapeAvaxPerpDatabase")},
    "shib": {"label": "SHIB-PERP", "factory": _db_factory("trading.agape_shib_perp.db", "AgapeShibPerpDatabase")},
}

ALL_BOT_IDS: List[str] = list(_BOT_REGISTRY.keys())


def _fetch_latest_scan(bot_id: str) -> Optional[Dict]:
    """Pull the single most recent scan_activity row for one bot. Module-level for test patching."""
    entry = _BOT_REGISTRY.get(bot_id)
    if not entry:
        return None
    db = entry["factory"]()
    if db is None:
        return None
    try:
        scans = db.get_scan_activity(limit=1)
        return scans[0] if scans else None
    except Exception as e:
        logger.error(f"agape-perpetuals data-health: fetch {bot_id} failed: {e}")
        return None


def _minutes_since(ts) -> Optional[float]:
    if ts is None:
        return None
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts).total_seconds() / 60.0


@router.get("/data-health")
async def get_data_health():
    """Per-bot latest-scan freshness and funding-regime coverage.

    Returns one entry per AGAPE perpetual bot plus an overall `healthy` flag.
    The frontend shows the amber data-health bar whenever `healthy` is false.
    """

    def _worker(bot_id: str) -> Dict:
        label = _BOT_REGISTRY[bot_id]["label"]
        scan = _fetch_latest_scan(bot_id)
        if scan is None:
            return {
                "bot_id": bot_id,
                "label": label,
                "last_scan": None,
                "minutes_since_scan": None,
                "funding_regime": None,
                "funding_unknown": True,
                "stale": True,
                "healthy": False,
            }
        last_scan = scan.get("timestamp")
        last_scan_iso = last_scan.isoformat() if hasattr(last_scan, "isoformat") else last_scan
        minutes = _minutes_since(last_scan)
        funding_regime = scan.get("funding_regime")
        funding_unknown = (funding_regime or "UNKNOWN") == "UNKNOWN"
        stale = minutes is None or minutes > STALE_AFTER_MINUTES
        return {
            "bot_id": bot_id,
            "label": label,
            "last_scan": last_scan_iso,
            "minutes_since_scan": minutes,
            "funding_regime": funding_regime,
            "funding_unknown": funding_unknown,
            "stale": stale,
            "healthy": not (stale or funding_unknown),
        }

    pool_size = max(1, min(len(ALL_BOT_IDS), 10))
    with ThreadPoolExecutor(max_workers=pool_size) as ex:
        bots = list(ex.map(_worker, ALL_BOT_IDS))

    healthy = all(b["healthy"] for b in bots)
    unknown_count = sum(1 for b in bots if b["funding_unknown"])
    stale_count = sum(1 for b in bots if b["stale"])

    return {
        "healthy": healthy,
        "bots": bots,
        "unknown_count": unknown_count,
        "stale_count": stale_count,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
