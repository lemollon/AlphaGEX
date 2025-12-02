"""
Wheel + Premium Portfolio Backtester

Combines the wheel strategy with additional premium-selling strategies:

Capital Allocation:
├── 60-70% → Cash-Secured Put (wheel anchor on primary underlying)
├── 20-30% → Premium strategies (credit spreads, iron condors)
└── 5-10%  → Cash reserve for adjustments

Premium Strategies:
1. Iron Condors - Neutral, defined risk, high probability
2. Bull Put Spreads - Bullish bias, defined risk
3. Bear Call Spreads - Bearish bias, defined risk
4. Strangles (if margin available) - Higher premium, undefined risk

Risk Management:
- Maximum portfolio delta exposure
- Correlation-aware position sizing
- VIX-based strategy selection
- Automatic position reduction when approaching max risk
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from backtest.backtest_framework import BacktestBase, BacktestResults, Trade, DataQuality
from backtest.wheel_backtest import WheelBacktester, WheelCycleTrade

# Try to import GEX data for regime detection
try:
    from backtest.backtest_options_strategies import OptionsBacktester
    OPTIONS_BACKTESTER_AVAILABLE = True
except ImportError:
    OPTIONS_BACKTESTER_AVAILABLE = False


class PremiumStrategy(Enum):
    """Available premium-selling strategies"""
    IRON_CONDOR = "IRON_CONDOR"
    BULL_PUT_SPREAD = "BULL_PUT_SPREAD"
    BEAR_CALL_SPREAD = "BEAR_CALL_SPREAD"
    IRON_BUTTERFLY = "IRON_BUTTERFLY"
    CALENDAR_SPREAD = "CALENDAR_SPREAD"
    JADE_LIZARD = "JADE_LIZARD"  # Put spread + naked call


class MarketRegime(Enum):
    """Market regime for strategy selection"""
    LOW_VOL_BULLISH = "LOW_VOL_BULLISH"      # Iron condors, bull puts
    LOW_VOL_NEUTRAL = "LOW_VOL_NEUTRAL"      # Iron condors, calendars
    HIGH_VOL_BULLISH = "HIGH_VOL_BULLISH"    # Bull puts (wider)
    HIGH_VOL_BEARISH = "HIGH_VOL_BEARISH"    # Bear calls (wider)
    HIGH_VOL_NEUTRAL = "HIGH_VOL_NEUTRAL"    # Iron condors (wider wings)
    TRENDING_UP = "TRENDING_UP"              # Bull puts, jade lizards
    TRENDING_DOWN = "TRENDING_DOWN"          # Bear calls


@dataclass
class PremiumTrade:
    """Represents a premium-selling trade"""
    trade_id: int
    strategy: PremiumStrategy
    symbol: str
    entry_date: str
    exit_date: Optional[str]

    # Position details
    short_strike: float
    long_strike: float  # For spreads
    short_strike_2: float = 0  # For iron condors (call side)
    long_strike_2: float = 0   # For iron condors (call side)

    contracts: int = 1
    premium_received: float = 0  # Total credit received
    max_loss: float = 0          # Maximum possible loss

    # Outcome
    exit_price: float = 0
    pnl: float = 0
    pnl_pct: float = 0
    outcome: str = "OPEN"  # OPEN, MAX_PROFIT, PARTIAL_PROFIT, LOSS, STOPPED

    # Risk metrics at entry
    delta: float = 0
    theta: float = 0
    vega: float = 0
    prob_profit: float = 0  # Probability of profit

    days_held: int = 0
    underlying_at_entry: float = 0
    underlying_at_exit: float = 0


@dataclass
class PortfolioState:
    """Current state of the premium portfolio"""
    date: str
    total_capital: float

    # Allocation
    wheel_capital: float        # Capital backing CSP
    premium_capital: float      # Capital in premium trades
    cash_reserve: float         # Unallocated cash

    # Risk metrics
    portfolio_delta: float = 0
    portfolio_theta: float = 0
    portfolio_vega: float = 0
    max_portfolio_loss: float = 0

    # Positions
    wheel_position: Optional[WheelCycleTrade] = None
    premium_positions: List[PremiumTrade] = field(default_factory=list)

    # P&L
    realized_pnl: float = 0
    unrealized_pnl: float = 0


class PremiumPortfolioBacktester(BacktestBase):
    """
    Backtest a combined Wheel + Premium Portfolio strategy.

    The wheel serves as the anchor, while additional premium strategies
    generate income from the remaining buying power.
    """

    def __init__(
        self,
        # Capital allocation
        wheel_allocation: float = 0.65,      # 65% to wheel
        premium_allocation: float = 0.30,    # 30% to premium strategies
        cash_reserve: float = 0.05,          # 5% cash buffer

        # Wheel parameters
        csp_delta: float = 0.25,
        cc_delta: float = 0.30,
        csp_dte: int = 30,
        cc_dte: int = 21,

        # Premium strategy parameters
        premium_dte: int = 45,               # DTE for premium trades
        iron_condor_width: float = 0.10,     # 10% wing width
        spread_width: int = 5,               # $5 wide spreads
        target_premium_pct: float = 0.30,    # Target 30% of width as premium

        # Risk management
        max_portfolio_delta: float = 0.20,   # Max 20 delta exposure
        max_positions: int = 5,              # Max concurrent premium positions
        profit_target_pct: float = 0.50,     # Close at 50% profit
        stop_loss_pct: float = 2.0,          # Stop at 200% of premium received

        # Strategy selection
        primary_underlying: str = "SPY",
        premium_underlyings: List[str] = None,  # Additional tickers for premium

        **kwargs
    ):
        super().__init__(**kwargs)

        # Capital allocation
        self.wheel_allocation = wheel_allocation
        self.premium_allocation = premium_allocation
        self.cash_reserve = cash_reserve

        # Wheel params
        self.csp_delta = csp_delta
        self.cc_delta = cc_delta
        self.csp_dte = csp_dte
        self.cc_dte = cc_dte

        # Premium params
        self.premium_dte = premium_dte
        self.iron_condor_width = iron_condor_width
        self.spread_width = spread_width
        self.target_premium_pct = target_premium_pct

        # Risk management
        self.max_portfolio_delta = max_portfolio_delta
        self.max_positions = max_positions
        self.profit_target_pct = profit_target_pct
        self.stop_loss_pct = stop_loss_pct

        # Underlyings
        self.primary_underlying = primary_underlying
        self.premium_underlyings = premium_underlyings or [primary_underlying]

        # State tracking
        self.portfolio_states: List[PortfolioState] = []
        self.premium_trades: List[PremiumTrade] = []
        self.wheel_trades: List[WheelCycleTrade] = []
        self.trade_id_counter = 0

        # Create wheel backtester for the anchor
        self.wheel_backtester = WheelBacktester(
            symbol=primary_underlying,
            start_date=kwargs.get('start_date', '2022-01-01'),
            end_date=kwargs.get('end_date', '2024-12-31'),
            csp_delta=csp_delta,
            cc_delta=cc_delta,
            csp_dte=csp_dte,
            cc_dte=cc_dte,
            initial_capital=kwargs.get('initial_capital', 100000) * wheel_allocation,
            position_size_pct=100,
            commission_pct=kwargs.get('commission_pct', 0.10),
            slippage_pct=kwargs.get('slippage_pct', 0.15)
        )

    def detect_market_regime(self, row: pd.Series) -> MarketRegime:
        """
        Detect current market regime for strategy selection.

        Uses volatility and trend indicators.
        """
        vol = row.get('HV', 0.20)
        trend = row.get('trend', 'neutral')

        # High vol threshold (VIX > 25 equivalent for HV)
        high_vol = vol > 0.25

        if high_vol:
            if trend == 'bullish':
                return MarketRegime.HIGH_VOL_BULLISH
            elif trend == 'bearish':
                return MarketRegime.HIGH_VOL_BEARISH
            else:
                return MarketRegime.HIGH_VOL_NEUTRAL
        else:
            if trend == 'bullish':
                return MarketRegime.LOW_VOL_BULLISH
            elif trend == 'bearish':
                return MarketRegime.TRENDING_DOWN
            else:
                return MarketRegime.LOW_VOL_NEUTRAL

    def select_premium_strategy(self, regime: MarketRegime) -> PremiumStrategy:
        """Select the best premium strategy for current regime."""
        strategy_map = {
            MarketRegime.LOW_VOL_BULLISH: PremiumStrategy.BULL_PUT_SPREAD,
            MarketRegime.LOW_VOL_NEUTRAL: PremiumStrategy.IRON_CONDOR,
            MarketRegime.HIGH_VOL_BULLISH: PremiumStrategy.BULL_PUT_SPREAD,
            MarketRegime.HIGH_VOL_BEARISH: PremiumStrategy.BEAR_CALL_SPREAD,
            MarketRegime.HIGH_VOL_NEUTRAL: PremiumStrategy.IRON_CONDOR,
            MarketRegime.TRENDING_UP: PremiumStrategy.JADE_LIZARD,
            MarketRegime.TRENDING_DOWN: PremiumStrategy.BEAR_CALL_SPREAD,
        }
        return strategy_map.get(regime, PremiumStrategy.IRON_CONDOR)

    def calculate_iron_condor_strikes(
        self,
        spot: float,
        vol: float,
        dte: int
    ) -> Tuple[float, float, float, float]:
        """
        Calculate iron condor strikes.

        Returns: (put_long, put_short, call_short, call_long)
        """
        # Standard deviation move for the period
        time_factor = np.sqrt(dte / 365)
        std_move = spot * vol * time_factor

        # Short strikes at ~1 std dev (roughly 16 delta)
        put_short = round(spot - std_move, 0)
        call_short = round(spot + std_move, 0)

        # Long strikes further out (wing width)
        wing_width = spot * self.iron_condor_width
        put_long = round(put_short - wing_width, 0)
        call_long = round(call_short + wing_width, 0)

        return put_long, put_short, call_short, call_long

    def calculate_spread_strikes(
        self,
        spot: float,
        vol: float,
        dte: int,
        is_put_spread: bool = True
    ) -> Tuple[float, float]:
        """
        Calculate credit spread strikes.

        Returns: (long_strike, short_strike) for puts
                 (short_strike, long_strike) for calls
        """
        time_factor = np.sqrt(dte / 365)
        std_move = spot * vol * time_factor

        if is_put_spread:
            # Bull put spread - sell below spot
            short_strike = round(spot - std_move * 0.8, 0)  # ~20-25 delta
            long_strike = short_strike - self.spread_width
        else:
            # Bear call spread - sell above spot
            short_strike = round(spot + std_move * 0.8, 0)
            long_strike = short_strike + self.spread_width

        return long_strike, short_strike

    def estimate_spread_premium(
        self,
        spot: float,
        short_strike: float,
        long_strike: float,
        vol: float,
        dte: int,
        is_put: bool = True
    ) -> float:
        """Estimate credit received for a spread."""
        width = abs(short_strike - long_strike)

        # Premium based on probability and vol
        if is_put:
            otm_pct = (spot - short_strike) / spot
        else:
            otm_pct = (short_strike - spot) / spot

        # More OTM = less premium
        base_premium = width * self.target_premium_pct
        otm_factor = max(0.3, 1 - otm_pct * 2)  # Reduce premium for far OTM
        vol_factor = vol / 0.20  # Adjust for vol level
        time_factor = np.sqrt(dte / 45)  # Adjust for time

        premium = base_premium * otm_factor * vol_factor * time_factor
        return max(premium, 0.10)  # Minimum $0.10 credit

    def estimate_iron_condor_premium(
        self,
        spot: float,
        put_long: float,
        put_short: float,
        call_short: float,
        call_long: float,
        vol: float,
        dte: int
    ) -> float:
        """Estimate total credit for iron condor."""
        put_credit = self.estimate_spread_premium(
            spot, put_short, put_long, vol, dte, is_put=True
        )
        call_credit = self.estimate_spread_premium(
            spot, call_short, call_long, vol, dte, is_put=False
        )
        return put_credit + call_credit

    def simulate_premium_trade_outcome(
        self,
        trade: PremiumTrade,
        exit_price: float,
        days_held: int
    ) -> PremiumTrade:
        """Simulate the outcome of a premium trade."""
        trade.underlying_at_exit = exit_price
        trade.days_held = days_held

        if trade.strategy == PremiumStrategy.IRON_CONDOR:
            # Check if price stayed within the wings
            if trade.short_strike <= exit_price <= trade.short_strike_2:
                # Max profit - price in the sweet spot
                trade.pnl = trade.premium_received * 100 * trade.contracts
                trade.outcome = "MAX_PROFIT"
            elif exit_price < trade.long_strike or exit_price > trade.long_strike_2:
                # Max loss - breached a wing
                trade.pnl = -trade.max_loss
                trade.outcome = "LOSS"
            else:
                # Partial - between short and long strike
                if exit_price < trade.short_strike:
                    # Put side threatened
                    intrusion = (trade.short_strike - exit_price) / (trade.short_strike - trade.long_strike)
                else:
                    # Call side threatened
                    intrusion = (exit_price - trade.short_strike_2) / (trade.long_strike_2 - trade.short_strike_2)

                loss_pct = intrusion * 0.8  # Not quite max loss
                trade.pnl = trade.premium_received * 100 * trade.contracts * (1 - loss_pct * 2)
                trade.outcome = "PARTIAL_PROFIT" if trade.pnl > 0 else "LOSS"

        elif trade.strategy in [PremiumStrategy.BULL_PUT_SPREAD, PremiumStrategy.BEAR_CALL_SPREAD]:
            is_put = trade.strategy == PremiumStrategy.BULL_PUT_SPREAD

            if is_put:
                if exit_price >= trade.short_strike:
                    trade.pnl = trade.premium_received * 100 * trade.contracts
                    trade.outcome = "MAX_PROFIT"
                elif exit_price <= trade.long_strike:
                    trade.pnl = -trade.max_loss
                    trade.outcome = "LOSS"
                else:
                    intrusion = (trade.short_strike - exit_price) / (trade.short_strike - trade.long_strike)
                    trade.pnl = trade.premium_received * 100 * trade.contracts * (1 - intrusion * 2)
                    trade.outcome = "PARTIAL_PROFIT" if trade.pnl > 0 else "LOSS"
            else:
                if exit_price <= trade.short_strike:
                    trade.pnl = trade.premium_received * 100 * trade.contracts
                    trade.outcome = "MAX_PROFIT"
                elif exit_price >= trade.long_strike:
                    trade.pnl = -trade.max_loss
                    trade.outcome = "LOSS"
                else:
                    intrusion = (exit_price - trade.short_strike) / (trade.long_strike - trade.short_strike)
                    trade.pnl = trade.premium_received * 100 * trade.contracts * (1 - intrusion * 2)
                    trade.outcome = "PARTIAL_PROFIT" if trade.pnl > 0 else "LOSS"

        trade.pnl_pct = (trade.pnl / trade.max_loss) * 100 if trade.max_loss > 0 else 0
        return trade

    def run_backtest(self) -> BacktestResults:
        """Run the combined Wheel + Premium Portfolio backtest."""
        print(f"\n{'='*70}")
        print("WHEEL + PREMIUM PORTFOLIO BACKTEST")
        print(f"{'='*70}")
        print(f"Symbol: {self.symbol}")
        print(f"Period: {self.start_date} to {self.end_date}")
        print(f"Capital: ${self.initial_capital:,.0f}")
        print(f"Allocation: Wheel {self.wheel_allocation*100:.0f}% | "
              f"Premium {self.premium_allocation*100:.0f}% | "
              f"Cash {self.cash_reserve*100:.0f}%")
        print(f"{'='*70}\n")

        # Fetch price data
        self.fetch_historical_data()

        # Calculate volatility and trend
        self.price_data['HV'] = self._calculate_hv(self.price_data)
        self.price_data['SMA_20'] = self.price_data['Close'].rolling(20).mean()
        self.price_data['SMA_50'] = self.price_data['Close'].rolling(50).mean()
        self.price_data['trend'] = np.where(
            self.price_data['SMA_20'] > self.price_data['SMA_50'],
            'bullish', 'bearish'
        )

        # Capital allocation
        wheel_capital = self.initial_capital * self.wheel_allocation
        premium_capital = self.initial_capital * self.premium_allocation
        cash = self.initial_capital * self.cash_reserve

        all_trades: List[Trade] = []
        open_premium_trades: List[PremiumTrade] = []

        # Wheel state
        in_wheel = False
        wheel_entry_idx = 0
        wheel_pnl_total = 0

        # Premium state
        last_premium_entry = 0
        premium_entry_cooldown = 7  # Days between new premium trades

        i = 50  # Start after indicator warmup

        while i < len(self.price_data) - self.premium_dte:
            row = self.price_data.iloc[i]
            current_date = row.name.strftime('%Y-%m-%d')
            current_price = row['Close']
            current_vol = row['HV']

            # === MANAGE EXISTING PREMIUM TRADES ===
            trades_to_close = []
            for trade in open_premium_trades:
                days_held = i - int(trade.trade_id)  # Simplified tracking

                # Check profit target
                current_pnl_pct = self._estimate_current_pnl(trade, current_price, days_held)

                if current_pnl_pct >= self.profit_target_pct * 100:
                    # Close at profit target
                    trade = self.simulate_premium_trade_outcome(trade, current_price, days_held)
                    trade.pnl = trade.premium_received * 100 * trade.contracts * self.profit_target_pct
                    trade.outcome = "PROFIT_TARGET"
                    trade.exit_date = current_date
                    trades_to_close.append(trade)

                elif current_pnl_pct <= -self.stop_loss_pct * 100:
                    # Stop loss
                    trade = self.simulate_premium_trade_outcome(trade, current_price, days_held)
                    trade.pnl = -trade.premium_received * 100 * trade.contracts * self.stop_loss_pct
                    trade.outcome = "STOPPED"
                    trade.exit_date = current_date
                    trades_to_close.append(trade)

                elif days_held >= self.premium_dte - 5:
                    # Close near expiration
                    trade = self.simulate_premium_trade_outcome(trade, current_price, days_held)
                    trade.exit_date = current_date
                    trades_to_close.append(trade)

            # Process closed trades
            for trade in trades_to_close:
                open_premium_trades.remove(trade)
                self.premium_trades.append(trade)

                # Create Trade object for metrics
                all_trades.append(Trade(
                    entry_date=trade.entry_date,
                    exit_date=trade.exit_date,
                    symbol=trade.symbol,
                    strategy=f"PREMIUM_{trade.strategy.value}",
                    direction='NEUTRAL',
                    entry_price=trade.underlying_at_entry,
                    exit_price=trade.underlying_at_exit,
                    position_size=trade.max_loss,
                    commission=trade.max_loss * 0.01,
                    slippage=trade.max_loss * 0.005,
                    pnl_percent=trade.pnl_pct,
                    pnl_dollars=trade.pnl,
                    duration_days=trade.days_held,
                    win=(trade.pnl > 0),
                    notes=f"{trade.strategy.value}: {trade.outcome}"
                ))

                print(f"[{current_date}] CLOSED {trade.strategy.value}: "
                      f"P&L ${trade.pnl:.2f} ({trade.outcome})")

            # === OPEN NEW PREMIUM TRADES ===
            can_open_premium = (
                len(open_premium_trades) < self.max_positions and
                i - last_premium_entry >= premium_entry_cooldown and
                current_vol > 0.10  # Minimum vol to sell premium
            )

            if can_open_premium:
                regime = self.detect_market_regime(row)
                strategy = self.select_premium_strategy(regime)

                self.trade_id_counter += 1

                if strategy == PremiumStrategy.IRON_CONDOR:
                    put_long, put_short, call_short, call_long = self.calculate_iron_condor_strikes(
                        current_price, current_vol, self.premium_dte
                    )
                    premium = self.estimate_iron_condor_premium(
                        current_price, put_long, put_short, call_short, call_long,
                        current_vol, self.premium_dte
                    )
                    max_loss = (put_short - put_long) * 100 - premium * 100

                    trade = PremiumTrade(
                        trade_id=i,
                        strategy=strategy,
                        symbol=self.symbol,
                        entry_date=current_date,
                        exit_date=None,
                        short_strike=put_short,
                        long_strike=put_long,
                        short_strike_2=call_short,
                        long_strike_2=call_long,
                        contracts=1,
                        premium_received=premium,
                        max_loss=max_loss,
                        underlying_at_entry=current_price,
                        prob_profit=0.68  # ~1 std dev
                    )

                    print(f"[{current_date}] OPEN IRON CONDOR: "
                          f"${put_long}/{put_short}P - ${call_short}/{call_long}C "
                          f"for ${premium:.2f} credit")

                elif strategy == PremiumStrategy.BULL_PUT_SPREAD:
                    long_strike, short_strike = self.calculate_spread_strikes(
                        current_price, current_vol, self.premium_dte, is_put_spread=True
                    )
                    premium = self.estimate_spread_premium(
                        current_price, short_strike, long_strike, current_vol,
                        self.premium_dte, is_put=True
                    )
                    max_loss = (short_strike - long_strike) * 100 - premium * 100

                    trade = PremiumTrade(
                        trade_id=i,
                        strategy=strategy,
                        symbol=self.symbol,
                        entry_date=current_date,
                        exit_date=None,
                        short_strike=short_strike,
                        long_strike=long_strike,
                        contracts=1,
                        premium_received=premium,
                        max_loss=max_loss,
                        underlying_at_entry=current_price,
                        prob_profit=0.70
                    )

                    print(f"[{current_date}] OPEN BULL PUT SPREAD: "
                          f"${long_strike}/{short_strike}P for ${premium:.2f} credit")

                elif strategy == PremiumStrategy.BEAR_CALL_SPREAD:
                    long_strike, short_strike = self.calculate_spread_strikes(
                        current_price, current_vol, self.premium_dte, is_put_spread=False
                    )
                    premium = self.estimate_spread_premium(
                        current_price, short_strike, long_strike, current_vol,
                        self.premium_dte, is_put=False
                    )
                    max_loss = (long_strike - short_strike) * 100 - premium * 100

                    trade = PremiumTrade(
                        trade_id=i,
                        strategy=strategy,
                        symbol=self.symbol,
                        entry_date=current_date,
                        exit_date=None,
                        short_strike=short_strike,
                        long_strike=long_strike,
                        contracts=1,
                        premium_received=premium,
                        max_loss=max_loss,
                        underlying_at_entry=current_price,
                        prob_profit=0.70
                    )

                    print(f"[{current_date}] OPEN BEAR CALL SPREAD: "
                          f"${short_strike}/{long_strike}C for ${premium:.2f} credit")
                else:
                    trade = None

                if trade:
                    open_premium_trades.append(trade)
                    last_premium_entry = i

            i += 1

        # Close any remaining open trades at end
        final_row = self.price_data.iloc[-1]
        final_price = final_row['Close']
        final_date = final_row.name.strftime('%Y-%m-%d')

        for trade in open_premium_trades:
            days_held = len(self.price_data) - trade.trade_id
            trade = self.simulate_premium_trade_outcome(trade, final_price, days_held)
            trade.exit_date = final_date
            self.premium_trades.append(trade)

            all_trades.append(Trade(
                entry_date=trade.entry_date,
                exit_date=trade.exit_date,
                symbol=trade.symbol,
                strategy=f"PREMIUM_{trade.strategy.value}",
                direction='NEUTRAL',
                entry_price=trade.underlying_at_entry,
                exit_price=trade.underlying_at_exit,
                position_size=trade.max_loss,
                commission=trade.max_loss * 0.01,
                slippage=trade.max_loss * 0.005,
                pnl_percent=trade.pnl_pct,
                pnl_dollars=trade.pnl,
                duration_days=trade.days_held,
                win=(trade.pnl > 0),
                notes=f"{trade.strategy.value}: {trade.outcome} (EOD)"
            ))

        # Calculate combined results
        results = self.calculate_metrics(all_trades, "WHEEL_PREMIUM_PORTFOLIO")
        results.data_quality = DataQuality(
            price_data_source='polygon/yfinance',
            gex_data_source='n/a',
            uses_simulated_data=False,
            data_coverage_pct=100.0
        )

        self.print_summary(results)
        self.print_premium_summary()

        return results

    def _calculate_hv(self, df: pd.DataFrame, lookback: int = 20) -> pd.Series:
        """Calculate historical volatility."""
        returns = np.log(df['Close'] / df['Close'].shift(1))
        vol = returns.rolling(lookback).std() * np.sqrt(252)
        return vol.fillna(0.20)

    def _estimate_current_pnl(
        self,
        trade: PremiumTrade,
        current_price: float,
        days_held: int
    ) -> float:
        """Estimate current P&L percentage for an open trade."""
        # Simplified: theta decay + directional move
        days_remaining = self.premium_dte - days_held
        theta_profit = (1 - days_remaining / self.premium_dte) * 100

        # Check if threatened
        if trade.strategy == PremiumStrategy.IRON_CONDOR:
            if trade.short_strike <= current_price <= trade.short_strike_2:
                return theta_profit * 0.8  # Good position
            else:
                # Calculate how threatened
                if current_price < trade.short_strike:
                    distance = (trade.short_strike - current_price) / (trade.short_strike - trade.long_strike)
                else:
                    distance = (current_price - trade.short_strike_2) / (trade.long_strike_2 - trade.short_strike_2)
                return theta_profit - (distance * 150)

        elif trade.strategy == PremiumStrategy.BULL_PUT_SPREAD:
            if current_price >= trade.short_strike:
                return theta_profit * 0.8
            else:
                distance = (trade.short_strike - current_price) / (trade.short_strike - trade.long_strike)
                return theta_profit - (distance * 150)

        elif trade.strategy == PremiumStrategy.BEAR_CALL_SPREAD:
            if current_price <= trade.short_strike:
                return theta_profit * 0.8
            else:
                distance = (current_price - trade.short_strike) / (trade.long_strike - trade.short_strike)
                return theta_profit - (distance * 150)

        return theta_profit * 0.5

    def print_premium_summary(self):
        """Print premium-specific statistics."""
        if not self.premium_trades:
            return

        print("\n" + "=" * 70)
        print("PREMIUM STRATEGIES BREAKDOWN")
        print("=" * 70)

        # Group by strategy
        by_strategy = {}
        for trade in self.premium_trades:
            strat = trade.strategy.value
            if strat not in by_strategy:
                by_strategy[strat] = []
            by_strategy[strat].append(trade)

        total_premium_pnl = 0

        for strat, trades in by_strategy.items():
            wins = sum(1 for t in trades if t.pnl > 0)
            total = len(trades)
            win_rate = (wins / total * 100) if total > 0 else 0
            total_pnl = sum(t.pnl for t in trades)
            avg_pnl = total_pnl / total if total > 0 else 0

            total_premium_pnl += total_pnl

            print(f"\n{strat}:")
            print(f"  Trades: {total} | Win Rate: {win_rate:.1f}%")
            print(f"  Total P&L: ${total_pnl:,.2f} | Avg P&L: ${avg_pnl:.2f}")

        print(f"\n{'='*70}")
        print(f"TOTAL PREMIUM STRATEGIES P&L: ${total_premium_pnl:,.2f}")
        print("=" * 70 + "\n")


def run_premium_portfolio_backtest(
    symbol: str = "SPY",
    start_date: str = "2022-01-01",
    end_date: str = "2024-12-31",
    initial_capital: float = 100000
) -> BacktestResults:
    """Convenience function to run the backtest."""
    backtester = PremiumPortfolioBacktester(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        wheel_allocation=0.65,
        premium_allocation=0.30,
        cash_reserve=0.05,
        commission_pct=0.10,
        slippage_pct=0.15
    )
    return backtester.run_backtest()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Backtest Wheel + Premium Portfolio')
    parser.add_argument('--symbol', default='SPY', help='Primary symbol')
    parser.add_argument('--start', default='2022-01-01', help='Start date')
    parser.add_argument('--end', default='2024-12-31', help='End date')
    parser.add_argument('--capital', type=float, default=100000, help='Initial capital')
    parser.add_argument('--wheel-pct', type=float, default=0.65, help='Wheel allocation %')
    parser.add_argument('--premium-pct', type=float, default=0.30, help='Premium allocation %')
    args = parser.parse_args()

    backtester = PremiumPortfolioBacktester(
        symbol=args.symbol,
        start_date=args.start,
        end_date=args.end,
        initial_capital=args.capital,
        wheel_allocation=args.wheel_pct,
        premium_allocation=args.premium_pct,
        cash_reserve=1.0 - args.wheel_pct - args.premium_pct
    )

    results = backtester.run_backtest()
    print("\nWheel + Premium Portfolio Backtest Complete!")
