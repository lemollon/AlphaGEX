"""HELIOS — GEX polling client for /api/gex/SPY.

Wraps the production GEX endpoint with:
  - Parse -> GexSnapshot dataclass
  - 90s staleness gate (raises GexStaleError)
  - Single retry on 5xx with backoff
  - 1-day expected-move computation from vix + spot

No external state. All I/O is via the injectable `http` object so this is
testable without a network.
"""
from __future__ import annotations

import datetime as dt
import logging
import math
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR = 252.0
SQRT_INV_TRADING_DAYS = math.sqrt(1.0 / TRADING_DAYS_PER_YEAR)


class GexStaleError(RuntimeError):
    """Raised when the upstream snapshot's timestamp is older than the staleness threshold."""


@dataclass(frozen=True)
class GexSnapshot:
    symbol: str
    spot: float
    net_gex: float
    flip_point: float
    call_wall: float
    put_wall: float
    vix: float
    regime: str
    sigma_1d_band_width: float  # 1-day 1-sigma move in dollars
    snapshot_at: dt.datetime    # tz-aware UTC


class GexClient:
    """Polling client. Inject `http` for tests."""

    def __init__(
        self,
        *,
        base_url: str,
        http=None,
        stale_max_seconds: int = 90,
        retry_backoff: float = 5.0,
        timeout: float = 5.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.stale_max_seconds = stale_max_seconds
        self.retry_backoff = retry_backoff
        self.timeout = timeout
        if http is None:
            import requests
            self.http = requests
        else:
            self.http = http

    def get_spy(self, *, now: Optional[dt.datetime] = None) -> GexSnapshot:
        url = f"{self.base_url}/api/gex/SPY"
        resp = self._get_with_retry(url)
        payload = resp.json()
        data = payload.get("data") or {}

        ts_raw = data.get("timestamp")
        snapshot_at = _parse_iso_utc(ts_raw) if ts_raw else (now or dt.datetime.now(dt.timezone.utc))
        now = now or dt.datetime.now(dt.timezone.utc)
        age_sec = (now - snapshot_at).total_seconds()
        if age_sec > self.stale_max_seconds:
            raise GexStaleError(f"gex snapshot age={age_sec:.1f}s > {self.stale_max_seconds}s")

        spot = float(data.get("spot_price") or 0.0)
        vix = float(data.get("vix") or 0.0)
        sigma_1d = spot * (vix / 100.0) * SQRT_INV_TRADING_DAYS if spot > 0 and vix > 0 else 0.0

        return GexSnapshot(
            symbol=str(data.get("symbol", "SPY")),
            spot=spot,
            net_gex=float(data.get("net_gex") or 0.0),
            flip_point=float(data.get("flip_point") or 0.0),
            call_wall=float(data.get("call_wall") or 0.0),
            put_wall=float(data.get("put_wall") or 0.0),
            vix=vix,
            regime=str(data.get("regime") or "NEUTRAL"),
            sigma_1d_band_width=sigma_1d,
            snapshot_at=snapshot_at,
        )

    def _get_with_retry(self, url):
        try:
            resp = self.http.get(url, timeout=self.timeout)
            resp.raise_for_status()
            return resp
        except Exception as e1:
            logger.warning("gex_client first-try failed (%s), retrying once", e1)
            if self.retry_backoff > 0:
                time.sleep(self.retry_backoff)
            resp = self.http.get(url, timeout=self.timeout)
            resp.raise_for_status()
            return resp


def _parse_iso_utc(s: str) -> dt.datetime:
    s = s.replace("Z", "+00:00")
    t = dt.datetime.fromisoformat(s)
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return t
