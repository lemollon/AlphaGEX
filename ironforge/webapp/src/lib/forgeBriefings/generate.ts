import { gatherContext } from './context'
import { buildSystemPrompt, buildUserPrompt } from './voices'
import { parseBriefResponse } from './schema'
import { classifyMood } from './mood'
import { upsertBrief, existsOk, setMetaOk, setMetaError } from './repo'
import type { BotKey, BriefType } from './types'

const ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages'
const ANTHROPIC_MODEL = 'claude-sonnet-4-6'
const ANTHROPIC_VERSION = '2023-06-01'

interface GenerateOpts {
  bot: BotKey
  brief_type: BriefType
  brief_date: string
  baseUrl: string
  force?: boolean
}

interface GenerateResult {
  ok: boolean
  brief_id: string
  status: 'ok' | 'skipped_idempotent' | 'skipped_disabled' | 'error'
  reason?: string
}

function deterministicId(bot: BotKey, type: BriefType, date: string): string {
  if (type === 'codex_monthly') return `codex:${bot}:${date.slice(0, 7)}`
  const prefix = type === 'daily_eod' ? 'daily'
    : type === 'fomc_eve' ? 'fomc_eve'
    : type === 'post_event' ? 'post_event'
    : 'weekly'
  return `${prefix}:${bot}:${date}`
}

function pnlPctOfTarget(today_trades: any[]): number {
  if (!today_trades || today_trades.length === 0) return 0
  let sumPnl = 0; let sumCredit = 0
  for (const t of today_trades) {
    sumPnl += Number(t.realized_pnl ?? 0)
    sumCredit += Number(t.total_credit ?? 0) * Number(t.contracts ?? 1) * 100
  }
  if (sumCredit === 0) return 0
  return sumPnl / sumCredit
}

async function callClaude(systemPrompt: string, userPrompt: string): Promise<{
  text: string; model: string; tokens_in: number; tokens_out: number; cost_usd: number
}> {
  const apiKey = process.env.CLAUDE_API_KEY
  if (!apiKey) throw new Error('CLAUDE_API_KEY not set')
  const body = {
    model: ANTHROPIC_MODEL,
    max_tokens: 1600,
    system: [{ type: 'text', text: systemPrompt, cache_control: { type: 'ephemeral' } }],
    messages: [{ role: 'user', content: userPrompt }],
  }
  const res = await fetch(ANTHROPIC_API_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': apiKey,
      'anthropic-version': ANTHROPIC_VERSION,
      'anthropic-beta': 'prompt-caching-2024-07-31',
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`Anthropic ${res.status}: ${await res.text().catch(() => '')}`)
  const json: any = await res.json()
  const text = json.content?.[0]?.text ?? ''
  const tokens_in = (json.usage?.input_tokens ?? 0) + (json.usage?.cache_read_input_tokens ?? 0)
  const tokens_out = json.usage?.output_tokens ?? 0
  // Sonnet 4.6 pricing: $3/MTok in, $15/MTok out
  const cost_usd = (tokens_in / 1_000_000) * 3 + (tokens_out / 1_000_000) * 15
  return { text, model: json.model ?? ANTHROPIC_MODEL, tokens_in, tokens_out, cost_usd: +cost_usd.toFixed(4) }
}

export async function generateBrief(opts: GenerateOpts): Promise<GenerateResult> {
  const brief_id = deterministicId(opts.bot, opts.brief_type, opts.brief_date)

  if (!opts.force && await existsOk(brief_id)) {
    return { ok: true, brief_id, status: 'skipped_idempotent' }
  }

  if (opts.bot !== 'portfolio') {
    try {
      const { query } = await import('../db')
      const rows = await query<{ forge_briefings_enabled: boolean | null }>(
        `SELECT forge_briefings_enabled FROM ${opts.bot}_config LIMIT 1`,
      )
      if (rows[0]?.forge_briefings_enabled === false) {
        return { ok: true, brief_id, status: 'skipped_disabled' }
      }
    } catch { /* default-on */ }
  }

  let ctx
  try {
    ctx = await gatherContext({
      bot: opts.bot, brief_type: opts.brief_type,
      brief_date: opts.brief_date, baseUrl: opts.baseUrl,
    })
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    await setMetaError(opts.bot, opts.brief_type, `gather: ${msg}`)
    return { ok: false, brief_id, status: 'error', reason: `gather failed: ${msg}` }
  }

  const systemPrompt = buildSystemPrompt(opts.bot, opts.brief_type)
  const userPrompt = buildUserPrompt(ctx)

  let claudeRes
  try {
    claudeRes = await callClaude(systemPrompt, userPrompt)
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    await setMetaError(opts.bot, opts.brief_type, msg)
    return { ok: false, brief_id, status: 'error', reason: `claude failed: ${msg}` }
  }

  const parsed = parseBriefResponse(claudeRes.text)
  if (!parsed.ok) {
    await setMetaError(opts.bot, opts.brief_type, `parse: ${parsed.error}`)
    return { ok: false, brief_id, status: 'error', reason: `parse failed: ${parsed.error}` }
  }

  const trade_count = ctx.today_trades?.length ?? 0
  const mood = classifyMood({
    pnl_pct_of_target: pnlPctOfTarget(ctx.today_trades),
    risk_score: parsed.brief.risk_score,
    trade_count,
  })

  try {
    await upsertBrief({
      brief_id, bot: opts.bot, brief_type: opts.brief_type, brief_date: opts.brief_date,
      parsed: parsed.brief, mood,
      macro_ribbon: ctx.macro,
      sparkline_data: ctx.equity_curve_7d,
      prior_briefs_referenced: ctx.memory_recent.map(m => m.brief_id),
      codex_referenced: ctx.memory_codex?.brief_id ?? null,
      model: claudeRes.model,
      tokens_in: claudeRes.tokens_in, tokens_out: claudeRes.tokens_out,
      cost_usd: claudeRes.cost_usd,
      generation_status: 'ok',
    })
    await setMetaOk(opts.bot, opts.brief_type, brief_id)
    return { ok: true, brief_id, status: 'ok' }
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    await setMetaError(opts.bot, opts.brief_type, `db: ${msg}`)
    return { ok: false, brief_id, status: 'error', reason: `db failed: ${msg}` }
  }
}
