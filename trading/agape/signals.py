"""
AGAPE Signal Generator - Generates directional /MET trade signals.

Uses crypto market microstructure (funding, OI, liquidations, crypto GEX)
as the equivalent of GEX-based signal generation used by ARES/ATHENA.

Signal Flow:
  1. Fetch crypto market snapshot (CryptoDataProvider)
  2. Analyze microstructure signals
  3. Consult Oracle for approval
  4. Calculate position size and risk levels
  5. Return AgapeSignal with full audit trail
"""

import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from zoneinfo import ZoneInfo

from trading.agape.models import (
    AgapeConfig,
    AgapeSignal,
    SignalAction,
    PositionSide,
)

logger = logging.getLogger(__name__)

CENTRAL_TZ = ZoneInfo("America/Chicago")

# Graceful imports
CryptoDataProvider = None
get_crypto_data_provider = None
try:
    from data.crypto_data_provider import (
        CryptoDataProvider,
        get_crypto_data_provider,
        CryptoMarketSnapshot,
    )
    logger.info("AGAPE Signals: CryptoDataProvider loaded")
except ImportError as e:
    logger.warning(f"AGAPE Signals: CryptoDataProvider not available: {e}")

OracleAdvisor = None
try:
    from quant.oracle_advisor import OracleAdvisor
    logger.info("AGAPE Signals: OracleAdvisor loaded")
except ImportError as e:
    logger.warning(f"AGAPE Signals: OracleAdvisor not available: {e}")


