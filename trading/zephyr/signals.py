"""
ZEPHYR Signals - the scalp trigger + fee gate (pure logic, fully testable).

Edge definition (in cents, both sides modeled as a long of that side's contract):
  - YES is underpriced when fair_cents > yes_ask  -> buy YES, edge ~ fair - ask
  - YES is overpriced  when fair_cents < yes_bid  -> buy NO,  edge ~ bid - fair
A scalp is only allowed when |edge| clears (round_trip_fee + buffer). Makers are
preferred (cheaper fees + post inside the spread); takers only fire when the
sharp line has jumped far enough that crossing still clears the gate.
"""

from __future__ import annotations

from typing import Optional

from .models import (
    DEFAULT_MAKER_FEE_COEFF,
    DEFAULT_TAKER_FEE_COEFF,
    FairValueQuote,
    ScalpSignal,
    SignalAction,
    Side,
    kalshi_fee,
    market_config,
)


def _yes_no_from_book(yes_bid: float, yes_ask: float) -> tuple[float, float, float]:
    """Return (yes_mid, no_bid, no_ask). NO price = 100 - YES price (Kalshi)."""
    yes_mid = (yes_bid + yes_ask) / 2.0
    no_bid = 100.0 - yes_ask
    no_ask = 100.0 - yes_bid
    return yes_mid, no_bid, no_ask


def required_edge_cents(price_cents: float, contracts: int, sport: str, is_maker: bool) -> float:
    """Fee gate threshold: round-trip fee (in cents-equiv) + the sport buffer.

    We size the fee at the *entry* price for both legs as a conservative proxy
    (exit price is unknown at decision time and a scalp closes near entry).
    """
    cfg = market_config(sport)
    fees = cfg.get("fees", {})
    entry_coeff = fees.get("maker_coeff", DEFAULT_MAKER_FEE_COEFF) if is_maker \
        else fees.get("taker_coeff", DEFAULT_TAKER_FEE_COEFF)
    # exit assumed taker (we want OUT fast); conservative.
    exit_coeff = fees.get("taker_coeff", DEFAULT_TAKER_FEE_COEFF)
    rt_fee_dollars = (
        kalshi_fee(price_cents, contracts, entry_coeff)
        + kalshi_fee(price_cents, contracts, exit_coeff)
    )
    # convert $ fee to cents-of-edge per contract so it compares to edge_cents
    rt_fee_cents = (rt_fee_dollars / max(contracts, 1)) * 100.0
    return rt_fee_cents + float(cfg.get("min_edge_buffer_cents", 2.0))


def evaluate(
    market_id: str,
    sport: str,
    yes_bid: float,
    yes_ask: float,
    fair: FairValueQuote,
    contracts: Optional[int] = None,
    spread_too_wide_cents: float = 8.0,
    min_provider_confidence: float = 0.25,
) -> ScalpSignal:
    """Decide whether (and how) to scalp this market right now."""
    cfg = market_config(sport)
    contracts = contracts or int(cfg.get("max_contracts_per_scalp", 5))
    yes_mid, no_bid, no_ask = _yes_no_from_book(yes_bid, yes_ask)
    fair_cents = fair.fair_cents

    def _none(reason: str) -> ScalpSignal:
        return ScalpSignal(
            action=SignalAction.NONE, market_id=market_id, sport=sport, side=None,
            limit_cents=None, contracts=contracts, fair_cents=fair_cents,
            kalshi_mid_cents=yes_mid, edge_cents=0.0, required_edge_cents=0.0,
            reason=reason,
        )

    # --- guard rails ------------------------------------------------------
    if fair.confidence < min_provider_confidence:
        return _none(f"fair-value confidence {fair.confidence:.2f} below floor")
    spread = yes_ask - yes_bid
    if spread <= 0 or spread > spread_too_wide_cents:
        return _none(f"spread {spread:.1f}c unusable (>{spread_too_wide_cents}c or crossed)")

    # --- which side is mispriced? ----------------------------------------
    buy_yes_edge = fair_cents - yes_ask     # taker buys YES at ask
    buy_no_edge = fair_cents_to_no_edge(fair_cents, no_ask)  # taker buys NO at ask
    maker_yes_edge = fair_cents - yes_bid   # maker posts YES at (near) bid
    maker_no_edge = (100.0 - fair_cents) - no_bid  # maker posts NO at (near) bid

    # Prefer maker: post inside the spread on the underpriced side.
    if fair_cents > yes_mid:
        side, is_maker = Side.YES, True
        limit = min(yes_ask - 1.0, yes_bid + 1.0)  # one tick inside the spread
        edge = maker_yes_edge
        taker_edge, taker_limit = buy_yes_edge, yes_ask
        action_maker, action_taker = SignalAction.BUY_YES_MAKER, SignalAction.BUY_YES_TAKER
    else:
        side, is_maker = Side.NO, True
        limit = min(no_ask - 1.0, no_bid + 1.0)
        edge = maker_no_edge
        taker_edge, taker_limit = buy_no_edge, no_ask
        action_maker, action_taker = SignalAction.BUY_NO_MAKER, SignalAction.BUY_NO_TAKER

    # --- fee gate: maker first, then taker -------------------------------
    maker_price = limit if limit else (yes_bid if side == Side.YES else no_bid)
    req_maker = required_edge_cents(maker_price, contracts, sport, is_maker=True)
    if edge >= req_maker and 1.0 <= maker_price <= 99.0:
        return ScalpSignal(
            action=action_maker, market_id=market_id, sport=sport, side=side,
            limit_cents=round(maker_price, 1), contracts=contracts, fair_cents=fair_cents,
            kalshi_mid_cents=yes_mid, edge_cents=round(edge, 2),
            required_edge_cents=round(req_maker, 2),
            reason=f"maker {side.value}: edge {edge:.1f}c >= req {req_maker:.1f}c",
        )

    # Taker only if the sharp line jumped far enough to clear the costlier gate.
    req_taker = required_edge_cents(taker_limit, contracts, sport, is_maker=False)
    if taker_edge >= req_taker and 1.0 <= taker_limit <= 99.0:
        return ScalpSignal(
            action=action_taker, market_id=market_id, sport=sport, side=side,
            limit_cents=round(taker_limit, 1), contracts=contracts, fair_cents=fair_cents,
            kalshi_mid_cents=yes_mid, edge_cents=round(taker_edge, 2),
            required_edge_cents=round(req_taker, 2),
            reason=f"taker {side.value}: edge {taker_edge:.1f}c >= req {req_taker:.1f}c",
        )

    return _none(
        f"edge too thin: maker {edge:.1f}<{req_maker:.1f} / taker {taker_edge:.1f}<{req_taker:.1f}"
    )


def fair_cents_to_no_edge(fair_cents: float, no_ask: float) -> float:
    """Edge of buying NO at no_ask given YES fair. fair(NO)=100-fair(YES)."""
    return (100.0 - fair_cents) - no_ask
