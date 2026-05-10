"""Train/Validation/OOS split + GO/NO-GO eval per spec §8.3."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from backtest.skew_signal.engine import TradeRow


@dataclass(frozen=True)
class GoNoGoResult:
    go: bool
    n_total: int
    win_rate: float
    rr_ratio: float
    ev_per_trade: float
    timestop_pct: float
    summary: str


def split_trades(trades: List[TradeRow]) -> Tuple[List[TradeRow], List[TradeRow], List[TradeRow]]:
    train, val, oos = [], [], []
    for t in trades:
        if t.trade_date.year == 2023: train.append(t)
        elif t.trade_date.year == 2024: val.append(t)
        elif t.trade_date.year == 2025: oos.append(t)
    return train, val, oos


def evaluate_go_no_go(insample: List[TradeRow], oos: List[TradeRow]) -> GoNoGoResult:
    n = len(insample)
    if n == 0:
        return GoNoGoResult(go=False, n_total=0, win_rate=0.0, rr_ratio=0.0,
                            ev_per_trade=0.0, timestop_pct=0.0,
                            summary="No in-sample trades. NO-GO.")
    pnls = [t.pnl_net for t in insample]
    winners = [p for p in pnls if p > 0]
    losers = [p for p in pnls if p <= 0]
    wr = len(winners) / n
    avg_win = sum(winners) / len(winners) if winners else 0.0
    avg_loss = abs(sum(losers) / len(losers)) if losers else 1.0
    rr = avg_win / avg_loss if avg_loss > 0 else 0.0
    ev = sum(pnls) / n
    timestop_pct = sum(1 for t in insample if t.exit_reason == "EOD") / n

    insample_pass = (n >= 150 and wr >= 0.66 and rr >= 1.5 and ev >= 5.0)
    oos_n = len(oos)
    oos_wr = sum(1 for t in oos if t.pnl_net > 0) / oos_n if oos_n else 0.0
    oos_pass = oos_n >= 30 and abs(oos_wr - wr) <= 0.05

    go = insample_pass and oos_pass

    lines = [
        f"In-sample: n={n}, WR={wr:.1%}, RR={rr:.2f}, EV=${ev:.2f}/trade, time-stop={timestop_pct:.1%}",
        f"OOS: n={oos_n}, WR={oos_wr:.1%}",
        f"VERDICT: {'GO' if go else 'NO-GO'}",
    ]
    if not insample_pass:
        if n < 150: lines.append(f"  fail: n<150")
        if wr < 0.66: lines.append(f"  fail: WR<66%")
        if rr < 1.5: lines.append(f"  fail: RR<1.5")
        if ev < 5.0: lines.append(f"  fail: EV<+$5")
    if not oos_pass and insample_pass:
        if oos_n < 30: lines.append(f"  fail: OOS n<30")
        if abs(oos_wr - wr) > 0.05: lines.append(f"  fail: OOS WR drift > 5pp")

    return GoNoGoResult(
        go=go, n_total=n, win_rate=wr, rr_ratio=rr, ev_per_trade=ev,
        timestop_pct=timestop_pct, summary="\n".join(lines),
    )
