"""
Crypto Data Provider - Fetches ETH market microstructure data.

Replaces equity GEX data with crypto equivalents:
  - Funding Rates (→ Gamma Regime equivalent)
  - Open Interest by strike (→ Gamma Walls / Flip Point equivalent)
  - Liquidation Levels (→ Price Magnets equivalent)
  - Long/Short Ratio (→ Directional Bias equivalent)
  - Crypto GEX from Deribit options (→ Direct GEX equivalent)

Data Sources:
  - CoinGlass API (funding, OI, liquidations, L/S ratio)
  - Deribit API (options data, Greeks, OI by strike)
  - GammaFlip.io API (pre-calculated crypto GEX)
"""

import os
import time
import logging
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

CENTRAL_TZ = ZoneInfo("America/Chicago")


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class CryptoQuote:
    """Real-time price quote for a crypto asset."""
    symbol: str
    price: float
    bid: float
    ask: float
    volume_24h: float
    change_24h_pct: float
    timestamp: datetime
    source: str = "coinglass"


@dataclass
class FundingRate:
    """Perpetual futures funding rate - equivalent to gamma regime indicator.

    High positive → overleveraged longs → NEGATIVE GAMMA equivalent (momentum)
    Near zero     → balanced             → POSITIVE GAMMA equivalent (mean-revert)
    High negative → overleveraged shorts  → GAMMA FLIP equivalent (squeeze)
    """
    symbol: str
    rate: float                    # Current funding rate (e.g., 0.01 = 1%)
    predicted_rate: float          # Next predicted rate
    exchange: str                  # binance, bybit, okx, etc.
    interval_hours: int            # 8 = standard, 1 = hourly
    annualized_rate: float         # Annualized for comparison
    timestamp: datetime

    @property
    def regime(self) -> str:
        """Map funding rate to gamma-equivalent regime."""
        if self.rate > 0.03:
            return "EXTREME_LONG"      # Like extreme negative gamma
        elif self.rate > 0.01:
            return "OVERLEVERAGED_LONG"  # Like negative gamma
        elif self.rate > 0.005:
            return "MILD_LONG_BIAS"    # Like slightly negative gamma
        elif self.rate > -0.005:
            return "BALANCED"          # Like positive gamma (mean reversion)
        elif self.rate > -0.01:
            return "MILD_SHORT_BIAS"   # Like slightly negative gamma
        elif self.rate > -0.03:
            return "OVERLEVERAGED_SHORT"  # Like negative gamma (squeeze risk)
        else:
            return "EXTREME_SHORT"     # Like extreme negative gamma (imminent squeeze)


@dataclass
class OpenInterestLevel:
    """Open interest at a specific strike/price level.

    Equivalent to gamma at a strike in equity GEX.
    High OI clusters act as price magnets like gamma walls.
    """
    strike: float
    call_oi: float
    put_oi: float
    net_oi: float                  # call_oi - put_oi
    total_oi: float                # call_oi + put_oi
    call_volume: float
    put_volume: float
    source: str = "deribit"


@dataclass
class LiquidationCluster:
    """Liquidation level cluster - equivalent to gamma wall.

    Where leveraged positions get force-closed, creating price
    magnets just like gamma walls in equity markets.
    """
    price_level: float
    long_liquidation_usd: float    # Longs liquidated if price drops here
    short_liquidation_usd: float   # Shorts liquidated if price rises here
    net_liquidation_usd: float     # Net pressure direction
    intensity: str                 # HIGH, MEDIUM, LOW
    distance_pct: float            # Distance from current price

    @property
    def is_magnet(self) -> bool:
        """Is this cluster strong enough to act as a price magnet?"""
        return self.intensity in ("HIGH", "MEDIUM") and self.distance_pct < 5.0


@dataclass
class LongShortRatio:
    """Aggregate long/short ratio - equivalent to GEX directional bias.

    Extreme ratios signal overcrowding on one side, similar to
    how extreme GEX readings predict reversals.
    """
    symbol: str
    long_pct: float                # e.g., 55.0 = 55% long
    short_pct: float               # e.g., 45.0 = 45% short
    ratio: float                   # long_pct / short_pct
    exchange: str
    timestamp: datetime

    @property
    def bias(self) -> str:
        """Directional bias from ratio."""
        if self.ratio > 1.5:
            return "EXTREME_LONG"
        elif self.ratio > 1.2:
            return "LONG_BIASED"
        elif self.ratio > 0.8:
            return "BALANCED"
        elif self.ratio > 0.67:
            return "SHORT_BIASED"
        else:
            return "EXTREME_SHORT"


