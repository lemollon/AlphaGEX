# Forge Reports (Briefings) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a Claude-powered daily/weekly/monthly briefings system for IronForge's three bots + portfolio voice, with cross-day memory, a `/briefings` hub, calendar hover-preview integration, and 3-year retention.

**Architecture:** New `lib/forgeBriefings/*` module wraps the existing market-brief patterns. Scheduler tick fires from inside `scanner.ts` per-cycle; generator gathers DB + dashboard state + memory + macro context, calls Claude with a per-bot voice system prompt (cached), parses JSON, upserts to `forge_briefings`. UI is a hub (`/briefings`), detail (`/briefings/[id]`), archive, and codex pages, plus calendar badge + hover preview integration on the existing `CalendarMonthGrid`.

**Tech Stack:** Next.js 14 App Router, TypeScript, PostgreSQL via `pg`, Anthropic SDK (`@anthropic-ai/sdk` — same `CLAUDE_API_KEY` env var market-brief.ts uses), Vitest, Tailwind CSS, server-side PNG render via `@vercel/og` (already commonly available; install if missing).

**Spec:** `docs/superpowers/specs/2026-05-04-ironforge-forge-reports-design.md`

---

## File Map

**New files (`ironforge/webapp/`):**
- `src/lib/forgeBriefings/types.ts` — shared TypeScript interfaces
- `src/lib/forgeBriefings/halt-window.ts` — only if needed for FOMC-eve / post-event date math (reuses Vigil helpers if possible)
- `src/lib/forgeBriefings/voices.ts` — bot-specific system prompts + brief schema spec
- `src/lib/forgeBriefings/mood.ts` — rules-based mood classifier
- `src/lib/forgeBriefings/schema.ts` — JSON response validator
- `src/lib/forgeBriefings/context.ts` — gathers DB + dashboard + memory + macro
- `src/lib/forgeBriefings/repo.ts` — DB ops
- `src/lib/forgeBriefings/generate.ts` — orchestrator
- `src/lib/forgeBriefings/scheduler.ts` — `tick(now)` returns triggers to fire
- `src/lib/forgeBriefings/prune.ts` — 3-year retention
- `src/lib/forgeBriefings/png.ts` — server-side PNG export
- `src/lib/forgeBriefings/__tests__/*.test.ts` — unit tests
- `src/app/api/briefings/route.ts` — GET list
- `src/app/api/briefings/[id]/route.ts` — GET single
- `src/app/api/briefings/[id]/png/route.ts` — PNG download
- `src/app/api/briefings/generate/route.ts` — POST manual trigger
- `src/app/api/briefings/calendar-badges/route.ts` — date-range badges
- `src/app/briefings/page.tsx` — hub
- `src/app/briefings/[id]/page.tsx` — detail
- `src/app/briefings/archive/page.tsx` — archive
- `src/app/briefings/codex/page.tsx` — codex
- `src/components/BriefingCard.tsx` — main card
- `src/components/BriefingMacroRibbon.tsx`
- `src/components/BriefingTradeOfDay.tsx`
- `src/components/BriefingFactors.tsx`
- `src/components/BriefingWisdom.tsx`
- `src/components/BriefingMoodGlyph.tsx`
- `src/components/BriefingSparkline.tsx`
- `src/components/CalendarBriefBadge.tsx`
- `src/components/CalendarBriefMiniCard.tsx`
- `src/components/WeeklySynthesisHero.tsx`
- `public/glyph-mood-forged.svg`
- `public/glyph-mood-measured.svg`
- `public/glyph-mood-cooled.svg`
- `public/glyph-mood-burning.svg`
- `public/glyph-brief-badge.svg`

**Modified files:**
- `src/lib/db.ts` — add tables in `INIT_DDL` + per-bot ALTER in `ensureTables()`
- `src/lib/scanner.ts` — call `forgeBriefingsScheduler.tick()` once per cycle
- `src/components/CalendarMonthGrid.tsx` — render badge + hover preview
- `src/components/Nav.tsx` — add Briefings link
- `src/components/LatestBriefCard.tsx` — read from `forge_briefings` (with legacy fallback)

---

## Task 1: DB schema

**Files:**
- Modify: `ironforge/webapp/src/lib/db.ts`

- [ ] **Step 1:** Open `src/lib/db.ts`. Locate the INIT_DDL block where the Vigil `ironforge_event_calendar_meta` table is defined (around the `ironforge_event_calendar` block). Add the new tables immediately after, BEFORE the per-bot `' + ['flame', ...].map(...)` template:

```ts
CREATE TABLE IF NOT EXISTS forge_briefings (
  brief_id            TEXT PRIMARY KEY,
  bot                 TEXT NOT NULL,
  brief_type          TEXT NOT NULL,
  brief_date          DATE NOT NULL,
  brief_time          TIMESTAMPTZ NOT NULL,
  title               TEXT NOT NULL,
  summary             TEXT NOT NULL,
  wisdom              TEXT,
  risk_score          INT,
  mood                TEXT,
  bot_voice_signature TEXT,
  factors             JSONB,
  trade_of_day        JSONB,
  macro_ribbon        JSONB,
  sparkline_data      JSONB,
  prior_briefs_referenced TEXT[],
  codex_referenced    TEXT,
  model               TEXT,
  tokens_in           INT,
  tokens_out          INT,
  cost_usd            NUMERIC(8,4),
  generation_status   TEXT NOT NULL DEFAULT 'ok',
  is_active           BOOLEAN NOT NULL DEFAULT TRUE,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_forge_briefings_bot_date
  ON forge_briefings (bot, brief_date DESC) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_forge_briefings_type_date
  ON forge_briefings (brief_type, brief_date DESC) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_forge_briefings_lookup
  ON forge_briefings (bot, brief_type, brief_date) WHERE is_active = TRUE;
CREATE TABLE IF NOT EXISTS forge_briefings_meta (
  bot                 TEXT NOT NULL,
  brief_type          TEXT NOT NULL,
  last_run_ts         TIMESTAMPTZ,
  last_run_status     TEXT,
  last_brief_id       TEXT,
  retry_count         INT DEFAULT 0,
  PRIMARY KEY (bot, brief_type)
);
```

- [ ] **Step 2:** Inside `ensureTables()`, in the existing per-bot ALTER loop (where Vigil added `event_blackout_enabled`), add immediately after the Vigil ALTER:

```ts
try {
  await client.query(
    `ALTER TABLE ${bot}_config ADD COLUMN IF NOT EXISTS forge_briefings_enabled BOOLEAN NOT NULL DEFAULT TRUE`,
  )
} catch { /* column exists or table missing */ }
```

- [ ] **Step 3:** Verify TypeScript compiles:

```
cd ironforge/webapp && npx tsc --noEmit src/lib/db.ts 2>&1 | head -10
```

Expected: no output (clean).

- [ ] **Step 4:** Commit:

```
git add ironforge/webapp/src/lib/db.ts
git commit -m "feat(ironforge): add forge_briefings tables + per-bot toggle column"
```

---

## Task 2: Types + voices

**Files:**
- Create: `ironforge/webapp/src/lib/forgeBriefings/types.ts`
- Create: `ironforge/webapp/src/lib/forgeBriefings/voices.ts`
- Create: `ironforge/webapp/src/lib/forgeBriefings/__tests__/voices.test.ts`

- [ ] **Step 1:** Create `src/lib/forgeBriefings/types.ts`:

```ts
export type BotKey = 'flame' | 'spark' | 'inferno' | 'portfolio'
export type BriefType = 'daily_eod' | 'fomc_eve' | 'post_event' | 'weekly_synth' | 'codex_monthly'
export type Mood = 'forged' | 'measured' | 'cooled' | 'burning'

export interface Factor { rank: number; title: string; detail: string }

export interface TradeOfDay {
  position_id: string
  strikes: { ps: number; pl: number; cs?: number; cl?: number }
  entry_credit: number
  exit_cost: number
  contracts: number
  pnl: number
  payoff_points: Array<{ spot: number; pnl: number }>
}

export interface MacroRibbon {
  spy_open: number; spy_close: number; spy_range_pct: number; em_pct: number
  vix: number; vix_change: number; regime: string; pin_risk: 'Low' | 'Medium' | 'High'
}

export interface SparklinePoint { date: string; cumulative_pnl: number }

export interface ParsedBrief {
  title: string
  summary: string
  wisdom: string | null
  risk_score: number
  bot_voice_signature: string
  factors: Factor[]
  trade_of_day?: TradeOfDay | null
}

export interface BriefRow {
  brief_id: string
  bot: BotKey
  brief_type: BriefType
  brief_date: string
  brief_time: string | Date
  title: string
  summary: string
  wisdom: string | null
  risk_score: number | null
  mood: Mood | null
  bot_voice_signature: string | null
  factors: Factor[] | null
  trade_of_day: TradeOfDay | null
  macro_ribbon: MacroRibbon | null
  sparkline_data: SparklinePoint[] | null
  prior_briefs_referenced: string[] | null
  codex_referenced: string | null
  model: string | null
  tokens_in: number | null
  tokens_out: number | null
  cost_usd: number | null
  generation_status: string
  is_active: boolean
}

export interface GatheredContext {
  bot: BotKey
  brief_type: BriefType
  brief_date: string  // YYYY-MM-DD CT
  today_positions: any[]
  today_trades: any[]
  daily_perf: any
  equity_curve_7d: SparklinePoint[]
  dashboard_state: any | null
  macro: MacroRibbon
  memory_recent: Array<{ brief_id: string; brief_date: string; summary: string; wisdom: string | null }>
  memory_codex: { brief_id: string; summary: string } | null
  upcoming_blackout: { title: string; halt_start_ts: string; halt_end_ts: string } | null
  active_blackout: { title: string; halt_end_ts: string } | null
}
```

- [ ] **Step 2:** Create `src/lib/forgeBriefings/voices.ts`:

```ts
import type { BotKey, BriefType, GatheredContext } from './types'

const SCHEMA_INSTRUCTION = `
You MUST respond with a single JSON object matching this exact schema. No prose before or after.
{
  "title": string (max 80 chars, factual title for this brief),
  "bot_voice_signature": string (one-line opener in your bot voice; max 90 chars),
  "wisdom": string | null (one-line aphorism for the Forge Wisdom pull-quote; max 120 chars; null if no insight worth pulling),
  "risk_score": number (0-10 integer; how risky was today vs typical for this bot),
  "summary": string (2 paragraphs of prose, ~120-200 words total, in your bot voice),
  "factors": [
    { "rank": 1, "title": string (max 40 chars), "detail": string (max 200 chars) },
    ...up to 5 factors total, ranked by importance
  ],
  "trade_of_day": null | {
    "position_id": string,
    "strikes": { "ps": number, "pl": number, "cs": number|null, "cl": number|null },
    "entry_credit": number,
    "exit_cost": number,
    "contracts": number,
    "pnl": number,
    "payoff_points": [ {"spot": number, "pnl": number}, ... 5-9 points spanning the wings ]
  }
}
`

const FLAME_VOICE = `You are FLAME — the 2DTE Iron Condor / put-spread voice in the IronForge system. You are deliberate, measured, and patient. You speak like a banker who respects theta as a craftsman respects a tool. You frame outcomes in terms of patience paying off (or not). You never use exclamation points. You open every brief with a one-line signature beginning "The forge cools slowly..." or a close variant. You write in plain English; when you mention pin risk, the call wall, or theta decay, you treat them as forces, not jargon.`

const SPARK_VOICE = `You are SPARK — the 1DTE Iron Condor voice in the IronForge system. You are wry, professional, and precise. Plain English. Quick-witted but never glib. You respect pin risk and the call wall the way a seasoned poker player respects pot odds. You open every brief with a one-line signature beginning "A spark catches..." or a close variant. You count things explicitly (trades, dollars, percentage moves) — numbers are your scaffolding.`

const INFERNO_VOICE = `You are INFERNO — the 0DTE FORTRESS-style aggressive Iron Condor voice in the IronForge system. You are punchy, high-energy, and direct. War-room tone. Short sentences. You count trades and P&L explicitly. You acknowledge volatility and afternoon vol crush by name. You open every brief with a one-line signature beginning "The inferno burns..." or a close variant. You never sugarcoat losses, but you never panic either. The day is long; tomorrow is another battle.`

const MASTER_VOICE = `You are the Master of the Forge — the portfolio synthesis voice in the IronForge system. You synthesize FLAME, SPARK, and INFERNO. You quote them when their voices are distinctive. You look for cross-bot patterns: did all three bots agree on direction? Did one bot's risk score diverge from the other two? You open every brief with a one-line signature beginning "The forge speaks..." or a close variant. You are neutral in tone — informative, not opinionated.`

const VOICES: Record<BotKey, string> = {
  flame: FLAME_VOICE,
  spark: SPARK_VOICE,
  inferno: INFERNO_VOICE,
  portfolio: MASTER_VOICE,
}

