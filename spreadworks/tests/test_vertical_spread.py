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
