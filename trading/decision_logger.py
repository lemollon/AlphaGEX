"""
Decision Transparency Logger

Creates a complete audit trail for EVERY trading decision:
1. What data was used (exact prices, timestamps, sources)
2. Why this decision was made (regime, signals, backtest stats)
3. What alternatives were considered
4. Expected vs actual outcomes

This is the bridge between backtester and live trader.
Without this, you're trading blind.
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Lazy database import to avoid circular dependencies
_db_connection = None


def get_db_connection():
    """Lazy database connection"""
    global _db_connection
    if _db_connection is None:
        try:
            from database_adapter import get_connection
            _db_connection = get_connection
        except ImportError:
            logger.warning("Database adapter not available")
            return None
    return _db_connection()


class BotName(Enum):
    """Names for each trading bot"""
    PHOENIX = "PHOENIX"  # AutonomousPaperTrader - 0DTE SPY/SPX
    ATLAS = "ATLAS"      # SPXWheelTrader - SPX Cash-Secured Put Wheel
    HERMES = "HERMES"    # WheelStrategyManager - Manual Wheel via UI
    ORACLE = "ORACLE"    # MultiStrategyOptimizer - Advisory/Recommendations
    ARES = "ARES"        # ARESTrader - Aggressive Iron Condor (10% monthly target)
    ATHENA = "ATHENA"    # ATHENATrader - Directional Spreads (Bull/Bear Call Spreads)


class DecisionType(Enum):
    """Types of trading decisions"""
    ENTRY_SIGNAL = "ENTRY_SIGNAL"
    EXIT_SIGNAL = "EXIT_SIGNAL"
    POSITION_SIZE = "POSITION_SIZE"
    STRIKE_SELECTION = "STRIKE_SELECTION"
    STRATEGY_SELECTION = "STRATEGY_SELECTION"
    RISK_CHECK = "RISK_CHECK"
    NO_TRADE = "NO_TRADE"
    ADJUSTMENT = "ADJUSTMENT"
    STAY_FLAT = "STAY_FLAT"
    RISK_BLOCKED = "RISK_BLOCKED"
    ML_PREDICTION = "ML_PREDICTION"
    ENSEMBLE_SIGNAL = "ENSEMBLE_SIGNAL"
    KELLY_CALCULATION = "KELLY_CALCULATION"
    ROLL_DECISION = "ROLL_DECISION"
    CALIBRATION = "CALIBRATION"


class DataSource(Enum):
    """Data sources used"""
    TRADIER_LIVE = "TRADIER_LIVE"
    POLYGON_REALTIME = "POLYGON_REALTIME"
    POLYGON_HISTORICAL = "POLYGON_HISTORICAL"
    TRADING_VOLATILITY = "TRADING_VOLATILITY"
    CALCULATED = "CALCULATED"
    CACHED = "CACHED"
    SIMULATED = "SIMULATED"  # RED FLAG - should never be in production


@dataclass
class TradeLeg:
    """
    Complete data for ONE leg of a trade.
    For multi-leg strategies (spreads, condors), use multiple TradeLeg objects.
    """
    # Core identification
    leg_id: int = 1  # Leg 1, 2, 3, etc.
    action: str = ""  # BUY or SELL
    option_type: str = ""  # 'call' or 'put'

    # Strike and expiration (REQUIRED for every trade)
    strike: float = 0
    expiration: str = ""  # YYYY-MM-DD

    # Prices at entry (REQUIRED)
    entry_price: float = 0  # Per-share price at entry
    entry_bid: float = 0
    entry_ask: float = 0
    entry_mid: float = 0

    # Prices at exit (filled when position closes)
    exit_price: float = 0
    exit_bid: float = 0
    exit_ask: float = 0
    exit_timestamp: str = ""

    # Position sizing
    contracts: int = 0
    premium_per_contract: float = 0  # entry_price * 100

    # Greeks at entry (important for risk)
    delta: float = 0
    gamma: float = 0
    theta: float = 0
    vega: float = 0
    iv: float = 0

    # Order execution details
    order_id: str = ""
    fill_price: float = 0  # Actual fill (may differ from limit)
    fill_timestamp: str = ""
    order_status: str = ""  # filled, partial, rejected

    # P&L for this leg
    realized_pnl: float = 0

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class PriceSnapshot:
    """Exact price data used for a decision"""
    symbol: str
    price: float
    bid: float = 0
    ask: float = 0
    timestamp: str = ""
    source: DataSource = DataSource.CALCULATED

    # For options
    strike: float = 0
    expiration: str = ""
    option_type: str = ""  # 'call' or 'put'
    delta: float = 0
    gamma: float = 0
    theta: float = 0
    iv: float = 0


@dataclass
class MarketContext:
    """Market conditions at decision time"""
    timestamp: str

    # Underlying
    spot_price: float
    spot_source: DataSource

    # Volatility
    vix: float = 0
    historical_vol: float = 0
    iv_rank: float = 0

    # GEX/Gamma
    net_gex: float = 0
    gex_regime: str = ""  # 'positive', 'negative', 'neutral'
    flip_point: float = 0
    call_wall: float = 0
    put_wall: float = 0
    gex_source: DataSource = DataSource.CALCULATED

    # Trend
    trend: str = ""  # 'bullish', 'bearish', 'neutral'
    sma_20: float = 0
    sma_50: float = 0

    # Market regime
    regime: str = ""
    regime_confidence: float = 0


@dataclass
class BacktestReference:
    """Link to backtest that informed this decision"""
    strategy_name: str
    backtest_date: str = ""

    # Stats from backtest
    win_rate: float = 0
    expectancy: float = 0
    avg_win: float = 0
    avg_loss: float = 0
    sharpe_ratio: float = 0
    total_trades: int = 0
    max_drawdown: float = 0
    backtest_period: str = ""

    # Data quality
    uses_real_data: bool = True
    data_source: str = "polygon"
    date_range: str = ""


@dataclass
class DecisionReasoning:
    """Why this decision was made"""
    primary_reason: str
    supporting_factors: List[str] = field(default_factory=list)
    risk_factors: List[str] = field(default_factory=list)
    alternatives_considered: List[str] = field(default_factory=list)
    why_not_alternatives: List[str] = field(default_factory=list)


@dataclass
class TradeDecision:
    """Complete audit record for a trading decision"""
    # Identification
    decision_id: str
    timestamp: str
    decision_type: DecisionType
    bot_name: BotName = BotName.PHOENIX  # Which bot made this decision

    # The Three Keys: What, Why, How (human-readable summary)
    what: str = ""  # Brief: "BUY 2x SPY $590C expiring today"
    why: str = ""   # Full reasoning chain
    how: str = ""   # Calculation details (Kelly, Monte Carlo, etc.)

    # What was decided
    action: str = ""  # 'BUY', 'SELL', 'HOLD', 'SKIP'
    symbol: str = ""
    strategy: str = ""

    # =========================================================================
    # TRADE LEGS - Complete data for each leg of the trade
    # For single-leg: 1 TradeLeg in the list
    # For spreads: 2 TradeLeg objects (long + short)
    # For condors: 4 TradeLeg objects
    # =========================================================================
    legs: List[TradeLeg] = field(default_factory=list)

    # Prices used (legacy - use legs for complete data)
    underlying_snapshot: PriceSnapshot = None
    option_snapshot: Optional[PriceSnapshot] = None

    # Underlying price at entry and exit
    underlying_price_at_entry: float = 0
    underlying_price_at_exit: float = 0

    # Market context
    market_context: MarketContext = None

    # Backtest backing
    backtest_reference: Optional[BacktestReference] = None

    # Oracle AI advice (from OracleAdvisor)
    oracle_advice: Optional[Dict] = None  # Full oracle prediction with win_prob, confidence, factors

    # Reasoning
    reasoning: DecisionReasoning = None

    # Position sizing
    position_size_dollars: float = 0
    position_size_contracts: int = 0
    position_size_method: str = ""  # 'kelly', 'fixed', 'risk_parity'
    max_risk_dollars: float = 0

    # Expected outcome
    target_profit_pct: float = 0
    stop_loss_pct: float = 0
    expected_hold_days: int = 0
    probability_of_profit: float = 0

    # Validation
    passed_risk_checks: bool = True
    risk_check_details: List[str] = field(default_factory=list)

    # Outcome (filled in later)
    actual_entry_price: float = 0
    actual_exit_price: float = 0
    actual_pnl: float = 0
    actual_hold_days: int = 0
    outcome_notes: str = ""

    # Order execution (broker details)
    order_id: str = ""
    fill_timestamp: str = ""

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON/database storage"""
        def convert_value(v):
            """Recursively convert Enums and nested objects"""
            if isinstance(v, Enum):
                return v.value
            elif isinstance(v, dict):
                return {k: convert_value(val) for k, val in v.items()}
            elif isinstance(v, list):
                return [convert_value(item) for item in v]
            else:
                return v

        raw_dict = asdict(self)
        return convert_value(raw_dict)


