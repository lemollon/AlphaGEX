"""
Autonomous Trading Scheduler for Render Deployment
Uses APScheduler to run trading logic during market hours
Integrates seamlessly with Streamlit web service
"""

# Try to import APScheduler, but make it optional
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    BackgroundScheduler = None
    CronTrigger = None
    print("Warning: APScheduler not installed. Autonomous trading scheduler will be disabled.")

from autonomous_paper_trader import AutonomousPaperTrader
from core_classes_and_engines import TradingVolatilityAPI
from datetime import datetime
import pytz
import logging
import traceback
from pathlib import Path
import json

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
    """Manages background scheduling of autonomous trading operations"""

    def __init__(self):
        if not APSCHEDULER_AVAILABLE:
            logger.warning("APScheduler not available - scheduler will not run")
            self.scheduler = None
            self.is_running = False
            return

        self.scheduler = None
        self.trader = AutonomousPaperTrader()
        self.api_client = TradingVolatilityAPI()
        self.is_running = False
        self.last_trade_check = None
        self.last_position_check = None
        self.last_error = None
        self.execution_count = 0

    def is_market_open(self) -> bool:
        """Check if US market is currently open (9:30 AM - 4:00 PM ET, Mon-Fri)"""
        ny_tz = pytz.timezone('America/New_York')
        now = datetime.now(ny_tz)

        # Check if weekend
        if now.weekday() >= 5:  # Saturday=5, Sunday=6
            return False

        # Market hours: 9:30 AM - 4:00 PM ET
        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)

        return market_open <= now < market_close

    def scheduled_trade_logic(self):
        """
        Main trading logic executed every hour during market hours
        This is what APScheduler calls on schedule
        """
        ny_tz = pytz.timezone('America/New_York')
        now = datetime.now(ny_tz)

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
        logger.info(f"Timezone: America/New_York (Eastern Time)")
        logger.info(f"Schedule: Every hour from 10:00 AM - 3:00 PM ET, Monday-Friday")
        logger.info(f"Log file: {LOG_FILE}")
        logger.info("=" * 80)

        # Create scheduler with NY timezone
        self.scheduler = BackgroundScheduler(timezone='America/New_York')

        # Add job: Run every hour from 10 AM to 3 PM ET, Monday-Friday
        # This gives us: 10 AM, 11 AM, 12 PM, 1 PM, 2 PM, 3 PM (6 checks per day)
        # We skip 9 AM (market just opened) and 4 PM (too close to close)
        self.scheduler.add_job(
            self.scheduled_trade_logic,
            trigger=CronTrigger(
                hour='10-15',  # 10 AM through 3 PM (15 is 3:00 PM)
                minute=0,      # On the hour
                day_of_week='mon-fri',
                timezone='America/New_York'
            ),
            id='autonomous_trading',
            name='Autonomous Trading Logic',
            replace_existing=True
        )

        self.scheduler.start()
        self.is_running = True

        logger.info("✓ Scheduler started successfully")
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
        logger.info("✓ Scheduler stopped")

    def get_status(self) -> dict:
        """Get current scheduler status for monitoring dashboard"""
        ny_tz = pytz.timezone('America/New_York')
        now = datetime.now(ny_tz)

        status = {
            'is_running': self.is_running,
            'market_open': self.is_market_open(),
            'current_time_et': now.strftime('%Y-%m-%d %H:%M:%S %Z'),
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
