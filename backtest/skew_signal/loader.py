"""Load full chain (all strikes) at a target minute, with OI from helios_options_oi."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Dict, Optional

import psycopg2


@dataclass(frozen=True)
class ChainBar:
    strike: float
    call_bid: float
    call_ask: float
    put_bid: float
    put_ask: float
    call_oi: int = 0
    put_oi: int = 0

    @property
    def call_mid(self) -> float:
        return 0.5 * (self.call_bid + self.call_ask)

    @property
    def put_mid(self) -> float:
        return 0.5 * (self.put_bid + self.put_ask)

    def call_valid(self) -> bool:
        return self.call_bid > 0 and self.call_ask > 0 and self.call_ask >= self.call_bid

    def put_valid(self) -> bool:
        return self.put_bid > 0 and self.put_ask > 0 and self.put_ask >= self.put_bid


def load_chain_at_minute(
    db_url: str,
    trade_date: dt.date,
    expiration_date: dt.date,
    target_minute: int,
) -> Optional[Dict[float, ChainBar]]:
    """Pull the full chain at minute M plus OI. Returns {strike: ChainBar} or None."""
    chain_sql = """
        WITH first_bar AS (
            SELECT MIN(bar_time) AS t0
            FROM helios_options_intraday
            WHERE trade_date = %s AND expiration_date = %s
        )
        SELECT b.strike, b."right", b.bid, b.ask
        FROM helios_options_intraday b, first_bar
        WHERE b.trade_date = %s AND b.expiration_date = %s
          AND b.bar_time = first_bar.t0 + (%s * INTERVAL '1 minute')
        ORDER BY b.strike, b."right"
    """
    oi_sql = """
        SELECT strike, "right", open_interest
        FROM helios_options_oi
        WHERE trade_date = %s AND expiration_date = %s
    """
    conn = psycopg2.connect(db_url)
    try:
        cur = conn.cursor()
        cur.execute(chain_sql, (trade_date, expiration_date,
                                trade_date, expiration_date, target_minute))
        rows = cur.fetchall()
        if not rows:
            return None
        cur.execute(oi_sql, (trade_date, expiration_date))
        oi_rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()

    by_strike: Dict[float, dict] = {}
    for strike, right, bid, ask in rows:
        k = float(strike)
        e = by_strike.setdefault(k, {
            "call_bid": 0.0, "call_ask": 0.0,
            "put_bid": 0.0, "put_ask": 0.0,
        })
        bid_v = float(bid) if bid is not None else 0.0
        ask_v = float(ask) if ask is not None else 0.0
        if right == "C":
            e["call_bid"] = bid_v; e["call_ask"] = ask_v
        else:
            e["put_bid"] = bid_v; e["put_ask"] = ask_v

    oi_by_strike: Dict[float, dict] = {}
    for strike, right, oi in oi_rows:
        k = float(strike)
        e = oi_by_strike.setdefault(k, {"call_oi": 0, "put_oi": 0})
        if right == "C":
            e["call_oi"] = int(oi)
        else:
            e["put_oi"] = int(oi)

    out: Dict[float, ChainBar] = {}
    for k, q in by_strike.items():
        oi = oi_by_strike.get(k, {"call_oi": 0, "put_oi": 0})
        out[k] = ChainBar(
            strike=k,
            call_bid=q["call_bid"], call_ask=q["call_ask"],
            put_bid=q["put_bid"], put_ask=q["put_ask"],
            call_oi=oi["call_oi"], put_oi=oi["put_oi"],
        )
    return out
