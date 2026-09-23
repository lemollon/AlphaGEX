"""Read-only VALOR historical research routes.

These endpoints never touch trading accounts, orders, positions, or scheduler state.
They use the DATABENTO_API_KEY present in the Render runtime to price and run
historical futures research server-side.
"""
from __future__ import annotations

import math
import os
from datetime import time
from typing import Dict, List

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from starlette.concurrency import run_in_threadpool

router = APIRouter(prefix="/api/valor/research/databento", tags=["valor-research"])

PRODUCTS: Dict[str, Dict[str, float | str]] = {
    "MES": {"symbol": "MES.v.0", "point_value": 5.0, "cost_pts": 1.10},
    "MNQ": {"symbol": "MNQ.v.0", "point_value": 2.0, "cost_pts": 2.00},
    "RTY": {"symbol": "M2K.v.0", "point_value": 5.0, "cost_pts": 0.80},
    "MGC": {"symbol": "MGC.v.0", "point_value": 10.0, "cost_pts": 0.50},
    "NG": {"symbol": "MNG.v.0", "point_value": 100.0, "cost_pts": 0.032},
    "CL": {"symbol": "MCL.v.0", "point_value": 100.0, "cost_pts": 0.05},
}

RTH = {
    "MES": (time(8, 30), time(15, 0)),
    "MNQ": (time(8, 30), time(15, 0)),
    "RTY": (time(8, 30), time(15, 0)),
    "MGC": (time(7, 20), time(12, 30)),
    "NG": (time(8, 0), time(13, 30)),
    "CL": (time(8, 0), time(13, 30)),
}


def _client():
    key = os.getenv("DATABENTO_API_KEY")
    if not key:
        raise RuntimeError("DATABENTO_API_KEY is not configured in this Render service")
    import databento as db
    return db.Historical(key)


def _validate_ticker(ticker: str) -> str:
    t = ticker.upper()
    if t not in PRODUCTS:
        raise ValueError(f"Unsupported ticker {ticker}")
    return t


def _is_rth(ts: pd.Timestamp, ticker: str) -> bool:
    local = ts.tz_convert("America/Chicago")
    start, end = RTH[ticker]
    tt = local.time()
    return start <= tt < end


def _summarize(pnl: pd.Series) -> Dict[str, float | int | None]:
    pnl = pnl.dropna()
    if pnl.empty:
        return {"trades": 0, "net_dollars": 0.0, "avg_trade": 0.0, "win_rate": 0.0, "profit_factor": None}
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    pf = None
    if not losses.empty and abs(float(losses.sum())) > 0:
        pf = float(wins.sum()) / abs(float(losses.sum()))
    return {
        "trades": int(len(pnl)),
        "net_dollars": round(float(pnl.sum()), 2),
        "avg_trade": round(float(pnl.mean()), 2),
        "win_rate": round(float((pnl > 0).mean() * 100), 2),
        "profit_factor": round(pf, 3) if pf is not None and math.isfinite(pf) else None,
    }


def _future_close(df: pd.DataFrame, horizon: int) -> pd.Series:
    left = pd.DataFrame({
        "row_id": np.arange(len(df)),
        "target_ts": df["timestamp"] + pd.to_timedelta(horizon, unit="m"),
    })
    right = df[["timestamp", "close"]].rename(columns={"timestamp": "future_ts", "close": "future_close"})
    merged = pd.merge_asof(
        left.sort_values("target_ts"),
        right.sort_values("future_ts"),
        left_on="target_ts",
        right_on="future_ts",
        direction="forward",
        tolerance=pd.Timedelta("2min"),
    ).sort_values("row_id")
    return merged["future_close"].reset_index(drop=True)


