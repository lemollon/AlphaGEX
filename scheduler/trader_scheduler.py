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
- ARES: Aggressive Iron Condor targeting 10% monthly (daily at 9:35 AM ET)
- ARES EOD: Process expired 0DTE positions (daily at 4:05 PM ET)
- ATHENA: GEX Directional Spreads (every 30 min 9:35 AM - 3:30 PM ET)
- ARGUS: Gamma Commentary Generation (every 5 min 8:30 AM - 3:00 PM CT)

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
    'PHOENIX': 300_000,   # 0DTE options trading
    'ATLAS': 400_000,     # SPX wheel strategy
    'ARES': 200_000,      # Aggressive Iron Condor (10% monthly target)
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

# Import ARES (Aggressive Iron Condor)
try:
    from trading.ares_iron_condor import ARESTrader, TradingMode as ARESTradingMode
    ARES_AVAILABLE = True
except ImportError:
    ARES_AVAILABLE = False
    ARESTrader = None
    ARESTradingMode = None
    print("Warning: ARESTrader not available. ARES bot will be disabled.")

# Import ATHENA (Directional Spreads)
try:
    from trading.athena_directional_spreads import ATHENATrader, TradingMode as ATHENATradingMode
    ATHENA_AVAILABLE = True
except ImportError:
    ATHENA_AVAILABLE = False
    ATHENATrader = None
    ATHENATradingMode = None
    print("Warning: ATHENATrader not available. ATHENA bot will be disabled.")

# Import decision logger for comprehensive logging
try:
    from trading.decision_logger import get_phoenix_logger, get_atlas_logger, get_ares_logger, BotName
    DECISION_LOGGER_AVAILABLE = True
