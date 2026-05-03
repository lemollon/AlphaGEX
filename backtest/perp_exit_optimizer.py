"""
Perp Exit-Rule Optimizer

Replays each historical perp entry against candidate exit-rule
parameter sets to find which exit configs would have produced the
best realized P&L while preserving trade frequency.

Per user constraint: only exit logic is varied. Entries are taken
as-is from history (so trade frequency stays whatever the live
signal/entry path produced).

Mirrors the exit logic in trading/agape_*_perp/trader.py:_manage_no_loss_trailing
so simulator results map directly to live config knobs.

Usage:
    python -m backtest.perp_exit_optimizer                # all 5 bots, coarse grid
    python -m backtest.perp_exit_optimizer --bot XRP      # one bot
    python -m backtest.perp_exit_optimizer --grid fine    # finer grid (slower)
    python -m backtest.perp_exit_optimizer --json out.json
"""

from __future__ import annotations

import argparse
import bisect
import itertools
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("perp_exit_optimizer")


BOTS = [
    {"name": "AGAPE_XRP_PERP",  "ticker": "XRP",  "table": "agape_xrp_perp",  "price_col": "xrp_price",  "starting_capital": 9000.0},
    {"name": "AGAPE_BTC_PERP",  "ticker": "BTC",  "table": "agape_btc_perp",  "price_col": "btc_price",  "starting_capital": 25000.0},
    {"name": "AGAPE_ETH_PERP",  "ticker": "ETH",  "table": "agape_eth_perp",  "price_col": "eth_price",  "starting_capital": 12500.0},
    {"name": "AGAPE_DOGE_PERP", "ticker": "DOGE", "table": "agape_doge_perp", "price_col": "doge_price", "starting_capital": 5000.0},
    {"name": "AGAPE_SHIB_PERP", "ticker": "SHIB", "table": "agape_shib_perp", "price_col": "shib_price", "starting_capital": 5000.0},
]


@dataclass(frozen=True)
class ExitConfig:
    activation_pct: float
    trail_pct: float
    profit_target_pct: float   # 0 disables hard target (matches trader.py semantics)
    max_loss_pct: float
    emergency_stop_pct: float
    max_hold_hours: float
    sar_enabled: bool
    sar_trigger_pct: float
    sar_mfe_threshold_pct: float


# Mirror of current production defaults so we have a baseline to beat
CURRENT_DEFAULTS = {
    "AGAPE_XRP_PERP":  ExitConfig(1.0, 0.75, 0.0, 3.0, 5.0, 24, True, 1.5, 0.3),
    "AGAPE_BTC_PERP":  ExitConfig(1.5, 1.25, 0.0, 3.0, 5.0, 24, True, 1.5, 0.3),
    "AGAPE_ETH_PERP":  ExitConfig(1.5, 1.25, 0.0, 3.0, 5.0, 24, True, 1.5, 0.3),
    "AGAPE_DOGE_PERP": ExitConfig(0.2, 0.1,  0.0, 0.75, 5.0, 24, True, 1.5, 0.3),
    "AGAPE_SHIB_PERP": ExitConfig(0.15, 0.05, 0.0, 0.5, 5.0, 24, True, 1.5, 0.3),
}


def _grid(level: str) -> dict[str, list]:
    if level == "coarse":
        return {
            "activation": [0.3, 0.5, 0.8, 1.2],
            "trail":      [0.15, 0.3, 0.5, 0.8],
            "profit_tgt": [0.0, 0.8, 1.5, 2.5],
            "max_loss":   [0.5, 1.0, 2.0, 3.0],
            "max_hold":   [4, 8, 16],
            "sar":        [(False, 0.0, 0.0), (True, 1.5, 0.3)],
        }
    if level == "fine":
        return {
            "activation": [0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0, 1.2, 1.5],
            "trail":      [0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8],
            "profit_tgt": [0.0, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0],
            "max_loss":   [0.4, 0.6, 0.8, 1.0, 1.5, 2.0, 2.5, 3.0],
            "max_hold":   [3, 4, 6, 8, 12, 16, 24],
            "sar":        [(False, 0.0, 0.0), (True, 1.0, 0.3), (True, 1.5, 0.3), (True, 2.0, 0.3)],
        }
    raise ValueError(f"unknown grid level: {level}")


# ---------- data loading ----------

def _ensure_aware(ts):
    if ts is None:
        return None
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


