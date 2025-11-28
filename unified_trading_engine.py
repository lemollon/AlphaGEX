"""
unified_trading_engine.py - SINGLE ENGINE for Live Trading AND Backtesting

This module ensures that:
1. Live trading and backtesting use the EXACT same decision logic
2. Both run on the same time intervals (configurable: 5min, 15min, 1hour, daily)
3. The market regime classifier is the SINGLE source of truth
4. Results from backtesting directly inform live trading parameters

CORE PRINCIPLE: What you backtest is EXACTLY what you trade live.

Author: AlphaGEX
Date: 2025-11-26
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time as dt_time
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
from zoneinfo import ZoneInfo
import json

# Import the unified classifier
from core.market_regime_classifier import (
    MarketRegimeClassifier,
    RegimeClassification,
    MarketAction,
    VolatilityRegime,
    GammaRegime,
    TrendRegime,
    get_classifier,
    reset_classifier
)

# Database
try:
    from database_adapter import get_connection
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

# UNIFIED Data Provider (Tradier primary, Polygon fallback)
try:
    from data.unified_data_provider import get_data_provider, get_quote, get_options_chain, get_gex, get_vix
    UNIFIED_DATA_AVAILABLE = True
except ImportError:
    UNIFIED_DATA_AVAILABLE = False

# Legacy Polygon fallback
try:
    from data.polygon_helper import PolygonHelper
    POLYGON_AVAILABLE = True
except ImportError:
    POLYGON_AVAILABLE = False


class TradingInterval(Enum):
    """Supported trading intervals - same for live and backtest"""
    FIVE_MIN = "5min"
    FIFTEEN_MIN = "15min"
    THIRTY_MIN = "30min"
    ONE_HOUR = "1hour"
    FOUR_HOUR = "4hour"
    DAILY = "daily"


@dataclass
class TradingBar:
    """
    A single bar of market data - used identically in live and backtest.
    This ensures both systems see the same data structure.
    """
    timestamp: datetime
    symbol: str

    # Price data
    open: float
    high: float
    low: float
    close: float
    volume: int

    # GEX data (fetched or simulated for backtest)
    net_gex: float
    flip_point: float
    call_wall: float
    put_wall: float

    # Volatility data
    current_iv: float
    historical_vol: float
    vix: float
    vix_term_structure: str  # "contango" or "backwardation"

    # IV history for rank calculation
    iv_history: List[float] = field(default_factory=list)

    # Momentum (calculated from recent bars)
    momentum_1h: float = 0.0
    momentum_4h: float = 0.0

    # Moving averages
    ma_20: float = 0.0
    ma_50: float = 0.0

    @property
    def above_20ma(self) -> bool:
        return self.close > self.ma_20 if self.ma_20 > 0 else True

    @property
    def above_50ma(self) -> bool:
        return self.close > self.ma_50 if self.ma_50 > 0 else True


@dataclass
class Position:
    """An open position - same structure for live and paper"""
    id: int
    symbol: str
    strategy: str
    action: MarketAction
    option_type: str  # 'call', 'put', 'spread', etc.
    strike: float
    expiration: str
    entry_price: float
    entry_time: datetime
    contracts: int

    # Risk parameters (from regime classifier)
    stop_loss_pct: float
    profit_target_pct: float

    # Current state
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0

    # Regime at entry
    entry_regime: Optional[RegimeClassification] = None


@dataclass
class TradeResult:
    """Completed trade - same structure for live and backtest"""
    position: Position
    exit_price: float
    exit_time: datetime
    exit_reason: str  # 'stop_loss', 'profit_target', 'regime_change', 'expiration'
    realized_pnl: float
    realized_pnl_pct: float
    duration_bars: int
    duration_minutes: int


class UnifiedTradingEngine:
    """
    The SINGLE engine that powers both live trading and backtesting.

    Usage:

    # For LIVE trading:
    engine = UnifiedTradingEngine(mode='live', interval=TradingInterval.FIVE_MIN)
    engine.start()

    # For BACKTESTING:
    engine = UnifiedTradingEngine(mode='backtest', interval=TradingInterval.FIVE_MIN)
    results = engine.run_backtest(start_date='2024-01-01', end_date='2024-12-31')
    """

    # Market hours in Central Time
    MARKET_OPEN = dt_time(8, 30)   # 8:30 AM CT
    MARKET_CLOSE = dt_time(15, 0)  # 3:00 PM CT

    # Trading constraints
    MAX_POSITIONS = 3              # Max concurrent positions
    MAX_DAILY_TRADES = 5           # Max new trades per day
    MIN_CONFIDENCE = 60            # Minimum confidence to trade

    def __init__(
        self,
        symbol: str = "SPY",
        mode: str = "live",  # 'live' or 'backtest'
        interval: TradingInterval = TradingInterval.FIVE_MIN,
        initial_capital: float = 100000,
        max_position_pct: float = 0.15,  # Max 15% per position
        paper_trading: bool = True  # Even 'live' mode can be paper
    ):
        self.symbol = symbol
        self.mode = mode
        self.interval = interval
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.max_position_pct = max_position_pct
        self.paper_trading = paper_trading

        # The unified classifier - same instance for entire session
        self.classifier = MarketRegimeClassifier(symbol)

        # State
        self.positions: List[Position] = []
        self.closed_trades: List[TradeResult] = []
        self.daily_trades_count = 0
        self.current_date = None

        # Bar history for momentum/MA calculations
        self.bar_history: List[TradingBar] = []
        self.max_history_bars = 500  # Keep enough for calculations

        # IV history for rank calculation
        self.iv_history: List[float] = []
        self.max_iv_history = 252  # 1 year of trading days

        # Callbacks for live mode
        self.on_signal: Optional[Callable] = None
        self.on_trade: Optional[Callable] = None
        self.on_exit: Optional[Callable] = None

    def _interval_to_minutes(self) -> int:
        """Convert interval enum to minutes"""
        mapping = {
            TradingInterval.FIVE_MIN: 5,
            TradingInterval.FIFTEEN_MIN: 15,
            TradingInterval.THIRTY_MIN: 30,
            TradingInterval.ONE_HOUR: 60,
            TradingInterval.FOUR_HOUR: 240,
            TradingInterval.DAILY: 390  # Trading day minutes
        }
        return mapping[self.interval]

    def _calculate_momentum(self, bars: List[TradingBar], periods: int) -> float:
        """Calculate momentum as % change over period"""
        if len(bars) < periods:
            return 0.0
        return ((bars[-1].close - bars[-periods].close) / bars[-periods].close) * 100

    def _calculate_ma(self, bars: List[TradingBar], period: int) -> float:
        """Calculate simple moving average"""
        if len(bars) < period:
            return 0.0
        return sum(bar.close for bar in bars[-period:]) / period

    def _calculate_historical_vol(self, bars: List[TradingBar], period: int = 20) -> float:
        """Calculate historical (realized) volatility"""
        if len(bars) < period + 1:
            return 0.20  # Default 20%

        returns = []
        for i in range(-period, 0):
            if bars[i-1].close > 0:
                ret = np.log(bars[i].close / bars[i-1].close)
                returns.append(ret)

        if not returns:
            return 0.20

        # Annualize (252 trading days, adjusted for interval)
        bars_per_day = 390 / self._interval_to_minutes()
        annual_factor = np.sqrt(252 * bars_per_day)

        return np.std(returns) * annual_factor

    def process_bar(self, bar: TradingBar) -> Optional[RegimeClassification]:
        """
        Process a single bar - THE CORE LOOP for both live and backtest.

        This method:
        1. Updates bar history
        2. Calculates derived metrics (momentum, MAs, HV)
        3. Runs the regime classifier
        4. Manages existing positions
        5. Opens new positions if appropriate

        Returns the regime classification for this bar.
        """
        # Reset daily counter if new day
        bar_date = bar.timestamp.date()
        if self.current_date != bar_date:
            self.current_date = bar_date
            self.daily_trades_count = 0

        # Add bar to history
        self.bar_history.append(bar)
        if len(self.bar_history) > self.max_history_bars:
            self.bar_history = self.bar_history[-self.max_history_bars:]

        # Update IV history
        if bar.current_iv > 0:
            self.iv_history.append(bar.current_iv)
            if len(self.iv_history) > self.max_iv_history:
                self.iv_history = self.iv_history[-self.max_iv_history:]

        # Calculate derived metrics
        bars_per_hour = 60 / self._interval_to_minutes()
        momentum_1h = self._calculate_momentum(self.bar_history, int(bars_per_hour))
        momentum_4h = self._calculate_momentum(self.bar_history, int(bars_per_hour * 4))

        ma_20 = self._calculate_ma(self.bar_history, 20)
        ma_50 = self._calculate_ma(self.bar_history, 50)

        historical_vol = self._calculate_historical_vol(self.bar_history)

        # Update bar with calculated values
        bar.momentum_1h = momentum_1h
        bar.momentum_4h = momentum_4h
        bar.ma_20 = ma_20
        bar.ma_50 = ma_50
        bar.historical_vol = historical_vol
        bar.iv_history = self.iv_history.copy()

        # ============================================================
        # RUN THE UNIFIED REGIME CLASSIFIER
        # ============================================================
        regime = self.classifier.classify(
            spot_price=bar.close,
            net_gex=bar.net_gex,
            flip_point=bar.flip_point,
            current_iv=bar.current_iv,
            iv_history=self.iv_history,
            historical_vol=historical_vol,
            vix=bar.vix,
            vix_term_structure=bar.vix_term_structure,
            momentum_1h=momentum_1h,
            momentum_4h=momentum_4h,
            above_20ma=bar.above_20ma,
            above_50ma=bar.above_50ma,
            timestamp=bar.timestamp
        )

        # Callback for signal
        if self.on_signal:
            self.on_signal(regime)

        # ============================================================
        # POSITION MANAGEMENT
        # ============================================================
        self._manage_positions(bar, regime)

        # ============================================================
        # NEW POSITION LOGIC
        # ============================================================
        if self._should_open_position(regime):
            self._open_position(bar, regime)

        return regime

    def _manage_positions(self, bar: TradingBar, regime: RegimeClassification):
        """Check and manage all open positions"""
        positions_to_close = []

        for position in self.positions:
            # Update current price (in real trading, fetch from market)
            # For now, use spot price as proxy
            position.current_price = self._estimate_option_price(position, bar)

            # Calculate unrealized P&L
            if position.entry_price > 0:
                position.unrealized_pnl_pct = (
                    (position.current_price - position.entry_price) / position.entry_price * 100
                )
                position.unrealized_pnl = (
                    (position.current_price - position.entry_price) * position.contracts * 100
                )

            # Check exit conditions
            exit_reason = None

            # Stop loss hit
            if position.unrealized_pnl_pct <= -position.stop_loss_pct * 100:
                exit_reason = 'stop_loss'

            # Profit target hit
            elif position.unrealized_pnl_pct >= position.profit_target_pct * 100:
                exit_reason = 'profit_target'

            # Regime materially changed against us
            elif regime.regime_changed:
                # Check if new regime invalidates our thesis
                if position.action == MarketAction.BUY_CALLS:
                    if regime.recommended_action in [MarketAction.BUY_PUTS, MarketAction.SELL_PREMIUM]:
                        exit_reason = 'regime_change'
                elif position.action == MarketAction.BUY_PUTS:
                    if regime.recommended_action in [MarketAction.BUY_CALLS, MarketAction.SELL_PREMIUM]:
                        exit_reason = 'regime_change'
                elif position.action == MarketAction.SELL_PREMIUM:
                    if regime.gamma_regime in [GammaRegime.NEGATIVE, GammaRegime.STRONG_NEGATIVE]:
                        exit_reason = 'regime_change'  # Can't sell premium in negative gamma

            # Check expiration
            exp_date = datetime.strptime(position.expiration, '%Y-%m-%d').date()
            if bar.timestamp.date() >= exp_date:
                exit_reason = 'expiration'

            if exit_reason:
                positions_to_close.append((position, exit_reason))

        # Close positions
        for position, reason in positions_to_close:
            self._close_position(position, bar, reason)

    def _should_open_position(self, regime: RegimeClassification) -> bool:
        """Determine if we should open a new position"""
        # Don't trade if STAY_FLAT
        if regime.recommended_action == MarketAction.STAY_FLAT:
            return False

        # Don't trade if closing positions
        if regime.recommended_action == MarketAction.CLOSE_POSITIONS:
            return False

        # Check confidence threshold
        if regime.confidence < self.MIN_CONFIDENCE:
            return False

        # Check position limits
        if len(self.positions) >= self.MAX_POSITIONS:
            return False

        # Check daily trade limit
        if self.daily_trades_count >= self.MAX_DAILY_TRADES:
            return False

        # Don't double down on same action
        for pos in self.positions:
            if pos.action == regime.recommended_action:
                return False

        return True

    def _open_position(self, bar: TradingBar, regime: RegimeClassification):
        """Open a new position based on regime recommendation"""
        # Get strategy parameters from classifier
        strategy = self.classifier.get_strategy_for_action(
            regime.recommended_action, regime
        )

        if strategy['option_type'] is None:
            return  # No trade to make

        # Calculate base position size
        base_position_pct = min(regime.max_position_size_pct, self.max_position_pct)

        # VIX STRESS FACTOR: Real-time VIX-based position reduction
        # This matches SPX/SPY trader logic for consistency across all engines
        #
        # NOTE: Trader VIX thresholds (22/28/35) are MORE CONSERVATIVE than
        # unified_config.py thresholds (20/30/40). This is INTENTIONAL.
        # Traders trigger position reduction EARLIER for safety.
        #
        # Threshold Comparison:
        #   Trader: 22 (elevated), 28 (high), 35 (extreme)
        #   Config: 20 (elevated), 30 (high), 40 (extreme)
        #
        # See tests/test_vix_configuration.py for validation of this design.
        vix_stress_factor = 1.0
        vix_stress_level = 'normal'
        current_vix = bar.vix if bar.vix > 0 else 18.0

        if current_vix >= 35:
            vix_stress_factor = 0.25  # 75% reduction - extreme fear
            vix_stress_level = 'extreme'
        elif current_vix >= 28:
            vix_stress_factor = 0.50  # 50% reduction - high stress
            vix_stress_level = 'high'
        elif current_vix >= 22:
            vix_stress_factor = 0.75  # 25% reduction - elevated
            vix_stress_level = 'elevated'

        # Apply VIX stress factor to position size
        adjusted_position_pct = base_position_pct * vix_stress_factor
        position_value = self.current_capital * adjusted_position_pct

        if vix_stress_level != 'normal':
            print(f"⚠️ VIX {vix_stress_level.upper()} ({current_vix:.1f}): Position reduced by {(1-vix_stress_factor)*100:.0f}%")

        # Determine strike and expiration
        strike = self._select_strike(bar, regime, strategy)
        expiration = self._select_expiration(bar, strategy)

        # Estimate entry price
        entry_price = self._estimate_entry_price(bar, strike, strategy)

        # Calculate contracts
        contracts = max(1, int(position_value / (entry_price * 100)))

        # Create position
        position = Position(
            id=len(self.closed_trades) + len(self.positions) + 1,
            symbol=self.symbol,
            strategy=strategy['strategy_name'],
            action=regime.recommended_action,
            option_type=strategy['option_type'],
            strike=strike,
            expiration=expiration,
            entry_price=entry_price,
            entry_time=bar.timestamp,
            contracts=contracts,
            stop_loss_pct=regime.stop_loss_pct,
            profit_target_pct=regime.profit_target_pct,
            entry_regime=regime
        )

        self.positions.append(position)
        self.daily_trades_count += 1

        # Log
        print(f"\n{'='*60}")
        print(f"NEW POSITION OPENED")
        print(f"{'='*60}")
        print(f"Time: {bar.timestamp}")
        print(f"Action: {regime.recommended_action.value}")
        print(f"Strategy: {strategy['strategy_name']}")
        print(f"Strike: ${strike}")
        print(f"Expiration: {expiration}")
        print(f"Contracts: {contracts}")
        print(f"Entry Price: ${entry_price:.2f}")
        print(f"Stop Loss: {regime.stop_loss_pct*100:.0f}%")
        print(f"Profit Target: {regime.profit_target_pct*100:.0f}%")
        print(f"Confidence: {regime.confidence:.0f}%")
        print(f"\nReasoning:\n{regime.reasoning}")
        print(f"{'='*60}\n")

        # Callback
        if self.on_trade:
            self.on_trade(position, regime)

        # Persist to database
        self._persist_position(position)

    def _close_position(self, position: Position, bar: TradingBar, reason: str):
        """Close a position and record the trade result"""
        exit_price = position.current_price

        # Calculate realized P&L
        realized_pnl = (exit_price - position.entry_price) * position.contracts * 100
        realized_pnl_pct = (exit_price - position.entry_price) / position.entry_price * 100

        # Calculate duration
        duration_minutes = int((bar.timestamp - position.entry_time).total_seconds() / 60)
        duration_bars = duration_minutes / self._interval_to_minutes()

        # Create trade result
        result = TradeResult(
            position=position,
            exit_price=exit_price,
            exit_time=bar.timestamp,
            exit_reason=reason,
            realized_pnl=realized_pnl,
            realized_pnl_pct=realized_pnl_pct,
            duration_bars=int(duration_bars),
            duration_minutes=duration_minutes
        )

        # Update capital
        self.current_capital += realized_pnl

        # Remove from positions, add to closed
        self.positions.remove(position)
        self.closed_trades.append(result)

        # Log
        print(f"\n{'='*60}")
        print(f"POSITION CLOSED - {reason.upper()}")
        print(f"{'='*60}")
        print(f"Strategy: {position.strategy}")
        print(f"Entry: ${position.entry_price:.2f} at {position.entry_time}")
        print(f"Exit: ${exit_price:.2f} at {bar.timestamp}")
        print(f"P&L: ${realized_pnl:.2f} ({realized_pnl_pct:+.1f}%)")
        print(f"Duration: {duration_minutes} minutes ({duration_bars:.0f} bars)")
        print(f"New Capital: ${self.current_capital:.2f}")
        print(f"{'='*60}\n")

        # Callback
        if self.on_exit:
            self.on_exit(result)

        # Persist to database
        self._persist_trade_result(result)

    def _select_strike(self, bar: TradingBar, regime: RegimeClassification, strategy: Dict) -> float:
        """Select appropriate strike based on strategy"""
        spot = bar.close

        selection = strategy.get('strike_selection', 'atm')

        if selection == 'atm':
            return round(spot / 5) * 5
        elif selection == 'atm_plus_1':
            return round(spot / 5) * 5 + 5
        elif selection == 'atm_minus_1':
            return round(spot / 5) * 5 - 5
        elif selection == 'atm_to_flip':
            return round(bar.flip_point / 5) * 5
        elif selection == 'delta_based':
            # For iron condor, return ATM (specific legs handled elsewhere)
            return round(spot / 5) * 5
        else:
            return round(spot / 5) * 5

    def _select_expiration(self, bar: TradingBar, strategy: Dict) -> str:
        """Select appropriate expiration based on strategy"""
        dte_range = strategy.get('dte_range', (7, 14))
        target_dte = (dte_range[0] + dte_range[1]) // 2

        exp_date = bar.timestamp.date() + timedelta(days=target_dte)

        # Find next Friday
        while exp_date.weekday() != 4:  # Friday
            exp_date += timedelta(days=1)

        return exp_date.strftime('%Y-%m-%d')

    def _estimate_entry_price(self, bar: TradingBar, strike: float, strategy: Dict) -> float:
        """Estimate option entry price (simplified Black-Scholes proxy)"""
        spot = bar.close
        iv = bar.current_iv

        # Very simplified pricing
        moneyness = abs(spot - strike) / spot

        if strategy['option_type'] == 'call':
            if spot > strike:  # ITM
                intrinsic = spot - strike
                time_value = spot * iv * 0.1
                return intrinsic + time_value
            else:  # OTM
                return spot * iv * 0.1 * (1 - moneyness * 2)
        elif strategy['option_type'] == 'put':
            if spot < strike:  # ITM
                intrinsic = strike - spot
                time_value = spot * iv * 0.1
                return intrinsic + time_value
            else:  # OTM
                return spot * iv * 0.1 * (1 - moneyness * 2)
        else:  # Spread
            return spot * iv * 0.05  # Credit received

        return max(0.50, spot * iv * 0.08)  # Minimum price

    def _estimate_option_price(self, position: Position, bar: TradingBar) -> float:
        """Estimate current option price"""
        spot = bar.close
        strike = position.strike
        entry = position.entry_price

        # Simplified - track movement from entry
        if position.option_type == 'call':
            delta = 0.5 if spot > strike else 0.3
            price_move = (spot - bar.open) / bar.open
            return entry * (1 + price_move * delta * 10)
        elif position.option_type == 'put':
            delta = -0.5 if spot < strike else -0.3
            price_move = (spot - bar.open) / bar.open
            return entry * (1 - price_move * abs(delta) * 10)
        else:  # Spread - theta decay
            days_held = (bar.timestamp - position.entry_time).days
            theta_decay = 0.02 * days_held  # 2% per day decay
            return entry * (1 - theta_decay)

    def _persist_position(self, position: Position):
        """Save position to database"""
        if not DB_AVAILABLE:
            return

        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute("""
                INSERT INTO unified_positions
                (symbol, strategy, action, option_type, strike, expiration,
                 entry_price, entry_time, contracts, stop_loss_pct, profit_target_pct,
                 entry_regime)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                position.symbol,
                position.strategy,
                position.action.value,
                position.option_type,
                position.strike,
                position.expiration,
                position.entry_price,
                position.entry_time,
                position.contracts,
                position.stop_loss_pct,
                position.profit_target_pct,
                json.dumps(self.classifier.to_dict())
            ))

            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Warning: Could not persist position: {e}")

    def _persist_trade_result(self, result: TradeResult):
        """Save trade result to database"""
        if not DB_AVAILABLE:
            return

        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute("""
                INSERT INTO unified_trades
                (symbol, strategy, action, option_type, strike, expiration,
                 entry_price, entry_time, exit_price, exit_time, exit_reason,
                 contracts, realized_pnl, realized_pnl_pct, duration_minutes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                result.position.symbol,
                result.position.strategy,
                result.position.action.value,
                result.position.option_type,
                result.position.strike,
                result.position.expiration,
                result.position.entry_price,
                result.position.entry_time,
                result.exit_price,
                result.exit_time,
                result.exit_reason,
                result.position.contracts,
                result.realized_pnl,
                result.realized_pnl_pct,
                result.duration_minutes
            ))

            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Warning: Could not persist trade: {e}")

    # ================================================================
    # BACKTEST MODE
    # ================================================================

    def run_backtest(
        self,
        start_date: str,
        end_date: str,
        price_data: Optional[pd.DataFrame] = None,
        gex_data: Optional[pd.DataFrame] = None
    ) -> Dict:
        """
        Run backtest over historical period.

        Uses the SAME process_bar() method as live trading.

        Args:
            start_date: Start date YYYY-MM-DD
            end_date: End date YYYY-MM-DD
            price_data: Optional pre-loaded price data
            gex_data: Optional pre-loaded GEX data

        Returns:
            Dict with backtest results and metrics
        """
        if self.mode != 'backtest':
            raise ValueError("Engine must be in 'backtest' mode")

        # Reset state
        reset_classifier(self.symbol)
        self.classifier = MarketRegimeClassifier(self.symbol)
        self.positions = []
        self.closed_trades = []
        self.bar_history = []
        self.iv_history = []
        self.current_capital = self.initial_capital

        print(f"\n{'='*60}")
        print(f"UNIFIED BACKTEST: {self.symbol}")
        print(f"Period: {start_date} to {end_date}")
        print(f"Interval: {self.interval.value}")
        print(f"Initial Capital: ${self.initial_capital:,.2f}")
        print(f"{'='*60}\n")

        # Fetch or use provided data
        if price_data is None:
            price_data = self._fetch_backtest_data(start_date, end_date)

        if gex_data is None:
            gex_data = self._fetch_or_simulate_gex(price_data)

        # Generate bars at specified interval
        bars = self._generate_bars(price_data, gex_data)

        print(f"Processing {len(bars)} bars...")

        # Process each bar
        for i, bar in enumerate(bars):
            if i % 100 == 0:
                print(f"  Bar {i}/{len(bars)} - {bar.timestamp}")

            self.process_bar(bar)

        # Close any remaining positions at end
        if self.positions and bars:
            last_bar = bars[-1]
            for pos in self.positions.copy():
                self._close_position(pos, last_bar, 'backtest_end')

        # Calculate metrics
        results = self._calculate_backtest_metrics()

        # Print summary
        self._print_backtest_summary(results)

        return results

    def _fetch_backtest_data(self, start_date: str, end_date: str) -> pd.DataFrame:
        """Fetch historical price data"""
        # Try Polygon first
        if POLYGON_AVAILABLE:
            try:
                helper = PolygonHelper()
                # Fetch at the appropriate interval
                if self.interval in [TradingInterval.FIVE_MIN, TradingInterval.FIFTEEN_MIN, TradingInterval.THIRTY_MIN]:
                    timeframe = 'minute'
                    multiplier = self._interval_to_minutes()
                elif self.interval == TradingInterval.ONE_HOUR:
                    timeframe = 'hour'
                    multiplier = 1
                else:
                    timeframe = 'day'
                    multiplier = 1

                # This would need actual implementation based on your Polygon helper
                pass
            except Exception as e:
                print(f"Polygon fetch failed: {e}")

        # Fallback to yfinance
        try:
            import yfinance as yf
            ticker = yf.Ticker(self.symbol)

            interval_map = {
                TradingInterval.FIVE_MIN: '5m',
                TradingInterval.FIFTEEN_MIN: '15m',
                TradingInterval.THIRTY_MIN: '30m',
                TradingInterval.ONE_HOUR: '1h',
                TradingInterval.DAILY: '1d'
            }

            yf_interval = interval_map.get(self.interval, '1d')

            # Note: yfinance has limits on intraday data (60 days for 5m)
            df = ticker.history(
                start=start_date,
                end=end_date,
                interval=yf_interval
            )

            return df
        except Exception as e:
            raise ValueError(f"Could not fetch data: {e}")

    def _fetch_or_simulate_gex(self, price_data: pd.DataFrame) -> pd.DataFrame:
        """Fetch historical GEX or simulate based on price action"""
        # Try to fetch from database
        if DB_AVAILABLE:
            try:
                conn = get_connection()
                c = conn.cursor()

                c.execute("""
                    SELECT timestamp, net_gex, flip_point, call_wall, put_wall
                    FROM gex_history
                    WHERE symbol = %s
                    ORDER BY timestamp
                """, (self.symbol,))

                rows = c.fetchall()
                conn.close()

                if rows:
                    gex_df = pd.DataFrame(rows, columns=['timestamp', 'net_gex', 'flip_point', 'call_wall', 'put_wall'])
                    gex_df['timestamp'] = pd.to_datetime(gex_df['timestamp'])
                    gex_df.set_index('timestamp', inplace=True)
                    return gex_df
            except Exception as e:
                print(f"GEX fetch failed: {e}")

        # Simulate GEX based on price action
        print("Simulating GEX data from price action...")

        gex_data = []
        for idx, row in price_data.iterrows():
            close = row['Close']
            high = row['High']
            low = row['Low']
            volume = row.get('Volume', 1000000)

            # Simple simulation rules:
            # - Big down days = negative GEX (dealers short gamma)
            # - Big up days = positive GEX (dealers long gamma)
            # - Flip point = recent support/resistance

            daily_return = (close - row['Open']) / row['Open'] if row['Open'] > 0 else 0
            daily_range = (high - low) / close if close > 0 else 0

            if daily_return < -0.01 and daily_range > 0.015:
                net_gex = -2e9 - abs(daily_return) * 10e9
            elif daily_return > 0.01 and daily_range > 0.015:
                net_gex = 2e9 + daily_return * 5e9
            else:
                net_gex = np.random.uniform(-0.5e9, 1.5e9)

            flip_point = close * 0.98  # 2% below
            call_wall = close * 1.02   # 2% above
            put_wall = close * 0.96    # 4% below

            gex_data.append({
                'timestamp': idx,
                'net_gex': net_gex,
                'flip_point': flip_point,
                'call_wall': call_wall,
                'put_wall': put_wall
            })

        return pd.DataFrame(gex_data).set_index('timestamp')

    def _generate_bars(self, price_data: pd.DataFrame, gex_data: pd.DataFrame) -> List[TradingBar]:
        """Convert raw data into TradingBar objects"""
        bars = []

        # Get VIX data (simplified)
        vix_default = 18.0

        for idx, row in price_data.iterrows():
            timestamp = idx if isinstance(idx, datetime) else pd.to_datetime(idx)

            # Get GEX data for this timestamp
            gex_row = None
            if not gex_data.empty:
                # Find closest GEX reading
                try:
                    gex_idx = gex_data.index.get_indexer([timestamp], method='nearest')[0]
                    gex_row = gex_data.iloc[gex_idx]
                except:
                    pass

            bar = TradingBar(
                timestamp=timestamp,
                symbol=self.symbol,
                open=row['Open'],
                high=row['High'],
                low=row['Low'],
                close=row['Close'],
                volume=int(row.get('Volume', 1000000)),
                net_gex=gex_row['net_gex'] if gex_row is not None else 0,
                flip_point=gex_row['flip_point'] if gex_row is not None else row['Close'] * 0.98,
                call_wall=gex_row['call_wall'] if gex_row is not None else row['Close'] * 1.02,
                put_wall=gex_row['put_wall'] if gex_row is not None else row['Close'] * 0.96,
                current_iv=0.20,  # Would fetch from options data
                historical_vol=0.18,
                vix=vix_default,
                vix_term_structure="contango"
            )

            bars.append(bar)

        return bars

    def _calculate_backtest_metrics(self) -> Dict:
        """Calculate comprehensive backtest metrics"""
        if not self.closed_trades:
            return {
                'total_trades': 0,
                'win_rate': 0,
                'total_return_pct': 0,
                'sharpe_ratio': 0,
                'max_drawdown_pct': 0
            }

        # Basic metrics
        wins = [t for t in self.closed_trades if t.realized_pnl > 0]
        losses = [t for t in self.closed_trades if t.realized_pnl <= 0]

        total_trades = len(self.closed_trades)
        win_rate = len(wins) / total_trades * 100 if total_trades > 0 else 0

        avg_win = np.mean([t.realized_pnl for t in wins]) if wins else 0
        avg_loss = abs(np.mean([t.realized_pnl for t in losses])) if losses else 0

        # Total return
        total_pnl = sum(t.realized_pnl for t in self.closed_trades)
        total_return_pct = (total_pnl / self.initial_capital) * 100

        # Drawdown calculation
        equity = [self.initial_capital]
        for trade in self.closed_trades:
            equity.append(equity[-1] + trade.realized_pnl)

        peak = equity[0]
        max_dd = 0
        for e in equity:
            if e > peak:
                peak = e
            dd = (peak - e) / peak * 100
            if dd > max_dd:
                max_dd = dd

        # Sharpe ratio (simplified)
        returns = [t.realized_pnl_pct for t in self.closed_trades]
        if len(returns) > 1:
            sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0
        else:
            sharpe = 0

        # Expectancy
        expectancy = (win_rate/100 * avg_win) - ((100-win_rate)/100 * avg_loss)

        # Action breakdown
        action_breakdown = {}
        for trade in self.closed_trades:
            action = trade.position.action.value
            if action not in action_breakdown:
                action_breakdown[action] = {'count': 0, 'total_pnl': 0, 'wins': 0}
            action_breakdown[action]['count'] += 1
            action_breakdown[action]['total_pnl'] += trade.realized_pnl
            if trade.realized_pnl > 0:
                action_breakdown[action]['wins'] += 1

        for action in action_breakdown:
            action_breakdown[action]['win_rate'] = (
                action_breakdown[action]['wins'] / action_breakdown[action]['count'] * 100
            )

        return {
            'total_trades': total_trades,
            'winning_trades': len(wins),
            'losing_trades': len(losses),
            'win_rate': round(win_rate, 1),
            'avg_win': round(avg_win, 2),
            'avg_loss': round(avg_loss, 2),
            'largest_win': round(max(t.realized_pnl for t in self.closed_trades), 2),
            'largest_loss': round(min(t.realized_pnl for t in self.closed_trades), 2),
            'total_pnl': round(total_pnl, 2),
            'total_return_pct': round(total_return_pct, 2),
            'final_capital': round(self.current_capital, 2),
            'max_drawdown_pct': round(max_dd, 2),
            'sharpe_ratio': round(sharpe, 2),
            'expectancy': round(expectancy, 2),
            'action_breakdown': action_breakdown,
            'avg_duration_minutes': round(
                np.mean([t.duration_minutes for t in self.closed_trades]), 1
            ),
            'trades': [
                {
                    'entry_time': str(t.position.entry_time),
                    'exit_time': str(t.exit_time),
                    'strategy': t.position.strategy,
                    'action': t.position.action.value,
                    'pnl': round(t.realized_pnl, 2),
                    'pnl_pct': round(t.realized_pnl_pct, 2),
                    'exit_reason': t.exit_reason
                }
                for t in self.closed_trades
            ]
        }

    def _print_backtest_summary(self, results: Dict):
        """Print backtest summary"""
        print(f"\n{'='*60}")
        print(f"BACKTEST RESULTS SUMMARY")
        print(f"{'='*60}")
        print(f"Total Trades: {results['total_trades']}")
        print(f"Win Rate: {results['win_rate']}%")
        print(f"")
        print(f"Average Win: ${results.get('avg_win', 0):,.2f}")
        print(f"Average Loss: ${results.get('avg_loss', 0):,.2f}")
        print(f"Largest Win: ${results.get('largest_win', 0):,.2f}")
        print(f"Largest Loss: ${results.get('largest_loss', 0):,.2f}")
        print(f"")
        print(f"Total P&L: ${results['total_pnl']:,.2f}")
        print(f"Total Return: {results['total_return_pct']}%")
        print(f"Max Drawdown: {results['max_drawdown_pct']}%")
        print(f"Sharpe Ratio: {results['sharpe_ratio']}")
        print(f"Expectancy: ${results['expectancy']:,.2f}/trade")
        print(f"")
        print(f"Final Capital: ${results['final_capital']:,.2f}")

        if results.get('action_breakdown'):
            print(f"\n{'='*40}")
            print(f"BREAKDOWN BY ACTION")
            print(f"{'='*40}")
            for action, stats in results['action_breakdown'].items():
                print(f"{action}:")
                print(f"  Trades: {stats['count']}, Win Rate: {stats['win_rate']:.1f}%, P&L: ${stats['total_pnl']:,.2f}")

        print(f"{'='*60}\n")


# ============================================================================
# DATABASE SCHEMA
# ============================================================================

CREATE_UNIFIED_TABLES_SQL = """
-- Regime classifications (from classifier)
CREATE TABLE IF NOT EXISTS regime_classifications (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    regime_data JSONB NOT NULL,
    recommended_action VARCHAR(50) NOT NULL,
    confidence FLOAT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_regime_symbol_time ON regime_classifications(symbol, created_at);

-- Unified positions (both live and backtest)
CREATE TABLE IF NOT EXISTS unified_positions (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    strategy VARCHAR(100) NOT NULL,
    action VARCHAR(50) NOT NULL,
    option_type VARCHAR(20),
    strike FLOAT,
    expiration DATE,
    entry_price FLOAT NOT NULL,
    entry_time TIMESTAMP NOT NULL,
    contracts INTEGER NOT NULL,
    stop_loss_pct FLOAT,
    profit_target_pct FLOAT,
    entry_regime JSONB,
    is_backtest BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Unified closed trades (both live and backtest)
CREATE TABLE IF NOT EXISTS unified_trades (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    strategy VARCHAR(100) NOT NULL,
    action VARCHAR(50) NOT NULL,
    option_type VARCHAR(20),
    strike FLOAT,
    expiration DATE,
    entry_price FLOAT NOT NULL,
    entry_time TIMESTAMP NOT NULL,
    exit_price FLOAT NOT NULL,
    exit_time TIMESTAMP NOT NULL,
    exit_reason VARCHAR(50),
    contracts INTEGER NOT NULL,
    realized_pnl FLOAT,
    realized_pnl_pct FLOAT,
    duration_minutes INTEGER,
    is_backtest BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trades_symbol_time ON unified_trades(symbol, exit_time);
CREATE INDEX IF NOT EXISTS idx_trades_action ON unified_trades(action);
"""


if __name__ == "__main__":
    # Example usage

    # BACKTEST MODE
    print("Running backtest example...")
    engine = UnifiedTradingEngine(
        symbol="SPY",
        mode="backtest",
        interval=TradingInterval.DAILY,  # Use daily for faster testing
        initial_capital=100000
    )

    # Run backtest on recent period
    results = engine.run_backtest(
        start_date="2024-01-01",
        end_date="2024-06-30"
    )

    print(f"\nBacktest complete!")
    print(f"Results: {json.dumps(results, indent=2, default=str)}")
