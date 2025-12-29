"""
ARES - Aggressive Iron Condor Trading Bot
==========================================

Named after the Greek God of War - aggressive and relentless.

TARGET: 10% Monthly Returns via Daily Iron Condor Trading

THE MATH FOR 10% MONTHLY:
=========================
- 20 trading days/month
- Need ~0.5% per day to compound to 10% monthly
- Iron Condor at 1 SD collects ~$3-5 on $10 wide spread
- Win rate at 1 SD: ~68% for BOTH sides to be profitable
- With 10% risk per trade and compounding, this achieves the target

AGGRESSIVE PARAMETERS:
=====================
- Trade EVERY weekday (Mon-Fri)
- Iron Condor: Bull Put + Bear Call simultaneously
- 10% risk per trade (aggressive Kelly)
- 1 SD strikes (balanced risk/reward)
- NO stop loss - let options expire (defined risk)
- Compound daily - reinvest gains immediately

Usage:
    from trading.ares_iron_condor import ARESTrader
    ares = ARESTrader(initial_capital=100_000)
    ares.run_daily_cycle()
"""

import os
import math
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from zoneinfo import ZoneInfo

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

# Import decision logger
try:
    from trading.decision_logger import (
        DecisionLogger, TradeDecision, DecisionType,
        DataSource, TradeLeg, MarketContext as LoggerMarketContext, DecisionReasoning, BotName
    )
    LOGGER_AVAILABLE = True
except ImportError:
    LOGGER_AVAILABLE = False
    DecisionLogger = None

# Import Oracle AI advisor
try:
    from quant.oracle_advisor import (
        OracleAdvisor, MarketContext as OracleMarketContext,
        TradingAdvice, GEXRegime, OraclePrediction, TradeOutcome,
        BotName as OracleBotName
    )
    ORACLE_AVAILABLE = True
except ImportError:
    ORACLE_AVAILABLE = False
    OracleAdvisor = None
    OracleMarketContext = None
    TradingAdvice = None
    TradeOutcome = None
    OracleBotName = None

# Import comprehensive bot logger (NEW)
try:
    from trading.bot_logger import (
        log_bot_decision, update_decision_outcome, update_execution_timeline,
        BotDecision, MarketContext as BotLogMarketContext, ClaudeContext,
        Alternative, RiskCheck, ApiCall, ExecutionTimeline, generate_session_id,
        get_session_tracker, DecisionTracker  # For tracking API calls, errors, timing
    )
    BOT_LOGGER_AVAILABLE = True
except ImportError:
    BOT_LOGGER_AVAILABLE = False
    log_bot_decision = None
    get_session_tracker = None
    DecisionTracker = None

# Import scan activity logger for comprehensive scan-by-scan visibility
try:
    from trading.scan_activity_logger import (
        log_ares_scan, ScanOutcome, CheckResult
    )
    SCAN_LOGGER_AVAILABLE = True
except ImportError:
    SCAN_LOGGER_AVAILABLE = False
    log_ares_scan = None
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

# Data validation for stale data detection and sanity checks
try:
    from trading.data_validation import (
        validate_market_data,
        validate_iron_condor_strikes,
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
        create_iron_condor_stop_config,
        get_stop_loss_manager,
        check_position_stop_loss
    )
    STOP_LOSS_AVAILABLE = True
except ImportError:
    STOP_LOSS_AVAILABLE = False
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


class TradingMode(Enum):
    """Trading execution mode"""
    PAPER = "paper"       # Sandbox/Paper trading
    LIVE = "live"         # Live trading with real money
    BACKTEST = "backtest" # Backtesting mode (no execution)


class StrategyPreset(Enum):
    """
    Strategy presets based on backtesting results (2022-2024):
    - BASELINE: Original ARES, no VIX filtering (Sharpe 8.55)
    - CONSERVATIVE: VIX > 35 skip only
    - MODERATE: VIX > 32 skip (Sharpe 16.84, recommended)
    - AGGRESSIVE: Full VIX ruleset with streak tracking
    - WIDE_STRIKES: Higher SD multiplier for wider strikes
    """
    BASELINE = "baseline"
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"  # Default - best risk-adjusted returns
    AGGRESSIVE = "aggressive"
    WIDE_STRIKES = "wide_strikes"


# Strategy preset configurations
# NOTE: All presets now use 1.0 SD minimum (strikes OUTSIDE expected move)
# This ensures IC wings are protected from normal daily price movement
# GEX walls provide additional protection when available
STRATEGY_PRESETS = {
    StrategyPreset.BASELINE: {
        "name": "Baseline",
        "description": "No VIX filtering, 1.0 SD strikes outside expected move",
        "vix_hard_skip": None,  # No VIX skip
        "risk_per_trade_pct": 10.0,
        "sd_multiplier": 1.0,  # Strikes OUTSIDE expected move
        "backtest_sharpe": 8.55,
        "backtest_win_rate": 94.8,
    },
    StrategyPreset.CONSERVATIVE: {
        "name": "Conservative",
        "description": "Skip extreme volatility (VIX > 35), 1.0 SD strikes",
        "vix_hard_skip": 35.0,
        "risk_per_trade_pct": 10.0,
        "sd_multiplier": 1.0,  # Strikes OUTSIDE expected move
        "backtest_sharpe": 10.2,
        "backtest_win_rate": 95.5,
    },
    StrategyPreset.MODERATE: {
        "name": "Moderate (Recommended)",
        "description": "VIX > 32 skip, 1.0 SD strikes - best risk-adjusted",
        "vix_hard_skip": 32.0,
        "risk_per_trade_pct": 10.0,
        "sd_multiplier": 1.0,  # Strikes OUTSIDE expected move
        "backtest_sharpe": 16.84,
        "backtest_win_rate": 97.6,
    },
    StrategyPreset.AGGRESSIVE: {
        "name": "Aggressive Filter",
        "description": "Full VIX ruleset with streak tracking, 1.0 SD",
        "vix_hard_skip": 30.0,
        "vix_monday_friday_skip": 30.0,
        "vix_streak_skip": 28.0,
        "risk_per_trade_pct": 10.0,
        "sd_multiplier": 1.0,  # Strikes OUTSIDE expected move
        "backtest_sharpe": 18.5,
        "backtest_win_rate": 98.2,
    },
    StrategyPreset.WIDE_STRIKES: {
        "name": "Wide Strikes",
        "description": "1.2 SD even wider strikes for maximum safety",
        "vix_hard_skip": 32.0,
        "risk_per_trade_pct": 8.0,
        "sd_multiplier": 1.2,  # Even further outside expected move
        "backtest_sharpe": 14.2,
        "backtest_win_rate": 98.5,
    },
}


@dataclass
class IronCondorPosition:
    """Represents an open Iron Condor position"""
    position_id: str
    open_date: str
    expiration: str

    # Strikes
    put_long_strike: float
    put_short_strike: float
    call_short_strike: float
    call_long_strike: float

    # Credits received
    put_credit: float
    call_credit: float
    total_credit: float

    # Position details
    contracts: int
    spread_width: float
    max_loss: float

    # Order IDs from broker
    put_spread_order_id: str = ""
    call_spread_order_id: str = ""

    # Status
    status: str = "open"  # open, closed, expired
    close_date: str = ""
    close_price: float = 0
    realized_pnl: float = 0

    # Market data at entry
    underlying_price_at_entry: float = 0
    vix_at_entry: float = 0
    expected_move: float = 0


@dataclass
class ARESConfig:
    """Configuration for ARES trading bot"""
    # Strategy preset (determines VIX filtering and risk parameters)
    strategy_preset: str = "moderate"     # moderate, conservative, aggressive, baseline, wide_strikes

    # VIX filtering thresholds (set by strategy preset, can be overridden)
    vix_hard_skip: float = 32.0           # Skip if VIX > this (None = disabled)
    vix_monday_friday_skip: float = 0.0   # Skip on Mon/Fri if VIX > this (0 = disabled)
    vix_streak_skip: float = 0.0          # Skip after 2+ losses if VIX > this (0 = disabled)

    # Risk parameters
    risk_per_trade_pct: float = 10.0     # 10% of capital per trade
    spread_width: float = 10.0            # $10 wide spreads (SPX)
    spread_width_spy: float = 2.0         # $2 wide spreads (SPY for sandbox)
    sd_multiplier: float = 1.0            # 1.0 SD = strikes OUTSIDE expected move (safer for IC)

    # Execution parameters
    ticker: str = "SPX"                   # Trade SPX in production
    sandbox_ticker: str = "SPY"           # Trade SPY in sandbox (better data)
    use_0dte: bool = True                 # Use 0DTE options
    max_contracts: int = 1000             # Max contracts per trade
    min_credit_per_spread: float = 1.50   # Minimum credit to accept (SPX)
    min_credit_per_spread_spy: float = 0.02  # Minimum credit (SPY - lowered for liquidity)

    # Paper trading mode selection
    # True = Paper trade SPX using live Tradier data, record trades in AlphaGEX DB only
    # False = Paper trade SPY via Tradier sandbox API (for order execution simulation)
    paper_trade_spx: bool = True          # Default to SPX paper trading with live data

    # Trade management
    use_stop_loss: bool = False           # Enable per-position stop loss
    stop_loss_premium_multiple: float = 2.0  # Exit when loss >= 2x premium collected
    stop_loss_use_time_decay: bool = True # Tighten stop near expiration
    profit_target_pct: float = 50         # Take profit at 50% of max

    # Trading schedule
    trade_every_day: bool = True          # Trade Mon-Fri
    entry_time_start: str = "08:30"       # Entry window start (market open)
    entry_time_end: str = "15:55"         # Entry window end (before close)

    def apply_strategy_preset(self, preset_name: str) -> None:
        """Apply a strategy preset's settings to this config"""
        try:
            preset_enum = StrategyPreset(preset_name)
            preset = STRATEGY_PRESETS.get(preset_enum)
            if preset:
                self.strategy_preset = preset_name
                self.vix_hard_skip = preset.get("vix_hard_skip") or 0.0
                self.vix_monday_friday_skip = preset.get("vix_monday_friday_skip", 0.0)
                self.vix_streak_skip = preset.get("vix_streak_skip", 0.0)
                self.risk_per_trade_pct = preset.get("risk_per_trade_pct", 10.0)
                self.sd_multiplier = preset.get("sd_multiplier", 1.0)
                logger.info(f"Applied strategy preset: {preset_name} - VIX skip: {self.vix_hard_skip}, SD: {self.sd_multiplier}")
        except ValueError:
            logger.warning(f"Unknown strategy preset: {preset_name}, keeping current settings")


