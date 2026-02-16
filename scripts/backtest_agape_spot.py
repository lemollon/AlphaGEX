#!/usr/bin/env python3
"""
PHASE 4A: AGAPE-SPOT BACKTESTING FRAMEWORK
============================================
Backtests new trading strategies against historical scan data from
the agape_spot_scan_activity table (1-minute price snapshots).

Strategies:
  1. BASELINE: Replicate current AGAPE-SPOT logic
  2. MEAN_REVERSION: Buy oversold dips, quick take-profit
  3. TIME_FILTERED: Same as baseline but restricted to profitable hours
  4. REGIME_SIZED: Dynamic position sizing based on trend regime

Data source: agape_spot_scan_activity
  - 1-min snapshots with: eth_price, funding_rate, funding_regime
  - combined_signal, oracle_win_prob, signal_action

Usage:
  python scripts/backtest_agape_spot.py                     # All strategies, ETH-USD
  python scripts/backtest_agape_spot.py --ticker BTC-USD    # BTC only
  python scripts/backtest_agape_spot.py --strategy mean_rev # Mean-reversion only
  python scripts/backtest_agape_spot.py --days 7            # Last 7 days only

Requires: DATABASE_URL environment variable or .env file.
"""

import argparse
import os
import sys
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CENTRAL_TZ = ZoneInfo("America/Chicago")

# Coinbase fee model: 0.4% taker per side
FEE_PER_SIDE = 0.004


# ===================================================================
# DATA CLASSES
# ===================================================================

@dataclass
class BacktestTrade:
    """A single simulated trade."""
    ticker: str
    entry_time: datetime
    entry_price: float
    quantity: float
    strategy: str
    # Optional entry context
    funding_rate: float = 0.0
    funding_regime: str = "UNKNOWN"
    chop_index: float = 0.0
    oracle_win_prob: float = 0.0
    combined_signal: str = "UNKNOWN"
    # Exit data (filled on close)
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    pnl_gross: float = 0.0
    pnl_net: float = 0.0
    fees: float = 0.0
    high_water_mark: float = 0.0
    trailing_active: bool = False
    current_stop: float = 0.0

    @property
    def is_open(self) -> bool:
        return self.exit_time is None

    def close(self, exit_time: datetime, exit_price: float, reason: str):
        self.exit_time = exit_time
        self.exit_price = exit_price
        self.exit_reason = reason
        notional = self.entry_price * self.quantity
        self.pnl_gross = (exit_price - self.entry_price) * self.quantity
        self.fees = notional * FEE_PER_SIDE * 2  # entry + exit
        self.pnl_net = self.pnl_gross - self.fees


