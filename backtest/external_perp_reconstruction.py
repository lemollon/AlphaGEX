#!/usr/bin/env python3
"""External perpetual-market reconstruction backtest.

Purpose
-------
Compare the *structural* effect of the previous aggressive perp defaults with
the hardened defaults using fresh public market data rather than the now-reset
AlphaGEX trade tables.

This is intentionally a reconstruction backtest, not a claim that historical
AlphaGEX combined_signal can be recreated perfectly. Historical price/funding
are public; historical GEX/liquidation-cluster/Prophet state is not complete.

Data:
- Hyperliquid public candleSnapshot (1h)
- Hyperliquid public fundingHistory

Strategies compared:
OLD
- LOW confidence accepted
- RANGE/WAIT funding fallback allowed
- 5% risk budget
- SAR enabled

NEW
- MEDIUM+ confidence
- no RANGE/WAIT fallback entries
- 1% risk budget
- SAR disabled

Both versions use the same reconstructed primary trend signal and identical
market data. P&L is net of entry/exit taker fees, modeled slippage and funding.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

INFO_URL = "https://api.hyperliquid.xyz/info"
MS_HOUR = 60 * 60 * 1000

COINS = {
    "BTC": {"hl": "BTC", "capital": 25000.0, "max_leverage": 10.0, "activation": 1.5, "trail": 1.25, "max_loss": 3.0},
    "ETH": {"hl": "ETH", "capital": 12500.0, "max_leverage": 10.0, "activation": 1.5, "trail": 1.25, "max_loss": 3.0},
    "SOL": {"hl": "SOL", "capital": 5000.0, "max_leverage": 10.0, "activation": 0.7, "trail": 0.6, "max_loss": 3.0},
    "AVAX": {"hl": "AVAX", "capital": 2500.0, "max_leverage": 5.0, "activation": 0.8, "trail": 0.6, "max_loss": 3.0},
    "XRP": {"hl": "XRP", "capital": 9000.0, "max_leverage": 5.0, "activation": 1.0, "trail": 0.75, "max_loss": 3.0},
    "DOGE": {"hl": "DOGE", "capital": 2500.0, "max_leverage": 5.0, "activation": 0.2, "trail": 0.1, "max_loss": 0.75},
    "SHIB": {"hl": "kSHIB", "capital": 1000.0, "max_leverage": 3.0, "activation": 0.15, "trail": 0.05, "max_loss": 0.5},
}

TAKER_FEE_BPS = 6.0
SLIPPAGE_BPS = 2.0
MAX_HOLD_HOURS = 24
SAR_TRIGGER_PCT = 1.5
SAR_MFE_THRESHOLD_PCT = 0.3


@dataclass
class Bar:
    ts: int
    o: float
    h: float
    l: float
    c: float
    v: float
    funding: float = 0.0


@dataclass
class Position:
    side: int  # +1 long, -1 short
    entry_idx: int
    entry_price: float
    qty: float
    notional: float
    entry_fee: float
    hwm: float
    lwm: float
    funding_cash: float = 0.0
    trailing_active: bool = False
    trail_stop: Optional[float] = None
    mfe_pct: float = 0.0


@dataclass
class Result:
    coin: str
    strategy: str
    start_equity: float
    end_equity: float
    return_pct: float
    max_drawdown_pct: float
    trades: int
    wins: int
    losses: int
    win_rate_pct: float
    profit_factor: float
    expectancy_usd: float
    avg_trade_pct: float
    avg_hold_hours: float
    fees_usd: float
    funding_usd: float
    gross_pnl_usd: float
    net_pnl_usd: float


def post_json(payload: dict, timeout: int = 20):
    """POST to Hyperliquid with bounded retry/backoff for public API throttling."""
    data = json.dumps(payload).encode("utf-8")
    last_exc = None
    for attempt in range(7):
        req = urllib.request.Request(
            INFO_URL,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "AlphaGEX-backtest/1.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code not in (429, 500, 502, 503, 504):
                raise
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            try:
                delay = float(retry_after) if retry_after else min(30.0, 1.5 * (2 ** attempt))
            except (TypeError, ValueError):
                delay = min(30.0, 1.5 * (2 ** attempt))
            time.sleep(delay)
        except Exception as exc:
            last_exc = exc
            if attempt >= 6:
                raise
            time.sleep(min(20.0, 1.0 * (2 ** attempt)))
    if last_exc:
        raise last_exc
    raise RuntimeError("Hyperliquid request failed without an exception")


def fetch_candles(coin: str, start_ms: int, end_ms: int) -> List[dict]:
    """Fetch a complete hourly candle window using forward pagination.

    Hyperliquid limits each candleSnapshot response, so long windows such as
    365 days must be paged. We advance from the last returned candle and
    de-duplicate by open timestamp.
    """
    rows: Dict[int, dict] = {}
    cursor = start_ms
    while cursor < end_ms:
        batch = post_json({
            "type": "candleSnapshot",
            "req": {"coin": coin, "interval": "1h", "startTime": cursor, "endTime": end_ms},
        })
        if not batch:
            break
        max_ts = cursor
        for row in batch:
            ts = int(row.get("t", row.get("T", 0)) or 0)
            if ts <= 0:
                continue
            rows[ts] = row
            max_ts = max(max_ts, ts)
        next_cursor = max_ts + MS_HOUR
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        if len(batch) < 4900:
            break
        time.sleep(0.15)
    return [rows[k] for k in sorted(rows)]


def fetch_funding(coin: str, start_ms: int, end_ms: int) -> List[dict]:
    """Fetch complete funding history using forward pagination."""
    rows: Dict[int, dict] = {}
    cursor = start_ms
    while cursor < end_ms:
        batch = post_json({
            "type": "fundingHistory",
            "coin": coin,
            "startTime": cursor,
            "endTime": end_ms,
        })
        if not batch:
            break
        max_ts = cursor
        for row in batch:
            ts = int(row.get("time", 0) or 0)
            if ts <= 0:
                continue
            rows[ts] = row
            max_ts = max(max_ts, ts)
        next_cursor = max_ts + 1
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        if len(batch) < 450:
            break
        time.sleep(0.15)
    return [rows[k] for k in sorted(rows)]


def to_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


def load_bars(coin: str, days: int) -> List[Bar]:
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - days * 24 * MS_HOUR
    raw = fetch_candles(coin, start_ms, end_ms)
    fund = fetch_funding(coin, start_ms, end_ms)
    funding_by_hour: Dict[int, float] = {}
    for row in fund:
        ts = int(row.get("time", 0) or 0)
        if ts <= 0:
            continue
        bucket = (ts // MS_HOUR) * MS_HOUR
        funding_by_hour[bucket] = funding_by_hour.get(bucket, 0.0) + to_float(row.get("fundingRate"))

    bars: List[Bar] = []
    for row in raw:
        ts = int(row.get("t", row.get("T", 0)) or 0)
        if ts <= 0:
            continue
        bucket = (ts // MS_HOUR) * MS_HOUR
        bars.append(Bar(
            ts=bucket,
            o=to_float(row.get("o")),
            h=to_float(row.get("h")),
            l=to_float(row.get("l")),
            c=to_float(row.get("c")),
            v=to_float(row.get("v")),
            funding=funding_by_hour.get(bucket, 0.0),
        ))
    bars.sort(key=lambda b: b.ts)
    return [b for b in bars if b.o > 0 and b.h > 0 and b.l > 0 and b.c > 0]


def ema(values: List[float], period: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    if len(values) < period:
        return out
    alpha = 2.0 / (period + 1.0)
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        prev = alpha * values[i] + (1 - alpha) * prev
        out[i] = prev
    return out


def rolling_std(values: List[float], period: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    for i in range(period - 1, len(values)):
        out[i] = statistics.pstdev(values[i - period + 1:i + 1])
    return out


def signal_series(bars: List[Bar]) -> List[Tuple[int, str, float]]:
    """Return (direction, confidence, score) for each bar.

    Reconstructs a robust directional state from public data only:
    20/50 EMA trend + 24h/72h momentum + funding contrarian pressure.
    """
    closes = [b.c for b in bars]
    e20 = ema(closes, 20)
    e50 = ema(closes, 50)
    rets = [0.0]
    for i in range(1, len(closes)):
        rets.append(math.log(closes[i] / closes[i-1]))
    vol24 = rolling_std(rets, 24)

    out = [(0, "LOW", 0.0)] * len(bars)
    for i in range(len(bars)):
        if i < 72 or e20[i] is None or e50[i] is None or not vol24[i]:
            continue
        r24 = closes[i] / closes[i-24] - 1.0
        r72 = closes[i] / closes[i-72] - 1.0
        trend = (e20[i] / e50[i] - 1.0)
        vol = max(vol24[i] * math.sqrt(24), 1e-6)
        funding = bars[i].funding

        score = 0.45 * (trend / vol) + 0.35 * (r24 / vol) + 0.20 * (r72 / max(vol * math.sqrt(3), 1e-6))
        # Funding is used as a mild contrarian pressure, not the primary signal.
        score -= max(-0.5, min(0.5, funding * 2500.0)) * 0.20

        abs_score = abs(score)
        if abs_score >= 0.75:
            conf = "HIGH"
        elif abs_score >= 0.35:
            conf = "MEDIUM"
        else:
            conf = "LOW"

        direction = 1 if score > 0.08 else -1 if score < -0.08 else 0
        out[i] = (direction, conf, score)
    return out


def adverse_fill(mid: float, side: int, opening: bool) -> float:
    slip = SLIPPAGE_BPS / 10000.0
    # Buy orders pay up, sell orders hit down.
    is_buy = (side == 1 and opening) or (side == -1 and not opening)
    return mid * (1.0 + slip if is_buy else 1.0 - slip)


def run_strategy(coin: str, bars: List[Bar], mode: str) -> Result:
    cfg = COINS[coin]
    start_equity = cfg["capital"]
    equity = start_equity
    peak_equity = equity
    max_dd = 0.0
    sigs = signal_series(bars)

    risk_pct = 5.0 if mode == "OLD" else 1.0
    min_conf = "LOW" if mode == "OLD" else "MEDIUM"
    sar_enabled = mode == "OLD"
    allow_fallback = mode == "OLD"

    rank = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
    pos: Optional[Position] = None
    trades: List[dict] = []
    fees_total = 0.0
    funding_total = 0.0
    gross_total = 0.0

    for i, bar in enumerate(bars):
        if pos is not None:
            # Funding convention: positive funding => longs pay, shorts receive.
            funding_cash = -pos.side * pos.notional * bar.funding
            pos.funding_cash += funding_cash

            favourable = ((bar.h / pos.entry_price) - 1.0) * 100.0 if pos.side == 1 else ((pos.entry_price / bar.l) - 1.0) * 100.0
            pos.mfe_pct = max(pos.mfe_pct, favourable)
            pos.hwm = max(pos.hwm, bar.h)
            pos.lwm = min(pos.lwm, bar.l)

            hold = i - pos.entry_idx
            exit_price = None
            reason = None

            # Worst-side excursion within the hourly bar.
            adverse_pct = ((bar.l / pos.entry_price) - 1.0) * 100.0 if pos.side == 1 else ((pos.entry_price / bar.h) - 1.0) * 100.0

            if sar_enabled and adverse_pct <= -SAR_TRIGGER_PCT and pos.mfe_pct < SAR_MFE_THRESHOLD_PCT:
                raw = pos.entry_price * (1.0 - SAR_TRIGGER_PCT/100.0) if pos.side == 1 else pos.entry_price * (1.0 + SAR_TRIGGER_PCT/100.0)
                exit_price = adverse_fill(raw, pos.side, opening=False)
                reason = "SAR"
            elif adverse_pct <= -cfg["max_loss"]:
                raw = pos.entry_price * (1.0 - cfg["max_loss"]/100.0) if pos.side == 1 else pos.entry_price * (1.0 + cfg["max_loss"]/100.0)
                exit_price = adverse_fill(raw, pos.side, opening=False)
                reason = "MAX_LOSS"
            else:
                if not pos.trailing_active and pos.mfe_pct >= cfg["activation"]:
                    pos.trailing_active = True
                    dist = pos.entry_price * cfg["trail"] / 100.0
                    pos.trail_stop = max(pos.entry_price, pos.hwm - dist) if pos.side == 1 else min(pos.entry_price, pos.lwm + dist)

                if pos.trailing_active:
                    dist = pos.entry_price * cfg["trail"] / 100.0
                    candidate = pos.hwm - dist if pos.side == 1 else pos.lwm + dist
                    if pos.side == 1:
                        pos.trail_stop = max(pos.trail_stop or pos.entry_price, candidate, pos.entry_price)
                        if bar.l <= pos.trail_stop:
                            exit_price = adverse_fill(pos.trail_stop, pos.side, opening=False)
                            reason = "TRAIL"
                    else:
                        pos.trail_stop = min(pos.trail_stop or pos.entry_price, candidate, pos.entry_price)
                        if bar.h >= pos.trail_stop:
                            exit_price = adverse_fill(pos.trail_stop, pos.side, opening=False)
                            reason = "TRAIL"

                if exit_price is None and hold >= MAX_HOLD_HOURS:
                    exit_price = adverse_fill(bar.c, pos.side, opening=False)
                    reason = "MAX_HOLD"

            if exit_price is not None:
                gross = (exit_price - pos.entry_price) * pos.qty * pos.side
                exit_fee = abs(exit_price * pos.qty) * TAKER_FEE_BPS / 10000.0
                net = gross - pos.entry_fee - exit_fee + pos.funding_cash
                equity += net
                fees_total += pos.entry_fee + exit_fee
                funding_total += pos.funding_cash
                gross_total += gross
                trades.append({
                    "net": net,
                    "gross": gross,
                    "fees": pos.entry_fee + exit_fee,
                    "funding": pos.funding_cash,
                    "hold": hold,
                    "reason": reason,
                    "equity": equity,
                })
                peak_equity = max(peak_equity, equity)
                if peak_equity > 0:
                    max_dd = max(max_dd, (peak_equity - equity) / peak_equity * 100.0)
                pos = None

        if pos is None and i >= 72:
            direction, conf, score = sigs[i]
            if rank.get(conf, 0) < rank[min_conf]:
                continue

            # OLD strategy manufactures a funding-reversion trade even when the
            # primary reconstructed signal is neutral, mirroring WAIT/RANGE fallbacks.
            if direction == 0 and allow_fallback:
                if bar.funding >= 0.00015:
                    direction = -1
                elif bar.funding <= -0.00015:
                    direction = 1

            if direction == 0:
                continue

            entry = adverse_fill(bar.c, direction, opening=True)
            risk_budget = max(0.0, equity) * risk_pct / 100.0
            stop_fraction = cfg["max_loss"] / 100.0
            desired_notional = risk_budget / max(stop_fraction, 1e-6)
            max_notional = max(0.0, equity) * cfg["max_leverage"]
            notional = min(desired_notional, max_notional)
            if notional <= 0:
                continue
            qty = notional / entry
            fee = notional * TAKER_FEE_BPS / 10000.0
            pos = Position(
                side=direction,
                entry_idx=i,
                entry_price=entry,
                qty=qty,
                notional=notional,
                entry_fee=fee,
                hwm=entry,
                lwm=entry,
            )

    if pos is not None:
        bar = bars[-1]
        exit_price = adverse_fill(bar.c, pos.side, opening=False)
        gross = (exit_price - pos.entry_price) * pos.qty * pos.side
        exit_fee = abs(exit_price * pos.qty) * TAKER_FEE_BPS / 10000.0
        net = gross - pos.entry_fee - exit_fee + pos.funding_cash
        equity += net
        fees_total += pos.entry_fee + exit_fee
        funding_total += pos.funding_cash
        gross_total += gross
        trades.append({"net": net, "gross": gross, "fees": pos.entry_fee + exit_fee, "funding": pos.funding_cash, "hold": len(bars)-1-pos.entry_idx, "reason": "END", "equity": equity})

    wins = [t for t in trades if t["net"] > 0]
    losses = [t for t in trades if t["net"] <= 0]
    gross_wins = sum(t["net"] for t in wins)
    gross_losses = abs(sum(t["net"] for t in losses))
    pf = gross_wins / gross_losses if gross_losses > 0 else (999.0 if gross_wins > 0 else 0.0)
    net_pnl = equity - start_equity
    avg_hold = sum(t["hold"] for t in trades) / len(trades) if trades else 0.0
    avg_trade_pct = (net_pnl / start_equity * 100.0 / len(trades)) if trades else 0.0

    return Result(
        coin=coin,
        strategy=mode,
        start_equity=round(start_equity, 2),
        end_equity=round(equity, 2),
        return_pct=round((equity / start_equity - 1.0) * 100.0, 2),
        max_drawdown_pct=round(max_dd, 2),
        trades=len(trades),
        wins=len(wins),
        losses=len(losses),
        win_rate_pct=round((len(wins) / len(trades) * 100.0) if trades else 0.0, 2),
        profit_factor=round(pf, 3),
        expectancy_usd=round(net_pnl / len(trades), 2) if trades else 0.0,
        avg_trade_pct=round(avg_trade_pct, 4),
        avg_hold_hours=round(avg_hold, 2),
        fees_usd=round(fees_total, 2),
        funding_usd=round(funding_total, 2),
        gross_pnl_usd=round(gross_total, 2),
        net_pnl_usd=round(net_pnl, 2),
    )


def write_outputs(results: List[Result], out_dir: Path, days: int):
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = [asdict(r) for r in results]

    with (out_dir / "summary.json").open("w") as f:
        json.dump({"days": days, "generated_at": datetime.now(timezone.utc).isoformat(), "results": rows}, f, indent=2)

    with (out_dir / "summary.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    by_coin = {}
    for r in results:
        by_coin.setdefault(r.coin, {})[r.strategy] = r

    lines = [
        "# AlphaGEX External Perpetual Reconstruction Backtest",
        "",
        f"Window: {days} days, 1-hour Hyperliquid candles + historical funding.",
        "",
        "> This is a public-data reconstruction test of the structural OLD vs NEW defaults. "
        "It does not reproduce unavailable historical GEX/liquidation/Prophet state exactly.",
        "",
        "| Coin | Old Return | New Return | Old PF | New PF | Old DD | New DD | Old Trades | New Trades |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for coin in COINS:
        old = by_coin.get(coin, {}).get("OLD")
        new = by_coin.get(coin, {}).get("NEW")
        if not old or not new:
            continue
        lines.append(
            f"| {coin} | {old.return_pct:.2f}% | {new.return_pct:.2f}% | "
            f"{old.profit_factor:.2f} | {new.profit_factor:.2f} | "
            f"{old.max_drawdown_pct:.2f}% | {new.max_drawdown_pct:.2f}% | "
            f"{old.trades} | {new.trades} |"
        )

    old_total = sum(r.net_pnl_usd for r in results if r.strategy == "OLD")
    new_total = sum(r.net_pnl_usd for r in results if r.strategy == "NEW")
    lines += [
        "",
        f"Aggregate net P&L — OLD: ${old_total:,.2f}; NEW: ${new_total:,.2f}.",
        "",
        "Selection rule for further testing: prefer configurations with positive expectancy and PF > 1 "
        "across multiple coins/windows, not merely the highest absolute P&L.",
    ]
    (out_dir / "report.md").write_text("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--out", default="artifacts/perp_external_backtest")
    ap.add_argument("--coins", default=",".join(COINS.keys()))
    args = ap.parse_args()

    wanted = [x.strip().upper() for x in args.coins.split(",") if x.strip()]
    results: List[Result] = []

    for coin in wanted:
        if coin not in COINS:
            print(f"SKIP unknown coin {coin}")
            continue
        hl = COINS[coin]["hl"]
        print(f"Fetching {coin} ({hl}) {args.days}d...")
        try:
            bars = load_bars(hl, args.days)
        except Exception as exc:
            print(f"ERROR {coin}: {type(exc).__name__}: {exc}")
            continue
        print(f"  bars={len(bars)}")
        if len(bars) < 200:
            print(f"  insufficient history; skip")
            continue
        for mode in ("OLD", "NEW"):
            r = run_strategy(coin, bars, mode)
            results.append(r)
            print(
                f"  {mode}: return={r.return_pct:+.2f}% PF={r.profit_factor:.2f} "
                f"DD={r.max_drawdown_pct:.2f}% trades={r.trades} net=${r.net_pnl_usd:+.2f}"
            )

    if not results:
        raise SystemExit("No backtest results produced")

    write_outputs(results, Path(args.out), args.days)


if __name__ == "__main__":
    main()
