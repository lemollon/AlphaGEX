"""
Bot Name Mapping - Greek to Biblical Display Names

Maps internal bot codenames (Greek mythology) to user-facing biblical display names.
This is the Python-side equivalent of frontend/src/lib/botDisplayNames.ts.

Internal names (Greek) are used in:
- API endpoints and route prefixes
- Database table names
- File/directory names
- Code references (classes, functions)

Display names (Biblical) are used in:
- API response labels
- Log messages shown to users
- GEXIS assistant references
- Notification text
"""

from typing import Optional


# =============================================================================
# TRADING BOT NAME MAPPING (Greek -> Biblical)
# =============================================================================

BOT_DISPLAY_NAMES: dict[str, str] = {
    # Bot Internal Name    -> Display Name
    "ARES":                 "FORTRESS",      # SPY Iron Condor - Psalm 18:2
    "ATHENA":               "SOLOMON",       # Directional Spreads - 1 Kings 4:29
    "TITAN":                "SAMSON",        # Aggressive SPX IC - Judges 16:28
    "PEGASUS":              "ANCHOR",        # SPX Weekly IC - Hebrews 6:19
    "ICARUS":               "GIDEON",        # Aggressive Directional - Judges 6:14
    "PHOENIX":              "LAZARUS",       # 0DTE Momentum - John 11:43-44
    "ATLAS":                "CORNERSTONE",   # SPX Wheel - Psalm 118:22
    "HERMES":               "SHEPHERD",      # Manual Wheel - Psalm 23:1-2
    "PROMETHEUS":           "JUBILEE",       # Box Spread + IC - Leviticus 25:10
    "HERACLES":             "VALOR",         # MES Futures Scalping - Joshua 1:9
    "AGAPE":                "AGAPE",         # ETH Micro Futures - 1 Cor 13:4,7
    "AGAPE_SPOT":           "AGAPE-SPOT",    # 24/7 Crypto Spot - 1 Cor 13:8
    "AGAPE_ETH_PERP":   "AGAPE-ETH-PERP",    # ETH Perpetual Contract
    "AGAPE_BTC_PERP":   "AGAPE-BTC-PERP",     # BTC Perpetual Contract
    "AGAPE_XRP_PERP":   "AGAPE-XRP-PERP",     # XRP Perpetual Contract
    "AGAPE_DOGE_PERP":  "AGAPE-DOGE-PERP",    # DOGE Perpetual Contract
    "AGAPE_SHIB_PERP":  "AGAPE-SHIB-PERP",    # SHIB Perpetual Contract
}

# Also accept the new names as keys (identity mapping)
for _display_name in list(BOT_DISPLAY_NAMES.values()):
    normalized = _display_name.replace("-", "_")
    if normalized not in BOT_DISPLAY_NAMES:
        BOT_DISPLAY_NAMES[normalized] = _display_name


# =============================================================================
# ADVISORY SYSTEM NAME MAPPING (Greek -> Biblical)
# =============================================================================

ADVISOR_DISPLAY_NAMES: dict[str, str] = {
    "ORACLE":               "PROPHET",       # ML Decision Maker - Amos 3:7
    "SAGE":                 "WISDOM",        # XGBoost Predictions - Proverbs 2:6
    "ARGUS":                "WATCHTOWER",    # 0DTE Gamma Viz - Isaiah 62:6
    "ORION":                "STARS",         # GEX ML Models - Psalm 147:4
    "GEXIS":                "COUNSELOR",     # AI Assistant - John 14:26
    "KRONOS":               "CHRONICLES",    # Backtester - Deuteronomy 32:7
    "HYPERION":             "GLORY",         # Weekly Gamma - Psalm 19:1
    "APOLLO":               "DISCERNMENT",   # ML Scanner - Philippians 1:9-10
    "PROVERBS":             "PROVERBS",      # Feedback Loop - Proverbs 1:1-2
    "NEXUS":                "COVENANT",      # Neural Network - Ezekiel 37:26
}


# =============================================================================
# REVERSE MAPPINGS (Biblical -> Greek)
# =============================================================================

DISPLAY_TO_INTERNAL: dict[str, str] = {v: k for k, v in BOT_DISPLAY_NAMES.items()
                                        if k == k.upper() and "_" not in k or k in (
                                            "AGAPE_SPOT", "ARES", "ATHENA", "TITAN",
                                            "PEGASUS", "ICARUS", "PHOENIX", "ATLAS",
                                            "HERMES", "PROMETHEUS", "HERACLES", "AGAPE",
                                            "AGAPE_ETH_PERP", "AGAPE_BTC_PERP",
                                            "AGAPE_XRP_PERP", "AGAPE_DOGE_PERP",
                                            "AGAPE_SHIB_PERP"
                                        )}

ADVISOR_DISPLAY_TO_INTERNAL: dict[str, str] = {v: k for k, v in ADVISOR_DISPLAY_NAMES.items()}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_bot_display_name(codename: str) -> str:
    """Get the biblical display name for a bot's internal codename.

    Args:
        codename: Internal bot name (e.g., "ARES", "ares", "fortress")

    Returns:
        Biblical display name, or the original codename if not found.
    """
    upper = codename.upper().replace("-", "_")
    return BOT_DISPLAY_NAMES.get(upper, codename)


def get_advisor_display_name(codename: str) -> str:
    """Get the biblical display name for an advisory system.

    Args:
        codename: Internal advisor name (e.g., "ORACLE", "SAGE")

    Returns:
        Biblical display name, or the original codename if not found.
    """
    return ADVISOR_DISPLAY_NAMES.get(codename.upper(), codename)


def get_internal_name(display_name: str) -> Optional[str]:
    """Get the internal Greek codename from a biblical display name.

    Args:
        display_name: Biblical name (e.g., "FORTRESS", "SOLOMON")

    Returns:
        Internal codename, or None if not found.
    """
    upper = display_name.upper().replace("-", "_")
    return DISPLAY_TO_INTERNAL.get(upper) or ADVISOR_DISPLAY_TO_INTERNAL.get(upper)


def is_known_bot(name: str) -> bool:
    """Check if a name (internal or display) is a known trading bot."""
    upper = name.upper().replace("-", "_")
    return upper in BOT_DISPLAY_NAMES


def is_known_advisor(name: str) -> bool:
    """Check if a name (internal or display) is a known advisory system."""
    upper = name.upper()
    return upper in ADVISOR_DISPLAY_NAMES
