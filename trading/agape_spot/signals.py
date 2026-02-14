"""
AGAPE-SPOT Signal Generator - Multi-ticker, LONG-ONLY spot trade signals.

Supports: ETH-USD, BTC-USD, XRP-USD, SHIB-USD, DOGE-USD
LONG-ONLY: Coinbase spot doesn't support shorting for US retail.

Uses crypto market microstructure (funding, OI, liquidations, crypto GEX)
with spot-native position sizing per ticker.

Reuses AGAPE's DirectionTracker for nimble reversal detection.
"""

import logging
from collections import deque
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from zoneinfo import ZoneInfo

from trading.agape_spot.models import (
    AgapeSpotConfig,
    AgapeSpotSignal,
    SignalAction,
    SPOT_TICKERS,
    BayesianWinTracker,
    FundingRegime,
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

# Bayesian Crypto Tracker for choppy-market edge detection
BayesianCryptoTracker = None
BayesianTradeOutcome = None
get_bayesian_tracker = None
try:
    from quant.bayesian_crypto_tracker import (
        BayesianCryptoTracker,
        TradeOutcome as BayesianTradeOutcome,
        get_tracker as get_bayesian_tracker,
    )
    logger.info("AGAPE-SPOT Signals: BayesianCryptoTracker loaded")
except ImportError as e:
    logger.warning(f"AGAPE-SPOT Signals: BayesianCryptoTracker not available: {e}")

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

ProphetAdvisor = None
MarketContext = None
GEXRegime = None
try:
    from quant.prophet_advisor import ProphetAdvisor, MarketContext, GEXRegime
    logger.info("AGAPE-SPOT Signals: ProphetAdvisor loaded")
except ImportError as e:
    logger.warning(f"AGAPE-SPOT Signals: ProphetAdvisor not available: {e}")

# ML Shadow Advisor for shadow mode predictions
_ml_advisor = None
_ml_load_attempted = False


def _get_ml_advisor():
    """Lazy-load the ML advisor singleton."""
    global _ml_advisor, _ml_load_attempted
    if _ml_load_attempted:
        return _ml_advisor
    _ml_load_attempted = True
    try:
        from trading.agape_spot.ml import get_agape_spot_ml_advisor
        _ml_advisor = get_agape_spot_ml_advisor()
        if _ml_advisor.is_trained:
            logger.info("AGAPE-SPOT Signals: ML advisor loaded (trained)")
        else:
            logger.info("AGAPE-SPOT Signals: ML advisor loaded (not yet trained)")
    except Exception as e:
        logger.warning(f"AGAPE-SPOT Signals: ML advisor not available: {e}")
        _ml_advisor = None
    return _ml_advisor


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
    - ETH-leader filter: uses ETH's Deribit GEX signal as compass for altcoins
    - Momentum filter: blocks entries during price downtrends
    """

    # Momentum tracker: rolling window of recent prices per ticker
    # Used to detect short-term trend direction before entering
    MOMENTUM_WINDOW = 10  # Last 10 readings (~10 min at 1-min scans)

    # Win probability gate: minimum Bayesian probability to allow entry
    MIN_WIN_PROBABILITY: float = 0.50

    def __init__(self, config: AgapeSpotConfig, win_trackers: Optional[Dict[str, BayesianWinTracker]] = None):
        self.config = config
        self._crypto_provider = None
        self._prophet = None
        self._win_trackers: Dict[str, BayesianWinTracker] = win_trackers or {}

        # Per-ticker price history for momentum detection
        self._price_history: Dict[str, deque] = {}
        for ticker in config.tickers:
            self._price_history[ticker] = deque(maxlen=self.MOMENTUM_WINDOW)

        # ML shadow prediction results (set per scan in _calculate_win_probability)
        self._last_ml_prob: Optional[float] = None
        self._last_bayesian_prob: Optional[float] = None

        # Cached ETH leader signal (refreshed each cycle, shared across tickers)
        self._eth_leader_signal: Optional[str] = None
        self._eth_leader_confidence: Optional[str] = None
        self._eth_leader_bias: Optional[str] = None
        self._eth_leader_updated: Optional[datetime] = None

        if get_crypto_data_provider:
            try:
                self._crypto_provider = get_crypto_data_provider()
            except Exception as e:
                logger.warning(f"AGAPE-SPOT Signals: Crypto provider init failed: {e}")

        if ProphetAdvisor:
            try:
                self._prophet = ProphetAdvisor()
            except Exception as e:
                logger.warning(f"AGAPE-SPOT Signals: Prophet init failed: {e}")

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

    # ------------------------------------------------------------------
    # ETH-Leader Filter: use ETH's Deribit GEX as directional compass
    # ------------------------------------------------------------------

    def _refresh_eth_leader(self) -> None:
        """Fetch ETH's market snapshot and cache the combined signal.

        ETH has full Deribit options GEX data that XRP/SHIB/DOGE lack.
        Since altcoins are ~80%+ correlated with ETH, we use ETH's
        signal as a directional compass: if ETH says bearish, don't
        enter altcoin longs.

        Cached per cycle so we only call the provider once for all tickers.
        """
        now = datetime.now(CENTRAL_TZ)
        # Only refresh if stale (>30 seconds)
        if self._eth_leader_updated and (now - self._eth_leader_updated).total_seconds() < 30:
            return

        if not self._crypto_provider:
            return

        try:
            eth_snapshot = self._crypto_provider.get_snapshot("ETH")
            if eth_snapshot and eth_snapshot.spot_price > 0:
                self._eth_leader_signal = eth_snapshot.combined_signal
                self._eth_leader_confidence = eth_snapshot.combined_confidence
                self._eth_leader_bias = eth_snapshot.directional_bias
                self._eth_leader_updated = now
        except Exception as e:
            logger.debug(f"AGAPE-SPOT Signals: ETH leader refresh failed: {e}")

    def check_eth_leader(self, ticker: str) -> Tuple[bool, str]:
        """Check if ETH's signal allows an altcoin long entry.

        Returns (allowed, reason).

        Policy:
          ETH LONG/RANGE_BOUND  → allow altcoin entry
          ETH SHORT (HIGH/MED)  → block altcoin entry
          ETH WAIT              → allow (no strong signal either way)
          ETH unavailable       → allow (don't block on missing data)
        """
        entry_filters = self.config.get_entry_filters(ticker)
        if not entry_filters.get("use_eth_leader"):
            return (True, "")

        self._refresh_eth_leader()

        if self._eth_leader_signal is None:
            return (True, "")  # No ETH data, don't block

        sig = self._eth_leader_signal
        conf = self._eth_leader_confidence or "LOW"
        bias = self._eth_leader_bias or "NEUTRAL"

        # Block when ETH is clearly bearish
        if sig == "SHORT" and conf in ("HIGH", "MEDIUM"):
            return (False, f"ETH_LEADER_SHORT_{conf}")

        # Block when ETH directional bias is bearish with high confidence
        if bias == "BEARISH" and sig != "LONG":
            return (False, f"ETH_LEADER_BEARISH_BIAS")

        return (True, "")

    # ------------------------------------------------------------------
    # Momentum Filter: block entries during price downtrends
    # ------------------------------------------------------------------

    def record_price(self, ticker: str, price: float) -> None:
        """Record a price observation for momentum tracking."""
        if ticker not in self._price_history:
            self._price_history[ticker] = deque(maxlen=self.MOMENTUM_WINDOW)
        self._price_history[ticker].append(price)

    def check_momentum(self, ticker: str, current_price: float) -> Tuple[bool, str]:
        """Check if short-term momentum supports a long entry.

        Returns (allowed, reason).

        Uses a simple lookback: if price has fallen more than 0.2% from
        the oldest reading in the window, block entry.  We want to buy
        into rising or flat markets, not falling ones.
        """
        entry_filters = self.config.get_entry_filters(ticker)
        if not entry_filters.get("use_momentum_filter"):
            return (True, "")

        history = self._price_history.get(ticker)
        if not history or len(history) < 3:
            return (True, "")  # Not enough data yet, don't block

        oldest_price = history[0]
        if oldest_price <= 0:
            return (True, "")

        momentum_pct = ((current_price - oldest_price) / oldest_price) * 100

        # Block entry if price dropped >0.2% over the lookback window
        if momentum_pct < -0.2:
            return (False, f"MOMENTUM_DOWN_{momentum_pct:+.2f}pct")

        return (True, "")

    def get_prophet_advice(self, market_data: Dict) -> Dict[str, Any]:
        if not self._prophet:
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

            recommendation = self._prophet.get_strategy_recommendation(context)
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
            logger.error(f"AGAPE-SPOT Signals: Prophet call failed: {e}")

        return {
            "advice": "UNAVAILABLE",
            "win_probability": 0.5,
            "confidence": 0.0,
            "top_factors": ["oracle_error"],
        }

    def generate_signal(
        self,
        ticker: str,
        prophet_data: Optional[Dict] = None,
        vol_context: Optional[Dict] = None,
    ) -> AgapeSpotSignal:
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

        if prophet_data is None:
            prophet_data = self.get_prophet_advice(market_data)

        oracle_advice = prophet_data.get("advice", "UNAVAILABLE")
        oracle_win_prob = prophet_data.get("win_probability", 0.5)

        if self.config.require_prophet_approval:
            prophet_approved = oracle_advice in ("TRADE_FULL", "TRADE_REDUCED", "ENTER", "TRADE")
            if not prophet_approved and oracle_advice != "UNAVAILABLE":
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
                    reasoning=f"BLOCKED_PROPHET_{oracle_advice}",
                    oracle_advice=oracle_advice,
                    oracle_win_probability=oracle_win_prob,
                    oracle_confidence=prophet_data.get("confidence", 0),
                    oracle_top_factors=prophet_data.get("top_factors", []),
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
                oracle_confidence=prophet_data.get("confidence", 0),
                oracle_top_factors=prophet_data.get("top_factors", []),
            )

        # Spot-native position sizing (per-ticker)
        quantity, max_risk = self._calculate_position_size(ticker, spot)

        # If sizing returned 0 (below min notional), emit WAIT instead of LONG
        if quantity <= 0:
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
                reasoning=f"BELOW_MIN_NOTIONAL_{ticker}",
                oracle_advice=oracle_advice,
                oracle_win_probability=oracle_win_prob,
                oracle_confidence=prophet_data.get("confidence", 0),
                oracle_top_factors=prophet_data.get("top_factors", []),
            )

        stop_loss, take_profit = self._calculate_levels(
            spot, market_data, ticker, vol_context=vol_context,
        )

        # Volatility context for the signal
        vc = vol_context or {}

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
            atr=vc.get("atr"),
            atr_pct=vc.get("atr_pct"),
            chop_index=vc.get("chop_index"),
            volatility_regime=vc.get("regime", "UNKNOWN"),
            action=SignalAction.LONG,
            confidence=combined_confidence,
            reasoning=reasoning,
            oracle_advice=oracle_advice,
            oracle_win_probability=oracle_win_prob,
            oracle_confidence=prophet_data.get("confidence", 0),
            oracle_top_factors=prophet_data.get("top_factors", []),
            entry_price=spot,
            stop_loss=stop_loss,
            take_profit=take_profit,
            quantity=quantity,
            max_risk_usd=max_risk,
        )

    def _determine_action(
        self, ticker: str, combined_signal: str, confidence: str, market_data: Dict
    ) -> Tuple[SignalAction, str]:
        """Translate combined signal into LONG or WAIT (never SHORT).

        Entry quality gates (checked in order):
        1. Minimum confidence level
        2. Require actual funding data (XRP/SHIB)
        3. ETH-leader filter: block when ETH GEX says bearish
        4. Momentum filter: block when price is falling
        """
        min_confidence = self.config.min_confidence
        confidence_rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        if confidence_rank.get(confidence, 0) < confidence_rank.get(min_confidence, 1):
            return (SignalAction.WAIT, f"LOW_CONFIDENCE_{confidence}")

        # Per-ticker entry filter: require actual funding data before entering
        entry_filters = self.config.get_entry_filters(ticker)
        if entry_filters.get("require_funding_data"):
            funding_regime = market_data.get("funding_regime", "UNKNOWN")
            if funding_regime in ("UNKNOWN", "", None):
                return (SignalAction.WAIT, "NO_FUNDING_DATA")

        # ETH-leader filter: use ETH's Deribit GEX as directional compass
        eth_ok, eth_reason = self.check_eth_leader(ticker)
        if not eth_ok:
            return (SignalAction.WAIT, eth_reason)

        # Momentum filter: block entries during price downtrends
        spot = market_data.get("spot_price", 0)
        if spot > 0:
            self.record_price(ticker, spot)
            mom_ok, mom_reason = self.check_momentum(ticker, spot)
            if not mom_ok:
                return (SignalAction.WAIT, mom_reason)

        # Bayesian Choppy-Market Gate: when no momentum, raise the win prob threshold
        funding_regime_str = market_data.get("funding_regime", "UNKNOWN")
        is_choppy = self._detect_choppy_market(ticker, market_data)
        if is_choppy and self.config.enable_bayesian_choppy and get_bayesian_tracker:
            choppy_win_prob = self._get_bayesian_choppy_win_prob(ticker)
            if choppy_win_prob < self.config.choppy_min_win_prob:
                logger.info(
                    f"AGAPE-SPOT CHOPPY GATE: {ticker} choppy market, "
                    f"bayesian_edge={choppy_win_prob:.4f} < "
                    f"gate={self.config.choppy_min_win_prob} — BLOCKED"
                )
                return (SignalAction.WAIT, f"CHOPPY_NO_EDGE_{choppy_win_prob:.3f}")
            else:
                logger.info(
                    f"AGAPE-SPOT CHOPPY EDGE: {ticker} choppy market, "
                    f"bayesian_edge={choppy_win_prob:.4f} >= "
                    f"gate={self.config.choppy_min_win_prob} — TRADING EDGE"
                )

        # Bayesian win probability gate: block when regime win rate is too low
        win_prob = self._calculate_win_probability(ticker, funding_regime_str, market_data)
        if win_prob < self.MIN_WIN_PROBABILITY:
            win_tracker = self._win_trackers.get(ticker)
            tracker_info = ""
            if win_tracker:
                tracker_info = (
                    f" [alpha={win_tracker.alpha:.1f}, beta={win_tracker.beta:.1f}, "
                    f"trades={win_tracker.total_trades}, cold_start={win_tracker.is_cold_start}]"
                )
            logger.info(
                f"AGAPE-SPOT WIN_PROB: {ticker} win_prob={win_prob:.4f} "
                f"< gate={self.MIN_WIN_PROBABILITY:.2f}, "
                f"regime={funding_regime_str}{tracker_info} — BLOCKED"
            )
            return (SignalAction.WAIT, f"WIN_PROB_{win_prob:.3f}_BELOW_GATE")

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

    def _is_altcoin(self, ticker: str) -> bool:
        """Return True for non-major tickers (XRP, SHIB, DOGE).

        ETH-USD and BTC-USD are 'majors' with full Deribit options data.
        """
        return ticker not in ("ETH-USD", "BTC-USD")

    def _derive_range_bound_direction(
        self, ticker: str, market_data: Dict, tracker
    ) -> Tuple[SignalAction, str]:
        """Derive direction from range-bound market. LONG or WAIT only.

        For altcoins (XRP, SHIB, DOGE): a small long bias (+0.3) is added
        because RANGE_BOUND HIGH is the dominant signal and the old neutral
        threshold caused 0 trades for days.  Crypto is long-only so a mild
        bullish lean in ranging markets is appropriate.
        """
        funding_rate = market_data.get("funding_rate", 0)
        ls_ratio = market_data.get("ls_ratio", 1.0)
        max_pain = market_data.get("max_pain")
        spot = market_data.get("spot_price", 0)

        # Altcoins get a small long bias — RANGE_BOUND with no extreme signals
        # was producing RANGE_BOUND_NO_BIAS 100% of the time, blocking all trades.
        score = 0.3 if self._is_altcoin(ticker) else 0.0

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
        """Derive direction from squeeze/funding fallback. LONG or WAIT only.

        For altcoins: relaxed conditions.  The old logic required extreme
        funding or high squeeze which almost never fires for XRP/SHIB/DOGE
        (408 NO_FALLBACK_SIGNAL for XRP in 7 days).  For altcoins, also
        accept ELEVATED squeeze and moderate negative funding.
        """
        squeeze_risk = market_data.get("squeeze_risk", "LOW")
        ls_bias = market_data.get("ls_bias", "NEUTRAL")
        funding_regime = market_data.get("funding_regime", "NEUTRAL")
        is_alt = self._is_altcoin(ticker)

        if squeeze_risk == "HIGH":
            if ls_bias == "SHORT_HEAVY":
                # Short squeeze -> bullish for longs
                should_skip, _ = tracker.should_skip_direction("LONG")
                if not should_skip:
                    return (SignalAction.LONG, self._build_reasoning("SQUEEZE_LONG", market_data))
            elif ls_bias == "LONG_HEAVY":
                # Long squeeze -> bearish, WAIT (long-only)
                return (SignalAction.WAIT, "SQUEEZE_BEARISH_LONG_ONLY")

        # Altcoins: also accept ELEVATED squeeze with non-bearish bias
        if is_alt and squeeze_risk == "ELEVATED" and ls_bias != "LONG_HEAVY":
            should_skip, _ = tracker.should_skip_direction("LONG")
            if not should_skip:
                return (SignalAction.LONG, self._build_reasoning("ELEVATED_SQUEEZE_LONG", market_data))

        if funding_regime in ("HEAVILY_NEGATIVE", "EXTREME_NEGATIVE"):
            should_skip, _ = tracker.should_skip_direction("LONG")
            if not should_skip:
                return (SignalAction.LONG, self._build_reasoning("FUNDING_LONG", market_data))

        # Altcoins: also accept moderate negative funding (contrarian long)
        if is_alt and funding_regime in ("NEGATIVE", "SLIGHTLY_NEGATIVE"):
            should_skip, _ = tracker.should_skip_direction("LONG")
            if not should_skip:
                return (SignalAction.LONG, self._build_reasoning("MILD_FUNDING_LONG", market_data))

        if funding_regime in ("HEAVILY_POSITIVE", "EXTREME_POSITIVE"):
            # Bearish funding -> WAIT (long-only)
            return (SignalAction.WAIT, "FUNDING_BEARISH_LONG_ONLY")

        # Altcoins: if nothing else triggers, allow a LONG when funding is balanced
        # and bias is not bearish.  Gated per-ticker: XRP/SHIB have this disabled
        # because without Deribit data, this fired every scan with zero conviction,
        # producing random entries and sub-1.0 profit factors.
        entry_filters = self.config.get_entry_filters(ticker)
        if is_alt and entry_filters.get("allow_base_long", True):
            if ls_bias != "LONG_HEAVY" and funding_regime not in (
                "HEAVILY_POSITIVE", "EXTREME_POSITIVE", "POSITIVE",
            ):
                should_skip, _ = tracker.should_skip_direction("LONG")
                if not should_skip:
                    return (SignalAction.LONG, self._build_reasoning("ALTCOIN_BASE_LONG", market_data))

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

    def _detect_choppy_market(self, ticker: str, market_data: Dict) -> bool:
        """Detect choppy (no-momentum) market for a specific ticker.

        Choppy = RANGE_BOUND signal + balanced funding + low squeeze.
        This is where the small-gain grinding strategy can profit
        IF the Bayesian tracker confirms an edge.
        """
        combined_signal = market_data.get("combined_signal", "WAIT")
        funding_regime = market_data.get("funding_regime", "UNKNOWN")
        squeeze_risk = market_data.get("squeeze_risk", "LOW")
        ls_bias = market_data.get("ls_bias", "NEUTRAL")

        choppy_regimes = [r.strip() for r in self.config.choppy_funding_regimes.split(",")]
        max_squeeze = self.config.choppy_max_squeeze_risk
        squeeze_rank = {"LOW": 1, "ELEVATED": 2, "HIGH": 3}
        max_rank = squeeze_rank.get(max_squeeze, 2)
        cur_rank = squeeze_rank.get(squeeze_risk, 3)

        # Primary: RANGE_BOUND with acceptable squeeze
        if combined_signal == "RANGE_BOUND" and cur_rank <= max_rank:
            return True

        # Secondary: balanced microstructure regardless of combined signal
        if (
            funding_regime in choppy_regimes
            and cur_rank <= max_rank
            and ls_bias in ("NEUTRAL", "BALANCED")
        ):
            return True

        return False

    def _get_bayesian_choppy_win_prob(self, ticker: str) -> float:
        """Get Bayesian win probability for choppy conditions on this ticker.

        Uses the BayesianCryptoTracker per-ticker strategy.
        Falls back to 0.52 (allow trading) if unavailable or cold start.
        """
        if not get_bayesian_tracker:
            return 0.52

        strategy_name = f"agape_spot_choppy_{ticker.replace('-', '_').lower()}"
        tracker = get_bayesian_tracker(
            strategy_name=strategy_name,
            starting_capital=self.config.get_starting_capital(ticker),
        )

        estimate = tracker.get_estimate()

        # Cold start: allow trading to collect data
        if estimate.total_trades < 5:
            return 0.52

        return estimate.mean

    def _calculate_win_probability(
        self, ticker: str, funding_regime_str: str, market_data: Optional[Dict] = None,
    ) -> float:
        """Calculate win probability for a ticker in its current funding regime.

        Blends regime-specific Bayesian estimate with a base rate.
        Cold start floor ensures the bot can trade and collect data early on.

        ML Shadow Mode: if an ML model is trained, runs a parallel prediction
        and logs both for later comparison. If ML is promoted, uses ML probability.

        Returns a probability in [0.0, 1.0].
        """
        win_tracker = self._win_trackers.get(ticker)
        if not win_tracker:
            return 0.52  # No tracker -> allow trading

        funding_regime = FundingRegime.from_funding_string(funding_regime_str)
        bayesian_prob = win_tracker.get_regime_probability(funding_regime)

        # Blend weight ramps from 0.3 (few trades) to 0.7 (100+ trades)
        bayesian_weight = min(0.7, 0.3 + (win_tracker.total_trades / 100))
        base_rate = 0.5  # Prior expectation: 50/50
        blended_prob = (bayesian_prob * bayesian_weight) + (base_rate * (1 - bayesian_weight))

        # Cold start floor: when too few trades, floor so the bot can trade
        is_cold = win_tracker.is_cold_start
        if is_cold and blended_prob < win_tracker.cold_start_floor:
            blended_prob = win_tracker.cold_start_floor

        bayesian_final = round(max(0.0, min(1.0, blended_prob)), 4)

        # --- ML Shadow Prediction ---
        ml_prob = None
        ml_source = None
        ml_advisor = _get_ml_advisor()
        if ml_advisor and ml_advisor.is_trained and market_data:
            try:
                from datetime import datetime as _dt
                now = _dt.now(CENTRAL_TZ)
                features = {
                    'funding_rate': market_data.get('funding_rate', 0.0),
                    'funding_regime': funding_regime_str,
                    'ls_ratio': market_data.get('ls_ratio', 1.0),
                    'ls_bias': market_data.get('ls_bias', 'NEUTRAL'),
                    'squeeze_risk': market_data.get('squeeze_risk', 'LOW'),
                    'crypto_gex': market_data.get('crypto_gex', 0.0),
                    'oracle_win_prob': market_data.get('oracle_win_prob', 0.5),
                    'day_of_week': now.weekday(),
                    'hour_of_day': now.hour,
                    'positive_funding_win_rate': win_tracker.get_regime_probability(FundingRegime.POSITIVE),
                    'negative_funding_win_rate': win_tracker.get_regime_probability(FundingRegime.NEGATIVE),
                    'chop_index': market_data.get('chop_index', 0.5),
                }
                result = ml_advisor.predict(features)
                if result:
                    ml_prob = round(result['win_probability'], 4)
                    ml_source = result['source']
            except Exception as e:
                logger.debug(f"AGAPE-SPOT ML shadow prediction failed: {e}")

        # Store last shadow predictions on self for scan logging
        self._last_ml_prob = ml_prob
        self._last_bayesian_prob = bayesian_final

        # Check if ML is promoted — if so, use ML probability for gating
        is_promoted = self._is_ml_promoted()
        if is_promoted and ml_prob is not None:
            final_prob = ml_prob
            prob_source = "ML"
        else:
            final_prob = bayesian_final
            prob_source = "BAYESIAN"

        ml_info = ""
        if ml_prob is not None:
            ml_info = f", ml_prob={ml_prob:.4f} ({'ACTIVE' if is_promoted else 'shadow'})"

        logger.info(
            f"AGAPE-SPOT WIN_PROB [{prob_source}]: {ticker} regime={funding_regime.value}, "
            f"regime_prob={bayesian_prob:.3f}, bayes_wt={bayesian_weight:.2f}, "
            f"blended={blended_prob:.4f}, "
            f"cold_start={'YES' if is_cold else 'NO'} "
            f"({win_tracker.total_trades}/{win_tracker.cold_start_trades} trades), "
            f"final={final_prob:.4f} (gate={self.MIN_WIN_PROBABILITY:.2f}){ml_info}"
        )

        return final_prob

    def _is_ml_promoted(self) -> bool:
        """Check if ML has been promoted to active trading."""
        try:
            from trading.agape_spot.db import AgapeSpotDatabase
            db = AgapeSpotDatabase()
            val = db.get_ml_config('ml_promoted')
            return val == 'true'
        except Exception:
            return False

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

        # Risk per unit based on per-ticker max loss (altcoins: 0.75%, ETH: 1.5%)
        exit_params = self.config.get_exit_params(ticker)
        stop_distance_pct = exit_params["max_unrealized_loss_pct"] / 100
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

        # Enforce Coinbase minimum notional ($2 default, $1 API minimum + buffer)
        min_notional = ticker_config.get("min_notional_usd", 2.0)
        notional = quantity * spot_price
        if notional < min_notional:
            # Bump quantity to meet minimum notional
            min_qty = min_notional / spot_price
            min_qty = max(min_qty, min_order)
            min_qty = round(min_qty, quantity_decimals)
            # If min_qty fits within capital and max_per_trade, use it
            if min_qty <= max_per_trade and (min_qty * spot_price) <= capital:
                quantity = min_qty
            else:
                # Can't meet minimum notional within constraints — skip trade
                logger.warning(
                    f"AGAPE-SPOT Signals: {ticker} notional ${notional:.2f} "
                    f"below min ${min_notional:.2f} and can't bump up — "
                    f"returning 0 quantity"
                )
                return (0, 0.0)

        actual_risk = quantity * risk_per_unit
        return (quantity, round(actual_risk, 2))

    def _calculate_levels(
        self,
        spot: float,
        market_data: Dict,
        ticker: str = "ETH-USD",
        vol_context: Optional[Dict] = None,
    ) -> Tuple[float, float]:
        """Calculate stop-loss and take-profit levels. LONG-ONLY.

        ATR-ADAPTIVE: When ATR data is available, stops are sized to actual
        volatility so normal market noise doesn't trigger them. Falls back
        to the fixed per-ticker percentages when ATR is unavailable.

        Stop = max(1.5 × ATR, fixed_pct_stop)  — at least as wide as 1.5 ATR
        Target = max(2.5 × ATR, fixed_pct_target) — 2.5:1.5 ATR reward:risk
        """
        exit_params = self.config.get_exit_params(ticker)
        max_loss_pct = exit_params["max_unrealized_loss_pct"]

        # Base stop/target from per-ticker config (the floor)
        stop_pct = max_loss_pct / 100
        target_pct = stop_pct * 2  # 2:1 reward:risk

        squeeze = market_data.get("squeeze_risk", "LOW")
        if squeeze == "HIGH":
            stop_pct *= 1.25
            target_pct *= 1.33
        elif squeeze == "ELEVATED":
            stop_pct *= 1.1
            target_pct *= 1.17

        # ATR-adaptive: widen stops to match actual volatility
        vc = vol_context or {}
        atr = vc.get("atr")
        if atr and atr > 0 and spot > 0:
            # Stop: 1.5 × ATR below entry (covers normal noise)
            # In choppy markets, widen to 2.0 × ATR
            atr_mult = 2.0 if vc.get("is_choppy") else 1.5
            atr_stop_distance = atr * atr_mult
            atr_stop_pct = atr_stop_distance / spot

            # Target: proportional — keep 2:1 reward:risk vs ATR stop
            atr_target_distance = atr_stop_distance * 2.0
            atr_target_pct = atr_target_distance / spot

            # Use the WIDER of ATR-based or fixed-pct (ATR is the floor)
            stop_pct = max(stop_pct, atr_stop_pct)
            target_pct = max(target_pct, atr_target_pct)

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
