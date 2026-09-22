#!/usr/bin/env python3
"""Backtest the AlphaGEX/Trade Volatility long-only stock strategy against TTP-style rules.

Sources:
- Stored AlphaGEX morning setups/watchlists from Render Postgres.
- Historical 1-minute stock bars from Polygon.

This intentionally does NOT recreate missing historical Trading Volatility
/top-setups rankings. It only evaluates dates/symbols that AlphaGEX actually
stored, preventing look-ahead or invented vendor history.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
from sqlalchemy import create_engine, text

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


@dataclass(frozen=True)
class Program:
    name: str
    profit_target_pct: float
    max_loss_pct: float
    daily_pause_pct: float
    min_positions: int
    consistency_pct: float
    calendar_day_limit: int | None


PROGRAMS = {
    "max": Program("MAX", 6.0, 3.0, 1.0, 20, 30.0, 60),
    "flex": Program("FLEX", 6.0, 4.0, 2.0, 10, 50.0, None),
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--program", choices=PROGRAMS, default="max")
    p.add_argument("--account", type=float, default=25000)
    p.add_argument("--start", default=None)
    p.add_argument("--end", default=None)
    p.add_argument("--risk-pct", type=float, default=0.25)
    p.add_argument("--max-trades-day", type=int, default=3)
    p.add_argument("--min-rvol", type=float, default=1.5)
    p.add_argument("--max-stop-pct", type=float, default=1.5)
    p.add_argument("--max-position-pct", type=float, default=40.0)
    p.add_argument("--slippage-bps", type=float, default=2.0)
    p.add_argument("--trials", type=int, default=5000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out-prefix", default="ttp_tv_stock_backtest")
    return p.parse_args()


def load_setups(engine, start: str | None, end: str | None) -> pd.DataFrame:
    where = ["s.thesis = 'bullish'", "s.payload_json::jsonb #>> '{entry,type}' = 'opening_range_breakout'"]
    params: dict[str, object] = {}
    if start:
        where.append("s.trading_date >= :start")
        params["start"] = start
    if end:
        where.append("s.trading_date <= :end")
        params["end"] = end
    sql = text(f"""
        select s.trading_date, s.symbol, s.setup_id, s.payload_json,
               w.symbols_json
        from intraday_setups s
        join intraday_selected_watchlists w using (trading_date)
        where {' and '.join(where)}
        order by s.trading_date, s.symbol
    """)
    df = pd.read_sql(sql, engine, params=params)
    if df.empty:
        return df
    keep = []
    for _, row in df.iterrows():
        try:
            roster = json.loads(row["symbols_json"])
        except Exception:
            roster = []
        keep.append(row["symbol"] in roster or row["symbol"] in {"SPY", "QQQ"})
    return df.loc[keep].reset_index(drop=True)


def fetch_polygon_window(symbol: str, target: date, api_key: str) -> pd.DataFrame:
    start = target - timedelta(days=35)
    end = target
    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/minute/"
        f"{start.isoformat()}/{end.isoformat()}"
    )
    r = requests.get(
        url,
        params={"apiKey": api_key, "adjusted": "true", "sort": "asc", "limit": 50000},
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()
    rows = payload.get("results") or []
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    ts = pd.to_datetime(df["t"], unit="ms", utc=True).dt.tz_convert(ET)
    out = pd.DataFrame(
        {
            "ts": ts,
            "open": df["o"].astype(float),
            "high": df["h"].astype(float),
            "low": df["l"].astype(float),
            "close": df["c"].astype(float),
            "volume": df["v"].astype(float),
        }
    )
    out["session_date"] = out["ts"].dt.date
    out["minute_of_day"] = out["ts"].dt.hour * 60 + out["ts"].dt.minute
    out = out[(out["minute_of_day"] >= 570) & (out["minute_of_day"] <= 960)].copy()
    return out


def add_intraday_features(window: pd.DataFrame, target: date) -> pd.DataFrame:
    sessions = sorted(d for d in window["session_date"].unique() if d <= target)
    prior = [d for d in sessions if d < target][-20:]
    today = window[window["session_date"] == target].copy()
    if today.empty:
        return today

    today["cum_vol"] = today["volume"].cumsum()
    today["cum_pv"] = (today["close"] * today["volume"]).cumsum()
    today["vwap"] = today["cum_pv"] / today["cum_vol"].replace(0, np.nan)

    baseline: dict[int, list[float]] = {}
    for d in prior:
        day = window[window["session_date"] == d].copy()
        if day.empty:
            continue
        day["cum_vol"] = day["volume"].cumsum()
        for _, r in day.iterrows():
            baseline.setdefault(int(r["minute_of_day"]), []).append(float(r["cum_vol"]))

    def rvol(row: pd.Series) -> float:
        vals = baseline.get(int(row["minute_of_day"])) or []
        if len(vals) < 5:
            return float("nan")
        denom = float(np.mean(vals))
        return float(row["cum_vol"] / denom) if denom > 0 else float("nan")

    today["rvol"] = today.apply(rvol, axis=1)
    return today.reset_index(drop=True)


def simulate_trade(
    bars: pd.DataFrame,
    account: float,
    risk_pct: float,
    min_rvol: float,
    max_stop_pct: float,
    max_position_pct: float,
    slippage_bps: float,
) -> dict | None:
    if bars.empty:
        return None

    opening = bars[(bars["minute_of_day"] >= 570) & (bars["minute_of_day"] < 575)]
    if len(opening) < 5:
        return None
    orh = float(opening["high"].max())

    candidates = bars[
        (bars["minute_of_day"] >= 575)
        & (bars["minute_of_day"] <= 690)
        & (bars["close"] > orh)
        & (bars["close"] > bars["vwap"])
        & (bars["rvol"] >= min_rvol)
    ]
    if candidates.empty:
        return None

    entry_idx = int(candidates.index[0])
    entry_bar = bars.loc[entry_idx]
    prior = bars[(bars.index < entry_idx) & (bars["minute_of_day"] >= 570)].tail(5)
    if prior.empty:
        return None

    raw_entry = float(entry_bar["close"])
    entry = raw_entry * (1.0 + slippage_bps / 10000.0)
    stop = float(prior["low"].min())
    stop_dist = entry - stop
    if stop_dist <= 0:
        return None
    stop_pct = stop_dist / entry * 100.0
    if stop_pct > max_stop_pct:
        return None

    risk_dollars = account * risk_pct / 100.0
    shares_by_risk = math.floor(risk_dollars / stop_dist)
    shares_by_bp = math.floor((account * max_position_pct / 100.0) / entry)
    shares = max(0, min(shares_by_risk, shares_by_bp))
    if shares < 1:
        return None

    t1 = entry + stop_dist
    t2 = entry + 2.0 * stop_dist
    half = shares // 2
    rem = shares - half

    realized = 0.0
    target1_hit = False
    exit_ts = None
    exit_px_avg_num = 0.0
    exit_shares = 0

    future = bars[(bars.index > entry_idx) & (bars["minute_of_day"] <= 945)]
    for _, bar in future.iterrows():
        lo = float(bar["low"])
        hi = float(bar["high"])

        if not target1_hit:
            if lo <= stop:
                px = stop * (1.0 - slippage_bps / 10000.0)
                realized += (px - entry) * shares
                exit_px_avg_num += px * shares
                exit_shares += shares
                exit_ts = bar["ts"]
                break
            if hi >= t1:
                px = t1 * (1.0 - slippage_bps / 10000.0)
                if half > 0:
                    realized += (px - entry) * half
                    exit_px_avg_num += px * half
                    exit_shares += half
                target1_hit = True
                continue
        else:
            # Conservative same-bar ordering: breakeven stop before 2R target.
            if lo <= entry:
                px = entry * (1.0 - slippage_bps / 10000.0)
                realized += (px - entry) * rem
                exit_px_avg_num += px * rem
                exit_shares += rem
                exit_ts = bar["ts"]
                break
            if hi >= t2:
                px = t2 * (1.0 - slippage_bps / 10000.0)
                realized += (px - entry) * rem
                exit_px_avg_num += px * rem
                exit_shares += rem
                exit_ts = bar["ts"]
                break

    if exit_ts is None:
        final = future.iloc[-1] if not future.empty else entry_bar
        px = float(final["close"]) * (1.0 - slippage_bps / 10000.0)
        open_shares = shares - exit_shares
        realized += (px - entry) * open_shares
        exit_px_avg_num += px * open_shares
        exit_shares += open_shares
        exit_ts = final["ts"]

    avg_exit = exit_px_avg_num / exit_shares if exit_shares else entry
    duration_s = max(0.0, (exit_ts - entry_bar["ts"]).total_seconds())
    per_share_gain = avg_exit - entry
    valid_profit = realized
    if realized > 0 and (duration_s < 30.0 or per_share_gain < 0.10):
        valid_profit = 0.0

    return {
        "entry_ts": entry_bar["ts"],
        "exit_ts": exit_ts,
        "entry": round(entry, 4),
        "stop": round(stop, 4),
        "target1": round(t1, 4),
        "target2": round(t2, 4),
        "shares": shares,
        "rvol": round(float(entry_bar["rvol"]), 3),
        "vwap": round(float(entry_bar["vwap"]), 4),
        "orh": round(orh, 4),
        "pnl": round(realized, 2),
        "valid_profit": round(valid_profit, 2),
        "duration_seconds": round(duration_s, 1),
        "per_share_gain": round(per_share_gain, 4),
    }


def evaluate_sequence(trades: pd.DataFrame, account: float, program: Program, max_trades_day: int) -> dict:
    target = account * program.profit_target_pct / 100.0
    max_loss = account * program.max_loss_pct / 100.0
    daily_pause = account * program.daily_pause_pct / 100.0

    equity_pnl = 0.0
    valid_profit = 0.0
    position_count = 0
    best_valid_trade = 0.0
    start_date = None

    for d, day in trades.groupby("trading_date", sort=True):
        if start_date is None:
            start_date = pd.Timestamp(d).date()
        if program.calendar_day_limit is not None:
            if (pd.Timestamp(d).date() - start_date).days >= program.calendar_day_limit:
                return {"status": "TIMEOUT", "equity_pnl": equity_pnl, "valid_profit": valid_profit, "positions": position_count}

        day_pnl = 0.0
        for _, t in day.sort_values("entry_ts").head(max_trades_day).iterrows():
            if day_pnl <= -daily_pause:
                break
            pnl = float(t["pnl"])
            equity_pnl += pnl
            day_pnl += pnl
            position_count += 1
            if pnl > 0:
                vp = float(t["valid_profit"])
                valid_profit += vp
                best_valid_trade = max(best_valid_trade, vp)

            if equity_pnl <= -max_loss:
                return {"status": "FAIL_MAX_LOSS", "equity_pnl": equity_pnl, "valid_profit": valid_profit, "positions": position_count}

            consistency_ok = best_valid_trade <= target * program.consistency_pct / 100.0
            if valid_profit >= target and position_count >= program.min_positions and consistency_ok:
                return {"status": "PASS", "equity_pnl": equity_pnl, "valid_profit": valid_profit, "positions": position_count}

    consistency_ok = best_valid_trade <= target * program.consistency_pct / 100.0
    return {
        "status": "INCOMPLETE",
        "equity_pnl": equity_pnl,
        "valid_profit": valid_profit,
        "positions": position_count,
        "consistency_ok": consistency_ok,
    }


def monte_carlo(trades: pd.DataFrame, account: float, program: Program, max_trades_day: int, trials: int, seed: int) -> dict:
    if trades.empty or trades["trading_date"].nunique() < 10:
        return {"trials": 0, "warning": "Need at least 10 stored trading days before Monte Carlo is meaningful."}

    grouped = [g.copy() for _, g in trades.groupby("trading_date", sort=True)]
    rng = np.random.default_rng(seed)
    statuses: list[str] = []
    for _ in range(trials):
        sampled = []
        base = date(2020, 1, 1)
        for i in range(max(60, len(grouped))):
            g = grouped[int(rng.integers(0, len(grouped)))].copy()
            g["trading_date"] = base + timedelta(days=i)
            sampled.append(g)
        sim = pd.concat(sampled, ignore_index=True)
        statuses.append(evaluate_sequence(sim, account, program, max_trades_day)["status"])

    s = pd.Series(statuses)
    return {
        "trials": trials,
        "pass_rate_pct": round(float((s == "PASS").mean() * 100), 2),
        "max_loss_fail_pct": round(float((s == "FAIL_MAX_LOSS").mean() * 100), 2),
        "timeout_pct": round(float((s == "TIMEOUT").mean() * 100), 2),
        "incomplete_pct": round(float((s == "INCOMPLETE").mean() * 100), 2),
    }


def main() -> None:
    args = parse_args()
    db_url = os.getenv("DATABASE_URL")
    polygon_key = os.getenv("POLYGON_API_KEY")
    if not db_url:
        raise SystemExit("DATABASE_URL is required")
    if not polygon_key:
        raise SystemExit("POLYGON_API_KEY is required")

    engine = create_engine(db_url)
    setups = load_setups(engine, args.start, args.end)
    if setups.empty:
        raise SystemExit("No stored bullish opening-range Trade Volatility watchlist setups found.")

    cache: dict[tuple[str, date], pd.DataFrame] = {}
    results: list[dict] = []
    for _, setup in setups.iterrows():
        d = pd.Timestamp(setup["trading_date"]).date()
        symbol = str(setup["symbol"]).upper()
        key = (symbol, d)
        if key not in cache:
            cache[key] = fetch_polygon_window(symbol, d, polygon_key)
        bars = add_intraday_features(cache[key], d)
        trade = simulate_trade(
            bars,
            account=args.account,
            risk_pct=args.risk_pct,
            min_rvol=args.min_rvol,
            max_stop_pct=args.max_stop_pct,
            max_position_pct=args.max_position_pct,
            slippage_bps=args.slippage_bps,
        )
        if trade:
            trade.update({"trading_date": d, "symbol": symbol, "setup_id": setup["setup_id"]})
            results.append(trade)

    trades = pd.DataFrame(results)
    trades.to_csv(f"{args.out_prefix}_trades.csv", index=False)

    program = PROGRAMS[args.program]
    sequence = evaluate_sequence(trades, args.account, program, args.max_trades_day) if not trades.empty else {"status": "NO_TRADES"}
    mc = monte_carlo(trades, args.account, program, args.max_trades_day, args.trials, args.seed)

    if trades.empty:
        metrics = {"trades": 0}
    else:
        wins = trades[trades["pnl"] > 0]
        losses = trades[trades["pnl"] < 0]
        gross_win = float(wins["pnl"].sum())
        gross_loss = abs(float(losses["pnl"].sum()))
        metrics = {
            "trades": int(len(trades)),
            "days": int(trades["trading_date"].nunique()),
            "win_rate_pct": round(float((trades["pnl"] > 0).mean() * 100), 2),
            "net_pnl": round(float(trades["pnl"].sum()), 2),
            "profit_factor": round(gross_win / gross_loss, 3) if gross_loss else None,
            "avg_trade": round(float(trades["pnl"].mean()), 2),
            "avg_winner": round(float(wins["pnl"].mean()), 2) if len(wins) else None,
            "avg_loser": round(float(losses["pnl"].mean()), 2) if len(losses) else None,
        }

    summary = {
        "program": program.name,
        "account": args.account,
        "strategy": {
            "direction": "long-only",
            "entry_window_et": "09:35-11:30",
            "entry": "close > 5-min opening-range high AND close > VWAP AND RVOL threshold",
            "min_rvol": args.min_rvol,
            "risk_pct": args.risk_pct,
            "stop": "lowest low of previous 5 one-minute bars",
            "max_stop_pct": args.max_stop_pct,
            "profit_management": "50% at +1R, remainder at +2R; breakeven stop after +1R",
            "flat_by_et": "15:45",
            "max_trades_day": args.max_trades_day,
            "slippage_bps_each_side": args.slippage_bps,
        },
        "data": {
            "stored_setup_rows": int(len(setups)),
            "stored_setup_days": int(setups["trading_date"].nunique()),
            "note": "Only AlphaGEX-stored historical watchlists are tested; missing historical TV rankings are not reconstructed.",
        },
        "metrics": metrics,
        "evaluation": sequence,
        "monte_carlo": mc,
    }
    with open(f"{args.out_prefix}_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
