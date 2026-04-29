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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--output",
        default="docs/goliath/goliath-calibration-results.md",
        help="Markdown output path",
    )
    parser.add_argument("--days", type=int, default=LOOKBACK_DAYS)
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
    return 0  # exit 0 even on partial CALIB-BLOCK per Step 8 contract


if __name__ == "__main__":
    sys.exit(main())
