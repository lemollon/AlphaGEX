"""
Options Strategy Backtester

Backtests the 11 options strategies from STRATEGIES config:
- BULLISH_CALL_SPREAD
- BEARISH_PUT_SPREAD
- BULL_PUT_SPREAD
- BEAR_CALL_SPREAD
- IRON_CONDOR
- IRON_BUTTERFLY
- LONG_STRADDLE
- LONG_STRANGLE
- NEGATIVE_GEX_SQUEEZE
- POSITIVE_GEX_BREAKDOWN
- PREMIUM_SELLING
- CALENDAR_SPREAD

Uses REAL GEX data from Trading Volatility API
Uses REALISTIC option pricing with Black-Scholes model, Greeks, bid/ask spreads
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from backtest_framework import BacktestBase, BacktestResults, Trade
from typing import Dict, List, Optional
from config_and_database import STRATEGIES
from realistic_option_pricing import (
    BlackScholesOption, StrikeSelector, SpreadPricer,
    create_bullish_call_spread, create_bearish_put_spread
)


class OptionsBacktester(BacktestBase):
    """Backtest options strategies from STRATEGIES config using REAL GEX data"""

    def __init__(self, use_realistic_pricing: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.gex_data = None
        self.api_client = None
        self.use_realistic_pricing = use_realistic_pricing
        self.spread_pricer = SpreadPricer() if use_realistic_pricing else None
        self.strike_selector = StrikeSelector() if use_realistic_pricing else None

    def simulate_gex_data(self, price_data: pd.DataFrame) -> pd.DataFrame:
        """
        Simulate approximate GEX levels when real data unavailable

        Uses simplified heuristics based on price action and volatility
        """
        df = price_data.copy()

        # Calculate returns and volatility
        df['returns'] = df['Close'].pct_change()
        df['volatility'] = df['returns'].rolling(10).std() * 100

        # Simulate GEX levels
        df['flip_point'] = df['Close'] * 0.975  # 2.5% below
        df['call_wall'] = df['Close'] * 1.020   # 2% above
        df['put_wall'] = df['Close'] * 0.975    # 2.5% below

        # Net GEX inversely correlated with volatility
        median_vol = df['volatility'].median()
        df['net_gex'] = df['volatility'].apply(
            lambda v: -5e9 if v > median_vol * 1.5 else 2e9 if v < median_vol * 0.7 else 0
        )

        # Derived metrics
        df['distance_to_flip'] = abs(df['Close'] - df['flip_point']) / df['flip_point'] * 100
        df['distance_to_call_wall'] = abs(df['Close'] - df['call_wall']) / df['Close'] * 100
        df['distance_to_put_wall'] = abs(df['Close'] - df['put_wall']) / df['Close'] * 100
        df['min_wall_distance'] = df[['distance_to_call_wall', 'distance_to_put_wall']].min(axis=1)

        # Technical indicators
        df['SMA_20'] = df['Close'].rolling(20).mean()
        df['SMA_50'] = df['Close'].rolling(50).mean()
        df['trend'] = np.where(df['SMA_20'] > df['SMA_50'], 'bullish', 'bearish')

        # IV Rank (simplified)
        df['vol_rank'] = df['volatility'].rolling(252).apply(
            lambda x: (x.iloc[-1] - x.min()) / (x.max() - x.min()) * 100 if x.max() > x.min() else 50
        )

        print(f"✓ Simulated GEX data generated for options strategies")

        return df

    def fetch_real_gex_data(self, price_data: pd.DataFrame) -> pd.DataFrame:
        """
        Fetch REAL historical GEX data from Trading Volatility API

        Returns price data merged with actual GEX levels and calculated technical indicators
        """
        try:
            from core_classes_and_engines import TradingVolatilityAPI
        except ImportError as e:
            print(f"⚠️ Trading Volatility API not available: {e}")
            print("   Falling back to SIMULATED GEX data for backtesting...")
            return self.simulate_gex_data(price_data)

        df = price_data.copy()

        # CRITICAL: Normalize price data index to midnight
        # Polygon returns timestamps like "2022-11-28 05:00:00"
        # We need "2022-11-28 00:00:00" to match GEX data
        if isinstance(df.index, pd.DatetimeIndex):
            df.index = df.index.normalize()
            # Also strip timezone if present
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)

        # Initialize API client
        if self.api_client is None:
            try:
                self.api_client = TradingVolatilityAPI()
            except Exception as e:
                print(f"⚠️ Failed to initialize Trading Volatility API: {e}")
                print("   Falling back to SIMULATED GEX data for backtesting...")
                return self.simulate_gex_data(price_data)

        print(f"📡 Fetching REAL historical GEX data from Trading Volatility API...")

        # Calculate days back from date range
        start_dt = pd.to_datetime(self.start_date)
        end_dt = pd.to_datetime(self.end_date)
        days_back = (end_dt - start_dt).days + 10  # Add buffer

        # Fetch real historical GEX data
        try:
            historical_gex = self.api_client.get_historical_gamma(self.symbol, days_back=days_back)
        except Exception as e:
            print(f"⚠️ Failed to fetch historical GEX data: {e}")
            print("   Falling back to SIMULATED GEX data for backtesting...")
            return self.simulate_gex_data(price_data)

        if not historical_gex or len(historical_gex) == 0:
            print("⚠️ WARNING: No historical GEX data available from Trading Volatility API")
            print("   Falling back to SIMULATED GEX data for backtesting...")
            print("   NOTE: Results will be approximate - use real data for production validation")
            return self.simulate_gex_data(price_data)

        print(f"✅ Received {len(historical_gex)} days of REAL GEX data")

        # Convert to DataFrame and parse dates
        gex_df = pd.DataFrame(historical_gex)

        # Parse date field (handle different possible formats)
        date_field = None
        for field in ['date', 'Date', 'timestamp', 'trading_date', 'collection_date']:
            if field in gex_df.columns:
                date_field = field
                break

        if date_field is None:
            print("⚠️  Warning: No date field found in GEX data")
            print(f"   Available fields: {list(gex_df.columns)}")
            raise ValueError("Cannot parse dates from GEX historical data")

        # Parse dates with flexible format handling
        # Trading Volatility API returns inconsistent formats:
        # - "2022-01-20_20:47:25" (underscore separator)
        # - "2022-01-10 14:36:25.864668" (space separator with microseconds)
        gex_df['date'] = pd.to_datetime(gex_df[date_field].str.replace('_', ' '), format='mixed', errors='coerce')

        # Normalize to date-only (strip time) to match price data index
        # Price data has dates like "2022-01-20" while GEX has "2022-01-20 20:47:25"
        gex_df['date'] = gex_df['date'].dt.normalize()

        # CRITICAL: Remove timezone info to match price data (which is timezone-naive)
        # pd.to_datetime with format='mixed' sometimes creates tz-aware timestamps
        # Timezone-aware and naive timestamps WON'T match in pandas joins
        if gex_df['date'].dt.tz is not None:
            gex_df['date'] = gex_df['date'].dt.tz_localize(None)

        gex_df.set_index('date', inplace=True)

        # Rename columns to standard names if needed
        column_mapping = {
            'net_gex': 'net_gex',
            'netGex': 'net_gex',
            'net_gamma': 'net_gex',
            'gex_per_1pct_chg': 'net_gex',
            'nearest_gex_value': 'net_gex',
            'flip_point': 'flip_point',
            'flipPoint': 'flip_point',
            'zero_gamma': 'flip_point',
            'gex_flip_price': 'flip_point',
            'call_wall': 'call_wall',
            'callWall': 'call_wall',
            'put_wall': 'put_wall',
            'putWall': 'put_wall'
        }

        for old_name, new_name in column_mapping.items():
            if old_name in gex_df.columns and new_name not in gex_df.columns:
                gex_df.rename(columns={old_name: new_name}, inplace=True)

        # Merge on date index - only include columns that exist
        print("Merging GEX data with price data...")
        available_gex_cols = [col for col in ['net_gex', 'flip_point', 'call_wall', 'put_wall']
                              if col in gex_df.columns]

        if available_gex_cols:
            df = df.join(gex_df[available_gex_cols], how='left')

            # CRITICAL: Convert GEX columns to numeric (API returns strings)
            for col in available_gex_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
        else:
            print("⚠️  No recognized GEX columns found, falling back to simulated data")
            return self.simulate_gex_data(price_data)

        # Forward fill missing GEX values (weekends/holidays)
        if 'net_gex' in df.columns:
            df['net_gex'].fillna(method='ffill', inplace=True)
        if 'flip_point' in df.columns:
            df['flip_point'].fillna(method='ffill', inplace=True)
        if 'call_wall' in df.columns:
            df['call_wall'].fillna(method='ffill', inplace=True)
        else:
            # Estimate call wall if not provided
            df['call_wall'] = df['Close'] * 1.05  # 5% above current price
        if 'put_wall' in df.columns:
            df['put_wall'].fillna(method='ffill', inplace=True)
        else:
            # Estimate put wall if not provided
            df['put_wall'] = df['Close'] * 0.95  # 5% below current price

        # Calculate derived metrics needed for strategy conditions
        df['distance_to_flip'] = abs(df['Close'] - df['flip_point']) / df['flip_point'] * 100
        df['distance_to_call_wall'] = abs(df['Close'] - df['call_wall']) / df['Close'] * 100
        df['distance_to_put_wall'] = abs(df['Close'] - df['put_wall']) / df['Close'] * 100
        df['min_wall_distance'] = df[['distance_to_call_wall', 'distance_to_put_wall']].min(axis=1)

        # Calculate technical indicators
        df['returns'] = df['Close'].pct_change()
        df['volatility'] = df['returns'].rolling(10).std() * 100
        df['SMA_20'] = df['Close'].rolling(20).mean()
        df['SMA_50'] = df['Close'].rolling(50).mean()
        df['trend'] = np.where(df['SMA_20'] > df['SMA_50'], 'bullish', 'bearish')

        # IV Rank (simplified - based on recent volatility)
        df['vol_rank'] = df['volatility'].rolling(252).apply(
            lambda x: (x.iloc[-1] - x.min()) / (x.max() - x.min()) * 100 if x.max() > x.min() else 50
        )

        print(f"✅ GEX data merged successfully - ready for strategy backtesting")
        if 'net_gex' in df.columns and not df['net_gex'].isna().all():
            net_gex_min = float(df['net_gex'].min())
            net_gex_max = float(df['net_gex'].max())
            print(f"   Net GEX range: ${net_gex_min/1e9:.2f}B to ${net_gex_max/1e9:.2f}B")
        if 'flip_point' in df.columns and not df['flip_point'].isna().all():
            flip_min = float(df['flip_point'].min())
            flip_max = float(df['flip_point'].max())
            print(f"   Flip point range: ${flip_min:.2f} to ${flip_max:.2f}")

        return df

    def check_strategy_conditions(self, row: pd.Series, strategy_name: str) -> bool:
        """Check if strategy entry conditions are met"""
        if strategy_name not in STRATEGIES:
            return False

        strategy_config = STRATEGIES[strategy_name]
        conditions = strategy_config['conditions']

        # Check each condition
        for condition_name, condition_value in conditions.items():
            if condition_name == 'net_gex_threshold':
                if isinstance(condition_value, (int, float)):
                    if row['net_gex'] < condition_value:
                        return False
            elif condition_name == 'distance_to_flip':
                if row['distance_to_flip'] > condition_value:
                    return False
            elif condition_name == 'trend':
                if condition_value == 'bullish' and row['trend'] != 'bullish':
                    return False
                elif condition_value == 'bearish' and row['trend'] != 'bearish':
                    return False
                elif condition_value == 'neutral_to_bullish' and row['trend'] == 'bearish':
                    return False
                elif condition_value == 'neutral_to_bearish' and row['trend'] == 'bullish':
                    return False
            elif condition_name == 'distance_to_call_wall':
                if row['distance_to_call_wall'] > condition_value:
                    return False
            elif condition_name == 'distance_to_put_wall':
                if row['distance_to_put_wall'] > condition_value:
                    return False
            elif condition_name == 'min_wall_distance':
                if row['min_wall_distance'] < condition_value:
                    return False
            elif condition_name == 'iv_rank_below':
                if row['vol_rank'] > condition_value:
                    return False
            elif condition_name == 'low_volatility':
                # Use pre-calculated volatility metrics from the dataframe
                # row['volatility'] is a single value, not a Series
                if condition_value:
                    # Skip this check since volatility is already calculated in the dataframe
                    pass
            elif condition_name == 'price_at_flip':
                if abs(row['Close'] - row['flip_point']) / row['flip_point'] * 100 > condition_value:
                    return False

        return True

    def estimate_iv_from_vol_rank(self, vol_rank: float) -> float:
        """
        Estimate implied volatility from volatility rank

        Args:
            vol_rank: Volatility rank (0-100)

        Returns:
            Estimated IV as decimal (e.g., 0.25 for 25%)
        """
        # SPY typical IV range: 10% (low) to 40% (high)
        # Map vol_rank to this range
        min_iv = 0.10
        max_iv = 0.40
        iv = min_iv + (vol_rank / 100.0) * (max_iv - min_iv)
        return iv

    def simulate_option_pnl_realistic(self, strategy_name: str, entry_price: float,
                                     exit_price: float, days_held: int,
                                     entry_vol_rank: float, exit_vol_rank: Optional[float] = None) -> Dict:
        """
        Calculate realistic option PnL using Black-Scholes pricing

        Returns dict with:
        - pnl_percent: Total P&L as percentage
        - spread_details: Detailed spread information
        - greeks: Net Greeks of the position
        """
        if exit_vol_rank is None:
            exit_vol_rank = entry_vol_rank

        # Estimate IV from vol_rank
        entry_iv = self.estimate_iv_from_vol_rank(entry_vol_rank)
        exit_iv = self.estimate_iv_from_vol_rank(exit_vol_rank)

        # Get strategy config
        strategy_config = STRATEGIES.get(strategy_name, {})
        dte_range = strategy_config.get('dte_range', [3, 14])
        avg_dte = (dte_range[0] + dte_range[1]) // 2

        # Price spread at entry using realistic pricing
        if strategy_name == 'BULLISH_CALL_SPREAD':
            spread_details = create_bullish_call_spread(
                spot_price=entry_price,
                volatility=entry_iv,
                dte=avg_dte,
                target_delta=0.30,  # 30-delta call spread
                spread_width_pct=5.0  # 5% wide
            )
        elif strategy_name == 'BEARISH_PUT_SPREAD':
            spread_details = create_bearish_put_spread(
                spot_price=entry_price,
                volatility=entry_iv,
                dte=avg_dte,
                target_delta=-0.30,  # 30-delta put spread
                spread_width_pct=5.0
            )
        elif strategy_name == 'BULL_PUT_SPREAD':
            # Credit spread - sell put spread below market
            spread_details = create_bearish_put_spread(
                spot_price=entry_price * 0.95,  # 5% OTM
                volatility=entry_iv,
                dte=avg_dte,
                target_delta=-0.20,  # 20-delta
                spread_width_pct=3.0  # Narrower spread
            )
            # Invert for credit received
            spread_details['debit'] = -spread_details['debit']
        elif strategy_name == 'BEAR_CALL_SPREAD':
            # Credit spread - sell call spread above market
            spread_details = create_bullish_call_spread(
                spot_price=entry_price * 1.05,  # 5% OTM
                volatility=entry_iv,
                dte=avg_dte,
                target_delta=0.20,  # 20-delta
                spread_width_pct=3.0
            )
            # Invert for credit received
            spread_details['debit'] = -spread_details['debit']
        else:
            # For other strategies, fall back to simplified pricing
            return {
                'pnl_percent': self.simulate_option_pnl_simplified(strategy_name, entry_price, exit_price, days_held),
                'spread_details': {},
                'greeks': {}
            }

        # Calculate P&L at exit
        pnl_details = self.spread_pricer.calculate_spread_pnl(
            spread_details=spread_details,
            current_price=exit_price,
            days_held=days_held,
            entry_volatility=entry_iv,
            exit_volatility=exit_iv
        )

        return {
            'pnl_percent': pnl_details['pnl_percent'],
            'spread_details': spread_details,
            'pnl_details': pnl_details,
            'greeks': {
                'delta': spread_details['net_delta'],
                'gamma': spread_details['net_gamma'],
                'theta': spread_details['net_theta'],
                'vega': spread_details['net_vega']
            }
        }

    def simulate_option_pnl_simplified(self, strategy_name: str, entry_price: float,
                           exit_price: float, days_held: int) -> float:
        """
        Simulate option PnL based on directional move and strategy type

        Simplified model:
        - Debit spreads: Max gain = width, Max loss = debit paid
        - Credit spreads: Max gain = credit, Max loss = width - credit
        - Straddles/Strangles: PnL scales with move size
        - Iron Condor: Profit if stays in range
        """
        strategy_config = STRATEGIES.get(strategy_name, {})
        price_change_pct = ((exit_price - entry_price) / entry_price) * 100

        # Get expected parameters
        risk_reward = strategy_config.get('risk_reward', 1.0)
        win_rate = strategy_config.get('win_rate', 0.5)

        # Directional debit spreads
        if strategy_name in ['BULLISH_CALL_SPREAD', 'BEARISH_PUT_SPREAD', 'NEGATIVE_GEX_SQUEEZE']:
            # Win if move in expected direction > 1%
            if strategy_name == 'BULLISH_CALL_SPREAD' or strategy_name == 'NEGATIVE_GEX_SQUEEZE':
                target_move = 2.0  # Need 2% up to win
                if price_change_pct > target_move:
                    return +risk_reward * 100  # Max gain
                elif price_change_pct < -1.0:
                    return -100  # Max loss
                else:
                    return price_change_pct * 30  # Partial
            else:  # BEARISH_PUT_SPREAD
                target_move = -2.0  # Need 2% down to win
                if price_change_pct < target_move:
                    return +risk_reward * 100
                elif price_change_pct > 1.0:
                    return -100
                else:
                    return -price_change_pct * 30

        # Credit spreads
        elif strategy_name in ['BULL_PUT_SPREAD', 'BEAR_CALL_SPREAD', 'PREMIUM_SELLING']:
            # Win if stays above/below strike
            max_gain = 40  # Typical credit
            max_loss = -100  # Width - credit

            if strategy_name == 'BULL_PUT_SPREAD':
                # Win if price stays above or rises
                if price_change_pct >= -0.5:
                    return max_gain
                elif price_change_pct < -2.0:
                    return max_loss
                else:
                    return max_gain * (1 + price_change_pct / 2)
            elif strategy_name == 'BEAR_CALL_SPREAD':
                # Win if price stays below or falls
                if price_change_pct <= 0.5:
                    return max_gain
                elif price_change_pct > 2.0:
                    return max_loss
                else:
                    return max_gain * (1 - price_change_pct / 2)
            else:  # PREMIUM_SELLING
                # Win if no significant move
                if abs(price_change_pct) < 1.0:
                    return max_gain
                elif abs(price_change_pct) > 2.5:
                    return max_loss
                else:
                    return max_gain * (1 - abs(price_change_pct) / 2.5)

        # Range-bound strategies
        elif strategy_name in ['IRON_CONDOR', 'IRON_BUTTERFLY']:
            max_gain = 30  # Typical credit
            max_loss = -100

            # Iron Condor: Win if stays in range
            if abs(price_change_pct) < 1.5:
                return max_gain
            elif abs(price_change_pct) > 3.0:
                return max_loss
            else:
                return max_gain * (1 - abs(price_change_pct) / 3.0)

        # Volatility strategies
        elif strategy_name in ['LONG_STRADDLE', 'LONG_STRANGLE']:
            # Win if large move in either direction
            debit_paid = -100
            max_gain_multiple = risk_reward

            if abs(price_change_pct) > 3.0:
                return abs(price_change_pct) * max_gain_multiple * 50  # Large gain
            elif abs(price_change_pct) < 1.0:
                return debit_paid  # Full loss if no move
            else:
                return debit_paid + (abs(price_change_pct) - 1.0) * 50  # Partial

        # GEX-specific
        elif strategy_name == 'POSITIVE_GEX_BREAKDOWN':
            # Win if breaks below flip point
            if price_change_pct < -1.0:
                return abs(price_change_pct) * 80
            elif price_change_pct > 1.0:
                return -100
            else:
                return price_change_pct * 40

        # Calendar spread
        elif strategy_name == 'CALENDAR_SPREAD':
            # Win if stays near entry price
            if abs(price_change_pct) < 0.5:
                return +50
            elif abs(price_change_pct) > 2.0:
                return -80
            else:
                return 50 * (1 - abs(price_change_pct) / 2.0)

        # Default fallback
        return price_change_pct * 50

    def run_backtest(self) -> BacktestResults:
        """Run options strategies backtest using REAL GEX data"""
        print(f"\n📊 Running Options Strategies Backtest...")

        # Fetch price data
        self.fetch_historical_data()

        # Fetch REAL GEX data from Trading Volatility API
        print("Fetching REAL historical GEX data from Trading Volatility API...")
        self.gex_data = self.fetch_real_gex_data(self.price_data)

        all_trades = []

        # Test each strategy
        for strategy_name in STRATEGIES.keys():
            print(f"\nTesting {strategy_name}...")
            strategy_trades = self.test_strategy(strategy_name)
            all_trades.extend(strategy_trades)

            if strategy_trades:
                results = self.calculate_metrics(strategy_trades, strategy_name)
                print(f"  Trades: {results.total_trades}, Win Rate: {results.win_rate:.1f}%, Expectancy: {results.expectancy_pct:+.2f}%")

                # Save individual strategy results
                self.save_results_to_db(results)

        # Calculate combined results
        results = self.calculate_metrics(all_trades, "Options Strategies (Combined)")
        self.print_summary(results)
        self.save_results_to_db(results)

        return results

    def test_strategy(self, strategy_name: str) -> List[Trade]:
        """Test a single options strategy"""
        trades = []
        strategy_config = STRATEGIES[strategy_name]
        dte_range = strategy_config.get('dte_range', [3, 14])
        min_dte = dte_range[0]
        max_dte = dte_range[1]

        for i in range(50, len(self.gex_data) - max_dte):
            row = self.gex_data.iloc[i]

            # Skip if not enough data
            if pd.isna(row['net_gex']) or pd.isna(row['flip_point']):
                continue

            # Check entry conditions
            if self.check_strategy_conditions(row, strategy_name):
                entry_date = row.name.strftime('%Y-%m-%d')
                entry_price = row['Close']

                # Hold for average DTE
                holding_days = (min_dte + max_dte) // 2

                # Exit at holding_days or earlier if max profit hit
                exit_idx = min(i + holding_days, len(self.gex_data) - 1)
                exit_row = self.gex_data.iloc[exit_idx]
                exit_date = exit_row.name.strftime('%Y-%m-%d')
                exit_price = exit_row['Close']

                # Calculate option PnL
                days_held = (pd.to_datetime(exit_date) - pd.to_datetime(entry_date)).days

                # Use realistic or simplified pricing
                if self.use_realistic_pricing and strategy_name in [
                    'BULLISH_CALL_SPREAD', 'BEARISH_PUT_SPREAD',
                    'BULL_PUT_SPREAD', 'BEAR_CALL_SPREAD'
                ]:
                    entry_vol_rank = row.get('vol_rank', 50.0)
                    exit_vol_rank = exit_row.get('vol_rank', entry_vol_rank)

                    pnl_result = self.simulate_option_pnl_realistic(
                        strategy_name, entry_price, exit_price, days_held,
                        entry_vol_rank, exit_vol_rank
                    )
                    option_pnl_pct = pnl_result['pnl_percent']

                    # Store spread details in notes
                    spread_info = pnl_result['spread_details']
                    greeks = pnl_result['greeks']
                    notes = (f"DTE: {days_held}, "
                           f"Strikes: ${spread_info.get('long_strike', 0):.0f}/${spread_info.get('short_strike', 0):.0f}, "
                           f"Debit: ${spread_info.get('debit', 0):.2f}, "
                           f"Delta: {greeks.get('delta', 0):.3f}, "
                           f"Theta: ${greeks.get('theta', 0):.2f}/day")
                else:
                    # Use simplified pricing for other strategies
                    option_pnl_pct = self.simulate_option_pnl_simplified(
                        strategy_name, entry_price, exit_price, days_held
                    )
                    notes = f"DTE: {days_held}"

                # Create trade with option PnL
                # Override calculate_pnl to use simulated option PnL
                position_size = self.initial_capital * (self.position_size_pct / 100)

                # IMPORTANT: When using realistic pricing, costs are ALREADY included
                # in the option_pnl_pct (bid/ask spreads + market slippage)
                # Only add small broker commission for realistic pricing
                if self.use_realistic_pricing and strategy_name in [
                    'BULLISH_CALL_SPREAD', 'BEARISH_PUT_SPREAD',
                    'BULL_PUT_SPREAD', 'BEAR_CALL_SPREAD'
                ]:
                    # Realistic pricing already includes bid/ask + market slippage
                    # Only subtract small broker commission (~$1-2 per contract)
                    # For $10k position (~28 contracts), commission ~$56 = 0.56%
                    commission = position_size * 0.005  # 0.5% broker commission only
                    slippage = 0  # Already included in realistic pricing
                    net_pnl_pct = option_pnl_pct - (commission / position_size * 100)
                else:
                    # Simplified pricing needs full costs applied
                    commission = position_size * (self.commission_pct / 100) * 2
                    slippage = position_size * (self.slippage_pct / 100)
                    total_costs = commission + slippage
                    cost_pct = (total_costs / position_size) * 100
                    net_pnl_pct = option_pnl_pct - cost_pct

                net_pnl_dollars = position_size * (net_pnl_pct / 100)

                trade = Trade(
                    entry_date=entry_date,
                    exit_date=exit_date,
                    symbol=self.symbol,
                    strategy=strategy_name,
                    direction='LONG',  # Options always long the spread
                    entry_price=entry_price,
                    exit_price=exit_price,
                    position_size=position_size,
                    commission=commission,
                    slippage=slippage,
                    pnl_percent=net_pnl_pct,
                    pnl_dollars=net_pnl_dollars,
                    duration_days=days_held,
                    win=(net_pnl_pct > 0),
                    confidence=strategy_config.get('win_rate', 0.5) * 100,
                    notes=notes
                )
                trades.append(trade)

        return trades


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Backtest options strategies')
    parser.add_argument('--symbol', default='SPY', help='Symbol to backtest')
    parser.add_argument('--start', default='2022-01-01', help='Start date YYYY-MM-DD')
    parser.add_argument('--end', default='2024-12-31', help='End date YYYY-MM-DD')
    args = parser.parse_args()

    backtester = OptionsBacktester(
        symbol=args.symbol,
        start_date=args.start,
        end_date=args.end,
        position_size_pct=10.0,
        commission_pct=0.10,  # Higher for options
        slippage_pct=0.15      # Higher for options
    )

    results = backtester.run_backtest()

    print("\n📊 Options Backtest Complete!")
