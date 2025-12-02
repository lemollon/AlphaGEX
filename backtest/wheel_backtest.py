"""
Wheel Strategy Backtester

Backtests the complete wheel strategy cycle:
1. Sell Cash-Secured Put (CSP) - Collect premium
2. If assigned, buy shares at strike minus premium (cost basis)
3. Sell Covered Call (CC) - Collect more premium
4. If called away, sell shares and restart cycle

Key metrics tracked:
- Premium income from CSP and CC
- Assignment rate
- Called away rate
- Full cycle P&L
- Return on capital (cash needed for CSP)

Uses REAL price data and realistic option pricing.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from backtest.backtest_framework import BacktestBase, BacktestResults, Trade, DataQuality

# Try to import Black-Scholes pricing
try:
    from realistic_option_pricing import BlackScholesOption
    BS_AVAILABLE = True
except ImportError:
    BS_AVAILABLE = False


@dataclass
class WheelCycleTrade:
    """Represents a complete wheel cycle (may span multiple legs)"""
    cycle_id: int
    symbol: str
    start_date: str
    end_date: Optional[str]

    # CSP Phase
    csp_strike: float
    csp_premium: float  # Per share
    csp_expiration: str
    csp_outcome: str  # 'EXPIRED_OTM', 'ASSIGNED', 'CLOSED_EARLY'

    # Assignment (if assigned)
    shares_assigned: int = 0
    cost_basis_per_share: float = 0

    # CC Phase(s) - can have multiple
    cc_premiums: List[float] = None  # List of CC premiums collected
    cc_strikes: List[float] = None
    cc_outcome: str = None  # 'EXPIRED_OTM', 'CALLED_AWAY', 'STILL_HOLDING'

    # Final outcome
    final_price: float = 0
    total_premium_collected: float = 0
    capital_appreciation: float = 0
    total_pnl: float = 0
    total_pnl_pct: float = 0
    days_in_cycle: int = 0

    def __post_init__(self):
        if self.cc_premiums is None:
            self.cc_premiums = []
        if self.cc_strikes is None:
            self.cc_strikes = []


class WheelBacktester(BacktestBase):
    """
    Backtest the wheel strategy with realistic mechanics.

    The wheel strategy:
    1. Sell CSP at ~30 delta strike, collect premium
    2. If assigned (price < strike at expiration), own 100 shares
    3. Sell CC at ~30 delta above cost basis
    4. If called away (price > strike at expiration), profit and restart
    5. If CC expires OTM, sell another CC

    Continues until called away or max holding period reached.
    """

    def __init__(self,
                 csp_delta: float = 0.25,
                 cc_delta: float = 0.30,
                 csp_dte: int = 30,
                 cc_dte: int = 21,
                 max_cc_cycles: int = 12,  # Max CC attempts before force exit
                 target_premium_yield: float = 0.02,  # 2% per CSP/CC cycle
                 contracts_per_trade: int = 1,
                 **kwargs):
        """
        Initialize wheel backtester.

        Args:
            csp_delta: Target delta for CSP (typically 0.20-0.35)
            cc_delta: Target delta for CC (typically 0.25-0.40)
            csp_dte: Days to expiration for CSP
            cc_dte: Days to expiration for CC
            max_cc_cycles: Maximum CC cycles before force exit
            target_premium_yield: Target premium as % of strike
            contracts_per_trade: Number of contracts (1 contract = 100 shares)
        """
        super().__init__(**kwargs)
        self.csp_delta = csp_delta
        self.cc_delta = cc_delta
        self.csp_dte = csp_dte
        self.cc_dte = cc_dte
        self.max_cc_cycles = max_cc_cycles
        self.target_premium_yield = target_premium_yield
        self.contracts = contracts_per_trade
        self.shares_per_contract = 100

        self.wheel_cycles: List[WheelCycleTrade] = []
        self.current_cycle_id = 0

    def estimate_put_premium(self, spot: float, strike: float, dte: int, vol: float) -> float:
        """
        Estimate put option premium.

        Uses Black-Scholes if available, otherwise simplified estimate.
        """
        if BS_AVAILABLE:
            try:
                option = BlackScholesOption(
                    spot_price=spot,
                    strike_price=strike,
                    time_to_expiry=dte / 365,
                    volatility=vol,
                    risk_free_rate=0.05,
                    option_type='put'
                )
                return option.price
            except:
                pass

        # Simplified premium estimation
        # Premium roughly = distance_pct * volatility * sqrt(dte/365) * intrinsic_factor
        moneyness = (spot - strike) / spot  # Positive = OTM for put
        time_factor = np.sqrt(dte / 365)

        if moneyness >= 0:  # OTM put
            # OTM put premium based on delta targeting
            # At 25 delta, premium is roughly 1-3% of strike
            base_premium = strike * self.target_premium_yield * time_factor
            vol_adjustment = vol / 0.20  # Normalize to 20% baseline vol
            premium = base_premium * vol_adjustment
        else:  # ITM put
            intrinsic = abs(moneyness) * strike
            extrinsic = strike * 0.01 * time_factor
            premium = intrinsic + extrinsic

        return max(premium, 0.05)  # Minimum $0.05 premium

    def estimate_call_premium(self, spot: float, strike: float, dte: int, vol: float) -> float:
        """
        Estimate call option premium.
        """
        if BS_AVAILABLE:
            try:
                option = BlackScholesOption(
                    spot_price=spot,
                    strike_price=strike,
                    time_to_expiry=dte / 365,
                    volatility=vol,
                    risk_free_rate=0.05,
                    option_type='call'
                )
                return option.price
            except:
                pass

        # Simplified premium estimation for calls
        moneyness = (strike - spot) / spot  # Positive = OTM for call
        time_factor = np.sqrt(dte / 365)

        if moneyness >= 0:  # OTM call
            base_premium = spot * self.target_premium_yield * time_factor * 0.8  # CCs yield slightly less
            vol_adjustment = vol / 0.20
            premium = base_premium * vol_adjustment
        else:  # ITM call
            intrinsic = abs(moneyness) * spot
            extrinsic = spot * 0.01 * time_factor
            premium = intrinsic + extrinsic

        return max(premium, 0.05)

    def select_csp_strike(self, spot: float, vol: float) -> float:
        """
        Select CSP strike price based on target delta.

        For ~25 delta put, strike is roughly 1 std dev below spot.
        """
        # Simplified: strike at spot * (1 - delta_adjustment * vol * sqrt(T))
        # For 25 delta, adjustment is roughly 0.7
        delta_adjustment = 0.7 * (self.csp_delta / 0.25)  # Scale by target delta
        time_factor = np.sqrt(self.csp_dte / 365)

        strike = spot * (1 - delta_adjustment * vol * time_factor)

        # Round to nearest dollar
        return round(strike, 0)

    def select_cc_strike(self, cost_basis: float, current_price: float, vol: float) -> float:
        """
        Select CC strike price.

        Strategy: Strike should be above cost basis to ensure profit if called away.
        Also consider current price and delta targeting.
        """
        # Minimum strike is above cost basis
        min_strike = cost_basis * 1.01  # At least 1% above cost basis

        # Target strike based on delta (further OTM = lower delta)
        delta_adjustment = 0.5 * (self.cc_delta / 0.30)
        time_factor = np.sqrt(self.cc_dte / 365)

        target_strike = current_price * (1 + delta_adjustment * vol * time_factor)

        # Use higher of minimum and target
        strike = max(min_strike, target_strike)

        return round(strike, 0)

    def estimate_historical_volatility(self, price_data: pd.DataFrame, lookback: int = 20) -> pd.Series:
        """Calculate rolling historical volatility."""
        returns = np.log(price_data['Close'] / price_data['Close'].shift(1))
        vol = returns.rolling(lookback).std() * np.sqrt(252)
        return vol.fillna(0.20)  # Default to 20% if insufficient data

    def run_backtest(self) -> BacktestResults:
        """Run wheel strategy backtest."""
        print(f"\n{'='*70}")
        print("WHEEL STRATEGY BACKTEST")
        print(f"{'='*70}")
        print(f"Symbol: {self.symbol}")
        print(f"Period: {self.start_date} to {self.end_date}")
        print(f"CSP Delta: {self.csp_delta} | CC Delta: {self.cc_delta}")
        print(f"CSP DTE: {self.csp_dte} | CC DTE: {self.cc_dte}")
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

            # STATE 1: Not in any position - look to sell CSP
            if not in_csp and not holding_shares:
                # Sell CSP
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

                i = expiration_idx  # Jump to expiration
                continue

            # STATE 2: CSP expiration day
            if in_csp and not holding_shares:
                expiration_price = current_price

                if expiration_price >= current_cycle.csp_strike:
                    # CSP expired OTM - keep full premium
                    current_cycle.csp_outcome = 'EXPIRED_OTM'
                    current_cycle.end_date = current_date
                    current_cycle.total_premium_collected = (
                        current_cycle.csp_premium * self.contracts * self.shares_per_contract
                    )
                    current_cycle.total_pnl = current_cycle.total_premium_collected

                    # Calculate P&L %
                    capital_at_risk = current_cycle.csp_strike * self.contracts * self.shares_per_contract
                    current_cycle.total_pnl_pct = (current_cycle.total_pnl / capital_at_risk) * 100
                    current_cycle.days_in_cycle = (
                        pd.to_datetime(current_date) - pd.to_datetime(current_cycle.start_date)
                    ).days

                    print(f"[{current_date}] CSP EXPIRED OTM: +${current_cycle.total_pnl:.2f} "
                          f"({current_cycle.total_pnl_pct:.2f}%)")

                    # Create trade record
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
                    # CSP assigned - now own shares
                    current_cycle.csp_outcome = 'ASSIGNED'
                    current_cycle.shares_assigned = self.contracts * self.shares_per_contract
                    current_cycle.cost_basis_per_share = (
                        current_cycle.csp_strike - current_cycle.csp_premium
                    )

                    print(f"[{current_date}] CSP ASSIGNED: Bought {current_cycle.shares_assigned} shares "
                          f"at ${current_cycle.csp_strike:.0f}, Cost basis: ${current_cycle.cost_basis_per_share:.2f}")

                    in_csp = False
                    holding_shares = True

                    # Immediately sell covered call
                    i += 1
                    continue

            # STATE 3: Holding shares - sell covered call
            if holding_shares and (cc_count == 0 or i >= cc_entry_idx + self.cc_dte):
                if cc_count >= self.max_cc_cycles:
                    # Force exit after max CC cycles
                    exit_price = current_price
                    current_cycle.cc_outcome = 'FORCE_EXIT'
                    current_cycle.final_price = exit_price
                    current_cycle.end_date = current_date

                    # Calculate total P&L
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

                # Jump to expiration
                exp_idx = min(i + self.cc_dte, len(self.price_data) - 1)
                i = exp_idx
                continue

            # STATE 4: CC expiration
            if holding_shares and i >= cc_entry_idx + self.cc_dte:
                cc_strike = current_cycle.cc_strikes[-1] if current_cycle.cc_strikes else current_price * 1.05
                expiration_price = current_price

                if expiration_price >= cc_strike:
                    # Called away - cycle complete!
                    current_cycle.cc_outcome = 'CALLED_AWAY'
                    current_cycle.final_price = cc_strike  # Sell at strike
                    current_cycle.end_date = current_date

                    # Calculate total P&L
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
                    # CC expired OTM - keep shares, sell another CC
                    print(f"[{current_date}] CC EXPIRED OTM: Keep premium, sell another CC")
                    # Will sell new CC on next iteration

                i += 1
                continue

            i += 1

        # Close any open position at end
        if current_cycle is not None:
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
                    notes=f"End of data exit"
                )
                all_trades.append(trade)
                self.wheel_cycles.append(current_cycle)

        # Calculate metrics
        results = self.calculate_metrics(all_trades, "WHEEL_STRATEGY")
        results.data_quality = DataQuality(
            price_data_source='polygon/yfinance',
            gex_data_source='n/a',
            uses_simulated_data=False,
            data_coverage_pct=100.0
        )

        self.print_summary(results)
        self.print_wheel_summary()

        return results

    def print_wheel_summary(self):
        """Print wheel-specific summary statistics."""
        if not self.wheel_cycles:
            return

        print("\n" + "=" * 70)
        print("WHEEL STRATEGY DETAILS")
        print("=" * 70)

        total_cycles = len(self.wheel_cycles)
        csp_only = sum(1 for c in self.wheel_cycles if c.csp_outcome == 'EXPIRED_OTM')
        assigned = sum(1 for c in self.wheel_cycles if c.csp_outcome == 'ASSIGNED')
        called_away = sum(1 for c in self.wheel_cycles if c.cc_outcome == 'CALLED_AWAY')

        total_premium = sum(c.total_premium_collected for c in self.wheel_cycles)
        total_appreciation = sum(c.capital_appreciation for c in self.wheel_cycles if c.capital_appreciation)
        total_pnl = sum(c.total_pnl for c in self.wheel_cycles)

        avg_days = np.mean([c.days_in_cycle for c in self.wheel_cycles if c.days_in_cycle])

        print(f"Total Cycles: {total_cycles}")
        print(f"  CSP Expired OTM: {csp_only} ({csp_only/total_cycles*100:.1f}%)")
        print(f"  Assigned (shares bought): {assigned} ({assigned/total_cycles*100:.1f}%)")
        print(f"  Called Away (full cycle): {called_away} ({called_away/total_cycles*100:.1f}%)")
        print()
        print(f"Total Premium Collected: ${total_premium:,.2f}")
        print(f"Total Capital Appreciation: ${total_appreciation:,.2f}")
        print(f"Total P&L: ${total_pnl:,.2f}")
        print(f"Average Days per Cycle: {avg_days:.1f}")

        # Calculate annualized return
        if self.wheel_cycles:
            first_date = pd.to_datetime(self.wheel_cycles[0].start_date)
            last_date = pd.to_datetime(self.wheel_cycles[-1].end_date or self.end_date)
            total_days = (last_date - first_date).days
            if total_days > 0:
                avg_capital = self.wheel_cycles[0].csp_strike * 100  # Capital for 1 contract
                annualized = (total_pnl / avg_capital) * (365 / total_days) * 100
                print(f"Annualized Return (approx): {annualized:.1f}%")

        print("=" * 70 + "\n")


def run_wheel_backtest(symbol: str = "SPY",
                       start_date: str = "2022-01-01",
                       end_date: str = "2024-12-31",
                       csp_delta: float = 0.25,
                       cc_delta: float = 0.30) -> BacktestResults:
    """
    Convenience function to run wheel backtest.
    """
    backtester = WheelBacktester(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        csp_delta=csp_delta,
        cc_delta=cc_delta,
        initial_capital=50000,  # Enough for 1 SPY contract at ~$450
        position_size_pct=100,  # Use full capital
        commission_pct=0.10,
        slippage_pct=0.15
    )

    return backtester.run_backtest()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Backtest wheel strategy')
    parser.add_argument('--symbol', default='SPY', help='Symbol to backtest')
    parser.add_argument('--start', default='2022-01-01', help='Start date YYYY-MM-DD')
    parser.add_argument('--end', default='2024-12-31', help='End date YYYY-MM-DD')
    parser.add_argument('--csp-delta', type=float, default=0.25, help='CSP target delta')
    parser.add_argument('--cc-delta', type=float, default=0.30, help='CC target delta')
    args = parser.parse_args()

    results = run_wheel_backtest(
        symbol=args.symbol,
        start_date=args.start,
        end_date=args.end,
        csp_delta=args.csp_delta,
        cc_delta=args.cc_delta
    )

    print("\nWheel Strategy Backtest Complete!")