class AgapeSignalGenerator:
    """Generates directional trade signals for /MET based on crypto microstructure.

    GEX → Crypto Signal Mapping Applied:
        ARGUS gamma regime   → Funding rate regime
        ARGUS gamma walls    → OI clusters + liquidation zones
        ARGUS flip point     → Max pain level
        ARGUS net GEX        → Crypto GEX from Deribit
        ARGUS market signals → Combined crypto signals (6 inputs)
    """

    def __init__(self, config: AgapeConfig):
        self.config = config
        self._crypto_provider = None
        self._oracle = None

        if get_crypto_data_provider:
            try:
                self._crypto_provider = get_crypto_data_provider()
            except Exception as e:
                logger.warning(f"AGAPE Signals: Crypto provider init failed: {e}")

        if OracleAdvisor:
            try:
                self._oracle = OracleAdvisor()
            except Exception as e:
                logger.warning(f"AGAPE Signals: Oracle init failed: {e}")

    def get_market_data(self) -> Optional[Dict[str, Any]]:
        """Fetch current market snapshot - equivalent to ARES's get_market_data().

        Returns crypto microstructure data instead of options/GEX data.
        """
        if not self._crypto_provider:
            logger.error("AGAPE Signals: No crypto data provider")
            return None

        try:
            snapshot = self._crypto_provider.get_snapshot(self.config.ticker)
            if not snapshot or snapshot.spot_price <= 0:
                logger.warning("AGAPE Signals: Invalid snapshot (no spot price)")
                return None

            return {
                "symbol": snapshot.symbol,
                "spot_price": snapshot.spot_price,
                "timestamp": snapshot.timestamp,
                # Funding Rate (→ Gamma Regime)
                "funding_rate": snapshot.funding_rate.rate if snapshot.funding_rate else 0,
                "funding_regime": snapshot.funding_regime,
                # Liquidations (→ Gamma Walls / Magnets)
                "nearest_long_liq": snapshot.nearest_long_liq,
                "nearest_short_liq": snapshot.nearest_short_liq,
                "squeeze_risk": snapshot.squeeze_risk,
                "liquidation_clusters": len(snapshot.liquidation_clusters),
                # L/S Ratio (→ Directional Bias)
                "ls_ratio": snapshot.ls_ratio.ratio if snapshot.ls_ratio else 1.0,
                "ls_bias": snapshot.ls_ratio.bias if snapshot.ls_ratio else "NEUTRAL",
                # OI / Max Pain (→ Flip Point)
                "max_pain": snapshot.max_pain,
                # Crypto GEX (→ Direct GEX)
                "crypto_gex": snapshot.crypto_gex.net_gex if snapshot.crypto_gex else 0,
                "crypto_gex_regime": (
                    snapshot.crypto_gex.gamma_regime if snapshot.crypto_gex else "NEUTRAL"
                ),
                # Derived signals
                "leverage_regime": snapshot.leverage_regime,
                "directional_bias": snapshot.directional_bias,
                "volatility_regime": snapshot.volatility_regime,
                "combined_signal": snapshot.combined_signal,
                "combined_confidence": snapshot.combined_confidence,
            }
        except Exception as e:
            logger.error(f"AGAPE Signals: Market data fetch failed: {e}")
            return None

    def get_oracle_advice(self, market_data: Dict) -> Dict[str, Any]:
        """Consult Oracle for trade approval.

        Adapts the Oracle call for crypto context - passes crypto microstructure
        data where Oracle expects GEX/VIX data.
        """
        if not self._oracle:
            logger.info("AGAPE Signals: Oracle not available, using signal-only mode")
            return {
                "advice": "UNAVAILABLE",
                "win_probability": 0.5,
                "confidence": 0.0,
                "top_factors": ["oracle_unavailable"],
            }

        try:
            # Map crypto data to Oracle's expected format
            oracle_input = {
                "symbol": market_data.get("symbol", "ETH"),
                "spot_price": market_data["spot_price"],
                "vix": self._funding_to_vix_proxy(market_data.get("funding_rate", 0)),
                "gex_regime": market_data.get("crypto_gex_regime", "NEUTRAL"),
                "net_gex": market_data.get("crypto_gex", 0),
                "flip_point": market_data.get("max_pain", market_data["spot_price"]),
                # Additional context
                "funding_rate": market_data.get("funding_rate", 0),
                "funding_regime": market_data.get("funding_regime", "UNKNOWN"),
                "ls_ratio": market_data.get("ls_ratio", 1.0),
                "squeeze_risk": market_data.get("squeeze_risk", "LOW"),
                "asset_class": "crypto",
            }

            result = self._oracle.get_recommendation(oracle_input)
            if result:
                return {
                    "advice": result.get("recommendation", "SKIP"),
                    "win_probability": float(result.get("win_probability", 0.5)),
                    "confidence": float(result.get("confidence", 0)),
                    "top_factors": result.get("top_factors", []),
                }
        except Exception as e:
            logger.error(f"AGAPE Signals: Oracle call failed: {e}")

        return {
            "advice": "UNAVAILABLE",
            "win_probability": 0.5,
            "confidence": 0.0,
            "top_factors": ["oracle_error"],
        }

    def generate_signal(
        self, oracle_data: Optional[Dict] = None
    ) -> AgapeSignal:
        """Generate a trade signal - main entry point.

        Equivalent to ARES's generate_signal() but for directional /MET trades.

        Flow:
          1. Fetch crypto market microstructure
          2. Evaluate combined signal strength
          3. Consult Oracle (if not pre-fetched)
          4. Calculate position sizing and risk levels
          5. Return AgapeSignal with full context
        """
        now = datetime.now(CENTRAL_TZ)

        # Step 1: Get market data
        market_data = self.get_market_data()
        if not market_data:
            return AgapeSignal(
                spot_price=0,
                timestamp=now,
                action=SignalAction.WAIT,
                reasoning="NO_MARKET_DATA",
            )

        spot = market_data["spot_price"]

        # Step 2: Get Oracle advice
        if oracle_data is None:
            oracle_data = self.get_oracle_advice(market_data)

        # Step 3: Check Oracle approval (ORACLE IS GOD)
        oracle_advice = oracle_data.get("advice", "UNAVAILABLE")
        oracle_win_prob = oracle_data.get("win_probability", 0.5)

        if self.config.require_oracle_approval:
            oracle_approved = oracle_advice in (
                "TRADE_FULL", "TRADE_REDUCED", "ENTER", "TRADE",
            )
            if not oracle_approved and oracle_advice != "UNAVAILABLE":
                return AgapeSignal(
                    spot_price=spot,
                    timestamp=now,
                    funding_rate=market_data.get("funding_rate", 0),
                    funding_regime=market_data.get("funding_regime", "UNKNOWN"),
                    ls_ratio=market_data.get("ls_ratio", 1.0),
                    ls_bias=market_data.get("ls_bias", "NEUTRAL"),
                    squeeze_risk=market_data.get("squeeze_risk", "LOW"),
                    leverage_regime=market_data.get("leverage_regime", "UNKNOWN"),
                    max_pain=market_data.get("max_pain"),
                    crypto_gex=market_data.get("crypto_gex", 0),
                    crypto_gex_regime=market_data.get("crypto_gex_regime", "NEUTRAL"),
                    action=SignalAction.WAIT,
                    confidence="LOW",
                    reasoning=f"BLOCKED_ORACLE_{oracle_advice}",
                    oracle_advice=oracle_advice,
                    oracle_win_probability=oracle_win_prob,
                    oracle_confidence=oracle_data.get("confidence", 0),
                    oracle_top_factors=oracle_data.get("top_factors", []),
                )

        # Step 4: Determine trade direction from combined signal
        combined_signal = market_data.get("combined_signal", "WAIT")
        combined_confidence = market_data.get("combined_confidence", "LOW")

        action, side, reasoning = self._determine_action(
            combined_signal, combined_confidence, market_data
        )

        if action == SignalAction.WAIT:
            return AgapeSignal(
                spot_price=spot,
                timestamp=now,
                funding_rate=market_data.get("funding_rate", 0),
                funding_regime=market_data.get("funding_regime", "UNKNOWN"),
                ls_ratio=market_data.get("ls_ratio", 1.0),
                ls_bias=market_data.get("ls_bias", "NEUTRAL"),
                squeeze_risk=market_data.get("squeeze_risk", "LOW"),
                leverage_regime=market_data.get("leverage_regime", "UNKNOWN"),
                max_pain=market_data.get("max_pain"),
                crypto_gex=market_data.get("crypto_gex", 0),
                crypto_gex_regime=market_data.get("crypto_gex_regime", "NEUTRAL"),
                action=SignalAction.WAIT,
                confidence=combined_confidence,
                reasoning=reasoning,
                oracle_advice=oracle_advice,
                oracle_win_probability=oracle_win_prob,
                oracle_confidence=oracle_data.get("confidence", 0),
                oracle_top_factors=oracle_data.get("top_factors", []),
            )

        # Step 5: Calculate position sizing and levels
        contracts, max_risk = self._calculate_position_size(spot)
        stop_loss, take_profit = self._calculate_levels(spot, side, market_data)

        return AgapeSignal(
            spot_price=spot,
            timestamp=now,
            funding_rate=market_data.get("funding_rate", 0),
            funding_regime=market_data.get("funding_regime", "UNKNOWN"),
            ls_ratio=market_data.get("ls_ratio", 1.0),
            ls_bias=market_data.get("ls_bias", "NEUTRAL"),
            nearest_long_liq=market_data.get("nearest_long_liq"),
            nearest_short_liq=market_data.get("nearest_short_liq"),
            squeeze_risk=market_data.get("squeeze_risk", "LOW"),
            leverage_regime=market_data.get("leverage_regime", "UNKNOWN"),
            max_pain=market_data.get("max_pain"),
            crypto_gex=market_data.get("crypto_gex", 0),
            crypto_gex_regime=market_data.get("crypto_gex_regime", "NEUTRAL"),
            action=action,
            confidence=combined_confidence,
            reasoning=reasoning,
            oracle_advice=oracle_advice,
            oracle_win_probability=oracle_win_prob,
            oracle_confidence=oracle_data.get("confidence", 0),
            oracle_top_factors=oracle_data.get("top_factors", []),
            side=side,
            entry_price=spot,
            stop_loss=stop_loss,
            take_profit=take_profit,
            contracts=contracts,
            max_risk_usd=max_risk,
        )

    def _determine_action(
        self,
        combined_signal: str,
        confidence: str,
        market_data: Dict,
    ) -> Tuple[SignalAction, Optional[str], str]:
        """Translate combined crypto signal into trade action.

        Maps crypto signals to ARES-equivalent actions:
          LONG       → Buy /MET (bullish directional)
          SHORT      → Sell /MET (bearish directional)
          RANGE_BOUND → WAIT (future: could sell straddles)
          WAIT       → No trade
        """
        min_confidence = self.config.min_confidence

        # Check minimum confidence
        confidence_rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        if confidence_rank.get(confidence, 0) < confidence_rank.get(min_confidence, 2):
            return (SignalAction.WAIT, None, f"LOW_CONFIDENCE_{confidence}")

        if combined_signal == "LONG":
            reasoning = self._build_reasoning("LONG", market_data)
            return (SignalAction.LONG, "long", reasoning)

        elif combined_signal == "SHORT":
            reasoning = self._build_reasoning("SHORT", market_data)
            return (SignalAction.SHORT, "short", reasoning)

        elif combined_signal == "RANGE_BOUND":
            # For now, skip range-bound (future: premium selling)
            return (SignalAction.WAIT, None, "RANGE_BOUND_NO_STRATEGY_YET")

        return (SignalAction.WAIT, None, f"NO_SIGNAL_{combined_signal}")

    def _build_reasoning(self, direction: str, market_data: Dict) -> str:
        """Build human-readable reasoning string."""
        parts = [direction]

        fr = market_data.get("funding_regime", "UNKNOWN")
        parts.append(f"funding={fr}")

        ls = market_data.get("ls_bias", "NEUTRAL")
        parts.append(f"ls_bias={ls}")

        sq = market_data.get("squeeze_risk", "LOW")
        if sq in ("HIGH", "ELEVATED"):
            parts.append(f"squeeze={sq}")

        gex = market_data.get("crypto_gex_regime", "NEUTRAL")
        parts.append(f"crypto_gex={gex}")

        mp = market_data.get("max_pain")
        spot = market_data.get("spot_price", 0)
        if mp and spot:
            dist = ((mp - spot) / spot) * 100
            parts.append(f"max_pain_dist={dist:+.1f}%")

        return " | ".join(parts)

    def _calculate_position_size(self, spot_price: float) -> Tuple[int, float]:
        """Calculate position size based on risk parameters.

        /MET: Each $1 move in ETH = $0.10 per contract.
        Risk per trade = config.risk_per_trade_pct of capital.
        """
        capital = self.config.starting_capital
        max_risk_usd = capital * (self.config.risk_per_trade_pct / 100)

        # Risk per contract based on stop distance
        # Default: 2% stop → $0.10 * spot * 0.02 per contract
        stop_distance = spot_price * (self.config.stop_loss_pct / 100 * 0.02)
        risk_per_contract = stop_distance * self.config.contract_size

        if risk_per_contract <= 0:
            return (1, max_risk_usd)

        contracts = int(max_risk_usd / risk_per_contract)
        contracts = max(1, min(contracts, self.config.max_contracts))

        actual_risk = contracts * risk_per_contract
        return (contracts, round(actual_risk, 2))

    def _calculate_levels(
        self,
        spot: float,
        side: str,
        market_data: Dict,
    ) -> Tuple[float, float]:
        """Calculate stop loss and take profit levels.

        Uses liquidation clusters as reference points where available,
        falling back to percentage-based levels.
        """
        # Default percentage-based levels
        stop_pct = 0.02    # 2% stop loss
        target_pct = 0.03  # 3% take profit (1.5:1 R:R)

        # Adjust based on squeeze risk
        squeeze = market_data.get("squeeze_risk", "LOW")
        if squeeze == "HIGH":
            stop_pct = 0.025   # Wider stop in volatile conditions
            target_pct = 0.04  # But bigger target too
        elif squeeze == "ELEVATED":
            stop_pct = 0.022
            target_pct = 0.035

        # Use liquidation levels as reference if available
        near_long_liq = market_data.get("nearest_long_liq")
        near_short_liq = market_data.get("nearest_short_liq")

        if side == "long":
            # Stop below nearest long liquidation cluster (cascade risk)
            if near_long_liq and near_long_liq < spot:
                liq_stop = near_long_liq * 0.995  # Just below liquidation zone
                pct_stop = spot * (1 - stop_pct)
                stop_loss = max(liq_stop, pct_stop)  # Don't go tighter than %
            else:
                stop_loss = spot * (1 - stop_pct)

            # Target above nearest short liquidation (squeeze target)
            if near_short_liq and near_short_liq > spot:
                take_profit = near_short_liq * 0.99  # Just before squeeze zone
            else:
                take_profit = spot * (1 + target_pct)
        else:
            # SHORT: stop above short liq, target below long liq
            if near_short_liq and near_short_liq > spot:
                liq_stop = near_short_liq * 1.005
                pct_stop = spot * (1 + stop_pct)
                stop_loss = min(liq_stop, pct_stop)
            else:
                stop_loss = spot * (1 + stop_pct)

            if near_long_liq and near_long_liq < spot:
                take_profit = near_long_liq * 1.01
            else:
                take_profit = spot * (1 - target_pct)

        return (round(stop_loss, 2), round(take_profit, 2))

    @staticmethod
    def _funding_to_vix_proxy(funding_rate: float) -> float:
        """Convert funding rate to a VIX-like proxy for Oracle compatibility.

        Mapping:
          |funding| < 0.005  → VIX ~15 (calm)
          |funding| 0.005-0.01 → VIX ~20 (normal)
          |funding| 0.01-0.03 → VIX ~28 (elevated)
          |funding| > 0.03   → VIX ~35+ (extreme)
        """
        abs_fr = abs(funding_rate)
        if abs_fr < 0.005:
            return 15.0
        elif abs_fr < 0.01:
            return 20.0
        elif abs_fr < 0.02:
            return 25.0
        elif abs_fr < 0.03:
            return 30.0
        else:
            return 35.0 + (abs_fr - 0.03) * 500  # Scale up for extreme
