"""Live ChainProvider — wraps the existing Tradier helpers in routes.py.

Used by the production scanner. Tests use a FakeChainProvider injected
directly, never this module.
"""
from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from typing import Any

import httpx

logger = logging.getLogger("spreadworks.bots.chain")

TRADIER_BASE = "https://api.tradier.com/v1"
TRADIER_TOKEN = os.getenv("TRADIER_TOKEN", "")
# AlphaGEX backend that serves the WATCHTOWER gamma snapshot (per-expiration
# pin / magnets / walls). Same default as backend/routes.py.
ALPHAGEX_BASE_URL = os.getenv("ALPHAGEX_BASE_URL", "http://localhost:8000")


def _headers() -> dict:
    return {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}


class LiveTradierChainProvider:
    """Synchronous Tradier chain fetcher.

    Scanner runs in a thread (via asyncio.to_thread) so blocking httpx is OK.
    """

    def __init__(self):
        self._client = httpx.Client(timeout=10.0)

    def get_chain(self, *, ticker: str, dte: int, today: date) -> dict | None:
        target = today + timedelta(days=dte)
        # Tradier returns the next available expiration on or after `target`
        exp = self._nearest_expiration_on_or_after(ticker, target)
        if exp is None:
            return None
        chain_resp = self._client.get(
            f"{TRADIER_BASE}/markets/options/chains",
            params={"symbol": ticker, "expiration": exp, "greeks": "true"},
            headers=_headers(),
        )
        if chain_resp.status_code != 200:
            logger.warning(f"chain fetch failed {chain_resp.status_code}")
            return None
        data = chain_resp.json().get("options", {}).get("option", []) or []
        if ticker == "SPX":
            # SPX dailies trade under the SPXW root (PM-settled). On monthly
            # 3rd Fridays Tradier returns BOTH roots for the expiration — the
            # AM-settled SPX options stop trading at the open, so quoting or
            # exiting against them intraday is wrong. Keep SPXW only whenever
            # it's present; _occ() builds SPXW symbols to match.
            spxw = [o for o in data if str(o.get("symbol", "")).startswith("SPXW")]
            if spxw:
                data = spxw
        spot = self._spot(ticker)
        if spot is None:
            return None
        atm_straddle = self._atm_straddle_mid(data, spot)
        vix = self._spot("VIX") or 0
        iv_atm = self._atm_iv(data, spot)
        return {
            "spot": spot, "vix": vix, "atm_straddle_mid": atm_straddle,
            "iv_atm": iv_atm, "expiration": exp, "ticker": ticker,
            "options": [
                {"strike": o["strike"], "type": o["option_type"],
                 "bid": o.get("bid") or 0, "ask": o.get("ask") or 0}
                for o in data
            ],
            # Per-expiration GEX structure (pin / magnets / walls / regime).
            # Resolved for THIS expiration so the gamma structure matches the
            # DTE being traded. Empty dict on any failure — strategies fall
            # back gracefully (e.g. butterfly bodies on spot).
            "gex": self._fetch_gex(ticker, exp),
        }

    def _fetch_gex(self, ticker: str, expiration: str) -> dict:
        """Fetch the WATCHTOWER gamma snapshot for `expiration` and distil it
        to the fields the bot strategies consume. Resolving by expiration is
        what makes the pin DTE-specific — the gamma structure differs every
        day and across expirations. Returns {} on any failure so the scanner
        never breaks just because GEX is briefly unavailable."""
        try:
            resp = self._client.get(
                f"{ALPHAGEX_BASE_URL}/api/watchtower/gamma",
                params={"symbol": ticker, "expiration": expiration},
                timeout=5.0,
            )
            if resp.status_code != 200:
                logger.warning(f"gex fetch failed {resp.status_code} for {ticker} {expiration}")
                return {}
            d = resp.json().get("data", {}) or {}
            ms = d.get("market_structure", {}) or {}
            fp = ms.get("flip_point")
            flip = fp.get("current") if isinstance(fp, dict) else fp
            gw = ms.get("gamma_walls", {}) or {}
            magnets = d.get("magnets") or []
            pin = d.get("likely_pin")
            # Diagnostic: butterfly bodies center on these magnets/pin. If both
            # are missing the body silently falls back to spot — log it so a
            # bot "opening at spot" is traceable to absent GEX vs. a code bug.
            if not magnets and pin is None:
                logger.warning(
                    f"gex has no magnets and no pin for {ticker} {expiration} "
                    f"-> butterfly body will fall back to SPOT"
                )
            else:
                logger.info(
                    f"gex for {ticker} {expiration}: magnets={len(magnets)} "
                    f"pin={pin} flip={flip}"
                )
            return {
                "pin_strike": pin,
                "pin_probability": d.get("pin_probability"),
                "magnets": magnets,
                "flip_point": flip,
                "call_wall": gw.get("call_wall") if isinstance(gw, dict) else None,
                "put_wall": gw.get("put_wall") if isinstance(gw, dict) else None,
                "gamma_regime": d.get("gamma_regime") or ms.get("gamma_regime"),
            }
        except Exception as e:  # network / parse — never fatal for a scan
            logger.warning(f"gex fetch error for {ticker} {expiration}: {e}")
            return {}

    def get_leg_mids(self, *, ticker: str, legs: list[dict[str, Any]]) -> list[float | None]:
        # Build OCC symbols and batch-fetch quotes
        symbols = [self._occ(ticker, leg) for leg in legs]
        resp = self._client.get(
            f"{TRADIER_BASE}/markets/quotes",
            params={"symbols": ",".join(symbols), "greeks": "false"},
            headers=_headers(),
        )
        if resp.status_code != 200:
            raise RuntimeError(f"quote fetch failed: {resp.status_code}")
        quotes = resp.json().get("quotes", {}).get("quote", []) or []
        if isinstance(quotes, dict):
            quotes = [quotes]
        by_sym = {q["symbol"]: q for q in quotes}
        out: list[float | None] = []
        for sym in symbols:
            q = by_sym.get(sym)
            if q is None:
                # Symbol missing from the response entirely. Treating it as a
                # $0.00 mid is what marked multi-leg debit combos NEGATIVE and
                # tripped phantom SLs (2026-07-06..08 SPLASH/SURGE losses).
                # Emit None; the scanner skips PT/SL on a stale mark.
                logger.warning(f"leg quote missing for {sym} — mid unavailable")
                out.append(None)
                continue
            bid = float(q.get("bid") or 0); ask = float(q.get("ask") or 0)
            out.append((bid + ask) / 2.0)
        return out

    def get_daily_history(self, *, ticker: str, days: int) -> list[dict[str, Any]]:
        """Daily OHLC bars for the last `days` calendar days (Tradier history).

        Returns a list of {date, open, high, low, close} ascending by date.
        Empty list on any failure — the dip detector treats that as
        insufficient_history and simply skips the ticker.
        """
        from datetime import date as _date, timedelta as _td
        end = _date.today()
        start = end - _td(days=days)
        try:
            resp = self._client.get(
                f"{TRADIER_BASE}/markets/history",
                params={"symbol": ticker, "interval": "daily",
                        "start": start.isoformat(), "end": end.isoformat()},
                headers=_headers(),
            )
            if resp.status_code != 200:
                logger.warning(f"history fetch failed {resp.status_code} for {ticker}")
                return []
            days_node = (resp.json().get("history") or {}).get("day", []) or []
            if isinstance(days_node, dict):
                days_node = [days_node]
            out = [
                {"date": d["date"], "open": d.get("open"), "high": d.get("high"),
                 "low": d.get("low"), "close": d.get("close")}
                for d in days_node if d.get("date")
            ]
            out.sort(key=lambda b: str(b["date"]))
            return out
        except Exception as e:
            logger.warning(f"history fetch error for {ticker}: {e}")
            return []

    # ---- helpers ----
    def _nearest_expiration_on_or_after(self, ticker: str, target: date) -> str | None:
        resp = self._client.get(
            f"{TRADIER_BASE}/markets/options/expirations",
            params={"symbol": ticker, "includeAllRoots": "true"},
            headers=_headers(),
        )
        if resp.status_code != 200: return None
        dates = resp.json().get("expirations", {}).get("date", []) or []
        if isinstance(dates, str): dates = [dates]
        for d in dates:
            if d >= target.isoformat():
                return d
        return None

    def _spot(self, ticker: str) -> float | None:
        sym = "VIX" if ticker == "VIX" else ticker
        resp = self._client.get(
            f"{TRADIER_BASE}/markets/quotes",
            params={"symbols": sym}, headers=_headers(),
        )
        if resp.status_code != 200: return None
        q = resp.json().get("quotes", {}).get("quote", {}) or {}
        if isinstance(q, list): q = q[0] if q else {}
        return float(q.get("last") or 0) or None

    def _atm_straddle_mid(self, opts: list[dict], spot: float) -> float:
        if not opts: return 0.0
        strikes = sorted({o["strike"] for o in opts})
        atm = min(strikes, key=lambda s: abs(float(s) - spot))
        call = next((o for o in opts if o["strike"] == atm and o["option_type"] == "call"), None)
        put = next((o for o in opts if o["strike"] == atm and o["option_type"] == "put"), None)
        if not call or not put: return 0.0
        cm = (float(call.get("bid") or 0) + float(call.get("ask") or 0)) / 2
        pm = (float(put.get("bid") or 0) + float(put.get("ask") or 0)) / 2
        return round(cm + pm, 4)

    def _atm_iv(self, opts: list[dict], spot: float) -> float:
        """Resolve ATM IV with a fallback ladder.

        Back-month chains at the open often have no mid_iv on the exact ATM
        call (no quote yet). Without a fallback the bot's vega-edge filter
        reads back_iv=0 and blocks every entry for the first hours of the
        session. Ladder: ATM call → ATM put → ±5 strikes (call then put).
        For each candidate try mid_iv, smv_vol, ask_iv, bid_iv — same set
        the `/api/spreadworks/chain` route uses.
        """
        if not opts: return 0.0
        strikes = sorted({float(o["strike"]) for o in opts})
        if not strikes: return 0.0
        atm = min(strikes, key=lambda s: abs(s - spot))
        atm_idx = strikes.index(atm)
        # Walk outward from ATM: 0, +1, -1, +2, -2, ...
        order = [atm_idx]
        for off in range(1, 6):
            for d in (off, -off):
                j = atm_idx + d
                if 0 <= j < len(strikes):
                    order.append(j)
        by_strike: dict[float, dict[str, dict]] = {}
        for o in opts:
            s = float(o["strike"])
            by_strike.setdefault(s, {})[o["option_type"]] = o
        def _read(o: dict | None) -> float:
            if not o: return 0.0
            g = o.get("greeks") or {}
            for k in ("mid_iv", "smv_vol", "ask_iv", "bid_iv"):
                v = g.get(k)
                if v: return float(v)
            return 0.0
        for j in order:
            s = strikes[j]
            row = by_strike.get(s, {})
            iv = _read(row.get("call")) or _read(row.get("put"))
            if iv: return iv
        return 0.0

    def _occ(self, ticker: str, leg: dict) -> str:
        # OCC format: ROOT + YYMMDD + C/P + Strike*1000 (8 digits)
        # Example: SPY260520C00500000 = SPY, 2026-05-20, Call, $500.00
        # SPX dailies/weeklies trade under the SPXW root (PM-settled, the side
        # we trade); building "SPX..." symbols would find no quote for them —
        # which the scanner would then treat as a stale mark every scan.
        root = "SPXW" if ticker == "SPX" else ticker
        d = date.fromisoformat(leg["expiration"])
        yymmdd = d.strftime("%y%m%d")
        cp = "C" if leg["type"] == "call" else "P"
        strike_milli = int(round(float(leg["strike"]) * 1000))
        return f"{root}{yymmdd}{cp}{strike_milli:08d}"


def build_live_chain_provider() -> LiveTradierChainProvider:
    return LiveTradierChainProvider()