def load_entries(conn, table: str) -> list[dict]:
    """Fetch historical entries, excluding admin RESETs (those distort the
    P&L picture and didn't follow normal exit logic)."""
    sql = f"""
        SELECT position_id, side, quantity, entry_price, open_time, close_time, close_reason, realized_pnl
        FROM {table}_positions
        WHERE close_time IS NOT NULL
          AND open_time IS NOT NULL
          AND quantity IS NOT NULL
          AND entry_price > 0
          AND close_reason IS NOT NULL
          AND close_reason NOT LIKE '%%RESET%%'
          AND close_reason NOT LIKE '%%MANUAL%%'
        ORDER BY open_time
    """
    cur = conn.cursor()
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = []
    for r in cur.fetchall():
        d = dict(zip(cols, r))
        d["open_time"] = _ensure_aware(d["open_time"])
        d["close_time"] = _ensure_aware(d["close_time"])
        rows.append(d)
    cur.close()
    return rows


def load_price_stream(conn, table: str, price_col: str) -> tuple[list[float], list[float]]:
    """Fetch every recorded scan with a non-null price.
    Returns (timestamps_epoch_seconds, prices) — parallel arrays sorted by ts."""
    sql = f"""
        SELECT timestamp, {price_col} AS price
        FROM {table}_scan_activity
        WHERE {price_col} IS NOT NULL AND {price_col} > 0
        ORDER BY timestamp
    """
    cur = conn.cursor()
    cur.execute(sql)
    ts_list, px_list = [], []
    for ts, px in cur.fetchall():
        ts = _ensure_aware(ts)
        ts_list.append(ts.timestamp())
        px_list.append(float(px))
    cur.close()
    # Also pull from equity_snapshots — denser for some bots
    sql2 = f"""
        SELECT timestamp, {price_col} AS price
        FROM {table}_equity_snapshots
        WHERE {price_col} IS NOT NULL AND {price_col} > 0
        ORDER BY timestamp
    """
    cur = conn.cursor()
    try:
        cur.execute(sql2)
        for ts, px in cur.fetchall():
            ts = _ensure_aware(ts)
            ts_list.append(ts.timestamp())
            px_list.append(float(px))
    except Exception as e:
        logger.warning(f"{table} equity_snapshots fetch failed (continuing): {e}")
    finally:
        cur.close()
    # Re-sort merged
    pairs = sorted(zip(ts_list, px_list), key=lambda p: p[0])
    # Deduplicate identical timestamps
    out_ts, out_px = [], []
    last_t = None
    for t, p in pairs:
        if t != last_t:
            out_ts.append(t)
            out_px.append(p)
            last_t = t
    return out_ts, out_px


# ---------- simulation ----------