const TYPE_INTRO: Record<BriefType, string> = {
  daily_eod: 'This is your end-of-day debrief. Today is now closed. Reflect on the day that was.',
  fomc_eve: 'This is your FOMC-eve preview. The blackout starts tomorrow. Consider what this week sets up.',
  post_event: 'This is your post-event debrief. The Vigil blackout has ended and the bots resume trading. Analyze the macro move that just happened and what it means for the days ahead.',
  weekly_synth: 'This is your weekly synthesis. Five trading days are now closed. Tell the story of the week.',
  codex_monthly: 'This is your monthly codex entry — a permanent long-memory summary. Distill the month into themes a future-you should remember a year from now. ~600 words.',
}

export function buildSystemPrompt(bot: BotKey, briefType: BriefType): string {
  const voice = VOICES[bot]
  const intro = TYPE_INTRO[briefType]
  return `${voice}\n\n${intro}\n\n${SCHEMA_INSTRUCTION}`
}

export function buildUserPrompt(ctx: GatheredContext): string {
  return `Context for today's brief:\n\n${JSON.stringify({
    bot: ctx.bot,
    brief_type: ctx.brief_type,
    brief_date: ctx.brief_date,
    today: {
      positions: ctx.today_positions,
      trades: ctx.today_trades,
      daily_perf: ctx.daily_perf,
    },
    dashboard_state: ctx.dashboard_state,
    macro: ctx.macro,
    equity_curve_7d: ctx.equity_curve_7d,
    memory: {
      recent_dailies: ctx.memory_recent,
      codex_long_memory: ctx.memory_codex,
    },
    calendar: {
      active_blackout: ctx.active_blackout,
      upcoming_blackout: ctx.upcoming_blackout,
    },
  }, null, 2)}`
}
```

- [ ] **Step 3:** Create `src/lib/forgeBriefings/__tests__/voices.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { buildSystemPrompt, buildUserPrompt } from '../voices'
import type { GatheredContext } from '../types'

describe('buildSystemPrompt', () => {
  it('includes the FLAME voice and the daily_eod intro', () => {
    const p = buildSystemPrompt('flame', 'daily_eod')
    expect(p).toContain('You are FLAME')
    expect(p).toContain('end-of-day debrief')
    expect(p).toContain('You MUST respond with a single JSON object')
  })

  it('uses the SPARK voice with weekly synth intro', () => {
    const p = buildSystemPrompt('spark', 'weekly_synth')
    expect(p).toContain('You are SPARK')
    expect(p).toContain('weekly synthesis')
  })

  it('uses the Master voice for portfolio briefs', () => {
    const p = buildSystemPrompt('portfolio', 'daily_eod')
    expect(p).toContain('Master of the Forge')
  })

  it('uses the codex monthly intro', () => {
    const p = buildSystemPrompt('inferno', 'codex_monthly')
    expect(p).toContain('You are INFERNO')
    expect(p).toContain('monthly codex')
  })
})

describe('buildUserPrompt', () => {
  it('serializes the context as JSON', () => {
    const ctx: GatheredContext = {
      bot: 'flame', brief_type: 'daily_eod', brief_date: '2026-05-04',
      today_positions: [], today_trades: [], daily_perf: { trades: 0 },
      equity_curve_7d: [], dashboard_state: null,
      macro: { spy_open: 587, spy_close: 588, spy_range_pct: 0.5, em_pct: 0.9, vix: 18, vix_change: -0.5, regime: 'Negative Gamma', pin_risk: 'Medium' },
      memory_recent: [], memory_codex: null,
      upcoming_blackout: null, active_blackout: null,
    }
    const p = buildUserPrompt(ctx)
    expect(p).toContain('"bot": "flame"')
    expect(p).toContain('"brief_date": "2026-05-04"')
    expect(p).toContain('"regime": "Negative Gamma"')
  })
})
```

- [ ] **Step 4:** Run tests:

```
cd ironforge/webapp && npx vitest run src/lib/forgeBriefings/__tests__/voices.test.ts
```

Expected: 5 tests pass.

- [ ] **Step 5:** Commit:

```
git add ironforge/webapp/src/lib/forgeBriefings/types.ts \
        ironforge/webapp/src/lib/forgeBriefings/voices.ts \
        ironforge/webapp/src/lib/forgeBriefings/__tests__/voices.test.ts
git commit -m "feat(ironforge): forge briefings types + per-bot voice prompts"
```

---

## Task 3: Mood classifier (TDD)

**Files:**
- Create: `ironforge/webapp/src/lib/forgeBriefings/mood.ts`
- Create: `ironforge/webapp/src/lib/forgeBriefings/__tests__/mood.test.ts`

- [ ] **Step 1:** Write the failing test:

```ts
// __tests__/mood.test.ts
import { describe, it, expect } from 'vitest'
import { classifyMood } from '../mood'

describe('classifyMood', () => {
  it('returns "forged" when P&L >= 80% of max profit and risk <= 4', () => {
    expect(classifyMood({ pnl_pct_of_target: 0.85, risk_score: 3, trade_count: 1 })).toBe('forged')
  })

  it('returns "burning" when risk_score >= 7 regardless of P&L', () => {
    expect(classifyMood({ pnl_pct_of_target: 0.5, risk_score: 8, trade_count: 1 })).toBe('burning')
  })

  it('returns "burning" when trade_count >= 3 (high activity)', () => {
    expect(classifyMood({ pnl_pct_of_target: 0.2, risk_score: 5, trade_count: 4 })).toBe('burning')
  })

  it('returns "cooled" when -100% < P&L <= -50% of target', () => {
    expect(classifyMood({ pnl_pct_of_target: -0.6, risk_score: 5, trade_count: 1 })).toBe('cooled')
  })

  it('returns "measured" for the default middle band', () => {
    expect(classifyMood({ pnl_pct_of_target: 0.3, risk_score: 5, trade_count: 1 })).toBe('measured')
    expect(classifyMood({ pnl_pct_of_target: -0.2, risk_score: 4, trade_count: 1 })).toBe('measured')
  })

  it('returns "measured" for zero-trade days', () => {
    expect(classifyMood({ pnl_pct_of_target: 0, risk_score: 0, trade_count: 0 })).toBe('measured')
  })
})
```

- [ ] **Step 2:** Run to confirm fail:

```
cd ironforge/webapp && npx vitest run src/lib/forgeBriefings/__tests__/mood.test.ts
```

Expected: FAIL — module not found.

- [ ] **Step 3:** Implement `src/lib/forgeBriefings/mood.ts`:

```ts
import type { Mood } from './types'

export interface MoodInput {
  pnl_pct_of_target: number   // e.g. 0.85 means 85% of max profit captured (or -0.6 = 60% of stop hit)
  risk_score: number          // 0-10
  trade_count: number
}

export function classifyMood(input: MoodInput): Mood {
  // High activity OR high risk → burning (trumps P&L)
  if (input.risk_score >= 7) return 'burning'
  if (input.trade_count >= 3) return 'burning'
  // Strong win + calm conditions → forged
  if (input.pnl_pct_of_target >= 0.8 && input.risk_score <= 4) return 'forged'
  // Significant loss but not blown → cooled
  if (input.pnl_pct_of_target <= -0.5 && input.pnl_pct_of_target > -1.0) return 'cooled'
  // Default middle band
  return 'measured'
}
```

- [ ] **Step 4:** Run tests:

```
cd ironforge/webapp && npx vitest run src/lib/forgeBriefings/__tests__/mood.test.ts
```

Expected: 6 tests pass.

- [ ] **Step 5:** Commit:

```
git add ironforge/webapp/src/lib/forgeBriefings/mood.ts \
        ironforge/webapp/src/lib/forgeBriefings/__tests__/mood.test.ts
git commit -m "feat(ironforge): forge briefings mood classifier"
```

---

## Task 4: JSON schema validator (TDD)

**Files:**
- Create: `ironforge/webapp/src/lib/forgeBriefings/schema.ts`
- Create: `ironforge/webapp/src/lib/forgeBriefings/__tests__/schema.test.ts`

- [ ] **Step 1:** Write the failing test:

```ts
// __tests__/schema.test.ts
import { describe, it, expect } from 'vitest'
import { parseBriefResponse } from '../schema'

const VALID = {
  title: 'FLAME — Day in the Forge',
  bot_voice_signature: 'The forge cools slowly, but it cools.',
  wisdom: 'Theta does its work whether you watch or not.',
  risk_score: 5,
  summary: 'Para 1.\n\nPara 2.',
  factors: [
    { rank: 1, title: 'Pin gravity at 587', detail: 'SPY hugged 587 from open to close.' },
    { rank: 2, title: 'VIX cooled', detail: 'VIX dropped 0.7 on the day.' },
  ],
  trade_of_day: {
    position_id: 'pos-1', strikes: { ps: 582, pl: 577, cs: 595, cl: 600 },
    entry_credit: 1.20, exit_cost: 0.36, contracts: 5, pnl: 420,
    payoff_points: [{ spot: 575, pnl: -800 }, { spot: 587, pnl: 420 }, { spot: 600, pnl: -800 }],
  },
}

describe('parseBriefResponse', () => {
  it('parses a valid response wrapped in JSON', () => {
    const r = parseBriefResponse(JSON.stringify(VALID))
    expect(r.ok).toBe(true)
    if (r.ok) expect(r.brief.title).toBe('FLAME — Day in the Forge')
  })

  it('strips markdown code fences if Claude wraps the JSON', () => {
    const wrapped = '```json\n' + JSON.stringify(VALID) + '\n```'
    const r = parseBriefResponse(wrapped)
    expect(r.ok).toBe(true)
  })

  it('rejects when title is missing', () => {
    const bad = { ...VALID, title: undefined }
    const r = parseBriefResponse(JSON.stringify(bad))
    expect(r.ok).toBe(false)
  })

  it('rejects when risk_score is not 0-10', () => {
    const bad = { ...VALID, risk_score: 15 }
    const r = parseBriefResponse(JSON.stringify(bad))
    expect(r.ok).toBe(false)
  })

  it('accepts trade_of_day === null', () => {
    const noTrade = { ...VALID, trade_of_day: null }
    const r = parseBriefResponse(JSON.stringify(noTrade))
    expect(r.ok).toBe(true)
  })

  it('rejects unparseable strings', () => {
    expect(parseBriefResponse('not json').ok).toBe(false)
    expect(parseBriefResponse('').ok).toBe(false)
  })
})
```

- [ ] **Step 2:** Run to confirm fail.

- [ ] **Step 3:** Implement `src/lib/forgeBriefings/schema.ts`:

```ts
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
```

- [ ] **Step 4:** Run tests. Expected: 6 pass.

- [ ] **Step 5:** Commit:

```
git add ironforge/webapp/src/lib/forgeBriefings/schema.ts \
        ironforge/webapp/src/lib/forgeBriefings/__tests__/schema.test.ts
git commit -m "feat(ironforge): forge briefings JSON response schema validator"
```

---

## Task 5: Repo (DB ops)

**Files:**
- Create: `ironforge/webapp/src/lib/forgeBriefings/repo.ts`

- [ ] **Step 1:** Write `src/lib/forgeBriefings/repo.ts`:

```ts
import { query, dbExecute } from '../db'
import type { BriefRow, BotKey, BriefType, ParsedBrief, MacroRibbon, SparklinePoint, Mood } from './types'

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
  return rows[0] ?? null
}

export async function existsOk(briefId: string): Promise<boolean> {
  const rows = await query<{ ok: boolean }>(
    `SELECT (generation_status = 'ok') AS ok FROM forge_briefings WHERE brief_id = $1 AND is_active = TRUE`,
    [briefId],
  )
  return rows[0]?.ok === true
}

export async function listForBot(bot: BotKey, briefType: BriefType, limit: number): Promise<BriefRow[]> {
  return query<BriefRow>(
    `SELECT * FROM forge_briefings
     WHERE bot = $1 AND brief_type = $2 AND is_active = TRUE
     ORDER BY brief_date DESC LIMIT $3`,
    [bot, briefType, limit],
  )
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
  return query<BriefRow>(
    `SELECT * FROM forge_briefings WHERE ${where.join(' AND ')}
     ORDER BY brief_date DESC, brief_time DESC
     LIMIT $${idx++} OFFSET $${idx++}`,
    params,
  )
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
  return rows
}

