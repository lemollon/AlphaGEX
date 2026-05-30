# services/vol_advisor_tracker.py
"""Forward tracking for the vol regime advisor: snapshot today's call, score matured calls."""
import json
import logging
from typing import Optional
import pandas as pd

logger = logging.getLogger(__name__)

def score_row(row: dict, fwd: pd.DataFrame) -> dict:
    """Grade one logged recommendation against forward VIX/SPY.
    fwd: rows AFTER the log date (index ascending), columns vix, spy.
    Returns realized_vix_chg, realized_spy_ret, event_landed_day, correct, in_window."""
    horizon = int(row.get("horizon_days") or 5)
    window = int(row.get("window_p75_days") or horizon)
    base_vix = float(row["vix"]); base_spy = float(row["spy"])
    pred = row.get("predicted_dir") or _dir_from_stance(row.get("stance"))

    fwd = fwd.head(max(horizon, window, 21))
    if fwd.empty:
        return {"realized_vix_chg": None, "realized_spy_ret": None,
                "event_landed_day": None, "correct": None, "in_window": None}

    h = min(horizon, len(fwd))
    realized_vix_chg = float(fwd["vix"].iloc[h-1] / base_vix - 1.0)
    realized_spy_ret = float(fwd["spy"].iloc[h-1] / base_spy - 1.0)

    landed = None
    for k in range(1, len(fwd) + 1):
        v = fwd["vix"].iloc[k-1]; p = fwd["spy"].iloc[k-1]
        if pred == "spy_up" and p >= base_spy * 1.005: landed = k; break
        if pred == "spy_down" and p <= base_spy * 0.995: landed = k; break
        if pred == "vol_down" and v <= base_vix * 0.90: landed = k; break
        if pred == "vol_up" and v >= base_vix * 1.20: landed = k; break

    if pred == "spy_up": correct = realized_spy_ret > 0
    elif pred == "spy_down": correct = realized_spy_ret < 0
    elif pred == "vol_down": correct = realized_vix_chg < 0
    elif pred == "vol_up": correct = realized_vix_chg > 0
    else: correct = None

    in_window = (landed is not None and landed <= window)
    return {"realized_vix_chg": realized_vix_chg, "realized_spy_ret": realized_spy_ret,
            "event_landed_day": landed, "correct": bool(correct) if correct is not None else None,
            "in_window": bool(in_window)}

def _dir_from_stance(stance: Optional[str]) -> str:
    return {"buy_the_bounce": "spy_up", "lean_calls": "spy_up",
            "lean_puts": "spy_down"}.get(stance or "", "vol_down")

# ---- DB wrappers (thin; depend on database_adapter + core engine) ----

def snapshot_today(report: dict) -> bool:
    """Insert today's advisor call into vol_advisor_log (idempotent on log_date)."""
    try:
        from database_adapter import get_connection
        from datetime import datetime
        from zoneinfo import ZoneInfo
        ET = ZoneInfo("America/New_York")
        d = datetime.now(ET).date()
        rec = report.get("recommendation", {})
        timing = report.get("timing", {})
        inputs = report.get("inputs", {})
        active = {k: v for k, v in (report.get("signals") or {}).items() if v.get("active")}
        conn = get_connection(); c = conn.cursor()
        c.execute("""
            INSERT INTO vol_advisor_log
              (log_date, vix, vvix, vix9d, vix3m, vix6m, regime_label, stance, conviction,
               active_signals, predicted_dir, horizon_days, window_p75_days)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (log_date) DO NOTHING
        """, (d, inputs.get("vix"), inputs.get("vvix"), inputs.get("vix9d"),
              inputs.get("vix3m"), inputs.get("vix6m"), report.get("regime_label"),
              rec.get("stance"), rec.get("conviction"), json.dumps(active),
              _dir_from_stance(rec.get("stance")), timing.get("median_days"),
              timing.get("p75_days")))
        conn.commit(); conn.close()
        return True
    except Exception as e:
        logger.error(f"snapshot_today failed: {e}")
        return False

def _build_fwd(hist: pd.DataFrame, spy: pd.Series, log_date, horizon) -> Optional[pd.DataFrame]:
    """Forward (vix, spy) frame for trading days strictly after log_date.

    hist is Timestamp-indexed (CBOE history, 'vix' col); spy is date-indexed
    (Yahoo daily closes). The two index types must be bridged via `.date()` —
    a Timestamp never equals a date in `in`/`.loc`, so without this the SPY
    column comes back all-NaN and nothing scores. Returns None if the horizon
    has not fully elapsed yet.
    """
    fwd_idx = hist.index[hist.index > pd.Timestamp(log_date)]
    if len(fwd_idx) < (horizon or 5):
        return None  # not matured yet
    spy_vals = [float(spy.loc[d.date()]) if d.date() in spy.index else float("nan")
                for d in fwd_idx]
    return pd.DataFrame({"vix": hist.loc[fwd_idx, "vix"].values, "spy": spy_vals},
                        index=fwd_idx).dropna()

def score_matured() -> int:
    """Score all unscored rows whose horizon has fully elapsed. Returns # scored."""
    try:
        from database_adapter import get_connection
        from core.vol_regime_advisor import fetch_cboe_history
        hist = fetch_cboe_history()
        spy = _spy_history()
        conn = get_connection(); c = conn.cursor()
        c.execute("""SELECT id, log_date, vix, stance, predicted_dir,
                            horizon_days, window_p75_days FROM vol_advisor_log
                     WHERE scored_at IS NULL ORDER BY log_date""")
        rows = c.fetchall()
        scored = 0
        for r in rows:
            rid, log_date, base_vix = r[0], r[1], r[2]
            stance, predicted_dir, horizon, window = r[3], r[4], r[5], r[6]
            if log_date not in spy.index:
                continue
            base_spy = float(spy.loc[log_date])
            fwd = _build_fwd(hist, spy, log_date, horizon)
            if fwd is None or fwd.empty:
                continue
            res = score_row({"stance": stance, "predicted_dir": predicted_dir,
                             "horizon_days": horizon, "window_p75_days": window,
                             "vix": base_vix, "spy": base_spy}, fwd)
            c.execute("""UPDATE vol_advisor_log SET realized_vix_chg=%s, realized_spy_ret=%s,
                         event_landed_day=%s, correct=%s, in_window=%s, scored_at=NOW()
                         WHERE id=%s""",
                      (res["realized_vix_chg"], res["realized_spy_ret"], res["event_landed_day"],
                       res["correct"], res["in_window"], rid))
            scored += 1
        conn.commit(); conn.close()
        return scored
    except Exception as e:
        logger.error(f"score_matured failed: {e}")
        return 0

def _spy_history() -> pd.Series:
    """Daily SPY closes for scoring, from Yahoo chart API (keyless)."""
    import requests
    j = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/SPY"
                     "?period1=1136073600&period2=9999999999&interval=1d",
                     headers={"User-Agent": "Mozilla/5.0"}, timeout=10).json()
    r = j["chart"]["result"][0]
    ts = pd.to_datetime(r["timestamp"], unit="s").normalize()
    s = pd.Series(r["indicators"]["adjclose"][0]["adjclose"], index=ts).dropna()
    s.index = s.index.date
    return s[~pd.Index(s.index).duplicated(keep="last")]
