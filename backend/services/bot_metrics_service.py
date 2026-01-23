"""
Unified Bot Metrics Service - Single Source of Truth

This service provides consistent metrics calculations for all trading bots.
It eliminates data reconciliation issues by:
1. Using ONE source for capital (database config, with Tradier fallback)
2. Using ONE source for P&L (database aggregates, not frontend calculations)
3. Using ONE source for win rate (database calculations)
4. Providing consistent field names across all bots
5. Ensuring historical and intraday charts align

Created: January 2025
Purpose: Fix data inconsistencies identified in bot frontend audit
"""

import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, List, Tuple
from zoneinfo import ZoneInfo
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)

# Import MTM calculation functions for live unrealized P&L
MTM_AVAILABLE = False
calculate_ic_mark_to_market = None
calculate_spread_mark_to_market = None
try:
    from trading.mark_to_market import calculate_ic_mark_to_market, calculate_spread_mark_to_market
    MTM_AVAILABLE = True
    logger.info("bot_metrics_service: MTM functions loaded successfully")
except ImportError as e:
    logger.warning(f"bot_metrics_service: MTM functions not available: {e}")

CENTRAL_TZ = ZoneInfo("America/Chicago")


class BotName(Enum):
    """Supported trading bots"""
    ARES = "ARES"
    ATHENA = "ATHENA"
    ICARUS = "ICARUS"
    TITAN = "TITAN"
    PEGASUS = "PEGASUS"


@dataclass
class BotCapitalConfig:
    """Capital configuration for a bot - THE source of truth for capital"""
    bot_name: str
    starting_capital: float
    capital_source: str  # 'database', 'tradier', 'default'
    tradier_connected: bool
    tradier_balance: Optional[float]
    last_updated: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            'last_updated': self.last_updated.isoformat() if self.last_updated else None
        }


@dataclass
class BotMetricsSummary:
    """
    Unified metrics summary for a bot.
    ALL stats should come from this structure - never calculate in frontend.
    """
    # Identity
    bot_name: str

    # Capital (SINGLE SOURCE)
    starting_capital: float
    current_equity: float
    capital_source: str

    # P&L (ALL FROM DATABASE)
    total_realized_pnl: float
    total_unrealized_pnl: float
    total_pnl: float  # realized + unrealized
    today_realized_pnl: float
    today_unrealized_pnl: float
    today_pnl: float  # today realized + unrealized

    # Trade Stats (ALL FROM DATABASE)
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float  # 0-100 percentage, NOT decimal

    # Position Counts
    open_positions: int
    closed_positions: int

    # Performance
    total_return_pct: float
    max_drawdown_pct: float
    high_water_mark: float

    # Timestamps
    calculated_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            'calculated_at': self.calculated_at.isoformat() if self.calculated_at else None
        }


