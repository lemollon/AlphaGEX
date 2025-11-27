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
from typing import Dict, List, Optional, Tuple, Any
from zoneinfo import ZoneInfo
from database_adapter import get_connection
from trading_costs import (
    TradingCostsCalculator, SPX_COSTS, INSTITUTIONAL_COSTS,
    OrderSide, SymbolType
)
import os

CENTRAL_TZ = ZoneInfo("America/Chicago")

# CRITICAL: Import UNIFIED Data Provider (Tradier primary, Polygon fallback)
try:
    from unified_data_provider import (
        get_data_provider,
        get_quote,
        get_price,
        get_options_chain,
        get_gex,
        get_vix
    )
    UNIFIED_DATA_AVAILABLE = True
    print("✅ SPX Trader: Unified Data Provider (Tradier) integrated")
except ImportError as e:
    UNIFIED_DATA_AVAILABLE = False
    print(f"⚠️ SPX Trader: Unified Data Provider not available: {e}")
    # Fallback
    from polygon_data_fetcher import polygon_fetcher

# Legacy Polygon fallback
if not UNIFIED_DATA_AVAILABLE:
    from polygon_data_fetcher import polygon_fetcher

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

# CRITICAL: Import Database Logger for AI Thought Process logging
try:
    from autonomous_database_logger import AutonomousDatabaseLogger
    DB_LOGGER_AVAILABLE = True
    print("✅ SPX Trader: Database Logger available for AI thought process")
except ImportError as e:
    DB_LOGGER_AVAILABLE = False
    print(f"⚠️ SPX Trader: Database Logger not available: {e}")

# Import AI Reasoning for enhanced thought process
try:
    from autonomous_ai_reasoning import get_ai_reasoning
    AI_REASONING_AVAILABLE = True
    print("✅ SPX Trader: AI Reasoning Engine available")
except ImportError as e:
    AI_REASONING_AVAILABLE = False
    print(f"⚠️ SPX Trader: AI Reasoning not available: {e}")

# CRITICAL: Import Strategy Stats for backtester integration
try:
    from strategy_stats import get_strategy_stats, get_recent_changes
    STRATEGY_STATS_AVAILABLE = True
    print("✅ SPX Trader: Strategy Stats (Backtester Integration) available")
