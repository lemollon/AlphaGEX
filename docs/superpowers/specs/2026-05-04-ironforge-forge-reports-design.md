# IronForge Forge Reports (Briefings) — Design

**Date:** 2026-05-04
**Author:** Claude (brainstormed with Optionist Prime)
**Status:** Approved — proceeding to implementation plan
**Scope:** `ironforge/webapp/` (FLAME / SPARK / INFERNO + portfolio briefs)
**Wave:** 1 of 2 (Wave 2 = MCP / tool-use refactor, deferred)

---

## 1. Problem & Goal

The IronForge bots (FLAME 2DTE, SPARK 1DTE, INFERNO 0DTE) close out positions every afternoon, but there is no narrative layer that interprets *what just happened* and *why it matters*. The existing `lib/market-brief.ts` produces SPARK-only briefs that show on each bot's dashboard, but:

- FLAME and INFERNO have empty `*_market_briefs` tables — no briefs at all
- Briefs do not build on each other across days/weeks
- There is no synthesis layer (weekly, monthly)
- The visual presentation is a single text card on the bot dashboard
- The calendar (`/calendar`, just shipped as Vigil) has no link to past day insights
- Briefs cannot be discovered, browsed, archived, or shared as a body of work

**Goal:** ship a cohesive **Forge Reports** system that gives IronForge a daily/weekly/monthly insights layer for all three bots plus a portfolio voice, with cross-day memory, a dedicated `/briefings` page that holds attention, and integration with the Vigil calendar so the year-view becomes a navigable record. Up to 3 years of history retained.

## 2. Scope

**In scope (Wave 1):**
- Daily EOD brief per bot (3:30 PM CT, Mon-Fri)
- Portfolio EOD brief (one per day, Master voice synthesizing all 3 bots)
- Weekly synthesis per bot + portfolio (Friday 4:00 PM CT)
- FOMC-eve brief per bot (Thursday before each FOMC blackout, 3:35 PM CT) — uses Vigil calendar
- Post-event brief per bot (day after each blackout ends, 9:00 AM CT) — uses Vigil calendar
- Monthly codex entry per bot + portfolio (last business day of month, 5:00 PM CT)
- Cross-day memory (A): each daily brief reads last 5 daily briefs as context
- Long memory (C): each daily brief reads most recent codex entry as context
- Per-bot personality voices (FLAME deliberate, SPARK wry, INFERNO punchy, Master neutral)
- `/briefings` hub page (weekly hero + recent dailies + codex rail)
- `/briefings/[id]` full brief view (rich, animated, downloadable as PNG)
- `/briefings/archive` paginated 3-year timeline with filters
- `/briefings/codex` monthly history
- Calendar integration: past cells with briefs get a custom badge + hover preview + click-through
- Dashboard integration: existing `LatestBriefCard` upgraded to use new schema
- 3-year retention: soft-delete > 3yr (30-day window), then hard-delete
- Per-bot opt-out toggle in `{bot}_config`

**Out of scope (Wave 2 — separate later project):**
- MCP / agentic tool-use architecture (replace pre-stuffed context with tool calls)
- Discord auto-post of briefings
- PROPHET ML-advisor consuming briefings as features

**Non-goals:**
- This system never affects trading behavior — purely informational
- No automated changes to bot config based on brief insights
- Existing `lib/market-brief.ts` stays as-is; new system runs in parallel for one rollover, then `LatestBriefCard` switches to read `forge_briefings`

## 3. Architecture

All work inside `ironforge/webapp/`. No new Render services. Reuses existing `CLAUDE_API_KEY` env var.

