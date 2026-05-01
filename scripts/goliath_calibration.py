#!/usr/bin/env python3
"""GOLIATH Phase 1.5 calibration orchestrator.

Fetches 90d data via fetch_all_universe(), runs all 4 metric calibrations,
writes a markdown report. Partial-result tolerant: a CALIB-BLOCK on any
single metric does not fail the run; that metric's section in the report
shows its blocked state and the others still produce normal output.

Usage:
    python scripts/goliath_calibration.py
    python scripts/goliath_calibration.py --days 90 --output docs/goliath/goliath-calibration-results.md
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading.goliath.models import GoliathConfig  # noqa: E402
from trading.goliath.calibration import (  # noqa: E402
    LETF_PAIRS,
    LOOKBACK_DAYS,
    fetch_all_universe,
)
from trading.goliath.calibration import (  # noqa: E402
    tracking_error,
    vol_drag,
    vol_window,
    wall_concentration,
)


def _render_summary(results: dict) -> str:
    lines = ["## Summary", "", "| Metric | Tag | Recommended |", "|---|---|---|"]
    for name, r in results.items():
        rec = getattr(r, "recommended_value", None)
        rec_s = "—" if rec is None else f"`{rec}`"
        lines.append(f"| {name} | `{r.tag}` | {rec_s} |")
    return "\n".join(lines) + "\n\n"


def _render_wall(r) -> str:
    return (
        "## 1. Wall concentration (sanity check)\n\n"
        f"**Tag:** `{r.tag}` &nbsp; **Spec default:** `{r.spec_default}x`\n\n"
        f"- Universe count: {r.universe_count}\n"
        f"- Universe min / median / max: "
        f"{r.universe_min} / {r.universe_median} / {r.universe_max}\n"
        f"- Outliers (>3x deviation from median): {r.outliers or 'none'}\n"
        f"- Per-underlying: {dict(r.per_underlying)}\n\n"
        f"**Notes:** {r.notes}\n\n"
    )


def _render_te(r) -> str:
    rec = "—" if r.recommended_value is None else f"`{r.recommended_value:.4f}`"
    return (
        "## 2. Tracking error fudge factor\n\n"
        f"**Tag:** `{r.tag}` &nbsp; **Spec default:** `{r.spec_default}` "
        f"&nbsp; **Recommended:** {rec}\n\n"
        f"- Universe count: {r.universe_count}\n"
        f"- Universe median ratio: {r.universe_median_ratio}\n"
        f"- Outliers (>1.5x universe median): {r.outliers or 'none'}\n"
        f"- Per-pair: {r.per_pair}\n\n"
        f"**Notes:** {r.notes}\n\n"
    )


def _render_drag(r) -> str:
    rec = "—" if r.recommended_value is None else f"`{r.recommended_value:.4f}`"
    return (
        "## 3. Volatility drag coefficient\n\n"
        f"**Tag:** `{r.tag}` &nbsp; **Spec default:** `{r.spec_default}` "
        f"&nbsp; **Recommended:** {rec}\n\n"
        f"- Universe count: {r.universe_count}\n"
        f"- Universe mean ratio: {r.universe_mean_ratio}\n"
        f"- Universe median ratio: {r.universe_median_ratio}\n"
        f"- Universe SE: {r.universe_se}\n"
        f"- Outliers (>25% from universe mean): {r.outliers or 'none'}\n"
        f"- Per-pair: {r.per_pair}\n\n"
        f"**Notes:** {r.notes}\n\n"
    )


def _render_window(r) -> str:
    rec = "—" if r.recommended_value is None else f"`{r.recommended_value}d`"
    return (
        "## 4. Realized volatility window\n\n"
        f"**Tag:** `{r.tag}` &nbsp; **Spec default:** `{r.spec_default}d` "
        f"&nbsp; **Recommended:** {rec}\n\n"
        f"- Universe count: {r.universe_count}\n"
        f"- Pair-level winner counts: {dict(r.universe_winners)}\n"
        f"- Universe majority winner: {r.universe_winner}\n"
        f"- Per-underlying override candidates: "
        f"{r.per_underlying_overrides or 'none'}\n"
        f"- Per-pair: {r.per_pair}\n\n"
        f"**Notes:** {r.notes}\n\n"
    )


def _safe_calibrate(name: str, fn, data, config) -> object:
    """Run one metric's calibrate() with full exception capture so a
    crash in any single metric doesn't abort the orchestrator."""
    try:
        return fn(data, config)
    except Exception as exc:  # noqa: BLE001
        # Synthesize a CALIB-BLOCK-shaped result so the report still renders.
        # We use a tiny anonymous result-like object; downstream renderers
        # only access attributes that exist on every metric's result type.
        from types import SimpleNamespace
        return SimpleNamespace(
            tag="CALIB-BLOCK",
            spec_default="?",
            universe_count=0,
            universe_min=None, universe_median=None, universe_max=None,
            universe_median_ratio=None, universe_mean_ratio=None, universe_se=None,
            universe_winner=None, universe_winners={},
            per_underlying={}, per_pair={},
            per_underlying_overrides=[], outliers=[],
            recommended_value=None,
            notes=f"orchestrator caught exception during {name}.calibrate(): {exc!r}",
        )


