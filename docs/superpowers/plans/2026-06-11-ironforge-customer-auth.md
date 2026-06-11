# IronForge Customer Authentication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give IronForge customers real login/session/logout, onboarding resume, and forgot/reset password by extending the existing in-house iron-session + bcrypt stack, with a customer session cookie fully isolated from the operator session.

**Architecture:** Approach A from the spec. A new `ironforge_customer` session cookie (separate from operator `ironforge_session`) carries customer identity. `/login` becomes the customer login; the operator login relocates to `/ops/login`. Pure decision helpers (login classifier, onboarding-route resolver) are unit-tested; routes/pages are verified by build. All customer data lives in the `ironforge-customers` Postgres via `@/lib/customers-db`.

**Tech Stack:** Next.js 14 (App Router), TypeScript, iron-session, bcryptjs, Postgres (`pg`), Resend (email), vitest.

**Spec:** `docs/superpowers/specs/2026-06-11-ironforge-customer-auth-design.md`

**Working directory for all paths:** `ironforge/webapp/`
**Verification commands:** `npx vitest run <file>` (tests), `npx next build` (default build check). Run from `ironforge/webapp/`.

---

## File Structure

**New files**
- `src/lib/auth/onboarding-route.ts` — pure `nextRouteForOnboarding(step)` resolver
- `src/lib/auth/customer-auth.ts` — pure `classifyLoginAttempt(...)` decision helper + `TIMING_DUMMY_HASH`
- `src/lib/auth/customer-session.ts` — `ironforge_customer` cookie config + `getCustomerSession()`
- `src/app/api/auth/customer-login/route.ts`
- `src/app/api/auth/customer-logout/route.ts`
- `src/app/api/auth/customer-me/route.ts`
- `src/app/api/auth/forgot-password/route.ts`
- `src/app/api/auth/reset-password/route.ts`
- `src/app/ops/login/page.tsx` — relocated operator login
- `src/app/forgot-password/page.tsx`
- `src/app/reset-password/page.tsx`
- `src/app/onboarding/complete/page.tsx` — post-legal placeholder
- Tests: `src/lib/__tests__/onboarding-route.test.ts`, `customer-auth.test.ts`, `password-reset-email.test.ts`

**Modified files**
- `src/lib/customers-db.ts` — add `password_reset_tokens` table + `last_login_at` column
- `src/lib/email.ts` — add `sendPasswordResetEmail`
- `src/app/login/page.tsx` — repurpose to customer login (email/password + unverified handling + forgot link)
- `src/lib/auth/access.ts` — public allowlist additions
- `src/middleware.ts` — operator redirect → `/ops/login`; `/onboarding/*` accepts customer session
- `src/components/Shell.tsx` — full-bleed for the new auth/onboarding screens

---

## Task 1: Onboarding-route resolver (pure)

**Files:**
- Create: `src/lib/auth/onboarding-route.ts`
- Test: `src/lib/__tests__/onboarding-route.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// src/lib/__tests__/onboarding-route.test.ts
import { describe, it, expect } from 'vitest'
import { nextRouteForOnboarding } from '@/lib/auth/onboarding-route'

describe('nextRouteForOnboarding', () => {
  it('routes fresh / verified accounts to the legal step', () => {
    expect(nextRouteForOnboarding('account_created')).toBe('/onboarding/legal')
    expect(nextRouteForOnboarding('email_verified')).toBe('/onboarding/legal')
  })
  it('routes legal-accepted to the risk-assessment step', () => {
    expect(nextRouteForOnboarding('legal_accepted')).toBe('/onboarding/risk')
  })
  it('routes risk-assessed to the completion placeholder', () => {
    expect(nextRouteForOnboarding('risk_assessed')).toBe('/onboarding/complete')
  })
  it('defaults unknown/null steps to the completion placeholder', () => {
    expect(nextRouteForOnboarding(undefined)).toBe('/onboarding/complete')
    expect(nextRouteForOnboarding(null)).toBe('/onboarding/complete')
    expect(nextRouteForOnboarding('something_future')).toBe('/onboarding/complete')
  })
})
```

> **Note (added 2026-06-11):** the risk-assessment step shipped between legal and
> completion, so `legal_accepted` resolves to `/onboarding/risk` (not `/onboarding/complete`).

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/lib/__tests__/onboarding-route.test.ts`
Expected: FAIL — cannot resolve `@/lib/auth/onboarding-route`.

- [ ] **Step 3: Write minimal implementation**

```ts
// src/lib/auth/onboarding-route.ts
/**
 * Maps a customer's onboarding_step to the route they should resume at after login
 * or email verification (sub-project: customer auth). Pure — no I/O. Future onboarding
 * steps (billing, brokerage, risk profile) add cases here.
 */
