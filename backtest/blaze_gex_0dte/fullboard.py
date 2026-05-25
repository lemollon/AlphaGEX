"""Full-board GEX reconstruction from the orat_options_eod EOD chain.

Computes true net-GEX / walls / flip / regime from ALL strikes across ALL
expirations for a trade_date (gamma & OI are provided by ORAT, so no IV solve).
This is the production-fidelity counterpart to the local ATM-band reconstruction
in reconstruct.py.
"""
from __future__ import annotations
import datetime as dt
import math
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

_TRADING_DAYS = 252.0

@dataclass(frozen=True)
class EodGex:
    trade_date: dt.date
    spot: float
    net_gex: float
    call_wall: float
    put_wall: float
    flip_point: float
    regime: str
    sigma_1d_band_width: float

# row = (strike, gamma, call_oi, put_oi, underlying_price, call_iv)
Row = Tuple[float, Optional[float], Optional[int], Optional[int], Optional[float], Optional[float]]

def compute_eod_gex(rows: Iterable[Row], trade_date: dt.date) -> Optional[EodGex]:
    rows = [r for r in rows if r and r[0] is not None]
    if not rows:
        return None
    spots = [float(r[4]) for r in rows if r[4] is not None and float(r[4]) > 0]
    if not spots:
        return None
    spot = max(spots)
    # aggregate gamma*OI per strike across all expirations
    cg: dict = {}
    pg: dict = {}
    for strike, gamma, call_oi, put_oi, _u, _iv in rows:
        k = float(strike)
        g = float(gamma) if gamma is not None else 0.0
        cg[k] = cg.get(k, 0.0) + g * (float(call_oi) if call_oi is not None else 0.0)
        pg[k] = pg.get(k, 0.0) + g * (float(put_oi) if put_oi is not None else 0.0)
    if not cg:
        return None
    call_cands = [(v, k) for k, v in cg.items() if k >= spot and v > 0]
    put_cands = [(pg[k], k) for k in pg if k <= spot and pg[k] > 0]
    call_wall = max(call_cands)[1] if call_cands else spot
    put_wall = max(put_cands)[1] if put_cands else spot
    scale = 100.0 * spot * spot * 0.01
    net_gex = sum(cg[k] - pg.get(k, 0.0) for k in cg) * scale
    # flip: strike where cumulative net gamma crosses zero
    flip = spot
    cum = 0.0
    for k in sorted(cg):
        nxt = cum + (cg[k] - pg.get(k, 0.0))
        if cum <= 0 < nxt or cum >= 0 > nxt:
            flip = k
            break
        cum = nxt
    regime = "MODERATE_NEGATIVE" if net_gex < 0 else "MODERATE_POSITIVE"
    # ATM IV from the strike nearest spot that has a usable call_iv
    atm_iv = None
    best_dist = None
    for strike, _g, _co, _po, _u, call_iv in rows:
        if call_iv is None or float(call_iv) <= 0:
            continue
        dist = abs(float(strike) - spot)
        if best_dist is None or dist < best_dist:
            best_dist = dist
            atm_iv = float(call_iv)
    sigma_1d = spot * atm_iv * math.sqrt(1.0 / _TRADING_DAYS) if atm_iv else 0.0
    return EodGex(trade_date=trade_date, spot=spot, net_gex=net_gex,
                  call_wall=call_wall, put_wall=put_wall, flip_point=flip,
                  regime=regime, sigma_1d_band_width=sigma_1d)

def load_eod_gex(conn, trade_date: dt.date, ticker: str = "SPY") -> Optional[EodGex]:
    """Load + compute full-board GEX for one trade_date from orat_options_eod."""
    cur = conn.cursor()
    cur.execute(
        "SELECT strike, gamma, call_oi, put_oi, underlying_price, call_iv "
        "FROM orat_options_eod WHERE ticker = %s AND trade_date = %s",
        (ticker, trade_date),
    )
    rows = cur.fetchall()
    cur.close()
    return compute_eod_gex(rows, trade_date)
