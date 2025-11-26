"""
SPX Institutional Paper Trader - $100 Million Capital
======================================================

Professional-grade SPX options trader designed for large capital deployment.

Key Features:
- SPX index options (cash-settled, European-style)
- 60/40 tax advantage (60% long-term, 40% short-term)
- Institutional slippage modeling
- Position sizing for $100M capital
- Liquidity constraints management

CRITICAL DIFFERENCES FROM SPY:
- SPX is cash-settled (no early assignment risk)
- European-style (only exercises at expiration)
- Multiplier: $100 per point (same as SPY)
- Wider bid/ask spreads
- Better tax treatment

CRITICAL: Uses SPX-specific GEX data from Trading Volatility API
"""

import pandas as pd
from datetime import datetime, timedelta, time as dt_time
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo
from database_adapter import get_connection
from polygon_data_fetcher import polygon_fetcher
from trading_costs import (
    TradingCostsCalculator, SPX_COSTS, INSTITUTIONAL_COSTS,
    OrderSide, SymbolType
)
import os

CENTRAL_TZ = ZoneInfo("America/Chicago")

# CRITICAL: Import UNIFIED Market Regime Classifier
# This is the SINGLE source of truth - SPX uses SPX data, NOT SPY data
try:
    from market_regime_classifier import (
        MarketRegimeClassifier,
        RegimeClassification,
        MarketAction,
        VolatilityRegime,
        GammaRegime,
        TrendRegime,
        get_classifier
    )
    UNIFIED_CLASSIFIER_AVAILABLE = True
    print("✅ SPX Trader: Unified Market Regime Classifier integrated")
except ImportError as e:
    UNIFIED_CLASSIFIER_AVAILABLE = False
    print(f"⚠️ SPX Trader: Unified Classifier not available: {e}")

# Import Trading Volatility API for SPX GEX data
try:
    from core_classes_and_engines import TradingVolatilityAPI
    TV_API_AVAILABLE = True
    print("✅ SPX Trader: Trading Volatility API available for SPX GEX data")
except ImportError as e:
    TV_API_AVAILABLE = False
    print(f"⚠️ SPX Trader: Trading Volatility API not available: {e}")