class DecisionLogger:
    """
    Logs all trading decisions with full transparency.

    Every decision shows:
    - Exact data used (prices, timestamps, sources)
    - Why this decision was made
    - What backtest results informed it
    - Risk checks performed
    - Expected vs actual outcomes
    """

    def __init__(self):
        # Texas Central Time - standard timezone for all AlphaGEX operations
        self.tz = ZoneInfo("America/Chicago")
        self.decisions: List[TradeDecision] = []
        self._decision_counter = 0
        self._db_initialized = False

    def _maybe_init_db(self):
        """Lazy database initialization"""
        if not self._db_initialized:
            self._ensure_tables()
            self._db_initialized = True

    def _ensure_tables(self):
        """
        Verify decision log tables exist.
        NOTE: Tables are now defined in db/config_and_database.py (single source of truth).
        """
        # Table trading_decisions is created by db/config_and_database.py init_database()
        # on app startup. No need to create it here.
        logger.info("Decision logging tables expected from main schema (db/config_and_database.py)")

    def _generate_decision_id(self) -> str:
        """Generate unique decision ID"""
        self._decision_counter += 1
        now = datetime.now(self.tz)
        return f"DEC-{now.strftime('%Y%m%d%H%M%S')}-{self._decision_counter:04d}"

    def log_decision(self, decision: TradeDecision) -> str:
        """
        Log a trading decision with full context.

        Returns decision_id for later outcome update.
        """
        self._maybe_init_db()

        if not decision.decision_id:
            decision.decision_id = self._generate_decision_id()

        if not decision.timestamp:
            decision.timestamp = datetime.now(self.tz).isoformat()

        # Store in memory
        self.decisions.append(decision)

        # Store in database
        conn = get_db_connection()
        if conn:
            try:
                cursor = conn.cursor()

                # Extract nested values safely
                spot_price = decision.underlying_snapshot.price if decision.underlying_snapshot else 0
                spot_source = decision.underlying_snapshot.source.value if decision.underlying_snapshot else ""

                option_price = decision.option_snapshot.price if decision.option_snapshot else None
                strike = decision.option_snapshot.strike if decision.option_snapshot else None
                expiration = decision.option_snapshot.expiration if decision.option_snapshot else None

                vix = decision.market_context.vix if decision.market_context else None
                net_gex = decision.market_context.net_gex if decision.market_context else None
                gex_regime = decision.market_context.gex_regime if decision.market_context else None
                market_regime = decision.market_context.regime if decision.market_context else None
                trend = decision.market_context.trend if decision.market_context else None

                backtest_strategy = decision.backtest_reference.strategy_name if decision.backtest_reference else None
                backtest_win_rate = decision.backtest_reference.win_rate if decision.backtest_reference else None
                backtest_expectancy = decision.backtest_reference.expectancy if decision.backtest_reference else None
                backtest_real_data = decision.backtest_reference.uses_real_data if decision.backtest_reference else None

                primary_reason = decision.reasoning.primary_reason if decision.reasoning else None
                supporting = json.dumps(decision.reasoning.supporting_factors) if decision.reasoning else None
                risks = json.dumps(decision.reasoning.risk_factors) if decision.reasoning else None

                cursor.execute('''
                    INSERT INTO trading_decisions (
                        decision_id, timestamp, decision_type, action, symbol, strategy,
                        spot_price, spot_source, option_price, strike, expiration,
                        vix, net_gex, gex_regime, market_regime, trend,
                        backtest_strategy, backtest_win_rate, backtest_expectancy, backtest_uses_real_data,
                        primary_reason, supporting_factors, risk_factors,
                        position_size_dollars, position_size_contracts, max_risk_dollars,
                        target_profit_pct, stop_loss_pct, prob_profit,
                        passed_risk_checks, risk_check_details,
                        full_decision
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s,
                        %s
                    )
                ''', (
                    decision.decision_id, decision.timestamp, decision.decision_type.value,
                    decision.action, decision.symbol, decision.strategy,
                    spot_price, spot_source, option_price, strike, expiration,
                    vix, net_gex, gex_regime, market_regime, trend,
                    backtest_strategy, backtest_win_rate, backtest_expectancy, backtest_real_data,
                    primary_reason, supporting, risks,
                    decision.position_size_dollars, decision.position_size_contracts, decision.max_risk_dollars,
                    decision.target_profit_pct, decision.stop_loss_pct, decision.probability_of_profit,
                    decision.passed_risk_checks, json.dumps(decision.risk_check_details),
                    json.dumps(decision.to_dict())
                ))

                conn.commit()
                conn.close()

                logger.info(f"Logged decision {decision.decision_id}: {decision.action} {decision.symbol}")

            except Exception as e:
                logger.error(f"Failed to log decision to database: {e}")
                try:
                    conn.close()
                except:
                    pass

        return decision.decision_id

    def update_outcome(
        self,
        decision_id: str,
        actual_entry_price: float,
        actual_exit_price: float,
        actual_pnl: float,
        actual_hold_days: int,
        notes: str = ""
    ):
        """Update a decision with actual outcome"""
        self._maybe_init_db()
        conn = get_db_connection()
        if not conn:
            return

        try:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE trading_decisions SET
                    actual_entry_price = %s,
                    actual_exit_price = %s,
                    actual_pnl = %s,
                    actual_hold_days = %s,
                    outcome_notes = %s,
                    outcome_updated_at = NOW()
                WHERE decision_id = %s
            ''', (actual_entry_price, actual_exit_price, actual_pnl,
                  actual_hold_days, notes, decision_id))

            conn.commit()
            conn.close()
            logger.info(f"Updated outcome for {decision_id}: P&L ${actual_pnl:.2f}")

        except Exception as e:
            logger.error(f"Failed to update outcome: {e}")
            try:
                conn.close()
            except:
                pass

    def create_entry_decision(
        self,
        symbol: str,
        strategy: str,
        action: str,
        spot_price: float,
        spot_source: DataSource,
        strike: float = 0,
        expiration: str = "",
        option_price: float = 0,
        option_delta: float = 0,
        vix: float = 0,
        net_gex: float = 0,
        gex_regime: str = "",
        market_regime: str = "",
        trend: str = "",
        backtest_win_rate: float = 0,
        backtest_expectancy: float = 0,
        backtest_uses_real_data: bool = True,
        primary_reason: str = "",
        supporting_factors: List[str] = None,
        risk_factors: List[str] = None,
        position_size_dollars: float = 0,
        contracts: int = 0,
        max_risk: float = 0,
        target_profit_pct: float = 50,
        stop_loss_pct: float = 200,
        prob_profit: float = 0
    ) -> TradeDecision:
        """
        Create a complete entry decision with all context.

        This is the main method to use when entering a trade.
        """
        now = datetime.now(self.tz)

        decision = TradeDecision(
            decision_id=self._generate_decision_id(),
            timestamp=now.isoformat(),
            decision_type=DecisionType.ENTRY_SIGNAL,
            action=action,
            symbol=symbol,
            strategy=strategy,

            underlying_snapshot=PriceSnapshot(
                symbol=symbol,
                price=spot_price,
                timestamp=now.isoformat(),
                source=spot_source
            ),

            option_snapshot=PriceSnapshot(
                symbol=symbol,
                price=option_price,
                strike=strike,
                expiration=expiration,
                delta=option_delta,
                source=spot_source
            ) if option_price > 0 else None,

            market_context=MarketContext(
                timestamp=now.isoformat(),
                spot_price=spot_price,
                spot_source=spot_source,
                vix=vix,
                net_gex=net_gex,
                gex_regime=gex_regime,
                regime=market_regime,
                trend=trend
            ),

            backtest_reference=BacktestReference(
                strategy_name=strategy,
                backtest_date=now.strftime('%Y-%m-%d'),
                win_rate=backtest_win_rate,
                expectancy=backtest_expectancy,
                avg_win=0,
                avg_loss=0,
                sharpe_ratio=0,
                total_trades=0,
                uses_real_data=backtest_uses_real_data,
                data_source="polygon" if backtest_uses_real_data else "simulated",
                date_range=""
            ) if backtest_win_rate > 0 else None,

            reasoning=DecisionReasoning(
                primary_reason=primary_reason,
                supporting_factors=supporting_factors or [],
                risk_factors=risk_factors or []
            ),

            position_size_dollars=position_size_dollars,
            position_size_contracts=contracts,
            max_risk_dollars=max_risk,
            target_profit_pct=target_profit_pct,
            stop_loss_pct=stop_loss_pct,
            probability_of_profit=prob_profit
        )

        return decision

    def get_decisions_for_export(
        self,
        start_date: str = None,
        end_date: str = None,
        symbol: str = None,
        strategy: str = None
    ) -> List[Dict]:
        """Get decisions for Excel export"""
        conn = get_db_connection()
        if not conn:
            return []

        try:
            cursor = conn.cursor()

            query = "SELECT full_decision FROM trading_decisions WHERE 1=1"
            params = []

            if start_date:
                query += " AND timestamp >= %s"
                params.append(start_date)
            if end_date:
                query += " AND timestamp <= %s"
                params.append(end_date)
            if symbol:
                query += " AND symbol = %s"
                params.append(symbol)
            if strategy:
                query += " AND strategy = %s"
                params.append(strategy)

            query += " ORDER BY timestamp DESC"

            cursor.execute(query, params)
            rows = cursor.fetchall()
            conn.close()

            return [row[0] for row in rows if row[0]]

        except Exception as e:
            logger.error(f"Failed to get decisions: {e}")
            return []

    def print_decision_summary(self, decision: TradeDecision):
        """Print a human-readable decision summary"""
        print("\n" + "=" * 70)
        print(f"DECISION: {decision.decision_id}")
        print("=" * 70)
        print(f"Time:     {decision.timestamp}")
        print(f"Action:   {decision.action} {decision.symbol}")
        print(f"Strategy: {decision.strategy}")
        print()
        print("DATA USED:")
        print(f"  Spot Price: ${decision.underlying_snapshot.price:.2f}")
        print(f"  Source:     {decision.underlying_snapshot.source.value}")
        if decision.option_snapshot:
            print(f"  Option:     ${decision.option_snapshot.strike:.0f} "
                  f"{decision.option_snapshot.expiration}")
            print(f"  Premium:    ${decision.option_snapshot.price:.2f}")
            print(f"  Delta:      {decision.option_snapshot.delta:.2f}")
        print()
        if decision.market_context:
            print("MARKET CONTEXT:")
            print(f"  VIX:        {decision.market_context.vix:.1f}")
            print(f"  Net GEX:    ${decision.market_context.net_gex/1e9:.2f}B")
            print(f"  GEX Regime: {decision.market_context.gex_regime}")
            print(f"  Trend:      {decision.market_context.trend}")
        print()
        if decision.backtest_reference:
            print("BACKTEST BACKING:")
            print(f"  Win Rate:   {decision.backtest_reference.win_rate:.1f}%")
            print(f"  Expectancy: {decision.backtest_reference.expectancy:.2f}%")
            print(f"  Real Data:  {'YES' if decision.backtest_reference.uses_real_data else 'NO - SIMULATED'}")
        print()
        if decision.reasoning:
            print("REASONING:")
            print(f"  Why:        {decision.reasoning.primary_reason}")
            if decision.reasoning.supporting_factors:
                print(f"  Support:    {', '.join(decision.reasoning.supporting_factors)}")
            if decision.reasoning.risk_factors:
                print(f"  Risks:      {', '.join(decision.reasoning.risk_factors)}")
        print()
        print(f"POSITION:")
        print(f"  Size:       ${decision.position_size_dollars:,.0f} "
              f"({decision.position_size_contracts} contracts)")
        print(f"  Max Risk:   ${decision.max_risk_dollars:,.0f}")
        print(f"  Target:     {decision.target_profit_pct:.0f}% profit")
        print(f"  Stop:       {decision.stop_loss_pct:.0f}% loss")
        print("=" * 70 + "\n")


# Singleton instance
_decision_logger: Optional[DecisionLogger] = None


def get_decision_logger() -> DecisionLogger:
    """Get singleton decision logger"""
    global _decision_logger
    if _decision_logger is None:
        _decision_logger = DecisionLogger()
    return _decision_logger


# =============================================================================
# EXPORT FUNCTIONS - For monitoring, analysis, and optimization
# =============================================================================

def export_decisions_json(
    bot_name: str = None,
    start_date: str = None,
    end_date: str = None,
    decision_type: str = None,
    symbol: str = None,
    limit: int = 1000
) -> List[Dict]:
    """
    Export decision logs as JSON list.

    Args:
        bot_name: Filter by bot (PHOENIX, ATLAS, HERMES, ORACLE)
        start_date: Filter from date (YYYY-MM-DD)
        end_date: Filter to date (YYYY-MM-DD)
        decision_type: Filter by type (ENTRY_SIGNAL, STAY_FLAT, etc.)
        symbol: Filter by symbol (SPY, SPX)
        limit: Max records to return

    Returns:
        List of decision dictionaries with full details
    """
    conn = get_db_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()

        query = """
            SELECT
                decision_id, timestamp, decision_type, action, symbol, strategy,
                spot_price, vix, net_gex, gex_regime, market_regime, trend,
                backtest_win_rate, backtest_expectancy, backtest_uses_real_data,
                primary_reason, supporting_factors, risk_factors,
                position_size_dollars, position_size_contracts, max_risk_dollars,
                target_profit_pct, stop_loss_pct, prob_profit,
                passed_risk_checks, actual_pnl, outcome_notes,
                full_decision
            FROM trading_decisions
            WHERE 1=1
        """
        params = []

        if bot_name:
            # Bot name stored in full_decision JSON
            query += " AND full_decision->>'bot_name' = %s"
            params.append(bot_name)
        if start_date:
            query += " AND DATE(timestamp) >= %s"
            params.append(start_date)
        if end_date:
            query += " AND DATE(timestamp) <= %s"
            params.append(end_date)
        if decision_type:
            query += " AND decision_type = %s"
            params.append(decision_type)
        if symbol:
            query += " AND symbol = %s"
            params.append(symbol)

        query += " ORDER BY timestamp DESC LIMIT %s"
        params.append(limit)

        cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        results = []

        for row in cursor.fetchall():
            record = dict(zip(columns, row))
            # Convert datetime to string
            if record.get('timestamp'):
                record['timestamp'] = record['timestamp'].isoformat() if hasattr(record['timestamp'], 'isoformat') else str(record['timestamp'])

            # Extract what/why/how from full_decision JSON
            full_dec = record.get('full_decision') or {}
            if isinstance(full_dec, dict):
                # Core decision info
                record['what'] = full_dec.get('what', '')
                record['why'] = full_dec.get('why', '')
                record['how'] = full_dec.get('how', '')
                record['bot_name'] = full_dec.get('bot_name', 'ARES')

                # Trade legs with complete data (strikes, prices, Greeks)
                record['legs'] = full_dec.get('legs', [])

                # =========================================================
                # ORACLE AI ADVICE - Full prediction data
                # =========================================================
                oracle = full_dec.get('oracle_advice') or full_dec.get('oracle_prediction') or {}
                if oracle:
                    record['oracle_advice'] = {
                        'advice': oracle.get('advice', ''),
                        'win_probability': oracle.get('win_probability', 0),
                        'confidence': oracle.get('confidence', 0),
                        'suggested_risk_pct': oracle.get('suggested_risk_pct', 0),
                        'suggested_sd_multiplier': oracle.get('suggested_sd_multiplier', 0),
                        'use_gex_walls': oracle.get('use_gex_walls', False),
                        'suggested_put_strike': oracle.get('suggested_put_strike'),
                        'suggested_call_strike': oracle.get('suggested_call_strike'),
                        'top_factors': oracle.get('top_factors', []),
                        'reasoning': oracle.get('reasoning', ''),
                        'model_version': oracle.get('model_version', ''),
                    }
                    # Claude AI analysis if available
                    claude = oracle.get('claude_analysis', {})
                    if claude:
                        record['oracle_advice']['claude_analysis'] = {
                            'analysis': claude.get('analysis', ''),
                            'confidence_adjustment': claude.get('confidence_adjustment', 0),
                            'risk_factors': claude.get('risk_factors', []),
                            'opportunities': claude.get('opportunities', []),
                            'recommendation': claude.get('recommendation', ''),
                        }

                # =========================================================
                # GEX CONTEXT - Walls, flip point, regime
                # =========================================================
                market_ctx = full_dec.get('market_context', {})
                if market_ctx:
                    record['gex_context'] = {
                        'net_gex': market_ctx.get('net_gex', 0),
                        'gex_normalized': market_ctx.get('gex_normalized', 0),
                        'call_wall': market_ctx.get('call_wall', 0),
                        'put_wall': market_ctx.get('put_wall', 0),
                        'flip_point': market_ctx.get('flip_point', 0),
                        'distance_to_flip_pct': market_ctx.get('gex_distance_to_flip_pct', 0),
                        'regime': market_ctx.get('gex_regime', market_ctx.get('regime', '')),
                        'between_walls': market_ctx.get('gex_between_walls', True),
                    }
                    # Market conditions
                    record['market_context'] = {
                        'spot_price': market_ctx.get('spot_price', 0),
                        'vix': market_ctx.get('vix', 0),
                        'vix_percentile': market_ctx.get('vix_percentile_30d', 0),
                        'expected_move': market_ctx.get('expected_move_pct', 0),
                        'trend': market_ctx.get('trend', ''),
                        'day_of_week': market_ctx.get('day_of_week', 0),
                        'days_to_opex': market_ctx.get('days_to_opex', 0),
                    }

                # =========================================================
                # BACKTEST REFERENCE - Historical performance backing
                # =========================================================
                backtest = full_dec.get('backtest_reference', {})
                if backtest:
                    record['backtest_stats'] = {
                        'strategy_name': backtest.get('strategy_name', ''),
                        'win_rate': backtest.get('win_rate', 0),
                        'expectancy': backtest.get('expectancy', 0),
                        'avg_win': backtest.get('avg_win', 0),
                        'avg_loss': backtest.get('avg_loss', 0),
                        'sharpe_ratio': backtest.get('sharpe_ratio', 0),
                        'max_drawdown': backtest.get('max_drawdown', 0),
                        'total_trades': backtest.get('total_trades', 0),
                        'uses_real_data': backtest.get('uses_real_data', True),
                        'backtest_period': backtest.get('date_range', backtest.get('backtest_period', '')),
                    }

                # =========================================================
                # POSITION SIZING - Full calculation breakdown
                # =========================================================
                record['position_sizing'] = {
                    'contracts': full_dec.get('position_size_contracts', 0),
                    'position_dollars': full_dec.get('position_size_dollars', 0),
                    'max_risk_dollars': full_dec.get('max_risk_dollars', 0),
                    'sizing_method': full_dec.get('position_size_method', ''),
                    'target_profit_pct': full_dec.get('target_profit_pct', 0),
                    'stop_loss_pct': full_dec.get('stop_loss_pct', 0),
                    'probability_of_profit': full_dec.get('probability_of_profit', 0),
                }

                # =========================================================
                # ALTERNATIVES EVALUATED - What else was considered
                # =========================================================
                reasoning = full_dec.get('reasoning', {})
                if reasoning and isinstance(reasoning, dict):
                    record['alternatives'] = {
                        'primary_reason': reasoning.get('primary_reason', ''),
                        'supporting_factors': reasoning.get('supporting_factors', []),
                        'risk_factors': reasoning.get('risk_factors', []),
                        'alternatives_considered': reasoning.get('alternatives_considered', []),
                        'why_not_alternatives': reasoning.get('why_not_alternatives', []),
                    }

                # =========================================================
                # RISK CHECKS - What passed/failed
                # =========================================================
                record['risk_checks'] = []
                risk_details = full_dec.get('risk_check_details', [])
                if isinstance(risk_details, list):
                    for check in risk_details:
                        if isinstance(check, str):
                            record['risk_checks'].append({
                                'check': check,
                                'passed': not check.upper().startswith('FAILED'),
                            })
                        elif isinstance(check, dict):
                            record['risk_checks'].append(check)
                record['passed_risk_checks'] = full_dec.get('passed_risk_checks', True)

                # =========================================================
                # UNDERLYING PRICES & OUTCOME
                # =========================================================
                record['underlying_price_at_entry'] = full_dec.get('underlying_price_at_entry', 0)
                record['underlying_price_at_exit'] = full_dec.get('underlying_price_at_exit', 0)
                record['actual_pnl'] = full_dec.get('actual_pnl', record.get('actual_pnl', 0))
                record['outcome_notes'] = full_dec.get('outcome_notes', '')

                # Legacy fields for backwards compatibility
                record['position_size_contracts'] = full_dec.get('position_size_contracts', 0)
                record['position_size_dollars'] = full_dec.get('position_size_dollars', 0)

            results.append(record)

        cursor.close()
        conn.close()

        return results

    except Exception as e:
        logger.error(f"Failed to export decisions: {e}")
        return []


def export_decisions_csv(
    bot_name: str = None,
    start_date: str = None,
    end_date: str = None,
    symbol: str = None
) -> str:
    """
    Export decision logs as CSV string for download.

    Returns CSV with ALL critical trade fields:
    - Strike, entry_price, exit_price, expiration for each leg
    - Contracts, premium, P&L
    - Greeks, VIX, underlying price
    - Order execution details
    """
    decisions = export_decisions_json(bot_name, start_date, end_date, symbol=symbol, limit=10000)

    if not decisions:
        return "timestamp,bot,decision_type,action,symbol,strategy,underlying_price,leg_num,option_type,strike,expiration,entry_price,exit_price,contracts,premium,delta,gamma,theta,iv,vix,order_id,pnl,reason\n"

    lines = ["timestamp,bot,decision_type,action,symbol,strategy,underlying_price,leg_num,option_type,strike,expiration,entry_price,exit_price,contracts,premium,delta,gamma,theta,iv,vix,order_id,pnl,reason"]

    for d in decisions:
        # Extract from full_decision if available
        full_dec = d.get('full_decision') or {}
        bot = full_dec.get('bot_name', 'PHOENIX') if isinstance(full_dec, dict) else 'PHOENIX'
        reason = (d.get('primary_reason') or '')[:100].replace(',', ';').replace('\n', ' ')

        # Get legs array from full_decision
        legs = full_dec.get('legs', []) if isinstance(full_dec, dict) else []

        if legs:
            # Output one row per leg
            for leg in legs:
                line = ','.join([
                    str(d.get('timestamp', '')),
                    bot,
                    str(d.get('decision_type', '')),
                    str(leg.get('action', d.get('action', ''))),
                    str(d.get('symbol', '')),
                    str(d.get('strategy', '')),
                    str(full_dec.get('underlying_price_at_entry', d.get('spot_price', ''))),
                    str(leg.get('leg_id', 1)),
                    str(leg.get('option_type', '')),
                    str(leg.get('strike', '')),
                    str(leg.get('expiration', '')),
                    str(leg.get('entry_price', '')),
                    str(leg.get('exit_price', '')),
                    str(leg.get('contracts', '')),
                    str(leg.get('premium_per_contract', '')),
                    str(leg.get('delta', '')),
                    str(leg.get('gamma', '')),
                    str(leg.get('theta', '')),
                    str(leg.get('iv', '')),
                    str(d.get('vix', '')),
                    str(leg.get('order_id', full_dec.get('order_id', ''))),
                    str(leg.get('realized_pnl', d.get('actual_pnl', ''))),
                    f'"{reason}"'
                ])
                lines.append(line)
        else:
            # Legacy format - single row with option_snapshot data
            opt = full_dec.get('option_snapshot', {}) if isinstance(full_dec, dict) else {}
            line = ','.join([
                str(d.get('timestamp', '')),
                bot,
                str(d.get('decision_type', '')),
                str(d.get('action', '')),
                str(d.get('symbol', '')),
                str(d.get('strategy', '')),
                str(d.get('spot_price', '')),
                "1",  # leg_num
                str(opt.get('option_type', '')),
                str(d.get('strike', opt.get('strike', ''))),
                str(d.get('expiration', opt.get('expiration', ''))),
                str(opt.get('price', '')),  # entry_price
                str(d.get('actual_exit_price', '')),
                str(d.get('position_size_contracts', '')),
                str(d.get('position_size_dollars', '')),
                str(opt.get('delta', '')),
                str(opt.get('gamma', '')),
                str(opt.get('theta', '')),
                str(opt.get('iv', '')),
                str(d.get('vix', '')),
                str(full_dec.get('order_id', '')),
                str(d.get('actual_pnl', '')),
                f'"{reason}"'
            ])
            lines.append(line)

    return "\n".join(lines)


def get_bot_decision_summary(bot_name: str = None, days: int = 7) -> Dict:
    """
    Get summary statistics for bot decisions.

    Returns:
        {
            'total_decisions': int,
            'trades_executed': int,
            'stay_flat_count': int,
            'blocked_count': int,
            'by_type': {'ENTRY_SIGNAL': 10, ...},
            'by_bot': {'PHOENIX': 50, 'ATLAS': 20},
            'avg_confidence': float,
            'win_count': int,
            'loss_count': int,
            'total_pnl': float,
            'avg_position_size': float
        }
    """
    conn = get_db_connection()
    if not conn:
        return {}

    try:
        cursor = conn.cursor()

        params = [days]
        bot_filter = ""
        if bot_name:
            bot_filter = "AND full_decision->>'bot_name' = %s"
            params.append(bot_name)

        # Main stats
        cursor.execute(f"""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN action IN ('BUY', 'SELL') THEN 1 END) as trades,
                COUNT(CASE WHEN decision_type = 'NO_TRADE' THEN 1 END) as stay_flat,
                COUNT(CASE WHEN decision_type = 'RISK_CHECK' AND passed_risk_checks = false THEN 1 END) as blocked,
                AVG(prob_profit) as avg_confidence,
                COUNT(CASE WHEN actual_pnl > 0 THEN 1 END) as wins,
                COUNT(CASE WHEN actual_pnl < 0 THEN 1 END) as losses,
                SUM(COALESCE(actual_pnl, 0)) as total_pnl,
                AVG(position_size_dollars) as avg_position
            FROM trading_decisions
            WHERE timestamp >= NOW() - INTERVAL '%s days'
            {bot_filter}
        """, params)

        row = cursor.fetchone()

        # By decision type
        cursor.execute(f"""
            SELECT decision_type, COUNT(*)
            FROM trading_decisions
            WHERE timestamp >= NOW() - INTERVAL '%s days'
            {bot_filter}
            GROUP BY decision_type
        """, params)
        by_type = dict(cursor.fetchall())

        # By bot (if not filtered)
        by_bot = {}
        if not bot_name:
            cursor.execute("""
                SELECT
                    COALESCE(full_decision->>'bot_name', 'PHOENIX') as bot,
                    COUNT(*)
                FROM trading_decisions
                WHERE timestamp >= NOW() - INTERVAL '%s days'
                GROUP BY COALESCE(full_decision->>'bot_name', 'PHOENIX')
            """, [days])
            by_bot = dict(cursor.fetchall())

        cursor.close()
        conn.close()

        return {
            'total_decisions': row[0] or 0,
            'trades_executed': row[1] or 0,
            'stay_flat_count': row[2] or 0,
            'blocked_count': row[3] or 0,
            'avg_confidence': round(row[4] or 0, 1),
            'win_count': row[5] or 0,
            'loss_count': row[6] or 0,
            'total_pnl': round(row[7] or 0, 2),
            'avg_position_size': round(row[8] or 0, 2),
            'by_type': by_type,
            'by_bot': by_bot
        }

    except Exception as e:
        logger.error(f"Failed to get decision summary: {e}")
        return {}


def get_recent_decisions(bot_name: str = None, limit: int = 20) -> List[Dict]:
    """
    Get recent decisions for dashboard display.

    Returns simplified records with key fields for quick viewing.
    """
    conn = get_db_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()

        params = []
        bot_filter = ""
        if bot_name:
            bot_filter = "WHERE full_decision->>'bot_name' = %s"
            params.append(bot_name)

        cursor.execute(f"""
            SELECT
                decision_id,
                timestamp,
                decision_type,
                action,
                symbol,
                strategy,
                spot_price,
                primary_reason,
                position_size_dollars,
                actual_pnl,
                COALESCE(full_decision->>'bot_name', 'PHOENIX') as bot_name,
                COALESCE(full_decision->>'what', '') as what,
                COALESCE(full_decision->>'why', '') as why
            FROM trading_decisions
            {bot_filter}
            ORDER BY timestamp DESC
            LIMIT %s
        """, params + [limit])

        columns = [desc[0] for desc in cursor.description]
        results = []

        for row in cursor.fetchall():
            record = dict(zip(columns, row))
            if record.get('timestamp'):
                record['timestamp'] = record['timestamp'].isoformat() if hasattr(record['timestamp'], 'isoformat') else str(record['timestamp'])
            results.append(record)

        cursor.close()
        conn.close()

        return results

    except Exception as e:
        logger.error(f"Failed to get recent decisions: {e}")
        return []


# Bot-specific loggers for convenience
_bot_loggers: Dict[str, DecisionLogger] = {}


def get_phoenix_logger() -> DecisionLogger:
    """Get logger for PHOENIX bot (0DTE)"""
    if 'PHOENIX' not in _bot_loggers:
        _bot_loggers['PHOENIX'] = DecisionLogger()
    return _bot_loggers['PHOENIX']


def get_atlas_logger() -> DecisionLogger:
    """Get logger for ATLAS bot (Wheel)"""
    if 'ATLAS' not in _bot_loggers:
        _bot_loggers['ATLAS'] = DecisionLogger()
    return _bot_loggers['ATLAS']


def get_hermes_logger() -> DecisionLogger:
    """Get logger for HERMES (Manual Wheel)"""
    if 'HERMES' not in _bot_loggers:
        _bot_loggers['HERMES'] = DecisionLogger()
    return _bot_loggers['HERMES']


def get_oracle_logger() -> DecisionLogger:
    """Get logger for ORACLE (Advisor)"""
    if 'ORACLE' not in _bot_loggers:
        _bot_loggers['ORACLE'] = DecisionLogger()
    return _bot_loggers['ORACLE']


def get_ares_logger() -> DecisionLogger:
    """Get logger for ARES (Aggressive Iron Condor)"""
    if 'ARES' not in _bot_loggers:
        _bot_loggers['ARES'] = DecisionLogger()
    return _bot_loggers['ARES']


def get_athena_logger() -> DecisionLogger:
    """Get logger for ATHENA (Directional Spreads)"""
    if 'ATHENA' not in _bot_loggers:
        _bot_loggers['ATHENA'] = DecisionLogger()
    return _bot_loggers['ATHENA']
