"""Vertical-spread builder tests."""
from __future__ import annotations
from backend.bots.strategies.vertical_spread import build_vertical_signal, DEFAULT_VERTICAL_PARAMS


def _chain(spot, ticker="NVDA"):
    opts = []
    for s in range(100, 201, 5):
        # crude monotonic pricing: calls cheaper as strike rises; puts cheaper as strike falls
        # Half-spread 0.05 keeps (ask-bid)/mid < max_spread_pct=0.15 even for 0.70 mid options.
        call_mid = max(0.30, (spot - s) * 0.4 + 6.0)
        put_mid = max(0.30, (s - spot) * 0.4 + 6.0)
        opts.append({"strike": s, "type": "call", "bid": round(call_mid - 0.05, 2), "ask": round(call_mid + 0.05, 2)})
        opts.append({"strike": s, "type": "put", "bid": round(put_mid - 0.05, 2), "ask": round(put_mid + 0.05, 2)})
    return {"spot": spot, "expiration": "2026-06-22", "ticker": ticker, "options": opts}


def _p(**o):
    p = dict(DEFAULT_VERTICAL_PARAMS); p.update(o); return p


_CFG = {"bp_pct": 0.02, "pt_pct": 0.50, "sl_pct": 0.50, "max_contracts": 10}


def test_bull_call_spread_is_debit_two_legs():
    sig = build_vertical_signal(kind="bull_call_spread", chain=_chain(140.0),
                                config=_CFG, equity=25000.0, params=_p())
    assert sig is not None and hasattr(sig, "debit") and not hasattr(sig, "credit")
    legs = sig.legs()
    assert len(legs) == 2
    longs = [l for l in legs if l["side"] == "long"]
    shorts = [l for l in legs if l["side"] == "short"]
    assert len(longs) == 1 and len(shorts) == 1
    assert all(l["type"] == "call" for l in legs)
    assert longs[0]["strike"] < shorts[0]["strike"]
    assert sig.debit > 0
    assert sig.max_loss == round(sig.debit * 100, 2)


def test_bear_put_spread_is_debit_puts():
    sig = build_vertical_signal(kind="bear_put_spread", chain=_chain(140.0),
                                config=_CFG, equity=25000.0, params=_p())
    assert sig is not None and hasattr(sig, "debit")
    legs = sig.legs()
    assert all(l["type"] == "put" for l in legs)
    longs = [l for l in legs if l["side"] == "long"][0]
    shorts = [l for l in legs if l["side"] == "short"][0]
    assert longs["strike"] > shorts["strike"]
    assert sig.debit > 0


from backend.bots.executor import compute_mtm


def test_bull_put_spread_is_credit():
    sig = build_vertical_signal(kind="bull_put_spread", chain=_chain(140.0),
                                config=_CFG, equity=25000.0, params=_p())
    assert sig is not None and hasattr(sig, "credit") and not hasattr(sig, "debit")
    legs = sig.legs()
    assert all(l["type"] == "put" for l in legs)
    s = [l for l in legs if l["side"] == "short"][0]
    lo = [l for l in legs if l["side"] == "long"][0]
    assert s["strike"] > lo["strike"]
    assert sig.credit > 0
    assert sig.max_profit == round(sig.credit * 100, 2)


def test_bear_call_spread_is_credit():
    sig = build_vertical_signal(kind="bear_call_spread", chain=_chain(140.0),
                                config=_CFG, equity=25000.0, params=_p())
    assert sig is not None and hasattr(sig, "credit")
    s = [l for l in sig.legs() if l["side"] == "short"][0]
    lo = [l for l in sig.legs() if l["side"] == "long"][0]
    assert s["strike"] < lo["strike"]


def test_debit_vertical_mtm_sign():
    legs = [{"side": "long", "type": "call", "strike": 140, "expiration": "x", "entry_price": 5.0},
            {"side": "short", "type": "call", "strike": 146, "expiration": "x", "entry_price": 2.0}]
    _, pnl = compute_mtm(strategy="bull_call_spread", legs=legs, entry_price=3.0,
                         contracts=1, leg_mids=[7.0, 3.0])
    assert pnl == 100.0


def test_credit_vertical_mtm_sign():
    legs = [{"side": "long", "type": "put", "strike": 130, "expiration": "x", "entry_price": 1.0},
            {"side": "short", "type": "put", "strike": 136, "expiration": "x", "entry_price": 3.0}]
    _, pnl = compute_mtm(strategy="bull_put_spread", legs=legs, entry_price=2.0,
                         contracts=1, leg_mids=[0.5, 1.5])
    assert pnl == 100.0


def _chain_1wide(spot, ticker="SPY"):
    """$1-strike chain (mimics a real SPY 0DTE grid) so short_otm_abs/
    spread_abs dollar offsets land on exact strikes for the assertions."""
    opts = []
    for s in range(int(spot) - 15, int(spot) + 16):
        call_mid = max(0.30, (spot - s) * 0.4 + 6.0)
        put_mid = max(0.30, (s - spot) * 0.4 + 6.0)
        opts.append({"strike": s, "type": "call", "bid": round(call_mid - 0.05, 2), "ask": round(call_mid + 0.05, 2)})
        opts.append({"strike": s, "type": "put", "bid": round(put_mid - 0.05, 2), "ask": round(put_mid + 0.05, 2)})
    return {"spot": spot, "expiration": "2026-08-13", "ticker": ticker, "options": opts}


