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


def _ensure_research_tables(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS valor_three_year_research_runs (
            run_id TEXT PRIMARY KEY,
            started_at TIMESTAMPTZ DEFAULT NOW(),
            finished_at TIMESTAMPTZ,
            status TEXT NOT NULL,
            estimated_cost_usd NUMERIC,
            detail TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS valor_three_year_research_results (
            run_id TEXT NOT NULL,
            ticker TEXT NOT NULL,
            year INTEGER NOT NULL,
            bars INTEGER,
            first_bar TIMESTAMPTZ,
            last_bar TIMESTAMPTZ,
            cost_model_points NUMERIC,
            rule TEXT NOT NULL,
            horizon_min INTEGER NOT NULL,
            session TEXT NOT NULL,
            trades INTEGER,
            net_dollars NUMERIC,
            avg_trade NUMERIC,
            win_rate NUMERIC,
            profit_factor NUMERIC,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (run_id, ticker, year, rule, horizon_min, session)
        )
    """)
    conn.commit()


def _autorun_three_year_research():
    """Resume or start 2023-2025 research without redoing completed ticker-years."""
    import uuid
    from database_adapter import get_connection

    conn = get_connection()
    run_id = None
    try:
        _ensure_research_tables(conn)
        cur = conn.cursor()

        # Resume the latest incomplete run if one exists.
        cur.execute("""
            SELECT run_id, estimated_cost_usd
            FROM valor_three_year_research_runs
            WHERE status IN ('estimating_cost','cost_estimated','running')
            ORDER BY started_at DESC
            LIMIT 1
        """)
        existing = cur.fetchone()

        if existing:
            run_id, estimated_cost = existing
        else:
            run_id = "valor3y-" + uuid.uuid4().hex[:12]
            estimated_cost = None
            cur.execute(
                "INSERT INTO valor_three_year_research_runs(run_id,status,detail) VALUES (%s,%s,%s)",
                (run_id, "estimating_cost", "Databento 2023-2025 six-contract research"),
            )
            conn.commit()

        if estimated_cost is None:
            client = _client()
            total = 0.0
            pieces = []
            for ticker, cfg in PRODUCTS.items():
                cost = float(client.metadata.get_cost(
                    dataset="GLBX.MDP3",
                    schema="ohlcv-1m",
                    symbols=str(cfg["symbol"]),
                    stype_in="continuous",
                    start="2023-01-01",
                    end="2026-01-01",
                ))
                pieces.append((ticker, cost))
                total += cost

            cur.execute(
                "UPDATE valor_three_year_research_runs SET estimated_cost_usd=%s, status=%s, detail=%s WHERE run_id=%s",
                (total, "cost_estimated", str(pieces), run_id),
            )
            conn.commit()
        else:
            total = float(estimated_cost)

        ceiling = float(os.getenv("VALOR_RESEARCH_MAX_COST_USD", "125"))
        if total > ceiling:
            cur.execute(
                "UPDATE valor_three_year_research_runs SET finished_at=NOW(), status=%s, detail=%s WHERE run_id=%s",
                ("stopped_cost_limit", f"Estimated \${total:.2f} exceeds ceiling \${ceiling:.2f}", run_id),
            )
            conn.commit()
            return

        cur.execute(
            "UPDATE valor_three_year_research_runs SET status=%s, detail=%s WHERE run_id=%s",
            ("running", f"Estimated \${total:.2f}; resuming incomplete ticker-year jobs", run_id),
        )
        conn.commit()

        cur.execute("""
            SELECT ticker, year, COUNT(*)
            FROM valor_three_year_research_results
            WHERE run_id=%s
            GROUP BY ticker, year
        """, (run_id,))
        completed = {(r[0], int(r[1])) for r in cur.fetchall() if int(r[2]) >= 75}

        for ticker in PRODUCTS:
            for year in (2023, 2024, 2025):
                if (ticker, year) in completed:
                    continue

                payload = _run_year(ticker, year)
                for row in payload["results"]:
                    cur.execute(
                        """
                        INSERT INTO valor_three_year_research_results
                        (run_id,ticker,year,bars,first_bar,last_bar,cost_model_points,
                         rule,horizon_min,session,trades,net_dollars,avg_trade,win_rate,profit_factor)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (run_id,ticker,year,rule,horizon_min,session)
                        DO UPDATE SET
                          bars=EXCLUDED.bars,
                          first_bar=EXCLUDED.first_bar,
                          last_bar=EXCLUDED.last_bar,
                          cost_model_points=EXCLUDED.cost_model_points,
                          trades=EXCLUDED.trades,
                          net_dollars=EXCLUDED.net_dollars,
                          avg_trade=EXCLUDED.avg_trade,
                          win_rate=EXCLUDED.win_rate,
                          profit_factor=EXCLUDED.profit_factor
                        """,
                        (
                            run_id, ticker, year, payload["bars"], payload["first_bar"], payload["last_bar"],
                            payload["cost_model_points"], row["rule"], row["horizon_min"], row["session"],
                            row["trades"], row["net_dollars"], row["avg_trade"], row["win_rate"], row["profit_factor"],
                        ),
                    )
                conn.commit()

        cur.execute("""
            SELECT COUNT(DISTINCT ticker || '-' || year::text)
            FROM valor_three_year_research_results
            WHERE run_id=%s
        """, (run_id,))
        finished_jobs = int(cur.fetchone()[0] or 0)

        if finished_jobs >= 18:
            cur.execute(
                "UPDATE valor_three_year_research_runs SET finished_at=NOW(), status=%s, detail=%s WHERE run_id=%s",
                ("completed", "All six contracts x 2023-2025 completed", run_id),
            )
        else:
            cur.execute(
                "UPDATE valor_three_year_research_runs SET status=%s, detail=%s WHERE run_id=%s",
                ("running", f"{finished_jobs}/18 ticker-year jobs stored; resume on next startup if interrupted", run_id),
            )
        conn.commit()
    except Exception as exc:
        try:
            _ensure_research_tables(conn)
            cur = conn.cursor()
            if run_id:
                cur.execute(
                    "UPDATE valor_three_year_research_runs SET status=%s, detail=%s WHERE run_id=%s",
                    ("running", f"Interrupted: {repr(exc)}; will resume", run_id),
                )
                conn.commit()
        except Exception:
            pass
        raise
    finally:
        conn.close()

def launch_autorun_if_enabled():
    """Start the research in a daemon thread; safe for API startup."""
    if os.getenv("VALOR_RESEARCH_AUTORUN", "").strip().lower() not in {"1","true","yes","on"}:
        return False
    import threading
    t = threading.Thread(target=_autorun_three_year_research, name="valor-3y-research", daemon=True)
    t.start()
    return True


# ---------------------------------------------------------------------------
# Contract-specific candidate search (2023-2025 only; 2026 remains untouched)
# ---------------------------------------------------------------------------

def _rth_minutes(ts: pd.Series, ticker: str) -> pd.Series:
    local = pd.to_datetime(ts, utc=True).dt.tz_convert("America/Chicago")
    start, _ = RTH[ticker]
    return (local.dt.hour * 60 + local.dt.minute) - (start.hour * 60 + start.minute)


def _cross_events(raw_side: pd.Series) -> pd.Series:
    s = raw_side.fillna(0).astype(int)
    return s.where((s != 0) & (s != s.shift(1).fillna(0)), 0)


def _candidate_sides(df: pd.DataFrame, ticker: str) -> Dict[str, pd.Series]:
    close = df["close"]
    high = df["high"]
    low = df["low"]
    ret15 = close - close.shift(15)
    ret30 = close - close.shift(30)
    ret60 = close - close.shift(60)

    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr14 = tr.rolling(14, min_periods=14).mean()
    atr60 = tr.rolling(60, min_periods=60).mean()
    atr_ratio = atr14 / atr60.replace(0, np.nan)

    ema20 = close.ewm(span=20, adjust=False).mean()
    ema80 = close.ewm(span=80, adjust=False).mean()
    ema200 = close.ewm(span=200, adjust=False).mean()

    hh30 = high.shift(1).rolling(30, min_periods=30).max()
    ll30 = low.shift(1).rolling(30, min_periods=30).min()
    hh60 = high.shift(1).rolling(60, min_periods=60).max()
    ll60 = low.shift(1).rolling(60, min_periods=60).min()
    hh120 = high.shift(1).rolling(120, min_periods=120).max()
    ll120 = low.shift(1).rolling(120, min_periods=120).min()

    mom15 = pd.Series(np.sign(ret15), index=df.index).astype(int)
    mom30 = pd.Series(np.sign(ret30), index=df.index).astype(int)
    mom60 = pd.Series(np.sign(ret60), index=df.index).astype(int)

    br30 = pd.Series(np.where(close > hh30, 1, np.where(close < ll30, -1, 0)), index=df.index)
    br60 = pd.Series(np.where(close > hh60, 1, np.where(close < ll60, -1, 0)), index=df.index)
    br120 = pd.Series(np.where(close > hh120, 1, np.where(close < ll120, -1, 0)), index=df.index)

    trend = pd.Series(np.sign(ema20 - ema80), index=df.index).astype(int)
    trend_long = pd.Series(np.sign(ema80 - ema200), index=df.index).astype(int)

    # Trend-confirmed breakout families.
    br30_trend = br30.where(br30 == trend, 0)
    br60_trend = br60.where(br60 == trend, 0)
    br120_trend = br120.where(br120 == trend_long, 0)

    # High-volatility and low-volatility specializations.
    br30_hv = br30.where(atr_ratio >= 1.05, 0)
    br60_hv = br60.where(atr_ratio >= 1.05, 0)
    mr15_lv = (-mom15).where(atr_ratio <= 0.95, 0)
    mr30_lv = (-mom30).where(atr_ratio <= 0.95, 0)

    # RTH opening range, using first 30/60 minutes of each CT session.
    local = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert("America/Chicago")
    session_date = local.dt.date
    mins = _rth_minutes(df["timestamp"], ticker)
    rth_mask = df["rth"]

    def opening_range(n: int):
        seed = rth_mask & (mins >= 0) & (mins < n)
        or_high = high.where(seed).groupby(session_date).transform("max")
        or_low = low.where(seed).groupby(session_date).transform("min")
        active = rth_mask & (mins >= n)
        breakout = pd.Series(np.where(active & (close > or_high), 1,
                                      np.where(active & (close < or_low), -1, 0)), index=df.index)
        reversion = pd.Series(np.where(active & (close > or_high), -1,
                                       np.where(active & (close < or_low), 1, 0)), index=df.index)
        return breakout, reversion

    orb30, orm30 = opening_range(30)
    orb60, orm60 = opening_range(60)

    all_rules = {
        "momentum_15m": mom15,
        "momentum_30m": mom30,
        "momentum_60m": mom60,
        "mean_reversion_15m": -mom15,
        "mean_reversion_30m": -mom30,
        "breakout_30m": br30,
        "breakout_60m": br60,
        "breakout_120m": br120,
        "breakout_30m_trend": br30_trend,
        "breakout_60m_trend": br60_trend,
        "breakout_120m_trend": br120_trend,
        "breakout_30m_highvol": br30_hv,
        "breakout_60m_highvol": br60_hv,
        "meanrev_15m_lowvol": mr15_lv,
        "meanrev_30m_lowvol": mr30_lv,
        "ema_trend_20_80": trend,
        "ema_trend_80_200": trend_long,
        "opening_range_breakout_30": _cross_events(orb30),
        "opening_range_breakout_60": _cross_events(orb60),
        "opening_range_revert_30": _cross_events(orm30),
        "opening_range_revert_60": _cross_events(orm60),
    }

    # Contract-specific shortlist: deliberately different playbooks.
    keep = {
        "MNQ": {
            "breakout_30m","breakout_60m","breakout_30m_trend","breakout_60m_trend",
            "breakout_30m_highvol","ema_trend_20_80","opening_range_breakout_30",
            "opening_range_breakout_60",
        },
        "MES": {
            "mean_reversion_15m","mean_reversion_30m","meanrev_15m_lowvol","meanrev_30m_lowvol",
            "opening_range_revert_30","opening_range_revert_60",
            "breakout_60m_trend","opening_range_breakout_30",
        },
        "RTY": {
            "mean_reversion_15m","mean_reversion_30m","meanrev_15m_lowvol","meanrev_30m_lowvol",
            "opening_range_revert_30","opening_range_revert_60",
            "breakout_30m_highvol","opening_range_breakout_30",
        },
        "MGC": {
            "mean_reversion_15m","mean_reversion_30m","breakout_60m","breakout_120m",
            "breakout_60m_trend","breakout_120m_trend","ema_trend_80_200",
            "opening_range_breakout_60","opening_range_revert_60",
        },
        "NG": {
            "breakout_30m","breakout_60m","breakout_120m","breakout_30m_highvol",
            "breakout_60m_highvol","breakout_60m_trend","breakout_120m_trend",
            "momentum_60m","opening_range_breakout_30","opening_range_breakout_60",
        },
        "CL": {
            "breakout_30m","breakout_60m","breakout_120m","breakout_30m_highvol",
            "breakout_60m_highvol","breakout_60m_trend","ema_trend_20_80",
            "opening_range_breakout_30","opening_range_breakout_60",
        },
    }
    return {k: v for k, v in all_rules.items() if k in keep[ticker]}


def _run_contract_specific_year(ticker: str, year: int) -> dict:
    t = _validate_ticker(ticker)
    cfg = PRODUCTS[t]
    client = _client()
    data = client.timeseries.get_range(
        dataset="GLBX.MDP3",
        schema="ohlcv-1m",
        symbols=str(cfg["symbol"]),
        stype_in="continuous",
        start=f"{year}-01-01",
        end=f"{year+1}-01-01",
    )
    df = data.to_df().reset_index()
    if df.empty:
        raise RuntimeError(f"No Databento bars returned for {t} {year}")

    ts_col = "ts_event" if "ts_event" in df.columns else df.columns[0]
    df["timestamp"] = pd.to_datetime(df[ts_col], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    for col in ("open","high","low","close"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["rth"] = df["timestamp"].map(lambda x: _is_rth(x, t))

    rules = _candidate_sides(df, t)
    results = []
    for horizon in (30, 60, 90, 120, 180, 240):
        future = _future_close(df, horizon)
        epoch = df["timestamp"].astype("int64") // 1_000_000_000
        bucket = (epoch // (horizon * 60)).astype("int64")
        for rule_name, side in rules.items():
            base = pd.DataFrame({
                "timestamp": df["timestamp"], "close": df["close"],
                "future_close": future, "side": side, "rth": df["rth"], "bucket": bucket,
            })
            base = base[(base["side"] != 0) & base["future_close"].notna()].copy()
            for session in ("ALL","RTH","OVERNIGHT"):
                x = base if session=="ALL" else base[base["rth"].eq(session=="RTH")]
                x = x.drop_duplicates(subset=["bucket"], keep="first")
                gross_pts = x["side"] * (x["future_close"] - x["close"])
                pnl = (gross_pts - float(cfg["cost_pts"])) * float(cfg["point_value"])
                results.append({
                    "ticker": t, "year": year, "rule": rule_name, "horizon_min": horizon,
                    "session": session, **_summarize(pnl),
                })
    return {"ticker": t, "year": year, "bars": len(df), "results": results}


def _ensure_candidate_table(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS valor_contract_strategy_results (
            research_id TEXT NOT NULL,
            ticker TEXT NOT NULL,
            year INTEGER NOT NULL,
            rule TEXT NOT NULL,
            horizon_min INTEGER NOT NULL,
            session TEXT NOT NULL,
            trades INTEGER,
            net_dollars NUMERIC,
            avg_trade NUMERIC,
            win_rate NUMERIC,
            profit_factor NUMERIC,
            bars INTEGER,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY(research_id,ticker,year,rule,horizon_min,session)
        )
    """)
    conn.commit()


def _autorun_contract_strategy_search():
    from database_adapter import get_connection
    research_id = "valor-contract-v1"
    conn = get_connection()
    try:
        _ensure_candidate_table(conn)
        cur = conn.cursor()
        for ticker in PRODUCTS:
            for year in (2023,2024,2025):
                cur.execute("""
                    SELECT COUNT(*) FROM valor_contract_strategy_results
                    WHERE research_id=%s AND ticker=%s AND year=%s
                """, (research_id,ticker,year))
                if int(cur.fetchone()[0] or 0) > 0:
                    continue
                payload = _run_contract_specific_year(ticker, year)
                for row in payload["results"]:
                    cur.execute("""
                        INSERT INTO valor_contract_strategy_results
                        (research_id,ticker,year,rule,horizon_min,session,trades,net_dollars,
                         avg_trade,win_rate,profit_factor,bars)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT DO NOTHING
                    """, (
                        research_id,ticker,year,row["rule"],row["horizon_min"],row["session"],
                        row["trades"],row["net_dollars"],row["avg_trade"],row["win_rate"],
                        row["profit_factor"],payload["bars"],
                    ))
                conn.commit()
    finally:
        conn.close()


def launch_contract_search_if_enabled():
    if os.getenv("VALOR_CONTRACT_RESEARCH_AUTORUN", "").strip().lower() not in {"1","true","yes","on"}:
        return False
    import threading
    t = threading.Thread(target=_autorun_contract_strategy_search, name="valor-contract-research", daemon=True)
    t.start()
    return True