def simulate(entry: dict, ts_arr: list[float], px_arr: list[float], cfg: ExitConfig) -> tuple[float, str, float, float, float]:
    """Replay one entry forward and return (close_price, reason, hold_hours, mfe_pct, mae_pct).

    Mirrors trading/agape_*_perp/trader.py:_manage_no_loss_trailing exit
    ordering. HWM is updated AFTER exit checks each tick (matches
    production's _update_hwm running after _manage_no_loss_trailing).
    """
    open_ts = entry["open_time"].timestamp()
    entry_price = float(entry["entry_price"])
    is_long = entry["side"] == "long"
    direction = 1.0 if is_long else -1.0

    deadline_ts = open_ts + cfg.max_hold_hours * 3600.0

    start = bisect.bisect_left(ts_arr, open_ts)
    if start >= len(ts_arr):
        return (entry_price, "NO_FORWARD_DATA", 0.0, 0.0, 0.0)

    hwm = entry_price
    trailing_active = False
    current_stop: float | None = None
    mfe_pct_max = 0.0
    mae_pct_max = 0.0
    last_price = entry_price

    n = len(ts_arr)
    i = start
    while i < n:
        ts = ts_arr[i]
        if ts > deadline_ts:
            return (last_price, "MAX_HOLD_TIME", cfg.max_hold_hours, mfe_pct_max, mae_pct_max)
        price = px_arr[i]
        last_price = price
        i += 1

        profit_pct = ((price - entry_price) / entry_price * 100.0) * direction
        if profit_pct > mfe_pct_max:
            mfe_pct_max = profit_pct
        if profit_pct < mae_pct_max:
            mae_pct_max = profit_pct
        max_profit_pct = ((hwm - entry_price) / entry_price * 100.0) * direction

        # 1. SAR — fires only on losses with low realised MFE
        if cfg.sar_enabled and -profit_pct >= cfg.sar_trigger_pct and max_profit_pct < cfg.sar_mfe_threshold_pct:
            close_price = entry_price * (1.0 - cfg.sar_trigger_pct / 100.0) if is_long else entry_price * (1.0 + cfg.sar_trigger_pct / 100.0)
            return (close_price, f"SAR_{cfg.sar_trigger_pct}pct", (ts - open_ts) / 3600.0, mfe_pct_max, mae_pct_max)

        # 2. MAX LOSS
        if -profit_pct >= cfg.max_loss_pct:
            return (price, f"MAX_LOSS_{cfg.max_loss_pct}pct", (ts - open_ts) / 3600.0, mfe_pct_max, mae_pct_max)

        # 3. EMERGENCY STOP (kept for parity; usually wider than MAX_LOSS)
        if -profit_pct >= cfg.emergency_stop_pct:
            return (price, "EMERGENCY_STOP", (ts - open_ts) / 3600.0, mfe_pct_max, mae_pct_max)

        # 4. Trailing stop hit
        if trailing_active and current_stop is not None:
            hit = (is_long and price <= current_stop) or ((not is_long) and price >= current_stop)
            if hit:
                return (current_stop, "TRAIL_STOP", (ts - open_ts) / 3600.0, mfe_pct_max, mae_pct_max)

        # 5. Hard profit target
        if cfg.profit_target_pct > 0.0 and profit_pct >= cfg.profit_target_pct:
            return (price, f"PROFIT_TARGET_{cfg.profit_target_pct}pct", (ts - open_ts) / 3600.0, mfe_pct_max, mae_pct_max)

        # 6. Activate trail
        if (not trailing_active) and max_profit_pct >= cfg.activation_pct:
            trail_dist = entry_price * (cfg.trail_pct / 100.0)
            initial_stop = max(entry_price, hwm - trail_dist) if is_long else min(entry_price, hwm + trail_dist)
            trailing_active = True
            current_stop = initial_stop

        # 7. Update trail
        if trailing_active:
            trail_dist = entry_price * (cfg.trail_pct / 100.0)
            if is_long:
                new_stop = hwm - trail_dist
                if (current_stop is None or new_stop > current_stop) and new_stop >= entry_price:
                    current_stop = new_stop
            else:
                new_stop = hwm + trail_dist
                if (current_stop is not None and new_stop < current_stop) and new_stop <= entry_price:
                    current_stop = new_stop

        # Update hwm AFTER exit checks (matches production cadence)
        if (is_long and price > hwm) or ((not is_long) and price < hwm):
            hwm = price

    # Stream ended without an exit — treat as still open (skip in aggregate)
    return (last_price, "STREAM_END", (ts_arr[-1] - open_ts) / 3600.0, mfe_pct_max, mae_pct_max)


def evaluate(entries: list[dict], ts_arr: list[float], px_arr: list[float], cfg: ExitConfig) -> dict:
    total_pnl = 0.0
    sum_win = 0.0
    sum_loss = 0.0
    wins = losses = 0
    reasons: dict[str, int] = {}
    skipped = 0
    hold_hours_sum = 0.0
    counted = 0

    for e in entries:
        cp, reason, hold_h, _, _ = simulate(e, ts_arr, px_arr, cfg)
        if reason in ("NO_FORWARD_DATA", "STREAM_END"):
            skipped += 1
            continue
        qty = float(e["quantity"])
        d = 1.0 if e["side"] == "long" else -1.0
        pnl = (cp - float(e["entry_price"])) * qty * d
        total_pnl += pnl
        if pnl > 0:
            wins += 1
            sum_win += pnl
        else:
            losses += 1
            sum_loss += abs(pnl)
        # Bucket reasons (strip pct suffix for readability)
        bucket = reason.split("_")[0] if "_" in reason else reason
        if bucket == "MAX":
            bucket = "MAX_LOSS" if reason.startswith("MAX_LOSS") else "MAX_HOLD"
        if bucket == "PROFIT":
            bucket = "PROFIT_TARGET"
        if bucket == "TRAIL":
            bucket = "TRAIL_STOP"
        reasons[bucket] = reasons.get(bucket, 0) + 1
        hold_hours_sum += hold_h
        counted += 1

    n = wins + losses
    win_rate = (wins / n * 100.0) if n else 0.0
    pf = (sum_win / sum_loss) if sum_loss > 0 else (float("inf") if sum_win > 0 else 0.0)
    pf_capped = round(pf, 2) if pf != float("inf") else 999.0
    return {
        "total_pnl": round(total_pnl, 2),
        "trades_evaluated": counted,
        "skipped_no_data": skipped,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": round(win_rate, 1),
        "avg_win": round(sum_win / wins, 2) if wins else 0.0,
        "avg_loss": round(sum_loss / losses, 2) if losses else 0.0,
        "profit_factor": pf_capped,
        "avg_hold_hours": round(hold_hours_sum / counted, 2) if counted else 0.0,
        "reasons": reasons,
    }