export async function setRetryPending(bot: BotKey, briefType: BriefType): Promise<void> {
  await dbExecute(`
    INSERT INTO forge_briefings_meta (bot, brief_type, last_run_ts, last_run_status, retry_count)
    VALUES ($1, $2, NOW(), 'retry_pending', 1)
    ON CONFLICT (bot, brief_type) DO UPDATE SET
      last_run_ts = NOW(), last_run_status = 'retry_pending',
      retry_count = forge_briefings_meta.retry_count + 1
  `, [bot, briefType])
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
```

- [ ] **Step 2:** Type-check:

```
cd ironforge/webapp && npx tsc --noEmit 2>&1 | grep "forgeBriefings/repo" | head -5
```

Expected: no output.

- [ ] **Step 3:** Commit:

```
git add ironforge/webapp/src/lib/forgeBriefings/repo.ts
git commit -m "feat(ironforge): forge briefings repo (DB ops)"
```

---

## Task 6: Context gather

**Files:**
- Create: `ironforge/webapp/src/lib/forgeBriefings/context.ts`

This module is large but boring SQL/fetch glue. It's wired together by the generator (Task 7) so we'll smoke-test it via that integration.

- [ ] **Step 1:** Write `src/lib/forgeBriefings/context.ts`:

```ts
import { query } from '../db'
import { getRawQuotes } from '../tradier'
import { listForBot } from './repo'
import type { BotKey, BriefType, GatheredContext, MacroRibbon, SparklinePoint } from './types'

const PER_BOT_DTE: Record<Exclude<BotKey, 'portfolio'>, string> = {
  flame: '2DTE', spark: '1DTE', inferno: '0DTE',
}

function num(v: any): number {
  if (v == null || v === '') return 0
  const n = parseFloat(v)
  return isNaN(n) ? 0 : n
}

async function fetchDashboardState(bot: Exclude<BotKey, 'portfolio'>, baseUrl: string): Promise<any | null> {
  try {
    const [statusR, posR, perfR] = await Promise.all([
      fetch(`${baseUrl}/api/${bot}/status`).then(r => r.ok ? r.json() : null).catch(() => null),
      fetch(`${baseUrl}/api/${bot}/positions`).then(r => r.ok ? r.json() : null).catch(() => null),
      fetch(`${baseUrl}/api/${bot}/performance`).then(r => r.ok ? r.json() : null).catch(() => null),
    ])
    if (!statusR && !posR && !perfR) return null
    return { status: statusR, positions: posR, performance: perfR }
  } catch {
    return null
  }
}

async function fetchMacroRibbon(): Promise<MacroRibbon> {
  const fallback: MacroRibbon = {
    spy_open: 0, spy_close: 0, spy_range_pct: 0, em_pct: 0,
    vix: 0, vix_change: 0, regime: 'Unknown', pin_risk: 'Medium',
  }
  try {
    const q = await getRawQuotes(['SPY', 'VIX', 'VIX3M'])
    const spy = q['SPY'] as any
    const vix = q['VIX'] as any
    const vix3m = q['VIX3M'] as any
    const spyOpen = num(spy?.open)
    const spyClose = num(spy?.last)
    const spyHigh = num(spy?.high)
    const spyLow  = num(spy?.low)
    const range = spyClose > 0 ? ((spyHigh - spyLow) / spyClose) * 100 : 0
    const vixVal = num(vix?.last)
    const vixChange = num(vix?.change)
    const em = spyClose > 0 ? (vixVal / 100 / Math.sqrt(252)) * 100 : 0
    const ts = num(vix3m?.last) > 0 && vixVal > 0 ? (num(vix3m.last) / vixVal - 1) : 0
    const regime = ts > 0.05 ? 'Negative Gamma' : ts < -0.05 ? 'Positive Gamma' : 'Mixed Gamma'
    const pin: 'Low' | 'Medium' | 'High' = vixVal < 14 ? 'High' : vixVal < 22 ? 'Medium' : 'Low'
    return {
      spy_open: spyOpen, spy_close: spyClose, spy_range_pct: +range.toFixed(2),
      em_pct: +em.toFixed(2), vix: +vixVal.toFixed(2), vix_change: +vixChange.toFixed(2),
      regime, pin_risk: pin,
    }
  } catch {
    return fallback
  }
}

async function fetchEquityCurve7d(bot: Exclude<BotKey, 'portfolio'>): Promise<SparklinePoint[]> {
  const rows = await query<any>(`
    SELECT (close_time AT TIME ZONE 'America/Chicago')::date AS d,
           SUM(realized_pnl) AS day_pnl
    FROM ${bot}_positions
    WHERE status IN ('closed', 'expired')
      AND close_time >= NOW() - INTERVAL '7 days'
    GROUP BY d ORDER BY d ASC
  `)
  let cum = 0
  return rows.map(r => {
    cum += num(r.day_pnl)
    return { date: r.d?.toISOString?.()?.slice(0, 10) ?? String(r.d), cumulative_pnl: +cum.toFixed(2) }
  })
}

async function fetchTodayContext(bot: Exclude<BotKey, 'portfolio'>): Promise<{ today_positions: any[]; today_trades: any[]; daily_perf: any }> {
  const dte = PER_BOT_DTE[bot]
  const [positions, trades, perf] = await Promise.all([
    query(`SELECT position_id, status, put_short_strike, put_long_strike, call_short_strike, call_long_strike,
                  total_credit, contracts, realized_pnl, close_reason, open_time, close_time
           FROM ${bot}_positions
           WHERE (open_time AT TIME ZONE 'America/Chicago')::date = (NOW() AT TIME ZONE 'America/Chicago')::date
             AND dte_mode = $1`,
          [dte]),
    query(`SELECT position_id, total_credit, realized_pnl, close_reason, contracts
           FROM ${bot}_positions
           WHERE status IN ('closed','expired')
             AND (close_time AT TIME ZONE 'America/Chicago')::date = (NOW() AT TIME ZONE 'America/Chicago')::date
             AND dte_mode = $1`,
          [dte]),
    query(`SELECT * FROM ${bot}_daily_perf
           WHERE trade_date = (NOW() AT TIME ZONE 'America/Chicago')::date LIMIT 1`),
  ])
  return { today_positions: positions, today_trades: trades, daily_perf: perf[0] ?? null }
}

async function fetchMemory(bot: BotKey): Promise<{
  memory_recent: GatheredContext['memory_recent']; memory_codex: GatheredContext['memory_codex']
}> {
  const recent = await listForBot(bot, 'daily_eod', 5)
  const codex = await listForBot(bot, 'codex_monthly', 1)
  return {
    memory_recent: recent.map(r => ({
      brief_id: r.brief_id, brief_date: String(r.brief_date),
      summary: r.summary, wisdom: r.wisdom,
    })),
    memory_codex: codex[0] ? { brief_id: codex[0].brief_id, summary: codex[0].summary } : null,
  }
}

async function fetchCalendarContext(): Promise<{
  active_blackout: GatheredContext['active_blackout']; upcoming_blackout: GatheredContext['upcoming_blackout']
}> {
  const active = await query<any>(`
    SELECT title, halt_end_ts FROM ironforge_event_calendar
    WHERE is_active = TRUE AND NOW() BETWEEN halt_start_ts AND halt_end_ts
    ORDER BY halt_end_ts ASC LIMIT 1
  `)
  const upcoming = await query<any>(`
    SELECT title, halt_start_ts, halt_end_ts FROM ironforge_event_calendar
    WHERE is_active = TRUE AND halt_start_ts > NOW()
    ORDER BY halt_start_ts ASC LIMIT 1
  `)
  return {
    active_blackout: active[0] ? { title: active[0].title, halt_end_ts: active[0].halt_end_ts } : null,
    upcoming_blackout: upcoming[0] ? {
      title: upcoming[0].title, halt_start_ts: upcoming[0].halt_start_ts, halt_end_ts: upcoming[0].halt_end_ts,
    } : null,
  }
}

export async function gatherContext(opts: {
  bot: BotKey; brief_type: BriefType; brief_date: string; baseUrl: string
}): Promise<GatheredContext> {
  const macro = await fetchMacroRibbon()
  const calendar = await fetchCalendarContext()

  if (opts.bot === 'portfolio') {
    // Portfolio gathers each per-bot slice in parallel and merges
    const subs = await Promise.all((['flame', 'spark', 'inferno'] as const).map(async b => ({
      bot: b,
      ...(await fetchTodayContext(b)),
      equity_curve_7d: await fetchEquityCurve7d(b),
      dashboard_state: await fetchDashboardState(b, opts.baseUrl),
    })))
    const memory = await fetchMemory('portfolio')
    return {
      bot: 'portfolio', brief_type: opts.brief_type, brief_date: opts.brief_date,
      today_positions: subs.flatMap(s => s.today_positions.map((p: any) => ({ ...p, _bot: s.bot }))),
      today_trades: subs.flatMap(s => s.today_trades.map((t: any) => ({ ...t, _bot: s.bot }))),
      daily_perf: { per_bot: subs.map(s => ({ bot: s.bot, daily_perf: s.daily_perf })) },
      equity_curve_7d: [], // portfolio sparkline computed separately on UI
      dashboard_state: { per_bot: subs.map(s => ({ bot: s.bot, ...s.dashboard_state })) },
      macro,
      memory_recent: memory.memory_recent, memory_codex: memory.memory_codex,
      active_blackout: calendar.active_blackout, upcoming_blackout: calendar.upcoming_blackout,
    }
  }

  const [today, equity, dashboard, memory] = await Promise.all([
    fetchTodayContext(opts.bot),
    fetchEquityCurve7d(opts.bot),
    fetchDashboardState(opts.bot, opts.baseUrl),
    fetchMemory(opts.bot),
  ])
  return {
    bot: opts.bot, brief_type: opts.brief_type, brief_date: opts.brief_date,
    today_positions: today.today_positions, today_trades: today.today_trades, daily_perf: today.daily_perf,
    equity_curve_7d: equity, dashboard_state: dashboard, macro,
    memory_recent: memory.memory_recent, memory_codex: memory.memory_codex,
    active_blackout: calendar.active_blackout, upcoming_blackout: calendar.upcoming_blackout,
  }
}
```

- [ ] **Step 2:** Type-check:

```
cd ironforge/webapp && npx tsc --noEmit 2>&1 | grep "forgeBriefings/context" | head -5
```

Expected: no output.

- [ ] **Step 3:** Commit:

```
git add ironforge/webapp/src/lib/forgeBriefings/context.ts
git commit -m "feat(ironforge): forge briefings context gatherer (DB + dashboard + memory + macro)"
```

---

## Task 7: Generator (Claude orchestrator)

**Files:**
- Create: `ironforge/webapp/src/lib/forgeBriefings/generate.ts`

- [ ] **Step 1:** Write `src/lib/forgeBriefings/generate.ts`:

```ts
import { gatherContext } from './context'
import { buildSystemPrompt, buildUserPrompt } from './voices'
import { parseBriefResponse } from './schema'
import { classifyMood } from './mood'
import { upsertBrief, existsOk, setMetaOk, setMetaError } from './repo'
import type { BotKey, BriefType, MoodInput as _MoodInput } from './types'

const ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages'
const ANTHROPIC_MODEL = 'claude-sonnet-4-6'
const ANTHROPIC_VERSION = '2023-06-01'

interface GenerateOpts {
  bot: BotKey
  brief_type: BriefType
  brief_date: string  // YYYY-MM-DD
  baseUrl: string     // e.g. http://localhost:3000 (server-side)
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
  // Sonnet 4.6 pricing: $3/MTok in, $15/MTok out (cached input ~$0.30/MTok)
  const cost_usd = (tokens_in / 1_000_000) * 3 + (tokens_out / 1_000_000) * 15
  return { text, model: json.model ?? ANTHROPIC_MODEL, tokens_in, tokens_out, cost_usd: +cost_usd.toFixed(4) }
}

export async function generateBrief(opts: GenerateOpts): Promise<GenerateResult> {
  const brief_id = deterministicId(opts.bot, opts.brief_type, opts.brief_date)

  if (!opts.force && await existsOk(brief_id)) {
    return { ok: true, brief_id, status: 'skipped_idempotent' }
  }

  // Per-bot toggle (skip portfolio)
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
```

- [ ] **Step 2:** Type-check:

```
cd ironforge/webapp && npx tsc --noEmit 2>&1 | grep "forgeBriefings/generate" | head -5
```

Expected: no output.

- [ ] **Step 3:** Commit:

```
git add ironforge/webapp/src/lib/forgeBriefings/generate.ts
git commit -m "feat(ironforge): forge briefings generator (Claude orchestrator)"
```

---

## Task 8: Scheduler (TDD)

**Files:**
- Create: `ironforge/webapp/src/lib/forgeBriefings/scheduler.ts`
- Create: `ironforge/webapp/src/lib/forgeBriefings/__tests__/scheduler.test.ts`

- [ ] **Step 1:** Write the failing tests:

```ts
// __tests__/scheduler.test.ts
import { describe, it, expect } from 'vitest'
import { decideTriggers } from '../scheduler'

function ct(iso: string): Date {
  return new Date(iso) // assume tests use ISO with Z suffix
}

describe('decideTriggers — daily EOD', () => {
  it('fires daily_eod for all 3 bots + portfolio at 15:30 CT on a weekday', () => {
    // 15:30 CDT (DST) = 20:30 UTC on a Mon
    const t = decideTriggers(new Date('2026-05-04T20:30:00Z'), [], [])
    const types = t.map(x => `${x.bot}:${x.brief_type}`)
    expect(types).toContain('flame:daily_eod')
    expect(types).toContain('spark:daily_eod')
    expect(types).toContain('inferno:daily_eod')
    expect(types).toContain('portfolio:daily_eod')
  })

  it('does NOT fire daily_eod at 15:29 CT', () => {
    // 15:29 CDT = 20:29 UTC
    const t = decideTriggers(new Date('2026-05-04T20:29:00Z'), [], [])
    expect(t.find(x => x.brief_type === 'daily_eod')).toBeUndefined()
  })

  it('does NOT fire on weekends', () => {
    // Saturday 15:30 CDT = 20:30 UTC
    const t = decideTriggers(new Date('2026-05-09T20:30:00Z'), [], [])
    expect(t.length).toBe(0)
  })

  it('fires within a tolerance window 15:30-15:34 (so a 1-min scanner doesn\'t miss the slot)', () => {
    const t1 = decideTriggers(new Date('2026-05-04T20:31:00Z'), [], [])
    const t2 = decideTriggers(new Date('2026-05-04T20:34:00Z'), [], [])
    const t3 = decideTriggers(new Date('2026-05-04T20:35:00Z'), [], [])
    expect(t1.find(x => x.brief_type === 'daily_eod')).toBeDefined()
    expect(t2.find(x => x.brief_type === 'daily_eod')).toBeDefined()
    expect(t3.find(x => x.brief_type === 'daily_eod')).toBeUndefined()
  })
})

describe('decideTriggers — weekly', () => {
  it('fires weekly_synth on Friday at 16:00 CT for all bots + portfolio', () => {
    // Fri 16:00 CDT = 21:00 UTC
    const t = decideTriggers(new Date('2026-05-08T21:00:00Z'), [], [])
    const types = t.map(x => `${x.bot}:${x.brief_type}`)
    expect(types).toContain('flame:weekly_synth')
    expect(types).toContain('portfolio:weekly_synth')
  })

  it('does NOT fire weekly_synth on Thursday', () => {
    const t = decideTriggers(new Date('2026-05-07T21:00:00Z'), [], [])
    expect(t.find(x => x.brief_type === 'weekly_synth')).toBeUndefined()
  })
})

describe('decideTriggers — codex monthly', () => {
  it('fires codex_monthly on the last business day of the month at 17:00 CT', () => {
    // Fri May 29 2026 is the last business day of May (May 30=Sat, 31=Sun)
    // 17:00 CDT = 22:00 UTC
    const t = decideTriggers(new Date('2026-05-29T22:00:00Z'), [], [])
    const types = t.map(x => `${x.bot}:${x.brief_type}`)
    expect(types).toContain('flame:codex_monthly')
    expect(types).toContain('portfolio:codex_monthly')
  })

  it('does NOT fire codex on the first day of the next month', () => {
    // Mon Jun 1 2026 17:00 CDT = 22:00 UTC
    const t = decideTriggers(new Date('2026-06-01T22:00:00Z'), [], [])
    expect(t.find(x => x.brief_type === 'codex_monthly')).toBeUndefined()
  })
})

describe('decideTriggers — fomc_eve', () => {
  it('fires fomc_eve on the Thursday before an upcoming Wed FOMC at 15:35 CT', () => {
    // Wed Jun 18 2025 FOMC; Thursday before = Jun 12; 15:35 CDT = 20:35 UTC
    const upcoming = [{ event_date: '2025-06-18', halt_start_ts: '2025-06-13T13:30:00Z' }]
    const t = decideTriggers(new Date('2025-06-12T20:35:00Z'), upcoming, [])
    expect(t.find(x => x.brief_type === 'fomc_eve' && x.bot === 'flame')).toBeDefined()
  })
})

describe('decideTriggers — post_event', () => {
  it('fires post_event the day after a halt_end_ts at 09:00 CT', () => {
    // Wed Jun 18 2025 halt_end at 19:00 UTC. Next morning Thu Jun 19 09:00 CDT = 14:00 UTC.
    const recentlyEnded = [{ halt_end_ts: '2025-06-18T19:00:00Z', event_date: '2025-06-18' }]
    const t = decideTriggers(new Date('2025-06-19T14:00:00Z'), [], recentlyEnded)
    expect(t.find(x => x.brief_type === 'post_event' && x.bot === 'spark')).toBeDefined()
  })
})
```

- [ ] **Step 2:** Run to confirm fail.

- [ ] **Step 3:** Implement `src/lib/forgeBriefings/scheduler.ts`:

```ts
import type { BotKey, BriefType } from './types'

const PER_BOTS: BotKey[] = ['flame', 'spark', 'inferno']

export interface Trigger { bot: BotKey; brief_type: BriefType; brief_date: string }

export interface UpcomingEvent { event_date: string; halt_start_ts: string }
export interface RecentlyEndedEvent { event_date: string; halt_end_ts: string }

function ctParts(now: Date): { y: number; m: number; d: number; dow: number; hhmm: number; ymd: string } {
  const dtf = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Chicago',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', weekday: 'short', hour12: false,
  })
  const parts = dtf.formatToParts(now).reduce((acc, p) => {
    if (p.type !== 'literal') acc[p.type] = p.value
    return acc
  }, {} as Record<string, string>)
  const y = parseInt(parts.year)
  const m = parseInt(parts.month)
  const d = parseInt(parts.day)
  const hh = parseInt(parts.hour === '24' ? '0' : parts.hour)
  const mm = parseInt(parts.minute)
  const dowMap: Record<string, number> = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 }
  const dow = dowMap[parts.weekday] ?? 0
  return {
    y, m, d, dow, hhmm: hh * 100 + mm,
    ymd: `${parts.year}-${parts.month}-${parts.day}`,
  }
}

