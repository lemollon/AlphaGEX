"""
Autonomous Trading Scheduler for Render Deployment
Uses APScheduler to run trading logic during market hours
Integrates seamlessly with Streamlit web service

CAPITAL ALLOCATION:
==================
Total Capital: $1,000,000
├── PHOENIX (0DTE SPY/SPX):      $300,000 (30%)
├── ATLAS (SPX Wheel):           $400,000 (40%)
├── ARES (Aggressive IC):        $200,000 (20%)
└── Reserve:                     $100,000 (10%)

TRADING BOTS:
============
- PHOENIX: 0DTE options trading (hourly 10 AM - 3 PM ET)
- ATLAS: SPX Cash-Secured Put Wheel (daily at 10:05 AM ET)
- ARES: Aggressive Iron Condor targeting 10% monthly (every 5 min 8:30 AM - 2:55 PM CT)
- ATHENA: GEX Directional Spreads (every 5 min 8:35 AM - 2:30 PM CT)
- ALL EOD: Process expired positions at 3:01 PM CT (all bots run simultaneously for <5 min reconciliation)
- ARGUS: Gamma Commentary Generation (every 5 min 8:30 AM - 3:00 PM CT)

All bots now scan every 5 minutes for optimal entry timing and log NO_TRADE
decisions with full context when they scan but don't take a trade.

This partitioning provides:
- Aggressive short-term trading via PHOENIX
- Steady premium collection via ATLAS wheel
- High-return strategy via ARES Iron Condors
- Reserve for margin calls and opportunities
"""

# ============================================================================
# CAPITAL ALLOCATION CONFIGURATION
# ============================================================================
CAPITAL_ALLOCATION = {
    'PHOENIX': 250_000,   # 0DTE options trading
    'ATLAS': 300_000,     # SPX wheel strategy
    'ARES': 150_000,      # Aggressive Iron Condor (SPY 0DTE)
    'PEGASUS': 200_000,   # SPX Iron Condor ($10 spreads, weekly)
    'TITAN': 200_000,     # Aggressive SPX Iron Condor ($12 spreads, daily)
    'RESERVE': 100_000,   # Emergency reserve
    'TOTAL': 1_000_000,
}

# ============================================================================

# Try to import APScheduler, but make it optional
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    BackgroundScheduler = None
    CronTrigger = None
    IntervalTrigger = None
    print("Warning: APScheduler not installed. Autonomous trading scheduler will be disabled.")

from core.autonomous_paper_trader import AutonomousPaperTrader
from core_classes_and_engines import TradingVolatilityAPI
from database_adapter import get_connection
from datetime import datetime
from zoneinfo import ZoneInfo

# Texas Central Time - standard timezone for all AlphaGEX operations
CENTRAL_TZ = ZoneInfo("America/Chicago")
import logging
import traceback
from pathlib import Path
import json

# Import ATLAS (SPX Wheel Trader)
try:
    from trading.spx_wheel_system import SPXWheelTrader, TradingMode
    ATLAS_AVAILABLE = True
except ImportError:
    ATLAS_AVAILABLE = False
    SPXWheelTrader = None
    TradingMode = None
    print("Warning: SPXWheelTrader not available. ATLAS bot will be disabled.")

# Import ARES V2 (SPY Iron Condors)
try:
    from trading.ares_v2 import ARESTrader, ARESConfig, TradingMode as ARESTradingMode
    ARES_AVAILABLE = True
except ImportError:
    ARES_AVAILABLE = False
    ARESTrader = None
    ARESConfig = None
    ARESTradingMode = None
    print("Warning: ARES V2 not available. ARES bot will be disabled.")

# Import ATHENA V2 (SPY Directional Spreads)
try:
    from trading.athena_v2 import ATHENATrader, ATHENAConfig, TradingMode as ATHENATradingMode
    ATHENA_AVAILABLE = True
except ImportError:
    ATHENA_AVAILABLE = False
    ATHENATrader = None
    ATHENAConfig = None
    ATHENATradingMode = None
    print("Warning: ATHENA V2 not available. ATHENA bot will be disabled.")

# Import PEGASUS (SPX Iron Condors)
try:
    from trading.pegasus import PEGASUSTrader, PEGASUSConfig, TradingMode as PEGASUSTradingMode
    PEGASUS_AVAILABLE = True
except ImportError:
    PEGASUS_AVAILABLE = False
    PEGASUSTrader = None
    PEGASUSConfig = None
    PEGASUSTradingMode = None
    print("Warning: PEGASUS not available. SPX trading will be disabled.")

# Import ICARUS (Aggressive Directional Spreads - relaxed GEX filters)
try:
    from trading.icarus import ICARUSTrader, ICARUSConfig, TradingMode as ICARUSTradingMode
    ICARUS_AVAILABLE = True
except ImportError:
    ICARUS_AVAILABLE = False
    ICARUSTrader = None
    ICARUSConfig = None
    ICARUSTradingMode = None
    print("Warning: ICARUS not available. Aggressive directional trading will be disabled.")

# Import TITAN (Aggressive SPX Iron Condors - daily trading)
try:
    from trading.titan import TITANTrader, TITANConfig, TradingMode as TITANTradingMode
    TITAN_AVAILABLE = True
except ImportError:
    TITAN_AVAILABLE = False
    TITANTrader = None
    TITANConfig = None
    TITANTradingMode = None
    print("Warning: TITAN not available. Aggressive SPX Iron Condor trading will be disabled.")

# Import mark-to-market utilities for accurate equity snapshots
MTM_AVAILABLE = False
try:
    from trading.mark_to_market import (
        calculate_ic_mark_to_market,
        calculate_spread_mark_to_market,
        build_occ_symbol,
        get_option_quotes_batch,
    )
    MTM_AVAILABLE = True
except ImportError:
    calculate_ic_mark_to_market = None
    calculate_spread_mark_to_market = None
    print("Warning: Mark-to-market not available. Equity snapshots will use trader instance values.")

# Import decision logger for comprehensive logging
try:
    from trading.decision_logger import get_phoenix_logger, get_atlas_logger, get_ares_logger, BotName
    DECISION_LOGGER_AVAILABLE = True
except ImportError:
    DECISION_LOGGER_AVAILABLE = False
    print("Warning: Decision logger not available.")

# Import SOLOMON (Feedback Loop Intelligence System)
try:
    from quant.solomon_feedback_loop import get_solomon, run_feedback_loop
    SOLOMON_AVAILABLE = True
except ImportError:
    SOLOMON_AVAILABLE = False
    get_solomon = None
    run_feedback_loop = None
    print("Warning: Solomon not available. Feedback loop will be disabled.")

# REMOVED: ML Regime Classifier - Oracle is god
# The MLRegimeClassifier import and training code has been removed.
# Oracle decides all trades.
REGIME_CLASSIFIER_AVAILABLE = False

try:
    from quant.gex_directional_ml import GEXDirectionalPredictor
    GEX_DIRECTIONAL_AVAILABLE = True
except ImportError:
    GEX_DIRECTIONAL_AVAILABLE = False
    GEXDirectionalPredictor = None
    print("Warning: GEXDirectionalPredictor not available. Directional ML training will be disabled.")

# Import GEX Probability Models for ARGUS/HYPERION ML training
try:
    from quant.gex_probability_models import GEXSignalGenerator
    GEX_PROBABILITY_MODELS_AVAILABLE = True
except ImportError:
    GEX_PROBABILITY_MODELS_AVAILABLE = False
    GEXSignalGenerator = None
    print("Warning: GEXSignalGenerator not available. GEX ML training will be disabled.")

# Import Auto-Validation System for ML model health monitoring and auto-retrain
try:
    from quant.auto_validation_system import (
        get_auto_validation_system, run_validation, get_validation_status
    )
    AUTO_VALIDATION_AVAILABLE = True
except ImportError:
    AUTO_VALIDATION_AVAILABLE = False
    get_auto_validation_system = None

# Import OracleAdvisor for PHOENIX signal generation and feedback loop
try:
    from quant.oracle_advisor import (
        OracleAdvisor, MarketContext as OracleMarketContext, GEXRegime, TradingAdvice,
        BotName as OracleBotName, TradeOutcome,  # Issue #2: PHOENIX feedback loop
        auto_train as oracle_auto_train  # Migration 023: Feedback loop integration
    )
    ORACLE_AVAILABLE = True
except ImportError:
    ORACLE_AVAILABLE = False
    OracleAdvisor = None
    OracleMarketContext = None
    GEXRegime = None
    TradingAdvice = None
    oracle_auto_train = None

# Import Solomon Enhanced for strategy-level feedback
try:
    from quant.solomon_enhancements import get_solomon_enhanced, SolomonEnhanced
    SOLOMON_ENHANCED_AVAILABLE = True
except ImportError:
    SOLOMON_ENHANCED_AVAILABLE = False
    get_solomon_enhanced = None
    SolomonEnhanced = None
    OracleBotName = None
    TradeOutcome = None
    print("Warning: OracleAdvisor not available for PHOENIX.")
    run_validation = None
    get_validation_status = None
    print("Warning: AutoValidationSystem not available. ML validation will be disabled.")

# Import scan activity logger for comprehensive scan visibility
try:
    from trading.scan_activity_logger import (
        log_ares_scan, log_athena_scan, log_pegasus_scan, log_icarus_scan, log_titan_scan,
        ScanOutcome
    )
    SCAN_ACTIVITY_LOGGER_AVAILABLE = True
    print("✅ Scan activity logger loaded - scans will be logged to database")
except ImportError as e:
    SCAN_ACTIVITY_LOGGER_AVAILABLE = False
    log_ares_scan = None
    log_athena_scan = None
    log_pegasus_scan = None
    log_icarus_scan = None
    log_titan_scan = None
    ScanOutcome = None
    print(f"❌ WARNING: Scan activity logger NOT available: {e}")
    print("   Scans will NOT be logged to the database!")

# Import VIX Hedge Manager for scheduled signal generation
try:
    from core.vix_hedge_manager import get_vix_hedge_manager, VIXHedgeManager
    VIX_HEDGE_AVAILABLE = True
except ImportError:
    VIX_HEDGE_AVAILABLE = False
    get_vix_hedge_manager = None
    VIXHedgeManager = None
    print("Warning: VIX Hedge Manager not available. VIX signal generation will be disabled.")

# Setup logging
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "autonomous_trader.log"

# Configure logging to file (Render persists logs)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()  # Also print to console
    ]
)

logger = logging.getLogger(__name__)


