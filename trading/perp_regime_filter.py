"""
Per-coin signal filters derived from backtest of 729 closed perp trades.

Each rule below corresponds to a specific (coin, signal_direction,
funding_regime) bucket that lost money in historical scan_activity
joined to closed positions. Filters are surgical — only the buckets
with both negative total PnL and >=10 trades are blocked. Profitable
buckets are untouched.

Backtest evidence (data range up to 2026-05-03, all 5 perps):
  BTC LONG  in MILD_SHORT_BIAS funding   →  20 trades, 50% WR, -$2,833
  BTC SHORT in UNKNOWN funding           →  13 trades,  7.7% WR, -$250
  BTC SHORT in BALANCED funding          →  18 trades, 50% WR, -$1,134
  DOGE SHORT in BALANCED funding         →  45 trades, 53% WR, -$616
  XRP SHORT in any funding               →  41 trades, 41.5% WR, -$1,240

Total expected savings vs baseline: ~$6,073 across the same trade
count (+18% of historical PnL). Profitable patterns left untouched:
  BTC LONG  in BALANCED                  →  74 trades, 68.9% WR, +$28,118
  ETH LONG  in BALANCED                  →  96 trades, 62.5% WR, +$7,640
  ETH SHORT in BALANCED                  →  21 trades, 71.4% WR, +$2,444
  DOGE SHORT in MILD_LONG_BIAS           →  36 trades, 72.2% WR, +$342

Filters are first-pass conservative; revisit after another N trades to
re-validate (or relax if a regime turns favorable on more data).
"""

import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


# (bot_name, signal_action, funding_regime_match) → reason string.
# funding_regime_match=None means "any regime".
_BLOCKED_PATTERNS: dict = {
    # BTC
    ("AGAPE_BTC_PERP",  "LONG",  "MILD_SHORT_BIAS"): "BTC_LONG_in_MILD_SHORT_BIAS_loses",
    ("AGAPE_BTC_PERP",  "SHORT", "UNKNOWN"):         "BTC_SHORT_in_UNKNOWN_funding_loses",
    ("AGAPE_BTC_PERP",  "SHORT", "BALANCED"):        "BTC_SHORT_in_BALANCED_loses",
    # DOGE
    ("AGAPE_DOGE_PERP", "SHORT", "BALANCED"):        "DOGE_SHORT_in_BALANCED_loses",
    # XRP — all SHORT regimes are losers in our sample
    ("AGAPE_XRP_PERP",  "SHORT", None):              "XRP_SHORT_no_edge_in_any_regime",
}


def is_signal_blocked(
    bot_name: str,
    signal_action: str,
    funding_regime: Optional[str],
) -> Tuple[bool, str]:
    """Check if a generated signal should be skipped per the backtest rules.

    Returns (blocked, reason). Reason is empty when not blocked.
    Fails open: unknown bot or missing inputs → not blocked.
    """
    if not bot_name or not signal_action:
        return False, ""
    action = signal_action.upper()

    # Exact-regime match
    key_exact = (bot_name, action, (funding_regime or "").upper() if funding_regime else None)
    if key_exact in _BLOCKED_PATTERNS:
        return True, _BLOCKED_PATTERNS[key_exact]

    # Wildcard regime (any) match
    key_any = (bot_name, action, None)
    if key_any in _BLOCKED_PATTERNS:
        return True, _BLOCKED_PATTERNS[key_any]

    return False, ""