def test_short_otm_abs_and_spread_abs_override_pct():
    """EBB (registry #23b): short put nearest spot-$2, long put $5 lower —
    short_otm_abs/spread_abs override the pct-of-spot strike computation."""
    sig = build_vertical_signal(
        kind="bull_put_spread", chain=_chain_1wide(600.0),
        config=_CFG, equity=25000.0,
        params=_p(short_otm_abs=2.0, spread_abs=5.0),
    )
    assert sig is not None
    legs = sig.legs()
    short = [l for l in legs if l["side"] == "short"][0]
    long_ = [l for l in legs if l["side"] == "long"][0]
    assert short["strike"] == 598   # spot - $2
    assert long_["strike"] == 593   # short - $5
    assert sig.width == 5


# ---------------------------------------------------------------------------
# REGRESSION: the cheap long wing must not be rejected as a bad quote.
#
# EBB and EBB PM were enabled 2026-08-13 and placed ZERO trades. Every scan
# inside the entry window logged `price_too_low: mid=0.04` (EBB) and
# `mid=0.03` (EBB PM). Cause: _spread_ok applied min_option_price AND
# max_spread_pct to BOTH legs, including the long wing that is bought $2-$5
# further OTM. On a 0DTE put spread that wing is worth 3-4 cents by
# construction and quotes 0.02/0.04 — a 66% relative spread. Both guards are
# premium-quality checks and only make sense on the leg being SOLD.
# ---------------------------------------------------------------------------

# EBB's own sizing: bp_pct 0.20 on a $3k paper account, 1 contract cap.
_ZCFG = {"bp_pct": 0.20, "pt_pct": 1.0, "sl_pct": 9.9999, "max_contracts": 1}


def _zdte_chain(spot=640.0):
    """0DTE-shaped puts: near the money worth real money, a few points OTM
    worth pennies with a wide relative market — exactly what broke EBB."""
    opts = []
    for s in range(600, 681, 1):
        d = spot - s                      # points OTM for a put
        if d <= 0:
            put_mid = 2.50 + abs(d) * 0.4
        elif d <= 1:
            put_mid = 0.55
        elif d <= 2:
            put_mid = 0.28
        elif d <= 3:
            put_mid = 0.04                # <- the wing EBB PM buys
        else:
            put_mid = 0.03                # <- the wing EBB buys
        half = 0.01 if put_mid < 0.10 else 0.03
        opts.append({"strike": s, "type": "put",
                     "bid": round(max(put_mid - half, 0.01), 2),
                     "ask": round(put_mid + half, 2)})
        opts.append({"strike": s, "type": "call", "bid": 1.00, "ask": 1.06})
    return {"spot": spot, "expiration": "2026-08-14", "ticker": "SPY", "options": opts}


def test_cheap_long_wing_does_not_block_a_credit_spread():
    """The exact EBB PM config: short spot-1, $2 wing. Must build."""
    sig = build_vertical_signal(
        kind="bull_put_spread", chain=_zdte_chain(640.0), config=_ZCFG, equity=3000.0,
        params=_p(short_otm_abs=1.0, spread_abs=2.0,
                  min_option_price=0.10, max_spread_pct=0.15, min_credit=0.10))
    assert sig is not None, "cheap wing must not be rejected — this is the EBB bug"
    legs = sig.legs()
    assert len(legs) == 2 and all(l["type"] == "put" for l in legs)
    short = [l for l in legs if l["side"] == "short"][0]
    long_ = [l for l in legs if l["side"] == "long"][0]
    assert short["strike"] == 639          # spot - 1
    assert long_["strike"] == 637          # short - 2
    assert sig.net > 0                     # it is a credit


def test_short_leg_price_floor_still_enforced():
    """The floor must still reject a short leg with no premium in it — the
    guard was mis-scoped, not wrong."""
    sig = build_vertical_signal(
        kind="bull_put_spread", chain=_zdte_chain(640.0), config=_ZCFG, equity=3000.0,
        params=_p(short_otm_abs=4.0, spread_abs=2.0,     # short lands in the penny zone
                  min_option_price=0.10, max_spread_pct=0.15, min_credit=0.01))
    assert sig is None, "a 3-cent SHORT leg has no premium worth selling"


def test_unquoted_wing_is_still_rejected():
    """Cheap is fine; absent is not — an unquoted wing means uncapped risk."""
    ch = _zdte_chain(640.0)
    for o in ch["options"]:
        if o["type"] == "put" and o["strike"] == 637:
            o["bid"], o["ask"] = 0.0, 0.0
    sig = build_vertical_signal(
        kind="bull_put_spread", chain=ch, config=_ZCFG, equity=3000.0,
        params=_p(short_otm_abs=1.0, spread_abs=2.0,
                  min_option_price=0.10, max_spread_pct=0.15, min_credit=0.10))
    assert sig is None, "a wing with no market must be rejected"