| Component | File | Purpose |
|---|---|---|
| Briefings table | `forge_briefings` (Postgres) | Daily/weekly/codex/portfolio briefs |
| Meta table | `forge_briefings_meta` (Postgres) | Per-(bot,type) last-run + retry tracking |
| Per-bot toggle | `forge_briefings_enabled` column on `{bot}_config` | Default TRUE |
| Generator | `lib/forgeBriefings/generate.ts` | Orchestrates one brief end-to-end |
| Voices | `lib/forgeBriefings/voices.ts` | Bot-specific system prompts |
| Context | `lib/forgeBriefings/context.ts` | Gathers DB + dashboard state + memory + macro |
| Repo | `lib/forgeBriefings/repo.ts` | DB ops |
| Scheduler | `lib/forgeBriefings/scheduler.ts` | Decides what fires when |
| PNG render | `lib/forgeBriefings/png.ts` | Server-side PNG export |
| Pruner | `lib/forgeBriefings/prune.ts` | 3-year retention |
| Scheduler tick | Inside `lib/scanner.ts` | Calls scheduler.tick() once per cycle |
| API: list | `app/api/briefings/route.ts` | GET with filters |
| API: detail | `app/api/briefings/[id]/route.ts` | GET single |
| API: PNG | `app/api/briefings/[id]/png/route.ts` | PNG download |
| API: generate | `app/api/briefings/generate/route.ts` | POST manual trigger |
| API: badges | `app/api/briefings/calendar-badges/route.ts` | Date-range badges for calendar hover |
| Page: hub | `app/briefings/page.tsx` | Hero + recent dailies + codex rail |
| Page: detail | `app/briefings/[id]/page.tsx` | Full single-brief view |
| Page: archive | `app/briefings/archive/page.tsx` | Paginated timeline |
| Page: codex | `app/briefings/codex/page.tsx` | Monthly history |
| Card | `components/BriefingCard.tsx` | Shareable card (used in 4 places) |
| Macro ribbon | `components/BriefingMacroRibbon.tsx` | Top strip |
| Trade of day | `components/BriefingTradeOfDay.tsx` | Payoff diagram |
| Factors | `components/BriefingFactors.tsx` | Ranked list |
| Wisdom | `components/BriefingWisdom.tsx` | Gold serif italic pull-quote |
| Mood glyph | `components/BriefingMoodGlyph.tsx` | Custom SVG mood |
| Sparkline | `components/BriefingSparkline.tsx` | 7-day equity line |
| Cal badge | `components/CalendarBriefBadge.tsx` | Calendar cell badge |
| Cal mini-card | `components/CalendarBriefMiniCard.tsx` | Hover preview |
| Hero | `components/WeeklySynthesisHero.tsx` | Full-width weekly hero |
| Glyph: forged | `public/glyph-mood-forged.svg` | Mood SVG |
| Glyph: measured | `public/glyph-mood-measured.svg` | Mood SVG |
| Glyph: cooled | `public/glyph-mood-cooled.svg` | Mood SVG |
| Glyph: burning | `public/glyph-mood-burning.svg` | Mood SVG |
| Glyph: badge | `public/glyph-brief-badge.svg` | Calendar cell badge |
| Modified | `lib/db.ts` | Add tables + per-bot column |
| Modified | `lib/scanner.ts` | Call scheduler.tick() |
| Modified | `components/CalendarMonthGrid.tsx` | Render badge + hover preview |
| Modified | `components/Nav.tsx` | Add Briefings link |
| Modified | `components/LatestBriefCard.tsx` | Read `forge_briefings` instead of legacy table |

## 4. Data Model

### 4.1 `forge_briefings`

```sql
CREATE TABLE IF NOT EXISTS forge_briefings (
  brief_id            TEXT PRIMARY KEY,
  bot                 TEXT NOT NULL,            -- 'flame'|'spark'|'inferno'|'portfolio'
  brief_type          TEXT NOT NULL,            -- 'daily_eod'|'fomc_eve'|'post_event'|'weekly_synth'|'codex_monthly'
  brief_date          DATE NOT NULL,
  brief_time          TIMESTAMPTZ NOT NULL,
  title               TEXT NOT NULL,
  summary             TEXT NOT NULL,
  wisdom              TEXT,
  risk_score          INT,
  mood                TEXT,                     -- 'forged'|'measured'|'cooled'|'burning'
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
```

### 4.2 `forge_briefings_meta`

```sql
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

### 4.3 Per-bot toggle

```sql
ALTER TABLE flame_config   ADD COLUMN IF NOT EXISTS forge_briefings_enabled BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE spark_config   ADD COLUMN IF NOT EXISTS forge_briefings_enabled BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE inferno_config ADD COLUMN IF NOT EXISTS forge_briefings_enabled BOOLEAN NOT NULL DEFAULT TRUE;
```

### 4.4 Brief ID format (deterministic — drives idempotency)

| Type | Format | Example |
|---|---|---|
| `daily_eod` | `daily:{bot}:{YYYY-MM-DD}` | `daily:flame:2026-05-04` |
| `fomc_eve` | `fomc_eve:{bot}:{YYYY-MM-DD}` | `fomc_eve:spark:2026-06-12` |
| `post_event` | `post_event:{bot}:{YYYY-MM-DD}` | `post_event:inferno:2026-06-19` |
| `weekly_synth` | `weekly:{bot}:{YYYY-MM-DD}` (Friday's date) | `weekly:portfolio:2026-05-08` |
| `codex_monthly` | `codex:{bot}:{YYYY-MM}` | `codex:flame:2026-05` |

A second trigger for the same key upserts — no duplicates possible. `bot='portfolio'` is the synthesis voice that runs after the per-bot ones for that trigger.

### 4.5 JSONB shapes

```typescript
// factors
[{ rank: 1, title: 'Pin gravity at 587', detail: '...' }, ...]

