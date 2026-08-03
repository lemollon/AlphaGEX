"""
Kalshi Trade API client (REST) with RSA-PSS request signing.

Used by ZEPHYR (ASAHEL), the live-sports scalper. Kalshi authenticates each
request with an API key ID + an RSA private-key signature over
`timestamp + METHOD + path` (NOT a bearer token).

Credentials (env):
  KALSHI_API_KEY_ID        - the key id (UUID)
  KALSHI_PRIVATE_KEY_PATH  - path to the RSA private key (PEM), OR
  KALSHI_PRIVATE_KEY_PEM   - the PEM contents inline
  KALSHI_API_BASE          - override base URL (default: prod)

Graceful fallback: if creds or the `cryptography` lib are missing, the client
constructs in an unauthenticated state. Public reads (markets/orderbook) still
work; any order call raises a clear error instead of silently no-op'ing.
"""

from __future__ import annotations

import base64
import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    _CRYPTO_OK = True
except BaseException:  # noqa: BLE001 - a broken/native dep (pyo3 PanicException) must
    # not crash import; degrade to read-only instead of taking the whole client down.
    _CRYPTO_OK = False


DEFAULT_BASE = "https://api.elections.kalshi.com/trade-api/v2"


class KalshiAuthError(RuntimeError):
    pass


class KalshiClient:
    def __init__(
        self,
        api_key_id: Optional[str] = None,
        private_key_pem: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 4.0,
    ):
        self.base_url = (base_url or os.getenv("KALSHI_API_BASE") or DEFAULT_BASE).rstrip("/")
        self.timeout = timeout
        self.api_key_id = api_key_id or os.getenv("KALSHI_API_KEY_ID", "")
        self._private_key = self._load_private_key(private_key_pem)
        self._session = requests.Session() if requests is not None else None

    # ----------------------------------------------------------------- auth
    def _load_private_key(self, inline_pem: Optional[str]):
        if not _CRYPTO_OK:
            logger.warning("cryptography unavailable - Kalshi client is read-only")
            return None
        pem = inline_pem or os.getenv("KALSHI_PRIVATE_KEY_PEM")
        if not pem:
            path = os.getenv("KALSHI_PRIVATE_KEY_PATH")
            if path and os.path.exists(path):
                with open(path, "rb") as f:
                    pem = f.read()
        if not pem:
            logger.info("No Kalshi private key configured - read-only mode")
            return None
        if isinstance(pem, str):
            pem = pem.encode()
        try:
            return serialization.load_pem_private_key(pem, password=None)
        except Exception as e:  # pragma: no cover
            logger.error("Failed to load Kalshi private key: %s", e)
            return None

    @property
    def can_trade(self) -> bool:
        return bool(self.api_key_id and self._private_key is not None and self._session)

    def _sign(self, ts_ms: str, method: str, path: str) -> str:
        msg = (ts_ms + method.upper() + path).encode()
        sig = self._private_key.sign(
            msg,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
        return base64.b64encode(sig).decode()

    def _headers(self, method: str, path: str) -> Dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key_id and self._private_key is not None:
            ts = str(int(time.time() * 1000))
            # path used for signing excludes the query string
            sign_path = path.split("?")[0]
            headers.update({
                "KALSHI-ACCESS-KEY": self.api_key_id,
                "KALSHI-ACCESS-TIMESTAMP": ts,
                "KALSHI-ACCESS-SIGNATURE": self._sign(ts, method, sign_path),
            })
        return headers

    # -------------------------------------------------------------- request
    def _request(self, method: str, path: str, *, params=None, json=None, auth_required=False):
        if self._session is None:
            raise KalshiAuthError("requests not installed")
        if auth_required and not self.can_trade:
            raise KalshiAuthError(
                "Kalshi trading credentials not configured (need KALSHI_API_KEY_ID + private key)"
            )
        url = self.base_url + path
        resp = self._session.request(
            method, url, params=params, json=json,
            headers=self._headers(method, path), timeout=self.timeout,
        )
        if resp.status_code >= 400:
            raise KalshiAuthError(f"Kalshi {method} {path} -> {resp.status_code}: {resp.text[:300]}")
        return resp.json() if resp.content else {}

    # ----------------------------------------------------------- public reads
    def get_events(self, series_ticker: str, status: str = "open", limit: int = 200) -> List[Dict[str, Any]]:
        data = self._request("GET", "/events", params={
            "series_ticker": series_ticker, "status": status, "limit": limit,
        })
        return data.get("events", [])

    def get_markets(self, event_ticker: Optional[str] = None, series_ticker: Optional[str] = None,
                    status: str = "open", limit: int = 200) -> List[Dict[str, Any]]:
        params = {"status": status, "limit": limit}
        if event_ticker:
            params["event_ticker"] = event_ticker
        if series_ticker:
            params["series_ticker"] = series_ticker
        data = self._request("GET", "/markets", params=params)
        return data.get("markets", [])

    def get_market(self, ticker: str) -> Dict[str, Any]:
        return self._request("GET", f"/markets/{ticker}").get("market", {})

    def get_orderbook(self, ticker: str, depth: int = 5) -> Dict[str, Any]:
        return self._request("GET", f"/markets/{ticker}/orderbook", params={"depth": depth}).get("orderbook", {})

    # ------------------------------------------------------------ authed ops
    def get_balance(self) -> Dict[str, Any]:
        return self._request("GET", "/portfolio/balance", auth_required=True)

    def get_positions(self) -> List[Dict[str, Any]]:
        return self._request("GET", "/portfolio/positions", auth_required=True).get("market_positions", [])

    def place_order(self, *, ticker: str, side: str, action: str, count: int,
                    order_type: str = "limit", price_cents: Optional[int] = None,
                    client_order_id: Optional[str] = None,
                    time_in_force: str = "fill_or_kill" ) -> Dict[str, Any]:
        """Place an order. side='yes'|'no', action='buy'|'sell'.

        For maker scalps use order_type='limit' with a resting time_in_force;
        for taker exits use a marketable limit / fill_or_kill.
        """
        body: Dict[str, Any] = {
            "ticker": ticker, "side": side, "action": action,
            "count": int(count), "type": order_type,
            "client_order_id": client_order_id or f"zephyr-{int(time.time()*1000)}",
        }
        if order_type == "limit" and price_cents is not None:
            # Kalshi expects the price on the chosen side, in cents.
            key = "yes_price" if side == "yes" else "no_price"
            body[key] = int(round(price_cents))
        if time_in_force:
            body["time_in_force"] = time_in_force
        return self._request("POST", "/portfolio/orders", json=body, auth_required=True)

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        return self._request("DELETE", f"/portfolio/orders/{order_id}", auth_required=True)


def create_kalshi_client() -> KalshiClient:
    return KalshiClient()
