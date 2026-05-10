"""Walk-forward Train/Validation/OOS split + GO/NO-GO evaluator.

Per spec §7.4 and §11:

Splits:
  Train      : 2023-01-03 → 2023-12-29
  Validation : 2024-01-02 → 2024-12-31
  OOS        : 2025-01-02 → 2025-12-05  (frozen until final eval)

GO criteria per qualifying bin:
  1. n_insample (train+val) >= 30, n_oos >= 15
  2. mean_pnl >= +$5 after costs (in-sample)
  3. OOS mean_pnl same sign, magnitude within ±50% of in-sample
  4. Per-trade Sharpe >= 0.3 in-sample

Aggregate GO: at least 1 qualifying bin AND total qualifying trades >= 100.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from backtest.touch_pin.engine import TradeRow
from backtest.touch_pin.binning import bin_trades, BinSummary


@dataclass(frozen=True)
class GoNoGoResult:
    go: bool
    n_qualifying_bins: int
    n_total_trades_in_qualifying_bins: int
    qualifying_bins: List[BinSummary]
    summary: str


def split_trades(trades: List[TradeRow]) -> Tuple[List[TradeRow], List[TradeRow], List[TradeRow]]:
    """Split trade rows into (train=2023, validation=2024, oos=2025)."""
    train, val, oos = [], [], []
    for t in trades:
        if t.trade_date.year == 2023:
            train.append(t)
        elif t.trade_date.year == 2024:
            val.append(t)
        elif t.trade_date.year == 2025:
            oos.append(t)
    return train, val, oos


def evaluate_go_no_go(insample: List[TradeRow], oos: List[TradeRow]) -> GoNoGoResult:
    """Pick qualifying bins from insample, validate them on oos."""
    in_bins = bin_trades(insample)
    oos_bins_lookup = {_bin_key(b): b for b in bin_trades(oos)}

    qualifying: List[BinSummary] = []
    notes: List[str] = []
    for b in in_bins:
        if b.n < 30:
            continue
        if b.mean_pnl < 5.0:
            continue
        if b.sharpe_per_trade < 0.3:
            continue
        key = _bin_key(b)
        oos_b = oos_bins_lookup.get(key)
        if oos_b is None or oos_b.n < 15:
            notes.append(
                f"bin {key} insufficient OOS samples (oos_n={oos_b.n if oos_b else 0})"
            )
            continue
        if (oos_b.mean_pnl < 0) != (b.mean_pnl < 0):
            notes.append(
                f"bin {key} OOS sign flip (in=${b.mean_pnl:.2f} oos=${oos_b.mean_pnl:.2f})"
            )
            continue
        ratio_lo = 0.5 * abs(b.mean_pnl)
        ratio_hi = 1.5 * abs(b.mean_pnl)
        if abs(oos_b.mean_pnl) < ratio_lo or abs(oos_b.mean_pnl) > ratio_hi:
            notes.append(
                f"bin {key} OOS magnitude outside ±50% (in=${b.mean_pnl:.2f} oos=${oos_b.mean_pnl:.2f})"
            )
            continue
        qualifying.append(b)

    n_total = sum(b.n for b in qualifying)
    go = bool(qualifying) and n_total >= 100

    summary_lines = [f"Qualifying bins: {len(qualifying)}, total in-sample trades: {n_total}"]
    if go:
        summary_lines.append("VERDICT: GO")
    else:
        summary_lines.append("VERDICT: NO-GO")
        if notes:
            summary_lines.append("Disqualified bins (top 10):")
            summary_lines.extend(f"  - {n}" for n in notes[:10])

    return GoNoGoResult(
        go=go,
        n_qualifying_bins=len(qualifying),
        n_total_trades_in_qualifying_bins=n_total,
        qualifying_bins=qualifying,
        summary="\n".join(summary_lines),
    )


def _bin_key(b: BinSummary):
    return (b.side, b.magnet_imb_bucket, b.vix_bucket, b.distance_bucket, b.regime_label)
