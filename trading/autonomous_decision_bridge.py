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

from trading.decision_logger import (
    DecisionLogger,
    TradeDecision,
    DecisionType,
    DataSource,
    PriceSnapshot,
    MarketContext,
    BacktestReference,
    DecisionReasoning
)

logger = logging.getLogger(__name__)


class DecisionBridge:
    """
    Bridge between autonomous trader and decision transparency logger.

    Converts autonomous trader's internal data structures to
    the standardized TradeDecision format for full audit trail.
    """

    def __init__(self):
        self.logger = DecisionLogger()
        self.tz = ZoneInfo("America/New_York")

    def log_trade_execution(
        self,
        trade_data: Dict,
        gex_data: Dict,
        option_data: Dict,
        contracts: int,
        entry_price: float,
        regime: Any = None,
        backtest_stats: Dict = None
    ) -> str:
        """
        Log a trade execution with full transparency.

        Args:
            trade_data: Trade parameters (strike, dte, option_type, strategy, etc.)
            gex_data: GEX/gamma data (spot_price, net_gex, flip_point, etc.)
            option_data: Option pricing (bid, ask, mid, source, etc.)
            contracts: Number of contracts
            entry_price: Actual entry price per share
            regime: Market regime classification
            backtest_stats: Statistics from backtested strategy

        Returns:
            decision_id for later outcome update
        """
        now = datetime.now(self.tz)
        symbol = trade_data.get('symbol', 'SPY')

        # Build underlying price snapshot
        underlying_snapshot = PriceSnapshot(
            symbol=symbol,
            price=gex_data.get('spot_price', 0),
            bid=0,  # Underlying bid/ask if available
            ask=0,
            timestamp=now.isoformat(),
            source=DataSource.POLYGON_REALTIME  # Default source
        )

        # Build option price snapshot
        option_source = self._determine_option_source(option_data)
        option_snapshot = PriceSnapshot(
            symbol=symbol,
            price=entry_price,
            bid=option_data.get('bid', 0) or 0,
            ask=option_data.get('ask', 0) or 0,
            timestamp=now.isoformat(),
            source=option_source,
            strike=trade_data.get('strike', 0),
            expiration=trade_data.get('expiration', ''),
            option_type=trade_data.get('option_type', ''),
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
                win_rate=backtest_stats.get('win_rate', 0),
                expectancy=backtest_stats.get('expectancy', 0),
                total_trades=backtest_stats.get('total_trades', 0),
                max_drawdown=backtest_stats.get('max_drawdown', 0),
                sharpe_ratio=backtest_stats.get('sharpe_ratio', 0),
                backtest_period=backtest_stats.get('period', ''),
                uses_real_data=backtest_stats.get('uses_real_data', False)
            )

        # Build reasoning
        supporting = self._extract_supporting_factors(trade_data, gex_data)
        # Add regime alignment as a supporting factor
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

        # Build the full decision
        decision = TradeDecision(
            decision_id="",  # Will be generated
            timestamp=now.isoformat(),
            decision_type=DecisionType.ENTRY_SIGNAL,
            action="BUY",
            symbol=symbol,
            strategy=trade_data.get('strategy', 'Unknown'),
            underlying_snapshot=underlying_snapshot,
            option_snapshot=option_snapshot,
            market_context=market_context,
            backtest_reference=backtest_ref,
            reasoning=reasoning,
            position_size_dollars=contracts * entry_price * 100,
            position_size_contracts=contracts,
            position_size_method=trade_data.get('sizing_method', 'risk_based'),
            max_risk_dollars=contracts * entry_price * 100,  # Max loss = premium
            target_profit_pct=trade_data.get('target_pct', 50),
            stop_loss_pct=trade_data.get('stop_pct', 50),
            expected_hold_days=trade_data.get('dte', 7),
            probability_of_profit=trade_data.get('pop', 0)
        )

        # Log and return decision_id
        decision_id = self.logger.log_decision(decision)
        logger.info(f"Logged trade execution: {decision_id}")

        return decision_id

    def log_no_trade(
        self,
        symbol: str,
        spot_price: float,
        reason: str,
        gex_data: Dict = None,
        regime: Any = None
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

        decision = TradeDecision(
            decision_id="",
            timestamp=now.isoformat(),
            decision_type=DecisionType.NO_TRADE,
            action="SKIP",
            symbol=symbol,
            strategy="N/A",
            underlying_snapshot=underlying_snapshot,
            market_context=market_context,
            reasoning=reasoning,
            passed_risk_checks=False,
            risk_check_details=[reason]
        )

        return self.logger.log_decision(decision)

    def log_exit(
        self,
        symbol: str,
        decision_id: str,
        exit_price: float,
        pnl: float,
        hold_days: int,
        reason: str
    ):
        """Log trade exit and update outcome"""
        self.logger.update_outcome(
            decision_id=decision_id,
            actual_entry_price=0,  # Already logged
            actual_exit_price=exit_price,
            actual_pnl=pnl,
            actual_hold_days=hold_days,
            notes=reason
        )
        logger.info(f"Updated exit for {decision_id}: P&L=${pnl:.2f}")

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