function inWindow(hhmm: number, startInclusive: number, endInclusive: number): boolean {
  return hhmm >= startInclusive && hhmm <= endInclusive
}

function isLastBusinessDayOfMonth(y: number, m: number, d: number, dow: number): boolean {
  // Walk forward day-by-day; if all subsequent days in the month are weekend, this is the last business day.
  if (dow === 0 || dow === 6) return false  // weekend itself is never a business day
  const daysInMonth = new Date(Date.UTC(y, m, 0)).getUTCDate()  // Date(year, month) — month is 1-indexed here means next month, so day 0 = last day of m
  for (let next = d + 1; next <= daysInMonth; next++) {
    const nd = new Date(Date.UTC(y, m - 1, next)).getUTCDay()
    if (nd >= 1 && nd <= 5) return false
  }
  return true
}

function thursdayBefore(eventDate: string): string {
  // Returns YYYY-MM-DD of the Thursday strictly before eventDate
  const [y, mo, d] = eventDate.split('-').map(Number)
  const dt = new Date(Date.UTC(y, mo - 1, d))
  const dow = dt.getUTCDay() // 0=Sun..6=Sat
  // Days to subtract to reach Thursday (4)
  let back: number
  if (dow === 4) back = 7        // event is Thu → previous Thu
  else if (dow > 4) back = dow - 4  // Fri→1, Sat→2
  else back = dow + 3            // Sun→3, Mon→4, Tue→5, Wed→6
  dt.setUTCDate(dt.getUTCDate() - back)
  return `${dt.getUTCFullYear()}-${String(dt.getUTCMonth() + 1).padStart(2, '0')}-${String(dt.getUTCDate()).padStart(2, '0')}`
}

function dayAfter(dateStr: string): string {
  const [y, mo, d] = dateStr.split('-').map(Number)
  const dt = new Date(Date.UTC(y, mo - 1, d))
  dt.setUTCDate(dt.getUTCDate() + 1)
  return `${dt.getUTCFullYear()}-${String(dt.getUTCMonth() + 1).padStart(2, '0')}-${String(dt.getUTCDate()).padStart(2, '0')}`
}

export function decideTriggers(
  now: Date,
  upcomingEvents: UpcomingEvent[],
  recentlyEndedEvents: RecentlyEndedEvent[],
): Trigger[] {
  const ct = ctParts(now)
  const out: Trigger[] = []

  // Skip weekends entirely (except codex which handles its own day check)
  const isWeekend = ct.dow === 0 || ct.dow === 6

  // 1. Daily EOD — Mon-Fri 15:30-15:34 CT
  if (!isWeekend && inWindow(ct.hhmm, 1530, 1534)) {
    for (const bot of PER_BOTS) out.push({ bot, brief_type: 'daily_eod', brief_date: ct.ymd })
    out.push({ bot: 'portfolio', brief_type: 'daily_eod', brief_date: ct.ymd })
  }

  // 2. Weekly synth — Friday 16:00-16:04 CT
  if (ct.dow === 5 && inWindow(ct.hhmm, 1600, 1604)) {
    for (const bot of PER_BOTS) out.push({ bot, brief_type: 'weekly_synth', brief_date: ct.ymd })
    out.push({ bot: 'portfolio', brief_type: 'weekly_synth', brief_date: ct.ymd })
  }

  // 3. Codex monthly — last business day 17:00-17:04 CT
  if (isLastBusinessDayOfMonth(ct.y, ct.m, ct.d, ct.dow) && inWindow(ct.hhmm, 1700, 1704)) {
    for (const bot of PER_BOTS) out.push({ bot, brief_type: 'codex_monthly', brief_date: ct.ymd })
    out.push({ bot: 'portfolio', brief_type: 'codex_monthly', brief_date: ct.ymd })
  }

  // 4. FOMC eve — Thursday before each upcoming FOMC, 15:35-15:39 CT
  if (!isWeekend && inWindow(ct.hhmm, 1535, 1539)) {
    for (const ev of upcomingEvents) {
      if (thursdayBefore(ev.event_date) === ct.ymd) {
        for (const bot of PER_BOTS) out.push({ bot, brief_type: 'fomc_eve', brief_date: ct.ymd })
        break
      }
    }
  }

  // 5. Post-event — day after a halt_end_ts, 09:00-09:04 CT
  if (!isWeekend && inWindow(ct.hhmm, 900, 904)) {
    for (const ev of recentlyEndedEvents) {
      if (dayAfter(ev.event_date) === ct.ymd) {
        for (const bot of PER_BOTS) out.push({ bot, brief_type: 'post_event', brief_date: ct.ymd })
        break
      }
    }
  }

  return out
}
```

- [ ] **Step 4:** Run tests:

```
cd ironforge/webapp && npx vitest run src/lib/forgeBriefings/__tests__/scheduler.test.ts
```

Expected: all tests pass.

- [ ] **Step 5:** Commit:

```
git add ironforge/webapp/src/lib/forgeBriefings/scheduler.ts \
        ironforge/webapp/src/lib/forgeBriefings/__tests__/scheduler.test.ts
git commit -m "feat(ironforge): forge briefings scheduler trigger logic"
```

---

## Task 9: Scheduler tick + scanner wiring

**Files:**
- Create: `ironforge/webapp/src/lib/forgeBriefings/tick.ts`
- Modify: `ironforge/webapp/src/lib/scanner.ts`

- [ ] **Step 1:** Write `src/lib/forgeBriefings/tick.ts`:

```ts
import { query } from '../db'
import { decideTriggers, type Trigger } from './scheduler'
import { generateBrief } from './generate'

const BASE_URL = process.env.IRONFORGE_BASE_URL || 'http://localhost:3000'

async function loadEventLists() {
  const upcoming = await query<{ event_date: string; halt_start_ts: string }>(`
    SELECT event_date::text AS event_date, halt_start_ts
    FROM ironforge_event_calendar
    WHERE is_active = TRUE AND event_date > CURRENT_DATE
      AND event_date <= CURRENT_DATE + INTERVAL '14 days'
    ORDER BY event_date ASC
  `).catch(() => [])
  const recent = await query<{ event_date: string; halt_end_ts: string }>(`
    SELECT event_date::text AS event_date, halt_end_ts
    FROM ironforge_event_calendar
    WHERE is_active = TRUE AND halt_end_ts >= NOW() - INTERVAL '2 days'
      AND halt_end_ts < NOW()
    ORDER BY halt_end_ts DESC
  `).catch(() => [])
  return { upcoming, recent }
}

