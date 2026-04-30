/**
 * SPARK market-risk brief generator (Commit Q1 — foundation).
 *
 * Informational only — does NOT affect trading behavior. Produces a
 * beginner-friendly plain-English summary of what could challenge a 1DTE
 * Iron Condor today, plus a 0-10 risk score and ranked factor list.
 *
 * Pipeline:
 *   1. gatherInputs(briefType)
 *        — fetches SPY + VIX family + VVIX via Tradier quotes
 *        — reads today's open SPARK position (if any) + last 7 days of
 *          closed SPARK trades from the DB
 *        — computes VIX term structure (vix3m / vix - 1)
 *        — returns a compact JSON object
 *
 *   2. buildPrompt(inputs, briefType)
 *        — produces a system + user prompt pair optimized for a beginner
 *          audience (jargon gets inline definitions, every factor is tied
 *          back to the open IC position)
 *
 *   3. callClaude(messages)
 *        — uses `process.env.CLAUDE_API_KEY` (same key AlphaGEX uses)
 *        — model: claude-sonnet-4-6 (latest Sonnet)
 *        — ~800 max output tokens per brief
 *
 *   4. parseResponse(text)
 *        — extracts RISK_SCORE + FACTORS + SUMMARY + WATCH_NEXT_HOUR
 *          via regex. Falls back to storing raw text if parsing fails.
 *
 *   5. storeBrief(parsed, inputs)
 *        — INSERT into spark_market_briefs; returns the new row id.
 *
 * Used by:
 *   - POST /api/spark/briefs/generate (manual trigger, Q1)
 *   - scanner.ts cron hooks (auto-generation, Q2, not yet)
 */
import { dbQuery, dbExecute, num } from './db'
import { getRawQuotes, isConfigured as isTradierConfigured } from './tradier'

// ── Constants ──────────────────────────────────────────────────────────

const ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages'
const ANTHROPIC_MODEL = 'claude-sonnet-4-6'
const ANTHROPIC_MAX_TOKENS = 1400
const ANTHROPIC_VERSION = '2023-06-01'

// SPY underlying + VIX family — all free via Tradier /markets/quotes.
const QUOTE_SYMBOLS = ['SPY', 'VIX', 'VVIX', 'VIX9D', 'VIX3M', 'VIX6M']

// ── Types ──────────────────────────────────────────────────────────────

export type BriefType = 'morning' | 'intraday' | 'eod_debrief'

export interface MarketState {
  spy_price: number | null
  vix: number | null
  vvix: number | null
  vix9d: number | null
  vix3m: number | null
  vix6m: number | null
  /** vix3m / vix - 1. Positive = contango (calm); negative = backwardation (stress). */
  term_structure: number | null
  /** Convenience: label the structure regime in plain English for the prompt. */
  term_structure_label: 'contango' | 'backwardation' | 'flat' | 'unknown'
}

export interface PositionState {
  has_open_ic: boolean
  ticker: string | null
  expiration: string | null
  put_long: number | null
  put_short: number | null
  call_short: number | null
  call_long: number | null
  contracts: number | null
  entry_credit: number | null
  open_time: string | null
  person: string | null
  account_type: string | null
  /** distance from spot to short put as % of spot */
  pct_to_short_put: number | null
  /** distance from spot to short call as % of spot */
  pct_to_short_call: number | null
}

export interface RecentTrade {
  closed_at: string
  realized_pnl: number
  close_reason: string
  contracts: number
  credit: number
}

export interface BriefInputs {
  brief_type: BriefType
  ct_timestamp: string
  ct_hhmm: string
  market_state: MarketState
  position_state: PositionState
  recent_trades: RecentTrade[]
}

export interface ParsedBrief {
  risk_score: number | null
  factors: Array<{ title: string; detail: string }>
  summary: string
  watch_next_hour: string | null
  raw_text: string
}

// ── Input gathering ────────────────────────────────────────────────────

function ctNow(): Date {
  return new Date(new Date().toLocaleString('en-US', { timeZone: 'America/Chicago' }))
}
function ctHHMM(): string {
  return ctNow().toTimeString().slice(0, 5)
}

