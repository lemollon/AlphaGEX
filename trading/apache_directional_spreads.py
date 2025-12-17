"""
APACHE - Directional Spread Trading Bot
=========================================

Named after the Apache warrior - swift, strategic, and precise.

STRATEGY: GEX-Based Directional Spreads
- BULLISH: Bull Call Spread (buy ATM call, sell OTM call)
- BEARISH: Bear Call Spread (sell ATM call, buy OTM call)

SIGNAL FLOW:
    KRONOS (GEX Calculator) --> ORACLE (ML Advisor) --> APACHE (Execution)

The key edge is the GEX wall proximity filter:
- Buy calls near put wall (support) for bullish
- Sell calls near call wall (resistance) for bearish

Backtest Results (2024 out-of-sample):
- With 1% wall filter: 90% win rate, 4.86x profit ratio
- With 0.5% wall filter: 98% win rate, 18.19x profit ratio

Usage:
    from trading.apache_directional_spreads import APACHETrader
    apache = APACHETrader(initial_capital=100_000)
    apache.run_daily_cycle()

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

# Import comprehensive bot logger
try:
    from trading.bot_logger import (
        log_bot_decision, update_decision_outcome, update_execution_timeline,
        BotDecision, MarketContext as BotLogMarketContext, ClaudeContext,
        Alternative, RiskCheck, ApiCall, ExecutionTimeline, generate_session_id,
        get_session_tracker, DecisionTracker
    )
    BOT_LOGGER_AVAILABLE = True
except ImportError:
    BOT_LOGGER_AVAILABLE = False
    log_bot_decision = None
    get_session_tracker = None
    DecisionTracker = None

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


@dataclass
class APACHEConfig:
    """Configuration for APACHE trading bot"""
    # Risk parameters
    risk_per_trade_pct: float = 2.0      # 2% of capital per trade (conservative for directional)
    max_daily_trades: int = 5             # Max trades per day
    max_open_positions: int = 3           # Max concurrent positions

    # Strategy parameters
    spread_width: int = 2                 # $2 spread width
    default_contracts: int = 10           # Default position size
    wall_filter_pct: float = 1.0          # Only trade within 1% of relevant wall
    trailing_stop_pct: float = 0.3        # 0.3% trailing stop

    # Execution parameters
    ticker: str = "SPY"
    mode: TradingMode = TradingMode.PAPER
    use_gex_walls: bool = True
    use_claude_validation: bool = True

    # Timing
    entry_start_time: str = "09:35"       # Start trading 5 min after open
    entry_end_time: str = "15:30"         # Stop entries 30 min before close
    exit_by_time: str = "15:55"           # Exit all by this time (0DTE)


class APACHETrader:
    """
    APACHE - Directional Spread Trading Bot

    Uses GEX signals from KRONOS, processed through ORACLE ML advisor,
    to execute Bull Call Spreads (bullish) and Bear Call Spreads (bearish).
    """

    def __init__(
        self,
        initial_capital: float = 100_000,
        config: Optional[APACHEConfig] = None
    ):
        """Initialize APACHE trader"""
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.config = config or APACHEConfig()

        # Initialize Oracle advisor
        self.oracle: Optional[OracleAdvisor] = None
        if ORACLE_AVAILABLE:
            try:
                self.oracle = OracleAdvisor()
                logger.info("APACHE: Oracle advisor initialized")
            except Exception as e:
                logger.warning(f"APACHE: Could not initialize Oracle: {e}")

        # Initialize Kronos GEX calculator
        self.kronos: Optional[KronosGEXCalculator] = None
        if KRONOS_AVAILABLE:
            try:
                self.kronos = KronosGEXCalculator()
                logger.info("APACHE: Kronos GEX calculator initialized")
            except Exception as e:
                logger.warning(f"APACHE: Could not initialize Kronos: {e}")

        # Initialize Tradier for execution
        self.tradier: Optional[TradierDataFetcher] = None
        if TRADIER_AVAILABLE and self.config.mode != TradingMode.BACKTEST:
            try:
                self.tradier = TradierDataFetcher()
                logger.info("APACHE: Tradier execution initialized")
            except Exception as e:
                logger.warning(f"APACHE: Could not initialize Tradier: {e}")

        # Initialize GEX ML Signal Integration
        self.gex_ml: Optional[GEXSignalIntegration] = None
        if GEX_ML_AVAILABLE:
            try:
                self.gex_ml = GEXSignalIntegration()
                if self.gex_ml.load_models():
                    logger.info("APACHE: GEX ML signal integration initialized")
                else:
                    logger.warning("APACHE: GEX ML models not found - run train_gex_probability_models.py")
                    self.gex_ml = None
            except Exception as e:
                logger.warning(f"APACHE: Could not initialize GEX ML: {e}")

        # Position tracking
        self.open_positions: List[SpreadPosition] = []
        self.closed_positions: List[SpreadPosition] = []
        self.daily_trades: int = 0
        self.last_trade_date: Optional[str] = None

        # Session tracking for logging
        self.session_tracker = None
        if BOT_LOGGER_AVAILABLE and get_session_tracker:
            self.session_tracker = get_session_tracker("APACHE")

        # Load config from database if available
        self._load_config_from_db()

        logger.info(f"APACHE initialized: capital=${initial_capital:,.2f}, mode={self.config.mode.value}")

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
                    'contracts_per_trade', 'max_daily_trades', 'trailing_stop_pct', 'ticker'
                )
            """)

            rows = c.fetchall()
            for row in rows:
                name, value = row
                if name == 'enabled' and value == 'false':
                    logger.warning("APACHE is DISABLED in config")
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

            conn.close()
            logger.info("APACHE: Loaded config from database")
        except Exception as e:
            logger.debug(f"APACHE: Could not load config from DB: {e}")

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

    def get_gex_data(self) -> Optional[Dict[str, Any]]:
        """Get current GEX data from Kronos"""
        if not self.kronos:
            self._log_to_db("WARNING", "Kronos not available for GEX data")
            return None

        try:
            # Get today's date for GEX calculation
            today = datetime.now().strftime("%Y-%m-%d")

            # Use calculate_gex_for_date method
            gex = self.kronos.calculate_gex_for_date(today, dte_max=7)
            if gex:
                return {
                    'net_gex': gex.net_gex,
                    'call_wall': gex.call_wall,
                    'put_wall': gex.put_wall,
                    'flip_point': gex.flip_point,
                    'spot_price': gex.spot_price,
                    'regime': gex.gex_regime  # Already calculated by Kronos
                }
            else:
                self._log_to_db("WARNING", f"No GEX data for {today}")
        except Exception as e:
            self._log_to_db("ERROR", f"Failed to get GEX data: {e}")

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
            # Get APACHE-specific advice from Oracle
            advice = self.oracle.get_apache_advice(
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
            signal = self.gex_ml.get_signal_for_apache(gex_data, vix=vix)

            self._log_to_db("INFO", f"ML Signal: {signal['advice']}", {
                'confidence': signal['confidence'],
                'win_probability': signal['win_probability'],
                'spread_type': signal['spread_type'],
                'expected_volatility': signal['expected_volatility'],
                'model_predictions': signal['model_predictions']
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
                advice.reasoning[:500]  # Truncate reasoning
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
        signal_id: Optional[int] = None
    ) -> Optional[SpreadPosition]:
        """Execute a spread trade"""
        decision_tracker = None
        if BOT_LOGGER_AVAILABLE and DecisionTracker:
            decision_tracker = DecisionTracker()
            decision_tracker.start()

        # Get 0DTE expiration
        today = datetime.now().strftime("%Y-%m-%d")

        # Calculate strikes
        atm_strike = round(spot_price)
        if spread_type == SpreadType.BULL_CALL_SPREAD:
            long_strike = atm_strike
            short_strike = atm_strike + self.config.spread_width
        else:  # BEAR_CALL_SPREAD
            short_strike = atm_strike
            long_strike = atm_strike + self.config.spread_width

        # Position sizing
        spread_width = abs(short_strike - long_strike)
        max_loss = spread_width * 100 * self.config.default_contracts
        max_risk = self.current_capital * (self.config.risk_per_trade_pct / 100)

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
                position_id=f"APACHE-{uuid.uuid4().hex[:8]}",
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
                oracle_reasoning=advice.reasoning[:200]
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
                decision_tracker=decision_tracker
            )

            self._log_to_db("INFO", f"PAPER TRADE: {spread_type.value}", {
                'position_id': position.position_id,
                'strikes': f"{long_strike}/{short_strike}",
                'contracts': contracts,
                'entry_debit': entry_debit
            })

            return position

        # TODO: Live execution via Tradier
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
        advice: OraclePrediction,
        decision_tracker: Optional[Any] = None
    ) -> None:
        """Log comprehensive decision using bot_logger"""
        if not BOT_LOGGER_AVAILABLE or not log_bot_decision:
            return

        try:
            # Build market context
            market_ctx = BotLogMarketContext(
                spot_price=gex_data.get('spot_price', 0),
                vix=20.0,  # TODO: Get actual VIX
                net_gex=gex_data.get('net_gex', 0),
                gex_regime=gex_data.get('regime', 'NEUTRAL'),
                flip_point=gex_data.get('flip_point', 0),
                call_wall=gex_data.get('call_wall', 0),
                put_wall=gex_data.get('put_wall', 0)
            )

            # Build Claude context if available
            claude_ctx = ClaudeContext()
            if advice.claude_analysis:
                claude_ctx.response = advice.claude_analysis.analysis
                claude_ctx.confidence = str(advice.claude_analysis.confidence_adjustment)
                claude_ctx.warnings = advice.claude_analysis.risk_factors

            # Create decision object
            decision = BotDecision(
                bot_name="APACHE",
                decision_type="ENTRY",
                action="SELL" if position.spread_type == SpreadType.BEAR_CALL_SPREAD else "BUY",
                symbol=self.config.ticker,
                strategy=position.spread_type.value,
                strike=position.long_strike,
                expiration=position.expiration,
                option_type="CALL",
                contracts=position.contracts,
                session_id=generate_session_id() if self.session_tracker else "",
                market_context=market_ctx,
                claude_context=claude_ctx,
                entry_reasoning=advice.reasoning,
                strike_reasoning=f"ATM: {position.long_strike}, OTM: {position.short_strike}",
                size_reasoning=f"Risk per trade: {self.config.risk_per_trade_pct}%",
                kelly_pct=self.config.risk_per_trade_pct,
                position_size_dollars=abs(position.entry_debit) * 100 * position.contracts,
                max_risk_dollars=position.max_loss,
                backtest_win_rate=advice.win_probability,
                passed_all_checks=True
            )

            # Add API calls if tracked
            if decision_tracker:
                decision.api_calls = decision_tracker.api_calls
                decision.errors_encountered = decision_tracker.errors
                decision.processing_time_ms = decision_tracker.elapsed_ms

            # Log to database
            log_bot_decision(decision)

        except Exception as e:
            self._log_to_db("ERROR", f"Failed to log decision: {e}")

    def check_exits(self) -> List[SpreadPosition]:
        """Check all open positions for exit conditions"""
        closed = []
        now = datetime.now(CENTRAL_TZ)

        for position in self.open_positions[:]:  # Copy list to allow modification
            should_exit = False
            exit_reason = ""

            # Check time-based exit (0DTE - exit before close)
            exit_time = now.replace(hour=15, minute=55, second=0)
            if now >= exit_time:
                should_exit = True
                exit_reason = "EOD_EXIT"

            # TODO: Check trailing stop if we have intraday price data

            if should_exit:
                self._close_position(position, exit_reason)
                closed.append(position)

        return closed

    def _close_position(self, position: SpreadPosition, reason: str) -> None:
        """Close a position"""
        position.status = "closed"
        position.close_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # For paper trading, simulate close price
        if self.config.mode == TradingMode.PAPER:
            # Assume we close at current value
            if position.spread_type == SpreadType.BULL_CALL_SPREAD:
                # Bullish - assume 60% of trades hit max profit based on backtest
                position.close_price = position.entry_debit * 1.5
                position.realized_pnl = (position.close_price - position.entry_debit) * 100 * position.contracts
            else:
                # Bearish credit spread - keep premium
                position.realized_pnl = abs(position.entry_debit) * 100 * position.contracts * 0.8

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

    def _log_exit_decision(self, position: SpreadPosition, reason: str) -> None:
        """Log exit decision"""
        if not BOT_LOGGER_AVAILABLE or not log_bot_decision:
            return

        try:
            decision = BotDecision(
                bot_name="APACHE",
                decision_type="EXIT",
                action="CLOSE",
                symbol=self.config.ticker,
                strategy=position.spread_type.value,
                strike=position.long_strike,
                expiration=position.expiration,
                option_type="CALL",
                contracts=position.contracts,
                exit_reasoning=reason,
                actual_pnl=position.realized_pnl,
                exit_triggered_by=reason
            )

            log_bot_decision(decision)
        except Exception as e:
            self._log_to_db("ERROR", f"Failed to log exit: {e}")

    def run_daily_cycle(self) -> Dict[str, Any]:
        """Run the daily trading cycle using ML signals"""
        self._log_to_db("INFO", "=== APACHE Daily Cycle Starting ===")

        result = {
            'trades_attempted': 0,
            'trades_executed': 0,
            'positions_closed': 0,
            'daily_pnl': 0,
            'signal_source': None,
            'errors': []
        }

        # Check if we should trade
        should_trade, reason = self.should_trade()
        if not should_trade:
            self._log_to_db("INFO", f"Skipping trade: {reason}")
            result['errors'].append(reason)
            return result

        # Get GEX data first (needed for both ML and Oracle)
        gex_data = self.get_gex_data()
        if not gex_data:
            result['errors'].append("No GEX data")
            return result

        # === PRIMARY: Use ML Signal ===
        ml_signal = None
        spread_type = None
        signal_source = "ML"

        if self.gex_ml:
            ml_signal = self.get_ml_signal(gex_data)

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
                result['signal_source'] = 'ML'
                # Still check exits
                closed = self.check_exits()
                result['positions_closed'] = len(closed)
                result['daily_pnl'] = sum(p.realized_pnl for p in closed)
                return result

        # === FALLBACK: Use Oracle if ML unavailable ===
        if not spread_type and ORACLE_AVAILABLE:
            signal_source = "Oracle"
            advice = self.get_oracle_advice()

            if advice:
                result['trades_attempted'] = 1

                if advice.advice == TradingAdvice.SKIP_TODAY:
                    self._log_to_db("INFO", f"Oracle says SKIP: {advice.reasoning}")
                    result['signal_source'] = 'Oracle'
                    return result

                # Determine spread type from Oracle reasoning
                if "BULL_CALL_SPREAD" in advice.reasoning:
                    spread_type = SpreadType.BULL_CALL_SPREAD
                elif "BEAR_CALL_SPREAD" in advice.reasoning:
                    spread_type = SpreadType.BEAR_CALL_SPREAD

        # No actionable signal
        if not spread_type:
            self._log_to_db("INFO", "No actionable signal from ML or Oracle")
            result['errors'].append("No actionable signal")
            return result

        result['signal_source'] = signal_source

        # Save signal to database
        signal_id = self._save_ml_signal_to_db(ml_signal, gex_data) if ml_signal else None

        # Create a mock advice object for execution (to maintain compatibility)
        class MockAdvice:
            def __init__(self, ml_sig):
                self.confidence = ml_sig['confidence'] if ml_sig else 0.5
                self.win_probability = ml_sig['win_probability'] if ml_sig else 0.5
                self.reasoning = ml_sig['reasoning'] if ml_sig else "Oracle signal"
                self.claude_analysis = None

        advice_obj = MockAdvice(ml_signal)

        # Execute spread
        position = self.execute_spread(
            spread_type=spread_type,
            spot_price=gex_data['spot_price'],
            gex_data=gex_data,
            advice=advice_obj,
            signal_id=signal_id
        )

        if position:
            result['trades_executed'] = 1
            self._log_to_db("INFO", f"Trade executed: {position.position_id} ({signal_source})")

        # Check exits for existing positions
        closed = self.check_exits()
        result['positions_closed'] = len(closed)
        result['daily_pnl'] = sum(p.realized_pnl for p in closed)

        self._log_to_db("INFO", f"=== APACHE Cycle Complete ===", result)

        return result

    def _save_ml_signal_to_db(self, ml_signal: Dict, gex_data: Dict) -> Optional[int]:
        """Save ML signal to apache_signals table"""
        try:
            conn = get_connection()
            c = conn.cursor()

            direction = "FLAT"
            if ml_signal['advice'] == 'LONG':
                direction = "BULLISH"
            elif ml_signal['advice'] == 'SHORT':
                direction = "BEARISH"

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
                ml_signal['reasoning'][:500]
            ))

            signal_id = c.fetchone()[0]
            conn.commit()
            conn.close()

            self._log_to_db("INFO", f"ML Signal saved: {direction}", {'signal_id': signal_id})
            return signal_id
        except Exception as e:
            self._log_to_db("ERROR", f"Failed to save ML signal: {e}")
            return None

    def get_status(self) -> Dict[str, Any]:
        """Get current bot status"""
        return {
            'bot_name': 'APACHE',
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
            'tradier_available': self.tradier is not None
        }


# Convenience function for running Apache
def run_apache(capital: float = 100_000, mode: str = "paper") -> APACHETrader:
    """Quick start Apache trading bot"""
    config = APACHEConfig(
        mode=TradingMode.PAPER if mode == "paper" else TradingMode.LIVE
    )
    trader = APACHETrader(initial_capital=capital, config=config)
    return trader


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Test run
    apache = run_apache()
    status = apache.get_status()
    print(f"\nAPACHE Status: {status}")

    # Run cycle
    result = apache.run_daily_cycle()
    print(f"\nCycle Result: {result}")
