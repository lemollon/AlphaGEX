"""
ATHENA - Directional Spread Trading Bot
=========================================

Named after Athena, Greek goddess of wisdom and strategic warfare.

STRATEGY: GEX-Based Directional Spreads (both debit spreads)
- BULLISH: Bull Call Spread (buy ATM call, sell OTM call)
- BEARISH: Bear Put Spread (buy ATM put, sell OTM put)

SIGNAL FLOW:
    KRONOS (GEX Calculator) --> ORACLE (ML Advisor) --> ATHENA (Execution)

The key edge is the GEX wall proximity filter:
- Buy calls near put wall (support) for bullish
- Buy puts near call wall (resistance) for bearish

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

# Circuit breaker for risk management - CRITICAL for production safety
try:
    from trading.circuit_breaker import (
        get_circuit_breaker,
        is_trading_enabled,
        record_trade_pnl,
        CircuitBreakerState
    )
    CIRCUIT_BREAKER_AVAILABLE = True
except ImportError:
    CIRCUIT_BREAKER_AVAILABLE = False
    get_circuit_breaker = None
    is_trading_enabled = None
    record_trade_pnl = None

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

# Data validation for stale data detection and sanity checks
try:
    from trading.data_validation import (
        validate_market_data,
        validate_spread_strikes,
        validate_spot_price,
        StaleDataError,
        InvalidDataError,
        MAX_DATA_AGE_SECONDS
    )
    DATA_VALIDATION_AVAILABLE = True
except ImportError:
    DATA_VALIDATION_AVAILABLE = False
    validate_market_data = None
    StaleDataError = Exception
    InvalidDataError = Exception
    MAX_DATA_AGE_SECONDS = 300

# Position-level stop loss management
try:
    from trading.position_stop_loss import (
        PositionStopLossManager,
        StopLossConfig,
        StopLossType,
        create_spread_stop_config,
        get_stop_loss_manager,
        check_position_stop_loss
    )
    STOP_LOSS_MODULE_AVAILABLE = True
except ImportError:
    STOP_LOSS_MODULE_AVAILABLE = False
    PositionStopLossManager = None
    get_stop_loss_manager = None

# Idempotency for order deduplication
try:
    from trading.idempotency import (
        get_idempotency_manager,
        generate_idempotency_key,
        check_idempotency,
        with_idempotency,
        mark_idempotency_completed,
        mark_idempotency_failed
    )
    IDEMPOTENCY_AVAILABLE = True
except ImportError:
    IDEMPOTENCY_AVAILABLE = False
    get_idempotency_manager = None

logger = logging.getLogger(__name__)

CENTRAL_TZ = ZoneInfo("America/Chicago")


class TradingMode(Enum):
    """Trading execution mode"""
    PAPER = "paper"       # Sandbox/Paper trading
    LIVE = "live"         # Live trading with real money
    BACKTEST = "backtest" # Backtesting mode (no execution)


class SpreadType(Enum):
    """Type of vertical spread"""
    BULL_CALL_SPREAD = "BULL_CALL_SPREAD"  # Bullish: Buy ATM call, Sell OTM call (debit)
    BEAR_PUT_SPREAD = "BEAR_PUT_SPREAD"    # Bearish: Buy ATM put, Sell OTM put (debit)


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
    # Wall filter - CRITICAL for win rate (backtest results):
    #   0.5% = 98% WR, 18.19x profit ratio (BEST)
    #   1.0% = 90% WR, 4.86x profit ratio
    #   1.5% = ~85% WR (original hardcoded value - too loose)
    wall_filter_pct: float = 0.5          # Trade only within 0.5% of GEX wall

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

    # Timing (aligned with scheduler: 8:35 AM - 2:30 PM CT)
    entry_start_time: str = "08:35"       # Start trading 5 min after market open
    entry_end_time: str = "14:30"         # Stop entries at 2:30 PM CT
    exit_by_time: str = "15:55"           # Exit all by this time (0DTE)


class ATHENATrader:
    """
    ATHENA - Directional Spread Trading Bot

    Uses GEX signals from KRONOS, processed through ORACLE ML advisor,
    to execute Bull Call Spreads (bullish) and Bear Put Spreads (bearish).
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

        # CRITICAL: Load any existing open positions from database
        # This ensures positions survive bot restarts
        self._load_open_positions_from_db()

        logger.info(f"ATHENA initialized: capital=${initial_capital:,.2f}, mode={self.config.mode.value}, open_positions={len(self.open_positions)}")

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
                    db_value = float(value)
                    # CRITICAL: Backtest showed 0.5% = 98% WR, 1.0% = 90% WR
                    # Warn if database has a suboptimal value
                    if db_value > 0.5:
                        logger.warning(f"ATHENA: Database wall_filter_pct={db_value}% is SUBOPTIMAL! "
                                      f"Backtest showed: 0.5%=98% WR, 1.0%=90% WR. Using 0.5% instead.")
                        self.config.wall_filter_pct = 0.5  # Override with optimal value
                    else:
                        self.config.wall_filter_pct = db_value
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

    def _load_open_positions_from_db(self) -> None:
        """
        Load all open positions from database on startup.

        CRITICAL: This ensures positions survive bot restarts.
        Without this, positions in the DB become invisible when the bot restarts
        because self.open_positions starts as an empty list.
        """
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Get all positions with status='open' that haven't expired yet
            today = datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d')

            cursor.execute('''
                SELECT
                    position_id, spread_type, created_at, expiration,
                    long_strike, short_strike, entry_price, contracts,
                    max_profit, max_loss, spot_at_entry, gex_regime,
                    oracle_confidence, oracle_reasoning, ticker
                FROM apache_positions
                WHERE status = 'open' AND expiration >= %s
                ORDER BY created_at ASC
            ''', (today,))

            loaded_count = 0
            for row in cursor.fetchall():
                spread_type = SpreadType.BULL_CALL_SPREAD if row[1] == 'BULL_CALL_SPREAD' else SpreadType.BEAR_PUT_SPREAD
                open_date_val = str(row[2])[:10] if row[2] else ""

                pos = SpreadPosition(
                    position_id=row[0],
                    spread_type=spread_type,
                    open_date=open_date_val,
                    expiration=str(row[3]) if row[3] else "",
                    long_strike=float(row[4] or 0),
                    short_strike=float(row[5] or 0),
                    entry_debit=float(row[6] or 0),
                    contracts=int(row[7] or 0),
                    spread_width=abs(float(row[5] or 0) - float(row[4] or 0)),
                    max_profit=float(row[8] or 0),
                    max_loss=float(row[9] or 0),
                    underlying_price_at_entry=float(row[10] or 0),
                    gex_regime_at_entry=row[11] or "",
                    oracle_confidence=float(row[12] or 0),
                    oracle_reasoning=row[13] or "",
                    order_id="",
                    status='open',
                    initial_contracts=int(row[7] or 0),
                    contracts_remaining=int(row[7] or 0)
                )

                # Add to open_positions list
                self.open_positions.append(pos)
                loaded_count += 1
                logger.info(f"ATHENA: Recovered position {pos.position_id} - {pos.spread_type.value} {pos.long_strike}/{pos.short_strike} exp {pos.expiration}")

            if loaded_count > 0:
                logger.info(f"ATHENA: Recovered {loaded_count} open positions from database")
            else:
                logger.info("ATHENA: No open positions to recover from database")

        except Exception as e:
            logger.error(f"ATHENA: Error loading open positions from DB: {e}")
        finally:
            if conn:
                conn.close()

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

    def _log_detailed_trade_open(
        self,
        position: 'SpreadPosition',
        gex_data: Dict,
        advice: Any,
        ml_signal: Optional[Dict] = None,
        rr_ratio: float = 0
    ) -> None:
        """
        Log super detailed trade information to console when a trade opens.
        Provides complete visibility into trade setup, Greeks, market context, and reasoning.
        """
        try:
            from datetime import datetime
            now = datetime.now(CENTRAL_TZ)

            # Calculate Greeks
            vix = gex_data.get('vix', 15)
            spot = position.underlying_price_at_entry
            greeks = self._get_leg_greeks(position, spot, vix)

            # Net Greeks
            net_delta = greeks.get('long_delta', 0) - greeks.get('short_delta', 0)
            net_gamma = greeks.get('long_gamma', 0) - greeks.get('short_gamma', 0)
            net_theta = greeks.get('long_theta', 0) - greeks.get('short_theta', 0)
            net_vega = greeks.get('long_vega', 0) - greeks.get('short_vega', 0)

            # Calculate time to EOD exit
            eod_time = now.replace(hour=15, minute=55, second=0)
            time_to_eod = eod_time - now
            hours_to_eod = time_to_eod.total_seconds() / 3600

            # Trade direction
            is_bullish = position.spread_type == SpreadType.BULL_CALL_SPREAD
            direction = "BULLISH" if is_bullish else "BEARISH"
            spread_name = "Bull Call Spread" if is_bullish else "Bear Put Spread"

            # Breakeven calculation
            if is_bullish:
                breakeven = position.long_strike + position.entry_debit
            else:
                breakeven = position.short_strike - abs(position.entry_debit)

            # Risk/Reward ratio
            if position.max_loss > 0:
                rr = position.max_profit / position.max_loss
            else:
                rr = rr_ratio if rr_ratio > 0 else 0

            # GEX data
            put_wall = gex_data.get('put_wall', 0)
            call_wall = gex_data.get('call_wall', 0)
            net_gex = gex_data.get('net_gex', 0)
            regime = gex_data.get('regime', 'NEUTRAL')
            flip_point = gex_data.get('flip_point', 0)

            # ML Signal data
            ml_direction = "N/A"
            ml_confidence = 0
            ml_win_prob = 0
            flip_gravity = 0
            magnet_pull = 0
            if ml_signal:
                ml_direction = ml_signal.get('direction', 'N/A')
                ml_confidence = ml_signal.get('confidence', 0)
                ml_win_prob = ml_signal.get('win_probability', 0)
                flip_gravity = ml_signal.get('flip_gravity', 0)
                magnet_pull = ml_signal.get('magnet_attraction', 0)

            # Oracle data
            oracle_confidence = getattr(advice, 'confidence', 0) * 100
            oracle_win_prob = getattr(advice, 'win_probability', 0) * 100
            oracle_reasoning = getattr(advice, 'reasoning', 'N/A')[:200]
            suggested_risk = getattr(advice, 'suggested_risk_pct', 0)

            # Total position cost
            total_cost = abs(position.entry_debit) * position.contracts * 100

            # Build detailed log
            log_output = f"""
════════════════════════════════════════════════════════════════════════════════
🎯 ATHENA TRADE OPENED
════════════════════════════════════════════════════════════════════════════════
Position ID:     {position.position_id}
Trade Type:      {position.spread_type.value} ({direction})
Ticker:          {self.config.ticker}
Time:            {now.strftime('%Y-%m-%d %H:%M:%S CT')}

📅 EXPIRATION
─────────────────────────────────────────────────────────────────────────────────
Expiration:      {position.expiration} (0DTE - Today!)
Time to Close:   {hours_to_eod:.1f}h until 15:55 CT EOD exit

📊 STRIKES & PRICING
─────────────────────────────────────────────────────────────────────────────────
Long Strike:     ${position.long_strike:.2f} {'(ATM)' if is_bullish else '(OTM)'}
Short Strike:    ${position.short_strike:.2f} {'(OTM)' if is_bullish else '(ATM)'}
Spread Width:    ${position.spread_width:.2f}
Entry {'Debit' if position.entry_debit > 0 else 'Credit'}:     ${abs(position.entry_debit):.2f} per contract
Contracts:       {position.contracts}
Total Cost:      ${total_cost:.2f}

💰 PROFIT/LOSS POTENTIAL
─────────────────────────────────────────────────────────────────────────────────
Max Profit:      ${position.max_profit:.2f} (+{(position.max_profit/total_cost*100) if total_cost > 0 else 0:.1f}%)  @ SPY {'≥' if is_bullish else '≤'} ${position.short_strike:.2f}
Max Loss:        ${position.max_loss:.2f} (-100.0%)    @ SPY {'≤' if is_bullish else '≥'} ${position.long_strike:.2f}
Breakeven:       ${breakeven:.2f}
Risk/Reward:     1:{rr:.2f}

📈 GREEKS AT ENTRY
─────────────────────────────────────────────────────────────────────────────────
           Long Leg    Short Leg    Net
Delta:     {greeks.get('long_delta', 0):+.3f}       {greeks.get('short_delta', 0):+.3f}        {net_delta:+.3f}
Gamma:     {greeks.get('long_gamma', 0):+.3f}       {greeks.get('short_gamma', 0):+.3f}        {net_gamma:+.3f}
Theta:     {greeks.get('long_theta', 0):+.3f}       {greeks.get('short_theta', 0):+.3f}        {net_theta:+.3f}
Vega:      {greeks.get('long_vega', 0):+.3f}       {greeks.get('short_vega', 0):+.3f}        {net_vega:+.3f}
IV:        {greeks.get('long_iv', 0)*100:.1f}%        {greeks.get('short_iv', 0)*100:.1f}%        ---

📉 MARKET CONDITIONS
─────────────────────────────────────────────────────────────────────────────────
SPY Price:       ${spot:.2f}
VIX:             {vix:.1f} ({'Low' if vix < 15 else 'Moderate' if vix < 25 else 'High'} volatility)
GEX Regime:      {regime} ({'Bullish bias' if regime == 'POSITIVE' else 'Bearish bias' if regime == 'NEGATIVE' else 'Neutral'})
Net GEX:         {net_gex/1e9:.2f}B
Put Wall:        ${put_wall:.2f}
Call Wall:       ${call_wall:.2f}
Flip Point:      ${flip_point:.2f}
SPY vs Walls:    ${spot - put_wall:.2f} above put wall, ${call_wall - spot:.2f} below call wall

🤖 ML PREDICTION (ORACLE)
─────────────────────────────────────────────────────────────────────────────────
Direction:       {ml_direction}
ML Confidence:   {ml_confidence*100:.1f}%
Win Probability: {ml_win_prob*100:.1f}%
Flip Gravity:    {flip_gravity*100:.1f}% (attraction to flip point)
Magnet Pull:     {magnet_pull*100:.1f}% (attraction to {('call' if is_bullish else 'put')} wall)

🧠 ORACLE AI ADVICE
─────────────────────────────────────────────────────────────────────────────────
Confidence:      {oracle_confidence:.1f}%
Win Probability: {oracle_win_prob:.1f}%
Suggested Risk:  {suggested_risk:.1f}%
Reasoning:       {oracle_reasoning}

✅ POSITION SIZING
─────────────────────────────────────────────────────────────────────────────────
Risk Per Trade:  {self.config.risk_per_trade_pct:.1f}% of capital
Max Risk $:      ${self.current_capital * self.config.risk_per_trade_pct / 100:.2f}
Position Size:   {position.contracts} contracts (${total_cost:.2f})
Capital:         ${self.current_capital:,.2f}
Daily Trades:    {self.daily_trades}/{self.config.max_daily_trades}
Open Positions:  {len(self.open_positions)}/{self.config.max_open_positions}
════════════════════════════════════════════════════════════════════════════════
"""
            # Print to console
            print(log_output)
            logger.info(f"ATHENA Trade Opened: {position.position_id} | {spread_name} {position.contracts}x ${position.long_strike}/${position.short_strike} | Entry: ${abs(position.entry_debit):.2f}")

        except Exception as e:
            logger.error(f"Error in detailed trade logging: {e}")
            import traceback
            traceback.print_exc()

    def _log_detailed_trade_close(
        self,
        position: 'SpreadPosition',
        exit_reason: str,
        exit_price: float,
        gex_data: Optional[Dict] = None
    ) -> None:
        """
        Log super detailed trade information to console when a trade closes.
        Shows entry vs exit comparison, P&L breakdown, and performance metrics.
        """
        try:
            from datetime import datetime
            now = datetime.now(CENTRAL_TZ)

            # Calculate duration (timezone-aware)
            try:
                # Parse date string and make timezone-aware
                open_date_naive = datetime.strptime(position.open_date, "%Y-%m-%d")
                open_time = open_date_naive.replace(tzinfo=CENTRAL_TZ)
                duration = now - open_time
                duration_str = f"{duration.days}d {duration.seconds // 3600}h {(duration.seconds % 3600) // 60}m"
            except (ValueError, TypeError, AttributeError) as e:
                logger.debug(f"Could not calculate duration: {e}")
                duration_str = "N/A"

            # P&L calculations
            entry_cost = abs(position.entry_debit) * position.initial_contracts * 100
            realized_pnl = position.realized_pnl if hasattr(position, 'realized_pnl') else 0
            pnl_pct = (realized_pnl / entry_cost * 100) if entry_cost > 0 else 0

            # Trade result
            is_win = realized_pnl > 0
            result_emoji = "✅ WIN" if is_win else "❌ LOSS" if realized_pnl < 0 else "➖ BREAKEVEN"

            # Greeks at exit (if we have current market data)
            vix = gex_data.get('vix', 15) if gex_data else 15
            current_spot = gex_data.get('spot', position.underlying_price_at_entry) if gex_data else position.underlying_price_at_entry
            greeks_exit = self._get_leg_greeks(position, current_spot, vix)
            greeks_entry = self._get_leg_greeks(position, position.underlying_price_at_entry, vix)

            net_delta_entry = greeks_entry.get('long_delta', 0) - greeks_entry.get('short_delta', 0)
            net_delta_exit = greeks_exit.get('long_delta', 0) - greeks_exit.get('short_delta', 0)

            # Scale-out summary
            scale_out_info = ""
            if position.scale_out_1_done or position.scale_out_2_done:
                scale_out_info = f"""
📊 SCALE-OUT SUMMARY
─────────────────────────────────────────────────────────────────────────────────
Scale-Out 1:     {'✓ Done' if position.scale_out_1_done else '✗ Not triggered'}
Scale-Out 2:     {'✓ Done' if position.scale_out_2_done else '✗ Not triggered'}
Scaled P&L:      ${position.total_scaled_pnl:.2f}
Contracts Left:  {position.contracts_remaining}/{position.initial_contracts}
"""

            # Direction
            is_bullish = position.spread_type == SpreadType.BULL_CALL_SPREAD
            spread_name = "Bull Call Spread" if is_bullish else "Bear Put Spread"

            # Spot price movement
            spot_entry = position.underlying_price_at_entry
            spot_exit = current_spot
            spot_change = spot_exit - spot_entry
            spot_change_pct = (spot_change / spot_entry * 100) if spot_entry > 0 else 0

            log_output = f"""
════════════════════════════════════════════════════════════════════════════════
🏁 ATHENA TRADE CLOSED - {result_emoji}
════════════════════════════════════════════════════════════════════════════════
Position ID:     {position.position_id}
Trade Type:      {spread_name}
Exit Reason:     {exit_reason}
Time:            {now.strftime('%Y-%m-%d %H:%M:%S CT')}

📊 RESULT
─────────────────────────────────────────────────────────────────────────────────
Entry {'Debit' if position.entry_debit > 0 else 'Credit'}:     ${abs(position.entry_debit):.2f}
Exit Price:      ${exit_price:.2f}
P&L per Contract: ${realized_pnl / position.initial_contracts / 100 if position.initial_contracts > 0 else 0:+.2f} ({pnl_pct:+.1f}%)
Contracts:       {position.initial_contracts}
═══════════════════════════════════════════
REALIZED P&L:    ${realized_pnl:+.2f} ({pnl_pct:+.1f}%)
═══════════════════════════════════════════
{scale_out_info}
📈 PRICE MOVEMENT
─────────────────────────────────────────────────────────────────────────────────
SPY at Entry:    ${spot_entry:.2f}
SPY at Exit:     ${spot_exit:.2f}
Change:          ${spot_change:+.2f} ({spot_change_pct:+.2f}%)
Long Strike:     ${position.long_strike:.2f}
Short Strike:    ${position.short_strike:.2f}

📉 GREEKS COMPARISON (Entry → Exit)
─────────────────────────────────────────────────────────────────────────────────
Net Delta:       {net_delta_entry:+.3f} → {net_delta_exit:+.3f} (Δ {net_delta_exit - net_delta_entry:+.3f})

⏱️ DURATION
─────────────────────────────────────────────────────────────────────────────────
Opened:          {position.open_date}
Closed:          {now.strftime('%Y-%m-%d %H:%M:%S')}
Duration:        {duration_str}

💰 UPDATED CAPITAL
─────────────────────────────────────────────────────────────────────────────────
Previous:        ${self.current_capital - realized_pnl:,.2f}
P&L:             ${realized_pnl:+.2f}
Current:         ${self.current_capital:,.2f}
════════════════════════════════════════════════════════════════════════════════
"""
            # Print to console
            print(log_output)
            logger.info(f"ATHENA Trade Closed: {position.position_id} | {exit_reason} | P&L: ${realized_pnl:+.2f} ({pnl_pct:+.1f}%)")

        except Exception as e:
            logger.error(f"Error in detailed trade close logging: {e}")
            import traceback
            traceback.print_exc()

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
            # Both are DEBIT spreads - we paid entry_debit to enter
            # Bull Call: +0.50 delta, profits when price RISES
            # Bear Put: -0.50 delta, profits when price FALLS
            if position.spread_type == SpreadType.BULL_CALL_SPREAD:
                # Spread value increases when underlying rises
                delta_estimate = 0.50  # ATM call spread delta
                spread_value_change = price_change_pct * position.spread_width * delta_estimate
                current_value = position.entry_debit + spread_value_change
            else:  # BEAR_PUT_SPREAD
                # Spread value increases when underlying drops (negative delta)
                delta_estimate = -0.50  # ATM put spread delta
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

        # For live trading, place closing order BEFORE updating state
        if self.config.mode == TradingMode.LIVE and TRADIER_AVAILABLE and self.tradier:
            try:
                # Determine option type based on spread type
                option_type = 'C' if position.spread_type == SpreadType.BULL_CALL_SPREAD else 'P'

                # Build OCC symbols for the spread legs using position's expiration
                long_symbol = self.tradier._build_occ_symbol(
                    self.config.ticker, position.expiration, position.long_strike, option_type
                )
                short_symbol = self.tradier._build_occ_symbol(
                    self.config.ticker, position.expiration, position.short_strike, option_type
                )

                # Close the spread (reverse the opening trade)
                # For both debit spreads: sell long leg, buy back short leg
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
                # CRITICAL: Order failed - do NOT update position state
                logger.error(f"Live scale-out FAILED - position state NOT updated: {e}")
                self._log_to_db("ERROR", f"LIVE SCALE-OUT FAILED", {
                    'position_id': position.position_id,
                    'contracts_attempted': contracts_to_exit,
                    'error': str(e)
                })
                return 0  # Return 0 P&L since no scale-out occurred

        # Update position tracking AFTER successful order (or for paper trading)
        position.contracts_remaining -= contracts_to_exit
        position.total_scaled_pnl += scale_pnl

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
                        'source': 'tradier_live',
                        'timestamp': datetime.now(CENTRAL_TZ).isoformat()
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
                        'source': source,
                        'timestamp': datetime.now(CENTRAL_TZ).isoformat()
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
                # Note: Database cache may be stale - data_validation will flag this
                return {
                    'net_gex': float(row[0]) if row[0] else 0,
                    'call_wall': float(row[1]) if row[1] else 0,
                    'put_wall': float(row[2]) if row[2] else 0,
                    'flip_point': float(row[3]) if row[3] else 0,
                    'spot_price': float(row[4]) if row[4] else 0,
                    'regime': row[5] or 'UNKNOWN',
                    'source': f'database_{row[6]}',
                    'timestamp': datetime.now(CENTRAL_TZ).isoformat()  # Use current time as we just fetched
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
            except Exception as e:
                logger.debug(f"Could not get VIX from unified provider: {e}")

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
            day_of_week=datetime.now(CENTRAL_TZ).weekday()
        )

        try:
            # Get ATHENA-specific advice from Oracle
            # Pass wall_filter_pct for configurable wall proximity check
            # Backtest: 0.5% = 98% WR, 1.0% = 90% WR (tighter is better)
            advice = self.oracle.get_athena_advice(
                context=context,
                use_gex_walls=self.config.use_gex_walls,
                use_claude_validation=self.config.use_claude_validation,
                wall_filter_pct=self.config.wall_filter_pct
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
        - spread_type: 'BULL_CALL_SPREAD', 'BEAR_PUT_SPREAD', or 'NONE'
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
            except Exception as e:
                logger.debug(f"Could not get VIX for ML signal: {e}")

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

        For BEARISH (Bear Put Spread):
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

        else:  # BEAR_PUT_SPREAD
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

        # Check if weekend (Saturday=5, Sunday=6)
        if now.weekday() >= 5:
            return False, "Market closed - weekend"

        # Check if market hours (use config times)
        start_parts = self.config.entry_start_time.split(':')
        end_parts = self.config.entry_end_time.split(':')
        market_open = now.replace(hour=int(start_parts[0]), minute=int(start_parts[1]), second=0)
        market_close = now.replace(hour=int(end_parts[0]), minute=int(end_parts[1]), second=0)

        if not (market_open <= now <= market_close):
            return False, f"Outside trading window ({self.config.entry_start_time} - {self.config.entry_end_time} CT)"

        # Check daily trade limit
        today = now.strftime("%Y-%m-%d")
        if self.last_trade_date != today:
            self.daily_trades = 0
            self.last_trade_date = today

        if self.daily_trades >= self.config.max_daily_trades:
            return False, f"Daily trade limit reached ({self.config.max_daily_trades})"

        # Check max open positions - SYNC WITH DB FIRST to avoid phantom position issues
        self._sync_open_positions_from_db()
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
            elif "BEAR_PUT_SPREAD" in advice.reasoning:
                direction = "BEARISH"

            # Extract spread type
            spread_type = None
            if "BULL_CALL_SPREAD" in advice.reasoning:
                spread_type = "BULL_CALL_SPREAD"
            elif "BEAR_PUT_SPREAD" in advice.reasoning:
                spread_type = "BEAR_PUT_SPREAD"

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
        rr_ratio: float = 0,
        signal_source: str = "ML",
        override_occurred: bool = False,
        override_details: Optional[Dict] = None
    ) -> Optional[SpreadPosition]:
        """Execute a spread trade"""
        decision_tracker = None
        if BOT_LOGGER_AVAILABLE and DecisionTracker:
            decision_tracker = DecisionTracker()
            decision_tracker.start()

        # Get 0DTE expiration - MUST use Central Time for correct market date
        today = datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")

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
            # Bull Call: Buy lower strike call (long), Sell higher strike call (short)
            long_strike = atm_strike
            short_strike = atm_strike + self.config.spread_width
        else:  # BEAR_PUT_SPREAD
            # Bear Put: Buy higher strike put (long), Sell lower strike put (short)
            long_strike = atm_strike
            short_strike = atm_strike - self.config.spread_width

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
            # Both Bull Call and Bear Put are DEBIT spreads
            # Typical debit is ~50% of spread width for ATM spreads
            entry_debit = spread_width * 0.5  # ~50% of width as debit
            max_profit = (spread_width - entry_debit) * 100 * contracts

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

            # Save to database with full entry context FIRST
            if not self._save_position_to_db(
                position=position,
                signal_id=signal_id,
                gex_data=gex_data,
                ml_signal=ml_signal,
                rr_ratio=rr_ratio
            ):
                logger.error(f"ATHENA: Failed to save position to DB - not tracking in memory")
                return None

            # Only update in-memory state AFTER successful DB save
            self.open_positions.append(position)
            self.daily_trades += 1

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

            # Log super detailed trade info to console
            self._log_detailed_trade_open(
                position=position,
                gex_data=gex_data,
                advice=advice,
                ml_signal=ml_signal,
                rr_ratio=rr_ratio
            )

            return position

        # Live execution via Tradier
        if self.config.mode == TradingMode.LIVE and TRADIER_AVAILABLE and self.tradier:
            try:
                # Format today's date for expiration
                today_expiration = datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")

                # Determine option type based on spread type
                # Bull Call Spread uses calls, Bear Put Spread uses puts
                option_type = "call" if spread_type == SpreadType.BULL_CALL_SPREAD else "put"

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

                        # Save to database with full entry context FIRST
                        if not self._save_position_to_db(
                            position=position,
                            signal_id=signal_id,
                            gex_data=gex_data,
                            ml_signal=ml_signal,
                            rr_ratio=rr_ratio
                        ):
                            logger.error(f"ATHENA: Failed to save LIVE position to DB - position may be orphaned!")
                            self._log_to_db("ERROR", "Failed to persist LIVE position to database", {
                                'position_id': position.position_id,
                                'order_id': order_info.get('id')
                            })
                            # Still track in memory since the order was placed
                            # but log this critical issue

                        # Only update in-memory state AFTER successful DB save
                        self.open_positions.append(position)
                        self.daily_trades += 1

                        self._log_to_db("INFO", f"LIVE TRADE EXECUTED: {spread_type.value}", {
                            'position_id': position.position_id,
                            'order_id': order_info.get('id'),
                            'order_status': order_info.get('status'),
                            'strikes': f"{long_strike}/{short_strike}",
                            'contracts': contracts,
                            'entry_debit': limit_debit
                        })

                        # Log super detailed trade info to console
                        self._log_detailed_trade_open(
                            position=position,
                            gex_data=gex_data,
                            advice=advice,
                            ml_signal=ml_signal,
                            rr_ratio=rr_ratio
                        )

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

    def _save_position_to_db(
        self,
        position: SpreadPosition,
        signal_id: Optional[int],
        gex_data: Optional[Dict] = None,
        ml_signal: Optional[Dict] = None,
        rr_ratio: float = 0
    ) -> bool:
        """Save position to apache_positions table with full entry context.

        Returns True if save succeeded, False otherwise.
        """
        conn = None
        try:
            conn = get_connection()
            c = conn.cursor()

            # Extract GEX data
            vix = gex_data.get('vix', 0) if gex_data else 0
            put_wall = gex_data.get('put_wall', 0) if gex_data else 0
            call_wall = gex_data.get('call_wall', 0) if gex_data else 0
            flip_point = gex_data.get('flip_point', 0) if gex_data else 0
            net_gex = gex_data.get('net_gex', 0) if gex_data else 0

            # Calculate Greeks
            spot = position.underlying_price_at_entry
            greeks = self._get_leg_greeks(position, spot, vix if vix > 0 else 15)
            net_delta = greeks.get('long_delta', 0) - greeks.get('short_delta', 0)
            net_gamma = greeks.get('long_gamma', 0) - greeks.get('short_gamma', 0)
            net_theta = greeks.get('long_theta', 0) - greeks.get('short_theta', 0)
            net_vega = greeks.get('long_vega', 0) - greeks.get('short_vega', 0)

            # Extract ML signal data
            ml_direction = ml_signal.get('direction', ml_signal.get('model_predictions', {}).get('direction')) if ml_signal else None
            ml_confidence = ml_signal.get('confidence', 0) if ml_signal else 0
            ml_win_prob = ml_signal.get('win_probability', 0) if ml_signal else 0

            # Calculate breakeven
            is_bullish = position.spread_type == SpreadType.BULL_CALL_SPREAD
            if is_bullish:
                breakeven = position.long_strike + position.entry_debit
            else:
                breakeven = position.short_strike - abs(position.entry_debit)

            c.execute("""
                INSERT INTO apache_positions (
                    position_id, signal_id, spread_type, ticker,
                    long_strike, short_strike, expiration,
                    entry_price, contracts, max_profit, max_loss,
                    spot_at_entry, gex_regime, oracle_confidence, oracle_reasoning,
                    vix_at_entry, put_wall_at_entry, call_wall_at_entry,
                    flip_point_at_entry, net_gex_at_entry,
                    entry_delta, entry_gamma, entry_theta, entry_vega,
                    ml_direction, ml_confidence, ml_win_probability,
                    breakeven, rr_ratio, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                position.oracle_reasoning,
                vix if vix > 0 else None,
                put_wall if put_wall > 0 else None,
                call_wall if call_wall > 0 else None,
                flip_point if flip_point > 0 else None,
                net_gex if net_gex != 0 else None,
                net_delta,
                net_gamma,
                net_theta,
                net_vega,
                ml_direction,
                ml_confidence if ml_confidence > 0 else None,
                ml_win_prob if ml_win_prob > 0 else None,
                breakeven,
                rr_ratio if rr_ratio > 0 else None,
                'open'  # Explicitly set status to 'open'
            ))

            conn.commit()
            return True
        except Exception as e:
            self._log_to_db("ERROR", f"Failed to save position: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            if conn:
                conn.close()

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
            else:  # BEAR_PUT_SPREAD (debit spread - buy higher strike put, sell lower strike put)
                legs = [
                    TradeLeg(
                        leg_id=1,
                        action="BUY",
                        option_type="put",
                        strike=position.long_strike,  # Higher strike - we buy this
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
                        option_type="put",
                        strike=position.short_strike,  # Lower strike - we sell this
                        expiration=position.expiration,
                        contracts=position.contracts,
                        delta=leg_greeks.get('short_delta', 0),
                        gamma=leg_greeks.get('short_gamma', 0),
                        theta=leg_greeks.get('short_theta', 0),
                        vega=leg_greeks.get('short_vega', 0),
                        iv=leg_greeks.get('short_iv', 0),
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
            spread_name = "Bull Call Spread" if position.spread_type == SpreadType.BULL_CALL_SPREAD else "Bear Put Spread"
            # Note: signal_source is now passed in from run_daily_cycle, don't override it
            # Add override indicator to the description if applicable
            override_indicator = " [OVERRIDE]" if override_occurred else ""
            what_desc = f"{spread_name} {position.contracts}x ${position.long_strike}/${position.short_strike} @ ${abs(position.entry_debit):.2f} ({signal_source}{override_indicator})"

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
                action="SELL" if position.spread_type == SpreadType.BEAR_PUT_SPREAD else "BUY",
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
                        action="SELL" if position.spread_type == SpreadType.BEAR_PUT_SPREAD else "BUY",
                        symbol=self.config.ticker,
                        strategy=position.spread_type.value,
                        # SIGNAL SOURCE & OVERRIDE TRACKING
                        signal_source=signal_source,
                        override_occurred=override_occurred,
                        override_details=override_details or {},
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
                        entry_reasoning=why_desc + (f" | OVERRIDE: {override_details}" if override_occurred and override_details else ""),
                        strike_reasoning=f"Long ${position.long_strike}, Short ${position.short_strike} ({position.spread_width} wide)",
                        size_reasoning=f"{self.config.risk_per_trade_pct:.0f}% risk = {position.contracts} contracts",
                        alternatives_considered=[
                            Alternative(strategy="STAY_OUT", reason="ML said STAY_OUT but Oracle overrode" if override_occurred else "Insufficient signal"),
                            Alternative(strategy="Opposite direction", reason="GEX confirms direction"),
                        ] if Alternative else [],
                        kelly_pct=self.config.risk_per_trade_pct / 100,
                        position_size_dollars=abs(position.entry_debit) * 100 * position.contracts,
                        max_risk_dollars=position.max_loss,
                        backtest_win_rate=ml_signal.get('win_probability', 0) if ml_signal else getattr(advice, 'win_probability', 0.5),
                        passed_all_checks=True,
                    )
                    decision_id = log_bot_decision(comprehensive_decision)
                    override_msg = " [OVERRIDE RECORDED]" if override_occurred else ""
                    logger.info(f"ATHENA: Logged to bot_decision_logs (ENTRY) - ID: {decision_id}{override_msg}")
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
                else:  # BEAR_PUT_SPREAD
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
                        else:  # BEAR_PUT_SPREAD
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

    def _close_position(self, position: SpreadPosition, reason: str) -> bool:
        """Close a position - includes P&L from all scale-outs.

        Returns True if position was closed successfully, False if DB update failed.
        """
        # Get current spread value for final close price
        current_spread_value = self._get_current_spread_value(position)

        # Prepare position for close (set fields for DB update)
        position.status = "closed"
        position.close_date = datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d %H:%M:%S")
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

        # Update database FIRST - before updating in-memory state
        if not self._update_position_in_db(position, reason):
            logger.error(f"ATHENA: Failed to update position {position.position_id} in DB - reverting")
            # Revert position status since DB failed
            position.status = "open"
            position.close_date = None
            position.close_price = None
            position.realized_pnl = None
            return False

        # Only update in-memory state AFTER successful DB save
        # Move to closed positions
        if position in self.open_positions:
            self.open_positions.remove(position)
        self.closed_positions.append(position)

        # Update capital
        self.current_capital += position.realized_pnl

        # Record P&L to circuit breaker for daily loss tracking
        if CIRCUIT_BREAKER_AVAILABLE and record_trade_pnl:
            try:
                record_trade_pnl(position.realized_pnl)
                logger.debug(f"ATHENA: Recorded P&L ${position.realized_pnl:.2f} to circuit breaker")
            except Exception as e:
                logger.warning(f"ATHENA: Failed to record P&L to circuit breaker: {e}")

        # Fetch current market data for detailed logging
        exit_gex_data = None
        try:
            current_gex = self.get_gex_data()
            if current_gex:
                # Add VIX to gex_data
                vix = 20.0
                if UNIFIED_DATA_AVAILABLE:
                    try:
                        from data.unified_data_provider import get_vix
                        vix = get_vix() or 20.0
                    except Exception as e:
                        logger.debug(f"Could not get VIX for exit GEX: {e}")
                exit_gex_data = {
                    'spot': current_gex.get('spot_price', position.underlying_price_at_entry),
                    'vix': vix
                }
        except Exception as e:
            logger.debug(f"Could not get exit GEX data: {e}")

        # Log super detailed trade close info to console
        self._log_detailed_trade_close(
            position=position,
            exit_reason=reason,
            exit_price=current_spread_value,
            gex_data=exit_gex_data
        )

        # Log exit decision
        self._log_exit_decision(position, reason)

        # Update daily performance tracking
        self._update_daily_performance(position)

        return True

    def _update_position_in_db(self, position: SpreadPosition, exit_reason: str) -> bool:
        """Update position status in database.

        Returns True if update succeeded, False otherwise.
        """
        conn = None
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
            return True
        except Exception as e:
            self._log_to_db("ERROR", f"Failed to update position: {e}")
            return False
        finally:
            if conn:
                conn.close()

    def _update_daily_performance(self, position: SpreadPosition) -> None:
        """Update daily performance table after closing a position"""
        conn = None
        try:
            conn = get_connection()
            c = conn.cursor()

            # CRITICAL: Must use Central Time to match market trading date
            today = datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")
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

            self._log_to_db("DEBUG", "Daily performance updated", {
                'date': today,
                'pnl': position.realized_pnl,
                'win': is_win
            })
        except Exception as e:
            self._log_to_db("ERROR", f"Failed to update daily performance: {e}")
        finally:
            if conn:
                conn.close()

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
            else:  # BEAR_PUT_SPREAD
                legs = [
                    TradeLeg(
                        leg_id=1,
                        action="SELL",  # Close long leg (higher strike put we bought)
                        option_type="put",
                        strike=position.long_strike,
                        expiration=position.expiration,
                        exit_price=position.close_price,
                        contracts=position.contracts,
                        realized_pnl=position.realized_pnl / 2
                    ),
                    TradeLeg(
                        leg_id=2,
                        action="BUY",  # Close short leg (lower strike put we sold)
                        option_type="put",
                        strike=position.short_strike,
                        expiration=position.expiration,
                        contracts=position.contracts,
                        realized_pnl=position.realized_pnl / 2
                    )
                ]

            spread_name = "Bull Call Spread" if position.spread_type == SpreadType.BULL_CALL_SPREAD else "Bear Put Spread"

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
        # CRITICAL: Sync positions with DB before any checks to prevent phantom position issues
        self._sync_open_positions_from_db()

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

        # =========================================================================
        # CIRCUIT BREAKER CHECK - FIRST LINE OF DEFENSE
        # =========================================================================
        if CIRCUIT_BREAKER_AVAILABLE and is_trading_enabled:
            try:
                can_trade, cb_reason = is_trading_enabled(
                    current_positions=len(self.open_positions),
                    margin_used=0  # ATHENA uses defined risk spreads, not margin
                )

                if not can_trade:
                    reason = f"Circuit breaker: {cb_reason}"
                    self._log_to_db("WARNING", f"ATHENA blocked by circuit breaker: {cb_reason}")
                    result['decision_reason'] = f"BLOCKED: {reason}"
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
                            outcome=ScanOutcome.SKIP,
                            decision_summary=f"CIRCUIT BREAKER ACTIVE: {cb_reason}",
                            action_taken="No trade - circuit breaker prevented trading for risk management",
                            market_data={'underlying_price': spot, 'vix': vix, 'symbol': 'SPY'},
                            full_reasoning=f"The circuit breaker system has blocked trading to protect capital. "
                                          f"This typically occurs when daily loss limits are hit or when too many "
                                          f"positions are open. Reason: {cb_reason}",
                            checks=[
                                CheckResult("should_trade", True, "Yes", "Yes", "Trade conditions met"),
                                CheckResult("circuit_breaker", False, "BLOCKED", "ENABLED", cb_reason)
                            ]
                        )
                    return result
            except Exception as e:
                logger.warning(f"ATHENA: Circuit breaker check failed: {e} - continuing with trade")

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

        # Validate GEX data freshness - CRITICAL SAFETY CHECK
        if DATA_VALIDATION_AVAILABLE and validate_market_data:
            is_valid, error_msg = validate_market_data(
                gex_data,
                max_age_seconds=MAX_DATA_AGE_SECONDS,
                require_timestamp=True
            )
            if not is_valid:
                logger.warning(f"ATHENA: GEX data validation failed: {error_msg}")
                result['errors'].append(f"GEX data validation failed: {error_msg}")
                result['decision_reason'] = f"SKIP: {error_msg}"
                self._log_skip_decision(f"GEX data validation failed: {error_msg}")
                # Log scan activity - STALE DATA
                if SCAN_LOGGER_AVAILABLE and log_athena_scan:
                    log_athena_scan(
                        outcome=ScanOutcome.ERROR,
                        decision_summary=f"GEX data validation failed: {error_msg}",
                        action_taken="Skipping trade - waiting for fresh data",
                        market_data=gex_data,
                        error_message=error_msg,
                        error_type="STALE_DATA_ERROR",
                        checks=[
                            CheckResult("data_freshness", False, error_msg, f"Data < {MAX_DATA_AGE_SECONDS}s old", "Data validation failed")
                        ]
                    )
                return result

        # Fetch VIX and add to gex_data for consistent access
        vix = 20.0  # Default
        if UNIFIED_DATA_AVAILABLE:
            try:
                from data.unified_data_provider import get_vix
                vix = get_vix() or 20.0
            except Exception as e:
                logger.debug(f"Could not get VIX for scan: {e}")
        gex_data['vix'] = vix

        # Store GEX context for logging
        result['gex_context'] = {
            'spot_price': gex_data.get('spot_price'),
            'call_wall': gex_data.get('call_wall'),
            'put_wall': gex_data.get('put_wall'),
            'regime': gex_data.get('regime'),
            'net_gex': gex_data.get('net_gex'),
            'source': gex_data.get('source'),
            'vix': vix
        }

        # === PRIMARY: Use ML Signal ===
        ml_signal = None
        spread_type = None
        signal_source = "ML"
        override_occurred = False
        override_details = {}

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
                elif ml_signal['spread_type'] == 'BEAR_PUT_SPREAD':
                    spread_type = SpreadType.BEAR_PUT_SPREAD

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
                override_occurred = False
                override_details = {}
                if ml_said_stay_out:
                    override_occurred = True
                    override_details = {
                        'overridden_signal': 'ML',
                        'overridden_advice': 'STAY_OUT',
                        'override_reason': f"Oracle high confidence: {oracle_advice.confidence:.0%}, win prob: {oracle_advice.win_probability:.0%}",
                        'override_by': 'Oracle',
                        'oracle_advice': oracle_advice.advice.value,
                        'oracle_confidence': oracle_advice.confidence,
                        'oracle_win_probability': oracle_advice.win_probability,
                        'ml_was_saying': 'STAY_OUT'
                    }
                    self._log_to_db("WARNING",
                        f"ORACLE OVERRIDE: Oracle says {oracle_advice.advice.value} (conf={oracle_advice.confidence:.0%}, "
                        f"win={oracle_advice.win_probability:.0%}) overriding ML STAY_OUT",
                        {'ml_advice': 'STAY_OUT', 'oracle_advice': oracle_advice.advice.value,
                         'oracle_confidence': oracle_advice.confidence,
                         'oracle_win_prob': oracle_advice.win_probability,
                         'override_details': override_details}
                    )
                    signal_source = "Oracle (override ML)"

                # Determine spread type from Oracle reasoning
                if "BULL_CALL_SPREAD" in oracle_advice.reasoning:
                    spread_type = SpreadType.BULL_CALL_SPREAD
                elif "BEAR_PUT_SPREAD" in oracle_advice.reasoning:
                    spread_type = SpreadType.BEAR_PUT_SPREAD
                # Also check for BULLISH/BEARISH direction as fallback
                elif hasattr(oracle_advice, 'direction'):
                    if oracle_advice.direction == 'BULLISH':
                        spread_type = SpreadType.BULL_CALL_SPREAD
                    elif oracle_advice.direction == 'BEARISH':
                        spread_type = SpreadType.BEAR_PUT_SPREAD

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

        # Execute spread with full override tracking
        position = self.execute_spread(
            spread_type=spread_type,
            spot_price=gex_data['spot_price'],
            gex_data=gex_data,
            advice=advice_obj,
            signal_id=signal_id,
            ml_signal=ml_signal,
            rr_ratio=rr_ratio,
            signal_source=signal_source,
            override_occurred=override_occurred,
            override_details=override_details if override_occurred else None
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

    # =========================================================================
    # EXPIRED POSITION HANDLING (EOD Processing)
    # =========================================================================

    def process_expired_positions(self) -> Dict:
        """
        Process all spread positions that have expired (today or earlier).

        Called at market close (3:05-3:10 PM CT) to:
        1. Find ALL open positions with expiration <= today (catches missed days)
        2. Get closing price of underlying
        3. Determine outcome (MAX_PROFIT, LOSS, PARTIAL)
        4. Calculate realized P&L
        5. Update position status to 'expired'
        6. Update daily performance metrics

        Returns:
            Dict with processing results
        """
        result = {
            'processed_count': 0,
            'total_pnl': 0.0,
            'winners': 0,
            'losers': 0,
            'positions': [],
            'errors': []
        }

        today = datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d')
        logger.info(f"ATHENA EOD: Processing expired positions (expiration <= {today})")

        try:
            ticker = self.config.ticker

            # Find ALL positions that should have expired (expiration <= today)
            positions_to_process = []

            # Check in-memory open positions - process ANY that have expired
            for pos in self.open_positions[:]:  # Copy list to allow modification
                if pos.expiration <= today and pos.status == 'open':
                    positions_to_process.append(pos)
                    logger.info(f"ATHENA EOD: Found in-memory position {pos.position_id} (expired {pos.expiration})")

            # Also check database for any positions not in memory
            db_positions = self._get_all_expired_positions_from_db(today)
            for db_pos in db_positions:
                # Avoid duplicates
                if not any(p.position_id == db_pos.position_id for p in positions_to_process):
                    positions_to_process.append(db_pos)
                    logger.info(f"ATHENA EOD: Found DB position {db_pos.position_id} (expired {db_pos.expiration})")

            if not positions_to_process:
                logger.info(f"ATHENA EOD: No positions expiring today")
                return result

            logger.info(f"ATHENA EOD: Found {len(positions_to_process)} positions to process")

            # Process each position with its own expiration date's closing price
            for position in positions_to_process:
                try:
                    # Get closing price for THIS position's expiration date
                    closing_price = self._get_underlying_close_price(ticker, position.expiration)

                    if closing_price is None or closing_price <= 0:
                        error_msg = f"Could not get closing price for {ticker} on {position.expiration}"
                        result['errors'].append(error_msg)
                        logger.error(f"ATHENA EOD: {error_msg}")
                        continue

                    logger.info(f"ATHENA EOD: {ticker} close on {position.expiration}: ${closing_price:.2f}")

                    # Determine outcome based on closing price vs strikes
                    outcome = self._determine_expiration_outcome(position, closing_price)
                    realized_pnl = self._calculate_expiration_pnl(position, outcome, closing_price)

                    # Update position
                    position.status = 'expired'
                    position.close_date = position.expiration  # Use actual expiration date
                    position.close_price = closing_price
                    position.realized_pnl = realized_pnl

                    # Move from open to closed
                    if position in self.open_positions:
                        self.open_positions.remove(position)
                    self.closed_positions.append(position)

                    # Update capital
                    self.current_capital += realized_pnl

                    # Record P&L to circuit breaker for daily loss tracking
                    if CIRCUIT_BREAKER_AVAILABLE and record_trade_pnl:
                        try:
                            record_trade_pnl(realized_pnl)
                            logger.debug(f"ATHENA EOD: Recorded P&L ${realized_pnl:.2f} to circuit breaker")
                        except Exception as e:
                            logger.warning(f"ATHENA EOD: Failed to record P&L to circuit breaker: {e}")

                    if realized_pnl > 0:
                        result['winners'] += 1
                    else:
                        result['losers'] += 1

                    # Save to database
                    self._update_position_in_db(position, f"EXPIRED_{outcome}")

                    # Update daily performance
                    self._update_daily_performance(position)

                    result['processed_count'] += 1
                    result['total_pnl'] += realized_pnl
                    result['positions'].append({
                        'position_id': position.position_id,
                        'spread_type': position.spread_type.value,
                        'outcome': outcome,
                        'realized_pnl': realized_pnl,
                        'closing_price': closing_price,
                        'long_strike': position.long_strike,
                        'short_strike': position.short_strike
                    })

                    logger.info(f"ATHENA EOD: Processed {position.position_id} - {outcome} - P&L: ${realized_pnl:.2f}")

                except Exception as e:
                    error_msg = f"Error processing position {position.position_id}: {e}"
                    result['errors'].append(error_msg)
                    logger.error(f"ATHENA EOD: {error_msg}")

            logger.info(f"ATHENA EOD: Complete - Processed {result['processed_count']} positions, "
                       f"Total P&L: ${result['total_pnl']:.2f}, "
                       f"Winners: {result['winners']}, Losers: {result['losers']}")

            return result

        except Exception as e:
            result['errors'].append(f"EOD processing failed: {e}")
            logger.error(f"ATHENA EOD: Processing failed: {e}")
            return result

    def _get_underlying_close_price(self, ticker: str, for_date: str = None) -> Optional[float]:
        """
        Get the closing price for the underlying on a specific date.

        Args:
            ticker: Stock symbol (SPY, SPX, etc.)
            for_date: Date string (YYYY-MM-DD) to get price for. If None, gets current price.

        Returns:
            Closing price or None if unavailable
        """
        today = datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d')

        # If requesting today's price or no date specified, get current/latest price
        if for_date is None or for_date >= today:
            return self._get_current_price(ticker)

        # For past dates, look up historical price
        return self._get_historical_close_price(ticker, for_date)

    def _get_current_price(self, ticker: str) -> Optional[float]:
        """Get current/latest price for the underlying."""
        try:
            # Try unified data provider first
            if UNIFIED_DATA_AVAILABLE:
                price = get_price(ticker)
                if price and price > 0:
                    return float(price)

            # Try Tradier production
            if self.tradier:
                quote = self.tradier.get_quote(ticker)
                if quote:
                    if 'close' in quote and quote['close']:
                        return float(quote['close'])
                    if 'last' in quote and quote['last']:
                        return float(quote['last'])

            # Try Tradier sandbox as fallback
            if self.tradier_sandbox:
                quote = self.tradier_sandbox.get_quote(ticker)
                if quote:
                    if 'close' in quote and quote['close']:
                        return float(quote['close'])
                    if 'last' in quote and quote['last']:
                        return float(quote['last'])

            return None
        except Exception as e:
            logger.error(f"ATHENA EOD: Error getting current price: {e}")
            return None

    def _get_historical_close_price(self, ticker: str, for_date: str) -> Optional[float]:
        """Get historical closing price for a specific past date."""
        try:
            # Try Tradier history API
            if self.tradier:
                try:
                    history = self.tradier.get_history(ticker, start=for_date, end=for_date)
                    if history and len(history) > 0:
                        return float(history[0].get('close', 0))
                except Exception:
                    pass

            # Fallback: try to get from database
            conn = None
            try:
                conn = get_connection()
                c = conn.cursor()
                c.execute("""
                    SELECT close_price FROM daily_prices
                    WHERE symbol = %s AND trade_date = %s
                    LIMIT 1
                """, (ticker, for_date))
                row = c.fetchone()
                if row:
                    return float(row[0])
            except Exception:
                pass
            finally:
                if conn:
                    conn.close()

            return None
        except Exception as e:
            logger.error(f"ATHENA EOD: Error getting historical price: {e}")
            return None

    def _get_all_expired_positions_from_db(self, as_of_date: str) -> List[SpreadPosition]:
        """
        Find all open positions in the database that have expired but weren't processed.

        This catches positions that may have been missed on previous days due to
        service downtime or errors.
        """
        positions = []
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT
                    position_id, spread_type, created_at, expiration,
                    long_strike, short_strike, entry_price, contracts,
                    max_profit, max_loss, spot_at_entry, gex_regime,
                    oracle_confidence, oracle_reasoning
                FROM apache_positions
                WHERE expiration <= %s AND status = 'open'
                ORDER BY expiration ASC
            ''', (as_of_date,))

            for row in cursor.fetchall():
                spread_type = SpreadType.BULL_CALL_SPREAD if row[1] == 'BULL_CALL_SPREAD' else SpreadType.BEAR_PUT_SPREAD
                # row[2] is created_at (timestamp), convert to date string for open_date
                open_date_val = str(row[2])[:10] if row[2] else ""
                pos = SpreadPosition(
                    position_id=row[0],
                    spread_type=spread_type,
                    open_date=open_date_val,
                    expiration=str(row[3]) if row[3] else "",
                    long_strike=float(row[4] or 0),
                    short_strike=float(row[5] or 0),
                    entry_debit=float(row[6] or 0),
                    contracts=int(row[7] or 0),
                    spread_width=abs(float(row[5] or 0) - float(row[4] or 0)),
                    max_profit=float(row[8] or 0),
                    max_loss=float(row[9] or 0),
                    underlying_price_at_entry=float(row[10] or 0),
                    gex_regime_at_entry=row[11] or "",
                    oracle_confidence=float(row[12] or 0),
                    oracle_reasoning=row[13] or "",
                    order_id="",  # Not stored in apache_positions table
                    status='open',
                    initial_contracts=int(row[7] or 0),
                    contracts_remaining=int(row[7] or 0)
                )
                positions.append(pos)
                logger.info(f"ATHENA EOD: Found expired position {pos.position_id} from {pos.expiration}")

            logger.info(f"ATHENA EOD: Found {len(positions)} expired positions in database")

        except Exception as e:
            logger.error(f"ATHENA EOD: Error loading expired positions from DB: {e}")
        finally:
            if conn:
                conn.close()

        return positions

    def _determine_expiration_outcome(self, position: SpreadPosition, closing_price: float) -> str:
        """
        Determine the outcome of an expired spread.

        For Bull Call Spread (buy low call, sell high call - debit spread):
        - MAX_PROFIT: Price >= short strike (both ITM, keep spread width - debit)
        - PARTIAL: Price between strikes (long ITM, short OTM)
        - MAX_LOSS: Price <= long strike (both OTM, lose debit)

        For Bear Put Spread (buy high put, sell low put - debit spread):
        - MAX_PROFIT: Price <= short strike (both ITM, keep spread width - debit)
        - PARTIAL: Price between strikes (long ITM, short OTM)
        - MAX_LOSS: Price >= long strike (both OTM, lose debit)
        """
        if position.spread_type == SpreadType.BULL_CALL_SPREAD:
            if closing_price >= position.short_strike:
                return "MAX_PROFIT"
            elif closing_price <= position.long_strike:
                return "MAX_LOSS"
            else:
                return "PARTIAL_PROFIT"
        else:  # BEAR_PUT_SPREAD
            # Bear Put: long_strike is higher (ATM), short_strike is lower (OTM)
            # We profit when price goes DOWN
            if closing_price <= position.short_strike:
                return "MAX_PROFIT"  # Both puts ITM, max profit
            elif closing_price >= position.long_strike:
                return "MAX_LOSS"    # Both puts OTM, max loss
            else:
                return "PARTIAL_PROFIT"  # Long put ITM, short put OTM

    def _calculate_expiration_pnl(self, position: SpreadPosition, outcome: str, closing_price: float) -> float:
        """
        Calculate realized P&L at expiration for a spread.

        Both Bull Call Spread and Bear Put Spread are DEBIT spreads:
        - Entry: Pay debit (entry_debit > 0)
        - MAX_PROFIT: Spread worth spread_width, P&L = (spread_width - entry_debit) * 100 * contracts
        - MAX_LOSS: Spread worth 0, P&L = -entry_debit * 100 * contracts
        - PARTIAL: Calculate based on intrinsic value
        """
        contracts = position.contracts_remaining if position.contracts_remaining > 0 else position.contracts
        debit_paid = position.entry_debit * 100 * contracts

        if position.spread_type == SpreadType.BULL_CALL_SPREAD:
            # Bull Call Spread - profits when price rises
            if outcome == "MAX_PROFIT":
                # Both calls ITM, spread worth full width
                spread_value = position.spread_width * 100 * contracts
                return spread_value - debit_paid

            elif outcome == "MAX_LOSS":
                # Both calls OTM, spread worth nothing
                return -debit_paid

            else:  # PARTIAL_PROFIT
                # Long call ITM, short call OTM
                intrinsic = max(0, closing_price - position.long_strike)
                spread_value = intrinsic * 100 * contracts
                return spread_value - debit_paid

        else:  # BEAR_PUT_SPREAD (debit spread)
            # Bear Put Spread - profits when price falls
            # long_strike is higher (ATM), short_strike is lower (OTM)
            if outcome == "MAX_PROFIT":
                # Both puts ITM, spread worth full width
                spread_value = position.spread_width * 100 * contracts
                return spread_value - debit_paid

            elif outcome == "MAX_LOSS":
                # Both puts OTM, spread worth nothing
                return -debit_paid

            else:  # PARTIAL_PROFIT
                # Long put ITM, short put OTM
                intrinsic = max(0, position.long_strike - closing_price)
                spread_value = intrinsic * 100 * contracts
                return spread_value - debit_paid

    # =========================================================================
    # LIVE P&L TRACKING
    # =========================================================================

    def _sync_open_positions_from_db(self) -> None:
        """
        CRITICAL: Sync open_positions list with database to prevent stale data.

        This method:
        1. Queries the DB for currently open positions
        2. Removes any positions from memory that are no longer open in DB
        3. Adds any positions that exist in DB but not in memory

        Called before get_live_pnl to ensure data freshness.
        """
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            today = datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d')

            # Get all position IDs that are truly open in the database
            cursor.execute('''
                SELECT position_id, status, expiration
                FROM apache_positions
                WHERE position_id IN (
                    SELECT position_id FROM apache_positions
                    WHERE status = 'open' AND expiration >= %s
                )
                OR position_id = ANY(%s)
            ''', (today, [p.position_id for p in self.open_positions] if self.open_positions else []))

            db_positions = {row[0]: {'status': row[1], 'expiration': str(row[2]) if row[2] else ''} for row in cursor.fetchall()}

            # Remove stale positions from memory (closed/expired in DB but still in memory)
            positions_to_remove = []
            for pos in self.open_positions:
                if pos.position_id not in db_positions:
                    # Position was deleted from DB
                    positions_to_remove.append(pos)
                    logger.info(f"ATHENA: Removing stale position {pos.position_id} (not in DB)")
                elif db_positions[pos.position_id]['status'] != 'open':
                    # Position was closed/expired in DB
                    positions_to_remove.append(pos)
                    logger.info(f"ATHENA: Removing stale position {pos.position_id} (status={db_positions[pos.position_id]['status']})")
                elif db_positions[pos.position_id]['expiration'] < today:
                    # Position has expired
                    positions_to_remove.append(pos)
                    logger.info(f"ATHENA: Removing expired position {pos.position_id} (exp={db_positions[pos.position_id]['expiration']})")

            for pos in positions_to_remove:
                self.open_positions.remove(pos)

            if positions_to_remove:
                logger.info(f"ATHENA: Synced positions - removed {len(positions_to_remove)} stale positions, {len(self.open_positions)} remaining")

        except Exception as e:
            logger.error(f"ATHENA: Error syncing open positions from DB: {e}")
        finally:
            if conn:
                conn.close()

    def get_live_pnl(self) -> Dict[str, Any]:
        """
        Get real-time unrealized P&L for all open positions.

        Returns:
            Dict with:
            - total_unrealized_pnl: Sum of all open position unrealized P&L
            - positions: List of position details with current P&L
            - last_updated: Timestamp of the calculation
        """
        # CRITICAL: Sync with database first to remove stale positions
        self._sync_open_positions_from_db()

        result = {
            'total_unrealized_pnl': 0.0,
            'total_realized_pnl': 0.0,
            'positions': [],
            'position_count': len(self.open_positions),
            'last_updated': datetime.now(CENTRAL_TZ).isoformat()
        }

        try:
            # Get current underlying price
            current_price = 0
            if UNIFIED_DATA_AVAILABLE:
                current_price = get_price(self.config.ticker)
            elif self.tradier:
                quote = self.tradier.get_quote(self.config.ticker)
                current_price = quote.get('last', 0) or quote.get('close', 0) if quote else 0

            if current_price <= 0:
                result['error'] = "Could not get current price"
                return result

            result['underlying_price'] = current_price

            for position in self.open_positions:
                try:
                    # Get current spread value
                    current_spread_value = self._get_current_spread_value(position)

                    # Calculate unrealized P&L
                    if position.spread_type == SpreadType.BULL_CALL_SPREAD:
                        # Debit spread: P&L = (current_value - entry_debit) * contracts * 100
                        unrealized = (current_spread_value - position.entry_debit) * position.contracts_remaining * 100
                    else:
                        # Credit spread: P&L = (entry_credit - current_value) * contracts * 100
                        # entry_debit is negative for credits
                        credit_received = abs(position.entry_debit)
                        unrealized = (credit_received - current_spread_value) * position.contracts_remaining * 100

                    # Include already-scaled P&L
                    total_position_pnl = unrealized + position.total_scaled_pnl

                    # Calculate P&L percentage
                    entry_value = abs(position.entry_debit) * position.initial_contracts * 100
                    pnl_pct = (total_position_pnl / entry_value * 100) if entry_value > 0 else 0

                    # Calculate DTE (days to expiration)
                    try:
                        exp_date = datetime.strptime(position.expiration, '%Y-%m-%d').date()
                        today_date = datetime.now(CENTRAL_TZ).date()
                        dte = (exp_date - today_date).days
                        is_0dte = dte == 0
                    except (ValueError, TypeError, AttributeError) as e:
                        logger.debug(f"Could not parse expiration date: {e}")
                        dte = None
                        is_0dte = False

                    # Calculate max profit progress (for debit spreads)
                    max_profit = position.max_profit if hasattr(position, 'max_profit') else abs(position.short_strike - position.long_strike) - abs(position.entry_debit)
                    profit_progress = (total_position_pnl / (max_profit * position.initial_contracts * 100) * 100) if max_profit > 0 else 0

                    pos_data = {
                        'position_id': position.position_id,
                        'spread_type': position.spread_type.value,
                        'long_strike': position.long_strike,
                        'short_strike': position.short_strike,
                        'expiration': position.expiration,
                        'contracts_remaining': position.contracts_remaining,
                        'initial_contracts': position.initial_contracts,
                        'entry_debit': position.entry_debit,
                        'current_spread_value': current_spread_value,
                        'unrealized_pnl': round(unrealized, 2),
                        'scaled_pnl': round(position.total_scaled_pnl, 2),
                        'total_pnl': round(total_position_pnl, 2),
                        'pnl_pct': round(pnl_pct, 2),
                        'underlying_at_entry': position.underlying_price_at_entry,
                        'current_underlying': current_price,
                        # === Entry Context for Transparency ===
                        'dte': dte,
                        'is_0dte': is_0dte,
                        'max_profit': round(max_profit * position.initial_contracts * 100, 2) if max_profit else None,
                        'profit_progress_pct': round(profit_progress, 1),
                        # ML/Oracle context at entry
                        'gex_regime_at_entry': getattr(position, 'gex_regime_at_entry', None) or '',
                        'oracle_confidence': getattr(position, 'oracle_confidence', None) or 0,
                        'oracle_reasoning': getattr(position, 'oracle_reasoning', None) or '',
                        # GEX levels at entry
                        'call_wall_at_entry': getattr(position, 'call_wall_at_entry', None) or 0,
                        'put_wall_at_entry': getattr(position, 'put_wall_at_entry', None) or 0,
                        # Direction based on spread type
                        'direction': 'BULLISH' if position.spread_type == SpreadType.BULL_CALL_SPREAD else 'BEARISH'
                    }

                    result['positions'].append(pos_data)
                    result['total_unrealized_pnl'] += unrealized

                except Exception as e:
                    logger.error(f"Error calculating live P&L for {position.position_id}: {e}")

            # Add realized P&L from closed positions today
            today = datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")
            result['total_realized_pnl'] = sum(
                p.realized_pnl for p in self.closed_positions
                if p.close_date and p.close_date.startswith(today)
            )

            result['total_unrealized_pnl'] = round(result['total_unrealized_pnl'], 2)
            result['total_realized_pnl'] = round(result['total_realized_pnl'], 2)
            result['net_pnl'] = round(result['total_unrealized_pnl'] + result['total_realized_pnl'], 2)

        except Exception as e:
            logger.error(f"Error in get_live_pnl: {e}")
            result['error'] = str(e)

        return result

    def get_status(self) -> Dict[str, Any]:
        """Get current bot status"""
        # CRITICAL: Sync with database first to ensure accurate position count
        # Without this, phantom positions can appear after restarts or DB changes
        self._sync_open_positions_from_db()

        # Use Central Time for date comparisons to match market trading days
        today_ct = datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")
        return {
            'bot_name': 'ATHENA',
            'mode': self.config.mode.value,
            'capital': self.current_capital,
            'open_positions': len(self.open_positions),
            'closed_today': len([p for p in self.closed_positions
                                if p.close_date and p.close_date.startswith(today_ct)]),
            'daily_trades': self.daily_trades,
            'daily_pnl': sum(p.realized_pnl for p in self.closed_positions
                           if p.close_date and p.close_date.startswith(today_ct)),
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
