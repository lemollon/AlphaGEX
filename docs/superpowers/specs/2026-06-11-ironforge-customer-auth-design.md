# IronForge Customer Authentication — Design

**Date:** 2026-06-11
**Status:** Approved (brainstorming) — pending implementation plan
**Depends on:** Sub-projects C (customer DB + signup), D (email transport), F (onboarding guard) — all shipped + live.
**Supersedes:** the temporary onboarding handoff cookie as the *sole* credential for reaching `/onboarding/*`.

## Purpose

Give IronForge customers a real, durable login + session so they can return to the
site, resume onboarding, and (later) reach the product. Today the only customer
identity bridge is the short-lived signed **onboarding handoff cookie** minted at
email verification (sub-project F); it is not a login session and grants nothing but
onboarding access. This sub-project adds genuine customer authentication by
**extending the existing custom iron-session + bcrypt stack** (the same stack that
already powers the 3 internal operators), rather than adopting a managed auth vendor.
Sub-project C already stored a bcrypt `password_hash` on the customer `users` row, so
this is the natural continuation of that decision.

## Decisions (locked during brainstorming)

1. **Build, not buy** — extend the in-house iron-session + bcrypt stack. No new vendor.
   `password_hash` on the customer `users` row stays the source of truth;
   `auth_user_id` remains an unused nullable hook.
2. **Approach A — separate customer session, customer owns `/login`.** `/login`
   becomes the customer login. Operators relocate to `/ops/login`. Two **distinct**
   session cookies, never cross-honored.
3. **Scope:** login + session + logout, onboarding resume, forgot/reset password,
   resend-verification + unverified-login handling. (All four selected.)

## Non-Goals (YAGNI)

- MFA / 2FA, social login, "remember me" tiers.
- Server-side session revocation lists (iron-session is stateless/encrypted-cookie).
- A customer dashboard or product area — none exists yet; post-onboarding lands on a
  placeholder.
- Account-settings / profile editing.
- **Login rate-limiting / brute-force throttling** — neither operator nor customer
  login has it today. Called out as a recommended **fast-follow**, not built here.

---

## Architecture

### 1. Session isolation (core safety property)

New module `ironforge/webapp/src/lib/auth/customer-session.ts`:

- Cookie name: **`ironforge_customer`** (distinct from the operator `ironforge_session`).
- Shape: `CustomerSessionData { customerId: string /* uuid */, email: string, emailVerified: boolean, onboardingStep: string }`.
- `customerSessionOptions`: `password = IRONFORGE_SESSION_SECRET` (reused), `cookieName = 'ironforge_customer'`, `httpOnly`, `secure` in production, `sameSite: 'lax'`, `maxAge` 30 days, `path: '/'`.
- `getCustomerSession()` — Node accessor via `getIronSession<CustomerSessionData>(cookies(), customerSessionOptions)` (mirrors `lib/auth/server.ts`).
- Middleware reads it the same Edge-safe way the operator session is read today
  (separate `getIronSession` call with `customerSessionOptions`).

**Invariant:** the operator gate reads ONLY `ironforge_session`; the customer gate
reads ONLY `ironforge_customer`. A customer session can never satisfy operator gating
because the operator path never looks at the customer cookie. This is structural, not
a runtime branch that can be fumbled.

### 2. Routes & pages

| Path | Type | Auth store | Notes |
|------|------|-----------|-------|
| `/login` | page | customer | **Repurposed** to customer login (email + password). "Forgot password?" link, link to `/signup`. |
| `/ops/login` | page | operator | The existing operator login form **relocated** from `/login`. |
| `/forgot-password` | page | — | Email input → generic confirmation. |
| `/reset-password?token=…` | page | — | New password + confirm; reuses signup password-rule checklist. |
| `POST /api/auth/customer-login` | route | customer | NEW. Verify email+password, set customer session, return next route. |
| `POST /api/auth/customer-logout` | route | customer | NEW. Destroy customer session. |
| `GET /api/auth/customer-me` | route | customer | NEW. Returns the current customer (or 401) for client use. |
| `POST /api/auth/forgot-password` | route | — | NEW. Enumeration-safe reset request. |
| `POST /api/auth/reset-password` | route | — | NEW. Consume token, set new password_hash. |
| `POST /api/auth/login` | route | operator | **Unchanged** — still authenticates `ironforge_users`; the operator page just moves. |
| `POST /api/auth/resend-verification` | route | — | **Existing** (sub-project D), reused by unverified-login. |

