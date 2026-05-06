# IronForge Landing & Auth — Design Spec

**Status:** Draft — recommended direction documented in §6 (final approval pending)
**Date:** 2026-05-06
**Scope:** Public landing page + authentication (sign-up / sign-in) + gating of existing dashboards

---

## 1. Goal

Add a premium, animated public landing page at `/` with full self-serve authentication. The current home page (bots showcase, strategy config, signal flow, exit rules, system footer) becomes the signed-in dashboard at `/dashboard`. All existing bot routes (`/spark`, `/flame`, `/inferno`, `/compare`, `/accounts`) are gated — unauthenticated visitors are redirected to `/sign-in`.

The landing page must look and feel premium (production-quality photography, refined typography, atmospheric animation) — not a wireframe with stock icons.

---

## 2. Routing & Gating

**Public (no auth required):**
- `/` — landing page (new)
- `/sign-in` — sign-in page (new)
- `/sign-up` — sign-up page (new)
- `/forgot-password` — password reset request (new)
- `/reset-password` — password reset form (new, token-validated)
- `/api/auth/*` — NextAuth handlers
- `/api/health` — existing health check (unchanged)
- `/api/landing/stats` — **NEW** — aggregate paper P&L + total trades + composite win rate across all 3 bots, for the Live Stats Strip on the landing. Read-only, derived from existing `{bot}_positions` tables. Cached 60s.

**Gated (require valid session, redirect to `/sign-in?callbackUrl=…` if unauthenticated):**
- `/dashboard` — current home page contents (moved from `/`)
- `/spark`, `/flame`, `/inferno`, `/compare`, `/accounts`, `/briefings`, `/calendar` — existing dashboards
- All `/api/[bot]/*` routes — existing bot APIs (server-side session check)

**Gating mechanism:** Next.js middleware (`src/middleware.ts`) reads the NextAuth JWT cookie and redirects unauthenticated requests for gated paths. API routes additionally verify the session server-side using `getServerSession()` and return `401` if missing.

---

## 3. Authentication

**Library:** NextAuth (Auth.js) v5 with the PostgreSQL adapter (`@auth/pg-adapter`).

**Providers (per user choice B):**
1. **Credentials** — email + password
   - Passwords hashed with `bcrypt` (cost 12)
   - Email + password validated against the `users` table
2. **Google** — OAuth, email scope
   - Requires `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` env vars
   - Auto-creates a user row on first sign-in

**Session strategy:** JWT (signed with `NEXTAUTH_SECRET`), stored in an `httpOnly` cookie. 30-day expiry, sliding refresh.

**Email verification:** Sent on sign-up but not gating in v1.
1. User row created with `email_verified = NULL`
2. Verification email sent with a one-time token (6-hour expiry)
3. User can sign in immediately. A subtle banner shows "Verify your email" until they click the link, then disappears.
4. Verification doesn't gate any specific action in v1 — it's a future hook for if/when we need to confirm contact details (notifications, account recovery, billing).

Google OAuth users are auto-verified (Google has already verified the email).

**Authorization (admin vs. regular user):** IronForge bots are *globally shared* (FLAME/SPARK/INFERNO are single instances, not per-user). To prevent any sign-up from toggling bots or forcing trades:
- Add `is_admin BOOLEAN NOT NULL DEFAULT FALSE` to the `users` table
- Bootstrap admin: any email matching the `IRONFORGE_ADMIN_EMAILS` env var (comma-separated allowlist) is auto-promoted to `is_admin = TRUE` on first sign-in
- Regular users: read-only across all dashboards. Can view positions, equity curves, trade history, performance, scan activity, logs.
- Admin only: `POST /api/[bot]/toggle`, `POST /api/[bot]/force-trade`, `POST /api/[bot]/force-close`, `POST /api/[bot]/eod-close`, `POST /api/[bot]/fix-collateral`, `PUT /api/[bot]/config`, `POST /api/[bot]/pdt`, account CRUD on `/api/accounts/*`.
- Server-side enforcement in each route handler via a `requireAdmin(req)` helper that returns 403 for non-admins.
- UI: action buttons are hidden (not just disabled) for non-admins.

**Password reset:** `/forgot-password` form sends a reset link. Token (24-hour expiry) → `/reset-password?token=…` → new password.

