#!/usr/bin/env python3
"""
Standalone Wheel Strategy Backtest
===================================
Runs a complete wheel strategy backtest without external API dependencies.
Uses simulated realistic price data for SPY-like behavior.

Usage:
    python scripts/run_wheel_backtest_standalone.py
    python scripts/run_wheel_backtest_standalone.py --symbol SPY --days 365 --initial-price 450
"""

import numpy as np
import argparse
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class WheelCycle:
    """Represents a complete wheel cycle"""
    cycle_id: int
    start_date: str
    end_date: Optional[str] = None

    # CSP Phase
    csp_strike: float = 0
    csp_premium: float = 0
    csp_expiration: str = ""
    csp_outcome: str = ""  # EXPIRED_OTM, ASSIGNED

    # Assignment
    shares_assigned: int = 0
    cost_basis: float = 0

    # CC Phase(s)
    cc_strikes: List[float] = field(default_factory=list)
    cc_premiums: List[float] = field(default_factory=list)
    cc_outcome: str = ""

    # Final
    total_premium: float = 0
    capital_gain: float = 0
    total_pnl: float = 0
    days_in_cycle: int = 0


def generate_realistic_prices(symbol: str, days: int, initial_price: float,
                              annual_return: float = 0.10,
                              annual_volatility: float = 0.18) -> List[dict]:
    """
    Generate realistic stock price data with realistic market behavior.

    Uses geometric Brownian motion with:
    - Mean reversion tendencies
    - Occasional volatility spikes
    - Realistic daily moves
    """
    np.random.seed(42)  # For reproducibility

    daily_return = annual_return / 252
    daily_vol = annual_volatility / np.sqrt(252)

    prices = [initial_price]
    dates = []

    start = datetime(2023, 1, 3)  # Start on a trading day
    current_date = start

    for i in range(days):
        # Skip weekends
        while current_date.weekday() >= 5:
            current_date += timedelta(days=1)

        dates.append(current_date.strftime('%Y-%m-%d'))

        if i > 0:
            # Add occasional volatility spikes (market stress)
            vol_multiplier = 1.0
            if np.random.random() < 0.02:  # 2% chance of high vol day
                vol_multiplier = 2.5

            # Daily return with drift and random walk
            daily_change = np.random.normal(daily_return, daily_vol * vol_multiplier)
            new_price = prices[-1] * (1 + daily_change)
            prices.append(max(new_price, prices[-1] * 0.9))  # Floor at 10% down

        current_date += timedelta(days=1)

    data = []
    for i, (date, close) in enumerate(zip(dates, prices)):
        # Generate OHLC from close
        daily_range = close * daily_vol
        high = close + abs(np.random.normal(0, daily_range/2))
        low = close - abs(np.random.normal(0, daily_range/2))
        open_price = prices[i-1] if i > 0 else close

        data.append({
            'date': date,
            'open': open_price,
            'high': max(high, open_price, close),
            'low': min(low, open_price, close),
            'close': close,
            'volume': int(np.random.normal(50_000_000, 10_000_000))
        })

    return data


def estimate_put_premium(spot: float, strike: float, dte: int, vol: float) -> float:
    """Estimate put premium using simplified Black-Scholes approximation."""
    moneyness = (spot - strike) / spot
    time_factor = np.sqrt(dte / 365)

    if moneyness >= 0:  # OTM put
        # Premium decreases as strike moves further OTM
        otm_pct = moneyness
        base_premium = strike * 0.02 * time_factor  # ~2% for ATM monthly
        otm_discount = np.exp(-otm_pct * 10)  # Decay faster for further OTM
        premium = base_premium * otm_discount * (vol / 0.18)
    else:  # ITM put
        intrinsic = abs(strike - spot)
        extrinsic = spot * 0.01 * time_factor
        premium = intrinsic + extrinsic

    return max(premium, 0.10)


def estimate_call_premium(spot: float, strike: float, dte: int, vol: float) -> float:
    """Estimate call premium using simplified Black-Scholes approximation."""
    moneyness = (strike - spot) / spot
    time_factor = np.sqrt(dte / 365)

    if moneyness >= 0:  # OTM call
        otm_pct = moneyness
        base_premium = spot * 0.015 * time_factor  # Calls slightly cheaper
        otm_discount = np.exp(-otm_pct * 10)
        premium = base_premium * otm_discount * (vol / 0.18)
    else:  # ITM call
        intrinsic = abs(spot - strike)
        extrinsic = spot * 0.01 * time_factor
        premium = intrinsic + extrinsic

    return max(premium, 0.10)


def calculate_historical_vol(prices: List[float], lookback: int = 20) -> float:
    """Calculate rolling historical volatility."""
    if len(prices) < lookback:
        return 0.18  # Default volatility

    recent = prices[-lookback:]
    returns = [np.log(recent[i]/recent[i-1]) for i in range(1, len(recent))]
    return np.std(returns) * np.sqrt(252)


