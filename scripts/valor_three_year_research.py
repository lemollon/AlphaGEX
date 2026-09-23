#!/usr/bin/env python3
"""Three-year VALOR futures research harness.

Research only. Does not import or mutate live VALOR state.

Data:
- Databento CME Globex MDP 3.0, 1-minute OHLCV, volume-based continuous front month.
- Optional GEX/regime CSV produced from AlphaGEX historical stores.

Default research window is 2023-01-01 through 2025-12-31. 2026 is intentionally
left untouched for final out-of-sample validation.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

import pandas as pd

PRODUCTS = {
    "MES": {"continuous": "MES.v.0", "point_value": 5.0, "tick_size": 0.25, "cost_pts": 1.10},
    "MNQ": {"continuous": "MNQ.v.0", "point_value": 2.0, "tick_size": 0.25, "cost_pts": 2.00},
    "RTY": {"continuous": "M2K.v.0", "point_value": 5.0, "tick_size": 0.10, "cost_pts": 0.80},
    "MGC": {"continuous": "MGC.v.0", "point_value": 10.0, "tick_size": 0.10, "cost_pts": 0.50},
    "NG": {"continuous": "MNG.v.0", "point_value": 100.0, "tick_size": 0.001, "cost_pts": 0.032},
    "CL": {"continuous": "MCL.v.0", "point_value": 100.0, "tick_size": 0.01, "cost_pts": 0.05},
}

DEFAULT_START = "2023-01-01"
DEFAULT_END = "2026-01-01"


def _client():
    key = os.getenv("DATABENTO_API_KEY")
    if not key:
        raise RuntimeError("DATABENTO_API_KEY is required")
    import databento as db
    return db.Historical(key)


def download_bars(ticker: str, start: str, end: str, out_dir: Path) -> Path:
    cfg = PRODUCTS[ticker]
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{ticker}_{start}_{end}_1m.parquet"
    if path.exists():
        return path

    client = _client()
    data = client.timeseries.get_range(
        dataset="GLBX.MDP3",
        schema="ohlcv-1m",
        symbols=cfg["continuous"],
        stype_in="continuous",
        start=start,
        end=end,
    )
    df = data.to_df().reset_index()
    if df.empty:
        raise RuntimeError(f"No data returned for {ticker}")
    df["ticker"] = ticker
    df["continuous_symbol"] = cfg["continuous"]
    df.to_parquet(path, index=False)
    return path


def load_gex(path: Optional[Path]) -> Optional[pd.DataFrame]:
    if not path:
        return None
    g = pd.read_csv(path)
    if "timestamp" not in g.columns:
        raise ValueError("GEX CSV must include timestamp")
    g["timestamp"] = pd.to_datetime(g["timestamp"], utc=True)
    return g.sort_values("timestamp")


def attach_gex(bars: pd.DataFrame, gex: Optional[pd.DataFrame], ticker: str) -> pd.DataFrame:
    if gex is None:
        return bars
    x = gex[gex["ticker"].eq(ticker)].copy() if "ticker" in gex.columns else gex.copy()
    if x.empty:
        return bars
    bars = bars.sort_values("ts_event").copy()
    bars["timestamp"] = pd.to_datetime(bars["ts_event"], utc=True)
    return pd.merge_asof(
        bars,
        x.sort_values("timestamp"),
        on="timestamp",
        direction="backward",
        tolerance=pd.Timedelta("1D"),
    )


def add_session_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    ts = pd.to_datetime(out["timestamp"], utc=True).dt.tz_convert("America/Chicago")
    out["ct_hour"] = ts.dt.hour
    out["trade_date"] = ts.dt.date
    out["session"] = ((out["ct_hour"] >= 8) & (out["ct_hour"] < 15)).map({True: "RTH", False: "OVERNIGHT"})
    return out


def forward_edge(df: pd.DataFrame, side: pd.Series, horizon_minutes: int, cost_pts: float) -> pd.DataFrame:
    out = df.copy()
    h = int(horizon_minutes)
    out["side"] = side.astype(float)
    out["future_close"] = out["close"].shift(-h)
    out["gross_pts"] = out["side"] * (out["future_close"] - out["close"])
    out["net_pts"] = out["gross_pts"] - cost_pts
    return out


def summarize(x: pd.DataFrame, point_value: float) -> Dict[str, float]:
    x = x.dropna(subset=["net_pts"])
    if x.empty:
        return {"n": 0}
    pnl = x["net_pts"] * point_value
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    pf = float(wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() != 0 else math.inf
    return {
        "n": int(len(x)),
        "net_dollars": round(float(pnl.sum()), 2),
        "avg_trade_dollars": round(float(pnl.mean()), 2),
        "win_rate": round(float((pnl > 0).mean() * 100), 2),
        "profit_factor": round(pf, 3) if math.isfinite(pf) else None,
    }


def run_candidate_grid(df: pd.DataFrame, ticker: str) -> list[dict]:
    cfg = PRODUCTS[ticker]
    results = []
    horizons = (30, 60, 120, 180, 240)

    # Futures-native baselines are always available.
    ret15 = df["close"].pct_change(15)
    rules = {
        "mom15": ret15.apply(lambda v: 1 if v > 0 else (-1 if v < 0 else 0)),
        "meanrev15": ret15.apply(lambda v: -1 if v > 0 else (1 if v < 0 else 0)),
    }

    # GEX direction is evaluated only when aligned historical GEX is present.
    if {"gamma_regime", "flip_point"}.issubset(df.columns):
        rules["valor_current"] = pd.Series(
            [(-1 if p > f else 1) if str(g).upper() == "POSITIVE" else (1 if p > f else -1)
             for p, f, g in zip(df["close"], df["flip_point"], df["gamma_regime"])],
            index=df.index,
        )

    for name, side in rules.items():
        for horizon in horizons:
            z = forward_edge(df, side, horizon, cfg["cost_pts"])
            for session in ("ALL", "RTH", "OVERNIGHT"):
                y = z if session == "ALL" else z[z["session"].eq(session)]
                if "gamma_regime" in y.columns:
                    regimes: Iterable[str] = ("ALL", "POSITIVE", "NEGATIVE")
                else:
                    regimes = ("ALL",)
                for regime in regimes:
                    q = y if regime == "ALL" else y[y["gamma_regime"].astype(str).str.upper().eq(regime)]
                    s = summarize(q, cfg["point_value"])
                    results.append({
                        "ticker": ticker,
                        "rule": name,
                        "horizon_min": horizon,
                        "session": session,
                        "gamma_regime": regime,
                        **s,
                    })
    return results


def split_period(df: pd.DataFrame, year: int) -> pd.DataFrame:
    return df[pd.to_datetime(df["timestamp"], utc=True).dt.year.eq(year)].copy()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=DEFAULT_START)
    ap.add_argument("--end", default=DEFAULT_END)
    ap.add_argument("--tickers", nargs="+", default=list(PRODUCTS))
    ap.add_argument("--data-dir", default="/var/data/valor_3y")
    ap.add_argument("--gex-csv")
    ap.add_argument("--download-only", action="store_true")
    args = ap.parse_args()

    out_dir = Path(args.data_dir)
    gex = load_gex(Path(args.gex_csv)) if args.gex_csv else None
    all_results = []

    for ticker in args.tickers:
        p = download_bars(ticker, args.start, args.end, out_dir)
        df = pd.read_parquet(p)
        df["timestamp"] = pd.to_datetime(df["ts_event"], utc=True)
        df = attach_gex(df, gex, ticker)
        df = add_session_columns(df)
        if args.download_only:
            continue

        for year in (2023, 2024, 2025):
            yearly = split_period(df, year)
            for row in run_candidate_grid(yearly, ticker):
                row["year"] = year
                all_results.append(row)

    if not args.download_only:
        results = pd.DataFrame(all_results)
        results.to_csv(out_dir / "valor_3y_results.csv", index=False)
        with open(out_dir / "valor_3y_manifest.json", "w") as f:
            json.dump({
                "start": args.start,
                "end": args.end,
                "tickers": args.tickers,
                "dataset": "GLBX.MDP3",
                "schema": "ohlcv-1m",
                "symbology": "continuous volume front month",
                "research_only": True,
            }, f, indent=2)
        print(results.sort_values(["ticker","year","net_dollars"], ascending=[True,True,False]).to_string(index=False))


if __name__ == "__main__":
    main()
