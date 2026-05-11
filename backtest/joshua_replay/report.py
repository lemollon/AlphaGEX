"""Replay report — markdown summary per-setup + overall."""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import List

from backtest.joshua_replay.engine import TradeOutcome


def build_report(trades: List[TradeOutcome], *, start: dt.date, end: dt.date) -> str:
    lines = [
        "# JOSHUA Replay Report",
        "",
        f"**Window**: {start} -> {end}",
        f"**Total trades**: {len(trades)}",
        "",
    ]
    if not trades:
        lines.append("**No trades fired.**")
        return "\n".join(lines)

    overall_wr = _wr(trades)
    overall_ev = _ev_per_trade(trades)
    lines.extend([
        f"**Overall WR**: {overall_wr:.1f}%",
        f"**Overall EV/trade**: ${overall_ev:.2f}",
        "",
        "## Per-setup breakdown",
        "",
        "| Setup | Trades | WR | PT% | SL% | TIME_STOP% | EV/trade ($) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    by_setup = defaultdict(list)
    for t in trades:
        by_setup[t.setup].append(t)
    for setup in sorted(by_setup):
        ts = by_setup[setup]
        wr = _wr(ts)
        ev = _ev_per_trade(ts)
        pt = 100.0 * sum(1 for t in ts if t.exit_reason == "PT") / len(ts)
        sl = 100.0 * sum(1 for t in ts if t.exit_reason == "SL") / len(ts)
        time_stop = 100.0 * sum(1 for t in ts if t.exit_reason in ("EOD", "TIME_STOP")) / len(ts)
        lines.append(
            f"| {setup} | {len(ts)} | {wr:.1f}% | {pt:.1f}% | {sl:.1f}% | {time_stop:.1f}% | {ev:.2f} |"
        )
    lines.append("")
    lines.append("## GO/NO-GO check")
    lines.append("")
    bar_n = len(trades) >= 30
    bar_wr = overall_wr >= 55.0
    bar_ev = overall_ev >= 3.0
    bar_diversification = len(by_setup) >= 2
    lines.append(f"- n >= 30 trades: {'PASS' if bar_n else 'FAIL'} ({len(trades)})")
    lines.append(f"- WR >= 55%: {'PASS' if bar_wr else 'FAIL'} ({overall_wr:.1f}%)")
    lines.append(f"- EV >= +$3/trade: {'PASS' if bar_ev else 'FAIL'} (${overall_ev:.2f})")
    lines.append(f"- 2+ setups firing: {'PASS' if bar_diversification else 'FAIL'} ({len(by_setup)})")
    verdict = "GO" if all([bar_n, bar_wr, bar_ev, bar_diversification]) else "NO-GO"
    lines.append("")
    lines.append(f"**Verdict: {verdict}**")
    return "\n".join(lines)


def _wr(trades: List[TradeOutcome]) -> float:
    if not trades:
        return 0.0
    wins = sum(1 for t in trades if t.realized_pct > 0)
    return 100.0 * wins / len(trades)


def _ev_per_trade(trades: List[TradeOutcome]) -> float:
    if not trades:
        return 0.0
    pnls = [(t.realized_pct / 100.0) * t.debit * 100.0 for t in trades]
    return sum(pnls) / len(pnls)
