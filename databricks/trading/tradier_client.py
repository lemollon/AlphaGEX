"""
Standalone Tradier API Client
==============================

Lightweight Tradier API client for market data.
Replaces the dependency on AlphaGEX's data.tradier_data_fetcher module.
Only implements the methods needed by FLAME and SPARK signal generators.
"""

import logging
from typing import Optional, Dict, Any, List

import requests

from config import DatabricksConfig

logger = logging.getLogger(__name__)


class TradierClient:
    """
    Minimal Tradier API client for option quotes and chain data.

    Uses production Tradier API (not sandbox) for real market data.
    """

    def __init__(self, api_key: str = None, base_url: str = None):
        self.api_key = api_key or DatabricksConfig.TRADIER_API_KEY
        self.base_url = base_url or DatabricksConfig.TRADIER_BASE_URL
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        })

    def _get(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """Make a GET request to Tradier API."""
        try:
            url = f"{self.base_url}{endpoint}"
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.warning(f"Tradier API error: {e}")
            return None

    def get_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get a stock quote."""
        data = self._get("/markets/quotes", {"symbols": symbol})
        if not data:
            return None
        quotes = data.get("quotes", {}).get("quote", {})
        if isinstance(quotes, list):
            quotes = quotes[0] if quotes else {}
        return quotes

    def get_option_expirations(self, symbol: str) -> Optional[List[str]]:
        """Get available option expiration dates."""
        data = self._get("/markets/options/expirations", {"symbol": symbol})
        if not data:
            return None
        expirations = data.get("expirations", {}).get("date", [])
        if isinstance(expirations, str):
            return [expirations]
        return expirations

    def get_option_chain(self, symbol: str, expiration: str) -> Optional[List[Dict]]:
        """Get full option chain for a given expiration."""
        data = self._get("/markets/options/chains", {
            "symbol": symbol,
            "expiration": expiration,
            "greeks": "false",
        })
        if not data:
            return None
        options = data.get("options", {}).get("option", [])
        if isinstance(options, dict):
            return [options]
        return options

    def get_option_quote(self, occ_symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get a quote for a specific option contract by OCC symbol.

        OCC symbol format: SPY260225P00580000
        """
        data = self._get("/markets/quotes", {"symbols": occ_symbol})
        if not data:
            return None
        quotes = data.get("quotes", {}).get("quote", {})
        if isinstance(quotes, list):
            quotes = quotes[0] if quotes else {}
        if quotes and quotes.get("bid") is not None:
            return quotes
        unmatched = data.get("quotes", {}).get("unmatched_symbols", {})
        if unmatched:
            logger.debug(f"Option symbol not found: {occ_symbol}")
            return None
        return quotes

    def get_vix(self) -> Optional[float]:
        """Get current VIX value."""
        quote = self.get_quote("VIX")
        if quote:
            return float(quote.get("last", 0)) or None
        return None
