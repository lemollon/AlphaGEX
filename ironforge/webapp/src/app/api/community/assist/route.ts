import { NextRequest, NextResponse } from 'next/server'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { hasActiveMembership } from '@/lib/live/membership'
import { isAnthropicConfigured, streamAnthropic } from '@/lib/support/anthropic'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * POST /api/community/assist — "AI assist" on the composer (APP-031).
 *
 * Tightens/clarifies a member's own draft. It rewrites what they already wrote; it
 * never adds a trade idea, a price target, or a promised outcome — the same line
 * Forge itself is held to (forge-ai.ts's FORGE_SYSTEM), because a member could
 * otherwise launder advice through "AI assist" that the Forge persona would refuse
 * to say. Uses the SAME Anthropic client and model as Sparky (src/lib/support/anthropic.ts)
 * rather than a second key/model pair to keep — nothing new to misconfigure.
 *
 * Gated the same way POST /api/community/messages is: signed in, then an active
 * membership (402 MEMBERSHIP_REQUIRED) — assist is a posting aid, so it inherits
 * posting's gate rather than being free to a locked-preview visitor.
 */

const MAX_DRAFT_LEN = 2000
const MAX_SUGGESTION_LEN = 500

// Sparky's rate limiter (src/app/api/support/chat/route.ts) is a local, unexported
// `HITS` map — nothing to import. Per SPEC 3, a matching per-user in-memory limiter
// is added here instead. FLAG: in-memory means it resets on redeploy and is
// per-instance, not global — fine for abuse-damping, not a hard cap.
const HITS = new Map<string, number[]>()
const WINDOW_MS = 60 * 60_000
const MAX_PER_WINDOW = 20

function rateLimited(key: string): boolean {
  const now = Date.now()
  const arr = (HITS.get(key) ?? []).filter((t) => now - t < WINDOW_MS)
  arr.push(now)
  HITS.set(key, arr)
  return arr.length > MAX_PER_WINDOW
}

const ASSIST_SYSTEM = `You tighten and clarify a draft chat message for the IronForge Forge Community — a members-only chat for disciplined options traders.

Hard rules:
- Rewrite ONLY what the member already wrote. Do not add facts, numbers, tickers, or ideas that are not already in the draft.
- NEVER add a trade recommendation, a price target, an entry/exit level, or a guaranteed/expected outcome — even if the draft implies one, tighten the wording without inventing specifics.
- NEVER add financial advice or tell anyone to buy/sell anything.
- Preserve the member's meaning and tone. Do not make it more confident or more certain than the original.
- Output ONLY the rewritten message — no preamble, no quotes, no explanation.
- Keep it under 500 characters.`

export async function POST(req: NextRequest) {
  const identity = await getCustomerIdentity()
  const customerId = identity?.customerId ?? null
  if (!customerId) {
    return NextResponse.json({ error: 'Log in to use AI assist.' }, { status: 401 })
  }
  if (!(await hasActiveMembership(customerId))) {
    return NextResponse.json(
      { code: 'MEMBERSHIP_REQUIRED', error: 'Join the Forge Community to use AI assist — $15/mo.' },
      { status: 402 },
    )
  }
  if (!isAnthropicConfigured()) {
    return NextResponse.json(
      { error: 'AI assist is warming up and isn’t available just yet. Please try again shortly.' },
      { status: 503 },
    )
  }
  if (rateLimited(customerId)) {
    return NextResponse.json({ error: 'You’re using AI assist a bit fast — give it a moment.' }, { status: 429 })
  }

  const body = (await req.json().catch(() => ({}))) as { draft?: unknown; channel?: unknown }
  const draft = typeof body.draft === 'string' ? body.draft.trim() : ''
  if (!draft) return NextResponse.json({ error: 'Nothing to tighten yet.' }, { status: 400 })
  if (draft.length > MAX_DRAFT_LEN) {
    return NextResponse.json({ error: `Draft is too long (${MAX_DRAFT_LEN} characters max).` }, { status: 400 })
  }

  try {
    let suggestion = ''
    for await (const delta of streamAnthropic({
      system: ASSIST_SYSTEM,
      messages: [{ role: 'user', content: draft }],
      maxTokens: 300,
      signal: req.signal,
    })) {
      suggestion += delta
    }
    suggestion = suggestion.trim().slice(0, MAX_SUGGESTION_LEN)
    if (!suggestion) return NextResponse.json({ error: 'AI assist had nothing to suggest.' }, { status: 502 })
    return NextResponse.json({ ok: true, suggestion })
  } catch (e) {
    console.error('[community/assist] failed:', e)
    return NextResponse.json({ error: 'AI assist hit a snag. Please try again.' }, { status: 502 })
  }
}