class WheelBacktester:
    """
    Backtests the wheel strategy (CSP -> assignment -> covered calls).
    """

    def __init__(self,
                 symbol: str = "SPY",
                 csp_delta: float = 0.25,
                 cc_delta: float = 0.30,
                 csp_dte: int = 30,
                 cc_dte: int = 21,
                 contracts: int = 1,
                 max_cc_cycles: int = 12):
        self.symbol = symbol
        self.csp_delta = csp_delta
        self.cc_delta = cc_delta
        self.csp_dte = csp_dte
        self.cc_dte = cc_dte
        self.contracts = contracts
        self.shares = contracts * 100
        self.max_cc_cycles = max_cc_cycles

        self.cycles: List[WheelCycle] = []
        self.cycle_id = 0

    def select_csp_strike(self, spot: float, vol: float) -> float:
        """Select CSP strike based on target delta (~25 delta = 1 std dev OTM)."""
        delta_adjustment = 0.7 * (self.csp_delta / 0.25)
        time_factor = np.sqrt(self.csp_dte / 365)
        strike = spot * (1 - delta_adjustment * vol * time_factor)
        return round(strike, 0)

    def select_cc_strike(self, cost_basis: float, current_price: float, vol: float) -> float:
        """Select CC strike above cost basis."""
        min_strike = cost_basis * 1.01
        delta_adjustment = 0.5 * (self.cc_delta / 0.30)
        time_factor = np.sqrt(self.cc_dte / 365)
        target_strike = current_price * (1 + delta_adjustment * vol * time_factor)
        return round(max(min_strike, target_strike), 0)

    def run_backtest(self, price_data: List[dict]) -> dict:
        """Run the wheel strategy backtest."""
        print("\n" + "=" * 70)
        print("WHEEL STRATEGY BACKTEST (Standalone)")
        print("=" * 70)
        print(f"Symbol: {self.symbol}")
        print(f"Period: {price_data[0]['date']} to {price_data[-1]['date']}")
        print(f"CSP Delta: {self.csp_delta} | CC Delta: {self.cc_delta}")
        print(f"CSP DTE: {self.csp_dte} | CC DTE: {self.cc_dte}")
        print(f"Contracts: {self.contracts} ({self.shares} shares)")
        print("=" * 70 + "\n")

        prices = [d['close'] for d in price_data]

        # State tracking
        in_csp = False
        holding_shares = False
        current_cycle: Optional[WheelCycle] = None
        csp_exp_idx = 0
        cc_exp_idx = 0
        cc_count = 0

        i = 50  # Start after lookback period

        while i < len(price_data) - self.csp_dte:
            row = price_data[i]
            current_date = row['date']
            current_price = row['close']
            current_vol = calculate_historical_vol(prices[:i+1])

            # STATE 1: Not in position - sell CSP
            if not in_csp and not holding_shares:
                csp_strike = self.select_csp_strike(current_price, current_vol)
                csp_premium = estimate_put_premium(current_price, csp_strike,
                                                   self.csp_dte, current_vol)

                self.cycle_id += 1
                exp_idx = min(i + self.csp_dte, len(price_data) - 1)

                current_cycle = WheelCycle(
                    cycle_id=self.cycle_id,
                    start_date=current_date,
                    csp_strike=csp_strike,
                    csp_premium=csp_premium,
                    csp_expiration=price_data[exp_idx]['date']
                )

                in_csp = True
                csp_exp_idx = exp_idx
                cc_count = 0

                print(f"[{current_date}] SELL CSP: Strike ${csp_strike:.0f}, "
                      f"Premium ${csp_premium:.2f} (Spot: ${current_price:.2f})")

                i = exp_idx
                continue

            # STATE 2: CSP expiration
            if in_csp and not holding_shares:
                exp_price = current_price

                if exp_price >= current_cycle.csp_strike:
                    # CSP expired OTM - keep premium
                    current_cycle.csp_outcome = 'EXPIRED_OTM'
                    current_cycle.end_date = current_date
                    current_cycle.total_premium = current_cycle.csp_premium * self.shares
                    current_cycle.total_pnl = current_cycle.total_premium
                    current_cycle.days_in_cycle = self.csp_dte

                    capital_at_risk = current_cycle.csp_strike * self.shares
                    pnl_pct = (current_cycle.total_pnl / capital_at_risk) * 100

                    print(f"[{current_date}] CSP EXPIRED OTM: +${current_cycle.total_pnl:.2f} "
                          f"({pnl_pct:.2f}%)")

                    self.cycles.append(current_cycle)
                    in_csp = False
                    current_cycle = None
                    i += 1
                    continue

                else:
                    # CSP assigned
                    current_cycle.csp_outcome = 'ASSIGNED'
                    current_cycle.shares_assigned = self.shares
                    current_cycle.cost_basis = current_cycle.csp_strike - current_cycle.csp_premium

                    print(f"[{current_date}] CSP ASSIGNED: Bought {self.shares} shares "
                          f"at ${current_cycle.csp_strike:.0f}, Cost basis: ${current_cycle.cost_basis:.2f}")

                    in_csp = False
                    holding_shares = True
                    i += 1
                    continue

            # STATE 3: Holding shares - sell covered call
            if holding_shares:
                if cc_count >= self.max_cc_cycles:
                    # Force exit
                    exit_price = current_price
                    current_cycle.cc_outcome = 'FORCE_EXIT'
                    current_cycle.end_date = current_date

                    total_cc_premium = sum(current_cycle.cc_premiums) * self.shares
                    csp_premium_total = current_cycle.csp_premium * self.shares
                    share_pnl = (exit_price - current_cycle.cost_basis) * self.shares

                    current_cycle.total_premium = csp_premium_total + total_cc_premium
                    current_cycle.capital_gain = share_pnl
                    current_cycle.total_pnl = current_cycle.total_premium + share_pnl

                    print(f"[{current_date}] FORCE EXIT at ${exit_price:.2f}: "
                          f"Total P&L ${current_cycle.total_pnl:.2f}")

                    self.cycles.append(current_cycle)
                    holding_shares = False
                    current_cycle = None
                    i += 1
                    continue

                # Sell covered call (or check expiration)
                if cc_count == 0 or i >= cc_exp_idx:
                    # Check CC expiration first (if we have one)
                    if cc_count > 0 and i >= cc_exp_idx:
                        cc_strike = current_cycle.cc_strikes[-1]

                        if current_price >= cc_strike:
                            # Called away!
                            current_cycle.cc_outcome = 'CALLED_AWAY'
                            current_cycle.end_date = current_date

                            total_cc_premium = sum(current_cycle.cc_premiums) * self.shares
                            csp_premium_total = current_cycle.csp_premium * self.shares
                            share_pnl = (cc_strike - current_cycle.cost_basis) * self.shares

                            current_cycle.total_premium = csp_premium_total + total_cc_premium
                            current_cycle.capital_gain = share_pnl
                            current_cycle.total_pnl = current_cycle.total_premium + share_pnl

                            capital = current_cycle.csp_strike * self.shares
                            pnl_pct = (current_cycle.total_pnl / capital) * 100

                            print(f"[{current_date}] CALLED AWAY at ${cc_strike:.0f}!")
                            print(f"         Premium: ${current_cycle.total_premium:.2f} + "
                                  f"Gain: ${share_pnl:.2f} = ${current_cycle.total_pnl:.2f} ({pnl_pct:.2f}%)")

                            self.cycles.append(current_cycle)
                            holding_shares = False
                            current_cycle = None
                            i += 1
                            continue
                        else:
                            print(f"[{current_date}] CC #{cc_count} EXPIRED OTM, selling another")

                    # Sell new CC
                    cc_strike = self.select_cc_strike(current_cycle.cost_basis,
                                                      current_price, current_vol)
                    cc_premium = estimate_call_premium(current_price, cc_strike,
                                                       self.cc_dte, current_vol)

                    current_cycle.cc_strikes.append(cc_strike)
                    current_cycle.cc_premiums.append(cc_premium)
                    cc_count += 1
                    cc_exp_idx = min(i + self.cc_dte, len(price_data) - 1)

                    print(f"[{current_date}] SELL CC #{cc_count}: Strike ${cc_strike:.0f}, "
                          f"Premium ${cc_premium:.2f} (Spot: ${current_price:.2f})")

                    i = cc_exp_idx
                    continue

            i += 1

        # Close any open position
        if current_cycle and holding_shares:
            final_price = price_data[-1]['close']
            final_date = price_data[-1]['date']

            total_cc_premium = sum(current_cycle.cc_premiums) * self.shares
            csp_premium_total = current_cycle.csp_premium * self.shares
            share_pnl = (final_price - current_cycle.cost_basis) * self.shares

            current_cycle.cc_outcome = 'END_OF_DATA'
            current_cycle.end_date = final_date
            current_cycle.total_premium = csp_premium_total + total_cc_premium
            current_cycle.capital_gain = share_pnl
            current_cycle.total_pnl = current_cycle.total_premium + share_pnl

            self.cycles.append(current_cycle)
            print(f"[{final_date}] END OF DATA: Closed at ${final_price:.2f}")

        return self.generate_summary()

    def generate_summary(self) -> dict:
        """Generate backtest summary statistics."""
        if not self.cycles:
            return {}

        total_cycles = len(self.cycles)
        csp_only = sum(1 for c in self.cycles if c.csp_outcome == 'EXPIRED_OTM')
        assigned = sum(1 for c in self.cycles if c.csp_outcome == 'ASSIGNED')
        called_away = sum(1 for c in self.cycles if c.cc_outcome == 'CALLED_AWAY')

        total_premium = sum(c.total_premium for c in self.cycles)
        total_gain = sum(c.capital_gain for c in self.cycles)
        total_pnl = sum(c.total_pnl for c in self.cycles)

        wins = sum(1 for c in self.cycles if c.total_pnl > 0)
        losses = total_cycles - wins
        win_rate = (wins / total_cycles * 100) if total_cycles > 0 else 0

        avg_win = np.mean([c.total_pnl for c in self.cycles if c.total_pnl > 0]) if wins > 0 else 0
        avg_loss = np.mean([c.total_pnl for c in self.cycles if c.total_pnl <= 0]) if losses > 0 else 0

        # Capital calculation (for 1 contract of ~$450 stock)
        avg_capital = np.mean([c.csp_strike * self.shares for c in self.cycles])

        print("\n" + "=" * 70)
        print("WHEEL STRATEGY RESULTS")
        print("=" * 70)
        print(f"\nCYCLE BREAKDOWN:")
        print(f"  Total Cycles:        {total_cycles}")
        print(f"  CSP Expired OTM:     {csp_only} ({csp_only/total_cycles*100:.1f}%)")
        print(f"  Assigned:            {assigned} ({assigned/total_cycles*100:.1f}%)")
        print(f"  Called Away:         {called_away} ({called_away/assigned*100:.1f}% of assigned)" if assigned > 0 else "")

        print(f"\nPERFORMANCE:")
        print(f"  Win Rate:            {win_rate:.1f}%")
        print(f"  Wins:                {wins}")
        print(f"  Losses:              {losses}")
        print(f"  Avg Win:             ${avg_win:,.2f}")
        print(f"  Avg Loss:            ${avg_loss:,.2f}")

        print(f"\nP&L BREAKDOWN:")
        print(f"  Total Premium:       ${total_premium:,.2f}")
        print(f"  Total Capital Gain:  ${total_gain:,.2f}")
        print(f"  Total P&L:           ${total_pnl:,.2f}")

        # Annualized return
        first_date = datetime.strptime(self.cycles[0].start_date, '%Y-%m-%d')
        last_date = datetime.strptime(self.cycles[-1].end_date, '%Y-%m-%d')
        total_days = (last_date - first_date).days

        if total_days > 0 and avg_capital > 0:
            annualized_return = (total_pnl / avg_capital) * (365 / total_days) * 100
            print(f"\n  Annualized Return:   {annualized_return:.1f}%")
            print(f"  Capital Required:    ${avg_capital:,.0f}")

        print("=" * 70 + "\n")

        return {
            'total_cycles': total_cycles,
            'csp_expired_otm': csp_only,
            'assigned': assigned,
            'called_away': called_away,
            'win_rate': win_rate,
            'total_premium': total_premium,
            'total_capital_gain': total_gain,
            'total_pnl': total_pnl,
            'annualized_return': annualized_return if total_days > 0 else 0
        }


