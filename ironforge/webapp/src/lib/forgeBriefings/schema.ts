import type { ParsedBrief } from './types'

function stripCodeFences(s: string): string {
  const fenceMatch = s.match(/^```(?:json)?\s*\n?([\s\S]*?)\n?```\s*$/m)
  return fenceMatch ? fenceMatch[1] : s
}

export type ParseResult = { ok: true; brief: ParsedBrief } | { ok: false; error: string }

export function parseBriefResponse(raw: string): ParseResult {
  if (!raw || typeof raw !== 'string') return { ok: false, error: 'empty response' }
  const trimmed = stripCodeFences(raw.trim())
  let obj: any
  try { obj = JSON.parse(trimmed) } catch (e) {
    return { ok: false, error: `JSON parse: ${(e as Error).message}` }
  }
  if (!obj || typeof obj !== 'object') return { ok: false, error: 'not an object' }
  if (typeof obj.title !== 'string' || obj.title.length === 0) return { ok: false, error: 'missing title' }
  if (typeof obj.summary !== 'string' || obj.summary.length === 0) return { ok: false, error: 'missing summary' }
  if (typeof obj.bot_voice_signature !== 'string') return { ok: false, error: 'missing bot_voice_signature' }
  if (obj.wisdom !== null && typeof obj.wisdom !== 'string') return { ok: false, error: 'wisdom must be string or null' }
  if (typeof obj.risk_score !== 'number' || obj.risk_score < 0 || obj.risk_score > 10) {
    return { ok: false, error: 'risk_score must be 0-10' }
  }
  if (!Array.isArray(obj.factors)) return { ok: false, error: 'factors must be array' }
  for (const f of obj.factors) {
    if (typeof f.rank !== 'number' || typeof f.title !== 'string' || typeof f.detail !== 'string') {
      return { ok: false, error: 'invalid factor shape' }
    }
  }
  if (obj.trade_of_day !== null && obj.trade_of_day !== undefined) {
    const t = obj.trade_of_day
    if (typeof t.position_id !== 'string' || typeof t.pnl !== 'number' || !Array.isArray(t.payoff_points)) {
      return { ok: false, error: 'invalid trade_of_day shape' }
    }
  }
  return {
    ok: true,
    brief: {
      title: obj.title,
      summary: obj.summary,
      wisdom: obj.wisdom ?? null,
      risk_score: Math.round(obj.risk_score),
      bot_voice_signature: obj.bot_voice_signature,
      factors: obj.factors,
      trade_of_day: obj.trade_of_day ?? null,
    },
  }
}
