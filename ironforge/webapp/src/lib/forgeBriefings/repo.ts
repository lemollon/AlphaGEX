import { query, dbExecute } from '../db'
import type { BriefRow, BotKey, BriefType, ParsedBrief, MacroRibbon, SparklinePoint, Mood, Factor } from './types'
import { stripDecorativeUnicode } from './sanitize'

/**
 * Strip any emoji / decorative-symbol unicode from text fields before they
 * leave the read layer. The voice prompts already prohibit emojis in new
 * briefs, but historic rows generated before that rule may contain them
 * and would render as black tofu boxes in the UI.
 */
function sanitizeBrief<T extends BriefRow | null>(row: T): T {
  if (!row) return row
  return {
    ...row,
    title: stripDecorativeUnicode(row.title),
    summary: stripDecorativeUnicode(row.summary),
    wisdom: row.wisdom ? stripDecorativeUnicode(row.wisdom) : row.wisdom,
    bot_voice_signature: stripDecorativeUnicode(row.bot_voice_signature),
    factors: Array.isArray(row.factors)
      ? row.factors.map((f: Factor) => ({
          ...f,
          title: stripDecorativeUnicode(f.title),
          detail: stripDecorativeUnicode(f.detail),
        }))
      : row.factors,
  } as T
}

export interface UpsertBriefInput {
  brief_id: string
  bot: BotKey
  brief_type: BriefType
  brief_date: string
  parsed: ParsedBrief
  mood: Mood
  macro_ribbon: MacroRibbon
  sparkline_data: SparklinePoint[]
  prior_briefs_referenced: string[]
  codex_referenced: string | null
  model: string
  tokens_in: number
  tokens_out: number
  cost_usd: number
  generation_status: string
}

export async function upsertBrief(input: UpsertBriefInput): Promise<void> {
  await dbExecute(`
    INSERT INTO forge_briefings (
      brief_id, bot, brief_type, brief_date, brief_time,
      title, summary, wisdom, risk_score, mood, bot_voice_signature,
      factors, trade_of_day, macro_ribbon, sparkline_data,
      prior_briefs_referenced, codex_referenced,
      model, tokens_in, tokens_out, cost_usd, generation_status
    ) VALUES (
      $1,$2,$3,$4,NOW(),
      $5,$6,$7,$8,$9,$10,
      $11,$12,$13,$14,
      $15,$16,$17,$18,$19,$20,$21
    )
    ON CONFLICT (brief_id) DO UPDATE SET
      title = EXCLUDED.title,
      summary = EXCLUDED.summary,
      wisdom = EXCLUDED.wisdom,
      risk_score = EXCLUDED.risk_score,
      mood = EXCLUDED.mood,
      bot_voice_signature = EXCLUDED.bot_voice_signature,
      factors = EXCLUDED.factors,
      trade_of_day = EXCLUDED.trade_of_day,
      macro_ribbon = EXCLUDED.macro_ribbon,
      sparkline_data = EXCLUDED.sparkline_data,
      prior_briefs_referenced = EXCLUDED.prior_briefs_referenced,
      codex_referenced = EXCLUDED.codex_referenced,
      model = EXCLUDED.model,
      tokens_in = EXCLUDED.tokens_in,
      tokens_out = EXCLUDED.tokens_out,
      cost_usd = EXCLUDED.cost_usd,
      generation_status = EXCLUDED.generation_status,
      is_active = TRUE,
      updated_at = NOW()
  `, [
    input.brief_id, input.bot, input.brief_type, input.brief_date,
    input.parsed.title, input.parsed.summary, input.parsed.wisdom,
    input.parsed.risk_score, input.mood, input.parsed.bot_voice_signature,
    JSON.stringify(input.parsed.factors), JSON.stringify(input.parsed.trade_of_day ?? null),
    JSON.stringify(input.macro_ribbon), JSON.stringify(input.sparkline_data),
    input.prior_briefs_referenced, input.codex_referenced,
    input.model, input.tokens_in, input.tokens_out, input.cost_usd, input.generation_status,
  ])
}

export async function findById(briefId: string): Promise<BriefRow | null> {
  const rows = await query<BriefRow>(
    `SELECT * FROM forge_briefings WHERE brief_id = $1 AND is_active = TRUE`,
    [briefId],
  )
  return sanitizeBrief(rows[0] ?? null)
}

