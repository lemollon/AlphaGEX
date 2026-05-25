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

from backtest.intraday_walls.bs import derive_spot_from_parity
from backtest.joshua_replay.engine import replay_day, TradeOutcome
from trading.helios.gex_client import GexSnapshot
from .loader import DayChain, load_day
from .reconstruct import _t_years_remaining
from .providers import make_providers
from .runner import _minute_of

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

def parity_spot_at_minute(day: DayChain, minute: int) -> Optional[float]:
    """Intraday spot via put-call parity at the most-ATM strike in the 0DTE chain."""
    chain = day.bars.get(minute)
    if not chain:
        return None
    t = _t_years_remaining(day.trade_date, minute)
    both = []
    for (k, r), q in chain.items():
        if r != "C":
            continue
        p = chain.get((k, "P"))
        if not p:
            continue
        c_bid, c_ask = q
        p_bid, p_ask = p
        if not (c_bid and c_ask and p_bid and p_ask):
            continue
        cm = (c_bid + c_ask) / 2.0
        pm = (p_bid + p_ask) / 2.0
        both.append((cm + pm, k, cm, pm))
    if not both:
        return None
    both.sort()
    _, atm_k, cm, pm = both[0]
    spot = derive_spot_from_parity(cm, pm, atm_k, t)
    return spot if spot > 0 else None


def build_fullboard_snapshots(day: DayChain, eod: EodGex) -> List[GexSnapshot]:
    """Per-minute GexSnapshots: intraday parity spot + the day's full-board GEX
    (walls/flip/regime/sigma held constant intraday)."""
    out: List[GexSnapshot] = []
    for minute in day.minutes():
        spot = parity_spot_at_minute(day, minute)
        if spot is None:
            continue
        snap_at = dt.datetime(day.trade_date.year, day.trade_date.month, day.trade_date.day,
                              13, 30, tzinfo=dt.timezone.utc) + dt.timedelta(minutes=minute)
        out.append(GexSnapshot(
            symbol="SPY", spot=spot, net_gex=eod.net_gex, flip_point=eod.flip_point,
            call_wall=eod.call_wall, put_wall=eod.put_wall, vix=0.0,
            regime=eod.regime, sigma_1d_band_width=eod.sigma_1d_band_width, snapshot_at=snap_at,
        ))
    return out


def replay_daychain_fullboard(day: DayChain, eod: EodGex, config) -> List[TradeOutcome]:
    snaps = build_fullboard_snapshots(day, eod)
    if not snaps:
        return []
    _debit_unused, mark_provider = make_providers(day)

    def debit_estimator(snap, action) -> float:
        minute = _minute_of(snap)
        r = "C" if action.direction == "call" else "P"
        lq = day.quote(minute, float(action.long_strike), r)
        sq = day.quote(minute, float(action.short_strike), r)
        if not lq or not sq or lq[1] is None or sq[0] is None:
            return 0.0
        return max(0.0, lq[1] - sq[0])

    return replay_day(snaps, config=config, spot_mark_provider=mark_provider, debit_estimator=debit_estimator)


def run_fullboard_backtest(iron_db_url: str, orat_db_url: str, config, start: dt.date, end: dt.date) -> List[TradeOutcome]:
    """Cross-DB: 0DTE intraday chain from IronForge + full-board EOD GEX from ORAT."""
    import psycopg2
    iron = psycopg2.connect(iron_db_url)
    orat = psycopg2.connect(orat_db_url)
    out: List[TradeOutcome] = []
    try:
        cur = iron.cursor()
        cur.execute(
            "SELECT DISTINCT trade_date FROM helios_options_intraday "
            "WHERE expiration_date = trade_date AND trade_date BETWEEN %s AND %s ORDER BY trade_date",
            (start, end),
        )
        dates = [r[0] for r in cur.fetchall()]
        cur.close()
        for d in dates:
            day = load_day(iron, d)
            if day is None:
                continue
            eod = load_eod_gex(orat, d)
            if eod is None:
                continue
            out.extend(replay_daychain_fullboard(day, eod, config))
    finally:
        iron.close()
        orat.close()
    return out


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
