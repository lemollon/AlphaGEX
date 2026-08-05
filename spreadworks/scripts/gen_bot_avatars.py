#!/usr/bin/env python3
"""Generate per-bot Discord avatar PNGs for the SpreadWorks alert feed.

Discord lets a webhook override `username` + `avatar_url` per message, so every
bot alert can arrive under its own name and logo through the ONE
`DISCORD_WEBHOOK_URL` webhook. This script renders those logos.

Source of truth for colors is `frontend/src/lib/botRegistry.js` (`BOT_THEME`) —
the same palette the bot's own dashboard page tints to — so the Discord avatar
and the UI nameplate always match. Re-run after adding a bot or changing a
theme color:

    python spreadworks/scripts/gen_bot_avatars.py

Writes 256x256 RGBA PNGs to BOTH `frontend/public/bots/` (vite source) and
`frontend/dist/bots/` (the COMMITTED dist the backend actually serves — see
the SPA catch-all in backend/__init__.py, which serves any file under dist).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SPREADWORKS = Path(__file__).resolve().parent.parent
REGISTRY_JS = SPREADWORKS / "frontend" / "src" / "lib" / "botRegistry.js"
OUT_DIRS = [
    SPREADWORKS / "frontend" / "public" / "bots",
    SPREADWORKS / "frontend" / "dist" / "bots",
]

SIZE = 256          # render size; Discord downscales to ~40px in the feed
SUPERSAMPLE = 4     # draw at 4x then LANCZOS down — clean antialiased edges
DISC = (14, 22, 38, 255)        # #0E1626 SpreadWorks dark disc
DISC_EDGE = (30, 41, 59, 255)   # subtle inner bevel

# Two-letter monograms. Kept explicit (not derived) because several bots
# collide on their first letters — SURGE/SPLASH/SQUALL, AFTERBURN/AFTERGLOW,
# EMBER/EMBREACH, TIDE/THERMAL/TEMPEST — and the monogram is the ONLY thing
# distinguishing bots that share a palette entry (e.g. UPDRAFT and EMBER are
# both amber-400). Every value here must be unique.
MONOGRAM = {
    "surge": "SG", "ripple": "RP", "splash": "SP", "tide": "TD",
    "drift": "DF", "flow": "FL", "undertow": "UT", "delta": "DL",
    "meadow": "MD", "updraft": "UP", "thermal": "TH", "tempest": "TP",
    "backdraft": "BD", "wildfire": "WF", "reversal": "RV", "embreach": "EB",
    "embreachq": "EQ", "flashpoint": "FP", "squall": "SQ", "afterglow": "AG",
    "ember": "EM", "afterburn": "AB", "weekender": "WK", "tsunami": "TS",
}

# Bots with no BOT_THEME entry — TSUNAMI lives outside the options registry.
# There is deliberately NO "spreadworks" house avatar: briefings and market
# open/close posts send no identity override at all, so they keep the webhook's
# own configured SpreadWorks name + icon.
EXTRA = {
    "tsunami": "#22d3ee",
}

FONT_CANDIDATES = [
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]


def parse_theme_colors() -> dict[str, str]:
    """Pull {bot_key: '#rrggbb'} out of BOT_THEME in botRegistry.js.

    Regex rather than a JS parse: BOT_THEME is a flat literal and this keeps
    the script dependency-free. Anchored on `primary:` so the rgba() soft/ring
    variants are ignored.
    """
    src = REGISTRY_JS.read_text(encoding="utf-8")
    start = src.index("export const BOT_THEME")
    body = src[start:]
    colors: dict[str, str] = {}
    current: str | None = None
    for line in body.splitlines():
        m = re.match(r"\s{2}([a-z][a-z0-9_]*):\s*\{", line)
        if m:
            current = m.group(1)
            continue
        m = re.match(r"\s*primary:\s*'(#[0-9a-fA-F]{6})'", line)
        if m and current:
            colors[current] = m.group(1)
            current = None
    return colors


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def load_font(px: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).is_file():
            return ImageFont.truetype(path, px)
    raise SystemExit(
        "No bold TrueType font found. Add one to FONT_CANDIDATES — the default "
        "PIL bitmap font is unreadable when downscaled."
    )


def render(key: str, color_hex: str) -> Image.Image:
    s = SIZE * SUPERSAMPLE
    rgb = hex_rgb(color_hex)
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    pad = int(s * 0.01)
    # Outer glow: concentric rings at rising alpha instead of a real blur, so
    # the result is deterministic across Pillow versions.
    for i in range(int(s * 0.045), 0, -1):
        a = int(70 * (1 - i / (s * 0.045)))
        d.ellipse([pad + i * 0.6, pad + i * 0.6, s - pad - i * 0.6, s - pad - i * 0.6],
                  outline=(*rgb, a), width=int(s * 0.012))

    # Dark disc
    d.ellipse([pad, pad, s - pad, s - pad], fill=DISC)
    # Bot-colored ring + faint inner bevel
    d.ellipse([pad, pad, s - pad, s - pad], outline=(*rgb, 255), width=int(s * 0.035))
    inset = int(s * 0.085)
    d.ellipse([inset, inset, s - inset, s - inset], outline=DISC_EDGE, width=int(s * 0.008))

    mono = MONOGRAM.get(key)
    if mono is None:
        # Unknown bot: fall back to the first two letters. Not guaranteed
        # unique, but always renders something rather than crashing the deploy.
        mono = key[:2].upper()
    # 0.34 keeps the widest pairs (WK, WF, TP) clear of the ring.
    font = load_font(int(s * 0.34))
    box = d.textbbox((0, 0), mono, font=font)
    d.text(((s - (box[2] - box[0])) / 2 - box[0],
            (s - (box[3] - box[1])) / 2 - box[1]),
           mono, font=font, fill=(*rgb, 255))

    return img.resize((SIZE, SIZE), Image.LANCZOS)


def main() -> int:
    colors = parse_theme_colors()
    colors.update(EXTRA)
    if len(colors) < 20:
        print(f"ERROR: only parsed {len(colors)} themes from {REGISTRY_JS} — "
              "the BOT_THEME literal shape probably changed.", file=sys.stderr)
        return 1

    dupes = [m for m in set(MONOGRAM.values()) if list(MONOGRAM.values()).count(m) > 1]
    if dupes:
        print(f"ERROR: duplicate monograms {dupes}", file=sys.stderr)
        return 1

    for out in OUT_DIRS:
        out.mkdir(parents=True, exist_ok=True)

    for key, color in sorted(colors.items()):
        img = render(key, color)
        for out in OUT_DIRS:
            img.save(out / f"{key}.png")
    print(f"Wrote {len(colors)} avatars x {len(OUT_DIRS)} dirs")
    missing = sorted(set(colors) - set(MONOGRAM))
    if missing:
        print(f"NOTE: no explicit monogram for {missing} — used first-2-letters "
              "fallback. Add them to MONOGRAM.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