def _run_year(ticker: str, year: int) -> dict:
    t = _validate_ticker(ticker)
    cfg = PRODUCTS[t]
    client = _client()
    start = f"{year}-01-01"
    end = f"{year + 1}-01-01"
    data = client.timeseries.get_range(
        dataset="GLBX.MDP3",
        schema="ohlcv-1m",
        symbols=str(cfg["symbol"]),
        stype_in="continuous",
        start=start,
        end=end,
    )
    df = data.to_df().reset_index()
    if df.empty:
        raise RuntimeError(f"No Databento bars returned for {t} {year}")

    ts_col = "ts_event" if "ts_event" in df.columns else df.columns[0]
    df["timestamp"] = pd.to_datetime(df[ts_col], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["high"] = pd.to_numeric(df["high"], errors="coerce")
    df["low"] = pd.to_numeric(df["low"], errors="coerce")
    df["rth"] = df["timestamp"].map(lambda x: _is_rth(x, t))

    ret15 = df["close"] - df["close"].shift(15)
    ret30 = df["close"] - df["close"].shift(30)
    prev_high30 = df["high"].shift(1).rolling(30, min_periods=30).max()
    prev_low30 = df["low"].shift(1).rolling(30, min_periods=30).min()
    ema20 = df["close"].ewm(span=20, adjust=False).mean()
    ema80 = df["close"].ewm(span=80, adjust=False).mean()

    rules: Dict[str, pd.Series] = {
        "momentum_15m": pd.Series(np.sign(ret15), index=df.index),
        "mean_reversion_15m": pd.Series(-np.sign(ret15), index=df.index),
        "momentum_30m": pd.Series(np.sign(ret30), index=df.index),
        "breakout_30m": pd.Series(np.where(df["close"] > prev_high30, 1, np.where(df["close"] < prev_low30, -1, 0)), index=df.index),
        "ema_trend_20_80": pd.Series(np.sign(ema20 - ema80), index=df.index),
    }

    results: List[dict] = []
    for horizon in (30, 60, 120, 180, 240):
        future = _future_close(df, horizon)
        epoch = df["timestamp"].astype("int64") // 1_000_000_000
        bucket = (epoch // (horizon * 60)).astype("int64")
        for rule_name, side in rules.items():
            base = pd.DataFrame({
                "timestamp": df["timestamp"],
                "close": df["close"],
                "future_close": future,
                "side": side,
                "rth": df["rth"],
                "bucket": bucket,
            })
            base = base[(base["side"] != 0) & base["future_close"].notna()].copy()
            for session in ("ALL", "RTH", "OVERNIGHT"):
                x = base if session == "ALL" else base[base["rth"].eq(session == "RTH")]
                # One independent entry per holding-period bucket.
                x = x.drop_duplicates(subset=["bucket"], keep="first")
                gross_pts = x["side"] * (x["future_close"] - x["close"])
                pnl = (gross_pts - float(cfg["cost_pts"])) * float(cfg["point_value"])
                results.append({
                    "ticker": t,
                    "year": year,
                    "rule": rule_name,
                    "horizon_min": horizon,
                    "session": session,
                    **_summarize(pnl),
                })

    ranked = sorted(results, key=lambda r: (r["net_dollars"], r["profit_factor"] or -1), reverse=True)
    return {
        "ticker": t,
        "year": year,
        "bars": int(len(df)),
        "first_bar": df["timestamp"].iloc[0].isoformat(),
        "last_bar": df["timestamp"].iloc[-1].isoformat(),
        "cost_model_points": float(cfg["cost_pts"]),
        "results": results,
        "top_10": ranked[:10],
        "research_only": True,
    }


@router.get("/status")
async def databento_status():
    return {"configured": bool(os.getenv("DATABENTO_API_KEY")), "research_only": True}


@router.get("/cost")
async def databento_cost(
    start: str = Query("2023-01-01"),
    end: str = Query("2026-01-01"),
):
    def work():
        client = _client()
        rows = []
        total = 0.0
        for ticker, cfg in PRODUCTS.items():
            cost = float(client.metadata.get_cost(
                dataset="GLBX.MDP3",
                schema="ohlcv-1m",
                symbols=str(cfg["symbol"]),
                stype_in="continuous",
                start=start,
                end=end,
            ))
            rows.append({"ticker": ticker, "symbol": cfg["symbol"], "cost_usd": round(cost, 4)})
            total += cost
        return {"start": start, "end": end, "requests": rows, "total_cost_usd": round(total, 4)}
    try:
        return await run_in_threadpool(work)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/run-year")
async def databento_run_year(ticker: str, year: int):
    if year not in (2023, 2024, 2025):
        raise HTTPException(status_code=400, detail="Research years are restricted to 2023-2025; 2026 remains untouched.")
    try:
        return await run_in_threadpool(_run_year, ticker, year)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
