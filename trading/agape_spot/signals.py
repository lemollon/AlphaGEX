"""
AGAPE-SPOT Signal Generator - Multi-ticker, LONG-ONLY spot trade signals.

Supports: ETH-USD, XRP-USD, SHIB-USD, DOGE-USD
LONG-ONLY: Coinbase spot doesn't support shorting for US retail.

Uses crypto market microstructure (funding, OI, liquidations, crypto GEX)
with spot-native position sizing per ticker.

Reuses AGAPE's DirectionTracker for nimble reversal detection.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from zoneinfo import ZoneInfo

from trading.agape_spot.models import (
    AgapeSpotConfig,
    AgapeSpotSignal,
    SignalAction,
    SPOT_TICKERS,
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


# Per-ticker direction tracker instances
_spot_direction_trackers: Dict[str, Any] = {}


def get_spot_direction_tracker(ticker: str, config: Optional[AgapeSpotConfig] = None):
    """Get or create a direction tracker for the given ticker."""
    global _spot_direction_trackers
    if ticker not in _spot_direction_trackers:
        if AgapeDirectionTracker:
            cooldown = config.direction_cooldown_scans if config else 2
            caution = config.direction_win_streak_caution if config else 100
            memory = config.direction_memory_size if config else 10
            _spot_direction_trackers[ticker] = AgapeDirectionTracker(
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
            _spot_direction_trackers[ticker] = MinimalTracker()
    return _spot_direction_trackers[ticker]


def record_spot_trade_outcome(ticker: str, direction: str, is_win: bool, scan_number: int) -> None:
    """Record a trade outcome for the given ticker's direction tracker."""
    tracker = get_spot_direction_tracker(ticker)
    tracker.record_trade(direction, is_win, scan_number)


