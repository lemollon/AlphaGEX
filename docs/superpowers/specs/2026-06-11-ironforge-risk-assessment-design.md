# IronForge Risk Assessment (Suitability → Recommended Bot) — Design

**Date:** 2026-06-11
**Status:** Approved — implementing.
**Depends on:** Sub-project F (onboarding guard + handoff cookie) — shipped + live.
**Relates to:** customer-auth spec (`2026-06-11-ironforge-customer-auth-design.md`, not yet built).

## Purpose

Insert the previously-deferred **risk profile** step into the onboarding funnel. It is a
short, advisory **suitability questionnaire** whose primary job is to **help the customer
choose the right IronForge bot** for their risk profile. It never hard-blocks: it always
completes and produces a risk tier + a recommended bot, with a caution at the low end.

## Decisions (locked during brainstorming)

1. **Purpose:** suitability-informed **recommendation** (not a hard compliance wall).
2. **Output:** answers → **risk tier** (Conservative / Moderate / Aggressive) → **recommended bot**
   (Conservative → FLAME, Moderate → SPARK, Aggressive → INFERNO).
3. **Low end:** never block. A low score recommends the most conservative bot (FLAME) and
   shows a prominent caution. Advisory throughout.

## Non-Goals (YAGNI)

- No hard disqualifiers / blocking.
- No binding enforcement — the recommendation is a strong default; strategy selection /
  deployment authorization (a later onboarding phase) decides what actually runs.
- No income/net-worth dollar capture (kept light; capacity is captured qualitatively).

---

## Funnel placement

New step between legal and completion:

```
email_verified → /onboarding/legal → (accept) onboarding_step='legal_accepted'
  → /onboarding/risk → (submit) onboarding_step='risk_assessed'
  → completion ("you're all set — billing & brokerage coming soon")
```

**Built against the currently-shipped state (F):** `/onboarding/risk` is guarded exactly
like `/onboarding/legal` — a server-component check of the onboarding handoff cookie
(`verifyOnboardingToken`), redirecting to `/login` if absent. No middleware change is
needed (it already matches the `/onboarding/*` rule). The legal step's success now
**redirects to `/onboarding/risk`** instead of showing the terminal "coming soon" panel;
that terminal panel moves to the risk step's post-submit success state.

**Customer-auth coordination (REQUIREMENT for that future build):** when the customer-auth
sub-project is implemented, its `nextRouteForOnboarding` resolver MUST map
`legal_accepted → /onboarding/risk` and `risk_assessed → /onboarding/complete` (not
`legal_accepted → /onboarding/complete`). The customer-auth plan doc currently lives on a
separate branch; this requirement is recorded here as the source of truth and must be
folded into that resolver + its tests before customer-auth ships.

## The questionnaire

Six single-choice questions, each option carrying 0/2/4 points (range 0–24). Stored by
`key`, not by display text, so copy can change without breaking scoring.

| # | key | Question | Options (points) |
|---|-----|----------|------------------|
| 1 | `experience` | Your experience trading options | None (0) · Some, under 2 yrs (2) · Experienced, 2+ yrs (4) |
| 2 | `goal` | Your primary goal | Preserve capital (0) · Steady growth (2) · Aggressive growth (4) |
| 3 | `tolerance` | Your risk tolerance | Avoid losses (0) · Accept moderate swings (2) · Comfortable with large swings for higher return (4) |
| 4 | `drawdown` | If your account dropped 20% in a week, you would | Sell to stop losses (0) · Hold (2) · Add more (4) |
| 5 | `capacity` | This money represents | A large or critical portion of my savings (0) · A moderate portion (2) · A small slice I can afford to lose (4) |
| 6 | `horizon` | Your style / availability to monitor | Long-term, hands-off (0) · Active weekly (2) · Daily, fast-paced (4) |

## Scoring → tier → bot

Pure function `scoreToProfile(answers) → { score, tier, recommendedBot, caution }`:

- Sum the six option points (0–24).
- **0–8 → Conservative → FLAME**
- **9–16 → Moderate → SPARK**
- **17–24 → Aggressive → INFERNO**
- `caution = true` when `tier === 'Conservative'` **OR** `capacity` answer = the
  "large or critical portion" option (capacity override), regardless of total.

Bot rationale strings (shown with the result):
- FLAME: "2-day-to-expiration iron condors — the most conservative, slowest-paced bot."
- SPARK: "1-day-to-expiration iron condors — a balanced middle ground."
- INFERNO: "0-day-to-expiration, aggressive and fast-paced — highest risk and activity."

## Data model (customers DB, via `@/lib/customers-db`)

New table (auto-created in `INIT_DDL`):

```sql
CREATE TABLE IF NOT EXISTS risk_assessments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id),
  answers JSONB NOT NULL,
  score INT NOT NULL,
  tier TEXT NOT NULL,
  recommended_bot TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_risk_assessments_user ON risk_assessments(user_id);
```

Denormalized onto `users` for quick reads:
```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS risk_tier TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS recommended_bot TEXT;
```
Plus `onboarding_step = 'risk_assessed'` on submit, and a `RISK_ASSESSMENT_COMPLETED`
audit event (`{ score, tier, recommended_bot }`).

## Routes & pages

- **`/onboarding/risk`** (`page.tsx` server-guarded + `RiskForm.tsx` client) — the six
  questions as radio groups, a gated Submit, and an inline **result view** after submit:
  "You're a **{tier}** investor — we recommend **{bot}**," the bot rationale, the caution
  banner when applicable, and a **Continue / Finish** action to the completion state.
- **`POST /api/onboarding/risk-assessment`** — self-guards on the onboarding cookie
  (`verifyOnboardingToken`), 503 when customers DB unset, validates all six answers
  present + valid via a pure `validateRiskAnswers`, computes `scoreToProfile`, inserts the
  `risk_assessments` row + updates `users` (tier, bot, step) + audit, returns
  `{ ok, score, tier, recommendedBot, caution }`.

## Error handling

- Missing/invalid answers → 400 with a generic "Please answer every question."
- Customers DB unset → 503 graceful (mirrors legal/signup).
- Audit best-effort, never blocks.

## Testing (vitest)

- `scoreToProfile`: boundary scores 0, 8→Conservative; 9, 16→Moderate; 17, 24→Aggressive;
  capacity-override sets caution at a high score; each bot mapping.
- `validateRiskAnswers`: rejects missing keys / out-of-range option ids; accepts a full set.
- Routes/pages verified by `npx next build`.

## Files

**New**
- `src/lib/onboarding/risk-scoring.ts` — `RISK_QUESTIONS`, `scoreToProfile`, `validateRiskAnswers`, types
- `src/app/onboarding/risk/page.tsx` — server guard
- `src/app/onboarding/risk/RiskForm.tsx` — questionnaire + result client
- `src/app/api/onboarding/risk-assessment/route.ts`
- `src/lib/__tests__/risk-scoring.test.ts`

**Modified**
- `src/lib/customers-db.ts` — `risk_assessments` table + `users.risk_tier`/`recommended_bot`
- `src/app/onboarding/legal/LegalForm.tsx` — on accept, redirect to `/onboarding/risk` (replaces terminal panel)
- `src/components/Shell.tsx` — already full-bleed for `/onboarding/*` (no change needed; confirmed)

Customer-auth resolver coordination is a documented REQUIREMENT (see above), not a file
change in this sub-project — that plan lives on a separate branch.
```
