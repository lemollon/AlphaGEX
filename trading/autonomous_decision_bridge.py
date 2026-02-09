"""
Autonomous Trader Decision Bridge

Integrates the DecisionTransparencyLogger with the Autonomous Paper Trader.
This provides full audit trail for every trading decision made by the bot.

Usage in autonomous_paper_trader.py:
    from trading.autonomous_decision_bridge import DecisionBridge

    # In __init__:
    self.decision_bridge = DecisionBridge()

    # When executing a trade:
    self.decision_bridge.log_trade_execution(
        trade_data=trade,
        gex_data=gex_data,
        option_data=option_price_data,
        contracts=contracts,
        entry_price=entry_price,
        regime=regime_classification
    )
"""

from datetime import datetime
from typing import Dict, Optional, Any
from zoneinfo import ZoneInfo
import logging

# Texas Central Time - standard timezone for all AlphaGEX operations
CENTRAL_TZ = ZoneInfo("America/Chicago")

from trading.decision_logger import (
    DecisionLogger,
    TradeDecision,
    DecisionType,
    DataSource,
    PriceSnapshot,
    MarketContext,
    BacktestReference,
    DecisionReasoning,
    BotName,
    TradeLeg
)

# Import comprehensive bot logger
try:
    from trading.bot_logger import (
        log_bot_decision, update_decision_outcome,
        BotDecision, MarketContext as BotLogMarketContext, ClaudeContext,
        Alternative, RiskCheck, ApiCall, ExecutionTimeline, generate_session_id,
        get_session_tracker  # For scan_cycle and decision_sequence tracking
    )
    BOT_LOGGER_AVAILABLE = True
    _phoenix_session_tracker = get_session_tracker("LAZARUS") if BOT_LOGGER_AVAILABLE else None
except ImportError:
    BOT_LOGGER_AVAILABLE = False
    log_bot_decision = None

logger = logging.getLogger(__name__)