export async function forgeBriefingsTick(): Promise<void> {
  let triggers: Trigger[] = []
  try {
    const { upcoming, recent } = await loadEventLists()
    triggers = decideTriggers(new Date(), upcoming, recent)
  } catch (err) {
    console.warn('[forge-briefings] tick — decideTriggers failed (non-fatal):', err)
    return
  }
  if (triggers.length === 0) return

  // Generate sequentially so we don't burst the Claude API
  for (const t of triggers) {
    try {
      const result = await generateBrief({
        bot: t.bot, brief_type: t.brief_type,
        brief_date: t.brief_date, baseUrl: BASE_URL,
      })
      console.log(`[forge-briefings] ${t.bot}/${t.brief_type}: ${result.status}${result.reason ? ' — ' + result.reason : ''}`)
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      console.warn(`[forge-briefings] ${t.bot}/${t.brief_type}: unexpected error: ${msg}`)
    }
  }
}
```

- [ ] **Step 2:** Wire into `scanner.ts`. Open `src/lib/scanner.ts`. Find the existing import line for the Vigil refresh:

```ts
import { eventCalendarRefresh } from './eventCalendar/refresh'
import { isEventBlackoutActive } from './eventCalendar/gate'
```

Add after them:

```ts
import { forgeBriefingsTick } from './forgeBriefings/tick'
```

- [ ] **Step 3:** In the same file, find where Vigil's `eventCalendarRefresh()` is called inside `runAllScans()`. Add immediately after that call:

```ts
// Forge Reports: per-cycle scheduler tick. Idempotent + non-throwing —
// failures log to forge_briefings_meta and never block trading.
forgeBriefingsTick().catch((err: unknown) => {
  const msg = err instanceof Error ? err.message : String(err)
  console.warn(`[scanner] forge-briefings tick failed (non-fatal): ${msg}`)
})
```

- [ ] **Step 4:** Verify build:

```
cd ironforge/webapp && npx next build 2>&1 | tail -10
```

Expected: Compiled successfully.

- [ ] **Step 5:** Commit:

```
git add ironforge/webapp/src/lib/forgeBriefings/tick.ts ironforge/webapp/src/lib/scanner.ts
git commit -m "feat(ironforge): forge briefings scheduler tick + scanner wiring"
```

---

## Task 10: Pruner

**Files:**
- Create: `ironforge/webapp/src/lib/forgeBriefings/prune.ts`

The pruner runs once a day from the same scheduler tick (cheap soft-delete check + occasional hard-delete). We add it to `tick.ts`.

- [ ] **Step 1:** Write `src/lib/forgeBriefings/prune.ts`:

```ts
import { dbExecute, query } from '../db'

const PRUNE_RUN_FLAG_KEY = 'last_prune_date'

/**
 * Soft-delete daily/weekly briefs older than 3 years; hard-delete soft-deleted
 * rows that have been inactive for more than 30 days. Codex monthly entries
 * never prune.
 *
 * Runs at most once per day; tracked via forge_briefings_meta with a synthetic
 * row (bot='__system', brief_type='prune').
 */
export async function pruneIfDue(): Promise<{ ranToday: boolean; soft: number; hard: number }> {
  const meta = await query<{ last_run_ts: Date | null }>(
    `SELECT last_run_ts FROM forge_briefings_meta WHERE bot='__system' AND brief_type='prune'`,
  ).catch(() => [])
  const last = meta[0]?.last_run_ts ? new Date(meta[0].last_run_ts) : null
  const todayCt = new Date().toLocaleDateString('en-CA', { timeZone: 'America/Chicago' })
  const lastCt = last ? last.toLocaleDateString('en-CA', { timeZone: 'America/Chicago' }) : null
  if (lastCt === todayCt) return { ranToday: false, soft: 0, hard: 0 }

  const soft = await dbExecute(`
    UPDATE forge_briefings SET is_active = FALSE, updated_at = NOW()
    WHERE is_active = TRUE
      AND brief_type IN ('daily_eod','weekly_synth','fomc_eve','post_event')
      AND brief_date < (CURRENT_DATE - INTERVAL '3 years')
  `).catch(() => 0)

  const hard = await dbExecute(`
    DELETE FROM forge_briefings
    WHERE is_active = FALSE
      AND brief_type IN ('daily_eod','weekly_synth','fomc_eve','post_event')
      AND updated_at < (NOW() - INTERVAL '30 days')
  `).catch(() => 0)

  await dbExecute(`
    INSERT INTO forge_briefings_meta (bot, brief_type, last_run_ts, last_run_status)
    VALUES ('__system', 'prune', NOW(), $1)
    ON CONFLICT (bot, brief_type) DO UPDATE SET
      last_run_ts = NOW(), last_run_status = $1
  `, [`soft=${soft} hard=${hard}`]).catch(() => {})

  return { ranToday: true, soft, hard }
}
```

- [ ] **Step 2:** Wire into `tick.ts`. Open `src/lib/forgeBriefings/tick.ts`. Add import + call:

```ts
import { pruneIfDue } from './prune'
```

At the start of `forgeBriefingsTick()`, before `decideTriggers`:

```ts
pruneIfDue().catch(() => {})  // best-effort, doesn't block triggers
```

- [ ] **Step 3:** Verify build:

```
cd ironforge/webapp && npx next build 2>&1 | tail -5
```

- [ ] **Step 4:** Commit:

```
git add ironforge/webapp/src/lib/forgeBriefings/prune.ts ironforge/webapp/src/lib/forgeBriefings/tick.ts
git commit -m "feat(ironforge): forge briefings 3-year retention pruner"
```

---

## Task 11: API routes (events list + single + generate)

**Files:**
- Create: `ironforge/webapp/src/app/api/briefings/route.ts`
- Create: `ironforge/webapp/src/app/api/briefings/[id]/route.ts`
- Create: `ironforge/webapp/src/app/api/briefings/generate/route.ts`
- Create: `ironforge/webapp/src/app/api/briefings/calendar-badges/route.ts`

- [ ] **Step 1:** `src/app/api/briefings/route.ts`:

```ts
import { NextRequest, NextResponse } from 'next/server'
import { listInRange } from '@/lib/forgeBriefings/repo'
import type { BotKey, BriefType } from '@/lib/forgeBriefings/types'

export const dynamic = 'force-dynamic'

const BOTS = new Set<BotKey>(['flame', 'spark', 'inferno', 'portfolio'])
const TYPES = new Set<BriefType>(['daily_eod', 'fomc_eve', 'post_event', 'weekly_synth', 'codex_monthly'])

export async function GET(req: NextRequest) {
  const sp = new URL(req.url).searchParams
  const opts: any = {
    from: sp.get('from') || undefined,
    to: sp.get('to') || undefined,
    limit: sp.get('limit') ? parseInt(sp.get('limit')!) : undefined,
    offset: sp.get('offset') ? parseInt(sp.get('offset')!) : undefined,
  }
  const bot = sp.get('bot') as BotKey | null
  const type = sp.get('type') as BriefType | null
  if (bot && BOTS.has(bot)) opts.bot = bot
  if (type && TYPES.has(type)) opts.brief_type = type
  try {
    const briefs = await listInRange(opts)
    return NextResponse.json({ briefs })
  } catch (err) {
    return NextResponse.json({ error: (err as Error).message }, { status: 500 })
  }
}
```

- [ ] **Step 2:** `src/app/api/briefings/[id]/route.ts`:

```ts
import { NextRequest, NextResponse } from 'next/server'
import { findById } from '@/lib/forgeBriefings/repo'

export const dynamic = 'force-dynamic'

export async function GET(_req: NextRequest, { params }: { params: { id: string } }) {
  try {
    const brief = await findById(decodeURIComponent(params.id))
    if (!brief) return NextResponse.json({ error: 'not found' }, { status: 404 })
    return NextResponse.json({ brief })
  } catch (err) {
    return NextResponse.json({ error: (err as Error).message }, { status: 500 })
  }
}
```

- [ ] **Step 3:** `src/app/api/briefings/generate/route.ts`:

```ts
import { NextRequest, NextResponse } from 'next/server'
import { generateBrief } from '@/lib/forgeBriefings/generate'
import type { BotKey, BriefType } from '@/lib/forgeBriefings/types'

export const dynamic = 'force-dynamic'

const BOTS = new Set<BotKey>(['flame', 'spark', 'inferno', 'portfolio'])
const TYPES = new Set<BriefType>(['daily_eod', 'fomc_eve', 'post_event', 'weekly_synth', 'codex_monthly'])

export async function POST(req: NextRequest) {
  const sp = new URL(req.url).searchParams
  const body = await req.json().catch(() => ({}))
  const bot = ((body.bot as BotKey) || (sp.get('bot') as BotKey) || 'portfolio')
  const brief_type = ((body.brief_type as BriefType) || (sp.get('type') as BriefType) || 'daily_eod')
  const force = body.force === true || sp.get('force') === '1'
  const brief_date = body.brief_date || sp.get('brief_date') ||
    new Date().toLocaleDateString('en-CA', { timeZone: 'America/Chicago' })

  if (!BOTS.has(bot) || !TYPES.has(brief_type)) {
    return NextResponse.json({ error: 'invalid bot or type' }, { status: 400 })
  }

  const baseUrl = req.nextUrl.origin
  try {
    const result = await generateBrief({ bot, brief_type, brief_date, baseUrl, force })
    return NextResponse.json(result)
  } catch (err) {
    return NextResponse.json({ error: (err as Error).message }, { status: 500 })
  }
}
```

- [ ] **Step 4:** `src/app/api/briefings/calendar-badges/route.ts`:

```ts
import { NextRequest, NextResponse } from 'next/server'
import { listCalendarBadges } from '@/lib/forgeBriefings/repo'

export const dynamic = 'force-dynamic'

export async function GET(req: NextRequest) {
  const sp = new URL(req.url).searchParams
  const from = sp.get('from')
  const to = sp.get('to')
  if (!from || !to) return NextResponse.json({ error: 'from + to required (YYYY-MM-DD)' }, { status: 400 })
  try {
    const rows = await listCalendarBadges(from, to)
    // Group by date with per-bot mood + a "lead" brief (portfolio if available, else first per-bot)
    const byDate: Record<string, any> = {}
    for (const r of rows) {
      if (!byDate[r.brief_date]) {
        byDate[r.brief_date] = {
          brief_date: r.brief_date,
          per_bot: {} as Record<string, { mood: string | null; risk_score: number | null; brief_id: string }>,
          lead: null as null | { brief_id: string; risk_score: number | null; first_sentence: string },
        }
      }
      byDate[r.brief_date].per_bot[r.bot] = {
        mood: r.mood, risk_score: r.risk_score, brief_id: r.brief_id,
      }
      const isPortfolio = r.bot === 'portfolio'
      if (!byDate[r.brief_date].lead || isPortfolio) {
        byDate[r.brief_date].lead = {
          brief_id: r.brief_id, risk_score: r.risk_score, first_sentence: r.first_sentence,
        }
      }
    }
    return NextResponse.json({ days: Object.values(byDate) })
  } catch (err) {
    return NextResponse.json({ error: (err as Error).message }, { status: 500 })
  }
}
```

- [ ] **Step 5:** Build + commit:

```
cd ironforge/webapp && npx next build 2>&1 | grep -E "(Compiled|error|Failed|/api/briefings)"
```

```
git add ironforge/webapp/src/app/api/briefings
git commit -m "feat(ironforge): /api/briefings list + detail + generate + calendar-badges routes"
```

---

## Task 12: PNG export route

**Files:**
- Create: `ironforge/webapp/src/lib/forgeBriefings/png.ts`
- Create: `ironforge/webapp/src/app/api/briefings/[id]/png/route.ts`

Uses Next.js's built-in `next/og` (no extra install needed for Next 14).

- [ ] **Step 1:** Write `src/lib/forgeBriefings/png.ts`:

```ts
import { ImageResponse } from 'next/og'
import type { BriefRow } from './types'