def _read_existing_csv_pairs(output_path: str) -> tuple[list[dict], set[str]]:
    """Read existing per-week CSV (if any) and return (rows, pairs_present).

    Used for partial-run resumption: when the script re-runs with the same
    --per-week-csv path, pairs already represented in the file are skipped
    and their rows are preserved verbatim. New pairs are appended.

    Returns ([], set()) when the file doesn't exist or is empty.
    """
    p = Path(output_path)
    if not p.exists():
        return [], set()
    try:
        with open(p, newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except Exception as exc:  # noqa: BLE001
        print(f"  [per-week-csv] could not read existing {output_path}: {exc!r}; "
              "treating as empty (full re-run)")
        return [], set()
    pairs_present = {r["pair"] for r in rows if r.get("pair")}
    return rows, pairs_present


def _emit_per_week_csv(
    price_history: dict,
    leverage: float,
    vol_window_days: int,
    output_path: str,
) -> int:
    """Per-week per-pair diagnostic CSV. Read-only re-derivation of the
    weekly inputs that tracking_error / vol_drag aggregate over -- writes
    the underlying numbers so a reviewer can see whether outliers are
    chronic (every week) or episodic (1-2 weeks dominating the stat).

    Does NOT mutate any metric module result; pure additional output.
    Math intentionally mirrors trading.goliath.calibration.tracking_error
    and trading.goliath.calibration.vol_drag so per-week numbers reconcile
    to the per-pair summaries already in the markdown report.

    Partial-run resumption: if ``output_path`` already exists with rows for
    some pairs, those pairs are skipped and their existing rows are
    preserved. New pairs are appended. This makes re-runs safe after a
    yfinance rate-limit incident — no need to refetch tickers we already
    have.
    """
    import numpy as np  # local import keeps the module-level imports lean

    existing_rows, pairs_already_present = _read_existing_csv_pairs(output_path)
    if pairs_already_present:
        print(
            f"  [per-week-csv] resuming: {len(pairs_already_present)} pair(s) "
            f"already in {output_path} ({sorted(pairs_already_present)}); "
            "skipping their recomputation"
        )

    rows: list[dict] = list(existing_rows)
    new_row_count = 0
    t_weekly = 1.0 / 52.0
    fudge = 0.1  # spec default; matches tracking_error.py
    te_geometric = math.sqrt(2.0 / 3.0)

    for letf, underlying in LETF_PAIRS.items():
        if letf in pairs_already_present:
            continue
        u_df = price_history.get(underlying)
        l_df = price_history.get(letf)
        if u_df is None or u_df.empty or l_df is None or l_df.empty:
            continue
        if "Close" not in u_df.columns or "Close" not in l_df.columns:
            continue

        common = u_df.index.intersection(l_df.index)
        if len(common) < vol_window_days + 14:
            continue

        u = u_df["Close"].loc[common].sort_index()
        l = l_df["Close"].loc[common].sort_index()
        u_log = np.log(u / u.shift(1)).dropna()

        u_weekly = u.resample("W-FRI").last().dropna()
        l_weekly = l.resample("W-FRI").last().dropna()
        common_w = u_weekly.index.intersection(l_weekly.index)
        if len(common_w) < 5:
            continue

        u_returns = u_weekly.loc[common_w].pct_change().dropna()
        l_returns = l_weekly.loc[common_w].pct_change().dropna()
        common_r = u_returns.index.intersection(l_returns.index)
        if len(common_r) < 4:
            continue
        u_returns = u_returns.loc[common_r]
        l_returns = l_returns.loc[common_r]

        for week_end in common_r:
            u_ret = float(u_returns.loc[week_end])
            l_ret = float(l_returns.loc[week_end])
            observed_drag = l_ret - leverage * u_ret

            log_window = u_log.loc[:week_end].tail(vol_window_days)
            if len(log_window) < vol_window_days:
                sigma = None
                predicted_drag = None
                predicted_te = None
                drag_residual = None
            else:
                sigma = float(log_window.std() * math.sqrt(252))
                predicted_drag = -0.5 * leverage * (leverage - 1) * sigma ** 2 * t_weekly
                predicted_te = leverage * sigma * math.sqrt(t_weekly) * te_geometric * fudge
                drag_residual = observed_drag - predicted_drag

            rows.append({
                "pair": letf,
                "underlying": underlying,
                "week_ending": week_end.strftime("%Y-%m-%d"),
                "underlying_close": float(u_weekly.loc[week_end]),
                "letf_close": float(l_weekly.loc[week_end]),
                "underlying_return": u_ret,
                "letf_return": l_ret,
                "observed_drag": observed_drag,
                "predicted_drag": predicted_drag,
                "drag_residual": drag_residual,
                "trailing_sigma_annualized": sigma,
                "predicted_te": predicted_te,
                "observed_te_proxy": abs(observed_drag),
            })
            new_row_count += 1

    if not rows:
        print(f"  [per-week-csv] no rows produced; skipping {output_path}")
        return 0

    # CSV column order: prefer the schema of the *first* row, which may
    # be from existing rows (resume case) or newly computed rows.
    fieldnames = list(rows[0].keys())
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    if new_row_count == len(rows):
        print(f"  [per-week-csv] wrote {len(rows)} rows to {out}")
    else:
        preserved = len(rows) - new_row_count
        print(
            f"  [per-week-csv] wrote {len(rows)} rows to {out} "
            f"({new_row_count} new + {preserved} preserved from existing CSV)"
        )
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--output",
        default="docs/goliath/goliath-calibration-results.md",
        help="Markdown output path",
    )
    parser.add_argument("--days", type=int, default=LOOKBACK_DAYS)
    parser.add_argument(
        "--per-week-csv",
        default=None,
        help=(
            "Optional: write per-week per-pair diagnostic CSV to this path. "
            "Read-only addition; does not change the markdown report content. "
            "Use to investigate whether per-pair outliers are chronic or episodic."
        ),
    )
    args = parser.parse_args()

    config = GoliathConfig(
        instance_name="GOLIATH-CALIBRATION",
        letf_ticker="N/A",
        underlying_ticker="N/A",
    )

    print(f"Fetching {args.days}d data for universe ...")
    gex_history, price_history = fetch_all_universe(days=args.days)
    n_gex = sum(1 for df in gex_history.values() if not df.empty)
    n_price = sum(1 for df in price_history.values() if not df.empty)
    print(f"  gex_history:   {n_gex}/{len(gex_history)} non-empty")
    print(f"  price_history: {n_price}/{len(price_history)} non-empty")

    print("Running calibrations ...")
    results = {
        "wall_concentration": _safe_calibrate(
            "wall_concentration", wall_concentration.calibrate, gex_history, config
        ),
        "tracking_error": _safe_calibrate(
            "tracking_error", tracking_error.calibrate, price_history, config
        ),
        "vol_drag": _safe_calibrate(
            "vol_drag", vol_drag.calibrate, price_history, config
        ),
        "vol_window": _safe_calibrate(
            "vol_window", vol_window.calibrate, price_history, config
        ),
    }
    for name, r in results.items():
        rec = getattr(r, "recommended_value", None)
        print(f"  {name:20s}  {r.tag}  recommended={rec}")

    universe = sorted(set(LETF_PAIRS) | set(LETF_PAIRS.values()))
    now = datetime.now(timezone.utc).isoformat()
    body = (
        "# GOLIATH Phase 1.5 calibration results\n\n"
        f"- Generated: {now}\n"
        f"- Lookback: {args.days} days\n"
        f"- Universe ({len(universe)}): {universe}\n"
        f"- Data availability: {n_gex}/{len(gex_history)} GEX histories, "
        f"{n_price}/{len(price_history)} price histories\n\n"
        + _render_summary(results)
        + _render_wall(results["wall_concentration"])
        + _render_te(results["tracking_error"])
        + _render_drag(results["vol_drag"])
        + _render_window(results["vol_window"])
        + "\n## Sign-off\n\n"
        "_Awaiting Leron review. Spec defaults remain in effect until any "
        "CALIB-ADJUST recommendations above are explicitly approved._\n"
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(body)
    print(f"\nReport written: {out_path}  ({len(body.splitlines())} lines)")

    if args.per_week_csv:
        _emit_per_week_csv(
            price_history=price_history,
            leverage=float(config.leverage),
            vol_window_days=int(config.realized_vol_window_days),
            output_path=args.per_week_csv,
        )

    return 0  # exit 0 even on partial CALIB-BLOCK per Step 8 contract


if __name__ == "__main__":
    sys.exit(main())