@dataclass
class BacktestResult:
    """Summary of a backtest run."""
    strategy: str
    ticker: str
    trades: List[BacktestTrade] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    @property
    def closed_trades(self):
        return [t for t in self.trades if not t.is_open]

    @property
    def total_trades(self): return len(self.closed_trades)

    @property
    def wins(self): return sum(1 for t in self.closed_trades if t.pnl_net > 0)

    @property
    def losses(self): return sum(1 for t in self.closed_trades if t.pnl_net <= 0)

    @property
    def win_rate(self): return self.wins / self.total_trades if self.total_trades > 0 else 0

    @property
    def gross_pnl(self): return sum(t.pnl_gross for t in self.closed_trades)

    @property
    def net_pnl(self): return sum(t.pnl_net for t in self.closed_trades)

    @property
    def total_fees(self): return sum(t.fees for t in self.closed_trades)

    @property
    def avg_win(self):
        wins = [t.pnl_net for t in self.closed_trades if t.pnl_net > 0]
        return sum(wins) / len(wins) if wins else 0

    @property
    def avg_loss(self):
        losses = [t.pnl_net for t in self.closed_trades if t.pnl_net <= 0]
        return sum(losses) / len(losses) if losses else 0

    @property
    def profit_factor(self):
        gross_wins = sum(t.pnl_net for t in self.closed_trades if t.pnl_net > 0)
        gross_losses = abs(sum(t.pnl_net for t in self.closed_trades if t.pnl_net <= 0))
        return gross_wins / gross_losses if gross_losses > 0 else float('inf') if gross_wins > 0 else 0

    @property
    def max_drawdown(self):
        equity = 0
        peak = 0
        max_dd = 0
        for t in sorted(self.closed_trades, key=lambda x: x.exit_time or datetime.min):
            equity += t.pnl_net
            peak = max(peak, equity)
            dd = peak - equity
            max_dd = max(max_dd, dd)
        return max_dd

    @property
    def sharpe_ratio(self):
        """Annualized Sharpe (assuming ~365 trading days for crypto)."""
        if not self.closed_trades:
            return 0
        returns = [t.pnl_net for t in self.closed_trades]
        import statistics
        if len(returns) < 2:
            return 0
        mean_r = statistics.mean(returns)
        std_r = statistics.stdev(returns)
        if std_r == 0:
            return 0
        # Trades per day
        if self.start_time and self.end_time:
            days = max((self.end_time - self.start_time).total_seconds() / 86400, 1)
            trades_per_day = self.total_trades / days
        else:
            trades_per_day = 10  # fallback
        return (mean_r / std_r) * (trades_per_day * 365) ** 0.5

    @property
    def max_consecutive_losses(self):
        max_streak = 0
        current = 0
        for t in sorted(self.closed_trades, key=lambda x: x.exit_time or datetime.min):
            if t.pnl_net <= 0:
                current += 1
                max_streak = max(max_streak, current)
            else:
                current = 0
        return max_streak

    def print_summary(self):
        """Pretty-print results."""
        print(f"\n  {'='*60}")
        print(f"  Strategy: {self.strategy} | Ticker: {self.ticker}")
        print(f"  {'='*60}")
        print(f"  Total trades:        {self.total_trades}")
        print(f"  Win/Loss:            {self.wins}W / {self.losses}L")
        print(f"  Win Rate:            {self.win_rate:.1%}")
        print(f"  Gross P&L:           ${self.gross_pnl:+,.2f}")
        print(f"  Total Fees:          ${self.total_fees:,.2f}")
        print(f"  Net P&L:             ${self.net_pnl:+,.2f}")
        print(f"  Avg Win:             ${self.avg_win:+,.2f}")
        print(f"  Avg Loss:            ${self.avg_loss:+,.2f}")
        print(f"  Profit Factor:       {self.profit_factor:.2f}")
        print(f"  Max Drawdown:        ${self.max_drawdown:,.2f}")
        print(f"  Max Loss Streak:     {self.max_consecutive_losses}")
        if self.total_trades > 0:
            ev = (self.win_rate * self.avg_win) + ((1 - self.win_rate) * self.avg_loss)
            print(f"  EV per trade:        ${ev:+,.4f}")
            print(f"  EV after fees:       ${ev:+,.4f} (fees included in win/loss)")

    def print_by_exit_reason(self):
        reasons = {}
        for t in self.closed_trades:
            r = t.exit_reason or "UNKNOWN"
            if r not in reasons:
                reasons[r] = {"count": 0, "pnl": 0, "wins": 0}
            reasons[r]["count"] += 1
            reasons[r]["pnl"] += t.pnl_net
            if t.pnl_net > 0:
                reasons[r]["wins"] += 1

        print(f"\n  By Exit Reason:")
        print(f"  {'Reason':<25} {'Count':>7} {'WR%':>7} {'Net P&L':>12}")
        print(f"  {'-'*55}")
        for r, d in sorted(reasons.items(), key=lambda x: x[1]["pnl"]):
            wr = d["wins"] / d["count"] * 100 if d["count"] > 0 else 0
            print(f"  {r:<25} {d['count']:>7} {wr:>6.1f}% ${d['pnl']:>+10,.2f}")

    def print_equity_curve_ascii(self, width=60):
        """Print ASCII equity curve."""
        if not self.closed_trades:
            return
        sorted_trades = sorted(self.closed_trades, key=lambda x: x.exit_time or datetime.min)
        equities = []
        eq = 0
        for t in sorted_trades:
            eq += t.pnl_net
            equities.append(eq)

        if not equities:
            return

        min_eq = min(equities)
        max_eq = max(equities)
        eq_range = max_eq - min_eq if max_eq != min_eq else 1

        print(f"\n  Equity Curve ({len(equities)} trades):")
        print(f"  Max: ${max_eq:+,.2f}  |  Min: ${min_eq:+,.2f}  |  Final: ${equities[-1]:+,.2f}")

        # Downsample if too many trades
        step = max(1, len(equities) // width)
        sampled = equities[::step]

        for eq in sampled:
            pos = int((eq - min_eq) / eq_range * 40)
            marker = "*"
            line = " " * pos + marker
            print(f"  |{line}")


# ===================================================================
# STRATEGY BASE CLASS
# ===================================================================

class Strategy:
    """Base class for backtesting strategies."""

    name: str = "base"

    def __init__(self, ticker: str, capital: float = 1000.0):
        self.ticker = ticker
        self.capital = capital
        self.open_positions: List[BacktestTrade] = []
        self.closed_trades: List[BacktestTrade] = []
        self.price_history: deque = deque(maxlen=60)  # 60 minutes of prices

    def should_enter(self, scan: dict) -> Optional[dict]:
        """Return trade params dict if should enter, None otherwise."""
        raise NotImplementedError

    def should_exit(self, trade: BacktestTrade, scan: dict) -> Optional[str]:
        """Return exit reason string if should exit, None otherwise."""
        raise NotImplementedError

    def get_quantity(self, price: float, size_mult: float = 1.0) -> float:
        """Calculate position quantity."""
        position_capital = self.capital * 0.3 * size_mult  # 30% per position
        return position_capital / price if price > 0 else 0

    def process_scan(self, scan: dict):
        """Process a single scan cycle."""
        price = scan.get("price")
        if not price or price <= 0:
            return

        self.price_history.append(price)

        # Manage exits first
        for trade in list(self.open_positions):
            reason = self.should_exit(trade, scan)
            if reason:
                trade.close(scan["timestamp"], price, reason)
                self.closed_trades.append(trade)
                self.open_positions.remove(trade)

        # Check entries
        if len(self.open_positions) < self.max_positions:
            entry = self.should_enter(scan)
            if entry:
                trade = BacktestTrade(
                    ticker=self.ticker,
                    entry_time=scan["timestamp"],
                    entry_price=price,
                    quantity=entry.get("quantity", self.get_quantity(price)),
                    strategy=self.name,
                    funding_rate=scan.get("funding_rate", 0),
                    funding_regime=scan.get("funding_regime", "UNKNOWN"),
                    oracle_win_prob=scan.get("oracle_win_prob", 0),
                    combined_signal=scan.get("combined_signal", "UNKNOWN"),
                    high_water_mark=price,
                )
                self.open_positions.append(trade)

    @property
    def max_positions(self) -> int:
        return 3

    def get_result(self) -> BacktestResult:
        result = BacktestResult(
            strategy=self.name,
            ticker=self.ticker,
            trades=self.closed_trades.copy(),
        )
        if self.closed_trades:
            result.start_time = min(t.entry_time for t in self.closed_trades)
            result.end_time = max(t.exit_time for t in self.closed_trades if t.exit_time)
        return result


# ===================================================================
# STRATEGY 1: BASELINE (replicates current AGAPE-SPOT logic)
# ===================================================================

class BaselineStrategy(Strategy):
    """Replicates current AGAPE-SPOT logic for comparison."""

    name = "BASELINE"

    def __init__(self, ticker: str, capital: float = 1000.0):
        super().__init__(ticker, capital)
        self.no_loss_activation_pct = 1.5
        self.trail_distance_pct = 1.25
        self.max_loss_pct = 1.5
        self.max_hold_minutes = 4 * 60  # 4 hours
        self.min_scans_between = 5
        self.scans_since_last_trade = 999

    def should_enter(self, scan: dict) -> Optional[dict]:
        self.scans_since_last_trade += 1
        if self.scans_since_last_trade < self.min_scans_between:
            return None

        # Require LONG signal
        action = scan.get("signal_action", "")
        if action not in ("LONG", "TRADE"):
            # Also accept if combined_signal is LONG
            if scan.get("combined_signal") != "LONG":
                return None

        self.scans_since_last_trade = 0
        return {"quantity": self.get_quantity(scan["price"])}

    def should_exit(self, trade: BacktestTrade, scan: dict) -> Optional[str]:
        price = scan["price"]
        entry = trade.entry_price
        hold_min = (scan["timestamp"] - trade.entry_time).total_seconds() / 60

        # Update HWM
        if price > trade.high_water_mark:
            trade.high_water_mark = price

        profit_pct = (price - entry) / entry * 100

        # Max loss
        if profit_pct <= -self.max_loss_pct:
            return "MAX_LOSS"

        # Emergency stop
        if profit_pct <= -5.0:
            return "EMERGENCY_STOP"

        # Max hold
        if hold_min >= self.max_hold_minutes:
            return "MAX_HOLD"

        # Trailing stop
        if trade.trailing_active:
            if price <= trade.current_stop:
                return "TRAIL_STOP"
        else:
            # Activate trail
            hwm_profit = (trade.high_water_mark - entry) / entry * 100
            if hwm_profit >= self.no_loss_activation_pct:
                trade.trailing_active = True
                trade.current_stop = trade.high_water_mark * (1 - self.trail_distance_pct / 100)

        # Update stop if trailing
        if trade.trailing_active:
            new_stop = trade.high_water_mark * (1 - self.trail_distance_pct / 100)
            trade.current_stop = max(trade.current_stop, new_stop)

        return None


# ===================================================================
# STRATEGY 2: MEAN REVERSION SCALP
# ===================================================================

class MeanReversionStrategy(Strategy):
    """Mean-reversion: buy oversold dips, quick take-profit.

    Entry: Price dropped > entry_drop_pct from 30-min high
    Exit: Fixed profit target OR time stop OR max loss
    """

    name = "MEAN_REVERSION"

    def __init__(self, ticker: str, capital: float = 1000.0,
                 entry_drop_pct: float = -0.8,
                 profit_target_pct: float = 0.5,
                 stop_loss_pct: float = 1.0,
                 max_hold_min: int = 30,
                 min_scans_between: int = 15):
        super().__init__(ticker, capital)
        self.entry_drop_pct = entry_drop_pct
        self.profit_target_pct = profit_target_pct
        self.stop_loss_pct = stop_loss_pct
        self.max_hold_min = max_hold_min
        self.min_scans_between = min_scans_between
        self.scans_since_last_trade = 999

    @property
    def max_positions(self) -> int:
        return 2

    def _get_30min_high(self) -> float:
        """Get the highest price in the last 30 readings (≈30 min)."""
        if len(self.price_history) < 10:
            return 0
        recent = list(self.price_history)[-30:]
        return max(recent)

    def should_enter(self, scan: dict) -> Optional[dict]:
        self.scans_since_last_trade += 1
        if self.scans_since_last_trade < self.min_scans_between:
            return None

        price = scan["price"]
        high_30m = self._get_30min_high()

        if high_30m <= 0:
            return None

        drop_pct = (price - high_30m) / high_30m * 100

        # Entry: price dropped enough from recent high
        if drop_pct <= self.entry_drop_pct:
            # Additional filter: funding not extremely positive (shorts not paying)
            funding = scan.get("funding_rate", 0)
            if funding and funding > 0.01:
                return None  # Extremely bullish funding = not a real dip

            self.scans_since_last_trade = 0
            return {"quantity": self.get_quantity(price, size_mult=0.5)}

        return None

    def should_exit(self, trade: BacktestTrade, scan: dict) -> Optional[str]:
        price = scan["price"]
        entry = trade.entry_price
        hold_min = (scan["timestamp"] - trade.entry_time).total_seconds() / 60

        profit_pct = (price - entry) / entry * 100

        # Take profit
        if profit_pct >= self.profit_target_pct:
            return "PROFIT_TARGET"

        # Stop loss
        if profit_pct <= -self.stop_loss_pct:
            return "STOP_LOSS"

        # Time stop
        if hold_min >= self.max_hold_min:
            return "TIME_STOP"

        return None


# ===================================================================
# STRATEGY 3: TIME-FILTERED BASELINE
# ===================================================================

class TimeFilteredStrategy(BaselineStrategy):
    """Same as baseline but only trades during profitable hours (CT)."""

    name = "TIME_FILTERED"

    def __init__(self, ticker: str, capital: float = 1000.0,
                 allowed_hours: Optional[List[int]] = None):
        super().__init__(ticker, capital)
        # Default: 8am-2pm CT (the profitable window from Phase 1 data)
        self.allowed_hours = allowed_hours or list(range(8, 15))

    def should_enter(self, scan: dict) -> Optional[dict]:
        hour_ct = scan["timestamp"].astimezone(CENTRAL_TZ).hour
        if hour_ct not in self.allowed_hours:
            return None
        return super().should_enter(scan)


# ===================================================================
# STRATEGY 4: REGIME-SIZED
# ===================================================================

class RegimeSizedStrategy(BaselineStrategy):
    """Dynamic position sizing based on trend regime."""

    name = "REGIME_SIZED"

    def __init__(self, ticker: str, capital: float = 1000.0):
        super().__init__(ticker, capital)
        self.sma_window = 20  # 20-minute SMA

    def _get_sma(self) -> float:
        if len(self.price_history) < self.sma_window:
            return 0
        recent = list(self.price_history)[-self.sma_window:]
        return sum(recent) / len(recent)

    def _get_regime(self, price: float) -> str:
        sma = self._get_sma()
        if sma <= 0:
            return "UNKNOWN"

        pct_from_sma = (price - sma) / sma * 100

        if pct_from_sma > 0.5:
            return "STRONG_UP"
        elif pct_from_sma > 0.1:
            return "MILD_UP"
        elif pct_from_sma > -0.1:
            return "NEUTRAL"
        elif pct_from_sma > -0.5:
            return "MILD_DOWN"
        else:
            return "STRONG_DOWN"

    def get_quantity(self, price: float, size_mult: float = 1.0) -> float:
        regime = self._get_regime(price)
        regime_multipliers = {
            "STRONG_UP": 1.0,
            "MILD_UP": 0.8,
            "NEUTRAL": 0.5,
            "MILD_DOWN": 0.25,
            "STRONG_DOWN": 0.0,  # Don't trade in strong downtrends
            "UNKNOWN": 0.5,
        }
        mult = regime_multipliers.get(regime, 0.5) * size_mult
        return super().get_quantity(price, mult)

    def should_enter(self, scan: dict) -> Optional[dict]:
        regime = self._get_regime(scan["price"])
        if regime == "STRONG_DOWN":
            return None  # Skip trading entirely in strong downtrends
        return super().should_enter(scan)


# ===================================================================
# STRATEGY 5: DCA (Dollar-Cost Average on Dips)
# ===================================================================

class DCAStrategy(Strategy):
    """Scale into positions on dips instead of single entry."""

    name = "DCA_ENTRY"

    def __init__(self, ticker: str, capital: float = 1000.0,
                 num_tranches: int = 3,
                 tranche_spacing_pct: float = 0.5,
                 profit_target_pct: float = 0.8,
                 max_loss_pct: float = 2.0,
                 max_hold_min: int = 120):
        super().__init__(ticker, capital)
        self.num_tranches = num_tranches
        self.tranche_spacing_pct = tranche_spacing_pct
        self.profit_target_pct = profit_target_pct
        self.max_loss_pct = max_loss_pct
        self.max_hold_min = max_hold_min
        self.min_scans_between = 30
        self.scans_since_last_trade = 999
        # Track DCA sequences
        self.dca_sequences: List[Dict] = []  # {first_entry_price, tranches_filled, total_qty, avg_entry}

    @property
    def max_positions(self) -> int:
        return 6  # 2 sequences * 3 tranches

    def should_enter(self, scan: dict) -> Optional[dict]:
        self.scans_since_last_trade += 1
        price = scan["price"]

        # Check if we should add a tranche to existing sequence
        for seq in self.dca_sequences:
            if seq["tranches_filled"] < self.num_tranches:
                next_trigger = seq["first_entry_price"] * (1 - self.tranche_spacing_pct * seq["tranches_filled"] / 100)
                if price <= next_trigger:
                    seq["tranches_filled"] += 1
                    qty = self.get_quantity(price, size_mult=1.0 / self.num_tranches)
                    seq["total_qty"] += qty
                    seq["avg_entry"] = (seq["avg_entry"] * (seq["tranches_filled"] - 1) + price) / seq["tranches_filled"]
                    return {"quantity": qty}

        # New sequence: require signal + cooldown
        if self.scans_since_last_trade < self.min_scans_between:
            return None

        action = scan.get("signal_action", "")
        if action not in ("LONG", "TRADE"):
            if scan.get("combined_signal") != "LONG":
                return None

        if len(self.dca_sequences) >= 2:
            return None  # Max 2 active sequences

        qty = self.get_quantity(price, size_mult=1.0 / self.num_tranches)
        self.dca_sequences.append({
            "first_entry_price": price,
            "tranches_filled": 1,
            "total_qty": qty,
            "avg_entry": price,
        })
        self.scans_since_last_trade = 0
        return {"quantity": qty}

    def should_exit(self, trade: BacktestTrade, scan: dict) -> Optional[str]:
        price = scan["price"]
        entry = trade.entry_price
        hold_min = (scan["timestamp"] - trade.entry_time).total_seconds() / 60

        profit_pct = (price - entry) / entry * 100

        if profit_pct >= self.profit_target_pct:
            return "PROFIT_TARGET"
        if profit_pct <= -self.max_loss_pct:
            return "MAX_LOSS"
        if hold_min >= self.max_hold_min:
            return "MAX_HOLD"

        return None


# ===================================================================
# STRATEGY 6: COMBINED (Mean-Rev in downtrends, Baseline in uptrends)
# ===================================================================

class CombinedStrategy(Strategy):
    """Uses regime detection to switch between strategies.

    Uptrend/Neutral: Baseline trending strategy
    Downtrend: Mean-reversion scalp strategy
    """

    name = "COMBINED_REGIME"

    def __init__(self, ticker: str, capital: float = 1000.0):
        super().__init__(ticker, capital)
        self.baseline = BaselineStrategy(ticker, capital * 0.6)
        self.mean_rev = MeanReversionStrategy(ticker, capital * 0.4)
        self.sma_window = 30

    @property
    def max_positions(self) -> int:
        return 4

    def _get_regime(self, price: float) -> str:
        if len(self.price_history) < self.sma_window:
            return "UNKNOWN"
        recent = list(self.price_history)[-self.sma_window:]
        sma = sum(recent) / len(recent)
        pct = (price - sma) / sma * 100
        if pct > 0.2:
            return "UPTREND"
        elif pct < -0.2:
            return "DOWNTREND"
        return "NEUTRAL"

    def process_scan(self, scan: dict):
        price = scan.get("price")
        if not price or price <= 0:
            return

        self.price_history.append(price)
        # Share price history
        self.baseline.price_history = self.price_history
        self.mean_rev.price_history = self.price_history

        regime = self._get_regime(price)

        # Manage exits for all open positions
        for trade in list(self.open_positions):
            if trade.strategy == "BASELINE":
                reason = self.baseline.should_exit(trade, scan)
            else:
                reason = self.mean_rev.should_exit(trade, scan)
            if reason:
                trade.close(scan["timestamp"], price, reason)
                self.closed_trades.append(trade)
                self.open_positions.remove(trade)

        # Entries based on regime
        if len(self.open_positions) < self.max_positions:
            if regime == "DOWNTREND":
                entry = self.mean_rev.should_enter(scan)
                if entry:
                    trade = BacktestTrade(
                        ticker=self.ticker,
                        entry_time=scan["timestamp"],
                        entry_price=price,
                        quantity=entry["quantity"],
                        strategy="MEAN_REV",
                        funding_rate=scan.get("funding_rate", 0),
                        funding_regime=scan.get("funding_regime", "UNKNOWN"),
                        oracle_win_prob=scan.get("oracle_win_prob", 0),
                        combined_signal=scan.get("combined_signal", "UNKNOWN"),
                        high_water_mark=price,
                    )
                    self.open_positions.append(trade)
            else:  # UPTREND or NEUTRAL
                entry = self.baseline.should_enter(scan)
                if entry:
                    trade = BacktestTrade(
                        ticker=self.ticker,
                        entry_time=scan["timestamp"],
                        entry_price=price,
                        quantity=entry["quantity"],
                        strategy="BASELINE",
                        funding_rate=scan.get("funding_rate", 0),
                        funding_regime=scan.get("funding_regime", "UNKNOWN"),
                        oracle_win_prob=scan.get("oracle_win_prob", 0),
                        combined_signal=scan.get("combined_signal", "UNKNOWN"),
                        high_water_mark=price,
                    )
                    self.open_positions.append(trade)


# ===================================================================
# DATA LOADER
# ===================================================================

def load_scan_data(conn, ticker: str, days: int = 14) -> List[dict]:
    """Load scan data from database as a list of dicts."""
    cur = conn.cursor()
    cur.execute("""
        SELECT
            timestamp,
            eth_price,
            funding_rate,
            funding_regime,
            combined_signal,
            combined_confidence,
            oracle_win_prob,
            signal_action,
            signal_reasoning
        FROM agape_spot_scan_activity
        WHERE ticker = %s
          AND eth_price IS NOT NULL AND eth_price > 0
          AND timestamp > NOW() - INTERVAL '%s days'
        ORDER BY timestamp ASC
    """, (ticker, days))

    rows = cur.fetchall()
    cur.close()

    scans = []
    for r in rows:
        scans.append({
            "timestamp": r[0],
            "price": float(r[1]),
            "funding_rate": float(r[2]) if r[2] else 0,
            "funding_regime": r[3] or "UNKNOWN",
            "combined_signal": r[4] or "UNKNOWN",
            "combined_confidence": r[5] or "LOW",
            "oracle_win_prob": float(r[6]) if r[6] else 0,
            "signal_action": r[7] or "WAIT",
            "signal_reasoning": r[8] or "",
        })

    return scans


# ===================================================================
# COMPARISON TABLE
# ===================================================================

def print_comparison(results: List[BacktestResult]):
    """Print side-by-side comparison of all strategies."""
    print("\n" + "=" * 100)
    print("  STRATEGY COMPARISON")
    print("=" * 100)

    headers = ["Metric"] + [r.strategy for r in results]
    widths = [20] + [15] * len(results)

    def row(label, values):
        parts = [f"{label:<{widths[0]}}"]
        for i, v in enumerate(values):
            parts.append(f"{v:>{widths[i+1]}}")
        print("  " + " ".join(parts))

    # Header
    row("", [r.strategy for r in results])
    print("  " + "-" * (sum(widths) + len(widths)))

    row("Total Trades", [str(r.total_trades) for r in results])
    row("Win Rate", [f"{r.win_rate:.1%}" for r in results])
    row("Gross P&L", [f"${r.gross_pnl:+,.2f}" for r in results])
    row("Fees", [f"${r.total_fees:,.2f}" for r in results])
    row("Net P&L", [f"${r.net_pnl:+,.2f}" for r in results])
    row("Avg Win", [f"${r.avg_win:+,.2f}" for r in results])
    row("Avg Loss", [f"${r.avg_loss:+,.2f}" for r in results])
    row("Profit Factor", [f"{r.profit_factor:.2f}" for r in results])
    row("Max Drawdown", [f"${r.max_drawdown:,.2f}" for r in results])
    row("Max Loss Streak", [str(r.max_consecutive_losses) for r in results])

    # EV per trade
    evs = []
    for r in results:
        if r.total_trades > 0:
            ev = r.net_pnl / r.total_trades
            evs.append(f"${ev:+,.4f}")
        else:
            evs.append("N/A")
    row("EV/Trade (net)", evs)

    # Best strategy
    best = max(results, key=lambda r: r.net_pnl)
    baseline = next((r for r in results if r.strategy == "BASELINE"), results[0])
    improvement = best.net_pnl - baseline.net_pnl

    print(f"\n  WINNER: {best.strategy} with ${best.net_pnl:+,.2f} net P&L")
    if best.strategy != "BASELINE":
        print(f"  Improvement vs BASELINE: ${improvement:+,.2f}")


# ===================================================================
# BUY-AND-HOLD COMPARISON
# ===================================================================

def buy_and_hold_pnl(scans: List[dict], capital: float = 1000.0) -> float:
    """Calculate buy-and-hold P&L for comparison."""
    if not scans:
        return 0
    first_price = scans[0]["price"]
    last_price = scans[-1]["price"]
    qty = capital / first_price
    gross = (last_price - first_price) * qty
    fees = capital * FEE_PER_SIDE  # Only entry fee for B&H
    return gross - fees


# ===================================================================
# MAIN
# ===================================================================

def get_db_connection():
    try:
        import psycopg2
        url = os.environ.get("DATABASE_URL")
        if not url:
            env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
            if os.path.exists(env_path):
                with open(env_path) as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("DATABASE_URL=") and not line.startswith("#"):
                            url = line.split("=", 1)[1].strip()
                            break
        if not url:
            print("ERROR: DATABASE_URL not set.")
            sys.exit(1)
        return psycopg2.connect(url, connect_timeout=30)
    except Exception as e:
        print(f"ERROR: DB connection failed: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="AGAPE-SPOT Backtesting Framework")
    parser.add_argument("--ticker", default="ETH-USD", help="Ticker to backtest (default: ETH-USD)")
    parser.add_argument("--days", type=int, default=14, help="Days of history to use (default: 14)")
    parser.add_argument("--strategy", default="all",
                        help="Strategy to test: baseline, mean_rev, time_filtered, regime_sized, dca, combined, all")
    parser.add_argument("--capital", type=float, default=1000.0, help="Starting capital (default: 1000)")
    args = parser.parse_args()

    print("=" * 80)
    print("  AGAPE-SPOT BACKTESTING FRAMEWORK")
    print(f"  Ticker: {args.ticker} | Days: {args.days} | Capital: ${args.capital:,.0f}")
    print(f"  Generated: {datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d %H:%M:%S CT')}")
    print("=" * 80)

    conn = get_db_connection()

    # Load scan data
    print(f"\n  Loading scan data for {args.ticker} (last {args.days} days)...")
    scans = load_scan_data(conn, args.ticker, args.days)
    conn.close()

    if not scans:
        print("  No scan data found. Run AGAPE-SPOT first to collect data.")
        return

    print(f"  Loaded {len(scans):,} scans from {scans[0]['timestamp']} to {scans[-1]['timestamp']}")

    # Price stats
    prices = [s["price"] for s in scans]
    print(f"  Price range: ${min(prices):,.2f} - ${max(prices):,.2f}")
    price_change = (prices[-1] - prices[0]) / prices[0] * 100
    print(f"  Price change: {price_change:+.2f}%")

    # Buy-and-hold baseline
    bh_pnl = buy_and_hold_pnl(scans, args.capital)
    print(f"  Buy-and-hold P&L: ${bh_pnl:+,.2f}")

    # Initialize strategies
    strategies = {}

    if args.strategy in ("all", "baseline"):
        strategies["BASELINE"] = BaselineStrategy(args.ticker, args.capital)

    if args.strategy in ("all", "mean_rev"):
        strategies["MEAN_REVERSION"] = MeanReversionStrategy(
            args.ticker, args.capital,
            entry_drop_pct=-0.8,
            profit_target_pct=0.5,
            stop_loss_pct=1.0,
            max_hold_min=30,
        )

    if args.strategy in ("all", "time_filtered"):
        strategies["TIME_FILTERED"] = TimeFilteredStrategy(
            args.ticker, args.capital,
            allowed_hours=list(range(8, 15)),
        )

    if args.strategy in ("all", "regime_sized"):
        strategies["REGIME_SIZED"] = RegimeSizedStrategy(args.ticker, args.capital)

    if args.strategy in ("all", "dca"):
        strategies["DCA_ENTRY"] = DCAStrategy(args.ticker, args.capital)

    if args.strategy in ("all", "combined"):
        strategies["COMBINED_REGIME"] = CombinedStrategy(args.ticker, args.capital)

    # Run backtest
    print(f"\n  Running {len(strategies)} strategies over {len(scans):,} scans...")

    for scan in scans:
        for name, strat in strategies.items():
            strat.process_scan(scan)

    # Close any remaining open positions at last price
    last_scan = scans[-1]
    for name, strat in strategies.items():
        for trade in list(strat.open_positions):
            trade.close(last_scan["timestamp"], last_scan["price"], "BACKTEST_END")
            strat.closed_trades.append(trade)
            strat.open_positions.remove(trade)

    # Collect results
    results = [strat.get_result() for strat in strategies.values()]

    # Print individual results
    for result in results:
        result.print_summary()
        result.print_by_exit_reason()

    # Comparison
    if len(results) > 1:
        print_comparison(results)

    # vs Buy-and-Hold
    print(f"\n  BUY-AND-HOLD COMPARISON:")
    print(f"  B&H P&L: ${bh_pnl:+,.2f}")
    for r in results:
        alpha = r.net_pnl - bh_pnl
        print(f"  {r.strategy}: ${r.net_pnl:+,.2f} (alpha: ${alpha:+,.2f})")

    print("\n" + "=" * 80)
    print("  BACKTEST COMPLETE")
    print("  To test different parameters, modify strategy constructors in this file.")
    print("  To add a new strategy, create a class extending Strategy.")
    print("=" * 80)


if __name__ == "__main__":
    main()
