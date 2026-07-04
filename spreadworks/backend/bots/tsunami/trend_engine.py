"""TSUNAMI-TREND — LETF trend engine (replaces the untradable options spec).

Backtested 2026-07-03 (dev/ironforge-data/tools/tsunami_bt/): the original
3-leg LETF options structure could never fill (zero-bid wall-mapped puts,
tracking band narrower than the strike grid), and the gamma-wall stock
signal was beta (excess t=0.51). What survived train/holdout discipline:

    Hold a 2x LETF while it closes above its own 50-day MA;
    weight = SLICE * min(2, 0.35 / 20d realized vol); whole shares;
    rebalance only when target drifts >25% from held; MA break -> cash.

$500 start, slice 0.40: CAGR 29.4%, Sharpe 1.15, MaxDD -25.7%, every year
positive (2022-08..2026-07, real LETF closes, decay priced in).

Paper-only. Daily rebalance near the close (scheduler: Mon-Fri 14:45 CT).
Data: Tradier daily history + live quote. State: tsunami_trend_book /
tsunami_trend_trades / tsunami_trend_cash; equity into
tsunami_equity_snapshots (scope PLATFORM). Discord on every fill.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Optional

from backend.bots.tsunami.data import tradier_client
from backend.bots.tsunami.db_compat import get_connection, is_database_available
from backend.bots.tsunami.monitoring import discord as tsunami_discord

logger = logging.getLogger(__name__)

PAIRS = [  # (reference asset, instrument) — signal and execution on the instrument
    # long 2x equity LETFs
    ("TSLA", "TSLL"),
    ("AMD", "AMDL"),
    ("NVDA", "NVDL"),
    ("COIN", "CONL"),
    ("MSTR", "MSTU"),
    # long 2x crypto complex (universe expansion, backtested 2026-07-04)
    ("BTC", "BITX"),
    ("ETH", "ETHU"),
    ("IONQ", "IONX"),
    # inverse crypto complex — the short side. An inverse ETF above its own
    # 50d MA IS the confirmed downtrend trade; its price already carries the
    # decay. Equity single-name inverses (TSLQ/NVD/CONI/AMDS) were backtested
    # and REJECTED: bear rallies chop them up (NVD alone -$227 on $500).
    ("BTC-", "SBIT"),
    ("ETH-", "ETHD"),
    ("MSTR-", "SMST"),
]
START_CASH = 500.0
SLICE = 0.40
VOL_TGT = 0.35
W_CAP = 2.0
MA_N = 50
RV_N = 20
REBAL_BAND = 0.25
SLIP = 0.0002  # paper-fill slippage per side

_DDL = """
CREATE TABLE IF NOT EXISTS tsunami_trend_book (
    letf        VARCHAR(10) PRIMARY KEY,
    shares      INTEGER      NOT NULL DEFAULT 0,
    avg_cost    DECIMAL(12,4) NOT NULL DEFAULT 0,
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS tsunami_trend_trades (
    id          BIGSERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    letf        VARCHAR(10) NOT NULL,
    side        VARCHAR(4)  NOT NULL CHECK (side IN ('BUY','SELL')),
    shares      INTEGER     NOT NULL,
    price       DECIMAL(12,4) NOT NULL,
    reason      TEXT        NOT NULL DEFAULT '',
    realized_pnl DECIMAL(12,4)
);
CREATE TABLE IF NOT EXISTS tsunami_trend_cash (
    id      INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    cash    DECIMAL(12,4) NOT NULL
);
INSERT INTO tsunami_trend_cash (id, cash)
    VALUES (1, %s) ON CONFLICT (id) DO NOTHING;
"""


def ensure_trend_tables() -> bool:
    if not is_database_available():
        return False
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(_DDL, (START_CASH,))
        conn.commit()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.exception("[tsunami.trend] ensure tables failed: %r", exc)
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()


def _signal_weight(letf: str) -> Optional[float]:
    """Target weight for one LETF from its own daily closes + live quote.

    None = data unavailable (leave the book untouched — fail safe)."""
    hist = tradier_client.get_daily_history(letf, days=130)
    if len(hist) < MA_N + 1:
        logger.warning("[tsunami.trend] %s: only %d bars — no signal", letf, len(hist))
        return None
    closes = [float(h["close"]) for h in hist if h.get("close")]
    quote = tradier_client.get_quote(letf)
    last = float((quote or {}).get("last") or (quote or {}).get("close") or 0)
    if last <= 0:
        return None
    series = closes[-(MA_N + RV_N):] + [last]
    ma = sum(series[-MA_N:]) / MA_N
    if last <= ma:
        return 0.0
    rets = [math.log(series[i] / series[i - 1]) for i in range(1, len(series))][-RV_N:]
    if len(rets) < RV_N:
        return None
    mean = sum(rets) / len(rets)
    rv = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)) * math.sqrt(252)
    if rv <= 0:
        return None
    return SLICE * min(W_CAP, VOL_TGT / rv)


def run_rebalance(now: Optional[datetime] = None) -> dict:
    """One daily rebalance cycle. Returns a summary dict for logging."""
    now = now or datetime.now(timezone.utc)
    summary = {"fills": [], "skipped": [], "equity": None}
    if not is_database_available():
        logger.warning("[tsunami.trend] DB unavailable — cycle skipped")
        return summary

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT cash FROM tsunami_trend_cash WHERE id=1")
            row = cur.fetchone()
            cash = float(row[0]) if row else START_CASH
            cur.execute("SELECT letf, shares, avg_cost FROM tsunami_trend_book")
            book = {r[0]: {"shares": int(r[1]), "avg_cost": float(r[2])} for r in cur.fetchall()}

        quotes: dict[str, float] = {}
        equity = cash
        for _, letf in PAIRS:
            q = tradier_client.get_quote(letf)
            px = float((q or {}).get("last") or (q or {}).get("close") or 0)
            quotes[letf] = px
            held = book.get(letf, {}).get("shares", 0)
            if held and px > 0:
                equity += held * px

        for _, letf in PAIRS:
            px = quotes.get(letf, 0.0)
            held = book.get(letf, {}).get("shares", 0)
            if px <= 0:
                summary["skipped"].append(f"{letf}:no_quote")
                continue
            w = _signal_weight(letf)
            if w is None:
                summary["skipped"].append(f"{letf}:no_signal")
                continue
            target = int((w * equity) // px)
            fill = None
            if held == 0 and target >= 1:
                cost = target * px * (1 + SLIP)
                if cost <= cash:
                    cash -= cost
                    fill = ("BUY", target, px, f"trend on, w={w:.2f}")
                    book[letf] = {"shares": target, "avg_cost": px * (1 + SLIP)}
            elif held > 0 and target == 0:
                proceeds = held * px * (1 - SLIP)
                cash += proceeds
                pnl = proceeds - held * book[letf]["avg_cost"]
                fill = ("SELL", held, px, "MA50 break -> cash", pnl)
                book[letf] = {"shares": 0, "avg_cost": 0.0}
            elif held > 0 and abs(target - held) / held > REBAL_BAND:
                diff = target - held
                if diff > 0 and diff * px * (1 + SLIP) <= cash:
                    cash -= diff * px * (1 + SLIP)
                    ac = book[letf]["avg_cost"]
                    book[letf] = {"shares": target,
                                  "avg_cost": (held * ac + diff * px * (1 + SLIP)) / target}
                    fill = ("BUY", diff, px, "vol rebalance up")
                elif diff < 0:
                    cash += (-diff) * px * (1 - SLIP)
                    pnl = (-diff) * (px * (1 - SLIP) - book[letf]["avg_cost"])
                    book[letf]["shares"] = target
                    fill = ("SELL", -diff, px, "vol rebalance down", pnl)

            if fill:
                side, n, fpx, reason = fill[0], fill[1], fill[2], fill[3]
                pnl = fill[4] if len(fill) > 4 else None
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO tsunami_trend_trades (letf, side, shares, price, reason, realized_pnl)"
                        " VALUES (%s,%s,%s,%s,%s,%s)",
                        (letf, side, n, fpx, reason, pnl))
                    cur.execute(
                        "INSERT INTO tsunami_trend_book (letf, shares, avg_cost, updated_at)"
                        " VALUES (%s,%s,%s,NOW())"
                        " ON CONFLICT (letf) DO UPDATE SET shares=EXCLUDED.shares,"
                        " avg_cost=EXCLUDED.avg_cost, updated_at=NOW()",
                        (letf, book[letf]["shares"], book[letf]["avg_cost"]))
                summary["fills"].append(f"{letf} {side} {n}@{fpx:.2f}")
                try:
                    tsunami_discord.post_embed(
                        title=f"🌊 TSUNAMI-TREND paper {side}",
                        description=(f"{side} {n} {letf} @ ${fpx:.2f} — {reason}"
                                     + (f" (realized ${pnl:+.2f})" if pnl is not None else "")),
                    )
                except Exception:  # noqa: BLE001
                    pass

        equity = cash + sum(b["shares"] * quotes.get(l, 0.0) for l, b in book.items())
        with conn.cursor() as cur:
            cur.execute("UPDATE tsunami_trend_cash SET cash=%s WHERE id=1", (cash,))
            cur.execute(
                "INSERT INTO tsunami_equity_snapshots"
                " (scope, instance_name, starting_capital, cumulative_realized_pnl,"
                "  unrealized_pnl, open_position_count, equity)"
                " VALUES ('PLATFORM', NULL, %s, %s, %s, %s, %s)",
                (START_CASH, equity - START_CASH, 0,
                 sum(1 for b in book.values() if b["shares"] > 0), equity))
        conn.commit()
        summary["equity"] = equity
        logger.info("[tsunami.trend] rebalance done: equity=$%.2f fills=%s skipped=%s",
                    equity, summary["fills"], summary["skipped"])
        return summary
    except Exception as exc:  # noqa: BLE001
        logger.exception("[tsunami.trend] rebalance failed: %r", exc)
        conn.rollback()
        return summary
    finally:
        conn.close()
