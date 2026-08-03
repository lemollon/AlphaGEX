"""
ZEPHYR Fair Value - the scalp ANCHOR (this is ZEPHYR's decision authority).

Pluggable provider interface. Two adapters:
  - EspnWinProbProvider  : FREE. ESPN in-game win probability. Good enough to
                           build the pipeline and MEASURE Kalshi lag, NOT a
                           production alpha source (slower/softer than a book).
  - OddsApiProvider      : production upgrade (The-Odds-API / aggregated books,
                           incl. Pinnacle). Strips vig -> fair prob. Paid.

The vig-stripping math is pure and unit-tested. Network fetches degrade
gracefully (return None) so a feed outage can never crash the trader.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional

from .models import CENTRAL_TZ, FairValueQuote

logger = logging.getLogger(__name__)

try:
    import requests  # noqa
except Exception:  # pragma: no cover - requests is a base dep, fallback anyway
    requests = None


# ==============================================================================
# PURE MATH (testable, no I/O)
# ==============================================================================
def american_to_implied(odds: float) -> float:
    """American moneyline -> raw implied probability (still includes vig)."""
    if odds < 0:
        return (-odds) / ((-odds) + 100.0)
    return 100.0 / (odds + 100.0)


def strip_vig_two_way(p_home_raw: float, p_away_raw: float) -> float:
    """Remove the bookmaker margin from a two-way market.

    Returns the no-vig probability of the FIRST outcome (home/YES). Uses simple
    proportional normalization: p / (p_home + p_away).
    """
    total = p_home_raw + p_away_raw
    if total <= 0:
        return 0.5
    return p_home_raw / total


def fair_from_american(home_ml: float, away_ml: float) -> float:
    """Convenience: two American moneylines -> no-vig P(home)."""
    return strip_vig_two_way(
        american_to_implied(home_ml), american_to_implied(away_ml)
    )


# ==============================================================================
# PROVIDER INTERFACE
# ==============================================================================
class FairValueProvider(ABC):
    """A source of sharp 'fair value' probabilities for Kalshi markets."""

    name: str = "base"
    confidence: float = 0.5

    @abstractmethod
    def fair(self, market_id: str, **ctx) -> Optional[FairValueQuote]:
        """Return a FairValueQuote for one market, or None if unavailable."""
        raise NotImplementedError


class EspnWinProbProvider(FairValueProvider):
    """FREE in-game win probability from ESPN's public scoreboard API.

    Maps a Kalshi market to an ESPN event via `ctx['espn_event_id']` and
    `ctx['team']` (the team the YES side resolves on). This is a STAND-IN to
    prove the pipeline + measure lag; it is intentionally low confidence so the
    fee gate stays strict while we evaluate whether edge clears fees.
    """

    name = "espn"
    confidence = 0.30  # deliberately modest -> keeps the fee gate honest

    SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/{sport_path}/scoreboard"
    SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/{sport_path}/summary"

    SPORT_PATHS = {
        "MLB": "baseball/mlb",
        "NBA": "basketball/nba",
        "NFL": "football/nfl",
    }

    def __init__(self, timeout: float = 2.5):
        self.timeout = timeout

    def fair(self, market_id: str, **ctx) -> Optional[FairValueQuote]:
        if requests is None:
            return None
        sport = (ctx.get("sport") or "MLB").upper()
        event_id = ctx.get("espn_event_id")
        team_id = str(ctx.get("team_id") or "")
        if not event_id:
            return None
        sport_path = self.SPORT_PATHS.get(sport, self.SPORT_PATHS["MLB"])
        url = self.SUMMARY.format(sport_path=sport_path)
        try:
            r = requests.get(url, params={"event": event_id}, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            logger.debug("ESPN fair-value fetch failed for %s: %s", market_id, e)
            return None

        prob = self._extract_winprob(data, team_id)
        if prob is None:
            return None
        return FairValueQuote(
            market_id=market_id,
            fair_prob=max(0.01, min(0.99, prob)),
            source=self.name,
            ts=datetime.now(CENTRAL_TZ),
            confidence=self.confidence,
            raw={"espn_event_id": event_id, "team_id": team_id},
        )

    @staticmethod
    def _extract_winprob(summary: dict, team_id: str) -> Optional[float]:
        """Pull the latest win probability for team_id from an ESPN summary."""
        wp = summary.get("winprobability") or []
        if not wp:
            return None
        last = wp[-1]
        # ESPN reports homeWinPercentage; map to the requested team via header.
        home_pct = last.get("homeWinPercentage")
        if home_pct is None:
            return None
        header = summary.get("header", {})
        competitions = header.get("competitions", [{}])
        competitors = competitions[0].get("competitors", []) if competitions else []
        home_team_id = next(
            (c.get("id") for c in competitors if c.get("homeAway") == "home"), None
        )
        if team_id and home_team_id and team_id == str(home_team_id):
            return float(home_pct)
        if team_id and home_team_id and team_id != str(home_team_id):
            return 1.0 - float(home_pct)
        return float(home_pct)


class OddsApiProvider(FairValueProvider):
    """Production adapter: aggregated sportsbook odds (e.g. The-Odds-API).

    Reads `ODDS_API_KEY` from env. Strips vig from a sharp book (prefer
    Pinnacle when present) to produce a no-vig fair probability. Stubbed to
    return None when no key is configured so the bot runs on ESPN until you
    wire a paid feed.
    """

    name = "odds_api"
    confidence = 0.75

    def __init__(self, preferred_book: str = "pinnacle", timeout: float = 2.5):
        self.api_key = os.getenv("ODDS_API_KEY", "")
        self.preferred_book = preferred_book
        self.timeout = timeout

    def fair(self, market_id: str, **ctx) -> Optional[FairValueQuote]:
        if not self.api_key or requests is None:
            return None
        # Intentionally minimal: real implementation maps market_id -> event and
        # pulls h2h odds, preferring self.preferred_book. Left as the documented
        # production hook; ESPN provider carries P0/P1.
        logger.debug("OddsApiProvider configured but event mapping not wired for %s", market_id)
        return None


# ==============================================================================
# FACTORY
# ==============================================================================
def get_provider(name: str = "espn") -> FairValueProvider:
    name = (name or "espn").lower()
    if name == "odds_api":
        prov = OddsApiProvider()
        if not prov.api_key:
            logger.warning("ODDS_API_KEY not set - falling back to free ESPN provider")
            return EspnWinProbProvider()
        return prov
    return EspnWinProbProvider()