async function gatherMarketState(): Promise<MarketState> {
  if (!isTradierConfigured()) {
    return {
      spy_price: null, vix: null, vvix: null, vix9d: null,
      vix3m: null, vix6m: null, term_structure: null, term_structure_label: 'unknown',
    }
  }
  const quotes = await getRawQuotes(QUOTE_SYMBOLS).catch(() => ({} as Record<string, Record<string, unknown>>))
  const p = (sym: string): number | null => {
    const q = quotes[sym]
    if (!q) return null
    const rawLast = q.last
    const last = typeof rawLast === 'number'
      ? rawLast
      : (typeof rawLast === 'string' ? parseFloat(rawLast) : NaN)
    return Number.isFinite(last) ? last : null
  }
  const spy = p('SPY')
  const vix = p('VIX')
  const vix3m = p('VIX3M')
  const termStructure = (vix != null && vix3m != null && vix > 0)
    ? Math.round(((vix3m / vix) - 1) * 10000) / 10000
    : null
  const termLabel: MarketState['term_structure_label'] =
    termStructure == null ? 'unknown'
    : termStructure > 0.01 ? 'contango'
    : termStructure < -0.01 ? 'backwardation'
    : 'flat'
  return {
    spy_price: spy,
    vix,
    vvix: p('VVIX'),
    vix9d: p('VIX9D'),
    vix3m,
    vix6m: p('VIX6M'),
    term_structure: termStructure,
    term_structure_label: termLabel,
  }
}

async function gatherPositionState(spotPrice: number | null): Promise<PositionState> {
  // Production positions only — paper/sandbox contract counts don't represent
  // real-money risk and were polluting the brief (e.g. brief warned about a
  // 143-contract sandbox position when production held far less).
  const rows = await dbQuery(
    `SELECT position_id, ticker, expiration,
            put_long_strike, put_short_strike,
            call_short_strike, call_long_strike,
            contracts, total_credit, open_time, person, account_type
     FROM spark_positions
     WHERE status = 'open' AND dte_mode = '1DTE' AND account_type = 'production'
     ORDER BY open_time DESC NULLS LAST`,
  )
  if (rows.length === 0) {
    return {
      has_open_ic: false,
      ticker: null, expiration: null,
      put_long: null, put_short: null, call_short: null, call_long: null,
      contracts: null, entry_credit: null,
      open_time: null, person: null, account_type: null,
      pct_to_short_put: null, pct_to_short_call: null,
    }
  }
  const r = rows[0]
  const exp = r.expiration instanceof Date
    ? r.expiration.toISOString().slice(0, 10)
    : String(r.expiration).slice(0, 10)
  // Aggregate contracts across all open production ICs (multiple persons /
  // accounts can hold simultaneous production positions).
  const totalContracts = rows.reduce((sum, row) => sum + (Number(row.contracts) || 0), 0)
  // Credit-weighted average so the prompt sees a representative per-contract credit.
  const totalCreditDollars = rows.reduce(
    (sum, row) => sum + (num(row.total_credit) * (Number(row.contracts) || 0)),
    0,
  )
  const avgCredit = totalContracts > 0 ? totalCreditDollars / totalContracts : num(r.total_credit)
  const pctToShortPut = (spotPrice && r.put_short_strike)
    ? Math.round(((spotPrice - num(r.put_short_strike)) / spotPrice) * 10000) / 100
    : null
  const pctToShortCall = (spotPrice && r.call_short_strike)
    ? Math.round(((num(r.call_short_strike) - spotPrice) / spotPrice) * 10000) / 100
    : null
  return {
    has_open_ic: true,
    ticker: r.ticker || 'SPY',
    expiration: exp,
    put_long: num(r.put_long_strike),
    put_short: num(r.put_short_strike),
    call_short: num(r.call_short_strike),
    call_long: num(r.call_long_strike),
    contracts: totalContracts,
    entry_credit: avgCredit,
    open_time: r.open_time ? new Date(r.open_time).toISOString() : null,
    person: r.person ?? null,
    account_type: 'production',
    pct_to_short_put: pctToShortPut,
    pct_to_short_call: pctToShortCall,
  }
}

