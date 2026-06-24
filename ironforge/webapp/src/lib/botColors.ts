// Single source of truth for per-bot identity colors.
//
// Keep these in sync with:
//   - globals.css  :root  --bot-* custom properties (CSS consumers)
//   - app/_landing/landingMarkup.ts (auto-generated landing markup; upstream landing.html)
//
// One color per bot, reused on the landing, compare page, dashboards and nav.
export const BOT_COLORS = {
  flame: '#FF5500', // 2DTE — brand orange
  spark: '#3b82f6', // 1DTE — blue
  inferno: '#ef4444', // 0DTE — red
  blaze: '#06b6d4', // 1DTE directional — cyan
  flare: '#f5a623', // 0DTE directional — amber
  kindle: '#fbbf24', // 1DTE IC, $500 live (SPARK strategy) — gold/amber
} as const

export type BotKey = keyof typeof BOT_COLORS