def main():
    parser = argparse.ArgumentParser(description='Standalone Wheel Strategy Backtest')
    parser.add_argument('--symbol', default='SPY', help='Symbol (for labeling)')
    parser.add_argument('--days', type=int, default=500, help='Trading days to simulate')
    parser.add_argument('--initial-price', type=float, default=450, help='Starting price')
    parser.add_argument('--volatility', type=float, default=0.18, help='Annual volatility')
    parser.add_argument('--csp-delta', type=float, default=0.25, help='CSP target delta')
    parser.add_argument('--cc-delta', type=float, default=0.30, help='CC target delta')
    parser.add_argument('--contracts', type=int, default=1, help='Number of contracts')

    args = parser.parse_args()

    print("\nGenerating simulated price data...")
    price_data = generate_realistic_prices(
        args.symbol,
        args.days,
        args.initial_price,
        annual_volatility=args.volatility
    )

    print(f"Generated {len(price_data)} days of price data")
    print(f"Price range: ${min(d['close'] for d in price_data):.2f} - ${max(d['close'] for d in price_data):.2f}")

    backtester = WheelBacktester(
        symbol=args.symbol,
        csp_delta=args.csp_delta,
        cc_delta=args.cc_delta,
        contracts=args.contracts
    )

    results = backtester.run_backtest(price_data)

    print("\n✅ Wheel Strategy Backtest Complete!")
    print("\nNote: This backtest uses simulated price data to demonstrate the strategy mechanics.")
    print("For production backtests, configure Polygon.io or Tradier API keys for real historical data.")


if __name__ == "__main__":
    main()
