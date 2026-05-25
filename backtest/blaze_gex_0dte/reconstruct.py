"""Reconstruct a per-minute GexSnapshot stream from a 0DTE DayChain."""
from __future__ import annotations
import datetime as dt
import math
from typing import List, Optional
from zoneinfo import ZoneInfo

from backtest.intraday_walls.bs import bs_gamma, implied_vol, derive_spot_from_parity
from trading.helios.gex_client import GexSnapshot
from .loader import DayChain

_ET = ZoneInfo("America/New_York")
_TRADING_DAYS = 252.0
_CLOSE_HOUR = 16  # 4 PM ET settlement

def regime_for_net_gex(net_gex: float) -> str:
    return "MODERATE_NEGATIVE" if net_gex < 0 else "MODERATE_POSITIVE"

def _t_years_remaining(trade_date: dt.date, minute: int, first_bar_et_hour=9, first_bar_et_min=30) -> float:
    open_et = dt.datetime(trade_date.year, trade_date.month, trade_date.day,
                          first_bar_et_hour, first_bar_et_min, tzinfo=_ET)
    now_et = open_et + dt.timedelta(minutes=minute)
    close_et = dt.datetime(trade_date.year, trade_date.month, trade_date.day, _CLOSE_HOUR, 0, tzinfo=_ET)
    secs = max((close_et - now_et).total_seconds(), 60.0)
    return secs / (365.0 * 24.0 * 3600.0)

def _atm_strike(chain_keys, spot: float) -> Optional[float]:
    strikes = sorted({k for (k, _r) in chain_keys})
    if not strikes:
        return None
    return min(strikes, key=lambda k: abs(k - spot))

def build_snapshots(day: DayChain) -> List[GexSnapshot]:
    out: List[GexSnapshot] = []
    for minute in day.minutes():
        chain = day.bars[minute]
        t = _t_years_remaining(day.trade_date, minute)
        both = [(c[0] + p[0], k) for (k, r), c in chain.items()
                if r == "C" and (k, "P") in chain
                for p in [chain[(k, "P")]]
                if c[0] and p[0] and c[1] and p[1]]
        if not both:
            continue
        both.sort()
        atm_k = both[0][1]
        cm = (chain[(atm_k, "C")][0] + chain[(atm_k, "C")][1]) / 2
        pm = (chain[(atm_k, "P")][0] + chain[(atm_k, "P")][1]) / 2
        spot = derive_spot_from_parity(cm, pm, atm_k, t)
        if spot <= 0:
            continue
        by_strike = {}
        atm_iv = None
        for (k, r), q in chain.items():
            mid = day.mid(minute, k, r)
            if mid is None:
                continue
            oi = day.oi.get((k, r), 0)
            if oi <= 0:
                continue
            iv = implied_vol(mid, spot, k, t, r == "C")
            if iv is None:
                continue
            if k == atm_k and r == "C":
                atm_iv = iv
            dg = bs_gamma(spot, k, t, iv) * oi * 100.0 * spot * spot * 0.01
            d = by_strike.setdefault(k, {"C": 0.0, "P": 0.0})
            d["C" if r == "C" else "P"] += dg
        if not by_strike or atm_iv is None:
            continue
        call_above = [(v["C"], k) for k, v in by_strike.items() if k >= spot and v["C"] > 0]
        put_below = [(v["P"], k) for k, v in by_strike.items() if k <= spot and v["P"] > 0]
        call_wall = max(call_above)[1] if call_above else spot
        put_wall = max(put_below)[1] if put_below else spot
        net_gex = sum(v["C"] - v["P"] for v in by_strike.values())
        flip = spot
        cum = 0.0
        for k in sorted(by_strike):
            nxt = cum + (by_strike[k]["C"] - by_strike[k]["P"])
            if cum <= 0 < nxt or cum >= 0 > nxt:
                flip = k
                break
            cum = nxt
        sigma_1d = spot * atm_iv * math.sqrt(1.0 / _TRADING_DAYS)
        # Encode snapshot_at in the replay engine's FIXED UTC-5h minute
        # convention so engine._minutes_since_open_ct() recovers exactly the
        # loader's bar-minute (minute 0 = 9:30 ET open) in BOTH EST and EDT.
        # A real ET->UTC encode would drift +60 min in winter (engine uses a
        # fixed -5h, not DST-aware), mis-mapping the PT/SL mark lookups.
        # 13:30 UTC - 5h = 08:30 -> minute 0; +minute thereafter.
        snap_at = dt.datetime(day.trade_date.year, day.trade_date.month, day.trade_date.day,
                              13, 30, tzinfo=dt.timezone.utc) + dt.timedelta(minutes=minute)
        out.append(GexSnapshot(
            symbol="SPY", spot=spot, net_gex=net_gex, flip_point=flip,
            call_wall=call_wall, put_wall=put_wall, vix=0.0,
            regime=regime_for_net_gex(net_gex),
            sigma_1d_band_width=sigma_1d, snapshot_at=snap_at,
        ))
    return out
