"""
Claude-powered "Signal Brief" generator for AGAPE perpetual bots.

Reads the current crypto market snapshot for a ticker and returns a 3-4
sentence plain-English explanation of what the bot is seeing — funding
regime, L/S positioning, OI levels, GEX (if available), and what the
combined signal/confidence means.

Replaces dashboard reads like "L/S=2.29 funding=MILD_LONG_BIAS" with:
  "70% of accounts are long XRP — extremely crowded. Funding is mildly
   positive, meaning longs are still paying. The bot is leaning short
   with low confidence; this is a contrarian play, not a momentum trade."

Implementation notes:
  - Uses claude-sonnet-4-6 (good cost/quality fit for short briefs).
  - System prompt is cached (cache_control: ephemeral) - same prompt
    for every brief, only user message varies.
  - 5-minute in-memory cache per ticker, matching chart-data refresh.
  - Returns None on any failure - caller shows raw snapshot fallback.
"""

import json
import logging
import os
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Cost-effective model for short briefs. Bump to opus if quality matters.
_BRIEF_MODEL = os.getenv("PERP_BRIEF_MODEL", "claude-sonnet-4-6")
_BRIEF_MAX_TOKENS = 400

# In-memory cache per ticker. Briefs are now generated on a daily schedule
# (3:30 PM CT, see ai/perp_brief_daily_runner.py) and persisted to
# `agape_perp_signal_briefs`; routes read from that table. This in-process
# cache only protects the legacy on-demand call path against runaway loops
# — the 24h TTL means even if a caller bypasses the DB read, we won't fire
# more than once per ticker per day.
_CACHE: Dict[str, Dict] = {}
_CACHE_TIME: Dict[str, float] = {}
_CACHE_TTL = 86400

_SYSTEM_PROMPT = """You are an expert crypto perpetual futures analyst writing a short signal brief for a trading bot's dashboard. Your audience is the bot operator who wants plain-English context for what the bot is seeing right now.

You will receive a market snapshot for one perpetual ticker (BTC, ETH, XRP, DOGE, or SHIB). The snapshot contains:
- spot_price: current price
- funding_rate.rate: current funding rate (positive = longs pay shorts)
- funding_regime: regime classification (BALANCED, OVERLEVERAGED_LONG, etc.)
- ls_ratio: object with ratio (longs/shorts), long_pct, short_pct
- oi_snapshot.total_usd: aggregated open interest in USD across exchanges
- crypto_gex: gamma exposure regime (POSITIVE/NEGATIVE) — only present for BTC/ETH
- combined_signal: bot's decision (LONG/SHORT/RANGE_BOUND/WAIT)
- combined_confidence: HIGH/MEDIUM/LOW

Write a brief in this exact structure:

**[TICKER] — Leaning [SIGNAL] ([Confidence] confidence)**

[2-3 sentences explaining what the data means. Translate jargon: "L/S=2.29" becomes "70% of accounts are long". Always state WHAT the data shows, then WHY it matters for direction. If GEX is missing for the ticker, mention the bot has less conviction without options data.]

[1 sentence: what the bot will do given this signal, and one risk to watch.]

Keep it under 90 words total. Be direct. No filler. No disclaimers about "not financial advice"."""


def get_signal_brief(snapshot_dict: Dict) -> Optional[Dict]:
    """Generate a Claude signal brief for one perp ticker.

    Args:
        snapshot_dict: serialized CryptoMarketSnapshot fields (the same
            payload returned by /api/agape-{ticker}-perp/snapshot)

    Returns:
        {"brief": "...markdown text...", "model": str, "fetched_at": ms}
        or None if Claude is unavailable / call failed.
    """
    ticker = (snapshot_dict.get("symbol") or "UNKNOWN").upper()
    now = time.time()

    cached = _CACHE.get(ticker)
    cached_time = _CACHE_TIME.get(ticker, 0)
    if cached and (now - cached_time) < _CACHE_TTL:
        return {**cached, "cache_age_seconds": int(now - cached_time)}

    api_key = os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.debug("perp_signal_brief: no Anthropic API key")
        return None

    try:
        import anthropic
    except ImportError:
        logger.warning("perp_signal_brief: anthropic SDK not installed")
        return None

    # Trim snapshot to the fields that actually matter for the brief.
    # Keeping the user message small reduces token cost and gives Claude
    # less to misinterpret.
    trimmed = {
        "symbol": snapshot_dict.get("symbol"),
        "spot_price": snapshot_dict.get("spot_price"),
        "funding_rate": snapshot_dict.get("funding", {}).get("rate"),
        "funding_regime": snapshot_dict.get("funding", {}).get("regime"),
        "funding_annualized_pct": snapshot_dict.get("funding", {}).get("annualized"),
        "ls_ratio": snapshot_dict.get("long_short", {}).get("ratio"),
        "ls_long_pct": snapshot_dict.get("long_short", {}).get("long_pct"),
        "ls_short_pct": snapshot_dict.get("long_short", {}).get("short_pct"),
        "ls_bias": snapshot_dict.get("long_short", {}).get("bias"),
        "oi_total_usd": snapshot_dict.get("open_interest", {}).get("total_usd"),
        "gex_regime": snapshot_dict.get("crypto_gex", {}).get("regime"),
        "gex_net": snapshot_dict.get("crypto_gex", {}).get("net_gex"),
        "max_pain": snapshot_dict.get("crypto_gex", {}).get("flip_point"),
        "combined_signal": snapshot_dict.get("signals", {}).get("combined_signal"),
        "combined_confidence": snapshot_dict.get("signals", {}).get("combined_confidence"),
        "directional_bias": snapshot_dict.get("signals", {}).get("directional_bias"),
        "volatility_regime": snapshot_dict.get("signals", {}).get("volatility_regime"),
    }

    user_message = (
        f"Generate the signal brief for {ticker} from this snapshot:\n\n"
        f"```json\n{json.dumps(trimmed, indent=2, default=str)}\n```"
    )

    try:
        # 15s timeout: Anthropic SDK defaults to 600s, which would tie up a
        # uvicorn worker for 10 minutes if the call hangs. Brief is best-effort —
        # falling back to the raw snapshot is fine.
        client = anthropic.Anthropic(api_key=api_key, timeout=15.0)
        response = client.messages.create(
            model=_BRIEF_MODEL,
            max_tokens=_BRIEF_MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    # Cache the system prompt across briefs - it never changes
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_message}],
        )

        text_blocks = [b.text for b in response.content if getattr(b, "type", "") == "text"]
        brief_text = "\n".join(text_blocks).strip()
        if not brief_text:
            logger.warning(f"perp_signal_brief: empty response for {ticker}")
            return None

        usage = getattr(response, "usage", None)
        cache_read = getattr(usage, "cache_read_input_tokens", 0) if usage else 0
        cache_write = getattr(usage, "cache_creation_input_tokens", 0) if usage else 0

        payload = {
            "ticker": ticker,
            "brief": brief_text,
            "model": _BRIEF_MODEL,
            "fetched_at": int(now * 1000),
            "tokens": {
                "input": getattr(usage, "input_tokens", 0) if usage else 0,
                "output": getattr(usage, "output_tokens", 0) if usage else 0,
                "cache_read": cache_read,
                "cache_write": cache_write,
            },
        }

        _CACHE[ticker] = payload
        _CACHE_TIME[ticker] = now
        return {**payload, "cache_age_seconds": 0}

    except Exception as e:
        logger.error(f"perp_signal_brief: Claude call failed for {ticker}: {e}")
        return None
