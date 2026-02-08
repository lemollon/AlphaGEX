"""
AGAPE-SPOT Signal Generator - Generates directional ETH-USD spot trade signals.

Uses the same crypto market microstructure as AGAPE (funding, OI, liquidations, crypto GEX)
but with spot-native position sizing (ETH quantity instead of contracts).

Reuses AGAPE's DirectionTracker for nimble reversal detection.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from zoneinfo import ZoneInfo

from trading.agape_spot.models import (
    AgapeSpotConfig,
    AgapeSpotSignal,
    SignalAction,
    PositionSide,
)

logger = logging.getLogger(__name__)

CENTRAL_TZ = ZoneInfo("America/Chicago")

# Reuse AGAPE's direction tracker and signal logic
AgapeDirectionTracker = None
try:
    from trading.agape.signals import (
        AgapeDirectionTracker,
    )
except ImportError:
    pass

CryptoDataProvider = None
get_crypto_data_provider = None
try:
    from data.crypto_data_provider import (
        CryptoDataProvider,
        get_crypto_data_provider,
        CryptoMarketSnapshot,
    )
    logger.info("AGAPE-SPOT Signals: CryptoDataProvider loaded")
except ImportError as e:
    logger.warning(f"AGAPE-SPOT Signals: CryptoDataProvider not available: {e}")

OracleAdvisor = None
MarketContext = None
GEXRegime = None
try:
    from quant.oracle_advisor import OracleAdvisor, MarketContext, GEXRegime
    logger.info("AGAPE-SPOT Signals: OracleAdvisor loaded")
except ImportError as e:
    logger.warning(f"AGAPE-SPOT Signals: OracleAdvisor not available: {e}")


# Direction tracker singleton (separate from AGAPE's tracker)
_spot_direction_tracker = None


def get_spot_direction_tracker(config: Optional[AgapeSpotConfig] = None):
    global _spot_direction_tracker
    if _spot_direction_tracker is None:
        if AgapeDirectionTracker:
            cooldown = config.direction_cooldown_scans if config else 2
            caution = config.direction_win_streak_caution if config else 100
            memory = config.direction_memory_size if config else 10
            _spot_direction_tracker = AgapeDirectionTracker(
                cooldown_scans=cooldown,
                win_streak_caution=caution,
                memory_size=memory,
            )
        else:
            # Minimal fallback if AGAPE's tracker isn't importable
            class MinimalTracker:
                def update_scan(self, n): pass
                def should_skip_direction(self, d): return (False, "")
                def record_trade(self, d, w, s): pass
                def get_status(self): return {}
            _spot_direction_tracker = MinimalTracker()
    return _spot_direction_tracker


def record_spot_trade_outcome(direction: str, is_win: bool, scan_number: int) -> None:
    tracker = get_spot_direction_tracker()
    tracker.record_trade(direction, is_win, scan_number)


class AgapeSpotSignalGenerator:
    """Generates directional trade signals for spot ETH-USD.

    Same crypto microstructure signals as AGAPE, but position sizing
    is in ETH quantity (spot-native) instead of futures contracts.
    """

    def __init__(self, config: AgapeSpotConfig):
        self.config = config
        self._crypto_provider = None
        self._oracle = None

        if get_crypto_data_provider:
            try:
                self._crypto_provider = get_crypto_data_provider()
            except Exception as e:
                logger.warning(f"AGAPE-SPOT Signals: Crypto provider init failed: {e}")

        if OracleAdvisor:
            try:
                self._oracle = OracleAdvisor()
            except Exception as e:
                logger.warning(f"AGAPE-SPOT Signals: Oracle init failed: {e}")

    def get_market_data(self) -> Optional[Dict[str, Any]]:
        if not self._crypto_provider:
            logger.error("AGAPE-SPOT Signals: No crypto data provider")
            return None

        try:
            snapshot = self._crypto_provider.get_snapshot(self.config.ticker)
            if not snapshot or snapshot.spot_price <= 0:
                logger.warning("AGAPE-SPOT Signals: Invalid snapshot")
                return None

            return {
                "symbol": snapshot.symbol,
                "spot_price": snapshot.spot_price,
                "timestamp": snapshot.timestamp,
                "funding_rate": snapshot.funding_rate.rate if snapshot.funding_rate else 0,
                "funding_regime": snapshot.funding_regime,
                "nearest_long_liq": snapshot.nearest_long_liq,
                "nearest_short_liq": snapshot.nearest_short_liq,
                "squeeze_risk": snapshot.squeeze_risk,
                "liquidation_clusters": len(snapshot.liquidation_clusters),
                "ls_ratio": snapshot.ls_ratio.ratio if snapshot.ls_ratio else 1.0,
                "ls_bias": snapshot.ls_ratio.bias if snapshot.ls_ratio else "NEUTRAL",
                "max_pain": snapshot.max_pain,
                "crypto_gex": snapshot.crypto_gex.net_gex if snapshot.crypto_gex else 0,
                "crypto_gex_regime": snapshot.crypto_gex.gamma_regime if snapshot.crypto_gex else "NEUTRAL",
                "leverage_regime": snapshot.leverage_regime,
                "directional_bias": snapshot.directional_bias,
                "volatility_regime": snapshot.volatility_regime,
                "combined_signal": snapshot.combined_signal,
                "combined_confidence": snapshot.combined_confidence,
            }
        except Exception as e:
            logger.error(f"AGAPE-SPOT Signals: Market data fetch failed: {e}")
            return None

    def get_oracle_advice(self, market_data: Dict) -> Dict[str, Any]:
        if not self._oracle:
            return {
                "advice": "UNAVAILABLE",
                "win_probability": 0.5,
                "confidence": 0.0,
                "top_factors": ["oracle_unavailable"],
            }

        try:
            vix_proxy = self._funding_to_vix_proxy(market_data.get("funding_rate", 0))
            crypto_gex_regime = market_data.get("crypto_gex_regime", "NEUTRAL")

            gex_regime_map = {
                "POSITIVE": GEXRegime.POSITIVE,
                "NEGATIVE": GEXRegime.NEGATIVE,
                "NEUTRAL": GEXRegime.NEUTRAL,
            }
            gex_regime = gex_regime_map.get(crypto_gex_regime, GEXRegime.NEUTRAL)

            context = MarketContext(
                spot_price=market_data["spot_price"],
                vix=vix_proxy,
                gex_net=market_data.get("crypto_gex", 0),
                gex_regime=gex_regime,
                gex_flip_point=market_data.get("max_pain", market_data["spot_price"]),
                day_of_week=datetime.now(CENTRAL_TZ).weekday(),
            )

            recommendation = self._oracle.get_strategy_recommendation(context)
            if recommendation:
                advice = "TRADE" if recommendation.dir_suitability >= 0.5 else "SKIP"
                return {
                    "advice": advice,
                    "win_probability": recommendation.dir_suitability,
                    "confidence": recommendation.confidence,
                    "top_factors": [
                        f"strategy={recommendation.recommended_strategy.value}",
                        f"vix_regime={recommendation.vix_regime.value}",
                        f"gex_regime={recommendation.gex_regime.value}",
                        f"dir_suitability={recommendation.dir_suitability:.0%}",
                        f"size_mult={recommendation.size_multiplier}",
                    ],
                }
        except Exception as e:
            logger.error(f"AGAPE-SPOT Signals: Oracle call failed: {e}")

        return {
            "advice": "UNAVAILABLE",
            "win_probability": 0.5,
            "confidence": 0.0,
            "top_factors": ["oracle_error"],
        }

    def generate_signal(self, oracle_data: Optional[Dict] = None) -> AgapeSpotSignal:
        now = datetime.now(CENTRAL_TZ)

        market_data = self.get_market_data()
        if not market_data:
            return AgapeSpotSignal(
                spot_price=0, timestamp=now,
                action=SignalAction.WAIT, reasoning="NO_MARKET_DATA",
            )

        spot = market_data["spot_price"]

        if oracle_data is None:
            oracle_data = self.get_oracle_advice(market_data)

        oracle_advice = oracle_data.get("advice", "UNAVAILABLE")
        oracle_win_prob = oracle_data.get("win_probability", 0.5)

        if self.config.require_oracle_approval:
            oracle_approved = oracle_advice in ("TRADE_FULL", "TRADE_REDUCED", "ENTER", "TRADE")
            if not oracle_approved and oracle_advice != "UNAVAILABLE":
                return AgapeSpotSignal(
                    spot_price=spot, timestamp=now,
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

        combined_signal = market_data.get("combined_signal", "WAIT")
        combined_confidence = market_data.get("combined_confidence", "LOW")

        action, side, reasoning = self._determine_action(
            combined_signal, combined_confidence, market_data
        )

        if action == SignalAction.WAIT:
            return AgapeSpotSignal(
                spot_price=spot, timestamp=now,
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

        # Spot-native position sizing
        eth_quantity, max_risk = self._calculate_position_size(spot)
        stop_loss, take_profit = self._calculate_levels(spot, side, market_data)

        return AgapeSpotSignal(
            spot_price=spot, timestamp=now,
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
            eth_quantity=eth_quantity,
            max_risk_usd=max_risk,
        )

    def _determine_action(self, combined_signal, confidence, market_data):
        """Same logic as AGAPE - translate combined signal into action."""
        min_confidence = self.config.min_confidence
        confidence_rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        if confidence_rank.get(confidence, 0) < confidence_rank.get(min_confidence, 1):
            return (SignalAction.WAIT, None, f"LOW_CONFIDENCE_{confidence}")

        tracker = get_spot_direction_tracker(self.config)

        if combined_signal == "LONG":
            should_skip, skip_reason = tracker.should_skip_direction("LONG")
            if should_skip:
                return (SignalAction.WAIT, None, f"DIRECTION_TRACKER_{skip_reason}")
            reasoning = self._build_reasoning("LONG", market_data)
            return (SignalAction.LONG, "long", reasoning)

        elif combined_signal == "SHORT":
            should_skip, skip_reason = tracker.should_skip_direction("SHORT")
            if should_skip:
                return (SignalAction.WAIT, None, f"DIRECTION_TRACKER_{skip_reason}")
            reasoning = self._build_reasoning("SHORT", market_data)
            return (SignalAction.SHORT, "short", reasoning)

        elif combined_signal == "RANGE_BOUND":
            return self._derive_range_bound_direction(market_data, tracker)

        elif combined_signal == "WAIT":
            return self._derive_fallback_direction(market_data, tracker)

        return (SignalAction.WAIT, None, f"NO_SIGNAL_{combined_signal}")

    def _derive_range_bound_direction(self, market_data, tracker):
        funding_rate = market_data.get("funding_rate", 0)
        ls_ratio = market_data.get("ls_ratio", 1.0)
        max_pain = market_data.get("max_pain")
        spot = market_data.get("spot_price", 0)

        score = 0.0
        if funding_rate < -self.config.min_funding_rate_signal:
            score += 1.0
        elif funding_rate > self.config.min_funding_rate_signal:
            score -= 1.0

        if ls_ratio > self.config.min_ls_ratio_extreme:
            score -= 0.5
        elif ls_ratio < (1.0 / self.config.min_ls_ratio_extreme):
            score += 0.5

        if max_pain and spot:
            if max_pain > spot * 1.005:
                score += 0.5
            elif max_pain < spot * 0.995:
                score -= 0.5

        if score > 0:
            should_skip, reason = tracker.should_skip_direction("LONG")
            if should_skip:
                return (SignalAction.WAIT, None, f"RANGE_BOUND_LONG_BLOCKED_{reason}")
            return (SignalAction.LONG, "long", self._build_reasoning("RANGE_LONG", market_data))
        elif score < 0:
            should_skip, reason = tracker.should_skip_direction("SHORT")
            if should_skip:
                return (SignalAction.WAIT, None, f"RANGE_BOUND_SHORT_BLOCKED_{reason}")
            return (SignalAction.SHORT, "short", self._build_reasoning("RANGE_SHORT", market_data))

        return (SignalAction.WAIT, None, "RANGE_BOUND_NO_BIAS")

    def _derive_fallback_direction(self, market_data, tracker):
        squeeze_risk = market_data.get("squeeze_risk", "LOW")
        ls_bias = market_data.get("ls_bias", "NEUTRAL")
        funding_regime = market_data.get("funding_regime", "NEUTRAL")

        if squeeze_risk == "HIGH":
            if ls_bias == "SHORT_HEAVY":
                should_skip, _ = tracker.should_skip_direction("LONG")
                if not should_skip:
                    return (SignalAction.LONG, "long", self._build_reasoning("SQUEEZE_LONG", market_data))
            elif ls_bias == "LONG_HEAVY":
                should_skip, _ = tracker.should_skip_direction("SHORT")
                if not should_skip:
                    return (SignalAction.SHORT, "short", self._build_reasoning("SQUEEZE_SHORT", market_data))

        if funding_regime in ("HEAVILY_NEGATIVE", "EXTREME_NEGATIVE"):
            should_skip, _ = tracker.should_skip_direction("LONG")
            if not should_skip:
                return (SignalAction.LONG, "long", self._build_reasoning("FUNDING_LONG", market_data))
        elif funding_regime in ("HEAVILY_POSITIVE", "EXTREME_POSITIVE"):
            should_skip, _ = tracker.should_skip_direction("SHORT")
            if not should_skip:
                return (SignalAction.SHORT, "short", self._build_reasoning("FUNDING_SHORT", market_data))

        return (SignalAction.WAIT, None, "NO_FALLBACK_SIGNAL")

    def _build_reasoning(self, direction: str, market_data: Dict) -> str:
        parts = [direction]
        parts.append(f"funding={market_data.get('funding_regime', 'UNKNOWN')}")
        parts.append(f"ls_bias={market_data.get('ls_bias', 'NEUTRAL')}")
        sq = market_data.get("squeeze_risk", "LOW")
        if sq in ("HIGH", "ELEVATED"):
            parts.append(f"squeeze={sq}")
        parts.append(f"crypto_gex={market_data.get('crypto_gex_regime', 'NEUTRAL')}")
        mp = market_data.get("max_pain")
        spot = market_data.get("spot_price", 0)
        if mp and spot:
            dist = ((mp - spot) / spot) * 100
            parts.append(f"max_pain_dist={dist:+.1f}%")
        return " | ".join(parts)

    def _calculate_position_size(self, spot_price: float) -> Tuple[float, float]:
        """Calculate position size in ETH.

        SPOT-NATIVE: Risk-based sizing.
        risk_usd = capital * risk_pct
        eth_quantity = risk_usd / (spot * stop_distance_pct)
        Capped at max_eth_per_trade.
        """
        capital = self.config.starting_capital
        max_risk_usd = capital * (self.config.risk_per_trade_pct / 100)

        # Risk per ETH based on 2% stop distance
        stop_distance_pct = 0.02
        risk_per_eth = spot_price * stop_distance_pct

        if risk_per_eth <= 0:
            return (self.config.default_eth_size, max_risk_usd)

        eth_quantity = max_risk_usd / risk_per_eth
        eth_quantity = max(self.config.min_eth_order, min(eth_quantity, self.config.max_eth_per_trade))
        eth_quantity = round(eth_quantity, 4)

        actual_risk = eth_quantity * risk_per_eth
        return (eth_quantity, round(actual_risk, 2))

    def _calculate_levels(self, spot, side, market_data) -> Tuple[float, float]:
        """Same stop/target logic as AGAPE."""
        stop_pct = 0.02
        target_pct = 0.03

        squeeze = market_data.get("squeeze_risk", "LOW")
        if squeeze == "HIGH":
            stop_pct = 0.025
            target_pct = 0.04
        elif squeeze == "ELEVATED":
            stop_pct = 0.022
            target_pct = 0.035

        near_long_liq = market_data.get("nearest_long_liq")
        near_short_liq = market_data.get("nearest_short_liq")

        if side == "long":
            if near_long_liq and near_long_liq < spot:
                liq_stop = near_long_liq * 0.995
                pct_stop = spot * (1 - stop_pct)
                stop_loss = max(liq_stop, pct_stop)
            else:
                stop_loss = spot * (1 - stop_pct)
            if near_short_liq and near_short_liq > spot:
                take_profit = near_short_liq * 0.99
            else:
                take_profit = spot * (1 + target_pct)
        else:
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
            return 35.0 + (abs_fr - 0.03) * 500
