"""TSUNAMI-TREND — LETF trend engine (replaces the untradable options spec).

Backtested 2026-07-03 (dev/ironforge-data/tools/tsunami_bt/): the original
3-leg LETF options structure could never fill (zero-bid wall-mapped puts,
tracking band narrower than the strike grid), and the gamma-wall stock
signal was beta (excess t=0.51). What survived train/holdout discipline:

    Hold a 2x LETF while it closes above its own 50-day MA;
    weight = SLICE * min(2, 0.35 / 20d realized vol); fractional shares
    since 2026-07-09 (see SLICE comment -- slice recalibrated 0.40->0.30);
    rebalance only when target drifts >REBAL_BAND from held; MA break -> cash.

$500 start, slice 0.40: CAGR 29.4%, Sharpe 1.15, MaxDD -25.7%, every year
positive (2022-08..2026-07, real LETF closes, decay priced in).

2026-07-07 universe-expansion post-mortem (dev/ironforge-data/tools/
tsunami_bt/run_live17_bt.py + run_live17_fix_bt.py): adding SPXL/SPXS/
TQQQ/SQQQ/UVXY at full SLICE roughly DOUBLED MaxDD and collapsed Sharpe
1.20->0.43 (walk-forward 2024-01..2026-07) despite TQQQ/SPXL each being
individually profitable. Root cause: SPXL/TQQQ are index-level 3x LETFs
highly correlated with the existing mega-cap-growth longs (TSLL/AMDL/
NVDL/MSTU/CONL) -- sizing targets each name's OWN vol independently with
no portfolio-level correlation awareness, so a market-wide trend stacks
correlated beta with zero diversification credit. UVXY is a standalone
loser in every window tested (contango-decay/mean-reversion product,
wrong fit for a lagging trend-follow rule) -- dropped entirely. Fix:
SLICE_OVERRIDE halves the index sleeve (SPXL/TQQQ/SPXS/SQQQ) to 0.15 --
calibrated by sweep, restores Sharpe/Calmar to OLD12 parity in both the
walk-forward and recent (2025-01..2026-07) windows. A portfolio-level
realized-vol overlay was also tested and found NET NEGATIVE alone (too
laggy -- dials down after the drawdown, then underweights the recovery);
do not add one without re-testing on top of the calibrated slice.

Paper-only. Daily rebalance near the close (scheduler: Mon-Fri 14:45 CT).
Data: yfinance split-adjusted daily history + Tradier live quote (2026-07-09:
Tradier's daily history is NOT split-adjusted -- NVDL's reverse split made
the live price read 2x its "MA50" with 384% "vol", a phantom trending
signal; only the whole-share rounding kept it from being bought. Crushed
LETFs reverse-split routinely, so history MUST be adjusted). State:
tsunami_trend_book /
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
    # UXRP added 2026-07-04 per Leron despite thin history (listed 2025-07,
    # -$16 in its short walk-forward sample, no inverse exists). The MA50
    # gate is the safety net: it can't be bought unless it's trending.
    ("XRP", "UXRP"),
    # 2x quantum LETFs, added 2026-07-10 per Leron thesis ("quantum stocks
    # are going to do well"). Backtest (run_quantum_add_bt.py): 0.82-0.95
    # pairwise correlation with each other and 0.76-0.91 with IONX -- five
    # tickers, ONE bet -- and every add-variant trailed the no-add baseline
    # in the common window (quantum chop since late 2025). Added anyway as
    # a THESIS position, UXRP-precedent: the MA50 gate keeps them in cash
    # until the thesis actually shows up in price, and the quantum sleeve
    # override (0.15, IONX folded in) caps the one-bet stacking. QPUX is a
    # basket of the same underlyings (corr 0.91+ with each single name).
    ("QUANTUM", "QPUX"),
    ("RGTI", "RGTU"),
    ("QUBT", "QUBX"),
    ("QBTS", "QBTX"),
    # SPX / Nasdaq-100 index 3x LETFs, added 2026-07-07. Correlated with
    # the existing single-name longs -- see SLICE_OVERRIDE below. UVXY
    # (VIX long-vol) was tested and dropped: standalone loser in every
    # backtest window, wrong instrument for a trend-following rule.
    ("SPX", "SPXL"),
    ("NDX", "TQQQ"),
    # inverse crypto complex — the short side. An inverse ETF above its own
    # 50d MA IS the confirmed downtrend trade; its price already carries the
    # decay. Equity single-name inverses (TSLQ/NVD/CONI/AMDS) were backtested
    # and REJECTED: bear rallies chop them up (NVD alone -$227 on $500).
    ("BTC-", "SBIT"),
    ("ETH-", "ETHD"),
    ("MSTR-", "SMST"),
    ("SPX-", "SPXS"),
    ("NDX-", "SQQQ"),
]
START_CASH = 500.0
# 2026-07-09 fractional-share switch (Leron): whole shares on a $500 book
# could not express 6 of 7 trending signals (SPXL $275/sh vs a ~$60 target
# -- "position size rounds to 0 shares"). Fractional shares fix that, but
# at the old SLICE=0.40 they over-deploy (~70% avg gross vs ~51%) and cost
# ~0.4 Sharpe. Slice sweep {0.40,0.30,0.25,0.20,0.15} on walk-forward/
# recent/full windows: 0.30 is the calibrated match (Sharpe 1.23/1.47/1.27
# vs whole-share's 1.43/1.67/1.44, similar MaxDD) while expressing every
# signal. Index sleeve keeps the same 0.375 ratio (0.30*0.375=0.1125).
SLICE = 0.30
# Index-sleeve names are correlated substitutes for beta already held via
# the single-name longs -- full SLICE double-counts that exposure with no
# diversification credit (see 2026-07-07 post-mortem above). 0.15 was
# picked by sweep over {0.10, 0.15, 0.20, 0.25, 0.30, 0.40} on the
# walk-forward + recent windows; 0.15 matched or beat OLD12's Sharpe/
# Calmar in both.
SLICE_OVERRIDE = {
    "SPXL": 0.1125, "TQQQ": 0.1125, "SPXS": 0.1125, "SQQQ": 0.1125,
    # quantum sleeve 2026-07-10: IONX/QPUX/RGTU/QUBX/QBTX are one highly
    # correlated bet (see PAIRS comment); 0.15 was the best add-variant in
    # the since-2025-10 window (Sharpe 0.82 vs 0.28 at full slice). IONX
    # moves from full slice into the sleeve for the same reason SPXL/TQQQ
    # were discounted: correlated substitutes get no diversification credit.
    "IONX": 0.15, "QPUX": 0.15, "RGTU": 0.15, "QUBX": 0.15, "QBTX": 0.15,
}
VOL_TGT = 0.35
W_CAP = 2.0
MA_N = 50
RV_N = 20
# 2026-07-07 "max responsible aggression" sweep (run_live17_fix_bt.py):
# raising SLICE (0.40->1.20) or W_CAP (2.0->4.0) both made every metric
# WORSE monotonically -- bigger positions amplify whipsaw and hit the cash
# gate more often, they don't capture more edge. The one lever that WAS a
# genuine improvement (better Sharpe/Calmar/MaxDD, not a risk-for-return
# trade) was widening REBAL_BAND: swept 0.10-0.50, 0.35 was best-or-near-
# best on both the walk-forward and recent windows (walk-forward Sharpe
# 1.20->1.20/Calmar 1.61->1.64; recent Sharpe 1.13->1.30/Calmar 1.95->2.51)
# by cutting whipsaw-driven rebalance churn, not by taking more risk.
REBAL_BAND = 0.35
SLIP = 0.0002  # paper-fill slippage per side
MIN_ORDER_NOTIONAL = 1.0  # skip dust orders below $1 (broker fractional minimum)

_DDL = """
CREATE TABLE IF NOT EXISTS tsunami_trend_book (
    letf        VARCHAR(10) PRIMARY KEY,
    shares      NUMERIC(16,6) NOT NULL DEFAULT 0,
    avg_cost    DECIMAL(12,4) NOT NULL DEFAULT 0,
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS tsunami_trend_trades (
    id          BIGSERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    letf        VARCHAR(10) NOT NULL,
    side        VARCHAR(4)  NOT NULL CHECK (side IN ('BUY','SELL')),
    shares      NUMERIC(16,6) NOT NULL,
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
-- One row per instrument per rebalance cycle -- the "why" behind every
-- buy/sell/skip. Without this, only currently-held names + trade fills
-- were ever visible; there was no way to see the other instruments in
-- the universe or why they weren't bought (not trending, no data, etc).
CREATE TABLE IF NOT EXISTS tsunami_trend_signals (
    id            BIGSERIAL PRIMARY KEY,
    ts            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    letf          VARCHAR(10) NOT NULL,
    price         DECIMAL(12,4),
    ma50          DECIMAL(12,4),
    rv20          DECIMAL(8,4),
    trending      BOOLEAN,
    target_weight DECIMAL(8,4),
    target_shares NUMERIC(16,6),
    held_shares   NUMERIC(16,6),
    action        VARCHAR(12) NOT NULL,
    reason        TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_tsunami_trend_signals_letf_ts
    ON tsunami_trend_signals (letf, ts DESC);
CREATE INDEX IF NOT EXISTS idx_tsunami_trend_signals_ts
    ON tsunami_trend_signals (ts DESC);
-- 2026-07-09 fractional-share migration: widen INTEGER share columns on
-- pre-existing installs. int -> numeric is a safe widening cast; re-running
-- is a no-op type-wise (PostgreSQL just rewrites the small paper tables).
ALTER TABLE tsunami_trend_book    ALTER COLUMN shares        TYPE NUMERIC(16,6);
ALTER TABLE tsunami_trend_trades  ALTER COLUMN shares        TYPE NUMERIC(16,6);
ALTER TABLE tsunami_trend_signals ALTER COLUMN target_shares TYPE NUMERIC(16,6);
ALTER TABLE tsunami_trend_signals ALTER COLUMN held_shares   TYPE NUMERIC(16,6);
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


def _diag(price=None, ma50=None, rv20=None, trending=None) -> dict:
    return {"price": price, "ma50": ma50, "rv20": rv20, "trending": trending}


def _today_market_date():
    """Today's date on the exchange clock (America/New_York) — yfinance bar
    timestamps are exchange-tz, so the partial-bar cutoff must use the same
    calendar or evening runs (past midnight UTC) stop excluding today."""
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("America/New_York")).date()


def _adjusted_closes(letf: str) -> list[float]:
    """Split/dividend-adjusted daily closes from yfinance, oldest first,
    excluding any partial bar for today (the caller appends the live
    Tradier quote as today's price). Tradier's daily history is raw --
    unadjusted for splits -- so an MA/vol computed across a reverse split
    is garbage (NVDL 2026-07: price read 2x its "MA50" => phantom trend
    signal). Returns [] on any failure; the caller fail-safes to
    no-signal and leaves the book untouched."""
    try:
        import yfinance as yf  # type: ignore
    except ImportError as exc:
        logger.warning("[tsunami.trend] yfinance unavailable: %r", exc)
        return []
    try:
        hist = yf.Ticker(letf).history(period="1y", auto_adjust=True, actions=False)
        if hist is None or hist.empty:
            return []
        today = _today_market_date()
        return [float(c) for d, c in zip(hist.index, hist["Close"])
                if d.date() < today and c and c > 0]
    except Exception as exc:  # noqa: BLE001
        logger.warning("[tsunami.trend] yfinance history %s failed: %r", letf, exc)
        return []


def _signal_weight(letf: str) -> tuple[Optional[float], dict]:
    """Target weight for one LETF from its own daily closes + live quote.

    Returns (weight, diag). weight=None means data unavailable (leave the
    book untouched -- fail safe); weight=0.0 means trend is off (flat/
    exit). diag carries whatever was computed before any early return --
    price/ma50/rv20/trending -- so callers can log a "why" even on a skip,
    not just on a fill. Any field diag doesn't reach yet is None."""
    closes = _adjusted_closes(letf)
    if len(closes) < MA_N + 1:
        logger.warning("[tsunami.trend] %s: only %d bars — no signal", letf, len(closes))
        return None, _diag()
    quote = tradier_client.get_quote(letf)
    last = float((quote or {}).get("last") or (quote or {}).get("close") or 0)
    if last <= 0:
        return None, _diag()
    series = closes[-(MA_N + RV_N):] + [last]
    # Unadjusted-split tripwire. SMST's 2024-11 reverse split is missing
    # even from Yahoo's record (+272% phantom day), so no single data
    # source is trusted blindly -- an outsized jump means the history
    # and/or quote straddle an unadjusted split. Fail safe. Threshold is
    # 150%, not 100%: QBTX legitimately printed +104% on 2025-05-08 (QBTS
    # +51.2% x2, verified vs the underlying), so quantum 2x LETFs can
    # exceed +100% for real. 1.5 still catches the common crushed-LETF
    # reverse splits (1:4 and up = +300%+); exactly-1:2 splits rely on the
    # yfinance adjustment (the primary defense, which caught NVDL).
    for i in range(1, len(series)):
        if series[i - 1] > 0 and abs(series[i] / series[i - 1] - 1) > 1.5:
            logger.warning("[tsunami.trend] %s: >100%% bar-to-bar jump in signal "
                           "window (%.2f -> %.2f) — suspected unadjusted split, no signal",
                           letf, series[i - 1], series[i])
            return None, _diag()
    ma = sum(series[-MA_N:]) / MA_N
    if last <= ma:
        return 0.0, _diag(price=last, ma50=ma, trending=False)
    rets = [math.log(series[i] / series[i - 1]) for i in range(1, len(series))][-RV_N:]
    if len(rets) < RV_N:
        return None, _diag(price=last, ma50=ma, trending=True)
    mean = sum(rets) / len(rets)
    rv = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)) * math.sqrt(252)
    if rv <= 0:
        return None, _diag(price=last, ma50=ma, trending=True)
    slice_ = SLICE_OVERRIDE.get(letf, SLICE)
    weight = slice_ * min(W_CAP, VOL_TGT / rv)
    return weight, _diag(price=last, ma50=ma, rv20=rv, trending=True)


