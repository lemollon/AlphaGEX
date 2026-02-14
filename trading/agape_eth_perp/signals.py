"""
AGAPE-ETH-PERP Signal Generator - Generates directional ETH perpetual trade signals.

Key differences from AGAPE-XRP:
    - Uses CryptoDataProvider with ticker "ETH"
    - _calculate_position_size returns (quantity, max_risk_usd) where quantity is float ETH
    - No CME market hours consideration (24/7/365)
    - Signal uses quantity field instead of contracts
"""

import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from zoneinfo import ZoneInfo

from trading.agape_eth_perp.models import (
    AgapeEthPerpConfig,
    AgapeEthPerpSignal,
    SignalAction,
    PositionSide,
)

logger = logging.getLogger(__name__)

CENTRAL_TZ = ZoneInfo("America/Chicago")

CryptoDataProvider = None
get_crypto_data_provider = None
try:
    from data.crypto_data_provider import CryptoDataProvider, get_crypto_data_provider, CryptoMarketSnapshot
    logger.info("AGAPE-ETH-PERP Signals: CryptoDataProvider loaded")
except ImportError as e:
    logger.warning(f"AGAPE-ETH-PERP Signals: CryptoDataProvider not available: {e}")

ProphetAdvisor = None
MarketContext = None
GEXRegime = None
try:
    from quant.prophet_advisor import ProphetAdvisor, MarketContext, GEXRegime
    logger.info("AGAPE-ETH-PERP Signals: ProphetAdvisor loaded")
except ImportError as e:
    logger.warning(f"AGAPE-ETH-PERP Signals: ProphetAdvisor not available: {e}")


class AgapeEthPerpDirectionTracker:
    def __init__(self, cooldown_scans=2, win_streak_caution=100, memory_size=10):
        self.cooldown_scans = cooldown_scans
        self.win_streak_caution = win_streak_caution
        self.memory_size = memory_size
        self.long_trades = []
        self.short_trades = []
        self.long_cooldown_until = 0
        self.short_cooldown_until = 0
        self.current_scan = 0
        self.long_consecutive_wins = 0
        self.short_consecutive_wins = 0
        self.last_direction = None
        self.last_result = None

    def record_trade(self, direction, is_win, scan_number):
        self.current_scan = scan_number
        d = direction.upper()
        if d == "LONG":
            self.long_trades.append((is_win, scan_number))
            if len(self.long_trades) > self.memory_size:
                self.long_trades.pop(0)
            if is_win:
                self.long_consecutive_wins += 1
                self.short_consecutive_wins = 0
            else:
                self.long_consecutive_wins = 0
                self.long_cooldown_until = scan_number + self.cooldown_scans
        elif d == "SHORT":
            self.short_trades.append((is_win, scan_number))
            if len(self.short_trades) > self.memory_size:
                self.short_trades.pop(0)
            if is_win:
                self.short_consecutive_wins += 1
                self.long_consecutive_wins = 0
            else:
                self.short_consecutive_wins = 0
                self.short_cooldown_until = scan_number + self.cooldown_scans
        self.last_direction = d
        self.last_result = "WIN" if is_win else "LOSS"

    def update_scan(self, scan_number):
        self.current_scan = scan_number

    def should_skip_direction(self, direction):
        d = direction.upper()
        if d == "LONG" and self.current_scan < self.long_cooldown_until:
            remaining = self.long_cooldown_until - self.current_scan
            return True, f"LONG in cooldown ({remaining} scans remaining)"
        if d == "SHORT" and self.current_scan < self.short_cooldown_until:
            remaining = self.short_cooldown_until - self.current_scan
            return True, f"SHORT in cooldown ({remaining} scans remaining)"
        win_rate = self.get_recent_win_rate(d)
        if win_rate is not None and win_rate < 0.20:
            return True, f"{d} has poor recent win rate ({win_rate:.0%})"
        return False, ""

    def get_recent_win_rate(self, direction):
        trades = self.long_trades if direction.upper() == "LONG" else self.short_trades
        if len(trades) < 3:
            return None
        return sum(1 for w, _ in trades if w) / len(trades)

    def get_status(self):
        return {
            "current_scan": self.current_scan,
            "long_cooldown_until": self.long_cooldown_until,
            "short_cooldown_until": self.short_cooldown_until,
            "long_consecutive_wins": self.long_consecutive_wins,
            "short_consecutive_wins": self.short_consecutive_wins,
            "long_win_rate": self.get_recent_win_rate("LONG"),
            "short_win_rate": self.get_recent_win_rate("SHORT"),
            "last_direction": self.last_direction,
            "last_result": self.last_result,
        }


