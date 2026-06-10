# IronForge Design Refresh + Create Account Screen — Design Spec

**Date:** 2026-06-10
**Scope:** Phase A (global design refresh) + Phase B (Create Account screen UI). The
broader Account Creation enrollment flow (real auth, email verification, Attio CRM,
audit events, onboarding route guard) is **explicitly out of scope here** and
tracked as separate sub-projects C–F.

---

## 1. Background & Reframing

The original ask was "use this mockup as design specs to update the colors and more
in IronForge, with a new logo." During brainstorming the user supplied a formal
handoff doc (`IronForge_AccountCreation_DeveloperHandoff_v1`) that defines a full
**Account Creation enrollment flow (Phase 1)** — far larger than a styling change.

That work decomposes into six sub-projects:

| # | Sub-project | External dependency | Status |
|---|---|---|---|
| **A** | Design refresh (orange-red palette + new IF logo, site-wide) | none | **THIS SPEC** |
| **B** | Create Account screen (mockup UI + validation) | none | **THIS SPEC** |
| C | Account backend (`users` + `audit_events`, `/api/auth/signup`, auth user) | auth-provider decision + existing-customer-DB reconciliation | deferred |
| D | Email verification (Screen 2 + token flow) | email service | deferred |
| E | Attio CRM sync + retry queue | Attio API token | deferred |
| F | Onboarding route guard → `/onboarding/legal` | depends on C | deferred |

Decisions captured during brainstorming:
- **Sequencing:** phased — ship A+B now; brainstorm C–F later as their own specs.
- **New signup page is a NEW route** — it does **not** replace the home/landing page.
- **Logo:** recreate as crisp SVG (not raster).
- **Existing customer DB:** unknown — investigating it is the explicit first task of
  sub-project C (not this spec).
- **Auth provider:** deferred to sub-project C.

### Key codebase facts that shape the design
- The brand accent is **not** the `flame-*` Tailwind token (0 usages). It is
  **Tailwind's built-in `amber-*` palette — 414 usages across 61 files.**
- Per-bot identity colors are distinct and must stay: **SPARK = `blue-*`**,
  **INFERNO = `red-*`**. Only the brand/amber hue changes.
- Existing `ironforge_users` is an **operator login wall** (username + bcrypt +
  iron-session, 3 seeded operators) — NOT a customer table. The doc's `users` table
  is a different, email-based customer record (sub-project C).
- Logo files `public/ironforge-logo.svg` + `public/favicon.svg` (current: amber
  "anvil") are referenced by `app/layout.tsx`, `components/Nav.tsx`,
  `app/login/page.tsx`, and `app/_landing/landingMarkup.ts`.

---

## 2. Phase A — Global Design Refresh

### A1. Re-hue strategy: override Tailwind's `amber` palette
Because the accent rides on built-in `amber-*` classes, the lowest-risk global re-hue
is to **redefine the `amber` color scale** in `tailwind.config.ts`. All 414 usages
re-skin at once; no per-file class edits; SPARK (`blue`) and INFERNO (`red`) untouched.

New `amber` ramp, anchored on the mockup's primary `#E8531F`:

```
amber: {
  50:  '#FFF3ED',
  100: '#FFE3D3',
  200: '#FFC4A5',
  300: '#FB9B6B',
  400: '#F5743C',   // bright accent text (e.g. "Forge" wordmark)
  500: '#EE5A24',   // primary
  600: '#E8531F',   // button / hover anchor (the mockup CTA)
  700: '#B83C12',
  800: '#92300E',
  900: '#5C1E08',   // deep ember-brown (subtle borders like border-amber-900/30)
}
```

Also in `tailwind.config.ts`:
- Update the `flame` token (`DEFAULT/dark/glow`) to the orange-red set for consistency
  (`#E8531F` / `#C2410C` / `#FB7A3D`).
- Update `backgroundImage.ember-glow` / `ember-subtle` rgba from amber `(245,158,11)`
  to orange `(232,83,31)`.
- Optional minor neutralization of the near-black panels to match the mockup's cooler
  surfaces: `forge.card` `#1c1917 → #16161A`, `forge.border` `#292524 → #262629`.
  `forge.bg` may be nudged `#0c0a09 → #0B0B0D` (low priority; keep if it reads worse).

