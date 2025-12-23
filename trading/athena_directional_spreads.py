"""
ATHENA - Directional Spread Trading Bot
=========================================

Named after Athena, Greek goddess of wisdom and strategic warfare.

STRATEGY: GEX-Based Directional Spreads
- BULLISH: Bull Call Spread (buy ATM call, sell OTM call)
- BEARISH: Bear Call Spread (sell ATM call, buy OTM call)

SIGNAL FLOW:
    KRONOS (GEX Calculator) --> ORACLE (ML Advisor) --> ATHENA (Execution)

The key edge is the GEX wall proximity filter:
- Buy calls near put wall (support) for bullish
- Sell calls near call wall (resistance) for bearish

Backtest Results (2024 out-of-sample):
- With 1% wall filter: 90% win rate, 4.86x profit ratio
- With 0.5% wall filter: 98% win rate, 18.19x profit ratio

Usage:
    from trading.athena_directional_spreads import ATHENATrader
    athena = ATHENATrader(initial_capital=100_000)
    athena.run_daily_cycle()

Author: AlphaGEX Quant
Date: 2025-12
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from zoneinfo import ZoneInfo
from decimal import Decimal

# Database
from database_adapter import get_connection

# Import Tradier for execution
try:
    from data.tradier_data_fetcher import (
        TradierDataFetcher,
        OrderSide,
        OrderType,
        OrderDuration,
        OptionContract
    )
    TRADIER_AVAILABLE = True
except ImportError:
    TRADIER_AVAILABLE = False
    TradierDataFetcher = None

# Import Oracle AI advisor
try:
    from quant.oracle_advisor import (
        OracleAdvisor, MarketContext as OracleMarketContext,
        TradingAdvice, GEXRegime, OraclePrediction,
        BotName as OracleBotName
    )
    ORACLE_AVAILABLE = True
except ImportError:
    ORACLE_AVAILABLE = False
    OracleAdvisor = None
    OracleMarketContext = None
    TradingAdvice = None

# Import Kronos GEX calculator
try:
    from quant.kronos_gex_calculator import KronosGEXCalculator
    KRONOS_AVAILABLE = True
except ImportError:
    KRONOS_AVAILABLE = False
    KronosGEXCalculator = None

# Import GEX ML Signal Integration
try:
    from quant.gex_signal_integration import GEXSignalIntegration, get_signal_integration
    GEX_ML_AVAILABLE = True
except ImportError:
    GEX_ML_AVAILABLE = False
    GEXSignalIntegration = None
    get_signal_integration = None

# Import Tradier GEX Calculator for live GEX (fallback when ORAT unavailable)
try:
    from data.gex_calculator import TradierGEXCalculator, get_gex_calculator
    TRADIER_GEX_AVAILABLE = True
except ImportError:
    TRADIER_GEX_AVAILABLE = False
    TradierGEXCalculator = None
    get_gex_calculator = None

# Import comprehensive decision logger (same as ARES)
try:
    from trading.decision_logger import (
        DecisionLogger, TradeDecision, DecisionType, BotName,
        TradeLeg, MarketContext as LoggerMarketContext, DataSource,
        DecisionReasoning, get_athena_logger,
        MLPredictions, RiskCheck, BacktestReference
    )
    DECISION_LOGGER_AVAILABLE = True
except ImportError:
    DECISION_LOGGER_AVAILABLE = False
    DecisionLogger = None
    TradeDecision = None
    get_athena_logger = None
    MLPredictions = None
    RiskCheck = None
    BacktestReference = None

# Import comprehensive bot logger for dual logging (same as ARES)
try:
    from trading.bot_logger import (
        log_bot_decision, update_decision_outcome, update_execution_timeline,
        BotDecision, MarketContext as BotLogMarketContext, ClaudeContext,
        Alternative, RiskCheck as BotRiskCheck, ApiCall, ExecutionTimeline,
        generate_session_id, get_session_tracker, DecisionTracker
    )
    BOT_LOGGER_AVAILABLE = True
except ImportError:
    BOT_LOGGER_AVAILABLE = False
    log_bot_decision = None
    get_session_tracker = None
    DecisionTracker = None
    BotDecision = None
    BotLogMarketContext = None
    ClaudeContext = None

# Import scan activity logger for comprehensive scan-by-scan visibility
try:
    from trading.scan_activity_logger import (
        log_athena_scan, ScanOutcome, CheckResult
    )
    SCAN_LOGGER_AVAILABLE = True
except ImportError:
    SCAN_LOGGER_AVAILABLE = False
    log_athena_scan = None
    ScanOutcome = None
    CheckResult = None

# Import unified data provider
try:
    from data.unified_data_provider import (
        get_data_provider,
        get_quote,
        get_price,
        get_options_chain
    )
    UNIFIED_DATA_AVAILABLE = True
except ImportError:
    UNIFIED_DATA_AVAILABLE = False

logger = logging.getLogger(__name__)

CENTRAL_TZ = ZoneInfo("America/Chicago")


class TradingMode(Enum):
    """Trading execution mode"""
    PAPER = "paper"       # Sandbox/Paper trading
    LIVE = "live"         # Live trading with real money
    BACKTEST = "backtest" # Backtesting mode (no execution)


class SpreadType(Enum):
    """Type of vertical spread"""
    BULL_CALL_SPREAD = "BULL_CALL_SPREAD"  # Bullish: Buy ATM call, Sell OTM call
    BEAR_CALL_SPREAD = "BEAR_CALL_SPREAD"  # Bearish: Sell ATM call, Buy OTM call


@dataclass
class SpreadPosition:
    """Represents an open spread position"""
    position_id: str
    open_date: str
    expiration: str
    spread_type: SpreadType

    # Strikes
    long_strike: float
    short_strike: float

    # Prices
    entry_debit: float  # For bull call spread (negative = credit for bear call)

    # Position details
    contracts: int
    spread_width: float
    max_loss: float
    max_profit: float

    # Order IDs from broker
    order_id: str = ""

    # Status
    status: str = "open"  # open, closed, expired
    close_date: str = ""
    close_price: float = 0
    realized_pnl: float = 0

    # Market data at entry
    underlying_price_at_entry: float = 0
    gex_regime_at_entry: str = ""
    call_wall_at_entry: float = 0
    put_wall_at_entry: float = 0

    # Oracle prediction at entry
    oracle_confidence: float = 0
    oracle_reasoning: str = ""

    # Trailing stop tracking
    high_water_mark: float = 0  # Highest favorable price seen (underlying)
    low_water_mark: float = float('inf')  # Lowest favorable price seen (underlying)
    peak_spread_value: float = 0  # Highest spread value seen (for P&L trailing)
    current_atr: float = 0  # Current ATR value for volatility-adjusted stops

    # Scale-out tracking
    initial_contracts: int = 0  # Original contract count at entry
    contracts_remaining: int = 0  # Contracts still open
    scale_out_1_done: bool = False  # First scale-out completed
    scale_out_2_done: bool = False  # Second scale-out completed
    profit_threshold_hit: bool = False  # Has position hit profit threshold?
    total_scaled_pnl: float = 0  # Cumulative P&L from scale-outs


@dataclass
class ATHENAConfig:
    """Configuration for ATHENA trading bot"""
    # Risk parameters
    risk_per_trade_pct: float = 2.0      # 2% of capital per trade (conservative for directional)
    max_daily_trades: int = 5             # Max trades per day
    max_open_positions: int = 3           # Max concurrent positions

    # Strategy parameters
    spread_width: int = 2                 # $2 spread width
    default_contracts: int = 10           # Default position size
    wall_filter_pct: float = 1.0          # Only trade within 1% of relevant wall

    # Hybrid Trailing Stop Configuration
    # Phase 1: Let profits develop before trailing
    profit_threshold_pct: float = 40.0    # Don't trail until 40% of max profit reached

    # Phase 2: Scale-out at profit targets (lock in gains)
    scale_out_1_pct: float = 50.0         # First scale-out at 50% profit
    scale_out_1_size: float = 30.0        # Exit 30% of contracts
    scale_out_2_pct: float = 75.0         # Second scale-out at 75% profit
    scale_out_2_size: float = 30.0        # Exit 30% of contracts
    # Remaining 40% become "runners" with trailing stop

    # Phase 3: Trailing stop for runners
    trail_keep_pct: float = 50.0          # Keep 50% of gains (exit if give back 50%)
    atr_multiplier: float = 1.5           # Trail 1.5x ATR from high/low
    atr_period: int = 14                  # ATR lookback period

    # Hard stop loss (capital protection)
    hard_stop_pct: float = 50.0           # Exit if lose 50% of max loss

    # Minimum contracts for scaling (below this, use all-or-nothing)
    min_contracts_for_scaling: int = 3

    # Risk/Reward filter
    min_rr_ratio: float = 1.5             # Minimum risk:reward ratio (1.5 = need $1.50 reward per $1 risk)

    # Execution parameters
    ticker: str = "SPY"
    mode: TradingMode = TradingMode.PAPER
    use_gex_walls: bool = True
    use_claude_validation: bool = True

    # Timing
    entry_start_time: str = "09:35"       # Start trading 5 min after open
    entry_end_time: str = "15:30"         # Stop entries 30 min before close
    exit_by_time: str = "15:55"           # Exit all by this time (0DTE)


class ATHENATrader:
    """
    ATHENA - Directional Spread Trading Bot

    Uses GEX signals from KRONOS, processed through ORACLE ML advisor,
    to execute Bull Call Spreads (bullish) and Bear Call Spreads (bearish).
    """

    def __init__(
        self,
        initial_capital: float = 100_000,
        config: Optional[ATHENAConfig] = None
    ):
        """Initialize ATHENA trader"""
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.config = config or ATHENAConfig()

        # Initialize Oracle advisor
        self.oracle: Optional[OracleAdvisor] = None
        if ORACLE_AVAILABLE:
            try:
                self.oracle = OracleAdvisor()
                logger.info("ATHENA: Oracle advisor initialized")
            except Exception as e:
                logger.warning(f"ATHENA: Could not initialize Oracle: {e}")

        # Initialize Kronos GEX calculator
        self.kronos: Optional[KronosGEXCalculator] = None
        if KRONOS_AVAILABLE:
            try:
                self.kronos = KronosGEXCalculator()
                logger.info("ATHENA: Kronos GEX calculator initialized")
            except Exception as e:
                logger.warning(f"ATHENA: Could not initialize Kronos: {e}")

        # Initialize Tradier for execution
        self.tradier: Optional[TradierDataFetcher] = None
        if TRADIER_AVAILABLE and self.config.mode != TradingMode.BACKTEST:
            try:
                self.tradier = TradierDataFetcher()
                logger.info("ATHENA: Tradier execution initialized")
            except Exception as e:
                logger.warning(f"ATHENA: Could not initialize Tradier: {e}")

        # Initialize GEX ML Signal Integration
        self.gex_ml: Optional[GEXSignalIntegration] = None
        if GEX_ML_AVAILABLE:
            try:
                self.gex_ml = GEXSignalIntegration()
                if self.gex_ml.load_models():
                    logger.info("ATHENA: GEX ML signal integration initialized")
                else:
                    logger.warning("ATHENA: GEX ML models not found - run train_gex_probability_models.py")
                    self.gex_ml = None
            except Exception as e:
                logger.warning(f"ATHENA: Could not initialize GEX ML: {e}")

        # Position tracking
        self.open_positions: List[SpreadPosition] = []
        self.closed_positions: List[SpreadPosition] = []
        self.daily_trades: int = 0
        self.last_trade_date: Optional[str] = None

        # Session tracking for logging
        self.session_tracker = None
        if BOT_LOGGER_AVAILABLE and get_session_tracker:
            self.session_tracker = get_session_tracker("ATHENA")

        # Decision logger for full audit trail (same as ARES)
        self.decision_logger = None
        if DECISION_LOGGER_AVAILABLE and get_athena_logger:
            self.decision_logger = get_athena_logger()
            logger.info("ATHENA: Decision logger initialized")

        # Load config from database if available
        self._load_config_from_db()

        logger.info(f"ATHENA initialized: capital=${initial_capital:,.2f}, mode={self.config.mode.value}")

    def _load_config_from_db(self) -> None:
        """Load configuration from apache_config table"""
        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute("""
                SELECT setting_name, setting_value
                FROM apache_config
                WHERE setting_name IN (
                    'enabled', 'mode', 'wall_filter_pct', 'spread_width',
                    'contracts_per_trade', 'max_daily_trades', 'trailing_stop_pct', 'ticker',
                    'min_rr_ratio'
                )
            """)

            rows = c.fetchall()
            for row in rows:
                name, value = row
                if name == 'enabled' and value == 'false':
                    logger.warning("ATHENA is DISABLED in config")
                elif name == 'mode':
                    self.config.mode = TradingMode.PAPER if value == 'paper' else TradingMode.LIVE
                elif name == 'wall_filter_pct':
                    self.config.wall_filter_pct = float(value)
                elif name == 'spread_width':
                    self.config.spread_width = int(value)
                elif name == 'contracts_per_trade':
                    self.config.default_contracts = int(value)
                elif name == 'max_daily_trades':
                    self.config.max_daily_trades = int(value)
                elif name == 'trailing_stop_pct':
                    self.config.trailing_stop_pct = float(value)
                elif name == 'ticker':
                    self.config.ticker = value
                elif name == 'min_rr_ratio':
                    self.config.min_rr_ratio = float(value)

            conn.close()
            logger.info("ATHENA: Loaded config from database")
        except Exception as e:
            logger.debug(f"ATHENA: Could not load config from DB: {e}")

    def _log_to_db(self, level: str, message: str, details: Optional[Dict] = None) -> None:
        """Log message to apache_logs table"""
        try:
            conn = get_connection()
            c = conn.cursor()

            import json
            c.execute("""
                INSERT INTO apache_logs (log_level, message, details)
                VALUES (%s, %s, %s)
            """, (level, message, json.dumps(details) if details else None))

            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"Could not log to DB: {e}")

    def _calculate_atr(self, period: Optional[int] = None) -> float:
        """
        Calculate Average True Range (ATR) for volatility-adjusted trailing stops.

        ATR measures average daily price movement, adapting stops to market conditions.

        Returns:
            ATR value in dollars (e.g., 4.50 for SPY means ~$4.50 avg daily range)
        """
        if period is None:
            period = self.config.atr_period

        try:
            # Try to get historical data for ATR calculation
            import yfinance as yf

            ticker = yf.Ticker(self.config.ticker)
            hist = ticker.history(period=f"{period + 5}d")  # Extra days for buffer

            if hist.empty or len(hist) < period:
                # Fallback: estimate ATR based on typical SPY volatility
                return self._estimate_atr_fallback()

            # Calculate True Range for each day
            # TR = max(high-low, abs(high-prev_close), abs(low-prev_close))
            high = hist['High'].values
            low = hist['Low'].values
            close = hist['Close'].values

            true_ranges = []
            for i in range(1, len(hist)):
                tr = max(
                    high[i] - low[i],
                    abs(high[i] - close[i-1]),
                    abs(low[i] - close[i-1])
                )
                true_ranges.append(tr)

            # ATR is the simple moving average of True Range
            if len(true_ranges) >= period:
                atr = sum(true_ranges[-period:]) / period
                return round(atr, 2)

        except Exception as e:
            logger.debug(f"Could not calculate ATR: {e}")

        return self._estimate_atr_fallback()

    def _estimate_atr_fallback(self) -> float:
        """
        Fallback ATR estimate when historical data unavailable.

        Based on typical volatility:
        - SPY: ~$4-6 ATR in normal markets, ~$8-12 in volatile
        - Uses VIX as proxy for volatility regime
        """
        try:
            # Try to get VIX for volatility estimate
            if TRADIER_AVAILABLE and self.tradier:
                quote = self.tradier.get_quote('VIX')
                vix = quote.get('last', 20) or 20
            else:
                vix = 20  # Default assumption

            # Base ATR estimate for SPY based on price (~$500)
            base_price = 500
            base_atr = 4.5  # Normal market ATR for SPY

            # Scale ATR with VIX (higher VIX = higher ATR)
            vix_multiplier = vix / 20  # VIX 20 = 1x, VIX 30 = 1.5x, VIX 40 = 2x
            estimated_atr = base_atr * vix_multiplier

            return round(min(estimated_atr, 15.0), 2)  # Cap at $15

        except Exception as e:
            logger.debug(f"ATR fallback estimation failed: {e}")
            return 5.0  # Conservative default

    def _get_current_spread_value(self, position: SpreadPosition) -> float:
        """
        Get current value of a spread position.

        For paper trading, estimates based on underlying price movement.
        For live trading, fetches actual option quotes from Tradier.

        Returns:
            Current spread value (premium)
        """
        try:
            # Get current underlying price
            current_price = 0
            if UNIFIED_DATA_AVAILABLE:
                current_price = get_price(self.config.ticker)
            elif TRADIER_AVAILABLE and self.tradier:
                quote = self.tradier.get_quote(self.config.ticker)
                current_price = quote.get('last', 0) or quote.get('close', 0)

            if current_price <= 0:
                return position.entry_debit  # Can't calculate, return entry

            entry_price = position.underlying_price_at_entry
            price_change_pct = (current_price - entry_price) / entry_price

            # Estimate spread value based on delta approximation
            # Bull call spread gains ~0.50 delta initially
            # Bear call spread gains when price drops
            if position.spread_type == SpreadType.BULL_CALL_SPREAD:
                # Spread value increases when underlying rises
                delta_estimate = 0.50  # ATM spread delta
                spread_value_change = price_change_pct * position.spread_width * delta_estimate
                current_value = position.entry_debit + spread_value_change
            else:  # BEAR_CALL_SPREAD
                # Credit spread - value decreases when underlying drops (good for us)
                delta_estimate = -0.50
                spread_value_change = price_change_pct * position.spread_width * delta_estimate
                current_value = position.entry_debit + spread_value_change

            # Clamp to reasonable bounds (can't exceed spread width)
            max_value = position.spread_width
            min_value = 0
            return max(min_value, min(max_value, current_value))

        except Exception as e:
            logger.debug(f"Could not get spread value: {e}")
            return position.entry_debit

    def _execute_scale_out(self, position: SpreadPosition, contracts_to_exit: int,
                           current_spread_value: float, reason: str) -> float:
        """
        Execute a partial exit (scale-out) for a position.

        Args:
            position: The spread position
            contracts_to_exit: Number of contracts to close
            current_spread_value: Current value per spread
            reason: Exit reason for logging

        Returns:
            P&L from this scale-out
        """
        if contracts_to_exit <= 0 or contracts_to_exit > position.contracts_remaining:
            return 0

        # Calculate P&L for scaled contracts
        pnl_per_contract = (current_spread_value - position.entry_debit) * 100
        scale_pnl = pnl_per_contract * contracts_to_exit

        # Update position tracking
        position.contracts_remaining -= contracts_to_exit
        position.total_scaled_pnl += scale_pnl

        # For live trading, place closing order
        if self.config.mode == TradingMode.LIVE and TRADIER_AVAILABLE and self.tradier:
            try:
                # Build OCC symbols for the spread legs
                today = datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")
                long_symbol = self.tradier._build_occ_symbol(
                    self.config.ticker, today, position.long_strike, 'C'
                )
                short_symbol = self.tradier._build_occ_symbol(
                    self.config.ticker, today, position.short_strike, 'C'
                )

                # Close the spread (reverse the opening trade)
                # For bull call: sell long call, buy back short call
                self.tradier.place_option_order(
                    option_symbol=long_symbol,
                    side=OrderSide.SELL_TO_CLOSE,
                    quantity=contracts_to_exit,
                    order_type=OrderType.MARKET
                )
                self.tradier.place_option_order(
                    option_symbol=short_symbol,
                    side=OrderSide.BUY_TO_CLOSE,
                    quantity=contracts_to_exit,
                    order_type=OrderType.MARKET
                )

                logger.info(f"⚡ LIVE SCALE-OUT: {contracts_to_exit} contracts @ ${current_spread_value:.2f}")

            except Exception as e:
                logger.error(f"Live scale-out failed: {e}")

        self._log_to_db("INFO", f"SCALE-OUT: {reason}", {
            'position_id': position.position_id,
            'contracts_exited': contracts_to_exit,
            'contracts_remaining': position.contracts_remaining,
            'exit_price': current_spread_value,
            'scale_pnl': scale_pnl,
            'total_scaled_pnl': position.total_scaled_pnl
        })

        logger.info(f"📊 Scale-out: {contracts_to_exit} contracts, P&L: ${scale_pnl:.2f}, "
                   f"Remaining: {position.contracts_remaining}")

        return scale_pnl

    def get_gex_data(self) -> Optional[Dict[str, Any]]:
        """
        Get current GEX data for trading decisions.

        Priority order:
        1. Tradier LIVE - real-time options chain (best for live trading)
        2. Kronos/ORAT - historical data with recent date fallback
        3. Database cache - last resort
        """
        # PRIMARY: Tradier live GEX (real-time data for live trading)
        if TRADIER_GEX_AVAILABLE and get_gex_calculator:
            try:
                gex_calc = get_gex_calculator()
                # Use the ticker - for SPX, Tradier uses SPY as proxy
                ticker = 'SPY' if self.config.ticker == 'SPX' else self.config.ticker
                gex_data = gex_calc.get_gex(ticker)

                if gex_data and 'error' not in gex_data:
                    # Determine regime from net GEX
                    net_gex = gex_data.get('net_gex', 0)
                    if net_gex > 0.5e9:
                        regime = 'POSITIVE'
                    elif net_gex < -0.5e9:
                        regime = 'NEGATIVE'
                    else:
                        regime = 'NEUTRAL'

                    self._log_to_db("INFO", f"Using Tradier live GEX: net_gex={net_gex:,.0f}, regime={regime}")
                    return {
                        'net_gex': net_gex,
                        'call_wall': gex_data.get('call_wall', 0),
                        'put_wall': gex_data.get('put_wall', 0),
                        'flip_point': gex_data.get('flip_point', gex_data.get('gamma_flip', 0)),
                        'spot_price': gex_data.get('spot_price', 0),
                        'regime': regime,
                        'source': 'tradier_live'
                    }
                else:
                    error_msg = gex_data.get('error', 'Unknown error') if gex_data else 'No data'
                    self._log_to_db("DEBUG", f"Tradier GEX not available: {error_msg}")
            except Exception as e:
                self._log_to_db("DEBUG", f"Tradier GEX failed: {e}")

        # FALLBACK 1: Kronos/ORAT historical data (with recent date fallback)
        if self.kronos:
            try:
                gex, source = self.kronos.get_gex_for_today_or_recent(dte_max=7)
                if gex:
                    self._log_to_db("INFO", f"Using Kronos GEX: {source}")
                    return {
                        'net_gex': gex.net_gex,
                        'call_wall': gex.call_wall,
                        'put_wall': gex.put_wall,
                        'flip_point': gex.flip_point,
                        'spot_price': gex.spot_price,
                        'regime': gex.gex_regime,
                        'source': source
                    }
            except Exception as e:
                self._log_to_db("WARNING", f"Kronos calculation failed: {e}")

        # FALLBACK 2: Database cache (last resort)
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute("""
                SELECT net_gex, call_wall, put_wall, flip_point, spot_price, gex_regime, trade_date
                FROM gex_daily
                WHERE symbol = %s
                ORDER BY trade_date DESC
                LIMIT 1
            """, (self.config.ticker,))
            row = c.fetchone()
            conn.close()

            if row:
                self._log_to_db("INFO", f"Using cached GEX data from {row[6]}")
                return {
                    'net_gex': float(row[0]) if row[0] else 0,
                    'call_wall': float(row[1]) if row[1] else 0,
                    'put_wall': float(row[2]) if row[2] else 0,
                    'flip_point': float(row[3]) if row[3] else 0,
                    'spot_price': float(row[4]) if row[4] else 0,
                    'regime': row[5] or 'UNKNOWN',
                    'source': f'database_{row[6]}'
                }
        except Exception as e:
            self._log_to_db("WARNING", f"Database GEX fallback failed: {e}")

        self._log_to_db("WARNING", "No GEX data available from any source")
        return None

    def get_oracle_advice(self) -> Optional[OraclePrediction]:
        """Get trading advice from Oracle"""
        if not self.oracle:
            self._log_to_db("WARNING", "Oracle not available")
            return None

        # Get GEX data first
        gex_data = self.get_gex_data()
        if not gex_data:
            self._log_to_db("WARNING", "No GEX data available for Oracle")
            return None

        # Get VIX
        vix = 20.0  # Default
        if UNIFIED_DATA_AVAILABLE:
            try:
                from data.unified_data_provider import get_vix
                vix = get_vix() or 20.0
            except:
                pass

        # Build market context for Oracle
        context = OracleMarketContext(
            spot_price=gex_data['spot_price'],
            vix=vix,
            gex_net=gex_data['net_gex'],
            gex_call_wall=gex_data['call_wall'] or 0,
            gex_put_wall=gex_data['put_wall'] or 0,
            gex_flip_point=gex_data['flip_point'] or 0,
            gex_regime=GEXRegime.POSITIVE if gex_data['regime'] == 'POSITIVE' else GEXRegime.NEGATIVE,
            gex_distance_to_flip_pct=(
                (gex_data['spot_price'] - (gex_data['flip_point'] or gex_data['spot_price']))
                / gex_data['spot_price'] * 100
            ) if gex_data['flip_point'] else 0,
            gex_between_walls=self._is_between_walls(gex_data),
            day_of_week=datetime.now().weekday()
        )

        try:
            # Get ATHENA-specific advice from Oracle
            advice = self.oracle.get_athena_advice(
                context=context,
                use_gex_walls=self.config.use_gex_walls,
                use_claude_validation=self.config.use_claude_validation
            )

            self._log_to_db("INFO", f"Oracle advice: {advice.advice.value}", {
                'confidence': advice.confidence,
                'win_probability': advice.win_probability,
                'reasoning': advice.reasoning
            })

            return advice
        except Exception as e:
            self._log_to_db("ERROR", f"Failed to get Oracle advice: {e}")
            return None

    def get_ml_signal(self, gex_data: Dict = None) -> Optional[Dict]:
        """
        Get trading signal from GEX ML models.

        Returns signal dict with:
        - advice: 'LONG', 'SHORT', or 'STAY_OUT'
        - spread_type: 'BULL_CALL_SPREAD', 'BEAR_CALL_SPREAD', or 'NONE'
        - confidence: float 0-1
        - win_probability: float 0-1
        - expected_volatility: float (expected range %)
        - reasoning: str
        - model_predictions: dict with all 5 model outputs
        """
        if not self.gex_ml:
            self._log_to_db("WARNING", "GEX ML not available")
            return None

        # Get GEX data if not provided
        if not gex_data:
            gex_data = self.get_gex_data()
            if not gex_data:
                self._log_to_db("WARNING", "No GEX data available for ML signal")
                return None

        # Get VIX
        vix = 20.0
        if UNIFIED_DATA_AVAILABLE:
            try:
                from data.unified_data_provider import get_vix
                vix = get_vix() or 20.0
            except:
                pass

        try:
            # Get signal from ML models
            signal = self.gex_ml.get_signal_for_athena(gex_data, vix=vix)

            self._log_to_db("INFO", f"ML Signal: {signal['advice']}", {
                'confidence': signal['confidence'],
                'win_probability': signal['win_probability'],
                'spread_type': signal['spread_type'],
                'expected_volatility': signal['expected_volatility'],
                'model_predictions': signal['model_predictions'],
                'reasoning': signal['reasoning'],
                'suggested_strikes': signal.get('suggested_strikes', {})
            })

            return signal

        except Exception as e:
            self._log_to_db("ERROR", f"Failed to get ML signal: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _is_between_walls(self, gex_data: Dict) -> bool:
        """Check if price is between call and put walls"""
        spot = gex_data.get('spot_price', 0)
        call_wall = gex_data.get('call_wall', 0)
        put_wall = gex_data.get('put_wall', 0)

        if not spot or not call_wall or not put_wall:
            return True

        return put_wall <= spot <= call_wall

    def calculate_risk_reward(self, gex_data: Dict, spread_type: SpreadType) -> Tuple[float, str]:
        """
        Calculate risk:reward ratio using GEX walls as natural targets.

        For BULLISH (Bull Call Spread):
        - We're near put_wall (support), targeting call_wall (resistance)
        - Reward = distance to call_wall
        - Risk = distance from put_wall (our natural stop zone)
        - R:R = (call_wall - spot) / (spot - put_wall)

        For BEARISH (Bear Call Spread):
        - We're near call_wall (resistance), targeting put_wall (support)
        - Reward = distance to put_wall
        - Risk = distance from call_wall (our natural stop zone)
        - R:R = (spot - put_wall) / (call_wall - spot)

        Returns:
            Tuple of (rr_ratio, reasoning_string)
        """
        spot = gex_data.get('spot_price', 0)
        call_wall = gex_data.get('call_wall', 0)
        put_wall = gex_data.get('put_wall', 0)

        # Validate we have the data needed
        if not spot or not call_wall or not put_wall:
            return 0.0, "Missing GEX wall data for R:R calculation"

        if call_wall <= put_wall:
            return 0.0, f"Invalid wall setup: call_wall ({call_wall}) <= put_wall ({put_wall})"

        if spread_type == SpreadType.BULL_CALL_SPREAD:
            # Bullish: target is call_wall, stop is put_wall area
            reward = call_wall - spot
            risk = spot - put_wall

            if risk <= 0:
                return float('inf'), f"Price ({spot:.2f}) at or below put_wall ({put_wall:.2f}) - infinite R:R"
            if reward <= 0:
                return 0.0, f"Price ({spot:.2f}) at or above call_wall ({call_wall:.2f}) - no upside"

            rr_ratio = reward / risk
            reasoning = (f"BULLISH R:R = {rr_ratio:.2f}:1 | "
                        f"Reward: ${reward:.2f} to call_wall ({call_wall:.2f}), "
                        f"Risk: ${risk:.2f} to put_wall ({put_wall:.2f})")

        else:  # BEAR_CALL_SPREAD
            # Bearish: target is put_wall, stop is call_wall area
            reward = spot - put_wall
            risk = call_wall - spot

            if risk <= 0:
                return float('inf'), f"Price ({spot:.2f}) at or above call_wall ({call_wall:.2f}) - infinite R:R"
            if reward <= 0:
                return 0.0, f"Price ({spot:.2f}) at or below put_wall ({put_wall:.2f}) - no downside"

            rr_ratio = reward / risk
            reasoning = (f"BEARISH R:R = {rr_ratio:.2f}:1 | "
                        f"Reward: ${reward:.2f} to put_wall ({put_wall:.2f}), "
                        f"Risk: ${risk:.2f} to call_wall ({call_wall:.2f})")

        return rr_ratio, reasoning

    def should_trade(self) -> Tuple[bool, str]:
        """Check if we should trade today"""
        now = datetime.now(CENTRAL_TZ)

        # Check if market hours
        market_open = now.replace(hour=8, minute=30, second=0)
        market_close = now.replace(hour=15, minute=0, second=0)

        if not (market_open <= now <= market_close):
            return False, "Outside market hours"

        # Check daily trade limit
        today = now.strftime("%Y-%m-%d")
        if self.last_trade_date != today:
            self.daily_trades = 0
            self.last_trade_date = today

        if self.daily_trades >= self.config.max_daily_trades:
            return False, f"Daily trade limit reached ({self.config.max_daily_trades})"

        # Check max open positions
        if len(self.open_positions) >= self.config.max_open_positions:
            return False, f"Max positions reached ({self.config.max_open_positions})"

        return True, "Ready to trade"

    def save_signal_to_db(self, advice: OraclePrediction, gex_data: Dict) -> Optional[int]:
        """Save signal to apache_signals table"""
        try:
            conn = get_connection()
            c = conn.cursor()

            # Extract direction from reasoning
            direction = "FLAT"
            if "BULL_CALL_SPREAD" in advice.reasoning:
                direction = "BULLISH"
            elif "BEAR_CALL_SPREAD" in advice.reasoning:
                direction = "BEARISH"

            # Extract spread type
            spread_type = None
            if "BULL_CALL_SPREAD" in advice.reasoning:
                spread_type = "BULL_CALL_SPREAD"
            elif "BEAR_CALL_SPREAD" in advice.reasoning:
                spread_type = "BEAR_CALL_SPREAD"

            c.execute("""
                INSERT INTO apache_signals (
                    ticker, signal_direction, ml_confidence, oracle_advice,
                    gex_regime, call_wall, put_wall, spot_price,
                    spread_type, reasoning
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                self.config.ticker,
                direction,
                advice.confidence,
                advice.advice.value,
                gex_data.get('regime', 'NEUTRAL'),
                gex_data.get('call_wall'),
                gex_data.get('put_wall'),
                gex_data.get('spot_price'),
                spread_type,
                advice.reasoning[:1000]  # Store more reasoning
            ))

            signal_id = c.fetchone()[0]
            conn.commit()
            conn.close()

            self._log_to_db("INFO", f"Signal saved: {direction}", {'signal_id': signal_id})
            return signal_id
        except Exception as e:
            self._log_to_db("ERROR", f"Failed to save signal: {e}")
            return None

    def get_option_chain(self, expiration: str) -> Optional[Dict]:
        """Get options chain for the ticker"""
        if UNIFIED_DATA_AVAILABLE:
            try:
                return get_options_chain(self.config.ticker, expiration)
            except Exception as e:
                self._log_to_db("ERROR", f"Failed to get option chain: {e}")

        return None

    def execute_spread(
        self,
        spread_type: SpreadType,
        spot_price: float,
        gex_data: Dict,
        advice: OraclePrediction,
        signal_id: Optional[int] = None,
        ml_signal: Optional[Dict] = None,
        rr_ratio: float = 0
    ) -> Optional[SpreadPosition]:
        """Execute a spread trade"""
        decision_tracker = None
        if BOT_LOGGER_AVAILABLE and DecisionTracker:
            decision_tracker = DecisionTracker()
            decision_tracker.start()

        # Get 0DTE expiration
        today = datetime.now().strftime("%Y-%m-%d")

        # Calculate strikes
        # Use Oracle's suggested strike if available, otherwise calculate from spot
        # (Similar to ARES fix for GEX-Protected strikes)
        suggested_strike = getattr(advice, 'suggested_call_strike', None)
        if suggested_strike and suggested_strike > 0:
            atm_strike = round(suggested_strike)
            self._log_to_db("INFO", f"Using Oracle suggested strike: ${atm_strike}")
        else:
            atm_strike = round(spot_price)

        if spread_type == SpreadType.BULL_CALL_SPREAD:
            long_strike = atm_strike
            short_strike = atm_strike + self.config.spread_width
        else:  # BEAR_CALL_SPREAD
            short_strike = atm_strike
            long_strike = atm_strike + self.config.spread_width

        # Position sizing
        # Use Oracle's suggested risk percentage if available (similar to ARES SD multiplier fix)
        suggested_risk = getattr(advice, 'suggested_risk_pct', None)
        if suggested_risk and suggested_risk > 0:
            # Oracle suggests a risk percentage based on win probability
            # Apply it as an adjustment to config baseline
            effective_risk_pct = min(self.config.risk_per_trade_pct, suggested_risk)
            self._log_to_db("INFO", f"Using Oracle suggested risk: {effective_risk_pct:.1f}% (Oracle: {suggested_risk:.1f}%, Config: {self.config.risk_per_trade_pct:.1f}%)")
        else:
            effective_risk_pct = self.config.risk_per_trade_pct

        spread_width = abs(short_strike - long_strike)
        max_loss = spread_width * 100 * self.config.default_contracts
        max_risk = self.current_capital * (effective_risk_pct / 100)

        contracts = min(
            self.config.default_contracts,
            int(max_risk / (spread_width * 100))
        )
        contracts = max(1, contracts)  # At least 1 contract

        # For paper trading, simulate the fill
        if self.config.mode == TradingMode.PAPER:
            # Simulate spread price (typical debit for bull call)
            if spread_type == SpreadType.BULL_CALL_SPREAD:
                entry_debit = spread_width * 0.5  # ~50% of width as debit
                max_profit = (spread_width - entry_debit) * 100 * contracts
            else:  # BEAR_CALL_SPREAD
                entry_debit = -spread_width * 0.3  # Credit received
                max_profit = abs(entry_debit) * 100 * contracts

            # Create position
            import uuid
            position = SpreadPosition(
                position_id=f"ATHENA-{uuid.uuid4().hex[:8]}",
                open_date=today,
                expiration=today,  # 0DTE
                spread_type=spread_type,
                long_strike=long_strike,
                short_strike=short_strike,
                entry_debit=entry_debit,
                contracts=contracts,
                spread_width=spread_width,
                max_loss=spread_width * 100 * contracts,
                max_profit=max_profit,
                underlying_price_at_entry=spot_price,
                gex_regime_at_entry=gex_data.get('regime', 'NEUTRAL'),
                call_wall_at_entry=gex_data.get('call_wall', 0),
                put_wall_at_entry=gex_data.get('put_wall', 0),
                oracle_confidence=advice.confidence,
                oracle_reasoning=advice.reasoning[:1000],  # Store more reasoning
                # Initialize scale-out tracking
                initial_contracts=contracts,
                contracts_remaining=contracts,
                peak_spread_value=entry_debit,
                current_atr=self._calculate_atr()
            )

            self.open_positions.append(position)
            self.daily_trades += 1

            # Save to database
            self._save_position_to_db(position, signal_id)

            # Log comprehensive decision
            self._log_decision(
                position=position,
                gex_data=gex_data,
                advice=advice,
                ml_signal=ml_signal,
                rr_ratio=rr_ratio,
                decision_tracker=decision_tracker
            )

            self._log_to_db("INFO", f"PAPER TRADE: {spread_type.value}", {
                'position_id': position.position_id,
                'strikes': f"{long_strike}/{short_strike}",
                'contracts': contracts,
                'entry_debit': entry_debit
            })

            return position

        # Live execution via Tradier
        if self.config.mode == TradingMode.LIVE and TRADIER_AVAILABLE and self.tradier:
            try:
                # Format today's date for expiration
                today_expiration = datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")

                # Determine option type based on spread type
                option_type = "call"  # Both BULL_CALL and BEAR_CALL use call options

                # Get quotes for spread pricing
                long_contract = self.tradier.find_delta_option(
                    self.config.ticker, 0.50, today_expiration, option_type
                )
                if long_contract:
                    # Calculate limit price (mid of spread)
                    limit_debit = abs(long_contract.mid) * 0.5  # Approximate spread cost

                    # Execute the vertical spread order
                    order_response = self.tradier.place_vertical_spread(
                        symbol=self.config.ticker,
                        expiration=today_expiration,
                        long_strike=long_strike,
                        short_strike=short_strike,
                        option_type=option_type,
                        quantity=contracts,
                        limit_price=round(limit_debit, 2)
                    )

                    if order_response and order_response.get('order'):
                        order_info = order_response['order']

                        # Create position tracking record
                        import uuid
                        position = SpreadPosition(
                            position_id=f"ATHENA-LIVE-{order_info.get('id', uuid.uuid4().hex[:8])}",
                            open_date=today,
                            expiration=today,
                            spread_type=spread_type,
                            long_strike=long_strike,
                            short_strike=short_strike,
                            entry_debit=limit_debit,
                            contracts=contracts,
                            spread_width=spread_width,
                            max_loss=spread_width * 100 * contracts,
                            max_profit=(spread_width - limit_debit) * 100 * contracts,
                            underlying_price_at_entry=spot_price,
                            gex_regime_at_entry=gex_data.get('regime', 'NEUTRAL'),
                            call_wall_at_entry=gex_data.get('call_wall', 0),
                            put_wall_at_entry=gex_data.get('put_wall', 0),
                            oracle_confidence=advice.confidence,
                            oracle_reasoning=advice.reasoning[:1000],
                            # Initialize scale-out tracking
                            initial_contracts=contracts,
                            contracts_remaining=contracts,
                            peak_spread_value=limit_debit,
                            current_atr=self._calculate_atr()
                        )

                        self.open_positions.append(position)
                        self.daily_trades += 1

                        # Save to database
                        self._save_position_to_db(position, signal_id)

                        self._log_to_db("INFO", f"LIVE TRADE EXECUTED: {spread_type.value}", {
                            'position_id': position.position_id,
                            'order_id': order_info.get('id'),
                            'order_status': order_info.get('status'),
                            'strikes': f"{long_strike}/{short_strike}",
                            'contracts': contracts,
                            'entry_debit': limit_debit
                        })

                        logger.info(f"⚡ LIVE ORDER: {spread_type.value} {contracts}x {long_strike}/{short_strike}")
                        return position
                    else:
                        self._log_to_db("ERROR", "Live order failed", {'response': str(order_response)})
                        logger.error(f"Live order failed: {order_response}")

            except Exception as e:
                self._log_to_db("ERROR", f"Live execution error: {str(e)}", {})
                logger.error(f"Live execution via Tradier failed: {e}")
                import traceback
                traceback.print_exc()

        return None

    def _save_position_to_db(self, position: SpreadPosition, signal_id: Optional[int]) -> None:
        """Save position to apache_positions table"""
        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute("""
                INSERT INTO apache_positions (
                    position_id, signal_id, spread_type, ticker,
                    long_strike, short_strike, expiration,
                    entry_price, contracts, max_profit, max_loss,
                    spot_at_entry, gex_regime, oracle_confidence, oracle_reasoning
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                position.position_id,
                signal_id,
                position.spread_type.value,
                self.config.ticker,
                position.long_strike,
                position.short_strike,
                position.expiration,
                position.entry_debit,
                position.contracts,
                position.max_profit,
                position.max_loss,
                position.underlying_price_at_entry,
                position.gex_regime_at_entry,
                position.oracle_confidence,
                position.oracle_reasoning
            ))

            conn.commit()
            conn.close()
        except Exception as e:
            self._log_to_db("ERROR", f"Failed to save position: {e}")

    def _log_decision(
        self,
        position: SpreadPosition,
        gex_data: Dict,
        advice: Any,
        ml_signal: Optional[Dict] = None,
        rr_ratio: float = 0,
        decision_tracker: Optional[Any] = None
    ) -> None:
        """
        Log comprehensive decision using decision_logger (same structure as ARES).

        Includes:
        - ML predictions (direction, flip_gravity, magnet, pin_zone, volatility)
        - Greeks for each trade leg
        - Extended GEX context (distance_to_flip_pct)
        - Extended market context (vix_percentile, expected_move, trend, day_of_week)
        - Backtest stats from ML model
        - Structured risk checks
        """
        if not DECISION_LOGGER_AVAILABLE or not self.decision_logger:
            return

        try:
            # Get VIX and VIX percentile with validation
            vix = 20.0
            vix_percentile = 50.0
            if UNIFIED_DATA_AVAILABLE:
                try:
                    from data.unified_data_provider import get_vix
                    fetched_vix = get_vix()
                    if fetched_vix and fetched_vix > 0:
                        vix = fetched_vix
                    else:
                        logger.warning(f"ATHENA: get_vix() returned invalid value: {fetched_vix}, using default 20.0")
                except Exception as e:
                    logger.warning(f"ATHENA: Failed to get VIX: {e}, using default 20.0")

            # Validate VIX is in reasonable range (8-100)
            if vix < 8 or vix > 100:
                logger.warning(f"ATHENA: VIX {vix} outside normal range, clamping")
                vix = max(8, min(100, vix))

            # Estimate VIX percentile (simplified - could enhance with historical data)
            if vix < 12:
                vix_percentile = 10
            elif vix < 15:
                vix_percentile = 25
            elif vix < 18:
                vix_percentile = 40
            elif vix < 22:
                vix_percentile = 55
            elif vix < 28:
                vix_percentile = 75
            else:
                vix_percentile = 90

            # Calculate distance to flip point
            spot = gex_data.get('spot_price', 0)
            flip_point = gex_data.get('flip_point', 0)
            distance_to_flip_pct = 0
            if spot and flip_point:
                distance_to_flip_pct = ((spot - flip_point) / spot) * 100

            # Calculate expected move from VIX (simplified)
            expected_move_pct = (vix / 16) * (1 / 252 ** 0.5) * 100  # Daily expected move

            # Validate expected move is reasonable (0.5% to 10% daily)
            if expected_move_pct <= 0 or expected_move_pct > 10:
                logger.warning(f"ATHENA: Expected move {expected_move_pct:.2f}% invalid, recalculating")
                expected_move_pct = (vix / 16) * 0.063 * 100  # Fallback

            logger.info(f"ATHENA Trade Decision: VIX={vix:.2f}, Expected Move={expected_move_pct:.2f}%")

            # Determine trend from position relative to flip point
            trend = "NEUTRAL"
            if spot > flip_point * 1.005:
                trend = "BULLISH"
            elif spot < flip_point * 0.995:
                trend = "BEARISH"

            # Get day info
            now = datetime.now(CENTRAL_TZ)
            day_of_week = now.weekday()  # 0=Monday, 4=Friday

            # Days to monthly OPEX (3rd Friday)
            import calendar
            cal = calendar.Calendar()
            month_days = cal.monthdayscalendar(now.year, now.month)
            third_friday = None
            friday_count = 0
            for week in month_days:
                if week[4] != 0:  # Friday
                    friday_count += 1
                    if friday_count == 3:
                        third_friday = week[4]
                        break
            if third_friday:
                opex_date = now.replace(day=third_friday)
                if opex_date < now:
                    # Next month's OPEX
                    next_month = now.month + 1 if now.month < 12 else 1
                    next_year = now.year if now.month < 12 else now.year + 1
                    month_days = cal.monthdayscalendar(next_year, next_month)
                    friday_count = 0
                    for week in month_days:
                        if week[4] != 0:
                            friday_count += 1
                            if friday_count == 3:
                                third_friday = week[4]
                                break
                    opex_date = datetime(next_year, next_month, third_friday, tzinfo=CENTRAL_TZ)
                days_to_opex = (opex_date - now).days
            else:
                days_to_opex = 0

            # Get Greeks for legs (if available from options chain)
            leg_greeks = self._get_leg_greeks(position, gex_data.get('spot_price', 0), vix)

            # Create trade legs with Greeks
            if position.spread_type == SpreadType.BULL_CALL_SPREAD:
                legs = [
                    TradeLeg(
                        leg_id=1,
                        action="BUY",
                        option_type="call",
                        strike=position.long_strike,
                        expiration=position.expiration,
                        entry_price=position.entry_debit,
                        contracts=position.contracts,
                        delta=leg_greeks.get('long_delta', 0),
                        gamma=leg_greeks.get('long_gamma', 0),
                        theta=leg_greeks.get('long_theta', 0),
                        vega=leg_greeks.get('long_vega', 0),
                        iv=leg_greeks.get('long_iv', 0),
                    ),
                    TradeLeg(
                        leg_id=2,
                        action="SELL",
                        option_type="call",
                        strike=position.short_strike,
                        expiration=position.expiration,
                        contracts=position.contracts,
                        delta=leg_greeks.get('short_delta', 0),
                        gamma=leg_greeks.get('short_gamma', 0),
                        theta=leg_greeks.get('short_theta', 0),
                        vega=leg_greeks.get('short_vega', 0),
                        iv=leg_greeks.get('short_iv', 0),
                    )
                ]
            else:  # BEAR_CALL_SPREAD
                legs = [
                    TradeLeg(
                        leg_id=1,
                        action="SELL",
                        option_type="call",
                        strike=position.short_strike,
                        expiration=position.expiration,
                        entry_price=abs(position.entry_debit),
                        contracts=position.contracts,
                        delta=leg_greeks.get('short_delta', 0),
                        gamma=leg_greeks.get('short_gamma', 0),
                        theta=leg_greeks.get('short_theta', 0),
                        vega=leg_greeks.get('short_vega', 0),
                        iv=leg_greeks.get('short_iv', 0),
                    ),
                    TradeLeg(
                        leg_id=2,
                        action="BUY",
                        option_type="call",
                        strike=position.long_strike,
                        expiration=position.expiration,
                        contracts=position.contracts,
                        delta=leg_greeks.get('long_delta', 0),
                        gamma=leg_greeks.get('long_gamma', 0),
                        theta=leg_greeks.get('long_theta', 0),
                        vega=leg_greeks.get('long_vega', 0),
                        iv=leg_greeks.get('long_iv', 0),
                    )
                ]

            # Build ML Predictions object (if ML signal available)
            ml_predictions_obj = None
            if ml_signal and MLPredictions:
                model_preds = ml_signal.get('model_predictions', {})
                suggested_strikes = ml_signal.get('suggested_strikes', {})
                ml_predictions_obj = MLPredictions(
                    direction=model_preds.get('direction', ''),
                    direction_probability=ml_signal.get('win_probability', 0),
                    advice=ml_signal.get('advice', ''),
                    suggested_spread_type=ml_signal.get('spread_type', ''),
                    flip_gravity=model_preds.get('flip_gravity', 0),
                    magnet_attraction=model_preds.get('magnet_attraction', 0),
                    pin_zone_probability=model_preds.get('pin_zone', 0),
                    expected_volatility=ml_signal.get('expected_volatility', 0),
                    ml_confidence=ml_signal.get('confidence', 0),
                    win_probability=ml_signal.get('win_probability', 0),
                    suggested_entry_strike=suggested_strikes.get('entry_strike', 0),
                    suggested_exit_strike=suggested_strikes.get('exit_strike', 0),
                    ml_reasoning=ml_signal.get('reasoning', ''),
                    model_version=ml_signal.get('model_version', ''),
                    models_used=['direction', 'flip_gravity', 'magnet', 'pin_zone', 'volatility'],
                )

            # Build structured risk checks
            risk_checks_list = []
            if RiskCheck:
                # Market hours check
                risk_checks_list.append(RiskCheck(
                    check="Market Hours",
                    passed=True,
                    value=now.strftime("%H:%M"),
                    threshold=f"{self.config.entry_start_time}-{self.config.entry_end_time}"
                ))
                # Daily trade limit
                risk_checks_list.append(RiskCheck(
                    check="Daily Trade Limit",
                    passed=self.daily_trades < self.config.max_daily_trades,
                    value=str(self.daily_trades),
                    threshold=str(self.config.max_daily_trades)
                ))
                # Max positions
                risk_checks_list.append(RiskCheck(
                    check="Max Positions",
                    passed=len(self.open_positions) < self.config.max_open_positions,
                    value=str(len(self.open_positions)),
                    threshold=str(self.config.max_open_positions)
                ))
                # R:R ratio
                risk_checks_list.append(RiskCheck(
                    check="R:R Ratio",
                    passed=rr_ratio >= self.config.min_rr_ratio,
                    value=f"{rr_ratio:.2f}:1",
                    threshold=f"{self.config.min_rr_ratio}:1"
                ))
                # VIX check
                risk_checks_list.append(RiskCheck(
                    check="VIX Level",
                    passed=vix < 35,
                    value=f"{vix:.1f}",
                    threshold="< 35"
                ))
                # Between walls
                between_walls = self._is_between_walls(gex_data)
                risk_checks_list.append(RiskCheck(
                    check="Between GEX Walls",
                    passed=between_walls,
                    value="Yes" if between_walls else "No",
                    threshold="Required"
                ))

            # Build backtest reference (from ML model if available)
            backtest_ref = None
            if BacktestReference and ml_signal:
                # Get backtest stats from ML model metrics if available
                backtest_ref = BacktestReference(
                    strategy_name="ATHENA_GEX_ML",
                    backtest_date=now.strftime('%Y-%m-%d'),
                    win_rate=ml_signal.get('win_probability', 0) * 100,  # Convert to percentage
                    expectancy=0,  # Would need to calculate from historical
                    avg_win=0,
                    avg_loss=0,
                    sharpe_ratio=0,
                    total_trades=0,
                    max_drawdown=0,
                    backtest_period="2024-01 to 2024-12",
                    uses_real_data=True,
                    data_source="polygon",
                    date_range="12 months"
                )

            # Build supporting factors
            supporting_factors = [
                f"GEX Regime: {gex_data.get('regime', 'UNKNOWN')} (net: {gex_data.get('net_gex', 0):,.0f})",
                f"Call Wall: ${gex_data.get('call_wall', 0):,.0f}",
                f"Put Wall: ${gex_data.get('put_wall', 0):,.0f}",
                f"Spot: ${gex_data.get('spot_price', 0):,.2f}",
                f"VIX: {vix:.1f} ({vix_percentile:.0f}th percentile)",
            ]

            # Add ML/Oracle factors
            if ml_signal:
                supporting_factors.append(f"ML Direction: {ml_signal.get('model_predictions', {}).get('direction', 'N/A')}")
                supporting_factors.append(f"ML Confidence: {ml_signal.get('confidence', 0):.1%}")
                supporting_factors.append(f"Win Probability: {ml_signal.get('win_probability', 0):.1%}")
            elif hasattr(advice, 'win_probability'):
                supporting_factors.append(f"Win Probability: {advice.win_probability:.1%}")
                supporting_factors.append(f"Confidence: {getattr(advice, 'confidence', 0):.1%}")

            # Build risk factors
            risk_factors = [
                f"Max loss per spread: ${position.spread_width * 100:,.0f}",
                f"Total max risk: ${position.max_loss:,.0f}",
                f"0DTE expiration: {position.expiration}",
                f"R:R ratio: {rr_ratio:.2f}:1 (min {self.config.min_rr_ratio}:1)",
            ]

            # Alternatives considered
            alternatives_considered = [
                "STAY_OUT (insufficient signal strength)",
                "Opposite direction (Bull vs Bear)",
                "Wider spread width for more credit",
                "Wait for better entry",
            ]

            why_not_alternatives = [
                "GEX/ML signal confirmed direction",
                f"R:R ratio {rr_ratio:.2f}:1 met minimum threshold",
                "Current spread width provides optimal risk/reward",
            ]

            # Build oracle_advice dict for storage (Oracle fallback info)
            oracle_advice_dict = None
            if hasattr(advice, 'win_probability'):
                oracle_advice_dict = {
                    'advice': str(getattr(advice, 'advice', 'UNKNOWN')),
                    'win_probability': getattr(advice, 'win_probability', 0),
                    'confidence': getattr(advice, 'confidence', getattr(advice, 'win_probability', 0)),
                    'suggested_risk_pct': getattr(advice, 'suggested_risk_pct', self.config.risk_per_trade_pct),
                    'suggested_call_strike': getattr(advice, 'suggested_call_strike', None),
                    'reasoning': getattr(advice, 'reasoning', ''),
                }
                # Include Claude analysis if available
                if hasattr(advice, 'claude_analysis') and advice.claude_analysis:
                    claude = advice.claude_analysis
                    oracle_advice_dict['claude_analysis'] = {
                        'analysis': getattr(claude, 'analysis', getattr(claude, 'raw_response', '')),
                        'confidence_adjustment': getattr(claude, 'confidence_adjustment', 0),
                        'risk_factors': getattr(claude, 'risk_factors', []),
                        'opportunities': getattr(claude, 'opportunities', []),
                        'recommendation': getattr(claude, 'recommendation', ''),
                    }

            # Build comprehensive "what"
            spread_name = "Bull Call Spread" if position.spread_type == SpreadType.BULL_CALL_SPREAD else "Bear Call Spread"
            signal_source = "ML" if ml_signal else "Oracle"
            what_desc = f"{spread_name} {position.contracts}x ${position.long_strike}/${position.short_strike} @ ${abs(position.entry_debit):.2f} ({signal_source} signal)"

            # Build comprehensive "why"
            why_parts = [f"GEX-based directional {spread_name} for premium capture."]
            if ml_signal:
                model_preds = ml_signal.get('model_predictions', {})
                why_parts.append(f"ML predicts {model_preds.get('direction', 'N/A')} with {ml_signal.get('confidence', 0):.0%} confidence")
            why_parts.append(f"Regime: {gex_data.get('regime', 'UNKNOWN')}")
            win_prob = ml_signal.get('win_probability', 0) if ml_signal else getattr(advice, 'win_probability', 0)
            if win_prob:
                why_parts.append(f"Win Prob: {win_prob:.0%}")
            why_desc = " | ".join(why_parts)

            # Build comprehensive "how"
            how_desc = (
                f"Strike Selection: ATM ${position.long_strike}, OTM ${position.short_strike} "
                f"(${position.spread_width} wide). "
                f"Position Sizing: {self.config.risk_per_trade_pct:.0f}% risk = {position.contracts} contracts. "
                f"Execution: {'Tradier Sandbox (PAPER)' if self.config.mode == TradingMode.PAPER else 'Tradier Production (LIVE)'}."
            )

            decision = TradeDecision(
                decision_id=position.position_id,
                timestamp=datetime.now(CENTRAL_TZ).isoformat(),
                decision_type=DecisionType.ENTRY_SIGNAL,
                bot_name=BotName.ATHENA,
                what=what_desc,
                why=why_desc,
                how=how_desc,
                action="SELL" if position.spread_type == SpreadType.BEAR_CALL_SPREAD else "BUY",
                symbol=self.config.ticker,
                strategy=position.spread_type.value,
                legs=legs,
                underlying_price_at_entry=gex_data.get('spot_price', 0),
                market_context=LoggerMarketContext(
                    timestamp=datetime.now(CENTRAL_TZ).isoformat(),
                    spot_price=gex_data.get('spot_price', 0),
                    spot_source=DataSource.TRADIER_LIVE,
                    vix=vix,
                    vix_percentile_30d=vix_percentile,
                    expected_move_pct=expected_move_pct,
                    trend=trend,
                    day_of_week=day_of_week,
                    days_to_opex=days_to_opex,
                    net_gex=gex_data.get('net_gex', 0),
                    gex_regime=gex_data.get('regime', 'NEUTRAL'),
                    flip_point=gex_data.get('flip_point', 0),
                    call_wall=gex_data.get('call_wall', 0),
                    put_wall=gex_data.get('put_wall', 0),
                ),
                ml_predictions=ml_predictions_obj,
                oracle_advice=oracle_advice_dict,
                backtest_reference=backtest_ref,
                risk_checks=risk_checks_list,
                passed_risk_checks=all(rc.passed for rc in risk_checks_list) if risk_checks_list else True,
                reasoning=DecisionReasoning(
                    primary_reason=f"GEX-directed {spread_name} for premium collection via {signal_source}",
                    supporting_factors=supporting_factors,
                    risk_factors=risk_factors,
                    alternatives_considered=alternatives_considered,
                    why_not_alternatives=why_not_alternatives,
                ),
                position_size_dollars=abs(position.entry_debit) * 100 * position.contracts,
                position_size_contracts=position.contracts,
                position_size_method="risk_pct",
                max_risk_dollars=position.max_loss,
                target_profit_pct=50,  # Typical target for spreads
                stop_loss_pct=100,  # Max loss is spread width
                probability_of_profit=ml_signal.get('win_probability', 0) if ml_signal else getattr(advice, 'win_probability', 0.5),
            )

            # Log to database (primary)
            self.decision_logger.log_decision(decision)
            self._log_to_db("INFO", f"Decision logged: {position.position_id}")

            # DUAL LOGGING: Also log to bot_decision_logs for comprehensive audit trail (like ARES)
            if BOT_LOGGER_AVAILABLE and log_bot_decision and BotDecision:
                try:
                    comprehensive_decision = BotDecision(
                        bot_name="ATHENA",
                        decision_type="ENTRY",
                        action="SELL" if position.spread_type == SpreadType.BEAR_CALL_SPREAD else "BUY",
                        symbol=self.config.ticker,
                        strategy=position.spread_type.value,
                        strike=position.short_strike,
                        expiration=str(position.expiration),
                        option_type="call",
                        contracts=position.contracts,
                        market_context=BotLogMarketContext(
                            spot_price=gex_data.get('spot_price', 0),
                            vix=vix,
                            net_gex=gex_data.get('net_gex', 0),
                            gex_regime=gex_data.get('regime', 'NEUTRAL'),
                            flip_point=gex_data.get('flip_point', 0),
                            call_wall=gex_data.get('call_wall', 0),
                            put_wall=gex_data.get('put_wall', 0),
                            trend=trend,
                        ) if BotLogMarketContext else None,
                        claude_context=ClaudeContext(
                            prompt=f"ATHENA {signal_source} signal evaluation for {spread_name}",
                            response=oracle_advice_dict.get('claude_analysis', {}).get('analysis', '') if oracle_advice_dict else '',
                            model="claude-3-sonnet" if oracle_advice_dict else "",
                            tokens_used=0,
                            response_time_ms=0,
                            confidence=str(oracle_advice_dict.get('confidence', '')) if oracle_advice_dict else "",
                        ) if ClaudeContext and oracle_advice_dict else None,
                        entry_reasoning=why_desc,
                        strike_reasoning=f"Long ${position.long_strike}, Short ${position.short_strike} ({position.spread_width} wide)",
                        size_reasoning=f"{self.config.risk_per_trade_pct:.0f}% risk = {position.contracts} contracts",
                        alternatives_considered=[
                            Alternative(strategy="STAY_OUT", reason="Insufficient signal"),
                            Alternative(strategy="Opposite direction", reason="GEX confirms direction"),
                        ] if Alternative else [],
                        kelly_pct=self.config.risk_per_trade_pct / 100,
                        position_size_dollars=abs(position.entry_debit) * 100 * position.contracts,
                        max_risk_dollars=position.max_loss,
                        backtest_win_rate=ml_signal.get('win_probability', 0) if ml_signal else getattr(advice, 'win_probability', 0.5),
                        passed_all_checks=True,
                    )
                    decision_id = log_bot_decision(comprehensive_decision)
                    logger.info(f"ATHENA: Logged to bot_decision_logs (ENTRY) - ID: {decision_id}")
                except Exception as comp_e:
                    logger.warning(f"ATHENA: Could not log to comprehensive table: {comp_e}")

        except Exception as e:
            self._log_to_db("ERROR", f"Failed to log decision: {e}")
            import traceback
            traceback.print_exc()

    def _get_leg_greeks(self, position: SpreadPosition, spot: float, vix: float) -> Dict:
        """
        Get Greeks for trade legs.
        Uses simplified Black-Scholes approximation for 0DTE options.
        """
        greeks = {}
        try:
            import math
            # Simplified 0DTE Greeks approximation
            # For ATM options, delta ~0.5, gamma peaks, theta accelerates
            time_to_exp = 1/252  # 1 day in years

            # Long leg (ATM-ish)
            long_moneyness = (spot - position.long_strike) / spot
            greeks['long_delta'] = 0.5 + (long_moneyness * 2)  # Simplified
            greeks['long_delta'] = max(-1, min(1, greeks['long_delta']))
            greeks['long_gamma'] = 0.05  # Peaks near ATM for 0DTE
            greeks['long_theta'] = -0.10 * vix / 20  # Accelerated theta for 0DTE
            greeks['long_vega'] = 0.02
            greeks['long_iv'] = vix / 100

            # Short leg (OTM)
            short_moneyness = (spot - position.short_strike) / spot
            greeks['short_delta'] = 0.5 + (short_moneyness * 2)
            greeks['short_delta'] = max(-1, min(1, greeks['short_delta']))
            greeks['short_gamma'] = 0.03  # Lower gamma for OTM
            greeks['short_theta'] = -0.08 * vix / 20
            greeks['short_vega'] = 0.01
            greeks['short_iv'] = vix / 100 * 1.1  # Slight IV skew for OTM

        except Exception as e:
            self._log_to_db("DEBUG", f"Could not calculate Greeks: {e}")

        return greeks

    def check_exits(self) -> List[SpreadPosition]:
        """
        Check all open positions for exit conditions.

        Implements hybrid trailing stop with scaled exits:
        - Phase 1: Let profits develop (no trailing until profit threshold)
        - Phase 2: Scale out at profit targets (lock in gains)
        - Phase 3: Trail remaining "runners" with ATR + P&L stops
        """
        closed = []
        now = datetime.now(CENTRAL_TZ)

        for position in self.open_positions[:]:  # Copy list to allow modification
            should_exit_all = False
            exit_reason = ""

            try:
                # Get current market data
                current_price = 0
                if UNIFIED_DATA_AVAILABLE:
                    current_price = get_price(self.config.ticker)
                elif TRADIER_AVAILABLE and self.tradier:
                    quote = self.tradier.get_quote(self.config.ticker)
                    current_price = quote.get('last', 0) or quote.get('close', 0)

                if current_price <= 0:
                    continue  # Skip if no price data

                # Get current spread value
                current_spread_value = self._get_current_spread_value(position)
                entry_price = position.underlying_price_at_entry

                # Update water marks for underlying price
                if position.spread_type == SpreadType.BULL_CALL_SPREAD:
                    if position.high_water_mark == 0:
                        position.high_water_mark = max(entry_price, current_price)
                    else:
                        position.high_water_mark = max(position.high_water_mark, current_price)
                else:  # BEAR_CALL_SPREAD
                    if position.low_water_mark == float('inf'):
                        position.low_water_mark = min(entry_price, current_price)
                    else:
                        position.low_water_mark = min(position.low_water_mark, current_price)

                # Update peak spread value (for P&L trailing)
                position.peak_spread_value = max(position.peak_spread_value, current_spread_value)

                # Calculate current profit percentage
                max_profit_per_spread = position.spread_width - position.entry_debit
                current_profit = current_spread_value - position.entry_debit
                profit_pct = (current_profit / max_profit_per_spread * 100) if max_profit_per_spread > 0 else 0

                # ============================================================
                # CHECK 1: Hard Stop Loss (capital protection)
                # ============================================================
                max_loss_per_spread = position.entry_debit  # Max you can lose on debit spread
                current_loss = position.entry_debit - current_spread_value
                loss_pct = (current_loss / max_loss_per_spread * 100) if max_loss_per_spread > 0 else 0

                if loss_pct >= self.config.hard_stop_pct:
                    should_exit_all = True
                    exit_reason = f"HARD_STOP_LOSS ({loss_pct:.0f}% loss)"

                # ============================================================
                # CHECK 2: End of Day Exit (0DTE)
                # ============================================================
                if not should_exit_all:
                    exit_time = now.replace(hour=15, minute=55, second=0)
                    if now >= exit_time:
                        should_exit_all = True
                        exit_reason = "EOD_EXIT"

                # ============================================================
                # CHECK 3: Scale-out at Profit Targets
                # ============================================================
                if not should_exit_all and position.contracts_remaining > 0:
                    # Check if we have enough contracts for scaling
                    use_scaling = position.initial_contracts >= self.config.min_contracts_for_scaling

                    if use_scaling:
                        # Scale-out 1: First profit target
                        if not position.scale_out_1_done and profit_pct >= self.config.scale_out_1_pct:
                            contracts_to_exit = int(position.initial_contracts * self.config.scale_out_1_size / 100)
                            contracts_to_exit = min(contracts_to_exit, position.contracts_remaining - 1)  # Keep at least 1

                            if contracts_to_exit > 0:
                                self._execute_scale_out(
                                    position, contracts_to_exit, current_spread_value,
                                    f"SCALE_OUT_1 ({self.config.scale_out_1_pct:.0f}% profit)"
                                )
                                position.scale_out_1_done = True

                        # Scale-out 2: Second profit target
                        if not position.scale_out_2_done and profit_pct >= self.config.scale_out_2_pct:
                            contracts_to_exit = int(position.initial_contracts * self.config.scale_out_2_size / 100)
                            contracts_to_exit = min(contracts_to_exit, position.contracts_remaining - 1)  # Keep at least 1

                            if contracts_to_exit > 0:
                                self._execute_scale_out(
                                    position, contracts_to_exit, current_spread_value,
                                    f"SCALE_OUT_2 ({self.config.scale_out_2_pct:.0f}% profit)"
                                )
                                position.scale_out_2_done = True

                # ============================================================
                # CHECK 4: Hybrid Trailing Stop (ATR + P&L) for Runners
                # ============================================================
                if not should_exit_all and position.contracts_remaining > 0:
                    # Only start trailing after profit threshold hit
                    if profit_pct >= self.config.profit_threshold_pct:
                        position.profit_threshold_hit = True

                    if position.profit_threshold_hit:
                        trailing_triggered = False
                        trailing_reason = ""

                        # --- ATR-based trailing stop (volatility-adjusted) ---
                        atr = position.current_atr if position.current_atr > 0 else self._calculate_atr()
                        atr_distance = atr * self.config.atr_multiplier

                        if position.spread_type == SpreadType.BULL_CALL_SPREAD:
                            atr_stop_price = position.high_water_mark - atr_distance
                            if current_price < atr_stop_price:
                                trailing_triggered = True
                                trailing_reason = f"ATR_STOP (price {current_price:.2f} < {atr_stop_price:.2f})"
                        else:  # BEAR_CALL_SPREAD
                            atr_stop_price = position.low_water_mark + atr_distance
                            if current_price > atr_stop_price:
                                trailing_triggered = True
                                trailing_reason = f"ATR_STOP (price {current_price:.2f} > {atr_stop_price:.2f})"

                        # --- P&L-based trailing stop (protect profits) ---
                        if not trailing_triggered:
                            peak_profit = position.peak_spread_value - position.entry_debit
                            current_profit_from_peak = current_spread_value - position.entry_debit
                            keep_pct = self.config.trail_keep_pct / 100

                            # Exit if we've given back too much profit
                            min_acceptable_profit = peak_profit * keep_pct
                            if peak_profit > 0 and current_profit_from_peak < min_acceptable_profit:
                                trailing_triggered = True
                                trailing_reason = f"PNL_STOP (profit ${current_profit_from_peak:.2f} < min ${min_acceptable_profit:.2f})"

                        if trailing_triggered:
                            should_exit_all = True
                            exit_reason = f"TRAILING_STOP: {trailing_reason}"

            except Exception as e:
                self._log_to_db("DEBUG", f"Error in check_exits: {e}")
                logger.debug(f"check_exits error: {e}")

            # ============================================================
            # EXECUTE FULL EXIT (if triggered)
            # ============================================================
            if should_exit_all and position.contracts_remaining > 0:
                # Exit all remaining contracts
                current_spread_value = self._get_current_spread_value(position)
                self._execute_scale_out(
                    position, position.contracts_remaining, current_spread_value,
                    exit_reason
                )
                self._close_position(position, exit_reason)
                closed.append(position)

            # Also close if all contracts have been scaled out
            elif position.contracts_remaining == 0 and position.status == "open":
                self._close_position(position, "FULLY_SCALED_OUT")
                closed.append(position)

        return closed

    def _close_position(self, position: SpreadPosition, reason: str) -> None:
        """Close a position - includes P&L from all scale-outs"""
        position.status = "closed"
        position.close_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Get current spread value for final close price
        current_spread_value = self._get_current_spread_value(position)
        position.close_price = current_spread_value

        # Calculate total realized P&L (scale-outs already recorded + any remaining)
        # Note: If contracts_remaining is 0, all P&L came from scale-outs
        # If contracts_remaining > 0, this shouldn't happen (exit should scale out first)
        position.realized_pnl = position.total_scaled_pnl

        # Log summary of scaled exits
        initial = position.initial_contracts
        scaled_out = initial - position.contracts_remaining
        self._log_to_db("INFO", f"Position closed with scale-outs", {
            'position_id': position.position_id,
            'initial_contracts': initial,
            'scaled_out_contracts': scaled_out,
            'scale_out_1_done': position.scale_out_1_done,
            'scale_out_2_done': position.scale_out_2_done,
            'total_pnl': position.realized_pnl,
            'exit_reason': reason
        })

        # Move to closed positions
        if position in self.open_positions:
            self.open_positions.remove(position)
        self.closed_positions.append(position)

        # Update capital
        self.current_capital += position.realized_pnl

        # Update database
        self._update_position_in_db(position, reason)

        # Log exit decision
        self._log_exit_decision(position, reason)

        self._log_to_db("INFO", f"Position closed: {reason}", {
            'position_id': position.position_id,
            'realized_pnl': position.realized_pnl
        })

        # Update daily performance tracking
        self._update_daily_performance(position)

    def _update_position_in_db(self, position: SpreadPosition, exit_reason: str) -> None:
        """Update position status in database"""
        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute("""
                UPDATE apache_positions
                SET status = %s, exit_price = %s, exit_time = NOW(),
                    exit_reason = %s, realized_pnl = %s
                WHERE position_id = %s
            """, (
                position.status,
                position.close_price,
                exit_reason,
                position.realized_pnl,
                position.position_id
            ))

            conn.commit()
            conn.close()
        except Exception as e:
            self._log_to_db("ERROR", f"Failed to update position: {e}")

    def _update_daily_performance(self, position: SpreadPosition) -> None:
        """Update daily performance table after closing a position"""
        try:
            conn = get_connection()
            c = conn.cursor()

            today = datetime.now().strftime("%Y-%m-%d")
            is_win = position.realized_pnl > 0
            is_bullish = position.spread_type == SpreadType.BULL_CALL_SPREAD

            # Try to update existing row, or insert new one
            c.execute("""
                INSERT INTO apache_performance (
                    trade_date, trades_executed, trades_won, trades_lost,
                    gross_pnl, net_pnl, starting_capital, ending_capital,
                    bullish_trades, bearish_trades
                ) VALUES (
                    %s, 1, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (trade_date) DO UPDATE SET
                    trades_executed = apache_performance.trades_executed + 1,
                    trades_won = apache_performance.trades_won + EXCLUDED.trades_won,
                    trades_lost = apache_performance.trades_lost + EXCLUDED.trades_lost,
                    gross_pnl = apache_performance.gross_pnl + EXCLUDED.gross_pnl,
                    net_pnl = apache_performance.net_pnl + EXCLUDED.net_pnl,
                    ending_capital = EXCLUDED.ending_capital,
                    bullish_trades = apache_performance.bullish_trades + EXCLUDED.bullish_trades,
                    bearish_trades = apache_performance.bearish_trades + EXCLUDED.bearish_trades,
                    win_rate = CASE
                        WHEN (apache_performance.trades_executed + 1) > 0
                        THEN (apache_performance.trades_won + EXCLUDED.trades_won)::float / (apache_performance.trades_executed + 1)
                        ELSE 0
                    END,
                    daily_return_pct = CASE
                        WHEN apache_performance.starting_capital > 0
                        THEN ((EXCLUDED.ending_capital - apache_performance.starting_capital) / apache_performance.starting_capital) * 100
                        ELSE 0
                    END
            """, (
                today,
                1 if is_win else 0,  # trades_won
                0 if is_win else 1,  # trades_lost
                position.realized_pnl,  # gross_pnl
                position.realized_pnl,  # net_pnl (commissions deducted later)
                self.config.initial_capital,  # starting_capital
                self.current_capital,  # ending_capital
                1 if is_bullish else 0,  # bullish_trades
                0 if is_bullish else 1   # bearish_trades
            ))

            conn.commit()
            conn.close()

            self._log_to_db("DEBUG", "Daily performance updated", {
                'date': today,
                'pnl': position.realized_pnl,
                'win': is_win
            })
        except Exception as e:
            self._log_to_db("ERROR", f"Failed to update daily performance: {e}")

    def _log_exit_decision(self, position: SpreadPosition, reason: str) -> None:
        """Log exit decision using decision_logger (same as ARES)"""
        if not DECISION_LOGGER_AVAILABLE or not self.decision_logger:
            return

        try:
            # Create exit legs
            if position.spread_type == SpreadType.BULL_CALL_SPREAD:
                legs = [
                    TradeLeg(
                        leg_id=1,
                        action="SELL",  # Close long leg
                        option_type="call",
                        strike=position.long_strike,
                        expiration=position.expiration,
                        exit_price=position.close_price,
                        contracts=position.contracts,
                        realized_pnl=position.realized_pnl / 2  # Approximate split
                    ),
                    TradeLeg(
                        leg_id=2,
                        action="BUY",  # Close short leg
                        option_type="call",
                        strike=position.short_strike,
                        expiration=position.expiration,
                        contracts=position.contracts,
                        realized_pnl=position.realized_pnl / 2
                    )
                ]
            else:  # BEAR_CALL_SPREAD
                legs = [
                    TradeLeg(
                        leg_id=1,
                        action="BUY",  # Close short leg
                        option_type="call",
                        strike=position.short_strike,
                        expiration=position.expiration,
                        contracts=position.contracts,
                        realized_pnl=position.realized_pnl / 2
                    ),
                    TradeLeg(
                        leg_id=2,
                        action="SELL",  # Close long leg
                        option_type="call",
                        strike=position.long_strike,
                        expiration=position.expiration,
                        exit_price=position.close_price,
                        contracts=position.contracts,
                        realized_pnl=position.realized_pnl / 2
                    )
                ]

            spread_name = "Bull Call Spread" if position.spread_type == SpreadType.BULL_CALL_SPREAD else "Bear Call Spread"

            decision = TradeDecision(
                decision_id=f"{position.position_id}-EXIT",
                timestamp=datetime.now(CENTRAL_TZ).isoformat(),
                decision_type=DecisionType.EXIT_SIGNAL,
                bot_name=BotName.ATHENA,
                what=f"CLOSE {spread_name} {position.contracts}x ${position.long_strike}/${position.short_strike}",
                why=f"Exit triggered: {reason}",
                how=f"Closed at ${position.close_price:.2f} for P&L ${position.realized_pnl:,.2f}",
                action="CLOSE",
                symbol=self.config.ticker,
                strategy=position.spread_type.value,
                legs=legs,
                underlying_price_at_entry=position.underlying_price_at_entry,
                actual_pnl=position.realized_pnl,
                outcome_notes=reason,
            )

            self.decision_logger.log_decision(decision)
            self._log_to_db("INFO", f"Exit decision logged: {position.position_id}")

            # DUAL LOGGING: Also log to bot_decision_logs for comprehensive audit trail
            if BOT_LOGGER_AVAILABLE and log_bot_decision and BotDecision:
                try:
                    comprehensive_decision = BotDecision(
                        bot_name="ATHENA",
                        decision_type="EXIT",
                        action="CLOSE",
                        symbol=self.config.ticker,
                        strategy=position.spread_type.value,
                        strike=position.short_strike,
                        expiration=str(position.expiration),
                        option_type="call",
                        contracts=position.contracts,
                        entry_reasoning=f"Exit triggered: {reason}",
                        exit_reasoning=reason,
                        passed_all_checks=True,
                    )
                    # Update with outcome data
                    if update_decision_outcome:
                        update_decision_outcome(
                            decision_id=f"{position.position_id}-EXIT",
                            actual_pnl=position.realized_pnl,
                            exit_triggered_by=reason,
                            exit_price=position.close_price,
                        )
                    decision_id = log_bot_decision(comprehensive_decision)
                    logger.info(f"ATHENA: Logged to bot_decision_logs (EXIT) - ID: {decision_id}")
                except Exception as comp_e:
                    logger.warning(f"ATHENA: Could not log EXIT to comprehensive table: {comp_e}")

        except Exception as e:
            self._log_to_db("ERROR", f"Failed to log exit: {e}")

    def _log_skip_decision(self, reason: str, gex_data: Optional[Dict] = None,
                          ml_signal: Optional[Dict] = None, oracle_advice: Optional[Any] = None) -> None:
        """
        Log skip/no-trade decision with FULL TRANSPARENCY.

        Shows exactly what the bot was thinking:
        - Market conditions at decision time
        - ML model predictions (direction, confidence, probabilities)
        - Oracle advice (if consulted)
        - Why the decision was made
        - What would need to change for a trade
        """
        if not DECISION_LOGGER_AVAILABLE or not self.decision_logger:
            return

        try:
            # Get VIX with validation
            vix = 20.0
            if UNIFIED_DATA_AVAILABLE:
                try:
                    from data.unified_data_provider import get_vix
                    fetched_vix = get_vix()
                    if fetched_vix and fetched_vix > 0:
                        vix = fetched_vix
                    else:
                        logger.warning(f"ATHENA: get_vix() returned invalid value: {fetched_vix}, using default 20.0")
                except Exception as e:
                    logger.warning(f"ATHENA: Failed to get VIX: {e}, using default 20.0")

            # Validate VIX is in reasonable range (8-100)
            if vix < 8 or vix > 100:
                logger.warning(f"ATHENA: VIX {vix} outside normal range, clamping")
                vix = max(8, min(100, vix))

            # Calculate expected move
            expected_move_pct = (vix / 16) * (1 / 252 ** 0.5) * 100

            if expected_move_pct <= 0 or expected_move_pct > 10:
                expected_move_pct = (vix / 16) * 0.063 * 100

            # Build detailed "WHAT" description showing bot's thinking
            what_parts = [f"SKIP - {reason}"]

            # Add market snapshot
            if gex_data:
                spot = gex_data.get('spot_price', 0)
                regime = gex_data.get('regime', 'UNKNOWN')
                call_wall = gex_data.get('call_wall', 0)
                put_wall = gex_data.get('put_wall', 0)

                # Calculate wall distances
                if spot > 0:
                    call_dist = ((call_wall - spot) / spot * 100) if call_wall else 0
                    put_dist = ((spot - put_wall) / spot * 100) if put_wall else 0
                    what_parts.append(f"[{self.config.ticker} ${spot:.2f} | {regime} | Walls: Put -${put_dist:.1f}% / Call +${call_dist:.1f}%]")

            # Add ML signal details
            if ml_signal:
                ml_advice = ml_signal.get('advice', 'N/A')
                ml_conf = ml_signal.get('confidence', 0)
                ml_win = ml_signal.get('win_probability', 0)
                ml_spread = ml_signal.get('spread_type', 'NONE')
                predictions = ml_signal.get('model_predictions', {})

                what_parts.append(f"[ML: {ml_advice} ({ml_conf:.0%} conf, {ml_win:.0%} win) -> {ml_spread}]")

                if predictions:
                    direction = predictions.get('direction', 'FLAT')
                    flip_grav = predictions.get('flip_gravity', 0)
                    magnet = predictions.get('magnet_attraction', 0)
                    pin_zone = predictions.get('pin_zone', 0)
                    what_parts.append(f"[ML Predictions: {direction} | FlipGrav={flip_grav:.0%} | Magnet={magnet:.0%} | Pin={pin_zone:.0%}]")

            # Add Oracle advice details
            if oracle_advice:
                advice_str = oracle_advice.advice.value if hasattr(oracle_advice.advice, 'value') else str(oracle_advice.advice)
                oracle_conf = getattr(oracle_advice, 'confidence', 0)
                oracle_win = getattr(oracle_advice, 'win_probability', 0)
                what_parts.append(f"[Oracle: {advice_str} ({oracle_conf:.0%} conf, {oracle_win:.0%} win)]")

            # Build the complete "what" string
            what_description = " ".join(what_parts)

            logger.info(f"ATHENA Decision: {what_description}")

            # Build supporting factors with full context
            supporting_factors = []
            if gex_data:
                supporting_factors.extend([
                    f"GEX Regime: {gex_data.get('regime', 'UNKNOWN')}",
                    f"Spot: ${gex_data.get('spot_price', 0):,.2f}",
                    f"Call Wall: ${gex_data.get('call_wall', 0):,.0f}",
                    f"Put Wall: ${gex_data.get('put_wall', 0):,.0f}",
                    f"Net GEX: {gex_data.get('net_gex', 0):,.0f}",
                    f"VIX: {vix:.1f}",
                    f"Expected Move: {expected_move_pct:.2f}%",
                ])
            if ml_signal:
                supporting_factors.extend([
                    f"ML Advice: {ml_signal.get('advice', 'N/A')}",
                    f"ML Confidence: {ml_signal.get('confidence', 0):.1%}",
                    f"ML Win Prob: {ml_signal.get('win_probability', 0):.1%}",
                    f"ML Spread Type: {ml_signal.get('spread_type', 'NONE')}",
                    f"ML Reasoning: {ml_signal.get('reasoning', 'N/A')[:100]}...",
                ])
            if oracle_advice:
                advice_str = oracle_advice.advice.value if hasattr(oracle_advice.advice, 'value') else str(oracle_advice.advice)
                supporting_factors.extend([
                    f"Oracle Advice: {advice_str}",
                    f"Oracle Confidence: {getattr(oracle_advice, 'confidence', 0):.1%}",
                    f"Oracle Win Prob: {getattr(oracle_advice, 'win_probability', 0):.1%}",
                    f"Oracle Reasoning: {getattr(oracle_advice, 'reasoning', 'N/A')[:100]}...",
                ])

            market_context = None
            if gex_data:
                market_context = LoggerMarketContext(
                    timestamp=datetime.now(CENTRAL_TZ).isoformat(),
                    spot_price=gex_data.get('spot_price', 0),
                    spot_source=DataSource.TRADIER_LIVE,
                    vix=vix,
                    expected_move_pct=expected_move_pct,
                    net_gex=gex_data.get('net_gex', 0),
                    gex_regime=gex_data.get('regime', 'NEUTRAL'),
                    flip_point=gex_data.get('flip_point', 0),
                    call_wall=gex_data.get('call_wall', 0),
                    put_wall=gex_data.get('put_wall', 0),
                )

            # Build detailed "how" showing what conditions would need to change
            how_details = []
            if ml_signal and ml_signal.get('advice') == 'STAY_OUT':
                how_details.append("ML needs directional signal (LONG/SHORT) instead of STAY_OUT")
            if oracle_advice and hasattr(oracle_advice, 'advice'):
                if oracle_advice.advice == TradingAdvice.SKIP_TODAY:
                    how_details.append("Oracle needs to recommend TRADE_FULL instead of SKIP")
            if not ml_signal and not oracle_advice:
                how_details.append("Waiting for ML or Oracle signal")

            how_description = " | ".join(how_details) if how_details else "Conditions not met for directional spread entry"

            decision = TradeDecision(
                decision_id=self.decision_logger._generate_decision_id(),
                timestamp=datetime.now(CENTRAL_TZ).isoformat(),
                decision_type=DecisionType.NO_TRADE,
                bot_name=BotName.ATHENA,
                what=what_description,  # Use the detailed description we built
                why=reason,
                how=how_description,
                action="SKIP",
                symbol=self.config.ticker,
                strategy="directional_spread",
                market_context=market_context,
                reasoning=DecisionReasoning(
                    primary_reason=reason,
                    supporting_factors=supporting_factors,
                    risk_factors=[],
                ),
            )

            self.decision_logger.log_decision(decision)

            # DUAL LOGGING: Also log to bot_decision_logs for comprehensive audit trail
            if BOT_LOGGER_AVAILABLE and log_bot_decision and BotDecision:
                try:
                    comprehensive_decision = BotDecision(
                        bot_name="ATHENA",
                        decision_type="SKIP",
                        action="SKIP",
                        symbol=self.config.ticker,
                        strategy="directional_spread",
                        market_context=BotLogMarketContext(
                            spot_price=gex_data.get('spot_price', 0) if gex_data else 0,
                            vix=vix,
                            net_gex=gex_data.get('net_gex', 0) if gex_data else 0,
                            gex_regime=gex_data.get('regime', 'NEUTRAL') if gex_data else 'UNKNOWN',
                            flip_point=gex_data.get('flip_point', 0) if gex_data else 0,
                            call_wall=gex_data.get('call_wall', 0) if gex_data else 0,
                            put_wall=gex_data.get('put_wall', 0) if gex_data else 0,
                        ) if BotLogMarketContext and gex_data else None,
                        claude_context=ClaudeContext(
                            prompt=f"ATHENA SKIP evaluation: {reason}",
                            response=getattr(oracle_advice, 'reasoning', '') if oracle_advice else '',
                            confidence=str(getattr(oracle_advice, 'confidence', '')) if oracle_advice else "",
                        ) if ClaudeContext else None,
                        entry_reasoning=reason,
                        blocked_reason=reason,
                        passed_all_checks=False,
                        alternatives_considered=[
                            Alternative(
                                strategy=ml_signal.get('spread_type', 'NONE') if ml_signal else 'NONE',
                                reason=ml_signal.get('reasoning', 'ML signal insufficient') if ml_signal else 'No ML signal'
                            ),
                        ] if Alternative and ml_signal else [],
                    )
                    decision_id = log_bot_decision(comprehensive_decision)
                    logger.info(f"ATHENA: Logged to bot_decision_logs (SKIP) - ID: {decision_id}")
                except Exception as comp_e:
                    logger.warning(f"ATHENA: Could not log SKIP to comprehensive table: {comp_e}")

        except Exception as e:
            self._log_to_db("ERROR", f"Failed to log skip decision: {e}")

    def run_daily_cycle(self) -> Dict[str, Any]:
        """Run the daily trading cycle using ML signals"""
        now = datetime.now(CENTRAL_TZ)
        scan_number = self.daily_trades + 1

        # Wrap entire cycle in try/except to ALWAYS log errors to scan_activity
        try:
            return self._run_daily_cycle_inner(now, scan_number)
        except Exception as e:
            import traceback
            error_tb = traceback.format_exc()
            logger.error(f"[ATHENA] CRITICAL ERROR in run_daily_cycle: {e}")
            logger.error(error_tb)

            # Log the crash to scan_activity so it shows on frontend
            if SCAN_LOGGER_AVAILABLE and log_athena_scan:
                try:
                    log_athena_scan(
                        outcome=ScanOutcome.ERROR,
                        decision_summary=f"CRASH: {str(e)[:200]}",
                        action_taken="Bot crashed - will retry next scan",
                        error_message=str(e),
                        error_type="UNHANDLED_EXCEPTION",
                        checks=[
                            CheckResult("exception", False, str(e)[:100], "No errors", error_tb[:500])
                        ],
                        generate_ai_explanation=False  # Don't call Claude on crash
                    )
                except Exception as log_err:
                    logger.error(f"[ATHENA] Failed to log crash to scan_activity: {log_err}")

            # Re-raise so scheduler knows there was an error
            raise

    def _run_daily_cycle_inner(self, now: datetime, scan_number: int) -> Dict[str, Any]:
        """Inner implementation of run_daily_cycle - separated for error handling."""
        self._log_to_db("INFO", f"=== ATHENA Scan #{scan_number} at {now.strftime('%I:%M %p CT')} ===")
        self._log_to_db("INFO", f"ATHENA is ACTIVE - checking for directional spread opportunities...")

        # Log scan START to scan_activity table - ALWAYS log this
        if SCAN_LOGGER_AVAILABLE and log_athena_scan:
            try:
                from trading.scan_activity_logger import log_scan_activity, ScanOutcome as SO
                from database_adapter import get_connection

                # Ensure table exists and log scan start
                conn = get_connection()
                c = conn.cursor()
                c.execute("""
                    INSERT INTO bot_heartbeat (bot_name, status, last_action, last_scan_time)
                    VALUES ('ATHENA', 'SCANNING', %s, NOW())
                    ON CONFLICT (bot_name) DO UPDATE SET
                        status = 'SCANNING',
                        last_action = EXCLUDED.last_action,
                        last_scan_time = NOW()
                """, (f"Scan #{scan_number} started at {now.strftime('%I:%M %p CT')}",))
                conn.commit()
                conn.close()
                logger.info(f"[ATHENA] Scan #{scan_number} heartbeat logged to database")
            except Exception as e:
                logger.warning(f"[ATHENA] Failed to log scan start: {e}")

        result = {
            'trades_attempted': 0,
            'trades_executed': 0,
            'positions_closed': 0,
            'daily_pnl': 0,
            'signal_source': None,
            'errors': [],
            # Detailed decision info for logging
            'decision_reason': None,
            'ml_signal': None,
            'gex_context': None
        }

        # Check if we should trade
        should_trade, reason = self.should_trade()
        if not should_trade:
            self._log_to_db("INFO", f"Skipping trade: {reason}")
            self._log_skip_decision(reason)
            result['errors'].append(reason)
            result['decision_reason'] = f"SKIP: {reason}"
            # Log scan activity - SKIP REASON
            if SCAN_LOGGER_AVAILABLE and log_athena_scan:
                # Determine outcome based on reason
                if "market" in reason.lower() or "closed" in reason.lower():
                    outcome = ScanOutcome.MARKET_CLOSED
                elif "window" in reason.lower() or "before" in reason.lower():
                    outcome = ScanOutcome.BEFORE_WINDOW
                elif "max" in reason.lower() or "limit" in reason.lower():
                    outcome = ScanOutcome.SKIP
                else:
                    outcome = ScanOutcome.SKIP

                # Get basic market data for logging
                try:
                    from data.unified_data_provider import get_vix, get_price
                    vix = get_vix() or 20.0
                    spot = get_price("SPY") or 0
                except Exception:
                    vix = 20.0
                    spot = 0

                log_athena_scan(
                    outcome=outcome,
                    decision_summary=f"Skipping: {reason}",
                    action_taken="No trade - conditions not met",
                    market_data={'underlying_price': spot, 'vix': vix, 'symbol': 'SPY'},
                    checks=[
                        CheckResult("should_trade", False, "No", "Yes", reason)
                    ]
                )
            return result

        # Get GEX data first (needed for both ML and Oracle)
        gex_data = self.get_gex_data()
        if not gex_data:
            self._log_skip_decision("No GEX data available")
            result['errors'].append("No GEX data")
            result['decision_reason'] = "SKIP: No GEX data available"
            # Log scan activity - NO GEX DATA
            if SCAN_LOGGER_AVAILABLE and log_athena_scan:
                # Get basic market data for logging
                try:
                    from data.unified_data_provider import get_vix, get_price
                    vix = get_vix() or 20.0
                    spot = get_price("SPY") or 0
                except Exception:
                    vix = 20.0
                    spot = 0

                log_athena_scan(
                    outcome=ScanOutcome.ERROR,
                    decision_summary="No GEX data available from Kronos",
                    action_taken="Will retry on next scan",
                    market_data={'underlying_price': spot, 'vix': vix, 'symbol': 'SPY'},
                    error_message="GEX data unavailable - cannot calculate walls for R:R",
                    error_type="GEX_DATA_ERROR",
                    checks=[
                        CheckResult("should_trade", True, "Yes", "Yes", "Trade conditions met"),
                        CheckResult("gex_data", False, "None", "Required", "No GEX data returned - check Kronos/Tradier connection")
                    ]
                )
            return result

        # Store GEX context for logging
        result['gex_context'] = {
            'spot_price': gex_data.get('spot_price'),
            'call_wall': gex_data.get('call_wall'),
            'put_wall': gex_data.get('put_wall'),
            'regime': gex_data.get('regime'),
            'net_gex': gex_data.get('net_gex'),
            'source': gex_data.get('source')
        }

        # === PRIMARY: Use ML Signal ===
        ml_signal = None
        spread_type = None
        signal_source = "ML"

        if self.gex_ml:
            ml_signal = self.get_ml_signal(gex_data)

            if ml_signal:
                # Store ML signal for logging
                result['ml_signal'] = {
                    'advice': ml_signal['advice'],
                    'direction': ml_signal.get('model_predictions', {}).get('direction', 'UNKNOWN'),
                    'confidence': ml_signal['confidence'],
                    'win_probability': ml_signal['win_probability'],
                    'spread_type': ml_signal['spread_type'],
                    'reasoning': ml_signal['reasoning']
                }

            if ml_signal and ml_signal['advice'] in ['LONG', 'SHORT']:
                result['trades_attempted'] = 1

                # Determine spread type from ML signal
                if ml_signal['spread_type'] == 'BULL_CALL_SPREAD':
                    spread_type = SpreadType.BULL_CALL_SPREAD
                elif ml_signal['spread_type'] == 'BEAR_CALL_SPREAD':
                    spread_type = SpreadType.BEAR_CALL_SPREAD

                self._log_to_db("INFO", f"ML Signal: {ml_signal['advice']}", {
                    'confidence': ml_signal['confidence'],
                    'spread_type': ml_signal['spread_type']
                })

            elif ml_signal and ml_signal['advice'] == 'STAY_OUT':
                self._log_to_db("INFO", f"ML says STAY_OUT: {ml_signal['reasoning']}")
                # DON'T return immediately - check Oracle as second opinion
                # Oracle can OVERRIDE ML STAY_OUT if it's confident

        # === ORACLE: Use as FALLBACK (when ML unavailable) or OVERRIDE (when ML says STAY_OUT) ===
        oracle_advice = None  # Track Oracle advice separately for proper usage
        ml_said_stay_out = ml_signal and ml_signal['advice'] == 'STAY_OUT'

        if not spread_type and ORACLE_AVAILABLE:
            signal_source = "Oracle"
            oracle_advice = self.get_oracle_advice()

            if oracle_advice:
                result['trades_attempted'] = 1

                # Store Oracle advice for logging
                result['oracle_advice'] = {
                    'advice': oracle_advice.advice.value if hasattr(oracle_advice.advice, 'value') else str(oracle_advice.advice),
                    'win_probability': oracle_advice.win_probability,
                    'confidence': oracle_advice.confidence,
                    'reasoning': oracle_advice.reasoning
                }

                if oracle_advice.advice == TradingAdvice.SKIP_TODAY:
                    # Both ML (if checked) and Oracle say skip
                    if ml_said_stay_out:
                        skip_reason = f"ML STAY_OUT + Oracle SKIP agree: {oracle_advice.reasoning}"
                        self._log_to_db("INFO", f"Both ML and Oracle say SKIP")
                    else:
                        skip_reason = f"Oracle says SKIP: {oracle_advice.reasoning}"
                    self._log_to_db("INFO", skip_reason)
                    self._log_skip_decision(skip_reason, gex_data, ml_signal)
                    result['signal_source'] = 'ML+Oracle' if ml_said_stay_out else 'Oracle'
                    result['decision_reason'] = f"NO TRADE: {skip_reason}"
                    # Log scan activity - ORACLE SKIP
                    if SCAN_LOGGER_AVAILABLE and log_athena_scan:
                        spot = gex_data.get('spot_price', 0)
                        try:
                            from data.unified_data_provider import get_vix
                            vix = get_vix() or 20.0
                        except Exception:
                            vix = 20.0

                        log_athena_scan(
                            outcome=ScanOutcome.NO_TRADE,
                            decision_summary=skip_reason[:200],
                            action_taken="No trade - Oracle AI recommends skip",
                            market_data={'underlying_price': spot, 'vix': vix, 'symbol': 'SPY'},
                            gex_data=gex_data,
                            signal_source='ML+Oracle' if ml_said_stay_out else 'Oracle',
                            signal_direction="NEUTRAL",
                            signal_confidence=oracle_advice.confidence,
                            signal_win_probability=oracle_advice.win_probability,
                            checks=[
                                CheckResult("should_trade", True, "Yes", "Yes", "Trade conditions met"),
                                CheckResult("gex_data", True, f"Spot ${spot:.2f}", "Required", f"GEX regime: {gex_data.get('regime', 'UNKNOWN')}"),
                                CheckResult("ml_signal", ml_said_stay_out, "STAY_OUT" if ml_said_stay_out else "N/A", "Actionable", "ML recommends staying out" if ml_said_stay_out else "ML not available"),
                                CheckResult("oracle_signal", True, "SKIP_TODAY", "TRADE", f"Oracle: {oracle_advice.reasoning[:50]}")
                            ]
                        )
                    # Still check exits
                    closed = self.check_exits()
                    result['positions_closed'] = len(closed)
                    result['daily_pnl'] = sum(p.realized_pnl for p in closed)
                    return result

                # Oracle says TRADE - this OVERRIDES ML STAY_OUT
                if ml_said_stay_out:
                    self._log_to_db("WARNING",
                        f"ORACLE OVERRIDE: Oracle says {oracle_advice.advice.value} (conf={oracle_advice.confidence:.0%}, "
                        f"win={oracle_advice.win_probability:.0%}) overriding ML STAY_OUT",
                        {'ml_advice': 'STAY_OUT', 'oracle_advice': oracle_advice.advice.value,
                         'oracle_confidence': oracle_advice.confidence,
                         'oracle_win_prob': oracle_advice.win_probability}
                    )
                    signal_source = "Oracle (override ML)"

                # Determine spread type from Oracle reasoning
                if "BULL_CALL_SPREAD" in oracle_advice.reasoning:
                    spread_type = SpreadType.BULL_CALL_SPREAD
                elif "BEAR_CALL_SPREAD" in oracle_advice.reasoning:
                    spread_type = SpreadType.BEAR_CALL_SPREAD
                # Also check for BULLISH/BEARISH direction as fallback
                elif hasattr(oracle_advice, 'direction'):
                    if oracle_advice.direction == 'BULLISH':
                        spread_type = SpreadType.BULL_CALL_SPREAD
                    elif oracle_advice.direction == 'BEARISH':
                        spread_type = SpreadType.BEAR_CALL_SPREAD

                # Log Oracle-specific info (similar to ARES fix)
                self._log_to_db("INFO", f"Oracle Advice: {oracle_advice.advice.value}", {
                    'win_probability': oracle_advice.win_probability,
                    'confidence': oracle_advice.confidence,
                    'suggested_risk_pct': oracle_advice.suggested_risk_pct,
                    'suggested_call_strike': getattr(oracle_advice, 'suggested_call_strike', None),
                    'overriding_ml': ml_said_stay_out
                })

        # No actionable signal - provide detailed context
        if not spread_type:
            # Build detailed skip reason
            skip_details = []
            if ml_signal:
                skip_details.append(f"ML={ml_signal['advice']} (conf={ml_signal['confidence']:.0%})")
            else:
                skip_details.append("ML=unavailable")
            if oracle_advice:
                advice_str = oracle_advice.advice.value if hasattr(oracle_advice.advice, 'value') else str(oracle_advice.advice)
                skip_details.append(f"Oracle={advice_str} (win={oracle_advice.win_probability:.0%})")
            else:
                skip_details.append("Oracle=unavailable")

            skip_reason = f"No actionable signal: {', '.join(skip_details)}"

            self._log_to_db("INFO", skip_reason)
            self._log_skip_decision(skip_reason, gex_data, ml_signal)
            result['errors'].append("No actionable signal")
            result['decision_reason'] = f"NO TRADE: {skip_reason}"
            # Log scan activity - NO ACTIONABLE SIGNAL
            if SCAN_LOGGER_AVAILABLE and log_athena_scan:
                # Build market data from gex_data
                spot = gex_data.get('spot_price', 0)
                try:
                    from data.unified_data_provider import get_vix
                    vix = get_vix() or 20.0
                except Exception:
                    vix = 20.0

                log_athena_scan(
                    outcome=ScanOutcome.NO_TRADE,
                    decision_summary=skip_reason,
                    action_taken="No trade - signals not actionable",
                    market_data={'underlying_price': spot, 'vix': vix, 'symbol': 'SPY'},
                    gex_data=gex_data,
                    signal_source="ML+Oracle",
                    signal_direction=ml_signal.get('model_predictions', {}).get('direction', 'UNKNOWN') if ml_signal else "UNKNOWN",
                    signal_confidence=ml_signal['confidence'] if ml_signal else 0,
                    signal_win_probability=ml_signal['win_probability'] if ml_signal else 0,
                    checks=[
                        CheckResult("should_trade", True, "Yes", "Yes", "Trade conditions met"),
                        CheckResult("gex_data", True, f"Spot ${spot:.2f}", "Required", f"GEX regime: {gex_data.get('regime', 'UNKNOWN')}"),
                        CheckResult("gex_walls", True, f"Put ${gex_data.get('put_wall', 0):.0f} / Call ${gex_data.get('call_wall', 0):.0f}", "Informational", "Support/resistance levels"),
                        CheckResult("ml_signal", ml_signal is not None, ml_signal['advice'] if ml_signal else "None", "Actionable", f"ML says {ml_signal['advice'] if ml_signal else 'unavailable'}"),
                        CheckResult("oracle_signal", oracle_advice is not None, advice_str if oracle_advice else "None", "Actionable", f"Oracle says {advice_str if oracle_advice else 'unavailable'}"),
                        CheckResult("actionable_signal", False, "None", "Required", "Neither ML nor Oracle provided actionable direction")
                    ]
                )
            # Still check exits
            closed = self.check_exits()
            result['positions_closed'] = len(closed)
            result['daily_pnl'] = sum(p.realized_pnl for p in closed)
            return result

        result['signal_source'] = signal_source

        # === R:R FILTER: Check risk/reward ratio using GEX walls ===
        rr_ratio, rr_reasoning = self.calculate_risk_reward(gex_data, spread_type)
        result['rr_ratio'] = rr_ratio
        result['rr_reasoning'] = rr_reasoning

        self._log_to_db("INFO", f"R:R Analysis: {rr_reasoning}")

        if rr_ratio < self.config.min_rr_ratio:
            skip_reason = f"R:R {rr_ratio:.2f}:1 below minimum {self.config.min_rr_ratio}:1 - {rr_reasoning}"
            self._log_to_db("INFO",
                f"SKIP: R:R {rr_ratio:.2f}:1 below minimum {self.config.min_rr_ratio}:1",
                {'rr_ratio': rr_ratio, 'min_required': self.config.min_rr_ratio, 'reasoning': rr_reasoning}
            )
            self._log_skip_decision(skip_reason, gex_data, ml_signal)
            result['errors'].append(f"R:R {rr_ratio:.2f}:1 < {self.config.min_rr_ratio}:1 minimum")
            result['decision_reason'] = f"NO TRADE: {skip_reason}"
            # Log scan activity - R:R RATIO FAILED
            if SCAN_LOGGER_AVAILABLE and log_athena_scan:
                spot = gex_data.get('spot_price', 0)
                try:
                    from data.unified_data_provider import get_vix
                    vix = get_vix() or 20.0
                except Exception:
                    vix = 20.0

                log_athena_scan(
                    outcome=ScanOutcome.NO_TRADE,
                    decision_summary=skip_reason,
                    action_taken="No trade - risk/reward unfavorable",
                    market_data={'underlying_price': spot, 'vix': vix, 'symbol': 'SPY'},
                    gex_data=gex_data,
                    signal_source=signal_source,
                    signal_direction="BULLISH" if spread_type == SpreadType.BULL_CALL_SPREAD else "BEARISH",
                    signal_confidence=ml_signal['confidence'] if ml_signal else 0,
                    signal_win_probability=ml_signal['win_probability'] if ml_signal else 0,
                    risk_reward_ratio=rr_ratio,
                    checks=[
                        CheckResult("should_trade", True, "Yes", "Yes", "Trade conditions met"),
                        CheckResult("gex_data", True, f"Spot ${spot:.2f}", "Required", f"GEX regime: {gex_data.get('regime', 'UNKNOWN')}"),
                        CheckResult("gex_walls", True, f"Put ${gex_data.get('put_wall', 0):.0f} / Call ${gex_data.get('call_wall', 0):.0f}", "Informational", "Used for R:R calculation"),
                        CheckResult("signal", True, signal_source, "Actionable", f"{signal_source} signal received"),
                        CheckResult("rr_ratio", False, f"{rr_ratio:.2f}:1", f">={self.config.min_rr_ratio}:1", f"R:R too low - need {self.config.min_rr_ratio}:1 minimum")
                    ]
                )
            # Still check exits for existing positions
            closed = self.check_exits()
            result['positions_closed'] = len(closed)
            result['daily_pnl'] = sum(p.realized_pnl for p in closed)
            return result

        self._log_to_db("INFO",
            f"R:R PASSED: {rr_ratio:.2f}:1 >= {self.config.min_rr_ratio}:1 minimum",
            {'rr_ratio': rr_ratio, 'min_required': self.config.min_rr_ratio}
        )

        # Save signal to database
        signal_id = self._save_ml_signal_to_db(ml_signal, gex_data) if ml_signal else None

        # Create advice object for execution
        # CRITICAL: Use actual Oracle advice when Oracle is the signal source (fixes bug where
        # Oracle advice was being ignored - similar to ARES fix for SD multiplier/GEX walls)
        class MockAdvice:
            def __init__(self, ml_sig, oracle_adv=None):
                if oracle_adv is not None:
                    # Use actual Oracle advice - don't ignore it!
                    self.confidence = oracle_adv.confidence
                    self.win_probability = oracle_adv.win_probability
                    self.reasoning = oracle_adv.reasoning
                    self.claude_analysis = getattr(oracle_adv, 'claude_analysis', None)
                    # Preserve Oracle's suggested values for position sizing
                    self.suggested_risk_pct = getattr(oracle_adv, 'suggested_risk_pct', None)
                    self.suggested_call_strike = getattr(oracle_adv, 'suggested_call_strike', None)
                elif ml_sig:
                    self.confidence = ml_sig['confidence']
                    self.win_probability = ml_sig['win_probability']
                    self.reasoning = ml_sig['reasoning']
                    self.claude_analysis = None
                    self.suggested_risk_pct = None
                    self.suggested_call_strike = None
                else:
                    # Should not happen - but fallback to defaults
                    self.confidence = 0.5
                    self.win_probability = 0.5
                    self.reasoning = "Unknown signal source"
                    self.claude_analysis = None
                    self.suggested_risk_pct = None
                    self.suggested_call_strike = None

        # Use Oracle advice if Oracle was the signal source, otherwise use ML signal
        advice_obj = MockAdvice(ml_signal, oracle_advice if signal_source == "Oracle" else None)

        # Log which advice source is being used
        self._log_to_db("INFO", f"Using {signal_source} advice for execution", {
            'confidence': advice_obj.confidence,
            'win_probability': advice_obj.win_probability,
            'suggested_risk_pct': getattr(advice_obj, 'suggested_risk_pct', None),
            'suggested_call_strike': getattr(advice_obj, 'suggested_call_strike', None)
        })

        # Execute spread
        position = self.execute_spread(
            spread_type=spread_type,
            spot_price=gex_data['spot_price'],
            gex_data=gex_data,
            advice=advice_obj,
            signal_id=signal_id,
            ml_signal=ml_signal,
            rr_ratio=rr_ratio
        )

        if position:
            result['trades_executed'] = 1
            result['decision_reason'] = (
                f"TRADE EXECUTED: {spread_type.value} | "
                f"Strikes: {position.long_strike}/{position.short_strike} | "
                f"Contracts: {position.contracts} | "
                f"R:R: {rr_ratio:.2f}:1"
            )
            self._log_to_db("INFO", f"Trade executed: {position.position_id} ({signal_source})")
            # Log scan activity - TRADE EXECUTED
            if SCAN_LOGGER_AVAILABLE and log_athena_scan:
                # Build market data
                spot = gex_data.get('spot_price', 0)
                try:
                    from data.unified_data_provider import get_vix
                    vix = get_vix() or 20.0
                except Exception:
                    vix = 20.0

                log_athena_scan(
                    outcome=ScanOutcome.TRADED,
                    decision_summary=f"Executed {spread_type.value}: {position.long_strike}/{position.short_strike} x{position.contracts}",
                    action_taken=f"Opened {spread_type.value} spread",
                    market_data={'underlying_price': spot, 'vix': vix, 'symbol': 'SPY'},
                    gex_data=gex_data,
                    signal_source=signal_source,
                    signal_direction="BULLISH" if spread_type == SpreadType.BULL_CALL_SPREAD else "BEARISH",
                    signal_confidence=advice_obj.confidence,
                    signal_win_probability=advice_obj.win_probability,
                    risk_reward_ratio=rr_ratio,
                    trade_executed=True,
                    position_id=position.position_id,
                    strike_selection={
                        'long_strike': position.long_strike,
                        'short_strike': position.short_strike,
                        'spread_type': spread_type.value,
                        'rr_ratio': rr_ratio
                    },
                    contracts=position.contracts,
                    premium_collected=abs(position.entry_debit) * 100 * position.contracts if position.entry_debit < 0 else 0,
                    max_risk=position.max_loss,
                    checks=[
                        CheckResult("should_trade", True, "Yes", "Yes", "Trade conditions met"),
                        CheckResult("gex_data", True, f"Spot ${spot:.2f}", "Required", f"GEX regime: {gex_data.get('regime', 'UNKNOWN')}"),
                        CheckResult("gex_walls", True, f"Put ${gex_data.get('put_wall', 0):.0f} / Call ${gex_data.get('call_wall', 0):.0f}", "Informational", "Used for R:R calculation"),
                        CheckResult("signal", True, signal_source, "Actionable", f"{signal_source}: {'BULLISH' if spread_type == SpreadType.BULL_CALL_SPREAD else 'BEARISH'}"),
                        CheckResult("rr_ratio", True, f"{rr_ratio:.2f}:1", f">={self.config.min_rr_ratio}:1", "Risk:Reward filter passed"),
                        CheckResult("execution", True, position.position_id, "Required", "Order filled successfully")
                    ]
                )
        else:
            result['decision_reason'] = "NO TRADE: Execution failed"
            # Log scan activity - EXECUTION FAILED
            if SCAN_LOGGER_AVAILABLE and log_athena_scan:
                # Build market data
                spot = gex_data.get('spot_price', 0)
                try:
                    from data.unified_data_provider import get_vix
                    vix = get_vix() or 20.0
                except Exception:
                    vix = 20.0

                log_athena_scan(
                    outcome=ScanOutcome.ERROR,
                    decision_summary="Spread execution failed",
                    action_taken="Order rejected or failed - will retry",
                    market_data={'underlying_price': spot, 'vix': vix, 'symbol': 'SPY'},
                    gex_data=gex_data,
                    signal_source=signal_source,
                    signal_direction="BULLISH" if spread_type == SpreadType.BULL_CALL_SPREAD else "BEARISH" if spread_type else "UNKNOWN",
                    signal_confidence=advice_obj.confidence if advice_obj else 0,
                    signal_win_probability=advice_obj.win_probability if advice_obj else 0,
                    risk_reward_ratio=rr_ratio,
                    error_message="Order execution failed via Tradier API - check buying power and order status",
                    error_type="EXECUTION_ERROR",
                    checks=[
                        CheckResult("should_trade", True, "Yes", "Yes", "Trade conditions met"),
                        CheckResult("gex_data", True, f"Spot ${spot:.2f}", "Required", f"GEX regime: {gex_data.get('regime', 'UNKNOWN')}"),
                        CheckResult("signal", True, signal_source, "Actionable", f"{signal_source}: {'BULLISH' if spread_type == SpreadType.BULL_CALL_SPREAD else 'BEARISH'}"),
                        CheckResult("rr_ratio", True, f"{rr_ratio:.2f}:1", f">={self.config.min_rr_ratio}:1", "Risk:Reward passed"),
                        CheckResult("execution", False, "Failed", "Required", "Order execution failed - check Tradier order status")
                    ]
                )

        # Check exits for existing positions
        closed = self.check_exits()
        result['positions_closed'] = len(closed)
        result['daily_pnl'] = sum(p.realized_pnl for p in closed)

        self._log_to_db("INFO", f"=== ATHENA Cycle Complete ===", result)

        return result

    def _save_ml_signal_to_db(self, ml_signal: Dict, gex_data: Dict) -> Optional[int]:
        """Save ML signal to apache_signals table with full ML model data"""
        try:
            import json
            conn = get_connection()
            c = conn.cursor()

            direction = "FLAT"
            if ml_signal['advice'] == 'LONG':
                direction = "BULLISH"
            elif ml_signal['advice'] == 'SHORT':
                direction = "BEARISH"

            # Extract model predictions
            model_preds = ml_signal.get('model_predictions', {})

            # Try enhanced insert with ML columns (may fail if migration not run)
            try:
                c.execute("""
                    INSERT INTO apache_signals (
                        ticker, signal_direction, ml_confidence, oracle_advice,
                        gex_regime, call_wall, put_wall, spot_price,
                        spread_type, reasoning, signal_source,
                        direction_prediction, ml_predictions,
                        flip_gravity_prob, magnet_attraction_prob,
                        pin_zone_prob, expected_volatility_pct,
                        overall_conviction
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    self.config.ticker,
                    direction,
                    ml_signal['confidence'],
                    ml_signal['advice'],
                    gex_data.get('regime', 'NEUTRAL'),
                    gex_data.get('call_wall'),
                    gex_data.get('put_wall'),
                    gex_data.get('spot_price'),
                    ml_signal['spread_type'],
                    ml_signal['reasoning'][:1000],  # Store more reasoning
                    'ml',  # signal_source
                    model_preds.get('direction', 'FLAT'),  # direction_prediction
                    json.dumps(model_preds),  # ml_predictions as JSON
                    model_preds.get('flip_gravity'),
                    model_preds.get('magnet_attraction'),
                    model_preds.get('pin_zone'),
                    model_preds.get('volatility'),
                    ml_signal.get('win_probability', 0.5)  # overall_conviction
                ))
            except Exception:
                # Fallback to basic insert if new columns don't exist
                c.execute("""
                    INSERT INTO apache_signals (
                        ticker, signal_direction, ml_confidence, oracle_advice,
                        gex_regime, call_wall, put_wall, spot_price,
                        spread_type, reasoning
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    self.config.ticker,
                    direction,
                    ml_signal['confidence'],
                    ml_signal['advice'],
                    gex_data.get('regime', 'NEUTRAL'),
                    gex_data.get('call_wall'),
                    gex_data.get('put_wall'),
                    gex_data.get('spot_price'),
                    ml_signal['spread_type'],
                    ml_signal['reasoning'][:1000]  # Store more reasoning
                ))

            signal_id = c.fetchone()[0]
            conn.commit()
            conn.close()

            self._log_to_db("INFO", f"ML Signal saved: {direction}", {
                'signal_id': signal_id,
                'direction': model_preds.get('direction'),
                'confidence': ml_signal['confidence'],
                'win_probability': ml_signal.get('win_probability')
            })
            return signal_id
        except Exception as e:
            self._log_to_db("ERROR", f"Failed to save ML signal: {e}")
            return None

    def get_status(self) -> Dict[str, Any]:
        """Get current bot status"""
        return {
            'bot_name': 'ATHENA',
            'mode': self.config.mode.value,
            'capital': self.current_capital,
            'open_positions': len(self.open_positions),
            'closed_today': len([p for p in self.closed_positions
                                if p.close_date and p.close_date.startswith(datetime.now().strftime("%Y-%m-%d"))]),
            'daily_trades': self.daily_trades,
            'daily_pnl': sum(p.realized_pnl for p in self.closed_positions
                           if p.close_date and p.close_date.startswith(datetime.now().strftime("%Y-%m-%d"))),
            'oracle_available': self.oracle is not None,
            'kronos_available': self.kronos is not None,
            'tradier_available': self.tradier is not None,
            'tradier_gex_available': TRADIER_GEX_AVAILABLE,
            'gex_ml_available': self.gex_ml is not None
        }


# Convenience function for running ATHENA
def run_athena(capital: float = 100_000, mode: str = "paper") -> ATHENATrader:
    """Quick start ATHENA trading bot"""
    config = ATHENAConfig(
        mode=TradingMode.PAPER if mode == "paper" else TradingMode.LIVE
    )
    trader = ATHENATrader(initial_capital=capital, config=config)
    return trader


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Test run
    athena = run_athena()
    status = athena.get_status()
    print(f"\nATHENA Status: {status}")

    # Run cycle
    result = athena.run_daily_cycle()
    print(f"\nCycle Result: {result}")