export function nextRouteForOnboarding(step: string | null | undefined): string {
  switch (step) {
    case 'account_created':
    case 'email_verified':
      return '/onboarding/legal'
    case 'legal_accepted':
      return '/onboarding/risk'
    case 'risk_assessed':
    default:
      return '/onboarding/complete'
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/lib/__tests__/onboarding-route.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/lib/auth/onboarding-route.ts src/lib/__tests__/onboarding-route.test.ts
git commit -m "feat(ironforge): onboarding-step → resume-route resolver (customer auth)"
```

---

## Task 2: Login classifier (pure)

**Files:**
- Create: `src/lib/auth/customer-auth.ts`
- Test: `src/lib/__tests__/customer-auth.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// src/lib/__tests__/customer-auth.test.ts
import { describe, it, expect } from 'vitest'
import { classifyLoginAttempt } from '@/lib/auth/customer-auth'

describe('classifyLoginAttempt', () => {
  it('is invalid_credentials when the user is missing', () => {
    expect(classifyLoginAttempt({ userExists: false, passwordOk: false, emailVerified: false })).toBe('invalid_credentials')
  })
  it('is invalid_credentials when the password is wrong', () => {
    expect(classifyLoginAttempt({ userExists: true, passwordOk: false, emailVerified: true })).toBe('invalid_credentials')
  })
  it('is email_unverified when creds are valid but email is unverified', () => {
    expect(classifyLoginAttempt({ userExists: true, passwordOk: true, emailVerified: false })).toBe('email_unverified')
  })
  it('is ok when creds are valid and email is verified', () => {
    expect(classifyLoginAttempt({ userExists: true, passwordOk: true, emailVerified: true })).toBe('ok')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/lib/__tests__/customer-auth.test.ts`
Expected: FAIL — cannot resolve `@/lib/auth/customer-auth`.

- [ ] **Step 3: Write minimal implementation**

```ts
// src/lib/auth/customer-auth.ts
/**
 * Pure auth-decision helpers for customer login (sub-project: customer auth).
 * Kept separate from session plumbing (customer-session.ts) and routing
 * (onboarding-route.ts) so the login contract is unit-testable without a DB.
 */

export type LoginOutcome = 'invalid_credentials' | 'email_unverified' | 'ok'

export function classifyLoginAttempt(p: {
  userExists: boolean
  passwordOk: boolean
  emailVerified: boolean
}): LoginOutcome {
  if (!p.userExists || !p.passwordOk) return 'invalid_credentials'
  if (!p.emailVerified) return 'email_unverified'
  return 'ok'
}

/**
 * A real bcrypt hash used ONLY to equalize response timing when no user row is
 * found, so an attacker cannot distinguish "unknown email" from "wrong password"
 * by latency. Never matches any real password. Regenerate with:
 *   node -e "console.log(require('bcryptjs').hashSync('x',10))"
 */
export const TIMING_DUMMY_HASH =
  '$2b$10$2h/JuRccXabXFfJoqnuUgeBWR2f/WqS4aM/6VGsuQPWZxh16Uix3u'
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/lib/__tests__/customer-auth.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/lib/auth/customer-auth.ts src/lib/__tests__/customer-auth.test.ts
git commit -m "feat(ironforge): pure login classifier + timing dummy hash (customer auth)"
```

---

## Task 3: Customer session module

**Files:**
- Create: `src/lib/auth/customer-session.ts`

No unit test (iron-session is encrypted-cookie plumbing exercised by the routes; verified via build + the route tasks). Mirrors `src/lib/auth/session.ts` + `src/lib/auth/server.ts`.

- [ ] **Step 1: Write the module**

```ts
// src/lib/auth/customer-session.ts
import type { SessionOptions, IronSession } from 'iron-session'
import { getIronSession } from 'iron-session'
import { cookies } from 'next/headers'

/**
 * Customer session — DISTINCT from the operator session (src/lib/auth/session.ts).
 * The operator gate reads only `ironforge_session`; the customer gate reads only
 * `ironforge_customer`. They are never cross-honored, so a customer session can
 * never satisfy operator gating. (Sub-project: customer auth, Approach A.)
 */
export interface CustomerSessionData {
  customerId?: string // users.id (uuid) in the ironforge-customers DB
  email?: string
  emailVerified?: boolean
  onboardingStep?: string
}

export const CUSTOMER_SESSION_COOKIE = 'ironforge_customer'

export const customerSessionOptions: SessionOptions = {
  password: process.env.IRONFORGE_SESSION_SECRET || '',
  cookieName: CUSTOMER_SESSION_COOKIE,
  cookieOptions: {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    maxAge: 60 * 60 * 24 * 30, // 30 days
    path: '/',
  },
}

/** Route-handler / server-component accessor (Node runtime only). */
export async function getCustomerSession(): Promise<IronSession<CustomerSessionData>> {
  return getIronSession<CustomerSessionData>(cookies(), customerSessionOptions)
}
```

- [ ] **Step 2: Typecheck via build**

Run: `npx next build`
Expected: `✓ Compiled successfully` (module unused so far — confirms it typechecks).

- [ ] **Step 3: Commit**

```bash
git add src/lib/auth/customer-session.ts
git commit -m "feat(ironforge): isolated customer session cookie (customer auth)"
```

---

## Task 4: Customers DB — reset tokens + last_login_at

**Files:**
- Modify: `src/lib/customers-db.ts` (the `INIT_DDL` template string)

- [ ] **Step 1: Add the table + column to INIT_DDL**

Find the end of `INIT_DDL` (the `idx_evt_token_hash` index line, then the `attio_sync_queue` block added earlier). Append BEFORE the closing backtick:

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

ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;
```

Concretely, locate this existing tail of `INIT_DDL`:

```
CREATE INDEX IF NOT EXISTS idx_attio_queue_pending ON attio_sync_queue(status, attempts);
`
```

and replace it with:

```
CREATE INDEX IF NOT EXISTS idx_attio_queue_pending ON attio_sync_queue(status, attempts);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id),
  token_hash TEXT NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  consumed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_prt_token_hash ON password_reset_tokens(token_hash);

ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;
`
```

- [ ] **Step 2: Build to confirm it compiles**

Run: `npx next build`
Expected: `✓ Compiled successfully`. (DDL is a string; this just confirms no syntax break in the file.)

- [ ] **Step 3: Commit**

```bash
git add src/lib/customers-db.ts
git commit -m "feat(ironforge): password_reset_tokens table + users.last_login_at (customer auth)"
```

---

## Task 5: Password-reset email

**Files:**
- Modify: `src/lib/email.ts`
- Test: `src/lib/__tests__/password-reset-email.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// src/lib/__tests__/password-reset-email.test.ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { sendPasswordResetEmail } from '@/lib/email'

const OLD = { ...process.env }
beforeEach(() => {
  vi.restoreAllMocks()
  process.env.RESEND_API_KEY = 'test-key'
  process.env.EMAIL_FROM = 'IronForge <no-reply@ironforge.test>'
})
afterEach(() => { process.env = { ...OLD } })

describe('sendPasswordResetEmail', () => {
  it('skips when not configured', async () => {
    delete process.env.RESEND_API_KEY
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const res = await sendPasswordResetEmail({ to: 'a@b.com', resetUrl: 'https://x/reset?token=t', firstName: 'Ada' })
    expect(res.skipped).toBe(true)
    expect(fetchMock).not.toHaveBeenCalled()
  })
  it('posts the reset link to Resend on success', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ id: 'e1' }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const res = await sendPasswordResetEmail({ to: 'ada@b.com', resetUrl: 'https://x/reset?token=abc', firstName: 'Ada' })
    expect(res.sent).toBe(true)
    const body = JSON.parse((fetchMock.mock.calls[0][1] as any).body)
    expect(body.to).toBe('ada@b.com')
    expect(body.subject).toMatch(/reset/i)
    expect(body.html).toContain('https://x/reset?token=abc')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/lib/__tests__/password-reset-email.test.ts`
Expected: FAIL — `sendPasswordResetEmail` is not exported.

- [ ] **Step 3: Add the function to `src/lib/email.ts`**

Append at the end of the file (after `sendVerificationEmail`):

```ts
function resetHtml(firstName: string, resetUrl: string): string {
  const name = firstName ? esc(firstName) : 'there'
  return `<!doctype html><html><body style="margin:0;background:#0B0B0D;font-family:Arial,Helvetica,sans-serif;color:#e5e5e5">
  <div style="max-width:480px;margin:0 auto;padding:32px 24px">
    <h1 style="font-size:20px;color:#ffffff;margin:0 0 8px">Reset your password</h1>
    <p style="color:#a3a3a3;font-size:14px;line-height:1.6">Hi ${name}, we received a request to reset your IronForge password. Click below to choose a new one.</p>
    <p style="margin:28px 0">
      <a href="${esc(resetUrl)}" style="display:inline-block;background:#E8531F;color:#ffffff;text-decoration:none;font-weight:bold;font-size:14px;padding:12px 24px;border-radius:6px">Reset password</a>
    </p>
    <p style="color:#737373;font-size:12px;line-height:1.6">If the button does not work, paste this link into your browser:<br>${esc(resetUrl)}</p>
    <p style="color:#525252;font-size:11px;margin-top:28px">This link expires in 1 hour. If you did not request a password reset, you can safely ignore this email.</p>
  </div></body></html>`
}

export async function sendPasswordResetEmail(params: {
  to: string
  resetUrl: string
  firstName: string
}): Promise<SendResult> {
  if (!isEmailConfigured()) return { sent: false, skipped: true }
  try {
    const res = await fetch(RESEND_ENDPOINT, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${process.env.RESEND_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        from: process.env.EMAIL_FROM,
        to: params.to,
        subject: 'Reset your IronForge password',
        html: resetHtml(params.firstName, params.resetUrl),
      }),
    })
    if (!res.ok) {
      const detail = await res.text().catch(() => '')
      return { sent: false, error: `Resend ${res.status}: ${detail.slice(0, 200)}` }
    }
    return { sent: true }
  } catch (e) {
    return { sent: false, error: e instanceof Error ? e.message : 'send failed' }
  }
}
```

Note: `esc`, `RESEND_ENDPOINT`, `isEmailConfigured`, and `SendResult` already exist in `email.ts` from sub-project D — reuse them, do not redeclare.

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/lib/__tests__/password-reset-email.test.ts`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/lib/email.ts src/lib/__tests__/password-reset-email.test.ts
git commit -m "feat(ironforge): password-reset email via Resend (customer auth)"
```

---

## Task 6: Customer login route

**Files:**
- Create: `src/app/api/auth/customer-login/route.ts`

Verified by build (DB + bcrypt; pure logic already tested in Task 2). Mirrors signup route's DB-guard + audit patterns.

- [ ] **Step 1: Write the route**

```ts
// src/app/api/auth/customer-login/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { verifyPassword } from '@/lib/auth/password'
import { normalizeEmail } from '@/lib/signup-validation'
import { classifyLoginAttempt, TIMING_DUMMY_HASH } from '@/lib/auth/customer-auth'
import { nextRouteForOnboarding } from '@/lib/auth/onboarding-route'
import { getCustomerSession } from '@/lib/auth/customer-session'
import { isCustomersDbConfigured, customerQuery, customerExecute } from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

interface UserRow {
  id: string
  password_hash: string
  email_verified: boolean
  onboarding_step: string
}

function clientIp(req: NextRequest): string | null {
  const xff = req.headers.get('x-forwarded-for')
  return xff ? xff.split(',')[0].trim() : null
}

async function audit(userId: string | null, eventType: string, req: NextRequest, metadata: Record<string, unknown>) {
  try {
    await customerExecute(
      `INSERT INTO audit_events (user_id, event_type, ip_address, user_agent, metadata)
       VALUES ($1, $2, $3, $4, $5)`,
      [userId, eventType, clientIp(req), req.headers.get('user-agent'), JSON.stringify(metadata)],
    )
  } catch (e) {
    console.error('[customer-login] audit failed:', eventType, e)
  }
}

export async function POST(req: NextRequest) {
  if (!isCustomersDbConfigured()) {
    return NextResponse.json(
      { ok: false, error: 'Sign-in is temporarily unavailable. Please try again shortly.' },
      { status: 503 },
    )
  }

  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>
  const email = normalizeEmail(String(body.email ?? ''))
  const password = String(body.password ?? '')
  if (!email || !password) {
    return NextResponse.json({ ok: false, error: 'Email and password are required.' }, { status: 400 })
  }

  try {
    const rows = await customerQuery<UserRow>(
      `SELECT id, password_hash, email_verified, onboarding_step FROM users WHERE email = $1 LIMIT 1`,
      [email],
    )
    const user = rows[0]
    // Always run a bcrypt compare (dummy hash on miss) to equalize timing.
    const passwordOk = await verifyPassword(password, user?.password_hash ?? TIMING_DUMMY_HASH)

    const outcome = classifyLoginAttempt({
      userExists: !!user,
      passwordOk,
      emailVerified: !!user?.email_verified,
    })

    if (outcome === 'invalid_credentials') {
      return NextResponse.json(
        { ok: false, code: 'invalid_credentials', error: 'Invalid email or password.' },
        { status: 401 },
      )
    }
    if (outcome === 'email_unverified') {
      await audit(user!.id, 'LOGIN_BLOCKED_UNVERIFIED', req, {})
      return NextResponse.json(
        {
          ok: false,
          code: 'email_unverified',
          error: 'Please verify your email before signing in.',
        },
        { status: 403 },
      )
    }

    const session = await getCustomerSession()
    session.customerId = user!.id
    session.email = email
    session.emailVerified = true
    session.onboardingStep = user!.onboarding_step
    await session.save()

    void customerExecute(`UPDATE users SET last_login_at = now() WHERE id = $1`, [user!.id]).catch(() => {})
    await audit(user!.id, 'CUSTOMER_LOGIN', req, {})

    return NextResponse.json({ ok: true, next: nextRouteForOnboarding(user!.onboarding_step) })
  } catch (e) {
    console.error('[customer-login] failed:', e)
    return NextResponse.json({ ok: false, error: 'Something went wrong. Please try again.' }, { status: 500 })
  }
}
```

- [ ] **Step 2: Build**

Run: `npx next build`
Expected: `✓ Compiled successfully` and route `/api/auth/customer-login` listed.

- [ ] **Step 3: Commit**

```bash
git add src/app/api/auth/customer-login/route.ts
git commit -m "feat(ironforge): customer-login route (customer auth)"
```

---

## Task 7: Customer logout + me routes

**Files:**
- Create: `src/app/api/auth/customer-logout/route.ts`
- Create: `src/app/api/auth/customer-me/route.ts`

- [ ] **Step 1: Write the logout route**

```ts
// src/app/api/auth/customer-logout/route.ts
import { NextResponse } from 'next/server'
import { getCustomerSession } from '@/lib/auth/customer-session'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function POST() {
  const session = await getCustomerSession()
  session.destroy()
  return NextResponse.json({ ok: true })
}
```

- [ ] **Step 2: Write the me route**

```ts
// src/app/api/auth/customer-me/route.ts
import { NextResponse } from 'next/server'
import { getCustomerSession } from '@/lib/auth/customer-session'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET() {
  const session = await getCustomerSession()
  if (!session.customerId) {
    return NextResponse.json({ ok: false }, { status: 401 })
  }
  return NextResponse.json({
    ok: true,
    customer: {
      id: session.customerId,
      email: session.email,
      emailVerified: session.emailVerified,
      onboardingStep: session.onboardingStep,
    },
  })
}
```

- [ ] **Step 3: Build**

Run: `npx next build`
Expected: `✓ Compiled successfully`; both routes listed.

- [ ] **Step 4: Commit**

```bash
git add src/app/api/auth/customer-logout/route.ts src/app/api/auth/customer-me/route.ts
git commit -m "feat(ironforge): customer logout + me routes (customer auth)"
```

---

## Task 8: Forgot-password route (enumeration-safe)

**Files:**
- Create: `src/app/api/auth/forgot-password/route.ts`

Reuses `generateToken`/`hashToken` from `src/lib/auth/verification-token.ts` (raw token in the link, sha256 hash stored). TTL = 1 hour.

- [ ] **Step 1: Write the route**

```ts
// src/app/api/auth/forgot-password/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { normalizeEmail } from '@/lib/signup-validation'
import { generateToken } from '@/lib/auth/verification-token'
import { sendPasswordResetEmail } from '@/lib/email'
import { isCustomersDbConfigured, customerQuery, customerExecute } from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const RESET_TTL_MS = 60 * 60 * 1000 // 1 hour

interface UserRow {
  id: string
  first_name: string
  email: string
}

/** Always returns { ok: true } — never reveals whether an account exists. */
export async function POST(req: NextRequest) {
  const ok = () => NextResponse.json({ ok: true })

  if (!isCustomersDbConfigured()) return ok()

  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>
  const email = normalizeEmail(String(body.email ?? ''))
  if (!email) return ok()

  try {
    const rows = await customerQuery<UserRow>(
      `SELECT id, first_name, email FROM users WHERE email = $1 LIMIT 1`,
      [email],
    )
    const user = rows[0]
    if (user) {
      const { raw, hash } = generateToken()
      const expiresAt = new Date(Date.now() + RESET_TTL_MS).toISOString()
      await customerExecute(
        `INSERT INTO password_reset_tokens (user_id, token_hash, expires_at) VALUES ($1, $2, $3)`,
        [user.id, hash, expiresAt],
      )
      const resetUrl = `${req.nextUrl.origin}/reset-password?token=${encodeURIComponent(raw)}`
      try {
        await sendPasswordResetEmail({ to: user.email, resetUrl, firstName: user.first_name })
      } catch (e) {
        console.error('[forgot-password] email send threw:', e)
      }
      try {
        await customerExecute(
          `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'PASSWORD_RESET_REQUESTED', $2)`,
          [user.id, JSON.stringify({})],
        )
      } catch { /* best-effort */ }
    }
    return ok()
  } catch (e) {
    console.error('[forgot-password] failed:', e)
    return ok() // still enumeration-safe on internal error
  }
}
```

- [ ] **Step 2: Build**

Run: `npx next build`
Expected: `✓ Compiled successfully`; `/api/auth/forgot-password` listed.

- [ ] **Step 3: Commit**

```bash
git add src/app/api/auth/forgot-password/route.ts
git commit -m "feat(ironforge): enumeration-safe forgot-password route (customer auth)"
```

---

## Task 9: Reset-password route

**Files:**
- Create: `src/app/api/auth/reset-password/route.ts`

- [ ] **Step 1: Write the route**

```ts
// src/app/api/auth/reset-password/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { hashToken, isExpired } from '@/lib/auth/verification-token'
import { hashPassword } from '@/lib/auth/password'
import { checkPassword } from '@/lib/signup-validation'
import { isCustomersDbConfigured, customerQuery, customerTransaction, customerExecute } from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

interface TokenRow {
  id: string
  user_id: string
  expires_at: string
  consumed_at: string | null
}

export async function POST(req: NextRequest) {
  if (!isCustomersDbConfigured()) {
    return NextResponse.json(
      { ok: false, error: 'Password reset is temporarily unavailable. Please try again shortly.' },
      { status: 503 },
    )
  }

  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>
  const token = String(body.token ?? '')
  const password = String(body.password ?? '')
  const confirmPassword = String(body.confirmPassword ?? '')

  if (!token) {
    return NextResponse.json({ ok: false, error: 'This reset link is invalid.' }, { status: 400 })
  }
  if (!checkPassword(password).valid) {
    return NextResponse.json(
      { ok: false, error: 'Password does not meet the requirements.' },
      { status: 400 },
    )
  }
  if (password !== confirmPassword) {
    return NextResponse.json({ ok: false, error: 'Passwords do not match.' }, { status: 400 })
  }

  try {
    const rows = await customerQuery<TokenRow>(
      `SELECT id, user_id, expires_at, consumed_at FROM password_reset_tokens WHERE token_hash = $1 LIMIT 1`,
      [hashToken(token)],
    )
    const row = rows[0]
    if (!row || row.consumed_at || isExpired(row.expires_at, new Date())) {
      return NextResponse.json(
        { ok: false, error: 'This reset link is invalid or has expired.' },
        { status: 400 },
      )
    }

    const newHash = await hashPassword(password)
    await customerTransaction(async (run) => {
      await run(`UPDATE users SET password_hash = $1, updated_at = now() WHERE id = $2`, [newHash, row.user_id])
      await run(`UPDATE password_reset_tokens SET consumed_at = now() WHERE id = $1`, [row.id])
    })

    try {
      await customerExecute(
        `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'PASSWORD_RESET', $2)`,
        [row.user_id, JSON.stringify({})],
      )
    } catch { /* best-effort */ }

    return NextResponse.json({ ok: true })
  } catch (e) {
    console.error('[reset-password] failed:', e)
    return NextResponse.json({ ok: false, error: 'Something went wrong. Please try again.' }, { status: 500 })
  }
}
```

- [ ] **Step 2: Build**

Run: `npx next build`
Expected: `✓ Compiled successfully`; `/api/auth/reset-password` listed.

- [ ] **Step 3: Commit**

```bash
git add src/app/api/auth/reset-password/route.ts
git commit -m "feat(ironforge): reset-password route (customer auth)"
```

---

## Task 10: Relocate operator login → `/ops/login`

**Files:**
- Read current operator login: `src/app/login/page.tsx`
- Create: `src/app/ops/login/page.tsx`

The current `src/app/login/page.tsx` is the OPERATOR login (username field → `/api/auth/login`). Move it verbatim to `/ops/login` so it survives `/login` being repurposed in Task 11.

- [ ] **Step 1: Copy the current operator login page to the new path**

Run:
```bash
mkdir -p src/app/ops/login
cp src/app/login/page.tsx src/app/ops/login/page.tsx
```

- [ ] **Step 2: Build to confirm the relocated page compiles**

Run: `npx next build`
Expected: `✓ Compiled successfully`; both `/login` and `/ops/login` listed (still identical for now; `/login` is replaced in Task 11).

- [ ] **Step 3: Commit**

```bash
git add src/app/ops/login/page.tsx
git commit -m "feat(ironforge): relocate operator login to /ops/login (customer auth)"
```

---

## Task 11: Repurpose `/login` as the customer login

**Files:**
- Overwrite: `src/app/login/page.tsx`

Replaces the operator login with the customer email/password login. On `403 email_unverified`, swaps to a verify-email panel with a Resend button. On success, redirects to the `next` route from the response.

- [ ] **Step 1: Overwrite `src/app/login/page.tsx`**

```tsx
'use client'

import { useState } from 'react'
import Link from 'next/link'
import { Wordmark } from '@/components/Brand'

export default function CustomerLoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [unverified, setUnverified] = useState(false)
  const [resendMsg, setResendMsg] = useState<string | null>(null)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    setError(null)
    setUnverified(false)
    try {
      const res = await fetch('/api/auth/customer-login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      const data = await res.json().catch(() => ({}))
      if (res.ok && data.ok) {
        window.location.href = data.next || '/onboarding/complete'
        return
      }
      if (data.code === 'email_unverified') {
        setUnverified(true)
      } else {
        setError(data.error || 'Invalid email or password.')
      }
    } catch {
      setError('Network error. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  async function resend() {
    setResendMsg(null)
    try {
      await fetch('/api/auth/resend-verification', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      })
      setResendMsg('If that email needs verification, we just sent a new link.')
    } catch {
      setResendMsg('Could not send right now. Please try again shortly.')
    }
  }

  return (
    <div className="min-h-screen bg-forge-bg bg-ember-glow px-4 py-16">
      <div className="mx-auto max-w-md">
        <div className="mb-6 flex justify-center"><Wordmark /></div>
        <div className="rounded-2xl border border-white/10 bg-forge-card/90 p-8 shadow-2xl">
          <h1 className="text-2xl font-bold text-white">Sign in</h1>
          <p className="mt-1 text-sm text-gray-400">Welcome back to IronForge.</p>

          {unverified ? (
            <div className="mt-6 space-y-4">
              <p className="rounded-md border border-amber-700/40 bg-amber-950/30 px-3 py-2 text-sm text-amber-200">
                Please verify your email before signing in.
              </p>
              <button
                onClick={resend}
                className="flex w-full items-center justify-center rounded-md bg-amber-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-amber-500"
              >
                Resend verification email
              </button>
              {resendMsg && <p className="text-xs text-gray-400">{resendMsg}</p>}
              <button onClick={() => setUnverified(false)} className="w-full text-center text-xs text-gray-500 hover:text-gray-300">
                Back to sign in
              </button>
            </div>
          ) : (
            <form onSubmit={onSubmit} noValidate className="mt-6 space-y-4">
              <div>
                <label htmlFor="email" className="block text-xs text-gray-400">Email</label>
                <input
                  id="email" name="email" type="email" autoComplete="email" autoFocus required
                  value={email} onChange={(e) => setEmail(e.target.value)}
                  className="mt-1 w-full rounded-md border border-white/15 bg-black/40 px-3 py-2.5 text-sm text-white outline-none focus:border-amber-500"
                />
              </div>
              <div>
                <div className="flex items-center justify-between">
                  <label htmlFor="password" className="block text-xs text-gray-400">Password</label>
                  <Link href="/forgot-password" className="text-xs text-amber-500 hover:text-amber-400">Forgot password?</Link>
                </div>
                <input
                  id="password" name="password" type="password" autoComplete="current-password" required
                  value={password} onChange={(e) => setPassword(e.target.value)}
                  className="mt-1 w-full rounded-md border border-white/15 bg-black/40 px-3 py-2.5 text-sm text-white outline-none focus:border-amber-500"
                />
              </div>
              {error && (
                <p className="rounded-md border border-red-700/40 bg-red-950/30 px-3 py-2 text-xs text-red-300">{error}</p>
              )}
              <button
                type="submit" disabled={busy}
                className="flex w-full items-center justify-center rounded-md bg-amber-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-amber-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {busy ? 'Signing in…' : 'Sign in'}
              </button>
            </form>
          )}

          <p className="mt-6 text-center text-xs text-gray-500">
            Don&apos;t have an account?{' '}
            <Link href="/signup" className="font-semibold text-amber-500 hover:text-amber-400">Create one</Link>
          </p>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Build**

Run: `npx next build`
Expected: `✓ Compiled successfully`.

- [ ] **Step 3: Commit**

```bash
git add src/app/login/page.tsx
git commit -m "feat(ironforge): customer login at /login + unverified resend (customer auth)"
```

---

## Task 12: Forgot-password + reset-password pages

**Files:**
- Create: `src/app/forgot-password/page.tsx`
- Create: `src/app/reset-password/page.tsx`

- [ ] **Step 1: Write the forgot-password page**

```tsx
// src/app/forgot-password/page.tsx
'use client'

import { useState } from 'react'
import Link from 'next/link'
import { Wordmark } from '@/components/Brand'

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState(false)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    try {
      await fetch('/api/auth/forgot-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      })
    } catch { /* enumeration-safe: show the same confirmation regardless */ }
    setSent(true)
    setBusy(false)
  }

  return (
    <div className="min-h-screen bg-forge-bg bg-ember-glow px-4 py-16">
      <div className="mx-auto max-w-md">
        <div className="mb-6 flex justify-center"><Wordmark /></div>
        <div className="rounded-2xl border border-white/10 bg-forge-card/90 p-8 shadow-2xl">
          {sent ? (
            <>
              <h1 className="text-xl font-bold text-white">Check your email</h1>
              <p className="mt-2 text-sm leading-relaxed text-gray-400">
                If an account exists for <span className="font-medium text-amber-500">{email}</span>, we&apos;ve sent a
                link to reset your password. The link expires in 1 hour.
              </p>
              <p className="mt-6 text-center text-xs text-gray-500">
                <Link href="/login" className="font-semibold text-amber-500 hover:text-amber-400">Back to sign in</Link>
              </p>
            </>
          ) : (
            <>
              <h1 className="text-2xl font-bold text-white">Reset your password</h1>
              <p className="mt-1 text-sm text-gray-400">Enter your email and we&apos;ll send you a reset link.</p>
              <form onSubmit={onSubmit} noValidate className="mt-6 space-y-4">
                <div>
                  <label htmlFor="email" className="block text-xs text-gray-400">Email</label>
                  <input
                    id="email" type="email" autoComplete="email" autoFocus required
                    value={email} onChange={(e) => setEmail(e.target.value)}
                    className="mt-1 w-full rounded-md border border-white/15 bg-black/40 px-3 py-2.5 text-sm text-white outline-none focus:border-amber-500"
                  />
                </div>
                <button
                  type="submit" disabled={busy}
                  className="flex w-full items-center justify-center rounded-md bg-amber-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-amber-500 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {busy ? 'Sending…' : 'Send reset link'}
                </button>
              </form>
              <p className="mt-6 text-center text-xs text-gray-500">
                <Link href="/login" className="font-semibold text-amber-500 hover:text-amber-400">Back to sign in</Link>
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Write the reset-password page**

```tsx
// src/app/reset-password/page.tsx
'use client'

import { Suspense, useMemo, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { Wordmark } from '@/components/Brand'
import { checkPassword } from '@/lib/signup-validation'

const RULE_LABELS: { key: keyof ReturnType<typeof checkPassword>['rules']; label: string }[] = [
  { key: 'minLength', label: 'At least 12 characters' },
  { key: 'upper', label: 'An uppercase letter' },
  { key: 'lower', label: 'A lowercase letter' },
  { key: 'number', label: 'A number' },
  { key: 'special', label: 'A special character' },
]

function ResetInner() {
  const params = useSearchParams()
  const token = params.get('token') || ''
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  const check = useMemo(() => checkPassword(password), [password])
  const canSubmit = !!token && check.valid && password === confirm && !busy

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!canSubmit) return
    setBusy(true)
    setError(null)
    try {
      const res = await fetch('/api/auth/reset-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, password, confirmPassword: confirm }),
      })
      const data = await res.json().catch(() => ({}))
      if (res.ok && data.ok) {
        setDone(true)
      } else {
        setError(data.error || 'Could not reset your password.')
        setBusy(false)
      }
    } catch {
      setError('Network error. Please try again.')
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen bg-forge-bg bg-ember-glow px-4 py-16">
      <div className="mx-auto max-w-md">
        <div className="mb-6 flex justify-center"><Wordmark /></div>
        <div className="rounded-2xl border border-white/10 bg-forge-card/90 p-8 shadow-2xl">
          {done ? (
            <>
              <h1 className="text-xl font-bold text-white">Password updated</h1>
              <p className="mt-2 text-sm text-gray-400">Your password has been reset. You can now sign in.</p>
              <p className="mt-6 text-center text-xs text-gray-500">
                <Link href="/login" className="font-semibold text-amber-500 hover:text-amber-400">Go to sign in</Link>
              </p>
            </>
          ) : !token ? (
            <>
              <h1 className="text-xl font-bold text-white">Invalid reset link</h1>
              <p className="mt-2 text-sm text-gray-400">This link is missing its token. Request a new one.</p>
              <p className="mt-6 text-center text-xs text-gray-500">
                <Link href="/forgot-password" className="font-semibold text-amber-500 hover:text-amber-400">Request a reset link</Link>
              </p>
            </>
          ) : (
            <>
              <h1 className="text-2xl font-bold text-white">Choose a new password</h1>
              <form onSubmit={onSubmit} noValidate className="mt-6 space-y-4">
                <div>
                  <label htmlFor="password" className="block text-xs text-gray-400">New password</label>
                  <input
                    id="password" type="password" autoComplete="new-password" autoFocus required
                    value={password} onChange={(e) => setPassword(e.target.value)}
                    className="mt-1 w-full rounded-md border border-white/15 bg-black/40 px-3 py-2.5 text-sm text-white outline-none focus:border-amber-500"
                  />
                </div>
                <ul className="space-y-1">
                  {RULE_LABELS.map((r) => (
                    <li key={r.key} className={`text-xs ${check.rules[r.key] ? 'text-gray-300' : 'text-gray-500'}`}>
                      {check.rules[r.key] ? '✓' : '○'} {r.label}
                    </li>
                  ))}
                </ul>
                <div>
                  <label htmlFor="confirm" className="block text-xs text-gray-400">Confirm password</label>
                  <input
                    id="confirm" type="password" autoComplete="new-password" required
                    value={confirm} onChange={(e) => setConfirm(e.target.value)}
                    className="mt-1 w-full rounded-md border border-white/15 bg-black/40 px-3 py-2.5 text-sm text-white outline-none focus:border-amber-500"
                  />
                </div>
                {error && (
                  <p className="rounded-md border border-red-700/40 bg-red-950/30 px-3 py-2 text-xs text-red-300">{error}</p>
                )}
                <button
                  type="submit" disabled={!canSubmit}
                  className="flex w-full items-center justify-center rounded-md bg-amber-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-amber-500 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {busy ? 'Updating…' : 'Update password'}
                </button>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default function ResetPasswordPage() {
  // useSearchParams requires a Suspense boundary in the App Router.
  return (
    <Suspense fallback={<div className="min-h-screen bg-forge-bg" />}>
      <ResetInner />
    </Suspense>
  )
}
```

- [ ] **Step 3: Build**

Run: `npx next build`
Expected: `✓ Compiled successfully`; `/forgot-password` and `/reset-password` listed.

- [ ] **Step 4: Commit**

```bash
git add src/app/forgot-password/page.tsx src/app/reset-password/page.tsx
git commit -m "feat(ironforge): forgot-password + reset-password pages (customer auth)"
```

---

## Task 13: Onboarding completion placeholder page

**Files:**
- Create: `src/app/onboarding/complete/page.tsx`

Server-guarded like `/onboarding/legal` (must hold a valid onboarding handoff cookie OR — after Task 14 — be reachable via customer session through middleware). For the page-level guard we accept the onboarding cookie; a logged-in customer reaches it via middleware (Task 14) and the cookie check simply falls through to the same content.

- [ ] **Step 1: Write the page**

```tsx
// src/app/onboarding/complete/page.tsx
import Link from 'next/link'
import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { ONBOARDING_COOKIE, verifyOnboardingToken } from '@/lib/auth/onboarding'
import { getCustomerSession } from '@/lib/auth/customer-session'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export default async function OnboardingCompletePage() {
  // Reachable by a valid onboarding handoff cookie OR a logged-in customer session.
  const claims = await verifyOnboardingToken(cookies().get(ONBOARDING_COOKIE)?.value)
  const session = await getCustomerSession()
  if (!claims && !session.customerId) redirect('/login?next=/onboarding/complete')

  return (
    <div className="min-h-screen bg-forge-bg bg-ember-glow px-4 py-16">
      <div className="mx-auto max-w-md rounded-2xl border border-white/10 bg-forge-card/90 p-8 text-center shadow-2xl">
        <h1 className="text-xl font-bold text-white">You&apos;re all set — for now</h1>
        <p className="mt-2 text-sm leading-relaxed text-gray-400">
          Your account is created and your disclosures are on file. The next steps —
          billing, brokerage connection, and your risk profile — are coming soon.
          We&apos;ll email you the moment they&apos;re ready.
        </p>
        <p className="mt-6 text-xs text-gray-500">
          <Link href="/" className="font-semibold text-amber-500 hover:text-amber-400">Return home</Link>
        </p>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Build**

Run: `npx next build`
Expected: `✓ Compiled successfully`; `/onboarding/complete` listed.

- [ ] **Step 3: Commit**

```bash
git add src/app/onboarding/complete/page.tsx
git commit -m "feat(ironforge): onboarding completion placeholder (customer auth)"
```

---

## Task 14: Wire middleware, access allowlist, and Shell

**Files:**
- Modify: `src/lib/auth/access.ts`
- Modify: `src/middleware.ts`
- Modify: `src/components/Shell.tsx`

- [ ] **Step 1: Add public paths in `src/lib/auth/access.ts`**

Replace the `PUBLIC_EXACT` set with:

```ts
const PUBLIC_EXACT = new Set<string>([
  '/login',
  '/signup',
  '/pricing',
  '/ops/login',
  '/forgot-password',
  '/reset-password',
  '/api/auth/login',
  '/api/auth/signup',
  '/api/auth/verify',
  '/api/auth/resend-verification',
  '/api/auth/logout',
  '/api/auth/seed',
  '/api/auth/customer-login',
  '/api/auth/customer-logout',
  '/api/auth/customer-me',
  '/api/auth/forgot-password',
  '/api/auth/reset-password',
  '/api/health',
])
```

- [ ] **Step 2: Update `src/middleware.ts`**

Add the customer-session import alongside the existing imports:

```ts
import { CUSTOMER_SESSION_COOKIE, customerSessionOptions } from '@/lib/auth/customer-session'
import type { CustomerSessionData } from '@/lib/auth/customer-session'
```

Inside the onboarding block, change the credential check so a valid customer session also grants access. Replace this existing block:

```ts
  if (isOnboarding) {
    if (hasSession || hasServiceToken) return res
    const claims = await verifyOnboardingToken(req.cookies.get(ONBOARDING_COOKIE)?.value)
    if (claims) return res
    if (isApi) return NextResponse.json({ error: 'unauthorized' }, { status: 401 })
    const url = req.nextUrl.clone()
    url.pathname = '/login'
    url.searchParams.set('next', pathname)
    return NextResponse.redirect(url)
  }
```

with:

```ts
  if (isOnboarding) {
    if (hasSession || hasServiceToken) return res
    const claims = await verifyOnboardingToken(req.cookies.get(ONBOARDING_COOKIE)?.value)
    if (claims) return res
    // A logged-in customer can resume onboarding via their own session cookie.
    let hasCustomerSession = false
    try {
      const cs = await getIronSession<CustomerSessionData>(req, res, customerSessionOptions)
      hasCustomerSession = Boolean(cs.customerId)
    } catch {
      hasCustomerSession = false
    }
    if (hasCustomerSession) return res
    if (isApi) return NextResponse.json({ error: 'unauthorized' }, { status: 401 })
    const url = req.nextUrl.clone()
    url.pathname = '/login'
    url.searchParams.set('next', pathname)
    return NextResponse.redirect(url)
  }
```

Then change the OPERATOR-wall redirect target from `/login` to `/ops/login`. Replace the final redirect block:

```ts
  const url = req.nextUrl.clone()
  url.pathname = '/login'
  url.searchParams.set('next', pathname)
  return NextResponse.redirect(url)
```

with:

```ts
  const url = req.nextUrl.clone()
  url.pathname = '/ops/login'
  url.searchParams.set('next', pathname)
  return NextResponse.redirect(url)
```

Note: `CUSTOMER_SESSION_COOKIE` is imported for clarity/consistency; if the linter flags it as unused, drop it from the import and keep only `customerSessionOptions` + the type.

- [ ] **Step 3: Make the new auth/onboarding screens full-bleed in `src/components/Shell.tsx`**

Replace the `isStandalone` line:

```ts
  const isStandalone =
    pathname === '/signup' || pathname === '/pricing' || pathname.startsWith('/onboarding')
```

with:

```ts
  const isStandalone =
    pathname === '/signup' ||
    pathname === '/pricing' ||
    pathname === '/login' ||
    pathname === '/ops/login' ||
    pathname === '/forgot-password' ||
    pathname === '/reset-password' ||
    pathname.startsWith('/onboarding')
```

- [ ] **Step 4: Build**

Run: `npx next build`
Expected: `✓ Compiled successfully`. Confirm `/login`, `/ops/login`, `/forgot-password`, `/reset-password`, `/onboarding/complete`, and the customer API routes all appear.

- [ ] **Step 5: Commit**

```bash
git add src/lib/auth/access.ts src/middleware.ts src/components/Shell.tsx
git commit -m "feat(ironforge): wire customer auth into middleware/allowlist/Shell (customer auth)"
```

---

## Task 15: Full verification

- [ ] **Step 1: Run all new/touched unit tests**

Run:
```bash
npx vitest run src/lib/__tests__/onboarding-route.test.ts src/lib/__tests__/customer-auth.test.ts src/lib/__tests__/password-reset-email.test.ts
```
Expected: all PASS (3 + 4 + 2 = 9 tests).

- [ ] **Step 2: Final production build**

Run: `npx next build`
Expected: `✓ Compiled successfully` with the full route table.

- [ ] **Step 3: Manual smoke checklist (note results in the PR/summary)**

- `/login` renders the customer email/password form (not the operator username form).
- `/ops/login` renders the operator username form.
- `/forgot-password` and `/reset-password` render.
- Operator-wall redirect (when `IRONFORGE_PUBLIC_MODE` is off) points to `/ops/login`.

- [ ] **Step 4: Merge to main**

```bash
git checkout main && git merge --no-ff <branch> -m "Merge: IronForge customer authentication (login/session/reset/onboarding-resume)"
git push origin main
```

---

## Notes for the implementer

- **Run all commands from `ironforge/webapp/`.**
- **Reuse, don't redeclare:** `esc`, `RESEND_ENDPOINT`, `isEmailConfigured`, `SendResult` (email.ts); `generateToken`, `hashToken`, `isExpired` (verification-token.ts); `normalizeEmail`, `checkPassword` (signup-validation.ts); `customerQuery`, `customerExecute`, `customerTransaction`, `isCustomersDbConfigured` (customers-db.ts).
- **Security invariant:** the operator gate must keep reading ONLY `ironforge_session`. Do not add `customerId` checks to the operator path.
- **Env unchanged:** customer auth reuses `IRONFORGE_SESSION_SECRET`, `CUSTOMERS_DATABASE_URL`, `RESEND_API_KEY`, `EMAIL_FROM`. No new env vars required.
- **Out of scope (fast-follow):** login rate-limiting / brute-force throttling.
```