**Email transport:** Resend (or SMTP fallback). One env var: `RESEND_API_KEY`. Falls back to logging the email body to the console in dev if no API key is set.

---

## 4. Database Schema (additions)

NextAuth standard adapter tables, created via the same auto-create pattern as existing IronForge tables (in `@/lib/db.ts`):

```sql
-- NextAuth standard tables
CREATE TABLE IF NOT EXISTS users (
  id              TEXT PRIMARY KEY,
  email           TEXT UNIQUE NOT NULL,
  email_verified  TIMESTAMPTZ,
  password_hash   TEXT,                  -- NULL for OAuth-only users
  name            TEXT,
  image           TEXT,
  is_admin        BOOLEAN NOT NULL DEFAULT FALSE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS accounts (    -- OAuth provider linkage
  id                  TEXT PRIMARY KEY,
  user_id             TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  type                TEXT NOT NULL,
  provider            TEXT NOT NULL,
  provider_account_id TEXT NOT NULL,
  refresh_token       TEXT,
  access_token        TEXT,
  expires_at          BIGINT,
  token_type          TEXT,
  scope               TEXT,
  id_token            TEXT,
  session_state       TEXT,
  UNIQUE (provider, provider_account_id)
);

CREATE TABLE IF NOT EXISTS sessions (
  id            TEXT PRIMARY KEY,
  session_token TEXT UNIQUE NOT NULL,
  user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires       TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS verification_tokens (
  identifier TEXT NOT NULL,              -- email
  token      TEXT UNIQUE NOT NULL,
  expires    TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (identifier, token)
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
  token      TEXT PRIMARY KEY,
  user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires    TIMESTAMPTZ NOT NULL,
  used_at    TIMESTAMPTZ
);
```

These are **shared** tables (no `flame_/spark_/inferno_` prefix). They live alongside `ironforge_accounts`, `ironforge_pdt_config`, etc.

---

## 5. Visual System (locked)

**Design direction:** Editorial Cinematic — Apple/Hermès/Aesop-grade restraint with a fire-themed atmospheric layer.

**Typography:**
- Display serif: **Cormorant Garamond** (300, 400, 500, 600 weights) — for hero headline, logo, tagline
- Sans: **Inter** (300, 400, 500, 600, 700, 800) — for body, nav, eyebrow, CTAs, forms
- Both loaded from Google Fonts via `next/font/google` (no FOUT, self-hosted at build time)

**Color palette (extends existing `forge-*` tokens):**
- Background base: `#0a0503` (forge-bg-deep), `#0a0a0c` (forge-bg)
- Primary accent: `#fbbf24` (amber-400) — interactive, primary CTA
- Secondary accent: `#f97316` (orange-500) — gradient pairing
- Tertiary accent: `#ef4444` (red-500) — gradient deepening
- Text: `#fafafa` (white), `#fde68a` (warm warm), `#a1a1aa` (muted), `#71717a` (dim)
- Hot iron gradient: `linear-gradient(180deg, #fef3c7 0%, #fbbf24 50%, #b45309 100%)`

**Hero atmospheric stack (5 layers, in z-order):**

The fire is **the photo's own fire**, not a fake layer added on top. Adding fire-shaped CSS overlays to a photo that already shows fire reads as cheap and doubled-up (an early pitch attempted SVG flame "tongues" and was scrapped on user feedback). The photo is the fire. Everything else is subtle atmosphere.

1. **Background photograph** — full-bleed Unsplash forge image (variant from §6) with cinematic dark gradient overlay so text always sits on dark. Photo has a slow 6s `brightness/saturate/contrast` pulse so the fire in the photo feels like it's breathing instead of frozen. No fake flame layer added.
2. **Color grading wash** — warm radial overlays (`mix-blend-mode: overlay`, opacity 0.5) to make the photo's fire pop more.
3. **Heat shimmer** — vertical waver overlay at bottom 220px, pure CSS `repeating-linear-gradient` of faint warm bands with `filter: blur(2px)` and a 4s `translateY` cycle. Suggests heat distortion without a heavy SVG filter.
4. **Ember field, three depths:**
   - Background embers (12 instances, `2px`, slow 14s rise, faint)
   - Mid embers (11 instances, `3px`, 9s rise, glowing amber-orange)
   - Foreground bokeh embers (5 instances, `9px` blurred, 7s rise, large soft red-orange)