# ---------- grid search ----------

def search(bot: dict, level: str = "coarse") -> dict:
    from database_adapter import get_connection
    t0 = time.time()
    conn = get_connection()
    try:
        entries = load_entries(conn, bot["table"])
        ts_arr, px_arr = load_price_stream(conn, bot["table"], bot["price_col"])
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if not entries:
        return {"bot": bot["name"], "error": "no entries"}
    if not ts_arr:
        return {"bot": bot["name"], "error": "no price stream"}

    g = _grid(level)
    results: list[dict] = []
    for a, t, p, m, h, (sar_en, sar_tg, sar_mfe) in itertools.product(
        g["activation"], g["trail"], g["profit_tgt"], g["max_loss"], g["max_hold"], g["sar"]
    ):
        if t >= a:                 # trail must be tighter than activation
            continue
        if m >= 5.0:               # max_loss must be tighter than emergency stop
            continue
        cfg = ExitConfig(
            activation_pct=a, trail_pct=t, profit_target_pct=p,
            max_loss_pct=m, emergency_stop_pct=5.0, max_hold_hours=h,
            sar_enabled=sar_en, sar_trigger_pct=sar_tg, sar_mfe_threshold_pct=sar_mfe,
        )
        metrics = evaluate(entries, ts_arr, px_arr, cfg)
        if metrics["trades_evaluated"] == 0:
            continue
        results.append({"config": asdict(cfg), "metrics": metrics})

    # Score: total_pnl primary, profit_factor tiebreak (penalize unbounded PF)
    def score(r):
        pf = r["metrics"]["profit_factor"]
        return (r["metrics"]["total_pnl"], min(pf, 5.0))
    results.sort(key=score, reverse=True)

    # Baseline = current production defaults replayed
    baseline_cfg = CURRENT_DEFAULTS[bot["name"]]
    baseline_metrics = evaluate(entries, ts_arr, px_arr, baseline_cfg)
    baseline_pnl = baseline_metrics["total_pnl"]

    elapsed = round(time.time() - t0, 1)
    return {
        "bot": bot["name"],
        "ticker": bot["ticker"],
        "n_entries_used": sum(1 for e in entries if e),
        "n_price_ticks": len(ts_arr),
        "price_window_start": datetime.fromtimestamp(ts_arr[0], tz=timezone.utc).isoformat(),
        "price_window_end": datetime.fromtimestamp(ts_arr[-1], tz=timezone.utc).isoformat(),
        "n_configs_tested": len(results),
        "baseline_current_config": {"config": asdict(baseline_cfg), "metrics": baseline_metrics},
        "top_10": results[:10],
        "elapsed_seconds": elapsed,
    }


def search_all(level: str = "coarse", bot_filter: str | None = None) -> dict:
    selected = BOTS if not bot_filter else [b for b in BOTS if b["ticker"].upper() == bot_filter.upper() or b["name"] == bot_filter.upper()]
    out = {"started_at": datetime.now(timezone.utc).isoformat(), "grid": level, "bots": []}
    for bot in selected:
        try:
            out["bots"].append(search(bot, level=level))
        except Exception as e:
            out["bots"].append({"bot": bot["name"], "error": str(e)})
    out["finished_at"] = datetime.now(timezone.utc).isoformat()
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Perp exit-rule optimizer")
    ap.add_argument("--bot", default=None, help="Single ticker (XRP/BTC/ETH/DOGE/SHIB), default all")
    ap.add_argument("--grid", default="coarse", choices=["coarse", "fine"])
    ap.add_argument("--json", default=None, help="Write full result JSON to this path")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    result = search_all(level=args.grid, bot_filter=args.bot)

    if args.json:
        with open(args.json, "w") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"Wrote {args.json}")
    else:
        print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
