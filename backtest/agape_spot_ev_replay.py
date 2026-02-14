#!/usr/bin/env python3
"""
AGAPE-SPOT EV Gate Replay Backtester
=====================================

Walk-forward replay of historical trades through three EV gate strategies:

  A) NO GATE      — every LONG signal is taken (baseline)
  B) FLAT $0.50   — choppy markets require EV >= $0.50
  C) EWMA DYNAMIC — choppy markets require EV >= 10% of EWMA magnitude

Data source:
  - agape_spot_positions (closed trades with realized P&L)
  - agape_spot_scan_activity (market conditions at each scan)

If DATABASE_URL is not set, runs in --synthetic mode with realistic
Monte Carlo data so you can validate the logic locally for free.

Usage:
    # Against real DB
    python backtest/agape_spot_ev_replay.py

    # Synthetic mode (no DB needed)
    python backtest/agape_spot_ev_replay.py --synthetic

    # Custom date range
    python backtest/agape_spot_ev_replay.py --days 30

    # Single ticker
    python backtest/agape_spot_ev_replay.py --ticker ETH-USD
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# ── Choppy detection thresholds (mirror signals.py) ──────────────
CHOPPY_FUNDING_REGIMES = {"BALANCED", "MILD_LONG_BIAS", "MILD_SHORT_BIAS"}
CHOPPY_MAX_SQUEEZE_RANK = 2  # LOW=1, ELEVATED=2, HIGH=3
SQUEEZE_RANK = {"LOW": 1, "ELEVATED": 2, "HIGH": 3}

# ── Gate parameters ──────────────────────────────────────────────
FLAT_THRESHOLD = 0.50       # Strategy B: old hardcoded threshold
EWMA_PCT = 0.10             # Strategy C: 10% of EWMA magnitude
EWMA_FLOOR = 0.02           # Strategy C: minimum threshold
EWMA_ALPHA = 0.034          # ln(2)/20 — halflife 20 trades
MIN_TRADES_FOR_EV = 5       # Need 5+ trades to compute EV
COLD_START_WIN_PROB = 0.50  # Cold-start fallback gate
CHOPPY_COLD_WIN_PROB = 0.52 # Choppy cold-start gate


@dataclass
class Trade:
    """A single closed trade from history."""
    timestamp: datetime
    ticker: str
    entry_price: float
    close_price: float
    realized_pnl: float
    quantity: float
    # Market conditions at entry
    funding_regime: str = "UNKNOWN"
    combined_signal: str = "WAIT"
    squeeze_risk: str = "LOW"
    ls_bias: str = "NEUTRAL"
    oracle_win_prob: float = 0.50
    close_reason: str = ""


@dataclass
class RunningStats:
    """Per-ticker running statistics for walk-forward replay."""
    total_trades: int = 0
    wins: int = 0
    sum_win: float = 0.0
    sum_loss: float = 0.0
    count_win: int = 0
    count_loss: int = 0
    # EWMA state
    ema_win: float = 0.0
    ema_loss: float = 0.0

    @property
    def avg_win(self) -> float:
        return self.sum_win / self.count_win if self.count_win else 0.0

    @property
    def avg_loss(self) -> float:
        return self.sum_loss / self.count_loss if self.count_loss else 0.0

    @property
    def ema_magnitude(self) -> float:
        parts = [v for v in (self.ema_win, self.ema_loss) if v > 0]
        return sum(parts) / len(parts) if parts else 0.0

    def has_ev_data(self) -> bool:
        return self.total_trades >= MIN_TRADES_FOR_EV and self.count_win > 0 and self.count_loss > 0

    def compute_ev(self, win_prob: float) -> float:
        """EV = (p × avg_win) - ((1-p) × |avg_loss|)."""
        return (win_prob * self.avg_win) - ((1.0 - win_prob) * abs(self.avg_loss))

    def ewma_threshold(self) -> float:
        """Dynamic EWMA-based choppy threshold."""
        if self.ema_magnitude > 0:
            return max(self.ema_magnitude * EWMA_PCT, EWMA_FLOOR)
        return EWMA_FLOOR

    def update(self, pnl: float):
        """Update running stats after a trade closes."""
        self.total_trades += 1
        mag = abs(pnl)
        if pnl > 0:
            self.wins += 1
            self.count_win += 1
            self.sum_win += pnl
            self.ema_win = mag if self.ema_win == 0.0 else EWMA_ALPHA * mag + (1 - EWMA_ALPHA) * self.ema_win
        else:
            self.count_loss += 1
            self.sum_loss += pnl  # negative
            self.ema_loss = mag if self.ema_loss == 0.0 else EWMA_ALPHA * mag + (1 - EWMA_ALPHA) * self.ema_loss


@dataclass
class StrategyResult:
    """Aggregate results for one strategy."""
    name: str
    trades_taken: int = 0
    trades_blocked: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl: float = 0.0
    gross_wins: float = 0.0
    gross_losses: float = 0.0
    peak_equity: float = 0.0
    max_drawdown: float = 0.0
    equity_curve: List[float] = field(default_factory=list)
    # Per-ticker breakdown
    ticker_pnl: Dict[str, float] = field(default_factory=dict)
    ticker_trades: Dict[str, int] = field(default_factory=dict)
    # Blocked trade analysis
    blocked_pnl: float = 0.0  # P&L of trades that were blocked
    blocked_wins: int = 0
    blocked_losses: int = 0

    @property
    def win_rate(self) -> float:
        return self.wins / self.trades_taken if self.trades_taken else 0.0

    @property
    def avg_win(self) -> float:
        return self.gross_wins / self.wins if self.wins else 0.0

    @property
    def avg_loss(self) -> float:
        return self.gross_losses / self.losses if self.losses else 0.0

    @property
    def profit_factor(self) -> float:
        return self.gross_wins / abs(self.gross_losses) if self.gross_losses else float("inf")

    @property
    def expectancy(self) -> float:
        return self.total_pnl / self.trades_taken if self.trades_taken else 0.0

    def record(self, pnl: float, ticker: str, blocked: bool = False):
        if blocked:
            self.trades_blocked += 1
            self.blocked_pnl += pnl
            if pnl > 0:
                self.blocked_wins += 1
            else:
                self.blocked_losses += 1
            return

        self.trades_taken += 1
        self.total_pnl += pnl
        self.ticker_pnl[ticker] = self.ticker_pnl.get(ticker, 0.0) + pnl
        self.ticker_trades[ticker] = self.ticker_trades.get(ticker, 0) + 1

        if pnl > 0:
            self.wins += 1
            self.gross_wins += pnl
        else:
            self.losses += 1
            self.gross_losses += pnl  # negative

        # Drawdown tracking
        self.equity_curve.append(self.total_pnl)
        if self.total_pnl > self.peak_equity:
            self.peak_equity = self.total_pnl
        dd = self.peak_equity - self.total_pnl
        if dd > self.max_drawdown:
            self.max_drawdown = dd


def is_choppy(trade: Trade) -> bool:
    """Mirror _detect_choppy_market() logic from signals.py."""
    squeeze = SQUEEZE_RANK.get(trade.squeeze_risk, 3)

    # Primary: RANGE_BOUND with acceptable squeeze
    if trade.combined_signal == "RANGE_BOUND" and squeeze <= CHOPPY_MAX_SQUEEZE_RANK:
        return True

    # Secondary: balanced microstructure regardless of signal
    if (
        trade.funding_regime in CHOPPY_FUNDING_REGIMES
        and squeeze <= CHOPPY_MAX_SQUEEZE_RANK
        and trade.ls_bias in ("NEUTRAL", "BALANCED")
    ):
        return True

    return False


def gate_no_filter(trade: Trade, stats: RunningStats) -> bool:
    """Strategy A: take everything."""
    return True


def gate_flat_050(trade: Trade, stats: RunningStats) -> bool:
    """Strategy B: flat $0.50 choppy gate (old behavior)."""
    if not is_choppy(trade):
        # Non-choppy: normal EV gate (EV > $0)
        if stats.has_ev_data():
            return stats.compute_ev(trade.oracle_win_prob) > 0.0
        return trade.oracle_win_prob >= COLD_START_WIN_PROB

    # Choppy: require EV >= $0.50
    if stats.has_ev_data():
        return stats.compute_ev(trade.oracle_win_prob) >= FLAT_THRESHOLD
    return trade.oracle_win_prob >= CHOPPY_COLD_WIN_PROB


def gate_ewma_dynamic(trade: Trade, stats: RunningStats) -> bool:
    """Strategy C: EWMA dynamic choppy gate (new behavior)."""
    if not is_choppy(trade):
        # Non-choppy: normal EV gate (EV > $0)
        if stats.has_ev_data():
            return stats.compute_ev(trade.oracle_win_prob) > 0.0
        return trade.oracle_win_prob >= COLD_START_WIN_PROB

    # Choppy: require EV >= dynamic threshold
    threshold = stats.ewma_threshold()
    if stats.has_ev_data():
        return stats.compute_ev(trade.oracle_win_prob) >= threshold
    return trade.oracle_win_prob >= CHOPPY_COLD_WIN_PROB


# ── Data Loading ─────────────────────────────────────────────────

def load_trades_from_db(days: int = 60, ticker: Optional[str] = None) -> List[Trade]:
    """Load closed trades from agape_spot_positions + scan conditions."""
    import psycopg2

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL not set. Use --synthetic for local testing.")
        sys.exit(1)

    conn = psycopg2.connect(url)
    cursor = conn.cursor()

    ticker_clause = "AND p.ticker = %s" if ticker else ""
    params: list = [days]
    if ticker:
        params.append(ticker)

    cursor.execute(f"""
        SELECT
            p.open_time,
            p.ticker,
            p.entry_price,
            p.close_price,
            p.realized_pnl,
            p.quantity,
            p.funding_regime_at_entry,
            COALESCE(s.combined_signal, 'WAIT'),
            p.squeeze_risk_at_entry,
            COALESCE(s.ls_bias, 'NEUTRAL'),
            COALESCE(p.oracle_win_probability, 0.50),
            p.close_reason
        FROM agape_spot_positions p
        LEFT JOIN LATERAL (
            SELECT combined_signal, ls_bias
            FROM agape_spot_scan_activity s
            WHERE s.ticker = p.ticker
              AND s.position_id = p.position_id
            LIMIT 1
        ) s ON TRUE
        WHERE p.status IN ('closed', 'expired', 'stopped')
          AND p.account_label != 'paper'
          AND p.open_time > NOW() - INTERVAL '%s days'
          {ticker_clause}
        ORDER BY p.open_time ASC
    """, params)

    trades = []
    for row in cursor.fetchall():
        trades.append(Trade(
            timestamp=row[0],
            ticker=row[1],
            entry_price=float(row[2]),
            close_price=float(row[3]),
            realized_pnl=float(row[4]),
            quantity=float(row[5]),
            funding_regime=row[6] or "UNKNOWN",
            combined_signal=row[7],
            squeeze_risk=row[8] or "LOW",
            ls_bias=row[9],
            oracle_win_prob=float(row[10]),
            close_reason=row[11] or "",
        ))

    cursor.close()
    conn.close()
    return trades


def generate_synthetic_trades(
    n_days: int = 60,
    ticker: Optional[str] = None,
    seed: int = 42,
) -> List[Trade]:
    """Generate realistic synthetic trades for local testing.

    Models the crypto microstructure:
    - Funding rates cluster near zero (BALANCED ~55% of time)
    - Trades during chop have smaller magnitude, lower win rate
    - Trends produce larger wins but are rarer
    - Each coin has different characteristics
    """
    import random
    random.seed(seed)

    TICKERS = [ticker] if ticker else ["ETH-USD", "BTC-USD", "XRP-USD", "SHIB-USD", "DOGE-USD"]

    # Per-coin profiles: (avg_win_trending, avg_loss_trending,
    #                      avg_win_choppy, avg_loss_choppy,
    #                      win_rate_trending, win_rate_choppy,
    #                      trades_per_day_trending, trades_per_day_choppy,
    #                      choppy_pct)
    PROFILES = {
        "ETH-USD":  (5.0, 3.0, 1.5, 2.0, 0.58, 0.48, 8, 5, 0.65),
        "BTC-USD":  (8.0, 5.0, 2.5, 3.0, 0.56, 0.46, 6, 4, 0.70),
        "XRP-USD":  (0.40, 0.30, 0.12, 0.15, 0.55, 0.47, 7, 4, 0.75),
        "SHIB-USD": (0.15, 0.12, 0.04, 0.06, 0.54, 0.45, 6, 3, 0.80),
        "DOGE-USD": (0.50, 0.35, 0.15, 0.20, 0.56, 0.47, 7, 4, 0.70),
    }

    REGIMES = ["BALANCED", "MILD_LONG_BIAS", "MILD_SHORT_BIAS",
               "OVERLEVERAGED_LONG", "OVERLEVERAGED_SHORT",
               "EXTREME_LONG", "EXTREME_SHORT"]

    trades: List[Trade] = []
    now = datetime.utcnow()
    start = now - timedelta(days=n_days)

    for day_offset in range(n_days):
        day = start + timedelta(days=day_offset)

        for tkr in TICKERS:
            p = PROFILES[tkr]
            (avg_w_t, avg_l_t, avg_w_c, avg_l_c,
             wr_t, wr_c, tpd_t, tpd_c, chop_pct) = p

            # Is today choppy?
            day_choppy = random.random() < chop_pct
            n_trades = random.randint(
                max(1, tpd_c - 2), tpd_c + 2
            ) if day_choppy else random.randint(
                max(1, tpd_t - 2), tpd_t + 2
            )

            for t_idx in range(n_trades):
                hour = 8 + int(t_idx * (14 / max(n_trades, 1)))
                ts = day.replace(hour=min(hour, 22), minute=random.randint(0, 59))

                if day_choppy:
                    win = random.random() < wr_c
                    if win:
                        pnl = avg_w_c * random.uniform(0.5, 1.8)
                    else:
                        pnl = -avg_l_c * random.uniform(0.5, 1.8)
                    funding = random.choice(["BALANCED", "MILD_LONG_BIAS", "MILD_SHORT_BIAS"])
                    combined = "RANGE_BOUND" if random.random() < 0.6 else "LONG"
                    squeeze = random.choice(["LOW", "LOW", "ELEVATED"])
                    ls_bias = random.choice(["NEUTRAL", "BALANCED", "NEUTRAL"])
                    # Oracle less confident in chop
                    win_prob = random.uniform(0.42, 0.56)
                else:
                    win = random.random() < wr_t
                    if win:
                        pnl = avg_w_t * random.uniform(0.6, 2.0)
                    else:
                        pnl = -avg_l_t * random.uniform(0.6, 1.5)
                    funding = random.choice([
                        "OVERLEVERAGED_SHORT", "EXTREME_SHORT",
                        "OVERLEVERAGED_LONG", "BALANCED",
                    ])
                    combined = "LONG" if random.random() < 0.7 else "RANGE_BOUND"
                    squeeze = random.choice(["LOW", "ELEVATED", "HIGH"])
                    ls_bias = random.choice(["BULLISH", "NEUTRAL", "BEARISH"])
                    win_prob = random.uniform(0.50, 0.65)

                entry = 100.0  # dummy
                close = entry + (pnl / max(1.0, 1.0))  # dummy

                trades.append(Trade(
                    timestamp=ts,
                    ticker=tkr,
                    entry_price=entry,
                    close_price=close,
                    realized_pnl=round(pnl, 4),
                    quantity=1.0,
                    funding_regime=funding,
                    combined_signal=combined,
                    squeeze_risk=squeeze,
                    ls_bias=ls_bias,
                    oracle_win_prob=round(win_prob, 4),
                    close_reason="TRAIL_STOP" if win else "STOP_LOSS",
                ))

    trades.sort(key=lambda t: t.timestamp)
    return trades


# ── Replay Engine ────────────────────────────────────────────────

def replay(
    trades: List[Trade],
    gates: Dict[str, callable],
) -> Dict[str, StrategyResult]:
    """Walk-forward replay through multiple gate strategies.

    For each trade in chronological order:
      1. Compute EV from running stats UP TO this point (no look-ahead)
      2. Ask each gate: would you take this trade?
      3. Record the ACTUAL P&L for gates that said yes
      4. Update running stats with the realized P&L

    Running stats are shared across all gates (they see the same trade
    history) because in production only one gate runs at a time.
    """
    # Per-ticker running stats (shared — represents actual trade history)
    stats: Dict[str, RunningStats] = {}
    results = {name: StrategyResult(name=name) for name in gates}

    choppy_count = 0
    total_count = len(trades)

    for trade in trades:
        tkr = trade.ticker
        if tkr not in stats:
            stats[tkr] = RunningStats()

        s = stats[tkr]
        choppy = is_choppy(trade)
        if choppy:
            choppy_count += 1

        # Ask each gate (using stats BEFORE this trade — no look-ahead)
        for name, gate_fn in gates.items():
            allowed = gate_fn(trade, s)
            results[name].record(
                trade.realized_pnl,
                trade.ticker,
                blocked=not allowed,
            )

        # Update shared running stats AFTER all gates have decided
        s.update(trade.realized_pnl)

    # Store choppy fraction for reporting
    for r in results.values():
        r._choppy_pct = choppy_count / total_count if total_count else 0.0
        r._total_signals = total_count

    return results


# ── Reporting ────────────────────────────────────────────────────

def print_report(results: Dict[str, StrategyResult], trades: List[Trade]):
    """Print comparison report."""
    tickers = sorted({t.ticker for t in trades})
    n_days = (trades[-1].timestamp - trades[0].timestamp).days + 1 if trades else 0

    print("\n" + "=" * 78)
    print("  AGAPE-SPOT EV GATE REPLAY BACKTEST")
    print("=" * 78)
    print(f"  Period:  {trades[0].timestamp.strftime('%Y-%m-%d')} → "
          f"{trades[-1].timestamp.strftime('%Y-%m-%d')} ({n_days} days)")
    print(f"  Tickers: {', '.join(tickers)}")
    print(f"  Total signals: {len(trades)}")

    first = list(results.values())[0]
    choppy_pct = getattr(first, "_choppy_pct", 0)
    print(f"  Choppy scans: {choppy_pct:.1%}")
    print("=" * 78)

    # ── Side-by-side comparison ──────────────────────────────────
    names = list(results.keys())
    header = f"{'Metric':<28s}"
    for name in names:
        header += f" {name:>15s}"
    print(f"\n{header}")
    print("-" * (28 + 16 * len(names)))

    def row(label, fn, fmt=".2f"):
        line = f"  {label:<26s}"
        for name in names:
            val = fn(results[name])
            if isinstance(val, (int, float)):
                line += f" {val:>15{fmt}}"
            else:
                line += f" {str(val):>15s}"
        print(line)

    row("Trades Taken",     lambda r: r.trades_taken,  "d")
    row("Trades Blocked",   lambda r: r.trades_blocked, "d")
    row("Win Rate",         lambda r: r.win_rate * 100, ".1f")
    row("Total P&L ($)",    lambda r: r.total_pnl,     ".2f")
    row("Avg Win ($)",      lambda r: r.avg_win,       ".3f")
    row("Avg Loss ($)",     lambda r: r.avg_loss,      ".3f")
    row("Expectancy ($/trade)", lambda r: r.expectancy, ".4f")
    row("Profit Factor",    lambda r: r.profit_factor,  ".2f")
    row("Max Drawdown ($)", lambda r: r.max_drawdown,   ".2f")
    row("Gross Wins ($)",   lambda r: r.gross_wins,     ".2f")
    row("Gross Losses ($)", lambda r: r.gross_losses,   ".2f")

    # ── Blocked trade analysis ───────────────────────────────────
    print(f"\n{'BLOCKED TRADE ANALYSIS':<28s}")
    print("-" * (28 + 16 * len(names)))
    row("Blocked P&L (would-be)",   lambda r: r.blocked_pnl, ".2f")
    row("Blocked Wins",             lambda r: r.blocked_wins, "d")
    row("Blocked Losses",           lambda r: r.blocked_losses, "d")
    row("Blocked Win Rate",
        lambda r: (r.blocked_wins / r.trades_blocked * 100) if r.trades_blocked else 0.0, ".1f")
    row("P&L Saved by Blocking",
        lambda r: -r.blocked_pnl if r.blocked_pnl < 0 else 0.0, ".2f")
    row("P&L Missed by Blocking",
        lambda r: r.blocked_pnl if r.blocked_pnl > 0 else 0.0, ".2f")

    # ── Per-ticker breakdown ─────────────────────────────────────
    print(f"\n{'PER-TICKER P&L':<28s}")
    print("-" * (28 + 16 * len(names)))
    for tkr in tickers:
        row(f"  {tkr}",
            lambda r, t=tkr: r.ticker_pnl.get(t, 0.0), ".2f")
    row(f"  {'TOTAL':<24s}",
        lambda r: r.total_pnl, ".2f")

    # ── Per-ticker trade count ───────────────────────────────────
    print(f"\n{'PER-TICKER TRADES':<28s}")
    print("-" * (28 + 16 * len(names)))
    for tkr in tickers:
        row(f"  {tkr}",
            lambda r, t=tkr: r.ticker_trades.get(t, 0), "d")

    # ── Delta analysis (EWMA vs others) ──────────────────────────
    if "C: EWMA Dynamic" in results:
        ewma = results["C: EWMA Dynamic"]
        print(f"\n{'EWMA DYNAMIC vs OTHERS':<78s}")
        print("-" * 78)
        for name in names:
            if name == "C: EWMA Dynamic":
                continue
            other = results[name]
            delta_pnl = ewma.total_pnl - other.total_pnl
            delta_trades = ewma.trades_taken - other.trades_taken
            delta_wr = (ewma.win_rate - other.win_rate) * 100
            delta_exp = ewma.expectancy - other.expectancy
            sign = "+" if delta_pnl >= 0 else ""
            print(f"  vs {name}:")
            print(f"    P&L:         {sign}${delta_pnl:.2f}")
            print(f"    Trades:      {delta_trades:+d}")
            print(f"    Win Rate:    {delta_wr:+.1f}%")
            print(f"    Expectancy:  {sign}${delta_exp:.4f}/trade")

    # ── Equity curve ASCII ───────────────────────────────────────
    print(f"\n{'EQUITY CURVES (ASCII)':<78s}")
    print("-" * 78)
    _print_ascii_equity(results)

    print("\n" + "=" * 78)
    print("  REPLAY COMPLETE")
    print("=" * 78 + "\n")


def _print_ascii_equity(results: Dict[str, StrategyResult], width: int = 70, height: int = 18):
    """Render ASCII equity curves for all strategies."""
    curves = {}
    for name, r in results.items():
        if r.equity_curve:
            curves[name] = r.equity_curve

    if not curves:
        print("  (no equity data)")
        return

    all_vals = [v for c in curves.values() for v in c]
    y_min = min(all_vals)
    y_max = max(all_vals)
    y_range = y_max - y_min if y_max != y_min else 1.0

    max_len = max(len(c) for c in curves.values())
    symbols = {"A: No Gate": ".", "B: Flat $0.50": "x", "C: EWMA Dynamic": "#"}

    # Build canvas
    canvas = [[" "] * width for _ in range(height)]

    for name, curve in curves.items():
        sym = symbols.get(name, "o")
        for i, val in enumerate(curve):
            x = int(i / max(max_len - 1, 1) * (width - 1))
            y = int((val - y_min) / y_range * (height - 1))
            y = height - 1 - y  # invert
            if 0 <= x < width and 0 <= y < height:
                canvas[y][x] = sym

    # Print with y-axis labels
    for row_idx, row in enumerate(canvas):
        val = y_max - (row_idx / (height - 1)) * y_range
        label = f"${val:>8.2f} |"
        print(f"  {label}{''.join(row)}")

    print(f"  {'':>10s}+{'-' * width}")
    legend = "  ".join(f"{sym}={name}" for name, sym in symbols.items() if name in curves)
    print(f"  {'':>11s}{legend}")


# ── Main ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AGAPE-SPOT EV Gate Replay Backtester")
    parser.add_argument("--synthetic", action="store_true",
                        help="Use synthetic data (no DB needed)")
    parser.add_argument("--days", type=int, default=60,
                        help="Number of days to replay (default: 60)")
    parser.add_argument("--ticker", type=str, default=None,
                        help="Single ticker to replay (default: all)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for synthetic mode")
    args = parser.parse_args()

    # Load data
    if args.synthetic or not os.environ.get("DATABASE_URL"):
        if not args.synthetic:
            print("INFO: DATABASE_URL not set, using --synthetic mode")
        print(f"Generating {args.days} days of synthetic data (seed={args.seed})...")
        trades = generate_synthetic_trades(args.days, args.ticker, args.seed)
    else:
        print(f"Loading {args.days} days of trades from database...")
        trades = load_trades_from_db(args.days, args.ticker)

    if not trades:
        print("ERROR: No trades found.")
        sys.exit(1)

    print(f"Loaded {len(trades)} trades across "
          f"{len({t.ticker for t in trades})} tickers")

    # Define gate strategies
    gates = {
        "A: No Gate":       gate_no_filter,
        "B: Flat $0.50":    gate_flat_050,
        "C: EWMA Dynamic":  gate_ewma_dynamic,
    }

    # Run replay
    results = replay(trades, gates)

    # Print report
    print_report(results, trades)


if __name__ == "__main__":
    main()