class DecisionBridge:
    """
    Bridge between autonomous trader and decision transparency logger.

    Converts autonomous trader's internal data structures to
    the standardized TradeDecision format for full audit trail.
    """

    def __init__(self):
        self.logger = DecisionLogger()
        # Texas Central Time - standard timezone for all AlphaGEX operations
        self.tz = ZoneInfo("America/Chicago")

    def log_trade_execution(
        self,
        trade_data: Dict,
        gex_data: Dict,
        option_data: Dict,
        contracts: int,
        entry_price: float,
        regime: Any = None,
        backtest_stats: Dict = None,
        order_id: str = "",
        oracle_advice: Any = None  # ProphetPrediction with claude_analysis for transparency
    ) -> str:
        """
        Log a trade execution with full transparency.

        LOGS ALL CRITICAL TRADE DATA:
        - Strike, entry_price, expiration for each leg
        - Contracts, premium per contract
        - Greeks (delta, gamma, theta, vega, IV)
        - Order ID and fill details
        - Underlying price at entry
        - VIX level
        - REAL Claude AI prompts and responses (from oracle_advice.claude_analysis)

        Args:
            trade_data: Trade parameters (strike, dte, option_type, strategy, etc.)
            gex_data: GEX/gamma data (spot_price, net_gex, flip_point, etc.)
            option_data: Option pricing (bid, ask, mid, source, delta, gamma, etc.)
            contracts: Number of contracts
            entry_price: Actual entry price per share
            regime: Market regime classification
            backtest_stats: Statistics from backtested strategy
            order_id: Broker order ID if available
            oracle_advice: ProphetPrediction object with claude_analysis for real Claude data

        Returns:
            decision_id for later outcome update
        """
        now = datetime.now(self.tz)
        symbol = trade_data.get('symbol', 'SPY')
        option_type = trade_data.get('option_type', 'CALL')
        strike = trade_data.get('strike', 0)
        expiration = trade_data.get('expiration', '')
        dte = trade_data.get('dte', 0)

        # =====================================================================
        # BUILD TRADE LEG with ALL critical data
        # =====================================================================
        trade_leg = TradeLeg(
            leg_id=1,
            action="BUY",
            option_type=option_type.lower(),

            # REQUIRED: Strike and expiration
            strike=strike,
            expiration=expiration,

            # REQUIRED: Entry prices
            entry_price=entry_price,
            entry_bid=option_data.get('bid', 0) or 0,
            entry_ask=option_data.get('ask', 0) or 0,
            entry_mid=(option_data.get('bid', 0) + option_data.get('ask', 0)) / 2 if option_data.get('bid') else entry_price,

            # Position sizing
            contracts=contracts,
            premium_per_contract=entry_price * 100,

            # Greeks at entry
            delta=option_data.get('delta', 0) or 0,
            gamma=option_data.get('gamma', 0) or 0,
            theta=option_data.get('theta', 0) or 0,
            vega=option_data.get('vega', 0) or 0,
            iv=option_data.get('iv', 0) or 0,

            # Order execution
            order_id=order_id or trade_data.get('order_id', ''),
            fill_price=entry_price,
            fill_timestamp=now.isoformat(),
            order_status=trade_data.get('order_status', 'filled')
        )

        # Build underlying price snapshot
        underlying_snapshot = PriceSnapshot(
            symbol=symbol,
            price=gex_data.get('spot_price', 0),
            bid=0,
            ask=0,
            timestamp=now.isoformat(),
            source=DataSource.POLYGON_REALTIME
        )

        # Build option price snapshot (legacy support)
        option_source = self._determine_option_source(option_data)
        option_snapshot = PriceSnapshot(
            symbol=symbol,
            price=entry_price,
            bid=option_data.get('bid', 0) or 0,
            ask=option_data.get('ask', 0) or 0,
            timestamp=now.isoformat(),
            source=option_source,
            strike=strike,
            expiration=expiration,
            option_type=option_type,
            delta=option_data.get('delta', 0) or 0,
            gamma=option_data.get('gamma', 0) or 0,
            theta=option_data.get('theta', 0) or 0,
            iv=option_data.get('iv', 0) or 0
        )

        # Build market context
        market_context = MarketContext(
            timestamp=now.isoformat(),
            spot_price=gex_data.get('spot_price', 0),
            spot_source=DataSource.POLYGON_REALTIME,
            vix=gex_data.get('vix', 0) or 0,
            net_gex=gex_data.get('net_gex', 0) or 0,
            gex_regime=gex_data.get('mm_state', ''),
            flip_point=gex_data.get('flip_point', 0) or 0,
            call_wall=gex_data.get('call_wall', 0) or 0,
            put_wall=gex_data.get('put_wall', 0) or 0,
            regime=self._extract_regime_name(regime),
            trend=gex_data.get('trend', '')
        )

        # Build backtest reference if available
        backtest_ref = None
        if backtest_stats:
            backtest_ref = BacktestReference(
                strategy_name=trade_data.get('strategy', 'Unknown'),
                backtest_date=datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d'),
                win_rate=backtest_stats.get('win_rate', 0),
                expectancy=backtest_stats.get('expectancy', 0),
                avg_win=backtest_stats.get('avg_win', 0),
                avg_loss=backtest_stats.get('avg_loss', 0),
                sharpe_ratio=backtest_stats.get('sharpe_ratio', 0),
                total_trades=backtest_stats.get('total_trades', 0),
                max_drawdown=backtest_stats.get('max_drawdown', 0),
                backtest_period=backtest_stats.get('period', ''),
                uses_real_data=backtest_stats.get('uses_real_data', True),
                data_source="polygon",
                date_range=backtest_stats.get('period', '')
            )

        # Build reasoning
        supporting = self._extract_supporting_factors(trade_data, gex_data)
        regime_name = self._extract_regime_name(regime)
        if regime_name:
            supporting.append(f"Regime: {regime_name}")
        if trade_data.get('confidence', 0) > 70:
            supporting.append(f"High confidence: {trade_data.get('confidence')}%")

        reasoning = DecisionReasoning(
            primary_reason=trade_data.get('signal_reason', 'Automated signal'),
            supporting_factors=supporting,
            risk_factors=self._extract_risk_factors(trade_data, gex_data)
        )

        # Build WHAT/WHY/HOW for transparency
        strategy_name = trade_data.get('strategy', 'Unknown')

        what_summary = f"BUY {contracts}x {symbol} ${strike}{option_type[0]} exp {expiration} @ ${entry_price:.2f}"

        why_summary = (
            f"Strategy: {strategy_name}. "
            f"Primary: {trade_data.get('signal_reason', 'Automated signal')}. "
            f"GEX Regime: {gex_data.get('mm_state', 'Unknown')}. "
            f"Net GEX: ${gex_data.get('net_gex', 0)/1e9:.2f}B. "
            f"VIX: {gex_data.get('vix', 0):.1f}. "
            f"Delta: {option_data.get('delta', 0):.2f}. "
            f"IV: {option_data.get('iv', 0)*100:.1f}%. "
            f"Confidence: {trade_data.get('confidence', 0)}%"
        )

        how_summary = (
            f"Position sizing: {trade_data.get('sizing_method', 'risk_based')}. "
            f"Contracts: {contracts} @ ${entry_price:.2f}/share = ${contracts * entry_price * 100:,.0f} total. "
            f"Strike: ${strike}, Exp: {expiration} ({dte}d). "
            f"Bid/Ask: ${option_data.get('bid', 0):.2f}/${option_data.get('ask', 0):.2f}. "
            f"Win rate: {backtest_stats.get('win_rate', 0):.0f}% "
            f"(from {backtest_stats.get('total_trades', 0)} trades). "
            f"Kelly: {trade_data.get('kelly_pct', 'N/A')}"
        ) if backtest_stats else (
            f"Position sizing: {trade_data.get('sizing_method', 'risk_based')}. "
            f"Contracts: {contracts} @ ${entry_price:.2f}/share = ${contracts * entry_price * 100:,.0f} total. "
            f"Strike: ${strike}, Exp: {expiration} ({dte}d). "
            f"Bid/Ask: ${option_data.get('bid', 0):.2f}/${option_data.get('ask', 0):.2f}."
        )

        # Build the full decision with legs array
        decision = TradeDecision(
            decision_id="",
            timestamp=now.isoformat(),
            decision_type=DecisionType.ENTRY_SIGNAL,
            bot_name=BotName.LAZARUS,
            what=what_summary,
            why=why_summary,
            how=how_summary,
            action="BUY",
            symbol=symbol,
            strategy=trade_data.get('strategy', 'Unknown'),
            legs=[trade_leg],  # Trade leg with complete data
            underlying_snapshot=underlying_snapshot,
            option_snapshot=option_snapshot,
            underlying_price_at_entry=gex_data.get('spot_price', 0),
            market_context=market_context,
            backtest_reference=backtest_ref,
            reasoning=reasoning,
            position_size_dollars=contracts * entry_price * 100,
            position_size_contracts=contracts,
            position_size_method=trade_data.get('sizing_method', 'risk_based'),
            max_risk_dollars=contracts * entry_price * 100,
            target_profit_pct=trade_data.get('target_pct', 50),
            stop_loss_pct=trade_data.get('stop_pct', 50),
            expected_hold_days=dte,
            probability_of_profit=trade_data.get('pop', 0),
            order_id=order_id or trade_data.get('order_id', '')
        )

        # Log and return decision_id
        decision_id = self.logger.log_decision(decision)
        logger.info(f"Logged trade execution: {decision_id}")

        # === COMPREHENSIVE BOT LOGGER ===
        if BOT_LOGGER_AVAILABLE and log_bot_decision:
            try:
                # Build risk checks
                risk_checks = []
                vix = gex_data.get('vix', 0) or 0
                if vix > 0:
                    risk_checks.append(RiskCheck(
                        check_name="VIX_LEVEL",
                        passed=vix <= 35,
                        current_value=vix,
                        limit_value=35,
                        message=f"VIX at {vix:.1f}"
                    ))

                # Build alternatives from trade_data if available, otherwise note none recorded
                alt_objs = []
                alternatives_list = trade_data.get('alternatives_considered', [])
                for alt in alternatives_list:
                    if isinstance(alt, dict):
                        alt_objs.append(Alternative(
                            strike=alt.get('strike', 0),
                            strategy=alt.get('strategy', ''),
                            reason_rejected=alt.get('reason_rejected', '')
                        ))

                # Build Claude context from oracle_advice if available
                claude_ctx = None
                if oracle_advice and hasattr(oracle_advice, 'claude_analysis') and oracle_advice.claude_analysis:
                    ca = oracle_advice.claude_analysis
                    claude_ctx = ClaudeContext(
                        prompt=ca.raw_prompt or "",
                        response=ca.raw_response or "",
                        model=ca.model_used or "",
                        tokens_used=ca.tokens_used or 0,
                        response_time_ms=ca.response_time_ms or 0,
                        confidence=ca.recommendation or "",
                        warnings=ca.risk_factors or []
                    )

                comprehensive = BotDecision(
                    bot_name="LAZARUS",
                    decision_type="ENTRY",
                    action="BUY",
                    symbol=symbol,
                    strategy=trade_data.get('strategy', 'Unknown'),
                    strike=strike,
                    expiration=expiration,
                    option_type=option_type,
                    contracts=contracts,
                    session_id=_phoenix_session_tracker.session_id if _phoenix_session_tracker else generate_session_id(),
                    scan_cycle=_phoenix_session_tracker.current_cycle if _phoenix_session_tracker else 0,
                    decision_sequence=_phoenix_session_tracker.next_decision() if _phoenix_session_tracker else 0,
                    market_context=BotLogMarketContext(
                        spot_price=gex_data.get('spot_price', 0),
                        vix=vix,
                        net_gex=gex_data.get('net_gex', 0) or 0,
                        gex_regime=gex_data.get('mm_state', ''),
                        flip_point=gex_data.get('flip_point', 0) or 0,
                        call_wall=gex_data.get('call_wall', 0) or 0,
                        put_wall=gex_data.get('put_wall', 0) or 0,
                    ),
                    claude_context=claude_ctx,  # REAL Claude data from Prophet
                    entry_reasoning=trade_data.get('signal_reason', 'Automated signal'),
                    strike_reasoning=f"Strike ${strike} selected based on delta {option_data.get('delta', 0):.2f}",
                    size_reasoning=f"{contracts} contracts @ ${entry_price:.2f}",
                    alternatives_considered=alt_objs if alt_objs else None,
                    kelly_pct=trade_data.get('kelly_pct', 0) or 0,
                    position_size_dollars=contracts * entry_price * 100,
                    max_risk_dollars=contracts * entry_price * 100,
                    backtest_win_rate=backtest_stats.get('win_rate', 0) if backtest_stats else 0,
                    backtest_expectancy=backtest_stats.get('expectancy', 0) if backtest_stats else 0,
                    risk_checks=risk_checks,
                    passed_all_checks=True,
                    execution=ExecutionTimeline(
                        order_submitted_at=now,
                        expected_fill_price=entry_price,
                        actual_fill_price=entry_price,
                        broker_order_id=order_id or trade_data.get('order_id', ''),
                        broker_status="FILLED",
                    ),
                )
                comp_id = log_bot_decision(comprehensive)
                logger.info(f"Logged to bot_decision_logs (ENTRY): {comp_id}")
            except Exception as e:
                logger.warning(f"Could not log to comprehensive table: {e}")

        return decision_id

    def log_no_trade(
        self,
        symbol: str,
        spot_price: float,
        reason: str,
        gex_data: Dict = None,
        regime: Any = None,
        oracle_advice: Any = None  # ProphetPrediction with claude_analysis for transparency
    ) -> str:
        """Log when no trade is taken (equally important for audit)"""
        now = datetime.now(self.tz)

        underlying_snapshot = PriceSnapshot(
            symbol=symbol,
            price=spot_price,
            timestamp=now.isoformat(),
            source=DataSource.POLYGON_REALTIME
        )

        market_context = MarketContext(
            timestamp=now.isoformat(),
            spot_price=spot_price,
            spot_source=DataSource.POLYGON_REALTIME,
            vix=gex_data.get('vix', 0) if gex_data else 0,
            net_gex=gex_data.get('net_gex', 0) if gex_data else 0,
            gex_regime=gex_data.get('mm_state', '') if gex_data else '',
            regime=self._extract_regime_name(regime)
        )

        reasoning = DecisionReasoning(
            primary_reason=reason,
            supporting_factors=[],
            risk_factors=[reason]
        )

        # Build WHAT/WHY/HOW for transparency
        what_summary = f"NO TRADE for {symbol} - Market scan completed"
        why_summary = f"Reason: {reason}. VIX: {gex_data.get('vix', 0):.1f}. " if gex_data else f"Reason: {reason}."
        how_summary = "Automated scan found no actionable setup matching criteria."

        decision = TradeDecision(
            decision_id="",
            timestamp=now.isoformat(),
            decision_type=DecisionType.NO_TRADE,
            bot_name=BotName.LAZARUS,
            what=what_summary,
            why=why_summary,
            how=how_summary,
            action="SKIP",
            symbol=symbol,
            strategy="N/A",
            underlying_snapshot=underlying_snapshot,
            market_context=market_context,
            reasoning=reasoning,
            passed_risk_checks=False,
            risk_check_details=[reason]
        )

        decision_id = self.logger.log_decision(decision)

        # === COMPREHENSIVE BOT LOGGER (SKIP) ===
        if BOT_LOGGER_AVAILABLE and log_bot_decision:
            try:
                # Build Claude context from oracle_advice if available
                claude_ctx = None
                if oracle_advice and hasattr(oracle_advice, 'claude_analysis') and oracle_advice.claude_analysis:
                    ca = oracle_advice.claude_analysis
                    claude_ctx = ClaudeContext(
                        prompt=ca.raw_prompt or "",
                        response=ca.raw_response or "",
                        model=ca.model_used or "",
                        tokens_used=ca.tokens_used or 0,
                        response_time_ms=ca.response_time_ms or 0,
                        confidence=ca.recommendation or "",
                        warnings=ca.risk_factors or []
                    )

                comprehensive = BotDecision(
                    bot_name="LAZARUS",
                    decision_type="SKIP",
                    action="SKIP",
                    symbol=symbol,
                    strategy="N/A",
                    session_id=_phoenix_session_tracker.session_id if _phoenix_session_tracker else generate_session_id(),
                    scan_cycle=_phoenix_session_tracker.current_cycle if _phoenix_session_tracker else 0,
                    decision_sequence=_phoenix_session_tracker.next_decision() if _phoenix_session_tracker else 0,
                    market_context=BotLogMarketContext(
                        spot_price=spot_price,
                        vix=gex_data.get('vix', 0) if gex_data else 0,
                        net_gex=gex_data.get('net_gex', 0) if gex_data else 0,
                        gex_regime=gex_data.get('mm_state', '') if gex_data else '',
                    ),
                    claude_context=claude_ctx,  # REAL Claude data from Prophet
                    entry_reasoning=reason,
                    passed_all_checks=False,
                    blocked_reason=reason,
                )
                comp_id = log_bot_decision(comprehensive)
                logger.info(f"Logged to bot_decision_logs (SKIP): {comp_id}")
            except Exception as e:
                logger.warning(f"Could not log SKIP to comprehensive table: {e}")

        return decision_id

    def log_exit(
        self,
        symbol: str,
        decision_id: str,
        exit_price: float,
        pnl: float,
        hold_days: int,
        reason: str,
        underlying_price_at_exit: float = 0,
        exit_bid: float = 0,
        exit_ask: float = 0
    ):
        """
        Log trade exit and update outcome.

        Captures EXIT data:
        - exit_price per share
        - underlying price at exit
        - bid/ask at exit
        - realized P&L
        - hold time
        """
        self.logger.update_outcome(
            decision_id=decision_id,
            actual_entry_price=0,  # Already logged in entry
            actual_exit_price=exit_price,
            actual_pnl=pnl,
            actual_hold_days=hold_days,
            notes=f"{reason}. Exit bid/ask: ${exit_bid:.2f}/${exit_ask:.2f}. Underlying at exit: ${underlying_price_at_exit:.2f}"
        )
        logger.info(f"Updated exit for {decision_id}: P&L=${pnl:.2f}, Exit=${exit_price:.2f}")

        # === COMPREHENSIVE BOT LOGGER (EXIT) ===
        if BOT_LOGGER_AVAILABLE and log_bot_decision:
            try:
                now = datetime.now(self.tz)
                comprehensive = BotDecision(
                    bot_name="LAZARUS",
                    decision_type="EXIT",
                    action="SELL",
                    symbol=symbol,
                    strategy="exit",
                    session_id=_phoenix_session_tracker.session_id if _phoenix_session_tracker else generate_session_id(),
                    scan_cycle=_phoenix_session_tracker.current_cycle if _phoenix_session_tracker else 0,
                    decision_sequence=_phoenix_session_tracker.next_decision() if _phoenix_session_tracker else 0,
                    market_context=BotLogMarketContext(
                        spot_price=underlying_price_at_exit,
                    ),
                    exit_reasoning=reason,
                    actual_pnl=pnl,
                    exit_triggered_by=reason,
                    exit_timestamp=now,
                    exit_price=exit_price,
                    outcome_correct=pnl > 0,
                    outcome_notes=f"Hold {hold_days} days. Exit bid/ask: ${exit_bid:.2f}/${exit_ask:.2f}",
                )
                comp_id = log_bot_decision(comprehensive)
                logger.info(f"Logged to bot_decision_logs (EXIT): {comp_id}")
            except Exception as e:
                logger.warning(f"Could not log EXIT to comprehensive table: {e}")

    def _determine_option_source(self, option_data: Dict) -> DataSource:
        """Determine data source from option data flags"""
        if option_data.get('is_delayed'):
            return DataSource.POLYGON_HISTORICAL
        elif option_data.get('theoretical_price'):
            return DataSource.CALCULATED
        elif option_data.get('from_tradier'):
            return DataSource.TRADIER_LIVE
        else:
            return DataSource.POLYGON_REALTIME

    def _extract_regime_name(self, regime: Any) -> str:
        """Extract regime name from classification object"""
        if regime is None:
            return ""
        if hasattr(regime, 'regime'):
            return str(regime.regime)
        if hasattr(regime, 'name'):
            return regime.name
        if isinstance(regime, dict):
            return regime.get('regime', regime.get('name', ''))
        return str(regime)

    def _extract_supporting_factors(self, trade_data: Dict, gex_data: Dict) -> list:
        """Extract supporting factors for the trade"""
        factors = []

        if trade_data.get('signal_strength', 0) > 70:
            factors.append(f"High signal strength: {trade_data.get('signal_strength')}%")

        if gex_data.get('mm_state') == 'LONG_GAMMA':
            factors.append("Positive gamma (dealers long gamma)")

        if trade_data.get('trend_aligned'):
            factors.append("Trade aligned with trend")

        if trade_data.get('volume_confirmed'):
            factors.append("Volume confirmation present")

        if trade_data.get('psychology_trap'):
            factors.append(f"Psychology trap detected: {trade_data.get('psychology_trap')}")

        return factors

    def _extract_risk_factors(self, trade_data: Dict, gex_data: Dict) -> list:
        """Extract risk factors for the trade"""
        risks = []

        vix = gex_data.get('vix', 0) or 0
        if vix > 25:
            risks.append(f"Elevated VIX: {vix:.1f}")

        if gex_data.get('mm_state') == 'SHORT_GAMMA':
            risks.append("Negative gamma (increased volatility expected)")

        if trade_data.get('near_expiration'):
            risks.append("Near expiration - increased gamma risk")

        if trade_data.get('wide_spread'):
            risks.append("Wide bid-ask spread")

        return risks


# Convenience function for integration
def get_decision_bridge() -> DecisionBridge:
    """Get singleton decision bridge instance"""
    if not hasattr(get_decision_bridge, '_instance'):
        get_decision_bridge._instance = DecisionBridge()
    return get_decision_bridge._instance