export function renderBriefImage(brief: BriefRow): Response {
  return new ImageResponse(
    (
      <div
        style={{
          width: '100%', height: '100%', display: 'flex', flexDirection: 'column',
          backgroundColor: '#0b0b0d', color: '#e5e7eb', padding: 64,
          fontFamily: 'serif',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 32 }}>
          <div style={{ fontSize: 28, color: '#fbbf24', letterSpacing: 2 }}>
            IRON · FORGE
          </div>
          <div style={{ fontSize: 22, color: '#9ca3af' }}>
            {String(brief.brief_date)} · {brief.bot.toUpperCase()}
          </div>
        </div>
        <div style={{ fontSize: 22, color: '#fbbf24', fontStyle: 'italic', marginBottom: 18 }}>
          {brief.bot_voice_signature || ''}
        </div>
        <div style={{ fontSize: 56, fontWeight: 700, lineHeight: 1.1, marginBottom: 28 }}>
          {brief.title}
        </div>
        {brief.wisdom ? (
          <div style={{
            fontSize: 30, fontStyle: 'italic', color: '#fbbf24', borderLeft: '4px solid #fbbf24',
            paddingLeft: 20, marginBottom: 28, lineHeight: 1.3,
          }}>
            "{brief.wisdom}"
          </div>
        ) : null}
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 'auto', fontSize: 22 }}>
          <div style={{ color: '#9ca3af' }}>Risk {brief.risk_score ?? '—'}/10 · Mood {brief.mood ?? '—'}</div>
          <div style={{ color: '#9ca3af' }}>ironforge-899p.onrender.com</div>
        </div>
      </div>
    ),
    { width: 1200, height: 630 },
  )
}
```

- [ ] **Step 2:** `src/app/api/briefings/[id]/png/route.ts`:

```ts
import { NextRequest, NextResponse } from 'next/server'
import { findById } from '@/lib/forgeBriefings/repo'
import { renderBriefImage } from '@/lib/forgeBriefings/png'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET(_req: NextRequest, { params }: { params: { id: string } }) {
  const brief = await findById(decodeURIComponent(params.id)).catch(() => null)
  if (!brief) return NextResponse.json({ error: 'not found' }, { status: 404 })
  return renderBriefImage(brief)
}
```

- [ ] **Step 3:** Build + commit:

```
cd ironforge/webapp && npx next build 2>&1 | grep -E "(Compiled|error|/api/briefings/\[id\]/png)"
git add ironforge/webapp/src/lib/forgeBriefings/png.ts ironforge/webapp/src/app/api/briefings/\[id\]/png
git commit -m "feat(ironforge): PNG export route for briefings (server-rendered, 1200x630)"
```

---

## Task 13: Custom SVG glyphs

**Files:**
- Create: `public/glyph-mood-forged.svg`, `glyph-mood-measured.svg`, `glyph-mood-cooled.svg`, `glyph-mood-burning.svg`, `glyph-brief-badge.svg`

Single-color SVGs (use `currentColor` so they tint via CSS to per-bot accent). Style matches `/icon-flame.svg` weight (~2px stroke, simple geometry, ~24×24 viewbox).

- [ ] **Step 1:** Create `public/glyph-mood-forged.svg` (anvil with highlight):

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M3 14h18l-2 4H5z"/>
  <path d="M7 10h10v4H7z"/>
  <path d="M10 6v4M14 6v4"/>
  <path d="M12 2l1 2-1 2-1-2z" fill="currentColor"/>
</svg>
```

- [ ] **Step 2:** Create `public/glyph-mood-measured.svg` (balanced scale):

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 3v18"/>
  <path d="M5 6h14"/>
  <path d="M5 6L3 12h4z" fill="currentColor" fill-opacity="0.15"/>
  <path d="M19 6L17 12h4z" fill="currentColor" fill-opacity="0.15"/>
  <path d="M9 21h6"/>
</svg>
```

- [ ] **Step 3:** Create `public/glyph-mood-cooled.svg` (fading embers):

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="8" cy="16" r="2" fill="currentColor" fill-opacity="0.3"/>
  <circle cx="14" cy="14" r="2.5" fill="currentColor" fill-opacity="0.5"/>
  <circle cx="18" cy="18" r="1.5" fill="currentColor" fill-opacity="0.2"/>
  <path d="M4 21h16"/>
</svg>
```

- [ ] **Step 4:** Create `public/glyph-mood-burning.svg` (forge fire):

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 2c1 3-1 5 0 8 1 2 4 2 4 6a4 4 0 01-8 0c0-3 2-3 2-6 0-3-2-3 2-8z" fill="currentColor" fill-opacity="0.25"/>
  <path d="M10 16c.5 1 1.5 1.5 2 1.5s1.5-.5 2-1.5"/>
</svg>
```

- [ ] **Step 5:** Create `public/glyph-brief-badge.svg` (small scroll for calendar cells):

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M6 4h11l3 3v13H6z"/>
  <path d="M6 4v3a2 2 0 002 2h0"/>
  <path d="M10 12h7M10 16h5"/>
</svg>
```

- [ ] **Step 6:** Commit:

```
git add ironforge/webapp/public/glyph-mood-*.svg ironforge/webapp/public/glyph-brief-badge.svg
git commit -m "feat(ironforge): custom SVG glyphs (4 mood + 1 brief badge)"
```

---

## Task 14: Components — leaf-level

**Files:**
- Create: `BriefingMoodGlyph.tsx`, `BriefingWisdom.tsx`, `BriefingFactors.tsx`, `BriefingMacroRibbon.tsx`, `BriefingSparkline.tsx`, `BriefingTradeOfDay.tsx`

- [ ] **Step 1:** `src/components/BriefingMoodGlyph.tsx`:

```tsx
import type { Mood } from '@/lib/forgeBriefings/types'

const SRC: Record<Mood, string> = {
  forged:   '/glyph-mood-forged.svg',
  measured: '/glyph-mood-measured.svg',
  cooled:   '/glyph-mood-cooled.svg',
  burning:  '/glyph-mood-burning.svg',
}

const TINT: Record<string, string> = {
  flame: 'text-amber-400', spark: 'text-blue-400', inferno: 'text-red-400', portfolio: 'text-amber-300',
}

export default function BriefingMoodGlyph({ mood, bot, size = 32 }: { mood: Mood | null; bot?: string; size?: number }) {
  if (!mood) return null
  const tint = bot ? (TINT[bot] || 'text-amber-300') : 'text-amber-300'
  return (
    <span className={tint} title={mood}>
      <img src={SRC[mood]} alt={mood} style={{ width: size, height: size, filter: 'invert(80%) sepia(60%) saturate(700%) hue-rotate(360deg)' }} />
    </span>
  )
}
```

- [ ] **Step 2:** `src/components/BriefingWisdom.tsx`:

```tsx
export default function BriefingWisdom({ wisdom }: { wisdom: string | null }) {
  if (!wisdom) return null
  return (
    <blockquote
      className="border-l-4 border-amber-400 pl-5 my-4 text-amber-300 italic"
      style={{ fontFamily: 'Georgia, "Times New Roman", serif', fontSize: '1.4rem', lineHeight: 1.4 }}
    >
      "{wisdom}"
    </blockquote>
  )
}
```

- [ ] **Step 3:** `src/components/BriefingFactors.tsx`:

```tsx
import type { Factor } from '@/lib/forgeBriefings/types'

export default function BriefingFactors({ factors }: { factors: Factor[] | null }) {
  if (!factors || factors.length === 0) return null
  return (
    <div className="bg-forge-card rounded-lg p-4">
      <h3 className="text-amber-300 text-sm uppercase tracking-wider mb-3">Factors</h3>
      <ol className="space-y-3">
        {factors.map(f => (
          <li key={f.rank} className="text-sm text-gray-200">
            <span className="text-amber-400 font-medium mr-2">{f.rank}.</span>
            <span className="font-medium">{f.title}</span>
            <p className="text-gray-400 text-xs mt-0.5 ml-5">{f.detail}</p>
          </li>
        ))}
      </ol>
    </div>
  )
}
```

- [ ] **Step 4:** `src/components/BriefingMacroRibbon.tsx`:

```tsx
import type { MacroRibbon } from '@/lib/forgeBriefings/types'

export default function BriefingMacroRibbon({ data }: { data: MacroRibbon | null }) {
  if (!data) return null
  const sign = (n: number) => (n >= 0 ? '+' : '') + n.toFixed(2)
  return (
    <div className="rounded-lg border border-gray-800 bg-forge-card/50 px-4 py-3 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
      <div><span className="text-gray-500 text-xs">SPY</span> <span className="text-gray-200">{data.spy_close.toFixed(2)}</span> <span className="text-gray-400">range {data.spy_range_pct.toFixed(2)}%</span></div>
      <div className="text-gray-700">·</div>
      <div><span className="text-gray-500 text-xs">EM</span> <span className="text-gray-200">{data.em_pct.toFixed(2)}%</span></div>
      <div className="text-gray-700">·</div>
      <div><span className="text-gray-500 text-xs">VIX</span> <span className="text-gray-200">{data.vix.toFixed(2)}</span> <span className={data.vix_change >= 0 ? 'text-red-400' : 'text-emerald-400'}>{sign(data.vix_change)}</span></div>
      <div className="text-gray-700">·</div>
      <div><span className="text-gray-500 text-xs">Regime</span> <span className="text-gray-200">{data.regime}</span></div>
      <div className="text-gray-700">·</div>
      <div><span className="text-gray-500 text-xs">Pin Risk</span> <span className="text-gray-200">{data.pin_risk}</span></div>
    </div>
  )
}
```

- [ ] **Step 5:** `src/components/BriefingSparkline.tsx`:

```tsx
import type { SparklinePoint } from '@/lib/forgeBriefings/types'

export default function BriefingSparkline({ data, width = 220, height = 40 }: { data: SparklinePoint[] | null; width?: number; height?: number }) {
  if (!data || data.length < 2) return null
  const xs = data.map((_, i) => i)
  const ys = data.map(p => p.cumulative_pnl)
  const minY = Math.min(...ys), maxY = Math.max(...ys)
  const range = (maxY - minY) || 1
  const path = data.map((p, i) => {
    const x = (i / (data.length - 1)) * width
    const y = height - ((p.cumulative_pnl - minY) / range) * height
    return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  const last = ys[ys.length - 1]
  const positive = last >= ys[0]
  return (
    <div className="flex items-center gap-3">
      <svg width={width} height={height}>
        <path d={path} fill="none" stroke={positive ? '#34d399' : '#f87171'} strokeWidth={2} />
      </svg>
      <span className={`text-sm ${positive ? 'text-emerald-400' : 'text-red-400'}`}>
        {positive ? '+' : ''}${last.toFixed(2)}
      </span>
    </div>
  )
}
```

- [ ] **Step 6:** `src/components/BriefingTradeOfDay.tsx`:

```tsx
import type { TradeOfDay } from '@/lib/forgeBriefings/types'

export default function BriefingTradeOfDay({ trade }: { trade: TradeOfDay | null }) {
  if (!trade) return null
  const { strikes, payoff_points, pnl, contracts, entry_credit, exit_cost } = trade
  if (!payoff_points || payoff_points.length < 2) return null

  const w = 320, h = 140, padX = 20, padY = 16
  const xs = payoff_points.map(p => p.spot)
  const ys = payoff_points.map(p => p.pnl)
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const minY = Math.min(...ys), maxY = Math.max(...ys)
  const xRange = maxX - minX || 1
  const yRange = (maxY - minY) || 1
  const xToPx = (x: number) => padX + ((x - minX) / xRange) * (w - 2 * padX)
  const yToPx = (y: number) => h - padY - ((y - minY) / yRange) * (h - 2 * padY)
  const path = payoff_points.map((p, i) => `${i === 0 ? 'M' : 'L'}${xToPx(p.spot).toFixed(1)},${yToPx(p.pnl).toFixed(1)}`).join(' ')
  const zeroY = yToPx(0)

  return (
    <div className="bg-forge-card rounded-lg p-4">
      <div className="flex items-baseline justify-between mb-2">
        <h3 className="text-amber-300 text-sm uppercase tracking-wider">Trade of the Day</h3>
        <span className={pnl >= 0 ? 'text-emerald-400 font-medium' : 'text-red-400 font-medium'}>
          {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
        </span>
      </div>
      <div className="text-xs text-gray-400 mb-3">
        {contracts}× {strikes.ps}/{strikes.pl}p{strikes.cs ? ` · ${strikes.cs}/${strikes.cl}c` : ''} · in {entry_credit.toFixed(2)} → out {exit_cost.toFixed(2)}
      </div>
      <svg width="100%" viewBox={`0 0 ${w} ${h}`} className="overflow-visible">
        <line x1={padX} y1={zeroY} x2={w - padX} y2={zeroY} stroke="#374151" strokeDasharray="3,3" />
        <path d={path} fill="none" stroke="#fbbf24" strokeWidth={1.5} />
      </svg>
    </div>
  )
}
```

- [ ] **Step 7:** Build + commit:

```
cd ironforge/webapp && npx next build 2>&1 | tail -5
git add ironforge/webapp/src/components/Briefing*.tsx
git commit -m "feat(ironforge): briefing leaf components (mood/wisdom/factors/macro/sparkline/trade)"
```

---

## Task 15: Components — composite (BriefingCard, WeeklySynthesisHero, calendar pieces)

**Files:**
- Create: `BriefingCard.tsx`, `WeeklySynthesisHero.tsx`, `CalendarBriefBadge.tsx`, `CalendarBriefMiniCard.tsx`

- [ ] **Step 1:** `src/components/BriefingCard.tsx`:

