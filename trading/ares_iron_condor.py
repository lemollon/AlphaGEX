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

logger = logging.getLogger(__name__)


class TradingMode(Enum):
    """Trading execution mode"""
    PAPER = "paper"       # Sandbox/Paper trading
    LIVE = "live"         # Live trading with real money
    BACKTEST = "backtest" # Backtesting mode (no execution)


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
    # Risk parameters
    risk_per_trade_pct: float = 10.0     # 10% of capital per trade
    spread_width: float = 10.0            # $10 wide spreads (SPX)
    spread_width_spy: float = 2.0         # $2 wide spreads (SPY for sandbox)
    sd_multiplier: float = 0.5            # 0.5 SD strikes (closer to ATM for better liquidity)

    # Execution parameters
    ticker: str = "SPX"                   # Trade SPX in production
    sandbox_ticker: str = "SPY"           # Trade SPY in sandbox (better data)
    use_0dte: bool = True                 # Use 0DTE options
    max_contracts: int = 1000             # Max contracts per trade
    min_credit_per_spread: float = 1.50   # Minimum credit to accept (SPX)
    min_credit_per_spread_spy: float = 0.02  # Minimum credit (SPY - lowered for liquidity)

    # Trade management
    use_stop_loss: bool = False           # NO stop loss (defined risk)
    profit_target_pct: float = 50         # Take profit at 50% of max

    # Trading schedule
    trade_every_day: bool = True          # Trade Mon-Fri
    entry_time_start: str = "09:35"       # Entry window start (after market open)
    entry_time_end: str = "15:55"         # Entry window end (before close)


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

        self.tz = ZoneInfo("America/New_York")

        # Initialize Tradier clients
        # When TRADIER_SANDBOX=true: Use sandbox for BOTH market data AND orders
        # When TRADIER_SANDBOX=false: Use production for market data, sandbox for paper orders
        self.tradier = None  # Primary client for market data
        self.tradier_sandbox = None  # Sandbox client for paper trade submission

        if TRADIER_AVAILABLE and mode != TradingMode.BACKTEST:
            from unified_config import APIConfig
            is_sandbox_mode = APIConfig.TRADIER_SANDBOX

            if is_sandbox_mode:
                # Sandbox-only mode: Use sandbox API for everything (market data + orders)
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
                        logger.info(f"ARES: Tradier SANDBOX client initialized (sandbox-only mode)")
                    else:
                        logger.warning("ARES: Tradier sandbox credentials not configured")
                except Exception as e:
                    logger.warning(f"ARES: Failed to initialize Tradier sandbox: {e}")
            else:
                # Production mode: Use production API for market data
                try:
                    self.tradier = TradierDataFetcher(sandbox=False)
                    logger.info(f"ARES: Tradier PRODUCTION client initialized (for SPX market data)")
                except Exception as e:
                    logger.warning(f"ARES: Failed to initialize Tradier production: {e}")

                # Sandbox API for paper trade submission (only in PAPER mode)
                if mode == TradingMode.PAPER:
                    try:
                        sandbox_key = APIConfig.TRADIER_SANDBOX_API_KEY or APIConfig.TRADIER_API_KEY
                        sandbox_account = APIConfig.TRADIER_SANDBOX_ACCOUNT_ID or APIConfig.TRADIER_ACCOUNT_ID

                        if sandbox_key and sandbox_account:
                            self.tradier_sandbox = TradierDataFetcher(
                                api_key=sandbox_key,
                                account_id=sandbox_account,
                                sandbox=True
                            )
                            logger.info(f"ARES: Tradier SANDBOX client initialized (for paper trade submission)")
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

        # Performance tracking
        self.total_pnl = 0
        self.high_water_mark = initial_capital
        self.trade_count = 0
        self.win_count = 0

        # Position ID counter
        self._position_counter = 0

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

    def _generate_position_id(self) -> str:
        """Generate unique position ID"""
        self._position_counter += 1
        now = datetime.now(self.tz)
        return f"ARES-{now.strftime('%Y%m%d')}-{self._position_counter:04d}"

    def get_trading_ticker(self) -> str:
        """
        Get the ticker to trade.

        In PAPER mode with sandbox: Uses SPY (Tradier sandbox has SPY options)
        In LIVE mode: Uses SPX/SPXW for higher premium
        """
        # Use SPY in sandbox mode (Tradier sandbox doesn't support SPX options)
        if self.tradier_sandbox is not None:
            return self.config.sandbox_ticker  # SPY for sandbox
        return self.config.ticker  # SPX for production

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

            if ticker == "SPY":
                # Sandbox mode - use SPY directly
                quote = self.tradier.get_quote("SPY")
                if quote and quote.get('last'):
                    underlying_price = float(quote['last'])
                else:
                    logger.warning("ARES: Could not get SPY quote")
                    return None
            else:
                # Production mode - use SPX
                quote = self.tradier.get_quote("$SPX.X")
                if not quote or not quote.get('last'):
                    # Fallback to SPY * 10 estimate
                    spy_quote = self.tradier.get_quote("SPY")
                    if spy_quote and spy_quote.get('last'):
                        underlying_price = float(spy_quote['last']) * 10
                        logger.info("ARES: Using SPY*10 as SPX proxy")
                    else:
                        logger.warning("ARES: Could not get SPX or SPY quote")
                        return None
                else:
                    underlying_price = float(quote['last'])

            # Get VIX for expected move calculation
            vix = 15.0  # Default if not available
            vix_quote = self.tradier.get_quote("$VIX.X")
            if vix_quote and vix_quote.get('last'):
                vix = float(vix_quote['last'])
            else:
                # Try alternate symbol
                vix_quote = self.tradier.get_quote("VIX")
                if vix_quote and vix_quote.get('last'):
                    vix = float(vix_quote['last'])
                else:
                    logger.info("ARES: VIX not available, using default 15.0")

            # Calculate expected move (1 SD for 0DTE)
            iv = vix / 100
            expected_move = underlying_price * iv * math.sqrt(1/252)

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
            # Get advice from Oracle
            advice = self.oracle.get_ares_advice(
                context,
                use_gex_walls=True,
                use_claude_validation=True
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
        expiration: str
    ) -> Optional[Dict]:
        """
        Find optimal Iron Condor strikes at 1 SD from current price.

        Args:
            underlying_price: Current price (SPX or SPY)
            expected_move: Expected move (1 SD)
            expiration: Expiration date (YYYY-MM-DD)

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

            # Target strikes at SD distance
            # For SPY, round to $1 strikes; for SPX, round to $5 strikes
            sd = self.config.sd_multiplier
            strike_rounding = 1 if ticker == "SPY" else 5
            put_target = round((underlying_price - sd * expected_move) / strike_rounding) * strike_rounding
            call_target = round((underlying_price + sd * expected_move) / strike_rounding) * strike_rounding

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

            # Log decision with Oracle advice and REAL alternatives from strike selection
            self._log_entry_decision(position, market_data, oracle_advice, decision_tracker, ic_strikes)

            # Save position to database for persistence
            self._save_position_to_db(position)

            return position

        except Exception as e:
            logger.error(f"ARES: Error executing Iron Condor: {e}")
            return None

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
                f"1) Check trading window (9:35 AM - 3:30 PM ET), "
                f"2) Verify no existing position for today, "
                f"3) Get market data (price, VIX, expected move), "
                f"4) Consult Oracle AI for trade/skip advice, "
                f"5) Find 1 SD Iron Condor strikes if trading, "
                f"6) Execute via Tradier API (PAPER/LIVE mode)."
            )

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
                market_context=MarketContext(
                    timestamp=now.isoformat(),
                    spot_price=market_data.get('underlying_price', 0) if market_data else 0,
                    spot_source=DataSource.TRADIER_LIVE,
                    vix=market_data.get('vix', 0) if market_data else 0
                ) if market_data else None,
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

                    comprehensive_decision = BotDecision(
                        bot_name="ARES",
                        decision_type="SKIP",
                        action="SKIP",
                        symbol=self.get_trading_ticker(),
                        strategy="aggressive_iron_condor",
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

            decision = TradeDecision(
                decision_id=position.position_id,
                timestamp=datetime.now(self.tz).isoformat(),
                decision_type=DecisionType.ENTRY_SIGNAL,
                bot_name=BotName.ARES,
                what=f"SELL Iron Condor {position.contracts}x {position.put_short_strike}P/{position.call_short_strike}C @ ${position.total_credit:.2f}",
                why=f"1 SD Iron Condor for daily premium collection. VIX: {market_data['vix']:.1f}",
                action="SELL",
                symbol=self.config.ticker,
                strategy="aggressive_iron_condor",
                legs=legs,
                underlying_price_at_entry=market_data['underlying_price'],
                market_context=MarketContext(
                    timestamp=datetime.now(self.tz).isoformat(),
                    spot_price=market_data['underlying_price'],
                    spot_source=DataSource.TRADIER_LIVE,
                    vix=market_data['vix']
                ),
                reasoning=DecisionReasoning(
                    primary_reason="Daily aggressive Iron Condor for 10% monthly target",
                    supporting_factors=[
                        f"VIX at {market_data['vix']:.1f}",
                        f"1 SD expected move: ${market_data['expected_move']:.0f}",
                        f"Credit received: ${position.total_credit:.2f}",
                    ],
                    risk_factors=[
                        f"Max loss: ${position.max_loss * 100 * position.contracts:,.0f}",
                        "No stop loss - letting theta work"
                    ]
                ),
                position_size_dollars=position.total_credit * 100 * position.contracts,
                position_size_contracts=position.contracts,
                max_risk_dollars=position.max_loss * 100 * position.contracts
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

                    comprehensive_decision = BotDecision(
                        bot_name="ARES",
                        decision_type="ENTRY",
                        action="SELL",
                        symbol=self.get_trading_ticker(),
                        strategy="aggressive_iron_condor",
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

        # Start a new scan cycle for session tracking
        if self.session_tracker:
            cycle_num = self.session_tracker.new_cycle()
            logger.info(f"ARES: Starting scan cycle {cycle_num} for session {self.session_tracker.session_id}")

        # Create decision tracker for API calls, errors, and timing
        decision_tracker = None
        if BOT_LOGGER_AVAILABLE and DecisionTracker:
            decision_tracker = DecisionTracker()
            decision_tracker.start()

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
                reason="Outside trading window (9:35 AM - 3:30 PM ET)",
                market_data=None,
                oracle_advice=None,
                alternatives=["Wait for trading window to open"],
                decision_tracker=decision_tracker
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
            return result

        result['market_data'] = market_data

        logger.info(f"  Underlying: ${market_data['underlying_price']:,.2f}")
        logger.info(f"  VIX: {market_data['vix']:.1f}")
        logger.info(f"  Expected Move (1 SD): ${market_data['expected_move']:.2f}")

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
                'reasoning': oracle_advice.reasoning
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
                return result

            # Store Oracle's suggestions for use
            oracle_risk_pct = oracle_advice.suggested_risk_pct
            oracle_sd_mult = oracle_advice.suggested_sd_multiplier

            logger.info(f"  Oracle Advice: {oracle_advice.advice.value}")
            logger.info(f"  Oracle Win Prob: {oracle_advice.win_probability:.1%}")
        else:
            logger.info("  Oracle: Not available, using default parameters")

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
            return result

        # Calculate expected move with SD multiplier
        # Use config's SD multiplier if explicitly set, otherwise use Oracle's suggestion
        adjusted_expected_move = market_data['expected_move']
        effective_sd_mult = self.config.sd_multiplier  # Default to config
        if self.config.sd_multiplier == 1.0 and oracle_sd_mult:
            # Only use Oracle's suggestion if config is at default
            effective_sd_mult = oracle_sd_mult
        adjusted_expected_move = market_data['expected_move'] * effective_sd_mult
        logger.info(f"  SD Mult: {effective_sd_mult:.2f} (config={self.config.sd_multiplier}, oracle={oracle_sd_mult}) -> Adjusted Move: ${adjusted_expected_move:.2f}")

        # Find Iron Condor strikes (with Oracle's SD multiplier applied)
        # Track option chain API call
        if decision_tracker:
            with decision_tracker.track_api("tradier", "option_chain"):
                ic_strikes = self.find_iron_condor_strikes(
                    market_data['underlying_price'],
                    adjusted_expected_move,
                    expiration
                )
        else:
            ic_strikes = self.find_iron_condor_strikes(
                market_data['underlying_price'],
                adjusted_expected_move,
                expiration
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
            return result

        logger.info(f"  IC Strikes: {ic_strikes['put_long_strike']}/{ic_strikes['put_short_strike']}P - "
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
            conn.close()
            logger.info(f"ARES: Saved position {position.position_id} to database")
            return True

        except Exception as e:
            logger.error(f"ARES: Failed to save position to database: {e}")
            return False

    def _update_position_in_db(self, position: IronCondorPosition) -> bool:
        """
        Update a position's status in the database (e.g., when closed).

        Args:
            position: IronCondorPosition to update

        Returns:
            True if updated successfully
        """
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
            conn.close()
            logger.info(f"ARES: Updated position {position.position_id} in database")

            # Record outcome to Oracle feedback loop if position closed
            if position.status in ('closed', 'expired') and hasattr(position, 'realized_pnl'):
                self._record_oracle_outcome(position)

            return True

        except Exception as e:
            logger.error(f"ARES: Failed to update position in database: {e}")
            return False

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
            Dict with account info, positions, and recent orders
        """
        result = {
            'success': False,
            'mode': self.mode.value,
            'account': {},
            'positions': [],
            'orders': [],
            'errors': []
        }

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

            # Get recent orders
            try:
                orders = tradier_client.get_orders()
                if orders:
                    # Only include recent orders (last 10)
                    result['orders'] = orders[:10] if len(orders) > 10 else orders
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
                    # Get enough days of history to cover the date
                    days_back = (datetime.now(self.tz) - datetime.strptime(for_date, '%Y-%m-%d').replace(tzinfo=self.tz)).days + 5
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
                TradeDecision, DecisionType, BotName, MarketContext,
                DecisionReasoning, TradeLeg, DataSource
            )

            now = datetime.now(self.tz)

            # Create expiration decision
            decision = TradeDecision(
                decision_id=f"{position.position_id}-EXP",
                timestamp=now.isoformat(),
                decision_type=DecisionType.EXIT_SIGNAL,
                bot_name=BotName.ARES,
                what=f"EXPIRED Iron Condor {position.contracts}x {position.put_short_strike}/{position.call_short_strike} - {outcome}",
                why=f"0DTE expiration. {self.get_trading_ticker()} closed at ${closing_price:.2f}. " +
                    f"Put short: ${position.put_short_strike}, Call short: ${position.call_short_strike}. " +
                    f"P&L: ${position.realized_pnl:.2f}",
                action="EXPIRED",
                symbol=self.get_trading_ticker(),
                strategy="ARES_IRON_CONDOR",
                underlying_price_at_exit=closing_price,
                actual_pnl=position.realized_pnl,
                legs=[
                    TradeLeg(leg_id=1, action="EXPIRED", option_type="put", strike=position.put_long_strike,
                            expiration=position.expiration, realized_pnl=0),
                    TradeLeg(leg_id=2, action="EXPIRED", option_type="put", strike=position.put_short_strike,
                            expiration=position.expiration, entry_price=position.put_credit, realized_pnl=0),
                    TradeLeg(leg_id=3, action="EXPIRED", option_type="call", strike=position.call_short_strike,
                            expiration=position.expiration, entry_price=position.call_credit, realized_pnl=0),
                    TradeLeg(leg_id=4, action="EXPIRED", option_type="call", strike=position.call_long_strike,
                            expiration=position.expiration, realized_pnl=0),
                ],
                market_context=MarketContext(
                    timestamp=now.isoformat(),
                    spot_price=closing_price,
                    spot_source=DataSource.TRADIER_LIVE
                ),
                reasoning=DecisionReasoning(
                    primary_reason=f"0DTE expiration - {outcome}",
                    supporting_factors=[
                        f"Closing price: ${closing_price:.2f}",
                        f"Put short strike: ${position.put_short_strike}",
                        f"Call short strike: ${position.call_short_strike}",
                        f"Credit received: ${position.total_credit:.2f}"
                    ],
                    risk_factors=[]
                ),
                position_size_contracts=position.contracts,
                max_risk_dollars=position.max_loss * 100 * position.contracts,
                outcome_notes=outcome
            )

            self.decision_logger.log_decision(decision)

        except Exception as e:
            logger.debug(f"ARES EOD: Could not log expiration decision: {e}")

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
                'sandbox_ticker': self.config.sandbox_ticker
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
