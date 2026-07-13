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
  kindle: '#fbbf24', // 1DTE IC (retired 2026-07-13; history only) — gold/amber
  spark2: '#60a5fa', // 1DTE IC, SPARK v2 config on the second live account — light blue
} as const

export type BotKey = keyof typeof BOT_COLORS
