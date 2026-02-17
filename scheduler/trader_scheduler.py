"""
Autonomous Trading Scheduler for Render Deployment
Uses APScheduler to run trading logic during market hours
Integrates seamlessly with Streamlit web service

CAPITAL ALLOCATION:
==================
Total Capital: $1,000,000
├── LAZARUS (0DTE SPY/SPX):      $300,000 (30%)
├── CORNERSTONE (SPX Wheel):           $400,000 (40%)
├── FORTRESS (Aggressive IC):        $200,000 (20%)
└── Reserve:                     $100,000 (10%)

TRADING BOTS:
============
- LAZARUS: 0DTE options trading (hourly 10 AM - 3 PM ET)
- CORNERSTONE: SPX Cash-Secured Put Wheel (daily at 10:05 AM ET)
- FORTRESS: Aggressive Iron Condor targeting 10% monthly (every 5 min 8:30 AM - 2:55 PM CT)
- SOLOMON: GEX Directional Spreads (every 5 min 8:35 AM - 2:30 PM CT)
- ALL EOD: Process expired positions at 3:01 PM CT (all bots run simultaneously for <5 min reconciliation)
- WATCHTOWER: Gamma Commentary Generation (every 5 min 8:30 AM - 3:00 PM CT)

All bots now scan every 5 minutes for optimal entry timing and log NO_TRADE
decisions with full context when they scan but don't take a trade.

This partitioning provides:
- Aggressive short-term trading via LAZARUS
- Steady premium collection via CORNERSTONE wheel
- High-return strategy via FORTRESS Iron Condors
- Reserve for margin calls and opportunities
"""

