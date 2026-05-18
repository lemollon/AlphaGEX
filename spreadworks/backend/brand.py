"""SpreadWorks brand helpers for Discord embeds.

Single source of truth for color palette + label / mono formatting so
all 13+ embeds in routes.py speak the same vocabulary as the React app.

Mirrors `frontend/src/index.css` @theme tokens and the brand book in
`SpreadWorks Design System/README.md`.
"""

# ── Color palette (Discord uses 0xRRGGBB ints) ────────────────────
# Mirrors the React @theme tokens 1:1. Use these instead of hardcoding
# legacy hex values like 0x00E676 / 0xFF1744 / 0x448AFF / 0xFFD600.
ACCENT = 0x3B82F6     # electric blue — primary, info, neutral embeds
SUCCESS = 0x22C55E    # PUT side / long / profit / bullish
DANGER = 0xEF4444     # CALL side / short / loss / bearish
WARNING = 0xEAB308    # GEX yellow — flip point, medium-impact event
MUTED = 0x4B5563      # disabled / pending / unavailable


def pnl_color(value: float | None, *, neutral: int = ACCENT) -> int:
    """Green if profit, red if loss, accent if zero / None."""
    if value is None or value == 0:
        return neutral
    return SUCCESS if value > 0 else DANGER


def impact_color(impact: str) -> int:
    """Economic event impact → brand color."""
    return {"HIGH": DANGER, "MEDIUM": WARNING, "LOW": ACCENT}.get(impact, MUTED)


# ── Typography helpers ────────────────────────────────────────────

def mono(value) -> str:
    """Wrap a value in Discord inline-code so it renders monospaced.
    Brand book: 'Everything monospaced' for numbers."""
    return f"`{value}`"


def signed_dollar(value: float | None, *, decimals: int = 2) -> str:
    """`+$1,234.50` / `-$1,234.50` / `--`. Sign-explicit per brand book."""
    if value is None:
        return "--"
    sign = "+" if value >= 0 else "-"
    return mono(f"{sign}${abs(value):,.{decimals}f}")


def dollar(value: float | None, *, decimals: int = 2) -> str:
    """`$1,234.50` / `--`. No sign — for prices, strikes, breakevens."""
    if value is None:
        return "--"
    return mono(f"${value:,.{decimals}f}")


def pct(value: float | None, *, decimals: int = 1, signed: bool = False) -> str:
    """`+1.4%` / `25.3%` / `--`."""
    if value is None:
        return "--"
    if signed:
        return mono(f"{value:+.{decimals}f}%")
    return mono(f"{value:.{decimals}f}%")


def field(name: str, value: str, *, inline: bool = True) -> dict:
    """Embed field with UPPERCASE label (brand book: 'METRIC LABELS:
    UPPERCASE letter-spaced')."""
    return {"name": name.upper(), "value": value, "inline": inline}


# ── Title / footer helpers ────────────────────────────────────────

def title(*parts: str, separator: str = " · ") -> str:
    """Build a clean title from parts. No emoji prefix per brand book
    ('No emoji anywhere in working UI'). Uses middle-dot separator
    matching the chart-header pattern in the React app."""
    return separator.join(p for p in parts if p)


def footer(*parts: str, separator: str = " · ") -> dict:
    """Build a footer dict from parts."""
    return {"text": separator.join(p for p in parts if p)}