class AgapeSpotSignalGenerator:
    """Generates LONG-ONLY trade signals for multi-ticker spot crypto.

    Same crypto microstructure signals as AGAPE, but:
    - LONG-ONLY: never generates SHORT signals (WAIT instead)
    - Multi-ticker: accepts ticker parameter, uses per-ticker config
    - Position sizing uses per-ticker capital, min_order, max_per_trade
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

    def get_market_data(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Fetch market data for the given ticker.

        Uses the base symbol (e.g., 'ETH' for 'ETH-USD') with CryptoDataProvider.
        """
        if not self._crypto_provider:
            logger.error("AGAPE-SPOT Signals: No crypto data provider")
            return None

        try:
            # Use the base symbol from SPOT_TICKERS (e.g., "ETH" for "ETH-USD")
            ticker_config = SPOT_TICKERS.get(ticker, {})
            symbol = ticker_config.get("symbol", ticker.split("-")[0])

            snapshot = self._crypto_provider.get_snapshot(symbol)
            if not snapshot or snapshot.spot_price <= 0:
                logger.warning(f"AGAPE-SPOT Signals: Invalid snapshot for {ticker}")
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
            logger.error(f"AGAPE-SPOT Signals: Market data fetch failed for {ticker}: {e}")
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

    def generate_signal(self, ticker: str, oracle_data: Optional[Dict] = None) -> AgapeSpotSignal:
        """Generate a LONG-ONLY signal for the given ticker."""
        now = datetime.now(CENTRAL_TZ)

        market_data = self.get_market_data(ticker)
        if not market_data:
            return AgapeSpotSignal(
                ticker=ticker,
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
                    ticker=ticker,
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

        action, reasoning = self._determine_action(
            ticker, combined_signal, combined_confidence, market_data
        )

        if action == SignalAction.WAIT:
            return AgapeSpotSignal(
                ticker=ticker,
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

        # Spot-native position sizing (per-ticker)
        quantity, max_risk = self._calculate_position_size(ticker, spot)
        stop_loss, take_profit = self._calculate_levels(spot, market_data, ticker)

        return AgapeSpotSignal(
            ticker=ticker,
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
            action=SignalAction.LONG,
            confidence=combined_confidence,
            reasoning=reasoning,
            oracle_advice=oracle_advice,
            oracle_win_probability=oracle_win_prob,
            oracle_confidence=oracle_data.get("confidence", 0),
            oracle_top_factors=oracle_data.get("top_factors", []),
            entry_price=spot,
            stop_loss=stop_loss,
            take_profit=take_profit,
            quantity=quantity,
            max_risk_usd=max_risk,
        )

    def _determine_action(
        self, ticker: str, combined_signal: str, confidence: str, market_data: Dict
    ) -> Tuple[SignalAction, str]:
        """Translate combined signal into LONG or WAIT (never SHORT)."""
        min_confidence = self.config.min_confidence
        confidence_rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        if confidence_rank.get(confidence, 0) < confidence_rank.get(min_confidence, 1):
            return (SignalAction.WAIT, f"LOW_CONFIDENCE_{confidence}")

        tracker = get_spot_direction_tracker(ticker, self.config)

        if combined_signal == "LONG":
            should_skip, skip_reason = tracker.should_skip_direction("LONG")
            if should_skip:
                return (SignalAction.WAIT, f"DIRECTION_TRACKER_{skip_reason}")
            reasoning = self._build_reasoning("LONG", market_data)
            return (SignalAction.LONG, reasoning)

        elif combined_signal == "SHORT":
            # LONG-ONLY: bearish signals produce WAIT, not SHORT
            return (SignalAction.WAIT, "BEARISH_SIGNAL_LONG_ONLY")

        elif combined_signal == "RANGE_BOUND":
            return self._derive_range_bound_direction(ticker, market_data, tracker)

        elif combined_signal == "WAIT":
            return self._derive_fallback_direction(ticker, market_data, tracker)

        return (SignalAction.WAIT, f"NO_SIGNAL_{combined_signal}")

    def _derive_range_bound_direction(
        self, ticker: str, market_data: Dict, tracker
    ) -> Tuple[SignalAction, str]:
        """Derive direction from range-bound market. LONG or WAIT only."""
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
                return (SignalAction.WAIT, f"RANGE_BOUND_LONG_BLOCKED_{reason}")
            return (SignalAction.LONG, self._build_reasoning("RANGE_LONG", market_data))

        # Bearish or neutral score -> WAIT (long-only)
        if score < 0:
            return (SignalAction.WAIT, "RANGE_BOUND_BEARISH_LONG_ONLY")

        return (SignalAction.WAIT, "RANGE_BOUND_NO_BIAS")

    def _derive_fallback_direction(
        self, ticker: str, market_data: Dict, tracker
    ) -> Tuple[SignalAction, str]:
        """Derive direction from squeeze/funding fallback. LONG or WAIT only."""
        squeeze_risk = market_data.get("squeeze_risk", "LOW")
        ls_bias = market_data.get("ls_bias", "NEUTRAL")
        funding_regime = market_data.get("funding_regime", "NEUTRAL")

        if squeeze_risk == "HIGH":
            if ls_bias == "SHORT_HEAVY":
                # Short squeeze -> bullish for longs
                should_skip, _ = tracker.should_skip_direction("LONG")
                if not should_skip:
                    return (SignalAction.LONG, self._build_reasoning("SQUEEZE_LONG", market_data))
            elif ls_bias == "LONG_HEAVY":
                # Long squeeze -> bearish, WAIT (long-only)
                return (SignalAction.WAIT, "SQUEEZE_BEARISH_LONG_ONLY")

        if funding_regime in ("HEAVILY_NEGATIVE", "EXTREME_NEGATIVE"):
            should_skip, _ = tracker.should_skip_direction("LONG")
            if not should_skip:
                return (SignalAction.LONG, self._build_reasoning("FUNDING_LONG", market_data))
        elif funding_regime in ("HEAVILY_POSITIVE", "EXTREME_POSITIVE"):
            # Bearish funding -> WAIT (long-only)
            return (SignalAction.WAIT, "FUNDING_BEARISH_LONG_ONLY")

        return (SignalAction.WAIT, "NO_FALLBACK_SIGNAL")

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

    def _calculate_position_size(self, ticker: str, spot_price: float) -> Tuple[float, float]:
        """Calculate position size using per-ticker config from SPOT_TICKERS.

        SPOT-NATIVE: Risk-based sizing with capital-based cap.
        risk_usd = capital * risk_pct
        risk_based_qty = risk_usd / (spot * stop_distance_pct)
        capital_based_qty = (capital / max_positions) / spot
        quantity = min(risk_based_qty, capital_based_qty, max_per_trade)
        Capped at max_per_trade, floored at min_order.
        Rounded to quantity_decimals for the ticker.
        """
        ticker_config = SPOT_TICKERS.get(ticker, SPOT_TICKERS.get("ETH-USD", {}))
        # Use trading capital (live_capital for LIVE tickers, starting_capital for PAPER)
        capital = self.config.get_trading_capital(ticker)
        min_order = ticker_config.get("min_order", 0.001)
        max_per_trade = ticker_config.get("max_per_trade", 1.0)
        quantity_decimals = ticker_config.get("quantity_decimals", 4)
        default_quantity = ticker_config.get("default_quantity", 0.1)

        max_risk_usd = capital * (self.config.risk_per_trade_pct / 100)

        # Risk per unit based on 2% stop distance
        stop_distance_pct = 0.02
        risk_per_unit = spot_price * stop_distance_pct

        if risk_per_unit <= 0:
            return (default_quantity, max_risk_usd)

        risk_based_qty = max_risk_usd / risk_per_unit

        # Capital-based cap: don't allocate more than capital / max_positions_per_ticker
        max_positions = self.config.max_open_positions_per_ticker
        if max_positions > 0:
            max_notional = capital / max_positions
            capital_based_qty = max_notional / spot_price
        else:
            capital_based_qty = risk_based_qty  # no cap

        quantity = min(risk_based_qty, capital_based_qty, max_per_trade)
        quantity = max(min_order, quantity)
        quantity = round(quantity, quantity_decimals)

        actual_risk = quantity * risk_per_unit
        return (quantity, round(actual_risk, 2))

    def _calculate_levels(self, spot: float, market_data: Dict, ticker: str = "ETH-USD") -> Tuple[float, float]:
        """Calculate stop-loss and take-profit levels. LONG-ONLY: stop below, target above."""
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

        # LONG stop: below spot, tightened by long liquidation cluster
        if near_long_liq and near_long_liq < spot:
            liq_stop = near_long_liq * 0.995
            pct_stop = spot * (1 - stop_pct)
            stop_loss = max(liq_stop, pct_stop)
        else:
            stop_loss = spot * (1 - stop_pct)

        # LONG target: above spot, tightened by short liquidation cluster
        if near_short_liq and near_short_liq > spot:
            take_profit = near_short_liq * 0.99
        else:
            take_profit = spot * (1 + target_pct)

        pd = SPOT_TICKERS.get(ticker, {}).get("price_decimals", 2)
        return (round(stop_loss, pd), round(take_profit, pd))

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
