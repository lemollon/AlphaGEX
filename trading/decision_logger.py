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
    backtest_date: str

    # Stats from backtest
    win_rate: float
    expectancy: float
    avg_win: float
    avg_loss: float
    sharpe_ratio: float
    total_trades: int

    # Data quality
    uses_real_data: bool
    data_source: str
    date_range: str


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

    # What was decided
    action: str  # 'BUY', 'SELL', 'HOLD', 'SKIP'
    symbol: str
    strategy: str

    # Prices used
    underlying_snapshot: PriceSnapshot
    option_snapshot: Optional[PriceSnapshot] = None

    # Market context
    market_context: MarketContext = None

    # Backtest backing
    backtest_reference: Optional[BacktestReference] = None

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
        self.tz = ZoneInfo("America/New_York")
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
