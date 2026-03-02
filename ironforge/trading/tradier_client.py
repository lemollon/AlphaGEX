"""
Standalone Tradier API Client
==============================

Lightweight Tradier API client for market data and sandbox order execution.
Replaces the dependency on AlphaGEX's data.tradier_data_fetcher module.
Implements methods for FLAME/SPARK signal generation + sandbox order mirroring.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

import requests

from config import Config

logger = logging.getLogger(__name__)


def build_occ_symbol(ticker: str, expiration: str, strike: float, option_type: str) -> str:
    """
    Build OCC option symbol: SPY260227P00585000

    Args:
        ticker: e.g. "SPY"
        expiration: "YYYY-MM-DD"
        strike: e.g. 585.0
        option_type: "P" or "C"
    """
    dt = datetime.strptime(expiration, "%Y-%m-%d")
    yy = dt.strftime("%y")
    mm = dt.strftime("%m")
    dd = dt.strftime("%d")
    strike_part = str(int(round(strike * 1000))).zfill(8)
    return f"{ticker}{yy}{mm}{dd}{option_type}{strike_part}"


class TradierClient:
    """
    Tradier API client for option quotes, chain data, and sandbox order execution.

    Uses Tradier sandbox API for paper trading (configurable via Config).
    Sandbox orders mirror paper trades for real simulated execution.
    """

    def __init__(self, api_key: str = None, base_url: str = None, account_id: str = None):
        self.api_key = api_key or Config.TRADIER_API_KEY
        self.base_url = base_url or Config.TRADIER_BASE_URL
        self._account_id = account_id or getattr(Config, 'TRADIER_ACCOUNT_ID', '') or None
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

    def _post(self, endpoint: str, data: Dict = None) -> Optional[Dict]:
        """Make a POST request to Tradier API (form-encoded for orders)."""
        try:
            url = f"{self.base_url}{endpoint}"
            resp = self.session.post(url, data=data, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.warning(f"Tradier API POST error: {e}")
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

    # ------------------------------------------------------------------
    #  Sandbox order execution (mirrors paper trades in Tradier sandbox)
    # ------------------------------------------------------------------

    def get_account_id(self) -> Optional[str]:
        """
        Get sandbox account ID.

        Uses configured TRADIER_ACCOUNT_ID if set, otherwise auto-discovers
        from the user profile endpoint.
        """
        if self._account_id:
            return self._account_id

        data = self._get("/user/profile")
        if not data:
            logger.warning("Could not fetch Tradier profile for account ID")
            return None

        account = data.get("profile", {}).get("account", {})
        if isinstance(account, list):
            account_id = account[0].get("account_number") if account else None
        else:
            account_id = account.get("account_number")

        if account_id:
            self._account_id = str(account_id)
            logger.info(f"Auto-discovered Tradier account ID: {self._account_id}")
        return self._account_id

    def place_ic_order(
        self,
        ticker: str,
        expiration: str,
        put_short: float,
        put_long: float,
        call_short: float,
        call_long: float,
        contracts: int,
        total_credit: float,
        tag: str = "",
    ) -> Optional[Dict[str, Any]]:
        """
        Place an Iron Condor as a multileg order in Tradier sandbox.

        Sends a 4-leg credit order:
          - Sell put_short (sell to open)
          - Buy put_long  (buy to open)
          - Sell call_short (sell to open)
          - Buy call_long  (buy to open)

        Returns: {"order_id": int, "status": str} or None on failure.
        """
        account_id = self.get_account_id()
        if not account_id:
            logger.error("Cannot place sandbox order: no account ID")
            return None

        ps_occ = build_occ_symbol(ticker, expiration, put_short, "P")
        pl_occ = build_occ_symbol(ticker, expiration, put_long, "P")
        cs_occ = build_occ_symbol(ticker, expiration, call_short, "C")
        cl_occ = build_occ_symbol(ticker, expiration, call_long, "C")

        order_data = {
            "class": "multileg",
            "symbol": ticker,
            "type": "market",
            "duration": "day",
            "option_symbol[0]": ps_occ,
            "side[0]": "sell_to_open",
            "quantity[0]": str(contracts),
            "option_symbol[1]": pl_occ,
            "side[1]": "buy_to_open",
            "quantity[1]": str(contracts),
            "option_symbol[2]": cs_occ,
            "side[2]": "sell_to_open",
            "quantity[2]": str(contracts),
            "option_symbol[3]": cl_occ,
            "side[3]": "buy_to_open",
            "quantity[3]": str(contracts),
        }
        if tag:
            order_data["tag"] = tag[:255]

        result = self._post(f"/accounts/{account_id}/orders", data=order_data)
        if not result:
            logger.error(f"Sandbox IC order failed for {ticker} {expiration}")
            return None

        order = result.get("order", {})
        order_id = order.get("id")
        status = order.get("status", "unknown")

        logger.info(
            f"SANDBOX IC ORDER: {ticker} {expiration} "
            f"{put_long}/{put_short}P-{call_short}/{call_long}C "
            f"x{contracts} @ ${total_credit:.2f} → order_id={order_id} [{status}]"
        )
        return {"order_id": order_id, "status": status}

    def close_ic_order(
        self,
        ticker: str,
        expiration: str,
        put_short: float,
        put_long: float,
        call_short: float,
        call_long: float,
        contracts: int,
        close_price: float,
        tag: str = "",
    ) -> Optional[Dict[str, Any]]:
        """
        Close an Iron Condor by placing the opposite multileg order.

        Sends a 4-leg debit order to close:
          - Buy put_short  (buy to close)
          - Sell put_long   (sell to close)
          - Buy call_short  (buy to close)
          - Sell call_long   (sell to close)

        Returns: {"order_id": int, "status": str} or None on failure.
        """
        account_id = self.get_account_id()
        if not account_id:
            logger.error("Cannot close sandbox order: no account ID")
            return None

        ps_occ = build_occ_symbol(ticker, expiration, put_short, "P")
        pl_occ = build_occ_symbol(ticker, expiration, put_long, "P")
        cs_occ = build_occ_symbol(ticker, expiration, call_short, "C")
        cl_occ = build_occ_symbol(ticker, expiration, call_long, "C")

        order_data = {
            "class": "multileg",
            "symbol": ticker,
            "type": "market",
            "duration": "day",
            "option_symbol[0]": ps_occ,
            "side[0]": "buy_to_close",
            "quantity[0]": str(contracts),
            "option_symbol[1]": pl_occ,
            "side[1]": "sell_to_close",
            "quantity[1]": str(contracts),
            "option_symbol[2]": cs_occ,
            "side[2]": "buy_to_close",
            "quantity[2]": str(contracts),
            "option_symbol[3]": cl_occ,
            "side[3]": "sell_to_close",
            "quantity[3]": str(contracts),
        }
        if tag:
            order_data["tag"] = tag[:255]

        result = self._post(f"/accounts/{account_id}/orders", data=order_data)
        if not result:
            logger.error(f"Sandbox IC close order failed for {ticker} {expiration}")
            return None

        order = result.get("order", {})
        order_id = order.get("id")
        status = order.get("status", "unknown")

        logger.info(
            f"SANDBOX IC CLOSE: {ticker} {expiration} "
            f"{put_long}/{put_short}P-{call_short}/{call_long}C "
            f"x{contracts} @ ${close_price:.2f} → order_id={order_id} [{status}]"
        )
        return {"order_id": order_id, "status": status}

    def get_order_fill_price(self, order_id: int) -> Optional[float]:
        """
        Query a sandbox order and return the average fill price.

        Tries up to 3 times with 1-second delay between attempts,
        because sandbox market orders may take a moment to fill.

        Returns the net credit received (positive) or None if not filled.
        """
        import time as _time

        account_id = self.get_account_id()
        if not account_id:
            logger.warning("Cannot get fill price: no account ID")
            return None

        for attempt in range(3):
            data = self._get(f"/accounts/{account_id}/orders/{order_id}")
            if not data:
                _time.sleep(1)
                continue

            order = data.get("order", {})
            status = order.get("status", "")

            if status == "filled":
                # For multileg orders, avg_fill_price is on the order level
                avg_fill = order.get("avg_fill_price")
                if avg_fill is not None:
                    return abs(float(avg_fill))

                # Fallback: calculate from leg fills
                legs = order.get("leg", [])
                if isinstance(legs, dict):
                    legs = [legs]
                if legs:
                    total = 0.0
                    for leg in legs:
                        side = leg.get("side", "")
                        fill = float(leg.get("avg_fill_price") or 0)
                        if "sell" in side:
                            total += fill  # credit
                        else:
                            total -= fill  # debit
                    return abs(total) if total != 0 else None

            if status in ("pending", "open", "partially_filled"):
                _time.sleep(1)
                continue

            # rejected, canceled, expired — no fill
            logger.warning(f"Sandbox order {order_id} status={status}, no fill price")
            return None

        logger.warning(f"Sandbox order {order_id} not filled after 3 attempts")
        return None

    def get_sandbox_positions(self) -> Optional[List[Dict]]:
        """Get all open positions in the sandbox account."""
        account_id = self.get_account_id()
        if not account_id:
            return None
        data = self._get(f"/accounts/{account_id}/positions")
        if not data:
            return None
        positions = data.get("positions", {}).get("position", [])
        if isinstance(positions, dict):
            return [positions]
        return positions if positions else []

    def get_sandbox_orders(self) -> Optional[List[Dict]]:
        """Get recent orders in the sandbox account."""
        account_id = self.get_account_id()
        if not account_id:
            return None
        data = self._get(f"/accounts/{account_id}/orders")
        if not data:
            return None
        orders = data.get("orders", {}).get("order", [])
        if isinstance(orders, dict):
            return [orders]
        return orders if orders else []