except ImportError:
    DECISION_LOGGER_AVAILABLE = False
    print("Warning: Decision logger not available.")

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

        # PHOENIX - 0DTE SPY/SPX Options Trader
        # Capital: $400,000 (40% of total)
        self.trader = AutonomousPaperTrader(
            symbol='SPY',
            capital=CAPITAL_ALLOCATION['PHOENIX']
        )
        self.api_client = TradingVolatilityAPI()
        logger.info(f"✅ PHOENIX initialized with ${CAPITAL_ALLOCATION['PHOENIX']:,} capital")

        # ATLAS - SPX Cash-Secured Put Wheel Trader
        # Capital: $400,000 (40% of total)
        self.atlas_trader = None
        if ATLAS_AVAILABLE:
            try:
                self.atlas_trader = SPXWheelTrader(
                    mode=TradingMode.PAPER,
                    initial_capital=CAPITAL_ALLOCATION['ATLAS']
                )
                logger.info(f"✅ ATLAS initialized with ${CAPITAL_ALLOCATION['ATLAS']:,} capital")
            except Exception as e:
                logger.warning(f"ATLAS initialization failed: {e}")
                self.atlas_trader = None

        # ARES - Aggressive Iron Condor (10% monthly target)
        # Capital: $200,000 (20% of total)
        # PAPER mode: Uses real SPX data from Tradier Production API, paper trades internally
        # LIVE mode: Uses real SPX data AND submits real orders to Tradier
        self.ares_trader = None
        if ARES_AVAILABLE:
            try:
                self.ares_trader = ARESTrader(
                    mode=ARESTradingMode.PAPER,  # Paper trading with real SPX data
                    initial_capital=CAPITAL_ALLOCATION['ARES']
                )
                logger.info(f"✅ ARES initialized with ${CAPITAL_ALLOCATION['ARES']:,} capital (PAPER mode, real SPX data)")
            except Exception as e:
                logger.warning(f"ARES initialization failed: {e}")
                self.ares_trader = None

        # ATHENA - GEX-Based Directional Spreads
        # Capital: $100,000 (from Reserve)
        # Uses ML probability models for signal generation
        self.athena_trader = None
        if ATHENA_AVAILABLE:
            try:
                self.athena_trader = ATHENATrader(
                    initial_capital=100_000,  # Uses portion of reserve
                    config=None  # Will load from database
                )
                logger.info(f"✅ ATHENA initialized with $100,000 capital (PAPER mode, GEX ML signals)")
            except Exception as e:
                logger.warning(f"ATHENA initialization failed: {e}")
                self.athena_trader = None

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
        self.last_argus_check = None
        self.last_error = None
        self.execution_count = 0
        self.atlas_execution_count = 0
        self.ares_execution_count = 0
        self.athena_execution_count = 0
        self.argus_execution_count = 0

        # Load saved state from database
        self._load_state()

    def _load_state(self):
        """Load scheduler state from database (PostgreSQL)"""
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
                    conn.close()
                    return True  # Signal that auto-restart is needed

            conn.close()
            return False

        except Exception as e:
            logger.error(f"Error loading scheduler state: {str(e)}")
            return False

    def _save_state(self):
        """Save current scheduler state to database (PostgreSQL)"""
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
            conn.close()
            logger.debug("Scheduler state saved to database")

        except Exception as e:
            logger.error(f"Error saving scheduler state: {str(e)}")

    def _mark_auto_restart(self, reason="App restart"):
        """Mark that scheduler should auto-restart on next launch (PostgreSQL)"""
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
            conn.close()

        except Exception as e:
            logger.error(f"Error marking auto-restart: {str(e)}")

    def _clear_auto_restart(self):
        """Clear auto-restart flag after successful restart (PostgreSQL)"""
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
            conn.close()

        except Exception as e:
            logger.error(f"Error clearing auto-restart: {str(e)}")

    def is_market_open(self) -> bool:
        """Check if US market is currently open (8:30 AM - 3:00 PM CT, Mon-Fri)"""
        now = datetime.now(CENTRAL_TZ)

        # Check if weekend
        if now.weekday() >= 5:  # Saturday=5, Sunday=6
            return False

        # Market hours: 8:30 AM - 3:00 PM CT (same as 9:30 AM - 4:00 PM ET)
        market_open = now.replace(hour=8, minute=30, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=0, second=0, microsecond=0)

        return market_open <= now < market_close

    def scheduled_trade_logic(self):
        """
        Main trading logic executed every hour during market hours
        This is what APScheduler calls on schedule
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"Scheduler triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        # Double-check market is open (belt and suspenders)
        if not self.is_market_open():
            logger.info("Market is CLOSED. Skipping trade logic.")
            return

        logger.info("Market is OPEN. Running autonomous trading logic...")

        try:
            # Step 1: Find and execute new daily trade (if we haven't traded today)
            logger.info("Step 1: Checking for new trade opportunities...")
            self.last_trade_check = now

            trade_result = self.trader.find_and_execute_daily_trade(self.api_client)

            if trade_result:
                logger.info(f"✓ Trade executed: {trade_result.get('strategy', 'Unknown')}")
                logger.info(f"  Action: {trade_result.get('action', 'N/A')}")
                logger.info(f"  Entry: ${trade_result.get('entry_price', 0):.2f}")
                logger.info(f"  DTE: {trade_result.get('dte', 'N/A')}")
            else:
                logger.info("No new trade today (already traded or no good setups)")

            # Step 2: Manage existing positions (check stops, take profits, etc.)
            logger.info("Step 2: Managing existing positions...")
            self.last_position_check = now

            management_results = self.trader.auto_manage_positions(self.api_client)

            if management_results:
                logger.info(f"Position management completed:")
                for result in management_results:
                    logger.info(f"  - {result.get('symbol', 'Unknown')}: {result.get('action', 'N/A')}")
            else:
                logger.info("No positions to manage or no actions taken")

            # Update execution count
            self.execution_count += 1
            self.last_error = None

            # Save state after each execution
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
            return

        if not self.is_market_open():
            logger.info("Market is CLOSED. Skipping ATLAS logic.")
            return

        logger.info("Market is OPEN. Running ATLAS wheel strategy...")

        try:
            self.last_atlas_check = now

            # Run the daily wheel cycle
            # This handles: new positions, expiration processing, roll checks
            result = self.atlas_trader.run_daily_cycle()

            if result:
                logger.info(f"ATLAS daily cycle completed:")
                logger.info(f"  SPX Price: ${result.get('spx_price', 0):,.2f}")
                logger.info(f"  Open Positions: {result.get('open_positions', 0)}")
                logger.info(f"  Actions taken: {result.get('actions', [])}")

                # Log any new positions
                if result.get('new_position'):
                    logger.info(f"  NEW POSITION: {result.get('new_position')}")

                # Log any rolls
                if result.get('rolls'):
                    for roll in result.get('rolls', []):
                        logger.info(f"  ROLLED: {roll}")

                # Log any expirations
                if result.get('expirations'):
                    for exp in result.get('expirations', []):
                        logger.info(f"  EXPIRED: {exp}")
            else:
                logger.info("ATLAS: No actions taken today")

            self.atlas_execution_count += 1
            logger.info(f"ATLAS cycle #{self.atlas_execution_count} completed successfully")
            logger.info(f"=" * 80)

        except Exception as e:
            error_msg = f"ERROR in ATLAS trading logic: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            logger.info("ATLAS will continue despite error")
            logger.info(f"=" * 80)

    def scheduled_ares_logic(self):
        """
        ARES (Aggressive Iron Condor) trading logic - runs daily at 9:35 AM CT

        The aggressive Iron Condor strategy:
        - Targets 10% monthly returns
        - Trades 0DTE Iron Condors every weekday
        - 1 SD strikes, 10% risk per trade
        - No stop loss - let theta work
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"ARES (Aggressive IC) triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.ares_trader:
            logger.warning("ARES trader not available - skipping")
            return

        if not self.is_market_open():
            logger.info("Market is CLOSED. Skipping ARES logic.")
            return

        logger.info("Market is OPEN. Running ARES aggressive Iron Condor strategy...")

        try:
            self.last_ares_check = now

            # Run the daily ARES cycle
            result = self.ares_trader.run_daily_cycle()

            if result:
                logger.info(f"ARES daily cycle completed:")
                logger.info(f"  Capital: ${result.get('capital', 0):,.2f}")
                logger.info(f"  Open Positions: {result.get('open_positions', 0)}")
                logger.info(f"  Actions: {result.get('actions', [])}")

                # Log any new positions
                if result.get('new_position'):
                    pos = result.get('new_position')
                    logger.info(f"  NEW POSITION: {pos.get('position_id')} - {pos.get('strikes')}")
                    logger.info(f"    Contracts: {pos.get('contracts')}, Credit: ${pos.get('credit', 0):.2f}")
            else:
                logger.info("ARES: No actions taken today")

            self.ares_execution_count += 1
            logger.info(f"ARES cycle #{self.ares_execution_count} completed successfully")
            logger.info(f"=" * 80)

        except Exception as e:
            error_msg = f"ERROR in ARES trading logic: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            logger.info("ARES will continue despite error")
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

    def scheduled_athena_logic(self):
        """
        ATHENA (GEX Directional Spreads) trading logic - runs every 30 minutes during market hours

        The GEX-based directional spread strategy:
        - Uses live Tradier GEX data for real-time signal generation
        - ML probability models for direction prediction
        - Bull Call Spreads for bullish, Bear Call Spreads for bearish
        - 0DTE options on SPY
        - GEX wall proximity filter for high probability setups

        Runs continuously 8:35 AM - 2:30 PM CT to capture intraday GEX shifts.
        """
        now = datetime.now(CENTRAL_TZ)

        logger.info(f"=" * 80)
        logger.info(f"ATHENA (GEX Directional) triggered at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not self.athena_trader:
            logger.warning("ATHENA trader not available - skipping")
            return

        if not self.is_market_open():
            logger.info("Market is CLOSED. Skipping ATHENA logic.")
            return

        # Check if within entry window (8:35 AM - 2:30 PM CT)
        entry_start = now.replace(hour=8, minute=35, second=0)
        entry_end = now.replace(hour=14, minute=30, second=0)

        if now < entry_start:
            logger.info(f"Before entry window ({entry_start.strftime('%H:%M')}). Skipping.")
            return

        if now > entry_end:
            logger.info(f"After entry window ({entry_end.strftime('%H:%M')}). Checking exits only.")
            # Still run to check exits, but won't open new positions
            # The Apache trader handles this via should_trade() time checks

        logger.info("Market is OPEN. Scanning live GEX data for directional opportunities...")

        try:
            self.last_athena_check = now

            # Run the ATHENA intraday cycle
            result = self.athena_trader.run_daily_cycle()

            if result:
                logger.info(f"ATHENA intraday scan completed:")

                # === GEX CONTEXT ===
                gex_ctx = result.get('gex_context')
                if gex_ctx:
                    logger.info(f"  GEX Context:")
                    logger.info(f"    SPY: ${gex_ctx.get('spot_price', 0):.2f}")
                    logger.info(f"    Walls: Put ${gex_ctx.get('put_wall', 0):.0f} | Call ${gex_ctx.get('call_wall', 0):.0f}")
                    logger.info(f"    Regime: {gex_ctx.get('regime', 'N/A')} | Source: {gex_ctx.get('source', 'N/A')}")

                # === ML SIGNAL ===
                ml_sig = result.get('ml_signal')
                if ml_sig:
                    logger.info(f"  ML Signal:")
                    logger.info(f"    Direction: {ml_sig.get('direction', 'N/A')} | Advice: {ml_sig.get('advice', 'N/A')}")
                    logger.info(f"    Confidence: {ml_sig.get('confidence', 0)*100:.1f}% | Win Prob: {ml_sig.get('win_probability', 0)*100:.1f}%")

                # === DECISION REASON ===
                decision = result.get('decision_reason')
                if decision:
                    logger.info(f"  >>> DECISION: {decision}")

                # === TRADE STATS ===
                logger.info(f"  Stats: Attempted={result.get('trades_attempted', 0)} | Executed={result.get('trades_executed', 0)} | Closed={result.get('positions_closed', 0)}")

                if result.get('daily_pnl', 0) != 0:
                    logger.info(f"  Daily P&L: ${result.get('daily_pnl', 0):,.2f}")

                # Log R:R ratio if available
                if result.get('rr_ratio'):
                    logger.info(f"  R:R Ratio: {result.get('rr_ratio', 0):.2f}:1")

            else:
                logger.info("ATHENA: No result returned")

            self.athena_execution_count += 1
            logger.info(f"ATHENA scan #{self.athena_execution_count} completed (next scan in 30 min)")
            logger.info(f"=" * 80)

        except Exception as e:
            error_msg = f"ERROR in ATHENA trading logic: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            logger.info("ATHENA will retry next interval")
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
        logger.info(f"Bots: PHOENIX (0DTE), ATLAS (Wheel), ARES (Aggressive IC), ATHENA (GEX Directional), ARGUS (Commentary)")
        logger.info(f"Timezone: America/Chicago (Texas Central Time)")
        logger.info(f"PHOENIX Schedule: DISABLED here - handled by AutonomousTrader (every 5 min)")
        logger.info(f"ATLAS Schedule: Daily at 9:05 AM CT, Mon-Fri")
        logger.info(f"ARES Schedule: Daily at 9:35 AM CT, Mon-Fri")
        logger.info(f"ATHENA Schedule: Every 30 min (8:35 AM - 2:30 PM CT), Mon-Fri")
        logger.info(f"ARGUS Schedule: Every 5 min (8:30 AM - 3:00 PM CT), Mon-Fri")
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
        # ARES JOB: Aggressive Iron Condor - runs once daily at 9:35 AM CT
        # (Matches ARES trading window which starts at 9:35 AM CT)
        # =================================================================
        if self.ares_trader:
            self.scheduler.add_job(
                self.scheduled_ares_logic,
                trigger=CronTrigger(
                    hour=9,        # 9:00 AM CT
                    minute=35,     # 9:35 AM CT - matches ARES entry_time_start
                    day_of_week='mon-fri',
                    timezone='America/Chicago'
                ),
                id='ares_trading',
                name='ARES - Aggressive Iron Condor',
                replace_existing=True
            )
            logger.info("✅ ARES job scheduled (9:35 AM CT daily)")

            # =================================================================
            # ARES EOD JOB: Process expired positions - runs at 3:05 PM CT
            # =================================================================
            self.scheduler.add_job(
                self.scheduled_ares_eod_logic,
                trigger=CronTrigger(
                    hour=15,       # 3:00 PM CT - after market close
                    minute=5,      # 3:05 PM CT to ensure market data is final
                    day_of_week='mon-fri',
                    timezone='America/Chicago'
                ),
                id='ares_eod',
                name='ARES - EOD Position Expiration',
                replace_existing=True
            )
            logger.info("✅ ARES EOD job scheduled (3:05 PM CT daily)")
        else:
            logger.warning("⚠️ ARES not available - aggressive IC trading disabled")

        # =================================================================
        # ATHENA JOB: GEX Directional Spreads - runs every 30 minutes during market hours
        # Uses live Tradier GEX data to find intraday opportunities
        # =================================================================
        if self.athena_trader:
            # Run every 30 minutes during market hours (8:35 AM - 2:30 PM CT)
            # First run at 8:35 AM CT, then 9:05, 9:35, etc.
            self.scheduler.add_job(
                self.scheduled_athena_logic,
                trigger=IntervalTrigger(
                    minutes=30,
                    start_date=datetime.now(CENTRAL_TZ).replace(
                        hour=8, minute=35, second=0, microsecond=0
                    ),
                    timezone='America/Chicago'
                ),
                id='athena_trading',
                name='ATHENA - GEX Directional Spreads (30-min intervals)',
                replace_existing=True
            )
            logger.info("✅ ATHENA job scheduled (every 30 min during market hours)")
        else:
            logger.warning("⚠️ ATHENA not available - GEX directional trading disabled")

        # =================================================================
        # ARGUS JOB: Commentary Generation - runs every 5 minutes during market hours
        # Generates AI-powered gamma commentary for the Live Log
        # =================================================================
        self.scheduler.add_job(
            self.scheduled_argus_logic,
            trigger=IntervalTrigger(
                minutes=5,
                start_date=datetime.now(CENTRAL_TZ).replace(
                    hour=8, minute=30, second=0, microsecond=0
                ),
                timezone='America/Chicago'
            ),
            id='argus_commentary',
            name='ARGUS - Gamma Commentary (5-min intervals)',
            replace_existing=True
        )
        logger.info("✅ ARGUS job scheduled (every 5 min during market hours)")

        self.scheduler.start()
        self.is_running = True

        # Mark that auto-restart should be enabled
        self._mark_auto_restart("User started")
        self._clear_auto_restart()  # Clear immediately - we're running now
        self._save_state()  # Save running state

        logger.info("✓ Scheduler started successfully")
        logger.info("✓ Auto-restart enabled - will survive app restarts")
        logger.info("Next scheduled runs:")

        # Log next 3 scheduled runs
        jobs = self.scheduler.get_jobs()
        if jobs:
            for job in jobs:
                next_run = job.next_run_time
                if next_run:
                    logger.info(f"  - {next_run.strftime('%Y-%m-%d %H:%M:%S %Z')}")

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

    def get_status(self) -> dict:
        """Get current scheduler status for monitoring dashboard"""
        now = datetime.now(CENTRAL_TZ)

        status = {
            'is_running': self.is_running,
            'market_open': self.is_market_open(),
            'current_time_ct': now.strftime('%Y-%m-%d %H:%M:%S %Z'),
            'last_trade_check': self.last_trade_check.strftime('%Y-%m-%d %H:%M:%S') if self.last_trade_check else 'Never',
            'last_position_check': self.last_position_check.strftime('%Y-%m-%d %H:%M:%S') if self.last_position_check else 'Never',
            'execution_count': self.execution_count,
            'last_error': self.last_error,
        }

        # Get next scheduled run time
        if self.is_running and self.scheduler:
            jobs = self.scheduler.get_jobs()
            if jobs:
                next_run = jobs[0].next_run_time
                if next_run:
                    status['next_run'] = next_run.strftime('%Y-%m-%d %H:%M:%S %Z')
                else:
                    status['next_run'] = 'Not scheduled'
            else:
                status['next_run'] = 'No jobs'
        else:
            status['next_run'] = 'Scheduler not running'

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

    # Create and start scheduler
    scheduler = get_scheduler()

    # Handle graceful shutdown
    shutdown_requested = False

    def signal_handler(signum, frame):
        nonlocal shutdown_requested
        logger.info(f"Received signal {signum}, requesting shutdown...")
        shutdown_requested = True
        if scheduler.is_running:
            scheduler.stop()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Start the scheduler
    scheduler.start()

    logger.info("Scheduler started. Running continuously...")
    logger.info("Press Ctrl+C to stop (or send SIGTERM)")

    # Keep the process alive
    try:
        while not shutdown_requested:
            time.sleep(60)  # Check every minute

            # Log status periodically
            status = scheduler.get_status()
            if status['market_open']:
                logger.info(f"Market OPEN - Executions: PHOENIX={scheduler.execution_count}, ATLAS={scheduler.atlas_execution_count}, ARES={scheduler.ares_execution_count}, ATHENA={scheduler.athena_execution_count}, ARGUS={scheduler.argus_execution_count}")
            else:
                logger.debug(f"Market closed. Next run: {status.get('next_run', 'Unknown')}")

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        if scheduler.is_running:
            scheduler.stop()
        logger.info("Autonomous trader shutdown complete")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--standalone":
        run_standalone()
    else:
        # Default: run standalone mode (for Render)
        run_standalone()
