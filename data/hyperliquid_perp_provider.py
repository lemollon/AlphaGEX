"""Read-only Hyperliquid perpetual market-data adapter.

No wallet keys, signatures, or /exchange calls exist in this module.
It is suitable for paper/shadow calibration only.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import requests

from trading.shared.perp_realism import MarginTier, PerpQuote

logger = logging.getLogger(__name__)

INFO_URL = "https://api.hyperliquid.xyz/info"
SYMBOL_ALIASES = {"SHIB": "kSHIB"}


@dataclass(frozen=True)
class HyperliquidMarket:
    quote: PerpQuote
    funding_rate: float
    max_leverage: float
    tiers: Tuple[MarginTier, ...]


class HyperliquidPerpProvider:
    """Public, read-only market-data provider for Hyperliquid perps."""

    def __init__(self, timeout: float = 5.0, meta_ttl: float = 60.0):
        self.timeout = timeout
        self.meta_ttl = meta_ttl
        self._meta_cache = None
        self._meta_cache_at = 0.0

    def _post(self, payload: dict):
        response = requests.post(
            INFO_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def _meta_and_ctxs(self):
        now = time.time()
        if self._meta_cache is not None and now - self._meta_cache_at < self.meta_ttl:
            return self._meta_cache
        data = self._post({"type": "metaAndAssetCtxs"})
        if not isinstance(data, list) or len(data) < 2:
            raise ValueError("unexpected Hyperliquid metaAndAssetCtxs response")
        self._meta_cache = data
        self._meta_cache_at = now
        return data

    @staticmethod
    def _maintenance_tiers(raw_tiers: List[dict]) -> Tuple[MarginTier, ...]:
        """Convert lower-bound/max-leverage tiers to upper-bound MMR tiers."""
        if not raw_tiers:
            return ()

        parsed = sorted(
            (
                float(row.get("lowerBound", 0) or 0),
                float(row.get("maxLeverage", 1) or 1),
            )
            for row in raw_tiers
        )

        result: List[MarginTier] = []
        deduction = 0.0
        previous_rate = None
        for idx, (lower, max_lev) in enumerate(parsed):
            mmr = 1.0 / (2.0 * max(max_lev, 1.0))
            if idx > 0 and previous_rate is not None:
                deduction += lower * (mmr - previous_rate)
            upper = parsed[idx + 1][0] if idx + 1 < len(parsed) else float("inf")
            result.append(
                MarginTier(
                    max_notional=upper,
                    maintenance_margin_rate=mmr,
                    maintenance_amount=deduction,
                )
            )
            previous_rate = mmr
        return tuple(result)

    @staticmethod
    def _find_margin_table(meta: dict, asset: dict) -> Tuple[MarginTier, ...]:
        table_id = asset.get("marginTableId")
        if table_id is None:
            max_lev = float(asset.get("maxLeverage", 1) or 1)
            return (
                MarginTier(
                    max_notional=float("inf"),
                    maintenance_margin_rate=1.0 / (2.0 * max_lev),
                    maintenance_amount=0.0,
                ),
            )

        for row in meta.get("marginTables", []) or []:
            if not isinstance(row, list) or len(row) != 2:
                continue
            if int(row[0]) == int(table_id):
                return HyperliquidPerpProvider._maintenance_tiers(
                    row[1].get("marginTiers", []) or []
                )

        max_lev = float(asset.get("maxLeverage", 1) or 1)
        return (
            MarginTier(
                max_notional=float("inf"),
                maintenance_margin_rate=1.0 / (2.0 * max_lev),
                maintenance_amount=0.0,
            ),
        )

    def get_market(self, symbol: str) -> Optional[HyperliquidMarket]:
        coin = SYMBOL_ALIASES.get(symbol.upper(), symbol.upper())
        meta, ctxs = self._meta_and_ctxs()
        universe = meta.get("universe", []) or []

        index = None
        asset = None
        for i, row in enumerate(universe):
            if row.get("name") == coin:
                index = i
                asset = row
                break
        if index is None or asset is None or index >= len(ctxs):
            return None

        ctx = ctxs[index] or {}
        mark = float(ctx.get("markPx") or ctx.get("midPx") or ctx.get("oraclePx") or 0)
        oracle = float(ctx.get("oraclePx") or mark or 0)

        book = self._post({"type": "l2Book", "coin": coin})
        levels = book.get("levels", []) if isinstance(book, dict) else []
        bids = levels[0] if len(levels) > 0 else []
        asks = levels[1] if len(levels) > 1 else []
        bid = float(bids[0]["px"]) if bids else float(ctx.get("midPx") or mark or 0)
        ask = float(asks[0]["px"]) if asks else float(ctx.get("midPx") or mark or 0)

        if mark <= 0 or bid <= 0 or ask <= 0:
            return None

        tiers = self._find_margin_table(meta, asset)
        max_leverage = float(asset.get("maxLeverage", 1) or 1)
        funding = float(ctx.get("funding") or 0)

        return HyperliquidMarket(
            quote=PerpQuote(
                symbol=symbol.upper(),
                bid=bid,
                ask=ask,
                mark=mark,
                index=oracle,
                timestamp=book.get("time") if isinstance(book, dict) else None,
                source="hyperliquid",
            ),
            funding_rate=funding,
            max_leverage=max_leverage,
            tiers=tiers,
        )


_provider = None


def get_hyperliquid_perp_provider() -> HyperliquidPerpProvider:
    global _provider
    if _provider is None:
        _provider = HyperliquidPerpProvider()
    return _provider