All customer auth routes are `runtime = 'nodejs'` (bcrypt + pg). All read/write the
customers DB via `@/lib/customers-db`.

### 3. `customer-login` behavior

```
POST /api/auth/customer-login { email, password }
```
1. Normalize email (reuse `normalizeEmail`). Look up `users` by email.
2. Constant-work bcrypt compare (always run a compare even on miss to limit timing
   leak — verify against a dummy hash when the user is absent). Invalid → 401
   `invalid_credentials` (generic, no enumeration of which field).
3. If valid but `email_verified = false` → **403 `email_unverified`**, NO session set.
4. If valid + verified → set customer session `{ customerId, email, emailVerified: true,
   onboardingStep }`, update `users.last_login_at = now()`, write `CUSTOMER_LOGIN`
   audit, return `{ ok: true, next: nextRouteForOnboarding(onboardingStep) }`.

### 4. Onboarding resume

Pure resolver (testable, no I/O) in `lib/auth/onboarding-route.ts`:

```
nextRouteForOnboarding(step):
  'account_created' | 'email_verified' → '/onboarding/legal'
  'legal_accepted'                      → '/onboarding/complete'
  (unknown / future step)               → '/onboarding/complete'  // safe default; future steps add cases
```

- `/onboarding/complete` — placeholder page: "You're all set — billing, brokerage
  connection, and risk profile are coming soon." This is where future onboarding
  steps slot in.
- The `/onboarding/*` middleware guard (sub-project F) gains **customer session** as an
  accepted credential, alongside the existing handoff cookie / operator session /
  service token. The handoff cookie remains for the email-click moment (the user is not
  logged in when they click the verify link); a returning customer instead logs in and
  the customer session carries them back into the funnel.

### 5. Unverified-login UX

The `/login` page, on a `403 email_unverified` response, swaps the form for a
"Verify your email" panel with a **Resend verification email** button posting to the
existing `/api/auth/resend-verification` (generic-ok, no enumeration).

### 6. Forgot / reset password

New table (customers DB, auto-created in `customers-db.ts` `INIT_DDL`):

```sql
CREATE TABLE IF NOT EXISTS password_reset_tokens (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id),
  token_hash TEXT NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  consumed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_prt_token_hash ON password_reset_tokens(token_hash);
```

Token generation/hashing reuses the `verification-token.ts` pattern (raw in the link,
sha256 hash stored). TTL = 1 hour.

- `POST /api/auth/forgot-password { email }` → **always** `{ ok: true }`. If the user
  exists: create a reset token + send a reset link via a new `sendPasswordResetEmail`
  in `lib/email.ts` (guarded by the existing Resend config; no-op when unset). Write
  `PASSWORD_RESET_REQUESTED` audit. Never reveals whether the email exists.