def _log_signal(letf, diag, target_weight, target_shares, held_shares, action, reason) -> None:
    """Independent connection + transaction -- a signals-log write failure
    must never abort or poison run_rebalance's trading transaction. Called
    once per instrument per cycle regardless of outcome (fill/hold/skip)
    so the full universe -- not just currently-held names -- has a record
    of why each name was or wasn't traded."""
    try:
        conn = get_connection()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[tsunami.trend] signal log connect failed for %s: %r", letf, exc)
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO tsunami_trend_signals"
                " (letf, price, ma50, rv20, trending, target_weight, target_shares, held_shares, action, reason)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (letf, diag.get("price"), diag.get("ma50"), diag.get("rv20"), diag.get("trending"),
                 target_weight, target_shares, held_shares, action, reason))
        conn.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[tsunami.trend] signal log insert failed for %s: %r", letf, exc)
        conn.rollback()
    finally:
        conn.close()


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
            book = {r[0]: {"shares": float(r[1]), "avg_cost": float(r[2])} for r in cur.fetchall()}

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
                _log_signal(letf, _diag(), None, 0, held,
                            "NO_QUOTE", "no live quote from Tradier")
                continue
            w, diag = _signal_weight(letf)
            if w is None:
                summary["skipped"].append(f"{letf}:no_signal")
                if diag["price"] is None:
                    reason = "insufficient price history or no live quote"
                elif diag["rv20"] is None:
                    reason = "insufficient volatility history (recently listed)"
                else:
                    reason = "no signal"
                _log_signal(letf, diag, None, 0, held, "NO_SIGNAL", reason)
                continue
            target = round((w * equity) / px, 4)
            if target * px < MIN_ORDER_NOTIONAL:
                target = 0.0
            fill = None
            if held == 0 and target > 0:
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
                summary["fills"].append(f"{letf} {side} {n:g}@{fpx:.2f}")
                _log_signal(letf, diag, w, target, held, side, reason)
                try:
                    tsunami_discord.post_embed(
                        title=f"🌊 TSUNAMI-TREND paper {side}",
                        description=(f"{side} {n:g} {letf} @ ${fpx:.2f} — {reason}"
                                     + (f" (realized ${pnl:+.2f})" if pnl is not None else "")),
                    )
                except Exception:  # noqa: BLE001
                    pass
            else:
                if held == 0 and target == 0:
                    action, reason = "FLAT", ("not trending" if w == 0.0 else "target below $1 minimum order")
                elif held > 0 and target == held:
                    action, reason = "HOLD", "at target size"
                else:
                    drift = abs(target - held) / held if held else 1.0
                    if drift <= REBAL_BAND:
                        action, reason = "HOLD", f"drift {drift:.0%} within {REBAL_BAND:.0%} band"
                    else:
                        action, reason = "HOLD", "rebalance triggered but insufficient cash"
                _log_signal(letf, diag, w, target, held, action, reason)

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


