"""Strike mapping engine -- orchestrator returning TradeStructure or None.

Pipeline (master spec section 3):
    1. wall_finder.find_wall            -> Wall | None
    2. letf_mapper.map_to_letf          -> LETFTarget
    3. leg_builder.build_legs           -> ThreeLegStructure | None
    4. attach LETF chain quotes         -> per-leg OptionLeg (None if missing)
    5. economic-quality filters         -> reject on OI / bid-ask / net cost

Steps 4-5 enforce the economic conditions that Phase 3 gates G06/G07/G08
will formalize. Doing them here keeps Phase 2 self-contained: a successful
engine call returns a TradeStructure that already passes those gates.
The Phase 3 gate modules can be thin wrappers over the same predicates.

Returns None when:
    - no qualifying wall (Step 1)
    - no strikes in band / lowest-strike edge / no OTM range (Step 3)
    - any leg's quote is missing from the chain (Step 4)
    - any leg has OI < 200 (Gate G06 inline)
    - any leg has bid-ask > 20% of mid (Gate G07 inline)
    - net cost > 30% of long-call mid (Gate G08 inline)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Sequence

from trading.goliath.models import GoliathConfig
from trading.goliath.strike_mapping.leg_builder import (
    ThreeLegStructure,
    build_legs,
)
from trading.goliath.strike_mapping.letf_mapper import LETFTarget, map_to_letf
from trading.goliath.strike_mapping.wall_finder import (
    GammaStrike,
    Wall,
    find_wall,
)

# Economic thresholds (master spec section 2, gates G06-G08).
MIN_OI_PER_LEG = 200
MAX_BID_ASK_RATIO = 0.20
MAX_NET_COST_TO_CALL_RATIO = 0.30


@dataclass(frozen=True)
class OptionLeg:
    """One LETF option leg with strike + market data."""

    strike: float
    bid: float
    ask: float
    open_interest: int
    contract_type: Literal["put", "call"]


@dataclass(frozen=True)
class TradeStructure:
    """Complete 3-leg structure produced by the engine.

    Attributes:
        short_put / long_put / long_call: per-leg quote + OI
        put_spread_credit: short_put_mid - long_put_mid (positive = credit)
        long_call_cost: long_call mid price
        net_cost: long_call_cost - put_spread_credit (negative = net credit)
        wall: the underlying-side wall (provenance)
        letf_target: the LETF-side target band (provenance)
    """

    short_put: OptionLeg
    long_put: OptionLeg
    long_call: OptionLeg
    put_spread_credit: float
    long_call_cost: float
    net_cost: float
    wall: Wall
    letf_target: LETFTarget


def compute_mid(leg: OptionLeg) -> float:
    """Mid price of an option leg = (bid + ask) / 2.

    Public so gate modules (G07, G08) can reuse the same primitive
    without duplicating the formula. Returns the raw mid; callers are
    responsible for handling non-positive results.
    """
    return (leg.bid + leg.ask) / 2.0


def passes_bid_ask(leg: OptionLeg) -> bool:
    """Pass when the leg's bid-ask spread is <= MAX_BID_ASK_RATIO of mid.

    Public so Gate G07 can wrap this directly. Returns False when mid
    is non-positive (a degenerate leg fails the quality check).
    """
    mid = compute_mid(leg)
    if mid <= 0:
        return False
    return (leg.ask - leg.bid) / mid <= MAX_BID_ASK_RATIO


def build_trade_structure(
    underlying_strikes: Sequence[GammaStrike],
    underlying_spot: float,
    letf_spot: float,
    sigma_annualized: float,
    t_years: float,
    letf_chain: dict[tuple[float, str], OptionLeg],
    config: GoliathConfig,
) -> Optional[TradeStructure]:
    """Run the full strike-mapping pipeline and return a TradeStructure.

    Args:
        underlying_strikes: gamma-by-strike for the underlying
        underlying_spot: underlying spot price
        letf_spot: LETF spot price
        sigma_annualized: annualized realized vol of the underlying
        t_years: time horizon (e.g. 7/365 for 1-week DTE)
        letf_chain: dict keyed by (strike, "put"/"call") -> OptionLeg
        config: GoliathConfig

    Returns:
        TradeStructure on success, None on any rejection.
    """
    wall = find_wall(underlying_strikes, underlying_spot, config)
    if wall is None:
        return None

    letf_target = map_to_letf(
        underlying_wall_price=wall.strike,
        underlying_spot=underlying_spot,
        letf_spot=letf_spot,
        sigma_annualized=sigma_annualized,
        t_years=t_years,
        config=config,
    )

    available_strikes = sorted({k[0] for k in letf_chain.keys()})
    legs = build_legs(letf_target, available_strikes, letf_spot, config)
    if legs is None:
        return None

    short_put = letf_chain.get((legs.short_put_strike, "put"))
    long_put = letf_chain.get((legs.long_put_strike, "put"))
    long_call = letf_chain.get((legs.long_call_strike, "call"))
    if short_put is None or long_put is None or long_call is None:
        return None

    # Gate G06: OI >= 200 on each leg.
    for leg in (short_put, long_put, long_call):
        if leg.open_interest < MIN_OI_PER_LEG:
            return None

    # Gate G07: bid-ask spread <= 20% of mid on each leg.
    for leg in (short_put, long_put, long_call):
        if not passes_bid_ask(leg):
            return None

    short_put_mid = compute_mid(short_put)
    long_put_mid = compute_mid(long_put)
    long_call_mid = compute_mid(long_call)
    put_spread_credit = short_put_mid - long_put_mid
    net_cost = long_call_mid - put_spread_credit

    # Gate G08: net cost (debit) <= 30% of long-call cost. Credits trivially pass.
    if long_call_mid <= 0:
        return None
    if net_cost > MAX_NET_COST_TO_CALL_RATIO * long_call_mid:
        return None

    return TradeStructure(
        short_put=short_put,
        long_put=long_put,
        long_call=long_call,
        put_spread_credit=float(put_spread_credit),
        long_call_cost=float(long_call_mid),
        net_cost=float(net_cost),
        wall=wall,
        letf_target=letf_target,
    )