- Reset link → `/reset-password?token=<raw>`.
- `POST /api/auth/reset-password { token, password, confirmPassword }`:
  validate token (exists, unexpired, unconsumed) → validate password rules (reuse
  `checkPassword` / signup rules) → `UPDATE users SET password_hash` → consume token →
  `PASSWORD_RESET` audit → respond `{ ok: true }`; page redirects to `/login?reset=1`.
  (Stateless sessions can't be force-revoked here; acceptable for v1 — noted.)

### 7. Middleware adjustments (`src/middleware.ts`, `src/lib/auth/access.ts`)

- **Operator-wall redirect target** changes `/login` → **`/ops/login`** so a bounced
  operator does not land on the customer login.
- **`/onboarding/*` guard** additionally accepts a valid **customer session**.
- **Public allowlist** (`access.ts` `PUBLIC_EXACT`) adds: `/forgot-password`,
  `/reset-password`, `/ops/login`, `/api/auth/customer-login`,
  `/api/auth/customer-logout`, `/api/auth/customer-me`, `/api/auth/forgot-password`,
  `/api/auth/reset-password`. (`/login`, `/signup`, `/api/auth/login` already public.)
- The operator wall remains gated by the operator session exactly as today.

### 8. Customers DB additions (`lib/customers-db.ts`)

- `password_reset_tokens` table (above).
- `last_login_at TIMESTAMPTZ` column on `users` (additive; `ALTER TABLE … ADD COLUMN
  IF NOT EXISTS` appended to `INIT_DDL`).

---

## Data flow (returning customer, mid-onboarding)

```
/login (email+password)
  → POST /api/auth/customer-login
      verified? → set ironforge_customer cookie, last_login_at, CUSTOMER_LOGIN audit
      → next = nextRouteForOnboarding('email_verified') = /onboarding/legal
  → client redirects to /onboarding/legal
  → middleware: /onboarding/* allowed by valid customer session
  → LegalForm → POST /api/onboarding/accept-legal → onboarding_step='legal_accepted'
  → /onboarding/complete (placeholder)
```

## Error handling

- All customer auth routes 503 gracefully when `CUSTOMERS_DATABASE_URL` is unset
  (`isCustomersDbConfigured()` guard, same as signup).
- `customer-login`: generic `invalid_credentials` (401) vs `email_unverified` (403);
  no email enumeration on the generic path.
- `forgot-password`: never reveals account existence.
- Email send failures are non-blocking and logged (mirrors signup/D).
- Audit writes are best-effort and never block the user (mirrors C).

## Testing (vitest, existing patterns)

- `customer-session` round-trip (set/read claims; isolation from operator cookie).
- `nextRouteForOnboarding` resolver — every step → expected route, incl. unknown.
- reset-token generate/verify/expiry (reuse or mirror `verification-token` tests).
- `forgot-password` enumeration-safe contract (same response for known/unknown email;
  fetch/email mocked).
- `customer-login` contract: invalid → 401, unverified → 403 (no session), valid →
  session + next route (DB + bcrypt mocked or against the validation seam).
- Verification = `npx vitest run <touched files>` + `npx next build`.

## Files

**New**
- `src/lib/auth/customer-session.ts`
- `src/lib/auth/onboarding-route.ts` (pure resolver)
- `src/app/api/auth/customer-login/route.ts`
- `src/app/api/auth/customer-logout/route.ts`
- `src/app/api/auth/customer-me/route.ts`
- `src/app/api/auth/forgot-password/route.ts`
- `src/app/api/auth/reset-password/route.ts`
- `src/app/forgot-password/page.tsx`
- `src/app/reset-password/page.tsx`
- `src/app/ops/login/page.tsx` (relocated operator login)
- `src/app/onboarding/complete/page.tsx` (placeholder)
- tests under `src/lib/__tests__/`

**Modified**
- `src/app/login/page.tsx` → customer login form (email/password)
- `src/lib/customers-db.ts` → `password_reset_tokens` + `last_login_at`
- `src/lib/email.ts` → `sendPasswordResetEmail`
- `src/middleware.ts` → operator redirect → `/ops/login`; `/onboarding/*` accepts customer session
- `src/lib/auth/access.ts` → public allowlist additions
- `src/components/Shell.tsx` → full-bleed for new auth/onboarding screens
- `src/app/api/auth/verify/route.ts` → (optional) post-verify can also set the customer session directly so the user is logged in immediately after clicking the email link — **decide in plan**; default keeps handoff-cookie-only to avoid auto-login-from-email-link semantics.

## Open question deferred to implementation plan

- Whether email verification should *also* establish a customer session immediately
  (auto-login from the email link) or keep the current handoff-cookie-only bridge and
  require an explicit login. Default: keep handoff-cookie-only; revisit if the UX
  warrants. Listed so the plan makes an explicit call.