export async function existsOk(briefId: string): Promise<boolean> {
  const rows = await query<{ ok: boolean }>(
    `SELECT (generation_status = 'ok') AS ok FROM forge_briefings WHERE brief_id = $1 AND is_active = TRUE`,
    [briefId],
  )
  return rows[0]?.ok === true
}

export async function listForBot(bot: BotKey, briefType: BriefType, limit: number): Promise<BriefRow[]> {
  const rows = await query<BriefRow>(
    `SELECT * FROM forge_briefings
     WHERE bot = $1 AND brief_type = $2 AND is_active = TRUE
     ORDER BY brief_date DESC LIMIT $3`,
    [bot, briefType, limit],
  )
  return rows.map(r => sanitizeBrief(r) as BriefRow)
}

export async function listInRange(opts: {
  from?: string; to?: string; bot?: BotKey; brief_type?: BriefType
  limit?: number; offset?: number
}): Promise<BriefRow[]> {
  const where: string[] = ['is_active = TRUE']
  const params: any[] = []
  let idx = 1
  if (opts.from) { where.push(`brief_date >= $${idx++}::date`); params.push(opts.from) }
  if (opts.to)   { where.push(`brief_date <= $${idx++}::date`); params.push(opts.to)   }
  if (opts.bot)  { where.push(`bot = $${idx++}`);                params.push(opts.bot)  }
  if (opts.brief_type) { where.push(`brief_type = $${idx++}`);   params.push(opts.brief_type) }
  const limit = Math.max(1, Math.min(opts.limit ?? 20, 100))
  const offset = Math.max(0, opts.offset ?? 0)
  params.push(limit, offset)
  const rows = await query<BriefRow>(
    `SELECT * FROM forge_briefings WHERE ${where.join(' AND ')}
     ORDER BY brief_date DESC, brief_time DESC
     LIMIT $${idx++} OFFSET $${idx++}`,
    params,
  )
  return rows.map(r => sanitizeBrief(r) as BriefRow)
}

export async function listCalendarBadges(from: string, to: string): Promise<Array<{
  brief_date: string; bot: BotKey; brief_id: string; risk_score: number | null;
  mood: Mood | null; first_sentence: string
}>> {
  const rows = await query<any>(`
    SELECT brief_date::text AS brief_date, bot, brief_id, risk_score, mood,
           split_part(summary, '.', 1) || '.' AS first_sentence
    FROM forge_briefings
    WHERE is_active = TRUE
      AND brief_type IN ('daily_eod')
      AND brief_date BETWEEN $1::date AND $2::date
    ORDER BY brief_date ASC
  `, [from, to])
  return rows.map(r => ({ ...r, first_sentence: stripDecorativeUnicode(r.first_sentence) }))
}

export async function setMetaOk(bot: BotKey, briefType: BriefType, briefId: string): Promise<void> {
  await dbExecute(`
    INSERT INTO forge_briefings_meta (bot, brief_type, last_run_ts, last_run_status, last_brief_id, retry_count)
    VALUES ($1, $2, NOW(), 'ok', $3, 0)
    ON CONFLICT (bot, brief_type) DO UPDATE SET
      last_run_ts = NOW(), last_run_status = 'ok', last_brief_id = $3, retry_count = 0
  `, [bot, briefType, briefId])
}

export async function setMetaError(bot: BotKey, briefType: BriefType, msg: string): Promise<void> {
  await dbExecute(`
    INSERT INTO forge_briefings_meta (bot, brief_type, last_run_ts, last_run_status, retry_count)
    VALUES ($1, $2, NOW(), $3, 0)
    ON CONFLICT (bot, brief_type) DO UPDATE SET
      last_run_ts = NOW(), last_run_status = $3, retry_count = 0
  `, [bot, briefType, `error: ${msg.slice(0, 200)}`])
}

export async function getMetaRetry(bot: BotKey, briefType: BriefType): Promise<{ retry_count: number; last_run_ts: Date | null; last_run_status: string | null }> {
  const rows = await query<any>(
    `SELECT retry_count, last_run_ts, last_run_status FROM forge_briefings_meta WHERE bot = $1 AND brief_type = $2`,
    [bot, briefType],
  )
  if (!rows[0]) return { retry_count: 0, last_run_ts: null, last_run_status: null }
  return {
    retry_count: rows[0].retry_count ?? 0,
    last_run_ts: rows[0].last_run_ts ? new Date(rows[0].last_run_ts) : null,
    last_run_status: rows[0].last_run_status ?? null,
  }
}