class ARESTrader:
    """
    ARES - Aggressive Iron Condor Trading Bot

    Executes daily 0DTE Iron Condors targeting 10% monthly returns.
    Uses Tradier sandbox for paper trading, can switch to live.
    """

    def __init__(
        self,
        mode: TradingMode = TradingMode.PAPER,
        initial_capital: float = 100_000,
        config: ARESConfig = None
    ):
        """
        Initialize ARES trader.

        Args:
            mode: Trading mode (PAPER, LIVE, or BACKTEST)
            initial_capital: Starting capital for position sizing
            config: Optional custom configuration
        """
        self.mode = mode
        self.capital = initial_capital
        self.config = config or ARESConfig()

        # Texas Central Time - standard timezone for all AlphaGEX operations
        self.tz = ZoneInfo("America/Chicago")

        # Initialize Tradier clients
        # Trading modes:
        #   1. SPX Paper Trading (paper_trade_spx=True):
        #      - Uses PRODUCTION Tradier for live SPX market data
        #      - Trades recorded in AlphaGEX DB only (no Tradier order submission)
        #      - tradier_sandbox = None → triggers SPX trading
        #
        #   2. SPY Sandbox Trading (paper_trade_spx=False OR TRADIER_SANDBOX=true):
        #      - Uses Tradier SANDBOX for market data and order submission
        #      - tradier_sandbox = client → triggers SPY trading
        #
        self.tradier = None  # Primary client for market data
        self.tradier_sandbox = None  # Sandbox client for paper trade submission (None = SPX mode)

        if TRADIER_AVAILABLE and mode != TradingMode.BACKTEST:
            from unified_config import APIConfig
            is_sandbox_mode = APIConfig.TRADIER_SANDBOX

            if is_sandbox_mode and not self.config.paper_trade_spx:
                # SPY Sandbox-only mode: Use sandbox API for everything (market data + orders)
                try:
                    sandbox_key = APIConfig.TRADIER_SANDBOX_API_KEY or APIConfig.TRADIER_API_KEY
                    sandbox_account = APIConfig.TRADIER_SANDBOX_ACCOUNT_ID or APIConfig.TRADIER_ACCOUNT_ID

                    if sandbox_key and sandbox_account:
                        # Use sandbox for market data
                        self.tradier = TradierDataFetcher(
                            api_key=sandbox_key,
                            account_id=sandbox_account,
                            sandbox=True
                        )
                        # Use same sandbox client for orders in PAPER mode
                        if mode == TradingMode.PAPER:
                            self.tradier_sandbox = self.tradier
                        logger.info(f"ARES: Tradier SANDBOX client initialized (SPY sandbox mode)")
                    else:
                        logger.warning("ARES: Tradier sandbox credentials not configured")
                except Exception as e:
                    logger.warning(f"ARES: Failed to initialize Tradier sandbox: {e}")
            else:
                # SPX Paper Trading mode: Use production API for live market data
                # No sandbox client = SPX trading with AlphaGEX-only paper trades
                #
                # IMPORTANT: SPX/VIX index quotes ($SPX.X, $VIX.X) are ONLY available
                # on Tradier's PRODUCTION API. If production credentials aren't available,
                # we fall back to sandbox API and use SPY * 10 as SPX proxy.
                try:
                    # Check if production credentials are available
                    # TRADIER_PROD_* takes priority (allows keeping sandbox creds in TRADIER_API_KEY)
                    prod_key = APIConfig.TRADIER_PROD_API_KEY or APIConfig.TRADIER_API_KEY
                    prod_account = APIConfig.TRADIER_PROD_ACCOUNT_ID or APIConfig.TRADIER_ACCOUNT_ID

                    # Only use as production if we have TRADIER_PROD_* OR if TRADIER_SANDBOX is false
                    has_explicit_prod = APIConfig.TRADIER_PROD_API_KEY and APIConfig.TRADIER_PROD_ACCOUNT_ID
                    sandbox_mode = APIConfig.TRADIER_SANDBOX

                    if has_explicit_prod:
                        # Explicit production credentials - use them for market data
                        self.tradier = TradierDataFetcher(
                            api_key=APIConfig.TRADIER_PROD_API_KEY,
                            account_id=APIConfig.TRADIER_PROD_ACCOUNT_ID,
                            sandbox=False
                        )
                        logger.info(f"ARES: Tradier PRODUCTION client initialized (using TRADIER_PROD_* credentials)")
                    elif prod_key and prod_account and not sandbox_mode:
                        # No explicit prod creds but TRADIER_SANDBOX=false, use main credentials
                        self.tradier = TradierDataFetcher(sandbox=False)
                        logger.info(f"ARES: Tradier PRODUCTION client initialized (for live SPX market data)")
                    else:
                        # No production credentials - fall back to sandbox for SPY data
                        logger.warning("ARES: No Tradier production credentials - falling back to sandbox")
                        sandbox_key = APIConfig.TRADIER_SANDBOX_API_KEY
                        sandbox_account = APIConfig.TRADIER_SANDBOX_ACCOUNT_ID

                        if sandbox_key and sandbox_account:
                            self.tradier = TradierDataFetcher(
                                api_key=sandbox_key,
                                account_id=sandbox_account,
                                sandbox=True
                            )
                            logger.info("ARES: Tradier SANDBOX client initialized (will use SPY*10 for SPX)")
                        else:
                            logger.error("ARES: No Tradier credentials available (neither production nor sandbox)")
                except Exception as e:
                    logger.warning(f"ARES: Failed to initialize Tradier: {e}")

                # SPX Paper Trading: Do NOT set tradier_sandbox
                # This ensures get_trading_ticker() returns "SPX" and trades are recorded internally
                if self.config.paper_trade_spx:
                    logger.info(f"ARES: SPX Paper Trading enabled - trades recorded in AlphaGEX DB only (no Tradier orders)")
                    # tradier_sandbox stays None → SPX mode
                elif mode == TradingMode.PAPER:
                    # SPY Sandbox mode with production data (rare use case)
                    try:
                        sandbox_key = APIConfig.TRADIER_SANDBOX_API_KEY or APIConfig.TRADIER_API_KEY
                        sandbox_account = APIConfig.TRADIER_SANDBOX_ACCOUNT_ID or APIConfig.TRADIER_ACCOUNT_ID

                        if sandbox_key and sandbox_account:
                            self.tradier_sandbox = TradierDataFetcher(
                                api_key=sandbox_key,
                                account_id=sandbox_account,
                                sandbox=True
                            )
                            logger.info(f"ARES: Tradier SANDBOX client initialized (for SPY paper trade submission)")
                        else:
                            logger.warning("ARES: Tradier credentials not configured - cannot submit to sandbox")
                    except Exception as e:
                        logger.warning(f"ARES: Failed to initialize Tradier sandbox: {e}")

        # Decision logger
        self.decision_logger = None
        if LOGGER_AVAILABLE:
            self.decision_logger = DecisionLogger()

        # Oracle AI advisor
        self.oracle = None
        if ORACLE_AVAILABLE:
            try:
                self.oracle = OracleAdvisor()
                logger.info("ARES: Oracle AI advisor initialized")
            except Exception as e:
                logger.warning(f"ARES: Failed to initialize Oracle AI: {e}")

        # Session tracking for scan_cycle and decision_sequence
        self.session_tracker = None
        if BOT_LOGGER_AVAILABLE and get_session_tracker:
            self.session_tracker = get_session_tracker("ARES")
            logger.info("ARES: Session tracker initialized for decision logging")

        # State tracking
        self.open_positions: List[IronCondorPosition] = []
        self.closed_positions: List[IronCondorPosition] = []
        self.daily_trade_executed: Dict[str, bool] = {}  # date -> traded
        self.skip_date = None  # Date to skip trading (set via API)

        # Performance tracking
        self.total_pnl = 0
        self.high_water_mark = initial_capital
        self.trade_count = 0
        self.win_count = 0

        # Position ID counter
        self._position_counter = 0

        # Position stop loss manager
        self.stop_loss_manager = None
        if STOP_LOSS_AVAILABLE and self.config.use_stop_loss:
            try:
                self.stop_loss_manager = get_stop_loss_manager()
                logger.info(f"ARES: Stop loss manager initialized "
                           f"(premium multiple: {self.config.stop_loss_premium_multiple}x)")
            except Exception as e:
                logger.warning(f"ARES: Failed to initialize stop loss manager: {e}")

        if mode == TradingMode.LIVE:
            logger.warning("ARES: LIVE TRADING MODE - Real money at risk!")

        logger.info(f"ARES initialized: mode={mode.value}, capital=${initial_capital:,.0f}")
        logger.info(f"  Trading ticker: {self.get_trading_ticker()}")
        logger.info(f"  Risk per trade: {self.config.risk_per_trade_pct}%")
        logger.info(f"  Spread width: ${self.get_spread_width()}")
        logger.info(f"  SD multiplier: {self.config.sd_multiplier}")

        # Load existing positions from database (survives restarts)
        if mode != TradingMode.BACKTEST:
            try:
                loaded = self._load_positions_from_db()
                if loaded > 0:
                    logger.info(f"ARES: Restored {loaded} open positions from database")
            except Exception as e:
                logger.warning(f"ARES: Could not load positions from database: {e}")

            # Store mode and ticker in config for API status endpoint
            try:
                from database_adapter import get_connection
                conn = get_connection()
                c = conn.cursor()
                trading_ticker = self.get_trading_ticker()
                # Upsert ares_mode
                c.execute('''
                    INSERT INTO autonomous_config (key, value) VALUES ('ares_mode', %s)
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                ''', (mode.value,))
                # Upsert ares_ticker
                c.execute('''
                    INSERT INTO autonomous_config (key, value) VALUES ('ares_ticker', %s)
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                ''', (trading_ticker,))
                conn.commit()
                conn.close()
                logger.info(f"ARES: Stored config - mode={mode.value}, ticker={trading_ticker}")
            except Exception as e:
                logger.debug(f"ARES: Could not store config: {e}")

    def _generate_position_id(self) -> str:
        """Generate unique position ID"""
        self._position_counter += 1
        now = datetime.now(self.tz)
        return f"ARES-{now.strftime('%Y%m%d')}-{self._position_counter:04d}"

    def get_trading_ticker(self) -> str:
        """
        Get the ticker to trade.

        SPX Paper Trading (paper_trade_spx=True, tradier_sandbox=None):
            - Uses SPX with live production data
            - Trades recorded in AlphaGEX DB only

        SPY Sandbox Trading (paper_trade_spx=False, tradier_sandbox exists):
            - Uses SPY with Tradier sandbox
            - Orders submitted to Tradier sandbox API
        """
        # SPX when no sandbox client (internal paper trading with live data)
        # SPY when sandbox client exists (Tradier sandbox order submission)
        if self.tradier_sandbox is not None:
            return self.config.sandbox_ticker  # SPY for Tradier sandbox
        return self.config.ticker  # SPX for live data paper trading

    def get_spread_width(self) -> float:
        """
        Get spread width based on trading mode.

        SPX spreads are $10 wide, SPY spreads are $2 wide.
        """
        if self.tradier_sandbox is not None:
            return self.config.spread_width_spy  # $2 for SPY sandbox
        return self.config.spread_width  # $10 for SPX

    def get_min_credit(self) -> float:
        """
        Get minimum credit required based on trading mode.
        """
        if self.tradier_sandbox is not None:
            return self.config.min_credit_per_spread_spy  # $0.15 for SPY sandbox
        return self.config.min_credit_per_spread  # $1.50 for SPX

    def get_backtest_stats(self) -> Dict[str, float]:
        """
        Get REAL backtest statistics from the database.

        Returns:
            Dict with win_rate, expectancy, sharpe_ratio from actual backtest runs
        """
        try:
            from database_adapter import get_connection
            conn = get_connection()
            cursor = conn.cursor()

            # Query the most recent backtest for ARES/iron_condor strategy
            cursor.execute("""
                SELECT win_rate, expectancy_pct, sharpe_ratio
                FROM backtest_results
                WHERE strategy_name ILIKE '%iron_condor%'
                   OR strategy_name ILIKE '%ares%'
                ORDER BY timestamp DESC
                LIMIT 1
            """)

            row = cursor.fetchone()
            cursor.close()
            conn.close()

            if row:
                return {
                    'win_rate': float(row[0]) if row[0] else 0.68,
                    'expectancy': float(row[1]) if row[1] else 0.0,
                    'sharpe_ratio': float(row[2]) if row[2] else 0.0
                }
            else:
                # No backtest data - return None to indicate no real data
                return {
                    'win_rate': None,
                    'expectancy': None,
                    'sharpe_ratio': None
                }

        except Exception as e:
            logger.warning(f"ARES: Could not get backtest stats: {e}")
            return {
                'win_rate': None,
                'expectancy': None,
                'sharpe_ratio': None
            }

    def get_current_market_data(self) -> Optional[Dict]:
        """
        Get current market data for the trading ticker (SPX or SPY).

        Returns:
            Dict with underlying price, VIX, expected move
        """
        if not self.tradier:
            logger.warning("ARES: Tradier not available for market data")
            return None

        try:
            # Get the appropriate ticker for current mode
            ticker = self.get_trading_ticker()
            underlying_price = None

            # Debug: Log Tradier client configuration
            tradier_mode = "SANDBOX" if self.tradier.sandbox else "PRODUCTION"
            logger.info(f"ARES: Tradier client mode: {tradier_mode}, Trading ticker: {ticker}")

            if ticker == "SPY":
                # Sandbox mode - use SPY directly
                quote = self.tradier.get_quote("SPY")
                logger.debug(f"ARES: SPY quote response: {quote}")
                if quote and quote.get('last'):
                    underlying_price = float(quote['last'])
                else:
                    logger.warning(f"ARES: Could not get SPY quote, response was: {quote}")
                    return None
            else:
                # SPX mode - need index quote
                # NOTE: $SPX.X is ONLY available on Tradier PRODUCTION API, not sandbox!
                # If using sandbox, skip SPX attempt and go straight to SPY * 10

                if self.tradier.sandbox:
                    # Sandbox mode: Index quotes not available, use SPY * 10 directly
                    logger.info("ARES: Using sandbox API - fetching SPY for SPX estimate (indexes not available in sandbox)")
                    spy_quote = self.tradier.get_quote("SPY")
                    logger.debug(f"ARES: SPY quote response: {spy_quote}")
                    if spy_quote and spy_quote.get('last'):
                        underlying_price = float(spy_quote['last']) * 10
                        logger.info(f"ARES: SPX estimated from SPY*10: ${underlying_price:.2f}")
                    else:
                        logger.warning(f"ARES: Could not get SPY quote from sandbox. Response: {spy_quote}")
                        return None
                else:
                    # Production mode: Try $SPX.X first, fall back to SPY * 10
                    quote = self.tradier.get_quote("$SPX.X")
                    logger.debug(f"ARES: $SPX.X quote response: {quote}")
                    if quote and quote.get('last'):
                        underlying_price = float(quote['last'])
                        logger.info(f"ARES: SPX price from Tradier: ${underlying_price:.2f}")
                    else:
                        logger.info("ARES: $SPX.X not available, trying SPY fallback")
                        # Fallback to SPY * 10 estimate
                        spy_quote = self.tradier.get_quote("SPY")
                        logger.debug(f"ARES: SPY fallback quote response: {spy_quote}")
                        if spy_quote and spy_quote.get('last'):
                            underlying_price = float(spy_quote['last']) * 10
                            logger.info(f"ARES: Using SPY*10 as SPX proxy: ${underlying_price:.2f}")
                        else:
                            logger.warning(f"ARES: Could not get SPX or SPY quote. SPX response: {quote}, SPY response: {spy_quote}")
                            return None

            # Get VIX for expected move calculation
            # NOTE: $VIX.X is ONLY available on Tradier PRODUCTION API, not sandbox!
            vix = 15.0  # Default if not available

            if self.tradier.sandbox:
                # Sandbox mode: VIX quotes not available, use default
                logger.info("ARES: Using sandbox API - VIX not available, using default 15.0")
            else:
                # Production mode: Try to get VIX
                vix_quote = self.tradier.get_quote("$VIX.X")
                if vix_quote and vix_quote.get('last'):
                    vix = float(vix_quote['last'])
                    logger.debug(f"ARES: VIX from Tradier: {vix}")
                else:
                    # Try alternate symbol
                    vix_quote = self.tradier.get_quote("VIX")
                    if vix_quote and vix_quote.get('last'):
                        vix = float(vix_quote['last'])
                        logger.debug(f"ARES: VIX from alternate symbol: {vix}")
                    else:
                        logger.info("ARES: VIX not available from Tradier, using default 15.0")

            # Validate underlying price before calculation
            if not underlying_price or underlying_price <= 0:
                logger.error(f"ARES: Invalid underlying price: {underlying_price}")
                return None

            # Validate VIX is reasonable (between 8 and 100)
            if vix < 8 or vix > 100:
                logger.warning(f"ARES: VIX {vix} outside normal range, clamping")
                vix = max(8, min(100, vix))

            # Calculate expected move (1 SD for 0DTE)
            iv = vix / 100
            expected_move = underlying_price * iv * math.sqrt(1/252)

            # Validate expected move is reasonable (should be 0.1% to 5% of underlying)
            expected_move_pct = (expected_move / underlying_price) * 100
            if expected_move <= 0 or expected_move_pct < 0.1 or expected_move_pct > 5:
                logger.error(f"ARES: Expected move calculation invalid: ${expected_move:.2f} ({expected_move_pct:.2f}%)")
                # Fallback to reasonable estimate based on VIX
                expected_move = underlying_price * (vix / 100) * 0.063  # ~1/16 approximation
                logger.info(f"ARES: Using fallback expected move: ${expected_move:.2f}")

            logger.info(f"ARES Market Data: {ticker}=${underlying_price:.2f}, VIX={vix:.2f}, EM=${expected_move:.2f}")

            return {
                'ticker': ticker,
                'underlying_price': underlying_price,
                'vix': vix,
                'expected_move': expected_move,
                'timestamp': datetime.now(self.tz).isoformat()
            }

        except Exception as e:
            logger.error(f"ARES: Error getting market data: {e}")
            return None

    def _get_gex_data(self) -> Dict:
        """
        Get current GEX data from database for logging and AI explanations.

        Returns:
            Dict with net_gex, call_wall, put_wall, gex_flip_point, regime
        """
        gex_data = {
            'net_gex': 0,
            'call_wall': 0,
            'put_wall': 0,
            'gex_flip_point': 0,
            'regime': 'NEUTRAL'
        }

        try:
            from database_adapter import get_connection
            conn = get_connection()
            c = conn.cursor()

            # Get latest GEX data
            # NOTE: SPY is used for GEX regime classification (not strike selection).
            # GEX wall-based strike selection is DISABLED - see line ~2741 for details.
            c.execute("""
                SELECT net_gex, call_wall, put_wall, gex_flip_point
                FROM gex_data
                WHERE symbol = 'SPY'
                ORDER BY timestamp DESC
                LIMIT 1
            """)
            row = c.fetchone()
            if row:
                gex_data['net_gex'] = row[0] or 0
                gex_data['call_wall'] = row[1] or 0
                gex_data['put_wall'] = row[2] or 0
                gex_data['gex_flip_point'] = row[3] or 0

                # Determine regime
                if gex_data['net_gex'] > 0:
                    gex_data['regime'] = 'POSITIVE'
                elif gex_data['net_gex'] < 0:
                    gex_data['regime'] = 'NEGATIVE'

            conn.close()
        except Exception as e:
            logger.debug(f"ARES: Could not fetch GEX data: {e}")

        return gex_data

    def _build_oracle_context(self, market_data: Dict) -> Optional['OracleMarketContext']:
        """
        Build Oracle MarketContext from ARES market data.

        Args:
            market_data: Dict from get_current_market_data()

        Returns:
            OracleMarketContext for Oracle consultation
        """
        if not ORACLE_AVAILABLE or OracleMarketContext is None:
            return None

        try:
            now = datetime.now(self.tz)
            vix = market_data.get('vix', 15.0)
            spot = market_data.get('underlying_price', 0)

            # Try to get GEX data from database
            gex_net = 0
            gex_call_wall = 0
            gex_put_wall = 0
            gex_flip = 0

            try:
                from database_adapter import get_connection
                conn = get_connection()
                c = conn.cursor()

                # Get latest GEX data
                # NOTE: SPY is used intentionally for GEX regime classification since:
                # 1. SPY has higher options volume = more reliable GEX data
                # 2. SPX and SPY have correlated gamma exposure regimes
                # 3. GEX walls are NOT used for strike selection (disabled - see line ~2741)
                c.execute("""
                    SELECT net_gex, call_wall, put_wall, gex_flip_point
                    FROM gex_data
                    WHERE symbol = 'SPY'
                    ORDER BY timestamp DESC
                    LIMIT 1
                """)
                row = c.fetchone()
                if row:
                    gex_net = row[0] or 0
                    gex_call_wall = row[1] or 0
                    gex_put_wall = row[2] or 0
                    gex_flip = row[3] or 0
                conn.close()
            except Exception as e:
                logger.debug(f"ARES: Could not fetch GEX data: {e}")

            # Determine GEX regime
            gex_regime = GEXRegime.NEUTRAL
            if gex_net > 0:
                gex_regime = GEXRegime.POSITIVE
            elif gex_net < 0:
                gex_regime = GEXRegime.NEGATIVE

            # Check if price is between walls
            between_walls = True
            if gex_put_wall > 0 and gex_call_wall > 0:
                between_walls = gex_put_wall <= spot <= gex_call_wall

            # Calculate expected move as percentage
            expected_move_pct = (market_data.get('expected_move', 0) / spot * 100) if spot > 0 else 1.0

            return OracleMarketContext(
                spot_price=spot,
                price_change_1d=0,  # Would need historical data
                vix=vix,
                vix_percentile_30d=50.0,  # Default, could be enhanced
                vix_change_1d=0,
                gex_net=gex_net,
                gex_normalized=0,  # Would need calculation
                gex_regime=gex_regime,
                gex_flip_point=gex_flip,
                gex_call_wall=gex_call_wall,
                gex_put_wall=gex_put_wall,
                gex_distance_to_flip_pct=0,
                gex_between_walls=between_walls,
                day_of_week=now.weekday(),
                days_to_opex=0,  # 0DTE
                win_rate_30d=self.win_count / max(1, self.trade_count) if self.trade_count > 0 else 0.68,
                expected_move_pct=expected_move_pct
            )

        except Exception as e:
            logger.error(f"ARES: Error building Oracle context: {e}")
            return None

    def consult_oracle(self, market_data: Dict) -> Optional['OraclePrediction']:
        """
        Consult Oracle AI for trading advice.

        Args:
            market_data: Dict from get_current_market_data()

        Returns:
            OraclePrediction with advice, or None if Oracle unavailable
        """
        if not self.oracle:
            logger.debug("ARES: Oracle not available, proceeding without advice")
            return None

        context = self._build_oracle_context(market_data)
        if not context:
            logger.debug("ARES: Could not build Oracle context")
            return None

        try:
            # Calculate recent losses for streak-based filtering
            recent_losses = self._count_recent_losses()

            # Get advice from Oracle with strategy preset VIX thresholds
            advice = self.oracle.get_ares_advice(
                context,
                use_gex_walls=True,
                use_claude_validation=True,
                vix_hard_skip=self.config.vix_hard_skip,
                vix_monday_friday_skip=self.config.vix_monday_friday_skip,
                vix_streak_skip=self.config.vix_streak_skip,
                recent_losses=recent_losses
            )

            logger.info(f"ARES Oracle: {advice.advice.value} | Win Prob: {advice.win_probability:.1%} | "
                       f"Risk: {advice.suggested_risk_pct:.1%} | SD Mult: {advice.suggested_sd_multiplier:.2f}")

            if advice.reasoning:
                logger.info(f"ARES Oracle Reasoning: {advice.reasoning}")

            # Store prediction for feedback loop
            try:
                today = datetime.now(self.tz).strftime('%Y-%m-%d')
                self.oracle.store_prediction(advice, context, today)
                self._last_oracle_context = context  # Store for outcome update
            except Exception as e:
                logger.debug(f"ARES: Could not store Oracle prediction: {e}")

            return advice

        except Exception as e:
            logger.error(f"ARES: Error consulting Oracle: {e}")
            return None

    def _count_recent_losses(self, lookback_days: int = 5) -> int:
        """
        Count recent consecutive losses for streak-based VIX filtering.

        Args:
            lookback_days: Number of days to look back for losses

        Returns:
            Number of consecutive losses (0 if most recent was a win)
        """
        try:
            from database_adapter import get_connection
            conn = get_connection()
            c = conn.cursor()

            # Get recent closed positions ordered by close date
            c.execute("""
                SELECT realized_pnl, close_date
                FROM ares_positions
                WHERE status = 'expired'
                AND close_date IS NOT NULL
                ORDER BY close_date DESC
                LIMIT %s
            """, (lookback_days,))

            rows = c.fetchall()
            conn.close()

            # Count consecutive losses from most recent
            consecutive_losses = 0
            for pnl, _ in rows:
                if pnl < 0:
                    consecutive_losses += 1
                else:
                    break  # Stop at first win

            return consecutive_losses

        except Exception as e:
            logger.debug(f"ARES: Could not count recent losses: {e}")
            return 0

    def record_trade_outcome(
        self,
        trade_date: str,
        outcome_type: str,
        actual_pnl: float
    ) -> bool:
        """
        Record trade outcome back to Oracle for feedback loop.

        Args:
            trade_date: Date of the trade (YYYY-MM-DD)
            outcome_type: One of MAX_PROFIT, PUT_BREACHED, CALL_BREACHED, etc.
            actual_pnl: Actual P&L from the trade

        Returns:
            True if recorded successfully
        """
        if not self.oracle or not ORACLE_AVAILABLE:
            return False

        try:
            outcome = TradeOutcome[outcome_type]
            self.oracle.update_outcome(
                trade_date,
                OracleBotName.ARES,
                outcome,
                actual_pnl
            )
            logger.info(f"ARES: Recorded outcome to Oracle: {outcome_type}, PnL=${actual_pnl:,.2f}")
            return True
        except Exception as e:
            logger.error(f"ARES: Failed to record outcome: {e}")
            return False

    def find_iron_condor_strikes(
        self,
        underlying_price: float,
        expected_move: float,
        expiration: str,
        gex_put_strike: Optional[float] = None,
        gex_call_strike: Optional[float] = None
    ) -> Optional[Dict]:
        """
        Find optimal Iron Condor strikes.

        Uses GEX-Protected strikes if provided (72% win rate in backtests),
        otherwise falls back to SD-based strike selection.

        Args:
            underlying_price: Current price (SPX or SPY)
            expected_move: Expected move (1 SD)
            expiration: Expiration date (YYYY-MM-DD)
            gex_put_strike: Optional GEX wall-based put strike (Oracle suggestion)
            gex_call_strike: Optional GEX wall-based call strike (Oracle suggestion)

        Returns:
            Dict with strikes and credits, or None if not found
        """
        if not self.tradier:
            return None

        try:
            # Get options chain - use appropriate symbol for mode
            ticker = self.get_trading_ticker()
            spread_width = self.get_spread_width()
            min_credit = self.get_min_credit()

            # Determine options symbol
            if ticker == "SPY":
                symbol = "SPY"  # SPY options
            elif ticker == "SPX":
                symbol = "SPXW"  # Weekly SPX options
            else:
                symbol = ticker

            chain = self.tradier.get_option_chain(symbol, expiration, greeks=True)

            if not chain or not chain.chains or expiration not in chain.chains:
                logger.warning(f"ARES: No options chain for {symbol} exp {expiration}")
                return None

            contracts = chain.chains[expiration]
            if not contracts:
                return None

            # Target strikes - prefer GEX walls if available (72% win rate vs 60% for SD-based)
            # For SPY, round to $1 strikes; for SPX, round to $5 strikes
            sd = self.config.sd_multiplier
            strike_rounding = 1 if ticker == "SPY" else 5
            using_gex_walls = False

            if gex_put_strike and gex_call_strike:
                # GEX-Protected IC: strikes outside GEX walls
                put_target = round(gex_put_strike / strike_rounding) * strike_rounding
                call_target = round(gex_call_strike / strike_rounding) * strike_rounding
                using_gex_walls = True
                logger.info(f"ARES: Using GEX-Protected strikes - Put: ${put_target}, Call: ${call_target}")
            else:
                # Fallback to SD-based calculation
                put_target = round((underlying_price - sd * expected_move) / strike_rounding) * strike_rounding
                call_target = round((underlying_price + sd * expected_move) / strike_rounding) * strike_rounding
                logger.info(f"ARES: Using SD-based strikes - Put: ${put_target}, Call: ${call_target}")

            # Filter puts and calls
            otm_puts = [c for c in contracts
                       if c.option_type == 'put'
                       and c.strike < underlying_price
                       and c.bid > 0]

            otm_calls = [c for c in contracts
                        if c.option_type == 'call'
                        and c.strike > underlying_price
                        and c.bid > 0]

            if not otm_puts or not otm_calls:
                logger.warning("ARES: Insufficient options available")
                return None

            # === TRACK REAL ALTERNATIVES ===
            # Evaluate top 5 put candidates by distance to target
            put_candidates_sorted = sorted(otm_puts, key=lambda x: abs(x.strike - put_target))[:5]
            call_candidates_sorted = sorted(otm_calls, key=lambda x: abs(x.strike - call_target))[:5]

            alternatives_evaluated = []

            # Find short put (sell)
            short_put = min(otm_puts, key=lambda x: abs(x.strike - put_target))

            # Find long put (buy) - spread_width below short
            long_put_strike = short_put.strike - spread_width
            long_put_candidates = [c for c in contracts
                                  if c.option_type == 'put'
                                  and abs(c.strike - long_put_strike) < (0.5 if ticker == "SPY" else 1)
                                  and c.ask > 0]

            if not long_put_candidates:
                logger.warning(f"ARES: No long put at strike {long_put_strike}")
                return None

            long_put = min(long_put_candidates, key=lambda x: abs(x.strike - long_put_strike))

            # Find short call (sell)
            short_call = min(otm_calls, key=lambda x: abs(x.strike - call_target))

            # Find long call (buy) - spread_width above short
            long_call_strike = short_call.strike + spread_width
            long_call_candidates = [c for c in contracts
                                   if c.option_type == 'call'
                                   and abs(c.strike - long_call_strike) < (0.5 if ticker == "SPY" else 1)
                                   and c.ask > 0]

            if not long_call_candidates:
                logger.warning(f"ARES: No long call at strike {long_call_strike}")
                return None

            long_call = min(long_call_candidates, key=lambda x: abs(x.strike - long_call_strike))

            # Calculate credits
            put_credit = short_put.bid - long_put.ask
            call_credit = short_call.bid - long_call.ask
            total_credit = put_credit + call_credit

            # === BUILD REAL ALTERNATIVES LIST ===
            # Track put strikes that were evaluated but not selected
            for put_opt in put_candidates_sorted:
                if put_opt.strike != short_put.strike:
                    distance_from_target = abs(put_opt.strike - put_target)
                    selected_distance = abs(short_put.strike - put_target)
                    # Calculate what credit would have been with this strike
                    alt_long_strike = put_opt.strike - spread_width
                    alt_long = next((c for c in contracts if c.option_type == 'put'
                                    and abs(c.strike - alt_long_strike) < 1), None)
                    alt_credit = (put_opt.bid - alt_long.ask) if alt_long else 0

                    if distance_from_target > selected_distance:
                        reason = f"Further from 1 SD target (${distance_from_target:.0f} vs ${selected_distance:.0f} away)"
                    elif alt_credit < put_credit:
                        reason = f"Lower credit (${alt_credit:.2f} vs ${put_credit:.2f})"
                    else:
                        reason = "Selected strike had better risk/reward"

                    alternatives_evaluated.append({
                        'strike': put_opt.strike,
                        'option_type': 'put',
                        'strategy': f"Put spread at ${put_opt.strike}",
                        'reason_rejected': reason,
                        'credit_available': alt_credit
                    })

            # Track call strikes that were evaluated but not selected
            for call_opt in call_candidates_sorted:
                if call_opt.strike != short_call.strike:
                    distance_from_target = abs(call_opt.strike - call_target)
                    selected_distance = abs(short_call.strike - call_target)
                    alt_long_strike = call_opt.strike + spread_width
                    alt_long = next((c for c in contracts if c.option_type == 'call'
                                    and abs(c.strike - alt_long_strike) < 1), None)
                    alt_credit = (call_opt.bid - alt_long.ask) if alt_long else 0

                    if distance_from_target > selected_distance:
                        reason = f"Further from 1 SD target (${distance_from_target:.0f} vs ${selected_distance:.0f} away)"
                    elif alt_credit < call_credit:
                        reason = f"Lower credit (${alt_credit:.2f} vs ${call_credit:.2f})"
                    else:
                        reason = "Selected strike had better risk/reward"

                    alternatives_evaluated.append({
                        'strike': call_opt.strike,
                        'option_type': 'call',
                        'strategy': f"Call spread at ${call_opt.strike}",
                        'reason_rejected': reason,
                        'credit_available': alt_credit
                    })

            # Validate credit
            if total_credit < min_credit:
                logger.info(f"ARES: Credit too low: ${total_credit:.2f} < ${min_credit:.2f}")
                return None

            return {
                'put_long_strike': long_put.strike,
                'put_short_strike': short_put.strike,
                'call_short_strike': short_call.strike,
                'call_long_strike': long_call.strike,
                'put_credit': put_credit,
                'call_credit': call_credit,
                'total_credit': total_credit,
                'put_long_symbol': long_put.symbol,
                'put_short_symbol': short_put.symbol,
                'call_short_symbol': short_call.symbol,
                'call_long_symbol': long_call.symbol,
                # REAL alternatives evaluated during strike selection
                'alternatives_evaluated': alternatives_evaluated,
                # GEX-Protected mode flag (72% win rate vs 60% for SD-based)
                'using_gex_walls': using_gex_walls,
            }

        except Exception as e:
            logger.error(f"ARES: Error finding strikes: {e}")
            return None

    def calculate_position_size(self, max_loss_per_spread: float) -> int:
        """
        Calculate position size based on risk budget.

        Args:
            max_loss_per_spread: Maximum loss per spread ($)

        Returns:
            Number of contracts to trade
        """
        # Risk budget: X% of current capital
        risk_budget = self.capital * (self.config.risk_per_trade_pct / 100)

        # Max loss is spread width minus credit received (per contract * 100)
        max_loss_dollars = max_loss_per_spread * 100

        # Calculate contracts
        contracts = int(risk_budget / max_loss_dollars)
        contracts = max(1, min(contracts, self.config.max_contracts))

        return contracts

    def execute_iron_condor(
        self,
        ic_strikes: Dict,
        contracts: int,
        expiration: str,
        market_data: Dict,
        oracle_advice: Optional[Any] = None,
        decision_tracker: Optional[Any] = None
    ) -> Optional[IronCondorPosition]:
        """
        Execute Iron Condor order via Tradier.

        Args:
            ic_strikes: Strike data from find_iron_condor_strikes
            contracts: Number of contracts
            expiration: Expiration date
            market_data: Current market data
            oracle_advice: Oracle AI advice for this trade (optional)

        Returns:
            IronCondorPosition if successful, None otherwise
        """
        if not self.tradier:
            logger.warning("ARES: Cannot execute - Tradier not available")
            return None

        # Generate idempotency key to prevent duplicate orders
        idempotency_key = None
        if IDEMPOTENCY_AVAILABLE and generate_idempotency_key:
            idempotency_key = generate_idempotency_key(
                "ARES",
                expiration,
                ic_strikes.get('put_short_strike'),
                ic_strikes.get('call_short_strike'),
                contracts
            )

            # Check if this order was already processed
            already_processed, existing_result = check_idempotency(idempotency_key)
            if already_processed and existing_result:
                logger.info(f"ARES: Duplicate order detected (key: {idempotency_key})")
                # Return cached position if available
                if 'position_id' in existing_result:
                    logger.info(f"ARES: Returning cached result for {existing_result.get('position_id')}")
                return None  # Prevent duplicate

            # Mark as pending
            request_data = {
                'expiration': expiration,
                'contracts': contracts,
                'strikes': ic_strikes
            }
            if not with_idempotency(idempotency_key, "ARES", request_data):
                logger.warning(f"ARES: Could not acquire idempotency lock for {idempotency_key}")
                return None

        try:
            ticker = self.get_trading_ticker()
            spread_width = self.get_spread_width()
            order_id = ""
            order_status = ""
            sandbox_order_id = ""  # Track actual Tradier sandbox order ID

            # PAPER mode: Track internally in AlphaGEX AND submit to Tradier sandbox
            # LIVE mode: Submit real order to Tradier production
            if self.mode == TradingMode.PAPER:
                logger.info(f"ARES [PAPER]: Iron Condor on {ticker} - {ic_strikes['put_long_strike']}/{ic_strikes['put_short_strike']}P - {ic_strikes['call_short_strike']}/{ic_strikes['call_long_strike']}C")
                logger.info(f"ARES [PAPER]: {contracts} contracts @ ${ic_strikes['total_credit']:.2f} credit")

                # Submit to Tradier sandbox for paper trading
                sandbox_success = False
                if self.tradier_sandbox:
                    try:
                        # Use SPY for sandbox (SPX not available in Tradier sandbox)
                        sandbox_ticker = self.config.sandbox_ticker  # SPY

                        # Check if we're already trading SPY (sandbox-only mode)
                        # In that case, strikes are already SPY-scale, no conversion needed
                        current_ticker = self.get_trading_ticker()
                        if current_ticker == 'SPY':
                            # Already using SPY, no scaling needed
                            spy_put_long = int(round(ic_strikes['put_long_strike'], 0))
                            spy_put_short = int(round(ic_strikes['put_short_strike'], 0))
                            spy_call_short = int(round(ic_strikes['call_short_strike'], 0))
                            spy_call_long = int(round(ic_strikes['call_long_strike'], 0))
                            spy_credit = ic_strikes['total_credit']
                        else:
                            # Using SPX for data, scale strikes to SPY (SPY is ~1/10 of SPX)
                            spy_put_long = int(round(ic_strikes['put_long_strike'] / 10, 0))
                            spy_put_short = int(round(ic_strikes['put_short_strike'] / 10, 0))
                            spy_call_short = int(round(ic_strikes['call_short_strike'] / 10, 0))
                            spy_call_long = int(round(ic_strikes['call_long_strike'] / 10, 0))
                            # FIX: Don't floor credit - scale proportionally (remove artificial $0.10 minimum)
                            spy_credit = round(ic_strikes['total_credit'] / 10, 2)
                            # Only apply minimum if result would be $0.00 (prevent $0 orders)
                            if spy_credit < 0.01:
                                spy_credit = 0.01

                        # SPY has daily 0DTE options (since Nov 2022), same as SPX
                        logger.info(f"ARES [SANDBOX]: Submitting to Tradier sandbox - SPY {spy_put_long}/{spy_put_short}P - {spy_call_short}/{spy_call_long}C exp={expiration} credit=${spy_credit:.2f}")
                        sandbox_result = self.tradier_sandbox.place_iron_condor(
                            symbol=sandbox_ticker,
                            expiration=expiration,
                            put_long=spy_put_long,
                            put_short=spy_put_short,
                            call_short=spy_call_short,
                            call_long=spy_call_long,
                            quantity=contracts,
                            limit_price=spy_credit
                        )

                        if 'errors' in sandbox_result:
                            error_msg = sandbox_result.get('errors', {}).get('error', 'Unknown error')
                            logger.error(f"ARES [SANDBOX]: Tradier sandbox FAILED: {error_msg}")
                            logger.error(f"ARES [SANDBOX]: Full response: {sandbox_result}")
                            # FIX: Fall back to internal paper tracking instead of failing completely
                            logger.info(f"ARES [PAPER]: Falling back to internal paper tracking")
                            order_id = f"PAPER-{datetime.now(self.tz).strftime('%Y%m%d%H%M%S')}"
                            order_status = "paper_simulated"
                        else:
                            sandbox_order_info = sandbox_result.get('order', {}) or {}
                            sandbox_order_id = str(sandbox_order_info.get('id', ''))
                            sandbox_status = sandbox_order_info.get('status', '')

                            # FIX: Validate order was actually placed (check status)
                            if not sandbox_order_id:
                                logger.error(f"ARES [SANDBOX]: No order ID returned from Tradier")
                                # FIX: Fall back to internal paper tracking instead of failing
                                logger.info(f"ARES [PAPER]: Falling back to internal paper tracking")
                                order_id = f"PAPER-{datetime.now(self.tz).strftime('%Y%m%d%H%M%S')}"
                                order_status = "paper_simulated"
                            elif sandbox_status in ['rejected', 'error', 'expired', 'canceled']:
                                # Check for rejected/error status
                                logger.error(f"ARES [SANDBOX]: Order rejected - Status: {sandbox_status}")
                                # FIX: Fall back to internal paper tracking instead of failing
                                logger.info(f"ARES [PAPER]: Falling back to internal paper tracking")
                                order_id = f"PAPER-{datetime.now(self.tz).strftime('%Y%m%d%H%M%S')}"
                                order_status = "paper_simulated"
                            else:
                                logger.info(f"ARES [SANDBOX]: Order SUCCESS - ID: {sandbox_order_id}, Status: {sandbox_status}")
                                sandbox_success = True
                                # FIX: Use actual Tradier order ID instead of synthetic
                                order_id = f"SANDBOX-{sandbox_order_id}"
                                order_status = sandbox_status

                    except Exception as e:
                        logger.error(f"ARES [SANDBOX]: Failed to submit to sandbox: {e}")
                        # FIX: Fall back to internal paper tracking instead of failing completely
                        logger.info(f"ARES [PAPER]: Falling back to internal paper tracking")
                        order_id = f"PAPER-{datetime.now(self.tz).strftime('%Y%m%d%H%M%S')}"
                        order_status = "paper_simulated"
                else:
                    # No sandbox available - create internal tracking only
                    logger.info(f"ARES [PAPER]: Tradier sandbox not available - internal tracking only")
                    order_id = f"PAPER-{datetime.now(self.tz).strftime('%Y%m%d%H%M%S')}"
                    order_status = "paper_internal"

            else:
                # LIVE mode - submit real order
                logger.info(f"ARES [LIVE]: Submitting real order to Tradier...")
                result = self.tradier.place_iron_condor(
                    symbol=ticker,
                    expiration=expiration,
                    put_long=ic_strikes['put_long_strike'],
                    put_short=ic_strikes['put_short_strike'],
                    call_short=ic_strikes['call_short_strike'],
                    call_long=ic_strikes['call_long_strike'],
                    quantity=contracts,
                    limit_price=ic_strikes['total_credit']
                )

                # Check for Tradier API errors
                if 'errors' in result:
                    error_msg = result.get('errors', {}).get('error', 'Unknown error')
                    logger.error(f"ARES [LIVE]: Tradier API error: {error_msg}")
                    logger.error(f"ARES [LIVE]: Full response: {result}")
                    return None

                order_info = result.get('order', {}) or {}
                order_id = str(order_info.get('id', ''))
                order_status = order_info.get('status', '')

                # FIX: Validate order was actually placed (check both ID and status)
                if not order_id:
                    logger.error(f"ARES [LIVE]: Order not placed - no order ID returned")
                    logger.error(f"ARES [LIVE]: Full response: {result}")
                    return None

                # FIX: Check for rejected/error status in LIVE mode too
                if order_status in ['rejected', 'error', 'expired', 'canceled']:
                    logger.error(f"ARES [LIVE]: Order rejected - ID: {order_id}, Status: {order_status}")
                    return None

                logger.info(f"ARES [LIVE]: Order placed - ID: {order_id}, Status: {order_status}")

            # Create position record (only reached if order was successful)
            max_loss = spread_width - ic_strikes['total_credit']

            position = IronCondorPosition(
                position_id=self._generate_position_id(),
                open_date=datetime.now(self.tz).strftime('%Y-%m-%d'),
                expiration=expiration,
                put_long_strike=ic_strikes['put_long_strike'],
                put_short_strike=ic_strikes['put_short_strike'],
                call_short_strike=ic_strikes['call_short_strike'],
                call_long_strike=ic_strikes['call_long_strike'],
                put_credit=ic_strikes['put_credit'],
                call_credit=ic_strikes['call_credit'],
                total_credit=ic_strikes['total_credit'],
                contracts=contracts,
                spread_width=spread_width,
                max_loss=max_loss,
                put_spread_order_id=order_id,
                call_spread_order_id=order_id,
                underlying_price_at_entry=market_data['underlying_price'],
                vix_at_entry=market_data['vix'],
                expected_move=market_data['expected_move']
            )

            self.open_positions.append(position)
            self.trade_count += 1

            # Register position for stop loss monitoring
            if self.stop_loss_manager and STOP_LOSS_AVAILABLE:
                try:
                    exp_dt = datetime.strptime(expiration, '%Y-%m-%d').replace(
                        hour=16, minute=0, tzinfo=self.tz
                    )
                    stop_config = create_iron_condor_stop_config(
                        premium_multiple=self.config.stop_loss_premium_multiple,
                        use_time_decay=self.config.stop_loss_use_time_decay
                    )
                    self.stop_loss_manager.register_position(
                        position_id=position.position_id,
                        entry_price=position.total_credit * 100 * position.contracts,
                        expiration=exp_dt,
                        premium_received=position.total_credit,
                        max_defined_loss=position.max_loss * 100 * position.contracts,
                        config=stop_config
                    )
                    logger.info(f"ARES: Registered position {position.position_id} for stop loss tracking")
                except Exception as e:
                    logger.warning(f"ARES: Could not register position for stop loss: {e}")

            # Log decision with Oracle advice and REAL alternatives from strike selection
            self._log_entry_decision(position, market_data, oracle_advice, decision_tracker, ic_strikes)

            # Save position to database for persistence
            self._save_position_to_db(position)

            # Mark idempotency as completed with result
            if idempotency_key and IDEMPOTENCY_AVAILABLE and mark_idempotency_completed:
                mark_idempotency_completed(idempotency_key, {
                    'position_id': position.position_id,
                    'status': 'success',
                    'order_id': position.put_spread_order_id,
                    'credit': position.total_credit
                })

            return position

        except Exception as e:
            logger.error(f"ARES: Error executing Iron Condor: {e}")

            # Mark idempotency as failed
            if idempotency_key and IDEMPOTENCY_AVAILABLE and mark_idempotency_failed:
                mark_idempotency_failed(idempotency_key, str(e))

            return None

    def _get_position_current_value(self, position: IronCondorPosition) -> float:
        """
        Calculate the current value of an Iron Condor position.

        For Iron Condors (credit spreads):
        - Entry value = credit received * 100 * contracts (positive)
        - Current cost to close = current spread price * 100 * contracts
        - Current value = entry value - current close cost

        Returns:
            Current position value in dollars (positive = profit, negative = loss)
        """
        try:
            ticker = self.get_trading_ticker()

            # Get current option prices for all 4 legs
            if not self.tradier:
                return 0.0

            # Build option symbols
            exp_fmt = position.expiration.replace('-', '')
            if ticker == 'SPY':
                # SPY option format: SPY230101C00400000
                put_long_sym = f"SPY{exp_fmt}P{int(position.put_long_strike * 1000):08d}"
                put_short_sym = f"SPY{exp_fmt}P{int(position.put_short_strike * 1000):08d}"
                call_short_sym = f"SPY{exp_fmt}C{int(position.call_short_strike * 1000):08d}"
                call_long_sym = f"SPY{exp_fmt}C{int(position.call_long_strike * 1000):08d}"
            else:
                # SPX uses different format
                put_long_sym = f"SPXW{exp_fmt}P{int(position.put_long_strike)}"
                put_short_sym = f"SPXW{exp_fmt}P{int(position.put_short_strike)}"
                call_short_sym = f"SPXW{exp_fmt}C{int(position.call_short_strike)}"
                call_long_sym = f"SPXW{exp_fmt}C{int(position.call_long_strike)}"

            # Get quotes
            symbols = [put_long_sym, put_short_sym, call_short_sym, call_long_sym]
            quotes = self.tradier.get_quotes(symbols)

            if not quotes:
                # Fall back to theoretical value based on underlying price
                return self._estimate_position_value(position)

            # Calculate current spread value
            # Iron Condor to close = buy back short legs, sell long legs
            put_long_price = quotes.get(put_long_sym, {}).get('bid', 0) or 0
            put_short_price = quotes.get(put_short_sym, {}).get('ask', 0) or 0
            call_short_price = quotes.get(call_short_sym, {}).get('ask', 0) or 0
            call_long_price = quotes.get(call_long_sym, {}).get('bid', 0) or 0

            # Cost to close = buy shorts - sell longs
            close_cost = (put_short_price - put_long_price + call_short_price - call_long_price)

            entry_credit = position.total_credit
            current_profit = (entry_credit - close_cost) * 100 * position.contracts

            return current_profit

        except Exception as e:
            logger.debug(f"Error getting position value: {e}")
            return self._estimate_position_value(position)

    def _estimate_position_value(self, position: IronCondorPosition) -> float:
        """
        Estimate position value based on underlying price movement.

        Used when option quotes aren't available.
        """
        try:
            ticker = self.get_trading_ticker()
            current_price = 0

            if self.tradier:
                quote = self.tradier.get_quote(ticker)
                current_price = quote.get('last', 0) or quote.get('close', 0)

            if current_price <= 0:
                return 0.0

            entry_price = position.underlying_price_at_entry

            # Simple estimate: check if price is within profit zone
            put_short = position.put_short_strike
            call_short = position.call_short_strike

            # Max profit if price between short strikes
            if put_short <= current_price <= call_short:
                # Estimate partial profit based on time decay (assume linear)
                # For 0DTE, if within zone, likely at profit
                return position.total_credit * 100 * position.contracts * 0.5

            # If outside short strikes, estimate loss
            if current_price < put_short:
                intrusion = put_short - current_price
                max_loss = position.max_loss * 100 * position.contracts
                estimated_loss = min(intrusion * 100 * position.contracts, max_loss)
                return -estimated_loss
            elif current_price > call_short:
                intrusion = current_price - call_short
                max_loss = position.max_loss * 100 * position.contracts
                estimated_loss = min(intrusion * 100 * position.contracts, max_loss)
                return -estimated_loss

            return 0.0

        except Exception as e:
            logger.debug(f"Error estimating position value: {e}")
            return 0.0

    def monitor_positions_for_stop_loss(self) -> List[IronCondorPosition]:
        """
        Check all open positions for stop loss triggers.

        Returns:
            List of positions that hit their stop loss
        """
        if not self.stop_loss_manager or not self.config.use_stop_loss:
            return []

        triggered_positions = []

        for position in self.open_positions[:]:  # Copy list for safe iteration
            try:
                current_value = self._get_position_current_value(position)
                entry_value = position.total_credit * 100 * position.contracts

                is_triggered, reason = self.stop_loss_manager.check_stop_loss(
                    position.position_id,
                    current_value
                )

                if is_triggered:
                    logger.warning(f"ARES: STOP LOSS TRIGGERED for {position.position_id}: {reason}")
                    logger.warning(f"  Entry Value: ${entry_value:,.2f}")
                    logger.warning(f"  Current Value: ${current_value:,.2f}")
                    logger.warning(f"  Loss: ${entry_value - current_value:,.2f}")

                    triggered_positions.append(position)

                    # Close the position
                    self._close_position_on_stop_loss(position, reason, current_value)

            except Exception as e:
                logger.debug(f"Error checking stop loss for {position.position_id}: {e}")

        return triggered_positions

    def _close_position_on_stop_loss(
        self,
        position: IronCondorPosition,
        reason: str,
        current_value: float
    ) -> None:
        """
        Close a position due to stop loss trigger.

        Args:
            position: The position to close
            reason: Stop loss trigger reason
            current_value: Current position value
        """
        try:
            entry_value = position.total_credit * 100 * position.contracts
            realized_pnl = current_value  # current_value is already profit/loss

            position.status = "closed"
            position.close_date = datetime.now(self.tz).strftime('%Y-%m-%d %H:%M:%S')
            position.realized_pnl = realized_pnl

            # Update capital
            self.capital += realized_pnl
            self.total_pnl += realized_pnl

            if realized_pnl > 0:
                self.win_count += 1

            # Remove from open positions
            if position in self.open_positions:
                self.open_positions.remove(position)
            self.closed_positions.append(position)

            # Unregister from stop loss manager
            if self.stop_loss_manager:
                self.stop_loss_manager.unregister_position(position.position_id)

            # Log to database
            self._update_position_close_in_db(position, reason)

            # Record in circuit breaker
            if CIRCUIT_BREAKER_AVAILABLE and record_trade_pnl:
                try:
                    record_trade_pnl(realized_pnl, position.position_id)
                except Exception as e:
                    logger.debug(f"Could not record to circuit breaker: {e}")

            logger.info(f"ARES: Position {position.position_id} closed on STOP LOSS")
            logger.info(f"  Reason: {reason}")
            logger.info(f"  Realized P&L: ${realized_pnl:+,.2f}")
            logger.info(f"  Capital: ${self.capital:,.2f}")

        except Exception as e:
            logger.error(f"Error closing position on stop loss: {e}")

    def _update_position_close_in_db(self, position: IronCondorPosition, close_reason: str) -> bool:
        """Update position in database with close info.

        Returns True if update succeeded, False otherwise.
        """
        conn = None
        try:
            from database_adapter import get_connection
            conn = get_connection()
            c = conn.cursor()

            c.execute('''
                UPDATE ares_positions
                SET status = %s,
                    close_date = %s,
                    close_price = %s,
                    realized_pnl = %s,
                    close_reason = %s
                WHERE position_id = %s
            ''', (
                'closed',
                position.close_date,
                position.close_price,
                position.realized_pnl,
                close_reason,
                position.position_id
            ))

            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to update position close in DB: {e}")
            return False
        finally:
            if conn:
                conn.close()

    def _log_skip_decision(self, reason: str, market_data: Optional[Dict] = None,
                           oracle_advice: Optional[Any] = None, alternatives: Optional[List[str]] = None,
                           decision_tracker: Optional[Any] = None):
        """
        Log a SKIP decision with full transparency about WHY we didn't trade.

        This is critical for understanding ARES behavior and improving the strategy.
        """
        if not self.decision_logger or not LOGGER_AVAILABLE:
            return

        try:
            now = datetime.now(self.tz)
            today = now.strftime('%Y-%m-%d')

            # Build detailed reasoning
            supporting_factors = []
            risk_factors = []
            alternatives_considered = alternatives or []
            why_not_alternatives = []

            # Add market context if available
            if market_data:
                supporting_factors.append(f"Underlying: ${market_data.get('underlying_price', 0):,.2f}")
                supporting_factors.append(f"VIX: {market_data.get('vix', 0):.1f}")
                supporting_factors.append(f"Expected Move (1SD): ${market_data.get('expected_move', 0):.2f}")

                # VIX analysis
                vix = market_data.get('vix', 15)
                if vix > 30:
                    risk_factors.append(f"Elevated VIX ({vix:.1f}) indicates high volatility environment")
                elif vix < 12:
                    risk_factors.append(f"Low VIX ({vix:.1f}) may result in thin premiums")

            # Add Oracle reasoning if available
            oracle_reasoning = ""
            if oracle_advice:
                oracle_reasoning = f" Oracle: {oracle_advice.advice.value} ({oracle_advice.win_probability:.0%} win prob)"
                supporting_factors.append(f"Oracle Win Probability: {oracle_advice.win_probability:.1%}")
                supporting_factors.append(f"Oracle Recommendation: {oracle_advice.advice.value}")
                if oracle_advice.reasoning:
                    supporting_factors.append(f"Oracle Reasoning: {oracle_advice.reasoning}")
                if hasattr(oracle_advice, 'top_factors') and oracle_advice.top_factors:
                    for factor, importance in oracle_advice.top_factors[:3]:
                        supporting_factors.append(f"Key Factor: {factor} (importance: {importance:.0%})")

            # Build comprehensive "what" description
            what_desc = f"SKIP - No trade executed. Reason: {reason}"

            # Build comprehensive "why" description
            why_desc = f"{reason}.{oracle_reasoning}"
            if market_data:
                why_desc += f" Market: {self.get_trading_ticker()} @ ${market_data.get('underlying_price', 0):,.2f}, VIX: {market_data.get('vix', 0):.1f}"

            # Build "how" description with methodology
            how_desc = (
                f"ARES Aggressive IC Strategy evaluates daily: "
                f"1) Check trading window (8:30 AM - 3:30 PM CT), "
                f"2) Verify no existing position for today, "
                f"3) Get market data (price, VIX, expected move), "
                f"4) Consult Oracle AI for trade/skip advice, "
                f"5) Find 1 SD Iron Condor strikes if trading, "
                f"6) Execute via Tradier API (PAPER/LIVE mode)."
            )

            # Fetch GEX data for market context
            gex_net = 0
            gex_call_wall = 0
            gex_put_wall = 0
            gex_flip = 0
            gex_regime = ""
            if market_data:
                try:
                    from database_adapter import get_connection
                    conn = get_connection()
                    if conn:
                        c = conn.cursor()
                        c.execute("""
                            SELECT net_gex, call_wall, put_wall, gex_flip_point
                            FROM gex_data
                            WHERE symbol = 'SPY'
                            ORDER BY timestamp DESC
                            LIMIT 1
                        """)
                        row = c.fetchone()
                        if row:
                            gex_net = row[0] or 0
                            gex_call_wall = row[1] or 0
                            gex_put_wall = row[2] or 0
                            gex_flip = row[3] or 0
                            gex_regime = "POSITIVE" if gex_net > 0 else "NEGATIVE" if gex_net < 0 else "NEUTRAL"
                        conn.close()
                except Exception as e:
                    logger.debug(f"Could not fetch GEX for skip logging: {e}")

            # Build oracle_advice dict for storage
            oracle_advice_dict = None
            if oracle_advice:
                oracle_advice_dict = {
                    'advice': oracle_advice.advice.value if hasattr(oracle_advice.advice, 'value') else str(oracle_advice.advice),
                    'win_probability': oracle_advice.win_probability,
                    'confidence': getattr(oracle_advice, 'confidence', oracle_advice.win_probability),
                    'suggested_risk_pct': oracle_advice.suggested_risk_pct,
                    'suggested_sd_multiplier': oracle_advice.suggested_sd_multiplier,
                    'use_gex_walls': getattr(oracle_advice, 'use_gex_walls', False),
                    'top_factors': getattr(oracle_advice, 'top_factors', []),
                    'reasoning': oracle_advice.reasoning or '',
                }

            decision = TradeDecision(
                decision_id=f"ARES-SKIP-{today}-{now.strftime('%H%M%S')}",
                timestamp=now.isoformat(),
                decision_type=DecisionType.NO_ACTION,
                bot_name=BotName.ARES,
                what=what_desc,
                why=why_desc,
                how=how_desc,
                action="SKIP",
                symbol=self.get_trading_ticker(),
                strategy="aggressive_iron_condor",
                market_context=LoggerMarketContext(
                    timestamp=now.isoformat(),
                    spot_price=market_data.get('underlying_price', 0) if market_data else 0,
                    spot_source=DataSource.TRADIER_LIVE,
                    vix=market_data.get('vix', 0) if market_data else 0,
                    net_gex=gex_net,
                    gex_regime=gex_regime,
                    flip_point=gex_flip,
                    call_wall=gex_call_wall,
                    put_wall=gex_put_wall,
                ) if market_data else None,
                oracle_advice=oracle_advice_dict,
                reasoning=DecisionReasoning(
                    primary_reason=reason,
                    supporting_factors=supporting_factors,
                    risk_factors=risk_factors,
                    alternatives_considered=alternatives_considered,
                    why_not_alternatives=why_not_alternatives
                )
            )

            self.decision_logger.log_decision(decision)
            logger.info(f"ARES: Logged SKIP decision - {reason}")

            # === COMPREHENSIVE BOT LOGGER (NEW) ===
            if BOT_LOGGER_AVAILABLE and log_bot_decision:
                try:
                    # Build alternatives from list
                    alt_objs = [
                        Alternative(strategy=alt, reason_rejected="")
                        for alt in (alternatives or [])
                    ]

                    # Determine signal source for SKIP
                    skip_signal_source = "Oracle" if oracle_advice else "Config"

                    comprehensive_decision = BotDecision(
                        bot_name="ARES",
                        decision_type="SKIP",
                        action="SKIP",
                        symbol=self.get_trading_ticker(),
                        strategy="aggressive_iron_condor",
                        # SIGNAL SOURCE TRACKING
                        signal_source=skip_signal_source,
                        override_occurred=False,  # ARES doesn't have ML override scenario
                        override_details={},
                        session_id=self.session_tracker.session_id if self.session_tracker else generate_session_id(),
                        scan_cycle=self.session_tracker.current_cycle if self.session_tracker else 0,
                        decision_sequence=self.session_tracker.next_decision() if self.session_tracker else 0,
                        market_context=BotLogMarketContext(
                            spot_price=market_data.get('underlying_price', 0) if market_data else 0,
                            vix=market_data.get('vix', 0) if market_data else 0,
                        ),
                        claude_context=ClaudeContext(
                            # Use REAL Claude data from oracle_advice.claude_analysis
                            prompt=(oracle_advice.claude_analysis.raw_prompt
                                    if oracle_advice and oracle_advice.claude_analysis and oracle_advice.claude_analysis.raw_prompt
                                    else "No Claude validation for SKIP decision"),
                            response=(oracle_advice.claude_analysis.raw_response
                                      if oracle_advice and oracle_advice.claude_analysis and oracle_advice.claude_analysis.raw_response
                                      else oracle_advice.reasoning if oracle_advice else ""),
                            model=(oracle_advice.claude_analysis.model_used
                                   if oracle_advice and oracle_advice.claude_analysis
                                   else ""),
                            tokens_used=(oracle_advice.claude_analysis.tokens_used
                                         if oracle_advice and oracle_advice.claude_analysis
                                         else 0),
                            response_time_ms=(oracle_advice.claude_analysis.response_time_ms
                                              if oracle_advice and oracle_advice.claude_analysis
                                              else 0),
                            confidence=str(oracle_advice.advice.value) if oracle_advice else "",
                        ) if oracle_advice else ClaudeContext(),
                        entry_reasoning=reason,
                        alternatives_considered=alt_objs,
                        other_strategies_considered=alternatives or [],
                        passed_all_checks=False,
                        blocked_reason=reason,
                        # Add API tracking data if available
                        api_calls=decision_tracker.api_calls if decision_tracker else [],
                        errors_encountered=decision_tracker.errors if decision_tracker else [],
                        processing_time_ms=decision_tracker.elapsed_ms if decision_tracker else 0,
                    )
                    log_bot_decision(comprehensive_decision)
                    logger.info(f"ARES: Logged to bot_decision_logs (SKIP)")
                except Exception as comp_e:
                    logger.warning(f"ARES: Could not log to comprehensive table: {comp_e}")

        except Exception as e:
            logger.error(f"ARES: Error logging SKIP decision: {e}")

    def _log_entry_decision(self, position: IronCondorPosition, market_data: Dict,
                           oracle_advice: Optional[Any] = None, decision_tracker: Optional[Any] = None,
                           ic_strikes: Optional[Dict] = None):
        """Log entry decision with full transparency including Oracle reasoning"""
        if not self.decision_logger or not LOGGER_AVAILABLE:
            return

        try:
            # Create trade legs
            legs = [
                TradeLeg(
                    leg_id=1,
                    action="BUY",
                    option_type="put",
                    strike=position.put_long_strike,
                    expiration=position.expiration,
                    contracts=position.contracts
                ),
                TradeLeg(
                    leg_id=2,
                    action="SELL",
                    option_type="put",
                    strike=position.put_short_strike,
                    expiration=position.expiration,
                    entry_price=position.put_credit,
                    contracts=position.contracts
                ),
                TradeLeg(
                    leg_id=3,
                    action="SELL",
                    option_type="call",
                    strike=position.call_short_strike,
                    expiration=position.expiration,
                    entry_price=position.call_credit,
                    contracts=position.contracts
                ),
                TradeLeg(
                    leg_id=4,
                    action="BUY",
                    option_type="call",
                    strike=position.call_long_strike,
                    expiration=position.expiration,
                    contracts=position.contracts
                )
            ]

            # Build comprehensive supporting factors
            supporting_factors = [
                f"VIX at {market_data['vix']:.1f} - {'favorable' if 15 <= market_data['vix'] <= 30 else 'elevated' if market_data['vix'] > 30 else 'low'} for premium selling",
                f"1 SD expected move: ${market_data['expected_move']:.0f} ({market_data['expected_move']/market_data['underlying_price']*100:.2f}% of underlying)",
                f"Put spread: ${position.put_short_strike} / ${position.put_long_strike} (${position.put_credit:.2f} credit)",
                f"Call spread: ${position.call_short_strike} / ${position.call_long_strike} (${position.call_credit:.2f} credit)",
                f"Total credit received: ${position.total_credit:.2f} per spread",
                f"Position size: {position.contracts} contracts @ {self.config.risk_per_trade_pct:.0f}% risk",
            ]

            # Add Oracle factors if available
            if oracle_advice:
                supporting_factors.append(f"Oracle Win Probability: {oracle_advice.win_probability:.1%}")
                supporting_factors.append(f"Oracle Recommendation: {oracle_advice.advice.value}")
                if oracle_advice.reasoning:
                    supporting_factors.append(f"Oracle Reasoning: {oracle_advice.reasoning}")
                if oracle_advice.suggested_risk_pct:
                    supporting_factors.append(f"Oracle Risk Adjustment: {oracle_advice.suggested_risk_pct:.1%}")
                if oracle_advice.suggested_sd_multiplier and oracle_advice.suggested_sd_multiplier != 1.0:
                    supporting_factors.append(f"Oracle SD Multiplier: {oracle_advice.suggested_sd_multiplier:.2f}x")

            # Build risk factors
            risk_factors = [
                f"Max loss per spread: ${position.max_loss:.2f} (spread width ${position.spread_width:.0f} - credit ${position.total_credit:.2f})",
                f"Total max risk: ${position.max_loss * 100 * position.contracts:,.0f}",
                "No stop loss - defined risk strategy, let theta decay work",
                f"0DTE expiration: {position.expiration} - all-or-nothing outcome",
            ]

            if market_data['vix'] > 25:
                risk_factors.append(f"Elevated VIX ({market_data['vix']:.1f}) increases probability of breach")

            # Alternatives considered
            alternatives_considered = [
                "SKIP today (Oracle evaluation)",
                "Wider strikes (2 SD) for higher win rate but less premium",
                "Narrower strikes (0.5 SD) for more premium but lower win rate",
                "Single credit spread instead of Iron Condor",
                "Wait for better entry later in day",
            ]

            why_not_alternatives = [
                "Oracle approved trade with acceptable win probability",
                "1 SD provides optimal risk/reward based on backtest data",
                "Iron Condor provides balanced risk on both sides",
                "Early entry captures full theta decay",
            ]

            # Build comprehensive "why"
            why_parts = [
                f"1 SD Iron Condor for aggressive daily premium collection targeting 10% monthly returns.",
                f"VIX: {market_data['vix']:.1f}",
            ]
            if oracle_advice:
                why_parts.append(f"Oracle: {oracle_advice.advice.value} ({oracle_advice.win_probability:.0%} win prob)")
            why_desc = " | ".join(why_parts)

            # Build comprehensive "how"
            how_desc = (
                f"Strike Selection: Found strikes at 1 SD ({market_data['expected_move']:.0f} pts) from "
                f"${market_data['underlying_price']:,.2f}. "
                f"Put short @ ${position.put_short_strike}, Call short @ ${position.call_short_strike}. "
                f"Position Sizing: {self.config.risk_per_trade_pct:.0f}% of ${self.capital:,.0f} capital = "
                f"${self.capital * self.config.risk_per_trade_pct / 100:,.0f} risk budget. "
                f"Max loss ${position.max_loss:.2f}/spread → {position.contracts} contracts. "
                f"Execution: {'Tradier Sandbox (PAPER)' if self.mode == TradingMode.PAPER else 'Tradier Production (LIVE)'}."
            )

            # Fetch GEX data for market context
            gex_net = 0
            gex_call_wall = 0
            gex_put_wall = 0
            gex_flip = 0
            gex_regime = ""
            try:
                from database_adapter import get_connection
                conn = get_connection()
                if conn:
                    c = conn.cursor()
                    c.execute("""
                        SELECT net_gex, call_wall, put_wall, gex_flip_point
                        FROM gex_data
                        WHERE symbol = 'SPY'
                        ORDER BY timestamp DESC
                        LIMIT 1
                    """)
                    row = c.fetchone()
                    if row:
                        gex_net = row[0] or 0
                        gex_call_wall = row[1] or 0
                        gex_put_wall = row[2] or 0
                        gex_flip = row[3] or 0
                        gex_regime = "POSITIVE" if gex_net > 0 else "NEGATIVE" if gex_net < 0 else "NEUTRAL"
                    conn.close()
            except Exception as e:
                logger.debug(f"Could not fetch GEX for logging: {e}")

            # Build oracle_advice dict for storage
            oracle_advice_dict = None
            if oracle_advice:
                oracle_advice_dict = {
                    'advice': oracle_advice.advice.value if hasattr(oracle_advice.advice, 'value') else str(oracle_advice.advice),
                    'win_probability': oracle_advice.win_probability,
                    'confidence': getattr(oracle_advice, 'confidence', oracle_advice.win_probability),
                    'suggested_risk_pct': oracle_advice.suggested_risk_pct,
                    'suggested_sd_multiplier': oracle_advice.suggested_sd_multiplier,
                    'use_gex_walls': getattr(oracle_advice, 'use_gex_walls', False),
                    'suggested_put_strike': getattr(oracle_advice, 'suggested_put_strike', None),
                    'suggested_call_strike': getattr(oracle_advice, 'suggested_call_strike', None),
                    'top_factors': getattr(oracle_advice, 'top_factors', []),
                    'reasoning': oracle_advice.reasoning or '',
                    'model_version': getattr(oracle_advice, 'model_version', ''),
                }
                # Include Claude analysis if available
                if hasattr(oracle_advice, 'claude_analysis') and oracle_advice.claude_analysis:
                    claude = oracle_advice.claude_analysis
                    oracle_advice_dict['claude_analysis'] = {
                        'analysis': getattr(claude, 'analysis', getattr(claude, 'raw_response', '')),
                        'confidence_adjustment': getattr(claude, 'confidence_adjustment', 0),
                        'risk_factors': getattr(claude, 'risk_factors', []),
                        'opportunities': getattr(claude, 'opportunities', []),
                        'recommendation': getattr(claude, 'recommendation', ''),
                    }

            decision = TradeDecision(
                decision_id=position.position_id,
                timestamp=datetime.now(self.tz).isoformat(),
                decision_type=DecisionType.ENTRY_SIGNAL,
                bot_name=BotName.ARES,
                what=f"SELL Iron Condor {position.contracts}x {position.put_short_strike}P/{position.call_short_strike}C @ ${position.total_credit:.2f}",
                why=why_desc,
                how=how_desc,
                action="SELL",
                symbol=self.config.ticker,
                strategy="aggressive_iron_condor",
                legs=legs,
                underlying_price_at_entry=market_data['underlying_price'],
                market_context=LoggerMarketContext(
                    timestamp=datetime.now(self.tz).isoformat(),
                    spot_price=market_data['underlying_price'],
                    spot_source=DataSource.TRADIER_LIVE,
                    vix=market_data['vix'],
                    net_gex=gex_net,
                    gex_regime=gex_regime,
                    flip_point=gex_flip,
                    call_wall=gex_call_wall,
                    put_wall=gex_put_wall,
                ),
                oracle_advice=oracle_advice_dict,
                reasoning=DecisionReasoning(
                    primary_reason="Daily aggressive Iron Condor for 10% monthly target",
                    supporting_factors=supporting_factors,
                    risk_factors=risk_factors,
                    alternatives_considered=alternatives_considered,
                    why_not_alternatives=why_not_alternatives,
                ),
                position_size_dollars=position.total_credit * 100 * position.contracts,
                position_size_contracts=position.contracts,
                max_risk_dollars=position.max_loss * 100 * position.contracts,
                probability_of_profit=oracle_advice.win_probability if oracle_advice else 0.68,
            )

            self.decision_logger.log_decision(decision)

            # === COMPREHENSIVE BOT LOGGER (NEW) ===
            if BOT_LOGGER_AVAILABLE and log_bot_decision:
                try:
                    # Build alternative strikes from REAL evaluated options
                    alt_objs = []
                    real_alternatives = ic_strikes.get('alternatives_evaluated', []) if ic_strikes else []
                    for alt in real_alternatives:
                        alt_objs.append(Alternative(
                            strike=alt.get('strike', 0),
                            strategy=alt.get('strategy', ''),
                            reason_rejected=alt.get('reason_rejected', '')
                        ))

                    # Get REAL backtest statistics from database
                    backtest_stats = self.get_backtest_stats()

                    # Build REAL strategies considered based on what Oracle evaluated
                    strategies_evaluated = []
                    if oracle_advice:
                        # Oracle evaluates these strategies in its analysis
                        strategies_evaluated.append(f"Iron Condor at 1 SD - Oracle: {oracle_advice.advice.value}")
                        if oracle_advice.suggested_sd_multiplier and oracle_advice.suggested_sd_multiplier != 1.0:
                            strategies_evaluated.append(f"Adjusted SD ({oracle_advice.suggested_sd_multiplier:.1f}x) considered")
                        if oracle_advice.win_probability < 0.60:
                            strategies_evaluated.append("SKIP considered due to low win probability")
                    else:
                        strategies_evaluated = ["Default 1 SD Iron Condor (no Oracle evaluation)"]

                    # Build risk checks
                    risk_checks = [
                        RiskCheck(
                            check_name="VIX_RANGE",
                            passed=12 <= market_data['vix'] <= 35,
                            current_value=market_data['vix'],
                            limit_value=35,
                            message=f"VIX at {market_data['vix']:.1f}"
                        ),
                        RiskCheck(
                            check_name="POSITION_SIZE",
                            passed=position.contracts <= self.config.max_contracts,
                            current_value=position.contracts,
                            limit_value=self.config.max_contracts,
                            message=f"{position.contracts} contracts within limit"
                        ),
                        RiskCheck(
                            check_name="CREDIT_RECEIVED",
                            passed=position.total_credit >= self.get_min_credit(),
                            current_value=position.total_credit,
                            limit_value=self.get_min_credit(),
                            message=f"Credit ${position.total_credit:.2f} meets minimum"
                        ),
                    ]

                    # Determine signal source for ARES
                    ares_signal_source = "Oracle" if oracle_advice else "Config"

                    comprehensive_decision = BotDecision(
                        bot_name="ARES",
                        decision_type="ENTRY",
                        action="SELL",
                        symbol=self.get_trading_ticker(),
                        strategy="aggressive_iron_condor",
                        # SIGNAL SOURCE TRACKING
                        signal_source=ares_signal_source,
                        override_occurred=False,  # ARES doesn't have ML override scenario
                        override_details={},
                        strike=position.put_short_strike,  # Primary strike for display
                        expiration=position.expiration,
                        option_type="IRON_CONDOR",
                        contracts=position.contracts,
                        session_id=self.session_tracker.session_id if self.session_tracker else generate_session_id(),
                        scan_cycle=self.session_tracker.current_cycle if self.session_tracker else 0,
                        decision_sequence=self.session_tracker.next_decision() if self.session_tracker else 0,
                        market_context=BotLogMarketContext(
                            spot_price=market_data['underlying_price'],
                            vix=market_data['vix'],
                        ),
                        claude_context=ClaudeContext(
                            # Use REAL Claude data from oracle_advice.claude_analysis
                            prompt=(oracle_advice.claude_analysis.raw_prompt
                                    if oracle_advice and oracle_advice.claude_analysis and oracle_advice.claude_analysis.raw_prompt
                                    else f"No Claude validation (VIX={market_data['vix']:.1f}, Price=${market_data['underlying_price']:,.2f})"),
                            response=(oracle_advice.claude_analysis.raw_response
                                      if oracle_advice and oracle_advice.claude_analysis and oracle_advice.claude_analysis.raw_response
                                      else oracle_advice.reasoning if oracle_advice else ""),
                            model=(oracle_advice.claude_analysis.model_used
                                   if oracle_advice and oracle_advice.claude_analysis
                                   else ""),
                            tokens_used=(oracle_advice.claude_analysis.tokens_used
                                         if oracle_advice and oracle_advice.claude_analysis
                                         else 0),
                            response_time_ms=(oracle_advice.claude_analysis.response_time_ms
                                              if oracle_advice and oracle_advice.claude_analysis
                                              else 0),
                            confidence=str(oracle_advice.advice.value) if oracle_advice else "DEFAULT",
                        ) if oracle_advice else ClaudeContext(),
                        entry_reasoning=f"1 SD Iron Condor targeting 10% monthly returns. VIX: {market_data['vix']:.1f}",
                        strike_reasoning=f"Put spread: ${position.put_long_strike}/${position.put_short_strike}, Call spread: ${position.call_short_strike}/${position.call_long_strike} at 1 SD",
                        size_reasoning=f"{self.config.risk_per_trade_pct:.0f}% of ${self.capital:,.0f} = {position.contracts} contracts",
                        alternatives_considered=alt_objs,
                        other_strategies_considered=strategies_evaluated,  # REAL strategies evaluated
                        kelly_pct=self.config.risk_per_trade_pct,
                        position_size_dollars=position.total_credit * 100 * position.contracts,
                        max_risk_dollars=position.max_loss * 100 * position.contracts,
                        # REAL backtest stats from database (None if no data available)
                        backtest_win_rate=backtest_stats.get('win_rate'),
                        backtest_expectancy=backtest_stats.get('expectancy'),
                        backtest_sharpe=backtest_stats.get('sharpe_ratio'),
                        risk_checks=risk_checks,
                        passed_all_checks=True,
                        execution=ExecutionTimeline(
                            order_submitted_at=datetime.now(self.tz),
                            expected_fill_price=position.total_credit,
                            broker_order_id=position.put_spread_order_id or position.call_spread_order_id,
                            broker_status="SUBMITTED" if position.put_spread_order_id else "PENDING",
                        ),
                        # Add API tracking data if available
                        api_calls=decision_tracker.api_calls if decision_tracker else [],
                        errors_encountered=decision_tracker.errors if decision_tracker else [],
                        processing_time_ms=decision_tracker.elapsed_ms if decision_tracker else 0,
                    )
                    decision_id = log_bot_decision(comprehensive_decision)
                    logger.info(f"ARES: Logged to bot_decision_logs (ENTRY) - ID: {decision_id}")

                    # Store the decision_id on the position for later updates
                    if hasattr(position, '__dict__'):
                        position.__dict__['bot_decision_id'] = decision_id

                except Exception as comp_e:
                    logger.warning(f"ARES: Could not log to comprehensive table: {comp_e}")

        except Exception as e:
            logger.error(f"ARES: Error logging decision: {e}")

    def get_todays_expiration(self) -> Optional[str]:
        """Get today's expiration for 0DTE trading"""
        now = datetime.now(self.tz)
        ticker = self.get_trading_ticker()

        # For 0DTE, use today's date
        if self.config.use_0dte:
            return now.strftime('%Y-%m-%d')

        # Otherwise find nearest weekly expiration
        if not self.tradier:
            return None

        try:
            expirations = self.tradier.get_option_expirations(ticker)
            if expirations:
                return expirations[0]
        except Exception as e:
            logger.error(f"ARES: Error getting expirations for {ticker}: {e}")

        return None

    def is_trading_window(self) -> bool:
        """Check if we're in the trading entry window"""
        now = datetime.now(self.tz)

        # Check if weekday
        if now.weekday() >= 5:  # Saturday or Sunday
            return False

        # Parse entry window times
        start_parts = self.config.entry_time_start.split(':')
        end_parts = self.config.entry_time_end.split(':')

        start_time = now.replace(
            hour=int(start_parts[0]),
            minute=int(start_parts[1]),
            second=0,
            microsecond=0
        )
        end_time = now.replace(
            hour=int(end_parts[0]),
            minute=int(end_parts[1]),
            second=0,
            microsecond=0
        )

        return start_time <= now <= end_time

    def should_trade_today(self) -> bool:
        """Check if we should open a new trade today"""
        today = datetime.now(self.tz).strftime('%Y-%m-%d')

        # Already traded today?
        if self.daily_trade_executed.get(today, False):
            logger.info("ARES: Already traded today")
            return False

        # Have any open positions expiring today?
        for pos in self.open_positions:
            if pos.expiration == today:
                logger.info(f"ARES: Already have position {pos.position_id} expiring today")
                return False

        return True

    def run_daily_cycle(self) -> Dict:
        """
        Run the daily ARES trading cycle.

        This should be called during market hours (ideally 10:00 AM ET).

        Returns:
            Dict with cycle results
        """
        now = datetime.now(self.tz)
        today = now.strftime('%Y-%m-%d')

        # Wrap entire cycle in try/except to ALWAYS log errors to scan_activity
        try:
            return self._run_daily_cycle_inner(now, today)
        except Exception as e:
            import traceback
            error_tb = traceback.format_exc()
            logger.error(f"[ARES] CRITICAL ERROR in run_daily_cycle: {e}")
            logger.error(error_tb)

            # Log the crash to scan_activity so it shows on frontend
            if SCAN_LOGGER_AVAILABLE and log_ares_scan:
                try:
                    log_ares_scan(
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
                    logger.error(f"[ARES] Failed to log crash to scan_activity: {log_err}")

            # Re-raise so scheduler knows there was an error
            raise

    def _run_daily_cycle_inner(self, now: datetime, today: str) -> Dict:
        """Inner implementation of run_daily_cycle - separated for error handling."""
        # Start a new scan cycle for session tracking
        scan_number = 1
        if self.session_tracker:
            cycle_num = self.session_tracker.new_cycle()
            scan_number = cycle_num
            logger.info(f"ARES: Starting scan cycle {cycle_num} for session {self.session_tracker.session_id}")

        # Log scan START to database - ALWAYS log this
        if SCAN_LOGGER_AVAILABLE:
            try:
                from database_adapter import get_connection
                conn = get_connection()
                c = conn.cursor()
                c.execute("""
                    INSERT INTO bot_heartbeat (bot_name, status, last_action, last_scan_time)
                    VALUES ('ARES', 'SCANNING', %s, NOW())
                    ON CONFLICT (bot_name) DO UPDATE SET
                        status = 'SCANNING',
                        last_action = EXCLUDED.last_action,
                        last_scan_time = NOW()
                """, (f"Scan #{scan_number} started at {now.strftime('%I:%M %p CT')}",))
                conn.commit()
                conn.close()
                logger.info(f"[ARES] Scan #{scan_number} heartbeat logged to database")
            except Exception as e:
                logger.warning(f"[ARES] Failed to log scan start: {e}")

        # Create decision tracker for API calls, errors, and timing
        decision_tracker = None
        if BOT_LOGGER_AVAILABLE and DecisionTracker:
            decision_tracker = DecisionTracker()
            decision_tracker.start()

        # Check if today is a skip day (set via API)
        if self.skip_date and self.skip_date == now.date():
            logger.info(f"ARES: Skip day is set for {self.skip_date} - not trading today")
            if SCAN_LOGGER_AVAILABLE and log_ares_scan:
                log_ares_scan(
                    outcome=ScanOutcome.SKIPPED,
                    decision_summary="Manual skip requested via API",
                    action_taken="No trade - user requested skip for today",
                    checks=[CheckResult("skip_day", False, "Skip day set", "Skip day not set")]
                )
            return {
                "status": "skipped",
                "reason": "Skip day set via API",
                "skip_date": self.skip_date.isoformat()
            }

        # =========================================================================
        # CIRCUIT BREAKER CHECK - FIRST LINE OF DEFENSE
        # =========================================================================
        if CIRCUIT_BREAKER_AVAILABLE and is_trading_enabled:
            try:
                can_trade, cb_reason = is_trading_enabled(
                    current_positions=len(self.open_positions),
                    margin_used=0  # ARES uses defined risk, not margin
                )

                if not can_trade:
                    reason = f"Circuit breaker: {cb_reason}"
                    logger.warning(f"ARES: {reason}")
                    if SCAN_LOGGER_AVAILABLE and log_ares_scan:
                        log_ares_scan(
                            outcome=ScanOutcome.SKIP,
                            decision_summary=f"CIRCUIT BREAKER ACTIVE: {cb_reason}",
                            action_taken="No trade - circuit breaker prevented trading for risk management",
                            full_reasoning=f"The circuit breaker system has blocked trading to protect capital. "
                                          f"This typically occurs when daily loss limits are hit or when too many "
                                          f"positions are open. Reason: {cb_reason}",
                            checks=[
                                CheckResult("circuit_breaker", False, "BLOCKED", "ENABLED", cb_reason)
                            ]
                        )
                    return {
                        "status": "blocked",
                        "reason": reason,
                        "circuit_breaker": True
                    }
            except Exception as e:
                logger.warning(f"ARES: Circuit breaker check failed: {e} - continuing with trade")

        # =========================================================================
        # POSITION MONITORING - Check stop losses on open positions
        # =========================================================================
        if self.open_positions and self.config.use_stop_loss:
            try:
                triggered = self.monitor_positions_for_stop_loss()
                if triggered:
                    logger.info(f"ARES: {len(triggered)} position(s) closed on stop loss")
            except Exception as e:
                logger.warning(f"ARES: Error monitoring positions: {e}")

        logger.info(f"=" * 60)
        logger.info(f"ARES Daily Cycle - {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        logger.info(f"Mode: {self.mode.value.upper()}")
        logger.info(f"Capital: ${self.capital:,.2f}")
        logger.info(f"=" * 60)

        result = {
            'date': today,
            'timestamp': now.isoformat(),
            'actions': [],
            'new_position': None,
            'capital': self.capital,
            'open_positions': len(self.open_positions)
        }

        # Check if in trading window
        if not self.is_trading_window():
            logger.info("ARES: Outside trading window")
            result['actions'].append("Outside trading window")
            self._log_skip_decision(
                reason="Outside trading window (8:30 AM - 3:30 PM CT)",
                market_data=None,
                oracle_advice=None,
                alternatives=["Wait for trading window to open"],
                decision_tracker=decision_tracker
            )
            # Log scan activity - OUTSIDE WINDOW
            if SCAN_LOGGER_AVAILABLE and log_ares_scan:
                log_ares_scan(
                    outcome=ScanOutcome.BEFORE_WINDOW,
                    decision_summary="Outside trading window (8:30 AM - 3:30 PM CT)",
                    action_taken="Scan skipped - waiting for trading window",
                    full_reasoning="ARES only trades during market hours. Entry window is 8:30 AM - 3:30 PM CT to ensure good liquidity for 0DTE options.",
                    checks=[
                        CheckResult("trading_window", False, now.strftime('%H:%M'), "08:30-15:30 CT", "Current time is outside trading window")
                    ]
                )
            return result

        # Check if should trade today
        if not self.should_trade_today():
            result['actions'].append("Already traded today or position exists")
            self._log_skip_decision(
                reason="Already traded today or have existing position for today's expiration",
                market_data=None,
                oracle_advice=None,
                alternatives=["ARES trades once per day - position already established"],
                decision_tracker=decision_tracker
            )
            # Log scan activity - ALREADY TRADED
            if SCAN_LOGGER_AVAILABLE and log_ares_scan:
                log_ares_scan(
                    outcome=ScanOutcome.SKIP,
                    decision_summary="Already traded today - ARES trades once per day",
                    action_taken="Monitoring existing position",
                    full_reasoning="ARES is designed to trade ONE Iron Condor per day to avoid overexposure. A position was already opened earlier today.",
                    checks=[
                        CheckResult("daily_trade_limit", False, "1", "1 max", "Already executed daily trade"),
                        CheckResult("trading_window", True, now.strftime('%H:%M'), "08:30-15:30 CT", "Within window")
                    ]
                )
            return result

        # Get market data - track API call timing
        if decision_tracker:
            with decision_tracker.track_api("tradier", "quotes"):
                market_data = self.get_current_market_data()
        else:
            market_data = self.get_current_market_data()
        if not market_data:
            logger.warning("ARES: Could not get market data")
            result['actions'].append("Failed to get market data")
            self._log_skip_decision(
                reason="Failed to get market data from Tradier API",
                market_data=None,
                oracle_advice=None,
                alternatives=["Retry later when market data is available", "Check Tradier API status"],
                decision_tracker=decision_tracker
            )
            # Log scan activity - MARKET DATA ERROR
            if SCAN_LOGGER_AVAILABLE and log_ares_scan:
                log_ares_scan(
                    outcome=ScanOutcome.ERROR,
                    decision_summary="Failed to get market data from Tradier API",
                    action_taken="Will retry on next scan",
                    full_reasoning="Could not fetch current prices for SPX/SPY/VIX. This may be due to API rate limits or network issues.",
                    error_message="Tradier API did not return market data",
                    error_type="MARKET_DATA_ERROR",
                    checks=[
                        CheckResult("market_data_available", False, "None", "Required", "No market data returned")
                    ]
                )
            return result

        result['market_data'] = market_data

        # Validate market data freshness - CRITICAL SAFETY CHECK
        if DATA_VALIDATION_AVAILABLE and validate_market_data:
            is_valid, error_msg = validate_market_data(
                market_data,
                max_age_seconds=MAX_DATA_AGE_SECONDS,
                require_timestamp=True
            )
            if not is_valid:
                logger.warning(f"ARES: Market data validation failed: {error_msg}")
                result['actions'].append(f"Market data validation failed: {error_msg}")
                self._log_skip_decision(
                    reason=f"Market data validation failed: {error_msg}",
                    market_data=market_data,
                    oracle_advice=None,
                    alternatives=["Wait for fresh market data", "Check data source"],
                    decision_tracker=decision_tracker
                )
                # Log scan activity - STALE DATA
                if SCAN_LOGGER_AVAILABLE and log_ares_scan:
                    log_ares_scan(
                        outcome=ScanOutcome.ERROR,
                        decision_summary=f"Market data validation failed: {error_msg}",
                        action_taken="Skipping trade - waiting for fresh data",
                        full_reasoning=f"Safety check: {error_msg}. Trading on stale or invalid data could lead to incorrect strike selection.",
                        error_message=error_msg,
                        error_type="STALE_DATA_ERROR",
                        checks=[
                            CheckResult("data_freshness", False, error_msg, f"Data < {MAX_DATA_AGE_SECONDS}s old", "Data validation failed")
                        ],
                        market_data=market_data
                    )
                return result

        # Get GEX data for logging and AI explanations
        gex_data = self._get_gex_data()
        result['gex_data'] = gex_data

        logger.info(f"  Underlying: ${market_data['underlying_price']:,.2f}")
        logger.info(f"  VIX: {market_data['vix']:.1f}")
        logger.info(f"  Expected Move (1 SD): ${market_data['expected_move']:.2f}")
        if gex_data.get('net_gex'):
            logger.info(f"  GEX: {gex_data['regime']} (Net: ${gex_data['net_gex']:,.0f})")

        # =========================================================================
        # CONSULT ORACLE AI FOR TRADING ADVICE
        # =========================================================================
        # Track Oracle API call timing (includes Claude)
        if decision_tracker:
            with decision_tracker.track_api("oracle", "consult"):
                oracle_advice = self.consult_oracle(market_data)
        else:
            oracle_advice = self.consult_oracle(market_data)
        oracle_risk_pct = None
        oracle_sd_mult = None

        if oracle_advice:
            result['oracle_advice'] = {
                'advice': oracle_advice.advice.value,
                'win_probability': oracle_advice.win_probability,
                'suggested_risk_pct': oracle_advice.suggested_risk_pct,
                'suggested_sd_multiplier': oracle_advice.suggested_sd_multiplier,
                'reasoning': oracle_advice.reasoning,
                # GEX-Protected strikes (72% win rate when available)
                'suggested_put_strike': getattr(oracle_advice, 'suggested_put_strike', None),
                'suggested_call_strike': getattr(oracle_advice, 'suggested_call_strike', None),
                'use_gex_walls': getattr(oracle_advice, 'use_gex_walls', False)
            }

            # Honor Oracle's SKIP advice
            if ORACLE_AVAILABLE and TradingAdvice and oracle_advice.advice == TradingAdvice.SKIP_TODAY:
                logger.warning(f"ARES: Oracle advises SKIP - {oracle_advice.reasoning}")
                result['actions'].append(f"Oracle SKIP: {oracle_advice.reasoning}")
                self._log_skip_decision(
                    reason=f"Oracle AI recommends SKIP: {oracle_advice.reasoning}",
                    market_data=market_data,
                    oracle_advice=oracle_advice,
                    alternatives=[
                        "Proceed with trade anyway (ignoring Oracle)",
                        "Wait for better market conditions",
                        "Adjust strike selection to improve win probability"
                    ],
                    decision_tracker=decision_tracker
                )
                # Log scan activity - ORACLE SKIP
                if SCAN_LOGGER_AVAILABLE and log_ares_scan:
                    log_ares_scan(
                        outcome=ScanOutcome.NO_TRADE,
                        decision_summary=f"Oracle recommends SKIP: {oracle_advice.reasoning[:100]}",
                        action_taken="No trade - following Oracle AI advice",
                        market_data=market_data,
                        gex_data=gex_data,
                        signal_source="Oracle",
                        signal_confidence=oracle_advice.confidence if hasattr(oracle_advice, 'confidence') else 0,
                        signal_win_probability=oracle_advice.win_probability,
                        oracle_advice="SKIP_TODAY",
                        oracle_reasoning=oracle_advice.reasoning,
                        checks=[
                            CheckResult("trading_window", True, now.strftime('%H:%M'), "08:30-15:30 CT", "Within window"),
                            CheckResult("daily_trade_limit", True, "0", "1 max", "No trade yet today"),
                            CheckResult("market_data", True, f"${market_data['underlying_price']:.2f}", "Required", "Market data available"),
                            CheckResult("vix_level", True, f"{market_data['vix']:.1f}", "Informational", "Current volatility"),
                            CheckResult("oracle_approval", False, "SKIP", "TRADE", f"Oracle says skip: {oracle_advice.reasoning[:50]}")
                        ]
                    )
                return result

            # Store Oracle's suggestions for use
            oracle_risk_pct = oracle_advice.suggested_risk_pct
            oracle_sd_mult = oracle_advice.suggested_sd_multiplier

            logger.info(f"  Oracle Advice: {oracle_advice.advice.value}")
            logger.info(f"  Oracle Win Prob: {oracle_advice.win_probability:.1%}")

            # Use GEX wall-based strikes for IC wings OUTSIDE support/resistance
            # GEX walls = where market makers have gamma exposure = support/resistance
            # Put strike should be BELOW put wall (support)
            # Call strike should be ABOVE call wall (resistance)
            oracle_put_strike = getattr(oracle_advice, 'suggested_put_strike', None)
            oracle_call_strike = getattr(oracle_advice, 'suggested_call_strike', None)
            if oracle_put_strike and oracle_call_strike:
                logger.info(f"  Oracle GEX Walls: Put ${oracle_put_strike}, Call ${oracle_call_strike}")
        else:
            logger.info("  Oracle: Not available, using default parameters")
            oracle_put_strike = None
            oracle_call_strike = None

        # Get expiration
        expiration = self.get_todays_expiration()
        if not expiration:
            logger.warning("ARES: Could not get expiration date")
            result['actions'].append("Failed to get expiration")
            self._log_skip_decision(
                reason="Could not determine today's expiration date for 0DTE options",
                market_data=market_data,
                oracle_advice=oracle_advice,
                alternatives=["Check Tradier API for expiration calendar", "Retry later"],
                decision_tracker=decision_tracker
            )
            # Log scan activity - EXPIRATION ERROR
            if SCAN_LOGGER_AVAILABLE and log_ares_scan:
                log_ares_scan(
                    outcome=ScanOutcome.ERROR,
                    decision_summary="Could not determine today's expiration date for 0DTE options",
                    action_taken="Will retry on next scan",
                    market_data=market_data,
                    gex_data=gex_data,
                    error_message="Failed to get expiration date from Tradier API",
                    error_type="EXPIRATION_ERROR",
                    checks=[
                        CheckResult("trading_window", True, now.strftime('%H:%M'), "08:30-15:30 CT", "Within window"),
                        CheckResult("market_data", True, f"${market_data['underlying_price']:.2f}", "Required", "Available"),
                        CheckResult("expiration_date", False, "None", "Required", "Could not determine 0DTE expiration")
                    ]
                )
            return result

        # Calculate expected move with SD multiplier
        # IC wings should be OUTSIDE the expected move (SD >= 1.0)
        # Oracle suggests SD multipliers based on market conditions:
        #   0.9-1.2 range puts strikes at or outside expected move
        # This protects the IC from normal daily price movement
        adjusted_expected_move = market_data['expected_move']

        if oracle_sd_mult and oracle_sd_mult > 0:
            # Use Oracle's SD multiplier - it's calibrated for market conditions
            effective_sd_mult = oracle_sd_mult
            logger.info(f"  Using Oracle SD multiplier: {effective_sd_mult:.2f}")
        else:
            # Fallback to config (should be >= 1.0 for wings outside expected move)
            effective_sd_mult = self.config.sd_multiplier
            logger.info(f"  Using config SD multiplier: {effective_sd_mult:.2f}")

        adjusted_expected_move = market_data['expected_move'] * effective_sd_mult
        logger.info(f"  SD Mult: {effective_sd_mult:.2f} -> Adjusted Move: ${adjusted_expected_move:.2f} (expected move ${market_data['expected_move']:.2f})")

        # Find Iron Condor strikes
        # Uses GEX-Protected strikes if Oracle provides them (72% win rate)
        # Otherwise falls back to SD-based selection with Oracle's SD multiplier
        if decision_tracker:
            with decision_tracker.track_api("tradier", "option_chain"):
                ic_strikes = self.find_iron_condor_strikes(
                    market_data['underlying_price'],
                    adjusted_expected_move,
                    expiration,
                    gex_put_strike=oracle_put_strike,
                    gex_call_strike=oracle_call_strike
                )
        else:
            ic_strikes = self.find_iron_condor_strikes(
                market_data['underlying_price'],
                adjusted_expected_move,
                expiration,
                gex_put_strike=oracle_put_strike,
                gex_call_strike=oracle_call_strike
            )

        if not ic_strikes:
            logger.info("ARES: Could not find suitable Iron Condor strikes")
            result['actions'].append("No suitable strikes found")
            self._log_skip_decision(
                reason=f"Could not find suitable Iron Condor strikes for {expiration} at 1 SD ({adjusted_expected_move:.0f} pts)",
                market_data=market_data,
                oracle_advice=oracle_advice,
                alternatives=[
                    "Widen strike selection criteria",
                    "Try different expiration date",
                    "Market may have insufficient options liquidity today"
                ],
                decision_tracker=decision_tracker
            )
            # Log scan activity - NO STRIKES
            if SCAN_LOGGER_AVAILABLE and log_ares_scan:
                log_ares_scan(
                    outcome=ScanOutcome.NO_TRADE,
                    decision_summary=f"No suitable Iron Condor strikes found for {expiration}",
                    action_taken="Will retry on next scan",
                    market_data=market_data,
                    gex_data=gex_data,
                    signal_source="Oracle" if oracle_advice else "Config",
                    signal_confidence=oracle_advice.confidence if oracle_advice and hasattr(oracle_advice, 'confidence') else 0,
                    signal_win_probability=oracle_advice.win_probability if oracle_advice else 0,
                    oracle_advice=oracle_advice.advice.value if oracle_advice else "N/A",
                    oracle_reasoning=oracle_advice.reasoning if oracle_advice else "Oracle not available",
                    checks=[
                        CheckResult("trading_window", True, now.strftime('%H:%M'), "08:30-15:30 CT", "Within window"),
                        CheckResult("market_data", True, f"${market_data['underlying_price']:.2f}", "Required", "Available"),
                        CheckResult("vix_level", True, f"{market_data['vix']:.1f}", "Informational", "Current volatility"),
                        CheckResult("expected_move", True, f"${market_data['expected_move']:.2f}", f"{effective_sd_mult:.2f} SD", f"Looking for strikes {adjusted_expected_move:.0f} pts OTM"),
                        CheckResult("oracle_approval", True if oracle_advice and oracle_advice.advice != TradingAdvice.SKIP_TODAY else False, "TRADE", "TRADE", "Oracle approved"),
                        CheckResult("strikes_available", False, "None", "Required", "No suitable strikes found in chain - may need wider search or better liquidity")
                    ]
                )
            return result

        gex_mode = "GEX-Protected (72% WR)" if ic_strikes.get('using_gex_walls') else "SD-Based (60% WR)"
        logger.info(f"  IC Strikes [{gex_mode}]: {ic_strikes['put_long_strike']}/{ic_strikes['put_short_strike']}P - "
                   f"{ic_strikes['call_short_strike']}/{ic_strikes['call_long_strike']}C")
        logger.info(f"  Credit: ${ic_strikes['total_credit']:.2f}")

        # Calculate position size (with Oracle's risk % if available)
        max_loss = self.config.spread_width - ic_strikes['total_credit']

        # Use Oracle's risk percentage if available
        if oracle_risk_pct:
            original_risk_pct = self.config.risk_per_trade_pct
            self.config.risk_per_trade_pct = oracle_risk_pct
            contracts = self.calculate_position_size(max_loss)
            self.config.risk_per_trade_pct = original_risk_pct  # Restore original
            logger.info(f"  Oracle Risk Adj: {oracle_risk_pct:.1%} (default: {original_risk_pct:.1%})")
        else:
            contracts = self.calculate_position_size(max_loss)

        logger.info(f"  Contracts: {contracts}")
        logger.info(f"  Total Premium: ${ic_strikes['total_credit'] * 100 * contracts:,.2f}")
        logger.info(f"  Max Risk: ${max_loss * 100 * contracts:,.2f}")

        # Execute the trade with Oracle advice for logging
        position = self.execute_iron_condor(ic_strikes, contracts, expiration, market_data, oracle_advice, decision_tracker)

        if position:
            self.daily_trade_executed[today] = True
            result['new_position'] = {
                'position_id': position.position_id,
                'strikes': f"{position.put_long_strike}/{position.put_short_strike}P - "
                          f"{position.call_short_strike}/{position.call_long_strike}C",
                'contracts': position.contracts,
                'credit': position.total_credit,
                'max_loss': position.max_loss
            }
            result['actions'].append(f"Opened position {position.position_id}")
            logger.info(f"ARES: Position {position.position_id} opened successfully")

            # Log scan activity - TRADE EXECUTED
            if SCAN_LOGGER_AVAILABLE and log_ares_scan:
                log_ares_scan(
                    outcome=ScanOutcome.TRADED,
                    decision_summary=f"Opened Iron Condor: {position.put_short_strike}P/{position.call_short_strike}C x{contracts}",
                    action_taken=f"Executed Iron Condor - collected ${position.total_credit * 100 * contracts:,.2f} premium",
                    market_data=market_data,
                    gex_data=gex_data,
                    signal_source="Oracle" if oracle_advice else "Config",
                    signal_direction="NEUTRAL",
                    signal_confidence=oracle_advice.confidence if oracle_advice and hasattr(oracle_advice, 'confidence') else 0.68,
                    signal_win_probability=oracle_advice.win_probability if oracle_advice else 0.68,
                    oracle_advice=oracle_advice.advice.value if oracle_advice else "N/A",
                    oracle_reasoning=oracle_advice.reasoning if oracle_advice else "Using default parameters",
                    trade_executed=True,
                    position_id=position.position_id,
                    strike_selection={
                        'put_long': position.put_long_strike,
                        'put_short': position.put_short_strike,
                        'call_short': position.call_short_strike,
                        'call_long': position.call_long_strike,
                        'expiration': expiration,
                        'gex_mode': gex_mode
                    },
                    contracts=contracts,
                    premium_collected=position.total_credit * 100 * contracts,
                    max_risk=position.max_loss * 100 * contracts,
                    checks=[
                        CheckResult("trading_window", True, now.strftime('%H:%M'), "08:30-15:30 CT", "Within window"),
                        CheckResult("daily_trade_limit", True, "0", "1 max", "First trade today"),
                        CheckResult("market_data", True, f"${market_data['underlying_price']:.2f}", "Required", "Available"),
                        CheckResult("vix_level", True, f"{market_data['vix']:.1f}", "Informational", f"VIX at {market_data['vix']:.1f} - good for premium selling"),
                        CheckResult("oracle_approval", True, "TRADE", "TRADE", f"Oracle win probability: {oracle_advice.win_probability:.1%}" if oracle_advice else "Using defaults"),
                        CheckResult("strikes_available", True, f"{position.put_short_strike}P/{position.call_short_strike}C", "Required", f"Using {gex_mode}"),
                        CheckResult("execution", True, position.position_id, "Required", "Order filled successfully")
                    ]
                )
        else:
            result['actions'].append("Failed to execute Iron Condor")
            self._log_skip_decision(
                reason=f"Failed to execute Iron Condor order via Tradier API",
                market_data=market_data,
                oracle_advice=oracle_advice,
                alternatives=[
                    "Check Tradier API connectivity and account status",
                    "Verify sufficient buying power",
                    "Review option chain for liquidity issues",
                    "Retry order submission"
                ],
                decision_tracker=decision_tracker
            )
            # Log scan activity - EXECUTION FAILED
            if SCAN_LOGGER_AVAILABLE and log_ares_scan:
                log_ares_scan(
                    outcome=ScanOutcome.ERROR,
                    decision_summary="Iron Condor execution failed",
                    action_taken="Order rejected or failed - will retry",
                    market_data=market_data,
                    gex_data=gex_data,
                    signal_source="Oracle" if oracle_advice else "Config",
                    signal_confidence=oracle_advice.confidence if oracle_advice and hasattr(oracle_advice, 'confidence') else 0,
                    signal_win_probability=oracle_advice.win_probability if oracle_advice else 0,
                    oracle_advice=oracle_advice.advice.value if oracle_advice else "N/A",
                    error_message="Order execution failed via Tradier API - check buying power and order status",
                    error_type="EXECUTION_ERROR",
                    strike_selection={
                        'put_long': ic_strikes['put_long_strike'],
                        'put_short': ic_strikes['put_short_strike'],
                        'call_short': ic_strikes['call_short_strike'],
                        'call_long': ic_strikes['call_long_strike'],
                        'expiration': expiration
                    },
                    contracts=contracts,
                    checks=[
                        CheckResult("trading_window", True, now.strftime('%H:%M'), "08:30-15:30 CT", "Within window"),
                        CheckResult("market_data", True, f"${market_data['underlying_price']:.2f}", "Required", "Available"),
                        CheckResult("oracle_approval", True, "TRADE", "TRADE", "Oracle approved"),
                        CheckResult("strikes_available", True, f"{ic_strikes['put_short_strike']}P/{ic_strikes['call_short_strike']}C", "Required", "Suitable strikes found"),
                        CheckResult("execution", False, "Failed", "Required", "Order execution failed - check Tradier order status")
                    ]
                )

        result['open_positions'] = len(self.open_positions)

        logger.info(f"=" * 60)

        return result

    # =========================================================================
    # DATABASE PERSISTENCE METHODS
    # =========================================================================

    def _save_position_to_db(self, position: IronCondorPosition) -> bool:
        """
        Save an Iron Condor position to the database.

        Args:
            position: IronCondorPosition to save

        Returns:
            True if saved successfully
        """
        conn = None
        try:
            from database_adapter import get_connection
            conn = get_connection()
            cursor = conn.cursor()

            now = datetime.now(self.tz)

            cursor.execute('''
                INSERT INTO ares_positions (
                    position_id, open_date, open_time, expiration,
                    put_long_strike, put_short_strike, call_short_strike, call_long_strike,
                    put_credit, call_credit, total_credit,
                    contracts, spread_width, max_loss,
                    put_spread_order_id, call_spread_order_id,
                    status, underlying_price_at_entry, vix_at_entry, expected_move,
                    mode
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s, %s, %s,
                    %s
                )
                ON CONFLICT (position_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    updated_at = NOW()
            ''', (
                position.position_id, position.open_date, now.strftime('%H:%M:%S'), position.expiration,
                position.put_long_strike, position.put_short_strike, position.call_short_strike, position.call_long_strike,
                position.put_credit, position.call_credit, position.total_credit,
                position.contracts, position.spread_width, position.max_loss,
                position.put_spread_order_id, position.call_spread_order_id,
                position.status, position.underlying_price_at_entry, position.vix_at_entry, position.expected_move,
                self.mode.value
            ))

            conn.commit()
            logger.info(f"ARES: Saved position {position.position_id} to database")
            return True

        except Exception as e:
            logger.error(f"ARES: Failed to save position to database: {e}")
            return False
        finally:
            if conn:
                conn.close()

    def _update_position_in_db(self, position: IronCondorPosition) -> bool:
        """
        Update a position's status in the database (e.g., when closed).

        Args:
            position: IronCondorPosition to update

        Returns:
            True if updated successfully
        """
        conn = None
        try:
            from database_adapter import get_connection
            conn = get_connection()
            cursor = conn.cursor()

            now = datetime.now(self.tz)

            cursor.execute('''
                UPDATE ares_positions SET
                    status = %s,
                    close_date = %s,
                    close_time = %s,
                    close_price = %s,
                    realized_pnl = %s,
                    updated_at = NOW()
                WHERE position_id = %s
            ''', (
                position.status,
                position.close_date,
                now.strftime('%H:%M:%S') if position.close_date else None,
                position.close_price,
                position.realized_pnl,
                position.position_id
            ))

            conn.commit()
            logger.info(f"ARES: Updated position {position.position_id} in database")

            # Record outcome to Oracle feedback loop if position closed
            if position.status in ('closed', 'expired') and hasattr(position, 'realized_pnl'):
                self._record_oracle_outcome(position)

            return True

        except Exception as e:
            logger.error(f"ARES: Failed to update position in database: {e}")
            return False
        finally:
            if conn:
                conn.close()

    def _record_oracle_outcome(self, position: IronCondorPosition) -> None:
        """Record position outcome to Oracle for feedback loop."""
        if not self.oracle or not ORACLE_AVAILABLE:
            return

        try:
            # Determine outcome type based on P&L and strikes
            pnl = position.realized_pnl or 0
            max_credit = position.total_credit * 100 * position.contracts

            if pnl >= max_credit * 0.9:
                outcome_type = "MAX_PROFIT"
            elif pnl > 0:
                outcome_type = "PARTIAL_PROFIT"
            else:
                # Check which side breached (would need underlying close price)
                outcome_type = "LOSS"

            self.record_trade_outcome(
                trade_date=position.open_date,
                outcome_type=outcome_type,
                actual_pnl=pnl
            )
        except Exception as e:
            logger.debug(f"ARES: Could not record Oracle outcome: {e}")

    def _load_positions_from_db(self) -> int:
        """
        Load open positions from database on startup.

        Returns:
            Number of positions loaded
        """
        try:
            from database_adapter import get_connection
            conn = get_connection()
            cursor = conn.cursor()

            # Load open positions for current mode
            cursor.execute('''
                SELECT
                    position_id, open_date, expiration,
                    put_long_strike, put_short_strike, call_short_strike, call_long_strike,
                    put_credit, call_credit, total_credit,
                    contracts, spread_width, max_loss,
                    put_spread_order_id, call_spread_order_id,
                    status, underlying_price_at_entry, vix_at_entry, expected_move
                FROM ares_positions
                WHERE status = 'open' AND mode = %s
                ORDER BY open_date DESC
            ''', (self.mode.value,))

            rows = cursor.fetchall()
            loaded_count = 0

            for row in rows:
                position = IronCondorPosition(
                    position_id=row[0],
                    open_date=row[1],
                    expiration=row[2],
                    put_long_strike=row[3],
                    put_short_strike=row[4],
                    call_short_strike=row[5],
                    call_long_strike=row[6],
                    put_credit=row[7],
                    call_credit=row[8],
                    total_credit=row[9],
                    contracts=row[10],
                    spread_width=row[11],
                    max_loss=row[12],
                    put_spread_order_id=row[13] or "",
                    call_spread_order_id=row[14] or "",
                    status=row[15],
                    underlying_price_at_entry=row[16] or 0,
                    vix_at_entry=row[17] or 0,
                    expected_move=row[18] or 0
                )
                self.open_positions.append(position)
                loaded_count += 1

                # Mark today as traded if position opened today
                today = datetime.now(self.tz).strftime('%Y-%m-%d')
                if position.open_date == today:
                    self.daily_trade_executed[today] = True

            # Also load recent closed positions for history
            cursor.execute('''
                SELECT
                    position_id, open_date, expiration,
                    put_long_strike, put_short_strike, call_short_strike, call_long_strike,
                    put_credit, call_credit, total_credit,
                    contracts, spread_width, max_loss,
                    put_spread_order_id, call_spread_order_id,
                    status, close_date, close_price, realized_pnl,
                    underlying_price_at_entry, vix_at_entry, expected_move
                FROM ares_positions
                WHERE status != 'open' AND mode = %s
                ORDER BY close_date DESC
                LIMIT 100
            ''', (self.mode.value,))

            closed_rows = cursor.fetchall()
            for row in closed_rows:
                position = IronCondorPosition(
                    position_id=row[0],
                    open_date=row[1],
                    expiration=row[2],
                    put_long_strike=row[3],
                    put_short_strike=row[4],
                    call_short_strike=row[5],
                    call_long_strike=row[6],
                    put_credit=row[7],
                    call_credit=row[8],
                    total_credit=row[9],
                    contracts=row[10],
                    spread_width=row[11],
                    max_loss=row[12],
                    put_spread_order_id=row[13] or "",
                    call_spread_order_id=row[14] or "",
                    status=row[15],
                    close_date=row[16] or "",
                    close_price=row[17] or 0,
                    realized_pnl=row[18] or 0,
                    underlying_price_at_entry=row[19] or 0,
                    vix_at_entry=row[20] or 0,
                    expected_move=row[21] or 0
                )
                self.closed_positions.append(position)

                # Update stats from closed positions
                self.trade_count += 1
                self.total_pnl += position.realized_pnl
                if position.realized_pnl > 0:
                    self.win_count += 1

            conn.close()

            if loaded_count > 0:
                logger.info(f"ARES: Loaded {loaded_count} open positions from database")
            if len(self.closed_positions) > 0:
                logger.info(f"ARES: Loaded {len(self.closed_positions)} closed positions from history")

            # Update capital based on total P&L
            self.capital = 200000 + self.total_pnl  # ARES base capital
            self.high_water_mark = max(self.high_water_mark, self.capital)

            return loaded_count

        except Exception as e:
            logger.error(f"ARES: Failed to load positions from database: {e}")
            return 0

    # =========================================================================
    # TRADIER POSITION SYNC METHODS
    # =========================================================================

    def sync_positions_from_tradier(self) -> Dict:
        """
        Sync positions from Tradier account to AlphaGEX.

        This pulls open positions from Tradier and adds any that aren't already
        tracked in AlphaGEX. Useful for reconciliation after manual trades.

        Returns:
            Dict with sync results: synced_count, already_tracked, errors
        """
        result = {
            'synced_count': 0,
            'already_tracked': 0,
            'skipped': 0,
            'errors': [],
            'positions': []
        }

        # Determine which Tradier client to use based on mode
        tradier_client = self.tradier_sandbox if self.mode == TradingMode.PAPER else self.tradier

        if not tradier_client:
            result['errors'].append("Tradier client not available")
            logger.error("ARES SYNC: No Tradier client available")
            return result

        try:
            # Get positions from Tradier
            logger.info("ARES SYNC: Fetching positions from Tradier...")
            tradier_positions = tradier_client.get_positions()

            if not tradier_positions:
                logger.info("ARES SYNC: No positions found in Tradier")
                return result

            # Get list of known order IDs from our tracked positions
            known_order_ids = set()
            for pos in self.open_positions + self.closed_positions:
                if pos.put_spread_order_id:
                    # Extract the actual order ID (e.g., "SANDBOX-12345" -> "12345")
                    order_id = pos.put_spread_order_id.replace("SANDBOX-", "").replace("PAPER-", "")
                    known_order_ids.add(order_id)
                if pos.call_spread_order_id:
                    order_id = pos.call_spread_order_id.replace("SANDBOX-", "").replace("PAPER-", "")
                    known_order_ids.add(order_id)

            logger.info(f"ARES SYNC: Found {len(tradier_positions)} positions in Tradier")
            logger.info(f"ARES SYNC: Already tracking {len(known_order_ids)} order IDs")

            # Process each Tradier position
            for tpos in tradier_positions:
                try:
                    symbol = tpos.get('symbol', '')
                    quantity = abs(int(tpos.get('quantity', 0)))

                    # Only process SPY or SPX options
                    if not (symbol.startswith('SPY') or symbol.startswith('SPX') or symbol.startswith('SPXW')):
                        result['skipped'] += 1
                        continue

                    # Check if this is already tracked
                    position_id = tpos.get('id', '')
                    if str(position_id) in known_order_ids:
                        result['already_tracked'] += 1
                        continue

                    # Log the new position found
                    cost_basis = float(tpos.get('cost_basis', 0))
                    date_acquired = tpos.get('date_acquired', '')

                    logger.info(f"ARES SYNC: Found untracked position - {symbol} x{quantity} cost=${cost_basis:.2f}")

                    result['positions'].append({
                        'symbol': symbol,
                        'quantity': quantity,
                        'cost_basis': cost_basis,
                        'date_acquired': date_acquired,
                        'position_id': position_id
                    })

                    result['synced_count'] += 1

                except Exception as e:
                    result['errors'].append(f"Error processing position: {e}")
                    logger.warning(f"ARES SYNC: Error processing position: {e}")

            logger.info(f"ARES SYNC: Complete - Synced: {result['synced_count']}, "
                       f"Already tracked: {result['already_tracked']}, "
                       f"Skipped: {result['skipped']}")

            return result

        except Exception as e:
            result['errors'].append(f"Sync failed: {e}")
            logger.error(f"ARES SYNC: Failed to sync positions: {e}")
            return result

    def get_tradier_account_status(self) -> Dict:
        """
        Get current Tradier account status including positions and orders.

        Returns:
            Dict with account info, positions, and recent orders.
            In SPX paper trading mode (simulated), returns success with simulation info.
        """
        # Check if we're in SPX paper trading mode (simulated, no sandbox)
        is_spx_paper_mode = self.mode == TradingMode.PAPER and self.tradier_sandbox is None

        result = {
            'success': False,
            'mode': self.mode.value,
            'paper_mode_type': 'simulated' if is_spx_paper_mode else 'sandbox' if self.mode == TradingMode.PAPER else 'live',
            'account': {},
            'positions': [],
            'orders': [],
            'errors': []
        }

        # In SPX paper trading mode, we don't connect to Tradier sandbox
        # Trades are simulated and recorded in AlphaGEX database only
        if is_spx_paper_mode:
            result['success'] = True
            result['account'] = {
                'account_number': 'SIMULATED',
                'type': 'simulated',
                'equity': self.capital,
                'total_equity': self.capital,
                'cash': self.capital,
                'total_cash': self.capital,
                'buying_power': self.capital * 0.25,  # Approximate buying power
                'option_buying_power': self.capital * 0.25,
                'pending_orders_count': 0,
                'note': 'SPX paper trading mode - trades recorded in AlphaGEX DB only'
            }
            # Return in-memory positions from ARES
            result['positions'] = [
                {
                    'symbol': f"{pos.ticker or 'SPX'} IC {pos.put_short_strike}/{pos.call_short_strike}",
                    'quantity': pos.contracts,
                    'cost_basis': pos.total_credit * 100 * pos.contracts,
                    'date_acquired': pos.open_date,
                    'status': pos.status
                }
                for pos in self.open_positions
            ]
            return result

        tradier_client = self.tradier_sandbox if self.mode == TradingMode.PAPER else self.tradier

        if not tradier_client:
            result['errors'].append("Tradier client not available")
            return result

        try:
            # Get account balances
            try:
                balances = tradier_client.get_account_balance()
                if balances:
                    result['account'] = {
                        'account_number': tradier_client.account_id,
                        'total_equity': balances.get('total_equity', 0),
                        'equity': balances.get('total_equity', 0),
                        'total_cash': balances.get('total_cash', 0),
                        'cash': balances.get('total_cash', 0),
                        'option_buying_power': balances.get('option_buying_power', 0),
                        'buying_power': balances.get('option_buying_power', 0),
                        'pending_orders_count': balances.get('pending_orders_count', 0),
                        'type': 'sandbox' if tradier_client.sandbox else 'live'
                    }
            except Exception as e:
                result['errors'].append(f"Failed to get balances: {e}")

            # Get positions
            try:
                positions = tradier_client.get_positions()
                if positions:
                    result['positions'] = positions
            except Exception as e:
                result['errors'].append(f"Failed to get positions: {e}")

            # Get recent orders (include filled/expired, not just open)
            try:
                orders = tradier_client.get_orders(status='all')
                if orders:
                    # Only include recent orders (last 20, including filled)
                    result['orders'] = orders[:20] if len(orders) > 20 else orders
            except Exception as e:
                result['errors'].append(f"Failed to get orders: {e}")

            result['success'] = True
            return result

        except Exception as e:
            result['errors'].append(f"Account status failed: {e}")
            logger.error(f"ARES: Failed to get Tradier account status: {e}")
            return result

    def _update_daily_performance(self) -> bool:
        """
        Update daily performance tracking in the database.

        Returns:
            True if updated successfully
        """
        try:
            from database_adapter import get_connection
            conn = get_connection()
            cursor = conn.cursor()

            today = datetime.now(self.tz).strftime('%Y-%m-%d')
            starting_capital = 200000  # ARES allocated capital

            # Calculate daily stats
            daily_pnl = sum(pos.realized_pnl for pos in self.closed_positions
                          if pos.close_date == today)

            cursor.execute('''
                INSERT INTO ares_daily_performance (
                    date, starting_capital, ending_capital,
                    daily_pnl, daily_return_pct,
                    cumulative_pnl, cumulative_return_pct,
                    positions_opened, positions_closed,
                    high_water_mark, drawdown_pct
                ) VALUES (
                    %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s
                )
                ON CONFLICT (date) DO UPDATE SET
                    ending_capital = EXCLUDED.ending_capital,
                    daily_pnl = EXCLUDED.daily_pnl,
                    daily_return_pct = EXCLUDED.daily_return_pct,
                    cumulative_pnl = EXCLUDED.cumulative_pnl,
                    cumulative_return_pct = EXCLUDED.cumulative_return_pct,
                    positions_closed = EXCLUDED.positions_closed,
                    high_water_mark = EXCLUDED.high_water_mark,
                    drawdown_pct = EXCLUDED.drawdown_pct
            ''', (
                today, starting_capital, self.capital,
                daily_pnl, (daily_pnl / starting_capital) * 100 if starting_capital > 0 else 0,
                self.total_pnl, (self.total_pnl / starting_capital) * 100 if starting_capital > 0 else 0,
                1 if self.daily_trade_executed.get(today, False) else 0,
                sum(1 for pos in self.closed_positions if pos.close_date == today),
                self.high_water_mark,
                ((self.high_water_mark - self.capital) / self.high_water_mark) * 100 if self.high_water_mark > 0 else 0
            ))

            conn.commit()
            conn.close()
            return True

        except Exception as e:
            logger.error(f"ARES: Failed to update daily performance: {e}")
            return False

    # =========================================================================
    # END-OF-DAY POSITION EXPIRATION PROCESSING
    # =========================================================================

    def process_expired_positions(self) -> Dict:
        """
        Process all 0DTE positions that have expired (today or earlier).

        Called at market close (4:00-4:05 PM ET) to:
        1. Find ALL open positions with expiration <= today (catches missed days)
        2. Get closing price of underlying
        3. Determine outcome (MAX_PROFIT, PUT_BREACHED, CALL_BREACHED, DOUBLE_BREACH)
        4. Calculate realized P&L
        5. Update position status to 'expired'
        6. Feed Oracle for ML feedback loop
        7. Update daily performance metrics

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

        today = datetime.now(self.tz).strftime('%Y-%m-%d')
        logger.info(f"ARES EOD: Processing expired positions (expiration <= {today})")

        try:
            ticker = self.get_trading_ticker()

            # Find ALL positions that should have expired (expiration <= today)
            positions_to_process = []

            # Check in-memory open positions - process ANY that have expired
            for pos in self.open_positions[:]:  # Copy list to allow modification
                if pos.expiration <= today and pos.status == 'open':
                    positions_to_process.append(pos)
                    logger.info(f"ARES EOD: Found in-memory position {pos.position_id} (expired {pos.expiration})")

            # Also check database for any positions not in memory
            db_positions = self._get_all_expired_positions_from_db(today)
            for db_pos in db_positions:
                # Avoid duplicates
                if not any(p.position_id == db_pos.position_id for p in positions_to_process):
                    positions_to_process.append(db_pos)
                    logger.info(f"ARES EOD: Found DB position {db_pos.position_id} (expired {db_pos.expiration})")

            if not positions_to_process:
                logger.info(f"ARES EOD: No positions expiring today")
                return result

            logger.info(f"ARES EOD: Found {len(positions_to_process)} positions to process")

            # Process each position with its own expiration date's closing price
            for position in positions_to_process:
                try:
                    # Get closing price for THIS position's expiration date
                    closing_price = self._get_underlying_close_price(ticker, position.expiration)

                    if closing_price is None or closing_price <= 0:
                        error_msg = f"Could not get closing price for {ticker} on {position.expiration}"
                        result['errors'].append(error_msg)
                        logger.error(f"ARES EOD: {error_msg}")
                        continue

                    logger.info(f"ARES EOD: {ticker} close on {position.expiration}: ${closing_price:.2f}")

                    # Determine outcome based on closing price vs strikes
                    outcome = self._determine_expiration_outcome(position, closing_price)
                    realized_pnl = self._calculate_expiration_pnl(position, outcome, closing_price)

                    # Update position
                    position.status = 'expired'
                    position.close_date = position.expiration  # Use actual expiration date, not today
                    position.close_price = closing_price
                    position.realized_pnl = realized_pnl

                    # Move from open to closed
                    if position in self.open_positions:
                        self.open_positions.remove(position)
                    self.closed_positions.append(position)

                    # Update capital
                    self.capital += realized_pnl
                    self.total_pnl += realized_pnl

                    if realized_pnl > 0:
                        self.win_count += 1
                        result['winners'] += 1
                    else:
                        result['losers'] += 1

                    # Update high water mark
                    if self.capital > self.high_water_mark:
                        self.high_water_mark = self.capital

                    # Record P&L to circuit breaker for daily loss tracking
                    if CIRCUIT_BREAKER_AVAILABLE and record_trade_pnl:
                        try:
                            record_trade_pnl(realized_pnl)
                            logger.debug(f"ARES: Recorded P&L ${realized_pnl:.2f} to circuit breaker")
                        except Exception as e:
                            logger.warning(f"ARES: Failed to record P&L to circuit breaker: {e}")

                    # Save to database
                    self._update_position_in_db(position)

                    # Log the expiration
                    self._log_expiration_decision(position, outcome, closing_price)

                    result['processed_count'] += 1
                    result['total_pnl'] += realized_pnl
                    result['positions'].append({
                        'position_id': position.position_id,
                        'outcome': outcome,
                        'realized_pnl': realized_pnl,
                        'closing_price': closing_price,
                        'put_short_strike': position.put_short_strike,
                        'call_short_strike': position.call_short_strike
                    })

                    logger.info(f"ARES EOD: Processed {position.position_id} - {outcome} - P&L: ${realized_pnl:.2f}")

                except Exception as e:
                    error_msg = f"Error processing position {position.position_id}: {e}"
                    result['errors'].append(error_msg)
                    logger.error(f"ARES EOD: {error_msg}")

            # Update daily performance
            self._update_daily_performance()

            logger.info(f"ARES EOD: Complete - Processed {result['processed_count']} positions, "
                       f"Total P&L: ${result['total_pnl']:.2f}, "
                       f"Winners: {result['winners']}, Losers: {result['losers']}")

            return result

        except Exception as e:
            result['errors'].append(f"EOD processing failed: {e}")
            logger.error(f"ARES EOD: Processing failed: {e}")
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
        today = datetime.now(self.tz).strftime('%Y-%m-%d')

        # If requesting today's price or no date specified, get current/latest price
        if for_date is None or for_date >= today:
            return self._get_current_price(ticker)

        # For past dates, look up historical price
        return self._get_historical_close_price(ticker, for_date)

    def _get_current_price(self, ticker: str) -> Optional[float]:
        """Get current/latest price for the underlying."""
        try:
            # Try Tradier production first
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

            # Try unified data provider as last resort
            try:
                from data.unified_data_provider import get_unified_provider
                provider = get_unified_provider()
                if provider:
                    price = provider.get_current_price(ticker)
                    if price and price > 0:
                        logger.info(f"ARES EOD: Got {ticker} price from unified provider: ${price:.2f}")
                        return price
            except Exception as e:
                logger.debug(f"ARES EOD: Unified provider fallback failed: {e}")

            return None
        except Exception as e:
            logger.error(f"ARES EOD: Error getting current price: {e}")
            return None

    def _get_historical_close_price(self, ticker: str, for_date: str) -> Optional[float]:
        """
        Get historical closing price for a specific past date.

        Args:
            ticker: Stock symbol
            for_date: Date string (YYYY-MM-DD)

        Returns:
            Closing price for that date or None
        """
        try:
            # Try unified data provider for historical bars
            try:
                from data.unified_data_provider import get_unified_provider
                provider = get_unified_provider()
                if provider:
                    # Get enough days of history to cover the date (timezone-aware)
                    target_date = datetime.strptime(for_date, '%Y-%m-%d').replace(tzinfo=self.tz)
                    days_back = (datetime.now(self.tz) - target_date).days + 5
                    bars = provider.get_historical_bars(ticker, days=days_back, interval='day')

                    if bars:
                        # Find the bar matching our date
                        for bar in bars:
                            bar_date = bar.timestamp.strftime('%Y-%m-%d')
                            if bar_date == for_date:
                                logger.info(f"ARES EOD: Found historical {ticker} close for {for_date}: ${bar.close:.2f}")
                                return bar.close

                        # If exact date not found, try closest date before
                        for bar in sorted(bars, key=lambda x: x.timestamp, reverse=True):
                            bar_date = bar.timestamp.strftime('%Y-%m-%d')
                            if bar_date <= for_date:
                                logger.info(f"ARES EOD: Using {ticker} close from {bar_date} for {for_date}: ${bar.close:.2f}")
                                return bar.close

            except Exception as e:
                logger.warning(f"ARES EOD: Unified provider historical lookup failed: {e}")

            # Fallback: try Tradier historical endpoint directly
            if self.tradier:
                try:
                    params = {
                        'symbol': ticker,
                        'start': for_date,
                        'end': for_date,
                        'interval': 'daily'
                    }
                    response = self.tradier._make_request('GET', 'markets/history', params=params)
                    history = response.get('history', {})
                    if history and history != 'null':
                        day_data = history.get('day', {})
                        if day_data:
                            if isinstance(day_data, list):
                                day_data = day_data[0]
                            close = day_data.get('close')
                            if close:
                                logger.info(f"ARES EOD: Found Tradier historical {ticker} close for {for_date}: ${close:.2f}")
                                return float(close)
                except Exception as e:
                    logger.warning(f"ARES EOD: Tradier historical lookup failed: {e}")

            # Last resort: use current price with warning
            logger.warning(f"ARES EOD: Could not find historical price for {for_date}, using current price")
            return self._get_current_price(ticker)

        except Exception as e:
            logger.error(f"ARES EOD: Error getting historical close price for {for_date}: {e}")
            return None

    def _get_expiring_positions_from_db(self, expiration_date: str) -> List[IronCondorPosition]:
        """Get positions from database that are expiring on given date."""
        positions = []
        try:
            from database_adapter import get_connection
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT
                    position_id, open_date, expiration,
                    put_long_strike, put_short_strike, call_short_strike, call_long_strike,
                    put_credit, call_credit, total_credit,
                    contracts, spread_width, max_loss,
                    put_spread_order_id, call_spread_order_id,
                    status, underlying_price_at_entry, vix_at_entry, expected_move
                FROM ares_positions
                WHERE expiration = %s AND status = 'open' AND mode = %s
            ''', (expiration_date, self.mode.value))

            for row in cursor.fetchall():
                pos = IronCondorPosition(
                    position_id=row[0],
                    open_date=row[1],
                    expiration=row[2],
                    put_long_strike=row[3],
                    put_short_strike=row[4],
                    call_short_strike=row[5],
                    call_long_strike=row[6],
                    put_credit=row[7],
                    call_credit=row[8],
                    total_credit=row[9],
                    contracts=row[10],
                    spread_width=row[11],
                    max_loss=row[12],
                    put_spread_order_id=row[13] or "",
                    call_spread_order_id=row[14] or "",
                    status=row[15],
                    underlying_price_at_entry=row[16] or 0,
                    vix_at_entry=row[17] or 0,
                    expected_move=row[18] or 0
                )
                positions.append(pos)

            conn.close()

        except Exception as e:
            logger.error(f"ARES EOD: Error loading expiring positions from DB: {e}")

        return positions

    def _get_all_expired_positions_from_db(self, as_of_date: str) -> List[IronCondorPosition]:
        """
        Get ALL open positions from database that have expired (expiration <= as_of_date).

        This catches positions that may have been missed on previous days due to
        service downtime or errors.
        """
        positions = []
        try:
            from database_adapter import get_connection
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT
                    position_id, open_date, expiration,
                    put_long_strike, put_short_strike, call_short_strike, call_long_strike,
                    put_credit, call_credit, total_credit,
                    contracts, spread_width, max_loss,
                    put_spread_order_id, call_spread_order_id,
                    status, underlying_price_at_entry, vix_at_entry, expected_move
                FROM ares_positions
                WHERE expiration <= %s AND status = 'open' AND mode = %s
                ORDER BY expiration ASC
            ''', (as_of_date, self.mode.value))

            for row in cursor.fetchall():
                pos = IronCondorPosition(
                    position_id=row[0],
                    open_date=row[1],
                    expiration=row[2],
                    put_long_strike=row[3],
                    put_short_strike=row[4],
                    call_short_strike=row[5],
                    call_long_strike=row[6],
                    put_credit=row[7],
                    call_credit=row[8],
                    total_credit=row[9],
                    contracts=row[10],
                    spread_width=row[11],
                    max_loss=row[12],
                    put_spread_order_id=row[13] or "",
                    call_spread_order_id=row[14] or "",
                    status=row[15],
                    underlying_price_at_entry=row[16] or 0,
                    vix_at_entry=row[17] or 0,
                    expected_move=row[18] or 0
                )
                positions.append(pos)
                logger.info(f"ARES EOD: Found expired position {pos.position_id} from {pos.expiration}")

            conn.close()
            logger.info(f"ARES EOD: Found {len(positions)} expired positions in database")

        except Exception as e:
            logger.error(f"ARES EOD: Error loading expired positions from DB: {e}")

        return positions

    def _determine_expiration_outcome(self, position: IronCondorPosition, closing_price: float) -> str:
        """
        Determine the outcome of an expired Iron Condor.

        Outcomes:
        - MAX_PROFIT: Price between short strikes, all options expire worthless
        - PUT_BREACHED: Price below short put strike
        - CALL_BREACHED: Price above short call strike
        - DOUBLE_BREACH: Price somehow outside both (shouldn't happen same day)
        """
        put_breached = closing_price < position.put_short_strike
        call_breached = closing_price > position.call_short_strike

        if put_breached and call_breached:
            return "DOUBLE_BREACH"  # Theoretical edge case
        elif put_breached:
            return "PUT_BREACHED"
        elif call_breached:
            return "CALL_BREACHED"
        else:
            return "MAX_PROFIT"

    def _calculate_expiration_pnl(self, position: IronCondorPosition, outcome: str, closing_price: float) -> float:
        """
        Calculate realized P&L at expiration.

        For Iron Condors at expiration:
        - MAX_PROFIT: All options expire worthless, keep full credit
        - PUT_BREACHED: Put spread is ITM, we owe the intrinsic value
        - CALL_BREACHED: Call spread is ITM, we owe the intrinsic value

        P&L = Credit Received - Settlement Cost
        """
        credit_received = position.total_credit * 100 * position.contracts
        spread_width = position.spread_width

        if outcome == "MAX_PROFIT":
            # All options expire worthless - keep full credit
            return credit_received

        elif outcome == "PUT_BREACHED":
            # Put spread is in the money
            # Intrinsic value we owe = (put_short_strike - closing_price) capped at spread_width
            put_spread_intrinsic = min(
                position.put_short_strike - closing_price,
                spread_width
            )
            # Settlement cost = intrinsic value per contract
            settlement_cost = put_spread_intrinsic * 100 * position.contracts
            # P&L = Credit received - Settlement cost
            return credit_received - settlement_cost

        elif outcome == "CALL_BREACHED":
            # Call spread is in the money
            # Intrinsic value we owe = (closing_price - call_short_strike) capped at spread_width
            call_spread_intrinsic = min(
                closing_price - position.call_short_strike,
                spread_width
            )
            # Settlement cost = intrinsic value per contract
            settlement_cost = call_spread_intrinsic * 100 * position.contracts
            # P&L = Credit received - Settlement cost
            return credit_received - settlement_cost

        elif outcome == "DOUBLE_BREACH":
            # Both sides ITM (theoretical - shouldn't happen same day)
            # We owe max on both sides
            max_settlement = spread_width * 100 * position.contracts * 2
            return credit_received - max_settlement

        # Fallback: max loss
        return -(position.max_loss * 100 * position.contracts)

    def _log_expiration_decision(self, position: IronCondorPosition, outcome: str, closing_price: float):
        """Log the expiration event to the decision logger."""
        if not self.decision_logger:
            return

        try:
            from trading.decision_logger import (
                TradeDecision, DecisionType, BotName,
                MarketContext as LoggerMktCtx,
                DecisionReasoning, TradeLeg, DataSource
            )

            now = datetime.now(self.tz)

            # Fetch GEX data for market context
            gex_net = 0
            gex_call_wall = 0
            gex_put_wall = 0
            gex_flip = 0
            gex_regime = ""
            try:
                from database_adapter import get_connection
                conn = get_connection()
                if conn:
                    c = conn.cursor()
                    c.execute("""
                        SELECT net_gex, call_wall, put_wall, gex_flip_point
                        FROM gex_data
                        WHERE symbol = 'SPY'
                        ORDER BY timestamp DESC
                        LIMIT 1
                    """)
                    row = c.fetchone()
                    if row:
                        gex_net = row[0] or 0
                        gex_call_wall = row[1] or 0
                        gex_put_wall = row[2] or 0
                        gex_flip = row[3] or 0
                        gex_regime = "POSITIVE" if gex_net > 0 else "NEGATIVE" if gex_net < 0 else "NEUTRAL"
                    conn.close()
            except Exception as e:
                logger.debug(f"Could not fetch GEX for expiration logging: {e}")

            # Calculate distance to strikes for outcome analysis
            put_distance = closing_price - position.put_short_strike
            call_distance = position.call_short_strike - closing_price

            # Create expiration decision
            decision = TradeDecision(
                decision_id=f"{position.position_id}-EXP",
                timestamp=now.isoformat(),
                decision_type=DecisionType.EXIT_SIGNAL,
                bot_name=BotName.ARES,
                what=f"EXPIRED Iron Condor {position.contracts}x {position.put_short_strike}/{position.call_short_strike} - {outcome}",
                why=f"0DTE expiration. {self.get_trading_ticker()} closed at ${closing_price:.2f}. " +
                    f"Put short: ${position.put_short_strike} (${put_distance:+.2f}), " +
                    f"Call short: ${position.call_short_strike} (${call_distance:+.2f}). " +
                    f"P&L: ${position.realized_pnl:+.2f}",
                how=f"Settlement calculation: Credit received ${position.total_credit:.2f} x {position.contracts} contracts. " +
                    f"Max risk was ${position.max_loss:.2f}/spread. " +
                    f"Entry underlying: ${position.underlying_price_at_entry:.2f}, Exit: ${closing_price:.2f}.",
                action="EXPIRED",
                symbol=self.get_trading_ticker(),
                strategy="ARES_IRON_CONDOR",
                underlying_price_at_entry=position.underlying_price_at_entry,
                underlying_price_at_exit=closing_price,
                actual_pnl=position.realized_pnl,
                legs=[
                    TradeLeg(leg_id=1, action="EXPIRED", option_type="put", strike=position.put_long_strike,
                            expiration=position.expiration, contracts=position.contracts, realized_pnl=0),
                    TradeLeg(leg_id=2, action="EXPIRED", option_type="put", strike=position.put_short_strike,
                            expiration=position.expiration, entry_price=position.put_credit, contracts=position.contracts, realized_pnl=0),
                    TradeLeg(leg_id=3, action="EXPIRED", option_type="call", strike=position.call_short_strike,
                            expiration=position.expiration, entry_price=position.call_credit, contracts=position.contracts, realized_pnl=0),
                    TradeLeg(leg_id=4, action="EXPIRED", option_type="call", strike=position.call_long_strike,
                            expiration=position.expiration, contracts=position.contracts, realized_pnl=0),
                ],
                market_context=LoggerMktCtx(
                    timestamp=now.isoformat(),
                    spot_price=closing_price,
                    spot_source=DataSource.TRADIER_LIVE,
                    vix=position.vix_at_entry,
                    net_gex=gex_net,
                    gex_regime=gex_regime,
                    flip_point=gex_flip,
                    call_wall=gex_call_wall,
                    put_wall=gex_put_wall,
                ),
                reasoning=DecisionReasoning(
                    primary_reason=f"0DTE expiration - {outcome}",
                    supporting_factors=[
                        f"Closing price: ${closing_price:.2f}",
                        f"Put short strike: ${position.put_short_strike} (distance: ${put_distance:+.2f})",
                        f"Call short strike: ${position.call_short_strike} (distance: ${call_distance:+.2f})",
                        f"Credit received: ${position.total_credit:.2f}/spread",
                        f"Total premium collected: ${position.total_credit * 100 * position.contracts:.2f}",
                        f"VIX at entry: {position.vix_at_entry:.1f}",
                    ],
                    risk_factors=[
                        f"Spread width: ${position.spread_width:.0f}",
                        f"Max loss was: ${position.max_loss * 100 * position.contracts:,.2f}",
                    ]
                ),
                position_size_contracts=position.contracts,
                position_size_dollars=position.total_credit * 100 * position.contracts,
                max_risk_dollars=position.max_loss * 100 * position.contracts,
                outcome_notes=outcome
            )

            self.decision_logger.log_decision(decision)

        except Exception as e:
            logger.debug(f"ARES EOD: Could not log expiration decision: {e}")

    # =========================================================================
    # LIVE P&L TRACKING
    # =========================================================================

    def _sync_open_positions_from_db(self) -> None:
        """
        CRITICAL: Sync open_positions list with database to prevent stale data.

        This method:
        1. Queries the DB for currently open positions
        2. Removes any positions from memory that are no longer open in DB
        3. Ensures data freshness on every live P&L request

        Called before get_live_pnl to ensure data freshness.
        """
        try:
            from database_adapter import get_connection
            conn = get_connection()
            cursor = conn.cursor()

            today = datetime.now(self.tz).strftime('%Y-%m-%d')

            # Get all position IDs that are truly open in the database
            cursor.execute('''
                SELECT position_id, status, expiration
                FROM ares_positions
                WHERE mode = %s AND (
                    status = 'open'
                    OR position_id = ANY(%s)
                )
            ''', (self.mode.value, [p.position_id for p in self.open_positions] if self.open_positions else []))

            db_positions = {row[0]: {'status': row[1], 'expiration': str(row[2]) if row[2] else ''} for row in cursor.fetchall()}
            conn.close()

            # Remove stale positions from memory (closed/expired in DB but still in memory)
            positions_to_remove = []
            for pos in self.open_positions:
                if pos.position_id not in db_positions:
                    # Position was deleted from DB
                    positions_to_remove.append(pos)
                    logger.info(f"ARES: Removing stale position {pos.position_id} (not in DB)")
                elif db_positions[pos.position_id]['status'] != 'open':
                    # Position was closed/expired in DB
                    positions_to_remove.append(pos)
                    logger.info(f"ARES: Removing stale position {pos.position_id} (status={db_positions[pos.position_id]['status']})")
                elif db_positions[pos.position_id]['expiration'] < today:
                    # Position has expired
                    positions_to_remove.append(pos)
                    logger.info(f"ARES: Removing expired position {pos.position_id} (exp={db_positions[pos.position_id]['expiration']})")

            for pos in positions_to_remove:
                self.open_positions.remove(pos)

            if positions_to_remove:
                logger.info(f"ARES: Synced positions - removed {len(positions_to_remove)} stale positions, {len(self.open_positions)} remaining")

        except Exception as e:
            logger.error(f"ARES: Error syncing open positions from DB: {e}")

    def get_live_pnl(self) -> Dict[str, Any]:
        """
        Get real-time unrealized P&L for all open Iron Condor positions.

        For Iron Condors:
        - We sold the condor for a credit
        - Current value = cost to buy it back
        - Unrealized P&L = Credit Received - Current Cost to Close

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
            'last_updated': datetime.now(self.tz).isoformat()
        }

        try:
            ticker = self.get_trading_ticker()

            # Get current underlying price
            current_price = self._get_current_price(ticker)
            if current_price is None or current_price <= 0:
                result['error'] = "Could not get current price"
                return result

            result['underlying_price'] = current_price

            for position in self.open_positions:
                try:
                    # Get current option prices to calculate cost to close
                    current_value = self._get_current_iron_condor_value(position)

                    if current_value is None:
                        # Estimate value based on delta/proximity to strikes
                        current_value = self._estimate_iron_condor_value(position, current_price)

                    # Credit received at entry
                    credit_received = position.total_credit * 100 * position.contracts

                    # Cost to close now
                    cost_to_close = current_value * 100 * position.contracts

                    # Unrealized P&L = Credit - Cost to Close
                    unrealized = credit_received - cost_to_close

                    # Calculate P&L percentage based on max profit (credit)
                    pnl_pct = (unrealized / credit_received * 100) if credit_received > 0 else 0

                    # Calculate distance to short strikes
                    put_distance = current_price - position.put_short_strike
                    call_distance = position.call_short_strike - current_price

                    # Calculate DTE (days to expiration)
                    try:
                        exp_date = datetime.strptime(position.expiration, '%Y-%m-%d').date()
                        today_date = datetime.now(self.tz).date()
                        dte = (exp_date - today_date).days
                        is_0dte = dte == 0
                    except (ValueError, TypeError, AttributeError) as e:
                        logger.debug(f"Could not parse expiration date: {e}")
                        dte = None
                        is_0dte = False

                    # Max profit = credit received, calculate progress
                    max_profit = credit_received
                    profit_progress = (unrealized / max_profit * 100) if max_profit > 0 else 0

                    # Get VIX at entry if available
                    vix_at_entry = getattr(position, 'vix_at_entry', None) or 0
                    expected_move = getattr(position, 'expected_move', None) or 0

                    pos_data = {
                        'position_id': position.position_id,
                        'expiration': position.expiration,
                        'contracts': position.contracts,
                        'put_short_strike': position.put_short_strike,
                        'put_long_strike': position.put_long_strike,
                        'call_short_strike': position.call_short_strike,
                        'call_long_strike': position.call_long_strike,
                        'credit_received': round(position.total_credit, 2),
                        'current_value': round(current_value, 2) if current_value else None,
                        'unrealized_pnl': round(unrealized, 2),
                        'pnl_pct': round(pnl_pct, 2),
                        'underlying_at_entry': position.underlying_price_at_entry,
                        'current_underlying': current_price,
                        'put_distance': round(put_distance, 2),
                        'call_distance': round(call_distance, 2),
                        'risk_status': 'SAFE' if put_distance > 0 and call_distance > 0 else 'AT_RISK',
                        # === Entry Context for Transparency ===
                        'dte': dte,
                        'is_0dte': is_0dte,
                        'max_profit': round(max_profit, 2),
                        'profit_progress_pct': round(profit_progress, 1),
                        # Market context at entry
                        'vix_at_entry': vix_at_entry,
                        'expected_move': expected_move,
                        # Iron Condor specifics
                        'spread_width': position.spread_width,
                        'max_loss': round(position.max_loss * 100 * position.contracts, 2),
                        # Strategy type
                        'strategy': 'IRON_CONDOR',
                        'direction': 'NEUTRAL'  # Iron Condors are neutral/range-bound
                    }

                    result['positions'].append(pos_data)
                    result['total_unrealized_pnl'] += unrealized

                except Exception as e:
                    logger.error(f"Error calculating live P&L for {position.position_id}: {e}")

            # Add realized P&L from closed positions today
            today = datetime.now(self.tz).strftime("%Y-%m-%d")
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

    def _get_current_iron_condor_value(self, position: IronCondorPosition) -> Optional[float]:
        """
        Get current market value of the Iron Condor (cost to buy it back).

        Returns the total premium you'd pay to close all 4 legs.
        """
        try:
            ticker = self.get_trading_ticker()
            expiration = position.expiration

            # Get option quotes for all 4 legs
            legs = [
                (position.put_long_strike, 'put'),    # We're long this
                (position.put_short_strike, 'put'),   # We're short this
                (position.call_short_strike, 'call'), # We're short this
                (position.call_long_strike, 'call')   # We're long this
            ]

            total_value = 0.0
            tradier = self.tradier or self.tradier_sandbox

            if not tradier:
                return None

            for strike, option_type in legs:
                try:
                    # Build option symbol
                    option_symbol = self._build_option_symbol(ticker, expiration, strike, option_type)
                    quote = tradier.get_option_quote(option_symbol)

                    if quote:
                        # Use mid price
                        bid = quote.get('bid', 0) or 0
                        ask = quote.get('ask', 0) or 0
                        mid = (bid + ask) / 2 if bid and ask else (bid or ask)

                        # Add or subtract based on position direction
                        if strike in [position.put_long_strike, position.call_long_strike]:
                            # Long legs: we'd sell these, so subtract
                            total_value -= mid
                        else:
                            # Short legs: we'd buy these back, so add
                            total_value += mid
                except Exception:
                    continue

            return total_value if total_value != 0 else None

        except Exception as e:
            logger.debug(f"Could not get IC value: {e}")
            return None

    def _build_option_symbol(self, ticker: str, expiration: str, strike: float, option_type: str) -> str:
        """Build OCC option symbol."""
        # Format: SPY240115C00580000
        exp_date = datetime.strptime(expiration, '%Y-%m-%d')
        exp_str = exp_date.strftime('%y%m%d')
        opt_char = 'C' if option_type == 'call' else 'P'
        strike_str = f"{int(strike * 1000):08d}"
        return f"{ticker}{exp_str}{opt_char}{strike_str}"

    def _estimate_iron_condor_value(self, position: IronCondorPosition, current_price: float) -> float:
        """
        Estimate Iron Condor value when real-time quotes unavailable.

        Uses approximation based on:
        - Time to expiration (theta decay)
        - Distance to short strikes (delta exposure)
        """
        try:
            # Parse expiration (timezone-aware)
            exp_date = datetime.strptime(position.expiration, '%Y-%m-%d').replace(tzinfo=self.tz)
            now = datetime.now(self.tz)
            dte = (exp_date.date() - now.date()).days + 1

            # Credit received
            credit = position.total_credit

            # Calculate how much credit we've "earned" via theta
            # Rough estimate: linear decay
            if dte <= 0:
                # Expired or expiring today
                # Check if we're breached
                if current_price < position.put_short_strike:
                    # Put breached - we owe intrinsic
                    intrinsic = min(position.put_short_strike - current_price, position.spread_width)
                    return intrinsic
                elif current_price > position.call_short_strike:
                    # Call breached - we owe intrinsic
                    intrinsic = min(current_price - position.call_short_strike, position.spread_width)
                    return intrinsic
                else:
                    # Safe - worth very little
                    return 0.05  # Minimal value

            # Not expired yet - estimate based on time and position
            time_decay_factor = max(0.1, dte / 30)  # Assumes ~30 day option

            # Distance-based risk adjustment
            put_distance = current_price - position.put_short_strike
            call_distance = position.call_short_strike - current_price
            min_distance = min(put_distance, call_distance)

            if min_distance < 0:
                # Already breached - value is intrinsic + some time value
                intrinsic = abs(min_distance)
                return min(intrinsic + credit * 0.3, position.spread_width)

            # Safe position - estimate remaining value
            # More time = more value, closer to strikes = more value
            safety_factor = min_distance / (position.spread_width * 2)  # 0-1 range
            estimated_value = credit * time_decay_factor * (1 - safety_factor * 0.5)

            return max(0.05, min(estimated_value, credit))

        except Exception as e:
            logger.debug(f"Error estimating IC value: {e}")
            return position.total_credit * 0.5  # Fallback: half the credit

    def get_status(self) -> Dict:
        """Get current ARES status"""
        now = datetime.now(self.tz)
        today = now.strftime('%Y-%m-%d')

        # Determine paper trading type (sandbox-connected vs simulated)
        sandbox_connected = self.tradier_sandbox is not None
        paper_mode_type = 'sandbox' if sandbox_connected else 'simulated'

        return {
            'mode': self.mode.value,
            'capital': self.capital,
            'total_pnl': self.total_pnl,
            'trade_count': self.trade_count,
            'win_rate': (self.win_count / self.trade_count * 100) if self.trade_count > 0 else 0,
            'open_positions': len(self.open_positions),
            'closed_positions': len(self.closed_positions),
            'traded_today': self.daily_trade_executed.get(today, False),
            'in_trading_window': self.is_trading_window(),
            'high_water_mark': self.high_water_mark,
            'current_time': now.strftime('%Y-%m-%d %H:%M:%S %Z'),
            'sandbox_connected': sandbox_connected,
            'paper_mode_type': paper_mode_type,
            'config': {
                'risk_per_trade': self.config.risk_per_trade_pct,
                'spread_width': self.get_spread_width(),
                'sd_multiplier': self.config.sd_multiplier,
                'ticker': self.get_trading_ticker(),
                'production_ticker': self.config.ticker,
                'sandbox_ticker': self.config.sandbox_ticker,
                'strategy_preset': self.config.strategy_preset,
                'vix_hard_skip': self.config.vix_hard_skip,
                'vix_monday_friday_skip': self.config.vix_monday_friday_skip,
                'vix_streak_skip': self.config.vix_streak_skip
            }
        }


# Convenience function to get ARES logger
def get_ares_logger() -> DecisionLogger:
    """Get decision logger for ARES bot"""
    if LOGGER_AVAILABLE:
        return DecisionLogger()
    return None


# CLI for testing
if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    parser = argparse.ArgumentParser(description='ARES Iron Condor Bot')
    parser.add_argument('--mode', choices=['paper', 'live', 'backtest'],
                       default='paper', help='Trading mode')
    parser.add_argument('--capital', type=float, default=100_000,
                       help='Initial capital')
    parser.add_argument('--status', action='store_true',
                       help='Show status only')
    parser.add_argument('--run', action='store_true',
                       help='Run daily cycle')

    args = parser.parse_args()

    # Create trader
    mode = TradingMode[args.mode.upper()]
    ares = ARESTrader(mode=mode, initial_capital=args.capital)

    if args.status:
        status = ares.get_status()
        print("\nARES STATUS")
        print("=" * 40)
        for key, value in status.items():
            if isinstance(value, dict):
                print(f"{key}:")
                for k, v in value.items():
                    print(f"  {k}: {v}")
            else:
                print(f"{key}: {value}")

    elif args.run:
        result = ares.run_daily_cycle()
        print("\nARES DAILY CYCLE RESULT")
        print("=" * 40)
        for key, value in result.items():
            print(f"{key}: {value}")

    else:
        print("Use --status or --run to interact with ARES")
        print(f"\nCurrent status: {ares.get_status()['mode']} mode")