@dataclass
class CryptoGEX:
    """Pre-calculated crypto GEX from Deribit options.

    Direct equivalent of equity GEX but calculated from crypto
    options market maker positioning.
    """
    symbol: str
    net_gex: float                 # Net gamma exposure
    flip_point: float              # Where gamma flips sign
    call_gex: float                # Call-side gamma
    put_gex: float                 # Put-side gamma
    gamma_regime: str              # POSITIVE, NEGATIVE, NEUTRAL
    max_pain: float                # Price where most options expire worthless
    strikes: List[Dict]            # Per-strike GEX data
    timestamp: datetime
    source: str = "deribit"


@dataclass
class CryptoMarketSnapshot:
    """Complete market microstructure snapshot for ETH.

    This is the crypto equivalent of WATCHTOWER's GammaSnapshot.
    """
    symbol: str
    spot_price: float
    timestamp: datetime

    # Funding (→ Gamma Regime)
    funding_rate: Optional[FundingRate] = None
    funding_regime: str = "UNKNOWN"

    # Open Interest (→ Gamma Walls)
    oi_levels: List[OpenInterestLevel] = field(default_factory=list)
    max_pain: Optional[float] = None

    # Liquidations (→ Price Magnets)
    liquidation_clusters: List[LiquidationCluster] = field(default_factory=list)
    nearest_long_liq: Optional[float] = None
    nearest_short_liq: Optional[float] = None

    # Long/Short Ratio (→ Directional Bias)
    ls_ratio: Optional[LongShortRatio] = None

    # Crypto GEX (→ Direct GEX)
    crypto_gex: Optional[CryptoGEX] = None

    # Derived signals (equivalent to WATCHTOWER MarketStructureSignals)
    leverage_regime: str = "UNKNOWN"        # OVERLEVERAGED / BALANCED / DELEVERAGED
    directional_bias: str = "NEUTRAL"       # BULLISH / BEARISH / NEUTRAL
    volatility_regime: str = "NORMAL"       # LOW / NORMAL / ELEVATED / HIGH / EXTREME
    squeeze_risk: str = "LOW"               # HIGH / ELEVATED / MODERATE / LOW
    combined_signal: str = "WAIT"           # LONG / SHORT / RANGE_BOUND / WAIT
    combined_confidence: str = "LOW"        # HIGH / MEDIUM / LOW


# ---------------------------------------------------------------------------
# CoinGlass API Client
# ---------------------------------------------------------------------------