class SPXInstitutionalTrader:
    """
    SPX Options Trader for Institutional Capital ($100M)

    Designed for:
    - Large position management
    - Liquidity-aware execution
    - Risk controls for institutional mandates
    - Multi-strategy portfolio approach
    """

    def __init__(self, capital: float = 100_000_000):
        """
        Initialize SPX institutional trader.

        Args:
            capital: Starting capital (default $100M)
        """
        self.starting_capital = capital
        self.symbol = 'SPX'
        self.multiplier = 100  # $100 per index point

        # SPX-specific cost model (wider spreads than SPY)
        self.costs_calculator = TradingCostsCalculator(SPX_COSTS)

        # Position limits for institutional risk management
        self.max_position_pct = 0.05  # Max 5% of capital per position
        self.max_delta_exposure = 0.15  # Max 15% portfolio delta
        self.max_daily_trades = 50  # Limit daily activity
        self.max_contracts_per_trade = 500  # Liquidity constraint

        # Initialize database tables
        self._ensure_tables()

        # Risk parameters
        self.max_drawdown_pct = 10.0  # 10% max drawdown (tighter than retail)
        self.daily_loss_limit_pct = 2.0  # 2% daily loss limit
        self.vega_limit_pct = 0.5  # Max 0.5% portfolio in vega exposure

        # CRITICAL: Initialize Trading Volatility API for SPX GEX data
        if TV_API_AVAILABLE:
            self.api_client = TradingVolatilityAPI()
            print("✅ SPX Trader: API client ready for SPX GEX data")
        else:
            self.api_client = None

        # CRITICAL: Initialize UNIFIED Market Regime Classifier for SPX
        # This uses SPX-specific data, NOT SPY data
        if UNIFIED_CLASSIFIER_AVAILABLE:
            self.regime_classifier = get_classifier('SPX')  # SPX, not SPY!
            self.iv_history = []
            print("✅ SPX Trader: Unified classifier initialized with SPX symbol")
        else:
            self.regime_classifier = None
            self.iv_history = []

        print(f"✅ SPX Institutional Trader initialized")
        print(f"   Capital: ${self.starting_capital:,.0f}")
        print(f"   Max position: ${self.starting_capital * self.max_position_pct:,.0f}")
        print(f"   Max contracts/trade: {self.max_contracts_per_trade}")
        print(f"   Data Source: SPX GEX from Trading Volatility API")

    def _ensure_tables(self):
        """Create database tables for SPX trading"""
        conn = get_connection()
        c = conn.cursor()

        # SPX positions table
        c.execute("""
            CREATE TABLE IF NOT EXISTS spx_institutional_positions (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(10) DEFAULT 'SPX',
                strategy VARCHAR(100),
                action VARCHAR(50),
                entry_date DATE,
                entry_time TIME,
                strike DECIMAL(10,2),
                option_type VARCHAR(10),
                expiration_date DATE,
                contracts INTEGER,
                entry_price DECIMAL(10,4),
                entry_bid DECIMAL(10,4),
                entry_ask DECIMAL(10,4),
                entry_spot_price DECIMAL(10,2),
                entry_delta DECIMAL(8,4),
                entry_gamma DECIMAL(8,6),
                entry_vega DECIMAL(8,4),
                entry_theta DECIMAL(8,4),
                entry_iv DECIMAL(8,4),
                current_price DECIMAL(10,4),
                current_spot_price DECIMAL(10,2),
                unrealized_pnl DECIMAL(15,2) DEFAULT 0,
                unrealized_pnl_pct DECIMAL(8,4) DEFAULT 0,
                delta_exposure DECIMAL(15,2) DEFAULT 0,
                entry_commission DECIMAL(10,2) DEFAULT 0,
                entry_slippage DECIMAL(10,2) DEFAULT 0,
                confidence INTEGER,
                gex_regime VARCHAR(200),
                trade_reasoning TEXT,
                status VARCHAR(20) DEFAULT 'OPEN',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # SPX closed trades
        c.execute("""
            CREATE TABLE IF NOT EXISTS spx_institutional_closed_trades (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(10) DEFAULT 'SPX',
                strategy VARCHAR(100),
                action VARCHAR(50),
                strike DECIMAL(10,2),
                option_type VARCHAR(10),
                expiration_date DATE,
                contracts INTEGER,
                entry_date DATE,
                entry_time TIME,
                entry_price DECIMAL(10,4),
                entry_spot_price DECIMAL(10,2),
                exit_date DATE,
                exit_time TIME,
                exit_price DECIMAL(10,4),
                exit_spot_price DECIMAL(10,2),
                exit_reason VARCHAR(200),
                gross_pnl DECIMAL(15,2),
                total_commission DECIMAL(10,2),
                total_slippage DECIMAL(10,2),
                net_pnl DECIMAL(15,2),
                net_pnl_pct DECIMAL(8,4),
                hold_duration_minutes INTEGER,
                tax_treatment VARCHAR(20) DEFAULT '60/40',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # SPX configuration
        c.execute("""
            CREATE TABLE IF NOT EXISTS spx_institutional_config (
                id SERIAL PRIMARY KEY,
                key VARCHAR(100) UNIQUE,
                value TEXT,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Initialize config if not exists
        c.execute("""
            INSERT INTO spx_institutional_config (key, value)
            VALUES ('capital', %s)
            ON CONFLICT (key) DO NOTHING
        """, (str(self.starting_capital),))

        c.execute("""
            INSERT INTO spx_institutional_config (key, value)
            VALUES ('initialized', 'true')
            ON CONFLICT (key) DO NOTHING
        """)

        conn.commit()
        conn.close()

    def get_current_spot(self) -> float:
        """Get current SPX spot price"""
        try:
            # SPX is not directly tradeable, use ^SPX or calculate from ES futures
            price = polygon_fetcher.get_current_price('^SPX')
            if price and price > 0:
                return price

            # Fallback: Use SPY * 10 approximation
            spy_price = polygon_fetcher.get_current_price('SPY')
            if spy_price and spy_price > 0:
                return spy_price * 10

            return 5000.0  # Reasonable default
        except Exception as e:
            print(f"Error fetching SPX price: {e}")
            return 5000.0

    def calculate_position_size(
        self,
        entry_price: float,
        confidence: float,
        volatility_regime: str = 'normal'
    ) -> Tuple[int, Dict]:
        """
        Calculate optimal position size for institutional capital.

        Uses modified Kelly criterion with institutional constraints.

        Args:
            entry_price: Option premium price
            confidence: Trade confidence (0-100)
            volatility_regime: 'low', 'normal', 'high', 'extreme'

        Returns:
            (contracts, sizing_details)
        """
        # Get current available capital
        available = self.get_available_capital()

        # Base position size: Max 5% of capital per trade
        max_position_value = available * self.max_position_pct

        # Adjust for confidence (Kelly-inspired)
        # Higher confidence = closer to max position
        confidence_factor = (confidence / 100) * 0.5 + 0.5  # Range: 0.5-1.0

        # Volatility adjustment
        vol_adjustments = {
            'low': 1.2,      # Can take larger positions in low vol
            'normal': 1.0,
            'high': 0.7,     # Reduce size in high vol
            'extreme': 0.4   # Minimal size in extreme vol
        }
        vol_factor = vol_adjustments.get(volatility_regime, 1.0)

        # Adjusted position value
        position_value = max_position_value * confidence_factor * vol_factor

        # Calculate contracts
        cost_per_contract = entry_price * self.multiplier
        if cost_per_contract <= 0:
            return 0, {'error': 'Invalid entry price'}

        raw_contracts = int(position_value / cost_per_contract)

        # Apply liquidity constraint
        contracts = min(raw_contracts, self.max_contracts_per_trade)

        # For very large orders, warn about market impact
        market_impact_warning = None
        if contracts > 200:
            market_impact_warning = f"Large order ({contracts} contracts) may incur significant market impact"

        sizing_details = {
            'available_capital': available,
            'max_position_value': max_position_value,
            'confidence_factor': confidence_factor,
            'vol_factor': vol_factor,
            'adjusted_position_value': position_value,
            'cost_per_contract': cost_per_contract,
            'raw_contracts': raw_contracts,
            'final_contracts': contracts,
            'liquidity_constraint_applied': contracts < raw_contracts,
            'market_impact_warning': market_impact_warning,
            'total_premium': contracts * cost_per_contract
        }

        return contracts, sizing_details

    def get_available_capital(self) -> float:
        """Get current available capital (total - deployed)"""
        conn = get_connection()
        c = conn.cursor()

        # Get starting capital
        c.execute("SELECT value FROM spx_institutional_config WHERE key = 'capital'")
        result = c.fetchone()
        starting = float(result[0]) if result else self.starting_capital

        # Get realized P&L from closed trades
        c.execute("SELECT COALESCE(SUM(net_pnl), 0) FROM spx_institutional_closed_trades")
        realized = float(c.fetchone()[0] or 0)

        # Get capital deployed in open positions
        c.execute("""
            SELECT COALESCE(SUM(entry_price * contracts * 100), 0)
            FROM spx_institutional_positions
            WHERE status = 'OPEN'
        """)
        deployed = float(c.fetchone()[0] or 0)

        conn.close()

        return starting + realized - deployed

    def get_portfolio_greeks(self) -> Dict:
        """Calculate aggregate portfolio Greeks"""
        conn = get_connection()
        positions = pd.read_sql_query("""
            SELECT * FROM spx_institutional_positions WHERE status = 'OPEN'
        """, conn.raw_connection)
        conn.close()

        if positions.empty:
            return {
                'delta': 0,
                'gamma': 0,
                'vega': 0,
                'theta': 0,
                'total_delta': 0,
                'total_gamma': 0,
                'total_vega': 0,
                'total_theta': 0,
                'position_count': 0,
                'total_notional': 0
            }

        # Calculate weighted Greeks
        total_delta = 0
        total_gamma = 0
        total_vega = 0
        total_theta = 0
        total_notional = 0

        for _, pos in positions.iterrows():
            contracts = pos['contracts']
            multiplier = self.multiplier

            total_delta += (pos.get('entry_delta', 0) or 0) * contracts * multiplier
            total_gamma += (pos.get('entry_gamma', 0) or 0) * contracts * multiplier
            total_vega += (pos.get('entry_vega', 0) or 0) * contracts * multiplier
            total_theta += (pos.get('entry_theta', 0) or 0) * contracts * multiplier
            total_notional += pos['entry_price'] * contracts * multiplier

        return {
            'delta': total_delta,
            'gamma': total_gamma,
            'vega': total_vega,
            'theta': total_theta,
            'total_delta': total_delta,
            'total_gamma': total_gamma,
            'total_vega': total_vega,
            'total_theta': total_theta,
            'position_count': len(positions),
            'total_notional': total_notional
        }

    def check_risk_limits(self, proposed_trade: Dict) -> Tuple[bool, str]:
        """
        Check if proposed trade passes institutional risk limits.

        Args:
            proposed_trade: Trade details including contracts, delta, etc.

        Returns:
            (can_trade, reason)
        """
        # Get current portfolio state
        greeks = self.get_portfolio_greeks()
        capital = self.get_available_capital()

        # Check 1: Daily loss limit
        daily_pnl = self._get_daily_pnl()
        daily_loss_pct = (daily_pnl / self.starting_capital) * 100 if daily_pnl < 0 else 0
        if daily_loss_pct <= -self.daily_loss_limit_pct:
            return False, f"Daily loss limit breached: {daily_loss_pct:.2f}% <= -{self.daily_loss_limit_pct}%"

        # Check 2: Max drawdown
        max_drawdown = self._get_max_drawdown()
        if max_drawdown >= self.max_drawdown_pct:
            return False, f"Max drawdown breached: {max_drawdown:.2f}% >= {self.max_drawdown_pct}%"

        # Check 3: Delta exposure limit
        proposed_delta = proposed_trade.get('delta', 0) * proposed_trade.get('contracts', 0) * self.multiplier
        new_total_delta = greeks['total_delta'] + proposed_delta
        delta_exposure_pct = abs(new_total_delta / capital) * 100 if capital > 0 else 0

        if delta_exposure_pct > self.max_delta_exposure * 100:
            return False, f"Delta exposure limit: {delta_exposure_pct:.2f}% > {self.max_delta_exposure*100}%"

        # Check 4: Single position size limit
        trade_cost = proposed_trade.get('entry_price', 0) * proposed_trade.get('contracts', 0) * self.multiplier
        position_pct = (trade_cost / self.starting_capital) * 100
        if position_pct > self.max_position_pct * 100:
            return False, f"Position size limit: {position_pct:.2f}% > {self.max_position_pct*100}%"

        # Check 5: Daily trade count limit
        trade_count = self._get_daily_trade_count()
        if trade_count >= self.max_daily_trades:
            return False, f"Daily trade limit reached: {trade_count} >= {self.max_daily_trades}"

        return True, "All risk checks passed"

    def _get_daily_pnl(self) -> float:
        """Get today's P&L"""
        conn = get_connection()
        c = conn.cursor()
        today = datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d')

        c.execute("""
            SELECT COALESCE(SUM(net_pnl), 0)
            FROM spx_institutional_closed_trades
            WHERE exit_date = %s
        """, (today,))

        realized = float(c.fetchone()[0] or 0)

        c.execute("""
            SELECT COALESCE(SUM(unrealized_pnl), 0)
            FROM spx_institutional_positions
            WHERE status = 'OPEN'
        """)

        unrealized = float(c.fetchone()[0] or 0)
        conn.close()

        return realized + unrealized

    def _get_max_drawdown(self) -> float:
        """Calculate current drawdown from peak equity"""
        conn = get_connection()
        c = conn.cursor()

        # Get starting capital
        c.execute("SELECT value FROM spx_institutional_config WHERE key = 'capital'")
        starting = float(c.fetchone()[0] or self.starting_capital)

        # Get total realized P&L
        c.execute("SELECT COALESCE(SUM(net_pnl), 0) FROM spx_institutional_closed_trades")
        realized = float(c.fetchone()[0] or 0)

        # Get unrealized P&L
        c.execute("""
            SELECT COALESCE(SUM(unrealized_pnl), 0)
            FROM spx_institutional_positions WHERE status = 'OPEN'
        """)
        unrealized = float(c.fetchone()[0] or 0)

        conn.close()

        current_equity = starting + realized + unrealized
        peak_equity = starting + max(realized, 0)  # Simplified - would track actual peak

        if peak_equity <= 0:
            return 0

        drawdown_pct = ((peak_equity - current_equity) / peak_equity) * 100
        return max(0, drawdown_pct)

    def _get_daily_trade_count(self) -> int:
        """Get number of trades today"""
        conn = get_connection()
        c = conn.cursor()
        today = datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d')

        c.execute("""
            SELECT COUNT(*) FROM spx_institutional_positions
            WHERE entry_date = %s
        """, (today,))

        count = c.fetchone()[0] or 0
        conn.close()
        return count

    def execute_trade(
        self,
        action: str,
        option_type: str,
        strike: float,
        expiration: str,
        contracts: int,
        entry_price: float,
        bid: float,
        ask: float,
        spot_price: float,
        strategy: str,
        confidence: int,
        reasoning: str,
        greeks: Dict = None
    ) -> Optional[int]:
        """
        Execute an SPX options trade with institutional cost modeling.

        Args:
            action: 'BUY' or 'SELL'
            option_type: 'call' or 'put'
            strike: Strike price
            expiration: Expiration date (YYYY-MM-DD)
            contracts: Number of contracts
            entry_price: Option premium
            bid/ask: Current bid/ask
            spot_price: Current SPX spot
            strategy: Strategy name
            confidence: Trade confidence (0-100)
            reasoning: Trade reasoning
            greeks: Option Greeks dict

        Returns:
            Position ID if successful, None otherwise
        """
        # Check risk limits first
        proposed_trade = {
            'contracts': contracts,
            'entry_price': entry_price,
            'delta': greeks.get('delta', 0) if greeks else 0
        }

        can_trade, risk_reason = self.check_risk_limits(proposed_trade)
        if not can_trade:
            print(f"❌ Trade blocked: {risk_reason}")
            return None

        # Apply institutional slippage
        side = OrderSide.BUY if action.upper() == 'BUY' else OrderSide.SELL
        exec_price, slippage_details = self.costs_calculator.calculate_entry_price(
            bid=bid,
            ask=ask,
            contracts=contracts,
            side=side,
            symbol_type=SymbolType.INDEX
        )

        # Calculate commission
        commission = self.costs_calculator.calculate_commission(contracts)

        # Calculate total entry cost
        premium = exec_price * contracts * self.multiplier
        total_cost = premium + commission['total_commission']

        # Calculate slippage in dollars
        mid = (bid + ask) / 2
        slippage_dollars = abs(exec_price - mid) * contracts * self.multiplier

        # Insert into database
        conn = get_connection()
        c = conn.cursor()
        now = datetime.now(CENTRAL_TZ)

        c.execute("""
            INSERT INTO spx_institutional_positions (
                symbol, strategy, action, entry_date, entry_time,
                strike, option_type, expiration_date, contracts,
                entry_price, entry_bid, entry_ask, entry_spot_price,
                entry_delta, entry_gamma, entry_vega, entry_theta, entry_iv,
                current_price, current_spot_price,
                entry_commission, entry_slippage,
                confidence, gex_regime, trade_reasoning, status
            ) VALUES (
                'SPX', %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s,
                %s, %s,
                %s, %s, %s, 'OPEN'
            ) RETURNING id
        """, (
            strategy, action,
            now.strftime('%Y-%m-%d'), now.strftime('%H:%M:%S'),
            strike, option_type, expiration, contracts,
            exec_price, bid, ask, spot_price,
            greeks.get('delta', 0) if greeks else 0,
            greeks.get('gamma', 0) if greeks else 0,
            greeks.get('vega', 0) if greeks else 0,
            greeks.get('theta', 0) if greeks else 0,
            greeks.get('iv', 0) if greeks else 0,
            exec_price, spot_price,
            commission['total_commission'], slippage_dollars,
            confidence, 'SPX Institutional',
            reasoning
        ))

        position_id = c.fetchone()[0]
        conn.commit()
        conn.close()

        print(f"✅ SPX Trade Executed:")
        print(f"   Position ID: {position_id}")
        print(f"   {action} {contracts} SPX ${strike} {option_type.upper()}")
        print(f"   Entry: ${exec_price:.2f} (Mid: ${mid:.2f}, Slippage: ${slippage_dollars:.2f})")
        print(f"   Commission: ${commission['total_commission']:.2f}")
        print(f"   Total Cost: ${total_cost:,.2f}")

        return position_id

    def get_performance_summary(self) -> Dict:
        """Get comprehensive performance summary"""
        conn = get_connection()

        # Get closed trades
        closed = pd.read_sql_query("""
            SELECT * FROM spx_institutional_closed_trades
            ORDER BY exit_date DESC, exit_time DESC
        """, conn.raw_connection)

        # Get open positions
        open_pos = pd.read_sql_query("""
            SELECT * FROM spx_institutional_positions WHERE status = 'OPEN'
        """, conn.raw_connection)

        conn.close()

        if closed.empty and open_pos.empty:
            return {
                'total_trades': 0,
                'open_positions': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'realized_pnl': 0,
                'unrealized_pnl': 0,
                'net_pnl': 0,
                'avg_win': 0,
                'avg_loss': 0,
                'profit_factor': 0,
                'sharpe_ratio': 0,
                'max_drawdown': 0
            }

        # Calculate metrics
        total_realized = closed['net_pnl'].sum() if not closed.empty else 0
        total_unrealized = open_pos['unrealized_pnl'].sum() if not open_pos.empty else 0

        winning_trades_df = closed[closed['net_pnl'] > 0] if not closed.empty else pd.DataFrame()
        losing_trades_df = closed[closed['net_pnl'] <= 0] if not closed.empty else pd.DataFrame()
        winning_trades = len(winning_trades_df)
        losing_trades = len(losing_trades_df)
        win_rate = (winning_trades / len(closed) * 100) if len(closed) > 0 else 0

        # Calculate avg win and avg loss
        avg_win = winning_trades_df['net_pnl'].mean() if not winning_trades_df.empty else 0
        avg_loss = abs(losing_trades_df['net_pnl'].mean()) if not losing_trades_df.empty else 0

        # Calculate profit factor (sum of wins / sum of losses)
        total_wins = winning_trades_df['net_pnl'].sum() if not winning_trades_df.empty else 0
        total_losses = abs(losing_trades_df['net_pnl'].sum()) if not losing_trades_df.empty else 0
        profit_factor = (total_wins / total_losses) if total_losses > 0 else 0

        # Calculate Sharpe ratio (simplified - using daily returns if available)
        sharpe_ratio = 0
        if not closed.empty and len(closed) > 1:
            returns = closed['net_pnl'] / self.starting_capital
            if returns.std() > 0:
                sharpe_ratio = (returns.mean() / returns.std()) * (252 ** 0.5)  # Annualized

        total_commission = closed['total_commission'].sum() if not closed.empty else 0
        total_slippage = closed['total_slippage'].sum() if not closed.empty else 0

        return {
            'total_trades': len(closed),
            'open_positions': len(open_pos),
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'total_pnl': total_realized + total_unrealized,
            'realized_pnl': total_realized,
            'unrealized_pnl': total_unrealized,
            'total_realized_pnl': total_realized,
            'total_unrealized_pnl': total_unrealized,
            'net_pnl': total_realized + total_unrealized,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'sharpe_ratio': sharpe_ratio,
            'total_commission_paid': total_commission,
            'total_slippage_paid': total_slippage,
            'cost_drag': total_commission + total_slippage,
            'capital': self.starting_capital,
            'current_equity': self.starting_capital + total_realized + total_unrealized,
            'return_pct': ((total_realized + total_unrealized) / self.starting_capital) * 100,
            'max_drawdown': self._get_max_drawdown()
        }

    # ================================================================
    # SPX GEX DATA FETCHING - Uses SPX data, NOT SPY
    # ================================================================

    def get_spx_gex_data(self) -> Optional[Dict]:
        """
        Fetch SPX-specific GEX data from Trading Volatility API.

        CRITICAL: This uses 'SPX' symbol, NOT 'SPY'.
        SPX has its own gamma exposure profile that differs from SPY.
        """
        if not self.api_client:
            print("❌ SPX Trader: API client not available for GEX data")
            return None

        try:
            # Fetch SPX GEX data - NOT SPY!
            gex_data = self.api_client.get_net_gamma('SPX')

            if gex_data and not gex_data.get('error'):
                print(f"✅ SPX GEX Data: Net GEX ${gex_data.get('net_gex', 0)/1e9:.2f}B, Flip ${gex_data.get('flip_point', 0):.0f}")
                return gex_data
            else:
                print(f"⚠️ SPX GEX fetch returned error: {gex_data.get('error') if gex_data else 'No data'}")
                return None

        except Exception as e:
            print(f"❌ SPX GEX fetch error: {e}")
            return None

    def get_spx_skew_data(self) -> Optional[Dict]:
        """Fetch SPX-specific skew data"""
        if not self.api_client:
            return None

        try:
            skew_data = self.api_client.get_skew_data('SPX')
            return skew_data
        except Exception as e:
            print(f"⚠️ SPX skew fetch error: {e}")
            return None

    def _get_vix(self) -> float:
        """Get current VIX level"""
        try:
            vix_price = polygon_fetcher.get_current_price('^VIX')
            if vix_price and vix_price > 0:
                return vix_price
            return 17.0  # Default
        except Exception as e:
            print(f"⚠️ VIX fetch error: {e}")
            return 17.0

    def _get_spx_momentum(self) -> Dict:
        """Calculate SPX momentum from recent price action"""
        try:
            # Get SPX hourly data
            data = polygon_fetcher.get_price_history('^SPX', days=5, timeframe='hour', multiplier=1)

            if data is None or len(data) < 5:
                # Fallback: Use SPY * 10
                data = polygon_fetcher.get_price_history('SPY', days=5, timeframe='hour', multiplier=1)
                if data is not None:
                    data['Close'] = data['Close'] * 10

            if data is None or len(data) < 5:
                return {'1h': 0, '4h': 0, 'trend': 'neutral'}

            current_price = float(data['Close'].iloc[-1])
            price_1h_ago = float(data['Close'].iloc[-2]) if len(data) >= 2 else current_price
            price_4h_ago = float(data['Close'].iloc[-5]) if len(data) >= 5 else current_price

            change_1h = ((current_price - price_1h_ago) / price_1h_ago * 100)
            change_4h = ((current_price - price_4h_ago) / price_4h_ago * 100)

            if change_4h > 0.5:
                trend = 'strong_bullish'
            elif change_4h > 0.2:
                trend = 'bullish'
            elif change_4h < -0.5:
                trend = 'strong_bearish'
            elif change_4h < -0.2:
                trend = 'bearish'
            else:
                trend = 'neutral'

            return {'1h': round(change_1h, 2), '4h': round(change_4h, 2), 'trend': trend}

        except Exception as e:
            print(f"⚠️ SPX momentum calc error: {e}")
            return {'1h': 0, '4h': 0, 'trend': 'neutral'}

    # ================================================================
    # UNIFIED REGIME CLASSIFICATION - SPX-SPECIFIC
    # ================================================================

    def get_unified_regime_decision(self) -> Optional[Dict]:
        """
        Use the UNIFIED Market Regime Classifier with SPX data.

        This method:
        1. Fetches SPX GEX data (NOT SPY)
        2. Runs the unified classifier
        3. Returns trade recommendation

        ANTI-WHIPLASH: Classifier tracks regime persistence.
        """
        if not UNIFIED_CLASSIFIER_AVAILABLE or self.regime_classifier is None:
            print("⚠️ SPX: Unified classifier not available")
            return None

        if not self.api_client:
            print("⚠️ SPX: API client not available for GEX data")
            return None

        try:
            # Step 1: Fetch SPX-specific data
            gex_data = self.get_spx_gex_data()
            if not gex_data:
                print("❌ SPX: Could not fetch SPX GEX data")
                return None

            spot_price = gex_data.get('spot_price', 0) or self.get_current_spot()
            net_gex = gex_data.get('net_gex', 0)
            flip_point = gex_data.get('flip_point', spot_price * 0.98)

            # Get VIX and momentum
            vix = self._get_vix()
            momentum = self._get_spx_momentum()

            # Estimate IV from VIX (SPX IV typically tracks VIX closely)
            current_iv = vix / 100 * 0.9  # SPX IV ~ 90% of VIX

            # Track IV history
            self.iv_history.append(current_iv)
            if len(self.iv_history) > 252:
                self.iv_history = self.iv_history[-252:]

            historical_vol = current_iv * 0.85

            # Get MA status
            try:
                data = polygon_fetcher.get_price_history('^SPX', days=60, timeframe='day', multiplier=1)
                if data is None or len(data) < 50:
                    data = polygon_fetcher.get_price_history('SPY', days=60, timeframe='day', multiplier=1)
                    if data is not None:
                        data['Close'] = data['Close'] * 10

                if data is not None and len(data) >= 50:
                    ma_20 = float(data['Close'].tail(20).mean())
                    ma_50 = float(data['Close'].tail(50).mean())
                    above_20ma = spot_price > ma_20
                    above_50ma = spot_price > ma_50
                else:
                    above_20ma = True
                    above_50ma = True
            except:
                above_20ma = True
                above_50ma = True

            # ============================================================
            # RUN THE UNIFIED CLASSIFIER FOR SPX
            # ============================================================
            regime = self.regime_classifier.classify(
                spot_price=spot_price,
                net_gex=net_gex,
                flip_point=flip_point,
                current_iv=current_iv,
                iv_history=self.iv_history,
                historical_vol=historical_vol,
                vix=vix,
                vix_term_structure="contango",
                momentum_1h=momentum.get('1h', 0),
                momentum_4h=momentum.get('4h', 0),
                above_20ma=above_20ma,
                above_50ma=above_50ma
            )

            # Log the classification
            print(f"""
{'='*60}
SPX UNIFIED REGIME CLASSIFICATION
{'='*60}
VOLATILITY: {regime.volatility_regime.value} (IV Rank: {regime.iv_rank:.0f}%)
GAMMA: {regime.gamma_regime.value} (GEX: ${regime.net_gex/1e9:.2f}B)
TREND: {regime.trend_regime.value}

>>> RECOMMENDED ACTION: {regime.recommended_action.value}
>>> CONFIDENCE: {regime.confidence:.0f}%
>>> BARS IN REGIME: {regime.bars_in_regime}

REASONING:
{regime.reasoning}
{'='*60}
""")

            # If STAY_FLAT, return None
            if regime.recommended_action == MarketAction.STAY_FLAT:
                return None

            # Get strategy params
            strategy_params = self.regime_classifier.get_strategy_for_action(
                regime.recommended_action, regime
            )

            # Map to trade format
            if regime.recommended_action == MarketAction.BUY_CALLS:
                action = 'BUY'
                option_type = 'call'
                strike = round(max(spot_price, flip_point) / 5) * 5
            elif regime.recommended_action == MarketAction.BUY_PUTS:
                action = 'BUY'
                option_type = 'put'
                strike = round(min(spot_price, flip_point) / 5) * 5
            elif regime.recommended_action == MarketAction.SELL_PREMIUM:
                # For SPX, use put credit spread for premium selling
                return {
                    'symbol': 'SPX',
                    'strategy': f"SPX Unified: SELL_PREMIUM",
                    'action': 'SELL',
                    'option_type': 'put_spread',
                    'strike': round(spot_price * 0.95 / 5) * 5,  # 5% OTM put
                    'confidence': int(regime.confidence),
                    'reasoning': regime.reasoning,
                    'regime': regime,
                    'spot_price': spot_price,
                    'is_unified': True
                }
            else:
                return None

            return {
                'symbol': 'SPX',
                'strategy': f"SPX Unified: {strategy_params.get('strategy_name', regime.recommended_action.value)}",
                'action': action,
                'option_type': option_type,
                'strike': strike,
                'dte': strategy_params.get('dte_range', (7, 14))[0],
                'confidence': int(regime.confidence),
                'reasoning': regime.reasoning,
                'regime': regime,
                'spot_price': spot_price,
                'is_unified': True
            }

        except Exception as e:
            print(f"❌ SPX regime decision error: {e}")
            import traceback
            traceback.print_exc()
            return None

    def find_and_execute_daily_trade(self) -> Optional[int]:
        """
        Find and execute today's SPX trade using UNIFIED classifier.

        Uses SPX-specific GEX data from Trading Volatility API.

        Returns:
            Position ID if trade executed, None otherwise
        """
        print("\n" + "="*60)
        print("SPX INSTITUTIONAL TRADER - DAILY TRADE SEARCH")
        print("="*60)

        # Check if we've already traded today
        conn = get_connection()
        c = conn.cursor()
        today = datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d')

        c.execute("""
            SELECT COUNT(*) FROM spx_institutional_positions
            WHERE entry_date = %s
        """, (today,))
        trades_today = c.fetchone()[0] or 0
        conn.close()

        if trades_today >= self.max_daily_trades:
            print(f"⚠️ Already at max daily trades ({trades_today}/{self.max_daily_trades})")
            return None

        # Get unified regime decision
        trade = self.get_unified_regime_decision()

        if not trade:
            print("❌ No trade opportunity found by unified classifier")
            return None

        if trade.get('confidence', 0) < 60:
            print(f"⚠️ Confidence too low: {trade.get('confidence', 0)}%")
            return None

        # Calculate position size
        spot = trade.get('spot_price', self.get_current_spot())

        # Estimate entry price (simplified - would need real options data)
        if trade['option_type'] in ['call', 'put']:
            entry_price = spot * 0.02  # ~2% of spot as rough estimate
        else:
            entry_price = spot * 0.01  # Credit spread

        contracts, sizing = self.calculate_position_size(
            entry_price=entry_price,
            confidence=trade['confidence'],
            volatility_regime='normal' if trade.get('regime') and trade['regime'].volatility_regime == VolatilityRegime.NORMAL else 'high'
        )

        if contracts == 0:
            print("❌ Position sizing returned 0 contracts")
            return None

        # Get expiration
        exp_date = datetime.now(CENTRAL_TZ) + timedelta(days=7)
        while exp_date.weekday() != 4:  # Friday
            exp_date += timedelta(days=1)
        expiration = exp_date.strftime('%Y-%m-%d')

        # Execute trade
        position_id = self.execute_trade(
            action=trade['action'],
            option_type=trade['option_type'],
            strike=trade['strike'],
            expiration=expiration,
            contracts=contracts,
            entry_price=entry_price,
            bid=entry_price * 0.95,
            ask=entry_price * 1.05,
            spot_price=spot,
            strategy=trade['strategy'],
            confidence=trade['confidence'],
            reasoning=trade['reasoning']
        )

        if position_id:
            print(f"\n✅ SPX TRADE EXECUTED - Position ID: {position_id}")
            print(f"   Strategy: {trade['strategy']}")
            print(f"   {trade['action']} {contracts} x {trade['option_type'].upper()} @ ${trade['strike']}")
            print(f"   Confidence: {trade['confidence']}%")

        return position_id


# Factory function
def create_spx_trader(capital: float = 100_000_000) -> SPXInstitutionalTrader:
    """Create an SPX institutional trader with specified capital"""
    return SPXInstitutionalTrader(capital=capital)


# Singleton instance for $100M trading
_spx_trader_100m = None

def get_spx_trader_100m() -> SPXInstitutionalTrader:
    """Get singleton SPX trader with $100M capital"""
    global _spx_trader_100m
    if _spx_trader_100m is None:
        _spx_trader_100m = SPXInstitutionalTrader(capital=100_000_000)
    return _spx_trader_100m


if __name__ == '__main__':
    # Initialize and display stats
    trader = get_spx_trader_100m()

    print("\n" + "=" * 60)
    print("SPX INSTITUTIONAL TRADER - $100M CAPITAL")
    print("=" * 60)

    print(f"\nCapital: ${trader.starting_capital:,.0f}")
    print(f"Available: ${trader.get_available_capital():,.0f}")

    print("\nRisk Limits:")
    print(f"  Max Position: {trader.max_position_pct*100}% = ${trader.starting_capital*trader.max_position_pct:,.0f}")
    print(f"  Max Delta Exposure: {trader.max_delta_exposure*100}%")
    print(f"  Daily Loss Limit: {trader.daily_loss_limit_pct}%")
    print(f"  Max Drawdown: {trader.max_drawdown_pct}%")
    print(f"  Max Contracts/Trade: {trader.max_contracts_per_trade}")

    print("\nPortfolio Greeks:")
    greeks = trader.get_portfolio_greeks()
    for k, v in greeks.items():
        print(f"  {k}: {v:,.2f}" if isinstance(v, float) else f"  {k}: {v}")

    print("\nPerformance Summary:")
    perf = trader.get_performance_summary()
    for k, v in perf.items():
        if isinstance(v, float):
            print(f"  {k}: ${v:,.2f}" if 'pnl' in k.lower() or 'capital' in k.lower() or 'equity' in k.lower() or 'commission' in k.lower() or 'slippage' in k.lower() or 'drag' in k.lower() else f"  {k}: {v:.2f}")
        else:
            print(f"  {k}: {v}")

    print("\n" + "=" * 60)