```tsx
'use client'

import Link from 'next/link'
import type { BriefRow } from '@/lib/forgeBriefings/types'
import BriefingMacroRibbon from './BriefingMacroRibbon'
import BriefingFactors from './BriefingFactors'
import BriefingTradeOfDay from './BriefingTradeOfDay'
import BriefingSparkline from './BriefingSparkline'
import BriefingWisdom from './BriefingWisdom'
import BriefingMoodGlyph from './BriefingMoodGlyph'

const BOT_ACCENT: Record<string, string> = {
  flame: 'text-amber-400', spark: 'text-blue-400', inferno: 'text-red-400', portfolio: 'text-amber-300',
}

export default function BriefingCard({ brief, compact = false }: { brief: BriefRow; compact?: boolean }) {
  const accent = BOT_ACCENT[brief.bot] || 'text-amber-300'

  if (compact) {
    return (
      <Link href={`/briefings/${encodeURIComponent(brief.brief_id)}`} className="block bg-forge-card rounded-lg p-4 hover:bg-forge-card/80 transition-colors">
        <div className="flex items-center justify-between mb-1">
          <span className={`uppercase font-medium ${accent} text-sm`}>{brief.bot}</span>
          <span className="text-xs text-gray-500">{String(brief.brief_date)}</span>
        </div>
        <div className="flex items-center gap-3">
          <BriefingMoodGlyph mood={brief.mood} bot={brief.bot} size={24} />
          <div className="flex-1">
            <div className="text-sm text-gray-200 font-medium truncate">{brief.title}</div>
            <div className="text-xs text-gray-500 italic truncate">{brief.bot_voice_signature}</div>
          </div>
          <span className="text-xs text-gray-400">{brief.risk_score ?? '—'}/10</span>
        </div>
      </Link>
    )
  }

  return (
    <article className="space-y-5 animate-[fadeInUp_0.6s_ease-out]">
      <BriefingMacroRibbon data={brief.macro_ribbon} />
      <div className={`text-lg italic ${accent}`} style={{ fontFamily: 'Georgia, serif' }}>
        {brief.bot_voice_signature}
      </div>
      <div>
        <h1 className="text-3xl font-bold text-white mb-2">{brief.title}</h1>
        <div className="flex items-center gap-4 text-sm text-gray-400">
          <span className={`uppercase ${accent}`}>{brief.bot}</span>
          <span>·</span>
          <span>Risk {brief.risk_score ?? '—'}/10</span>
          <span>·</span>
          <span>Mood: {brief.mood ?? '—'}</span>
          <BriefingMoodGlyph mood={brief.mood} bot={brief.bot} size={20} />
        </div>
      </div>
      <BriefingWisdom wisdom={brief.wisdom} />
      <div className="text-gray-200 leading-relaxed whitespace-pre-line">{brief.summary}</div>
      <div className="grid md:grid-cols-2 gap-4">
        <BriefingTradeOfDay trade={brief.trade_of_day} />
        <BriefingFactors factors={brief.factors} />
      </div>
      <div className="pt-4 border-t border-gray-800 flex items-center justify-between">
        <BriefingSparkline data={brief.sparkline_data} />
        <div className="flex gap-3">
          <a href={`/api/briefings/${encodeURIComponent(brief.brief_id)}/png`} download className="text-amber-400 hover:text-amber-300 text-sm">
            Download PNG
          </a>
          <Link href={`/calendar?date=${String(brief.brief_date)}`} className="text-gray-400 hover:text-gray-200 text-sm">
            Open in calendar →
          </Link>
        </div>
      </div>
    </article>
  )
}
```

- [ ] **Step 2:** Add the fade-in keyframe to `src/app/globals.css` (append):

```css
@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
@media (prefers-reduced-motion: reduce) {
  .animate-\[fadeInUp_0\.6s_ease-out\] { animation: none !important; }
}
```

- [ ] **Step 3:** `src/components/WeeklySynthesisHero.tsx`:

```tsx
'use client'

import Link from 'next/link'
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import type { BriefRow } from '@/lib/forgeBriefings/types'
import BriefingSparkline from './BriefingSparkline'

export default function WeeklySynthesisHero() {
  const { data } = useSWR<{ briefs: BriefRow[] }>(
    '/api/briefings?bot=portfolio&type=weekly_synth&limit=1',
    fetcher,
    { refreshInterval: 5 * 60 * 1000 },
  )
  const brief = data?.briefs?.[0]
  if (!brief) {
    return (
      <div className="rounded-lg border border-amber-900/40 bg-forge-card p-8 text-center text-gray-400">
        No weekly synthesis yet. Friday after close, the Master of the Forge will speak.
      </div>
    )
  }
  return (
    <Link href={`/briefings/${encodeURIComponent(brief.brief_id)}`}
          className="block rounded-lg border border-amber-700/40 bg-gradient-to-br from-forge-card to-forge-card/40 p-8 hover:border-amber-500/60 transition-colors">
      <div className="flex items-baseline justify-between mb-2">
        <span className="text-xs uppercase tracking-widest text-amber-400">This Week in Iron</span>
        <span className="text-xs text-gray-500">Wk of {String(brief.brief_date)}</span>
      </div>
      <h2 className="text-3xl font-bold text-white mb-3">{brief.title}</h2>
      <p className="text-amber-300 italic mb-4" style={{ fontFamily: 'Georgia, serif' }}>
        {brief.bot_voice_signature}
      </p>
      <p className="text-gray-300 leading-relaxed line-clamp-4 mb-4">{brief.summary}</p>
      {brief.wisdom ? (
        <p className="text-amber-300 italic text-lg" style={{ fontFamily: 'Georgia, serif' }}>"{brief.wisdom}"</p>
      ) : null}
      <div className="mt-4 flex items-center justify-between">
        <BriefingSparkline data={brief.sparkline_data} />
        <span className="text-amber-400 text-sm">Read full →</span>
      </div>
    </Link>
  )
}
```

- [ ] **Step 4:** `src/components/CalendarBriefBadge.tsx`:

```tsx
import type { Mood } from '@/lib/forgeBriefings/types'

const TINT: Record<Mood, string> = {
  forged: 'text-emerald-400', measured: 'text-amber-300',
  cooled: 'text-gray-400', burning: 'text-red-400',
}

export default function CalendarBriefBadge({ mood }: { mood: Mood | null | undefined }) {
  return (
    <span className={`absolute top-0 right-0 ${mood ? TINT[mood] : 'text-amber-300'}`}
          style={{ width: 10, height: 10 }}>
      <img src="/glyph-brief-badge.svg" alt="" style={{ width: 10, height: 10 }} />
    </span>
  )
}
```

- [ ] **Step 5:** `src/components/CalendarBriefMiniCard.tsx`:

```tsx
import type { Mood } from '@/lib/forgeBriefings/types'

interface DayBadge {
  brief_date: string
  per_bot: Record<string, { mood: Mood | null; risk_score: number | null; brief_id: string }>
  lead: { brief_id: string; risk_score: number | null; first_sentence: string } | null
}

const MOOD_DOT: Record<Mood, string> = {
  forged: 'bg-emerald-400', measured: 'bg-amber-300',
  cooled: 'bg-gray-400', burning: 'bg-red-400',
}

export default function CalendarBriefMiniCard({ day }: { day: DayBadge }) {
  return (
    <div className="absolute z-50 bg-forge-card border border-amber-900/60 rounded-lg p-3 shadow-xl text-xs text-gray-200 pointer-events-none"
         style={{ width: 220, marginTop: 4 }}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-amber-300">{day.brief_date}</span>
        {day.lead?.risk_score != null ? <span className="text-gray-400">Risk {day.lead.risk_score}/10</span> : null}
      </div>
      <div className="flex gap-1 mb-2">
        {(['flame','spark','inferno','portfolio'] as const).map(b => {
          const pb = day.per_bot[b]
          if (!pb) return null
          return (
            <span key={b} className={`inline-block w-2 h-2 rounded-full ${pb.mood ? MOOD_DOT[pb.mood] : 'bg-gray-600'}`} title={`${b}: ${pb.mood ?? '—'}`} />
          )
        })}
      </div>
      {day.lead?.first_sentence ? (
        <p className="text-gray-300 line-clamp-3 italic">{day.lead.first_sentence}</p>
      ) : null}
    </div>
  )
}
```

- [ ] **Step 6:** Build + commit:

```
cd ironforge/webapp && npx next build 2>&1 | tail -5
git add ironforge/webapp/src/components/BriefingCard.tsx \
        ironforge/webapp/src/components/WeeklySynthesisHero.tsx \
        ironforge/webapp/src/components/CalendarBriefBadge.tsx \
        ironforge/webapp/src/components/CalendarBriefMiniCard.tsx \
        ironforge/webapp/src/app/globals.css
git commit -m "feat(ironforge): briefing card + weekly hero + calendar badge/mini-card components"
```

---

## Task 16: Pages

**Files:**
- Create: `src/app/briefings/page.tsx`, `src/app/briefings/[id]/page.tsx`, `src/app/briefings/archive/page.tsx`, `src/app/briefings/codex/page.tsx`

- [ ] **Step 1:** `src/app/briefings/page.tsx` (hub):

```tsx
'use client'

import Link from 'next/link'
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import type { BriefRow } from '@/lib/forgeBriefings/types'
import WeeklySynthesisHero from '@/components/WeeklySynthesisHero'
import BriefingCard from '@/components/BriefingCard'

export default function BriefingsHub() {
  const { data: dailies } = useSWR<{ briefs: BriefRow[] }>('/api/briefings?type=daily_eod&limit=12', fetcher, { refreshInterval: 60_000 })
  const { data: codex } = useSWR<{ briefs: BriefRow[] }>('/api/briefings?type=codex_monthly&limit=3', fetcher)

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Briefings</h1>
        <div className="flex gap-4 text-sm">
          <Link href="/briefings/archive" className="text-gray-400 hover:text-gray-200">Archive</Link>
          <Link href="/briefings/codex" className="text-gray-400 hover:text-gray-200">Codex</Link>
        </div>
      </div>

      <WeeklySynthesisHero />

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-3">
          <h2 className="text-amber-300 text-sm uppercase tracking-wider">Recent Daily Reports</h2>
          {(dailies?.briefs || []).map(b => (
            <BriefingCard key={b.brief_id} brief={b} compact />
          ))}
          {(!dailies?.briefs || dailies.briefs.length === 0) && (
            <div className="text-gray-500 text-sm py-8 text-center">No daily briefings yet.</div>
          )}
        </div>

        <aside className="space-y-3">
          <h2 className="text-amber-300 text-sm uppercase tracking-wider">Forge Codex</h2>
          {(codex?.briefs || []).map(b => (
            <Link key={b.brief_id} href={`/briefings/${encodeURIComponent(b.brief_id)}`} className="block bg-forge-card rounded-lg p-4 hover:bg-forge-card/80">
              <div className="text-xs text-gray-500 mb-1">{String(b.brief_date).slice(0, 7)} · {b.bot}</div>
              <div className="text-sm text-gray-200 font-medium">{b.title}</div>
            </Link>
          ))}
          <Link href="/briefings/codex" className="block text-center text-sm text-amber-400 hover:text-amber-300 py-2">
            Browse all codex →
          </Link>
        </aside>
      </div>
    </div>
  )
}
```

- [ ] **Step 2:** `src/app/briefings/[id]/page.tsx` (detail):

```tsx
'use client'

import Link from 'next/link'
import useSWR from 'swr'
import { useParams } from 'next/navigation'
import { fetcher } from '@/lib/fetcher'
import type { BriefRow } from '@/lib/forgeBriefings/types'
import BriefingCard from '@/components/BriefingCard'

export default function BriefingDetail() {
  const params = useParams<{ id: string }>()
  const id = decodeURIComponent(params.id as string)
  const { data, isLoading } = useSWR<{ brief: BriefRow }>(`/api/briefings/${encodeURIComponent(id)}`, fetcher)
  if (isLoading) return <div className="max-w-4xl mx-auto px-4 py-6 text-gray-400">Loading…</div>
  if (!data?.brief) return <div className="max-w-4xl mx-auto px-4 py-6 text-red-400">Brief not found.</div>
  return (
    <div className="max-w-4xl mx-auto px-4 py-6 space-y-4">
      <Link href="/briefings" className="text-sm text-gray-400 hover:text-gray-200">← Back to briefings</Link>
      <BriefingCard brief={data.brief} />
    </div>
  )
}
```

- [ ] **Step 3:** `src/app/briefings/archive/page.tsx`:

```tsx
'use client'

import Link from 'next/link'
import useSWR from 'swr'
import { useState } from 'react'
import { fetcher } from '@/lib/fetcher'
import type { BriefRow } from '@/lib/forgeBriefings/types'
import BriefingCard from '@/components/BriefingCard'

export default function BriefingsArchive() {
  const [bot, setBot] = useState<string>('')
  const [type, setType] = useState<string>('')
  const [page, setPage] = useState(0)
  const PAGE = 20
  const url = `/api/briefings?limit=${PAGE}&offset=${page * PAGE}` +
    (bot ? `&bot=${bot}` : '') + (type ? `&type=${type}` : '')
  const { data } = useSWR<{ briefs: BriefRow[] }>(url, fetcher)
  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Briefings Archive</h1>
        <Link href="/briefings" className="text-sm text-gray-400 hover:text-gray-200">← Back</Link>
      </div>
      <div className="flex gap-3 text-sm">
        <select value={bot} onChange={e => { setBot(e.target.value); setPage(0) }} className="bg-forge-card border border-gray-700 rounded px-2 py-1 text-white">
          <option value="">All bots</option>
          <option value="flame">FLAME</option><option value="spark">SPARK</option>
          <option value="inferno">INFERNO</option><option value="portfolio">Portfolio</option>
        </select>
        <select value={type} onChange={e => { setType(e.target.value); setPage(0) }} className="bg-forge-card border border-gray-700 rounded px-2 py-1 text-white">
          <option value="">All types</option>
          <option value="daily_eod">Daily EOD</option>
          <option value="weekly_synth">Weekly</option>
          <option value="fomc_eve">FOMC eve</option>
          <option value="post_event">Post-event</option>
          <option value="codex_monthly">Codex</option>
        </select>
      </div>
      <div className="space-y-3">
        {(data?.briefs || []).map(b => <BriefingCard key={b.brief_id} brief={b} compact />)}
        {(!data?.briefs || data.briefs.length === 0) && (
          <div className="text-gray-500 text-sm py-8 text-center">No briefings match.</div>
        )}
      </div>
      <div className="flex justify-between">
        <button disabled={page === 0} onClick={() => setPage(p => Math.max(0, p - 1))} className="text-sm text-gray-400 hover:text-gray-200 disabled:opacity-30">← Newer</button>
        <span className="text-xs text-gray-500">Page {page + 1}</span>
        <button disabled={!data?.briefs || data.briefs.length < PAGE} onClick={() => setPage(p => p + 1)} className="text-sm text-gray-400 hover:text-gray-200 disabled:opacity-30">Older →</button>
      </div>
    </div>
  )
}
```

- [ ] **Step 4:** `src/app/briefings/codex/page.tsx`:

```tsx
'use client'

import Link from 'next/link'
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import type { BriefRow } from '@/lib/forgeBriefings/types'

export default function BriefingsCodex() {
  const { data } = useSWR<{ briefs: BriefRow[] }>('/api/briefings?type=codex_monthly&limit=100', fetcher)
  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Forge Codex</h1>
        <Link href="/briefings" className="text-sm text-gray-400 hover:text-gray-200">← Back</Link>
      </div>
      <p className="text-gray-400 text-sm">Monthly long-memory entries — distilled themes a future-you should remember.</p>
      <div className="space-y-3">
        {(data?.briefs || []).map(b => (
          <details key={b.brief_id} className="bg-forge-card rounded-lg p-4">
            <summary className="cursor-pointer flex items-baseline justify-between">
              <span className="text-amber-300 font-medium">{String(b.brief_date).slice(0, 7)} · {b.bot}</span>
              <span className="text-sm text-gray-400">{b.title}</span>
            </summary>
            <div className="mt-3 text-gray-200 whitespace-pre-line text-sm">{b.summary}</div>
            <div className="mt-3 text-xs">
              <Link href={`/briefings/${encodeURIComponent(b.brief_id)}`} className="text-amber-400 hover:text-amber-300">Open full →</Link>
            </div>
          </details>
        ))}
        {(!data?.briefs || data.briefs.length === 0) && (
          <div className="text-gray-500 text-sm py-8 text-center">No codex entries yet.</div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 5:** Build + commit:

```
cd ironforge/webapp && npx next build 2>&1 | grep -E "(Compiled|error|/briefings)"
git add ironforge/webapp/src/app/briefings
git commit -m "feat(ironforge): /briefings hub + detail + archive + codex pages"
```

---

## Task 17: Calendar integration + Nav link + LatestBriefCard upgrade

**Files:**
- Modify: `src/components/CalendarMonthGrid.tsx`
- Modify: `src/components/Nav.tsx`
- Modify: `src/components/LatestBriefCard.tsx`

- [ ] **Step 1:** Open `src/components/CalendarMonthGrid.tsx`. At the top of the file (after imports), add:

```tsx
'use client'
// (keep existing 'use client' if present)
```

Convert the component to a client component if not already. Add an SWR fetch for badges at the year level. Replace the existing `MiniMonth` calls with one that has access to a `badges` map. Specifically, modify the default export `CalendarMonthGrid`:

```tsx
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import { useState } from 'react'
import CalendarBriefBadge from './CalendarBriefBadge'
import CalendarBriefMiniCard from './CalendarBriefMiniCard'

// inside CalendarMonthGrid:
export default function CalendarMonthGrid({ year, events }: { year: number; events: CalendarEvent[] }) {
  const today = new Date()
  const todayIso = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`
  const { data: badgesResp } = useSWR<{ days: any[] }>(
    `/api/briefings/calendar-badges?from=${year}-01-01&to=${year}-12-31`,
    fetcher,
  )
  const badgesByDate: Record<string, any> = {}
  for (const d of (badgesResp?.days || [])) badgesByDate[d.brief_date] = d

  const [hoverDate, setHoverDate] = useState<string | null>(null)

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 relative">
      {Array.from({ length: 12 }, (_, m) => (
        <MiniMonth
          key={m}
          year={year}
          month={m}
          events={events}
          todayIso={todayIso}
          badgesByDate={badgesByDate}
          onHover={setHoverDate}
          hoverDate={hoverDate}
        />
      ))}
    </div>
  )
}
```

Then update `MiniMonth` to accept `badgesByDate`, `onHover`, `hoverDate`. Inside its cell render, after the day number, add:

```tsx
{c.iso && badgesByDate[c.iso] ? (
  <span className="absolute top-0 right-0">
    <CalendarBriefBadge mood={badgesByDate[c.iso].lead?.mood ?? null} />
  </span>
) : null}
```

And add `onMouseEnter={() => onHover(c.iso!)}` / `onMouseLeave={() => onHover(null)}` on each cell. If `c.iso === hoverDate && badgesByDate[c.iso]`, render `<CalendarBriefMiniCard day={badgesByDate[c.iso]} />` inside the cell. The existing cell style needs `position: relative`.

Also wrap the cell in a Link if it has a brief: `<Link href={`/briefings/${encodeURIComponent(badgesByDate[c.iso].lead.brief_id)}`}>`. Otherwise render a regular div.

- [ ] **Step 2:** Open `src/components/Nav.tsx`. Insert `Briefings` link between `Calendar` and `Accounts`:

```ts
{ href: '/calendar', label: 'Calendar', className: 'text-gray-400 hover:text-gray-200' },
{ href: '/briefings', label: 'Briefings', className: 'text-gray-400 hover:text-gray-200' },
{ href: '/accounts', label: 'Accounts', className: 'text-gray-400 hover:text-gray-200' },
```

- [ ] **Step 3:** Modify `src/components/LatestBriefCard.tsx`. Add a fallback to read from `forge_briefings` first via `/api/briefings?bot={bot}&type=daily_eod&limit=1`; if 0 results, fall back to existing legacy `/api/{bot}/briefs/latest` fetch.

```tsx
// At top of LatestBriefCard, replace its primary fetch:
const { data: forgeData } = useSWR<{ briefs: any[] }>(
  `/api/briefings?bot=${bot}&type=daily_eod&limit=1`,
  fetcher,
  { refreshInterval: 5 * 60 * 1000 },
)
const { data: legacyData } = useSWR<{ brief: any }>(
  forgeData && (!forgeData.briefs || forgeData.briefs.length === 0) ? `/api/${bot}/briefs/latest` : null,
  fetcher,
)

const brief = forgeData?.briefs?.[0] ?? legacyData?.brief
```

(Keep all the existing render code — both schemas have `summary`, `risk_score`, etc.)

- [ ] **Step 4:** Build + commit:

```
cd ironforge/webapp && npx next build 2>&1 | tail -5
git add ironforge/webapp/src/components/CalendarMonthGrid.tsx \
        ironforge/webapp/src/components/Nav.tsx \
        ironforge/webapp/src/components/LatestBriefCard.tsx
git commit -m "feat(ironforge): calendar badge integration + Briefings nav link + LatestBriefCard fallback"
```

---

## Task 18: Build, test, push, merge

- [ ] **Step 1:** Final clean build:

```
cd ironforge/webapp && npx next build 2>&1 | tail -10
```

Expected: Compiled successfully.

- [ ] **Step 2:** Run all forgeBriefings tests:

```
cd ironforge/webapp && npx vitest run src/lib/forgeBriefings/__tests__/ 2>&1 | tail -10
```

Expected: 4 test files (voices, mood, schema, scheduler) all pass.

- [ ] **Step 3:** Run Vigil tests too (should still all pass — no regression):

```
cd ironforge/webapp && npx vitest run src/lib/eventCalendar/__tests__/ 2>&1 | tail -5
```

Expected: 3 files pass (21 tests).

- [ ] **Step 4:** Push branch:

```
cd C:/Users/lemol/AlphaGEX && git push -u origin claude/forge-reports
```

- [ ] **Step 5:** Merge to main:

```
git checkout main && git pull --ff-only origin main
git merge --no-ff claude/forge-reports -m "feat(ironforge): Forge Reports (briefings) — Wave 1

End-of-day + weekly + monthly Claude-generated briefings for FLAME/SPARK/
INFERNO + Master portfolio voice. Cross-day memory (last 5 daily + monthly
codex). /briefings hub + detail + archive + codex pages. Calendar badge
+ hover preview integration. 3-year retention with soft-delete window.
Per-bot personality voices.  No Discord auto-post (in-app PNG download only).

Spec:  docs/superpowers/specs/2026-05-04-ironforge-forge-reports-design.md
Plan:  docs/superpowers/plans/2026-05-04-ironforge-forge-reports.md

Defers MCP/tool-use refactor to Wave 2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
"
git push origin main
```

- [ ] **Step 6:** Once Render redeploys (~3 min), seed manually:

```
curl -X POST "https://ironforge-899p.onrender.com/api/briefings/generate?bot=spark&type=daily_eod&force=1"
```

Expected: `{"ok":true,"brief_id":"daily:spark:YYYY-MM-DD","status":"ok"}`. Visit `/briefings` to verify it renders.

---

## Self-Review

**Spec coverage:**
- §3 Architecture → Tasks 1-17 (all components mapped)
- §4 Data model → Task 1 (DDL), Task 5 (repo)
- §5 Generation pipeline → Tasks 6 (context), 7 (generator), 8 (scheduler), 9 (tick + scanner)
- §5.1 Trigger times → Task 8 (scheduler tests cover all 5)
- §5.2 Voices → Task 2 (voices.ts + tests)
- §5.3 Cost → covered by callClaude pricing math in Task 7
- §6.1-6.4 UI pages → Task 16
- §6.5 Calendar integration → Task 17
- §6.6 Dashboard integration → Task 17 (LatestBriefCard fallback)
- §6.7 Nav link → Task 17
- §6.8 Visual constraints (no emoji, custom glyphs, gold serif italic) → Tasks 13 (glyphs) + 14 (Wisdom typography)
- §7 Failure modes → handled in Task 7 (generator fail-soft) + Task 6 (gather fallback) + Task 10 (prune defensive)
- §8 Testing → Tasks 2, 3, 4, 8 (unit); §8.3 manual verify → Task 18 step 6
- §9 Rollout → Task 18

**Placeholder scan:** No "TBD" / "TODO" in plan. All steps have concrete code or commands.

**Type consistency:** `BotKey`, `BriefType`, `Mood`, `ParsedBrief`, `BriefRow`, `MacroRibbon`, `SparklinePoint`, `Factor`, `TradeOfDay`, `GatheredContext` defined in Task 2's `types.ts` and consistently used in repo (Task 5), context (Task 6), generate (Task 7), scheduler (Task 8), API routes (Tasks 11-12), components (Tasks 14-15), pages (Task 16). `MoodInput` is local to mood.ts (Task 3) — exported there, imported nowhere else.

**One gap fixed inline:** Originally my draft imported `MoodInput as _MoodInput` in generate.ts but didn't actually use it. Removed that unused import in the plan.

**Risks worth flagging on execution:**
1. The CalendarMonthGrid edit in Task 17 is the trickiest — the existing component has its own internal structure that needs careful merging. If conflicts arise, write the changes inline by reading the actual file first.
2. PNG export uses `next/og` JSX — Next 14 supports this in `app/api` routes via the `runtime = 'nodejs'` directive. If the build fails citing missing `@vercel/og`, run `npm install @vercel/og` (a transitive dep that may need explicit install on some Next 14 setups).
3. The `IRONFORGE_BASE_URL` env var in `tick.ts` defaults to localhost — on Render, set it to `https://ironforge-899p.onrender.com` so internal fetches to /api/{bot}/* hit the right host. If unset, internal fetches will fail and the brief still generates with `dashboard_state: null` — graceful degradation is built in.