### A2. `globals.css` raw-hex re-hue
Replace amber hex literals with the orange-red set:
- `body` background radial-gradients: `rgba(245,158,11,…)` / `rgba(217,119,6,…)` →
  orange equivalents `rgba(232,83,31,…)` / `rgba(184,60,18,…)`.
- `.fire-divider` gradient stops `#f59e0b/#d97706` → `#EE5A24/#B83C12`.
- `.glow-amber` / `.glow-flame` text-shadow hexes `#F59E0B` → `#EE5A24`.
- Leave `.glow-spark` (blue) and `.glow-inferno` (red) unchanged.

### A3. New logo (SVG)
Recreate the mockup's mark as crisp SVG and drop in at the existing filenames so all
references update for free:
- `public/ironforge-logo.svg` → **IF block monogram**: a bold geometric two-tone "IF"
  — white/near-white "I", orange "F" (`#E8531F`) — on transparent background, square
  viewBox, optimized at small sizes (used at `h-8/h-9`). Replaces the anvil.
- `public/favicon.svg` → same IF mark.
- The signup left panel renders the full **lockup inline**: IF mark above
  "IRON" (white) + "FORGE" (orange) wordmark, matching Image #2.

No raster PNGs are added; everything is SVG.

### A4. Verification for Phase A
- `npx next build` is green.
- Visual spot-check (description-level, since this is a styling change): Nav, `/login`,
  the landing `/`, and a representative bot dashboard render with the orange-red accent
  and the new logo; SPARK is still blue, INFERNO still red.

---

## 3. Phase B — Create Account Screen (`/signup`)

New route `app/signup/page.tsx`. Two-column layout reproducing the mockup, built on the
refreshed tokens. Copy is taken verbatim from the handoff doc where specified.

### B1. Layout
- **Left brand panel** (hidden/stacked on mobile):
  - IF + IRONFORGE logo lockup.
  - Headline: **"Automated Options Execution"**.
  - Subhead: "Rules-based strategies. Automated execution. Built for traders who
    demand an edge."
  - Three feature rows, each a **custom SVG glyph** (no emojis/stock icons, per house
    style) + title + one-line description:
    - **Secure & Transparent** — "Bank-grade security and total transparency."
    - **Automated Execution** — "Systematic strategies executed 24/7."
    - **You Stay in Control** — "You authorize. We execute. You decide."
  - Footer disclaimer: "IronForge is not a broker dealer and does not provide
    investment advice."
- **Right form card:**
  - Top-right link: **"Already have an account? Log in"** → `/login`.
  - H1: **"Create your account"**.
  - Subtitle (doc §2): "Start your setup for automated options execution. You will
    review disclosures, connect billing, and authorize your brokerage before anything
    is activated."
  - Fields (doc §3), each with a leading SVG icon matching the mockup:
    First Name, Last Name, Email Address, Mobile Phone, **State of Residence**
    (dropdown of 50 US states + DC), Password (show/hide toggle), Confirm Password
    (show/hide toggle), Referral Code (Optional).
  - Three required consent checkboxes (doc §3, copy from mockup):
    1. "I am at least 18 years old and legally able to open and manage a brokerage
       account."
    2. "I understand IronForge provides automated trade execution technology and **does
       not provide financial, investment, tax, or legal advice**." (bold fragment is an
       accent-colored span)
    3. "I agree to receive **electronic communications** related to my account, billing,
       legal notices, and platform activity."
  - Primary CTA: **"Create Account"** (orange `bg-amber-600`), full-width.
  - Trust footer line with a small lock glyph: "Your information is secure. We use
    bank-level encryption to protect your data."

### B2. Validation (frontend — doc §3, §4)
- Trim whitespace; first/last name non-empty.
- Email: valid format; lowercased before submit.
- Phone: valid format; best-effort E.164 normalization.
- State: required selection.
- Password: **≥12 chars AND uppercase AND lowercase AND number AND special char**,
  surfaced as a **live rule checklist** that ticks each rule as satisfied.
- Confirm Password: must equal Password.
- All three checkboxes required.
- **Create Account disabled until the form is valid**; show inline field-level errors
  on blur/submit.