_direction_tracker: Optional[AgapeEthPerpDirectionTracker] = None


def get_agape_eth_perp_direction_tracker(config=None):
    global _direction_tracker
    if _direction_tracker is None:
        _direction_tracker = AgapeEthPerpDirectionTracker(
            cooldown_scans=config.direction_cooldown_scans if config else 2,
            win_streak_caution=config.direction_win_streak_caution if config else 100,
            memory_size=config.direction_memory_size if config else 10,
        )
    return _direction_tracker


def record_agape_eth_perp_trade_outcome(direction, is_win, scan_number):
    get_agape_eth_perp_direction_tracker().record_trade(direction, is_win, scan_number)


class AgapeEthPerpSignalGenerator:
    """Generates directional trade signals for ETH-PERP based on crypto microstructure."""

    def __init__(self, config: AgapeEthPerpConfig):
        self.config = config
        self._crypto_provider = None
        self._oracle = None
        if get_crypto_data_provider:
            try:
                self._crypto_provider = get_crypto_data_provider()
            except Exception as e:
                logger.warning(f"AGAPE-ETH-PERP Signals: Crypto provider init failed: {e}")
        if ProphetAdvisor:
            try:
                self._oracle = ProphetAdvisor()
            except Exception as e:
                logger.warning(f"AGAPE-ETH-PERP Signals: Prophet init failed: {e}")

    def get_market_data(self):
        if not self._crypto_provider:
            return None
        try:
            snapshot = self._crypto_provider.get_snapshot(self.config.ticker)
            if not snapshot or snapshot.spot_price <= 0:
                return None
            return {
                "symbol": snapshot.symbol, "spot_price": snapshot.spot_price,
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
            logger.error(f"AGAPE-ETH-PERP Signals: Market data fetch failed: {e}")
            return None

    def get_prophet_advice(self, market_data):
        if not self._oracle:
            return {"advice": "UNAVAILABLE", "win_probability": 0.5, "confidence": 0.0, "top_factors": ["oracle_unavailable"]}
        try:
            vix_proxy = self._funding_to_vix_proxy(market_data.get("funding_rate", 0))
            gex_regime_map = {"POSITIVE": GEXRegime.POSITIVE, "NEGATIVE": GEXRegime.NEGATIVE, "NEUTRAL": GEXRegime.NEUTRAL}
            gex_regime = gex_regime_map.get(market_data.get("crypto_gex_regime", "NEUTRAL"), GEXRegime.NEUTRAL)
            context = MarketContext(
                spot_price=market_data["spot_price"], vix=vix_proxy,
                gex_net=market_data.get("crypto_gex", 0), gex_regime=gex_regime,
                gex_flip_point=market_data.get("max_pain", market_data["spot_price"]),
                day_of_week=datetime.now(CENTRAL_TZ).weekday(),
            )
            rec = self._oracle.get_strategy_recommendation(context)
            if rec:
                return {
                    "advice": "TRADE" if rec.dir_suitability >= 0.5 else "SKIP",
                    "win_probability": rec.dir_suitability, "confidence": rec.confidence,
                    "top_factors": [f"strategy={rec.recommended_strategy.value}", f"dir_suitability={rec.dir_suitability:.0%}"],
                }
        except Exception as e:
            logger.error(f"AGAPE-ETH-PERP Signals: Prophet call failed: {e}")
        return {"advice": "UNAVAILABLE", "win_probability": 0.5, "confidence": 0.0, "top_factors": ["oracle_error"]}

    def generate_signal(self, prophet_data=None):
        now = datetime.now(CENTRAL_TZ)
        market_data = self.get_market_data()
        if not market_data:
            return AgapeEthPerpSignal(spot_price=0, timestamp=now, action=SignalAction.WAIT, reasoning="NO_MARKET_DATA")
        spot = market_data["spot_price"]
        if prophet_data is None:
            prophet_data = self.get_prophet_advice(market_data)
        oracle_advice = prophet_data.get("advice", "UNAVAILABLE")
        oracle_win_prob = prophet_data.get("win_probability", 0.5)
        if self.config.require_oracle_approval:
            if oracle_advice not in ("TRADE_FULL", "TRADE_REDUCED", "ENTER", "TRADE", "UNAVAILABLE"):
                return AgapeEthPerpSignal(
                    spot_price=spot, timestamp=now, action=SignalAction.WAIT,
                    reasoning=f"BLOCKED_ORACLE_{oracle_advice}", oracle_advice=oracle_advice,
                )
        combined_signal = market_data.get("combined_signal", "WAIT")
        combined_confidence = market_data.get("combined_confidence", "LOW")
        action, side, reasoning = self._determine_action(combined_signal, combined_confidence, market_data)
        if action == SignalAction.WAIT:
            return AgapeEthPerpSignal(
                spot_price=spot, timestamp=now,
                funding_rate=market_data.get("funding_rate", 0),
                funding_regime=market_data.get("funding_regime", "UNKNOWN"),
                ls_ratio=market_data.get("ls_ratio", 1.0),
                squeeze_risk=market_data.get("squeeze_risk", "LOW"),
                crypto_gex=market_data.get("crypto_gex", 0),
                crypto_gex_regime=market_data.get("crypto_gex_regime", "NEUTRAL"),
                action=SignalAction.WAIT, confidence=combined_confidence, reasoning=reasoning,
                oracle_advice=oracle_advice, oracle_win_probability=oracle_win_prob,
                oracle_confidence=prophet_data.get("confidence", 0),
                oracle_top_factors=prophet_data.get("top_factors", []),
            )
        quantity, max_risk = self._calculate_position_size(spot)
        stop_loss, take_profit = self._calculate_levels(spot, side, market_data)
        return AgapeEthPerpSignal(
            spot_price=spot, timestamp=now,
            funding_rate=market_data.get("funding_rate", 0),
            funding_regime=market_data.get("funding_regime", "UNKNOWN"),
            ls_ratio=market_data.get("ls_ratio", 1.0), ls_bias=market_data.get("ls_bias", "NEUTRAL"),
            nearest_long_liq=market_data.get("nearest_long_liq"),
            nearest_short_liq=market_data.get("nearest_short_liq"),
            squeeze_risk=market_data.get("squeeze_risk", "LOW"),
            leverage_regime=market_data.get("leverage_regime", "UNKNOWN"),
            max_pain=market_data.get("max_pain"),
            crypto_gex=market_data.get("crypto_gex", 0),
            crypto_gex_regime=market_data.get("crypto_gex_regime", "NEUTRAL"),
            action=action, confidence=combined_confidence, reasoning=reasoning,
            oracle_advice=oracle_advice, oracle_win_probability=oracle_win_prob,
            oracle_confidence=prophet_data.get("confidence", 0),
            oracle_top_factors=prophet_data.get("top_factors", []),
            side=side, entry_price=spot, stop_loss=stop_loss,
            take_profit=take_profit, quantity=quantity, max_risk_usd=max_risk,
        )

    def _determine_action(self, combined_signal, confidence, market_data):
        confidence_rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        if confidence_rank.get(confidence, 0) < confidence_rank.get(self.config.min_confidence, 1):
            return (SignalAction.WAIT, None, f"LOW_CONFIDENCE_{confidence}")
        tracker = get_agape_eth_perp_direction_tracker(self.config)
        if combined_signal == "LONG":
            skip, reason = tracker.should_skip_direction("LONG")
            if skip:
                return (SignalAction.WAIT, None, f"DIRECTION_TRACKER_{reason}")
            return (SignalAction.LONG, "long", self._build_reasoning("LONG", market_data))
        elif combined_signal == "SHORT":
            skip, reason = tracker.should_skip_direction("SHORT")
            if skip:
                return (SignalAction.WAIT, None, f"DIRECTION_TRACKER_{reason}")
            return (SignalAction.SHORT, "short", self._build_reasoning("SHORT", market_data))
        elif combined_signal == "RANGE_BOUND":
            return self._derive_range_bound_direction(market_data, tracker)
        elif combined_signal == "WAIT":
            return self._derive_fallback_direction(market_data, tracker)
        return (SignalAction.WAIT, None, f"NO_SIGNAL_{combined_signal}")

    def _derive_range_bound_direction(self, market_data, tracker):
        funding_rate = market_data.get("funding_rate", 0)
        max_pain = market_data.get("max_pain")
        spot = market_data.get("spot_price", 0)
        ls_ratio = market_data.get("ls_ratio", 1.0)
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
            skip, reason = tracker.should_skip_direction("LONG")
            return (SignalAction.WAIT, None, f"RANGE_BLOCKED_{reason}") if skip else (SignalAction.LONG, "long", self._build_reasoning("RANGE_LONG", market_data))
        elif score < 0:
            skip, reason = tracker.should_skip_direction("SHORT")
            return (SignalAction.WAIT, None, f"RANGE_BLOCKED_{reason}") if skip else (SignalAction.SHORT, "short", self._build_reasoning("RANGE_SHORT", market_data))
        return (SignalAction.WAIT, None, "RANGE_BOUND_NO_BIAS")

    def _derive_fallback_direction(self, market_data, tracker):
        funding_regime = market_data.get("funding_regime", "NEUTRAL")
        squeeze_risk = market_data.get("squeeze_risk", "LOW")
        ls_bias = market_data.get("ls_bias", "NEUTRAL")
        if squeeze_risk == "HIGH":
            if ls_bias == "SHORT_HEAVY":
                skip, _ = tracker.should_skip_direction("LONG")
                if not skip:
                    return (SignalAction.LONG, "long", self._build_reasoning("SQUEEZE_LONG", market_data))
            elif ls_bias == "LONG_HEAVY":
                skip, _ = tracker.should_skip_direction("SHORT")
                if not skip:
                    return (SignalAction.SHORT, "short", self._build_reasoning("SQUEEZE_SHORT", market_data))
        if funding_regime in ("HEAVILY_NEGATIVE", "EXTREME_NEGATIVE"):
            skip, _ = tracker.should_skip_direction("LONG")
            if not skip:
                return (SignalAction.LONG, "long", self._build_reasoning("FUNDING_LONG", market_data))
        elif funding_regime in ("HEAVILY_POSITIVE", "EXTREME_POSITIVE"):
            skip, _ = tracker.should_skip_direction("SHORT")
            if not skip:
                return (SignalAction.SHORT, "short", self._build_reasoning("FUNDING_SHORT", market_data))
        return (SignalAction.WAIT, None, "NO_FALLBACK_SIGNAL")

    def _build_reasoning(self, direction, market_data):
        parts = [direction, f"funding={market_data.get('funding_regime', 'UNKNOWN')}",
                 f"ls_bias={market_data.get('ls_bias', 'NEUTRAL')}"]
        sq = market_data.get("squeeze_risk", "LOW")
        if sq in ("HIGH", "ELEVATED"):
            parts.append(f"squeeze={sq}")
        parts.append(f"crypto_gex={market_data.get('crypto_gex_regime', 'NEUTRAL')}")
        mp, spot = market_data.get("max_pain"), market_data.get("spot_price", 0)
        if mp and spot:
            parts.append(f"max_pain_dist={((mp - spot) / spot) * 100:+.1f}%")
        return " | ".join(parts)

    def _calculate_position_size(self, spot_price: float) -> Tuple[float, float]:
        """Calculate position size as ETH quantity (float) and max risk in USD.

        Returns:
            (quantity, max_risk_usd) where quantity is float ETH amount.
        """
        capital = self.config.starting_capital
        max_risk_usd = capital * (self.config.risk_per_trade_pct / 100)

        # Risk per unit ETH based on stop distance (2% default)
        stop_distance = spot_price * 0.02 * (self.config.stop_loss_pct / 100)
        if stop_distance <= 0:
            return (self.config.default_quantity, max_risk_usd)

        # quantity = max_risk / risk_per_eth
        raw_quantity = max_risk_usd / stop_distance

        # Clamp to min/max quantity bounds
        quantity = max(self.config.min_quantity, min(raw_quantity, self.config.max_quantity))

        # Round to 3 decimal places (0.001 ETH precision)
        quantity = round(quantity, 3)

        actual_risk = round(quantity * stop_distance, 2)
        return (quantity, actual_risk)

    def _calculate_levels(self, spot, side, market_data):
        stop_pct, target_pct = 0.02, 0.03
        squeeze = market_data.get("squeeze_risk", "LOW")
        if squeeze == "HIGH":
            stop_pct, target_pct = 0.025, 0.04
        elif squeeze == "ELEVATED":
            stop_pct, target_pct = 0.022, 0.035
        near_long = market_data.get("nearest_long_liq")
        near_short = market_data.get("nearest_short_liq")
        if side == "long":
            sl = max(near_long * 0.995, spot * (1 - stop_pct)) if near_long and near_long < spot else spot * (1 - stop_pct)
            tp = near_short * 0.99 if near_short and near_short > spot else spot * (1 + target_pct)
        else:
            sl = min(near_short * 1.005, spot * (1 + stop_pct)) if near_short and near_short > spot else spot * (1 + stop_pct)
            tp = near_long * 1.01 if near_long and near_long < spot else spot * (1 - target_pct)
        return (round(sl, 2), round(tp, 2))

    @staticmethod
    def _funding_to_vix_proxy(funding_rate):
        abs_fr = abs(funding_rate)
        if abs_fr < 0.005:
            return 15.0
        elif abs_fr < 0.01:
            return 20.0
        elif abs_fr < 0.02:
            return 25.0
        elif abs_fr < 0.03:
            return 30.0
        return 35.0 + (abs_fr - 0.03) * 500