@dataclass
class EquityCurvePoint:
    """Single point on equity curve - consistent structure"""
    date: str
    equity: float
    daily_pnl: float
    cumulative_pnl: float
    realized_pnl: float
    unrealized_pnl: float
    drawdown_pct: float
    trade_count: int
    return_pct: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class IntradayEquityPoint:
    """Single point on intraday equity curve"""
    timestamp: str
    time: str
    equity: float
    cumulative_pnl: float
    realized_pnl: float
    unrealized_pnl: float
    open_positions: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BotMetricsService:
    """
    Unified service for calculating bot metrics.

    RULES:
    1. Capital comes from database config first, Tradier second, default last
    2. All P&L aggregates come from database SUM() queries
    3. Win rate is calculated server-side, never in frontend
    4. Historical and intraday use THE SAME starting capital
    5. All percentages are 0-100, not decimals
    """

    # Default capital per bot (only used if database and Tradier unavailable)
    DEFAULT_CAPITAL = {
        BotName.ARES: 100000,
        BotName.ATHENA: 100000,
        BotName.ICARUS: 100000,
        BotName.TITAN: 200000,
        BotName.PEGASUS: 200000,
    }

    # Database table mappings
    BOT_TABLES = {
        BotName.ARES: {
            'positions': 'ares_positions',
            'snapshots': 'ares_equity_snapshots',
            'config_key': 'ares_starting_capital',
        },
        BotName.ATHENA: {
            'positions': 'athena_positions',
            'snapshots': 'athena_equity_snapshots',
            'config_key': 'athena_starting_capital',
        },
        BotName.ICARUS: {
            'positions': 'icarus_positions',
            'snapshots': 'icarus_equity_snapshots',
            'config_key': 'icarus_starting_capital',
        },
        BotName.TITAN: {
            'positions': 'titan_positions',
            'snapshots': 'titan_equity_snapshots',
            'config_key': 'titan_starting_capital',
        },
        BotName.PEGASUS: {
            'positions': 'pegasus_positions',
            'snapshots': 'pegasus_equity_snapshots',
            'config_key': 'pegasus_starting_capital',
        },
    }

    def __init__(self):
        """Initialize the metrics service"""
        self._tradier_fetcher = None
        self._capital_cache: Dict[str, BotCapitalConfig] = {}
        self._cache_ttl = 60  # Cache capital for 60 seconds

    def _get_connection(self):
        """Get database connection"""
        try:
            from database_adapter import get_connection
            return get_connection()
        except Exception as e:
            logger.error(f"Failed to get database connection: {e}")
            return None

    def _get_tradier_balance(self, sandbox: bool = True) -> Optional[Dict[str, Any]]:
        """Get Tradier account balance"""
        try:
            from data.tradier_data_fetcher import TradierDataFetcher
            from unified_config import APIConfig

            if sandbox:
                api_key = APIConfig.TRADIER_SANDBOX_API_KEY
                account_id = APIConfig.TRADIER_SANDBOX_ACCOUNT_ID
            else:
                api_key = APIConfig.TRADIER_API_KEY
                account_id = APIConfig.TRADIER_ACCOUNT_ID

            if not api_key or not account_id:
                return None

            fetcher = TradierDataFetcher(
                api_key=api_key,
                account_id=account_id,
                sandbox=sandbox
            )

            balance = fetcher.get_account_balance()
            if balance:
                return {
                    'connected': True,
                    'total_equity': balance.total_equity,
                    'option_buying_power': balance.option_buying_power,
                    'account_id': account_id,
                }
            return None
        except Exception as e:
            logger.debug(f"Tradier balance fetch failed: {e}")
            return None

    def get_capital_config(self, bot: BotName, force_refresh: bool = False) -> BotCapitalConfig:
        """
        Get the authoritative capital configuration for a bot.

        Priority:
        1. Database config (bot_starting_capital in autonomous_config)
        2. Tradier account balance (if connected)
        3. Default fallback

        This is THE source of truth for starting capital.
        """
        cache_key = bot.value
        now = datetime.now(CENTRAL_TZ)

        # Check cache
        if not force_refresh and cache_key in self._capital_cache:
            cached = self._capital_cache[cache_key]
            age = (now - cached.last_updated).total_seconds()
            if age < self._cache_ttl:
                return cached

        tables = self.BOT_TABLES[bot]
        config_key = tables['config_key']

        starting_capital = None
        capital_source = 'default'
        tradier_connected = False
        tradier_balance = None

        # 1. Try database config first
        conn = self._get_connection()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT value FROM autonomous_config WHERE key = %s",
                    (config_key,)
                )
                row = cursor.fetchone()
                if row and row[0]:
                    try:
                        db_capital = float(row[0])
                        if db_capital > 0:
                            starting_capital = db_capital
                            capital_source = 'database'
                    except (ValueError, TypeError):
                        pass
                conn.close()
            except Exception as e:
                logger.error(f"Database capital lookup failed for {bot.value}: {e}")
                if conn:
                    conn.close()

        # 2. Check Tradier connection (for status info only, NOT for starting capital)
        # CRITICAL: Do NOT use Tradier balance as starting_capital!
        # Tradier balance = starting_capital + all P&L, using it would cause double-counting
        tradier_data = self._get_tradier_balance(sandbox=(bot in [BotName.ARES]))
        if tradier_data and tradier_data.get('connected'):
            tradier_connected = True
            tradier_balance = tradier_data.get('total_equity', 0)
            # Note: tradier_balance is current equity (starting + P&L), not starting capital

        # 3. Fall back to default
        if starting_capital is None:
            starting_capital = self.DEFAULT_CAPITAL[bot]
            capital_source = 'default'

        config = BotCapitalConfig(
            bot_name=bot.value,
            starting_capital=starting_capital,
            capital_source=capital_source,
            tradier_connected=tradier_connected,
            tradier_balance=tradier_balance,
            last_updated=now
        )

        # Cache it
        self._capital_cache[cache_key] = config

        return config

    def set_starting_capital(self, bot: BotName, capital: float) -> bool:
        """
        Set the starting capital for a bot in the database.
        This should be called when:
        1. User manually configures capital
        2. First trade is made (capture Tradier balance)
        """
        if capital <= 0:
            return False

        tables = self.BOT_TABLES[bot]
        config_key = tables['config_key']

        conn = self._get_connection()
        if not conn:
            return False

        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO autonomous_config (key, value)
                VALUES (%s, %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """, (config_key, str(capital)))
            conn.commit()
            conn.close()

            # Clear cache
            if bot.value in self._capital_cache:
                del self._capital_cache[bot.value]

            logger.info(f"Set {bot.value} starting capital to ${capital:,.2f}")
            return True
        except Exception as e:
            logger.error(f"Failed to set capital for {bot.value}: {e}")
            if conn:
                conn.close()
            return False

    def get_metrics_summary(self, bot: BotName) -> BotMetricsSummary:
        """
        Get complete metrics summary for a bot.

        This is THE authoritative source for all bot statistics.
        Frontend should NEVER calculate these values itself.
        """
        now = datetime.now(CENTRAL_TZ)
        today = now.strftime('%Y-%m-%d')

        # Get capital config (single source)
        capital_config = self.get_capital_config(bot)
        starting_capital = capital_config.starting_capital

        tables = self.BOT_TABLES[bot]
        positions_table = tables['positions']

        # Initialize with defaults
        total_realized = 0.0
        total_unrealized = 0.0
        today_realized = 0.0
        today_unrealized = 0.0
        total_trades = 0
        winning_trades = 0
        losing_trades = 0
        open_count = 0
        closed_count = 0
        high_water_mark = starting_capital
        max_drawdown_pct = 0.0

        conn = self._get_connection()
        if not conn:
            logger.warning(f"get_metrics_summary({bot.value}): Database connection failed, returning defaults")

        if conn:
            try:
                cursor = conn.cursor()

                # Get aggregate stats from database (excluding unrealized - we calculate that with MTM)
                # CRITICAL: Include 'partial_close' status - these are positions where one leg closed
                # but the other failed. They have realized_pnl and must be counted in metrics.
                cursor.execute(f"""
                    SELECT
                        COUNT(*) FILTER (WHERE status = 'open') as open_count,
                        COUNT(*) FILTER (WHERE status IN ('closed', 'expired', 'partial_close')) as closed_count,
                        COUNT(*) FILTER (WHERE status IN ('closed', 'expired', 'partial_close') AND realized_pnl > 0) as wins,
                        COUNT(*) FILTER (WHERE status IN ('closed', 'expired', 'partial_close') AND realized_pnl <= 0) as losses,
                        COALESCE(SUM(CASE WHEN status IN ('closed', 'expired', 'partial_close') THEN realized_pnl ELSE 0 END), 0) as total_realized,
                        COALESCE(SUM(CASE
                            WHEN status IN ('closed', 'expired', 'partial_close')
                            AND DATE(close_time AT TIME ZONE 'America/Chicago') = %s
                            THEN realized_pnl ELSE 0 END), 0) as today_realized
                    FROM {positions_table}
                """, (today,))

                row = cursor.fetchone()
                if row:
                    open_count = int(row[0] or 0)
                    closed_count = int(row[1] or 0)
                    winning_trades = int(row[2] or 0)
                    losing_trades = int(row[3] or 0)
                    total_realized = float(row[4] or 0)
                    today_realized = float(row[5] or 0)

                    # DEBUG: Log query results for visibility
                    logger.info(
                        f"get_metrics_summary({bot.value}): "
                        f"table={positions_table}, open={open_count}, closed={closed_count}, "
                        f"wins={winning_trades}, losses={losing_trades}, "
                        f"total_realized=${total_realized:.2f}, today_realized=${today_realized:.2f}"
                    )
                else:
                    logger.warning(f"get_metrics_summary({bot.value}): Query returned no rows from {positions_table}")

                total_trades = closed_count

                # CRITICAL: Calculate unrealized P&L using mark-to-market (NOT from stale DB column)
                # The positions table unrealized_pnl column is never updated with live values
                if open_count > 0 and MTM_AVAILABLE:
                    try:
                        # Iron Condor bots: ARES, TITAN, PEGASUS
                        if bot in [BotName.ARES, BotName.TITAN, BotName.PEGASUS]:
                            underlying = 'SPY' if bot == BotName.ARES else 'SPX'
                            cursor.execute(f"""
                                SELECT position_id, total_credit, contracts, spread_width,
                                       put_short_strike, put_long_strike, call_short_strike, call_long_strike,
                                       expiration
                                FROM {positions_table}
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
                                        total_unrealized += mtm['unrealized_pnl']
                                except Exception as pos_err:
                                    logger.debug(f"MTM failed for {bot.value} position {pos_id}: {pos_err}")

                        # Directional spread bots: ATHENA, ICARUS
                        elif bot in [BotName.ATHENA, BotName.ICARUS]:
                            cursor.execute(f"""
                                SELECT position_id, spread_type, entry_debit, contracts,
                                       long_strike, short_strike, expiration
                                FROM {positions_table}
                                WHERE status = 'open'
                            """)
                            open_positions = cursor.fetchall()

                            for pos in open_positions:
                                pos_id, spread_type, debit, contracts, long_strike, short_strike, exp = pos
                                if not all([debit, contracts, long_strike, short_strike, exp]):
                                    continue
                                try:
                                    exp_str = str(exp) if not isinstance(exp, str) else exp
                                    mtm = calculate_spread_mark_to_market(
                                        underlying='SPY',
                                        expiration=exp_str,
                                        long_strike=float(long_strike),
                                        short_strike=float(short_strike),
                                        spread_type=spread_type or 'call_debit',
                                        contracts=int(contracts),
                                        entry_debit=float(debit),
                                        use_cache=True
                                    )
                                    if mtm.get('success') and mtm.get('unrealized_pnl') is not None:
                                        total_unrealized += mtm['unrealized_pnl']
                                except Exception as pos_err:
                                    logger.debug(f"MTM failed for {bot.value} position {pos_id}: {pos_err}")

                    except Exception as mtm_err:
                        logger.warning(f"MTM calculation failed for {bot.value}: {mtm_err}")

                # Calculate high water mark from equity snapshots
                snapshots_table = tables['snapshots']
                try:
                    cursor.execute(f"""
                        SELECT MAX(balance) FROM {snapshots_table}
                    """)
                    hwm_row = cursor.fetchone()
                    if hwm_row and hwm_row[0]:
                        high_water_mark = max(starting_capital, float(hwm_row[0]))
                except Exception:
                    pass  # Table might not exist

                conn.close()
            except Exception as e:
                logger.error(f"Failed to get metrics for {bot.value}: {e}")
                if conn:
                    conn.close()

        # Calculate derived metrics
        total_pnl = total_realized + total_unrealized
        today_pnl = today_realized + today_unrealized
        current_equity = starting_capital + total_pnl

        # Win rate as percentage (0-100), not decimal
        win_rate = 0.0
        if total_trades > 0:
            win_rate = round((winning_trades / total_trades) * 100, 1)

        # Return percentage
        total_return_pct = 0.0
        if starting_capital > 0:
            total_return_pct = round((total_pnl / starting_capital) * 100, 2)

        # Max drawdown (simplified - from high water mark)
        if high_water_mark > 0:
            max_drawdown_pct = round(((high_water_mark - current_equity) / high_water_mark) * 100, 2)
            max_drawdown_pct = max(0, max_drawdown_pct)  # Can't be negative

        return BotMetricsSummary(
            bot_name=bot.value,
            starting_capital=round(starting_capital, 2),
            current_equity=round(current_equity, 2),
            capital_source=capital_config.capital_source,
            total_realized_pnl=round(total_realized, 2),
            total_unrealized_pnl=round(total_unrealized, 2),
            total_pnl=round(total_pnl, 2),
            today_realized_pnl=round(today_realized, 2),
            today_unrealized_pnl=round(today_unrealized, 2),
            today_pnl=round(today_pnl, 2),
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            open_positions=open_count,
            closed_positions=closed_count,
            total_return_pct=total_return_pct,
            max_drawdown_pct=max_drawdown_pct,
            high_water_mark=round(high_water_mark, 2),
            calculated_at=now
        )

    def get_equity_curve(
        self,
        bot: BotName,
        days: int = 90,
        include_unrealized: bool = True
    ) -> Dict[str, Any]:
        """
        Get historical equity curve for a bot.

        CRITICAL: Uses the SAME starting capital as intraday chart.
        """
        now = datetime.now(CENTRAL_TZ)
        today = now.strftime('%Y-%m-%d')
        start_date = (now - timedelta(days=days)).strftime('%Y-%m-%d')

        # Get authoritative capital
        capital_config = self.get_capital_config(bot)
        starting_capital = capital_config.starting_capital

        tables = self.BOT_TABLES[bot]
        positions_table = tables['positions']

        equity_curve: List[EquityCurvePoint] = []

        conn = self._get_connection()
        if not conn:
            return self._empty_equity_curve(bot, starting_capital)

        try:
            cursor = conn.cursor()

            # Get daily P&L aggregates (include partial_close - positions with one leg closed)
            cursor.execute(f"""
                SELECT
                    DATE(close_time AT TIME ZONE 'America/Chicago') as trade_date,
                    SUM(realized_pnl) as daily_pnl,
                    COUNT(*) as trade_count
                FROM {positions_table}
                WHERE status IN ('closed', 'expired', 'partial_close')
                AND DATE(close_time AT TIME ZONE 'America/Chicago') >= %s
                GROUP BY DATE(close_time AT TIME ZONE 'America/Chicago')
                ORDER BY trade_date
            """, (start_date,))

            daily_data = cursor.fetchall()

            # Get current unrealized P&L
            unrealized_pnl = 0.0
            open_count = 0
            if include_unrealized:
                cursor.execute(f"""
                    SELECT
                        COALESCE(SUM(COALESCE(unrealized_pnl, 0)), 0),
                        COUNT(*)
                    FROM {positions_table}
                    WHERE status = 'open'
                """)
                unr_row = cursor.fetchone()
                if unr_row:
                    unrealized_pnl = float(unr_row[0] or 0)
                    open_count = int(unr_row[1] or 0)

            conn.close()

            # Build equity curve
            cumulative_pnl = 0.0
            high_water = starting_capital

            # Add starting point
            if daily_data:
                first_date = str(daily_data[0][0])
                equity_curve.append(EquityCurvePoint(
                    date=first_date,
                    equity=starting_capital,
                    daily_pnl=0,
                    cumulative_pnl=0,
                    realized_pnl=0,
                    unrealized_pnl=0,
                    drawdown_pct=0,
                    trade_count=0,
                    return_pct=0
                ))

            for trade_date, daily_pnl, trade_count in daily_data:
                date_str = str(trade_date)
                cumulative_pnl += float(daily_pnl or 0)
                current_equity = starting_capital + cumulative_pnl

                # Update high water mark
                if current_equity > high_water:
                    high_water = current_equity

                # Calculate drawdown
                drawdown_pct = 0.0
                if high_water > 0:
                    drawdown_pct = round(((high_water - current_equity) / high_water) * 100, 2)
                    drawdown_pct = max(0, drawdown_pct)

                return_pct = round((cumulative_pnl / starting_capital) * 100, 2) if starting_capital > 0 else 0

                equity_curve.append(EquityCurvePoint(
                    date=date_str,
                    equity=round(current_equity, 2),
                    daily_pnl=round(float(daily_pnl or 0), 2),
                    cumulative_pnl=round(cumulative_pnl, 2),
                    realized_pnl=round(cumulative_pnl, 2),
                    unrealized_pnl=0,
                    drawdown_pct=drawdown_pct,
                    trade_count=int(trade_count or 0),
                    return_pct=return_pct
                ))

            # Add today's point with unrealized
            total_pnl = cumulative_pnl + unrealized_pnl
            current_equity = starting_capital + total_pnl

            # Check if we need to add/update today's point
            if equity_curve and equity_curve[-1].date == today:
                # Update existing today entry
                equity_curve[-1] = EquityCurvePoint(
                    date=today,
                    equity=round(current_equity, 2),
                    daily_pnl=round(equity_curve[-1].daily_pnl + unrealized_pnl, 2),
                    cumulative_pnl=round(total_pnl, 2),
                    realized_pnl=round(cumulative_pnl, 2),
                    unrealized_pnl=round(unrealized_pnl, 2),
                    drawdown_pct=equity_curve[-1].drawdown_pct,
                    trade_count=equity_curve[-1].trade_count,
                    return_pct=round((total_pnl / starting_capital) * 100, 2) if starting_capital > 0 else 0
                )
            else:
                # Add new today entry
                equity_curve.append(EquityCurvePoint(
                    date=today,
                    equity=round(current_equity, 2),
                    daily_pnl=round(unrealized_pnl, 2),
                    cumulative_pnl=round(total_pnl, 2),
                    realized_pnl=round(cumulative_pnl, 2),
                    unrealized_pnl=round(unrealized_pnl, 2),
                    drawdown_pct=0,
                    trade_count=0,
                    return_pct=round((total_pnl / starting_capital) * 100, 2) if starting_capital > 0 else 0
                ))

            # Calculate max drawdown
            max_drawdown = max((p.drawdown_pct for p in equity_curve), default=0)

            return {
                "success": True,
                "bot": bot.value,
                "equity_curve": [p.to_dict() for p in equity_curve],
                "summary": {
                    "starting_capital": round(starting_capital, 2),
                    "current_equity": round(current_equity, 2),
                    "total_pnl": round(total_pnl, 2),
                    "realized_pnl": round(cumulative_pnl, 2),
                    "unrealized_pnl": round(unrealized_pnl, 2),
                    "max_drawdown_pct": round(max_drawdown, 2),
                    "total_return_pct": round((total_pnl / starting_capital) * 100, 2) if starting_capital > 0 else 0,
                    "total_trades": sum(p.trade_count for p in equity_curve),
                    "capital_source": capital_config.capital_source,
                },
                "capital_config": capital_config.to_dict()
            }

        except Exception as e:
            logger.error(f"Failed to build equity curve for {bot.value}: {e}")
            import traceback
            traceback.print_exc()
            if conn:
                conn.close()
            return self._empty_equity_curve(bot, starting_capital)

    def get_intraday_equity(self, bot: BotName, date_str: Optional[str] = None) -> Dict[str, Any]:
        """
        Get intraday equity curve for a bot.

        CRITICAL: Uses the SAME starting capital as historical chart.
        """
        now = datetime.now(CENTRAL_TZ)
        target_date = date_str or now.strftime('%Y-%m-%d')
        current_time = now.strftime('%H:%M:%S')

        # Get authoritative capital (SAME as historical!)
        capital_config = self.get_capital_config(bot)
        starting_capital = capital_config.starting_capital

        tables = self.BOT_TABLES[bot]
        positions_table = tables['positions']
        snapshots_table = tables['snapshots']

        data_points: List[IntradayEquityPoint] = []

        conn = self._get_connection()
        if not conn:
            return self._empty_intraday(bot, starting_capital, target_date)

        try:
            cursor = conn.cursor()

            # Get P&L data from positions table (handle missing table gracefully)
            prev_realized = 0.0
            today_realized = 0.0
            today_closed_count = 0
            open_count = 0

            try:
                # Get total realized P&L up to (but not including) target date
                # Include partial_close - positions where one leg closed but other failed
                cursor.execute(f"""
                    SELECT COALESCE(SUM(realized_pnl), 0)
                    FROM {positions_table}
                    WHERE status IN ('closed', 'expired', 'partial_close')
                    AND DATE(close_time AT TIME ZONE 'America/Chicago') < %s
                """, (target_date,))
                prev_realized = float(cursor.fetchone()[0] or 0)

                # Get target date's realized P&L
                cursor.execute(f"""
                    SELECT COALESCE(SUM(realized_pnl), 0), COUNT(*)
                    FROM {positions_table}
                    WHERE status IN ('closed', 'expired', 'partial_close')
                    AND DATE(close_time AT TIME ZONE 'America/Chicago') = %s
                """, (target_date,))
                row = cursor.fetchone()
                today_realized = float(row[0] or 0)
                today_closed_count = int(row[1] or 0)

                # Get open positions count
                cursor.execute(f"""
                    SELECT COUNT(*) FROM {positions_table} WHERE status = 'open'
                """)
                open_count = int(cursor.fetchone()[0] or 0)
            except Exception as table_err:
                # Positions table might not exist yet - use defaults
                logger.debug(f"Positions table {positions_table} not ready: {table_err}")
                prev_realized = 0.0
                today_realized = 0.0
                today_closed_count = 0
                open_count = 0

            # Get intraday snapshots FIRST (these have live unrealized P&L from scheduler)
            snapshots = []
            try:
                cursor.execute(f"""
                    SELECT timestamp, balance, unrealized_pnl, realized_pnl, open_positions
                    FROM {snapshots_table}
                    WHERE DATE(timestamp AT TIME ZONE 'America/Chicago') = %s
                    ORDER BY timestamp ASC
                """, (target_date,))
                snapshots = cursor.fetchall()
            except Exception:
                snapshots = []  # Table might not exist

            # Use latest snapshot's unrealized P&L for "live" point (scheduler calculates this with live pricing)
            # Only fall back to positions table if no snapshots exist
            current_unrealized = 0.0
            if snapshots:
                # Use the most recent snapshot's unrealized P&L
                latest_snap = snapshots[-1]
                current_unrealized = float(latest_snap[2] or 0)  # unrealized_pnl column
                # Update open_count from latest snapshot if available
                if latest_snap[4] is not None:
                    open_count = int(latest_snap[4])
            else:
                # Fallback: query positions table (may be stale, handle missing table)
                try:
                    cursor.execute(f"""
                        SELECT COALESCE(SUM(COALESCE(unrealized_pnl, 0)), 0)
                        FROM {positions_table}
                        WHERE status = 'open'
                    """)
                    current_unrealized = float(cursor.fetchone()[0] or 0)
                except Exception:
                    current_unrealized = 0.0  # Table doesn't exist

            conn.close()

            # Calculate market open equity
            # This is: starting_capital + all realized P&L before today
            market_open_equity = starting_capital + prev_realized

            # Add market open point
            data_points.append(IntradayEquityPoint(
                timestamp=f"{target_date}T08:30:00",
                time="08:30:00",
                equity=round(market_open_equity, 2),
                cumulative_pnl=round(prev_realized, 2),
                realized_pnl=round(prev_realized, 2),
                unrealized_pnl=0,
                open_positions=0
            ))

            all_equities = [market_open_equity]

            # Add snapshot points
            for snap in snapshots:
                ts, balance, snap_unrealized, snap_realized, snap_open = snap
                snap_time = ts.astimezone(CENTRAL_TZ) if ts.tzinfo else ts

                snap_unrealized_val = float(snap_unrealized or 0)
                snap_realized_val = float(snap_realized or 0) if snap_realized else prev_realized + today_realized
                snap_equity = float(balance) if balance else (starting_capital + snap_realized_val + snap_unrealized_val)

                all_equities.append(snap_equity)

                data_points.append(IntradayEquityPoint(
                    timestamp=snap_time.isoformat(),
                    time=snap_time.strftime('%H:%M:%S'),
                    equity=round(snap_equity, 2),
                    cumulative_pnl=round(snap_realized_val + snap_unrealized_val, 2),
                    realized_pnl=round(snap_realized_val, 2),
                    unrealized_pnl=round(snap_unrealized_val, 2),
                    open_positions=int(snap_open or 0)
                ))

            # Add current live point if viewing today
            if target_date == now.strftime('%Y-%m-%d'):
                total_realized = prev_realized + today_realized
                total_pnl = total_realized + current_unrealized
                current_equity = starting_capital + total_pnl
                all_equities.append(current_equity)

                data_points.append(IntradayEquityPoint(
                    timestamp=now.isoformat(),
                    time=current_time,
                    equity=round(current_equity, 2),
                    cumulative_pnl=round(total_pnl, 2),
                    realized_pnl=round(total_realized, 2),
                    unrealized_pnl=round(current_unrealized, 2),
                    open_positions=open_count
                ))

            # Calculate day stats
            high_of_day = max(all_equities) if all_equities else market_open_equity
            low_of_day = min(all_equities) if all_equities else market_open_equity

            # Day P&L = today's realized + current unrealized
            day_pnl = today_realized + current_unrealized
            current_equity = starting_capital + prev_realized + today_realized + current_unrealized

            return {
                "success": True,
                "bot": bot.value,
                "date": target_date,
                "data_points": [p.to_dict() for p in data_points],
                "current_equity": round(current_equity, 2),
                "day_pnl": round(day_pnl, 2),
                "day_realized": round(today_realized, 2),
                "day_unrealized": round(current_unrealized, 2),
                "starting_equity": round(starting_capital, 2),
                "market_open_equity": round(market_open_equity, 2),
                "high_of_day": round(high_of_day, 2),
                "low_of_day": round(low_of_day, 2),
                "snapshots_count": len(snapshots),
                "capital_source": capital_config.capital_source,
                "capital_config": capital_config.to_dict()
            }

        except Exception as e:
            logger.error(f"Failed to build intraday equity for {bot.value}: {e}")
            import traceback
            traceback.print_exc()
            if conn:
                conn.close()
            return self._empty_intraday(bot, starting_capital, target_date)

    def _empty_equity_curve(self, bot: BotName, starting_capital: float) -> Dict[str, Any]:
        """Return empty equity curve structure"""
        today = datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d')
        return {
            "success": True,
            "bot": bot.value,
            "equity_curve": [{
                "date": today,
                "equity": starting_capital,
                "daily_pnl": 0,
                "cumulative_pnl": 0,
                "realized_pnl": 0,
                "unrealized_pnl": 0,
                "drawdown_pct": 0,
                "trade_count": 0,
                "return_pct": 0
            }],
            "summary": {
                "starting_capital": starting_capital,
                "current_equity": starting_capital,
                "total_pnl": 0,
                "realized_pnl": 0,
                "unrealized_pnl": 0,
                "max_drawdown_pct": 0,
                "total_return_pct": 0,
                "total_trades": 0,
                "capital_source": "default"
            },
            "message": "No trading data found"
        }

    def _empty_intraday(self, bot: BotName, starting_capital: float, date_str: str) -> Dict[str, Any]:
        """Return empty intraday structure"""
        now = datetime.now(CENTRAL_TZ)
        return {
            "success": True,
            "bot": bot.value,
            "date": date_str,
            "data_points": [{
                "timestamp": now.isoformat(),
                "time": now.strftime('%H:%M:%S'),
                "equity": starting_capital,
                "cumulative_pnl": 0,
                "realized_pnl": 0,
                "unrealized_pnl": 0,
                "open_positions": 0
            }],
            "current_equity": starting_capital,
            "day_pnl": 0,
            "day_realized": 0,
            "day_unrealized": 0,
            "starting_equity": starting_capital,
            "market_open_equity": starting_capital,
            "high_of_day": starting_capital,
            "low_of_day": starting_capital,
            "snapshots_count": 0,
            "capital_source": "default",
            "message": "No intraday data found"
        }

    def format_position(
        self,
        position_data: Dict[str, Any],
        is_open: bool = True
    ) -> Dict[str, Any]:
        """
        Format a position with consistent field names.

        ALWAYS includes both max_profit AND premium_collected with same value.
        """
        # Calculate max_profit from position data
        total_credit = float(position_data.get('total_credit') or position_data.get('total_cr') or 0)
        contracts = int(position_data.get('contracts') or 1)
        max_profit = total_credit * 100 * contracts

        # Always include BOTH fields
        formatted = {
            **position_data,
            'max_profit': round(max_profit, 2),
            'premium_collected': round(max_profit, 2),  # SAME VALUE!
        }

        # Ensure win probability is percentage (0-100), not decimal
        if 'oracle_win_probability' in formatted:
            owp = formatted['oracle_win_probability']
            if owp is not None and owp <= 1:
                formatted['oracle_win_probability'] = round(owp * 100, 1)

        if 'min_win_probability' in formatted:
            mwp = formatted['min_win_probability']
            if mwp is not None and mwp <= 1:
                formatted['min_win_probability'] = round(mwp * 100, 1)

        return formatted


# Singleton instance
_metrics_service: Optional[BotMetricsService] = None


def get_metrics_service() -> BotMetricsService:
    """Get the singleton metrics service instance"""
    global _metrics_service
    if _metrics_service is None:
        _metrics_service = BotMetricsService()
    return _metrics_service
