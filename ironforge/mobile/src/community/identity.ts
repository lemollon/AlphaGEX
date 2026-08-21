/**
 * How a Community post is labelled and coloured — UX-005.
 *
 * Pure, and separate from the screen, because both rules are the kind that look
 * obviously right and are quietly wrong on real data: a two-word initial that breaks
 * on "Jean-Luc", a colour picked by array index that reshuffles every time the feed
 * reorders. Neither shows up in a screenshot of the happy path.
 */

/**
 * Up to two initials for an avatar bubble, matching "JM" / "AR" in UX-005.
 *
 * 🚨 Splits on any whitespace run and takes the FIRST CODE POINT of the first and
 * last parts. Not `name[0] + name[1]`, which yields "JO" for "Jordan M.", and not a
 * regex character class — `charAt(0)` cuts a surrogate pair in half and renders a
 * replacement glyph for anyone whose name starts outside the BMP.
 */
export function initials(name: string): string {
  const parts = (name ?? '').trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  const first = [...parts[0]][0] ?? ''
  const last = parts.length > 1 ? ([...parts[parts.length - 1]][0] ?? '') : ''
  return (first + last).toUpperCase()
}

/**
 * The category chip's accent, keyed to the channel the post was written in.
 *
 * UX-005 colours Market Talk orange, Trade Ideas blue and General neutral. Keyed by
 * SLUG rather than display name so renaming a channel in the database cannot silently
 * turn every chip grey, and defaulting to neutral so a channel added later gets a
 * plain chip instead of no chip at all.
 */
const CHANNEL_ACCENT: Record<string, string> = {
  'market-talk': '#EE5A24',
  'trade-ideas': '#3B82F6',
  'news-events': '#E0B23F',
  general: '#A3A3A3',
  'all-chat': '#A3A3A3',
}

export const NEUTRAL_ACCENT = '#A3A3A3'

export function channelAccent(slug: string | undefined): string {
  if (!slug) return NEUTRAL_ACCENT
  return CHANNEL_ACCENT[slug] ?? NEUTRAL_ACCENT
}

/**
 * A stable background tint for a member's initials bubble.
 *
 * 🚨 Derived from the NAME, not the list index. Index-based colouring changes every
 * time the feed reorders or a post is blocked out of it, so the same person appears
 * in a different colour on every poll — which reads as a different person.
 */
const BUBBLE_TINTS = ['#2A3340', '#33372A', '#3A2E2A', '#2A3A38', '#352A3A', '#3A3A2A']

export function bubbleTint(name: string): string {
  let hash = 0
  for (const ch of name ?? '') hash = (hash * 31 + ch.codePointAt(0)!) >>> 0
  return BUBBLE_TINTS[hash % BUBBLE_TINTS.length]
}