5. **Spark stream** — 8 continuous sparks emanating from a single anvil-point (mid-hero), varied trajectories, 3.5s ease-out.

Plus the cursor warm glow (380px radial, `mix-blend-mode: screen`, fades in/out on hover) and a slow gold sweep across the primary CTA every 4s.

**Animation philosophy:** Ambient layers are slow (4–14s cycles) and soft (blurred, eased). Interactive layers (see §5b) are immediate but proportionate. The page should read as atmosphere when idle, alive when engaged.

**Performance budget:**
- All ambient animations are CSS transforms/opacity (GPU-accelerated)
- Embers + sparks are static DOM nodes with staggered animation delays
- Hero photograph is `next/image` with `priority` and AVIF/WebP
- Interactive handlers throttle (`mousemove` ember spawn capped at ~14/sec) and clean up nodes (`setTimeout` removal so the DOM doesn't grow)
- All interactivity is `prefers-reduced-motion` aware: the cursor ember trail, parallax tilt, and click-strike sparks all collapse to no-ops when reduced motion is set; the magnetic CTA falls back to a static hover-glow

## 5b. Interactive Layer

Interactivity is part of the locked visual system, not an optional polish pass. The interactive features all live on the hero (and propagate to every Hero variant) and are wired by a single `useInteractiveHero()` hook.

| Interaction | Trigger | Behaviour | Implementation |
|-------------|---------|-----------|----------------|
| **Cursor ember trail** | `mousemove` over hero | Small embers (`4px`, glowing amber) spawn at the cursor and drift up + fade over ~1.4s. Throttled to ~14/sec. | One DOM node per spawn, removed after animation ends. |
| **Cursor warm glow** | `mousemove` over hero | A soft `320×320px` warm radial glow (`blur(24px)`, `mix-blend-mode: screen`) follows the cursor. Fades in on enter, out on leave. | Single persistent element, position via CSS vars. No reflow. |
| **Click-to-strike** | `click` on hero (not on a CTA / nav / logo) | Spawns a shockwave ring (`scale 0 → 8`, opacity `1 → 0`) plus 12 sparks bursting radially from the click point with `±0.4rad` angle jitter. ~1s. | Per-click DOM allocation, all removed after `setTimeout`. |
| **Parallax photo tilt** | `mousemove` over hero | The hero photograph translates ±12px / ±8px on its `transform` based on cursor position. Eased via `cubic-bezier(0.16, 1, 0.3, 1)` so it feels weighted, not jittery. | CSS transform on `<img>`. |
| **Magnetic primary CTA** | `mousemove` within 120px of CTA centre | The "Join the Forge" button gently lerps toward the cursor (max `25%` of the offset, plus a `1.04×` scale boost at full pull). Returns to rest on `mouseleave`. | CSS transform from JS-computed deltas. |
| **CTA hover glow intensify** | `mouseenter` on primary CTA | Box-shadow doubles in radius and intensity. Pure CSS. | `:hover` state. |
| **Logo mark flip** | `mouseenter` on `<Logo>` | Diamond mark spins `180°` + `1.15×` scale. 600ms eased. Pure CSS. | `:hover` state on parent. |
| **Nav link ignite** | `mouseenter` on nav links | Color shifts to amber + adds an amber text-shadow. 200ms. Pure CSS. | `:hover` state. |
| **Bot card ignite** | `mouseenter` on bot cards (Section 7.2) | Card lifts `−4px`, border color shifts to bot-tint, edge gets a faint embered glow. Pure CSS + a small ember field per card that fades in on hover. | `:hover` state + opacity-toggled child layer. |
| **Scroll reveal** | `IntersectionObserver` per section | Sections 7.2–7.7 fade in with a 12px upward translate as they cross 30% viewport. Stagger children by `60ms`. | Framer Motion `whileInView` with `viewport={{ once: true, margin: '-30%' }}`. |
| **Scroll-driven forge intensity** | `scroll` over the hero | As the user scrolls past the hero, the forge-breath pulse subtly amplifies (one-shot, capped). Signals "you've seen the hero, the forge is hotter now". | Framer Motion `useScroll` + `useTransform`. |
| **Live stats count-up** | section enters viewport | The Live Stats Strip (§7.4) numbers count up from 0 to actual value over 1.4s easing. Once per visit. | Single `requestAnimationFrame` loop per stat. |

All effects share these constraints: GPU-friendly properties only (`transform`, `opacity`), throttled where touching the DOM, removed cleanly, and gated by `prefers-reduced-motion`.

The rest of the page (sections 7.2 onward) inherits the same interactive system at a smaller scale — bot card hover effects mirror the hero's hover behavior; the final CTA section repeats the strike effect.

---

## 6. Hero Variations (USER TO PICK 1 OF 15)

**My recommendation:** Variant **#4 The Mythic** photo + the *"As iron sharpens iron"* headline (the user-flagged favorite in §6, photo `1557951959-e3e30ee937e5`). It's the heaviest fire imagery in the set, the headline is the Proverbs verse the user explicitly said is meaningful, and it pairs naturally with the deeper scriptures referenced in §7 below.

The recommendation is shown end-to-end (live flames, integrated sign-up, 3-pillar Why section, final CTA) in `final-pitch.html` in the brainstorm artifacts. **The user retains all 15 options for comparison** — the recommendation is not a lock-in.


All fifteen share the locked visual system (§5) and the locked interactive system (§5b). They differ in **photograph, eyebrow, headline, tagline, CTA copy, and footer scrim**. Grouped into three families so the user can compare like-with-like.

**Originals (with people / hammer at the forge — the variants the user reacted positively to):**

| # | Personality | Photo (Unsplash) | Headline | Tone |
|---|-------------|------------------|----------|------|
| 1 | **The Scripture** | photo-1716469801932-3b1b5494615c | *As iron sharpens iron* | Scholarly, biblical |
| 2 | **The Declaration** | photo-1685713011172-3ba27ff25e22 | *Forged in fire.* | Confident, modern |
| 3 | **The Discipline** | photo-1711829799900-42470ee55689 | *Where discipline meets edge* | Cerebral, institutional |
| 4 | **The Mythic ⚒** *(user-flagged favorite)* | photo-1557951959-e3e30ee937e5 | *The forge of markets* | Epic, dramatic — heaviest fire imagery, hammer eyebrow |
| 5 | **The Minimal** | photo-1716469801933-1d7db4c8aebb | *Sharpen the edge.* | Stripped down, Apple-grade |

**Fire only (abstract flames, no people):**

| # | Personality | Photo (Unsplash) | Headline | Tone |
|---|-------------|------------------|----------|------|
| 6 | **The Crucible** | photo-1566996533071-2c578080c06e | *Tempered by the market* | Process metaphor |
| 7 | **Pure Ember** | photo-1721585621878-fb2c9404cb23 | *Where signal becomes fire* | Abstract, atmospheric |
| 8 | **Strike. Refine. Repeat.** | photo-1727593458591-aed56a590222 | *Strike. Refine. Repeat.* | Process pitch, mirrors 1-min scan loop |
| 9 | **Liquid Heat** | photo-1612881177996-23adb4bb5a74 | *Liquid edge. Solid execution.* | Two-state metaphor (data → trades) |
| 10 | **Crimson Forge** | photo-1639337296777-563a536975f1 | *Built in fire.* | Most stripped down, premium-watch energy |

**New variety (anvil / hammer / glowing coals — variations on the hammer theme):**

| # | Personality | Photo (Unsplash) | Headline | Tone |
|---|-------------|------------------|----------|------|
| 11 | **The Hammer Strike ⚒** | photo-1777107508758-c5047c8ec37c | *Every cycle a hammer-fall* | Most literal hammer/scan-cycle metaphor |
| 12 | **Smith's Hand ⚒** | photo-1690056860816-375fe7a7a67a | *Forged with intent.* | Humanizes the bots — "crafted with care, run by machine" |
| 13 | **Coalbed** | photo-1621034817184-4c667b132f92 | *Patience · Heat · Edge* | The patience-before-action moment |
| 14 | **Embers Beneath** | photo-1628533132956-749bbe170b06 | *Quiet fire. Loud results.* | "Ignore the noise" trader mindset |
| 15 | **The Smelter** | photo-1777150931512-ff3b5eac3144 | *Refined by repetition.* | Repetition as the strategy itself |

**Decision required:** User picks 1 of 15 — that becomes the locked hero copy. The other fourteen are deleted from this spec and the implementation plan.

---

## 7. Page Structure

The landing page (`/`) is a single scrollable page with these sections:

1. **Hero** (above the fold) — the chosen variant from §6, ~100vh, with **integrated inline sign-up** (Google button + email/password form) on the right column so visitors can convert without scrolling. Left column carries the eyebrow, headline, tagline, scripture pull-quote, and a 4-stat strip (Bots Live / Scan Interval / Underlying / Transparency).
2. **Why IronForge — Three Pillars** — three cards on a dark forge backdrop, each with a Roman-numeral heading, a body paragraph, and a Bible verse footer. Pillars: *Refined by repetition* (Proverbs 17:3), *Patience over pressure* (Proverbs 16:32), *Sharpened by fire* (1 Peter 1:7). Each pillar fades + slides up on scroll.
3. **The Three Bots** — three cards (FLAME / SPARK / INFERNO) with current bot icons, brief description, DTE badge. Cards have subtle hover lift + glow per bot color (matches existing `botGlow` system) plus an "ignite on hover" ember field per card.
4. **How It Works** — 4-step horizontal flow (Market Data → Filter Gates → Strike Calc → Execute), styled like the existing "Signal Flow" section but with refined typography.
5. **Live Stats Strip** — calls the new public `/api/landing/stats` endpoint (§2). Shows aggregate paper P&L, total trades, composite win rate. Animated count-up on scroll into view. Refreshes every 60s via SWR.
6. **Architecture** — short visual showing Next.js + Render + Postgres + Tradier (no full audit, just trust signals).
7. **Final CTA** — full-bleed dark section with a pulsing forge-glow at the bottom, the *"As iron sharpens iron"* verse displayed in full, and a single oversized "Create Your Account →" button.
8. **Footer** — minimal: logo, links to `/sign-in`, `/sign-up`, GitHub (if public), the Proverbs verse, copyright.

**Scriptures referenced across the page (the user noted these are deep and meaningful — keep them):**

| Where | Verse | Reference |
|-------|-------|-----------|
| Hero eyebrow + final CTA | *As iron sharpens iron, so one person sharpens another.* | Proverbs 27:17 |
| Hero scripture-block | *I have refined you, though not as silver; I have tested you in the furnace of affliction.* | Isaiah 48:10 |
| Pillar i (Repetition) | *The crucible for silver and the furnace for gold, but the LORD tests the heart.* | Proverbs 17:3 |
| Pillar ii (Patience) | *Better a patient person than a warrior, one with self-control than one who takes a city.* | Proverbs 16:32 |
| Pillar iii (Refinement) | *Your faith of greater worth than gold, which perishes even though refined by fire.* | 1 Peter 1:7 |

Sections 2–6 use scroll-triggered fade/slide-in via Framer Motion's `whileInView`. Stagger the children so it reads as choreographed, not all-at-once.

---

## 8. Sign-Up / Sign-In Flow

**Sign-up** (`/sign-up`):
- Same dark background + drifting embers as the landing
- Centered card (max-width 420px) on a dark forge backdrop
- "Create your account" heading in Cormorant Garamond
- Google button (white) → continues to OAuth, returns to `/dashboard`
- Divider "or with email"
- Inputs: name, email, password (with strength indicator), confirm password
- Submit → creates user row, sends verification email, signs them in, redirects to `/dashboard?verify=pending`

**Sign-in** (`/sign-in`):
- Same shell as sign-up
- "Welcome back" heading
- Google button + email/password
- "Forgot password?" link → `/forgot-password`
- "No account? Sign up" link → `/sign-up`

**Forgot password** (`/forgot-password`):
- Email input → POST `/api/auth/forgot-password` → email sent (always responds 200 to prevent enumeration) → success message

**Reset password** (`/reset-password?token=…`):
- Validates token, shows new password form, updates `password_hash`, marks token used, signs them in, redirects to `/dashboard`

**Visual treatment:** All four pages share one shell component (`<AuthShell>`) so they feel like one continuous flow.

---

## 9. Components (new files)

```
ironforge/webapp/src/
├── app/
│   ├── page.tsx                         (REWRITTEN — landing page)
│   ├── dashboard/page.tsx               (NEW — current page.tsx contents)
│   ├── sign-in/page.tsx                 (NEW)
│   ├── sign-up/page.tsx                 (NEW)
│   ├── forgot-password/page.tsx         (NEW)
│   ├── reset-password/page.tsx          (NEW)
│   └── api/
│       └── auth/
│           ├── [...nextauth]/route.ts   (NEW — NextAuth handler)
│           ├── sign-up/route.ts         (NEW — credentials sign-up)
│           ├── forgot-password/route.ts (NEW)
│           └── reset-password/route.ts  (NEW)
├── components/
│   ├── landing/
│   │   ├── Hero.tsx                     (NEW — chosen variant from §6)
│   │   ├── EmberField.tsx               (NEW — atmospheric layer)
│   │   ├── SparkBurst.tsx               (NEW)
│   │   ├── BotCards.tsx                 (NEW)
│   │   ├── HowItWorks.tsx               (NEW)
│   │   ├── LiveStatsStrip.tsx           (NEW — count-up via requestAnimationFrame)
│   │   ├── ArchitectureSection.tsx      (NEW)
│   │   ├── FinalCTA.tsx                 (NEW)
│   │   └── Footer.tsx                   (NEW)
│   └── hooks/
│       ├── useInteractiveHero.ts        (NEW — wires §5b: cursor trail, click-strike, parallax, magnetic CTA)
│       └── useReducedMotion.ts          (NEW — wraps `prefers-reduced-motion` for §5b gating)
│   ├── auth/
│   │   ├── AuthShell.tsx                (NEW — shared sign-in/up/reset shell)
│   │   ├── GoogleButton.tsx             (NEW)
│   │   ├── EmailPasswordForm.tsx        (NEW)
│   │   └── PasswordStrengthMeter.tsx    (NEW)
│   └── Nav.tsx                          (UPDATED — sign-in/sign-out states)
├── lib/
│   ├── auth.ts                          (NEW — NextAuth config)
│   └── db.ts                            (UPDATED — auto-create auth tables)
└── middleware.ts                        (NEW — gating logic)
```

---

## 10. Environment Variables (additions)

```bash
# Required
NEXTAUTH_URL=https://ironforge.app                # or localhost in dev
NEXTAUTH_SECRET=<generated 32-byte base64 secret>
GOOGLE_CLIENT_ID=<from Google Cloud Console>
GOOGLE_CLIENT_SECRET=<from Google Cloud Console>
IRONFORGE_ADMIN_EMAILS=shairan2016@gmail.com      # comma-separated; auto-promotes these users on first sign-in

# Optional (email transport — if absent, emails log to console in dev)
RESEND_API_KEY=<from resend.com>
EMAIL_FROM="IronForge <noreply@ironforge.app>"
```

These get added to the Render web service env vars and `.env.local.example` in the repo.

---

## 11. Out of Scope (v1)

- Multi-factor authentication (TOTP, SMS) — defer
- Social providers beyond Google (GitHub, Apple, etc.) — defer
- Account deletion UI — manual via DB for now
- User profiles / avatars beyond what Google supplies — defer
- Per-user bot ownership (right now FLAME/SPARK/INFERNO are global; a future v2 may make them per-user, but not here)
- Billing / paid tiers — defer
- Email change flow (with re-verification) — defer

---

## 12. Open Questions (resolved)

| Question | Answer |
|----------|--------|
| Where does the landing live? | Option **iii** — `/` is public, all dashboards gated |
| Auth library? | **NextAuth (Auth.js) + Postgres** |
| Login methods? | **Email/password + Google** |
| Visual direction? | **Editorial Cinematic** with 5-layer atmospheric stack |
| Hero variant? | **TBD — user to pick 1 of 5 (see §6)** |

---

## 13. Implementation Phases (high-level)

1. **Auth foundation** — install NextAuth, schema migration, env vars, `/api/auth/*`, password hashing, Google OAuth wired
2. **Auth UI** — `<AuthShell>` + sign-in / sign-up / forgot / reset pages
3. **Gating** — `middleware.ts` + server-side session checks on all `/api/[bot]/*` routes
4. **Landing page** — chosen hero variant + sections 2–7
5. **Dashboard move** — current `/` contents → `/dashboard`, update Nav
6. **Polish** — scroll animations, count-up stats, performance pass (Lighthouse ≥ 95 on landing)

Detailed phase plan to be written by the `writing-plans` skill after the hero variant is selected.

---

*Brainstorm artifacts (5 hero mockups) preserved in `.superpowers/brainstorm/20817-1778098362/content/`.*