# ============================================================================
# CAPITAL ALLOCATION CONFIGURATION
# ============================================================================
CAPITAL_ALLOCATION = {
    'LAZARUS': 250_000,   # 0DTE options trading
    'CORNERSTONE': 300_000,     # SPX wheel strategy
    'FORTRESS': 150_000,      # Aggressive Iron Condor (SPY 0DTE)
    'ANCHOR': 200_000,   # SPX Iron Condor ($10 spreads, weekly)
    'SAMSON': 200_000,     # Aggressive SPX Iron Condor ($12 spreads, daily)
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

# Import CORNERSTONE (SPX Wheel Trader)
try:
    from trading.spx_wheel_system import SPXWheelTrader, TradingMode
    CORNERSTONE_AVAILABLE = True
except ImportError:
    CORNERSTONE_AVAILABLE = False
    SPXWheelTrader = None
    TradingMode = None
    print("Warning: SPXWheelTrader not available. CORNERSTONE bot will be disabled.")

# Import FORTRESS V2 (SPY Iron Condors)
try:
    from trading.fortress_v2 import FortressTrader, FortressConfig, TradingMode as FortressTradingMode
    FORTRESS_AVAILABLE = True
except ImportError:
    FORTRESS_AVAILABLE = False
    FortressTrader = None
    FortressConfig = None
    FortressTradingMode = None
    print("Warning: FORTRESS V2 not available. FORTRESS bot will be disabled.")

# Import SOLOMON V2 (SPY Directional Spreads)
try:
    from trading.solomon_v2 import SolomonTrader, SolomonConfig, TradingMode as SOLOMONTradingMode
    SOLOMON_AVAILABLE = True
except ImportError:
    SOLOMON_AVAILABLE = False
    SolomonTrader = None
    SolomonConfig = None
    SOLOMONTradingMode = None
    print("Warning: SOLOMON V2 not available. SOLOMON bot will be disabled.")

# Import ANCHOR (SPX Iron Condors)
try:
    from trading.anchor import AnchorTrader, AnchorConfig, TradingMode as ANCHORTradingMode
    ANCHOR_AVAILABLE = True
except ImportError:
    ANCHOR_AVAILABLE = False
    AnchorTrader = None
    AnchorConfig = None
    ANCHORTradingMode = None
    print("Warning: ANCHOR not available. SPX trading will be disabled.")

# Import GIDEON (Aggressive Directional Spreads - relaxed GEX filters)
try:
    from trading.gideon import GideonTrader, GideonConfig, TradingMode as GideonTradingMode
    GIDEON_AVAILABLE = True
except ImportError:
    GIDEON_AVAILABLE = False
    GideonTrader = None
    GideonConfig = None
    GideonTradingMode = None
    print("Warning: GIDEON not available. Aggressive directional trading will be disabled.")

# Import SAMSON (Aggressive SPX Iron Condors - daily trading)
try:
    from trading.samson import SamsonTrader, SamsonConfig, TradingMode as SamsonTradingMode
    SAMSON_AVAILABLE = True
except ImportError:
    SAMSON_AVAILABLE = False
    SamsonTrader = None
    SamsonConfig = None
    SamsonTradingMode = None
    print("Warning: SAMSON not available. Aggressive SPX Iron Condor trading will be disabled.")

# Import JUBILEE (Box Spread Synthetic Borrowing)
try:
    from trading.jubilee import JubileeTrader, JubileeConfig, TradingMode as JubileeTradingMode
    JUBILEE_BOX_AVAILABLE = True
except ImportError:
    JUBILEE_BOX_AVAILABLE = False
    JubileeTrader = None
    JubileeConfig = None
    JubileeTradingMode = None
    print("Warning: JUBILEE Box Spread not available. Synthetic borrowing will be disabled.")

# Import JUBILEE IC Trader (Iron Condor trading with borrowed capital)
try:
    from trading.jubilee.trader import JubileeICTrader, run_jubilee_ic_cycle
    from trading.jubilee.models import JubileeICConfig
    JUBILEE_IC_AVAILABLE = True
except ImportError:
    JUBILEE_IC_AVAILABLE = False
    JubileeICTrader = None
    JubileeICConfig = None
    run_jubilee_ic_cycle = None
    print("Warning: JUBILEE IC Trader not available. IC trading will be disabled.")

# Import VALOR (MES Futures Scalping with GEX)
try:
    from trading.valor import ValorTrader, ValorConfig, TradingMode as ValorTradingMode
    VALOR_AVAILABLE = True
except ImportError:
    VALOR_AVAILABLE = False
    ValorTrader = None
    ValorConfig = None
    ValorTradingMode = None
    print("Warning: VALOR not available. MES futures trading will be disabled.")

# Import AGAPE (ETH Micro Futures with Crypto GEX)
try:
    from trading.agape.trader import AgapeTrader, create_agape_trader
    from trading.agape.models import AgapeConfig, TradingMode as AgapeTradingMode
    AGAPE_AVAILABLE = True
except ImportError:
    AGAPE_AVAILABLE = False
    AgapeTrader = None
    AgapeConfig = None
    AgapeTradingMode = None
    print("Warning: AGAPE not available. ETH crypto trading will be disabled.")

# Import AGAPE-SPOT (24/7 Coinbase Spot ETH)
try:
    from trading.agape_spot.trader import AgapeSpotTrader, create_agape_spot_trader
    AGAPE_SPOT_AVAILABLE = True
except ImportError:
    AGAPE_SPOT_AVAILABLE = False
    AgapeSpotTrader = None
    print("Warning: AGAPE-SPOT not available. 24/7 spot ETH trading will be disabled.")

# Import AGAPE-BTC (BTC Micro Futures with Crypto GEX)
try:
    from trading.agape_btc.trader import AgapeBtcTrader, create_agape_btc_trader
    AGAPE_BTC_AVAILABLE = True
except ImportError:
    AGAPE_BTC_AVAILABLE = False
    AgapeBtcTrader = None
    print("Warning: AGAPE-BTC not available. BTC crypto trading will be disabled.")

# Import AGAPE-XRP (XRP Futures with Crypto GEX)
try:
    from trading.agape_xrp.trader import AgapeXrpTrader, create_agape_xrp_trader
    AGAPE_XRP_AVAILABLE = True
except ImportError:
    AGAPE_XRP_AVAILABLE = False
    AgapeXrpTrader = None
    print("Warning: AGAPE-XRP not available. XRP crypto trading will be disabled.")

# Import AGAPE-ETH-PERP (ETH Perpetual Contract)
try:
    from trading.agape_eth_perp.trader import AgapeEthPerpTrader, create_agape_eth_perp_trader
    AGAPE_ETH_PERP_AVAILABLE = True
except ImportError:
    AGAPE_ETH_PERP_AVAILABLE = False
    AgapeEthPerpTrader = None
    print("Warning: AGAPE-ETH-PERP not available. ETH perpetual trading will be disabled.")

# Import AGAPE-BTC-PERP (BTC Perpetual Contract)
try:
    from trading.agape_btc_perp.trader import AgapeBtcPerpTrader, create_agape_btc_perp_trader
    AGAPE_BTC_PERP_AVAILABLE = True
except ImportError:
    AGAPE_BTC_PERP_AVAILABLE = False
    AgapeBtcPerpTrader = None
    print("Warning: AGAPE-BTC-PERP not available. BTC perpetual trading will be disabled.")

# Import AGAPE-XRP-PERP (XRP Perpetual Contract)
try:
    from trading.agape_xrp_perp.trader import AgapeXrpPerpTrader, create_agape_xrp_perp_trader
    AGAPE_XRP_PERP_AVAILABLE = True
except ImportError:
    AGAPE_XRP_PERP_AVAILABLE = False
    AgapeXrpPerpTrader = None
    print("Warning: AGAPE-XRP-PERP not available. XRP perpetual trading will be disabled.")

# Import AGAPE-DOGE-PERP (DOGE Perpetual Contract)
try:
    from trading.agape_doge_perp.trader import AgapeDogePerpTrader, create_agape_doge_perp_trader
    AGAPE_DOGE_PERP_AVAILABLE = True
except ImportError:
    AGAPE_DOGE_PERP_AVAILABLE = False
    AgapeDogePerpTrader = None
    print("Warning: AGAPE-DOGE-PERP not available. DOGE perpetual trading will be disabled.")

# Import AGAPE-SHIB-PERP (SHIB Perpetual Contract)
try:
    from trading.agape_shib_perp.trader import AgapeShibPerpTrader, create_agape_shib_perp_trader
    AGAPE_SHIB_PERP_AVAILABLE = True
except ImportError:
    AGAPE_SHIB_PERP_AVAILABLE = False
    AgapeShibPerpTrader = None
    print("Warning: AGAPE-SHIB-PERP not available. SHIB perpetual trading will be disabled.")

# Import FAITH (2DTE Paper Iron Condor)
try:
    from trading.faith.trader import FaithTrader
    FAITH_AVAILABLE = True
except ImportError:
    FAITH_AVAILABLE = False
    FaithTrader = None
    print("Warning: FAITH not available. 2DTE paper IC trading will be disabled.")

# Import GRACE (1DTE Paper Iron Condor - for comparison with FAITH)
try:
    from trading.grace.trader import GraceTrader
    GRACE_AVAILABLE = True
except ImportError:
    GRACE_AVAILABLE = False
    GraceTrader = None
    print("Warning: GRACE not available. 1DTE paper IC trading will be disabled.")

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
    from trading.decision_logger import get_lazarus_logger, get_cornerstone_logger, get_fortress_logger, BotName
    DECISION_LOGGER_AVAILABLE = True
except ImportError:
    DECISION_LOGGER_AVAILABLE = False
    print("Warning: Decision logger not available.")

# Import PROVERBS (Feedback Loop Intelligence System)
try:
    from quant.proverbs_feedback_loop import get_proverbs, run_feedback_loop
    PROVERBS_AVAILABLE = True
except ImportError:
    PROVERBS_AVAILABLE = False
    get_proverbs = None
    run_feedback_loop = None
    print("Warning: Proverbs not available. Feedback loop will be disabled.")

# REMOVED: ML Regime Classifier - Prophet is god
# The MLRegimeClassifier import and training code has been removed.
# Prophet decides all trades.
REGIME_CLASSIFIER_AVAILABLE = False

try:
    from quant.gex_directional_ml import GEXDirectionalPredictor
    GEX_DIRECTIONAL_AVAILABLE = True
except ImportError:
    GEX_DIRECTIONAL_AVAILABLE = False
    GEXDirectionalPredictor = None
    print("Warning: GEXDirectionalPredictor not available. Directional ML training will be disabled.")

# Import GEX Probability Models for WATCHTOWER/GLORY ML training
try:
    from quant.gex_probability_models import GEXSignalGenerator
    GEX_PROBABILITY_MODELS_AVAILABLE = True
except ImportError:
    GEX_PROBABILITY_MODELS_AVAILABLE = False
    GEXSignalGenerator = None
    print("Warning: GEXSignalGenerator not available. GEX ML training will be disabled.")

# Import FORTRESS ML Advisor for scheduled ML training
try:
    from quant.fortress_ml_advisor import get_advisor as get_fortress_ml_advisor
    FORTRESS_ML_AVAILABLE = True
except ImportError:
    FORTRESS_ML_AVAILABLE = False
    get_fortress_ml_advisor = None
    print("Warning: FORTRESS ML Advisor not available. FORTRESS ML training will be disabled.")

# Import DISCERNMENT ML Engine for scheduled ML training
try:
    from core.discernment_ml_engine import get_discernment_engine
    DISCERNMENT_ML_AVAILABLE = True
except ImportError:
    DISCERNMENT_ML_AVAILABLE = False
    get_discernment_engine = None
    print("Warning: DISCERNMENT ML Engine not available. DISCERNMENT training will be disabled.")

# Import VALOR ML Advisor for scheduled ML training
try:
    from trading.valor.ml import get_valor_ml_advisor
    VALOR_ML_AVAILABLE = True
except ImportError:
    VALOR_ML_AVAILABLE = False
    get_valor_ml_advisor = None
    print("Warning: VALOR ML Advisor not available. VALOR ML training will be disabled.")

# Import SPX Wheel ML Trainer for scheduled ML training
try:
    from trading.spx_wheel_ml import get_spx_wheel_ml_trainer
    SPX_WHEEL_ML_AVAILABLE = True
except ImportError:
    SPX_WHEEL_ML_AVAILABLE = False
    get_spx_wheel_ml_trainer = None
    print("Warning: SPX Wheel ML not available. SPX Wheel ML training will be disabled.")

# Import Pattern Learner for scheduled ML training
try:
    from ai.autonomous_ml_pattern_learner import PatternLearner
    PATTERN_LEARNER_AVAILABLE = True
except ImportError:
    PATTERN_LEARNER_AVAILABLE = False
    PatternLearner = None
    print("Warning: Pattern Learner not available. Pattern learning will be disabled.")


def populate_recent_gex_structures(days: int = 30) -> dict:
    """
    Populate recent gex_structure_daily from options_chain_snapshots.

    This ensures STARS has fresh training data before ML model training.
    Runs automatically before GEX ML training on Sundays.

    Args:
        days: Number of recent days to process (default: 30)

    Returns:
        dict with success count, failed count, and any errors
    """
    from datetime import timedelta
    import traceback as tb

    results = {'success': 0, 'failed': 0, 'errors': [], 'skipped': 0}

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Check what snapshot data is available
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        cursor.execute("""
            SELECT DISTINCT DATE(timestamp) as trade_date
            FROM options_chain_snapshots
            WHERE DATE(timestamp) >= %s
            ORDER BY trade_date
        """, (start_date,))

        available_dates = [row[0] for row in cursor.fetchall()]

        if not available_dates:
            conn.close()
            results['errors'].append("No options_chain_snapshots data available")
            return results

        # Check which dates already have gex_structure_daily data
        cursor.execute("""
            SELECT DISTINCT trade_date
            FROM gex_structure_daily
            WHERE trade_date >= %s
        """, (start_date,))
        existing_dates = set(row[0] for row in cursor.fetchall())

        # Process only new dates
        new_dates = [d for d in available_dates if d not in existing_dates]

        if not new_dates:
            conn.close()
            results['skipped'] = len(available_dates)
            return results

        # Import the calculation logic
        try:
            from scripts.populate_gex_from_snapshots import (
                calculate_gex_from_snapshots,
                insert_gex_structure,
                ensure_tables
            )
        except ImportError as e:
            conn.close()
            results['errors'].append(f"Could not import populate_gex_from_snapshots: {e}")
            return results

        # Ensure tables exist
        ensure_tables(conn)

        # Process each new date for SPY (primary training data)
        for trade_date in new_dates:
            try:
                structure = calculate_gex_from_snapshots(conn, 'SPY', trade_date)
                if structure:
                    insert_gex_structure(conn, structure)
                    results['success'] += 1
                else:
                    results['failed'] += 1
            except Exception as e:
                conn.rollback()
                results['failed'] += 1
                if len(results['errors']) < 5:
                    results['errors'].append(f"{trade_date}: {str(e)[:100]}")

        conn.close()

    except Exception as e:
        results['errors'].append(f"Database error: {str(e)[:200]}")
        results['errors'].append(tb.format_exc()[:500])

    return results

# Import Auto-Validation System for ML model health monitoring and auto-retrain
try:
    from quant.auto_validation_system import (
        get_auto_validation_system, run_validation, get_validation_status
    )
    AUTO_VALIDATION_AVAILABLE = True
except ImportError:
    AUTO_VALIDATION_AVAILABLE = False
    get_auto_validation_system = None

# Import ProphetAdvisor for LAZARUS signal generation and feedback loop
try:
    from quant.prophet_advisor import (
        ProphetAdvisor, MarketContext as ProphetMarketContext, GEXRegime, TradingAdvice,
        BotName as ProphetBotName, TradeOutcome,  # Issue #2: LAZARUS feedback loop
        auto_train as prophet_auto_train  # Migration 023: Feedback loop integration
    )
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False
    ProphetAdvisor = None
    ProphetMarketContext = None
    GEXRegime = None
    TradingAdvice = None
    prophet_auto_train = None

# Import Proverbs Enhanced for strategy-level feedback
try:
    from quant.proverbs_enhancements import get_proverbs_enhanced, ProverbsEnhanced
    PROVERBS_ENHANCED_AVAILABLE = True
except ImportError:
    PROVERBS_ENHANCED_AVAILABLE = False
    get_proverbs_enhanced = None
    ProverbsEnhanced = None
    ProphetBotName = None
    TradeOutcome = None
    print("Warning: ProphetAdvisor not available for LAZARUS.")
    run_validation = None
    get_validation_status = None
    print("Warning: AutoValidationSystem not available. ML validation will be disabled.")

# Import scan activity logger for comprehensive scan visibility
try:
    from trading.scan_activity_logger import (
        log_fortress_scan, log_solomon_scan, log_anchor_scan, log_gideon_scan, log_samson_scan,
        ScanOutcome
    )
    SCAN_ACTIVITY_LOGGER_AVAILABLE = True
    print("✅ Scan activity logger loaded - scans will be logged to database")
except ImportError as e:
    SCAN_ACTIVITY_LOGGER_AVAILABLE = False
    log_fortress_scan = None
    log_solomon_scan = None
    log_anchor_scan = None
    log_gideon_scan = None
    log_samson_scan = None
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

        # LAZARUS - 0DTE SPY/SPX Options Trader
        # Capital: $400,000 (40% of total)
        # CRITICAL: Wrap in try-except to prevent scheduler crash if LAZARUS init fails
        self.trader = None
        self.api_client = None
        self.lazarus_prophet = None  # Prophet for LAZARUS signal validation
        try:
            self.trader = AutonomousPaperTrader(
                symbol='SPY',
                capital=CAPITAL_ALLOCATION['LAZARUS']
            )
            self.api_client = TradingVolatilityAPI()
            # Initialize Prophet for LAZARUS signal validation
            if PROPHET_AVAILABLE:
                self.lazarus_prophet = ProphetAdvisor()
                logger.info(f"✅ LAZARUS initialized with ${CAPITAL_ALLOCATION['LAZARUS']:,} capital + Prophet")
            else:
                logger.info(f"✅ LAZARUS initialized with ${CAPITAL_ALLOCATION['LAZARUS']:,} capital (no Prophet)")
        except Exception as e:
            logger.error(f"LAZARUS initialization failed: {e}")
            logger.error("Scheduler will continue without LAZARUS - other bots will still run")

        # CORNERSTONE - SPX Cash-Secured Put Wheel Trader
        # Capital: $400,000 (40% of total)
        # LIVE mode: Executes real trades on Tradier (production API for SPX)
        self.cornerstone_trader = None
        if CORNERSTONE_AVAILABLE:
            try:
                self.cornerstone_trader = SPXWheelTrader(
                    mode=TradingMode.LIVE,
                    initial_capital=CAPITAL_ALLOCATION['CORNERSTONE']
                )
                logger.info(f"✅ CORNERSTONE initialized with ${CAPITAL_ALLOCATION['CORNERSTONE']:,} capital (LIVE mode - Tradier)")
            except Exception as e:
                logger.warning(f"CORNERSTONE initialization failed: {e}")
                self.cornerstone_trader = None

        # FORTRESS V2 - SPY Iron Condors (10% monthly target)
        # Capital: Uses AlphaGEX internal capital allocation
        # LIVE mode: Executes trades on Tradier SANDBOX accounts (3 accounts)
        self.fortress_trader = None
        if FORTRESS_AVAILABLE:
            try:
                config = FortressConfig(mode=FortressTradingMode.LIVE)
                self.fortress_trader = FortressTrader(config=config)
                logger.info(f"✅ FORTRESS V2 initialized (SPY Iron Condors, LIVE mode - Tradier SANDBOX)")
            except Exception as e:
                logger.warning(f"FORTRESS V2 initialization failed: {e}")
                self.fortress_trader = None

        # SOLOMON V2 - SPY Directional Spreads
        # Uses GEX + ML signals for directional spread trading
        # PAPER mode: Simulated trades with AlphaGEX internal capital, production Tradier for quotes only
        self.solomon_trader = None
        if SOLOMON_AVAILABLE:
            try:
                config = SolomonConfig(mode=SOLOMONTradingMode.PAPER)
                self.solomon_trader = SolomonTrader(config=config)
                logger.info(f"✅ SOLOMON V2 initialized (SPY Directional Spreads, PAPER mode - AlphaGEX internal)")
            except Exception as e:
                logger.warning(f"SOLOMON V2 initialization failed: {e}")
                self.solomon_trader = None

        # ANCHOR - SPX Iron Condors ($10 spreads)
        # Uses larger spread widths for SPX index options
        # PAPER mode: Simulated trades with AlphaGEX internal capital, production Tradier for SPX quotes
        self.anchor_trader = None
        if ANCHOR_AVAILABLE:
            try:
                config = AnchorConfig(mode=ANCHORTradingMode.PAPER)
                self.anchor_trader = AnchorTrader(config=config)
                logger.info(f"✅ ANCHOR initialized (SPX Iron Condors, PAPER mode - AlphaGEX internal)")
            except Exception as e:
                logger.warning(f"ANCHOR initialization failed: {e}")
                self.anchor_trader = None

        # GIDEON - Aggressive Directional Spreads (relaxed GEX filters)
        # Uses relaxed parameters vs SOLOMON: 10% wall filter, 40% min win prob, 4% risk
        # PAPER mode: Simulated trades with AlphaGEX internal capital, production Tradier for quotes
        self.gideon_trader = None
        if GIDEON_AVAILABLE:
            try:
                config = GideonConfig(mode=GideonTradingMode.PAPER)
                self.gideon_trader = GideonTrader(config=config)
                logger.info(f"✅ GIDEON initialized (Aggressive Directional Spreads, PAPER mode - AlphaGEX internal)")
            except Exception as e:
                logger.warning(f"GIDEON initialization failed: {e}")
                self.gideon_trader = None

        # SAMSON - Aggressive SPX Iron Condors ($12 spreads, daily trading)
        # Multiple trades per day with relaxed filters vs ANCHOR
        # PAPER mode: Simulated trades with AlphaGEX internal capital, production Tradier for SPX quotes
        self.samson_trader = None
        if SAMSON_AVAILABLE:
            try:
                config = SamsonConfig(mode=SamsonTradingMode.PAPER)
                self.samson_trader = SamsonTrader(config=config)
                logger.info(f"✅ SAMSON initialized (Aggressive SPX Iron Condors, PAPER mode - AlphaGEX internal)")
            except Exception as e:
                logger.warning(f"SAMSON initialization failed: {e}")
                self.samson_trader = None

        # FAITH - 2DTE Paper Iron Condor (SPY)
        # Paper-only bot: real Tradier data, simulated fills, $5K capital
        self.faith_trader = None
        if FAITH_AVAILABLE:
            try:
                self.faith_trader = FaithTrader()
                logger.info(f"✅ FAITH initialized (2DTE Paper Iron Condor, PAPER mode)")
            except Exception as e:
                logger.warning(f"FAITH 2DTE initialization failed: {e}")
                self.faith_trader = None

        # GRACE - 1DTE Paper Iron Condor (separate bot for comparison with FAITH)
        self.grace_trader = None
        if GRACE_AVAILABLE:
            try:
                self.grace_trader = GraceTrader()
                logger.info(f"✅ GRACE initialized (1DTE Paper Iron Condor, PAPER mode)")
            except Exception as e:
                logger.warning(f"GRACE initialization failed: {e}")
                self.grace_trader = None

        # JUBILEE - Box Spread Synthetic Borrowing
        # Generates cash through box spreads to fund IC bot volume scaling
        # PAPER mode: Simulated trades for testing the strategy
        self.jubilee_trader = None
        if JUBILEE_BOX_AVAILABLE:
            try:
                config = JubileeConfig(mode=JubileeTradingMode.PAPER)
                self.jubilee_trader = JubileeTrader(config=config)
                logger.info(f"✅ JUBILEE initialized (Box Spread Synthetic Borrowing, PAPER mode)")
            except Exception as e:
                logger.warning(f"JUBILEE initialization failed: {e}")
                self.jubilee_trader = None

        # JUBILEE: Ensure a viable box spread position exists at startup.
        # IC trading needs capital from box spreads. In PAPER mode, positions
        # are auto-extended (never roll), so just ensure one exists.
        if self.jubilee_trader:
            try:
                open_positions = self.jubilee_trader.get_positions()
                if not open_positions:
                    logger.warning("JUBILEE STARTUP: No open box spread found - creating one now")
                    self.jubilee_trader._create_emergency_paper_position()
                    logger.info("JUBILEE STARTUP: Box spread position created - IC trading is funded")
                else:
                    # Check if existing positions are still viable (not expired)
                    from datetime import date as _date
                    viable = any(
                        (datetime.strptime(p.get('expiration', '2000-01-01'), '%Y-%m-%d').date() - _date.today()).days > 0
                        for p in open_positions
                    )
                    if not viable:
                        logger.warning("JUBILEE STARTUP: All box spreads are expired - creating new one")
                        self.jubilee_trader._create_emergency_paper_position()
                        logger.info("JUBILEE STARTUP: Fresh box spread created - IC trading is funded")
                    else:
                        logger.info(f"JUBILEE STARTUP: {len(open_positions)} viable box spread(s) found - IC trading is funded")
            except Exception as e:
                logger.error(f"JUBILEE STARTUP: Failed to verify box spread: {e}")

        # JUBILEE IC - Iron Condor trading with borrowed capital
        # Uses capital from box spreads to trade SPX Iron Condors
        # This is the "returns engine" of the JUBILEE system
        self.jubilee_ic_trader = None
        if JUBILEE_IC_AVAILABLE:
            try:
                ic_config = JubileeICConfig()
                self.jubilee_ic_trader = JubileeICTrader(config=ic_config)
                logger.info(f"✅ JUBILEE IC initialized (SPX Iron Condors with borrowed capital, PAPER mode)")
            except Exception as e:
                logger.warning(f"JUBILEE IC initialization failed: {e}")
                self.jubilee_ic_trader = None

        # VALOR - MES Futures Scalping with GEX signals
        # 24/5 trading with 1-minute scan interval
        # PAPER mode: Simulated trades with $100k starting capital
        self.valor_trader = None
        if VALOR_AVAILABLE:
            try:
                config = ValorConfig(mode=ValorTradingMode.PAPER)
                self.valor_trader = ValorTrader(config=config)
                logger.info(f"✅ VALOR initialized (MES Futures Scalping, PAPER mode - $100k starting capital)")
            except Exception as e:
                logger.warning(f"VALOR initialization failed: {e}")
                self.valor_trader = None

        # AGAPE - ETH Micro Futures with Crypto GEX signals
        # 24/7 crypto trading with 5-minute scan interval
        # PAPER mode: Simulated trades with $5k starting capital
        self.agape_trader = None
        if AGAPE_AVAILABLE:
            try:
                self.agape_trader = create_agape_trader()
                logger.info("✅ AGAPE initialized (ETH Micro Futures, PAPER mode - $5k starting capital)")
            except Exception as e:
                logger.warning(f"AGAPE initialization failed: {e}")
                self.agape_trader = None

        # AGAPE-SPOT - 24/7 Coinbase Spot ETH-USD
        # Trades around the clock, no market hours restrictions
        # PAPER mode: Simulated trades with $5k starting capital
        self.agape_spot_trader = None
        if AGAPE_SPOT_AVAILABLE:
            try:
                self.agape_spot_trader = create_agape_spot_trader()
                logger.info("✅ AGAPE-SPOT initialized (24/7 Coinbase Spot ETH-USD, PAPER mode)")
            except Exception as e:
                logger.warning(f"AGAPE-SPOT initialization failed: {e}")
                self.agape_spot_trader = None

        # AGAPE-BTC - BTC Micro Futures with Crypto GEX signals
        # CME /MBT trading with 5-minute scan interval
        # PAPER mode: Simulated trades with $5k starting capital
        self.agape_btc_trader = None
        if AGAPE_BTC_AVAILABLE:
            try:
                self.agape_btc_trader = create_agape_btc_trader()
                logger.info("✅ AGAPE-BTC initialized (BTC Micro Futures, PAPER mode - $5k starting capital)")
            except Exception as e:
                logger.warning(f"AGAPE-BTC initialization failed: {e}")
                self.agape_btc_trader = None

        # AGAPE-XRP - XRP Futures with Crypto GEX signals
        # CME /XRP trading with 5-minute scan interval
        # PAPER mode: Simulated trades with $5k starting capital
        self.agape_xrp_trader = None
        if AGAPE_XRP_AVAILABLE:
            try:
                self.agape_xrp_trader = create_agape_xrp_trader()
                logger.info("✅ AGAPE-XRP initialized (XRP Futures, PAPER mode - $5k starting capital)")
            except Exception as e:
                logger.warning(f"AGAPE-XRP initialization failed: {e}")
                self.agape_xrp_trader = None

        # AGAPE-ETH-PERP - ETH Perpetual Contract
        # 24/7 perpetual contract trading with real exchange data
        # PAPER mode: Simulated trades with $5k starting capital
        self.agape_eth_perp_trader = None
        if AGAPE_ETH_PERP_AVAILABLE:
            try:
                self.agape_eth_perp_trader = create_agape_eth_perp_trader()
                logger.info("✅ AGAPE-ETH-PERP initialized (ETH Perpetual, PAPER mode - $5k starting capital)")
            except Exception as e:
                logger.warning(f"AGAPE-ETH-PERP initialization failed: {e}")
                self.agape_eth_perp_trader = None

        # AGAPE-BTC-PERP - BTC Perpetual Contract
        # 24/7 perpetual contract trading with real exchange data
        # PAPER mode: Simulated trades with $5k starting capital
        self.agape_btc_perp_trader = None
        if AGAPE_BTC_PERP_AVAILABLE:
            try:
                self.agape_btc_perp_trader = create_agape_btc_perp_trader()
                logger.info("✅ AGAPE-BTC-PERP initialized (BTC Perpetual, PAPER mode - $5k starting capital)")
            except Exception as e:
                logger.warning(f"AGAPE-BTC-PERP initialization failed: {e}")
                self.agape_btc_perp_trader = None

        # AGAPE-XRP-PERP - XRP Perpetual Contract
        # 24/7 perpetual contract trading with real exchange data
        # PAPER mode: Simulated trades with $5k starting capital
        self.agape_xrp_perp_trader = None
        if AGAPE_XRP_PERP_AVAILABLE:
            try:
                self.agape_xrp_perp_trader = create_agape_xrp_perp_trader()
                logger.info("✅ AGAPE-XRP-PERP initialized (XRP Perpetual, PAPER mode - $5k starting capital)")
            except Exception as e:
                logger.warning(f"AGAPE-XRP-PERP initialization failed: {e}")
                self.agape_xrp_perp_trader = None

        # AGAPE-DOGE-PERP - DOGE Perpetual Contract
        # 24/7 perpetual contract trading with real exchange data
        # PAPER mode: Simulated trades with $5k starting capital
        self.agape_doge_perp_trader = None
        if AGAPE_DOGE_PERP_AVAILABLE:
            try:
                self.agape_doge_perp_trader = create_agape_doge_perp_trader()
                logger.info("✅ AGAPE-DOGE-PERP initialized (DOGE Perpetual, PAPER mode - $5k starting capital)")
            except Exception as e:
                logger.warning(f"AGAPE-DOGE-PERP initialization failed: {e}")
                self.agape_doge_perp_trader = None

        # AGAPE-SHIB-PERP - SHIB Perpetual Contract
        # 24/7 perpetual contract trading with real exchange data
        # PAPER mode: Simulated trades with $5k starting capital
        self.agape_shib_perp_trader = None
        if AGAPE_SHIB_PERP_AVAILABLE:
            try:
                self.agape_shib_perp_trader = create_agape_shib_perp_trader()
                logger.info("✅ AGAPE-SHIB-PERP initialized (SHIB Perpetual, PAPER mode - $5k starting capital)")
            except Exception as e:
                logger.warning(f"AGAPE-SHIB-PERP initialization failed: {e}")
                self.agape_shib_perp_trader = None

        # Log capital allocation summary
        logger.info(f"📊 CAPITAL ALLOCATION:")
        logger.info(f"   LAZARUS: ${CAPITAL_ALLOCATION['LAZARUS']:,}")
        logger.info(f"   CORNERSTONE:   ${CAPITAL_ALLOCATION['CORNERSTONE']:,}")
        logger.info(f"   FORTRESS:    ${CAPITAL_ALLOCATION['FORTRESS']:,}")
        logger.info(f"   RESERVE: ${CAPITAL_ALLOCATION['RESERVE']:,}")
        logger.info(f"   TOTAL:   ${CAPITAL_ALLOCATION['TOTAL']:,}")

        self.is_running = False
        self.last_trade_check = None
        self.last_position_check = None
        self.last_cornerstone_check = None
        self.last_fortress_check = None
        self.last_solomon_check = None
        self.last_anchor_check = None
        self.last_gideon_check = None
        self.last_samson_check = None
        self.last_faith_check = None
        self.last_watchtower_check = None
        self.last_valor_check = None
        self.last_error = None
        self.execution_count = 0
        self.cornerstone_execution_count = 0
        self.fortress_execution_count = 0
        self.solomon_execution_count = 0
        self.anchor_execution_count = 0
        self.gideon_execution_count = 0
        self.samson_execution_count = 0
        self.faith_execution_count = 0
        self.grace_execution_count = 0
        self.watchtower_execution_count = 0
        self.valor_execution_count = 0

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

        # Check if LAZARUS trader is available
        if not self.trader:
            logger.warning("LAZARUS trader not available - skipping")
            self._save_heartbeat('LAZARUS', 'UNAVAILABLE')
            return

        # Double-check market is open (belt and suspenders)
        if not self.is_market_open():
            logger.info("Market is CLOSED. Skipping trade logic.")
            self._save_heartbeat('LAZARUS', 'MARKET_CLOSED')
            return

        logger.info("Market is OPEN. Running autonomous trading logic...")

        try:
            # Step 0: Consult Prophet for trade signal (if available)
            prophet_approved = True  # Default to True if Prophet unavailable
            prophet_prediction = None
            if self.lazarus_prophet and PROPHET_AVAILABLE:
                try:
                    # Get GEX data for Prophet context
                    gex_data = self.api_client.get_gex_data() if self.api_client else {}
                    spot_price = gex_data.get('spot_price', 0)
                    vix = gex_data.get('vix', 20)

                    if spot_price > 0:
                        # Build Prophet context
                        gex_regime_str = gex_data.get('gex_regime', 'NEUTRAL').upper()
                        try:
                            gex_regime = GEXRegime[gex_regime_str] if gex_regime_str in GEXRegime.__members__ else GEXRegime.NEUTRAL
                        except (KeyError, AttributeError):
                            gex_regime = GEXRegime.NEUTRAL

                        context = ProphetMarketContext(
                            spot_price=spot_price,
                            vix=vix,
                            gex_put_wall=gex_data.get('put_wall', 0),
                            gex_call_wall=gex_data.get('call_wall', 0),
                            gex_regime=gex_regime,
                            gex_net=gex_data.get('net_gex', 0),
                            gex_flip_point=gex_data.get('flip_point', 0),
                            day_of_week=now.weekday(),
                        )

                        # Get LAZARUS advice from Prophet
                        prophet_prediction = self.lazarus_prophet.get_lazarus_advice(
                            context=context,
                            use_claude_validation=True  # Enable Claude for transparency logging
                        )

                        if prophet_prediction:
                            logger.info(f"LAZARUS Prophet: {prophet_prediction.advice.value} "
                                       f"(win_prob={prophet_prediction.win_probability:.1%})")

                            # =========================================================
                            # Issue #2 fix: Store LAZARUS prediction in Prophet feedback loop
                            # This enables Prophet to learn from LAZARUS outcomes
                            # =========================================================
                            try:
                                trade_date = now.strftime('%Y-%m-%d')
                                self.lazarus_prophet.store_prediction(
                                    prediction=prophet_prediction,
                                    context=context,
                                    trade_date=trade_date
                                )
                                logger.info(f"LAZARUS: Stored Prophet prediction for feedback loop (date={trade_date})")
                            except Exception as store_e:
                                logger.warning(f"LAZARUS: Failed to store prediction: {store_e}")

                            # Prophet must approve with at least TRADE_REDUCED advice
                            if prophet_prediction.advice in [TradingAdvice.SKIP_TODAY, TradingAdvice.STAY_OUT]:
                                prophet_approved = False
                                logger.info(f"LAZARUS Prophet says SKIP: {prophet_prediction.reasoning}")
                                self._log_no_trade_decision('LAZARUS', f'Prophet: {prophet_prediction.reasoning}', {
                                    'symbol': 'SPY',
                                    'oracle_advice': prophet_prediction.advice.value,
                                    'win_probability': prophet_prediction.win_probability,
                                    'market': {'spot': spot_price, 'vix': vix, 'time': now.isoformat()}
                                })
                    else:
                        logger.warning("LAZARUS: No spot price for Prophet - proceeding without Prophet validation")
                except Exception as prophet_e:
                    logger.warning(f"LAZARUS Prophet check failed: {prophet_e} - proceeding without Prophet")

            # Skip trading if Prophet says no
            if not prophet_approved:
                self._save_heartbeat('LAZARUS', 'PROPHET_SKIP', {
                    'oracle_advice': prophet_prediction.advice.value if prophet_prediction else 'UNKNOWN',
                    'win_probability': prophet_prediction.win_probability if prophet_prediction else 0
                })
                logger.info("LAZARUS skipping trade due to Prophet advice")
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
                self._log_no_trade_decision('LAZARUS', 'Already traded today or no good setups', {
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
                    # Issue #2 fix: Record LAZARUS outcomes in Prophet feedback loop
                    # When positions are closed, record the outcome for ML training
                    # =========================================================
                    if self.lazarus_prophet and PROPHET_AVAILABLE and ProphetBotName and TradeOutcome:
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
                                self.lazarus_prophet.update_outcome(
                                    trade_date=trade_date,
                                    bot_name=ProphetBotName.LAZARUS,
                                    outcome=outcome,
                                    actual_pnl=float(pnl),
                                    spot_at_exit=gex_data.get('spot_price', 0) if 'gex_data' in dir() else 0
                                )
                                logger.info(f"LAZARUS: Recorded outcome {outcome.value} (PnL=${pnl:.2f}) for Prophet feedback")
                            except Exception as outcome_e:
                                logger.warning(f"LAZARUS: Failed to record outcome: {outcome_e}")
            else:
                logger.info("No positions to manage or no actions taken")

            # Update execution count
            self.execution_count += 1
            self.last_error = None

            # Save heartbeat and state after each execution
            self._save_heartbeat('LAZARUS', 'TRADED' if traded else 'SCAN_COMPLETE', {
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

            self._save_heartbeat('LAZARUS', 'ERROR', {'error': str(e)})

            # Don't crash the scheduler - just log and continue
            logger.info("Scheduler will continue despite error")
            logger.info(f"=" * 80)

    def scheduled_cornerstone_logic(self):
        """
        CORNERSTONE (SPX Wheel) trading logic - runs daily at 9:05 AM CT

        The wheel strategy operates on a weekly basis:
        - Sells cash-secured puts on SPX
        - Manages positions through expiration
        - Rolls when needed
        - Tracks performance vs backtest
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"CORNERSTONE (SPX Wheel) triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.cornerstone_trader:
            logger.warning("CORNERSTONE trader not available - skipping")
            self._save_heartbeat('CORNERSTONE', 'UNAVAILABLE')
            return

        if not self.is_market_open():
            logger.info("Market is CLOSED. Skipping CORNERSTONE logic.")
            self._save_heartbeat('CORNERSTONE', 'MARKET_CLOSED')
            return

        logger.info("Market is OPEN. Running CORNERSTONE wheel strategy...")

        try:
            self.last_cornerstone_check = now
            traded = False
            scan_context = {'symbol': 'SPX'}

            # Run the daily wheel cycle
            # This handles: new positions, expiration processing, roll checks
            result = self.cornerstone_trader.run_daily_cycle()

            if result:
                logger.info(f"CORNERSTONE daily cycle completed:")
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
                    self._log_no_trade_decision('CORNERSTONE', no_trade_reason, scan_context)
            else:
                logger.info("CORNERSTONE: No actions taken today")
                self._log_no_trade_decision('CORNERSTONE', 'No result from trading cycle', scan_context)

            self.cornerstone_execution_count += 1
            self._save_heartbeat('CORNERSTONE', 'TRADED' if traded else 'SCAN_COMPLETE', {
                'scan_number': self.cornerstone_execution_count,
                'traded': traded,
                'open_positions': result.get('open_positions', 0) if result else 0,
                'spx_price': result.get('spx_price', 0) if result else 0
            })
            logger.info(f"CORNERSTONE cycle #{self.cornerstone_execution_count} completed successfully")
            logger.info(f"=" * 80)

        except Exception as e:
            error_msg = f"ERROR in CORNERSTONE trading logic: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            self._save_heartbeat('CORNERSTONE', 'ERROR', {'error': str(e)})
            logger.info("CORNERSTONE will continue despite error")
            logger.info(f"=" * 80)

    def scheduled_fortress_logic(self):
        """
        FORTRESS V2 (SPY Iron Condor) trading logic - runs every 5 minutes during market hours

        Uses the new modular V2 architecture:
        - Database is single source of truth
        - Clean run_cycle() API
        - Trades SPY Iron Condors with $2 spreads
        """
        now = datetime.now(CENTRAL_TZ)

        # Update last check time IMMEDIATELY for health monitoring
        # (even if we return early due to market closed, the job IS running)
        self.last_fortress_check = now

        logger.info(f"=" * 80)
        logger.info(f"FORTRESS V2 (SPY IC) triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.fortress_trader:
            logger.warning("FORTRESS V2 trader not available - skipping")
            self._save_heartbeat('FORTRESS', 'UNAVAILABLE')
            # Log to scan_activity for visibility
            if SCAN_ACTIVITY_LOGGER_AVAILABLE and log_fortress_scan:
                log_fortress_scan(
                    outcome=ScanOutcome.UNAVAILABLE,
                    decision_summary="FORTRESS trader not initialized",
                    generate_ai_explanation=False
                )
            return

        is_open, market_status = self.get_market_status()

        # CRITICAL FIX: Allow position management even after market close
        # FORTRESS needs to close expiring positions up to 15 minutes after market close
        allow_close_only = False
        if not is_open and market_status == 'AFTER_WINDOW':
            # Check if we're within 15 minutes of market close (15:00-15:15 CT)
            market_close = now.replace(hour=15, minute=0, second=0, microsecond=0)
            minutes_after_close = (now - market_close).total_seconds() / 60
            if 0 <= minutes_after_close <= 15:
                # Allow position management but not new entries
                allow_close_only = True
                logger.info(f"FORTRESS: {minutes_after_close:.0f}min after market close - running close-only cycle")

        if not is_open and not allow_close_only:
            # Map market status to appropriate message
            message_mapping = {
                'BEFORE_WINDOW': "Before trading window (8:30 AM CT)",
                'AFTER_WINDOW': "After trading window (3:00 PM CT)",
                'WEEKEND': "Weekend - market closed",
                'HOLIDAY': "Holiday - market closed",
            }
            message = message_mapping.get(market_status, "Market is closed")

            logger.info(f"Market not open ({market_status}). Skipping FORTRESS logic.")
            self._save_heartbeat('FORTRESS', market_status)
            # Log to scan_activity for visibility
            if SCAN_ACTIVITY_LOGGER_AVAILABLE and log_fortress_scan and ScanOutcome:
                # Map market status to scan outcome
                outcome_mapping = {
                    'BEFORE_WINDOW': ScanOutcome.BEFORE_WINDOW,
                    'AFTER_WINDOW': ScanOutcome.AFTER_WINDOW,
                    'WEEKEND': ScanOutcome.MARKET_CLOSED,
                    'HOLIDAY': ScanOutcome.MARKET_CLOSED,
                }
                outcome = outcome_mapping.get(market_status, ScanOutcome.MARKET_CLOSED)
                scan_id = log_fortress_scan(
                    outcome=outcome,
                    decision_summary=message,
                    generate_ai_explanation=False
                )
                if scan_id:
                    logger.info(f"📝 FORTRESS scan logged to database: {scan_id}")
                else:
                    logger.warning("⚠️ FORTRESS scan_activity logging FAILED - check database connection")
            else:
                logger.warning(f"⚠️ FORTRESS scan NOT logged: SCAN_ACTIVITY_LOGGER_AVAILABLE={SCAN_ACTIVITY_LOGGER_AVAILABLE}")
            return

        try:
            # Run the V2 cycle (close_only mode prevents new entries after market close)
            result = self.fortress_trader.run_cycle(close_only=allow_close_only)

            traded = result.get('trade_opened', False)
            closed = result.get('positions_closed', 0)
            action = result.get('action', 'none')

            logger.info(f"FORTRESS V2 cycle completed: {action}")
            if traded:
                logger.info(f"  NEW TRADE OPENED")
            if closed > 0:
                logger.info(f"  Positions closed: {closed}, P&L: ${result.get('realized_pnl', 0):.2f}")
            if result.get('errors'):
                for err in result['errors']:
                    logger.warning(f"  Skip reason: {err}")

            self.fortress_execution_count += 1
            self._save_heartbeat('FORTRESS', 'TRADED' if traded else 'SCAN_COMPLETE', {
                'scan_number': self.fortress_execution_count,
                'traded': traded,
                'action': action
            })

            # NOTE: Removed duplicate "BACKUP" logging here.
            # The FORTRESS V2 trader.py already logs comprehensive scan activity
            # with full Prophet/ML data via _log_scan_activity().
            # The old backup created duplicate entries with incomplete data
            # (Prophet:0%, ML:0%, Thresh:0%) which caused diagnostic confusion.

            logger.info(f"FORTRESS V2 scan #{self.fortress_execution_count} completed")
            logger.info(f"=" * 80)

        except Exception as e:
            logger.error(f"ERROR in FORTRESS V2: {str(e)}")
            logger.error(traceback.format_exc())
            self._save_heartbeat('FORTRESS', 'ERROR', {'error': str(e)})
            # BACKUP: Log to scan_activity in case bot's internal logging failed
            # This ensures we always have visibility into what happened
            if SCAN_ACTIVITY_LOGGER_AVAILABLE and log_fortress_scan:
                try:
                    log_fortress_scan(
                        outcome=ScanOutcome.ERROR,
                        decision_summary=f"Scheduler-level error: {str(e)[:200]}",
                        error_message=str(e),
                        generate_ai_explanation=False
                    )
                except Exception as log_err:
                    logger.error(f"CRITICAL: Backup scan_activity logging also failed: {log_err}")
            logger.info(f"=" * 80)

    def scheduled_fortress_eod_logic(self):
        """
        FORTRESS End-of-Day processing - runs daily at 3:05 PM CT

        Processes expired 0DTE Iron Condor positions:
        - Calculates realized P&L based on closing price
        - Updates position status to 'expired'
        - Feeds Prophet for ML training feedback loop
        - Updates daily performance metrics
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"FORTRESS EOD (End-of-Day) triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.fortress_trader:
            logger.warning("FORTRESS trader not available - skipping EOD processing")
            return

        # EOD processing happens after market close, so we don't check is_market_open()
        logger.info("Processing expired FORTRESS positions...")

        try:
            # Run the EOD expiration processing
            result = self.fortress_trader.process_expired_positions()

            if result:
                logger.info(f"FORTRESS EOD processing completed:")
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
                logger.info("FORTRESS EOD: No positions to process")

            logger.info(f"FORTRESS EOD processing completed successfully")
            logger.info(f"=" * 80)

        except Exception as e:
            error_msg = f"ERROR in FORTRESS EOD processing: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            logger.info("FORTRESS EOD will retry next trading day")
            logger.info(f"=" * 80)

    def scheduled_fortress_friday_close_all(self):
        """
        FORTRESS Friday Close-All - runs at 2:55 PM CT on Fridays ONLY

        Safety net to ensure NO positions are held over the weekend.
        The regular 5-min cycle handles force-close via FRIDAY_WEEKEND_CLOSE
        at 2:50 PM, but this is a dedicated backup that runs close_only mode
        to catch any stragglers (pricing failures, partial closes, etc).
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"FORTRESS FRIDAY CLOSE-ALL triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.fortress_trader:
            logger.warning("FORTRESS trader not available - skipping Friday close-all")
            return

        if now.weekday() != 4:
            logger.info("Not Friday - skipping Friday close-all (should not happen)")
            return

        try:
            # Run close-only cycle to force-close any remaining positions
            result = self.fortress_trader.run_cycle(close_only=True)

            closed = result.get('positions_closed', 0)
            pnl = result.get('realized_pnl', 0)

            if closed > 0:
                logger.info(f"FORTRESS Friday close-all: Closed {closed} position(s), P&L: ${pnl:.2f}")
            else:
                logger.info("FORTRESS Friday close-all: No positions remaining (already flat)")

            self._save_heartbeat('FORTRESS', 'FRIDAY_CLOSE_ALL', {
                'closed': closed,
                'realized_pnl': pnl
            })
            logger.info(f"=" * 80)

        except Exception as e:
            logger.error(f"ERROR in FORTRESS Friday close-all: {str(e)}")
            logger.error(traceback.format_exc())
            logger.info(f"=" * 80)

    def scheduled_solomon_eod_logic(self):
        """
        SOLOMON End-of-Day processing - runs daily at 3:10 PM CT

        Processes expired 0DTE directional spread positions:
        - Calculates realized P&L based on closing price
        - Updates position status to 'expired'
        - Updates daily performance metrics
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"SOLOMON EOD (End-of-Day) triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.solomon_trader:
            logger.warning("SOLOMON trader not available - skipping EOD processing")
            return

        # EOD processing happens after market close, so we don't check is_market_open()
        logger.info("Processing expired SOLOMON positions...")

        try:
            # Run the EOD expiration processing
            result = self.solomon_trader.process_expired_positions()

            if result:
                logger.info(f"SOLOMON EOD processing completed:")
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
                logger.info("SOLOMON EOD: No positions to process")

            logger.info(f"SOLOMON EOD processing completed successfully")
            logger.info(f"=" * 80)

        except Exception as e:
            error_msg = f"ERROR in SOLOMON EOD processing: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            logger.info("SOLOMON EOD will retry next trading day")
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
                    'prophet': context.get('prophet', {}) if context else {},
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

    def scheduled_solomon_logic(self):
        """
        SOLOMON V2 (SPY Directional Spreads) trading logic - runs every 5 minutes during market hours

        Uses the new modular V2 architecture:
        - Database is single source of truth
        - Clean run_cycle() API
        - Trades SPY Directional Spreads with $2 spreads
        - GEX wall proximity filter for high probability setups
        """
        now = datetime.now(CENTRAL_TZ)

        # Update last check time IMMEDIATELY for health monitoring
        # (even if we return early due to market closed, the job IS running)
        self.last_solomon_check = now

        logger.info(f"=" * 80)
        logger.info(f"SOLOMON V2 (SPY Spreads) triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.solomon_trader:
            logger.warning("SOLOMON V2 trader not available - skipping")
            self._save_heartbeat('SOLOMON', 'UNAVAILABLE')
            # Log to scan_activity for visibility
            if SCAN_ACTIVITY_LOGGER_AVAILABLE and log_solomon_scan:
                log_solomon_scan(
                    outcome=ScanOutcome.UNAVAILABLE,
                    decision_summary="SOLOMON trader not initialized",
                    generate_ai_explanation=False
                )
            return

        is_open, market_status = self.get_market_status()

        # CRITICAL FIX: Allow position management even after market close
        # SOLOMON needs to close expiring positions up to 15 minutes after market close
        allow_close_only = False
        if not is_open and market_status == 'AFTER_WINDOW':
            # Check if we're within 15 minutes of market close (15:00-15:15 CT)
            market_close = now.replace(hour=15, minute=0, second=0, microsecond=0)
            minutes_after_close = (now - market_close).total_seconds() / 60
            if 0 <= minutes_after_close <= 15:
                # Allow position management but not new entries
                allow_close_only = True
                logger.info(f"SOLOMON: {minutes_after_close:.0f}min after market close - running close-only cycle")

        if not is_open and not allow_close_only:
            # Map market status to appropriate message
            message_mapping = {
                'BEFORE_WINDOW': "Before trading window (8:30 AM CT)",
                'AFTER_WINDOW': "After trading window (3:00 PM CT)",
                'WEEKEND': "Weekend - market closed",
                'HOLIDAY': "Holiday - market closed",
            }
            message = message_mapping.get(market_status, "Market is closed")

            logger.info(f"Market not open ({market_status}). Skipping SOLOMON logic.")
            self._save_heartbeat('SOLOMON', market_status)
            # Log to scan_activity for visibility
            if SCAN_ACTIVITY_LOGGER_AVAILABLE and log_solomon_scan and ScanOutcome:
                # Map market status to scan outcome
                outcome_mapping = {
                    'BEFORE_WINDOW': ScanOutcome.BEFORE_WINDOW,
                    'AFTER_WINDOW': ScanOutcome.AFTER_WINDOW,
                    'WEEKEND': ScanOutcome.MARKET_CLOSED,
                    'HOLIDAY': ScanOutcome.MARKET_CLOSED,
                }
                outcome = outcome_mapping.get(market_status, ScanOutcome.MARKET_CLOSED)
                log_solomon_scan(
                    outcome=outcome,
                    decision_summary=message,
                    generate_ai_explanation=False
                )
            return

        try:
            # Run the V2 cycle (close_only mode prevents new entries after market close)
            result = self.solomon_trader.run_cycle(close_only=allow_close_only)

            # SOLOMON V2 returns 'trades_opened' (int), not 'trade_opened' (bool)
            traded = result.get('trades_opened', result.get('trade_opened', 0)) > 0
            closed = result.get('trades_closed', result.get('positions_closed', 0))
            action = result.get('action', 'none')

            logger.info(f"SOLOMON V2 cycle completed: {action}")
            if traded:
                logger.info(f"  NEW TRADE OPENED")
            if closed > 0:
                logger.info(f"  Positions closed: {closed}, P&L: ${result.get('realized_pnl', 0):.2f}")
            if result.get('errors'):
                for err in result['errors']:
                    logger.warning(f"  Skip reason: {err}")

            self.solomon_execution_count += 1
            self._save_heartbeat('SOLOMON', 'TRADED' if traded else 'SCAN_COMPLETE', {
                'scan_number': self.solomon_execution_count,
                'traded': traded,
                'action': action
            })

            # NOTE: Removed duplicate "BACKUP" logging here.
            # SOLOMON V2 trader already logs comprehensive scan activity
            # with full Prophet/ML data via _log_scan_activity().

            logger.info(f"SOLOMON V2 scan #{self.solomon_execution_count} completed")
            logger.info(f"=" * 80)

        except Exception as e:
            logger.error(f"ERROR in SOLOMON V2: {str(e)}")
            logger.error(traceback.format_exc())
            self._save_heartbeat('SOLOMON', 'ERROR', {'error': str(e)})
            # BACKUP: Log to scan_activity in case bot's internal logging failed
            if SCAN_ACTIVITY_LOGGER_AVAILABLE and log_solomon_scan:
                try:
                    log_solomon_scan(
                        outcome=ScanOutcome.ERROR,
                        decision_summary=f"Scheduler-level error: {str(e)[:200]}",
                        error_message=str(e),
                        generate_ai_explanation=False
                    )
                except Exception as log_err:
                    logger.error(f"CRITICAL: Backup scan_activity logging also failed: {log_err}")
            logger.info(f"=" * 80)

    def scheduled_anchor_logic(self):
        """
        ANCHOR (SPX Iron Condor) trading logic - runs every 5 minutes during market hours

        Uses the new modular architecture:
        - Database is single source of truth
        - Clean run_cycle() API
        - Trades SPX Iron Condors with $10 spreads
        - Uses SPXW weekly options
        """
        now = datetime.now(CENTRAL_TZ)

        # Update last check time IMMEDIATELY for health monitoring
        self.last_anchor_check = now

        logger.info(f"=" * 80)
        logger.info(f"ANCHOR (SPX IC) triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.anchor_trader:
            logger.warning("ANCHOR trader not available - skipping")
            self._save_heartbeat('ANCHOR', 'UNAVAILABLE')
            # Log to scan_activity for visibility
            if SCAN_ACTIVITY_LOGGER_AVAILABLE and log_anchor_scan:
                log_anchor_scan(
                    outcome=ScanOutcome.UNAVAILABLE,
                    decision_summary="ANCHOR trader not initialized",
                    generate_ai_explanation=False
                )
            return

        is_open, market_status = self.get_market_status()

        # CRITICAL FIX: Allow position management even after market close
        # ANCHOR needs to close expiring positions up to 15 minutes after market close
        # to handle any positions that weren't closed during the 14:50-15:00 window
        allow_close_only = False
        if not is_open and market_status == 'AFTER_WINDOW':
            # Check if we're within 15 minutes of market close (15:00-15:15 CT)
            market_close = now.replace(hour=15, minute=0, second=0, microsecond=0)
            minutes_after_close = (now - market_close).total_seconds() / 60
            if 0 <= minutes_after_close <= 15:
                # Allow position management but not new entries
                allow_close_only = True
                logger.info(f"ANCHOR: {minutes_after_close:.0f}min after market close - running close-only cycle")

        if not is_open and not allow_close_only:
            # Map market status to appropriate message
            message_mapping = {
                'BEFORE_WINDOW': "Before trading window (8:30 AM CT)",
                'AFTER_WINDOW': "After trading window (3:00 PM CT)",
                'WEEKEND': "Weekend - market closed",
                'HOLIDAY': "Holiday - market closed",
            }
            message = message_mapping.get(market_status, "Market is closed")

            logger.info(f"Market not open ({market_status}). Skipping ANCHOR logic.")
            self._save_heartbeat('ANCHOR', market_status)
            # Log to scan_activity for visibility
            if SCAN_ACTIVITY_LOGGER_AVAILABLE and log_anchor_scan and ScanOutcome:
                # Map market status to scan outcome
                outcome_mapping = {
                    'BEFORE_WINDOW': ScanOutcome.BEFORE_WINDOW,
                    'AFTER_WINDOW': ScanOutcome.AFTER_WINDOW,
                    'WEEKEND': ScanOutcome.MARKET_CLOSED,
                    'HOLIDAY': ScanOutcome.MARKET_CLOSED,
                }
                outcome = outcome_mapping.get(market_status, ScanOutcome.MARKET_CLOSED)
                log_anchor_scan(
                    outcome=outcome,
                    decision_summary=message,
                    generate_ai_explanation=False
                )
            return

        try:
            # Run the cycle (close_only mode prevents new entries after market close)
            result = self.anchor_trader.run_cycle(close_only=allow_close_only)

            traded = result.get('trade_opened', False)
            closed = result.get('positions_closed', 0)
            action = result.get('action', 'none')

            logger.info(f"ANCHOR cycle completed: {action}")
            if traded:
                logger.info(f"  NEW TRADE OPENED")
            if closed > 0:
                logger.info(f"  Positions closed: {closed}, P&L: ${result.get('realized_pnl', 0):.2f}")
            if result.get('errors'):
                for err in result['errors']:
                    logger.warning(f"  Skip reason: {err}")

            self.anchor_execution_count += 1
            self._save_heartbeat('ANCHOR', 'TRADED' if traded else 'SCAN_COMPLETE', {
                'scan_number': self.anchor_execution_count,
                'traded': traded,
                'action': action
            })

            # NOTE: Removed duplicate "BACKUP" logging here.
            # ANCHOR trader already logs comprehensive scan activity
            # with full Prophet/ML data via its internal logger.

            logger.info(f"ANCHOR scan #{self.anchor_execution_count} completed")
            logger.info(f"=" * 80)

        except Exception as e:
            logger.error(f"ERROR in ANCHOR: {str(e)}")
            logger.error(traceback.format_exc())
            self._save_heartbeat('ANCHOR', 'ERROR', {'error': str(e)})
            # BACKUP: Log to scan_activity in case bot's internal logging failed
            if SCAN_ACTIVITY_LOGGER_AVAILABLE and log_anchor_scan:
                try:
                    log_anchor_scan(
                        outcome=ScanOutcome.ERROR,
                        decision_summary=f"Scheduler-level error: {str(e)[:200]}",
                        error_message=str(e),
                        generate_ai_explanation=False
                    )
                except Exception as log_err:
                    logger.error(f"CRITICAL: Backup scan_activity logging also failed: {log_err}")
            logger.info(f"=" * 80)

    def scheduled_anchor_eod_logic(self):
        """
        ANCHOR End-of-Day processing - runs daily at 3:15 PM CT

        Processes expired SPX Iron Condor positions:
        - Calculates realized P&L based on closing price
        - Updates position status to 'expired'
        - Updates daily performance metrics
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"ANCHOR EOD triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.anchor_trader:
            logger.warning("ANCHOR trader not available - skipping EOD processing")
            return

        logger.info("Processing expired ANCHOR positions...")

        try:
            # Force close any remaining open positions
            result = self.anchor_trader.force_close_all("EOD_EXPIRATION")

            if result:
                logger.info(f"ANCHOR EOD processing completed:")
                logger.info(f"  Closed: {result.get('closed', 0)} positions")
                logger.info(f"  Total P&L: ${result.get('total_pnl', 0):,.2f}")
            else:
                logger.info("ANCHOR EOD: No positions to process")

            logger.info(f"ANCHOR EOD processing completed successfully")
            logger.info(f"=" * 80)

        except Exception as e:
            logger.error(f"ERROR in ANCHOR EOD: {str(e)}")
            logger.error(traceback.format_exc())
            logger.info(f"=" * 80)

    def scheduled_gideon_logic(self):
        """
        GIDEON (Aggressive Directional Spreads) trading logic - runs every 5 minutes during market hours

        GIDEON is an aggressive clone of SOLOMON with relaxed GEX filters:
        - 10% wall filter (vs SOLOMON's 3%)
        - 40% min win probability (vs SOLOMON's 48%)
        - 4% risk per trade (vs SOLOMON's 2%)
        - 10 max daily trades (vs SOLOMON's 5)
        """
        now = datetime.now(CENTRAL_TZ)

        # Update last check time IMMEDIATELY for health monitoring
        self.last_gideon_check = now

        logger.info(f"=" * 80)
        logger.info(f"GIDEON (Aggressive Spreads) triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.gideon_trader:
            logger.warning("GIDEON trader not available - skipping")
            self._save_heartbeat('GIDEON', 'UNAVAILABLE')
            # Log to scan_activity for visibility
            if SCAN_ACTIVITY_LOGGER_AVAILABLE and log_gideon_scan:
                log_gideon_scan(
                    outcome=ScanOutcome.UNAVAILABLE,
                    decision_summary="GIDEON trader not initialized",
                    generate_ai_explanation=False
                )
            return

        is_open, market_status = self.get_market_status()

        # CRITICAL FIX: Allow position management even after market close
        # GIDEON needs to close expiring positions up to 15 minutes after market close
        allow_close_only = False
        if not is_open and market_status == 'AFTER_WINDOW':
            # Check if we're within 15 minutes of market close (15:00-15:15 CT)
            market_close = now.replace(hour=15, minute=0, second=0, microsecond=0)
            minutes_after_close = (now - market_close).total_seconds() / 60
            if 0 <= minutes_after_close <= 15:
                # Allow position management but not new entries
                allow_close_only = True
                logger.info(f"GIDEON: {minutes_after_close:.0f}min after market close - running close-only cycle")

        if not is_open and not allow_close_only:
            # Map market status to appropriate message
            message_mapping = {
                'BEFORE_WINDOW': "Before trading window (8:30 AM CT)",
                'AFTER_WINDOW': "After trading window (3:00 PM CT)",
                'WEEKEND': "Weekend - market closed",
                'HOLIDAY': "Holiday - market closed",
            }
            message = message_mapping.get(market_status, "Market is closed")

            logger.info(f"Market not open ({market_status}). Skipping GIDEON logic.")
            self._save_heartbeat('GIDEON', market_status)
            # Log to scan_activity for visibility
            if SCAN_ACTIVITY_LOGGER_AVAILABLE and log_gideon_scan and ScanOutcome:
                # Map market status to scan outcome
                outcome_mapping = {
                    'BEFORE_WINDOW': ScanOutcome.MARKET_CLOSED,
                    'AFTER_WINDOW': ScanOutcome.MARKET_CLOSED,
                    'WEEKEND': ScanOutcome.MARKET_CLOSED,
                    'HOLIDAY': ScanOutcome.MARKET_CLOSED,
                }
                outcome = outcome_mapping.get(market_status, ScanOutcome.MARKET_CLOSED)
                log_gideon_scan(
                    outcome=outcome,
                    decision_summary=message,
                    generate_ai_explanation=False
                )
            return

        try:
            # Run the cycle (close_only mode prevents new entries after market close)
            result = self.gideon_trader.run_cycle(close_only=allow_close_only)

            # GIDEON returns 'trades_opened' (int), not 'trade_opened' (bool)
            traded = result.get('trades_opened', result.get('trade_opened', 0)) > 0
            closed = result.get('trades_closed', result.get('positions_closed', 0))
            action = result.get('action', 'none')

            logger.info(f"GIDEON cycle completed: {action}")
            if traded:
                logger.info(f"  NEW TRADE OPENED")
            if closed > 0:
                logger.info(f"  Positions closed: {closed}, P&L: ${result.get('realized_pnl', 0):.2f}")
            if result.get('errors'):
                for err in result['errors']:
                    logger.warning(f"  Skip reason: {err}")

            self.gideon_execution_count += 1
            self._save_heartbeat('GIDEON', 'TRADED' if traded else 'SCAN_COMPLETE', {
                'scan_number': self.gideon_execution_count,
                'traded': traded,
                'action': action
            })

            # NOTE: Removed duplicate "BACKUP" logging here.
            # GIDEON trader already logs comprehensive scan activity
            # with full Prophet/ML data via its internal logger.

            logger.info(f"GIDEON scan #{self.gideon_execution_count} completed")
            logger.info(f"=" * 80)

        except Exception as e:
            logger.error(f"ERROR in GIDEON: {str(e)}")
            logger.error(traceback.format_exc())
            self._save_heartbeat('GIDEON', 'ERROR', {'error': str(e)})
            # BACKUP: Log to scan_activity in case bot's internal logging failed
            if SCAN_ACTIVITY_LOGGER_AVAILABLE and log_gideon_scan:
                try:
                    log_gideon_scan(
                        outcome=ScanOutcome.ERROR,
                        decision_summary=f"Scheduler-level error: {str(e)[:200]}",
                        error_message=str(e),
                        generate_ai_explanation=False
                    )
                except Exception as log_err:
                    logger.error(f"CRITICAL: Backup scan_activity logging also failed: {log_err}")
            logger.info(f"=" * 80)

    def scheduled_gideon_eod_logic(self):
        """
        GIDEON End-of-Day processing - runs daily at 3:12 PM CT

        Processes expired 0DTE directional spread positions:
        - Calculates realized P&L based on closing price
        - Updates position status to 'expired'
        - Updates daily performance metrics
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"GIDEON EOD triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.gideon_trader:
            logger.warning("GIDEON trader not available - skipping EOD processing")
            return

        logger.info("Processing expired GIDEON positions...")

        try:
            # Run the EOD expiration processing
            result = self.gideon_trader.process_expired_positions()

            if result:
                logger.info(f"GIDEON EOD processing completed:")
                logger.info(f"  Processed: {result.get('processed_count', 0)} positions")
                logger.info(f"  Total P&L: ${result.get('total_pnl', 0):,.2f}")

                # Log any warnings/errors
                if result.get('errors'):
                    logger.warning("GIDEON EOD had errors:")
                    for error in result['errors']:
                        logger.warning(f"    Error: {error}")
            else:
                logger.info("GIDEON EOD: No positions to process")

            logger.info(f"GIDEON EOD processing completed successfully")
            logger.info(f"=" * 80)

        except Exception as e:
            error_msg = f"ERROR in GIDEON EOD processing: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            logger.info("GIDEON EOD will retry next trading day")
            logger.info(f"=" * 80)

    def scheduled_samson_logic(self):
        """
        SAMSON (Aggressive SPX Iron Condor) trading logic - runs every 5 minutes during market hours

        SAMSON is an aggressive clone of ANCHOR with relaxed filters:
        - 40% VIX skip (vs ANCHOR's 32%)
        - 40% min win probability (vs ANCHOR's 50%)
        - 15% risk per trade (vs ANCHOR's 10%)
        - 10 max positions (vs ANCHOR's 5)
        - 0.8 SD multiplier for closer strikes (vs ANCHOR's 1.0)
        - $12 spread widths (vs ANCHOR's $10)
        - 30-minute cooldown for multiple trades per day
        """
        now = datetime.now(CENTRAL_TZ)

        # Update last check time IMMEDIATELY for health monitoring
        self.last_samson_check = now

        logger.info(f"=" * 80)
        logger.info(f"SAMSON (Aggressive SPX IC) triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.samson_trader:
            logger.warning("SAMSON trader not available - skipping")
            self._save_heartbeat('SAMSON', 'UNAVAILABLE')
            # Log to scan_activity for visibility
            if SCAN_ACTIVITY_LOGGER_AVAILABLE and log_samson_scan:
                log_samson_scan(
                    outcome=ScanOutcome.UNAVAILABLE,
                    decision_summary="SAMSON trader not initialized",
                    generate_ai_explanation=False
                )
            return

        is_open, market_status = self.get_market_status()

        # CRITICAL FIX: Allow position management even after market close
        # SAMSON needs to close expiring positions up to 15 minutes after market close
        allow_close_only = False
        if not is_open and market_status == 'AFTER_WINDOW':
            # Check if we're within 15 minutes of market close (15:00-15:15 CT)
            market_close = now.replace(hour=15, minute=0, second=0, microsecond=0)
            minutes_after_close = (now - market_close).total_seconds() / 60
            if 0 <= minutes_after_close <= 15:
                # Allow position management but not new entries
                allow_close_only = True
                logger.info(f"SAMSON: {minutes_after_close:.0f}min after market close - running close-only cycle")

        if not is_open and not allow_close_only:
            # Map market status to appropriate message
            message_mapping = {
                'BEFORE_WINDOW': "Before trading window (8:30 AM CT)",
                'AFTER_WINDOW': "After trading window (3:00 PM CT)",
                'WEEKEND': "Weekend - market closed",
                'HOLIDAY': "Holiday - market closed",
            }
            message = message_mapping.get(market_status, "Market is closed")

            logger.info(f"Market not open ({market_status}). Skipping SAMSON logic.")
            self._save_heartbeat('SAMSON', market_status)
            # Log to scan_activity for visibility
            if SCAN_ACTIVITY_LOGGER_AVAILABLE and log_samson_scan and ScanOutcome:
                # Map market status to scan outcome
                outcome_mapping = {
                    'BEFORE_WINDOW': ScanOutcome.MARKET_CLOSED,
                    'AFTER_WINDOW': ScanOutcome.MARKET_CLOSED,
                    'WEEKEND': ScanOutcome.MARKET_CLOSED,
                    'HOLIDAY': ScanOutcome.MARKET_CLOSED,
                }
                outcome = outcome_mapping.get(market_status, ScanOutcome.MARKET_CLOSED)
                log_samson_scan(
                    outcome=outcome,
                    decision_summary=message,
                    generate_ai_explanation=False
                )
            return

        try:
            # Run the cycle (close_only mode prevents new entries after market close)
            result = self.samson_trader.run_cycle(close_only=allow_close_only)

            traded = result.get('trade_opened', False)
            closed = result.get('positions_closed', 0)
            action = result.get('action', 'none')

            logger.info(f"SAMSON cycle completed: {action}")
            if traded:
                logger.info(f"  NEW TRADE OPENED")
            if closed > 0:
                logger.info(f"  Positions closed: {closed}, P&L: ${result.get('realized_pnl', 0):.2f}")
            if result.get('errors'):
                for err in result['errors']:
                    logger.warning(f"  Skip reason: {err}")

            self.samson_execution_count += 1
            self._save_heartbeat('SAMSON', 'TRADED' if traded else 'SCAN_COMPLETE', {
                'scan_number': self.samson_execution_count,
                'traded': traded,
                'action': action
            })

            # NOTE: Removed duplicate "BACKUP" logging here.
            # SAMSON trader already logs comprehensive scan activity
            # with full Prophet/ML data via its internal logger.

            logger.info(f"SAMSON scan #{self.samson_execution_count} completed")
            logger.info(f"=" * 80)

        except Exception as e:
            logger.error(f"ERROR in SAMSON: {str(e)}")
            logger.error(traceback.format_exc())
            self._save_heartbeat('SAMSON', 'ERROR', {'error': str(e)})
            # BACKUP: Log to scan_activity in case bot's internal logging failed
            if SCAN_ACTIVITY_LOGGER_AVAILABLE and log_samson_scan:
                try:
                    log_samson_scan(
                        outcome=ScanOutcome.ERROR,
                        decision_summary=f"Scheduler-level error: {str(e)[:200]}",
                        error_message=str(e),
                        generate_ai_explanation=False
                    )
                except Exception as log_err:
                    logger.error(f"CRITICAL: Backup scan_activity logging also failed: {log_err}")
            logger.info(f"=" * 80)

    def scheduled_samson_eod_logic(self):
        """
        SAMSON End-of-Day processing - runs daily at 3:17 PM CT

        Processes expired SPX Iron Condor positions:
        - Calculates realized P&L based on closing price
        - Updates position status to 'expired'
        - Updates daily performance metrics
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"SAMSON EOD triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.samson_trader:
            logger.warning("SAMSON trader not available - skipping EOD processing")
            return

        logger.info("Processing expired SAMSON positions...")

        try:
            # Force close any remaining open positions
            result = self.samson_trader.force_close_all("EOD_EXPIRATION")

            if result:
                logger.info(f"SAMSON EOD processing completed:")
                logger.info(f"  Closed: {result.get('closed', 0)} positions")
                logger.info(f"  Total P&L: ${result.get('total_pnl', 0):,.2f}")
            else:
                logger.info("SAMSON EOD: No positions to process")

            logger.info(f"SAMSON EOD processing completed successfully")
            logger.info(f"=" * 80)

        except Exception as e:
            logger.error(f"ERROR in SAMSON EOD: {str(e)}")
            logger.error(traceback.format_exc())
            logger.info(f"=" * 80)

    # ========================================================================
    # FAITH - 2DTE Paper Iron Condor (SPY)
    # ========================================================================

    def scheduled_faith_logic(self):
        """
        FAITH (2DTE Paper Iron Condor) trading logic - runs every 5 minutes during market hours

        Paper-only bot: real Tradier data, simulated fills, $5K capital.
        FAITH's run_cycle() handles market hours, position management,
        and new trade entry internally.
        """
        now = datetime.now(CENTRAL_TZ)
        self.last_faith_check = now

        logger.info(f"=" * 80)
        logger.info(f"FAITH (2DTE Paper IC) triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.faith_trader:
            logger.warning("FAITH trader not available - skipping")
            self._save_heartbeat('FAITH', 'UNAVAILABLE')
            return

        try:
            result = self.faith_trader.run_cycle()

            action = result.get('action', 'none')
            traded = result.get('traded', False)
            managed = result.get('positions_managed', 0)

            logger.info(f"FAITH cycle completed: {action}")
            if traded:
                logger.info(f"  NEW PAPER TRADE OPENED")
            if managed > 0:
                logger.info(f"  Positions managed: {managed}")

            self.faith_execution_count += 1
            self._save_heartbeat('FAITH', 'TRADED' if traded else 'SCAN_COMPLETE', {
                'scan_number': self.faith_execution_count,
                'traded': traded,
                'action': action
            })

            logger.info(f"FAITH scan #{self.faith_execution_count} completed")
            logger.info(f"=" * 80)

        except Exception as e:
            logger.error(f"ERROR in FAITH: {str(e)}")
            logger.error(traceback.format_exc())
            self._save_heartbeat('FAITH', 'ERROR', {'error': str(e)})
            logger.info(f"=" * 80)

    def scheduled_faith_eod_logic(self):
        """
        FAITH End-of-Day processing - runs daily at 3:50 PM CT

        FAITH uses 3:45 PM ET (2:45 PM CT) EOD cutoff. The regular 5-min
        cycle handles closing at that cutoff. This EOD job at 3:50 PM CT is
        a safety net to force-close any positions that slipped through.
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"FAITH EOD triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.faith_trader:
            logger.warning("FAITH trader not available - skipping EOD processing")
            return

        try:
            # Run a close-only cycle to catch any remaining positions
            result = self.faith_trader.run_cycle(close_only=True)
            managed = result.get('positions_managed', 0)

            if managed > 0:
                logger.info(f"FAITH EOD: Closed {managed} remaining position(s)")
            else:
                logger.info("FAITH EOD: No positions to process")

            logger.info(f"FAITH EOD processing completed")
            logger.info(f"=" * 80)

        except Exception as e:
            logger.error(f"ERROR in FAITH EOD: {str(e)}")
            logger.error(traceback.format_exc())
            logger.info(f"=" * 80)

    # ========================================================================
    # GRACE - 1DTE Paper Iron Condor (SPY) - separate bot for comparison
    # ========================================================================

    def scheduled_grace_logic(self):
        """
        GRACE 1DTE Paper Iron Condor trading logic - runs every 5 minutes during market hours.
        Separate bot from FAITH for side-by-side 1DTE vs 2DTE comparison.
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"GRACE (1DTE Paper IC) triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.grace_trader:
            logger.warning("GRACE trader not available - skipping")
            self._save_heartbeat('GRACE', 'UNAVAILABLE')
            return

        try:
            result = self.grace_trader.run_cycle()

            action = result.get('action', 'none')
            traded = result.get('traded', False)
            managed = result.get('positions_managed', 0)

            logger.info(f"GRACE cycle completed: {action}")
            if traded:
                logger.info(f"  NEW PAPER TRADE OPENED (1DTE)")
            if managed > 0:
                logger.info(f"  Positions managed: {managed}")

            self.grace_execution_count += 1
            self._save_heartbeat('GRACE', 'TRADED' if traded else 'SCAN_COMPLETE', {
                'scan_number': self.grace_execution_count,
                'traded': traded,
                'action': action
            })

            logger.info(f"GRACE scan #{self.grace_execution_count} completed")
            logger.info(f"=" * 80)

        except Exception as e:
            logger.error(f"ERROR in GRACE: {str(e)}")
            logger.error(traceback.format_exc())
            self._save_heartbeat('GRACE', 'ERROR', {'error': str(e)})
            logger.info(f"=" * 80)

    def scheduled_grace_eod_logic(self):
        """GRACE End-of-Day processing."""
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"GRACE EOD triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.grace_trader:
            logger.warning("GRACE trader not available - skipping EOD processing")
            return

        try:
            result = self.grace_trader.run_cycle(close_only=True)
            managed = result.get('positions_managed', 0)

            if managed > 0:
                logger.info(f"GRACE EOD: Closed {managed} remaining position(s)")
            else:
                logger.info("GRACE EOD: No positions to process")

            logger.info(f"GRACE EOD processing completed")
            logger.info(f"=" * 80)

        except Exception as e:
            logger.error(f"ERROR in GRACE EOD: {str(e)}")
            logger.error(traceback.format_exc())
            logger.info(f"=" * 80)

    # ========================================================================
    # VALOR - MES Futures Scalping (24/5 Operation)
    # ========================================================================

    def scheduled_valor_logic(self):
        """
        VALOR MES Futures Scalping - runs every 1 minute during futures hours

        VALOR trades MES futures using GEX signals:
        - Positive gamma = Mean reversion (fade moves)
        - Negative gamma = Momentum (breakouts)
        - 24/5 trading (Sun 5pm - Fri 4pm CT with 4-5pm daily break)
        - $100k paper trading capital
        - Bayesian win probability tracking → ML after 50 trades

        CRITICAL: Logs EVERY scan for ML training data collection.
        """
        now = datetime.now(CENTRAL_TZ)
        self.valor_execution_count += 1
        self.last_valor_check = now

        # Check if VALOR is available
        if not self.valor_trader:
            if self.valor_execution_count % 60 == 1:  # Log once per hour
                logger.warning("VALOR trader not available - futures trading disabled")
            return

        try:
            # Run the scan cycle
            result = self.valor_trader.run_scan()

            # Log result
            status = result.get("status", "unknown")
            trades = result.get("trades_executed", 0)
            signals = result.get("signals_generated", 0)
            closed = result.get("positions_closed", 0)
            errors = result.get("errors", [])

            if status == "market_closed":
                if self.valor_execution_count % 60 == 1:  # Log once per hour
                    logger.info(f"VALOR: Futures market closed")
            elif status == "error":
                logger.error(f"VALOR scan error: {errors}")
            elif trades > 0:
                logger.info(f"VALOR: Executed {trades} trade(s) from {signals} signal(s)")
            elif closed > 0:
                logger.info(f"VALOR: Closed {closed} position(s)")
            else:
                # Normal scan - log occasionally for monitoring
                if self.valor_execution_count % 10 == 0:
                    logger.debug(f"VALOR scan #{self.valor_execution_count}: {signals} signals, no trades")

        except Exception as e:
            logger.error(f"ERROR in VALOR scan: {str(e)}")
            logger.error(traceback.format_exc())

    def scheduled_valor_position_monitor(self):
        """
        VALOR Position Monitor - runs every 15 seconds during futures hours

        Fast position checking to reduce stop slippage. The main scan runs
        every 1 minute for signal generation, but stops can be overshot by
        several points in that time. This monitor checks more frequently.

        Does NOT generate new signals - only checks existing positions.
        """
        if not self.valor_trader:
            return

        try:
            result = self.valor_trader.monitor_positions()

            # Log closed positions
            if result.get("positions_closed", 0) > 0:
                logger.info(f"VALOR MONITOR: Closed {result['positions_closed']} position(s)")

            # Log status if not normal (helps debug issues)
            status = result.get("status", "")
            if status and status not in ["completed", "market_closed"]:
                logger.warning(f"VALOR MONITOR: Status={status}, checked={result.get('positions_checked', 0)}")

        except Exception as e:
            # Log errors (but not every 15 seconds - use a counter)
            if not hasattr(self, '_monitor_error_count'):
                self._monitor_error_count = 0
            self._monitor_error_count += 1
            # Log every 4th error (once per minute) to avoid spam
            if self._monitor_error_count % 4 == 1:
                logger.error(f"VALOR MONITOR ERROR: {e}")

    def scheduled_valor_eod_logic(self):
        """
        VALOR End-of-Day processing - runs at 4:00 PM CT (futures close)

        For futures, EOD happens at the daily maintenance break (4-5pm CT):
        - Close any open positions at current price
        - Mark positions to market
        - Update daily P&L
        - Save equity snapshot
        - Record outcomes for ML feedback loop
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"VALOR EOD triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.valor_trader:
            logger.warning("VALOR trader not available - skipping EOD processing")
            return

        try:
            # Process any expired positions (close them at current market price)
            eod_result = self.valor_trader.process_expired_positions()

            if eod_result.get('processed_count', 0) > 0:
                logger.info(f"VALOR EOD: Processed {eod_result['processed_count']} position(s)")
                logger.info(f"  EOD P&L: ${eod_result['total_pnl']:,.2f}")
                for pos in eod_result.get('positions', []):
                    logger.info(f"  - {pos['position_id']}: ${pos['pnl']:,.2f}")

            if eod_result.get('errors'):
                for error in eod_result['errors']:
                    logger.error(f"  EOD Error: {error}")

            # Get current status after EOD processing
            status = self.valor_trader.get_status()

            # Log summary
            paper_account = status.get('paper_account', {})
            today = status.get('today', {})

            logger.info(f"VALOR EOD Summary:")
            logger.info(f"  Paper Balance: ${paper_account.get('current_balance', 0):,.2f}")
            logger.info(f"  Cumulative P&L: ${paper_account.get('cumulative_pnl', 0):,.2f}")
            logger.info(f"  Return: {paper_account.get('return_pct', 0):.2f}%")
            logger.info(f"  Today's Trades: {today.get('positions_closed', 0)}")
            logger.info(f"  Today's P&L: ${today.get('realized_pnl', 0):,.2f}")

            # Get win tracker info
            win_tracker = status.get('win_tracker', {})
            logger.info(f"  Win Probability: {win_tracker.get('win_probability', 0.5)*100:.1f}%")
            logger.info(f"  Total Trades: {win_tracker.get('total_trades', 0)}")
            logger.info(f"  Ready for ML: {win_tracker.get('should_use_ml', False)}")

            logger.info(f"=" * 80)

        except Exception as e:
            logger.error(f"ERROR in VALOR EOD: {str(e)}")
            logger.error(traceback.format_exc())
            logger.info(f"=" * 80)

    def scheduled_agape_logic(self):
        """
        AGAPE ETH Micro Futures - runs every 5 minutes during CME crypto hours.

        CME Micro Ether futures trade Sun 5PM - Fri 4PM CT with daily 4-5PM break.
        Uses Deribit GEX as primary signal, CoinGlass funding rate as secondary.
        """
        if not self.agape_trader:
            return

        try:
            result = self.agape_trader.run_cycle()
            outcome = result.get("outcome", "UNKNOWN")

            if result.get("new_trade"):
                logger.info(f"AGAPE: New trade! {outcome}")
            elif result.get("positions_closed", 0) > 0:
                logger.info(f"AGAPE: Closed {result['positions_closed']} position(s)")
            elif result.get("error"):
                logger.error(f"AGAPE: Cycle error: {result['error']}")
            else:
                if self.agape_trader._cycle_count % 12 == 0:  # Log once per hour
                    logger.debug(f"AGAPE scan #{self.agape_trader._cycle_count}: {outcome}")

        except Exception as e:
            logger.error(f"ERROR in AGAPE scan: {str(e)}")
            logger.error(traceback.format_exc())

    def scheduled_agape_eod_logic(self):
        """
        AGAPE End-of-Day - runs at 3:45 PM CT (before CME 4PM close).
        Force-closes any open positions before the daily maintenance break.
        """
        now = datetime.now(CENTRAL_TZ)
        logger.info(f"{'=' * 80}")
        logger.info(f"AGAPE EOD triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.agape_trader:
            logger.warning("AGAPE trader not available - skipping EOD")
            return

        try:
            result = self.agape_trader.run_cycle(close_only=True)
            closed = result.get("positions_closed", 0)
            if closed > 0:
                logger.info(f"AGAPE EOD: Closed {closed} position(s)")

            perf = self.agape_trader.get_performance()
            logger.info(f"AGAPE EOD Summary:")
            logger.info(f"  Total Trades: {perf.get('total_trades', 0)}")
            logger.info(f"  Win Rate: {perf.get('win_rate', 0)}%")
            logger.info(f"  Total P&L: ${perf.get('total_pnl', 0):,.2f}")
            logger.info(f"{'=' * 80}")

        except Exception as e:
            logger.error(f"ERROR in AGAPE EOD: {str(e)}")
            logger.error(traceback.format_exc())
            logger.info(f"{'=' * 80}")

    def scheduled_agape_spot_logic(self):
        """
        AGAPE-SPOT 24/7 Coinbase Spot Multi-Coin - runs every 1 minute.
        No market hours restrictions - trades around the clock.
        """
        if not self.agape_spot_trader:
            return

        try:
            result = self.agape_spot_trader.run_cycle()

            if result.get("total_new_trades", 0) > 0:
                logger.info(f"AGAPE-SPOT: New trade(s)! {result.get('tickers', {})}")
            elif result.get("total_positions_closed", 0) > 0:
                logger.info(f"AGAPE-SPOT: Closed {result['total_positions_closed']} position(s)")
            elif result.get("errors"):
                for err in result["errors"]:
                    logger.error(f"AGAPE-SPOT: {err}")
            else:
                # Log status every 60 scans (~1 hour) to avoid log spam at 1-min intervals
                if self.agape_spot_trader._cycle_count % 60 == 0:
                    logger.debug(f"AGAPE-SPOT scan #{self.agape_spot_trader._cycle_count}")

        except Exception as e:
            logger.error(f"ERROR in AGAPE-SPOT scan: {str(e)}")
            logger.error(traceback.format_exc())

    def scheduled_agape_btc_logic(self):
        """
        AGAPE-BTC Micro Futures - runs every 5 minutes during CME crypto hours.

        CME Micro Bitcoin futures trade Sun 5PM - Fri 4PM CT with daily 4-5PM break.
        Uses Deribit GEX as primary signal, CoinGlass funding rate as secondary.
        """
        if not self.agape_btc_trader:
            return

        try:
            result = self.agape_btc_trader.run_cycle()
            outcome = result.get("outcome", "UNKNOWN")

            if result.get("new_trade"):
                logger.info(f"AGAPE-BTC: New trade! {outcome}")
            elif result.get("positions_closed", 0) > 0:
                logger.info(f"AGAPE-BTC: Closed {result['positions_closed']} position(s)")
            elif result.get("error"):
                logger.error(f"AGAPE-BTC: Cycle error: {result['error']}")
            else:
                if self.agape_btc_trader._cycle_count % 12 == 0:
                    logger.debug(f"AGAPE-BTC scan #{self.agape_btc_trader._cycle_count}: {outcome}")

        except Exception as e:
            logger.error(f"ERROR in AGAPE-BTC scan: {str(e)}")
            logger.error(traceback.format_exc())

    def scheduled_agape_btc_eod_logic(self):
        """
        AGAPE-BTC End-of-Day - runs at 3:45 PM CT (before CME 4PM close).
        """
        now = datetime.now(CENTRAL_TZ)
        logger.info(f"AGAPE-BTC EOD triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.agape_btc_trader:
            return

        try:
            result = self.agape_btc_trader.run_cycle(close_only=True)
            closed = result.get("positions_closed", 0)
            if closed > 0:
                logger.info(f"AGAPE-BTC EOD: Closed {closed} position(s)")

            perf = self.agape_btc_trader.get_performance()
            logger.info(f"AGAPE-BTC EOD Summary: Trades={perf.get('total_trades', 0)}, "
                        f"Win Rate={perf.get('win_rate', 0)}%, P&L=${perf.get('total_pnl', 0):,.2f}")

        except Exception as e:
            logger.error(f"ERROR in AGAPE-BTC EOD: {str(e)}")
            logger.error(traceback.format_exc())

    def scheduled_agape_xrp_logic(self):
        """
        AGAPE-XRP Futures - runs every 5 minutes during CME crypto hours.

        CME XRP futures trade Sun 5PM - Fri 4PM CT with daily 4-5PM break.
        Uses Deribit GEX as primary signal, CoinGlass funding rate as secondary.
        """
        if not self.agape_xrp_trader:
            return

        try:
            result = self.agape_xrp_trader.run_cycle()
            outcome = result.get("outcome", "UNKNOWN")

            if result.get("new_trade"):
                logger.info(f"AGAPE-XRP: New trade! {outcome}")
            elif result.get("positions_closed", 0) > 0:
                logger.info(f"AGAPE-XRP: Closed {result['positions_closed']} position(s)")
            elif result.get("error"):
                logger.error(f"AGAPE-XRP: Cycle error: {result['error']}")
            else:
                if self.agape_xrp_trader._cycle_count % 12 == 0:
                    logger.debug(f"AGAPE-XRP scan #{self.agape_xrp_trader._cycle_count}: {outcome}")

        except Exception as e:
            logger.error(f"ERROR in AGAPE-XRP scan: {str(e)}")
            logger.error(traceback.format_exc())

    def scheduled_agape_xrp_eod_logic(self):
        """
        AGAPE-XRP End-of-Day - runs at 3:45 PM CT (before CME 4PM close).
        """
        now = datetime.now(CENTRAL_TZ)
        logger.info(f"AGAPE-XRP EOD triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.agape_xrp_trader:
            return

        try:
            result = self.agape_xrp_trader.run_cycle(close_only=True)
            closed = result.get("positions_closed", 0)
            if closed > 0:
                logger.info(f"AGAPE-XRP EOD: Closed {closed} position(s)")

            perf = self.agape_xrp_trader.get_performance()
            logger.info(f"AGAPE-XRP EOD Summary: Trades={perf.get('total_trades', 0)}, "
                        f"Win Rate={perf.get('win_rate', 0)}%, P&L=${perf.get('total_pnl', 0):,.2f}")

        except Exception as e:
            logger.error(f"ERROR in AGAPE-XRP EOD: {str(e)}")
            logger.error(traceback.format_exc())

    # =========================================================================
    # PERPETUAL CONTRACT BOT SCHEDULED METHODS
    # =========================================================================

    def scheduled_agape_eth_perp_logic(self):
        """
        AGAPE-ETH-PERP - runs every 5 minutes, 24/7.
        Perpetual contracts trade around the clock on crypto exchanges.
        Uses real Deribit/CoinGlass/Coinbase data for signals.
        """
        if not self.agape_eth_perp_trader:
            return

        try:
            result = self.agape_eth_perp_trader.run_cycle()
            outcome = result.get("outcome", "UNKNOWN")

            if result.get("new_trade"):
                logger.info(f"AGAPE-ETH-PERP: New trade! {outcome}")
            elif result.get("positions_closed", 0) > 0:
                logger.info(f"AGAPE-ETH-PERP: Closed {result['positions_closed']} position(s)")
            elif result.get("error"):
                logger.error(f"AGAPE-ETH-PERP: Cycle error: {result['error']}")
            else:
                if self.agape_eth_perp_trader._cycle_count % 12 == 0:
                    logger.debug(f"AGAPE-ETH-PERP scan #{self.agape_eth_perp_trader._cycle_count}: {outcome}")

        except Exception as e:
            logger.error(f"ERROR in AGAPE-ETH-PERP scan: {str(e)}")
            logger.error(traceback.format_exc())

    def scheduled_agape_eth_perp_eod_logic(self):
        """AGAPE-ETH-PERP End-of-Day - runs at 3:45 PM CT."""
        now = datetime.now(CENTRAL_TZ)
        logger.info(f"AGAPE-ETH-PERP EOD triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.agape_eth_perp_trader:
            return

        try:
            result = self.agape_eth_perp_trader.run_cycle(close_only=True)
            closed = result.get("positions_closed", 0)
            if closed > 0:
                logger.info(f"AGAPE-ETH-PERP EOD: Closed {closed} position(s)")

            perf = self.agape_eth_perp_trader.get_performance()
            logger.info(f"AGAPE-ETH-PERP EOD Summary: Trades={perf.get('total_trades', 0)}, "
                        f"Win Rate={perf.get('win_rate', 0)}%, P&L=${perf.get('total_pnl', 0):,.2f}")

        except Exception as e:
            logger.error(f"ERROR in AGAPE-ETH-PERP EOD: {str(e)}")
            logger.error(traceback.format_exc())

    def scheduled_agape_btc_perp_logic(self):
        """
        AGAPE-BTC-PERP - runs every 5 minutes, 24/7.
        Perpetual contracts trade around the clock on crypto exchanges.
        """
        if not self.agape_btc_perp_trader:
            return

        try:
            result = self.agape_btc_perp_trader.run_cycle()
            outcome = result.get("outcome", "UNKNOWN")

            if result.get("new_trade"):
                logger.info(f"AGAPE-BTC-PERP: New trade! {outcome}")
            elif result.get("positions_closed", 0) > 0:
                logger.info(f"AGAPE-BTC-PERP: Closed {result['positions_closed']} position(s)")
            elif result.get("error"):
                logger.error(f"AGAPE-BTC-PERP: Cycle error: {result['error']}")
            else:
                if self.agape_btc_perp_trader._cycle_count % 12 == 0:
                    logger.debug(f"AGAPE-BTC-PERP scan #{self.agape_btc_perp_trader._cycle_count}: {outcome}")

        except Exception as e:
            logger.error(f"ERROR in AGAPE-BTC-PERP scan: {str(e)}")
            logger.error(traceback.format_exc())

    def scheduled_agape_btc_perp_eod_logic(self):
        """AGAPE-BTC-PERP End-of-Day - runs at 3:45 PM CT."""
        now = datetime.now(CENTRAL_TZ)
        logger.info(f"AGAPE-BTC-PERP EOD triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.agape_btc_perp_trader:
            return

        try:
            result = self.agape_btc_perp_trader.run_cycle(close_only=True)
            closed = result.get("positions_closed", 0)
            if closed > 0:
                logger.info(f"AGAPE-BTC-PERP EOD: Closed {closed} position(s)")

            perf = self.agape_btc_perp_trader.get_performance()
            logger.info(f"AGAPE-BTC-PERP EOD Summary: Trades={perf.get('total_trades', 0)}, "
                        f"Win Rate={perf.get('win_rate', 0)}%, P&L=${perf.get('total_pnl', 0):,.2f}")

        except Exception as e:
            logger.error(f"ERROR in AGAPE-BTC-PERP EOD: {str(e)}")
            logger.error(traceback.format_exc())

    def scheduled_agape_xrp_perp_logic(self):
        """
        AGAPE-XRP-PERP - runs every 5 minutes, 24/7.
        Perpetual contracts trade around the clock on crypto exchanges.
        """
        if not self.agape_xrp_perp_trader:
            return

        try:
            result = self.agape_xrp_perp_trader.run_cycle()
            outcome = result.get("outcome", "UNKNOWN")

            if result.get("new_trade"):
                logger.info(f"AGAPE-XRP-PERP: New trade! {outcome}")
            elif result.get("positions_closed", 0) > 0:
                logger.info(f"AGAPE-XRP-PERP: Closed {result['positions_closed']} position(s)")
            elif result.get("error"):
                logger.error(f"AGAPE-XRP-PERP: Cycle error: {result['error']}")
            else:
                if self.agape_xrp_perp_trader._cycle_count % 12 == 0:
                    logger.debug(f"AGAPE-XRP-PERP scan #{self.agape_xrp_perp_trader._cycle_count}: {outcome}")

        except Exception as e:
            logger.error(f"ERROR in AGAPE-XRP-PERP scan: {str(e)}")
            logger.error(traceback.format_exc())

    def scheduled_agape_xrp_perp_eod_logic(self):
        """AGAPE-XRP-PERP End-of-Day - runs at 3:45 PM CT."""
        now = datetime.now(CENTRAL_TZ)
        logger.info(f"AGAPE-XRP-PERP EOD triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.agape_xrp_perp_trader:
            return

        try:
            result = self.agape_xrp_perp_trader.run_cycle(close_only=True)
            closed = result.get("positions_closed", 0)
            if closed > 0:
                logger.info(f"AGAPE-XRP-PERP EOD: Closed {closed} position(s)")

            perf = self.agape_xrp_perp_trader.get_performance()
            logger.info(f"AGAPE-XRP-PERP EOD Summary: Trades={perf.get('total_trades', 0)}, "
                        f"Win Rate={perf.get('win_rate', 0)}%, P&L=${perf.get('total_pnl', 0):,.2f}")

        except Exception as e:
            logger.error(f"ERROR in AGAPE-XRP-PERP EOD: {str(e)}")
            logger.error(traceback.format_exc())

    def scheduled_agape_doge_perp_logic(self):
        """
        AGAPE-DOGE-PERP - runs every 5 minutes, 24/7.
        Perpetual contracts trade around the clock on crypto exchanges.
        """
        if not self.agape_doge_perp_trader:
            return

        try:
            result = self.agape_doge_perp_trader.run_cycle()
            outcome = result.get("outcome", "UNKNOWN")

            if result.get("new_trade"):
                logger.info(f"AGAPE-DOGE-PERP: New trade! {outcome}")
            elif result.get("positions_closed", 0) > 0:
                logger.info(f"AGAPE-DOGE-PERP: Closed {result['positions_closed']} position(s)")
            elif result.get("error"):
                logger.error(f"AGAPE-DOGE-PERP: Cycle error: {result['error']}")
            else:
                if self.agape_doge_perp_trader._cycle_count % 12 == 0:
                    logger.debug(f"AGAPE-DOGE-PERP scan #{self.agape_doge_perp_trader._cycle_count}: {outcome}")

        except Exception as e:
            logger.error(f"ERROR in AGAPE-DOGE-PERP scan: {str(e)}")
            logger.error(traceback.format_exc())

    def scheduled_agape_doge_perp_eod_logic(self):
        """AGAPE-DOGE-PERP End-of-Day - runs at 3:45 PM CT."""
        now = datetime.now(CENTRAL_TZ)
        logger.info(f"AGAPE-DOGE-PERP EOD triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.agape_doge_perp_trader:
            return

        try:
            result = self.agape_doge_perp_trader.run_cycle(close_only=True)
            closed = result.get("positions_closed", 0)
            if closed > 0:
                logger.info(f"AGAPE-DOGE-PERP EOD: Closed {closed} position(s)")

            perf = self.agape_doge_perp_trader.get_performance()
            logger.info(f"AGAPE-DOGE-PERP EOD Summary: Trades={perf.get('total_trades', 0)}, "
                        f"Win Rate={perf.get('win_rate', 0)}%, P&L=${perf.get('total_pnl', 0):,.2f}")

        except Exception as e:
            logger.error(f"ERROR in AGAPE-DOGE-PERP EOD: {str(e)}")
            logger.error(traceback.format_exc())

    def scheduled_agape_shib_perp_logic(self):
        """
        AGAPE-SHIB-PERP - runs every 5 minutes, 24/7.
        Perpetual contracts trade around the clock on crypto exchanges.
        """
        if not self.agape_shib_perp_trader:
            return

        try:
            result = self.agape_shib_perp_trader.run_cycle()
            outcome = result.get("outcome", "UNKNOWN")

            if result.get("new_trade"):
                logger.info(f"AGAPE-SHIB-PERP: New trade! {outcome}")
            elif result.get("positions_closed", 0) > 0:
                logger.info(f"AGAPE-SHIB-PERP: Closed {result['positions_closed']} position(s)")
            elif result.get("error"):
                logger.error(f"AGAPE-SHIB-PERP: Cycle error: {result['error']}")
            else:
                if self.agape_shib_perp_trader._cycle_count % 12 == 0:
                    logger.debug(f"AGAPE-SHIB-PERP scan #{self.agape_shib_perp_trader._cycle_count}: {outcome}")

        except Exception as e:
            logger.error(f"ERROR in AGAPE-SHIB-PERP scan: {str(e)}")
            logger.error(traceback.format_exc())

    def scheduled_agape_shib_perp_eod_logic(self):
        """AGAPE-SHIB-PERP End-of-Day - runs at 3:45 PM CT."""
        now = datetime.now(CENTRAL_TZ)
        logger.info(f"AGAPE-SHIB-PERP EOD triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.agape_shib_perp_trader:
            return

        try:
            result = self.agape_shib_perp_trader.run_cycle(close_only=True)
            closed = result.get("positions_closed", 0)
            if closed > 0:
                logger.info(f"AGAPE-SHIB-PERP EOD: Closed {closed} position(s)")

            perf = self.agape_shib_perp_trader.get_performance()
            logger.info(f"AGAPE-SHIB-PERP EOD Summary: Trades={perf.get('total_trades', 0)}, "
                        f"Win Rate={perf.get('win_rate', 0)}%, P&L=${perf.get('total_pnl', 0):,.2f}")

        except Exception as e:
            logger.error(f"ERROR in AGAPE-SHIB-PERP EOD: {str(e)}")
            logger.error(traceback.format_exc())

    def scheduled_jubilee_daily_logic(self):
        """
        JUBILEE Box Spread Daily Cycle - runs once daily at 9:30 AM CT

        Manages box spread positions for synthetic borrowing:
        - Updates position DTEs and accrued costs
        - Calculates IC bot returns attribution
        - Checks for roll opportunities (DTE < 30)
        - Records equity snapshots
        - Generates daily briefing

        Box spreads are longer-term (months), so daily checks are sufficient.
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"JUBILEE Daily Cycle triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.jubilee_trader:
            logger.warning("JUBILEE trader not available - skipping daily cycle")
            return

        try:
            # Run the daily cycle
            result = self.jubilee_trader.run_daily_cycle()

            if result:
                logger.info(f"JUBILEE Daily Cycle completed:")
                logger.info(f"  Positions updated: {result.get('positions_updated', 0)}")
                logger.info(f"  Roll candidates: {len(result.get('roll_candidates', []))}")

                # AUTOMATICALLY EXECUTE ROLLS - Box spreads should ALWAYS stay open
                # When DTE reaches threshold, roll to new expiration (don't let them expire)
                for candidate in result.get('roll_candidates', []):
                    position_id = candidate['position_id']
                    current_dte = candidate['current_dte']
                    logger.info(f"    AUTO-ROLLING: {position_id} (DTE: {current_dte})")

                    try:
                        roll_result = self.jubilee_trader.roll_position(position_id)
                        if roll_result.get('success'):
                            logger.info(f"    ✅ Successfully rolled {position_id} -> {roll_result.get('new_position_id')}")
                        else:
                            logger.warning(f"    ⚠️ Roll failed for {position_id}: {roll_result.get('error')}")
                    except Exception as roll_error:
                        logger.error(f"    ❌ Roll exception for {position_id}: {roll_error}")

                # Log warnings from daily briefing
                briefing = result.get('daily_briefing', {})
                warnings = briefing.get('actions', {}).get('warnings', [])
                for warning in warnings:
                    logger.warning(f"    Warning: {warning}")

                if result.get('errors'):
                    for error in result['errors']:
                        logger.error(f"    Error: {error}")

            # Verify box spread still exists after daily cycle.
            # The IC trader's _ensure_paper_box_spread() (called every 5 min)
            # is the primary safety net. This is just a log check.
            open_positions = self.jubilee_trader.get_positions()
            if not open_positions:
                logger.warning(
                    "JUBILEE: No open box spreads after daily cycle. "
                    "IC trader will create one on its next 5-min cycle via _ensure_paper_box_spread()."
                )

            logger.info(f"JUBILEE Daily Cycle completed successfully")
            logger.info(f"=" * 80)

        except Exception as e:
            logger.error(f"ERROR in JUBILEE Daily Cycle: {str(e)}")
            logger.error(traceback.format_exc())
            logger.info(f"=" * 80)

    def scheduled_jubilee_equity_snapshot(self):
        """
        JUBILEE Equity Snapshot - runs every 30 minutes during market hours.

        Saves current equity state including:
        - Total borrowed capital
        - Unrealized P&L on box spreads (using real Tradier quotes)
        - IC bot returns attribution
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"JUBILEE Equity Snapshot triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.is_market_open():
            logger.info("Market is CLOSED. Skipping JUBILEE equity snapshot.")
            return

        if not self.jubilee_trader:
            logger.warning("JUBILEE trader not available - skipping equity snapshot")
            return

        try:
            from trading.jubilee.db import JubileeDatabase
            db = JubileeDatabase()

            # Use existing record_equity_snapshot which fetches real Tradier quotes
            success = db.record_equity_snapshot(use_real_quotes=True)

            if success:
                logger.info(f"JUBILEE: Equity snapshot recorded successfully")
            else:
                logger.warning(f"JUBILEE: Failed to record equity snapshot")

        except Exception as e:
            logger.error(f"ERROR in JUBILEE Equity Snapshot: {str(e)}")
            logger.error(traceback.format_exc())

    def scheduled_jubilee_rate_analysis(self):
        """
        JUBILEE Rate Analysis - runs hourly during market hours.

        Fetches current box spread rates and saves to database for trend analysis.
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"JUBILEE Rate Analysis triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.is_market_open():
            logger.info("Market is CLOSED. Skipping JUBILEE rate analysis.")
            return

        if not self.jubilee_trader:
            logger.warning("JUBILEE trader not available - skipping rate analysis")
            return

        try:
            from trading.jubilee.signals import BoxSpreadSignalGenerator
            from trading.jubilee.db import JubileeDatabase

            generator = BoxSpreadSignalGenerator()
            db = JubileeDatabase()

            # Analyze current rates
            analysis = generator.analyze_current_rates()

            if analysis:
                # Save to database for trend tracking
                db.save_rate_analysis(analysis)
                logger.info(f"JUBILEE: Saved rate analysis - Box rate={analysis.box_implied_rate:.2f}%, "
                           f"Fed Funds={analysis.fed_funds_rate:.2f}%, Spread={analysis.spread_to_margin:.2f}%")
            else:
                logger.warning("JUBILEE: Failed to analyze current rates")

        except Exception as e:
            logger.error(f"ERROR in JUBILEE Rate Analysis: {str(e)}")
            logger.error(traceback.format_exc())

    def scheduled_jubilee_ic_cycle(self):
        """
        JUBILEE IC Trading Cycle - runs every 5 minutes during market hours (MATCHES ANCHOR).

        This is the main trading loop for JUBILEE Iron Condors that use
        borrowed capital from box spreads to generate returns.

        The cycle:
        1. Checks exit conditions on all open IC positions
        2. Generates new signals when capital is available
        3. Executes approved signals
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"JUBILEE IC Trading Cycle triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.is_market_open():
            logger.info("Market is CLOSED. Skipping JUBILEE IC trading cycle.")
            return

        if not self.jubilee_ic_trader:
            logger.warning("JUBILEE IC trader not available - skipping trading cycle")
            return

        try:
            result = self.jubilee_ic_trader.run_trading_cycle()

            if result.get('skip_reason'):
                logger.info(f"JUBILEE IC: {result['skip_reason']}")
            else:
                logger.info(f"JUBILEE IC Cycle completed:")
                logger.info(f"  Positions checked: {result.get('positions_checked', 0)}")
                logger.info(f"  Positions closed: {result.get('positions_closed', 0)}")
                if result.get('new_position'):
                    logger.info(f"  New position opened: {result['new_position']}")
                if result.get('errors'):
                    for err in result['errors']:
                        logger.warning(f"  Error: {err}")

        except Exception as e:
            logger.error(f"ERROR in JUBILEE IC Trading Cycle: {str(e)}")
            logger.error(traceback.format_exc())

    def scheduled_jubilee_ic_mtm_update(self):
        """
        JUBILEE IC Mark-to-Market Update - runs every 30 minutes.

        Updates the current value and unrealized P&L for all open IC positions
        using real-time quotes from Tradier production API.
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"JUBILEE IC MTM Update triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.is_market_open():
            logger.info("Market is CLOSED. Skipping JUBILEE IC MTM update.")
            return

        if not self.jubilee_ic_trader:
            logger.warning("JUBILEE IC trader not available - skipping MTM update")
            return

        try:
            from trading.jubilee.trader import run_jubilee_ic_mtm_update
            result = run_jubilee_ic_mtm_update()
            logger.info(f"JUBILEE IC MTM: Updated {result.get('updated', 0)}/{result.get('total', 0)} positions")

        except Exception as e:
            logger.error(f"ERROR in JUBILEE IC MTM Update: {str(e)}")
            logger.error(traceback.format_exc())

    def scheduled_jubilee_ic_equity_snapshot(self):
        """
        JUBILEE IC Equity Snapshot - runs every 5 minutes during market hours.

        Records periodic equity snapshots for the intraday equity curve chart.
        Without this, the chart only gets data points when trades open/close,
        which can leave the chart empty on quiet days.
        """
        now = datetime.now(CENTRAL_TZ)

        if not self.is_market_open():
            return

        if not self.jubilee_ic_trader:
            return

        try:
            from trading.jubilee.db import JubileeDatabase
            db = JubileeDatabase()
            success = db.record_ic_equity_snapshot()

            if success:
                logger.info(f"JUBILEE IC: Equity snapshot recorded at {now.strftime('%H:%M:%S')}")
            else:
                logger.warning(f"JUBILEE IC: Failed to record equity snapshot")

        except Exception as e:
            logger.error(f"ERROR in JUBILEE IC Equity Snapshot: {str(e)}")
            logger.error(traceback.format_exc())

    def scheduled_watchtower_logic(self):
        """
        WATCHTOWER (0DTE Gamma Live) commentary generation - runs every 5 minutes during market hours

        Generates AI-powered market commentary based on current gamma structure:
        - Gamma regime analysis
        - Magnet/pin predictions
        - Danger zone alerts
        - Expected move changes

        Commentary is stored in the watchtower_commentary table for the Live Log.
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"WATCHTOWER (Commentary) triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.is_market_open():
            logger.info("Market is CLOSED. Skipping WATCHTOWER commentary generation.")
            return

        logger.info("Market is OPEN. Generating WATCHTOWER gamma commentary...")

        try:
            self.last_watchtower_check = now

            # Call the WATCHTOWER commentary generation endpoint via HTTP
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
                        f"{base_url}/api/watchtower/commentary/generate",
                        json={"force": False},
                        timeout=60
                    )
                    if response.status_code == 200:
                        result = response.json()
                        logger.info(f"WATCHTOWER: Commentary generated via {base_url}")
                        break
                except requests.exceptions.RequestException as e:
                    logger.debug(f"WATCHTOWER: Could not reach {base_url}: {e}")
                    continue

            if result and result.get('success'):
                data = result.get('data', {})
                commentary = data.get('commentary', '')
                generated_at = data.get('generated_at', '')

                # Log success with preview of commentary
                preview = commentary[:100] + '...' if len(commentary) > 100 else commentary
                logger.info(f"WATCHTOWER commentary generated:")
                logger.info(f"  Time: {generated_at}")
                logger.info(f"  Preview: {preview}")
            else:
                logger.warning("WATCHTOWER: Commentary generation returned no result")

            self.watchtower_execution_count += 1
            logger.info(f"WATCHTOWER commentary #{self.watchtower_execution_count} completed (next in 5 min)")

            # Also check and update WATCHTOWER signal outcomes (intraday checks for profit/stop)
            try:
                for base_url in base_urls:
                    try:
                        response = requests.post(
                            f"{base_url}/api/watchtower/signals/update-outcomes?symbol=SPY",
                            timeout=30
                        )
                        if response.status_code == 200:
                            outcome_result = response.json()
                            if outcome_result.get('success'):
                                updates = outcome_result.get('data', {}).get('updates', {})
                                if updates.get('closed', 0) > 0:
                                    logger.info(f"WATCHTOWER Signals: {updates.get('wins', 0)} wins, {updates.get('losses', 0)} losses closed")
                            break
                    except requests.exceptions.RequestException:
                        continue
            except Exception as sig_err:
                logger.debug(f"WATCHTOWER signal outcome check skipped: {sig_err}")

            logger.info(f"=" * 80)

        except Exception as e:
            error_msg = f"ERROR in WATCHTOWER commentary generation: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            logger.info("WATCHTOWER will retry next interval")
            logger.info(f"=" * 80)

    def scheduled_watchtower_eod_logic(self):
        """
        WATCHTOWER End-of-Day processing - runs daily at 3:01 PM CT

        Updates pin prediction accuracy tracking:
        1. Updates today's pin prediction with actual closing price
        2. Calculates and stores WATCHTOWER prediction accuracy metrics

        This enables the pin accuracy tracking feature to work end-to-end.
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"WATCHTOWER EOD triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        try:
            # Call the WATCHTOWER EOD processing endpoint via HTTP
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
                        f"{base_url}/api/watchtower/eod-processing?symbol=SPY",
                        timeout=60
                    )
                    if response.status_code == 200:
                        result = response.json()
                        logger.info(f"WATCHTOWER EOD: Processing completed via {base_url}")
                        break
                except requests.exceptions.RequestException as e:
                    logger.debug(f"WATCHTOWER EOD: Could not reach {base_url}: {e}")
                    continue

            if result and result.get('success'):
                data = result.get('data', {})
                actions = data.get('actions', [])
                for action in actions:
                    status = "✓" if action.get('success') else "✗"
                    logger.info(f"  {status} {action.get('action')}: {action.get('description')}")
            else:
                logger.warning("WATCHTOWER EOD: Processing returned no result")

            # Force close all open WATCHTOWER signals at market close (0DTE expiration)
            logger.info("WATCHTOWER EOD: Closing all open signals (0DTE expiration)...")
            for base_url in base_urls:
                try:
                    response = requests.post(
                        f"{base_url}/api/watchtower/signals/update-outcomes?symbol=SPY&force_close=true",
                        timeout=60
                    )
                    if response.status_code == 200:
                        outcome_result = response.json()
                        if outcome_result.get('success'):
                            updates = outcome_result.get('data', {}).get('updates', {})
                            logger.info(f"WATCHTOWER EOD Signals: Closed {updates.get('closed', 0)} signals "
                                       f"({updates.get('wins', 0)} wins, {updates.get('losses', 0)} losses)")
                        break
                except requests.exceptions.RequestException as e:
                    logger.debug(f"WATCHTOWER EOD: Could not reach {base_url} for signal updates: {e}")
                    continue

            logger.info(f"WATCHTOWER EOD processing completed")
            logger.info(f"=" * 80)

        except Exception as e:
            error_msg = f"ERROR in WATCHTOWER EOD processing: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            logger.info("WATCHTOWER EOD will retry next trading day")
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

    def scheduled_proverbs_logic(self):
        """
        PROVERBS (Feedback Loop Intelligence) - runs DAILY at 4:00 PM CT

        Migration 023: Enhanced with Prophet-Proverbs integration for complete feedback loop.

        Orchestrates the autonomous feedback loop for all trading bots:
        1. Trains Prophet from new trade outcomes (auto_train)
        2. Runs Proverbs feedback loop (parameter proposals, A/B testing)
        3. Analyzes strategy-level performance (IC vs Directional)
        4. Tracks Prophet recommendation accuracy

        Bots: FORTRESS, SOLOMON, SAMSON, ANCHOR, GIDEON

        "Iron sharpens iron, and one man sharpens another" - Proverbs 27:17
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"PROVERBS (Feedback Loop) triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not PROVERBS_AVAILABLE:
            logger.warning("PROVERBS: Feedback loop system not available")
            return

        try:
            # ================================================================
            # STEP 1: Train Prophet from new trade outcomes
            # Migration 023: Prophet learns from outcomes before Proverbs analyzes
            # ================================================================
            if PROPHET_AVAILABLE and prophet_auto_train:
                logger.info("PROVERBS: Step 1 - Training Prophet from new outcomes...")
                try:
                    train_result = prophet_auto_train(threshold_outcomes=10)  # Lower threshold for daily runs
                    if train_result.get('triggered'):
                        logger.info(f"  Prophet training triggered: {train_result.get('reason')}")
                        if train_result.get('success'):
                            metrics = train_result.get('training_metrics')
                            if metrics:
                                logger.info(f"  Training metrics: accuracy={metrics.get('accuracy', 'N/A')}, samples={metrics.get('samples', 'N/A')}")
                        else:
                            logger.warning(f"  Prophet training failed: {train_result.get('error', 'Unknown error')}")
                    else:
                        logger.info(f"  Prophet training skipped: {train_result.get('reason')}")
                except Exception as e:
                    logger.warning(f"  Prophet auto_train failed: {e}")
            else:
                logger.info("PROVERBS: Step 1 - Prophet training skipped (not available)")

            # ================================================================
            # STEP 2: Run Proverbs feedback loop
            # ================================================================
            logger.info("PROVERBS: Step 2 - Running feedback loop analysis...")
            result = run_feedback_loop()

            if result.success:
                logger.info(f"PROVERBS: Feedback loop completed successfully")
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
                logger.error(f"PROVERBS: Feedback loop completed with errors")
                for error in result.errors:
                    logger.error(f"  Error: {error}")

            # ================================================================
            # STEP 3: Analyze strategy-level performance (Migration 023)
            # ================================================================
            strategy_analysis = None
            prophet_accuracy = None

            if PROVERBS_ENHANCED_AVAILABLE and get_proverbs_enhanced:
                logger.info("PROVERBS: Step 3 - Analyzing strategy-level performance...")
                try:
                    enhanced = get_proverbs_enhanced()

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

                    # Get Prophet accuracy
                    prophet_accuracy = enhanced.get_prophet_accuracy(days=30)
                    if prophet_accuracy.get('status') == 'analyzed':
                        summary = prophet_accuracy.get('summary', '')
                        if summary:
                            logger.info(f"  Prophet Accuracy: {summary}")

                except Exception as e:
                    logger.warning(f"  Strategy analysis failed: {e}")
            else:
                logger.info("PROVERBS: Step 3 - Strategy analysis skipped (Proverbs Enhanced not available)")

            # Save heartbeat with enhanced data
            self._save_heartbeat('PROVERBS', 'FEEDBACK_LOOP_COMPLETE', {
                'run_id': result.run_id,
                'success': result.success,
                'proposals_created': len(result.proposals_created),
                'proposals_applied': len(result.proposals_applied) if hasattr(result, 'proposals_applied') else 0,
                'alerts_raised': len(result.alerts_raised),
                'strategy_analysis': strategy_analysis.get('recommendation') if strategy_analysis else None,
                'prophet_accuracy': prophet_accuracy.get('summary') if prophet_accuracy else None
            })

            logger.info(f"PROVERBS: Next run tomorrow at 4:00 PM CT")
            logger.info(f"=" * 80)

        except Exception as e:
            error_msg = f"ERROR in PROVERBS feedback loop: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            self._save_heartbeat('PROVERBS', 'ERROR', {'error': str(e)})
            logger.info("PROVERBS will retry tomorrow at 4:00 PM CT")
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
        # REMOVED: ML Regime Classifier - Prophet is god
        # The REGIME_CLASSIFIER training code has been removed.
        # Prophet decides all trades.
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

    def scheduled_wisdom_training_logic(self):
        """
        WISDOM (Strategic Algorithmic Guidance Engine) Training - runs WEEKLY on Sunday at 4:30 PM CT

        FIX (Jan 2026): WISDOM was previously only available via manual API calls.
        This scheduled training ensures WISDOM models stay fresh and the Prophet
        receives updated probability predictions.

        Training order on Sundays:
        - 4:00 PM: PROVERBS (feedback loop)
        - 4:30 PM: WISDOM (this job)
        - 5:00 PM: QUANT (GEX Directional)
        - 6:00 PM: GEX ML (Probability Models)
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"WISDOM (ML Advisor) Training triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        try:
            # Try to import WISDOM training module
            from backend.api.routes.ml_routes import train_wisdom_model_internal

            logger.info("WISDOM: Starting weekly model training...")

            # Train WISDOM with CHRONICLES data as fallback
            result = train_wisdom_model_internal(
                min_samples=30,
                use_chronicles=True
            )

            if result.get('success'):
                logger.info(f"WISDOM: ✅ Training completed successfully")
                logger.info(f"  Training method: {result.get('training_method', 'unknown')}")
                logger.info(f"  Samples used: {result.get('samples_used', 0)}")
                logger.info(f"  Model accuracy: {result.get('accuracy', 'N/A')}")

                self._save_heartbeat('WISDOM', 'TRAINING_COMPLETE', result)
                self._record_training_history(
                    model_name='WISDOM',
                    status='COMPLETED',
                    accuracy_after=result.get('accuracy', 0) * 100 if result.get('accuracy') else None,
                    training_samples=result.get('samples_used', 0),
                    triggered_by='SCHEDULED'
                )
            else:
                logger.warning(f"WISDOM: ⚠️ Training not completed: {result.get('message', 'Unknown reason')}")
                self._save_heartbeat('WISDOM', 'TRAINING_SKIPPED', result)

        except ImportError as e:
            logger.warning(f"WISDOM: Training module not available: {e}")
            logger.info("WISDOM: Skipping scheduled training - module import failed")
        except Exception as e:
            logger.error(f"WISDOM: ❌ Training failed with error: {e}")
            logger.error(traceback.format_exc())
            self._save_heartbeat('WISDOM', 'ERROR', {'error': str(e)})
            self._record_training_history(
                model_name='WISDOM',
                status='FAILED',
                triggered_by='SCHEDULED',
                error=str(e)
            )

        logger.info(f"WISDOM: Next training scheduled for next Sunday at 4:30 PM CT")
        logger.info(f"=" * 80)

    def scheduled_prophet_training_logic(self):
        """
        PROPHET Training - runs DAILY at midnight CT

        FIX (Jan 2026): Prophet training was previously only triggered via PROVERBS
        feedback loop at 4 PM. This standalone job ensures Prophet gets trained
        even if PROVERBS has issues.

        Prophet learns from:
        1. Live trade outcomes (primary)
        2. Database backtests (fallback)
        3. CHRONICLES backtest data (final fallback)
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"PROPHET Training triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not PROPHET_AVAILABLE or not prophet_auto_train:
            logger.warning("PROPHET: Training module not available - skipping")
            return

        try:
            logger.info("PROPHET: Starting daily model training...")

            # Use lower threshold for daily training (10 outcomes)
            result = prophet_auto_train(threshold_outcomes=10, force=False)

            if result.get('triggered'):
                if result.get('success'):
                    metrics = result.get('training_metrics', {})
                    logger.info(f"PROPHET: ✅ Training completed successfully")
                    logger.info(f"  Method: {result.get('method', 'unknown')}")
                    logger.info(f"  Accuracy: {metrics.get('accuracy', 'N/A')}")
                    logger.info(f"  AUC-ROC: {metrics.get('auc_roc', 'N/A')}")
                    logger.info(f"  Samples: {metrics.get('total_samples', 0)}")

                    self._save_heartbeat('PROPHET', 'TRAINING_COMPLETE', result)
                    self._record_training_history(
                        model_name='PROPHET',
                        status='COMPLETED',
                        accuracy_after=metrics.get('accuracy', 0) * 100 if metrics.get('accuracy') else None,
                        training_samples=metrics.get('total_samples', 0),
                        triggered_by='SCHEDULED'
                    )
                else:
                    logger.warning(f"PROPHET: ⚠️ Training triggered but failed: {result.get('error')}")
                    self._save_heartbeat('PROPHET', 'TRAINING_FAILED', result)
            else:
                logger.info(f"PROPHET: ℹ️ Training not needed: {result.get('reason', 'No new outcomes')}")
                self._save_heartbeat('PROPHET', 'TRAINING_SKIPPED', result)

        except Exception as e:
            logger.error(f"PROPHET: ❌ Training failed with error: {e}")
            logger.error(traceback.format_exc())
            self._save_heartbeat('PROPHET', 'ERROR', {'error': str(e)})
            self._record_training_history(
                model_name='PROPHET',
                status='FAILED',
                triggered_by='SCHEDULED',
                error=str(e)
            )

        logger.info(f"PROPHET: Next training tomorrow at midnight CT")
        logger.info(f"=" * 80)

    def _ensure_required_tables(self):
        """
        AUTO-MIGRATION: Ensure all required tables exist on startup.

        This eliminates manual migration steps - tables are created automatically
        when the scheduler starts. Follows STANDARDS.md requirement for automatic
        data population without manual triggers.
        """
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Create ml_model_metadata table if not exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ml_model_metadata (
                    id SERIAL PRIMARY KEY,
                    model_name VARCHAR(50) NOT NULL,
                    model_version VARCHAR(50),
                    trained_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    training_samples INTEGER,
                    accuracy DECIMAL(5,4),
                    feature_importance JSONB,
                    hyperparameters JSONB,
                    model_type VARCHAR(50),
                    is_active BOOLEAN DEFAULT TRUE,
                    deployed_at TIMESTAMPTZ DEFAULT NOW(),
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    notes TEXT
                )
            """)

            # Create gex_collection_health table if not exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS gex_collection_health (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMPTZ DEFAULT NOW(),
                    symbol VARCHAR(10) DEFAULT 'SPY',
                    success BOOLEAN,
                    data_source VARCHAR(50),
                    error_message TEXT,
                    net_gex DECIMAL(20,2),
                    records_saved INTEGER DEFAULT 0
                )
            """)

            # Create discernment_outcomes table if not exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS discernment_outcomes (
                    id SERIAL PRIMARY KEY,
                    prediction_id INTEGER,
                    symbol VARCHAR(10),
                    prediction_timestamp TIMESTAMPTZ,
                    outcome_timestamp TIMESTAMPTZ DEFAULT NOW(),
                    predicted_direction VARCHAR(10),
                    actual_direction VARCHAR(10),
                    predicted_magnitude DECIMAL(5,2),
                    actual_magnitude DECIMAL(5,2),
                    direction_correct BOOLEAN,
                    magnitude_correct BOOLEAN,
                    price_at_prediction DECIMAL(10,2),
                    price_at_outcome DECIMAL(10,2)
                )
            """)

            conn.commit()
            logger.info("STARTUP: ✅ Required tables verified/created")

        except Exception as e:
            logger.error(f"STARTUP: Failed to ensure tables: {e}")
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass

    def _cleanup_incomplete_gex_records(self):
        """
        AUTO-CLEANUP: Remove incomplete GEX history records on startup.

        Incomplete records (net_gex=0, regime=NULL) occur when collection
        fails mid-process. These pollute the data and should be removed.

        Follows STANDARDS.md: automatic maintenance, no manual triggers.
        """
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Count incomplete records first
            cursor.execute("""
                SELECT COUNT(*) FROM gex_history
                WHERE (net_gex = 0 OR net_gex IS NULL)
                AND (regime IS NULL)
            """)
            incomplete_count = cursor.fetchone()[0]

            if incomplete_count == 0:
                logger.info("STARTUP: ✅ GEX history data is clean (no incomplete records)")
                conn.close()
                return

            # Delete incomplete records
            cursor.execute("""
                DELETE FROM gex_history
                WHERE (net_gex = 0 OR net_gex IS NULL)
                AND (regime IS NULL)
            """)
            deleted = cursor.rowcount

            conn.commit()
            logger.info(f"STARTUP: 🧹 Cleaned up {deleted} incomplete GEX records")

        except Exception as e:
            logger.error(f"STARTUP: Failed to cleanup GEX records: {e}")
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass

    def _check_startup_recovery(self):
        """
        FIX (Jan 2026): Check if any scheduled training was missed and run catch-up.

        This addresses the systemic issue where ML training stops on holidays
        and never restarts because scheduled jobs don't have catch-up logic.

        Called during scheduler startup to recover from:
        - Missed training due to scheduler restart
        - Missed training due to holidays/weekends
        - Missed training due to worker crashes

        Also performs automatic database maintenance:
        - Creates ml_model_metadata table if missing
        - Cleans up incomplete GEX history records
        """
        now = datetime.now(CENTRAL_TZ)
        logger.info(f"=" * 80)
        logger.info(f"STARTUP RECOVERY: Running automatic maintenance and training checks...")

        # =====================================================================
        # STEP 1: Ensure required tables exist (auto-migration)
        # =====================================================================
        self._ensure_required_tables()

        # =====================================================================
        # STEP 2: Clean up incomplete GEX records
        # =====================================================================
        self._cleanup_incomplete_gex_records()

        # =====================================================================
        # STEP 3: Check for overdue ML training
        # =====================================================================
        recovery_needed = []

        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Check WISDOM (weekly - should have run within 7 days)
            cursor.execute("""
                SELECT MAX(timestamp) FROM quant_training_history
                WHERE model_name = 'WISDOM' AND status = 'COMPLETED'
            """)
            row = cursor.fetchone()
            sage_last = row[0] if row and row[0] else None
            if not sage_last or (now.replace(tzinfo=None) - sage_last).days > 7:
                days_since = (now.replace(tzinfo=None) - sage_last).days if sage_last else 999
                logger.warning(f"WISDOM: Last trained {days_since} days ago - OVERDUE")
                recovery_needed.append(('WISDOM', days_since))

            # Check PROPHET (daily - should have run within 2 days)
            cursor.execute("""
                SELECT MAX(timestamp) FROM quant_training_history
                WHERE model_name = 'PROPHET' AND status = 'COMPLETED'
            """)
            row = cursor.fetchone()
            prophet_last = row[0] if row and row[0] else None
            if not prophet_last or (now.replace(tzinfo=None) - prophet_last).days > 2:
                days_since = (now.replace(tzinfo=None) - prophet_last).days if prophet_last else 999
                logger.warning(f"PROPHET: Last trained {days_since} days ago - OVERDUE")
                recovery_needed.append(('PROPHET', days_since))

            # Check GEX_DIRECTIONAL (weekly - should have run within 8 days)
            cursor.execute("""
                SELECT MAX(timestamp) FROM quant_training_history
                WHERE model_name = 'GEX_DIRECTIONAL' AND status = 'COMPLETED'
            """)
            row = cursor.fetchone()
            quant_last = row[0] if row and row[0] else None
            if not quant_last or (now.replace(tzinfo=None) - quant_last).days > 8:
                days_since = (now.replace(tzinfo=None) - quant_last).days if quant_last else 999
                logger.warning(f"GEX_DIRECTIONAL: Last trained {days_since} days ago - OVERDUE")
                recovery_needed.append(('GEX_DIRECTIONAL', days_since))

            # Check GEX ML (weekly - should have run within 8 days)
            cursor.execute("""
                SELECT MAX(created_at) FROM ml_models
                WHERE model_name = 'gex_signal_generator'
            """)
            row = cursor.fetchone()
            gex_ml_last = row[0] if row and row[0] else None
            if not gex_ml_last or (now.replace(tzinfo=None) - gex_ml_last).days > 8:
                days_since = (now.replace(tzinfo=None) - gex_ml_last).days if gex_ml_last else 999
                logger.warning(f"GEX_ML: Last trained {days_since} days ago - OVERDUE")
                recovery_needed.append(('GEX_ML', days_since))

            # Check FORTRESS_ML (weekly - should have run within 8 days)
            cursor.execute("""
                SELECT MAX(timestamp) FROM quant_training_history
                WHERE model_name = 'FORTRESS_ML' AND status = 'COMPLETED'
            """)
            row = cursor.fetchone()
            fortress_ml_last = row[0] if row and row[0] else None
            if FORTRESS_ML_AVAILABLE and (not fortress_ml_last or (now.replace(tzinfo=None) - fortress_ml_last).days > 8):
                days_since = (now.replace(tzinfo=None) - fortress_ml_last).days if fortress_ml_last else 999
                logger.warning(f"FORTRESS_ML: Last trained {days_since} days ago - OVERDUE")
                recovery_needed.append(('FORTRESS_ML', days_since))

            # Check DISCERNMENT_ML (weekly - should have run within 8 days)
            cursor.execute("""
                SELECT MAX(timestamp) FROM quant_training_history
                WHERE model_name = 'DISCERNMENT_ML' AND status = 'COMPLETED'
            """)
            row = cursor.fetchone()
            discernment_last = row[0] if row and row[0] else None
            if DISCERNMENT_ML_AVAILABLE and (not discernment_last or (now.replace(tzinfo=None) - discernment_last).days > 8):
                days_since = (now.replace(tzinfo=None) - discernment_last).days if discernment_last else 999
                logger.warning(f"DISCERNMENT_ML: Last trained {days_since} days ago - OVERDUE")
                recovery_needed.append(('DISCERNMENT_ML', days_since))

            # Check VALOR_ML (weekly - should have run within 8 days)
            cursor.execute("""
                SELECT MAX(timestamp) FROM quant_training_history
                WHERE model_name = 'VALOR_ML' AND status = 'COMPLETED'
            """)
            row = cursor.fetchone()
            valor_ml_last = row[0] if row and row[0] else None
            if VALOR_ML_AVAILABLE and (not valor_ml_last or (now.replace(tzinfo=None) - valor_ml_last).days > 8):
                days_since = (now.replace(tzinfo=None) - valor_ml_last).days if valor_ml_last else 999
                logger.warning(f"VALOR_ML: Last trained {days_since} days ago - OVERDUE")
                recovery_needed.append(('VALOR_ML', days_since))

            # Check SPX_WHEEL_ML (weekly - should have run within 8 days)
            cursor.execute("""
                SELECT MAX(timestamp) FROM quant_training_history
                WHERE model_name = 'SPX_WHEEL_ML' AND status = 'COMPLETED'
            """)
            row = cursor.fetchone()
            wheel_ml_last = row[0] if row and row[0] else None
            if SPX_WHEEL_ML_AVAILABLE and (not wheel_ml_last or (now.replace(tzinfo=None) - wheel_ml_last).days > 8):
                days_since = (now.replace(tzinfo=None) - wheel_ml_last).days if wheel_ml_last else 999
                logger.warning(f"SPX_WHEEL_ML: Last trained {days_since} days ago - OVERDUE")
                recovery_needed.append(('SPX_WHEEL_ML', days_since))

            # Check PATTERN_LEARNER (weekly - should have run within 8 days)
            cursor.execute("""
                SELECT MAX(timestamp) FROM quant_training_history
                WHERE model_name = 'PATTERN_LEARNER' AND status = 'COMPLETED'
            """)
            row = cursor.fetchone()
            pattern_last = row[0] if row and row[0] else None
            if PATTERN_LEARNER_AVAILABLE and (not pattern_last or (now.replace(tzinfo=None) - pattern_last).days > 8):
                days_since = (now.replace(tzinfo=None) - pattern_last).days if pattern_last else 999
                logger.warning(f"PATTERN_LEARNER: Last trained {days_since} days ago - OVERDUE")
                recovery_needed.append(('PATTERN_LEARNER', days_since))

            conn.close()

        except Exception as e:
            logger.warning(f"STARTUP RECOVERY: Could not check training history: {e}")
            # Continue anyway - we'll just run all training

        if not recovery_needed:
            logger.info("STARTUP RECOVERY: ✅ All ML models are fresh - no recovery needed")
            logger.info(f"=" * 80)
            return

        logger.info(f"STARTUP RECOVERY: Found {len(recovery_needed)} overdue models")

        # Run recovery training (sorted by priority - most overdue first)
        recovery_needed.sort(key=lambda x: x[1], reverse=True)

        for model_name, days_overdue in recovery_needed:
            logger.info(f"STARTUP RECOVERY: Running catch-up training for {model_name}...")

            try:
                if model_name == 'PROPHET':
                    self.scheduled_prophet_training_logic()
                elif model_name == 'WISDOM':
                    self.scheduled_wisdom_training_logic()
                elif model_name == 'GEX_DIRECTIONAL':
                    self.scheduled_quant_training_logic()
                elif model_name == 'GEX_ML':
                    self.scheduled_gex_ml_training_logic()
                elif model_name == 'FORTRESS_ML':
                    self.scheduled_fortress_ml_training_logic()
                elif model_name == 'DISCERNMENT_ML':
                    self.scheduled_discernment_ml_training_logic()
                elif model_name == 'VALOR_ML':
                    self.scheduled_valor_ml_training_logic()
                elif model_name == 'SPX_WHEEL_ML':
                    self.scheduled_spx_wheel_ml_training_logic()
                elif model_name == 'PATTERN_LEARNER':
                    self.scheduled_pattern_learner_training_logic()

                logger.info(f"STARTUP RECOVERY: ✅ {model_name} catch-up complete")

            except Exception as e:
                logger.error(f"STARTUP RECOVERY: ❌ {model_name} catch-up failed: {e}")

        logger.info(f"STARTUP RECOVERY: Complete")
        logger.info(f"=" * 80)

    def scheduled_gex_ml_training_logic(self):
        """
        GEX ML (Probability Models) - runs WEEKLY on Sunday at 6:00 PM CT

        Retrains the 5 GEX probability models used by WATCHTOWER and GLORY:
        1. Direction Probability (UP/DOWN/FLAT classification)
        2. Flip Gravity (probability of moving toward flip point)
        3. Magnet Attraction (probability of reaching magnets)
        4. Volatility Estimate (expected price range)
        5. Pin Zone Behavior (probability of staying pinned)

        Training runs after market close on Sunday to have fresh models for the week.
        Models are saved to database for persistence across deploys.

        PRODUCTION ENHANCEMENT: Now auto-populates recent training data from
        options_chain_snapshots before training to ensure fresh data.
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"GEX ML (Probability Models) triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not GEX_PROBABILITY_MODELS_AVAILABLE:
            logger.warning("GEX ML: GEXSignalGenerator not available - skipping")
            return

        try:
            # Step 1: Auto-populate recent training data from options_chain_snapshots
            logger.info("GEX ML: Populating recent training data from snapshots...")
            populate_results = populate_recent_gex_structures(days=30)

            if populate_results['success'] > 0:
                logger.info(f"  ✅ Added {populate_results['success']} new days to gex_structure_daily")
            if populate_results['skipped'] > 0:
                logger.info(f"  ℹ️  Skipped {populate_results['skipped']} days (already populated)")
            if populate_results['failed'] > 0:
                logger.warning(f"  ⚠️  Failed to process {populate_results['failed']} days")
            if populate_results['errors']:
                for err in populate_results['errors'][:3]:
                    logger.warning(f"     Error: {err}")

            # Step 2: Initialize generator for training
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
        - FORTRESS ML Advisor
        - Prophet Advisor
        - Discernment ML Engine
        - Jubilee ML
        - SPX Wheel ML
        - Market Regime Classifier
        - Pattern Learner
        - SOLOMON ML

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

    def scheduled_fortress_ml_training_logic(self):
        """
        FORTRESS ML Advisor Training - runs WEEKLY on Sunday at 7:00 PM CT

        Trains the FORTRESS ML Advisor (XGBoost classifier) on CHRONICLES
        backtest results and live trade outcomes. FORTRESS ML provides
        probability predictions used by all Iron Condor bots.

        Training order on Sundays:
        - 4:30 PM: WISDOM
        - 5:00 PM: QUANT (GEX Directional)
        - 6:00 PM: GEX ML (Probability Models)
        - 7:00 PM: FORTRESS ML (this job)
        - 7:30 PM: DISCERNMENT ML
        - 8:00 PM: VALOR ML
        - 8:30 PM: SPX WHEEL ML
        - 9:00 PM: PATTERN LEARNER
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"FORTRESS ML Training triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not FORTRESS_ML_AVAILABLE:
            logger.warning("FORTRESS ML: Advisor not available - skipping")
            return

        try:
            logger.info("FORTRESS ML: Starting weekly model training...")

            advisor = get_fortress_ml_advisor()

            # Try training from live outcomes first
            try:
                metrics = advisor.retrain_from_outcomes(min_new_samples=30)
                if metrics:
                    logger.info(f"FORTRESS ML: ✅ Trained from live outcomes")
                    logger.info(f"  Accuracy: {metrics.accuracy:.2%}")
                    logger.info(f"  AUC: {metrics.auc:.4f}" if hasattr(metrics, 'auc') else "")

                    self._save_heartbeat('FORTRESS_ML', 'TRAINING_COMPLETE', {
                        'method': 'live_outcomes',
                        'accuracy': metrics.accuracy
                    })
                    self._record_training_history(
                        model_name='FORTRESS_ML',
                        status='COMPLETED',
                        accuracy_after=metrics.accuracy * 100,
                        triggered_by='SCHEDULED'
                    )
                    logger.info(f"FORTRESS ML: Next training next Sunday at 7:00 PM CT")
                    logger.info(f"=" * 80)
                    return
            except Exception as e:
                logger.info(f"FORTRESS ML: Live outcomes training not possible: {e}")

            # Fallback: Train from CHRONICLES backtests
            try:
                from backtest.zero_dte_backtest import ZeroDTEBacktester
                backtester = ZeroDTEBacktester()
                results = backtester.get_recent_results(limit=500)

                if results and len(results) >= 30:
                    metrics = advisor.train_from_chronicles(results, min_samples=30)
                    if metrics:
                        logger.info(f"FORTRESS ML: ✅ Trained from CHRONICLES data")
                        logger.info(f"  Accuracy: {metrics.accuracy:.2%}")
                        logger.info(f"  Samples: {len(results)}")

                        self._save_heartbeat('FORTRESS_ML', 'TRAINING_COMPLETE', {
                            'method': 'chronicles',
                            'accuracy': metrics.accuracy,
                            'samples': len(results)
                        })
                        self._record_training_history(
                            model_name='FORTRESS_ML',
                            status='COMPLETED',
                            accuracy_after=metrics.accuracy * 100,
                            training_samples=len(results),
                            triggered_by='SCHEDULED'
                        )
                        logger.info(f"FORTRESS ML: Next training next Sunday at 7:00 PM CT")
                        logger.info(f"=" * 80)
                        return
                else:
                    logger.warning(f"FORTRESS ML: Not enough CHRONICLES data ({len(results) if results else 0} samples)")
            except Exception as e:
                logger.warning(f"FORTRESS ML: CHRONICLES training failed: {e}")

            logger.warning("FORTRESS ML: ⚠️ No training data available - skipping")
            self._save_heartbeat('FORTRESS_ML', 'TRAINING_SKIPPED', {'reason': 'no_data'})

        except Exception as e:
            logger.error(f"FORTRESS ML: ❌ Training failed: {e}")
            logger.error(traceback.format_exc())
            self._save_heartbeat('FORTRESS_ML', 'ERROR', {'error': str(e)})
            self._record_training_history(
                model_name='FORTRESS_ML',
                status='FAILED',
                triggered_by='SCHEDULED',
                error=str(e)
            )

        logger.info(f"FORTRESS ML: Next training next Sunday at 7:00 PM CT")
        logger.info(f"=" * 80)

    def scheduled_discernment_ml_training_logic(self):
        """
        DISCERNMENT ML Engine Training - runs WEEKLY on Sunday at 7:30 PM CT

        Trains 3 separate models (direction, magnitude, timing) from
        historical predictions with recorded outcomes. DISCERNMENT provides
        market structure analysis predictions.
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"DISCERNMENT ML Training triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not DISCERNMENT_ML_AVAILABLE:
            logger.warning("DISCERNMENT ML: Engine not available - skipping")
            return

        conn = None
        try:
            import pandas as pd

            logger.info("DISCERNMENT ML: Starting weekly model training...")

            conn = get_connection()
            cursor = conn.cursor()

            # Get training data (predictions with outcomes)
            cursor.execute('''
                SELECT
                    p.features,
                    o.actual_direction,
                    o.actual_magnitude,
                    CASE
                        WHEN ABS(o.actual_return_pct) < 0.5 THEN 'immediate'
                        WHEN ABS(o.actual_return_pct) < 1.5 THEN '1_day'
                        ELSE '3_day'
                    END as actual_timing
                FROM discernment_predictions p
                JOIN discernment_outcomes o ON p.prediction_id = o.prediction_id
                WHERE o.actual_direction IS NOT NULL
                AND o.actual_magnitude IS NOT NULL
            ''')

            rows = cursor.fetchall()
            conn.close()
            conn = None

            if len(rows) < 100:
                logger.info(f"DISCERNMENT ML: Insufficient data ({len(rows)} samples, need 100+) - skipping")
                self._save_heartbeat('DISCERNMENT_ML', 'TRAINING_SKIPPED', {
                    'reason': 'insufficient_data',
                    'samples': len(rows)
                })
                logger.info(f"DISCERNMENT ML: Next training next Sunday at 7:30 PM CT")
                logger.info(f"=" * 80)
                return

            # Prepare training dataframe
            import json as json_lib
            training_data = []
            for row in rows:
                features = json_lib.loads(row[0]) if row[0] else {}
                features['actual_direction'] = row[1]
                features['actual_magnitude'] = row[2]
                features['actual_timing'] = row[3]
                training_data.append(features)

            df = pd.DataFrame(training_data)

            # Train models
            engine = get_discernment_engine()
            engine.train_models(df)

            logger.info(f"DISCERNMENT ML: ✅ Training completed on {len(rows)} samples")

            self._save_heartbeat('DISCERNMENT_ML', 'TRAINING_COMPLETE', {
                'samples': len(rows)
            })
            self._record_training_history(
                model_name='DISCERNMENT_ML',
                status='COMPLETED',
                training_samples=len(rows),
                triggered_by='SCHEDULED'
            )

        except Exception as e:
            logger.error(f"DISCERNMENT ML: ❌ Training failed: {e}")
            logger.error(traceback.format_exc())
            self._save_heartbeat('DISCERNMENT_ML', 'ERROR', {'error': str(e)})
            self._record_training_history(
                model_name='DISCERNMENT_ML',
                status='FAILED',
                triggered_by='SCHEDULED',
                error=str(e)
            )
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

        logger.info(f"DISCERNMENT ML: Next training next Sunday at 7:30 PM CT")
        logger.info(f"=" * 80)

    def scheduled_valor_ml_training_logic(self):
        """
        VALOR ML Advisor Training - runs WEEKLY on Sunday at 8:00 PM CT

        Trains XGBoost classifier for MES futures trade win probability
        prediction. Uses scan_activity data from VALOR trades.
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"VALOR ML Training triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not VALOR_ML_AVAILABLE:
            logger.warning("VALOR ML: Advisor not available - skipping")
            return

        try:
            logger.info("VALOR ML: Starting weekly model training...")

            advisor = get_valor_ml_advisor()
            metrics = advisor.train(min_samples=50, use_new_params_only=True)

            if metrics:
                logger.info(f"VALOR ML: ✅ Training completed")
                logger.info(f"  Accuracy: {metrics.accuracy:.2%}")
                logger.info(f"  Brier Score: {metrics.brier_score:.4f}" if hasattr(metrics, 'brier_score') else "")
                logger.info(f"  Samples: {metrics.total_samples}" if hasattr(metrics, 'total_samples') else "")

                self._save_heartbeat('VALOR_ML', 'TRAINING_COMPLETE', {
                    'accuracy': metrics.accuracy,
                    'samples': getattr(metrics, 'total_samples', 0)
                })
                self._record_training_history(
                    model_name='VALOR_ML',
                    status='COMPLETED',
                    accuracy_after=metrics.accuracy * 100,
                    training_samples=getattr(metrics, 'total_samples', 0),
                    triggered_by='SCHEDULED'
                )
            else:
                logger.warning("VALOR ML: ⚠️ Training returned no metrics")
                self._save_heartbeat('VALOR_ML', 'TRAINING_SKIPPED', {'reason': 'no_metrics'})

        except ValueError as e:
            # Insufficient data is not an error - just skip
            logger.info(f"VALOR ML: {e} - skipping")
            self._save_heartbeat('VALOR_ML', 'TRAINING_SKIPPED', {'reason': str(e)})
        except Exception as e:
            logger.error(f"VALOR ML: ❌ Training failed: {e}")
            logger.error(traceback.format_exc())
            self._save_heartbeat('VALOR_ML', 'ERROR', {'error': str(e)})
            self._record_training_history(
                model_name='VALOR_ML',
                status='FAILED',
                triggered_by='SCHEDULED',
                error=str(e)
            )

        logger.info(f"VALOR ML: Next training next Sunday at 8:00 PM CT")
        logger.info(f"=" * 80)

    def scheduled_spx_wheel_ml_training_logic(self):
        """
        SPX WHEEL ML Training - runs WEEKLY on Sunday at 8:30 PM CT

        Trains RandomForest classifier for SPX put selling outcome prediction.
        Uses completed wheel trade outcomes from spx_wheel_ml_outcomes table.
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"SPX WHEEL ML Training triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not SPX_WHEEL_ML_AVAILABLE:
            logger.warning("SPX WHEEL ML: Trainer not available - skipping")
            return

        try:
            logger.info("SPX WHEEL ML: Starting weekly model training...")

            trainer = get_spx_wheel_ml_trainer()

            # Load outcomes from database
            outcomes = trainer._load_all_outcomes_from_db()

            if not outcomes or len(outcomes) < 30:
                logger.info(f"SPX WHEEL ML: Insufficient data ({len(outcomes) if outcomes else 0} samples, need 30+) - skipping")
                self._save_heartbeat('SPX_WHEEL_ML', 'TRAINING_SKIPPED', {
                    'reason': 'insufficient_data',
                    'samples': len(outcomes) if outcomes else 0
                })
                logger.info(f"SPX WHEEL ML: Next training next Sunday at 8:30 PM CT")
                logger.info(f"=" * 80)
                return

            result = trainer.train(outcomes, min_samples=30)

            if result.get('error'):
                logger.warning(f"SPX WHEEL ML: ⚠️ {result['error']}")
                self._save_heartbeat('SPX_WHEEL_ML', 'TRAINING_SKIPPED', result)
            else:
                accuracy = result.get('accuracy', 0)
                samples = result.get('samples', len(outcomes))
                logger.info(f"SPX WHEEL ML: ✅ Training completed")
                logger.info(f"  Accuracy: {accuracy:.2%}")
                logger.info(f"  Samples: {samples}")

                self._save_heartbeat('SPX_WHEEL_ML', 'TRAINING_COMPLETE', result)
                self._record_training_history(
                    model_name='SPX_WHEEL_ML',
                    status='COMPLETED',
                    accuracy_after=accuracy * 100,
                    training_samples=samples,
                    triggered_by='SCHEDULED'
                )

        except Exception as e:
            logger.error(f"SPX WHEEL ML: ❌ Training failed: {e}")
            logger.error(traceback.format_exc())
            self._save_heartbeat('SPX_WHEEL_ML', 'ERROR', {'error': str(e)})
            self._record_training_history(
                model_name='SPX_WHEEL_ML',
                status='FAILED',
                triggered_by='SCHEDULED',
                error=str(e)
            )

        logger.info(f"SPX WHEEL ML: Next training next Sunday at 8:30 PM CT")
        logger.info(f"=" * 80)

    def scheduled_pattern_learner_training_logic(self):
        """
        PATTERN LEARNER Training - runs WEEKLY on Sunday at 9:00 PM CT

        Trains RandomForest classifier for pattern success/failure prediction.
        Learns from historical pattern data to improve detection accuracy.
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"PATTERN LEARNER Training triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not PATTERN_LEARNER_AVAILABLE:
            logger.warning("PATTERN LEARNER: Not available - skipping")
            return

        try:
            logger.info("PATTERN LEARNER: Starting weekly model training...")

            learner = PatternLearner()
            result = learner.train_pattern_classifier(lookback_days=180)

            if result.get('error'):
                logger.info(f"PATTERN LEARNER: {result['error']} - skipping")
                self._save_heartbeat('PATTERN_LEARNER', 'TRAINING_SKIPPED', result)
            elif result.get('trained'):
                accuracy = result.get('accuracy', 0)
                samples = result.get('samples', 0)
                logger.info(f"PATTERN LEARNER: ✅ Training completed")
                logger.info(f"  Accuracy: {accuracy:.2%}")
                logger.info(f"  Samples: {samples}")
                logger.info(f"  Top features: {result.get('top_features', [])[:5]}")

                self._save_heartbeat('PATTERN_LEARNER', 'TRAINING_COMPLETE', result)
                self._record_training_history(
                    model_name='PATTERN_LEARNER',
                    status='COMPLETED',
                    accuracy_after=accuracy * 100,
                    training_samples=samples,
                    triggered_by='SCHEDULED'
                )
            else:
                logger.warning("PATTERN LEARNER: ⚠️ Training returned unexpected result")
                self._save_heartbeat('PATTERN_LEARNER', 'TRAINING_SKIPPED', result)

        except Exception as e:
            logger.error(f"PATTERN LEARNER: ❌ Training failed: {e}")
            logger.error(traceback.format_exc())
            self._save_heartbeat('PATTERN_LEARNER', 'ERROR', {'error': str(e)})
            self._record_training_history(
                model_name='PATTERN_LEARNER',
                status='FAILED',
                triggered_by='SCHEDULED',
                error=str(e)
            )

        logger.info(f"PATTERN LEARNER: Next training next Sunday at 9:00 PM CT")
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

        # Also update model metadata on successful training
        if status == 'COMPLETED' and accuracy_after is not None:
            self._update_model_metadata(
                model_name=model_name,
                accuracy=accuracy_after,
                training_samples=training_samples
            )

    def _update_model_metadata(self, model_name: str, accuracy: float = None,
                               training_samples: int = None, feature_importance: dict = None,
                               hyperparameters: dict = None, model_type: str = None):
        """Update ml_model_metadata table with currently deployed model info.

        This tracks the active/deployed version of each ML model.
        Called after successful training completion.
        """
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Generate version string
            from datetime import datetime
            version = datetime.now().strftime('%Y%m%d_%H%M%S')

            # First, ensure table exists (create if not)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ml_model_metadata (
                    id SERIAL PRIMARY KEY,
                    model_name VARCHAR(50) NOT NULL,
                    model_version VARCHAR(50),
                    trained_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    training_samples INTEGER,
                    accuracy DECIMAL(5,4),
                    feature_importance JSONB,
                    hyperparameters JSONB,
                    model_type VARCHAR(50),
                    is_active BOOLEAN DEFAULT TRUE,
                    deployed_at TIMESTAMPTZ DEFAULT NOW(),
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    notes TEXT
                )
            """)

            # Deactivate existing active model for this name
            cursor.execute("""
                UPDATE ml_model_metadata
                SET is_active = FALSE
                WHERE model_name = %s AND is_active = TRUE
            """, (model_name,))

            # Insert new active model record
            import json
            feature_json = json.dumps(feature_importance) if feature_importance else None
            hyper_json = json.dumps(hyperparameters) if hyperparameters else None

            cursor.execute("""
                INSERT INTO ml_model_metadata (
                    model_name, model_version, trained_at, training_samples,
                    accuracy, feature_importance, hyperparameters, model_type,
                    is_active, deployed_at
                ) VALUES (%s, %s, NOW(), %s, %s, %s, %s, %s, TRUE, NOW())
            """, (model_name, version, training_samples, accuracy,
                  feature_json, hyper_json, model_type or 'XGBoost'))

            conn.commit()
            cursor.close()
            logger.info(f"ML_MODEL_METADATA: Updated {model_name} v{version}, accuracy={accuracy}")
        except Exception as e:
            logger.error(f"Failed to update model metadata for {model_name}: {e}")
        finally:
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
        - FORTRESS, SOLOMON, ANCHOR, SAMSON, GIDEON

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
                'fortress': ('fortress_positions', 'fortress_equity_snapshots', 'fortress_starting_capital', 100000, 'fortress_trader'),
                'solomon': ('solomon_positions', 'solomon_equity_snapshots', 'solomon_starting_capital', 100000, 'solomon_trader'),
                'samson': ('samson_positions', 'samson_equity_snapshots', 'samson_starting_capital', 200000, 'samson_trader'),
                'anchor': ('anchor_positions', 'anchor_equity_snapshots', 'anchor_starting_capital', 200000, 'anchor_trader'),
                'gideon': ('gideon_positions', 'gideon_equity_snapshots', 'gideon_starting_capital', 100000, 'gideon_trader'),
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
                        # Include partial_close - positions where one leg closed but other failed
                        cursor.execute(f"""
                            SELECT COALESCE(SUM(realized_pnl), 0)
                            FROM {pos_table}
                            WHERE status IN ('closed', 'expired', 'partial_close')
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
                            # Iron Condor bots: FORTRESS, SAMSON, ANCHOR
                            if bot_name in ['fortress', 'samson', 'anchor']:
                                # Query IC positions with all MTM fields
                                underlying = 'SPY' if bot_name == 'fortress' else 'SPX'
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

                            # Directional spread bots: SOLOMON, GIDEON
                            elif bot_name in ['solomon', 'gideon']:
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
                        except Exception as col_err:
                            logger.warning(f"EQUITY_SNAPSHOTS: {bot_name.upper()} failed to add {col} column: {col_err}")

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

    def scheduled_bot_reports_logic(self):
        """
        BOT REPORTS - runs daily at 3:15 PM CT after market close

        Generates end-of-day analysis reports for all trading bots:
        - FORTRESS, SOLOMON, ANCHOR, SAMSON, GIDEON

        Reports include:
        - Trade-by-trade analysis with timestamps
        - Yahoo Finance intraday tick data
        - Claude AI analysis explaining WHY trades won/lost
        - Daily summary with lessons learned

        Reports are saved to {bot}_daily_reports tables for archive access.
        """
        now = datetime.now(CENTRAL_TZ)

        # Only run on weekdays
        if now.weekday() >= 5:  # Saturday = 5, Sunday = 6
            logger.info(f"BOT_REPORTS: Weekend, skipping report generation at {now.strftime('%H:%M:%S')}")
            return

        logger.info(f"BOT_REPORTS: Starting end-of-day report generation at {now.strftime('%H:%M:%S')}")

        try:
            # Import the report generator
            from backend.services.bot_report_generator import generate_report_for_bot

            bots = ['fortress', 'solomon', 'samson', 'anchor', 'gideon']
            reports_generated = 0
            reports_failed = 0

            for bot_name in bots:
                try:
                    logger.info(f"BOT_REPORTS: Generating report for {bot_name.upper()}...")

                    # Generate the report (saves to archive internally)
                    # Always produces a report even on 0-trade days
                    report = generate_report_for_bot(bot_name, now.date())

                    trade_count = report.get('trade_count', 0)
                    total_pnl = report.get('total_pnl', 0)
                    if trade_count > 0:
                        logger.info(f"BOT_REPORTS: {bot_name.upper()} report saved - {trade_count} trades, P&L: ${total_pnl:.2f}")
                    else:
                        logger.info(f"BOT_REPORTS: {bot_name.upper()} report saved - no trades today (summary-only)")
                    reports_generated += 1

                except Exception as e:
                    logger.error(f"BOT_REPORTS: {bot_name.upper()} report failed: {e}")
                    import traceback
                    traceback.print_exc()
                    reports_failed += 1
                    continue

            logger.info(f"BOT_REPORTS: Complete - {reports_generated} reports generated, {reports_failed} failed")

        except ImportError as e:
            logger.error(f"BOT_REPORTS: Failed to import report generator: {e}")
        except Exception as e:
            logger.error(f"BOT_REPORTS: Unexpected error: {e}")
            import traceback
            traceback.print_exc()

    def scheduled_reports_purge_logic(self):
        """
        REPORTS PURGE - runs weekly on Sunday at 6:30 PM CT

        Cleans up old reports older than 5 years to manage storage.
        """
        now = datetime.now(CENTRAL_TZ)
        logger.info(f"REPORTS_PURGE: Starting purge of reports older than 5 years at {now.strftime('%H:%M:%S')}")

        try:
            from backend.services.bot_report_generator import purge_old_reports

            # purge_old_reports handles all bots at once with days_to_keep parameter
            # 5 years = 5 * 365 = 1825 days
            results = purge_old_reports(days_to_keep=5 * 365)

            total_deleted = sum(results.values()) if results else 0
            for bot_name, deleted in results.items():
                if deleted > 0:
                    logger.info(f"REPORTS_PURGE: {bot_name.upper()} - purged {deleted} old reports")

            logger.info(f"REPORTS_PURGE: Complete - {total_deleted} total reports purged")

        except ImportError as e:
            logger.error(f"REPORTS_PURGE: Failed to import purge function: {e}")
        except Exception as e:
            logger.error(f"REPORTS_PURGE: Unexpected error: {e}")
            import traceback
            traceback.print_exc()

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
        logger.info(f"Bots: LAZARUS, CORNERSTONE, FORTRESS (SPY IC), ANCHOR (SPX IC), SOLOMON, WATCHTOWER, VIX_SIGNAL, PROVERBS, QUANT")
        logger.info(f"Timezone: America/Chicago (Texas Central Time)")
        logger.info(f"LAZARUS Schedule: DISABLED here - handled by AutonomousTrader (every 5 min)")
        logger.info(f"CORNERSTONE Schedule: Daily at 9:05 AM CT, Mon-Fri")
        logger.info(f"FORTRESS Schedule: Every 5 min (runs 24/7, market hours checked internally)")
        logger.info(f"ANCHOR Schedule: Every 5 min (runs 24/7, market hours checked internally)")
        logger.info(f"SOLOMON Schedule: Every 5 min (runs 24/7, market hours checked internally)")
        logger.info(f"GIDEON Schedule: Every 5 min (runs 24/7, market hours checked internally)")
        logger.info(f"SAMSON Schedule: Every 5 min (runs 24/7, market hours checked internally)")
        logger.info(f"WATCHTOWER Schedule: Every 5 min (runs 24/7, market hours checked internally)")
        logger.info(f"VIX_SIGNAL Schedule: HOURLY (9 AM - 3 PM CT), Hedge Signal Generation")
        logger.info(f"PROVERBS Schedule: DAILY at 4:00 PM CT (after market close)")
        logger.info(f"QUANT Schedule: WEEKLY on Sunday at 5:00 PM CT (ML model training)")
        logger.info(f"EQUITY_SNAPSHOTS Schedule: Every 5 min (runs 24/7, market hours checked internally)")
        logger.info(f"BOT_REPORTS Schedule: DAILY at 3:15 PM CT (end-of-day analysis reports)")
        logger.info(f"REPORTS_PURGE Schedule: WEEKLY on Sunday at 6:30 PM CT (5-year retention cleanup)")
        logger.info(f"Log file: {LOG_FILE}")
        logger.info("=" * 80)

        # Create scheduler with Central Texas timezone
        self.scheduler = BackgroundScheduler(timezone='America/Chicago')

        # =================================================================
        # LAZARUS JOB: DISABLED - Handled by AutonomousTrader (every 5 min)
        # =================================================================
        # NOTE: LAZARUS is run via the AutonomousTrader watchdog thread which
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
        #     id='lazarus_trading',
        #     name='LAZARUS - 0DTE Options Trading',
        #     replace_existing=True
        # )
        logger.info("⚠️ LAZARUS job DISABLED here - handled by AutonomousTrader (every 5 min)")

        # =================================================================
        # CORNERSTONE JOB: SPX Wheel - runs once daily at 9:05 AM CT
        # =================================================================
        if self.cornerstone_trader:
            self.scheduler.add_job(
                self.scheduled_cornerstone_logic,
                trigger=CronTrigger(
                    hour=9,        # 9:00 AM CT - after market settles
                    minute=5,      # 9:05 AM CT to avoid conflict with LAZARUS
                    day_of_week='mon-fri',
                    timezone='America/Chicago'
                ),
                id='cornerstone_trading',
                name='CORNERSTONE - SPX Wheel Trading',
                replace_existing=True
            )
            logger.info("✅ CORNERSTONE job scheduled (9:05 AM CT daily)")
        else:
            logger.warning("⚠️ CORNERSTONE not available - wheel trading disabled")

        # =================================================================
        # FORTRESS JOB: Aggressive Iron Condor - runs every 5 minutes
        # Scans continuously for optimal 0DTE Iron Condor entry timing
        # Jobs run immediately on startup and every 5 min thereafter.
        # Market hours are checked inside the job (saves BEFORE_WINDOW heartbeat if early).
        # =================================================================
        if self.fortress_trader:
            self.scheduler.add_job(
                self.scheduled_fortress_logic,
                trigger=IntervalTrigger(
                    minutes=5,
                    timezone='America/Chicago'
                ),
                id='fortress_trading',
                name='FORTRESS - Aggressive Iron Condor (5-min intervals)',
                replace_existing=True
            )
            logger.info("✅ FORTRESS job scheduled (every 5 min, checks market hours internally)")

            # =================================================================
            # FORTRESS EOD JOB: Process expired positions - runs at 3:01 PM CT
            # All EOD jobs run at 3:01 PM CT for fast reconciliation (<5 min post-close)
            # =================================================================
            self.scheduler.add_job(
                self.scheduled_fortress_eod_logic,
                trigger=CronTrigger(
                    hour=15,       # 3:00 PM CT - after market close
                    minute=1,      # 3:01 PM CT - immediate post-close reconciliation
                    day_of_week='mon-fri',
                    timezone='America/Chicago'
                ),
                id='fortress_eod',
                name='FORTRESS - EOD Position Expiration',
                replace_existing=True
            )
            logger.info("✅ FORTRESS EOD job scheduled (3:01 PM CT daily)")

            # =================================================================
            # FORTRESS FRIDAY CLOSE-ALL: Safety net to ensure NO positions survive weekend
            # Runs at 2:55 PM CT on Fridays only. The regular 5-min cycle handles
            # force-close at 2:50 PM, but this is a dedicated backup to catch any
            # positions that slipped through (pricing failures, retries, etc).
            # =================================================================
            self.scheduler.add_job(
                self.scheduled_fortress_friday_close_all,
                trigger=CronTrigger(
                    hour=14,       # 2:00 PM CT
                    minute=55,     # 2:55 PM CT - 5 min before market close
                    day_of_week='fri',
                    timezone='America/Chicago'
                ),
                id='fortress_friday_close',
                name='FORTRESS - Friday Close All (No Weekend Holds)',
                replace_existing=True
            )
            logger.info("✅ FORTRESS Friday close-all job scheduled (2:55 PM CT Fridays)")
        else:
            logger.warning("⚠️ FORTRESS not available - aggressive IC trading disabled")

        # =================================================================
        # SOLOMON JOB: GEX Directional Spreads - runs every 5 minutes
        # Uses live Tradier GEX data to find intraday opportunities
        # Jobs run immediately on startup and every 5 min thereafter.
        # Market hours are checked inside the job (saves BEFORE_WINDOW heartbeat if early).
        # =================================================================
        if self.solomon_trader:
            self.scheduler.add_job(
                self.scheduled_solomon_logic,
                trigger=IntervalTrigger(
                    minutes=5,
                    timezone='America/Chicago'
                ),
                id='solomon_trading',
                name='SOLOMON - GEX Directional Spreads (5-min intervals)',
                replace_existing=True
            )
            logger.info("✅ SOLOMON job scheduled (every 5 min, checks market hours internally)")

            # =================================================================
            # SOLOMON EOD JOB: Process expired positions - runs at 3:01 PM CT
            # All EOD jobs run at 3:01 PM CT for fast reconciliation (<5 min post-close)
            # =================================================================
            self.scheduler.add_job(
                self.scheduled_solomon_eod_logic,
                trigger=CronTrigger(
                    hour=15,       # 3:00 PM CT - after market close
                    minute=1,      # 3:01 PM CT - immediate post-close reconciliation
                    day_of_week='mon-fri',
                    timezone='America/Chicago'
                ),
                id='solomon_eod',
                name='SOLOMON - EOD Position Expiration',
                replace_existing=True
            )
            logger.info("✅ SOLOMON EOD job scheduled (3:01 PM CT daily)")
        else:
            logger.warning("⚠️ SOLOMON not available - GEX directional trading disabled")

        # =================================================================
        # ANCHOR JOB: SPX Iron Condors - runs every 5 minutes
        # Trades SPX options with $10 spread widths using SPXW symbols
        # Jobs run immediately on startup and every 5 min thereafter.
        # Market hours are checked inside the job (saves BEFORE_WINDOW heartbeat if early).
        # =================================================================
        if self.anchor_trader:
            self.scheduler.add_job(
                self.scheduled_anchor_logic,
                trigger=IntervalTrigger(
                    minutes=5,
                    timezone='America/Chicago'
                ),
                id='anchor_trading',
                name='ANCHOR - SPX Iron Condor (5-min intervals)',
                replace_existing=True
            )
            logger.info("✅ ANCHOR job scheduled (every 5 min, checks market hours internally)")

            # =================================================================
            # ANCHOR EOD JOB: Process expired positions - runs at 3:01 PM CT
            # All EOD jobs run at 3:01 PM CT for fast reconciliation (<5 min post-close)
            # =================================================================
            self.scheduler.add_job(
                self.scheduled_anchor_eod_logic,
                trigger=CronTrigger(
                    hour=15,       # 3:00 PM CT - after market close
                    minute=1,      # 3:01 PM CT - immediate post-close reconciliation
                    day_of_week='mon-fri',
                    timezone='America/Chicago'
                ),
                id='anchor_eod',
                name='ANCHOR - EOD Position Expiration',
                replace_existing=True
            )
            logger.info("✅ ANCHOR EOD job scheduled (3:01 PM CT daily)")
        else:
            logger.warning("⚠️ ANCHOR not available - SPX IC trading disabled")

        # =================================================================
        # GIDEON JOB: Aggressive Directional Spreads - runs every 5 minutes
        # Uses relaxed GEX filters for more aggressive trading
        # Jobs run immediately on startup and every 5 min thereafter.
        # Market hours are checked inside the job (saves BEFORE_WINDOW heartbeat if early).
        # =================================================================
        if self.gideon_trader:
            self.scheduler.add_job(
                self.scheduled_gideon_logic,
                trigger=IntervalTrigger(
                    minutes=5,
                    timezone='America/Chicago'
                ),
                id='gideon_trading',
                name='GIDEON - Aggressive Directional Spreads (5-min intervals)',
                replace_existing=True
            )
            logger.info("✅ GIDEON job scheduled (every 5 min, checks market hours internally)")

            # =================================================================
            # GIDEON EOD JOB: Process expired positions - runs at 3:01 PM CT
            # All EOD jobs run at 3:01 PM CT for fast reconciliation (<5 min post-close)
            # =================================================================
            self.scheduler.add_job(
                self.scheduled_gideon_eod_logic,
                trigger=CronTrigger(
                    hour=15,       # 3:00 PM CT - after market close
                    minute=1,      # 3:01 PM CT - immediate post-close reconciliation
                    day_of_week='mon-fri',
                    timezone='America/Chicago'
                ),
                id='gideon_eod',
                name='GIDEON - EOD Position Expiration',
                replace_existing=True
            )
            logger.info("✅ GIDEON EOD job scheduled (3:01 PM CT daily)")
        else:
            logger.warning("⚠️ GIDEON not available - aggressive directional trading disabled")

        # =================================================================
        # SAMSON JOB: Aggressive SPX Iron Condors - runs every 5 minutes
        # Trades SPX options with $12 spread widths, multiple trades per day with cooldown
        # Jobs run immediately on startup and every 5 min thereafter.
        # Market hours are checked inside the job (saves BEFORE_WINDOW heartbeat if early).
        # =================================================================
        if self.samson_trader:
            self.scheduler.add_job(
                self.scheduled_samson_logic,
                trigger=IntervalTrigger(
                    minutes=5,
                    timezone='America/Chicago'
                ),
                id='samson_trading',
                name='SAMSON - Aggressive SPX Iron Condor (5-min intervals)',
                replace_existing=True
            )
            logger.info("✅ SAMSON job scheduled (every 5 min, checks market hours internally)")

            # =================================================================
            # SAMSON EOD JOB: Process expired positions - runs at 3:01 PM CT
            # All EOD jobs run at 3:01 PM CT for fast reconciliation (<5 min post-close)
            # =================================================================
            self.scheduler.add_job(
                self.scheduled_samson_eod_logic,
                trigger=CronTrigger(
                    hour=15,       # 3:00 PM CT - after market close
                    minute=1,      # 3:01 PM CT - immediate post-close reconciliation
                    day_of_week='mon-fri',
                    timezone='America/Chicago'
                ),
                id='samson_eod',
                name='SAMSON - EOD Position Expiration',
                replace_existing=True
            )
            logger.info("✅ SAMSON EOD job scheduled (3:01 PM CT daily)")
        else:
            logger.warning("⚠️ SAMSON not available - aggressive SPX IC trading disabled")

        # =================================================================
        # FAITH JOB: 2DTE Paper Iron Condor - runs every 5 minutes
        # Paper-only bot with real Tradier data, $5K simulated capital
        # Market hours are checked inside the job (FAITH's run_cycle handles it)
        # =================================================================
        if self.faith_trader:
            self.scheduler.add_job(
                self.scheduled_faith_logic,
                trigger=IntervalTrigger(
                    minutes=5,
                    timezone='America/Chicago'
                ),
                id='faith_trading',
                name='FAITH - 2DTE Paper Iron Condor (5-min intervals)',
                replace_existing=True
            )
            logger.info("✅ FAITH job scheduled (every 5 min, checks market hours internally)")

            # =================================================================
            # FAITH EOD JOB: Safety net close - runs at 3:50 PM CT
            # FAITH's EOD cutoff is 3:45 PM ET (2:45 PM CT). The 5-min cycle
            # handles it, but this is a safety net at 3:50 PM CT.
            # =================================================================
            self.scheduler.add_job(
                self.scheduled_faith_eod_logic,
                trigger=CronTrigger(
                    hour=15,       # 3:00 PM CT
                    minute=50,     # 3:50 PM CT - safety net after EOD cutoff
                    day_of_week='mon-fri',
                    timezone='America/Chicago'
                ),
                id='faith_eod',
                name='FAITH - EOD Safety Net Close',
                replace_existing=True
            )
            logger.info("✅ FAITH EOD job scheduled (3:50 PM CT daily)")

        if not self.faith_trader:
            logger.warning("⚠️ FAITH not available - 2DTE paper IC trading disabled")

        # =================================================================
        # GRACE JOB: 1DTE Paper Iron Condor - separate bot for comparison
        # Same schedule as FAITH but completely separate bot with own tables
        # =================================================================
        if self.grace_trader:
            self.scheduler.add_job(
                self.scheduled_grace_logic,
                trigger=IntervalTrigger(
                    minutes=5,
                    timezone='America/Chicago'
                ),
                id='grace_trading',
                name='GRACE - 1DTE Paper Iron Condor (5-min intervals)',
                replace_existing=True
            )
            logger.info("✅ GRACE job scheduled (every 5 min, checks market hours internally)")

            self.scheduler.add_job(
                self.scheduled_grace_eod_logic,
                trigger=CronTrigger(
                    hour=15,
                    minute=50,
                    day_of_week='mon-fri',
                    timezone='America/Chicago'
                ),
                id='grace_eod',
                name='GRACE - EOD Safety Net Close',
                replace_existing=True
            )
            logger.info("✅ GRACE EOD job scheduled (3:50 PM CT daily)")
        else:
            logger.warning("⚠️ GRACE not available - 1DTE paper IC comparison disabled")

        # =================================================================
        # VALOR JOB: MES Futures Scalping - runs every 1 minute (24/5)
        # Trades MES futures using GEX signals for mean reversion / momentum
        # Futures trade nearly 24/5 (Sun 5pm - Fri 4pm CT with 4-5pm daily break)
        # Jobs run on startup and every 1 min thereafter.
        # Market hours checked inside the job.
        # =================================================================
        if self.valor_trader:
            self.scheduler.add_job(
                self.scheduled_valor_logic,
                trigger=IntervalTrigger(
                    minutes=1,
                    timezone='America/Chicago'
                ),
                id='valor_trading',
                name='VALOR - MES Futures Scalping (1-min intervals)',
                replace_existing=True
            )
            logger.info("✅ VALOR job scheduled (every 1 min, checks futures hours internally)")

            # =================================================================
            # VALOR POSITION MONITOR: Fast stop/target checking (every 15 sec)
            # Reduces stop slippage by checking positions more frequently
            # Does NOT generate new signals - only monitors existing positions
            # =================================================================
            self.scheduler.add_job(
                self.scheduled_valor_position_monitor,
                trigger=IntervalTrigger(
                    seconds=15,
                    timezone='America/Chicago'
                ),
                id='valor_position_monitor',
                name='VALOR - Position Monitor (15-sec intervals)',
                replace_existing=True
            )
            logger.info("✅ VALOR position monitor scheduled (every 15 sec)")

            # =================================================================
            # VALOR EOD JOB: Daily maintenance break - runs at 4:00 PM CT
            # Futures have a daily maintenance break from 4-5pm CT
            # =================================================================
            self.scheduler.add_job(
                self.scheduled_valor_eod_logic,
                trigger=CronTrigger(
                    hour=16,       # 4:00 PM CT - futures daily maintenance break
                    minute=0,
                    day_of_week='mon-fri',
                    timezone='America/Chicago'
                ),
                id='valor_eod',
                name='VALOR - Daily Maintenance Break Summary',
                replace_existing=True
            )
            logger.info("✅ VALOR EOD job scheduled (4:00 PM CT daily)")
        else:
            logger.warning("⚠️ VALOR not available - MES futures trading disabled")

        # =================================================================
        # AGAPE JOB: ETH Micro Futures - runs every 5 minutes
        # Crypto trades nearly 24/7 (CME: Sun 5PM - Fri 4PM CT)
        # Uses Deribit GEX as primary signal source
        # =================================================================
        if self.agape_trader:
            self.scheduler.add_job(
                self.scheduled_agape_logic,
                trigger=IntervalTrigger(
                    minutes=5,
                    timezone='America/Chicago'
                ),
                id='agape_trading',
                name='AGAPE - ETH Micro Futures (5-min intervals)',
                replace_existing=True
            )
            logger.info("✅ AGAPE job scheduled (every 5 min, checks CME crypto hours internally)")

            self.scheduler.add_job(
                self.scheduled_agape_eod_logic,
                trigger=CronTrigger(
                    hour=15,
                    minute=45,
                    day_of_week='mon-fri',
                    timezone='America/Chicago'
                ),
                id='agape_eod',
                name='AGAPE - Force Close Before CME Maintenance',
                replace_existing=True
            )
            logger.info("✅ AGAPE EOD job scheduled (3:45 PM CT daily)")
        else:
            logger.warning("⚠️ AGAPE not available - ETH crypto trading disabled")

        # =================================================================
        # AGAPE-SPOT JOB: 24/7 Coinbase Spot Multi-Coin - every 1 minute
        # Trades around the clock, no market hours restrictions
        # Faster scans = tighter trailing stops + quicker signal detection
        # =================================================================
        if self.agape_spot_trader:
            self.scheduler.add_job(
                self.scheduled_agape_spot_logic,
                trigger=IntervalTrigger(
                    minutes=1,
                    timezone='America/Chicago'
                ),
                id='agape_spot_trading',
                name='AGAPE-SPOT - 24/7 Coinbase Spot Multi-Coin (1-min intervals)',
                replace_existing=True
            )
            logger.info("✅ AGAPE-SPOT job scheduled (every 1 min, 24/7)")
        else:
            logger.warning("⚠️ AGAPE-SPOT not available - 24/7 spot ETH trading disabled")

        # =================================================================
        # AGAPE-BTC JOB: BTC Micro Futures (/MBT) - every 5 minutes
        # Crypto trades nearly 24/7 (CME: Sun 5PM - Fri 4PM CT)
        # =================================================================
        if self.agape_btc_trader:
            self.scheduler.add_job(
                self.scheduled_agape_btc_logic,
                trigger=IntervalTrigger(
                    minutes=5,
                    timezone='America/Chicago'
                ),
                id='agape_btc_trading',
                name='AGAPE-BTC - BTC Micro Futures (5-min intervals)',
                replace_existing=True
            )
            logger.info("✅ AGAPE-BTC job scheduled (every 5 min, checks CME crypto hours internally)")

            self.scheduler.add_job(
                self.scheduled_agape_btc_eod_logic,
                trigger=CronTrigger(
                    hour=15,
                    minute=45,
                    day_of_week='mon-fri',
                    timezone='America/Chicago'
                ),
                id='agape_btc_eod',
                name='AGAPE-BTC - Force Close Before CME Maintenance',
                replace_existing=True
            )
            logger.info("✅ AGAPE-BTC EOD job scheduled (3:45 PM CT daily)")
        else:
            logger.warning("⚠️ AGAPE-BTC not available - BTC crypto trading disabled")

        # =================================================================
        # AGAPE-XRP JOB: XRP Futures (/XRP) - every 5 minutes
        # Crypto trades nearly 24/7 (CME: Sun 5PM - Fri 4PM CT)
        # =================================================================
        if self.agape_xrp_trader:
            self.scheduler.add_job(
                self.scheduled_agape_xrp_logic,
                trigger=IntervalTrigger(
                    minutes=5,
                    timezone='America/Chicago'
                ),
                id='agape_xrp_trading',
                name='AGAPE-XRP - XRP Futures (5-min intervals)',
                replace_existing=True
            )
            logger.info("✅ AGAPE-XRP job scheduled (every 5 min, checks CME crypto hours internally)")

            self.scheduler.add_job(
                self.scheduled_agape_xrp_eod_logic,
                trigger=CronTrigger(
                    hour=15,
                    minute=45,
                    day_of_week='mon-fri',
                    timezone='America/Chicago'
                ),
                id='agape_xrp_eod',
                name='AGAPE-XRP - Force Close Before CME Maintenance',
                replace_existing=True
            )
            logger.info("✅ AGAPE-XRP EOD job scheduled (3:45 PM CT daily)")
        else:
            logger.warning("⚠️ AGAPE-XRP not available - XRP crypto trading disabled")

        # =================================================================
        # AGAPE-ETH-PERP JOB: ETH Perpetual Contract - every 5 minutes, 24/7
        # Perpetual contracts trade around the clock on crypto exchanges
        # Uses real Deribit/CoinGlass/Coinbase data
        # =================================================================
        if self.agape_eth_perp_trader:
            self.scheduler.add_job(
                self.scheduled_agape_eth_perp_logic,
                trigger=IntervalTrigger(
                    minutes=5,
                    timezone='America/Chicago'
                ),
                id='agape_eth_perp_trading',
                name='AGAPE-ETH-PERP - ETH Perpetual (5-min intervals, 24/7)',
                replace_existing=True
            )
            logger.info("✅ AGAPE-ETH-PERP job scheduled (every 5 min, 24/7)")

            self.scheduler.add_job(
                self.scheduled_agape_eth_perp_eod_logic,
                trigger=CronTrigger(
                    hour=15,
                    minute=45,
                    day_of_week='mon-fri',
                    timezone='America/Chicago'
                ),
                id='agape_eth_perp_eod',
                name='AGAPE-ETH-PERP - Daily Summary',
                replace_existing=True
            )
            logger.info("✅ AGAPE-ETH-PERP EOD job scheduled (3:45 PM CT daily)")
        else:
            logger.warning("⚠️ AGAPE-ETH-PERP not available - ETH perpetual trading disabled")

        # =================================================================
        # AGAPE-BTC-PERP JOB: BTC Perpetual Contract - every 5 minutes, 24/7
        # =================================================================
        if self.agape_btc_perp_trader:
            self.scheduler.add_job(
                self.scheduled_agape_btc_perp_logic,
                trigger=IntervalTrigger(
                    minutes=5,
                    timezone='America/Chicago'
                ),
                id='agape_btc_perp_trading',
                name='AGAPE-BTC-PERP - BTC Perpetual (5-min intervals, 24/7)',
                replace_existing=True
            )
            logger.info("✅ AGAPE-BTC-PERP job scheduled (every 5 min, 24/7)")

            self.scheduler.add_job(
                self.scheduled_agape_btc_perp_eod_logic,
                trigger=CronTrigger(
                    hour=15,
                    minute=45,
                    day_of_week='mon-fri',
                    timezone='America/Chicago'
                ),
                id='agape_btc_perp_eod',
                name='AGAPE-BTC-PERP - Daily Summary',
                replace_existing=True
            )
            logger.info("✅ AGAPE-BTC-PERP EOD job scheduled (3:45 PM CT daily)")
        else:
            logger.warning("⚠️ AGAPE-BTC-PERP not available - BTC perpetual trading disabled")

        # =================================================================
        # AGAPE-XRP-PERP JOB: XRP Perpetual Contract - every 5 minutes, 24/7
        # =================================================================
        if self.agape_xrp_perp_trader:
            self.scheduler.add_job(
                self.scheduled_agape_xrp_perp_logic,
                trigger=IntervalTrigger(
                    minutes=5,
                    timezone='America/Chicago'
                ),
                id='agape_xrp_perp_trading',
                name='AGAPE-XRP-PERP - XRP Perpetual (5-min intervals, 24/7)',
                replace_existing=True
            )
            logger.info("✅ AGAPE-XRP-PERP job scheduled (every 5 min, 24/7)")

            self.scheduler.add_job(
                self.scheduled_agape_xrp_perp_eod_logic,
                trigger=CronTrigger(
                    hour=15,
                    minute=45,
                    day_of_week='mon-fri',
                    timezone='America/Chicago'
                ),
                id='agape_xrp_perp_eod',
                name='AGAPE-XRP-PERP - Daily Summary',
                replace_existing=True
            )
            logger.info("✅ AGAPE-XRP-PERP EOD job scheduled (3:45 PM CT daily)")
        else:
            logger.warning("⚠️ AGAPE-XRP-PERP not available - XRP perpetual trading disabled")

        # =================================================================
        # AGAPE-DOGE-PERP JOB: DOGE Perpetual Contract - every 5 minutes, 24/7
        # =================================================================
        if self.agape_doge_perp_trader:
            self.scheduler.add_job(
                self.scheduled_agape_doge_perp_logic,
                trigger=IntervalTrigger(
                    minutes=5,
                    timezone='America/Chicago'
                ),
                id='agape_doge_perp_trading',
                name='AGAPE-DOGE-PERP - DOGE Perpetual (5-min intervals, 24/7)',
                replace_existing=True
            )
            logger.info("✅ AGAPE-DOGE-PERP job scheduled (every 5 min, 24/7)")

            self.scheduler.add_job(
                self.scheduled_agape_doge_perp_eod_logic,
                trigger=CronTrigger(
                    hour=15,
                    minute=45,
                    day_of_week='mon-fri',
                    timezone='America/Chicago'
                ),
                id='agape_doge_perp_eod',
                name='AGAPE-DOGE-PERP - Daily Summary',
                replace_existing=True
            )
            logger.info("✅ AGAPE-DOGE-PERP EOD job scheduled (3:45 PM CT daily)")
        else:
            logger.warning("⚠️ AGAPE-DOGE-PERP not available - DOGE perpetual trading disabled")

        # =================================================================
        # AGAPE-SHIB-PERP JOB: SHIB Perpetual Contract - every 5 minutes, 24/7
        # =================================================================
        if self.agape_shib_perp_trader:
            self.scheduler.add_job(
                self.scheduled_agape_shib_perp_logic,
                trigger=IntervalTrigger(
                    minutes=5,
                    timezone='America/Chicago'
                ),
                id='agape_shib_perp_trading',
                name='AGAPE-SHIB-PERP - SHIB Perpetual (5-min intervals, 24/7)',
                replace_existing=True
            )
            logger.info("✅ AGAPE-SHIB-PERP job scheduled (every 5 min, 24/7)")

            self.scheduler.add_job(
                self.scheduled_agape_shib_perp_eod_logic,
                trigger=CronTrigger(
                    hour=15,
                    minute=45,
                    day_of_week='mon-fri',
                    timezone='America/Chicago'
                ),
                id='agape_shib_perp_eod',
                name='AGAPE-SHIB-PERP - Daily Summary',
                replace_existing=True
            )
            logger.info("✅ AGAPE-SHIB-PERP EOD job scheduled (3:45 PM CT daily)")
        else:
            logger.warning("⚠️ AGAPE-SHIB-PERP not available - SHIB perpetual trading disabled")

        # =================================================================
        # JUBILEE JOB: Box Spread Daily Cycle - runs once daily at 9:30 AM CT
        # Updates positions, calculates returns, checks for roll opportunities
        # Box spreads are longer-term (months), so daily checks are sufficient
        # =================================================================
        if self.jubilee_trader:
            self.scheduler.add_job(
                self.scheduled_jubilee_daily_logic,
                trigger=CronTrigger(
                    hour=9,
                    minute=30,
                    day_of_week='mon-fri',
                    timezone='America/Chicago'
                ),
                id='jubilee_daily',
                name='JUBILEE - Box Spread Daily Cycle',
                replace_existing=True
            )
            logger.info("✅ JUBILEE job scheduled (9:30 AM CT daily - box spread position management)")

            # JUBILEE Equity Snapshots - runs every 30 minutes during market hours
            self.scheduler.add_job(
                self.scheduled_jubilee_equity_snapshot,
                trigger=IntervalTrigger(
                    minutes=30,
                    timezone='America/Chicago'
                ),
                id='jubilee_equity_snapshot',
                name='JUBILEE - Equity Snapshot (30-min intervals)',
                replace_existing=True
            )
            logger.info("✅ JUBILEE equity snapshot job scheduled (every 30 min)")

            # JUBILEE Rate Analysis - runs hourly during market hours
            self.scheduler.add_job(
                self.scheduled_jubilee_rate_analysis,
                trigger=IntervalTrigger(
                    hours=1,
                    timezone='America/Chicago'
                ),
                id='jubilee_rate_analysis',
                name='JUBILEE - Rate Analysis (hourly)',
                replace_existing=True
            )
            logger.info("✅ JUBILEE rate analysis job scheduled (hourly)")
        else:
            logger.warning("⚠️ JUBILEE not available - box spread synthetic borrowing disabled")

        # =================================================================
        # JUBILEE IC JOB: Iron Condor Trading Cycle - runs every 5 minutes (MATCHES ANCHOR)
        # Trades SPX Iron Condors using borrowed capital from box spreads
        # This generates the returns that (should) exceed borrowing costs
        # =================================================================
        if self.jubilee_ic_trader:
            self.scheduler.add_job(
                self.scheduled_jubilee_ic_cycle,
                trigger=IntervalTrigger(
                    minutes=5,
                    timezone='America/Chicago'
                ),
                id='jubilee_ic_trading',
                name='JUBILEE IC - Iron Condor Trading (5-min intervals, MATCHES ANCHOR)',
                replace_existing=True
            )
            logger.info("✅ JUBILEE IC job scheduled (every 5 min - MATCHES ANCHOR)")

            # JUBILEE IC MTM: Event-driven (on open/close) to match SAMSON
            # No separate scheduled MTM job needed
            logger.info("✅ JUBILEE IC MTM is event-driven (on trade open/close, matches SAMSON)")

            # JUBILEE IC Equity Snapshots - runs every 5 minutes during market hours
            # Records periodic equity snapshots so the intraday chart always has data,
            # even when no trades are opened or closed during the session
            self.scheduler.add_job(
                self.scheduled_jubilee_ic_equity_snapshot,
                trigger=IntervalTrigger(
                    minutes=5,
                    timezone='America/Chicago'
                ),
                id='jubilee_ic_equity_snapshot',
                name='JUBILEE IC - Equity Snapshot (5-min intervals)',
                replace_existing=True
            )
            logger.info("✅ JUBILEE IC equity snapshot job scheduled (every 5 min)")
        else:
            logger.warning("⚠️ JUBILEE IC not available - IC trading with borrowed capital disabled")

        # =================================================================
        # WATCHTOWER JOB: Commentary Generation - runs every 5 minutes
        # Generates AI-powered gamma commentary for the Live Log
        # Jobs run immediately on startup and every 5 min thereafter.
        # Market hours are checked inside the job.
        # =================================================================
        self.scheduler.add_job(
            self.scheduled_watchtower_logic,
            trigger=IntervalTrigger(
                minutes=5,
                timezone='America/Chicago'
            ),
            id='watchtower_commentary',
            name='WATCHTOWER - Gamma Commentary (5-min intervals)',
            replace_existing=True
        )
        logger.info("✅ WATCHTOWER job scheduled (every 5 min, checks market hours internally)")

        # =================================================================
        # WATCHTOWER EOD JOB: Pin Prediction Accuracy Processing - runs at 3:01 PM CT
        # Updates pin predictions with actual closing prices and calculates
        # accuracy metrics for the pin accuracy tracking feature.
        # =================================================================
        self.scheduler.add_job(
            self.scheduled_watchtower_eod_logic,
            trigger=CronTrigger(
                hour=15,       # 3:00 PM CT - after market close
                minute=1,      # 3:01 PM CT - immediate post-close
                day_of_week='mon-fri',
                timezone='America/Chicago'
            ),
            id='watchtower_eod',
            name='WATCHTOWER - EOD Pin Accuracy Processing',
            replace_existing=True
        )
        logger.info("✅ WATCHTOWER EOD job scheduled (3:01 PM CT daily)")

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
        # PROVERBS JOB: Feedback Loop Intelligence - runs DAILY after market close
        # Orchestrates autonomous bot improvement:
        # - Collects trade outcomes and analyzes performance
        # - Creates proposals for underperforming bots
        # - Validates proposals via A/B testing (7 days, 20 trades, 5% improvement)
        # - AUTO-APPLIES proven improvements - no manual intervention required
        # =================================================================
        if PROVERBS_AVAILABLE:
            self.scheduler.add_job(
                self.scheduled_proverbs_logic,
                trigger=CronTrigger(
                    hour=16,       # 4:00 PM CT - after market close
                    minute=0,
                    day_of_week='mon-fri',  # Every trading day
                    timezone='America/Chicago'
                ),
                id='proverbs_feedback_loop',
                name='PROVERBS - Daily Feedback Loop Intelligence',
                replace_existing=True
            )
            logger.info("✅ PROVERBS job scheduled (DAILY at 4:00 PM CT)")
        else:
            logger.warning("⚠️ PROVERBS not available - Feedback loop disabled")

        # =================================================================
        # PROPHET JOB: ML Training - runs DAILY at midnight CT
        # FIX (Jan 2026): Standalone Prophet training, not dependent on PROVERBS
        # =================================================================
        if PROPHET_AVAILABLE:
            self.scheduler.add_job(
                self.scheduled_prophet_training_logic,
                trigger=CronTrigger(
                    hour=0,        # Midnight CT
                    minute=0,
                    day_of_week='mon-sun',  # Every day
                    timezone='America/Chicago'
                ),
                id='prophet_training',
                name='PROPHET - Daily ML Training',
                replace_existing=True
            )
            logger.info("✅ PROPHET job scheduled (DAILY at midnight CT)")
        else:
            logger.warning("⚠️ PROPHET not available - training disabled")

        # =================================================================
        # WISDOM JOB: ML Training - runs WEEKLY on Sunday at 4:30 PM CT
        # FIX (Jan 2026): WISDOM was previously manual-only via API
        # =================================================================
        self.scheduler.add_job(
            self.scheduled_wisdom_training_logic,
            trigger=CronTrigger(
                hour=16,       # 4:30 PM CT
                minute=30,
                day_of_week='sun',  # Every Sunday
                timezone='America/Chicago'
            ),
            id='wisdom_training',
            name='WISDOM - Weekly ML Advisor Training',
            replace_existing=True
        )
        logger.info("✅ WISDOM job scheduled (WEEKLY on Sunday at 4:30 PM CT)")

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
        # GEX ML (Probability Models for WATCHTOWER/GLORY)
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
        # FORTRESS ML JOB: ML Advisor Training - runs WEEKLY on Sunday at 7:00 PM CT
        # Trains XGBoost classifier for Iron Condor probability predictions
        # =================================================================
        if FORTRESS_ML_AVAILABLE:
            self.scheduler.add_job(
                self.scheduled_fortress_ml_training_logic,
                trigger=CronTrigger(
                    hour=19,       # 7:00 PM CT - after GEX ML training
                    minute=0,
                    day_of_week='sun',  # Every Sunday
                    timezone='America/Chicago'
                ),
                id='fortress_ml_training',
                name='FORTRESS ML - Weekly ML Advisor Training',
                replace_existing=True
            )
            logger.info("✅ FORTRESS ML job scheduled (WEEKLY on Sunday at 7:00 PM CT)")
        else:
            logger.warning("⚠️ FORTRESS ML not available - ML advisor training disabled")

        # =================================================================
        # DISCERNMENT ML JOB: ML Engine Training - runs WEEKLY on Sunday at 7:30 PM CT
        # Trains direction, magnitude, timing models from prediction outcomes
        # =================================================================
        if DISCERNMENT_ML_AVAILABLE:
            self.scheduler.add_job(
                self.scheduled_discernment_ml_training_logic,
                trigger=CronTrigger(
                    hour=19,       # 7:30 PM CT
                    minute=30,
                    day_of_week='sun',  # Every Sunday
                    timezone='America/Chicago'
                ),
                id='discernment_ml_training',
                name='DISCERNMENT ML - Weekly Engine Training',
                replace_existing=True
            )
            logger.info("✅ DISCERNMENT ML job scheduled (WEEKLY on Sunday at 7:30 PM CT)")
        else:
            logger.warning("⚠️ DISCERNMENT ML not available - engine training disabled")

        # =================================================================
        # VALOR ML JOB: ML Advisor Training - runs WEEKLY on Sunday at 8:00 PM CT
        # Trains XGBoost classifier for MES futures win probability
        # =================================================================
        if VALOR_ML_AVAILABLE:
            self.scheduler.add_job(
                self.scheduled_valor_ml_training_logic,
                trigger=CronTrigger(
                    hour=20,       # 8:00 PM CT
                    minute=0,
                    day_of_week='sun',  # Every Sunday
                    timezone='America/Chicago'
                ),
                id='valor_ml_training',
                name='VALOR ML - Weekly Advisor Training',
                replace_existing=True
            )
            logger.info("✅ VALOR ML job scheduled (WEEKLY on Sunday at 8:00 PM CT)")
        else:
            logger.warning("⚠️ VALOR ML not available - advisor training disabled")

        # =================================================================
        # SPX WHEEL ML JOB: ML Training - runs WEEKLY on Sunday at 8:30 PM CT
        # Trains RandomForest for SPX put selling outcome prediction
        # =================================================================
        if SPX_WHEEL_ML_AVAILABLE:
            self.scheduler.add_job(
                self.scheduled_spx_wheel_ml_training_logic,
                trigger=CronTrigger(
                    hour=20,       # 8:30 PM CT
                    minute=30,
                    day_of_week='sun',  # Every Sunday
                    timezone='America/Chicago'
                ),
                id='spx_wheel_ml_training',
                name='SPX WHEEL ML - Weekly Training',
                replace_existing=True
            )
            logger.info("✅ SPX WHEEL ML job scheduled (WEEKLY on Sunday at 8:30 PM CT)")
        else:
            logger.warning("⚠️ SPX WHEEL ML not available - training disabled")

        # =================================================================
        # PATTERN LEARNER JOB: ML Training - runs WEEKLY on Sunday at 9:00 PM CT
        # Trains RandomForest for pattern success/failure prediction
        # =================================================================
        if PATTERN_LEARNER_AVAILABLE:
            self.scheduler.add_job(
                self.scheduled_pattern_learner_training_logic,
                trigger=CronTrigger(
                    hour=21,       # 9:00 PM CT
                    minute=0,
                    day_of_week='sun',  # Every Sunday
                    timezone='America/Chicago'
                ),
                id='pattern_learner_training',
                name='PATTERN LEARNER - Weekly Training',
                replace_existing=True
            )
            logger.info("✅ PATTERN LEARNER job scheduled (WEEKLY on Sunday at 9:00 PM CT)")
        else:
            logger.warning("⚠️ PATTERN LEARNER not available - training disabled")

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
        # BOT_REPORTS JOB: End-of-day analysis - runs at 3:15 PM CT daily
        # Generates Claude AI reports explaining WHY bots won/lost money
        # Includes Yahoo Finance intraday ticks for precise timestamps
        # =================================================================
        self.scheduler.add_job(
            self.scheduled_bot_reports_logic,
            trigger=CronTrigger(
                hour=15,       # 3:00 PM CT
                minute=15,     # 3:15 PM CT - after EOD reconciliation (3:01) completes
                day_of_week='mon-fri',
                timezone='America/Chicago'
            ),
            id='bot_reports',
            name='BOT_REPORTS - End-of-Day Analysis Reports',
            replace_existing=True
        )
        logger.info("✅ BOT_REPORTS job scheduled (3:15 PM CT daily, Mon-Fri)")

        # =================================================================
        # REPORTS_PURGE JOB: 5-year retention cleanup - runs Sunday 6:30 PM CT
        # Deletes reports older than 5 years to manage storage
        # =================================================================
        self.scheduler.add_job(
            self.scheduled_reports_purge_logic,
            trigger=CronTrigger(
                hour=18,       # 6:00 PM CT
                minute=30,     # 6:30 PM CT
                day_of_week='sun',
                timezone='America/Chicago'
            ),
            id='reports_purge',
            name='REPORTS_PURGE - 5-Year Retention Cleanup',
            replace_existing=True
        )
        logger.info("✅ REPORTS_PURGE job scheduled (WEEKLY on Sunday at 6:30 PM CT)")

        # =================================================================
        # CRITICAL: Verify at least one trading bot is available
        # If ALL bots failed to initialize, the scheduler will run but do NOTHING
        # =================================================================
        active_bots = []
        if self.fortress_trader:
            active_bots.append("FORTRESS")
        if self.solomon_trader:
            active_bots.append("SOLOMON")
        if self.anchor_trader:
            active_bots.append("ANCHOR")
        if self.gideon_trader:
            active_bots.append("GIDEON")
        if self.samson_trader:
            active_bots.append("SAMSON")
        if self.cornerstone_trader:
            active_bots.append("CORNERSTONE")
        if self.trader:
            active_bots.append("LAZARUS")

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
        # STARTUP RECOVERY: Check for missed ML training jobs
        # FIX (Jan 2026): Jobs that stopped on holidays wouldn't restart
        # This ensures overdue training gets caught up immediately
        # =================================================================
        try:
            self._check_startup_recovery()
        except Exception as e:
            logger.warning(f"Startup recovery check failed (non-fatal): {e}")

        # =================================================================
        # STARTUP HEARTBEAT: Save initial heartbeat for all bots
        # This ensures dashboard shows the scheduler is alive immediately,
        # even before the first job runs (which might be 5 minutes away).
        # =================================================================
        logger.info("Saving startup heartbeats for all bots...")
        is_open, market_status = self.get_market_status()
        startup_status = 'STARTING' if is_open else market_status
        startup_details = {'event': 'scheduler_startup', 'market_status': market_status}

        for bot_name in ['FORTRESS', 'SOLOMON', 'ANCHOR', 'GIDEON', 'SAMSON', 'CORNERSTONE', 'LAZARUS']:
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
            # If FORTRESS/SOLOMON haven't run in 15+ minutes, something is wrong
            # (they should run every 5 minutes)
            now = datetime.now(CENTRAL_TZ)
            max_stale_minutes = 15  # Jobs run every 5 min, allow 3x buffer

            # Only check job staleness if we have traders initialized
            # and have had at least one check
            stale_jobs = []

            if self.fortress_trader and self.last_fortress_check:
                fortress_age = (now - self.last_fortress_check).total_seconds() / 60
                if fortress_age > max_stale_minutes:
                    stale_jobs.append(f"FORTRESS ({fortress_age:.1f} min stale)")

            if self.solomon_trader and self.last_solomon_check:
                solomon_age = (now - self.last_solomon_check).total_seconds() / 60
                if solomon_age > max_stale_minutes:
                    stale_jobs.append(f"SOLOMON ({solomon_age:.1f} min stale)")

            if self.anchor_trader and self.last_anchor_check:
                anchor_age = (now - self.last_anchor_check).total_seconds() / 60
                if anchor_age > max_stale_minutes:
                    stale_jobs.append(f"ANCHOR ({anchor_age:.1f} min stale)")

            if self.gideon_trader and self.last_gideon_check:
                gideon_age = (now - self.last_gideon_check).total_seconds() / 60
                if gideon_age > max_stale_minutes:
                    stale_jobs.append(f"GIDEON ({gideon_age:.1f} min stale)")

            if self.samson_trader and self.last_samson_check:
                samson_age = (now - self.last_samson_check).total_seconds() / 60
                if samson_age > max_stale_minutes:
                    stale_jobs.append(f"SAMSON ({samson_age:.1f} min stale)")

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
            'used_by': ['WATCHTOWER', 'GLORY']
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


def get_fortress_trader():
    """Get the FORTRESS trader instance from the scheduler"""
    scheduler = get_scheduler()
    return scheduler.fortress_trader if scheduler else None


def get_cornerstone_trader():
    """Get the CORNERSTONE trader instance from the scheduler"""
    scheduler = get_scheduler()
    return scheduler.cornerstone_trader if scheduler else None


def get_solomon_trader():
    """Get the SOLOMON trader instance from the scheduler"""
    scheduler = get_scheduler()
    return scheduler.solomon_trader if scheduler else None


def get_anchor_trader():
    """Get the ANCHOR trader instance from the scheduler"""
    scheduler = get_scheduler()
    return scheduler.anchor_trader if scheduler else None


def get_gideon_trader():
    """Get the GIDEON trader instance from the scheduler"""
    scheduler = get_scheduler()
    return scheduler.gideon_trader if scheduler else None


def get_samson_trader():
    """Get the SAMSON trader instance from the scheduler"""
    scheduler = get_scheduler()
    return scheduler.samson_trader if scheduler else None


# ============================================================================
# STANDALONE EXECUTION MODE (for Render Background Worker)
# ============================================================================
def run_standalone():
    """
    Run the scheduler as a standalone process (for Render deployment).

    This runs BOTH bots:
    - LAZARUS: 0DTE SPY/SPX options (hourly during market hours)
    - CORNERSTONE: SPX Wheel strategy (daily at 10:05 AM ET)

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
    logger.info(f"LAZARUS (0DTE):      ${CAPITAL_ALLOCATION['LAZARUS']:,}")
    logger.info(f"CORNERSTONE (Wheel):       ${CAPITAL_ALLOCATION['CORNERSTONE']:,}")
    logger.info(f"FORTRESS (Aggressive):   ${CAPITAL_ALLOCATION['FORTRESS']:,}")
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
                                   f"FORTRESS={scheduler.fortress_execution_count} (last: {scheduler.last_fortress_check.strftime('%H:%M:%S') if scheduler.last_fortress_check else 'never'}), "
                                   f"SOLOMON={scheduler.solomon_execution_count} (last: {scheduler.last_solomon_check.strftime('%H:%M:%S') if scheduler.last_solomon_check else 'never'}), "
                                   f"restarts={restart_count}")

                        last_status_log = current_time
                else:
                    health_check_failures += 1
                    now_ct = datetime.now(CENTRAL_TZ)
                    logger.warning(f"[HEALTH FAIL @ {now_ct.strftime('%H:%M:%S')}] "
                                  f"Health check FAILED ({health_check_failures}/{max_health_failures}) - "
                                  f"FORTRESS last: {scheduler.last_fortress_check.strftime('%H:%M:%S') if scheduler and scheduler.last_fortress_check else 'never'}, "
                                  f"SOLOMON last: {scheduler.last_solomon_check.strftime('%H:%M:%S') if scheduler and scheduler.last_solomon_check else 'never'}")

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
