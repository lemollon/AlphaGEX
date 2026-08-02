# IronForge app icon — UX-001

Regenerate with `python ../../tools/make_icon.py` (needs Pillow + `Oswald-Bold.ttf`
alongside the script — the Oswald variable font from Google Fonts).

## Why this is rendered, not AI-generated

The artwork is a **wordmark**. Diffusion models cannot be trusted to spell or kern
letterforms, and this asset is permanent brand shipped to two app stores. The script
produces exact hex, exact letterforms, and crisp edges at every size — deterministically,
so a regeneration is byte-identical.

## Spec compliance (UX-001)

| Requirement | How it's met |
|---|---|
| Wordmark only | Type only. No mascot, no IF monogram. |
| White `IRON` | `#FFFFFF` |
| Forge Orange `FORGE` | `#FD5301` — the value hardcoded in `webapp/src/components/Brand.tsx` and called "the marketing accent" there. Deliberately **not** `#FF5500` (`--bot-flame`) or `#EE5A24` (`amber-500`, the UI accent). |
| Subtle charcoal illumination on black | Blurred radial `#3A3634` glow over `#0B0B0D` (`forge.bg`) |
| Legible at every platform size | See `legibility-contact-sheet.png` |

## The one deviation from a literal reading of the spec, and why

UX-001 says "wordmark only" and also requires the icon to "remain legible after OS
masking." On a **square** canvas those two pull against each other: `IRONFORGE` set on
one line inside 1024×1024 gives roughly a 90px cap height, which is unreadable once iOS
scales the tile to 60px.

The wordmark is therefore **stacked on two lines** — still wordmark-only, still white
IRON over orange FORGE, but with about 3× the cap height. The contact sheet shows it
holding at 60px and remaining readable at 40px. If design wants the single-line lockup
instead, that is a legibility regression they should sign off on explicitly.

## Files

- `icon-1024.png` — App Store master. **Opaque RGB, no alpha, no pre-rounded corners**;
  Apple rejects alpha here and applies its own squircle mask.
- `play-store-512.png` — Play Store listing icon.
- `ios/icon-*.png` — the iOS asset-catalog sizes.
- `android/ic_launcher_foreground.png` — **RGBA with a transparent background.** The
  launcher composites this over the background layer and parallaxes the two
  independently; baking the background in kills the effect and double-darkens the icon.
  Content sits inside the 66% safe circle, which is why it is rendered separately rather
  than downscaled from the master.
- `android/ic_launcher_background.png` — the charcoal-glow field, no wordmark.
- `android/ic_launcher-*.png` — flattened legacy launcher icons for pre-adaptive Android.