- **Mobile:** single-column stacked fields; checkboxes remain visible above the CTA.
- Duplicate-email handling is wired in the UI (shows "This email is already associated
  with an IronForge account. Log in or reset your password.") but cannot fire against
  the stub (no DB) — it activates in sub-project C.

### B3. Submit behavior (STUB — backend deferred to C/D/E)
- On valid submit, POST JSON to a **new stub** `app/api/auth/signup/route.ts` that:
  - Re-validates the payload **server-side** (same rules as frontend) and normalizes
    email/phone/state/referral.
  - Returns `{ ok: true }` on success or `{ ok: false, error, fields? }` (HTTP 400) on
    validation failure.
  - **Does NOT** create an auth user, write to Postgres, send email, or sync Attio.
    A code comment documents the exact request/response contract so C/D/E wire the real
    pipeline behind the same endpoint without changing the frontend.
- On success the client transitions to the **Screen 2 "Verify your email" visual
  shell** (doc §8): confirmation text + the submitted email + **placeholder** "Resend
  Verification Email" and "Continue" actions (non-functional, clearly stubbed). This
  gives a coherent end-to-end UX now; the real token flow is sub-project D.

### B4. Cross-links
- Add a single **"Create account"** link on `/login` pointing to `/signup`.
- Do **not** modify the landing/home page or its waitlist.

### B5. Verification for Phase B
- `npx next build` is green.
- `/signup` renders the two-column layout (single column on mobile), all fields and
  validation behave per §B2, the CTA is gated, and a valid submit shows the Screen 2
  shell. The stub endpoint returns 200 for a valid payload and 400 for an invalid one.

---

## 4. Files Touched (A + B)

**Modified**
- `ironforge/webapp/tailwind.config.ts` — override `amber` ramp; update `flame` token,
  `ember-glow` gradient, optional `forge.card/border/bg`.
- `ironforge/webapp/src/app/globals.css` — re-hue raw amber hexes.
- `ironforge/webapp/public/ironforge-logo.svg` — new IF monogram.
- `ironforge/webapp/public/favicon.svg` — new IF mark.
- `ironforge/webapp/src/app/login/page.tsx` — add "Create account" link.

**New**
- `ironforge/webapp/src/app/signup/page.tsx` — Create Account screen (client).
- Supporting modules as needed, e.g. `src/lib/us-states.ts` (state list),
  `src/lib/signup-validation.ts` (shared client/server rules), small feature-glyph SVG
  components for the left panel.
- `ironforge/webapp/src/app/api/auth/signup/route.ts` — stub validate-only endpoint.

**Untouched (deferred):** `ironforge_users`, any new `users`/`audit_events` tables,
auth-user creation, email service, Attio, `/onboarding/*`, landing/home page.

---

## 5. Out of Scope (tracked separately)
- C: `users` + `audit_events` schema, real `/api/auth/signup` persistence, auth-user
  creation, duplicate-email enforcement, existing-customer-DB investigation/reconcile.
- D: verification email send/resend, token validation, `email_verified` updates.
- E: Attio contact create/update + `ATTIO_SYNC_FAILED` retry queue.
- F: onboarding route guard and `/onboarding/legal`.

These each get their own brainstorm → spec → plan when their decisions/credentials are
available.

---

## 6. Acceptance Criteria (A + B)
1. Tailwind `amber` override re-hues the site to orange-red; SPARK stays blue, INFERNO
   stays red; `npx next build` green.
2. New IF SVG logo appears in Nav, login, landing, and signup; favicon updated.
3. `globals.css` dividers/glows/background read orange-red, not amber.
4. `/signup` reproduces the mockup two-column layout with all specified fields, copy,
   glyphs, and the orange CTA; responsive single-column on mobile.
5. Frontend validation enforces all doc §3 rules incl. the 12-char password checklist
   and checkbox gating; CTA disabled until valid; inline errors shown.
6. Valid submit hits the stub endpoint (server-side re-validates, returns success
   without persisting) and the client shows the Screen 2 verify-email shell.
7. `/login` has a working "Create account" link to `/signup`; home/landing unchanged.