class CoinGlassClient:
    """Fetches crypto market structure data from CoinGlass API.

    CoinGlass provides:
    - Funding rates across exchanges
    - Open interest aggregated data
    - Liquidation heatmap data
    - Long/Short ratio
    """
    # v3 endpoints are broken (404/500) as of Feb 2026.
    # v2 public API works: funding endpoint confirmed.
    BASE_URL_V2 = "https://open-api.coinglass.com/public/v2"
    BASE_URL_V3 = "https://open-api-v3.coinglass.com/api"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("COINGLASS_API_KEY", "")
        self.headers = {"coinglassSecret": self.api_key} if self.api_key else {}
        self._last_request_time = 0
        self._rate_limit_ms = 200  # 5 req/sec max

    def _rate_limit(self):
        """Enforce rate limiting."""
        elapsed = (time.time() - self._last_request_time) * 1000
        if elapsed < self._rate_limit_ms:
            time.sleep((self._rate_limit_ms - elapsed) / 1000)
        self._last_request_time = time.time()

    def _request(self, endpoint: str, params: Optional[Dict] = None, use_v2: bool = True) -> Optional[Dict]:
        """Make an API request with retry logic."""
        base = self.BASE_URL_V2 if use_v2 else self.BASE_URL_V3
        url = f"{base}/{endpoint}"
        for attempt in range(3):
            try:
                self._rate_limit()
                resp = requests.get(url, headers=self.headers, params=params, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success") or data.get("code") == "0":
                        return data.get("data", data)
                    logger.warning(f"CoinGlass API error: {data.get('msg', 'unknown')}")
                    return None
                elif resp.status_code == 429:
                    wait = (attempt + 1) * 2
                    logger.warning(f"CoinGlass rate limited, waiting {wait}s")
                    time.sleep(wait)
                    continue
                else:
                    logger.debug(f"CoinGlass HTTP {resp.status_code} on {endpoint}")
                    return None
            except requests.RequestException as e:
                logger.error(f"CoinGlass request failed (attempt {attempt + 1}): {e}")
                if attempt < 2:
                    time.sleep((attempt + 1) * 1)
        return None

    def get_funding_rate(self, symbol: str = "ETH") -> Optional[FundingRate]:
        """Get current funding rate across exchanges.

        Uses v2 /funding endpoint which returns an array of exchange data.
        We compute a simple average across exchanges for the target symbol.
        """
        data = self._request("funding", {"symbol": symbol, "time_type": "all"}, use_v2=True)
        if not data or not isinstance(data, list):
            return None
        try:
            # v2 returns list of exchanges. Find our symbol and average the rates.
            rates = []
            for entry in data:
                if entry.get("symbol", "").upper() == symbol.upper():
                    margin_list = entry.get("uMarginList", [])
                    for ex in margin_list:
                        r = ex.get("rate")
                        if r is not None:
                            rates.append(float(r))
                    break  # found our symbol

            if not rates:
                logger.debug(f"CoinGlass: No funding rates found for {symbol}")
                return None

            rate = sum(rates) / len(rates)
            # Annualize: 3 funding periods/day * 365 days
            annualized = rate * 3 * 365

            return FundingRate(
                symbol=symbol,
                rate=rate,
                predicted_rate=rate,  # v2 doesn't provide predicted; use current
                exchange="aggregate",
                interval_hours=8,
                annualized_rate=annualized,
                timestamp=datetime.now(CENTRAL_TZ),
            )
        except (KeyError, TypeError, ValueError) as e:
            logger.error(f"Failed to parse funding rate: {e}")
            return None

    def get_funding_rate_history(
        self, symbol: str = "ETH", limit: int = 100
    ) -> List[Dict]:
        """Get historical funding rates for trend analysis."""
        data = self._request(
            "futures/funding-rate-oi-weight-history",
            {"symbol": symbol, "limit": limit},
        )
        if not data or not isinstance(data, list):
            return []
        return data

    def get_open_interest(self, symbol: str = "ETH") -> Optional[Dict]:
        """Get aggregate open interest across exchanges."""
        data = self._request("futures/open-interest", {"symbol": symbol})
        if not data:
            return None
        return data

    def get_liquidation_data(self, symbol: str = "ETH") -> List[LiquidationCluster]:
        """Get liquidation heatmap data.

        Note: CoinGlass v2/v3 liquidation endpoints return 500 as of Feb 2026.
        Returns empty list if unavailable - signal generator handles this gracefully.
        """
        data = self._request("futures/liquidation-heatmap", {"symbol": symbol}, use_v2=False)
        if not data or not isinstance(data, list):
            return []

        clusters = []
        for level in data:
            try:
                price = float(level.get("price", 0))
                long_liq = float(level.get("longLiquidationUsd", 0))
                short_liq = float(level.get("shortLiquidationUsd", 0))
                total = long_liq + short_liq

                if total < 100_000:
                    intensity = "LOW"
                elif total < 1_000_000:
                    intensity = "MEDIUM"
                else:
                    intensity = "HIGH"

                clusters.append(LiquidationCluster(
                    price_level=price,
                    long_liquidation_usd=long_liq,
                    short_liquidation_usd=short_liq,
                    net_liquidation_usd=short_liq - long_liq,
                    intensity=intensity,
                    distance_pct=0.0,  # Calculated later with spot price
                ))
            except (KeyError, TypeError, ValueError):
                continue
        return clusters

    def get_long_short_ratio(self, symbol: str = "ETH") -> Optional[LongShortRatio]:
        """Get aggregate long/short ratio across exchanges.

        Note: CoinGlass v2/v3 long-short endpoints return 500 as of Feb 2026.
        Returns None if unavailable - signal generator handles this gracefully.
        """
        data = self._request(
            "futures/global-long-short-account-ratio",
            {"symbol": symbol},
            use_v2=False,
        )
        if not data:
            return None
        try:
            long_pct = float(data.get("longRate", data.get("longAccount", 50)))
            short_pct = float(data.get("shortRate", data.get("shortAccount", 50)))
            ratio = long_pct / short_pct if short_pct > 0 else 1.0

            return LongShortRatio(
                symbol=symbol,
                long_pct=long_pct,
                short_pct=short_pct,
                ratio=ratio,
                exchange="aggregate",
                timestamp=datetime.now(CENTRAL_TZ),
            )
        except (KeyError, TypeError, ValueError) as e:
            logger.error(f"Failed to parse L/S ratio: {e}")
            return None


# ---------------------------------------------------------------------------
# Deribit API Client
# ---------------------------------------------------------------------------

class DeribitClient:
    """Fetches ETH options data from Deribit for crypto GEX calculation.

    Deribit is the dominant crypto options exchange (~90% of volume).
    This gives us the closest equivalent to equity GEX.
    """
    BASE_URL = "https://www.deribit.com/api/v2/public"

    def __init__(self):
        self._last_request_time = 0
        self._rate_limit_ms = 100  # 10 req/sec

    def _rate_limit(self):
        elapsed = (time.time() - self._last_request_time) * 1000
        if elapsed < self._rate_limit_ms:
            time.sleep((self._rate_limit_ms - elapsed) / 1000)
        self._last_request_time = time.time()

    def _request(self, method: str, params: Optional[Dict] = None) -> Optional[Any]:
        """Make a Deribit public API request."""
        url = f"{self.BASE_URL}/{method}"
        for attempt in range(3):
            try:
                self._rate_limit()
                resp = requests.get(url, params=params, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("result")
                elif resp.status_code == 429:
                    time.sleep((attempt + 1) * 2)
                    continue
                else:
                    logger.error(f"Deribit HTTP {resp.status_code}")
                    return None
            except requests.RequestException as e:
                logger.error(f"Deribit request failed (attempt {attempt + 1}): {e}")
                if attempt < 2:
                    time.sleep((attempt + 1) * 1)
        return None

    def get_index_price(self, currency: str = "ETH") -> Optional[float]:
        """Get current index price."""
        result = self._request("get_index_price", {"index_name": f"{currency.lower()}_usd"})
        if result:
            return float(result.get("index_price", 0))
        return None

    def get_instruments(self, currency: str = "ETH", kind: str = "option") -> List[Dict]:
        """Get all active instruments."""
        result = self._request("get_instruments", {
            "currency": currency,
            "kind": kind,
            "expired": "false",
        })
        return result if isinstance(result, list) else []

    def get_book_summary(
        self, currency: str = "ETH", kind: str = "option"
    ) -> List[Dict]:
        """Get book summary for all instruments - includes OI and Greeks."""
        result = self._request("get_book_summary_by_currency", {
            "currency": currency,
            "kind": kind,
        })
        return result if isinstance(result, list) else []

    def get_options_chain_data(self, currency: str = "ETH") -> List[OpenInterestLevel]:
        """Build options chain with OI per strike from Deribit book summaries.

        This is the crypto equivalent of getting per-strike gamma data.
        """
        summaries = self.get_book_summary(currency, "option")
        if not summaries:
            return []

        # Aggregate by strike
        strikes: Dict[float, Dict] = {}
        for inst in summaries:
            try:
                name = inst.get("instrument_name", "")
                # Format: ETH-28FEB26-2500-C
                parts = name.split("-")
                if len(parts) < 4:
                    continue
                strike = float(parts[2])
                opt_type = parts[3]  # C or P
                oi = float(inst.get("open_interest", 0))
                volume = float(inst.get("volume", 0))

                if strike not in strikes:
                    strikes[strike] = {
                        "call_oi": 0, "put_oi": 0,
                        "call_vol": 0, "put_vol": 0,
                    }

                if opt_type == "C":
                    strikes[strike]["call_oi"] += oi
                    strikes[strike]["call_vol"] += volume
                else:
                    strikes[strike]["put_oi"] += oi
                    strikes[strike]["put_vol"] += volume
            except (IndexError, ValueError):
                continue

        levels = []
        for strike_price, data in sorted(strikes.items()):
            call_oi = data["call_oi"]
            put_oi = data["put_oi"]
            levels.append(OpenInterestLevel(
                strike=strike_price,
                call_oi=call_oi,
                put_oi=put_oi,
                net_oi=call_oi - put_oi,
                total_oi=call_oi + put_oi,
                call_volume=data["call_vol"],
                put_volume=data["put_vol"],
                source="deribit",
            ))
        return levels

    def calculate_max_pain(self, oi_levels: List[OpenInterestLevel]) -> Optional[float]:
        """Calculate max pain - the price where most options expire worthless.

        This is the crypto equivalent of the GEX flip point.
        """
        if not oi_levels:
            return None

        strikes = [level.strike for level in oi_levels]
        min_pain = float("inf")
        max_pain_strike = None

        for candidate in strikes:
            total_pain = 0
            for level in oi_levels:
                # Call pain: calls are worthless below strike
                if candidate > level.strike:
                    total_pain += (candidate - level.strike) * level.call_oi
                # Put pain: puts are worthless above strike
                if candidate < level.strike:
                    total_pain += (level.strike - candidate) * level.put_oi
            if total_pain < min_pain:
                min_pain = total_pain
                max_pain_strike = candidate

        return max_pain_strike


# ---------------------------------------------------------------------------
# Unified Crypto Data Provider
# ---------------------------------------------------------------------------

_provider_instance: Optional["CryptoDataProvider"] = None


def get_crypto_data_provider() -> "CryptoDataProvider":
    """Singleton accessor for the crypto data provider."""
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = CryptoDataProvider()
    return _provider_instance


class CryptoDataProvider:
    """Unified crypto data provider - the equivalent of UnifiedDataProvider for crypto.

    Combines CoinGlass + Deribit to build a complete market microstructure
    picture for ETH, mapping to AlphaGEX's GEX-based analysis framework.

    GEX Concept → Crypto Equivalent:
        Gamma Regime     → Funding Rate regime
        Gamma Walls      → High OI clusters + Liquidation zones
        Flip Point       → Max Pain level
        Net GEX          → Crypto GEX from Deribit options
        Price Magnets    → Liquidation clusters
        Directional Bias → Long/Short ratio
    """

    def __init__(self):
        self._coinglass: Optional[CoinGlassClient] = None
        self._deribit: Optional[DeribitClient] = None

        # Initialize CoinGlass
        try:
            self._coinglass = CoinGlassClient()
            logger.info("CryptoDataProvider: CoinGlass client initialized")
        except Exception as e:
            logger.warning(f"CryptoDataProvider: CoinGlass init failed: {e}")

        # Initialize Deribit (public API, no key needed)
        try:
            self._deribit = DeribitClient()
            logger.info("CryptoDataProvider: Deribit client initialized")
        except Exception as e:
            logger.warning(f"CryptoDataProvider: Deribit init failed: {e}")

        # Per-symbol cache (supports multi-coin without eviction)
        self._snapshot_cache: Dict[str, CryptoMarketSnapshot] = {}
        self._snapshot_cache_time: Dict[str, float] = {}
        self._cache_ttl: int = 30  # seconds

    def get_snapshot(self, symbol: str = "ETH") -> CryptoMarketSnapshot:
        """Get complete market microstructure snapshot.

        This is the main entry point - equivalent to WATCHTOWER's process_options_chain().
        Returns a CryptoMarketSnapshot with all signals derived.
        """
        now = time.time()
        cached = self._snapshot_cache.get(symbol)
        cached_time = self._snapshot_cache_time.get(symbol, 0)
        if cached and (now - cached_time) < self._cache_ttl:
            return cached

        spot = self._get_spot_price(symbol)
        if not spot or spot <= 0:
            logger.warning(f"CryptoDataProvider: No valid spot price for {symbol}")
            return None
        snapshot = CryptoMarketSnapshot(
            symbol=symbol,
            spot_price=spot,
            timestamp=datetime.now(CENTRAL_TZ),
        )

        # Fetch all data sources (with graceful fallbacks)
        if self._coinglass:
            snapshot.funding_rate = self._coinglass.get_funding_rate(symbol)
            snapshot.ls_ratio = self._coinglass.get_long_short_ratio(symbol)

            liquidations = self._coinglass.get_liquidation_data(symbol)
            if liquidations and spot:
                for liq in liquidations:
                    liq.distance_pct = abs(liq.price_level - spot) / spot * 100
                snapshot.liquidation_clusters = sorted(
                    liquidations, key=lambda x: x.distance_pct
                )
                # Find nearest on each side
                longs_below = [l for l in liquidations if l.price_level < spot]
                shorts_above = [l for l in liquidations if l.price_level > spot]
                if longs_below:
                    snapshot.nearest_long_liq = max(
                        longs_below, key=lambda x: x.long_liquidation_usd
                    ).price_level
                if shorts_above:
                    snapshot.nearest_short_liq = min(
                        shorts_above, key=lambda x: x.short_liquidation_usd
                    ).price_level

        if self._deribit:
            oi_levels = self._deribit.get_options_chain_data(symbol)
            if oi_levels:
                snapshot.oi_levels = oi_levels
                snapshot.max_pain = self._deribit.calculate_max_pain(oi_levels)

                # Build crypto GEX from OI data
                snapshot.crypto_gex = self._build_crypto_gex(symbol, spot, oi_levels)

        # Derive combined signals
        self._derive_signals(snapshot)

        self._snapshot_cache[symbol] = snapshot
        self._snapshot_cache_time[symbol] = now
        return snapshot

    def get_funding_rate(self, symbol: str = "ETH") -> Optional[FundingRate]:
        """Get current funding rate."""
        if self._coinglass:
            return self._coinglass.get_funding_rate(symbol)
        return None

    def get_liquidations(self, symbol: str = "ETH") -> List[LiquidationCluster]:
        """Get liquidation cluster data."""
        if not self._coinglass:
            return []
        spot = self._get_spot_price(symbol)
        liquidations = self._coinglass.get_liquidation_data(symbol)
        if spot:
            for liq in liquidations:
                liq.distance_pct = abs(liq.price_level - spot) / spot * 100
        return liquidations

    def get_long_short_ratio(self, symbol: str = "ETH") -> Optional[LongShortRatio]:
        """Get L/S ratio."""
        if self._coinglass:
            return self._coinglass.get_long_short_ratio(symbol)
        return None

    def get_options_oi(self, symbol: str = "ETH") -> List[OpenInterestLevel]:
        """Get per-strike OI from Deribit."""
        if self._deribit:
            return self._deribit.get_options_chain_data(symbol)
        return []

    # Coins supported by Deribit index prices
    _DERIBIT_SUPPORTED = {"BTC", "ETH", "SOL", "MATIC", "USDC"}

    def _get_spot_price(self, symbol: str) -> Optional[float]:
        """Get current spot price.

        Tries Deribit first (only for supported coins like ETH/BTC), then
        falls back to Coinbase public API (supports all coins including
        XRP, SHIB, DOGE).
        """
        # Deribit only supports a handful of coins
        if self._deribit and symbol.upper() in self._DERIBIT_SUPPORTED:
            price = self._deribit.get_index_price(symbol)
            if price:
                return price

        # Fallback: Coinbase public spot price (no auth required, all coins)
        try:
            ticker = f"{symbol.upper()}-USD"
            url = f"https://api.coinbase.com/v2/prices/{ticker}/spot"
            resp = requests.get(url, headers={"User-Agent": "AlphaGEX/1.0"}, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                price = float(data["data"]["amount"])
                if price > 0:
                    return price
        except Exception as e:
            logger.debug(f"CryptoDataProvider: Coinbase spot price failed for {symbol}: {e}")

        return None

    def _build_crypto_gex(
        self,
        symbol: str,
        spot: Optional[float],
        oi_levels: List[OpenInterestLevel],
    ) -> Optional[CryptoGEX]:
        """Build a GEX approximation from Deribit options OI.

        Since we don't have dealer positioning data directly, we approximate
        gamma exposure from OI distribution assuming market makers are net
        sellers of options (the standard GEX assumption).
        """
        if not oi_levels or not spot:
            return None

        total_call_gex = 0.0
        total_put_gex = 0.0
        per_strike = []

        for level in oi_levels:
            # Simplified gamma proxy: OI * proximity_weight
            # Closer to spot = higher gamma impact
            distance = abs(level.strike - spot) / spot
            proximity_weight = max(0, 1.0 - distance * 5)  # Decays with distance

            # Calls: positive gamma (dealers long gamma from sold calls)
            call_gamma = level.call_oi * proximity_weight
            # Puts: negative gamma contribution (dealers short gamma)
            put_gamma = -level.put_oi * proximity_weight

            strike_gex = call_gamma + put_gamma
            total_call_gex += call_gamma
            total_put_gex += put_gamma

            if proximity_weight > 0.1:
                per_strike.append({
                    "strike": level.strike,
                    "call_gex": round(call_gamma, 2),
                    "put_gex": round(put_gamma, 2),
                    "net_gex": round(strike_gex, 2),
                    "total_oi": level.total_oi,
                    "proximity": round(proximity_weight, 3),
                })

        net_gex = total_call_gex + total_put_gex
        max_pain = self._deribit.calculate_max_pain(oi_levels) if self._deribit else None

        if net_gex > 0:
            regime = "POSITIVE"
        elif net_gex < 0:
            regime = "NEGATIVE"
        else:
            regime = "NEUTRAL"

        return CryptoGEX(
            symbol=symbol,
            net_gex=round(net_gex, 2),
            flip_point=max_pain or spot,
            call_gex=round(total_call_gex, 2),
            put_gex=round(total_put_gex, 2),
            gamma_regime=regime,
            max_pain=max_pain or spot,
            strikes=per_strike,
            timestamp=datetime.now(CENTRAL_TZ),
        )

    def _derive_signals(self, snapshot: CryptoMarketSnapshot):
        """Derive combined trading signals from all data sources.

        This is the equivalent of WATCHTOWER's calculate_market_structure() -
        combines all individual signals into actionable trade recommendations.
        """
        # 1. Leverage Regime (from funding rate)
        if snapshot.funding_rate:
            fr = snapshot.funding_rate
            if fr.regime in ("EXTREME_LONG", "EXTREME_SHORT"):
                snapshot.leverage_regime = "OVERLEVERAGED"
            elif fr.regime in ("OVERLEVERAGED_LONG", "OVERLEVERAGED_SHORT"):
                snapshot.leverage_regime = "OVERLEVERAGED"
            elif fr.regime == "BALANCED":
                snapshot.leverage_regime = "BALANCED"
            else:
                snapshot.leverage_regime = "MILD_IMBALANCE"
            snapshot.funding_regime = fr.regime

        # 2. Directional Bias (from L/S ratio + funding direction)
        if snapshot.ls_ratio:
            ls = snapshot.ls_ratio
            if ls.bias in ("EXTREME_LONG", "LONG_BIASED"):
                snapshot.directional_bias = "BEARISH"  # Contrarian: crowd is long
            elif ls.bias in ("EXTREME_SHORT", "SHORT_BIASED"):
                snapshot.directional_bias = "BULLISH"  # Contrarian: crowd is short
            else:
                snapshot.directional_bias = "NEUTRAL"

        # 3. Squeeze Risk (from liquidation proximity)
        if snapshot.liquidation_clusters and snapshot.spot_price > 0:
            near_clusters = [
                c for c in snapshot.liquidation_clusters
                if c.distance_pct < 3.0 and c.intensity in ("HIGH", "MEDIUM")
            ]
            if len(near_clusters) >= 3:
                snapshot.squeeze_risk = "HIGH"
            elif len(near_clusters) >= 1:
                snapshot.squeeze_risk = "ELEVATED"
            else:
                snapshot.squeeze_risk = "LOW"

        # 4. Volatility Regime (from funding rate magnitude + squeeze risk)
        if snapshot.funding_rate:
            abs_fr = abs(snapshot.funding_rate.rate) if snapshot.funding_rate.rate else 0
            if abs_fr > 0.03 or snapshot.squeeze_risk == "HIGH":
                snapshot.volatility_regime = "HIGH"
            elif abs_fr > 0.01 or snapshot.squeeze_risk == "ELEVATED":
                snapshot.volatility_regime = "ELEVATED"
            elif abs_fr < 0.003:
                snapshot.volatility_regime = "LOW"
            else:
                snapshot.volatility_regime = "NORMAL"

        # 5. Combined Signal (the trade decision)
        snapshot.combined_signal, snapshot.combined_confidence = (
            self._calculate_combined_signal(snapshot)
        )

    def _calculate_combined_signal(
        self, snapshot: CryptoMarketSnapshot
    ) -> Tuple[str, str]:
        """Calculate the combined trade signal.

        Uses ALL available data sources with Deribit GEX as primary signal:

        Priority 1 (Deribit GEX - always available):
          NEGATIVE regime + price below max pain → LONG (mean reversion)
          NEGATIVE regime + price above max pain → SHORT (momentum)
          POSITIVE regime + stable               → RANGE_BOUND

        Priority 2 (CoinGlass data - when available, boosts confidence):
          Funding + L/S ratio confirm or override the GEX signal.
        """
        funding_regime = snapshot.funding_regime
        bias = snapshot.directional_bias
        squeeze = snapshot.squeeze_risk
        leverage = snapshot.leverage_regime

        # Deribit GEX data (primary signal - always available)
        has_gex = snapshot.crypto_gex is not None
        gex_regime = snapshot.crypto_gex.gamma_regime if has_gex else "NEUTRAL"
        gex_net = snapshot.crypto_gex.net_gex if has_gex else 0
        max_pain = snapshot.crypto_gex.max_pain if has_gex else None
        spot = snapshot.spot_price

        # CoinGlass data availability check
        has_coinglass = funding_regime not in ("UNKNOWN", "") and funding_regime is not None

        # ---- HIGH CONVICTION: CoinGlass + GEX agree ----
        if has_coinglass:
            if funding_regime == "BALANCED" and bias == "NEUTRAL" and squeeze == "LOW":
                return ("RANGE_BOUND", "HIGH")

            if funding_regime in ("EXTREME_LONG", "OVERLEVERAGED_LONG") and bias == "BEARISH":
                if squeeze in ("HIGH", "ELEVATED"):
                    return ("SHORT", "HIGH")
                return ("SHORT", "MEDIUM")

            if funding_regime in ("EXTREME_SHORT", "OVERLEVERAGED_SHORT") and bias == "BULLISH":
                if squeeze in ("HIGH", "ELEVATED"):
                    return ("LONG", "HIGH")
                return ("LONG", "MEDIUM")

        # ---- MEDIUM CONVICTION: Deribit GEX alone ----
        if has_gex and gex_regime == "NEGATIVE" and abs(gex_net) > 50000:
            # Negative gamma = momentum regime. Use max pain as directional anchor.
            if max_pain and spot > 0:
                pain_dist_pct = (max_pain - spot) / spot
                if pain_dist_pct > 0.03:
                    # Price well below max pain → gravity pulls UP
                    return ("LONG", "MEDIUM")
                elif pain_dist_pct < -0.03:
                    # Price well above max pain → gravity pulls DOWN
                    return ("SHORT", "MEDIUM")

        if has_gex and gex_regime == "POSITIVE" and squeeze == "LOW":
            # Positive gamma = mean reversion. Range-bound.
            return ("RANGE_BOUND", "MEDIUM")

        # ---- LOW CONVICTION: Weaker GEX signals ----
        if has_gex and gex_regime == "NEGATIVE":
            if max_pain and spot > 0:
                pain_dist_pct = (max_pain - spot) / spot
                if pain_dist_pct > 0.01:
                    return ("LONG", "LOW")
                elif pain_dist_pct < -0.01:
                    return ("SHORT", "LOW")

        # CoinGlass-only low-confidence fallback
        if has_coinglass:
            if leverage == "BALANCED" and squeeze == "LOW":
                return ("RANGE_BOUND", "MEDIUM")
            if bias == "BULLISH" and squeeze != "HIGH":
                return ("LONG", "LOW")
            if bias == "BEARISH" and squeeze != "HIGH":
                return ("SHORT", "LOW")

        # Too uncertain or too dangerous
        if leverage == "OVERLEVERAGED" and squeeze == "HIGH":
            return ("WAIT", "HIGH")

        return ("WAIT", "LOW")