async function gatherRecentTrades(): Promise<RecentTrade[]> {
  const rows = await dbQuery(
    `SELECT close_time, realized_pnl, close_reason, contracts, total_credit
     FROM spark_positions
     WHERE status IN ('closed', 'expired')
       AND dte_mode = '1DTE'
       AND account_type = 'production'
       AND close_time >= NOW() - INTERVAL '7 days'
       AND realized_pnl IS NOT NULL
     ORDER BY close_time DESC
     LIMIT 10`,
  )
  return rows.map((r) => ({
    closed_at: r.close_time instanceof Date ? r.close_time.toISOString() : String(r.close_time),
    realized_pnl: num(r.realized_pnl),
    close_reason: r.close_reason || 'unknown',
    contracts: Number(r.contracts) || 0,
    credit: num(r.total_credit),
  }))
}

export async function gatherInputs(briefType: BriefType): Promise<BriefInputs> {
  const marketState = await gatherMarketState()
  const positionState = await gatherPositionState(marketState.spy_price)
  const recentTrades = await gatherRecentTrades()
  return {
    brief_type: briefType,
    ct_timestamp: ctNow().toISOString(),
    ct_hhmm: ctHHMM(),
    market_state: marketState,
    position_state: positionState,
    recent_trades: recentTrades,
  }
}

// ── Prompt builders ────────────────────────────────────────────────────

const SYSTEM_PROMPT = `You are a risk advisor for a beginner options trader running a 1DTE Iron Condor bot on SPY called SPARK.

Your audience is NEW to options. Assume they know what an Iron Condor is but may not know technical terms like VVIX, term structure, contango/backwardation, GEX. Whenever you use such a term, briefly define it inline in plain English.

ACCOUNT SCOPE: The "OPEN IRON CONDOR" and "RECENT SPARK TRADES" sections describe the LIVE PRODUCTION (real-money) account only. Do NOT speculate about, mention, or include contract counts from paper, sandbox, or any other account. If the prompt says no open production IC, do not invent one.

OUTPUT FORMATTING — STRICT:
- Plain text only. NO markdown formatting at all.
- Do NOT use **bold**, *italics*, _underscores_, backticks, or "---" separators.
- Do NOT wrap titles or numbers in asterisks. Write "Term Structure Contango" not "**Term Structure Contango**".
- Use em dashes ( — ) or plain hyphens for separators between title and detail.

For each risk factor you identify:
  1. State the factor as a short title in plain English
  2. Briefly define any technical term inline (e.g. "VVIX — the vol of vol")
  3. Explain WHY it matters specifically for an Iron Condor
  4. Tie it to the user's open production position (strikes, distance to break-evens) when one exists

Your response MUST follow this exact format:

RISK_SCORE: <integer 0-10>

FACTORS:
1. <short title> — <plain English detail tying it to the open production IC>
2. <short title> — <plain English detail>
3. <short title> — <plain English detail>

SUMMARY:
<2-4 sentence plain-English narrative>

WATCH_NEXT_HOUR:
<one sentence of what to watch for next hour>

Keep it under 600 words total. Educate while informing. Plain text only.`

