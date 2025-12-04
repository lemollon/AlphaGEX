"""
Diagonal Put Spread + Wheel Strategy Backtester

Extends the WheelBacktester to add diagonal put spread hedging:
1. Base strategy: Cash-Secured Put Wheel (from WheelBacktester)
2. Hedge overlay: Diagonal put spreads in high IV environments

The diagonal spread provides:
- Downside protection during market stress
- Additional income in elevated IV
- Reduced overall portfolio volatility

Usage:
    from backtest.diagonal_wheel_backtest import DiagonalWheelBacktester

    backtester = DiagonalWheelBacktester(
        symbol="SPY",
        start_date="2020-01-01",
        end_date="2024-12-01",
        enable_diagonal_hedge=True,
        iv_threshold=0.50  # Only add diagonals when IV rank > 50%
    )
    results = backtester.run_backtest()
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from backtest.wheel_backtest import WheelBacktester, WheelCycleTrade
from backtest.backtest_framework import BacktestResults, Trade, DataQuality
from backtest.strategy_report import StrategyReportGenerator, StrategyReport, print_strategy_report


@dataclass
class DiagonalSpreadTrade:
    """Represents a diagonal put spread position"""
    spread_id: int
    entry_date: str
    exit_date: Optional[str]

    # Short leg (near-term, higher strike)
    short_strike: float
    short_premium: float  # Premium collected
    short_dte: int
    short_expiry: str

    # Long leg (longer-term, lower strike)
    long_strike: float
    long_premium: float  # Premium paid
    long_dte: int
    long_expiry: str

    # Net position
    net_credit: float  # short_premium - long_premium
    max_risk: float  # strike difference minus net credit
    underlying_at_entry: float
    iv_at_entry: float

    # Outcome
    pnl: float = 0
    pnl_pct: float = 0
    status: str = "OPEN"  # OPEN, CLOSED, EXPIRED


class DiagonalWheelBacktester(WheelBacktester):
    """
    Backtests combined Diagonal Put Spread + CSP Wheel strategy.

    Extends WheelBacktester to add diagonal put spread overlay:
    - Monitors IV rank throughout the backtest
    - Opens diagonal spreads when IV rank exceeds threshold
    - Manages spread expirations alongside wheel positions
    - Tracks combined P&L and risk metrics
    """

    def __init__(
        self,
        enable_diagonal_hedge: bool = True,
        iv_threshold: float = 0.50,  # IV rank threshold to enter diagonals
        diagonal_allocation_pct: float = 0.25,  # Max capital for diagonals
        diagonal_short_dte: int = 10,  # Near-term leg DTE
        diagonal_long_dte: int = 60,  # Longer-term leg DTE
        diagonal_short_delta: float = 0.25,  # Short leg delta
        diagonal_long_delta: float = 0.15,  # Long leg delta (further OTM)
        max_diagonal_positions: int = 3,
        **kwargs
    ):
        """
        Initialize combined backtester.

        Args:
            enable_diagonal_hedge: Enable diagonal put spread overlay
            iv_threshold: IV rank threshold to enter diagonals (0-1)
            diagonal_allocation_pct: Max capital allocation to diagonals
            diagonal_short_dte: DTE for short leg
            diagonal_long_dte: DTE for long leg
            diagonal_short_delta: Target delta for short leg
            diagonal_long_delta: Target delta for long leg
            max_diagonal_positions: Maximum concurrent diagonal positions
            **kwargs: Arguments passed to WheelBacktester
        """
        super().__init__(**kwargs)

        self.enable_diagonal = enable_diagonal_hedge
        self.iv_threshold = iv_threshold
        self.diagonal_allocation_pct = diagonal_allocation_pct
        self.diagonal_short_dte = diagonal_short_dte
        self.diagonal_long_dte = diagonal_long_dte
        self.diagonal_short_delta = diagonal_short_delta
        self.diagonal_long_delta = diagonal_long_delta
        self.max_diagonal_positions = max_diagonal_positions

        # Diagonal tracking
        self.diagonal_trades: List[DiagonalSpreadTrade] = []
        self.active_diagonals: List[DiagonalSpreadTrade] = []
        self.diagonal_id = 0

    def calculate_iv_rank(self, current_iv: float, iv_series: pd.Series, lookback: int = 252) -> float:
        """
        Calculate IV rank: where current IV sits relative to past year.

        IV Rank = (Current IV - 52-week Low) / (52-week High - 52-week Low)
        """
        if len(iv_series) < lookback:
            lookback = len(iv_series)

        recent_iv = iv_series.iloc[-lookback:]
        iv_min = recent_iv.min()
        iv_max = recent_iv.max()

        if iv_max == iv_min:
            return 0.5  # Default to middle if no range

        return (current_iv - iv_min) / (iv_max - iv_min)

    def estimate_diagonal_premiums(
        self,
        spot: float,
        vol: float,
        short_strike: float,
        long_strike: float
    ) -> Tuple[float, float]:
        """
        Estimate premiums for diagonal spread legs.

        Returns:
            Tuple of (short_premium, long_premium)
        """
        short_premium = self.estimate_put_premium(
            spot, short_strike, self.diagonal_short_dte, vol
        )
        long_premium = self.estimate_put_premium(
            spot, long_strike, self.diagonal_long_dte, vol * 0.95  # IV typically lower for further dates
        )

        return short_premium, long_premium

    def select_diagonal_strikes(self, spot: float, vol: float) -> Tuple[float, float]:
        """
        Select strikes for diagonal spread.

        Short leg: ~25 delta, closer to ATM
        Long leg: ~15 delta, further OTM (more downside protection)
        """
        # Short strike (higher, closer to ATM)
        time_factor_short = np.sqrt(self.diagonal_short_dte / 365)
        short_distance = 0.6 * vol * time_factor_short  # Approx 25 delta
        short_strike = round(spot * (1 - short_distance), 0)

        # Long strike (lower, further OTM)
        time_factor_long = np.sqrt(self.diagonal_long_dte / 365)
        long_distance = 0.9 * vol * time_factor_long  # Approx 15 delta
        long_strike = round(spot * (1 - long_distance), 0)

        return short_strike, long_strike

    def open_diagonal_spread(
        self,
        date: str,
        spot: float,
        vol: float,
        iv_rank: float
    ) -> Optional[DiagonalSpreadTrade]:
        """
        Open a diagonal put spread position.

        Returns:
            DiagonalSpreadTrade if opened, None otherwise
        """
        # Check if we have room for more diagonals
        if len(self.active_diagonals) >= self.max_diagonal_positions:
            return None

        # Select strikes
        short_strike, long_strike = self.select_diagonal_strikes(spot, vol)

        # Get premiums
        short_premium, long_premium = self.estimate_diagonal_premiums(
            spot, vol, short_strike, long_strike
        )

        net_credit = short_premium - long_premium

        if net_credit <= 0:
            return None  # Don't open if no net credit

        # Calculate expiry dates
        entry_dt = datetime.strptime(date, "%Y-%m-%d")
        short_expiry = (entry_dt + timedelta(days=self.diagonal_short_dte)).strftime("%Y-%m-%d")
        long_expiry = (entry_dt + timedelta(days=self.diagonal_long_dte)).strftime("%Y-%m-%d")

        self.diagonal_id += 1
        spread = DiagonalSpreadTrade(
            spread_id=self.diagonal_id,
            entry_date=date,
            exit_date=None,
            short_strike=short_strike,
            short_premium=short_premium,
            short_dte=self.diagonal_short_dte,
            short_expiry=short_expiry,
            long_strike=long_strike,
            long_premium=long_premium,
            long_dte=self.diagonal_long_dte,
            long_expiry=long_expiry,
            net_credit=net_credit,
            max_risk=(short_strike - long_strike) * 100 - net_credit,
            underlying_at_entry=spot,
            iv_at_entry=vol,
            status="OPEN"
        )

        self.active_diagonals.append(spread)
        return spread

    def process_diagonal_expirations(self, date: str, spot: float, vol: float) -> List[Trade]:
        """
        Process diagonal spread expirations and returns.

        Returns:
            List of Trade records for closed diagonals
        """
        trades = []
        current_dt = datetime.strptime(date, "%Y-%m-%d")

        for spread in self.active_diagonals[:]:  # Copy list for safe removal
            short_expiry_dt = datetime.strptime(spread.short_expiry, "%Y-%m-%d")

            # Check if short leg expired
            if current_dt >= short_expiry_dt:
                # Calculate P&L on short leg
                if spot >= spread.short_strike:
                    # Short put expired worthless - keep full premium
                    short_pnl = spread.short_premium
                else:
                    # Short put ITM - lose intrinsic
                    short_pnl = spread.short_premium - (spread.short_strike - spot) * 100

                # Estimate remaining value of long leg
                days_remaining = (datetime.strptime(spread.long_expiry, "%Y-%m-%d") - current_dt).days
                if days_remaining > 0:
                    long_value = self.estimate_put_premium(
                        spot, spread.long_strike, days_remaining, vol
                    )
                else:
                    # Long leg also expired
                    long_value = max(0, (spread.long_strike - spot) * 100)

                # Total P&L = short leg P&L + long leg value - long leg cost
                spread.pnl = short_pnl + long_value - spread.long_premium
                spread.pnl_pct = (spread.pnl / spread.max_risk) * 100 if spread.max_risk > 0 else 0
                spread.exit_date = date
                spread.status = "CLOSED"

                # Create trade record
                trade = Trade(
                    entry_date=spread.entry_date,
                    exit_date=date,
                    symbol=self.symbol,
                    strategy="DIAGONAL_PUT_SPREAD",
                    direction="NEUTRAL",
                    entry_price=spread.short_strike,
                    exit_price=spot,
                    position_size=spread.max_risk,
                    commission=spread.max_risk * (self.commission_pct / 100) * 2,
                    slippage=spread.max_risk * (self.slippage_pct / 100),
                    pnl_percent=spread.pnl_pct,
                    pnl_dollars=spread.pnl,
                    duration_days=(current_dt - datetime.strptime(spread.entry_date, "%Y-%m-%d")).days,
                    win=(spread.pnl > 0),
                    notes=f"Diagonal {spread.short_strike}/{spread.long_strike}"
                )
                trades.append(trade)

                self.active_diagonals.remove(spread)
                self.diagonal_trades.append(spread)

                print(f"[{date}] DIAGONAL CLOSED: {spread.short_strike}/{spread.long_strike} "
                      f"P&L: ${spread.pnl:.2f} ({spread.pnl_pct:.1f}%)")

        return trades

    def run_backtest(self) -> BacktestResults:
        """
        Run combined wheel + diagonal backtest.

        Overrides parent to add diagonal spread logic.
        """
        print(f"\n{'='*70}")
        print("COMBINED WHEEL + DIAGONAL BACKTEST")
        print(f"{'='*70}")
        print(f"Symbol: {self.symbol}")
        print(f"Period: {self.start_date} to {self.end_date}")
        print(f"CSP Delta: {self.csp_delta} | CC Delta: {self.cc_delta}")
        print(f"Diagonal Hedge: {'ENABLED' if self.enable_diagonal else 'DISABLED'}")
        if self.enable_diagonal:
            print(f"  IV Threshold: {self.iv_threshold*100:.0f}%")
            print(f"  Max Diagonal Positions: {self.max_diagonal_positions}")
        print(f"{'='*70}\n")

        # Fetch price data
        self.fetch_historical_data()

        # Calculate historical volatility
        self.price_data['HV'] = self.estimate_historical_volatility(self.price_data)

        # Track state
        in_csp = False
        holding_shares = False
        current_cycle: WheelCycleTrade = None
        csp_entry_idx = 0
        cc_entry_idx = 0
        cc_count = 0

        all_trades: List[Trade] = []

        i = 50  # Start after volatility lookback

        while i < len(self.price_data) - self.csp_dte:
            row = self.price_data.iloc[i]
            current_date = row.name.strftime('%Y-%m-%d')
            current_price = row['Close']
            current_vol = row['HV']

            # Calculate IV rank
            iv_series = self.price_data['HV'].iloc[:i+1]
            iv_rank = self.calculate_iv_rank(current_vol, iv_series)

            # === DIAGONAL LOGIC ===
            if self.enable_diagonal:
                # Process diagonal expirations
                diagonal_trades = self.process_diagonal_expirations(
                    current_date, current_price, current_vol
                )
                all_trades.extend(diagonal_trades)

                # Check if we should open new diagonal
                if iv_rank >= self.iv_threshold:
                    spread = self.open_diagonal_spread(
                        current_date, current_price, current_vol, iv_rank
                    )
                    if spread:
                        print(f"[{current_date}] OPEN DIAGONAL: {spread.short_strike}/{spread.long_strike} "
                              f"Net Credit: ${spread.net_credit:.2f} (IV Rank: {iv_rank*100:.0f}%)")

            # === ORIGINAL WHEEL LOGIC (from parent) ===
            # STATE 1: Not in any position - look to sell CSP
            if not in_csp and not holding_shares:
                csp_strike = self.select_csp_strike(current_price, current_vol)
                csp_premium = self.estimate_put_premium(
                    current_price, csp_strike, self.csp_dte, current_vol
                )

                self.current_cycle_id += 1
                expiration_idx = min(i + self.csp_dte, len(self.price_data) - 1)
                exp_date = self.price_data.iloc[expiration_idx].name.strftime('%Y-%m-%d')

                current_cycle = WheelCycleTrade(
                    cycle_id=self.current_cycle_id,
                    symbol=self.symbol,
                    start_date=current_date,
                    end_date=None,
                    csp_strike=csp_strike,
                    csp_premium=csp_premium,
                    csp_expiration=exp_date,
                    csp_outcome='PENDING'
                )

                in_csp = True
                csp_entry_idx = i
                cc_count = 0

                print(f"[{current_date}] SELL CSP: Strike ${csp_strike:.0f}, "
                      f"Premium ${csp_premium:.2f} (Spot: ${current_price:.2f})")

                i = expiration_idx
                continue

            # STATE 2: CSP expiration day
            if in_csp and not holding_shares:
                expiration_price = current_price

                if expiration_price >= current_cycle.csp_strike:
                    # CSP expired OTM
                    current_cycle.csp_outcome = 'EXPIRED_OTM'
                    current_cycle.end_date = current_date
                    current_cycle.total_premium_collected = (
                        current_cycle.csp_premium * self.contracts * self.shares_per_contract
                    )
                    current_cycle.total_pnl = current_cycle.total_premium_collected

                    capital_at_risk = current_cycle.csp_strike * self.contracts * self.shares_per_contract
                    current_cycle.total_pnl_pct = (current_cycle.total_pnl / capital_at_risk) * 100
                    current_cycle.days_in_cycle = (
                        pd.to_datetime(current_date) - pd.to_datetime(current_cycle.start_date)
                    ).days

                    print(f"[{current_date}] CSP EXPIRED OTM: +${current_cycle.total_pnl:.2f} "
                          f"({current_cycle.total_pnl_pct:.2f}%)")

                    trade = Trade(
                        entry_date=current_cycle.start_date,
                        exit_date=current_date,
                        symbol=self.symbol,
                        strategy='WHEEL_CSP',
                        direction='NEUTRAL',
                        entry_price=current_cycle.csp_strike,
                        exit_price=expiration_price,
                        position_size=capital_at_risk,
                        commission=capital_at_risk * (self.commission_pct / 100) * 2,
                        slippage=capital_at_risk * (self.slippage_pct / 100),
                        pnl_percent=current_cycle.total_pnl_pct,
                        pnl_dollars=current_cycle.total_pnl,
                        duration_days=current_cycle.days_in_cycle,
                        win=True,
                        notes=f"CSP ${current_cycle.csp_strike:.0f} expired OTM"
                    )
                    all_trades.append(trade)
                    self.wheel_cycles.append(current_cycle)

                    in_csp = False
                    current_cycle = None
                    i += 1
                    continue

                else:
                    # CSP assigned
                    current_cycle.csp_outcome = 'ASSIGNED'
                    current_cycle.shares_assigned = self.contracts * self.shares_per_contract
                    current_cycle.cost_basis_per_share = (
                        current_cycle.csp_strike - current_cycle.csp_premium
                    )

                    print(f"[{current_date}] CSP ASSIGNED: Bought {current_cycle.shares_assigned} shares "
                          f"at ${current_cycle.csp_strike:.0f}, Cost basis: ${current_cycle.cost_basis_per_share:.2f}")

                    in_csp = False
                    holding_shares = True
                    i += 1
                    continue

            # STATE 3: Holding shares - sell covered call
            if holding_shares and (cc_count == 0 or i >= cc_entry_idx + self.cc_dte):
                if cc_count >= self.max_cc_cycles:
                    # Force exit
                    exit_price = current_price
                    current_cycle.cc_outcome = 'FORCE_EXIT'
                    current_cycle.final_price = exit_price
                    current_cycle.end_date = current_date

                    total_cc_premium = sum(current_cycle.cc_premiums) * current_cycle.shares_assigned
                    csp_premium_total = current_cycle.csp_premium * current_cycle.shares_assigned
                    share_pnl = (exit_price - current_cycle.cost_basis_per_share) * current_cycle.shares_assigned

                    current_cycle.total_premium_collected = csp_premium_total + total_cc_premium
                    current_cycle.capital_appreciation = share_pnl
                    current_cycle.total_pnl = current_cycle.total_premium_collected + share_pnl

                    capital_at_risk = current_cycle.csp_strike * current_cycle.shares_assigned
                    current_cycle.total_pnl_pct = (current_cycle.total_pnl / capital_at_risk) * 100
                    current_cycle.days_in_cycle = (
                        pd.to_datetime(current_date) - pd.to_datetime(current_cycle.start_date)
                    ).days

                    print(f"[{current_date}] FORCE EXIT: Sold shares at ${exit_price:.2f}, "
                          f"Total P&L: ${current_cycle.total_pnl:.2f} ({current_cycle.total_pnl_pct:.2f}%)")

                    trade = Trade(
                        entry_date=current_cycle.start_date,
                        exit_date=current_date,
                        symbol=self.symbol,
                        strategy='WHEEL_FULL_CYCLE',
                        direction='NEUTRAL',
                        entry_price=current_cycle.csp_strike,
                        exit_price=exit_price,
                        position_size=capital_at_risk,
                        commission=capital_at_risk * (self.commission_pct / 100) * 4,
                        slippage=capital_at_risk * (self.slippage_pct / 100) * 2,
                        pnl_percent=current_cycle.total_pnl_pct,
                        pnl_dollars=current_cycle.total_pnl,
                        duration_days=current_cycle.days_in_cycle,
                        win=(current_cycle.total_pnl > 0),
                        notes=f"Full cycle: {cc_count} CCs, force exit"
                    )
                    all_trades.append(trade)
                    self.wheel_cycles.append(current_cycle)

                    holding_shares = False
                    current_cycle = None
                    i += 1
                    continue

                # Sell new covered call
                cc_strike = self.select_cc_strike(
                    current_cycle.cost_basis_per_share,
                    current_price,
                    current_vol
                )
                cc_premium = self.estimate_call_premium(
                    current_price, cc_strike, self.cc_dte, current_vol
                )

                current_cycle.cc_strikes.append(cc_strike)
                current_cycle.cc_premiums.append(cc_premium)
                cc_count += 1
                cc_entry_idx = i

                print(f"[{current_date}] SELL CC #{cc_count}: Strike ${cc_strike:.0f}, "
                      f"Premium ${cc_premium:.2f} (Spot: ${current_price:.2f})")

                exp_idx = min(i + self.cc_dte, len(self.price_data) - 1)
                i = exp_idx
                continue

            # STATE 4: CC expiration
            if holding_shares and i >= cc_entry_idx + self.cc_dte:
                cc_strike = current_cycle.cc_strikes[-1] if current_cycle.cc_strikes else current_price * 1.05
                expiration_price = current_price

                if expiration_price >= cc_strike:
                    # Called away
                    current_cycle.cc_outcome = 'CALLED_AWAY'
                    current_cycle.final_price = cc_strike
                    current_cycle.end_date = current_date

                    total_cc_premium = sum(current_cycle.cc_premiums) * current_cycle.shares_assigned
                    csp_premium_total = current_cycle.csp_premium * current_cycle.shares_assigned
                    share_pnl = (cc_strike - current_cycle.cost_basis_per_share) * current_cycle.shares_assigned

                    current_cycle.total_premium_collected = csp_premium_total + total_cc_premium
                    current_cycle.capital_appreciation = share_pnl
                    current_cycle.total_pnl = current_cycle.total_premium_collected + share_pnl

                    capital_at_risk = current_cycle.csp_strike * current_cycle.shares_assigned
                    current_cycle.total_pnl_pct = (current_cycle.total_pnl / capital_at_risk) * 100
                    current_cycle.days_in_cycle = (
                        pd.to_datetime(current_date) - pd.to_datetime(current_cycle.start_date)
                    ).days

                    print(f"[{current_date}] CALLED AWAY at ${cc_strike:.0f}!")
                    print(f"         Premium: ${current_cycle.total_premium_collected:.2f} + "
                          f"Appreciation: ${share_pnl:.2f} = Total: ${current_cycle.total_pnl:.2f} "
                          f"({current_cycle.total_pnl_pct:.2f}%)")

                    trade = Trade(
                        entry_date=current_cycle.start_date,
                        exit_date=current_date,
                        symbol=self.symbol,
                        strategy='WHEEL_FULL_CYCLE',
                        direction='NEUTRAL',
                        entry_price=current_cycle.csp_strike,
                        exit_price=cc_strike,
                        position_size=capital_at_risk,
                        commission=capital_at_risk * (self.commission_pct / 100) * 4,
                        slippage=capital_at_risk * (self.slippage_pct / 100) * 2,
                        pnl_percent=current_cycle.total_pnl_pct,
                        pnl_dollars=current_cycle.total_pnl,
                        duration_days=current_cycle.days_in_cycle,
                        win=(current_cycle.total_pnl > 0),
                        notes=f"Full cycle: {cc_count} CCs, called away"
                    )
                    all_trades.append(trade)
                    self.wheel_cycles.append(current_cycle)

                    holding_shares = False
                    current_cycle = None

                else:
                    print(f"[{current_date}] CC EXPIRED OTM: Keep premium, sell another CC")

                i += 1
                continue

            i += 1

        # Close any open positions
        self._close_remaining_positions(current_cycle, holding_shares, all_trades)

        # Close any remaining diagonals
        if self.active_diagonals:
            final_row = self.price_data.iloc[-1]
            final_price = final_row['Close']
            final_date = final_row.name.strftime('%Y-%m-%d')
            final_vol = final_row['HV']

            diagonal_trades = self.process_diagonal_expirations(
                final_date, final_price, final_vol
            )
            all_trades.extend(diagonal_trades)

        # Calculate metrics
        results = self.calculate_metrics(all_trades, "WHEEL_DIAGONAL_COMBINED")
        results.data_quality = DataQuality(
            price_data_source='polygon/yfinance',
            gex_data_source='n/a',
            uses_simulated_data=False,
            data_coverage_pct=100.0
        )

        self.print_summary(results)
        self.print_wheel_summary()
        self.print_diagonal_summary()

        return results

    def _close_remaining_positions(
        self,
        current_cycle: Optional[WheelCycleTrade],
        holding_shares: bool,
        all_trades: List[Trade]
    ):
        """Close any open wheel positions at end of backtest."""
        if current_cycle is None:
            return

        final_row = self.price_data.iloc[-1]
        final_price = final_row['Close']
        final_date = final_row.name.strftime('%Y-%m-%d')

        if holding_shares:
            current_cycle.cc_outcome = 'END_OF_DATA'
            current_cycle.final_price = final_price
            current_cycle.end_date = final_date

            total_cc_premium = sum(current_cycle.cc_premiums) * current_cycle.shares_assigned
            csp_premium_total = current_cycle.csp_premium * current_cycle.shares_assigned
            share_pnl = (final_price - current_cycle.cost_basis_per_share) * current_cycle.shares_assigned

            current_cycle.total_premium_collected = csp_premium_total + total_cc_premium
            current_cycle.capital_appreciation = share_pnl
            current_cycle.total_pnl = current_cycle.total_premium_collected + share_pnl

            capital_at_risk = current_cycle.csp_strike * current_cycle.shares_assigned
            current_cycle.total_pnl_pct = (current_cycle.total_pnl / capital_at_risk) * 100

            trade = Trade(
                entry_date=current_cycle.start_date,
                exit_date=final_date,
                symbol=self.symbol,
                strategy='WHEEL_INCOMPLETE',
                direction='NEUTRAL',
                entry_price=current_cycle.csp_strike,
                exit_price=final_price,
                position_size=capital_at_risk,
                commission=capital_at_risk * (self.commission_pct / 100) * 4,
                slippage=capital_at_risk * (self.slippage_pct / 100) * 2,
                pnl_percent=current_cycle.total_pnl_pct,
                pnl_dollars=current_cycle.total_pnl,
                duration_days=(pd.to_datetime(final_date) - pd.to_datetime(current_cycle.start_date)).days,
                win=(current_cycle.total_pnl > 0),
                notes="End of data exit"
            )
            all_trades.append(trade)
            self.wheel_cycles.append(current_cycle)

    def print_diagonal_summary(self):
        """Print diagonal spread specific summary."""
        if not self.diagonal_trades:
            print("\nNo diagonal spreads traded")
            return

        print("\n" + "=" * 70)
        print("DIAGONAL PUT SPREAD SUMMARY")
        print("=" * 70)

        total = len(self.diagonal_trades)
        winners = sum(1 for d in self.diagonal_trades if d.pnl > 0)
        losers = total - winners

        total_pnl = sum(d.pnl for d in self.diagonal_trades)
        avg_pnl = total_pnl / total if total > 0 else 0

        avg_iv_at_entry = np.mean([d.iv_at_entry for d in self.diagonal_trades])

        print(f"Total Diagonal Spreads: {total}")
        print(f"  Winners: {winners} ({winners/total*100:.1f}%)")
        print(f"  Losers: {losers} ({losers/total*100:.1f}%)")
        print()
        print(f"Total P&L: ${total_pnl:,.2f}")
        print(f"Average P&L: ${avg_pnl:.2f}")
        print(f"Average IV at Entry: {avg_iv_at_entry*100:.1f}%")
        print("=" * 70 + "\n")

    def generate_strategy_report(self) -> StrategyReport:
        """
        Generate institutional-quality report using StrategyReportGenerator.

        Returns:
            StrategyReport with complete statistics
        """
        gen = StrategyReportGenerator(
            strategy_name="Combined Wheel + Diagonal Put Spread",
            symbol=self.symbol,
            initial_capital=self.initial_capital,
            start_date=self.start_date,
            end_date=self.end_date
        )

        # Add wheel trades
        for i, cycle in enumerate(self.wheel_cycles):
            gen.add_trade(
                trade_id=i + 1,
                entry_date=cycle.start_date,
                exit_date=cycle.end_date or self.end_date,
                direction="SHORT_PUT" if cycle.csp_outcome == 'EXPIRED_OTM' else "WHEEL_CYCLE",
                entry_price=cycle.csp_strike,
                exit_price=cycle.final_price if cycle.final_price else cycle.csp_strike,
                contracts=self.contracts,
                pnl=cycle.total_pnl,
                price_source="POLYGON_HISTORICAL"
            )

        # Add diagonal trades
        for i, diag in enumerate(self.diagonal_trades):
            gen.add_trade(
                trade_id=len(self.wheel_cycles) + i + 1,
                entry_date=diag.entry_date,
                exit_date=diag.exit_date or self.end_date,
                direction="DIAGONAL_PUT_SPREAD",
                entry_price=diag.short_strike,
                exit_price=diag.long_strike,
                contracts=1,
                pnl=diag.pnl,
                price_source="POLYGON_HISTORICAL"
            )

        return gen.generate()


def run_diagonal_wheel_backtest(
    symbol: str = "SPY",
    start_date: str = "2022-01-01",
    end_date: str = "2024-12-31",
    enable_diagonal: bool = True,
    iv_threshold: float = 0.50
) -> Tuple[BacktestResults, Optional[StrategyReport]]:
    """
    Convenience function to run combined backtest.

    Returns:
        Tuple of (BacktestResults, StrategyReport)
    """
    backtester = DiagonalWheelBacktester(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        enable_diagonal_hedge=enable_diagonal,
        iv_threshold=iv_threshold,
        initial_capital=50000,
        position_size_pct=100,
        commission_pct=0.10,
        slippage_pct=0.15
    )

    results = backtester.run_backtest()
    report = backtester.generate_strategy_report()

    return results, report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Backtest wheel + diagonal strategy')
    parser.add_argument('--symbol', default='SPY', help='Symbol to backtest')
    parser.add_argument('--start', default='2022-01-01', help='Start date YYYY-MM-DD')
    parser.add_argument('--end', default='2024-12-31', help='End date YYYY-MM-DD')
    parser.add_argument('--no-diagonal', action='store_true', help='Disable diagonal hedge')
    parser.add_argument('--iv-threshold', type=float, default=0.50, help='IV rank threshold')
    args = parser.parse_args()

    results, report = run_diagonal_wheel_backtest(
        symbol=args.symbol,
        start_date=args.start,
        end_date=args.end,
        enable_diagonal=not args.no_diagonal,
        iv_threshold=args.iv_threshold
    )

    print("\n" + "=" * 70)
    print("STRATEGY REPORT")
    print("=" * 70)
    print_strategy_report(report)