class AutonomousTraderScheduler:
    """Manages background scheduling of autonomous trading operations with persistent state"""

    def __init__(self):
        if not APSCHEDULER_AVAILABLE:
            logger.warning("APScheduler not available - scheduler will not run")
            self.scheduler = None
            self.is_running = False
            return

        self.scheduler = None

        # Ensure all bot tables exist (may run before API initializes them)
        try:
            from db.config_and_database import init_bot_tables
            init_bot_tables()
            logger.info("✅ Bot tables initialized for scheduler")
        except Exception as e:
            logger.warning(f"Bot table initialization skipped: {e}")

        # PHOENIX - 0DTE SPY/SPX Options Trader
        # Capital: $400,000 (40% of total)
        # CRITICAL: Wrap in try-except to prevent scheduler crash if PHOENIX init fails
        self.trader = None
        self.api_client = None
        self.phoenix_oracle = None  # Oracle for PHOENIX signal validation
        try:
            self.trader = AutonomousPaperTrader(
                symbol='SPY',
                capital=CAPITAL_ALLOCATION['PHOENIX']
            )
            self.api_client = TradingVolatilityAPI()
            # Initialize Oracle for PHOENIX signal validation
            if ORACLE_AVAILABLE:
                self.phoenix_oracle = OracleAdvisor()
                logger.info(f"✅ PHOENIX initialized with ${CAPITAL_ALLOCATION['PHOENIX']:,} capital + Oracle")
            else:
                logger.info(f"✅ PHOENIX initialized with ${CAPITAL_ALLOCATION['PHOENIX']:,} capital (no Oracle)")
        except Exception as e:
            logger.error(f"PHOENIX initialization failed: {e}")
            logger.error("Scheduler will continue without PHOENIX - other bots will still run")

        # ATLAS - SPX Cash-Secured Put Wheel Trader
        # Capital: $400,000 (40% of total)
        # LIVE mode: Executes real trades on Tradier (production API for SPX)
        self.atlas_trader = None
        if ATLAS_AVAILABLE:
            try:
                self.atlas_trader = SPXWheelTrader(
                    mode=TradingMode.LIVE,
                    initial_capital=CAPITAL_ALLOCATION['ATLAS']
                )
                logger.info(f"✅ ATLAS initialized with ${CAPITAL_ALLOCATION['ATLAS']:,} capital (LIVE mode - Tradier)")
            except Exception as e:
                logger.warning(f"ATLAS initialization failed: {e}")
                self.atlas_trader = None

        # ARES V2 - SPY Iron Condors (10% monthly target)
        # Capital: Uses AlphaGEX internal capital allocation
        # LIVE mode: Sends orders to Tradier SANDBOX account for testing
        self.ares_trader = None
        if ARES_AVAILABLE:
            try:
                config = ARESConfig(mode=ARESTradingMode.LIVE)
                self.ares_trader = ARESTrader(config=config)
                logger.info(f"✅ ARES V2 initialized (SPY Iron Condors, LIVE mode - Tradier SANDBOX)")
            except Exception as e:
                logger.warning(f"ARES V2 initialization failed: {e}")
                self.ares_trader = None

        # ATHENA V2 - SPY Directional Spreads
        # Uses GEX + ML signals for directional spread trading
        # PAPER mode: Simulated trades with AlphaGEX internal capital, production Tradier for quotes only
        self.athena_trader = None
        if ATHENA_AVAILABLE:
            try:
                config = ATHENAConfig(mode=ATHENATradingMode.PAPER)
                self.athena_trader = ATHENATrader(config=config)
                logger.info(f"✅ ATHENA V2 initialized (SPY Directional Spreads, PAPER mode - AlphaGEX internal)")
            except Exception as e:
                logger.warning(f"ATHENA V2 initialization failed: {e}")
                self.athena_trader = None

        # PEGASUS - SPX Iron Condors ($10 spreads)
        # Uses larger spread widths for SPX index options
        # PAPER mode: Simulated trades with AlphaGEX internal capital, production Tradier for SPX quotes
        self.pegasus_trader = None
        if PEGASUS_AVAILABLE:
            try:
                config = PEGASUSConfig(mode=PEGASUSTradingMode.PAPER)
                self.pegasus_trader = PEGASUSTrader(config=config)
                logger.info(f"✅ PEGASUS initialized (SPX Iron Condors, PAPER mode - AlphaGEX internal)")
            except Exception as e:
                logger.warning(f"PEGASUS initialization failed: {e}")
                self.pegasus_trader = None

        # ICARUS - Aggressive Directional Spreads (relaxed GEX filters)
        # Uses relaxed parameters vs ATHENA: 10% wall filter, 40% min win prob, 4% risk
        # PAPER mode: Simulated trades with AlphaGEX internal capital, production Tradier for quotes
        self.icarus_trader = None
        if ICARUS_AVAILABLE:
            try:
                config = ICARUSConfig(mode=ICARUSTradingMode.PAPER)
                self.icarus_trader = ICARUSTrader(config=config)
                logger.info(f"✅ ICARUS initialized (Aggressive Directional Spreads, PAPER mode - AlphaGEX internal)")
            except Exception as e:
                logger.warning(f"ICARUS initialization failed: {e}")
                self.icarus_trader = None

        # TITAN - Aggressive SPX Iron Condors ($12 spreads, daily trading)
        # Multiple trades per day with relaxed filters vs PEGASUS
        # PAPER mode: Simulated trades with AlphaGEX internal capital, production Tradier for SPX quotes
        self.titan_trader = None
        if TITAN_AVAILABLE:
            try:
                config = TITANConfig(mode=TITANTradingMode.PAPER)
                self.titan_trader = TITANTrader(config=config)
                logger.info(f"✅ TITAN initialized (Aggressive SPX Iron Condors, PAPER mode - AlphaGEX internal)")
            except Exception as e:
                logger.warning(f"TITAN initialization failed: {e}")
                self.titan_trader = None

        # Log capital allocation summary
        logger.info(f"📊 CAPITAL ALLOCATION:")
        logger.info(f"   PHOENIX: ${CAPITAL_ALLOCATION['PHOENIX']:,}")
        logger.info(f"   ATLAS:   ${CAPITAL_ALLOCATION['ATLAS']:,}")
        logger.info(f"   ARES:    ${CAPITAL_ALLOCATION['ARES']:,}")
        logger.info(f"   RESERVE: ${CAPITAL_ALLOCATION['RESERVE']:,}")
        logger.info(f"   TOTAL:   ${CAPITAL_ALLOCATION['TOTAL']:,}")

        self.is_running = False
        self.last_trade_check = None
        self.last_position_check = None
        self.last_atlas_check = None
        self.last_ares_check = None
        self.last_athena_check = None
        self.last_pegasus_check = None
        self.last_icarus_check = None
        self.last_titan_check = None
        self.last_argus_check = None
        self.last_error = None
        self.execution_count = 0
        self.atlas_execution_count = 0
        self.ares_execution_count = 0
        self.athena_execution_count = 0
        self.pegasus_execution_count = 0
        self.icarus_execution_count = 0
        self.titan_execution_count = 0
        self.argus_execution_count = 0

        # Load saved state from database
        self._load_state()

    def _load_state(self):
        """Load scheduler state from database (PostgreSQL)"""
        conn = None
        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute('''
                SELECT is_running, last_trade_check, last_position_check,
                       execution_count, should_auto_restart, restart_reason
                FROM scheduler_state WHERE id = 1
            ''')

            row = c.fetchone()
            if row:
                was_running, last_trade, last_position, exec_count, should_restart, reason = row
                self.execution_count = exec_count or 0
                self.last_trade_check = last_trade
                self.last_position_check = last_position

                logger.info(f"Loaded scheduler state: was_running={bool(was_running)}, "
                           f"should_restart={bool(should_restart)}, "
                           f"execution_count={self.execution_count}")

                # Auto-restart if it was running before
                if should_restart and was_running:
                    logger.info(f"Previous session detected as running. Reason: {reason or 'App restart'}")
                    return True  # Signal that auto-restart is needed

            return False

        except Exception as e:
            logger.error(f"Error loading scheduler state: {str(e)}")
            return False
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def _save_state(self):
        """Save current scheduler state to database (PostgreSQL)"""
        conn = None
        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute('''
                UPDATE scheduler_state
                SET is_running = %s,
                    last_trade_check = %s,
                    last_position_check = %s,
                    execution_count = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
            ''', (
                1 if self.is_running else 0,
                str(self.last_trade_check) if self.last_trade_check else None,
                str(self.last_position_check) if self.last_position_check else None,
                self.execution_count
            ))

            conn.commit()
            logger.debug("Scheduler state saved to database")

        except Exception as e:
            logger.error(f"Error saving scheduler state: {str(e)}")
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def _mark_auto_restart(self, reason="App restart"):
        """Mark that scheduler should auto-restart on next launch (PostgreSQL)"""
        conn = None
        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute('''
                UPDATE scheduler_state
                SET should_auto_restart = 1,
                    restart_reason = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
            ''', (reason,))

            conn.commit()

        except Exception as e:
            logger.error(f"Error marking auto-restart: {str(e)}")
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def _clear_auto_restart(self):
        """Clear auto-restart flag after successful restart (PostgreSQL)"""
        conn = None
        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute('''
                UPDATE scheduler_state
                SET should_auto_restart = 0,
                    restart_reason = NULL
                WHERE id = 1
            ''')

            conn.commit()

        except Exception as e:
            logger.error(f"Error clearing auto-restart: {str(e)}")
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def get_market_status(self) -> tuple[bool, str]:
        """
        Check market status with detailed reason.

        Returns:
            tuple: (is_open, status) where status is one of:
                - 'OPEN' - Market is open
                - 'BEFORE_WINDOW' - Before trading window (8:30 AM CT)
                - 'AFTER_WINDOW' - After trading window (3:00 PM CT)
                - 'WEEKEND' - Saturday or Sunday
                - 'HOLIDAY' - Market holiday
        """
        now = datetime.now(CENTRAL_TZ)

        # Check if weekend
        if now.weekday() >= 5:  # Saturday=5, Sunday=6
            return False, 'WEEKEND'

        # Check for market holidays (full closure)
        # Using holidays from trading/market_calendar.py
        market_holidays = {
            # 2024
            '2024-01-01', '2024-01-15', '2024-02-19', '2024-03-29',
            '2024-05-27', '2024-06-19', '2024-07-04', '2024-09-02',
            '2024-11-28', '2024-12-25',
            # 2025
            '2025-01-01', '2025-01-20', '2025-02-17', '2025-04-18',
            '2025-05-26', '2025-06-19', '2025-07-04', '2025-09-01',
            '2025-11-27', '2025-12-25',
            # 2026
            '2026-01-01', '2026-01-19', '2026-02-16', '2026-04-03',
            '2026-05-25', '2026-06-19', '2026-07-03', '2026-09-07',
            '2026-11-26', '2026-12-25',
        }
        today_str = now.strftime('%Y-%m-%d')
        if today_str in market_holidays:
            return False, 'HOLIDAY'

        # Check for early close days (1 PM ET = 12 PM CT)
        # - Day before Independence Day (July 3 if weekday)
        # - Day after Thanksgiving (Black Friday)
        # - Christmas Eve (Dec 24 if weekday)
        # - New Year's Eve (Dec 31)
        early_close_dates = {
            # 2024
            '2024-07-03', '2024-11-29', '2024-12-24', '2024-12-31',
            # 2025
            '2025-07-03', '2025-11-28', '2025-12-24', '2025-12-31',
            # 2026
            '2026-07-02', '2026-11-27', '2026-12-24', '2026-12-31',
        }

        # Market hours: 8:30 AM - 3:00 PM CT (or 12:00 PM CT on early close days)
        market_open = now.replace(hour=8, minute=30, second=0, microsecond=0)
        if today_str in early_close_dates:
            market_close = now.replace(hour=12, minute=0, second=0, microsecond=0)
            logger.debug(f"Early close day: market closes at 12:00 PM CT")
        else:
            market_close = now.replace(hour=15, minute=0, second=0, microsecond=0)

        if now < market_open:
            return False, 'BEFORE_WINDOW'
        elif now >= market_close:
            return False, 'AFTER_WINDOW'

        return True, 'OPEN'

    def is_market_open(self) -> bool:
        """Check if US market is currently open (8:30 AM - 3:00 PM CT, Mon-Fri)"""
        is_open, _ = self.get_market_status()
        return is_open

    def scheduled_trade_logic(self):
        """
        Main trading logic executed every hour during market hours
        This is what APScheduler calls on schedule
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"Scheduler triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        # Check if PHOENIX trader is available
        if not self.trader:
            logger.warning("PHOENIX trader not available - skipping")
            self._save_heartbeat('PHOENIX', 'UNAVAILABLE')
            return

        # Double-check market is open (belt and suspenders)
        if not self.is_market_open():
            logger.info("Market is CLOSED. Skipping trade logic.")
            self._save_heartbeat('PHOENIX', 'MARKET_CLOSED')
            return

        logger.info("Market is OPEN. Running autonomous trading logic...")

        try:
            # Step 0: Consult Oracle for trade signal (if available)
            oracle_approved = True  # Default to True if Oracle unavailable
            oracle_prediction = None
            if self.phoenix_oracle and ORACLE_AVAILABLE:
                try:
                    # Get GEX data for Oracle context
                    gex_data = self.api_client.get_gex_data() if self.api_client else {}
                    spot_price = gex_data.get('spot_price', 0)
                    vix = gex_data.get('vix', 20)

                    if spot_price > 0:
                        # Build Oracle context
                        gex_regime_str = gex_data.get('gex_regime', 'NEUTRAL').upper()
                        try:
                            gex_regime = GEXRegime[gex_regime_str] if gex_regime_str in GEXRegime.__members__ else GEXRegime.NEUTRAL
                        except (KeyError, AttributeError):
                            gex_regime = GEXRegime.NEUTRAL

                        context = OracleMarketContext(
                            spot_price=spot_price,
                            vix=vix,
                            gex_put_wall=gex_data.get('put_wall', 0),
                            gex_call_wall=gex_data.get('call_wall', 0),
                            gex_regime=gex_regime,
                            gex_net=gex_data.get('net_gex', 0),
                            gex_flip_point=gex_data.get('flip_point', 0),
                            day_of_week=now.weekday(),
                        )

                        # Get PHOENIX advice from Oracle
                        oracle_prediction = self.phoenix_oracle.get_phoenix_advice(
                            context=context,
                            use_claude_validation=True  # Enable Claude for transparency logging
                        )

                        if oracle_prediction:
                            logger.info(f"PHOENIX Oracle: {oracle_prediction.advice.value} "
                                       f"(win_prob={oracle_prediction.win_probability:.1%})")

                            # =========================================================
                            # Issue #2 fix: Store PHOENIX prediction in Oracle feedback loop
                            # This enables Oracle to learn from PHOENIX outcomes
                            # =========================================================
                            try:
                                trade_date = now.strftime('%Y-%m-%d')
                                self.phoenix_oracle.store_prediction(
                                    prediction=oracle_prediction,
                                    context=context,
                                    trade_date=trade_date
                                )
                                logger.info(f"PHOENIX: Stored Oracle prediction for feedback loop (date={trade_date})")
                            except Exception as store_e:
                                logger.warning(f"PHOENIX: Failed to store prediction: {store_e}")

                            # Oracle must approve with at least TRADE_REDUCED advice
                            if oracle_prediction.advice in [TradingAdvice.SKIP_TODAY, TradingAdvice.STAY_OUT]:
                                oracle_approved = False
                                logger.info(f"PHOENIX Oracle says SKIP: {oracle_prediction.reasoning}")
                                self._log_no_trade_decision('PHOENIX', f'Oracle: {oracle_prediction.reasoning}', {
                                    'symbol': 'SPY',
                                    'oracle_advice': oracle_prediction.advice.value,
                                    'win_probability': oracle_prediction.win_probability,
                                    'market': {'spot': spot_price, 'vix': vix, 'time': now.isoformat()}
                                })
                    else:
                        logger.warning("PHOENIX: No spot price for Oracle - proceeding without Oracle validation")
                except Exception as oracle_e:
                    logger.warning(f"PHOENIX Oracle check failed: {oracle_e} - proceeding without Oracle")

            # Skip trading if Oracle says no
            if not oracle_approved:
                self._save_heartbeat('PHOENIX', 'ORACLE_SKIP', {
                    'oracle_advice': oracle_prediction.advice.value if oracle_prediction else 'UNKNOWN',
                    'win_probability': oracle_prediction.win_probability if oracle_prediction else 0
                })
                logger.info("PHOENIX skipping trade due to Oracle advice")
                logger.info(f"=" * 80)
                return

            # Step 1: Find and execute new daily trade (if we haven't traded today)
            logger.info("Step 1: Checking for new trade opportunities...")
            self.last_trade_check = now

            trade_result = self.trader.find_and_execute_daily_trade(self.api_client)

            traded = False
            if trade_result:
                logger.info(f"✓ Trade executed: {trade_result.get('strategy', 'Unknown')}")
                logger.info(f"  Action: {trade_result.get('action', 'N/A')}")
                logger.info(f"  Entry: ${trade_result.get('entry_price', 0):.2f}")
                logger.info(f"  DTE: {trade_result.get('dte', 'N/A')}")
                traded = True
            else:
                logger.info("No new trade today (already traded or no good setups)")
                self._log_no_trade_decision('PHOENIX', 'Already traded today or no good setups', {
                    'symbol': 'SPY',
                    'market': {'time': now.isoformat()}
                })

            # Step 2: Manage existing positions (check stops, take profits, etc.)
            logger.info("Step 2: Managing existing positions...")
            self.last_position_check = now

            management_results = self.trader.auto_manage_positions(self.api_client)

            if management_results:
                logger.info(f"Position management completed:")
                for result in management_results:
                    logger.info(f"  - {result.get('symbol', 'Unknown')}: {result.get('action', 'N/A')}")

                    # =========================================================
                    # Issue #2 fix: Record PHOENIX outcomes in Oracle feedback loop
                    # When positions are closed, record the outcome for ML training
                    # =========================================================
                    if self.phoenix_oracle and ORACLE_AVAILABLE and OracleBotName and TradeOutcome:
                        action = result.get('action', '').upper()
                        pnl = result.get('pnl', 0) or result.get('realized_pnl', 0) or 0

                        # Map action to TradeOutcome
                        outcome = None
                        if 'PROFIT' in action or 'WIN' in action or pnl > 0:
                            outcome = TradeOutcome.MAX_PROFIT if pnl > 100 else TradeOutcome.PARTIAL_PROFIT
                        elif 'STOP' in action or 'LOSS' in action or pnl < 0:
                            outcome = TradeOutcome.LOSS
                        elif 'CLOSE' in action or 'EXIT' in action:
                            outcome = TradeOutcome.PARTIAL_PROFIT if pnl >= 0 else TradeOutcome.LOSS

                        if outcome:
                            try:
                                trade_date = now.strftime('%Y-%m-%d')
                                self.phoenix_oracle.update_outcome(
                                    trade_date=trade_date,
                                    bot_name=OracleBotName.PHOENIX,
                                    outcome=outcome,
                                    actual_pnl=float(pnl),
                                    spot_at_exit=gex_data.get('spot_price', 0) if 'gex_data' in dir() else 0
                                )
                                logger.info(f"PHOENIX: Recorded outcome {outcome.value} (PnL=${pnl:.2f}) for Oracle feedback")
                            except Exception as outcome_e:
                                logger.warning(f"PHOENIX: Failed to record outcome: {outcome_e}")
            else:
                logger.info("No positions to manage or no actions taken")

            # Update execution count
            self.execution_count += 1
            self.last_error = None

            # Save heartbeat and state after each execution
            self._save_heartbeat('PHOENIX', 'TRADED' if traded else 'SCAN_COMPLETE', {
                'scan_number': self.execution_count,
                'traded': traded,
                'positions_managed': len(management_results) if management_results else 0
            })
            self._save_state()

            logger.info(f"Autonomous trading cycle completed successfully (run #{self.execution_count})")
            logger.info(f"=" * 80)

        except Exception as e:
            error_msg = f"ERROR in autonomous trading logic: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())

            self.last_error = {
                'timestamp': now.isoformat(),
                'error': str(e),
                'traceback': traceback.format_exc()
            }

            self._save_heartbeat('PHOENIX', 'ERROR', {'error': str(e)})

            # Don't crash the scheduler - just log and continue
            logger.info("Scheduler will continue despite error")
            logger.info(f"=" * 80)

    def scheduled_atlas_logic(self):
        """
        ATLAS (SPX Wheel) trading logic - runs daily at 9:05 AM CT

        The wheel strategy operates on a weekly basis:
        - Sells cash-secured puts on SPX
        - Manages positions through expiration
        - Rolls when needed
        - Tracks performance vs backtest
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"ATLAS (SPX Wheel) triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.atlas_trader:
            logger.warning("ATLAS trader not available - skipping")
            self._save_heartbeat('ATLAS', 'UNAVAILABLE')
            return

        if not self.is_market_open():
            logger.info("Market is CLOSED. Skipping ATLAS logic.")
            self._save_heartbeat('ATLAS', 'MARKET_CLOSED')
            return

        logger.info("Market is OPEN. Running ATLAS wheel strategy...")

        try:
            self.last_atlas_check = now
            traded = False
            scan_context = {'symbol': 'SPX'}

            # Run the daily wheel cycle
            # This handles: new positions, expiration processing, roll checks
            result = self.atlas_trader.run_daily_cycle()

            if result:
                logger.info(f"ATLAS daily cycle completed:")
                logger.info(f"  SPX Price: ${result.get('spx_price', 0):,.2f}")
                logger.info(f"  Open Positions: {result.get('open_positions', 0)}")
                logger.info(f"  Actions taken: {result.get('actions', [])}")

                scan_context['market'] = {'spx_price': result.get('spx_price', 0)}

                # Log any new positions
                if result.get('new_position'):
                    logger.info(f"  NEW POSITION: {result.get('new_position')}")
                    traded = True

                # Log any rolls
                if result.get('rolls'):
                    for roll in result.get('rolls', []):
                        logger.info(f"  ROLLED: {roll}")
                    traded = True

                # Log any expirations
                if result.get('expirations'):
                    for exp in result.get('expirations', []):
                        logger.info(f"  EXPIRED: {exp}")

                # Log NO_TRADE if no action taken
                if not traded and not result.get('new_position') and not result.get('rolls'):
                    no_trade_reason = result.get('skip_reason', 'No wheel action needed today')
                    self._log_no_trade_decision('ATLAS', no_trade_reason, scan_context)
            else:
                logger.info("ATLAS: No actions taken today")
                self._log_no_trade_decision('ATLAS', 'No result from trading cycle', scan_context)

            self.atlas_execution_count += 1
            self._save_heartbeat('ATLAS', 'TRADED' if traded else 'SCAN_COMPLETE', {
                'scan_number': self.atlas_execution_count,
                'traded': traded,
                'open_positions': result.get('open_positions', 0) if result else 0,
                'spx_price': result.get('spx_price', 0) if result else 0
            })
            logger.info(f"ATLAS cycle #{self.atlas_execution_count} completed successfully")
            logger.info(f"=" * 80)

        except Exception as e:
            error_msg = f"ERROR in ATLAS trading logic: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            self._save_heartbeat('ATLAS', 'ERROR', {'error': str(e)})
            logger.info("ATLAS will continue despite error")
            logger.info(f"=" * 80)

    def scheduled_ares_logic(self):
        """
        ARES V2 (SPY Iron Condor) trading logic - runs every 5 minutes during market hours

        Uses the new modular V2 architecture:
        - Database is single source of truth
        - Clean run_cycle() API
        - Trades SPY Iron Condors with $2 spreads
        """
        now = datetime.now(CENTRAL_TZ)

        # Update last check time IMMEDIATELY for health monitoring
        # (even if we return early due to market closed, the job IS running)
        self.last_ares_check = now

        logger.info(f"=" * 80)
        logger.info(f"ARES V2 (SPY IC) triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.ares_trader:
            logger.warning("ARES V2 trader not available - skipping")
            self._save_heartbeat('ARES', 'UNAVAILABLE')
            # Log to scan_activity for visibility
            if SCAN_ACTIVITY_LOGGER_AVAILABLE and log_ares_scan:
                log_ares_scan(
                    outcome=ScanOutcome.UNAVAILABLE,
                    decision_summary="ARES trader not initialized",
                    generate_ai_explanation=False
                )
            return

        is_open, market_status = self.get_market_status()

        # CRITICAL FIX: Allow position management even after market close
        # ARES needs to close expiring positions up to 15 minutes after market close
        allow_close_only = False
        if not is_open and market_status == 'AFTER_WINDOW':
            # Check if we're within 15 minutes of market close (15:00-15:15 CT)
            market_close = now.replace(hour=15, minute=0, second=0, microsecond=0)
            minutes_after_close = (now - market_close).total_seconds() / 60
            if 0 <= minutes_after_close <= 15:
                # Allow position management but not new entries
                allow_close_only = True
                logger.info(f"ARES: {minutes_after_close:.0f}min after market close - running close-only cycle")

        if not is_open and not allow_close_only:
            # Map market status to appropriate message
            message_mapping = {
                'BEFORE_WINDOW': "Before trading window (8:30 AM CT)",
                'AFTER_WINDOW': "After trading window (3:00 PM CT)",
                'WEEKEND': "Weekend - market closed",
                'HOLIDAY': "Holiday - market closed",
            }
            message = message_mapping.get(market_status, "Market is closed")

            logger.info(f"Market not open ({market_status}). Skipping ARES logic.")
            self._save_heartbeat('ARES', market_status)
            # Log to scan_activity for visibility
            if SCAN_ACTIVITY_LOGGER_AVAILABLE and log_ares_scan and ScanOutcome:
                # Map market status to scan outcome
                outcome_mapping = {
                    'BEFORE_WINDOW': ScanOutcome.BEFORE_WINDOW,
                    'AFTER_WINDOW': ScanOutcome.AFTER_WINDOW,
                    'WEEKEND': ScanOutcome.MARKET_CLOSED,
                    'HOLIDAY': ScanOutcome.MARKET_CLOSED,
                }
                outcome = outcome_mapping.get(market_status, ScanOutcome.MARKET_CLOSED)
                scan_id = log_ares_scan(
                    outcome=outcome,
                    decision_summary=message,
                    generate_ai_explanation=False
                )
                if scan_id:
                    logger.info(f"📝 ARES scan logged to database: {scan_id}")
                else:
                    logger.warning("⚠️ ARES scan_activity logging FAILED - check database connection")
            else:
                logger.warning(f"⚠️ ARES scan NOT logged: SCAN_ACTIVITY_LOGGER_AVAILABLE={SCAN_ACTIVITY_LOGGER_AVAILABLE}")
            return

        try:
            # Run the V2 cycle (close_only mode prevents new entries after market close)
            result = self.ares_trader.run_cycle(close_only=allow_close_only)

            traded = result.get('trade_opened', False)
            closed = result.get('positions_closed', 0)
            action = result.get('action', 'none')

            logger.info(f"ARES V2 cycle completed: {action}")
            if traded:
                logger.info(f"  NEW TRADE OPENED")
            if closed > 0:
                logger.info(f"  Positions closed: {closed}, P&L: ${result.get('realized_pnl', 0):.2f}")
            if result.get('errors'):
                for err in result['errors']:
                    logger.warning(f"  Skip reason: {err}")

            self.ares_execution_count += 1
            self._save_heartbeat('ARES', 'TRADED' if traded else 'SCAN_COMPLETE', {
                'scan_number': self.ares_execution_count,
                'traded': traded,
                'action': action
            })

            # NOTE: Removed duplicate "BACKUP" logging here.
            # The ARES V2 trader.py already logs comprehensive scan activity
            # with full Oracle/ML data via _log_scan_activity().
            # The old backup created duplicate entries with incomplete data
            # (Oracle:0%, ML:0%, Thresh:0%) which caused diagnostic confusion.

            logger.info(f"ARES V2 scan #{self.ares_execution_count} completed")
            logger.info(f"=" * 80)

        except Exception as e:
            logger.error(f"ERROR in ARES V2: {str(e)}")
            logger.error(traceback.format_exc())
            self._save_heartbeat('ARES', 'ERROR', {'error': str(e)})
            # BACKUP: Log to scan_activity in case bot's internal logging failed
            # This ensures we always have visibility into what happened
            if SCAN_ACTIVITY_LOGGER_AVAILABLE and log_ares_scan:
                try:
                    log_ares_scan(
                        outcome=ScanOutcome.ERROR,
                        decision_summary=f"Scheduler-level error: {str(e)[:200]}",
                        error_message=str(e),
                        generate_ai_explanation=False
                    )
                except Exception as log_err:
                    logger.error(f"CRITICAL: Backup scan_activity logging also failed: {log_err}")
            logger.info(f"=" * 80)

    def scheduled_ares_eod_logic(self):
        """
        ARES End-of-Day processing - runs daily at 3:05 PM CT

        Processes expired 0DTE Iron Condor positions:
        - Calculates realized P&L based on closing price
        - Updates position status to 'expired'
        - Feeds Oracle for ML training feedback loop
        - Updates daily performance metrics
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"ARES EOD (End-of-Day) triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.ares_trader:
            logger.warning("ARES trader not available - skipping EOD processing")
            return

        # EOD processing happens after market close, so we don't check is_market_open()
        logger.info("Processing expired ARES positions...")

        try:
            # Run the EOD expiration processing
            result = self.ares_trader.process_expired_positions()

            if result:
                logger.info(f"ARES EOD processing completed:")
                logger.info(f"  Processed: {result.get('processed_count', 0)} positions")
                logger.info(f"  Total P&L: ${result.get('total_pnl', 0):,.2f}")
                logger.info(f"  Winners: {result.get('winners', 0)}")
                logger.info(f"  Losers: {result.get('losers', 0)}")

                # Log individual position results
                for pos_result in result.get('positions', []):
                    logger.info(f"    - {pos_result['position_id']}: {pos_result['outcome']} "
                               f"P&L: ${pos_result['realized_pnl']:.2f}")

                if result.get('errors'):
                    for error in result['errors']:
                        logger.warning(f"    Error: {error}")
            else:
                logger.info("ARES EOD: No positions to process")

            logger.info(f"ARES EOD processing completed successfully")
            logger.info(f"=" * 80)

        except Exception as e:
            error_msg = f"ERROR in ARES EOD processing: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            logger.info("ARES EOD will retry next trading day")
            logger.info(f"=" * 80)

    def scheduled_athena_eod_logic(self):
        """
        ATHENA End-of-Day processing - runs daily at 3:10 PM CT

        Processes expired 0DTE directional spread positions:
        - Calculates realized P&L based on closing price
        - Updates position status to 'expired'
        - Updates daily performance metrics
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"ATHENA EOD (End-of-Day) triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.athena_trader:
            logger.warning("ATHENA trader not available - skipping EOD processing")
            return

        # EOD processing happens after market close, so we don't check is_market_open()
        logger.info("Processing expired ATHENA positions...")

        try:
            # Run the EOD expiration processing
            result = self.athena_trader.process_expired_positions()

            if result:
                logger.info(f"ATHENA EOD processing completed:")
                logger.info(f"  Processed: {result.get('processed_count', 0)} positions")
                logger.info(f"  Total P&L: ${result.get('total_pnl', 0):,.2f}")
                logger.info(f"  Winners: {result.get('winners', 0)}")
                logger.info(f"  Losers: {result.get('losers', 0)}")

                # Log individual position results
                for pos_result in result.get('positions', []):
                    logger.info(f"    - {pos_result['position_id']}: {pos_result['outcome']} "
                               f"({pos_result['spread_type']}) P&L: ${pos_result['realized_pnl']:.2f}")

                if result.get('errors'):
                    for error in result['errors']:
                        logger.warning(f"    Error: {error}")
            else:
                logger.info("ATHENA EOD: No positions to process")

            logger.info(f"ATHENA EOD processing completed successfully")
            logger.info(f"=" * 80)

        except Exception as e:
            error_msg = f"ERROR in ATHENA EOD processing: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            logger.info("ATHENA EOD will retry next trading day")
            logger.info(f"=" * 80)

    def _log_no_trade_decision(self, bot_name: str, reason: str, context: dict = None):
        """Log a NO_TRADE decision to the database for visibility"""
        conn = None
        try:
            conn = get_connection()
            c = conn.cursor()

            now = datetime.now(CENTRAL_TZ)
            decision_id = f"{bot_name}_{now.strftime('%Y%m%d_%H%M%S')}_NO_TRADE"

            # Use bot_decision_logs table (correct table name)
            c.execute('''
                INSERT INTO bot_decision_logs
                (decision_id, bot_name, symbol, decision_type, action, entry_reasoning, timestamp,
                 full_decision)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (decision_id) DO UPDATE SET
                    entry_reasoning = EXCLUDED.entry_reasoning,
                    timestamp = EXCLUDED.timestamp
            ''', (
                decision_id,
                bot_name,
                context.get('symbol', 'SPY') if context else 'SPY',
                'NO_TRADE',
                'SKIP',
                reason,
                now,
                json.dumps({
                    'what': 'Scanned market but did not trade',
                    'why': reason,
                    'how': 'Next scan in 5 minutes',
                    'market': context.get('market', {}) if context else {},
                    'gex': context.get('gex', {}) if context else {},
                    'oracle': context.get('oracle', {}) if context else {},
                    'ml': context.get('ml', {}) if context else {}
                })
            ))

            conn.commit()
            logger.info(f"[HEARTBEAT] {bot_name} NO_TRADE logged: {reason}")
        except Exception as e:
            logger.debug(f"Could not log NO_TRADE decision: {e}")
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def _save_heartbeat(self, bot_name: str, status: str = 'SCAN_COMPLETE', details: dict = None):
        """Save heartbeat to database for dashboard visibility"""
        conn = None
        try:
            conn = get_connection()
            c = conn.cursor()

            now = datetime.now(CENTRAL_TZ)

            # Ensure bot_heartbeats table exists
            c.execute('''
                CREATE TABLE IF NOT EXISTS bot_heartbeats (
                    id SERIAL PRIMARY KEY,
                    bot_name VARCHAR(50) NOT NULL,
                    last_heartbeat TIMESTAMP NOT NULL,
                    status VARCHAR(50) NOT NULL,
                    scan_count INTEGER DEFAULT 0,
                    trades_today INTEGER DEFAULT 0,
                    last_trade_time TIMESTAMP,
                    details JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(bot_name)
                )
            ''')

            c.execute('''
                INSERT INTO bot_heartbeats (bot_name, last_heartbeat, status, scan_count, details)
                VALUES (%s, %s, %s, 1, %s)
                ON CONFLICT (bot_name) DO UPDATE SET
                    last_heartbeat = EXCLUDED.last_heartbeat,
                    status = EXCLUDED.status,
                    scan_count = bot_heartbeats.scan_count + 1,
                    details = EXCLUDED.details
            ''', (bot_name, now, status, json.dumps(details) if details else None))

            conn.commit()
        except Exception as e:
            logger.debug(f"Could not save heartbeat: {e}")
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def scheduled_athena_logic(self):
        """
        ATHENA V2 (SPY Directional Spreads) trading logic - runs every 5 minutes during market hours

        Uses the new modular V2 architecture:
        - Database is single source of truth
        - Clean run_cycle() API
        - Trades SPY Directional Spreads with $2 spreads
        - GEX wall proximity filter for high probability setups
        """
        now = datetime.now(CENTRAL_TZ)

        # Update last check time IMMEDIATELY for health monitoring
        # (even if we return early due to market closed, the job IS running)
        self.last_athena_check = now

        logger.info(f"=" * 80)
        logger.info(f"ATHENA V2 (SPY Spreads) triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.athena_trader:
            logger.warning("ATHENA V2 trader not available - skipping")
            self._save_heartbeat('ATHENA', 'UNAVAILABLE')
            # Log to scan_activity for visibility
            if SCAN_ACTIVITY_LOGGER_AVAILABLE and log_athena_scan:
                log_athena_scan(
                    outcome=ScanOutcome.UNAVAILABLE,
                    decision_summary="ATHENA trader not initialized",
                    generate_ai_explanation=False
                )
            return

        is_open, market_status = self.get_market_status()

        # CRITICAL FIX: Allow position management even after market close
        # ATHENA needs to close expiring positions up to 15 minutes after market close
        allow_close_only = False
        if not is_open and market_status == 'AFTER_WINDOW':
            # Check if we're within 15 minutes of market close (15:00-15:15 CT)
            market_close = now.replace(hour=15, minute=0, second=0, microsecond=0)
            minutes_after_close = (now - market_close).total_seconds() / 60
            if 0 <= minutes_after_close <= 15:
                # Allow position management but not new entries
                allow_close_only = True
                logger.info(f"ATHENA: {minutes_after_close:.0f}min after market close - running close-only cycle")

        if not is_open and not allow_close_only:
            # Map market status to appropriate message
            message_mapping = {
                'BEFORE_WINDOW': "Before trading window (8:30 AM CT)",
                'AFTER_WINDOW': "After trading window (3:00 PM CT)",
                'WEEKEND': "Weekend - market closed",
                'HOLIDAY': "Holiday - market closed",
            }
            message = message_mapping.get(market_status, "Market is closed")

            logger.info(f"Market not open ({market_status}). Skipping ATHENA logic.")
            self._save_heartbeat('ATHENA', market_status)
            # Log to scan_activity for visibility
            if SCAN_ACTIVITY_LOGGER_AVAILABLE and log_athena_scan and ScanOutcome:
                # Map market status to scan outcome
                outcome_mapping = {
                    'BEFORE_WINDOW': ScanOutcome.BEFORE_WINDOW,
                    'AFTER_WINDOW': ScanOutcome.AFTER_WINDOW,
                    'WEEKEND': ScanOutcome.MARKET_CLOSED,
                    'HOLIDAY': ScanOutcome.MARKET_CLOSED,
                }
                outcome = outcome_mapping.get(market_status, ScanOutcome.MARKET_CLOSED)
                log_athena_scan(
                    outcome=outcome,
                    decision_summary=message,
                    generate_ai_explanation=False
                )
            return

        try:
            # Run the V2 cycle (close_only mode prevents new entries after market close)
            result = self.athena_trader.run_cycle(close_only=allow_close_only)

            # ATHENA V2 returns 'trades_opened' (int), not 'trade_opened' (bool)
            traded = result.get('trades_opened', result.get('trade_opened', 0)) > 0
            closed = result.get('trades_closed', result.get('positions_closed', 0))
            action = result.get('action', 'none')

            logger.info(f"ATHENA V2 cycle completed: {action}")
            if traded:
                logger.info(f"  NEW TRADE OPENED")
            if closed > 0:
                logger.info(f"  Positions closed: {closed}, P&L: ${result.get('realized_pnl', 0):.2f}")
            if result.get('errors'):
                for err in result['errors']:
                    logger.warning(f"  Skip reason: {err}")

            self.athena_execution_count += 1
            self._save_heartbeat('ATHENA', 'TRADED' if traded else 'SCAN_COMPLETE', {
                'scan_number': self.athena_execution_count,
                'traded': traded,
                'action': action
            })

            # NOTE: Removed duplicate "BACKUP" logging here.
            # ATHENA V2 trader already logs comprehensive scan activity
            # with full Oracle/ML data via _log_scan_activity().

            logger.info(f"ATHENA V2 scan #{self.athena_execution_count} completed")
            logger.info(f"=" * 80)

        except Exception as e:
            logger.error(f"ERROR in ATHENA V2: {str(e)}")
            logger.error(traceback.format_exc())
            self._save_heartbeat('ATHENA', 'ERROR', {'error': str(e)})
            # BACKUP: Log to scan_activity in case bot's internal logging failed
            if SCAN_ACTIVITY_LOGGER_AVAILABLE and log_athena_scan:
                try:
                    log_athena_scan(
                        outcome=ScanOutcome.ERROR,
                        decision_summary=f"Scheduler-level error: {str(e)[:200]}",
                        error_message=str(e),
                        generate_ai_explanation=False
                    )
                except Exception as log_err:
                    logger.error(f"CRITICAL: Backup scan_activity logging also failed: {log_err}")
            logger.info(f"=" * 80)

    def scheduled_pegasus_logic(self):
        """
        PEGASUS (SPX Iron Condor) trading logic - runs every 5 minutes during market hours

        Uses the new modular architecture:
        - Database is single source of truth
        - Clean run_cycle() API
        - Trades SPX Iron Condors with $10 spreads
        - Uses SPXW weekly options
        """
        now = datetime.now(CENTRAL_TZ)

        # Update last check time IMMEDIATELY for health monitoring
        self.last_pegasus_check = now

        logger.info(f"=" * 80)
        logger.info(f"PEGASUS (SPX IC) triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.pegasus_trader:
            logger.warning("PEGASUS trader not available - skipping")
            self._save_heartbeat('PEGASUS', 'UNAVAILABLE')
            # Log to scan_activity for visibility
            if SCAN_ACTIVITY_LOGGER_AVAILABLE and log_pegasus_scan:
                log_pegasus_scan(
                    outcome=ScanOutcome.UNAVAILABLE,
                    decision_summary="PEGASUS trader not initialized",
                    generate_ai_explanation=False
                )
            return

        is_open, market_status = self.get_market_status()

        # CRITICAL FIX: Allow position management even after market close
        # PEGASUS needs to close expiring positions up to 15 minutes after market close
        # to handle any positions that weren't closed during the 14:50-15:00 window
        allow_close_only = False
        if not is_open and market_status == 'AFTER_WINDOW':
            # Check if we're within 15 minutes of market close (15:00-15:15 CT)
            market_close = now.replace(hour=15, minute=0, second=0, microsecond=0)
            minutes_after_close = (now - market_close).total_seconds() / 60
            if 0 <= minutes_after_close <= 15:
                # Allow position management but not new entries
                allow_close_only = True
                logger.info(f"PEGASUS: {minutes_after_close:.0f}min after market close - running close-only cycle")

        if not is_open and not allow_close_only:
            # Map market status to appropriate message
            message_mapping = {
                'BEFORE_WINDOW': "Before trading window (8:30 AM CT)",
                'AFTER_WINDOW': "After trading window (3:00 PM CT)",
                'WEEKEND': "Weekend - market closed",
                'HOLIDAY': "Holiday - market closed",
            }
            message = message_mapping.get(market_status, "Market is closed")

            logger.info(f"Market not open ({market_status}). Skipping PEGASUS logic.")
            self._save_heartbeat('PEGASUS', market_status)
            # Log to scan_activity for visibility
            if SCAN_ACTIVITY_LOGGER_AVAILABLE and log_pegasus_scan and ScanOutcome:
                # Map market status to scan outcome
                outcome_mapping = {
                    'BEFORE_WINDOW': ScanOutcome.BEFORE_WINDOW,
                    'AFTER_WINDOW': ScanOutcome.AFTER_WINDOW,
                    'WEEKEND': ScanOutcome.MARKET_CLOSED,
                    'HOLIDAY': ScanOutcome.MARKET_CLOSED,
                }
                outcome = outcome_mapping.get(market_status, ScanOutcome.MARKET_CLOSED)
                log_pegasus_scan(
                    outcome=outcome,
                    decision_summary=message,
                    generate_ai_explanation=False
                )
            return

        try:
            # Run the cycle (close_only mode prevents new entries after market close)
            result = self.pegasus_trader.run_cycle(close_only=allow_close_only)

            traded = result.get('trade_opened', False)
            closed = result.get('positions_closed', 0)
            action = result.get('action', 'none')

            logger.info(f"PEGASUS cycle completed: {action}")
            if traded:
                logger.info(f"  NEW TRADE OPENED")
            if closed > 0:
                logger.info(f"  Positions closed: {closed}, P&L: ${result.get('realized_pnl', 0):.2f}")
            if result.get('errors'):
                for err in result['errors']:
                    logger.warning(f"  Skip reason: {err}")

            self.pegasus_execution_count += 1
            self._save_heartbeat('PEGASUS', 'TRADED' if traded else 'SCAN_COMPLETE', {
                'scan_number': self.pegasus_execution_count,
                'traded': traded,
                'action': action
            })

            # NOTE: Removed duplicate "BACKUP" logging here.
            # PEGASUS trader already logs comprehensive scan activity
            # with full Oracle/ML data via its internal logger.

            logger.info(f"PEGASUS scan #{self.pegasus_execution_count} completed")
            logger.info(f"=" * 80)

        except Exception as e:
            logger.error(f"ERROR in PEGASUS: {str(e)}")
            logger.error(traceback.format_exc())
            self._save_heartbeat('PEGASUS', 'ERROR', {'error': str(e)})
            # BACKUP: Log to scan_activity in case bot's internal logging failed
            if SCAN_ACTIVITY_LOGGER_AVAILABLE and log_pegasus_scan:
                try:
                    log_pegasus_scan(
                        outcome=ScanOutcome.ERROR,
                        decision_summary=f"Scheduler-level error: {str(e)[:200]}",
                        error_message=str(e),
                        generate_ai_explanation=False
                    )
                except Exception as log_err:
                    logger.error(f"CRITICAL: Backup scan_activity logging also failed: {log_err}")
            logger.info(f"=" * 80)

    def scheduled_pegasus_eod_logic(self):
        """
        PEGASUS End-of-Day processing - runs daily at 3:15 PM CT

        Processes expired SPX Iron Condor positions:
        - Calculates realized P&L based on closing price
        - Updates position status to 'expired'
        - Updates daily performance metrics
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"PEGASUS EOD triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.pegasus_trader:
            logger.warning("PEGASUS trader not available - skipping EOD processing")
            return

        logger.info("Processing expired PEGASUS positions...")

        try:
            # Force close any remaining open positions
            result = self.pegasus_trader.force_close_all("EOD_EXPIRATION")

            if result:
                logger.info(f"PEGASUS EOD processing completed:")
                logger.info(f"  Closed: {result.get('closed', 0)} positions")
                logger.info(f"  Total P&L: ${result.get('total_pnl', 0):,.2f}")
            else:
                logger.info("PEGASUS EOD: No positions to process")

            logger.info(f"PEGASUS EOD processing completed successfully")
            logger.info(f"=" * 80)

        except Exception as e:
            logger.error(f"ERROR in PEGASUS EOD: {str(e)}")
            logger.error(traceback.format_exc())
            logger.info(f"=" * 80)

    def scheduled_icarus_logic(self):
        """
        ICARUS (Aggressive Directional Spreads) trading logic - runs every 5 minutes during market hours

        ICARUS is an aggressive clone of ATHENA with relaxed GEX filters:
        - 10% wall filter (vs ATHENA's 3%)
        - 40% min win probability (vs ATHENA's 48%)
        - 4% risk per trade (vs ATHENA's 2%)
        - 10 max daily trades (vs ATHENA's 5)
        """
        now = datetime.now(CENTRAL_TZ)

        # Update last check time IMMEDIATELY for health monitoring
        self.last_icarus_check = now

        logger.info(f"=" * 80)
        logger.info(f"ICARUS (Aggressive Spreads) triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.icarus_trader:
            logger.warning("ICARUS trader not available - skipping")
            self._save_heartbeat('ICARUS', 'UNAVAILABLE')
            # Log to scan_activity for visibility
            if SCAN_ACTIVITY_LOGGER_AVAILABLE and log_icarus_scan:
                log_icarus_scan(
                    outcome=ScanOutcome.UNAVAILABLE,
                    decision_summary="ICARUS trader not initialized",
                    generate_ai_explanation=False
                )
            return

        is_open, market_status = self.get_market_status()

        # CRITICAL FIX: Allow position management even after market close
        # ICARUS needs to close expiring positions up to 15 minutes after market close
        allow_close_only = False
        if not is_open and market_status == 'AFTER_WINDOW':
            # Check if we're within 15 minutes of market close (15:00-15:15 CT)
            market_close = now.replace(hour=15, minute=0, second=0, microsecond=0)
            minutes_after_close = (now - market_close).total_seconds() / 60
            if 0 <= minutes_after_close <= 15:
                # Allow position management but not new entries
                allow_close_only = True
                logger.info(f"ICARUS: {minutes_after_close:.0f}min after market close - running close-only cycle")

        if not is_open and not allow_close_only:
            # Map market status to appropriate message
            message_mapping = {
                'BEFORE_WINDOW': "Before trading window (8:30 AM CT)",
                'AFTER_WINDOW': "After trading window (3:00 PM CT)",
                'WEEKEND': "Weekend - market closed",
                'HOLIDAY': "Holiday - market closed",
            }
            message = message_mapping.get(market_status, "Market is closed")

            logger.info(f"Market not open ({market_status}). Skipping ICARUS logic.")
            self._save_heartbeat('ICARUS', market_status)
            # Log to scan_activity for visibility
            if SCAN_ACTIVITY_LOGGER_AVAILABLE and log_icarus_scan and ScanOutcome:
                # Map market status to scan outcome
                outcome_mapping = {
                    'BEFORE_WINDOW': ScanOutcome.MARKET_CLOSED,
                    'AFTER_WINDOW': ScanOutcome.MARKET_CLOSED,
                    'WEEKEND': ScanOutcome.MARKET_CLOSED,
                    'HOLIDAY': ScanOutcome.MARKET_CLOSED,
                }
                outcome = outcome_mapping.get(market_status, ScanOutcome.MARKET_CLOSED)
                log_icarus_scan(
                    outcome=outcome,
                    decision_summary=message,
                    generate_ai_explanation=False
                )
            return

        try:
            # Run the cycle (close_only mode prevents new entries after market close)
            result = self.icarus_trader.run_cycle(close_only=allow_close_only)

            # ICARUS returns 'trades_opened' (int), not 'trade_opened' (bool)
            traded = result.get('trades_opened', result.get('trade_opened', 0)) > 0
            closed = result.get('trades_closed', result.get('positions_closed', 0))
            action = result.get('action', 'none')

            logger.info(f"ICARUS cycle completed: {action}")
            if traded:
                logger.info(f"  NEW TRADE OPENED")
            if closed > 0:
                logger.info(f"  Positions closed: {closed}, P&L: ${result.get('realized_pnl', 0):.2f}")
            if result.get('errors'):
                for err in result['errors']:
                    logger.warning(f"  Skip reason: {err}")

            self.icarus_execution_count += 1
            self._save_heartbeat('ICARUS', 'TRADED' if traded else 'SCAN_COMPLETE', {
                'scan_number': self.icarus_execution_count,
                'traded': traded,
                'action': action
            })

            # NOTE: Removed duplicate "BACKUP" logging here.
            # ICARUS trader already logs comprehensive scan activity
            # with full Oracle/ML data via its internal logger.

            logger.info(f"ICARUS scan #{self.icarus_execution_count} completed")
            logger.info(f"=" * 80)

        except Exception as e:
            logger.error(f"ERROR in ICARUS: {str(e)}")
            logger.error(traceback.format_exc())
            self._save_heartbeat('ICARUS', 'ERROR', {'error': str(e)})
            # BACKUP: Log to scan_activity in case bot's internal logging failed
            if SCAN_ACTIVITY_LOGGER_AVAILABLE and log_icarus_scan:
                try:
                    log_icarus_scan(
                        outcome=ScanOutcome.ERROR,
                        decision_summary=f"Scheduler-level error: {str(e)[:200]}",
                        error_message=str(e),
                        generate_ai_explanation=False
                    )
                except Exception as log_err:
                    logger.error(f"CRITICAL: Backup scan_activity logging also failed: {log_err}")
            logger.info(f"=" * 80)

    def scheduled_icarus_eod_logic(self):
        """
        ICARUS End-of-Day processing - runs daily at 3:12 PM CT

        Processes expired 0DTE directional spread positions:
        - Calculates realized P&L based on closing price
        - Updates position status to 'expired'
        - Updates daily performance metrics
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"ICARUS EOD triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.icarus_trader:
            logger.warning("ICARUS trader not available - skipping EOD processing")
            return

        logger.info("Processing expired ICARUS positions...")

        try:
            # Run the EOD expiration processing
            result = self.icarus_trader.process_expired_positions()

            if result:
                logger.info(f"ICARUS EOD processing completed:")
                logger.info(f"  Processed: {result.get('processed_count', 0)} positions")
                logger.info(f"  Total P&L: ${result.get('total_pnl', 0):,.2f}")

                # Log any warnings/errors
                if result.get('errors'):
                    logger.warning("ICARUS EOD had errors:")
                    for error in result['errors']:
                        logger.warning(f"    Error: {error}")
            else:
                logger.info("ICARUS EOD: No positions to process")

            logger.info(f"ICARUS EOD processing completed successfully")
            logger.info(f"=" * 80)

        except Exception as e:
            error_msg = f"ERROR in ICARUS EOD processing: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            logger.info("ICARUS EOD will retry next trading day")
            logger.info(f"=" * 80)

    def scheduled_titan_logic(self):
        """
        TITAN (Aggressive SPX Iron Condor) trading logic - runs every 5 minutes during market hours

        TITAN is an aggressive clone of PEGASUS with relaxed filters:
        - 40% VIX skip (vs PEGASUS's 32%)
        - 40% min win probability (vs PEGASUS's 50%)
        - 15% risk per trade (vs PEGASUS's 10%)
        - 10 max positions (vs PEGASUS's 5)
        - 0.8 SD multiplier for closer strikes (vs PEGASUS's 1.0)
        - $12 spread widths (vs PEGASUS's $10)
        - 30-minute cooldown for multiple trades per day
        """
        now = datetime.now(CENTRAL_TZ)

        # Update last check time IMMEDIATELY for health monitoring
        self.last_titan_check = now

        logger.info(f"=" * 80)
        logger.info(f"TITAN (Aggressive SPX IC) triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.titan_trader:
            logger.warning("TITAN trader not available - skipping")
            self._save_heartbeat('TITAN', 'UNAVAILABLE')
            # Log to scan_activity for visibility
            if SCAN_ACTIVITY_LOGGER_AVAILABLE and log_titan_scan:
                log_titan_scan(
                    outcome=ScanOutcome.UNAVAILABLE,
                    decision_summary="TITAN trader not initialized",
                    generate_ai_explanation=False
                )
            return

        is_open, market_status = self.get_market_status()

        # CRITICAL FIX: Allow position management even after market close
        # TITAN needs to close expiring positions up to 15 minutes after market close
        allow_close_only = False
        if not is_open and market_status == 'AFTER_WINDOW':
            # Check if we're within 15 minutes of market close (15:00-15:15 CT)
            market_close = now.replace(hour=15, minute=0, second=0, microsecond=0)
            minutes_after_close = (now - market_close).total_seconds() / 60
            if 0 <= minutes_after_close <= 15:
                # Allow position management but not new entries
                allow_close_only = True
                logger.info(f"TITAN: {minutes_after_close:.0f}min after market close - running close-only cycle")

        if not is_open and not allow_close_only:
            # Map market status to appropriate message
            message_mapping = {
                'BEFORE_WINDOW': "Before trading window (8:30 AM CT)",
                'AFTER_WINDOW': "After trading window (3:00 PM CT)",
                'WEEKEND': "Weekend - market closed",
                'HOLIDAY': "Holiday - market closed",
            }
            message = message_mapping.get(market_status, "Market is closed")

            logger.info(f"Market not open ({market_status}). Skipping TITAN logic.")
            self._save_heartbeat('TITAN', market_status)
            # Log to scan_activity for visibility
            if SCAN_ACTIVITY_LOGGER_AVAILABLE and log_titan_scan and ScanOutcome:
                # Map market status to scan outcome
                outcome_mapping = {
                    'BEFORE_WINDOW': ScanOutcome.MARKET_CLOSED,
                    'AFTER_WINDOW': ScanOutcome.MARKET_CLOSED,
                    'WEEKEND': ScanOutcome.MARKET_CLOSED,
                    'HOLIDAY': ScanOutcome.MARKET_CLOSED,
                }
                outcome = outcome_mapping.get(market_status, ScanOutcome.MARKET_CLOSED)
                log_titan_scan(
                    outcome=outcome,
                    decision_summary=message,
                    generate_ai_explanation=False
                )
            return

        try:
            # Run the cycle (close_only mode prevents new entries after market close)
            result = self.titan_trader.run_cycle(close_only=allow_close_only)

            traded = result.get('trade_opened', False)
            closed = result.get('positions_closed', 0)
            action = result.get('action', 'none')

            logger.info(f"TITAN cycle completed: {action}")
            if traded:
                logger.info(f"  NEW TRADE OPENED")
            if closed > 0:
                logger.info(f"  Positions closed: {closed}, P&L: ${result.get('realized_pnl', 0):.2f}")
            if result.get('errors'):
                for err in result['errors']:
                    logger.warning(f"  Skip reason: {err}")

            self.titan_execution_count += 1
            self._save_heartbeat('TITAN', 'TRADED' if traded else 'SCAN_COMPLETE', {
                'scan_number': self.titan_execution_count,
                'traded': traded,
                'action': action
            })

            # NOTE: Removed duplicate "BACKUP" logging here.
            # TITAN trader already logs comprehensive scan activity
            # with full Oracle/ML data via its internal logger.

            logger.info(f"TITAN scan #{self.titan_execution_count} completed")
            logger.info(f"=" * 80)

        except Exception as e:
            logger.error(f"ERROR in TITAN: {str(e)}")
            logger.error(traceback.format_exc())
            self._save_heartbeat('TITAN', 'ERROR', {'error': str(e)})
            # BACKUP: Log to scan_activity in case bot's internal logging failed
            if SCAN_ACTIVITY_LOGGER_AVAILABLE and log_titan_scan:
                try:
                    log_titan_scan(
                        outcome=ScanOutcome.ERROR,
                        decision_summary=f"Scheduler-level error: {str(e)[:200]}",
                        error_message=str(e),
                        generate_ai_explanation=False
                    )
                except Exception as log_err:
                    logger.error(f"CRITICAL: Backup scan_activity logging also failed: {log_err}")
            logger.info(f"=" * 80)

    def scheduled_titan_eod_logic(self):
        """
        TITAN End-of-Day processing - runs daily at 3:17 PM CT

        Processes expired SPX Iron Condor positions:
        - Calculates realized P&L based on closing price
        - Updates position status to 'expired'
        - Updates daily performance metrics
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"TITAN EOD triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.titan_trader:
            logger.warning("TITAN trader not available - skipping EOD processing")
            return

        logger.info("Processing expired TITAN positions...")

        try:
            # Force close any remaining open positions
            result = self.titan_trader.force_close_all("EOD_EXPIRATION")

            if result:
                logger.info(f"TITAN EOD processing completed:")
                logger.info(f"  Closed: {result.get('closed', 0)} positions")
                logger.info(f"  Total P&L: ${result.get('total_pnl', 0):,.2f}")
            else:
                logger.info("TITAN EOD: No positions to process")

            logger.info(f"TITAN EOD processing completed successfully")
            logger.info(f"=" * 80)

        except Exception as e:
            logger.error(f"ERROR in TITAN EOD: {str(e)}")
            logger.error(traceback.format_exc())
            logger.info(f"=" * 80)

    def scheduled_argus_logic(self):
        """
        ARGUS (0DTE Gamma Live) commentary generation - runs every 5 minutes during market hours

        Generates AI-powered market commentary based on current gamma structure:
        - Gamma regime analysis
        - Magnet/pin predictions
        - Danger zone alerts
        - Expected move changes

        Commentary is stored in the argus_commentary table for the Live Log.
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"ARGUS (Commentary) triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.is_market_open():
            logger.info("Market is CLOSED. Skipping ARGUS commentary generation.")
            return

        logger.info("Market is OPEN. Generating ARGUS gamma commentary...")

        try:
            self.last_argus_check = now

            # Call the ARGUS commentary generation endpoint via HTTP
            # This ensures we use the same logic as manual generation
            import requests

            # Try local FastAPI server first, then production
            base_urls = [
                "http://127.0.0.1:8000",
                "https://alphagex-api.onrender.com"
            ]

            result = None
            for base_url in base_urls:
                try:
                    response = requests.post(
                        f"{base_url}/api/argus/commentary/generate",
                        json={"force": False},
                        timeout=60
                    )
                    if response.status_code == 200:
                        result = response.json()
                        logger.info(f"ARGUS: Commentary generated via {base_url}")
                        break
                except requests.exceptions.RequestException as e:
                    logger.debug(f"ARGUS: Could not reach {base_url}: {e}")
                    continue

            if result and result.get('success'):
                data = result.get('data', {})
                commentary = data.get('commentary', '')
                generated_at = data.get('generated_at', '')

                # Log success with preview of commentary
                preview = commentary[:100] + '...' if len(commentary) > 100 else commentary
                logger.info(f"ARGUS commentary generated:")
                logger.info(f"  Time: {generated_at}")
                logger.info(f"  Preview: {preview}")
            else:
                logger.warning("ARGUS: Commentary generation returned no result")

            self.argus_execution_count += 1
            logger.info(f"ARGUS commentary #{self.argus_execution_count} completed (next in 5 min)")
            logger.info(f"=" * 80)

        except Exception as e:
            error_msg = f"ERROR in ARGUS commentary generation: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            logger.info("ARGUS will retry next interval")
            logger.info(f"=" * 80)

    def scheduled_argus_eod_logic(self):
        """
        ARGUS End-of-Day processing - runs daily at 3:01 PM CT

        Updates pin prediction accuracy tracking:
        1. Updates today's pin prediction with actual closing price
        2. Calculates and stores ARGUS prediction accuracy metrics

        This enables the pin accuracy tracking feature to work end-to-end.
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"ARGUS EOD triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        try:
            # Call the ARGUS EOD processing endpoint via HTTP
            import requests

            # Try local FastAPI server first, then production
            base_urls = [
                "http://127.0.0.1:8000",
                "https://alphagex-api.onrender.com"
            ]

            result = None
            for base_url in base_urls:
                try:
                    response = requests.post(
                        f"{base_url}/api/argus/eod-processing?symbol=SPY",
                        timeout=60
                    )
                    if response.status_code == 200:
                        result = response.json()
                        logger.info(f"ARGUS EOD: Processing completed via {base_url}")
                        break
                except requests.exceptions.RequestException as e:
                    logger.debug(f"ARGUS EOD: Could not reach {base_url}: {e}")
                    continue

            if result and result.get('success'):
                data = result.get('data', {})
                actions = data.get('actions', [])
                for action in actions:
                    status = "✓" if action.get('success') else "✗"
                    logger.info(f"  {status} {action.get('action')}: {action.get('description')}")
            else:
                logger.warning("ARGUS EOD: Processing returned no result")

            logger.info(f"ARGUS EOD processing completed")
            logger.info(f"=" * 80)

        except Exception as e:
            error_msg = f"ERROR in ARGUS EOD processing: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            logger.info("ARGUS EOD will retry next trading day")
            logger.info(f"=" * 80)

    def scheduled_vix_signal_logic(self):
        """
        VIX Hedge Signal generation - runs hourly during market hours

        Generates VIX-based hedge signals and saves them to the database for:
        - Signal history tracking on the VIX dashboard
        - Historical analysis of volatility conditions
        - Portfolio protection recommendations

        Signals are stored in vix_hedge_signals table.
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"VIX SIGNAL triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.is_market_open():
            logger.info("Market is CLOSED. Skipping VIX signal generation.")
            return

        logger.info("Market is OPEN. Generating VIX hedge signal...")

        try:
            if not VIX_HEDGE_AVAILABLE:
                logger.warning("VIX Hedge Manager not available. Skipping signal generation.")
                return

            # Get the VIX hedge manager singleton
            manager = get_vix_hedge_manager()

            # Generate and save signal (save happens automatically in generate_hedge_signal)
            signal = manager.generate_hedge_signal(
                portfolio_delta=0,  # Default - no specific portfolio context
                portfolio_value=100000  # Default portfolio value
            )

            logger.info(f"VIX SIGNAL: {signal.signal_type.value.upper()}")
            logger.info(f"  VIX Spot: {signal.metrics.get('vix_spot', 0):.2f}")
            logger.info(f"  Vol Regime: {signal.vol_regime.value}")
            logger.info(f"  Confidence: {signal.confidence:.0f}%")
            logger.info(f"  IV Percentile: {signal.metrics.get('iv_percentile', 0):.0f}th")
            logger.info(f"  Term Structure: {signal.metrics.get('term_structure_pct', 0):.1f}%")

            self._save_heartbeat('VIX_SIGNAL', 'GENERATED', {
                'vix_spot': signal.metrics.get('vix_spot', 0),
                'signal_type': signal.signal_type.value,
                'vol_regime': signal.vol_regime.value
            })

            logger.info(f"VIX signal saved to database successfully")
            logger.info(f"=" * 80)

        except Exception as e:
            error_msg = f"ERROR in VIX signal generation: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            self._save_heartbeat('VIX_SIGNAL', 'ERROR', {'error': str(e)})
            logger.info("VIX signal will retry next interval")
            logger.info(f"=" * 80)

    def scheduled_solomon_logic(self):
        """
        SOLOMON (Feedback Loop Intelligence) - runs DAILY at 4:00 PM CT

        Migration 023: Enhanced with Oracle-Solomon integration for complete feedback loop.

        Orchestrates the autonomous feedback loop for all trading bots:
        1. Trains Oracle from new trade outcomes (auto_train)
        2. Runs Solomon feedback loop (parameter proposals, A/B testing)
        3. Analyzes strategy-level performance (IC vs Directional)
        4. Tracks Oracle recommendation accuracy

        Bots: ARES, ATHENA, TITAN, PEGASUS, ICARUS

        "Iron sharpens iron, and one man sharpens another" - Proverbs 27:17
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"SOLOMON (Feedback Loop) triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not SOLOMON_AVAILABLE:
            logger.warning("SOLOMON: Feedback loop system not available")
            return

        try:
            # ================================================================
            # STEP 1: Train Oracle from new trade outcomes
            # Migration 023: Oracle learns from outcomes before Solomon analyzes
            # ================================================================
            if ORACLE_AVAILABLE and oracle_auto_train:
                logger.info("SOLOMON: Step 1 - Training Oracle from new outcomes...")
                try:
                    train_result = oracle_auto_train(threshold_outcomes=10)  # Lower threshold for daily runs
                    if train_result.get('triggered'):
                        logger.info(f"  Oracle training triggered: {train_result.get('reason')}")
                        if train_result.get('success'):
                            metrics = train_result.get('training_metrics')
                            if metrics:
                                logger.info(f"  Training metrics: accuracy={metrics.get('accuracy', 'N/A')}, samples={metrics.get('samples', 'N/A')}")
                        else:
                            logger.warning(f"  Oracle training failed: {train_result.get('error', 'Unknown error')}")
                    else:
                        logger.info(f"  Oracle training skipped: {train_result.get('reason')}")
                except Exception as e:
                    logger.warning(f"  Oracle auto_train failed: {e}")
            else:
                logger.info("SOLOMON: Step 1 - Oracle training skipped (not available)")

            # ================================================================
            # STEP 2: Run Solomon feedback loop
            # ================================================================
            logger.info("SOLOMON: Step 2 - Running feedback loop analysis...")
            result = run_feedback_loop()

            if result.success:
                logger.info(f"SOLOMON: Feedback loop completed successfully")
                logger.info(f"  Run ID: {result.run_id}")
                logger.info(f"  Bots checked: {', '.join(result.bots_checked)}")
                logger.info(f"  Outcomes processed: {result.outcomes_processed}")
                logger.info(f"  Proposals created: {len(result.proposals_created)}")
                logger.info(f"  Proposals applied: {len(result.proposals_applied) if hasattr(result, 'proposals_applied') else 0}")

                if result.proposals_created:
                    logger.info(f"  New proposals pending validation: {result.proposals_created}")

                if hasattr(result, 'proposals_applied') and result.proposals_applied:
                    logger.info(f"  ✅ PROVEN improvements auto-applied: {result.proposals_applied}")

                if result.alerts_raised:
                    logger.warning(f"  ALERTS: {len(result.alerts_raised)} alerts raised!")
                    for alert in result.alerts_raised:
                        logger.warning(f"    - {alert.get('bot_name')}: {alert.get('alert_type')}")
            else:
                logger.error(f"SOLOMON: Feedback loop completed with errors")
                for error in result.errors:
                    logger.error(f"  Error: {error}")

            # ================================================================
            # STEP 3: Analyze strategy-level performance (Migration 023)
            # ================================================================
            strategy_analysis = None
            oracle_accuracy = None

            if SOLOMON_ENHANCED_AVAILABLE and get_solomon_enhanced:
                logger.info("SOLOMON: Step 3 - Analyzing strategy-level performance...")
                try:
                    enhanced = get_solomon_enhanced()

                    # Get IC vs Directional analysis
                    strategy_analysis = enhanced.get_strategy_analysis(days=30)
                    if strategy_analysis.get('status') == 'analyzed':
                        ic = strategy_analysis.get('iron_condor', {})
                        dir_data = strategy_analysis.get('directional', {})
                        logger.info(f"  IC Performance: {ic.get('trades', 0)} trades, {ic.get('win_rate', 0):.1f}% win rate, ${ic.get('total_pnl', 0):.2f} P&L")
                        logger.info(f"  Directional Performance: {dir_data.get('trades', 0)} trades, {dir_data.get('win_rate', 0):.1f}% win rate, ${dir_data.get('total_pnl', 0):.2f} P&L")

                        rec = strategy_analysis.get('recommendation', '')
                        if rec:
                            logger.info(f"  Strategy Recommendation: {rec}")

                    # Get Oracle accuracy
                    oracle_accuracy = enhanced.get_oracle_accuracy(days=30)
                    if oracle_accuracy.get('status') == 'analyzed':
                        summary = oracle_accuracy.get('summary', '')
                        if summary:
                            logger.info(f"  Oracle Accuracy: {summary}")

                except Exception as e:
                    logger.warning(f"  Strategy analysis failed: {e}")
            else:
                logger.info("SOLOMON: Step 3 - Strategy analysis skipped (Solomon Enhanced not available)")

            # Save heartbeat with enhanced data
            self._save_heartbeat('SOLOMON', 'FEEDBACK_LOOP_COMPLETE', {
                'run_id': result.run_id,
                'success': result.success,
                'proposals_created': len(result.proposals_created),
                'proposals_applied': len(result.proposals_applied) if hasattr(result, 'proposals_applied') else 0,
                'alerts_raised': len(result.alerts_raised),
                'strategy_analysis': strategy_analysis.get('recommendation') if strategy_analysis else None,
                'oracle_accuracy': oracle_accuracy.get('summary') if oracle_accuracy else None
            })

            logger.info(f"SOLOMON: Next run tomorrow at 4:00 PM CT")
            logger.info(f"=" * 80)

        except Exception as e:
            error_msg = f"ERROR in SOLOMON feedback loop: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            self._save_heartbeat('SOLOMON', 'ERROR', {'error': str(e)})
            logger.info("SOLOMON will retry tomorrow at 4:00 PM CT")
            logger.info(f"=" * 80)

    def scheduled_quant_training_logic(self):
        """
        QUANT (ML Model Training) - runs WEEKLY on Sunday at 5:00 PM CT

        Retrains quantitative ML models to adapt to changing market conditions:
        - REGIME_CLASSIFIER: Market regime classification (BULLISH/BEARISH/NEUTRAL)
        - GEX_DIRECTIONAL: Directional prediction based on GEX analysis

        Weekly training ensures models stay current without overfitting to recent data.
        Training runs on Sunday when markets are closed to avoid interference with trading.
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"QUANT (ML Training) triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        training_results = {
            'timestamp': now.isoformat(),
            'models_trained': [],
            'models_failed': [],
            'details': {}
        }

        # =================================================================
        # REMOVED: ML Regime Classifier - Oracle is god
        # The REGIME_CLASSIFIER training code has been removed.
        # Oracle decides all trades.
        # =================================================================

        # =================================================================
        # GEX_DIRECTIONAL Training
        # =================================================================
        if GEX_DIRECTIONAL_AVAILABLE:
            try:
                logger.info("QUANT: Training GEX_DIRECTIONAL...")
                predictor = GEXDirectionalPredictor(ticker="SPY")
                result = predictor.train(start_date="2022-01-01", n_splits=5)

                if result:
                    # Save the model
                    predictor.save_model("models/gex_directional_model.joblib")

                    logger.info(f"  ✅ GEX_DIRECTIONAL trained successfully")
                    logger.info(f"     Accuracy: {result.accuracy:.2%}")
                    logger.info(f"     Training samples: {result.training_samples}")

                    training_results['models_trained'].append('GEX_DIRECTIONAL')
                    training_results['details']['GEX_DIRECTIONAL'] = {
                        'accuracy': result.accuracy,
                        'training_samples': result.training_samples,
                        'test_samples': result.test_samples
                    }

                    # Record to database
                    self._record_training_history(
                        model_name='GEX_DIRECTIONAL',
                        status='COMPLETED',
                        accuracy_after=result.accuracy * 100,
                        training_samples=result.training_samples,
                        triggered_by='SCHEDULED'
                    )
                else:
                    logger.warning("  ⚠️ GEX_DIRECTIONAL training returned no result")
                    training_results['models_failed'].append('GEX_DIRECTIONAL')

            except Exception as e:
                logger.error(f"  ❌ GEX_DIRECTIONAL training failed: {e}")
                logger.error(traceback.format_exc())
                training_results['models_failed'].append('GEX_DIRECTIONAL')
                self._record_training_history(
                    model_name='GEX_DIRECTIONAL',
                    status='FAILED',
                    triggered_by='SCHEDULED',
                    error=str(e)
                )
        else:
            logger.warning("QUANT: GEX_DIRECTIONAL not available - skipping")

        # =================================================================
        # Summary
        # =================================================================
        logger.info(f"QUANT: Training complete")
        logger.info(f"  Models trained: {len(training_results['models_trained'])}")
        logger.info(f"  Models failed: {len(training_results['models_failed'])}")

        # Save heartbeat
        self._save_heartbeat('QUANT', 'TRAINING_COMPLETE', training_results)

        logger.info(f"QUANT: Next training scheduled for next Sunday at 5:00 PM CT")
        logger.info(f"=" * 80)

    def scheduled_gex_ml_training_logic(self):
        """
        GEX ML (Probability Models) - runs WEEKLY on Sunday at 6:00 PM CT

        Retrains the 5 GEX probability models used by ARGUS and HYPERION:
        1. Direction Probability (UP/DOWN/FLAT classification)
        2. Flip Gravity (probability of moving toward flip point)
        3. Magnet Attraction (probability of reaching magnets)
        4. Volatility Estimate (expected price range)
        5. Pin Zone Behavior (probability of staying pinned)

        Training runs after market close on Sunday to have fresh models for the week.
        Models are saved to database for persistence across deploys.
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"GEX ML (Probability Models) triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not GEX_PROBABILITY_MODELS_AVAILABLE:
            logger.warning("GEX ML: GEXSignalGenerator not available - skipping")
            return

        try:
            # Initialize generator
            generator = GEXSignalGenerator()

            # Check if retraining is needed (models older than 7 days)
            needs_training = True
            if generator.is_trained:
                try:
                    # Check staleness
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT created_at FROM ml_models
                        WHERE model_name = 'gex_signal_generator'
                        ORDER BY version DESC LIMIT 1
                    """)
                    row = cursor.fetchone()
                    conn.close()

                    if row:
                        last_trained = row[0]
                        hours_since = (now.replace(tzinfo=None) - last_trained).total_seconds() / 3600
                        if hours_since < 168:  # Less than 7 days
                            logger.info(f"GEX ML: Models trained {hours_since:.1f} hours ago - still fresh")
                            needs_training = False
                        else:
                            logger.info(f"GEX ML: Models are {hours_since:.1f} hours old - retraining")
                except Exception as e:
                    logger.warning(f"GEX ML: Could not check staleness: {e}")

            if not needs_training:
                logger.info("GEX ML: Skipping training - models are fresh")
                self._save_heartbeat('GEX_ML', 'SKIPPED', {'reason': 'models_fresh'})
                return

            # Train models
            logger.info("GEX ML: Starting training on SPX and SPY data...")
            results = generator.train(
                symbols=['SPX', 'SPY'],
                start_date='2020-01-01',
                end_date=None  # Up to present
            )

            if results and generator.is_trained:
                # Save to database for persistence
                generator.save_to_db(
                    metrics=results if isinstance(results, dict) else None,
                    training_records=results.get('total_records') if isinstance(results, dict) else None
                )

                logger.info(f"  ✅ GEX ML training completed successfully")
                if isinstance(results, dict):
                    logger.info(f"     Training records: {results.get('total_records', 'N/A')}")
                    for model_name, metrics in results.get('model_metrics', {}).items():
                        if isinstance(metrics, dict) and 'accuracy' in metrics:
                            logger.info(f"     {model_name}: {metrics['accuracy']:.2%} accuracy")

                self._record_training_history(
                    model_name='GEX_PROBABILITY_MODELS',
                    status='COMPLETED',
                    accuracy_after=results.get('model_metrics', {}).get('direction', {}).get('accuracy', 0) * 100 if isinstance(results, dict) else None,
                    training_samples=results.get('total_records') if isinstance(results, dict) else None,
                    triggered_by='SCHEDULED'
                )

                self._save_heartbeat('GEX_ML', 'TRAINING_COMPLETE', {
                    'models_trained': 5,
                    'results': results if isinstance(results, dict) else {}
                })
            else:
                logger.warning("  ⚠️ GEX ML training returned no result or models not trained")
                self._save_heartbeat('GEX_ML', 'TRAINING_FAILED', {'reason': 'no_result'})

        except Exception as e:
            logger.error(f"  ❌ GEX ML training failed: {e}")
            logger.error(traceback.format_exc())
            self._record_training_history(
                model_name='GEX_PROBABILITY_MODELS',
                status='FAILED',
                triggered_by='SCHEDULED',
                error=str(e)
            )
            self._save_heartbeat('GEX_ML', 'TRAINING_FAILED', {'error': str(e)})

        logger.info(f"GEX ML: Next training scheduled for next Sunday at 6:00 PM CT")
        logger.info(f"=" * 80)

    def scheduled_validation_logic(self):
        """
        AUTO-VALIDATION (ML Health Check) - runs WEEKLY on Saturday at 6:00 PM CT

        Validates ALL 11 ML models using walk-forward validation:
        - GEX Signal Generator (5 sub-models)
        - GEX Directional ML
        - ML Regime Classifier
        - ARES ML Advisor
        - Oracle Advisor
        - Apollo ML Engine
        - Prometheus ML
        - SPX Wheel ML
        - Market Regime Classifier
        - Pattern Learner
        - ATHENA ML

        If degradation exceeds threshold, auto-retrain is triggered.
        Also updates Thompson Sampling capital allocation based on bot performance.
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"AUTO-VALIDATION triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not AUTO_VALIDATION_AVAILABLE:
            logger.warning("AUTO-VALIDATION: System not available")
            return

        try:
            logger.info("AUTO-VALIDATION: Running weekly ML model health check...")

            # Run validation on all models
            results = run_validation(force=True)

            # Count results by status
            healthy = sum(1 for r in results if r.status.value == 'healthy')
            degraded = sum(1 for r in results if r.status.value == 'degraded')
            failed = sum(1 for r in results if r.status.value == 'failed')
            retrained = sum(1 for r in results if r.recommendation == 'RETRAIN')

            logger.info(f"AUTO-VALIDATION: Health check complete")
            logger.info(f"  Total models: {len(results)}")
            logger.info(f"  Healthy: {healthy}")
            logger.info(f"  Degraded: {degraded}")
            logger.info(f"  Failed: {failed}")
            logger.info(f"  Auto-retrained: {retrained}")

            # Log details for each model
            for r in results:
                status_icon = "✅" if r.status.value == 'healthy' else "⚠️" if r.status.value == 'degraded' else "❌"
                logger.info(f"  {status_icon} {r.model_name}: {r.status.value} "
                           f"(IS: {r.in_sample_accuracy:.1%}, OOS: {r.out_of_sample_accuracy:.1%}, "
                           f"Degradation: {r.degradation_pct:.1f}%)")

            # Get Thompson allocation status
            system = get_auto_validation_system()
            if system.thompson:
                logger.info("AUTO-VALIDATION: Thompson Sampling allocation:")
                for bot in system.bot_names:
                    confidence = system.get_bot_confidence(bot)
                    logger.info(f"    {bot}: {confidence:.1%} confidence")

            # Save heartbeat
            self._save_heartbeat('AUTO_VALIDATION', 'HEALTH_CHECK_COMPLETE', {
                'total_models': len(results),
                'healthy': healthy,
                'degraded': degraded,
                'failed': failed,
                'retrained': retrained
            })

            logger.info(f"AUTO-VALIDATION: Next run scheduled for next Saturday at 6:00 PM CT")
            logger.info(f"=" * 80)

        except Exception as e:
            error_msg = f"ERROR in AUTO-VALIDATION: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            self._save_heartbeat('AUTO_VALIDATION', 'ERROR', {'error': str(e)})
            logger.info("AUTO-VALIDATION will retry next Saturday at 6:00 PM CT")
            logger.info(f"=" * 80)

    def _record_training_history(self, model_name: str, status: str, accuracy_after: float = None,
                                  training_samples: int = None, triggered_by: str = 'SCHEDULED',
                                  error: str = None):
        """Record training run to quant_training_history table.

        CRITICAL: Uses finally block to prevent connection leaks.
        Connection pool exhaustion causes scan stoppage.
        """
        conn = None  # Initialize to prevent NameError in finally block
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO quant_training_history (
                    timestamp, model_name, status, accuracy_after,
                    training_samples, triggered_by, error_message
                ) VALUES (NOW(), %s, %s, %s, %s, %s, %s)
            """, (model_name, status, accuracy_after, training_samples, triggered_by, error))

            conn.commit()
            cursor.close()
        except Exception as e:
            logger.error(f"Failed to record training history: {e}")
        finally:
            # CRITICAL: Always close connection to prevent pool exhaustion
            try:
                if conn:
                    conn.close()
            except Exception:
                pass

    def scheduled_trade_sync_logic(self):
        """
        TRADE SYNC - runs every 30 minutes during market hours

        Performs critical data synchronization:
        1. Cleanup stale positions (expired but still 'open')
        2. Fix missing P&L values on closed positions
        3. Sync bot tables to unified tracking tables

        This ensures data integrity across all trading bots.
        """
        now = datetime.now(CENTRAL_TZ)

        # Only run during market hours
        if not self.is_market_open():
            return

        logger.info(f"TRADE_SYNC: Starting sync at {now.strftime('%H:%M:%S')}")

        try:
            from trading.trade_sync_service import run_full_sync
            results = run_full_sync()

            stale_cleaned = results.get('stale_cleanup', {}).get('total_cleaned', 0)
            pnl_fixed = results.get('pnl_fix', {}).get('total_fixed', 0)
            errors = results.get('total_errors', [])

            if stale_cleaned > 0 or pnl_fixed > 0:
                logger.info(f"TRADE_SYNC: Cleaned {stale_cleaned} stale, fixed {pnl_fixed} P&L")
            if errors:
                for err in errors:
                    logger.warning(f"TRADE_SYNC: Error - {err}")

        except Exception as e:
            logger.error(f"TRADE_SYNC: Failed - {e}")

    def scheduled_equity_snapshots_logic(self):
        """
        EQUITY SNAPSHOTS - runs every 5 minutes during market hours

        Saves equity snapshots for all bots to enable intraday charting:
        - ARES, ATHENA, PEGASUS, TITAN, ICARUS

        These snapshots power the /equity-curve/intraday endpoints
        showing real-time equity changes throughout the trading day.

        NOTE: Writes directly to database (not via HTTP) since scheduler
        runs as separate worker from API on Render.
        """
        now = datetime.now(CENTRAL_TZ)

        # Only run during market hours
        if not self.is_market_open():
            logger.info(f"EQUITY_SNAPSHOTS: Market closed, skipping snapshot at {now.strftime('%H:%M:%S')}")
            return

        logger.info(f"EQUITY_SNAPSHOTS: Taking snapshots at {now.strftime('%H:%M:%S')}")

        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Bot configurations: (positions_table, snapshot_table, starting_capital_key, default_capital, trader_attr)
            # trader_attr is the scheduler attribute name for the bot's trader instance (for live unrealized P&L)
            bots_config = {
                'ares': ('ares_positions', 'ares_equity_snapshots', 'ares_starting_capital', 100000, 'ares_trader'),
                'athena': ('athena_positions', 'athena_equity_snapshots', 'athena_starting_capital', 100000, 'athena_trader'),
                'titan': ('titan_positions', 'titan_equity_snapshots', 'titan_starting_capital', 200000, 'titan_trader'),
                'pegasus': ('pegasus_positions', 'pegasus_equity_snapshots', 'pegasus_starting_capital', 200000, 'pegasus_trader'),
                'icarus': ('icarus_positions', 'icarus_equity_snapshots', 'icarus_starting_capital', 100000, 'icarus_trader'),
            }

            for bot_name, (pos_table, snap_table, cap_key, default_cap, trader_attr) in bots_config.items():
                try:
                    # Get starting capital from config
                    cursor.execute(f"SELECT value FROM autonomous_config WHERE key = %s", (cap_key,))
                    row = cursor.fetchone()
                    starting_capital = float(row[0]) if row and row[0] else default_cap

                    # Get realized P&L from closed positions (handle missing table gracefully)
                    realized_pnl = 0
                    open_count = 0
                    try:
                        cursor.execute(f"""
                            SELECT COALESCE(SUM(realized_pnl), 0)
                            FROM {pos_table}
                            WHERE status IN ('closed', 'expired')
                        """)
                        realized_row = cursor.fetchone()
                        realized_pnl = float(realized_row[0]) if realized_row and realized_row[0] else 0

                        # Count open positions
                        cursor.execute(f"""
                            SELECT COUNT(*) FROM {pos_table} WHERE status = 'open'
                        """)
                        open_count = cursor.fetchone()[0] or 0
                    except Exception as table_err:
                        # Positions table might not exist yet - use defaults
                        logger.info(f"EQUITY_SNAPSHOTS: {bot_name.upper()} positions table not ready ({table_err}), using defaults")
                        realized_pnl = 0
                        open_count = 0

                    # Calculate unrealized P&L using mark-to-market pricing from open positions
                    # This is more reliable than trader instance which may have stale data
                    unrealized_pnl = 0
                    mtm_method = 'none'

                    if open_count > 0 and MTM_AVAILABLE:
                        try:
                            # Iron Condor bots: ARES, TITAN, PEGASUS
                            if bot_name in ['ares', 'titan', 'pegasus']:
                                # Query IC positions with all MTM fields
                                underlying = 'SPY' if bot_name == 'ares' else 'SPX'
                                cursor.execute(f"""
                                    SELECT position_id, total_credit, contracts, spread_width,
                                           put_short_strike, put_long_strike, call_short_strike, call_long_strike,
                                           expiration
                                    FROM {pos_table}
                                    WHERE status = 'open'
                                """)
                                open_positions = cursor.fetchall()

                                for pos in open_positions:
                                    pos_id, credit, contracts, spread_w, put_short, put_long, call_short, call_long, exp = pos
                                    if not all([credit, contracts, put_short, put_long, call_short, call_long, exp]):
                                        continue
                                    try:
                                        exp_str = str(exp) if not isinstance(exp, str) else exp
                                        mtm = calculate_ic_mark_to_market(
                                            underlying=underlying,
                                            expiration=exp_str,
                                            put_short_strike=float(put_short),
                                            put_long_strike=float(put_long),
                                            call_short_strike=float(call_short),
                                            call_long_strike=float(call_long),
                                            contracts=int(contracts),
                                            entry_credit=float(credit),
                                            use_cache=True
                                        )
                                        if mtm.get('success') and mtm.get('unrealized_pnl') is not None:
                                            unrealized_pnl += mtm['unrealized_pnl']
                                            mtm_method = 'mark_to_market'
                                    except Exception as pos_err:
                                        logger.debug(f"EQUITY_SNAPSHOTS: {bot_name.upper()} MTM failed for {pos_id}: {pos_err}")

                            # Directional spread bots: ATHENA, ICARUS
                            elif bot_name in ['athena', 'icarus']:
                                cursor.execute(f"""
                                    SELECT position_id, spread_type, entry_debit, contracts,
                                           long_strike, short_strike, max_profit, max_loss, expiration
                                    FROM {pos_table}
                                    WHERE status = 'open'
                                """)
                                open_positions = cursor.fetchall()

                                for pos in open_positions:
                                    pos_id, spread_type, debit, contracts, long_strike, short_strike, max_profit, max_loss, exp = pos
                                    if not all([debit, contracts, long_strike, short_strike, exp]):
                                        continue
                                    try:
                                        exp_str = str(exp) if not isinstance(exp, str) else exp
                                        mtm = calculate_spread_mark_to_market(
                                            underlying='SPY',
                                            expiration=exp_str,
                                            long_strike=float(long_strike),
                                            short_strike=float(short_strike),
                                            spread_type=spread_type,
                                            contracts=int(contracts),
                                            entry_debit=float(debit),
                                            use_cache=True
                                        )
                                        if mtm.get('success') and mtm.get('unrealized_pnl') is not None:
                                            unrealized_pnl += mtm['unrealized_pnl']
                                            mtm_method = 'mark_to_market'
                                    except Exception as pos_err:
                                        logger.debug(f"EQUITY_SNAPSHOTS: {bot_name.upper()} MTM failed for {pos_id}: {pos_err}")

                            if mtm_method == 'mark_to_market':
                                logger.info(f"EQUITY_SNAPSHOTS: {bot_name.upper()} MTM unrealized=${unrealized_pnl:.2f}")
                        except Exception as mtm_err:
                            logger.warning(f"EQUITY_SNAPSHOTS: {bot_name.upper()} MTM calculation failed: {mtm_err}")
                            mtm_method = 'failed'

                    # Fallback to trader instance if MTM failed or unavailable
                    if mtm_method != 'mark_to_market' and open_count > 0:
                        trader_instance = getattr(self, trader_attr, None)
                        if trader_instance:
                            try:
                                status = trader_instance.get_status()
                                unrealized_pnl = status.get('unrealized_pnl', 0) or 0
                                logger.info(f"EQUITY_SNAPSHOTS: {bot_name.upper()} fallback to trader instance unrealized=${unrealized_pnl:.2f}")
                            except Exception as e:
                                logger.warning(f"EQUITY_SNAPSHOTS: {bot_name.upper()} trader instance fallback failed: {e}")
                                unrealized_pnl = 0

                    # Calculate current equity (realized + unrealized for intraday tracking)
                    current_equity = starting_capital + realized_pnl + unrealized_pnl

                    # Ensure snapshot table exists with all required columns
                    cursor.execute(f"""
                        CREATE TABLE IF NOT EXISTS {snap_table} (
                            id SERIAL PRIMARY KEY,
                            timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
                            balance DECIMAL(12, 2) NOT NULL,
                            unrealized_pnl DECIMAL(12, 2),
                            realized_pnl DECIMAL(12, 2),
                            open_positions INTEGER,
                            note TEXT,
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                        )
                    """)

                    # Add missing columns if they don't exist (for older tables)
                    for col in ['unrealized_pnl', 'realized_pnl']:
                        try:
                            cursor.execute(f"""
                                ALTER TABLE {snap_table} ADD COLUMN IF NOT EXISTS {col} DECIMAL(12, 2)
                            """)
                        except Exception:
                            pass

                    # Insert snapshot
                    cursor.execute(f"""
                        INSERT INTO {snap_table}
                        (timestamp, balance, unrealized_pnl, realized_pnl, open_positions, note)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        now,
                        round(current_equity, 2),
                        round(unrealized_pnl, 2),
                        round(realized_pnl, 2),
                        open_count,
                        f"Auto snapshot at {now.strftime('%H:%M:%S')}"
                    ))

                    logger.info(f"EQUITY_SNAPSHOTS: {bot_name.upper()} snapshot saved - equity=${current_equity:.2f}, realized=${realized_pnl:.2f}, open={open_count}")

                except Exception as e:
                    logger.warning(f"EQUITY_SNAPSHOTS: {bot_name.upper()} error: {e}")
                    import traceback
                    traceback.print_exc()
                    continue

            conn.commit()
            logger.info(f"EQUITY_SNAPSHOTS: All bot snapshots committed successfully")

        except Exception as e:
            logger.warning(f"EQUITY_SNAPSHOTS: Error taking snapshots: {e}")
            import traceback
            traceback.print_exc()
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def start(self):
        """Start the autonomous trading scheduler"""
        if not APSCHEDULER_AVAILABLE:
            logger.error("Cannot start scheduler - APScheduler not installed")
            logger.info("To enable autonomous trading, install: pip install apscheduler")
            return

        if self.is_running:
            logger.warning("Scheduler is already running")
            return

        logger.info("=" * 80)
        logger.info("STARTING AUTONOMOUS TRADING SCHEDULER")
        logger.info(f"Bots: PHOENIX, ATLAS, ARES (SPY IC), PEGASUS (SPX IC), ATHENA, ARGUS, VIX_SIGNAL, SOLOMON, QUANT")
        logger.info(f"Timezone: America/Chicago (Texas Central Time)")
        logger.info(f"PHOENIX Schedule: DISABLED here - handled by AutonomousTrader (every 5 min)")
        logger.info(f"ATLAS Schedule: Daily at 9:05 AM CT, Mon-Fri")
        logger.info(f"ARES Schedule: Every 5 min (runs 24/7, market hours checked internally)")
        logger.info(f"PEGASUS Schedule: Every 5 min (runs 24/7, market hours checked internally)")
        logger.info(f"ATHENA Schedule: Every 5 min (runs 24/7, market hours checked internally)")
        logger.info(f"ICARUS Schedule: Every 5 min (runs 24/7, market hours checked internally)")
        logger.info(f"TITAN Schedule: Every 5 min (runs 24/7, market hours checked internally)")
        logger.info(f"ARGUS Schedule: Every 5 min (runs 24/7, market hours checked internally)")
        logger.info(f"VIX_SIGNAL Schedule: HOURLY (9 AM - 3 PM CT), Hedge Signal Generation")
        logger.info(f"SOLOMON Schedule: DAILY at 4:00 PM CT (after market close)")
        logger.info(f"QUANT Schedule: WEEKLY on Sunday at 5:00 PM CT (ML model training)")
        logger.info(f"EQUITY_SNAPSHOTS Schedule: Every 5 min (runs 24/7, market hours checked internally)")
        logger.info(f"Log file: {LOG_FILE}")
        logger.info("=" * 80)

        # Create scheduler with Central Texas timezone
        self.scheduler = BackgroundScheduler(timezone='America/Chicago')

        # =================================================================
        # PHOENIX JOB: DISABLED - Handled by AutonomousTrader (every 5 min)
        # =================================================================
        # NOTE: PHOENIX is run via the AutonomousTrader watchdog thread which
        # executes every 5 minutes during market hours. This provides more
        # responsive trading than the hourly schedule here.
        # The AutonomousTrader is registered separately in backend/main.py.
        #
        # DISABLED to prevent duplicate trade execution:
        # self.scheduler.add_job(
        #     self.scheduled_trade_logic,
        #     trigger=CronTrigger(
        #         hour='10-15',  # 10 AM through 3 PM (15 is 3:00 PM)
        #         minute=0,      # On the hour
        #         day_of_week='mon-fri',
        #         timezone='America/New_York'
        #     ),
        #     id='phoenix_trading',
        #     name='PHOENIX - 0DTE Options Trading',
        #     replace_existing=True
        # )
        logger.info("⚠️ PHOENIX job DISABLED here - handled by AutonomousTrader (every 5 min)")

        # =================================================================
        # ATLAS JOB: SPX Wheel - runs once daily at 9:05 AM CT
        # =================================================================
        if self.atlas_trader:
            self.scheduler.add_job(
                self.scheduled_atlas_logic,
                trigger=CronTrigger(
                    hour=9,        # 9:00 AM CT - after market settles
                    minute=5,      # 9:05 AM CT to avoid conflict with PHOENIX
                    day_of_week='mon-fri',
                    timezone='America/Chicago'
                ),
                id='atlas_trading',
                name='ATLAS - SPX Wheel Trading',
                replace_existing=True
            )
            logger.info("✅ ATLAS job scheduled (9:05 AM CT daily)")
        else:
            logger.warning("⚠️ ATLAS not available - wheel trading disabled")

        # =================================================================
        # ARES JOB: Aggressive Iron Condor - runs every 5 minutes
        # Scans continuously for optimal 0DTE Iron Condor entry timing
        # Jobs run immediately on startup and every 5 min thereafter.
        # Market hours are checked inside the job (saves BEFORE_WINDOW heartbeat if early).
        # =================================================================
        if self.ares_trader:
            self.scheduler.add_job(
                self.scheduled_ares_logic,
                trigger=IntervalTrigger(
                    minutes=5,
                    timezone='America/Chicago'
                ),
                id='ares_trading',
                name='ARES - Aggressive Iron Condor (5-min intervals)',
                replace_existing=True
            )
            logger.info("✅ ARES job scheduled (every 5 min, checks market hours internally)")

            # =================================================================
            # ARES EOD JOB: Process expired positions - runs at 3:01 PM CT
            # All EOD jobs run at 3:01 PM CT for fast reconciliation (<5 min post-close)
            # =================================================================
            self.scheduler.add_job(
                self.scheduled_ares_eod_logic,
                trigger=CronTrigger(
                    hour=15,       # 3:00 PM CT - after market close
                    minute=1,      # 3:01 PM CT - immediate post-close reconciliation
                    day_of_week='mon-fri',
                    timezone='America/Chicago'
                ),
                id='ares_eod',
                name='ARES - EOD Position Expiration',
                replace_existing=True
            )
            logger.info("✅ ARES EOD job scheduled (3:01 PM CT daily)")
        else:
            logger.warning("⚠️ ARES not available - aggressive IC trading disabled")

        # =================================================================
        # ATHENA JOB: GEX Directional Spreads - runs every 5 minutes
        # Uses live Tradier GEX data to find intraday opportunities
        # Jobs run immediately on startup and every 5 min thereafter.
        # Market hours are checked inside the job (saves BEFORE_WINDOW heartbeat if early).
        # =================================================================
        if self.athena_trader:
            self.scheduler.add_job(
                self.scheduled_athena_logic,
                trigger=IntervalTrigger(
                    minutes=5,
                    timezone='America/Chicago'
                ),
                id='athena_trading',
                name='ATHENA - GEX Directional Spreads (5-min intervals)',
                replace_existing=True
            )
            logger.info("✅ ATHENA job scheduled (every 5 min, checks market hours internally)")

            # =================================================================
            # ATHENA EOD JOB: Process expired positions - runs at 3:01 PM CT
            # All EOD jobs run at 3:01 PM CT for fast reconciliation (<5 min post-close)
            # =================================================================
            self.scheduler.add_job(
                self.scheduled_athena_eod_logic,
                trigger=CronTrigger(
                    hour=15,       # 3:00 PM CT - after market close
                    minute=1,      # 3:01 PM CT - immediate post-close reconciliation
                    day_of_week='mon-fri',
                    timezone='America/Chicago'
                ),
                id='athena_eod',
                name='ATHENA - EOD Position Expiration',
                replace_existing=True
            )
            logger.info("✅ ATHENA EOD job scheduled (3:01 PM CT daily)")
        else:
            logger.warning("⚠️ ATHENA not available - GEX directional trading disabled")

        # =================================================================
        # PEGASUS JOB: SPX Iron Condors - runs every 5 minutes
        # Trades SPX options with $10 spread widths using SPXW symbols
        # Jobs run immediately on startup and every 5 min thereafter.
        # Market hours are checked inside the job (saves BEFORE_WINDOW heartbeat if early).
        # =================================================================
        if self.pegasus_trader:
            self.scheduler.add_job(
                self.scheduled_pegasus_logic,
                trigger=IntervalTrigger(
                    minutes=5,
                    timezone='America/Chicago'
                ),
                id='pegasus_trading',
                name='PEGASUS - SPX Iron Condor (5-min intervals)',
                replace_existing=True
            )
            logger.info("✅ PEGASUS job scheduled (every 5 min, checks market hours internally)")

            # =================================================================
            # PEGASUS EOD JOB: Process expired positions - runs at 3:01 PM CT
            # All EOD jobs run at 3:01 PM CT for fast reconciliation (<5 min post-close)
            # =================================================================
            self.scheduler.add_job(
                self.scheduled_pegasus_eod_logic,
                trigger=CronTrigger(
                    hour=15,       # 3:00 PM CT - after market close
                    minute=1,      # 3:01 PM CT - immediate post-close reconciliation
                    day_of_week='mon-fri',
                    timezone='America/Chicago'
                ),
                id='pegasus_eod',
                name='PEGASUS - EOD Position Expiration',
                replace_existing=True
            )
            logger.info("✅ PEGASUS EOD job scheduled (3:01 PM CT daily)")
        else:
            logger.warning("⚠️ PEGASUS not available - SPX IC trading disabled")

        # =================================================================
        # ICARUS JOB: Aggressive Directional Spreads - runs every 5 minutes
        # Uses relaxed GEX filters for more aggressive trading
        # Jobs run immediately on startup and every 5 min thereafter.
        # Market hours are checked inside the job (saves BEFORE_WINDOW heartbeat if early).
        # =================================================================
        if self.icarus_trader:
            self.scheduler.add_job(
                self.scheduled_icarus_logic,
                trigger=IntervalTrigger(
                    minutes=5,
                    timezone='America/Chicago'
                ),
                id='icarus_trading',
                name='ICARUS - Aggressive Directional Spreads (5-min intervals)',
                replace_existing=True
            )
            logger.info("✅ ICARUS job scheduled (every 5 min, checks market hours internally)")

            # =================================================================
            # ICARUS EOD JOB: Process expired positions - runs at 3:01 PM CT
            # All EOD jobs run at 3:01 PM CT for fast reconciliation (<5 min post-close)
            # =================================================================
            self.scheduler.add_job(
                self.scheduled_icarus_eod_logic,
                trigger=CronTrigger(
                    hour=15,       # 3:00 PM CT - after market close
                    minute=1,      # 3:01 PM CT - immediate post-close reconciliation
                    day_of_week='mon-fri',
                    timezone='America/Chicago'
                ),
                id='icarus_eod',
                name='ICARUS - EOD Position Expiration',
                replace_existing=True
            )
            logger.info("✅ ICARUS EOD job scheduled (3:01 PM CT daily)")
        else:
            logger.warning("⚠️ ICARUS not available - aggressive directional trading disabled")

        # =================================================================
        # TITAN JOB: Aggressive SPX Iron Condors - runs every 5 minutes
        # Trades SPX options with $12 spread widths, multiple trades per day with cooldown
        # Jobs run immediately on startup and every 5 min thereafter.
        # Market hours are checked inside the job (saves BEFORE_WINDOW heartbeat if early).
        # =================================================================
        if self.titan_trader:
            self.scheduler.add_job(
                self.scheduled_titan_logic,
                trigger=IntervalTrigger(
                    minutes=5,
                    timezone='America/Chicago'
                ),
                id='titan_trading',
                name='TITAN - Aggressive SPX Iron Condor (5-min intervals)',
                replace_existing=True
            )
            logger.info("✅ TITAN job scheduled (every 5 min, checks market hours internally)")

            # =================================================================
            # TITAN EOD JOB: Process expired positions - runs at 3:01 PM CT
            # All EOD jobs run at 3:01 PM CT for fast reconciliation (<5 min post-close)
            # =================================================================
            self.scheduler.add_job(
                self.scheduled_titan_eod_logic,
                trigger=CronTrigger(
                    hour=15,       # 3:00 PM CT - after market close
                    minute=1,      # 3:01 PM CT - immediate post-close reconciliation
                    day_of_week='mon-fri',
                    timezone='America/Chicago'
                ),
                id='titan_eod',
                name='TITAN - EOD Position Expiration',
                replace_existing=True
            )
            logger.info("✅ TITAN EOD job scheduled (3:01 PM CT daily)")
        else:
            logger.warning("⚠️ TITAN not available - aggressive SPX IC trading disabled")

        # =================================================================
        # ARGUS JOB: Commentary Generation - runs every 5 minutes
        # Generates AI-powered gamma commentary for the Live Log
        # Jobs run immediately on startup and every 5 min thereafter.
        # Market hours are checked inside the job.
        # =================================================================
        self.scheduler.add_job(
            self.scheduled_argus_logic,
            trigger=IntervalTrigger(
                minutes=5,
                timezone='America/Chicago'
            ),
            id='argus_commentary',
            name='ARGUS - Gamma Commentary (5-min intervals)',
            replace_existing=True
        )
        logger.info("✅ ARGUS job scheduled (every 5 min, checks market hours internally)")

        # =================================================================
        # ARGUS EOD JOB: Pin Prediction Accuracy Processing - runs at 3:01 PM CT
        # Updates pin predictions with actual closing prices and calculates
        # accuracy metrics for the pin accuracy tracking feature.
        # =================================================================
        self.scheduler.add_job(
            self.scheduled_argus_eod_logic,
            trigger=CronTrigger(
                hour=15,       # 3:00 PM CT - after market close
                minute=1,      # 3:01 PM CT - immediate post-close
                day_of_week='mon-fri',
                timezone='America/Chicago'
            ),
            id='argus_eod',
            name='ARGUS - EOD Pin Accuracy Processing',
            replace_existing=True
        )
        logger.info("✅ ARGUS EOD job scheduled (3:01 PM CT daily)")

        # =================================================================
        # VIX SIGNAL JOB: VIX Hedge Signal Generation - runs HOURLY during market hours
        # Generates signals for the VIX dashboard signal history:
        # - Tracks volatility conditions throughout the day
        # - Provides hedge recommendations based on VIX levels
        # - Saves signals to vix_hedge_signals table for historical analysis
        # =================================================================
        if VIX_HEDGE_AVAILABLE:
            self.scheduler.add_job(
                self.scheduled_vix_signal_logic,
                trigger=CronTrigger(
                    hour='9-15',   # 9 AM through 3 PM CT (market hours)
                    minute=0,      # On the hour
                    day_of_week='mon-fri',
                    timezone='America/Chicago'
                ),
                id='vix_signal_generation',
                name='VIX - Hedge Signal Generation (hourly)',
                replace_existing=True
            )
            logger.info("✅ VIX SIGNAL job scheduled (hourly 9 AM - 3 PM CT)")
        else:
            logger.warning("⚠️ VIX Hedge Manager not available - signal generation disabled")

        # =================================================================
        # SOLOMON JOB: Feedback Loop Intelligence - runs DAILY after market close
        # Orchestrates autonomous bot improvement:
        # - Collects trade outcomes and analyzes performance
        # - Creates proposals for underperforming bots
        # - Validates proposals via A/B testing (7 days, 20 trades, 5% improvement)
        # - AUTO-APPLIES proven improvements - no manual intervention required
        # =================================================================
        if SOLOMON_AVAILABLE:
            self.scheduler.add_job(
                self.scheduled_solomon_logic,
                trigger=CronTrigger(
                    hour=16,       # 4:00 PM CT - after market close
                    minute=0,
                    day_of_week='mon-fri',  # Every trading day
                    timezone='America/Chicago'
                ),
                id='solomon_feedback_loop',
                name='SOLOMON - Daily Feedback Loop Intelligence',
                replace_existing=True
            )
            logger.info("✅ SOLOMON job scheduled (DAILY at 4:00 PM CT)")
        else:
            logger.warning("⚠️ SOLOMON not available - Feedback loop disabled")

        # =================================================================
        # QUANT JOB: ML Model Training - runs WEEKLY on Sunday
        # Retrains quantitative ML models to adapt to market changes:
        # - REGIME_CLASSIFIER: Market regime classification
        # - GEX_DIRECTIONAL: Directional prediction from GEX data
        # Training on Sunday ensures models are fresh for the trading week
        # =================================================================
        if REGIME_CLASSIFIER_AVAILABLE or GEX_DIRECTIONAL_AVAILABLE:
            self.scheduler.add_job(
                self.scheduled_quant_training_logic,
                trigger=CronTrigger(
                    hour=17,       # 5:00 PM CT - markets closed
                    minute=0,
                    day_of_week='sun',  # Every Sunday
                    timezone='America/Chicago'
                ),
                id='quant_ml_training',
                name='QUANT - Weekly ML Model Training',
                replace_existing=True
            )
            logger.info("✅ QUANT job scheduled (WEEKLY on Sunday at 5:00 PM CT)")
        else:
            logger.warning("⚠️ QUANT not available - ML model training disabled")

        # =================================================================
        # GEX ML (Probability Models for ARGUS/HYPERION)
        # =================================================================
        # Trains the 5 XGBoost models used for strike probability calculations:
        # - Direction, Flip Gravity, Magnet Attraction, Volatility, Pin Zone
        # Training at 6:00 PM CT (after QUANT training at 5:00 PM)
        # =================================================================
        if GEX_PROBABILITY_MODELS_AVAILABLE:
            self.scheduler.add_job(
                self.scheduled_gex_ml_training_logic,
                trigger=CronTrigger(
                    hour=18,       # 6:00 PM CT - after QUANT training
                    minute=0,
                    day_of_week='sun',  # Every Sunday
                    timezone='America/Chicago'
                ),
                id='gex_ml_training',
                name='GEX ML - Weekly Probability Models Training',
                replace_existing=True
            )
            logger.info("✅ GEX ML job scheduled (WEEKLY on Sunday at 6:00 PM CT)")
        else:
            logger.warning("⚠️ GEX ML not available - probability models training disabled")

        # =================================================================
        # AUTO-VALIDATION JOB: ML Model Health Check - runs WEEKLY on Saturday
        # Validates ALL 11 ML models using walk-forward validation:
        # - Checks in-sample vs out-of-sample accuracy
        # - Triggers auto-retrain if degradation exceeds threshold
        # - Updates Thompson Sampling capital allocation
        # Runs Saturday to prepare models for Sunday training if needed
        # =================================================================
        if AUTO_VALIDATION_AVAILABLE:
            self.scheduler.add_job(
                self.scheduled_validation_logic,
                trigger=CronTrigger(
                    hour=18,       # 6:00 PM CT - after market close
                    minute=0,
                    day_of_week='sat',  # Every Saturday
                    timezone='America/Chicago'
                ),
                id='auto_validation',
                name='VALIDATION - Weekly ML Model Health Check',
                replace_existing=True
            )
            logger.info("✅ AUTO-VALIDATION job scheduled (WEEKLY on Saturday at 6:00 PM CT)")
        else:
            logger.warning("⚠️ AutoValidationSystem not available - ML validation disabled")

        # =================================================================
        # EQUITY SNAPSHOTS JOB: Intraday chart data - runs every 5 minutes
        # Saves equity snapshots for all bots during market hours
        # Jobs run immediately on startup and every 5 min thereafter.
        # =================================================================
        self.scheduler.add_job(
            self.scheduled_equity_snapshots_logic,
            trigger=IntervalTrigger(
                minutes=5,
                timezone='America/Chicago'
            ),
            id='equity_snapshots',
            name='EQUITY_SNAPSHOTS - Intraday Chart Data',
            replace_existing=True,
            next_run_time=datetime.now(CENTRAL_TZ)  # Run immediately on startup
        )
        logger.info("✅ EQUITY_SNAPSHOTS job scheduled (runs NOW, then every 5 min)")

        # =================================================================
        # TRADE_SYNC JOB: Data Integrity Sync - runs every 30 minutes
        # Performs critical data synchronization:
        # - Cleanup stale positions (expired but still 'open')
        # - Fix missing P&L values on closed positions
        # - Sync bot tables to unified tracking tables
        # =================================================================
        self.scheduler.add_job(
            self.scheduled_trade_sync_logic,
            trigger=IntervalTrigger(
                minutes=30,
                timezone='America/Chicago'
            ),
            id='trade_sync',
            name='TRADE_SYNC - Data Integrity Sync',
            replace_existing=True
        )
        logger.info("✅ TRADE_SYNC job scheduled (every 30 min, checks market hours internally)")

        # =================================================================
        # CRITICAL: Verify at least one trading bot is available
        # If ALL bots failed to initialize, the scheduler will run but do NOTHING
        # =================================================================
        active_bots = []
        if self.ares_trader:
            active_bots.append("ARES")
        if self.athena_trader:
            active_bots.append("ATHENA")
        if self.pegasus_trader:
            active_bots.append("PEGASUS")
        if self.icarus_trader:
            active_bots.append("ICARUS")
        if self.titan_trader:
            active_bots.append("TITAN")
        if self.atlas_trader:
            active_bots.append("ATLAS")
        if self.trader:
            active_bots.append("PHOENIX")

        if not active_bots:
            logger.error("=" * 80)
            logger.error("🚨 CRITICAL: NO TRADING BOTS INITIALIZED!")
            logger.error("🚨 The scheduler will start but NO SCANS will run!")
            logger.error("🚨 Check bot imports and initialization errors above!")
            logger.error("=" * 80)
        else:
            logger.info(f"✅ Active bots: {', '.join(active_bots)}")

        # Start the scheduler with proper exception handling
        try:
            self.scheduler.start()
            self.is_running = True

            # Verify jobs were actually scheduled
            jobs = self.scheduler.get_jobs()
            if len(jobs) == 0:
                logger.error("🚨 CRITICAL: Scheduler started but NO JOBS scheduled!")
            else:
                logger.info(f"✅ Scheduler started with {len(jobs)} jobs scheduled")

        except Exception as e:
            logger.error(f"CRITICAL: Failed to start scheduler: {e}")
            logger.error(traceback.format_exc())
            self.is_running = False
            self.scheduler = None
            raise RuntimeError(f"Scheduler failed to start: {e}")

        # Mark that auto-restart should be enabled
        self._mark_auto_restart("User started")
        self._clear_auto_restart()  # Clear immediately - we're running now
        self._save_state()  # Save running state

        # =================================================================
        # STARTUP HEARTBEAT: Save initial heartbeat for all bots
        # This ensures dashboard shows the scheduler is alive immediately,
        # even before the first job runs (which might be 5 minutes away).
        # =================================================================
        logger.info("Saving startup heartbeats for all bots...")
        is_open, market_status = self.get_market_status()
        startup_status = 'STARTING' if is_open else market_status
        startup_details = {'event': 'scheduler_startup', 'market_status': market_status}

        for bot_name in ['ARES', 'ATHENA', 'PEGASUS', 'ICARUS', 'TITAN', 'ATLAS', 'PHOENIX']:
            try:
                self._save_heartbeat(bot_name, startup_status, startup_details)
            except Exception as e:
                logger.debug(f"Could not save startup heartbeat for {bot_name}: {e}")
        logger.info(f"✅ Startup heartbeats saved for all bots (status: {startup_status})")

        logger.info("✓ Scheduler started successfully")
        logger.info("✓ Auto-restart enabled - will survive app restarts")
        logger.info("Next scheduled runs:")

        # Log next scheduled runs with error handling
        try:
            if self.scheduler:
                jobs = self.scheduler.get_jobs()
                if jobs:
                    for job in jobs[:5]:  # Limit to first 5
                        next_run = job.next_run_time
                        if next_run:
                            logger.info(f"  - {job.name}: {next_run.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        except Exception as e:
            logger.warning(f"Could not get scheduled jobs: {e}")

    def stop(self):
        """Stop the autonomous trading scheduler"""
        if not APSCHEDULER_AVAILABLE:
            logger.warning("Cannot stop scheduler - APScheduler not available")
            return

        if not self.is_running:
            logger.warning("Scheduler is not running")
            return

        logger.info("Stopping autonomous trading scheduler...")

        if self.scheduler:
            self.scheduler.shutdown()
            self.scheduler = None

        self.is_running = False

        # Clear auto-restart flag - user manually stopped
        self._clear_auto_restart()
        self._save_state()  # Save stopped state

        logger.info("✓ Scheduler stopped")
        logger.info("✓ Auto-restart disabled - won't restart on app reload")

    def is_scheduler_healthy(self) -> bool:
        """
        Check if the scheduler is healthy.

        This performs TWO checks:
        1. Thread liveness: Is the APScheduler thread alive?
        2. Job execution: Are jobs actually running? (checks last_*_check timestamps)

        The scheduler can be in a zombie state where the thread is alive but
        jobs aren't executing. This method detects both conditions.
        """
        if not self.is_running or not self.scheduler:
            return False

        try:
            # Check 1: Is APScheduler's internal thread alive?
            if hasattr(self.scheduler, '_thread') and self.scheduler._thread:
                if not self.scheduler._thread.is_alive():
                    logger.warning("Health check: APScheduler thread is DEAD")
                    return False
            else:
                # Fallback: try to get jobs (will fail if scheduler is dead)
                self.scheduler.get_jobs()

            # Check 2: Are jobs actually executing?
            # If ARES/ATHENA haven't run in 15+ minutes, something is wrong
            # (they should run every 5 minutes)
            now = datetime.now(CENTRAL_TZ)
            max_stale_minutes = 15  # Jobs run every 5 min, allow 3x buffer

            # Only check job staleness if we have traders initialized
            # and have had at least one check
            stale_jobs = []

            if self.ares_trader and self.last_ares_check:
                ares_age = (now - self.last_ares_check).total_seconds() / 60
                if ares_age > max_stale_minutes:
                    stale_jobs.append(f"ARES ({ares_age:.1f} min stale)")

            if self.athena_trader and self.last_athena_check:
                athena_age = (now - self.last_athena_check).total_seconds() / 60
                if athena_age > max_stale_minutes:
                    stale_jobs.append(f"ATHENA ({athena_age:.1f} min stale)")

            if self.pegasus_trader and self.last_pegasus_check:
                pegasus_age = (now - self.last_pegasus_check).total_seconds() / 60
                if pegasus_age > max_stale_minutes:
                    stale_jobs.append(f"PEGASUS ({pegasus_age:.1f} min stale)")

            if self.icarus_trader and self.last_icarus_check:
                icarus_age = (now - self.last_icarus_check).total_seconds() / 60
                if icarus_age > max_stale_minutes:
                    stale_jobs.append(f"ICARUS ({icarus_age:.1f} min stale)")

            if self.titan_trader and self.last_titan_check:
                titan_age = (now - self.last_titan_check).total_seconds() / 60
                if titan_age > max_stale_minutes:
                    stale_jobs.append(f"TITAN ({titan_age:.1f} min stale)")

            if stale_jobs:
                logger.warning(f"Health check: STALE JOBS detected - {', '.join(stale_jobs)}")
                return False

            return True

        except Exception as e:
            logger.error(f"Health check exception: {e}")
            return False

    def get_status(self) -> dict:
        """Get current scheduler status for monitoring dashboard"""
        now = datetime.now(CENTRAL_TZ)

        status = {
            'is_running': self.is_running,
            'scheduler_healthy': self.is_scheduler_healthy(),
            'market_open': self.is_market_open(),
            'current_time_ct': now.strftime('%Y-%m-%d %H:%M:%S %Z'),
            'last_trade_check': self.last_trade_check.strftime('%Y-%m-%d %H:%M:%S') if self.last_trade_check else 'Never',
            'last_position_check': self.last_position_check.strftime('%Y-%m-%d %H:%M:%S') if self.last_position_check else 'Never',
            'execution_count': self.execution_count,
            'last_error': self.last_error,
            'scheduled_jobs': [],
        }

        # Get all scheduled jobs with their next run times (with error handling)
        if self.is_running and self.scheduler:
            try:
                jobs = self.scheduler.get_jobs()
                for job in jobs:
                    job_info = {
                        'id': job.id,
                        'name': job.name,
                        'next_run': job.next_run_time.strftime('%Y-%m-%d %H:%M:%S %Z') if job.next_run_time else 'Not scheduled'
                    }
                    status['scheduled_jobs'].append(job_info)

                if jobs:
                    status['next_run'] = jobs[0].next_run_time.strftime('%Y-%m-%d %H:%M:%S %Z') if jobs[0].next_run_time else 'Not scheduled'
                else:
                    status['next_run'] = 'No jobs'
            except Exception as e:
                logger.warning(f"Error getting scheduled jobs: {e}")
                status['next_run'] = 'Error getting jobs'
                status['scheduler_healthy'] = False
        else:
            status['next_run'] = 'Scheduler not running'

        # Add QUANT training availability info
        status['quant_training'] = {
            'regime_classifier_available': REGIME_CLASSIFIER_AVAILABLE,
            'gex_directional_available': GEX_DIRECTIONAL_AVAILABLE,
            'schedule': 'Sunday 5:00 PM CT (weekly)'
        }

        # Add GEX ML training availability info
        status['gex_ml_training'] = {
            'available': GEX_PROBABILITY_MODELS_AVAILABLE,
            'schedule': 'Sunday 6:00 PM CT (weekly)',
            'models': ['direction', 'flip_gravity', 'magnet_attraction', 'volatility', 'pin_zone'],
            'used_by': ['ARGUS', 'HYPERION']
        }

        return status

    def get_recent_logs(self, lines: int = 50) -> list:
        """Get recent log entries for monitoring dashboard"""
        try:
            if LOG_FILE.exists():
                with open(LOG_FILE, 'r') as f:
                    all_lines = f.readlines()
                    return all_lines[-lines:]  # Return last N lines
            return []
        except Exception as e:
            logger.error(f"Error reading logs: {e}")
            return [f"Error reading logs: {str(e)}"]


# Global singleton instance
_scheduler_instance = None

def get_scheduler() -> AutonomousTraderScheduler:
    """Get or create the global scheduler instance"""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = AutonomousTraderScheduler()
    return _scheduler_instance


def get_ares_trader():
    """Get the ARES trader instance from the scheduler"""
    scheduler = get_scheduler()
    return scheduler.ares_trader if scheduler else None


def get_atlas_trader():
    """Get the ATLAS trader instance from the scheduler"""
    scheduler = get_scheduler()
    return scheduler.atlas_trader if scheduler else None


def get_athena_trader():
    """Get the ATHENA trader instance from the scheduler"""
    scheduler = get_scheduler()
    return scheduler.athena_trader if scheduler else None


def get_pegasus_trader():
    """Get the PEGASUS trader instance from the scheduler"""
    scheduler = get_scheduler()
    return scheduler.pegasus_trader if scheduler else None


def get_icarus_trader():
    """Get the ICARUS trader instance from the scheduler"""
    scheduler = get_scheduler()
    return scheduler.icarus_trader if scheduler else None


def get_titan_trader():
    """Get the TITAN trader instance from the scheduler"""
    scheduler = get_scheduler()
    return scheduler.titan_trader if scheduler else None


# ============================================================================
# STANDALONE EXECUTION MODE (for Render Background Worker)
# ============================================================================
def run_standalone():
    """
    Run the scheduler as a standalone process (for Render deployment).

    This runs BOTH bots:
    - PHOENIX: 0DTE SPY/SPX options (hourly during market hours)
    - ATLAS: SPX Wheel strategy (daily at 10:05 AM ET)

    The scheduler will:
    - Auto-start on launch
    - Run continuously during market hours
    - Auto-restart on errors
    - Persist state to database
    """
    import signal
    import time

    logger.info("=" * 80)
    logger.info("ALPHAGEX AUTONOMOUS TRADER - STANDALONE MODE")
    logger.info("=" * 80)
    logger.info(f"PHOENIX (0DTE):      ${CAPITAL_ALLOCATION['PHOENIX']:,}")
    logger.info(f"ATLAS (Wheel):       ${CAPITAL_ALLOCATION['ATLAS']:,}")
    logger.info(f"ARES (Aggressive):   ${CAPITAL_ALLOCATION['ARES']:,}")
    logger.info(f"RESERVE:             ${CAPITAL_ALLOCATION['RESERVE']:,}")
    logger.info("=" * 80)

    # Handle graceful shutdown
    shutdown_requested = False
    scheduler = None
    restart_count = 0
    max_restarts = 20  # Maximum restarts before giving up (higher for production resilience)
    health_check_failures = 0
    max_health_failures = 2  # Restart after 2 consecutive health check failures (more aggressive)
    last_status_log = time.time()

    def signal_handler(signum, frame):
        nonlocal shutdown_requested, last_status_log
        logger.info(f"Received signal {signum}, requesting shutdown...")
        shutdown_requested = True
        try:
            if scheduler and scheduler.is_running:
                scheduler.stop()
        except Exception as e:
            logger.error(f"Error stopping scheduler in signal handler: {e}")

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    def start_scheduler():
        """Start or restart the scheduler with error handling"""
        nonlocal scheduler, restart_count

        # Clear the singleton to force a fresh instance on restart
        global _scheduler_instance
        _scheduler_instance = None

        scheduler = get_scheduler()
        try:
            scheduler.start()
            restart_count += 1
            logger.info(f"Scheduler started (attempt #{restart_count})")
            return True
        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")
            logger.error(traceback.format_exc())
            return False

    # Initial start
    if not start_scheduler():
        logger.error("CRITICAL: Could not start scheduler on initial attempt")
        return

    logger.info("Scheduler started. Running continuously with health monitoring...")
    logger.info("Press Ctrl+C to stop (or send SIGTERM)")

    # Keep the process alive with health monitoring and auto-restart
    try:
        while not shutdown_requested:
            time.sleep(30)  # Check every 30 seconds (more aggressive monitoring)

            # Health check - verify scheduler thread is alive AND jobs are executing
            try:
                if scheduler and scheduler.is_scheduler_healthy():
                    health_check_failures = 0  # Reset on success

                    # Log status every 5 minutes
                    current_time = time.time()
                    if current_time - last_status_log >= 300:  # 5 minutes
                        status = scheduler.get_status()
                        now_ct = datetime.now(CENTRAL_TZ)

                        # Log scan counts and last check times for visibility
                        logger.info(f"[HEALTH OK @ {now_ct.strftime('%H:%M:%S')}] "
                                   f"ARES={scheduler.ares_execution_count} (last: {scheduler.last_ares_check.strftime('%H:%M:%S') if scheduler.last_ares_check else 'never'}), "
                                   f"ATHENA={scheduler.athena_execution_count} (last: {scheduler.last_athena_check.strftime('%H:%M:%S') if scheduler.last_athena_check else 'never'}), "
                                   f"restarts={restart_count}")

                        last_status_log = current_time
                else:
                    health_check_failures += 1
                    now_ct = datetime.now(CENTRAL_TZ)
                    logger.warning(f"[HEALTH FAIL @ {now_ct.strftime('%H:%M:%S')}] "
                                  f"Health check FAILED ({health_check_failures}/{max_health_failures}) - "
                                  f"ARES last: {scheduler.last_ares_check.strftime('%H:%M:%S') if scheduler and scheduler.last_ares_check else 'never'}, "
                                  f"ATHENA last: {scheduler.last_athena_check.strftime('%H:%M:%S') if scheduler and scheduler.last_athena_check else 'never'}")

                    if health_check_failures >= max_health_failures:
                        logger.error("SCHEDULER DEAD - Attempting auto-restart...")

                        if restart_count >= max_restarts:
                            logger.error(f"Max restarts ({max_restarts}) reached. Exiting.")
                            shutdown_requested = True
                            break

                        # Stop the dead scheduler
                        try:
                            if scheduler:
                                scheduler.stop()
                        except Exception:
                            pass

                        # Wait before restart
                        time.sleep(5)

                        # Restart
                        if start_scheduler():
                            health_check_failures = 0
                            logger.info("Scheduler auto-restart SUCCESSFUL")
                        else:
                            logger.error("Scheduler auto-restart FAILED")
                            time.sleep(30)  # Wait longer before next attempt

            except Exception as e:
                logger.error(f"Error in health check loop: {e}")
                logger.error(traceback.format_exc())
                health_check_failures += 1

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"CRITICAL ERROR in main loop: {e}")
        logger.error(traceback.format_exc())
    finally:
        logger.info("=" * 60)
        logger.info("GRACEFUL SHUTDOWN SEQUENCE")
        logger.info("=" * 60)

        # Step 1: Stop the scheduler
        try:
            if scheduler and scheduler.is_running:
                logger.info("[SHUTDOWN] Stopping APScheduler...")
                scheduler.stop()
                logger.info("[SHUTDOWN] APScheduler stopped")
        except Exception as e:
            logger.error(f"[SHUTDOWN] Error stopping scheduler: {e}")

        # Step 2: Log open positions for safeguarding awareness
        try:
            logger.info("[SHUTDOWN] Checking open positions...")
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT bot_name, COUNT(*) as count
                FROM autonomous_open_positions
                WHERE status = 'OPEN'
                GROUP BY bot_name
            """)
            rows = cursor.fetchall()
            if rows:
                logger.warning("[SHUTDOWN] OPEN POSITIONS AT WORKER SHUTDOWN:")
                for row in rows:
                    logger.warning(f"  {row[0]}: {row[1]} positions")
            else:
                logger.info("[SHUTDOWN] No open positions")
            cursor.close()
            conn.close()
        except Exception as e:
            logger.error(f"[SHUTDOWN] Position check failed: {e}")

        # Step 3: Close database connection pool
        try:
            from database_adapter import close_pool
            logger.info("[SHUTDOWN] Closing database connection pool...")
            close_pool()
            logger.info("[SHUTDOWN] Database pool closed")
        except Exception as e:
            logger.error(f"[SHUTDOWN] Database pool close failed: {e}")

        logger.info("=" * 60)
        logger.info("Autonomous trader shutdown complete")
        logger.info("=" * 60)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--standalone":
        run_standalone()
    else:
        # Default: run standalone mode (for Render)
        run_standalone()
