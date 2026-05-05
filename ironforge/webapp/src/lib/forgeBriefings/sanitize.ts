/**
 * Strip decorative unicode (emojis, symbol-icons, dingbats) from
 * Claude-generated brief text.
 *
 * The voice prompts already tell Claude not to emit these, but rows
 * generated before that rule landed (or any future drift) would render
 * as black tofu boxes / orphan emoji glyphs in the system font fallback,
 * which the user explicitly does not want.
 *
 * Safe to call on any string. Returns the input unchanged when null/empty.
 *
 * Ranges removed:
 *   U+1F300 – U+1FAFF   emoji proper (faces, weather, transport, alchemy, etc.)
 *   U+2600  – U+27BF    misc symbols + dingbats (✓ ✗ ⚠ ★ ☀ ☁ etc.)
 *   U+2300  – U+23FF    misc technical (⌚ ⌛ ⏰ etc.)
 *   U+FE0E – U+FE0F     variation selectors (the modifier that turns a
 *                       symbol into a color emoji)
 *   U+200D              zero-width joiner (used to combine emojis)
 *
 * Preserved:
 *   plain ASCII, em-dash —, en-dash –, middle dot ·, curly quotes "" '',
 *   accented Latin, math operators ± ÷ × ≈ etc., currency symbols.
 */
// Two alternatives because the `/u` flag + \u{XXXX} escapes require es6+
// target; tsconfig.target is es5. Equivalent coverage via UTF-16 surrogate
// pairs for the supplementary plane plus BMP \uXXXX escapes.
//   First alt:  high surrogate \uD83C-\uD83E + any low surrogate  → U+1F000-U+1FFFF
//   Second alt: BMP ranges 2300-23FF (misc technical),
//               2600-27BF (misc symbols + dingbats),
//               200D (zero-width joiner), FE0E-FE0F (variation selectors)
const STRIP_RE = new RegExp(
  // Supplementary plane emoji: high surrogate \uD83C-\uD83E + any low surrogate.
  '[\\uD83C-\\uD83E][\\uDC00-\\uDFFF]'
  + '|'
  // BMP ranges: misc technical, misc symbols + dingbats, ZWJ, variation selectors.
  + '[\\u2300-\\u23FF\\u2600-\\u27BF\\u200D\\uFE0E\\uFE0F]',
  'g',
)

export function stripDecorativeUnicode(s: string | null | undefined): string {
  if (!s) return ''
  return s.replace(STRIP_RE, '').replace(/  +/g, ' ').trim()
}