function formatInputsForPrompt(i: BriefInputs): string {
  const m = i.market_state
  const p = i.position_state
  const lines: string[] = []
  lines.push(`BRIEF TYPE: ${i.brief_type}`)
  lines.push(`CURRENT TIME (CT): ${i.ct_hhmm} on ${i.ct_timestamp.slice(0, 10)}`)
  lines.push('')
  lines.push('MARKET STATE:')
  lines.push(`  SPY: ${m.spy_price != null ? `$${m.spy_price.toFixed(2)}` : 'n/a'}`)
  lines.push(`  VIX: ${m.vix != null ? m.vix.toFixed(2) : 'n/a'}`)
  lines.push(`  VVIX: ${m.vvix != null ? m.vvix.toFixed(2) : 'n/a'} (vol of vol)`)
  lines.push(`  VIX9D: ${m.vix9d != null ? m.vix9d.toFixed(2) : 'n/a'}  VIX3M: ${m.vix3m != null ? m.vix3m.toFixed(2) : 'n/a'}`)
  lines.push(`  Term structure: ${m.term_structure != null ? (m.term_structure * 100).toFixed(2) + '%' : 'n/a'} (${m.term_structure_label})`)
  lines.push('')
  if (p.has_open_ic) {
    lines.push('OPEN IRON CONDOR:')
    lines.push(`  ${p.contracts}x ${p.ticker} exp ${p.expiration}`)
    lines.push(`  Put wing: ${p.put_long} / ${p.put_short}  Call wing: ${p.call_short} / ${p.call_long}`)
    lines.push(`  Entry credit: $${(p.entry_credit ?? 0).toFixed(2)}/contract`)
    if (p.pct_to_short_put != null && p.pct_to_short_call != null) {
      lines.push(`  Distance to short put: ${p.pct_to_short_put.toFixed(2)}%  Distance to short call: ${p.pct_to_short_call.toFixed(2)}%`)
    }
    lines.push(`  Account: ${p.person ?? '?'} / ${p.account_type ?? '?'}`)
  } else {
    lines.push('OPEN IRON CONDOR: none (no open SPARK IC right now)')
  }
  lines.push('')
  lines.push('RECENT SPARK TRADES (last 7 days):')
  if (i.recent_trades.length === 0) {
    lines.push('  (no closed trades in last 7 days)')
  } else {
    for (const t of i.recent_trades.slice(0, 7)) {
      const date = t.closed_at.slice(0, 10)
      lines.push(`  ${date}: ${t.contracts}x IC, credit $${t.credit.toFixed(2)} → ${t.realized_pnl >= 0 ? '+' : ''}$${t.realized_pnl.toFixed(2)} (${t.close_reason})`)
    }
  }
  lines.push('')
  lines.push('STRATEGY REMINDER: SPARK sells 1DTE Iron Condors on SPY, aiming to ride the sliding PT tiers 50% → 30% → 20% of credit retained. Each trade risks up to 15% of the Iron Viper production account BP.')
  return lines.join('\n')
}

// ── Claude API ─────────────────────────────────────────────────────────

interface ClaudeAPIMessage {
  role: 'user' | 'assistant'
  content: string
}

async function callClaude(messages: ClaudeAPIMessage[]): Promise<{ text: string; model: string }> {
  const apiKey = process.env.CLAUDE_API_KEY || process.env.ANTHROPIC_API_KEY
  if (!apiKey) {
    throw new Error('CLAUDE_API_KEY env var is not set — add it to IronForge Render environment.')
  }
  const body = {
    model: ANTHROPIC_MODEL,
    max_tokens: ANTHROPIC_MAX_TOKENS,
    system: SYSTEM_PROMPT,
    messages,
  }
  const resp = await fetch(ANTHROPIC_API_URL, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'anthropic-version': ANTHROPIC_VERSION,
      'x-api-key': apiKey,
    },
    body: JSON.stringify(body),
  })
  if (!resp.ok) {
    const errText = await resp.text().catch(() => '<unreadable>')
    throw new Error(`Claude API ${resp.status}: ${errText.slice(0, 500)}`)
  }
  const data = await resp.json()
  const textBlocks = Array.isArray(data?.content) ? data.content : []
  const text = textBlocks.map((b: any) => b?.text ?? '').join('').trim()
  const model = String(data?.model ?? ANTHROPIC_MODEL)
  if (!text) throw new Error('Claude API returned empty content')
  return { text, model }
}

// ── Response parsing ───────────────────────────────────────────────────

/** Strip markdown emphasis so it doesn't render as raw `**foo**` in the UI.
 * Scrubs asterisks unconditionally — Claude sometimes returns unbalanced
 * markers like `**Title*` which a paired-only regex would miss. The brief
 * body is plain English narrative, so there is no legitimate asterisk to
 * preserve. */