// trade_of_day
{
  position_id: '...', strikes: { ps: 582, pl: 577, cs: 595, cl: 600 },
  entry_credit: 1.20, exit_cost: 0.36, contracts: 5, pnl: 420,
  payoff_points: [{ spot: 575, pnl: -800 }, ...]   // for SVG payoff diagram
}

// macro_ribbon
{ spy_open: 587.10, spy_close: 587.43, spy_range_pct: 1.2, em_pct: 0.9,
  vix: 18.2, vix_change: -0.7, regime: 'Negative Gamma', pin_risk: 'Medium' }

// sparkline_data
[{ date: '2026-04-28', cumulative_pnl: 720 }, ...]  // last 7 days
```

## 5. Generation Pipeline

```
1. Scheduler tick (in scanner.ts, called each 1-min cycle)
   → forgeBriefingsScheduler.tick(now) returns list of (bot, type) to fire

2. For each (bot, type):
   a. Compute deterministic brief_id from (bot, type, brief_date)
   b. Idempotency: SELECT brief_id FROM forge_briefings WHERE brief_id=$id
      → if exists AND status='ok' AND not force=true → skip
   c. Per-bot toggle (skip portfolio): SELECT forge_briefings_enabled FROM {bot}_config
      → if FALSE → skip
   d. Gather context (context.ts):
      - DB: today's positions, today's trades, daily_perf, equity-curve
      - Live dashboard: internal fetch GET /api/{bot}/status, /positions, /performance
      - Macro: getRawQuotes(['SPY','VIX','VIX3M','VVIX'])
      - Memory A: last 5 daily_eod briefs for this bot (summary + wisdom)
      - Memory C: most recent codex_monthly brief for this bot
      - Vigil: any active blackout? upcoming blackout within 7 days?
   e. Build prompt (voices.ts):
      - System: bot voice + JSON schema requirement + tone guidelines
      - System block uses Anthropic prompt-cache (cache_control breakpoint)
      - User: gathered context as structured JSON
   f. Call Claude (Anthropic SDK with prompt caching headers)
   g. Parse JSON; validate schema; on parse fail → status='error:parse_fail', skip
   h. Compute mood from outcome (rules-based on today's P&L + risk score):
      - P&L >= 80% of target AND risk <= 4 → 'forged'
      - P&L between -50% and +80% target → 'measured'
      - P&L between -100% and -50% target → 'cooled'
      - High activity OR risk >= 7 → 'burning'
   i. Upsert into forge_briefings; update forge_briefings_meta

3. Errors:
   - Claude failure: increment retry_count, mark status='retry_pending'
     - Next scheduler tick within 5 min retries (max 1 retry per brief)
     - After retry fails: status='error:{msg}', skip until next scheduled run
   - DB write failure: log + skip (avoid duplicate side effects)
   - Each (bot, type) is independent — one failure never blocks another
```

### 5.1 Scheduler trigger times (CT)

| Trigger | When | Fires |
|---|---|---|
| Daily EOD | Mon-Fri 15:30 | `daily_eod` × 3 bots → then `daily_eod:portfolio` |
| FOMC eve | Thursday before each FOMC, 15:35 | `fomc_eve` × 3 bots |
| Post-event | Day after a Vigil halt_end_ts, 09:00 | `post_event` × 3 bots |
| Weekly synth | Friday 16:00 | `weekly_synth` × 3 bots → then `weekly_synth:portfolio` |
| Codex monthly | Last business day, 17:00 | `codex_monthly` × 3 bots → then `codex_monthly:portfolio` |
| Prune | Daily 03:00 | Soft-delete briefs > 3 yr; hard-delete soft-deleted > 30 d |

### 5.2 Voices (system prompt skeletons)

- **FLAME** — *deliberate, measured, banker tone. Long-duration trades. Patient framing. Treats theta as a craftsman. Opens with: "The forge cools slowly..."*
- **SPARK** — *wry, professional, plain-English. 1DTE. Quick-witted but precise. Treats pin risk and call walls with respect. Opens with: "A spark catches..."*
- **INFERNO** — *punchy, high-energy, war-room tone. 0DTE. Direct sentences. Counts trades and P&L explicitly. Opens with: "The inferno burns..."*
- **Master** (portfolio) — *neutral synthesis voice. Quotes the three bots. Looks for cross-bot patterns. Opens with: "The forge speaks..."*

All voices required to return strict JSON matching the brief schema. Tone instructions are in the system block (cached); per-call data is in the user block (not cached).

### 5.3 Cost estimate

| Trigger | Per-call | Per year |
|---|---|---|
| Daily EOD (3 bots + portfolio) | $0.06 | ~$60 |
| FOMC eve (3 bots × ~8/yr) | $0.05 | ~$1.20 |
| Post-event (3 bots × ~8/yr) | $0.05 | ~$1.20 |
| Weekly synth (3 bots + portfolio × 52) | $0.07 | ~$14.50 |
| Codex monthly (3 bots + portfolio × 12) | $0.10 | ~$4.80 |
| **Total** | | **~$80/yr** |

Prompt caching on system blocks reduces these by ~30-40% in practice.

## 6. UI

### 6.1 `/briefings` (hub)

Three sections stacked:
1. **Weekly synthesis hero** — top, full-width, ~400px tall. Shows current week's `weekly_synth:portfolio` brief. Animated reveal on load. Includes overlaid 5-day equity sparkline.
2. **Recent daily reports** — 2-column on desktop, 1-column on mobile. Most recent first. Card per brief: bot badge, mood glyph, risk score, voice signature, first sentence. Click → `/briefings/[id]`. "Load more" pagination.
3. **Codex side rail** — right column on desktop (below hero on mobile). Last 3 monthly entries, each a small clickable card.

### 6.2 `/briefings/[id]` (single)

Full brief view, hero-sized, sequential animated reveal (600ms total, 100ms stagger):
1. Macro ribbon (top)
2. Voice signature line
3. Title + risk score + mood + P&L
4. Forge Wisdom pull-quote (gold serif italic)
5. Summary prose (2 paragraphs)
6. Trade of the Day card (with SVG payoff diagram) + Factors list (side-by-side on desktop, stacked on mobile)
7. 7-day sparkline
8. Footer actions: [Download PNG] [Open in calendar →]

`prefers-reduced-motion` skips animations.

### 6.3 `/briefings/archive`

Paginated timeline. Filters across top: bot (all/FLAME/SPARK/INFERNO/portfolio), type (all/daily/weekly/codex/event), date-range, risk-score range. 20 briefs per page. Each row is a compact `BriefingCard` that links to `/briefings/[id]`.

### 6.4 `/briefings/codex`

Chronological monthly entries (most recent first). Each card expandable to reveal the full codex prose + a list of "view all daily/weekly briefs from this month" links.

### 6.5 Calendar integration

`CalendarMonthGrid` modifications:
- Past cells with at least one brief render `<CalendarBriefBadge>` in the corner (small custom SVG)
- Hovering pops `<CalendarBriefMiniCard>` (200×120, fixed position): date • per-bot mood-colored dots • portfolio risk score • first sentence of portfolio brief
- Click on cell with briefs → routes to portfolio brief for that date (`/briefings/daily:portfolio:YYYY-MM-DD`)
- Future cells unchanged (Vigil red/green continues)

Badge data fetched via `GET /api/briefings/calendar-badges?from=&to=` (returns `[{date, brief_id, risk_score, mood, first_sentence, bot_moods: {flame, spark, inferno}}]`)

### 6.6 Dashboard integration

Existing `LatestBriefCard.tsx` rewritten to read from `forge_briefings` instead of `{bot}_market_briefs`. Renders the new `BriefingCard` component. Backward compat: if `forge_briefings` has no entries for the bot yet, falls back to legacy table for one cycle.

### 6.7 Nav link

`Nav.tsx`: insert `Briefings` between `Calendar` and `Accounts`. Neutral gray styling.

### 6.8 Visual constraints

- **No emoji** — custom SVG glyphs for mood, badges, voice signatures
- **No stock icons** — match existing IronForge brand weight/style (`/icon-flame.svg`, etc.)
- **Forge Wisdom** — typographic only (gold serif italic, brand color)
- **Mood glyphs** — 4 custom SVGs in IronForge style; tinted to per-bot accent
- **Calendar badge** — custom scroll/parchment glyph; consistent with calendar grid weight
- **PNG export** — server-rendered with consistent custom typography; 1200×630 OG-friendly

## 7. Failure Modes

| Failure | Behavior | User-visible signal |
|---|---|---|
| `CLAUDE_API_KEY` missing | Set status='error:no_api_key' in meta; skip | Admin status banner on `/briefings` |
| Claude 5xx | Increment retry_count; retry once after 5 min; then status='error:{msg}' | Card on `/briefings` with "Generation failed" + retry button |
| Claude returns invalid JSON | Single re-prompt with stricter schema; if still fails → status='error:parse_fail' | Same card |
| DB write failure | Log + skip; never retry write | Backend log only |
| Internal fetch to /api/{bot}/* fails | Use DB-only context; mark `dashboard_state_unavailable=true` in factors | Brief still generated, factor list notes it |
| Vigil calendar query fails | Fall back to no calendar context | Brief still generated |
| Two bots' triggers overlap | Generation is sequential per scheduler tick (not parallel) — avoids API rate-limit | — |
| Scanner restart mid-day | Idempotency on brief_id ensures no duplicates; meta survives restart | — |
| Past brief queried that doesn't exist | 404 on `/api/briefings/[id]` → 404 page on `/briefings/[id]` | 404 page |
| User toggles bot off mid-week | `weekly_synth` for that bot still includes whatever daily briefs exist; portfolio synth handles missing bot gracefully | — |
| Codex generation fails | Daily/weekly briefs continue; codex retried next month | Status visible on `/briefings/codex` |

## 8. Testing Strategy

### 8.1 Unit tests (`tests/forgeBriefings/`)
- `scheduler.tick()` — table-driven over (now, expected_fires) cases including market hours, weekends, EOD time, Friday close, last-business-day, day-after-blackout
- `voices.ts` — system prompt assembly per bot returns correct voice + same JSON schema requirement
- `context.gather()` — mocked DB returns expected aggregated shape; mocked /api fetches return expected dashboard state; macro fetch failure handled gracefully
- `repo.upsertBrief()` — idempotency: same brief_id → UPDATE not INSERT; second call doesn't double-write
- `repo.findByBotDate()` — returns only is_active rows
- `prune.ts` — soft-delete > 3yr, hard-delete soft-deleted > 30d
- JSON schema validator on Claude response shape
- `mood-from-outcome` rules-based classifier

### 8.2 Integration tests (`tests/forgeBriefings/integration/`)
- Mock Claude API, run end-to-end generate for one (bot, type) — assert correct row written
- Run scheduler.tick() at 15:29, 15:30, 15:31 — verify no fire / fire / no-double-fire
- Internal /api/{bot}/status fetch fail → brief still completes with degraded factors

### 8.3 Manual verification (mandatory before merge)
1. `npm run build` — must compile
2. `POST /api/briefings/generate?bot=spark&type=daily_eod` with real Claude key on staging — verify row inserted, response prose makes sense, JSON parses
3. Visit `/briefings` — verify hero renders (use last 7 days of dummy data if needed)
4. Visit `/briefings/[id]` for the just-generated brief — verify all sections render, animations work, PNG export downloads correctly
5. Visit `/calendar` — verify badge appears on today's cell, hover shows mini-card, click navigates
6. Visit `/briefings/archive` — verify filters work, pagination works
7. Toggle `inferno_config.forge_briefings_enabled = FALSE`, force-trigger an INFERNO brief → verify skipped

## 9. Rollout Plan

Per the standing "act autonomously" + "merge proactively" rules:

1. Build feature on `claude/forge-reports` branch
2. Verify with `npm run build` + manual checklist on Render preview
3. Merge to `main` (Render auto-deploys)
4. Once deployed, `POST /api/briefings/generate` for one SPARK daily_eod manually to seed the table and verify the pipeline works end-to-end
5. Within 24h, scheduler will start firing on its own at the configured CT trigger times
6. Watch `forge_briefings_meta` for any error rows in the first week

## 10. Open Items / Future (Wave 2 + later)

- **Wave 2:** convert generation pipeline from pre-stuffed context to Claude tool-use loop (real MCP-style tools: `get_today_trades`, `get_dashboard_state`, `get_calendar_blackouts`, etc.). Lets Claude chase threads. ~2x token cost but more interesting insights.
- **Discord auto-post** (Wave 2 or later): extend `lib/discord.ts` to post EOD + weekly briefs as rich embeds + PNG snapshot
- **Forge Codex deep-dive page**: `/briefings/codex/[YYYY-MM]` showing the codex entry plus a calendar grid of that month with all briefs linked
- **Cross-bot insights**: Master voice could highlight when bots disagree (e.g., FLAME bullish bias, INFERNO bearish bias)
- **PROPHET integration** (much later): feed brief structured factors into the AlphaGEX ML advisor as a feature
