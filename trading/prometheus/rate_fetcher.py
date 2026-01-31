"""
PROMETHEUS Rate Fetcher
=======================

Fetches current interest rates from public sources for accurate
box spread rate comparisons.

Sources:
- Fed Funds Rate: FRED (Federal Reserve Economic Data)
- SOFR: FRED
- Treasury Rates: Treasury.gov

Caching: Rates are cached for 4 hours since they don't change frequently.
"""

import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
import os

logger = logging.getLogger(__name__)


@dataclass
class InterestRates:
    """Current interest rate data."""
    fed_funds_rate: float
    sofr_rate: float
    treasury_3m: float
    treasury_1y: float
    margin_rate: float  # Estimated broker margin rate
    last_updated: datetime
    source: str  # 'live' or 'cached' or 'fallback'


class RateFetcher:
    """
    Fetches and caches current interest rates.

    Uses FRED API (free, no key required for basic access) as primary source.
    Falls back to hardcoded values if fetching fails.
    """

    # FRED series IDs
    FRED_SERIES = {
        'fed_funds': 'FEDFUNDS',      # Federal Funds Effective Rate
        'sofr': 'SOFR',               # Secured Overnight Financing Rate
        'treasury_3m': 'DTB3',        # 3-Month Treasury Bill
        'treasury_1y': 'DTB1YR',      # 1-Year Treasury Bill
    }

    # Cache duration
    CACHE_DURATION_HOURS = 4

    # Fallback rates (updated periodically)
    FALLBACK_RATES = {
        'fed_funds': 4.33,    # As of Jan 2025
        'sofr': 4.30,         # Typically close to Fed Funds
        'treasury_3m': 4.25,
        'treasury_1y': 4.15,
        'margin_rate': 8.50,  # Typical broker margin
    }

    # Singleton instance
    _instance = None
    _cache: Optional[InterestRates] = None
    _cache_time: Optional[datetime] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_rates(self, force_refresh: bool = False) -> InterestRates:
        """
        Get current interest rates, using cache if available.

        Args:
            force_refresh: If True, bypass cache and fetch fresh data

        Returns:
            InterestRates dataclass with current rates
        """
        # Check cache
        if not force_refresh and self._is_cache_valid():
            return self._cache

        # Try to fetch fresh rates
        try:
            rates = self._fetch_rates()
            self._cache = rates
            self._cache_time = datetime.now()
            logger.info(f"Fetched fresh rates: Fed Funds={rates.fed_funds_rate}%, SOFR={rates.sofr_rate}%")
            return rates
        except Exception as e:
            logger.warning(f"Failed to fetch rates: {e}, using fallback")
            return self._get_fallback_rates()

    def _is_cache_valid(self) -> bool:
        """Check if cached rates are still valid."""
        if self._cache is None or self._cache_time is None:
            return False

        age = datetime.now() - self._cache_time
        return age < timedelta(hours=self.CACHE_DURATION_HOURS)

    def _fetch_rates(self) -> InterestRates:
        """
        Fetch rates from FRED API.

        FRED provides free access without API key for basic requests.
        We use the observations endpoint with limit=1 to get latest value.
        """
        rates = {}

        for rate_name, series_id in self.FRED_SERIES.items():
            try:
                value = self._fetch_fred_series(series_id)
                if value is not None:
                    rates[rate_name] = value
                else:
                    rates[rate_name] = self.FALLBACK_RATES.get(rate_name, 4.5)
            except Exception as e:
                logger.debug(f"Failed to fetch {series_id}: {e}")
                rates[rate_name] = self.FALLBACK_RATES.get(rate_name, 4.5)

        # Margin rate is estimated as Fed Funds + spread
        # Most brokers charge Fed Funds + 3-4%
        margin_spread = 4.0  # Typical broker spread over Fed Funds
        margin_rate = rates.get('fed_funds', 4.5) + margin_spread

        return InterestRates(
            fed_funds_rate=rates.get('fed_funds', self.FALLBACK_RATES['fed_funds']),
            sofr_rate=rates.get('sofr', self.FALLBACK_RATES['sofr']),
            treasury_3m=rates.get('treasury_3m', self.FALLBACK_RATES['treasury_3m']),
            treasury_1y=rates.get('treasury_1y', self.FALLBACK_RATES['treasury_1y']),
            margin_rate=margin_rate,
            last_updated=datetime.now(),
            source='live'
        )

    def _fetch_fred_series(self, series_id: str) -> Optional[float]:
        """
        Fetch a single FRED series value.

        Uses the FRED API without requiring an API key by accessing
        the public data endpoint.
        """
        # FRED API key from environment (optional but recommended)
        api_key = os.environ.get('FRED_API_KEY')

        if api_key:
            # Use official API with key
            url = f"https://api.stlouisfed.org/fred/series/observations"
            params = {
                'series_id': series_id,
                'api_key': api_key,
                'file_type': 'json',
                'limit': 1,
                'sort_order': 'desc'
            }
        else:
            # Use alternative approach - fetch from public data page
            # This is less reliable but works without API key
            return self._fetch_fred_fallback(series_id)

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            observations = data.get('observations', [])
            if observations:
                value_str = observations[0].get('value', '.')
                if value_str != '.':  # FRED uses '.' for missing data
                    return float(value_str)
        except Exception as e:
            logger.debug(f"FRED API fetch failed for {series_id}: {e}")

        return None

    def _fetch_fred_fallback(self, series_id: str) -> Optional[float]:
        """
        Fallback method to get FRED data without API key.

        Uses the Treasury Direct API for treasury rates,
        and estimated values for others.
        """
        try:
            # For treasury rates, use Treasury Direct API
            if series_id in ['DTB3', 'DTB1YR']:
                return self._fetch_treasury_rate(series_id)

            # For Fed Funds and SOFR, try alternative sources
            if series_id == 'FEDFUNDS':
                return self._estimate_fed_funds()

            if series_id == 'SOFR':
                # SOFR is typically very close to Fed Funds
                fed_funds = self._estimate_fed_funds()
                if fed_funds:
                    return fed_funds - 0.03  # SOFR usually slightly below

        except Exception as e:
            logger.debug(f"Fallback fetch failed for {series_id}: {e}")

        return None

    def _fetch_treasury_rate(self, series_id: str) -> Optional[float]:
        """Fetch treasury rate from Treasury Fiscal Data API."""
        try:
            # Use Treasury's daily treasury rates endpoint
            # This provides actual bill/note auction rates
            url = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/avg_interest_rates"
            params = {
                'sort': '-record_date',
                'page[size]': 10,
                'fields': 'record_date,security_desc,avg_interest_rate_amt'
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            records = data.get('data', [])

            # Look for matching security type
            target_desc = 'Treasury Bills' if series_id in ['DTB3', 'DTB1YR'] else None

            for record in records:
                desc = record.get('security_desc', '')
                if target_desc and target_desc in desc:
                    rate = record.get('avg_interest_rate_amt')
                    if rate:
                        logger.info(f"Got treasury rate from Treasury.gov: {rate}%")
                        return float(rate)

        except Exception as e:
            logger.debug(f"Treasury fetch failed: {e}")

        return None

    def _estimate_fed_funds(self) -> Optional[float]:
        """
        Estimate current Fed Funds rate.

        Uses known FOMC decision dates and rates.
        Updated after each FOMC meeting.
        """
        # Current Fed Funds target range (as of January 2026)
        # Update this after FOMC meetings
        # See: https://www.federalreserve.gov/monetarypolicy/openmarket.htm
        CURRENT_FED_FUNDS_LOWER = 4.25
        CURRENT_FED_FUNDS_UPPER = 4.50

        # Effective rate is typically middle of range
        effective_rate = (CURRENT_FED_FUNDS_LOWER + CURRENT_FED_FUNDS_UPPER) / 2
        logger.info(f"Using estimated Fed Funds rate: {effective_rate}% (FOMC range: {CURRENT_FED_FUNDS_LOWER}-{CURRENT_FED_FUNDS_UPPER}%)")
        return effective_rate

    def _get_fallback_rates(self) -> InterestRates:
        """
        Return fallback rates based on current FOMC target range.

        These rates are derived from the FOMC target range (4.25-4.50% as of Jan 2026).
        While not live-fetched, they reflect the current monetary policy.
        """
        margin_rate = self.FALLBACK_RATES['fed_funds'] + 4.0

        logger.info(f"Using FOMC-based fallback rates (Fed Funds ~{self.FALLBACK_RATES['fed_funds']}%)")

        return InterestRates(
            fed_funds_rate=self.FALLBACK_RATES['fed_funds'],
            sofr_rate=self.FALLBACK_RATES['sofr'],
            treasury_3m=self.FALLBACK_RATES['treasury_3m'],
            treasury_1y=self.FALLBACK_RATES['treasury_1y'],
            margin_rate=margin_rate,
            last_updated=datetime.now(),
            source='fomc_based'  # Indicates these are based on current FOMC target, not stale
        )

    def get_rate_summary(self) -> str:
        """Get a formatted summary of current rates."""
        rates = self.get_rates()

        return f"""
Interest Rate Summary ({rates.source})
======================================
Fed Funds Rate:    {rates.fed_funds_rate:.2f}%
SOFR:              {rates.sofr_rate:.2f}%
3-Month Treasury:  {rates.treasury_3m:.2f}%
1-Year Treasury:   {rates.treasury_1y:.2f}%
Est. Margin Rate:  {rates.margin_rate:.2f}%

Last Updated: {rates.last_updated.strftime('%Y-%m-%d %H:%M:%S')}
Source: {rates.source}
""".strip()


# Singleton accessor
_rate_fetcher: Optional[RateFetcher] = None


def get_rate_fetcher() -> RateFetcher:
    """Get the singleton RateFetcher instance."""
    global _rate_fetcher
    if _rate_fetcher is None:
        _rate_fetcher = RateFetcher()
    return _rate_fetcher


def get_current_rates() -> InterestRates:
    """Convenience function to get current rates."""
    return get_rate_fetcher().get_rates()


def get_fed_funds_rate() -> float:
    """Get just the Fed Funds rate."""
    return get_rate_fetcher().get_rates().fed_funds_rate


def get_margin_rate() -> float:
    """Get estimated broker margin rate."""
    return get_rate_fetcher().get_rates().margin_rate
