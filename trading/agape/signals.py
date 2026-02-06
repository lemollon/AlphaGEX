"""
AGAPE Signal Generator - Generates directional /MET trade signals.

AGGRESSIVE MODE: Trades on any actionable signal with low confidence thresholds.
Includes Direction Tracker for nimble reversal detection (ported from HERACLES).

Uses crypto market microstructure (funding, OI, liquidations, crypto GEX)
as the equivalent of GEX-based signal generation used by ARES/ATHENA.

Signal Flow:
  1. Fetch crypto market snapshot (CryptoDataProvider)
  2. Analyze microstructure signals
  3. Direction Tracker check (cooldown after losses, nimble reversals)
  4. Consult Oracle for advisory (non-blocking)
  5. Calculate position size and risk levels
  6. Return AgapeSignal with full audit trail
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
MarketContext = None
GEXRegime = None
try:
    from quant.oracle_advisor import OracleAdvisor, MarketContext, GEXRegime
    logger.info("AGAPE Signals: OracleAdvisor loaded")
except ImportError as e:
    logger.warning(f"AGAPE Signals: OracleAdvisor not available: {e}")


# ============================================================================
# DIRECTION TRACKER - Makes bot nimble at detecting direction changes
# Ported from HERACLES for aggressive trading
# ============================================================================

class AgapeDirectionTracker:
    """
    Tracks recent trade results by direction to adapt to market changes.
    Ported from HERACLES DirectionTracker.

    Features:
    1. Loss Cooldown: After a loss, pause that direction for N scans
    2. Opposite Boost: After a loss, boost confidence in opposite direction
    3. Recent Win Rate: Track win rate by direction over recent trades
    """

    def __init__(self, cooldown_scans: int = 2, win_streak_caution: int = 100, memory_size: int = 10):
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

    def record_trade(self, direction: str, is_win: bool, scan_number: int) -> None:
        self.current_scan = scan_number
        dir_upper = direction.upper()

        if dir_upper == "LONG":
            self.long_trades.append((is_win, scan_number))
            if len(self.long_trades) > self.memory_size:
                self.long_trades.pop(0)
            if is_win:
                self.long_consecutive_wins += 1
                self.short_consecutive_wins = 0
            else:
                self.long_consecutive_wins = 0
                self.long_cooldown_until = scan_number + self.cooldown_scans
                logger.info(f"AGAPE DIRECTION: LONG loss - cooldown until scan {self.long_cooldown_until}")
        elif dir_upper == "SHORT":
            self.short_trades.append((is_win, scan_number))
            if len(self.short_trades) > self.memory_size:
                self.short_trades.pop(0)
            if is_win:
                self.short_consecutive_wins += 1
                self.long_consecutive_wins = 0
            else:
                self.short_consecutive_wins = 0
                self.short_cooldown_until = scan_number + self.cooldown_scans
                logger.info(f"AGAPE DIRECTION: SHORT loss - cooldown until scan {self.short_cooldown_until}")

        self.last_direction = dir_upper
        self.last_result = "WIN" if is_win else "LOSS"

    def update_scan(self, scan_number: int) -> None:
        self.current_scan = scan_number

    def is_direction_cooled_down(self, direction: str) -> bool:
        dir_upper = direction.upper()
        if dir_upper == "LONG":
            return self.current_scan < self.long_cooldown_until
        elif dir_upper == "SHORT":
            return self.current_scan < self.short_cooldown_until
        return False

    def get_confidence_adjustment(self, direction: str) -> float:
        dir_upper = direction.upper()
        if dir_upper == "LONG" and self.long_consecutive_wins >= self.win_streak_caution:
            return 0.8
        if dir_upper == "SHORT" and self.short_consecutive_wins >= self.win_streak_caution:
            return 0.8
        if self.last_result == "LOSS" and self.last_direction:
            opposite = "SHORT" if self.last_direction == "LONG" else "LONG"
            if dir_upper == opposite:
                return 1.15
        return 1.0

    def should_skip_direction(self, direction: str) -> Tuple[bool, str]:
        dir_upper = direction.upper()
        if self.is_direction_cooled_down(dir_upper):
            remaining = (self.long_cooldown_until if dir_upper == "LONG"
                        else self.short_cooldown_until) - self.current_scan
            return True, f"{dir_upper} in cooldown ({remaining} scans remaining after loss)"
        win_rate = self.get_recent_win_rate(dir_upper)
        if win_rate is not None and win_rate < 0.20:
            return True, f"{dir_upper} has poor recent win rate ({win_rate:.0%})"
        return False, ""

    def get_recent_win_rate(self, direction: str) -> Optional[float]:
        dir_upper = direction.upper()
        trades = self.long_trades if dir_upper == "LONG" else self.short_trades
        if len(trades) < 3:
            return None
        wins = sum(1 for is_win, _ in trades if is_win)
        return wins / len(trades)

    def get_status(self) -> Dict[str, Any]:
        return {
            "current_scan": self.current_scan,
            "long_cooldown_until": self.long_cooldown_until,
            "short_cooldown_until": self.short_cooldown_until,
            "long_consecutive_wins": self.long_consecutive_wins,
            "short_consecutive_wins": self.short_consecutive_wins,
            "long_recent_trades": len(self.long_trades),
            "short_recent_trades": len(self.short_trades),
            "long_win_rate": self.get_recent_win_rate("LONG"),
            "short_win_rate": self.get_recent_win_rate("SHORT"),
            "last_direction": self.last_direction,
            "last_result": self.last_result,
        }


# Global direction tracker instance (singleton)
_direction_tracker: Optional[AgapeDirectionTracker] = None


def get_agape_direction_tracker(config: Optional[AgapeConfig] = None) -> AgapeDirectionTracker:
    """Get the global AGAPE direction tracker singleton."""
    global _direction_tracker
    if _direction_tracker is None:
        cooldown = config.direction_cooldown_scans if config else 2
        caution = config.direction_win_streak_caution if config else 100
        memory = config.direction_memory_size if config else 10
        _direction_tracker = AgapeDirectionTracker(
            cooldown_scans=cooldown,
            win_streak_caution=caution,
            memory_size=memory,
        )
    return _direction_tracker


def record_agape_trade_outcome(direction: str, is_win: bool, scan_number: int) -> None:
    """Record a trade outcome to the AGAPE direction tracker."""
    tracker = get_agape_direction_tracker()
    tracker.record_trade(direction, is_win, scan_number)


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
            # Map crypto data to Oracle's MarketContext dataclass
            vix_proxy = self._funding_to_vix_proxy(market_data.get("funding_rate", 0))
            crypto_gex_regime = market_data.get("crypto_gex_regime", "NEUTRAL")

            # Map crypto GEX regime to Oracle's GEXRegime enum
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
                # AGAPE is directional, so high dir_suitability = TRADE
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

        # Step 3: Check Oracle advice (ADVISORY ONLY - does not block trades)
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
        else:
            # Oracle is advisory only - log advice but never block
            logger.info(
                f"AGAPE Signal: Oracle advisory (non-blocking): {oracle_advice} "
                f"win_prob={oracle_win_prob:.2%}"
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

        AGGRESSIVE MODE: Trades on any actionable signal including RANGE_BOUND.
        Uses Direction Tracker to skip directions that are on cooldown.

        Maps crypto signals to actions:
          LONG       → Buy /MET (bullish directional)
          SHORT      → Sell /MET (bearish directional)
          RANGE_BOUND → Trade based on microstructure bias (no longer skipped)
          WAIT       → Derive direction from funding/LS bias (fallback)
        """
        min_confidence = self.config.min_confidence

        # Check minimum confidence - LOW means trade on anything
        confidence_rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        if confidence_rank.get(confidence, 0) < confidence_rank.get(min_confidence, 1):
            return (SignalAction.WAIT, None, f"LOW_CONFIDENCE_{confidence}")

        # Direction Tracker: skip directions on cooldown after losses
        direction_tracker = get_agape_direction_tracker(self.config)

        if combined_signal == "LONG":
            should_skip, skip_reason = direction_tracker.should_skip_direction("LONG")
            if should_skip:
                logger.info(f"AGAPE Signal: LONG skipped by direction tracker: {skip_reason}")
                return (SignalAction.WAIT, None, f"DIRECTION_TRACKER_{skip_reason}")
            reasoning = self._build_reasoning("LONG", market_data)
            return (SignalAction.LONG, "long", reasoning)

        elif combined_signal == "SHORT":
            should_skip, skip_reason = direction_tracker.should_skip_direction("SHORT")
            if should_skip:
                logger.info(f"AGAPE Signal: SHORT skipped by direction tracker: {skip_reason}")
                return (SignalAction.WAIT, None, f"DIRECTION_TRACKER_{skip_reason}")
            reasoning = self._build_reasoning("SHORT", market_data)
            return (SignalAction.SHORT, "short", reasoning)

        elif combined_signal == "RANGE_BOUND":
            # AGGRESSIVE: In range-bound, use microstructure bias to pick a direction
            return self._derive_range_bound_direction(market_data, direction_tracker)

        elif combined_signal == "WAIT":
            # AGGRESSIVE: Even on WAIT, try to derive direction from individual signals
            return self._derive_fallback_direction(market_data, direction_tracker)

        return (SignalAction.WAIT, None, f"NO_SIGNAL_{combined_signal}")

    def _derive_range_bound_direction(
        self,
        market_data: Dict,
        tracker: AgapeDirectionTracker,
    ) -> Tuple[SignalAction, Optional[str], str]:
        """Derive a directional trade from range-bound conditions.

        In range-bound markets, use microstructure signals to pick a direction:
        - Funding rate bias (negative funding = shorts paying longs = bullish)
        - Long/Short ratio extreme (crowded trade = fade the crowd)
        - Max pain distance (price tends to drift toward max pain)
        """
        funding_rate = market_data.get("funding_rate", 0)
        ls_bias = market_data.get("ls_bias", "NEUTRAL")
        max_pain = market_data.get("max_pain")
        spot = market_data.get("spot_price", 0)

        # Score for direction: positive = LONG, negative = SHORT
        score = 0.0

        # Funding rate: negative funding is bullish (shorts paying longs)
        if funding_rate < -self.config.min_funding_rate_signal:
            score += 1.0
        elif funding_rate > self.config.min_funding_rate_signal:
            score -= 1.0

        # L/S ratio: extreme long = bearish (fade), extreme short = bullish (fade)
        ls_ratio = market_data.get("ls_ratio", 1.0)
        if ls_ratio > self.config.min_ls_ratio_extreme:
            score -= 0.5  # Too many longs, fade
        elif ls_ratio < (1.0 / self.config.min_ls_ratio_extreme):
            score += 0.5  # Too many shorts, fade

        # Max pain: price drifts toward max pain
        if max_pain and spot:
            if max_pain > spot * 1.005:
                score += 0.5  # Max pain above = bullish drift
            elif max_pain < spot * 0.995:
                score -= 0.5  # Max pain below = bearish drift

        if score > 0:
            should_skip, reason = tracker.should_skip_direction("LONG")
            if should_skip:
                return (SignalAction.WAIT, None, f"RANGE_BOUND_LONG_BLOCKED_{reason}")
            reasoning = self._build_reasoning("RANGE_LONG", market_data)
            return (SignalAction.LONG, "long", reasoning)
        elif score < 0:
            should_skip, reason = tracker.should_skip_direction("SHORT")
            if should_skip:
                return (SignalAction.WAIT, None, f"RANGE_BOUND_SHORT_BLOCKED_{reason}")
            reasoning = self._build_reasoning("RANGE_SHORT", market_data)
            return (SignalAction.SHORT, "short", reasoning)

        return (SignalAction.WAIT, None, "RANGE_BOUND_NO_BIAS")

    def _derive_fallback_direction(
        self,
        market_data: Dict,
        tracker: AgapeDirectionTracker,
    ) -> Tuple[SignalAction, Optional[str], str]:
        """Derive direction from individual microstructure signals when combined is WAIT.

        Aggressive fallback: if any single signal is strong enough, trade it.
        """
        funding_regime = market_data.get("funding_regime", "NEUTRAL")
        squeeze_risk = market_data.get("squeeze_risk", "LOW")
        ls_bias = market_data.get("ls_bias", "NEUTRAL")
        crypto_gex_regime = market_data.get("crypto_gex_regime", "NEUTRAL")

        # Strong single-signal trades
        if squeeze_risk == "HIGH":
            # High squeeze risk = strong directional move coming
            if ls_bias == "SHORT_HEAVY":
                should_skip, reason = tracker.should_skip_direction("LONG")
                if not should_skip:
                    reasoning = self._build_reasoning("SQUEEZE_LONG", market_data)
                    return (SignalAction.LONG, "long", reasoning)
            elif ls_bias == "LONG_HEAVY":
                should_skip, reason = tracker.should_skip_direction("SHORT")
                if not should_skip:
                    reasoning = self._build_reasoning("SQUEEZE_SHORT", market_data)
                    return (SignalAction.SHORT, "short", reasoning)

        # Funding regime extreme
        if funding_regime in ("HEAVILY_NEGATIVE", "EXTREME_NEGATIVE"):
            should_skip, reason = tracker.should_skip_direction("LONG")
            if not should_skip:
                reasoning = self._build_reasoning("FUNDING_LONG", market_data)
                return (SignalAction.LONG, "long", reasoning)
        elif funding_regime in ("HEAVILY_POSITIVE", "EXTREME_POSITIVE"):
            should_skip, reason = tracker.should_skip_direction("SHORT")
            if not should_skip:
                reasoning = self._build_reasoning("FUNDING_SHORT", market_data)
                return (SignalAction.SHORT, "short", reasoning)

        return (SignalAction.WAIT, None, "NO_FALLBACK_SIGNAL")

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

        # Risk per contract based on 2% stop distance (matches _calculate_levels default)
        # stop_loss_pct=100 means 100% of base 2% stop = 2% of spot
        base_stop_pct = 0.02  # 2% base stop distance
        stop_distance = spot_price * base_stop_pct * (self.config.stop_loss_pct / 100)
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
