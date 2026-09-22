"""Shared perpetual paper/shadow execution realism.

This module is intentionally venue-agnostic. It never places real orders.
It provides:
- executable-side paper fills (ask for buys, bid for sells)
- configurable taker fees
- funding accrual
- tiered maintenance margin
- isolated-margin liquidation estimates
- mark-price account metrics

Venue-specific adapters can override fee schedules, risk tiers, mark price,
funding interval and exact liquidation calculations later without changing
strategy code.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PerpQuote:
    symbol: str
    bid: float
    ask: float
    mark: float
    index: float
    timestamp: Optional[object] = None
    source: str = "unknown"

    @property
    def mid(self) -> float:
        if self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2.0
        return self.mark or self.index


@dataclass(frozen=True)
class MarginTier:
    max_notional: float
    maintenance_margin_rate: float
    maintenance_amount: float = 0.0


@dataclass(frozen=True)
class PerpVenueRules:
    symbol: str
    default_leverage: float
    max_leverage: float
    taker_fee_bps: float
    maker_fee_bps: float
    funding_interval_hours: float
    fallback_maintenance_margin_rate: float
    impact_bps: float = 2.0
    fallback_slippage_bps: float = 10.0
    tiers: Sequence[MarginTier] = ()


@dataclass(frozen=True)
class FillEstimate:
    fill_price: float
    reference_price: float
    fee_usd: float
    slippage_usd: float
    slippage_bps: float
    used_executable_quote: bool


@dataclass(frozen=True)
class MarginEstimate:
    notional: float
    initial_margin: float
    maintenance_margin: float
    maintenance_margin_rate: float
    maintenance_amount: float
    leverage: float
    liquidation_price: Optional[float]
    distance_to_liquidation_pct: Optional[float]


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return float(default)


def _load_tiers(symbol: str) -> List[MarginTier]:
    """Load venue risk tiers from PERP_MARGIN_TIERS_JSON.

    Supported shape:
    {
      "BTC-PERP": [
        {"max_notional": 50000, "maintenance_margin_rate": 0.005,
         "maintenance_amount": 0},
        ...
      ]
    }
    """
    raw = os.getenv("PERP_MARGIN_TIERS_JSON", "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        rows = parsed.get(symbol, []) if isinstance(parsed, dict) else []
        tiers = [
            MarginTier(
                max_notional=float(row["max_notional"]),
                maintenance_margin_rate=float(row["maintenance_margin_rate"]),
                maintenance_amount=float(row.get("maintenance_amount", 0.0)),
            )
            for row in rows
        ]
        tiers.sort(key=lambda x: x.max_notional)
        return tiers
    except Exception as exc:
        logger.warning("Invalid PERP_MARGIN_TIERS_JSON for %s: %s", symbol, exc)
        return []


def get_rules(
    symbol: str,
    *,
    default_leverage: float,
    max_leverage: float,
    fallback_maintenance_margin_rate: float,
    funding_interval_hours: float = 8.0,
) -> PerpVenueRules:
    """Build configurable venue rules for a symbol.

    Until a venue adapter supplies authenticated account/risk data, defaults are
    deliberately conservative and can be overridden with environment variables.
    """
    key = symbol.replace("-", "_")
    return PerpVenueRules(
        symbol=symbol,
        default_leverage=_env_float(
            f"{key}_DEFAULT_LEVERAGE",
            _env_float("PERP_DEFAULT_LEVERAGE", default_leverage),
        ),
        max_leverage=_env_float(
            f"{key}_MAX_LEVERAGE",
            _env_float("PERP_MAX_LEVERAGE", max_leverage),
        ),
        taker_fee_bps=_env_float(
            f"{key}_TAKER_FEE_BPS",
            _env_float("PERP_TAKER_FEE_BPS", 6.0),
        ),
        maker_fee_bps=_env_float(
            f"{key}_MAKER_FEE_BPS",
            _env_float("PERP_MAKER_FEE_BPS", 2.0),
        ),
        funding_interval_hours=_env_float(
            f"{key}_FUNDING_INTERVAL_HOURS",
            _env_float("PERP_FUNDING_INTERVAL_HOURS", funding_interval_hours),
        ),
        fallback_maintenance_margin_rate=_env_float(
            f"{key}_MAINTENANCE_MARGIN_RATE",
            fallback_maintenance_margin_rate,
        ),
        impact_bps=_env_float(
            f"{key}_PAPER_IMPACT_BPS",
            _env_float("PERP_PAPER_IMPACT_BPS", 2.0),
        ),
        fallback_slippage_bps=_env_float(
            f"{key}_FALLBACK_SLIPPAGE_BPS",
            _env_float("PERP_FALLBACK_SLIPPAGE_BPS", 10.0),
        ),
        tiers=tuple(_load_tiers(symbol)),
    )


def select_margin_tier(rules: PerpVenueRules, notional: float) -> MarginTier:
    n = abs(float(notional))
    for tier in rules.tiers:
        if n <= tier.max_notional:
            return tier
    if rules.tiers:
        return rules.tiers[-1]
    return MarginTier(
        max_notional=float("inf"),
        maintenance_margin_rate=rules.fallback_maintenance_margin_rate,
        maintenance_amount=0.0,
    )


def simulate_taker_fill(
    side: str,
    quantity: float,
    rules: PerpVenueRules,
    *,
    bid: Optional[float] = None,
    ask: Optional[float] = None,
    mark: Optional[float] = None,
    fallback_price: Optional[float] = None,
) -> FillEstimate:
    """Estimate a taker fill from the executable side of the market.

    When bid/ask are unavailable, use the fallback price plus a conservative
    configurable slippage assumption. This preserves current behavior while
    making the degraded-data path explicit.
    """
    s = side.lower()
    qty = abs(float(quantity))
    if qty <= 0:
        raise ValueError("quantity must be positive")

    use_book = bool(bid and ask and bid > 0 and ask > 0 and ask >= bid)
    if use_book:
        reference = ask if s == "long" else bid
        impact = rules.impact_bps / 10000.0
        fill = reference * (1.0 + impact if s == "long" else 1.0 - impact)
        baseline = mark if mark and mark > 0 else (bid + ask) / 2.0
    else:
        baseline = fallback_price or mark
        if not baseline or baseline <= 0:
            raise ValueError("no valid quote or fallback price")
        reference = float(baseline)
        slip = rules.fallback_slippage_bps / 10000.0
        fill = reference * (1.0 + slip if s == "long" else 1.0 - slip)

    notional = abs(fill * qty)
    fee = notional * rules.taker_fee_bps / 10000.0
    slippage_usd = abs(fill - float(baseline)) * qty
    slippage_bps = abs(fill - float(baseline)) / float(baseline) * 10000.0

    return FillEstimate(
        fill_price=fill,
        reference_price=float(reference),
        fee_usd=fee,
        slippage_usd=slippage_usd,
        slippage_bps=slippage_bps,
        used_executable_quote=use_book,
    )


def funding_cashflow(
    *,
    notional: float,
    side: str,
    funding_rate: float,
    intervals: float = 1.0,
) -> float:
    """Return signed account cashflow from funding.

    Positive return value = account receives funding.
    Negative return value = account pays funding.

    Conventional linear-perp convention:
    positive funding => longs pay shorts.
    """
    n = abs(float(notional))
    rate = float(funding_rate or 0.0)
    count = max(0.0, float(intervals))
    payment = n * rate * count
    return -payment if side.lower() == "long" else payment


def estimate_margin(
    *,
    side: str,
    entry_price: float,
    mark_price: float,
    quantity: float,
    leverage: float,
    rules: PerpVenueRules,
    isolated_margin: Optional[float] = None,
) -> MarginEstimate:
    """Estimate dynamic initial/maintenance margin and isolated liquidation.

    The tier is selected from CURRENT MARK-PRICE NOTIONAL, so maintenance margin
    can change when price moves even when quantity does not.
    """
    qty = abs(float(quantity))
    if qty <= 0 or entry_price <= 0 or mark_price <= 0:
        raise ValueError("entry_price, mark_price and quantity must be positive")

    lev = min(max(float(leverage), 1.0), max(float(rules.max_leverage), 1.0))
    current_notional = mark_price * qty
    entry_notional = entry_price * qty
    tier = select_margin_tier(rules, current_notional)

    initial = entry_notional / lev
    margin = float(isolated_margin) if isolated_margin is not None else initial
    maintenance = max(
        0.0,
        current_notional * tier.maintenance_margin_rate - tier.maintenance_amount,
    )

    mmr = tier.maintenance_margin_rate
    deduction = tier.maintenance_amount
    if side.lower() == "long":
        denominator = qty * max(1e-12, 1.0 - mmr)
        liq = (entry_notional - margin - deduction) / denominator
    else:
        denominator = qty * (1.0 + mmr)
        liq = (entry_notional + margin + deduction) / denominator

    liq = max(0.0, liq)
    distance = abs(mark_price - liq) / mark_price * 100.0 if mark_price else None

    return MarginEstimate(
        notional=current_notional,
        initial_margin=initial,
        maintenance_margin=maintenance,
        maintenance_margin_rate=mmr,
        maintenance_amount=deduction,
        leverage=lev,
        liquidation_price=liq,
        distance_to_liquidation_pct=distance,
    )


def net_realized_pnl(
    *,
    side: str,
    quantity: float,
    entry_fill_price: float,
    exit_fill_price: float,
    entry_fee_usd: float = 0.0,
    exit_fee_usd: float = 0.0,
    funding_cashflow_usd: float = 0.0,
) -> float:
    direction = 1.0 if side.lower() == "long" else -1.0
    gross = (float(exit_fill_price) - float(entry_fill_price)) * abs(float(quantity)) * direction
    return gross - float(entry_fee_usd) - float(exit_fee_usd) + float(funding_cashflow_usd)