def mark_intraday_equity() -> Optional[float]:
    """Mark-to-market snapshot with NO trading -- feeds intraday chart
    granularity between daily rebalances. run_rebalance() (14:45 CT) is
    still the only path that buys/sells; this only reads the current book
    and cash, re-prices held shares off live quotes, and writes one more
    tsunami_equity_snapshots row. Returns the marked equity, or None if
    the DB is unavailable or the mark failed."""
    if not is_database_available():
        return None

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT cash FROM tsunami_trend_cash WHERE id=1")
            row = cur.fetchone()
            cash = float(row[0]) if row else START_CASH
            cur.execute("SELECT letf, shares FROM tsunami_trend_book WHERE shares > 0")
            held = cur.fetchall()

        equity = cash
        for letf, shares in held:
            q = tradier_client.get_quote(letf)
            px = float((q or {}).get("last") or (q or {}).get("close") or 0)
            if px > 0:
                equity += float(shares) * px

        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO tsunami_equity_snapshots"
                " (scope, instance_name, starting_capital, cumulative_realized_pnl,"
                "  unrealized_pnl, open_position_count, equity)"
                " VALUES ('PLATFORM', NULL, %s, %s, %s, %s, %s)",
                (START_CASH, equity - START_CASH, 0, len(held), equity))
        conn.commit()
        return equity
    except Exception as exc:  # noqa: BLE001
        logger.exception("[tsunami.trend] intraday mark failed: %r", exc)
        conn.rollback()
        return None
    finally:
        conn.close()
