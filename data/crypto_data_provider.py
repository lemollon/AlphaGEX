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
class OpenInterestSnapshot:
    """Aggregate open interest across exchanges for a perp ticker.

    OI is the leveraged-positioning equivalent of options OI in equity GEX.
    Used as a directional/conviction signal for assets without Deribit options
    (XRP, DOGE, SHIB).
    """
    symbol: str
    total_usd: float                # Sum across all exchanges
    total_quantity: float           # Sum in coin units
    coin_margin_usd: float          # OI margined in the coin itself
    stable_margin_usd: float        # OI margined in stables (USDT etc.)
    exchange_count: int
    timestamp: datetime

    @property
    def stable_share(self) -> float:
        """Fraction of OI in stable-margin (vs coin-margin).

        High stable share = retail/institutional USDT longs (more reactive).
        High coin share = HODLer hedges (slower, smarter money).
        """
        total = self.coin_margin_usd + self.stable_margin_usd
        return self.stable_margin_usd / total if total > 0 else 0.5


@dataclass
class TakerVolume:
    """Taker buy vs sell volume - aggressive directional flow.

    Replaces L/S ratio when that endpoint isn't available on the plan tier.
    Buy ratio > 0.55 = bullish aggression; < 0.45 = bearish aggression.
    """
    symbol: str
    buy_volume_usd: float
    sell_volume_usd: float
    exchange: str
    timestamp: datetime

    @property
    def buy_ratio(self) -> float:
        total = self.buy_volume_usd + self.sell_volume_usd
        return self.buy_volume_usd / total if total > 0 else 0.5

    @property
    def bias(self) -> str:
        r = self.buy_ratio
        if r > 0.60:
            return "STRONG_BUY"
        if r > 0.55:
            return "BUY"
        if r < 0.40:
            return "STRONG_SELL"
        if r < 0.45:
            return "SELL"
        return "BALANCED"


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

    # Open Interest (→ Conviction / leveraged positioning)
    oi_snapshot: Optional["OpenInterestSnapshot"] = None

    # Taker buy/sell volume (→ Aggressive directional flow, L/S substitute)
    taker_volume: Optional["TakerVolume"] = None

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
    - Funding rates across exchanges (v2 public)
    - Liquidation heatmap data (v4, paid plan)
    - Long/Short ratio (v4, paid plan)
    """
    # v2 = public legacy endpoint (funding only). No auth header required.
    # v3 = deprecated, returns 500 server-side regardless of auth.
    # v4 = current paid API. Header: CG-API-KEY.
    BASE_URL_V2 = "https://open-api.coinglass.com/public/v2"
    BASE_URL_V4 = "https://open-api-v4.coinglass.com/api"

    # Substrings in the API "msg" field that indicate the endpoint is
    # permanently gated by the user's plan tier. Once seen, we stop
    # calling that endpoint for the rest of the session - no point
    # burning rate-limit budget on something that always fails.
    _GATED_MSG_HINTS = ("upgrade plan", "not available for your")

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("COINGLASS_API_KEY", "")
        self._last_request_time = 0
        # CoinGlass paid plans are tier-throttled. Hobbyist = 30/min (one
        # call per 2s). 2.5s padding fits with margin.
        self._rate_limit_ms = 2500
        # Endpoints that returned "Upgrade plan" - skip on subsequent calls
        self._gated_endpoints: set = set()

    def _rate_limit(self):
        """Enforce rate limiting."""
        elapsed = (time.time() - self._last_request_time) * 1000
        if elapsed < self._rate_limit_ms:
            time.sleep((self._rate_limit_ms - elapsed) / 1000)
        self._last_request_time = time.time()

    def _is_gated_msg(self, msg: str) -> bool:
        m = (msg or "").lower()
        return any(hint in m for hint in self._GATED_MSG_HINTS)

    def _request(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        version: str = "v4",
    ) -> Optional[Any]:
        """Make an API request with retry logic.

        version="v2": legacy public endpoint, no auth header required.
        version="v4": current paid API, requires CG-API-KEY header.

        If a previous call to this endpoint returned "Upgrade plan",
        we short-circuit to None without hitting the API.
        """
        if endpoint in self._gated_endpoints:
            return None

        if version == "v2":
            base = self.BASE_URL_V2
            headers = {"coinglassSecret": self.api_key} if self.api_key else {}
        else:
            base = self.BASE_URL_V4
            headers = {"CG-API-KEY": self.api_key} if self.api_key else {}
        url = f"{base}/{endpoint}"
        # Only retry transient errors; don't compound 429s with extra calls.
        for attempt in range(2):
            try:
                self._rate_limit()
                resp = requests.get(url, headers=headers, params=params, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success") or data.get("code") == "0":
                        return data.get("data", data)
                    msg = data.get("msg", "unknown")
                    if self._is_gated_msg(msg):
                        # Permanent plan gate - never call this endpoint again
                        self._gated_endpoints.add(endpoint)
                        logger.warning(
                            f"CoinGlass {endpoint} gated by plan ({msg}); disabled for session"
                        )
                    else:
                        logger.warning(f"CoinGlass API error ({version}): {msg}")
                    return None
                elif resp.status_code == 429:
                    # Single backoff retry, not 3. Multiple retries on
                    # rate-limit just dig the hole deeper.
                    if attempt == 0:
                        logger.warning("CoinGlass rate limited, waiting 5s")
                        time.sleep(5)
                        continue
                    return None
                else:
                    logger.debug(f"CoinGlass HTTP {resp.status_code} on {endpoint} ({version})")
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
        data = self._request("funding", {"symbol": symbol, "time_type": "all"}, version="v2")
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
            "futures/funding-rate/oi-weight-history",
            {"symbol": symbol, "interval": "h1", "limit": limit},
            version="v4",
        )
        if not data or not isinstance(data, list):
            return []
        return data

    def get_open_interest(self, symbol: str = "ETH") -> Optional[OpenInterestSnapshot]:
        """Get aggregate open interest across all exchanges (v4).

        Confirmed working on user's plan for BTC/ETH/XRP/DOGE/SHIB.
        Returns aggregated totals so the signal layer can use OI as a
        conviction/positioning input even when L/S ratio is unavailable.
        """
        data = self._request(
            "futures/open-interest/exchange-list",
            {"symbol": symbol},
            version="v4",
        )
        if not data or not isinstance(data, list):
            return None

        total_usd = 0.0
        total_qty = 0.0
        coin_margin = 0.0
        stable_margin = 0.0
        count = 0
        for ex in data:
            try:
                total_usd += float(ex.get("open_interest_usd", 0) or 0)
                total_qty += float(ex.get("open_interest_quantity", 0) or 0)
                coin_margin += float(ex.get("open_interest_by_coin_margin", 0) or 0)
                stable_margin += float(ex.get("open_interest_by_stable_coin_margin", 0) or 0)
                count += 1
            except (TypeError, ValueError):
                continue

        if count == 0:
            return None

        return OpenInterestSnapshot(
            symbol=symbol,
            total_usd=total_usd,
            total_quantity=total_qty,
            coin_margin_usd=coin_margin,
            stable_margin_usd=stable_margin,
            exchange_count=count,
            timestamp=datetime.now(CENTRAL_TZ),
        )

    def get_taker_volume(self, symbol: str = "ETH", range_: str = "1d") -> Optional[TakerVolume]:
        """Get aggregate taker buy/sell volume across exchanges (v4).

        Used as L/S ratio substitute when L/S endpoint is gated by plan tier.
        High buy_ratio = aggressive longs hitting offers = bullish flow.
        """
        data = self._request(
            "futures/taker-buy-sell-volume/exchange-list",
            {"symbol": symbol, "range": range_},
            version="v4",
        )
        if not data or not isinstance(data, list):
            return None

        buy = 0.0
        sell = 0.0
        for ex in data:
            try:
                buy += float(ex.get("taker_buy_volume_usd", ex.get("buy_volume_usd", 0)) or 0)
                sell += float(ex.get("taker_sell_volume_usd", ex.get("sell_volume_usd", 0)) or 0)
            except (TypeError, ValueError):
                continue

        if buy + sell <= 0:
            return None

        return TakerVolume(
            symbol=symbol,
            buy_volume_usd=buy,
            sell_volume_usd=sell,
            exchange="aggregate",
            timestamp=datetime.now(CENTRAL_TZ),
        )

    def get_liquidation_data(self, symbol: str = "ETH") -> List[LiquidationCluster]:
        """Get liquidation heatmap data (v4, requires paid plan)."""
        data = self._request(
            "futures/liquidation/aggregated-heatmap/model1",
            {"symbol": symbol, "range": "1d"},
            version="v4",
        )
        if not data:
            return []

        # v4 heatmap response shape:
        # {"y": [price_levels], "data": [[x_idx, y_idx, usd], ...]}
        # OR a flat list of {"price","longLiquidationUsd","shortLiquidationUsd"} (legacy).
        # Handle both defensively.
        clusters = []

        if isinstance(data, dict) and "y" in data and "data" in data:
            price_axis = data.get("y", [])
            cells = data.get("data", [])
            # Aggregate USD per price bucket; v4 doesn't split long/short here
            # so we approximate by treating all liquidations as "near both sides"
            # (intensity scoring downstream is what we actually use).
            by_price: Dict[int, float] = {}
            for cell in cells:
                try:
                    if len(cell) >= 3:
                        y_idx = int(cell[1])
                        usd = float(cell[2])
                        by_price[y_idx] = by_price.get(y_idx, 0.0) + usd
                except (TypeError, ValueError):
                    continue
            for y_idx, total_usd in by_price.items():
                if y_idx < 0 or y_idx >= len(price_axis):
                    continue
                try:
                    price = float(price_axis[y_idx])
                except (TypeError, ValueError):
                    continue
                if total_usd < 100_000:
                    intensity = "LOW"
                elif total_usd < 1_000_000:
                    intensity = "MEDIUM"
                else:
                    intensity = "HIGH"
                clusters.append(LiquidationCluster(
                    price_level=price,
                    long_liquidation_usd=total_usd / 2,
                    short_liquidation_usd=total_usd / 2,
                    net_liquidation_usd=0.0,
                    intensity=intensity,
                    distance_pct=0.0,
                ))
            return clusters

        if isinstance(data, list):
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
                        distance_pct=0.0,
                    ))
                except (KeyError, TypeError, ValueError):
                    continue
        return clusters

    # CoinGlass v4 L/S ratio uses Binance perpetual symbols.
    # SHIB is too small for SHIBUSDT - Binance lists it as 1000SHIBUSDT.
    _LS_SYMBOL_MAP = {
        "BTC": "BTCUSDT",
        "ETH": "ETHUSDT",
        "XRP": "XRPUSDT",
        "DOGE": "DOGEUSDT",
        "SHIB": "1000SHIBUSDT",
        "SOL": "SOLUSDT",
    }

    def get_long_short_ratio(
        self,
        symbol: str = "ETH",
        exchange: str = "Binance",
        interval: str = "h4",
    ) -> Optional[LongShortRatio]:
        """Get long/short account ratio from CoinGlass v4.

        Probe revealed: works on user's plan with explicit exchange + h4
        interval. h1 is plan-gated (403). Field names are
        global_account_long_percent / global_account_short_percent /
        global_account_long_short_ratio.

        SHIB is mapped to 1000SHIBUSDT (Binance's notation for thousand-SHIB).
        """
        ticker = symbol.upper()
        cg_symbol = self._LS_SYMBOL_MAP.get(ticker, f"{ticker}USDT")

        data = self._request(
            "futures/global-long-short-account-ratio/history",
            {
                "exchange": exchange,
                "symbol": cg_symbol,
                "interval": interval,
                "limit": 1,
            },
            version="v4",
        )

        # Fallback: if SHIB at 1000SHIBUSDT didn't work, try plain SHIBUSDT
        if not data and ticker == "SHIB":
            data = self._request(
                "futures/global-long-short-account-ratio/history",
                {
                    "exchange": exchange,
                    "symbol": "SHIBUSDT",
                    "interval": interval,
                    "limit": 1,
                },
                version="v4",
            )

        if not data:
            return None

        try:
            latest = data[-1] if isinstance(data, list) and data else data
            if not isinstance(latest, dict):
                return None

            # v4 field names (confirmed via probe):
            long_pct = float(latest.get(
                "global_account_long_percent",
                latest.get("longAccount", latest.get("longRate", 50)),
            ))
            short_pct = float(latest.get(
                "global_account_short_percent",
                latest.get("shortAccount", latest.get("shortRate", 50)),
            ))
            ratio_field = latest.get(
                "global_account_long_short_ratio",
                latest.get("longShortRatio", latest.get("ratio")),
            )
            if ratio_field is not None:
                ratio = float(ratio_field)
            else:
                ratio = long_pct / short_pct if short_pct > 0 else 1.0

            return LongShortRatio(
                symbol=symbol,
                long_pct=long_pct,
                short_pct=short_pct,
                ratio=ratio,
                exchange=exchange,
                timestamp=datetime.now(CENTRAL_TZ),
            )
        except (KeyError, TypeError, ValueError, IndexError) as e:
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
        # 90s TTL keeps us well under CoinGlass rate limits even when 5
        # perp bots all scan together. Each snapshot does ~5 CoinGlass
        # calls; with 2.5s padding that's ~12s per snapshot, so the
        # cache window comfortably covers a single full refresh cycle.
        self._cache_ttl: int = 90  # seconds

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
            snapshot.oi_snapshot = self._coinglass.get_open_interest(symbol)
            snapshot.taker_volume = self._coinglass.get_taker_volume(symbol)

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
        # Check if we have REAL L/S and liquidation data (not just defaults)
        has_ls_data = snapshot.ls_ratio is not None
        has_liq_data = len(snapshot.liquidation_clusters) > 0

        # ---- HIGH CONVICTION: CoinGlass + GEX agree ----
        if has_coinglass:
            # Only claim HIGH confidence RANGE_BOUND when we have FULL data
            # (L/S ratio + liquidations). Without them, bias="NEUTRAL" and
            # squeeze="LOW" are just defaults, not measured values.
            if funding_regime == "BALANCED" and bias == "NEUTRAL" and squeeze == "LOW":
                if has_ls_data and has_liq_data:
                    return ("RANGE_BOUND", "HIGH")
                # Degraded data: funding-only RANGE_BOUND is lower confidence
                # and should use GEX direction if available
                if has_gex and gex_net != 0:
                    if gex_net > 0:
                        return ("LONG", "LOW")
                    else:
                        return ("SHORT", "LOW")
                # No L/S data, no liquidations, no GEX. Falling back to
                # RANGE_BOUND here masks real directional moves for assets
                # like XRP/DOGE/SHIB that lack Deribit GEX and often lack
                # L/S coverage. Fall through to the price-momentum block
                # below so we classify based on actual short-term movement
                # rather than defaulting every scan to RANGE_BOUND.

            if funding_regime in ("EXTREME_LONG", "OVERLEVERAGED_LONG") and bias == "BEARISH":
                if squeeze in ("HIGH", "ELEVATED"):
                    return ("SHORT", "HIGH")
                return ("SHORT", "MEDIUM")

            if funding_regime in ("EXTREME_SHORT", "OVERLEVERAGED_SHORT") and bias == "BULLISH":
                if squeeze in ("HIGH", "ELEVATED"):
                    return ("LONG", "HIGH")
                return ("LONG", "MEDIUM")

            # Funding-only directional signals (when L/S data is unavailable)
            if not has_ls_data:
                if funding_regime in ("EXTREME_LONG", "OVERLEVERAGED_LONG"):
                    return ("SHORT", "LOW")
                if funding_regime in ("EXTREME_SHORT", "OVERLEVERAGED_SHORT"):
                    return ("LONG", "LOW")
                if funding_regime in ("MILD_LONG_BIAS",):
                    if has_gex and gex_net < -10000:
                        return ("SHORT", "LOW")
                if funding_regime in ("MILD_SHORT_BIAS",):
                    if has_gex and gex_net > 10000:
                        return ("LONG", "LOW")

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

        # ---- TIER for alts (XRP/DOGE/SHIB): Funding + OI + Taker volume ----
        # No Deribit GEX, no liquidation heatmap (paywalled), L/S ratio gated by
        # plan tier. But OI exchange-list and taker volume DO work on the
        # current plan for all 5 perp tickers. Use them as the real signal
        # source instead of falling through to price-momentum noise.
        taker = snapshot.taker_volume
        oi = snapshot.oi_snapshot
        has_taker = taker is not None
        has_oi = oi is not None

        if has_taker and has_coinglass:
            taker_bias = taker.bias
            # Strong directional flow + funding agrees → MEDIUM conviction
            if taker_bias in ("STRONG_BUY", "BUY"):
                if funding_regime in ("BALANCED", "MILD_SHORT_BIAS", "OVERLEVERAGED_SHORT", "EXTREME_SHORT"):
                    # Buyers stepping in while shorts crowded = squeeze setup
                    return ("LONG", "MEDIUM" if taker_bias == "STRONG_BUY" else "LOW")
                if funding_regime in ("MILD_LONG_BIAS",):
                    return ("LONG", "LOW")
                # Already extreme long: caution, don't chase
            if taker_bias in ("STRONG_SELL", "SELL"):
                if funding_regime in ("BALANCED", "MILD_LONG_BIAS", "OVERLEVERAGED_LONG", "EXTREME_LONG"):
                    return ("SHORT", "MEDIUM" if taker_bias == "STRONG_SELL" else "LOW")
                if funding_regime in ("MILD_SHORT_BIAS",):
                    return ("SHORT", "LOW")
            if taker_bias == "BALANCED" and funding_regime == "BALANCED":
                return ("RANGE_BOUND", "MEDIUM")

        # OI-only fallback when taker volume isn't available
        if has_oi and has_coinglass and oi.total_usd > 0:
            # OI alone can't pick direction, but combined with funding sign:
            if funding_regime in ("EXTREME_LONG", "OVERLEVERAGED_LONG"):
                return ("SHORT", "LOW")  # Crowded longs + leveraged OI = unwind risk
            if funding_regime in ("EXTREME_SHORT", "OVERLEVERAGED_SHORT"):
                return ("LONG", "LOW")
            if funding_regime == "BALANCED":
                return ("RANGE_BOUND", "LOW")

        # ---- LAST RESORT: Price momentum (degraded data) ----
        # Only reached if CoinGlass entirely unavailable.
        if spot > 0:
            prev = self._snapshot_cache.get(snapshot.symbol)
            if prev and prev.spot_price > 0:
                price_change_pct = (spot - prev.spot_price) / prev.spot_price
                # Lowered from 0.2% to 0.05%: the old 0.2% threshold required
                # a large move in 30 seconds, which rarely happens in calm
                # markets.  This caused ALL crypto bots to get WAIT signals
                # whenever CoinGlass and Deribit APIs were unavailable.
                if abs(price_change_pct) > 0.0005:  # >0.05% move since last snapshot
                    if price_change_pct > 0:
                        return ("LONG", "LOW")  # Momentum following
                    else:
                        return ("SHORT", "LOW")
                # Small move: range-bound (still tradeable for long-only bots)
                return ("RANGE_BOUND", "LOW")
            else:
                # First cycle after startup: no previous snapshot for comparison.
                # Return RANGE_BOUND instead of WAIT so bots can evaluate entry
                # conditions rather than blanket-blocking the first scan.
                logger.info(
                    f"CryptoDataProvider: No previous snapshot for {snapshot.symbol}, "
                    f"defaulting to RANGE_BOUND (first cycle)"
                )
                return ("RANGE_BOUND", "LOW")

        logger.warning(
            f"CryptoDataProvider: All signal sources exhausted for "
            f"{snapshot.symbol} — no GEX, no CoinGlass, no momentum data"
        )
        return ("WAIT", "LOW")
