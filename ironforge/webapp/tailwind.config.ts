import type { Config } from 'tailwindcss'
import colors from 'tailwindcss/colors'

// ── Design-system palette (single source of truth) ──────────────────────────
// The whole app rides Tailwind color utilities, so unifying the scales here
// re-skins every inner page into the system in ONE place — the same technique
// already used to re-hue `amber` to the brand orange.
//   • green / emerald  → POSITIVE (profit, up, healthy)
//   • red / rose       → NEGATIVE (loss, down, danger)
//   • yellow           → CAUTION  (warnings only)
//   • every decorative hue (blue, cyan, violet, purple, fuchsia, pink, indigo,
//     teal, lime, sky, orange) → NEUTRAL, so color stays deliberate.
// Per-bot identity is NOT a Tailwind hue — it comes from lib/botColors.ts /
// globals.css --bot-* and is applied only as a thin accent (dot + card top-rule).
const POSITIVE = colors.emerald
const NEGATIVE = colors.red
const CAUTION = colors.amber
const NEUTRAL = colors.stone

const config: Config = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      fontFamily: {
        // --font-sans / --font-display are injected by next/font in app/layout.tsx
        sans: ['var(--font-sans)', 'ui-sans-serif', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'sans-serif'],
        display: ['var(--font-display)', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      colors: {
        // Brand accent rides amber-* (existing re-hue, anchored on the #FF5500 family)
        amber: {
          50: '#FFF3ED',
          100: '#FFE3D3',
          200: '#FFC4A5',
          300: '#FB9B6B',
          400: '#F5743C',
          500: '#EE5A24',
          600: '#E8531F',
          700: '#B83C12',
          800: '#92300E',
          900: '#5C1E08',
        },
        // Semantic unification — one green, one red, one caution everywhere
        green: POSITIVE,
        emerald: POSITIVE,
        red: NEGATIVE,
        rose: NEGATIVE,
        yellow: CAUTION,
        // Collapse decorative "skittles" to a single neutral. Bot identity is
        // reintroduced deliberately via lib/botColors (dots + card top-rules).
        blue: NEUTRAL,
        sky: NEUTRAL,
        cyan: NEUTRAL,
        indigo: NEUTRAL,
        violet: NEUTRAL,
        purple: NEUTRAL,
        fuchsia: NEUTRAL,
        pink: NEUTRAL,
        teal: NEUTRAL,
        lime: NEUTRAL,
        orange: NEUTRAL,
        flame: {
          DEFAULT: '#E8531F',
          dark: '#C2410C',
          glow: '#FB7A3D',
        },
        spark: {
          DEFAULT: '#3b82f6',
          dark: '#2563eb',
        },
        forge: {
          bg: '#0B0B0D',
          card: '#16161A',
          border: '#262629',
          muted: '#78716c',
        },
      },
      backgroundImage: {
        'ember-glow': 'radial-gradient(ellipse at 50% 0%, rgba(232,83,31,0.08) 0%, transparent 60%)',
        'ember-subtle': 'radial-gradient(ellipse at 50% 100%, rgba(232,83,31,0.04) 0%, transparent 50%)',
      },
      animation: {
        'pulse-slow': 'pulse 4s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
    },
  },
  plugins: [],
}
export default config
