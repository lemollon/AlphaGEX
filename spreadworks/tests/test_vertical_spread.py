"""Vertical-spread builder tests."""
from __future__ import annotations
from backend.bots.strategies.vertical_spread import build_vertical_signal, DEFAULT_VERTICAL_PARAMS


def _chain(spot, ticker="NVDA"):
    opts = []
    for s in range(100, 201, 5):
        # crude monotonic pricing: calls cheaper as strike rises; puts cheaper as strike falls
        call_mid = max(0.30, (spot - s) * 0.4 + 6.0)
        put_mid = max(0.30, (s - spot) * 0.4 + 6.0)
        opts.append({"strike": s, "type": "call", "bid": round(call_mid - 0.2, 2), "ask": round(call_mid + 0.2, 2)})
        opts.append({"strike": s, "type": "put", "bid": round(put_mid - 0.2, 2), "ask": round(put_mid + 0.2, 2)})
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
