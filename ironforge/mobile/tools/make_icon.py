"""
IronForge mobile app icon — UX-001.

Rendered deterministically rather than generated: a diffusion model cannot be trusted
to spell and kern a wordmark, and this artwork is permanent brand shipped to two app
stores. Exact hex, exact letterforms, crisp edges at every size.

UX-001 spec: wordmark only; white IRON; Forge Orange FORGE; subtle charcoal
illumination on black; no mascot, no IF monogram.

Stacked on two lines because the icon canvas is SQUARE — "IRONFORGE" set on one line
inside 1024x1024 renders about 90px tall, which is illegible once iOS scales it to a
60px home-screen tile. Stacking keeps it wordmark-only while roughly tripling cap
height.
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os

# Brand.tsx hardcodes #FD5301 for FORGE and calls it "the marketing accent" —
# deliberately NOT #FF5500 (--bot-flame) or #EE5A24 (amber-500 UI accent).
FORGE_ORANGE = (253, 83, 1)
IRON_WHITE = (255, 255, 255)
# forge.bg from tailwind.config.ts. Not pure black: it matches the app background.
BG = (11, 11, 13)
CHARCOAL = (58, 54, 52)

FONT = 'Oswald-Bold.ttf'
OUT = 'icons'
os.makedirs(OUT, exist_ok=True)


def load_font(size):
    f = ImageFont.truetype(FONT, size)
    try:
        # Oswald ships as a variable font; PIL defaults to Regular. The wordmark is Bold.
        f.set_variation_by_axes([700])
    except Exception:
        pass
    return f


def fit_font(text, target_w, start=520):
    """Largest size at which `text` fits target_w."""
    size = start
    while size > 20:
        f = load_font(size)
        if f.getbbox(text)[2] - f.getbbox(text)[0] <= target_w:
            return f
        size -= 4
    return load_font(20)


def render(canvas, content_frac, supersample=4, transparent=False):
    """
    canvas: output edge length in px.
    content_frac: fraction of the canvas the wordmark may occupy. iOS masks to a
      squircle so ~0.72 is safe; Android adaptive icons crop to a 66% circle, so the
      foreground layer needs a much smaller fraction.
    transparent: emit RGBA with no background. Required for the Android adaptive
      FOREGROUND layer — the launcher composites it over the separate background layer
      and parallaxes the two independently, so baking the background into the
      foreground kills the effect and double-darkens the result.
    """
    S = canvas * supersample

    if transparent:
        img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    else:
        img = Image.new('RGB', (S, S), BG)
        # Subtle charcoal illumination — a soft radial glow behind the wordmark, per
        # UX-001. Drawn oversized then blurred so there is no visible edge.
        glow = Image.new('L', (S, S), 0)
        gd = ImageDraw.Draw(glow)
        r = int(S * 0.40)
        gd.ellipse([S // 2 - r, S // 2 - r, S // 2 + r, S // 2 + r], fill=95)
        glow = glow.filter(ImageFilter.GaussianBlur(S * 0.11))
        img = Image.composite(Image.new('RGB', (S, S), CHARCOAL), img, glow)

    # content_frac == 0 means "field only, no wordmark" — the Android background layer.
    if content_frac <= 0:
        return img.resize((canvas, canvas), Image.LANCZOS)

    d = ImageDraw.Draw(img)
    content_w = int(S * content_frac)

    # Size both words to the SAME width so the block reads as one lockup. FORGE is
    # the wider string, so it sets the scale.
    f_forge = fit_font('FORGE', content_w, start=S)
    forge_bb = f_forge.getbbox('FORGE')
    forge_w = forge_bb[2] - forge_bb[0]
    f_iron = fit_font('IRON', forge_w, start=S)

    iron_bb = f_iron.getbbox('IRON')
    iron_w = iron_bb[2] - iron_bb[0]
    iron_h = iron_bb[3] - iron_bb[1]
    forge_h = forge_bb[3] - forge_bb[1]

    gap = int(forge_h * 0.14)
    total_h = iron_h + gap + forge_h
    top = (S - total_h) // 2

    d.text((S // 2 - iron_w // 2 - iron_bb[0], top - iron_bb[1]), 'IRON',
           font=f_iron, fill=IRON_WHITE)
    d.text((S // 2 - forge_w // 2 - forge_bb[0], top + iron_h + gap - forge_bb[1]),
           'FORGE', font=f_forge, fill=FORGE_ORANGE)

    return img.resize((canvas, canvas), Image.LANCZOS)


# ── App Store / master ──
# Opaque RGB, no alpha, no pre-rounded corners: Apple rejects alpha in the store icon
# and applies its own mask.
master = render(1024, 0.72)
master.save(f'{OUT}/icon-1024.png')

# ── iOS asset sizes ──
for px in (180, 167, 152, 120, 87, 80, 76, 60, 58, 40, 29, 20):
    master.resize((px, px), Image.LANCZOS).save(f'{OUT}/ios/icon-{px}.png')

# ── Android adaptive icon ──
# The launcher crops the foreground to a circle covering ~66% of the layer and may
# animate/parallax it, so the wordmark gets a much tighter content fraction here.
# Rendering it separately (rather than downscaling the master) is what keeps it from
# being clipped.
fg = render(432, 0.46, transparent=True)
fg.save(f'{OUT}/android/ic_launcher_foreground.png')
# Background layer: the charcoal-glow field with no wordmark, so the two layers can
# parallax against each other the way the launcher expects.
bg_layer = render(432, 0.0, supersample=2)
bg_layer.save(f'{OUT}/android/ic_launcher_background.png')
# Legacy (pre-adaptive) launcher icons — flattened, since old launchers take one bitmap.
for px in (192, 144, 96, 72, 48):
    render(px * 2, 0.46).resize((px, px), Image.LANCZOS).save(f'{OUT}/android/ic_launcher-{px}.png')

# Play Store listing icon (512, opaque)
render(512, 0.72).save(f'{OUT}/play-store-512.png')

# ── Legibility contact sheet ──
# The real acceptance test for UX-001 is "remains legible after OS masking", which is
# a question about 60px, not 1024px. This renders the actual shipped sizes side by side
# so it can be judged rather than assumed.
sizes = [180, 120, 87, 60, 40]
pad = 24
sheet_w = sum(sizes) + pad * (len(sizes) + 1)
sheet = Image.new('RGB', (sheet_w, max(sizes) + pad * 2), (24, 24, 27))
x = pad
for px in sizes:
    sheet.paste(master.resize((px, px), Image.LANCZOS), (x, (sheet.height - px) // 2))
    x += px + pad
sheet.save(f'{OUT}/legibility-contact-sheet.png')

print('master:', master.size, 'mode', master.mode)
print('wrote', sum(len(f) for _, _, f in os.walk(OUT)), 'files ->', os.path.abspath(OUT))