except ImportError as e:
    STRATEGY_STATS_AVAILABLE = False
    print(f"⚠️ SPX Trader: Strategy Stats not available: {e}")


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
        self.capital = capital  # Alias for compatibility
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

        # CRITICAL: Initialize Database Logger for AI Thought Process
        if DB_LOGGER_AVAILABLE:
            self.db_logger = AutonomousDatabaseLogger()
            self.db_logger.session_id = f"SPX-{self.db_logger.session_id}"
            print("✅ SPX Trader: Database Logger initialized for AI thought process")
        else:
            self.db_logger = None

        # Initialize AI Reasoning Engine
        if AI_REASONING_AVAILABLE:
            self.ai_reasoning = get_ai_reasoning()
            print("✅ SPX Trader: AI Reasoning Engine ready")
        else:
            self.ai_reasoning = None

        # Load backtest-informed parameters
        self.strategy_stats = self._load_strategy_stats()

        print(f"✅ SPX Institutional Trader initialized")
        print(f"   Capital: ${self.starting_capital:,.0f}")
        print(f"   Max position: ${self.starting_capital * self.max_position_pct:,.0f}")
        print(f"   Max contracts/trade: {self.max_contracts_per_trade}")
        print(f"   Data Source: SPX GEX from Trading Volatility API")
        print(f"   AI Logging: {'ENABLED' if self.db_logger else 'DISABLED'}")
        print(f"   Backtester Integration: {'ENABLED' if self.strategy_stats else 'DISABLED'}")

    # ============================================================================
    # BACKTESTER INTEGRATION - Use backtest results for informed trading
    # ============================================================================

    def _load_strategy_stats(self) -> Optional[Dict]:
        """Load strategy statistics from backtest results"""
        if not STRATEGY_STATS_AVAILABLE:
            return None

        try:
            stats = get_strategy_stats()
            if stats:
                proven_strategies = [k for k, v in stats.items()
                                   if v.get('total_trades', 0) >= 10]
                print(f"   📊 Loaded {len(proven_strategies)} proven strategies from backtest")
            return stats
        except Exception as e:
            print(f"⚠️ Could not load strategy stats: {e}")
            return None

    def get_backtest_params_for_strategy(self, strategy_name: str) -> Dict:
        """
        Get backtest-informed parameters for a specific strategy.

        Returns:
            Dict with win_rate, expectancy, sharpe, max_drawdown, etc.

        CRITICAL: avg_win and avg_loss MUST be set from backtest data.
        If not available, we use conservative estimates based on typical options returns.
        """
        # Conservative defaults for unproven strategies
        # These are INTENTIONALLY conservative to reduce position sizes
        DEFAULT_AVG_WIN = 8.0   # Realistic average win for options (~8%)
        DEFAULT_AVG_LOSS = 12.0  # Realistic average loss for options (~12%)
        DEFAULT_WIN_RATE = 0.55  # Conservative 55% win rate assumption

        default_result = {
            'win_rate': DEFAULT_WIN_RATE,
            'expectancy': 0.0,  # Neutral expectancy for unproven
            'sharpe_ratio': 0.0,
            'avg_win': DEFAULT_AVG_WIN,
            'avg_loss': DEFAULT_AVG_LOSS,
            'is_proven': False,
            'total_trades': 0,
            'source': 'default_conservative'
        }

        if not self.strategy_stats:
            return default_result

        def extract_stats(stats: Dict, source: str) -> Dict:
            """Helper to extract and validate stats from backtest data"""
            win_rate = stats.get('win_rate', DEFAULT_WIN_RATE)
            avg_win = stats.get('avg_win', 0.0)
            avg_loss = stats.get('avg_loss', 0.0)
            total_trades = stats.get('total_trades', 0)
            expectancy = stats.get('expectancy', 0.0)

            # CRITICAL: If avg_win/avg_loss are 0 or missing, use conservative defaults
            # This prevents Kelly from using unrealistic 20%/15% assumptions
            if avg_win == 0 or avg_win is None:
                avg_win = DEFAULT_AVG_WIN
                print(f"⚠️ Using default avg_win={DEFAULT_AVG_WIN}% for {source}")
            if avg_loss == 0 or avg_loss is None:
                avg_loss = DEFAULT_AVG_LOSS
                print(f"⚠️ Using default avg_loss={DEFAULT_AVG_LOSS}% for {source}")

            return {
                'win_rate': win_rate,
                'expectancy': expectancy,
                'sharpe_ratio': stats.get('sharpe_ratio', 0.0),
                'avg_win': abs(avg_win),  # Ensure positive
                'avg_loss': abs(avg_loss),  # Ensure positive
                'is_proven': total_trades >= 10,
                'total_trades': total_trades,
                'source': source
            }

        # Try exact match first
        if strategy_name in self.strategy_stats:
            return extract_stats(self.strategy_stats[strategy_name], 'backtest')

        # Try fuzzy matching for similar strategies
        # Normalize strategy name for matching
        normalized_name = strategy_name.upper().replace(' ', '_').replace(':', '_')

        for key in self.strategy_stats:
            normalized_key = key.upper().replace(' ', '_').replace(':', '_')
            # Check both directions for substring match
            if normalized_key in normalized_name or normalized_name in normalized_key:
                return extract_stats(self.strategy_stats[key], f'backtest_match:{key}')

        # Additional fuzzy matching: extract core strategy type
        core_strategies = ['CALL_SPREAD', 'PUT_SPREAD', 'IRON_CONDOR', 'STRADDLE',
                          'STRANGLE', 'BUTTERFLY', 'CONDOR', 'CREDIT_SPREAD']
        for core in core_strategies:
            if core in normalized_name:
                for key in self.strategy_stats:
                    if core in key.upper():
                        return extract_stats(self.strategy_stats[key], f'backtest_match:{key}')

        return default_result

    def should_trade_strategy(self, strategy_name: str, min_trades: int = 10,
                             min_expectancy: float = 0.5) -> Tuple[bool, str]:
        """
        Check if a strategy should be traded based on backtest performance.

        INSTITUTIONAL CRITERIA (stricter than retail):
        - Minimum 10 trades to be "proven"
        - Minimum 0.5% expectancy (not negative!)
        - Win rate validation

        Args:
            strategy_name: Name of the strategy
            min_trades: Minimum trades required to consider "proven"
            min_expectancy: Minimum expectancy % to allow trading (default 0.5% for institutional)

        Returns:
            (should_trade, reason)
        """
        params = self.get_backtest_params_for_strategy(strategy_name)

        # Check if proven
        if not params['is_proven']:
            # Unproven strategies can trade but with very conservative sizing
            return True, f"Unproven strategy ({params['total_trades']} trades) - using quarter-Kelly sizing"

        # INSTITUTIONAL GATE 1: Check expectancy (must be positive)
        if params['expectancy'] < 0:
            return False, f"❌ BLOCKED: Negative expectancy ({params['expectancy']:.2f}%)"

        # INSTITUTIONAL GATE 2: Check minimum expectancy threshold
        if params['expectancy'] < min_expectancy:
            return False, f"❌ BLOCKED: Expectancy too low ({params['expectancy']:.2f}% < {min_expectancy}% minimum)"

        # INSTITUTIONAL GATE 3: Check win rate (must be reasonable)
        if params['win_rate'] < 0.40:  # Less than 40% win rate is too risky
            return False, f"❌ BLOCKED: Win rate too low ({params['win_rate']*100:.0f}% < 40% minimum)"

        # INSTITUTIONAL GATE 4: Check risk/reward ratio makes sense
        avg_win = params.get('avg_win', 0)
        avg_loss = params.get('avg_loss', 0)
        if avg_loss > 0 and avg_win / avg_loss < 0.5:
            return False, f"❌ BLOCKED: Risk/Reward too poor ({avg_win:.1f}%/{avg_loss:.1f}%)"

        # All checks passed
        source = params.get('source', 'unknown')
        return True, f"✅ APPROVED: {params['total_trades']} trades, {params['win_rate']*100:.0f}% WR, {params['expectancy']:.2f}% expectancy ({source})"

    def calculate_kelly_from_backtest(self, strategy_name: str) -> float:
        """
        Calculate Kelly criterion position size from backtest results.

        Kelly % = W - [(1-W)/R]
        Where: W = win rate, R = risk/reward ratio (avg_win / avg_loss)

        Returns Kelly % (0.01 to 0.25 for institutional)

        CRITICAL: Uses conservative defaults from get_backtest_params_for_strategy()
        which ensures avg_win/avg_loss are never 0 or unrealistic values.
        """
        params = self.get_backtest_params_for_strategy(strategy_name)

        win_rate = params['win_rate']
        avg_win = params['avg_win']   # Already validated in get_backtest_params_for_strategy
        avg_loss = params['avg_loss']  # Already validated in get_backtest_params_for_strategy

        # Safety check: ensure avg_loss is never 0
        if avg_loss <= 0:
            avg_loss = 12.0  # Conservative default

        risk_reward = avg_win / avg_loss

        # Kelly formula: W - (1-W)/R
        kelly = win_rate - ((1 - win_rate) / risk_reward)

        # Log the Kelly calculation for transparency
        is_proven = params.get('is_proven', False)
        source = params.get('source', 'unknown')
        print(f"📊 Kelly Calc: W={win_rate:.1%}, AvgWin={avg_win:.1f}%, AvgLoss={avg_loss:.1f}%, "
              f"R/R={risk_reward:.2f}, RawKelly={kelly:.1%}, Source={source}, Proven={is_proven}")

        # Institutional quarter-Kelly for unproven strategies, half-Kelly for proven
        if is_proven:
            adjusted_kelly = kelly * 0.5  # Half-Kelly for proven
        else:
            adjusted_kelly = kelly * 0.25  # Quarter-Kelly for unproven (extra conservative)

        # Cap at 25% for institutional, minimum 1%
        final_kelly = max(0.01, min(0.25, adjusted_kelly))

        print(f"   Final Kelly: {final_kelly:.1%} ({'Half' if is_proven else 'Quarter'}-Kelly applied)")

        return final_kelly

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

        # SPX Position Sizing Audit Trail - COMPLIANCE REQUIREMENT
        # Tracks all sizing decisions with backtest parameters used
        c.execute("""
            CREATE TABLE IF NOT EXISTS spx_position_sizing_audit (
                id SERIAL PRIMARY KEY,
                trade_timestamp TIMESTAMP DEFAULT NOW(),
                strategy_name VARCHAR(200),
                position_id INTEGER,

                -- Backtest Parameters Used
                backtest_source VARCHAR(100),
                backtest_win_rate DECIMAL(6,4),
                backtest_avg_win DECIMAL(8,4),
                backtest_avg_loss DECIMAL(8,4),
                backtest_expectancy DECIMAL(8,4),
                backtest_total_trades INTEGER,
                is_proven BOOLEAN DEFAULT FALSE,

                -- Kelly Calculation
                raw_kelly_pct DECIMAL(8,4),
                applied_kelly_pct DECIMAL(8,4),
                kelly_adjustment VARCHAR(50),

                -- Position Sizing Factors
                available_capital DECIMAL(20,2),
                max_position_value DECIMAL(20,2),
                confidence_factor DECIMAL(6,4),
                vol_factor DECIMAL(6,4),
                backtest_factor DECIMAL(6,4),

                -- Final Result
                final_position_value DECIMAL(20,2),
                raw_contracts INTEGER,
                final_contracts INTEGER,
                liquidity_constraint_applied BOOLEAN DEFAULT FALSE,

                -- Notes
                sizing_notes TEXT
            )
        """)

        # Create index for efficient queries
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_spx_sizing_audit_date
            ON spx_position_sizing_audit(trade_timestamp DESC)
        """)

        # SPX Trade Activity table - ALL decisions and actions
        c.execute("""
            CREATE TABLE IF NOT EXISTS spx_trade_activity (
                id SERIAL PRIMARY KEY,
                activity_date DATE NOT NULL,
                activity_time TIME NOT NULL,
                activity_timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
                action_type VARCHAR(50) NOT NULL,
                symbol VARCHAR(10) DEFAULT 'SPX',
                details TEXT,
                spot_price DECIMAL(10,2),
                vix_level DECIMAL(8,2),
                net_gex DECIMAL(20,2),
                flip_point DECIMAL(10,2),
                ai_thought_process TEXT,
                ai_confidence INTEGER,
                position_id INTEGER,
                pnl_impact DECIMAL(15,2),
                success BOOLEAN DEFAULT TRUE,
                error_message TEXT
            )
        """)

        # Create index for efficient queries
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_spx_activity_date
            ON spx_trade_activity(activity_date DESC)
        """)

        conn.commit()
        conn.close()

    def _log_trade_activity(
        self,
        action_type: str,
        details: str,
        spot_price: float = None,
        vix: float = None,
        net_gex: float = None,
        flip_point: float = None,
        ai_thought_process: str = None,
        ai_confidence: int = None,
        position_id: int = None,
        pnl_impact: float = None,
        success: bool = True,
        error_message: str = None
    ):
        """Log activity to spx_trade_activity table with AI thought process"""
        try:
            conn = get_connection()
            c = conn.cursor()
            now = datetime.now(CENTRAL_TZ)

            c.execute("""
                INSERT INTO spx_trade_activity (
                    activity_date, activity_time, action_type, symbol,
                    details, spot_price, vix_level, net_gex, flip_point,
                    ai_thought_process, ai_confidence,
                    position_id, pnl_impact, success, error_message
                ) VALUES (%s, %s, %s, 'SPX', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                now.strftime('%Y-%m-%d'),
                now.strftime('%H:%M:%S'),
                action_type,
                details,
                spot_price,
                vix,
                net_gex,
                flip_point,
                ai_thought_process,
                ai_confidence,
                position_id,
                pnl_impact,
                success,
                error_message
            ))

            conn.commit()
            conn.close()
        except Exception as e:
            print(f"⚠️ Failed to log SPX trade activity: {e}")

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
        volatility_regime: str = 'normal',
        strategy_name: str = None
    ) -> Tuple[int, Dict]:
        """
        Calculate optimal position size for institutional capital.

        Uses modified Kelly criterion with institutional constraints.
        INTEGRATES BACKTESTER RESULTS for proven win rates.

        Args:
            entry_price: Option premium price
            confidence: Trade confidence (0-100)
            volatility_regime: 'low', 'normal', 'high', 'extreme'
            strategy_name: Strategy name for backtest lookup

        Returns:
            (contracts, sizing_details)
        """
        # Get current available capital
        available = self.get_available_capital()

        # BACKTESTER INTEGRATION: Get historical performance
        backtest_params = {}
        kelly_pct = 0.05  # Default 5%

        if strategy_name:
            # Check if strategy should be traded
            should_trade, reason = self.should_trade_strategy(strategy_name)
            if not should_trade:
                print(f"⚠️ Strategy blocked: {reason}")
                return 0, {'error': reason, 'blocked': True}

            # Get backtest-informed parameters
            backtest_params = self.get_backtest_params_for_strategy(strategy_name)

            # Calculate Kelly from backtest
            kelly_pct = self.calculate_kelly_from_backtest(strategy_name)

            if backtest_params.get('is_proven'):
                print(f"📊 Backtest-informed sizing: Kelly={kelly_pct*100:.1f}%, "
                      f"WinRate={backtest_params['win_rate']*100:.0f}%, "
                      f"Expectancy={backtest_params['expectancy']:.1f}%")

        # Base position size: Use Kelly % or max 5% of capital
        base_pct = min(kelly_pct, self.max_position_pct)
        max_position_value = available * base_pct

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

        # BACKTEST ADJUSTMENT: Reduce size for unproven strategies
        backtest_factor = 1.0
        if backtest_params and not backtest_params.get('is_proven'):
            backtest_factor = 0.5  # Half size for unproven strategies
            print(f"⚠️ Unproven strategy - reducing size by 50%")

        # Adjusted position value
        position_value = max_position_value * confidence_factor * vol_factor * backtest_factor

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
            'methodology': 'Kelly-Backtest Hybrid',
            'available_capital': available,
            'kelly_pct': kelly_pct * 100,
            'max_position_value': max_position_value,
            'confidence_factor': confidence_factor,
            'vol_factor': vol_factor,
            'backtest_factor': backtest_factor,
            'adjusted_position_value': position_value,
            'cost_per_contract': cost_per_contract,
            'raw_contracts': raw_contracts,
            'final_contracts': contracts,
            'liquidity_constraint_applied': contracts < raw_contracts,
            'market_impact_warning': market_impact_warning,
            'total_premium': contracts * cost_per_contract,
            'backtest_params': backtest_params
        }

        # AUDIT TRAIL: Log all sizing decisions for compliance
        self._log_position_sizing_audit(
            strategy_name=strategy_name or 'UNKNOWN',
            backtest_params=backtest_params,
            kelly_pct=kelly_pct,
            sizing_details=sizing_details
        )

        return contracts, sizing_details

    def _log_position_sizing_audit(
        self,
        strategy_name: str,
        backtest_params: Dict,
        kelly_pct: float,
        sizing_details: Dict,
        position_id: int = None
    ):
        """
        Log position sizing decision to audit table for compliance.

        CRITICAL: This creates an audit trail showing exactly how each
        position size was calculated, including all backtest parameters used.
        """
        try:
            conn = get_connection()
            c = conn.cursor()

            # Determine Kelly adjustment type
            is_proven = backtest_params.get('is_proven', False) if backtest_params else False
            kelly_adjustment = 'half-kelly' if is_proven else 'quarter-kelly'

            # Build sizing notes
            notes_parts = []
            if sizing_details.get('liquidity_constraint_applied'):
                notes_parts.append(f"Liquidity capped: {sizing_details.get('raw_contracts')} -> {sizing_details.get('final_contracts')}")
            if sizing_details.get('market_impact_warning'):
                notes_parts.append(sizing_details['market_impact_warning'])
            if sizing_details.get('backtest_factor', 1.0) < 1.0:
                notes_parts.append(f"Unproven strategy size reduction: {sizing_details.get('backtest_factor', 1.0)*100:.0f}%")

            sizing_notes = '; '.join(notes_parts) if notes_parts else None

            c.execute("""
                INSERT INTO spx_position_sizing_audit (
                    strategy_name, position_id,
                    backtest_source, backtest_win_rate, backtest_avg_win, backtest_avg_loss,
                    backtest_expectancy, backtest_total_trades, is_proven,
                    raw_kelly_pct, applied_kelly_pct, kelly_adjustment,
                    available_capital, max_position_value, confidence_factor, vol_factor, backtest_factor,
                    final_position_value, raw_contracts, final_contracts, liquidity_constraint_applied,
                    sizing_notes
                ) VALUES (
                    %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s
                )
            """, (
                strategy_name, position_id,
                backtest_params.get('source', 'unknown') if backtest_params else 'none',
                backtest_params.get('win_rate', 0) if backtest_params else 0,
                backtest_params.get('avg_win', 0) if backtest_params else 0,
                backtest_params.get('avg_loss', 0) if backtest_params else 0,
                backtest_params.get('expectancy', 0) if backtest_params else 0,
                backtest_params.get('total_trades', 0) if backtest_params else 0,
                is_proven,
                kelly_pct,  # Raw Kelly before adjustment
                sizing_details.get('kelly_pct', 0) / 100,  # Applied Kelly %
                kelly_adjustment,
                sizing_details.get('available_capital', 0),
                sizing_details.get('max_position_value', 0),
                sizing_details.get('confidence_factor', 1.0),
                sizing_details.get('vol_factor', 1.0),
                sizing_details.get('backtest_factor', 1.0),
                sizing_details.get('adjusted_position_value', 0),
                sizing_details.get('raw_contracts', 0),
                sizing_details.get('final_contracts', 0),
                sizing_details.get('liquidity_constraint_applied', False),
                sizing_notes
            ))

            conn.commit()
            conn.close()

            print(f"📝 Audit: Position sizing logged for {strategy_name}")

        except Exception as e:
            print(f"⚠️ Failed to log position sizing audit: {e}")

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

            # Log regime classification to trade activity
            self._log_trade_activity(
                action_type='REGIME_CLASSIFICATION',
                details=f"Action: {regime.recommended_action.value}, "
                        f"Vol: {regime.volatility_regime.value}, "
                        f"Gamma: {regime.gamma_regime.value}, "
                        f"Trend: {regime.trend_regime.value}",
                spot_price=spot_price,
                vix=vix,
                net_gex=net_gex,
                flip_point=flip_point,
                ai_thought_process=regime.reasoning,
                ai_confidence=int(regime.confidence)
            )

            # If STAY_FLAT, log detailed VIX/GEX context for why no action
            if regime.recommended_action == MarketAction.STAY_FLAT:
                # Build comprehensive no-action explanation
                vix_context = []
                if vix > 25:
                    vix_context.append(f"VIX elevated at {vix:.1f} (>25) - market stressed")
                elif vix < 15:
                    vix_context.append(f"VIX low at {vix:.1f} (<15) - complacency risk")
                else:
                    vix_context.append(f"VIX normal at {vix:.1f}")

                gex_context = []
                if net_gex > 0:
                    gex_context.append(f"Positive GEX (${net_gex/1e9:.2f}B) - dealers long gamma, dampened moves")
                else:
                    gex_context.append(f"Negative GEX (${net_gex/1e9:.2f}B) - dealers short gamma, amplified moves")

                if spot_price > flip_point:
                    gex_context.append(f"Price ${spot_price:.0f} ABOVE flip ${flip_point:.0f} - call gamma dominates")
                else:
                    gex_context.append(f"Price ${spot_price:.0f} BELOW flip ${flip_point:.0f} - put gamma dominates")

                no_action_reason = (
                    f"STAY_FLAT Decision Explained:\n"
                    f"VIX Analysis: {' | '.join(vix_context)}\n"
                    f"GEX Analysis: {' | '.join(gex_context)}\n"
                    f"Regime: Vol={regime.volatility_regime.value}, Gamma={regime.gamma_regime.value}, "
                    f"Trend={regime.trend_regime.value}\n"
                    f"Bars in regime: {regime.bars_in_regime} (waiting for confirmation)\n"
                    f"Classifier reasoning: {regime.reasoning}"
                )

                self._log_trade_activity(
                    action_type='STAY_FLAT',
                    details=no_action_reason[:500],  # Truncate for details field
                    spot_price=spot_price,
                    vix=vix,
                    net_gex=net_gex,
                    flip_point=flip_point,
                    ai_thought_process=no_action_reason,
                    ai_confidence=int(regime.confidence)
                )

                print(f"\n📊 VIX/GEX Context for STAY_FLAT:\n{no_action_reason}")
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
            self._log_trade_activity(
                action_type='MAX_TRADES_REACHED',
                details=f"Already at max daily trades ({trades_today}/{self.max_daily_trades})",
                success=False
            )
            print(f"⚠️ Already at max daily trades ({trades_today}/{self.max_daily_trades})")
            return None

        # Get unified regime decision
        trade = self.get_unified_regime_decision()

        if not trade:
            # Note: VIX context already logged in get_unified_regime_decision if STAY_FLAT
            print("❌ No trade opportunity found by unified classifier")
            return None

        if trade.get('confidence', 0) < 60:
            self._log_trade_activity(
                action_type='LOW_CONFIDENCE',
                details=f"Trade rejected - confidence {trade.get('confidence', 0)}% below 60% threshold",
                spot_price=trade.get('spot_price'),
                ai_thought_process=trade.get('reasoning'),
                ai_confidence=trade.get('confidence', 0),
                success=False
            )
            print(f"⚠️ Confidence too low: {trade.get('confidence', 0)}%")
            return None

        # Calculate position size
        spot = trade.get('spot_price', self.get_current_spot())

        # Estimate entry price (simplified - would need real options data)
        if trade['option_type'] in ['call', 'put']:
            entry_price = spot * 0.02  # ~2% of spot as rough estimate
        else:
            entry_price = spot * 0.01  # Credit spread

        # BACKTESTER INTEGRATION: Pass strategy name for backtest-informed sizing
        contracts, sizing = self.calculate_position_size(
            entry_price=entry_price,
            confidence=trade['confidence'],
            volatility_regime='normal' if trade.get('regime') and trade['regime'].volatility_regime == VolatilityRegime.NORMAL else 'high',
            strategy_name=trade.get('strategy', '')
        )

        if contracts == 0:
            self._log_trade_activity(
                action_type='ZERO_CONTRACTS',
                details=f"Position sizing returned 0 contracts for {trade['strategy']}",
                spot_price=spot,
                ai_thought_process=f"Sizing: {sizing}",
                ai_confidence=trade.get('confidence', 0),
                success=False
            )
            print("❌ Position sizing returned 0 contracts")
            return None

        # Log position sizing decision with backtest info
        backtest_info = sizing.get('backtest_params', {})
        self._log_trade_activity(
            action_type='POSITION_SIZING',
            details=f"Sized {contracts} contracts for {trade['strategy']} @ ${trade['strike']}",
            spot_price=spot,
            ai_thought_process=f"Position sizing: {sizing.get('methodology', 'Kelly')} - "
                              f"Kelly: {sizing.get('kelly_pct', 0):.1f}%, "
                              f"Max capital: ${sizing.get('max_position_value', 0):,.0f}, "
                              f"Backtest WinRate: {backtest_info.get('win_rate', 0)*100:.0f}%",
            ai_confidence=trade.get('confidence', 0)
        )

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
            # Log successful trade execution
            self._log_trade_activity(
                action_type='TRADE_EXECUTED',
                details=f"✅ {trade['action']} {contracts} {trade['option_type'].upper()} @ ${trade['strike']} exp {expiration}",
                spot_price=spot,
                ai_thought_process=trade.get('reasoning'),
                ai_confidence=trade.get('confidence', 0),
                position_id=position_id
            )
            print(f"\n✅ SPX TRADE EXECUTED - Position ID: {position_id}")
            print(f"   Strategy: {trade['strategy']}")
            print(f"   {trade['action']} {contracts} x {trade['option_type'].upper()} @ ${trade['strike']}")
            print(f"   Confidence: {trade['confidence']}%")
        else:
            self._log_trade_activity(
                action_type='TRADE_FAILED',
                details=f"Trade execution failed for {trade['strategy']}",
                spot_price=spot,
                ai_thought_process=trade.get('reasoning'),
                ai_confidence=trade.get('confidence', 0),
                success=False,
                error_message="execute_trade returned None"
            )

        return position_id

    # ============================================================================
    # EXIT LOGIC - CRITICAL FOR POSITION MANAGEMENT
    # ============================================================================

    def auto_manage_positions(self) -> List[Dict]:
        """
        AUTONOMOUS: Manage all open SPX positions
        Checks exit conditions and closes positions when criteria are met

        Returns list of actions taken
        """
        conn = get_connection()
        positions = pd.read_sql_query("""
            SELECT * FROM spx_institutional_positions WHERE status = 'OPEN'
        """, conn.raw_connection)
        conn.close()

        if positions.empty:
            return []

        actions_taken = []

        # Get current market data
        gex_data = self.get_spx_gex_data()
        current_spot = gex_data.get('spot_price', 0) if gex_data else self.get_current_spot()
        vix = self._get_vix()

        for _, pos in positions.iterrows():
            try:
                # Calculate current P&L using improved Greeks-based estimation
                entry_value = float(pos['entry_price']) * int(pos['contracts']) * self.multiplier
                entry_price = float(pos['entry_price'])
                entry_spot = float(pos['entry_spot_price'])

                # Estimate current price using all available Greeks
                current_price = self._estimate_option_price(
                    entry_price=entry_price,
                    entry_spot=entry_spot,
                    current_spot=current_spot,
                    delta=float(pos.get('entry_delta', 0.5) or 0.5),
                    gamma=float(pos.get('entry_gamma', 0.001) or 0.001),
                    theta=float(pos.get('entry_theta', -0.05) or -0.05),
                    vega=float(pos.get('entry_vega', 0.1) or 0.1),
                    entry_iv=float(pos.get('entry_iv', 0.15) or 0.15),
                    current_vix=vix,
                    expiration_date=str(pos['expiration_date']),
                    option_type=pos.get('option_type', 'call')
                )

                current_value = current_price * int(pos['contracts']) * self.multiplier
                unrealized_pnl = current_value - entry_value
                pnl_pct = (unrealized_pnl / entry_value * 100) if entry_value > 0 else 0

                # Update position
                self._update_position(int(pos['id']), current_price, current_spot, unrealized_pnl, pnl_pct)

                # Check exit conditions
                should_exit, reason = self._check_exit_conditions(
                    pos, pnl_pct, current_price, current_spot, gex_data or {}, vix
                )

                if should_exit:
                    self._close_position(int(pos['id']), current_price, unrealized_pnl, reason)

                    actions_taken.append({
                        'position_id': int(pos['id']),
                        'strategy': pos['strategy'],
                        'action': 'CLOSE',
                        'reason': reason,
                        'pnl': unrealized_pnl,
                        'pnl_pct': pnl_pct
                    })

                    self._log_trade_activity(
                        action_type='POSITION_CLOSED',
                        details=f"Closed {pos['strategy']}: P&L ${unrealized_pnl:+,.2f} ({pnl_pct:+.1f}%) - {reason}",
                        spot_price=current_spot,
                        vix=vix,
                        ai_thought_process=reason,
                        position_id=int(pos['id']),
                        pnl_impact=unrealized_pnl
                    )

            except Exception as e:
                print(f"Error managing SPX position {pos['id']}: {e}")
                continue

        return actions_taken

    def _estimate_option_price(
        self,
        entry_price: float,
        entry_spot: float,
        current_spot: float,
        delta: float,
        gamma: float,
        theta: float,
        vega: float,
        entry_iv: float,
        current_vix: float,
        expiration_date: str,
        option_type: str
    ) -> float:
        """
        Estimate current option price using Greeks-based Taylor expansion.

        This is a SIGNIFICANT improvement over simple delta estimation because:
        1. Includes gamma effect (second-order price sensitivity)
        2. Accounts for theta decay based on actual time passed
        3. Considers vega impact from IV changes (VIX as proxy)
        4. Handles direction properly for calls vs puts

        Formula (Taylor expansion):
        Price Change ≈ Delta * ΔS + 0.5 * Gamma * (ΔS)² + Theta * ΔT + Vega * ΔIV

        Args:
            entry_price: Option price at entry
            entry_spot: Underlying price at entry
            current_spot: Current underlying price
            delta: Position delta (signed for direction)
            gamma: Position gamma
            theta: Position theta (daily, negative for long options)
            vega: Position vega
            entry_iv: IV at entry (decimal)
            current_vix: Current VIX level
            expiration_date: Option expiration date string
            option_type: 'call' or 'put'

        Returns:
            Estimated current option price
        """
        try:
            # Calculate spot move (ΔS)
            spot_change = current_spot - entry_spot
            spot_change_pct = spot_change / entry_spot if entry_spot > 0 else 0

            # 1. DELTA EFFECT: First-order price sensitivity
            # For options on SPX, delta represents $ change per $1 spot move
            # But we need to normalize for the option price level
            delta_effect = delta * spot_change

            # 2. GAMMA EFFECT: Second-order price sensitivity (convexity)
            # Gamma measures rate of delta change, accelerates profits/losses
            gamma_effect = 0.5 * gamma * (spot_change ** 2)

            # 3. THETA EFFECT: Time decay
            # Calculate days since entry (rough estimate from current time)
            now = datetime.now(CENTRAL_TZ)
            try:
                exp_date = datetime.strptime(expiration_date[:10], '%Y-%m-%d').replace(tzinfo=CENTRAL_TZ)
                days_to_exp = max(0, (exp_date - now).days)
                # Theta accelerates as we approach expiration
                # Estimate 1 day of decay for simplicity (would need entry_date for accuracy)
                days_held = 1  # Conservative estimate
                theta_effect = theta * days_held
            except:
                theta_effect = theta * 1  # Default 1 day decay

            # 4. VEGA EFFECT: IV sensitivity
            # Use VIX as proxy for SPX IV change
            # SPX IV typically moves ~0.9 of VIX
            current_iv = current_vix / 100 * 0.9  # Convert VIX to decimal IV
            iv_change = current_iv - entry_iv  # Change in IV (decimal)
            vega_effect = vega * (iv_change * 100)  # Vega is per 1% IV change

            # Combine all effects
            total_price_change = delta_effect + gamma_effect + theta_effect + vega_effect

            # Calculate new price (handle percentage vs absolute)
            # For SPX options, the effects are in $ terms per contract
            # Normalize by dividing by spot to get premium change
            price_change_normalized = total_price_change / current_spot if current_spot > 0 else 0

            estimated_price = entry_price + (entry_price * spot_change_pct * abs(delta) * 10)

            # More accurate: use the Greek-based calculation
            # Delta, gamma effects are per $1 of spot, need to scale to premium
            premium_scale = entry_price / entry_spot if entry_spot > 0 else 0.01
            estimated_price = entry_price + (delta * spot_change * premium_scale) + \
                              (0.5 * gamma * (spot_change ** 2) * premium_scale) + \
                              theta_effect + \
                              (vega * iv_change)

            # Ensure price stays positive and reasonable
            # Option can't be worth more than spot (for calls) or strike (for puts)
            estimated_price = max(0.01, estimated_price)
            estimated_price = min(estimated_price, entry_price * 10)  # Cap at 10x entry (sanity)

            return estimated_price

        except Exception as e:
            print(f"⚠️ Price estimation error: {e}, using simple delta method")
            # Fallback to simple delta estimation
            spot_move_pct = (current_spot - entry_spot) / entry_spot if entry_spot > 0 else 0
            simple_estimate = entry_price * (1 + delta * spot_move_pct * 10)
            return max(0.01, simple_estimate)

    def _update_position(self, position_id: int, current_price: float, current_spot: float,
                         unrealized_pnl: float, pnl_pct: float):
        """Update position with current values"""
        conn = get_connection()
        c = conn.cursor()

        c.execute("""
            UPDATE spx_institutional_positions
            SET current_price = %s, current_spot_price = %s,
                unrealized_pnl = %s, unrealized_pnl_pct = %s
            WHERE id = %s
        """, (current_price, current_spot, unrealized_pnl, pnl_pct, position_id))

        conn.commit()
        conn.close()

    def _check_exit_conditions(self, pos: Dict, pnl_pct: float, current_price: float,
                               current_spot: float, gex_data: Dict, vix: float) -> Tuple[bool, str]:
        """
        SPX EXIT STRATEGY - Institutional risk management
        More conservative than retail due to larger position sizes
        """
        # HARD STOP: -30% loss for institutional (tighter than retail)
        if pnl_pct <= -30:
            return True, f"🚨 HARD STOP: {pnl_pct:.1f}% loss - institutional risk limit"

        # EXPIRATION SAFETY: Close 1 day before for SPX (European style but be safe)
        try:
            exp_date = datetime.strptime(str(pos['expiration_date']), '%Y-%m-%d').replace(tzinfo=CENTRAL_TZ)
            dte = (exp_date - datetime.now(CENTRAL_TZ)).days
        except:
            dte = 7  # Default to 7 if parsing fails

        if dte <= 1:
            return True, f"⏰ EXPIRATION: {dte} DTE - closing before expiry"

        # VIX SPIKE: Exit if VIX spikes significantly (risk-off)
        entry_iv = float(pos.get('entry_iv', 0.15))
        current_iv = vix / 100 * 0.9  # SPX IV ~ 90% of VIX
        if current_iv > entry_iv * 1.5 and pnl_pct < 0:
            return True, f"📈 VIX SPIKE: IV up {((current_iv/entry_iv)-1)*100:.0f}% with losing position"

        # PROFIT TARGET: Take profits at +25% for institutional (lower than retail)
        if pnl_pct >= 25:
            return True, f"💰 PROFIT TARGET: +{pnl_pct:.1f}% (institutional target)"

        # GEX REGIME CHANGE: Exit if gamma regime flips
        entry_gex = float(pos.get('entry_net_gex', 0)) if pos.get('entry_net_gex') else 0
        current_gex = gex_data.get('net_gex', 0)
        if entry_gex != 0 and current_gex != 0:
            if (entry_gex > 0 and current_gex < 0) or (entry_gex < 0 and current_gex > 0):
                return True, f"📊 GEX FLIP: Regime changed from {'positive' if entry_gex > 0 else 'negative'} to {'positive' if current_gex > 0 else 'negative'}"

        # TIME DECAY: Exit credit spreads at 50% profit (theta decay captured)
        if pos.get('action') == 'SELL' and pnl_pct >= 50:
            return True, f"⏱️ THETA DECAY: Captured {pnl_pct:.0f}% of credit"

        return False, ""

    def _close_position(self, position_id: int, exit_price: float, realized_pnl: float, reason: str):
        """Close position - move from open positions to closed trades"""
        conn = get_connection()
        c = conn.cursor()
        now = datetime.now(CENTRAL_TZ)

        # Get position data
        c.execute("""
            SELECT symbol, strategy, action, strike, option_type, expiration_date,
                   contracts, entry_date, entry_time, entry_price,
                   entry_bid, entry_ask, entry_spot_price, confidence,
                   gex_regime, trade_reasoning, current_spot_price,
                   entry_commission, entry_slippage
            FROM spx_institutional_positions
            WHERE id = %s
        """, (position_id,))

        pos = c.fetchone()
        if not pos:
            print(f"⚠️ SPX Position {position_id} not found")
            conn.close()
            return

        (symbol, strategy, action, strike, option_type, expiration_date,
         contracts, entry_date, entry_time, entry_price,
         entry_bid, entry_ask, entry_spot_price, confidence,
         gex_regime, trade_reasoning, exit_spot_price,
         entry_commission, entry_slippage) = pos

        # Calculate exit costs
        exit_commission = self.costs_calculator.calculate_commission(contracts)
        total_commission = float(entry_commission or 0) + exit_commission['total_commission']
        total_slippage = float(entry_slippage or 0)  # Exit slippage included in realized_pnl estimate

        # Calculate hold duration
        try:
            entry_dt = datetime.strptime(f"{entry_date} {entry_time}", '%Y-%m-%d %H:%M:%S')
            hold_minutes = int((now.replace(tzinfo=None) - entry_dt).total_seconds() / 60)
        except:
            hold_minutes = 0

        # Calculate net P&L
        gross_pnl = realized_pnl
        net_pnl = gross_pnl - exit_commission['total_commission']
        entry_value = float(entry_price) * contracts * self.multiplier
        net_pnl_pct = (net_pnl / entry_value * 100) if entry_value > 0 else 0

        # Insert into closed trades
        c.execute("""
            INSERT INTO spx_institutional_closed_trades (
                symbol, strategy, action, strike, option_type, expiration_date,
                contracts, entry_date, entry_time, entry_price, entry_spot_price,
                exit_date, exit_time, exit_price, exit_spot_price, exit_reason,
                gross_pnl, total_commission, total_slippage, net_pnl, net_pnl_pct,
                hold_duration_minutes
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s
            )
        """, (
            symbol, strategy, action, strike, option_type, expiration_date,
            contracts, entry_date, entry_time, entry_price, entry_spot_price,
            now.strftime('%Y-%m-%d'), now.strftime('%H:%M:%S'),
            exit_price, exit_spot_price, reason,
            gross_pnl, total_commission, total_slippage, net_pnl, net_pnl_pct,
            hold_minutes
        ))

        # Update position status to CLOSED
        c.execute("""
            UPDATE spx_institutional_positions SET status = 'CLOSED' WHERE id = %s
        """, (position_id,))

        conn.commit()
        conn.close()

        print(f"✅ SPX Position {position_id} CLOSED: {reason}")
        print(f"   Net P&L: ${net_pnl:+,.2f} ({net_pnl_pct:+.1f}%)")
        print(f"   Hold time: {hold_minutes} minutes")

        # FEEDBACK LOOP: Update strategy stats from actual trading results
        self._update_strategy_stats_from_trade(
            strategy_name=strategy,
            pnl_pct=net_pnl_pct,
            is_win=(net_pnl > 0)
        )

    def _update_strategy_stats_from_trade(
        self,
        strategy_name: str,
        pnl_pct: float,
        is_win: bool
    ):
        """
        Update strategy statistics from actual closed trades.

        This creates a FEEDBACK LOOP where real trading results inform
        future position sizing through the strategy_stats system.

        The update is incremental - we recalculate stats from all closed
        trades for this strategy.
        """
        try:
            if not STRATEGY_STATS_AVAILABLE:
                return

            # Get all closed trades for this strategy
            conn = get_connection()
            c = conn.cursor()

            # Extract core strategy name (remove "SPX Unified:" prefix etc)
            core_strategy = strategy_name
            if ':' in strategy_name:
                core_strategy = strategy_name.split(':')[-1].strip()
            core_strategy = core_strategy.upper().replace(' ', '_')

            # Query all closed trades for this strategy
            c.execute("""
                SELECT net_pnl_pct
                FROM spx_institutional_closed_trades
                WHERE UPPER(REPLACE(strategy, ' ', '_')) LIKE %s
                ORDER BY exit_date DESC, exit_time DESC
            """, (f'%{core_strategy}%',))

            results = c.fetchall()
            conn.close()

            if len(results) < 5:  # Need at least 5 trades for meaningful stats
                print(f"📊 Strategy stats not updated - only {len(results)} trades (need 5+)")
                return

            # Calculate stats from closed trades
            pnl_pcts = [float(r[0] or 0) for r in results]
            wins = [p for p in pnl_pcts if p > 0]
            losses = [p for p in pnl_pcts if p <= 0]

            total_trades = len(pnl_pcts)
            win_rate = len(wins) / total_trades if total_trades > 0 else 0.5
            avg_win = sum(wins) / len(wins) if wins else 0
            avg_loss = abs(sum(losses) / len(losses)) if losses else 0

            # Calculate expectancy
            expectancy = (win_rate * avg_win) + ((1 - win_rate) * -avg_loss)

            # Calculate Sharpe (simplified)
            if len(pnl_pcts) > 1:
                avg_return = sum(pnl_pcts) / len(pnl_pcts)
                variance = sum((p - avg_return) ** 2 for p in pnl_pcts) / len(pnl_pcts)
                std_dev = variance ** 0.5
                sharpe = (avg_return / std_dev * (252 ** 0.5)) if std_dev > 0 else 0
            else:
                sharpe = 0

            # Update strategy stats file
            from strategy_stats import update_strategy_stats, log_change

            # Create backtest-compatible results dict
            live_results = {
                'strategy_name': core_strategy,
                'start_date': 'live_trading',
                'end_date': datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d'),
                'total_trades': total_trades,
                'winning_trades': len(wins),
                'losing_trades': len(losses),
                'win_rate': win_rate * 100,  # Convert to percentage for compatibility
                'avg_win_pct': avg_win,
                'avg_loss_pct': -avg_loss,  # Negative for losses
                'expectancy_pct': expectancy,
                'sharpe_ratio': sharpe,
                'total_return_pct': sum(pnl_pcts)
            }

            # Update using the existing strategy_stats system
            update_strategy_stats(core_strategy, live_results)

            # Also log the change
            log_change(
                category='LIVE_TRADING_FEEDBACK',
                item=core_strategy,
                old_value=f"trades={total_trades-1}",
                new_value=f"trades={total_trades}, WR={win_rate:.1%}, expectancy={expectancy:.2f}%",
                reason=f"Updated from live SPX trade (P&L: {pnl_pct:+.1f}%)"
            )

            # Update local cache
            self.strategy_stats = self._load_strategy_stats()

            print(f"📊 Strategy stats updated for {core_strategy}:")
            print(f"   Trades: {total_trades}, Win Rate: {win_rate:.1%}, Expectancy: {expectancy:.2f}%")

        except Exception as e:
            print(f"⚠️ Failed to update strategy stats from trade: {e}")

    def get_open_positions_summary(self) -> Dict:
        """Get summary of all open SPX positions"""
        conn = get_connection()
        c = conn.cursor()

        c.execute("""
            SELECT COUNT(*) as count,
                   COALESCE(SUM(unrealized_pnl), 0) as total_unrealized,
                   COALESCE(SUM(delta_exposure), 0) as total_delta
            FROM spx_institutional_positions WHERE status = 'OPEN'
        """)
        result = c.fetchone()
        conn.close()

        return {
            'open_positions': result[0] or 0,
            'total_unrealized_pnl': float(result[1] or 0),
            'total_delta_exposure': float(result[2] or 0)
        }


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