function stripMarkdown(s: string): string {
  return s
    .replace(/\*+/g, '')                          // ALL asterisks (paired or stray)
    .replace(/__([^_]+)__/g, '$1')                 // __bold__
    .replace(/(?<!\w)_([^_\n]+)_(?!\w)/g, '$1')    // _italic_ (preserve snake_case)
    .replace(/`([^`]+)`/g, '$1')                   // `code`
    .replace(/^\s*-{3,}\s*$/gm, '')                // --- separator lines
    .replace(/\s+-{3,}\s*$/g, '')                  // trailing " ---" on a line
    .trim()
}

export function parseResponse(raw: string): ParsedBrief {
  const scoreMatch = raw.match(/RISK_SCORE:\s*(\d+)/i)
  const risk = scoreMatch ? Math.max(0, Math.min(10, parseInt(scoreMatch[1], 10))) : null

  const factorsBlockMatch = raw.match(/FACTORS:\s*([\s\S]*?)(?:SUMMARY:|WATCH_NEXT_HOUR:|$)/i)
  const factors: Array<{ title: string; detail: string }> = []
  if (factorsBlockMatch) {
    const lines = factorsBlockMatch[1].split('\n').map((l) => l.trim()).filter(Boolean)
    for (const ln of lines) {
      // expected: "1. Title - detail" or "- Title: detail"
      const m = ln.match(/^(?:\d+[\.\)]|-|\*)\s*([^-:]{1,80})[-:]\s*(.+)$/)
      if (m) {
        factors.push({ title: stripMarkdown(m[1]), detail: stripMarkdown(m[2]) })
      } else if (factors.length > 0) {
        // continuation line — append to previous detail
        factors[factors.length - 1].detail = stripMarkdown(
          factors[factors.length - 1].detail + ' ' + ln,
        )
      }
    }
  }

  const summaryMatch = raw.match(/SUMMARY:\s*([\s\S]*?)(?:WATCH_NEXT_HOUR:|$)/i)
  const summary = stripMarkdown((summaryMatch ? summaryMatch[1] : raw))

  const watchMatch = raw.match(/WATCH_NEXT_HOUR:\s*([\s\S]*?)$/i)
  const watch = watchMatch ? stripMarkdown(watchMatch[1]) : null

  return {
    risk_score: risk,
    factors,
    summary,
    watch_next_hour: watch,
    raw_text: raw,
  }
}

// ── Storage ────────────────────────────────────────────────────────────

export async function storeBrief(parsed: ParsedBrief, inputs: BriefInputs, model: string): Promise<number> {
  const ct = new Date(inputs.ct_timestamp)
  const briefDate = new Date(ct.toLocaleString('en-US', { timeZone: 'America/Chicago' }))
    .toISOString().slice(0, 10)
  const rows = await dbQuery(
    `INSERT INTO spark_market_briefs
      (brief_date, brief_type, risk_score, summary, factors_json, raw_inputs_json,
       spy_price, vix, vix3m, term_structure, model)
     VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8, $9, $10, $11)
     RETURNING id`,
    [
      briefDate,
      inputs.brief_type,
      parsed.risk_score,
      parsed.summary,
      JSON.stringify({ factors: parsed.factors, watch_next_hour: parsed.watch_next_hour, raw: parsed.raw_text }),
      JSON.stringify(inputs),
      inputs.market_state.spy_price,
      inputs.market_state.vix,
      inputs.market_state.vix3m,
      inputs.market_state.term_structure,
      model,
    ],
  )
  return Number(rows[0]?.id ?? 0)
}

// ── Public orchestrator ────────────────────────────────────────────────

export async function generateBrief(briefType: BriefType): Promise<{
  id: number
  brief: ParsedBrief
  inputs: BriefInputs
  model: string
}> {
  const inputs = await gatherInputs(briefType)
  const userContent = formatInputsForPrompt(inputs)
  const { text, model } = await callClaude([{ role: 'user', content: userContent }])
  const parsed = parseResponse(text)
  const id = await storeBrief(parsed, inputs, model)
  // Audit log (best effort) — store source marker so we can trace cost later.
  try {
    await dbExecute(
      `INSERT INTO spark_logs (level, message, details, dte_mode)
       VALUES ($1, $2, $3, $4)`,
      [
        'MARKET_BRIEF',
        `Brief #${id} (${briefType}) generated — risk_score=${parsed.risk_score ?? '?'}`,
        JSON.stringify({
          brief_id: id,
          brief_type: briefType,
          model,
          risk_score: parsed.risk_score,
          factor_count: parsed.factors.length,
        }),
        '1DTE',
      ],
    )
  } catch { /* best-effort */ }
  return { id, brief: parsed, inputs, model }
}
