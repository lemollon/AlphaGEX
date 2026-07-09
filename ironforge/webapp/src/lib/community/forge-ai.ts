import { getQuoteDetail } from '@/lib/tradier'

/**
 * Forge — the AI community member for the Forge Community page.
 * Same raw-fetch Claude pattern as market-brief.ts / forgeBriefings.
 * Persona + rules follow the IronForge_Forge_Community_V1 design doc §10.
 */

const ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages'
const ANTHROPIC_VERSION = '2023-06-01'
const FORGE_MODEL = 'claude-sonnet-4-6'
const MODERATION_MODEL = 'claude-haiku-4-5-20251001'

export function isForgeConfigured(): boolean {
  return !!(process.env.CLAUDE_API_KEY || process.env.ANTHROPIC_API_KEY)
}

async function callClaude(opts: {
  model: string
  system: string
  user: string
  maxTokens: number
}): Promise<string> {
  const apiKey = process.env.CLAUDE_API_KEY || process.env.ANTHROPIC_API_KEY
  if (!apiKey) throw new Error('CLAUDE_API_KEY env var is not set')
  const resp = await fetch(ANTHROPIC_API_URL, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'anthropic-version': ANTHROPIC_VERSION,
      'x-api-key': apiKey,
    },
    body: JSON.stringify({
      model: opts.model,
      max_tokens: opts.maxTokens,
      system: opts.system,
      messages: [{ role: 'user', content: opts.user }],
    }),
  })
  if (!resp.ok) {
    const errText = await resp.text().catch(() => '<unreadable>')
    throw new Error(`Claude API ${resp.status}: ${errText.slice(0, 300)}`)
  }
  const data = await resp.json()
  const blocks = Array.isArray(data?.content) ? data.content : []
  const text = blocks.map((b: any) => b?.text ?? '').join('').trim()
  if (!text) throw new Error('Claude API returned empty content')
  return text
}

const FORGE_SYSTEM = `You are Forge, the AI community member of the IronForge Forge Community — a members-only chat for disciplined options traders.

Persona: disciplined, professional, encouraging. You are a guide and moderator, never a guru.

Hard rules:
- NEVER provide financial advice, trade recommendations, or tell anyone to buy/sell anything. Education and observation only.
- NEVER insult users. NEVER use profanity.
- Use emojis sparingly (at most one per message).
- Keep replies short — 1 to 3 sentences for chat replies, at most a short paragraph for scheduled updates.
- NEVER invent market data. Only reference specific prices/levels/numbers that are explicitly provided to you in the prompt. If none are provided, speak in general terms.
- If a member has an account, billing, or technical problem you cannot resolve, direct them to support@ironforge.trade.
- End community updates (not every reply) with "Protect the forge." when it fits naturally.`

/** Reply when a member @-mentions Forge or addresses it directly. */
export function shouldForgeReply(message: string): boolean {
  return /(@forge\b|(^|\s)(hey|hi|hello|thanks|thank you|good morning|gm)[,!\s]+forge\b|^forge\b)/i.test(message)
}

async function getMarketContextLine(): Promise<string> {
  try {
    const spy = await getQuoteDetail('SPY')
    if (spy?.last != null) {
      const chg = spy.change_percentage != null ? ` (${spy.change_percentage >= 0 ? '+' : ''}${spy.change_percentage.toFixed(2)}% today)` : ''
      return `Live data you may reference: SPY is trading at $${spy.last.toFixed(2)}${chg}.`
    }
  } catch {
    /* no market data — Forge speaks in general terms */
  }
  return 'No live market data is available right now — do not cite any specific prices or levels.'
}

export async function generateForgeReply(opts: {
  senderName: string
  message: string
  recentMessages: Array<{ sender_name: string; sender_type: string; message: string }>
}): Promise<string> {
  const history = opts.recentMessages
    .slice(-10)
    .map((m) => `${m.sender_type === 'FORGE' ? 'Forge (you)' : m.sender_name}: ${m.message}`)
    .join('\n')
  const marketLine = await getMarketContextLine()
  const user = `${marketLine}

Recent channel messages:
${history || '(channel is quiet)'}

${opts.senderName} just posted: "${opts.message}"

Write Forge's reply to ${opts.senderName}.`
  return callClaude({ model: FORGE_MODEL, system: FORGE_SYSTEM, user, maxTokens: 300 })
}

export type ForgeSlot = 'premarket' | 'midday' | 'powerhour' | 'recap'

const SLOT_BRIEF: Record<ForgeSlot, string> = {
  premarket: 'a pre-market briefing: greet the community, set a disciplined tone for the trading day',
  midday: 'a midday update: a brief disciplined check-in for the community',
  powerhour: 'power-hour observations: remind the community to stay disciplined into the close',
  recap: 'a market recap: close out the day with an encouraging, disciplined note',
}

export async function generateScheduledPost(slot: ForgeSlot): Promise<string> {
  const marketLine = await getMarketContextLine()
  const user = `${marketLine}

Write ${SLOT_BRIEF[slot]} for the Forge Community chat. 2-4 short sentences.`
  return callClaude({ model: FORGE_MODEL, system: FORGE_SYSTEM, user, maxTokens: 350 })
}

// ── Moderation (scores BEFORE persistence, per design doc §11) ──────────

export interface ModerationVerdict {
  ok: boolean
  category?: string
  score?: number
}

/** Fast local pre-filter — catches the obvious cases with zero latency. */
const WORDLIST = /\b(fuck|shit|bitch|asshole|cunt|nigger|faggot|kys|kill yourself)\b/i

const MODERATION_SYSTEM = `You are a strict content moderator for a professional trading community chat.
Score the message and respond with ONLY a JSON object, no other text:
{"profanity":0.0,"threat":0.0,"harassment":0.0,"personal_attack":0.0,"spam":0.0}
Each score is 0.0-1.0. Normal trading talk, disagreement, and market opinions are all fine (all zeros).`

// Thresholds per design doc §11.
const THRESHOLDS: Array<[string, number]> = [
  ['profanity', 0.8],
  ['threat', 0.5],
  ['harassment', 0.6],
  ['personal_attack', 0.5],
  ['spam', 0.7],
]

export async function moderateMessage(message: string): Promise<ModerationVerdict> {
  if (WORDLIST.test(message)) {
    return { ok: false, category: 'PROFANITY_DETECTED', score: 1 }
  }
  if (!isForgeConfigured()) return { ok: true } // wordlist-only fallback
  try {
    const raw = await callClaude({
      model: MODERATION_MODEL,
      system: MODERATION_SYSTEM,
      user: message.slice(0, 2000),
      maxTokens: 120,
    })
    const jsonMatch = raw.match(/\{[\s\S]*\}/)
    if (!jsonMatch) return { ok: true }
    const scores = JSON.parse(jsonMatch[0]) as Record<string, number>
    for (const [category, threshold] of THRESHOLDS) {
      const score = Number(scores[category] ?? 0)
      if (score >= threshold) {
        return { ok: false, category: `${category.toUpperCase()}_DETECTED`, score }
      }
    }
    return { ok: true }
  } catch {
    // Fail-open: a moderation outage must not take the chat down.
    return { ok: true }
  }
}
