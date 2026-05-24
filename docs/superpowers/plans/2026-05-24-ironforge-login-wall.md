# IronForge Login Wall Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gate the entire IronForge dashboard behind invite-only named-operator login (iron-session + bcrypt), with shared data and no per-user isolation.

**Architecture:** A DB-free Edge middleware decrypts an iron-session cookie and default-denies every page/route except a small public whitelist (`/login`, the auth endpoints, `/api/health`) and requests bearing an internal service token. Auth logic lives in Node-runtime route handlers under `/api/auth/*`. A new additive `ironforge_users` table holds operators; the in-process scanner is untouched because it never makes HTTP calls.

**Tech Stack:** Next.js 14.2 (App Router), TypeScript, PostgreSQL (`pg` via `src/lib/db.ts`), `iron-session` v8, `bcryptjs`, vitest.

**Spec:** `docs/superpowers/specs/2026-05-24-ironforge-login-wall-design.md`

**Working directory for all commands:** `ironforge/webapp/` (the Next.js project root / Render `rootDir`).

**Branch:** `claude/ironforge-login-wall` (already exists; the spec is committed there).

---

## File Structure

**New files:**
- `src/lib/auth/session.ts` — Edge-safe: `SessionData`, `sessionOptions`, `safeEqual`, `hasValidServiceToken`, `serviceHeaders`. No `next/headers`, no `pg`, no `bcrypt`.
- `src/lib/auth/server.ts` — Node-only: `getSession()` (uses `next/headers`).
- `src/lib/auth/password.ts` — `hashPassword`, `verifyPassword` (bcryptjs).
- `src/lib/auth/access.ts` — pure `isPublicPath`, `decideAccess` (middleware decision logic).
- `src/middleware.ts` — the gate (Edge runtime).
- `src/app/api/auth/login/route.ts`, `logout/route.ts`, `me/route.ts`, `change-password/route.ts`, `seed/route.ts`.
- `src/app/login/page.tsx`, `src/app/change-password/page.tsx`.
- `src/components/AuthControls.tsx` — nav signed-in/logout control.
- Tests: `src/lib/auth/__tests__/{password,access,session}.test.ts`, `src/app/api/auth/__tests__/{login,change-password,seed}.test.ts`, `src/middleware.test.ts`.

**Modified files:**
- `src/lib/db.ts` — add `ironforge_users` to `INIT_DDL`.
- `src/components/Nav.tsx` — render `<AuthControls />`.
- `src/lib/forgeBriefings/context.ts` — add service-token header to self-calls.
- `src/app/api/builder/health/route.ts` — add service-token header to self-call.
- `package.json` — add `iron-session`, `bcryptjs`, `@types/bcryptjs`.
- `../render.yaml` (i.e. `ironforge/render.yaml`) — add three env vars.

---

## Task 1: Dependencies + Render env vars

**Files:**
- Modify: `package.json` (via npm)
- Modify: `ironforge/render.yaml`

- [ ] **Step 1: Install dependencies**

Run (from `ironforge/webapp/`):
```bash
npm install iron-session bcryptjs && npm install -D @types/bcryptjs
```
Expected: `package.json` gains `iron-session` + `bcryptjs` under dependencies and `@types/bcryptjs` under devDependencies; `package-lock.json` updated.

- [ ] **Step 2: Verify install**

Run: `npm ls iron-session bcryptjs`
Expected: both resolve to a version (iron-session 8.x, bcryptjs 2.x/3.x) with no `UNMET DEPENDENCY`.

- [ ] **Step 3: Add env vars to render.yaml**

In `ironforge/render.yaml`, inside the `ironforge-dashboard` service `envVars:` list (after the existing `TRADIER_SANDBOX_KEY_LOGAN` block), add:
```yaml
      - key: IRONFORGE_SESSION_SECRET
        sync: false
      - key: IRONFORGE_SERVICE_TOKEN
        sync: false
      - key: IRONFORGE_SEED_TOKEN
        sync: false
```

- [ ] **Step 4: Commit**

```bash
git add package.json package-lock.json ../render.yaml
git commit -m "feat(auth): add iron-session + bcryptjs deps and auth env vars"
```

---

## Task 2: `ironforge_users` table

**Files:**
- Modify: `src/lib/db.ts` (the `INIT_DDL` template, near the other `ironforge_*` tables ~line 95-101)

- [ ] **Step 1: Add the table to INIT_DDL**

In `src/lib/db.ts`, immediately after the `CREATE TABLE IF NOT EXISTS ironforge_person_aliases (...)` block (the `+ \`...\`` segment ending around line 100) and before the `ironforge_pdt_config` block, insert a new concatenated segment:
```typescript
` + `
CREATE TABLE IF NOT EXISTS ironforge_users (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  username TEXT NOT NULL UNIQUE,
  email TEXT UNIQUE,
  name TEXT NOT NULL,
  person TEXT,
  password_hash TEXT NOT NULL,
  is_active BOOLEAN DEFAULT TRUE,
  must_change_password BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  last_login_at TIMESTAMPTZ
);
` + `
```
(Match the existing `\` + \`` concatenation style used throughout `INIT_DDL`.)

- [ ] **Step 2: Verify it typechecks / builds the DDL string**

Run: `npx tsc --noEmit`
Expected: no new TypeScript errors (the change is inside a template string).

- [ ] **Step 3: Commit**

```bash
git add src/lib/db.ts
git commit -m "feat(auth): add ironforge_users table to INIT_DDL"
```

---

## Task 3: Password helpers (TDD)

**Files:**
- Create: `src/lib/auth/password.ts`
- Test: `src/lib/auth/__tests__/password.test.ts`

- [ ] **Step 1: Write the failing test**

Create `src/lib/auth/__tests__/password.test.ts`:
```typescript
import { describe, it, expect } from 'vitest'
import { hashPassword, verifyPassword } from '../password'

describe('password helpers', () => {
  it('hashes and verifies a correct password', async () => {
    const hash = await hashPassword('correct-horse-battery')
    expect(hash).not.toBe('correct-horse-battery')
    expect(await verifyPassword('correct-horse-battery', hash)).toBe(true)
  })

  it('rejects an incorrect password', async () => {
    const hash = await hashPassword('correct-horse-battery')
    expect(await verifyPassword('wrong', hash)).toBe(false)
  })

  it('returns false for an empty hash', async () => {
    expect(await verifyPassword('anything', '')).toBe(false)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/lib/auth/__tests__/password.test.ts`
Expected: FAIL — cannot find module `../password`.

- [ ] **Step 3: Write minimal implementation**

Create `src/lib/auth/password.ts`:
```typescript
import bcrypt from 'bcryptjs'

const ROUNDS = 10

export async function hashPassword(plain: string): Promise<string> {
  return bcrypt.hash(plain, ROUNDS)
}

export async function verifyPassword(plain: string, hash: string): Promise<boolean> {
  if (!hash) return false
  return bcrypt.compare(plain, hash)
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/lib/auth/__tests__/password.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/lib/auth/password.ts src/lib/auth/__tests__/password.test.ts
git commit -m "feat(auth): bcrypt password hash/verify helpers"
```

---

## Task 4: Access-control decision logic (TDD)

**Files:**
- Create: `src/lib/auth/access.ts`
- Test: `src/lib/auth/__tests__/access.test.ts`

- [ ] **Step 1: Write the failing test**

Create `src/lib/auth/__tests__/access.test.ts`:
```typescript
import { describe, it, expect } from 'vitest'
import { isPublicPath, decideAccess } from '../access'

describe('isPublicPath', () => {
  it('treats login, auth endpoints, and health as public', () => {
    expect(isPublicPath('/login')).toBe(true)
    expect(isPublicPath('/api/auth/login')).toBe(true)
    expect(isPublicPath('/api/auth/logout')).toBe(true)
    expect(isPublicPath('/api/auth/seed')).toBe(true)
    expect(isPublicPath('/api/health')).toBe(true)
  })
  it('treats app pages and bot routes as non-public', () => {
    expect(isPublicPath('/')).toBe(false)
    expect(isPublicPath('/spark')).toBe(false)
    expect(isPublicPath('/api/spark/status')).toBe(false)
    expect(isPublicPath('/api/auth/me')).toBe(false)
  })
})

describe('decideAccess', () => {
  const base = { pathname: '/spark', isApi: false, hasSession: false, hasServiceToken: false }
  it('allows when a valid service token is present', () => {
    expect(decideAccess({ ...base, isApi: true, pathname: '/api/spark/status', hasServiceToken: true })).toBe('allow')
  })
  it('allows public paths without a session', () => {
    expect(decideAccess({ ...base, pathname: '/login' })).toBe('allow')
  })
  it('allows any path with a session', () => {
    expect(decideAccess({ ...base, hasSession: true })).toBe('allow')
  })
  it('returns unauthorized for gated API without session', () => {
    expect(decideAccess({ ...base, isApi: true, pathname: '/api/spark/status' })).toBe('unauthorized')
  })
  it('returns redirect-login for gated page without session', () => {
    expect(decideAccess({ ...base })).toBe('redirect-login')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/lib/auth/__tests__/access.test.ts`
Expected: FAIL — cannot find module `../access`.

- [ ] **Step 3: Write minimal implementation**

Create `src/lib/auth/access.ts`:
```typescript
/** Paths reachable without a session. */
const PUBLIC_EXACT = new Set<string>([
  '/login',
  '/api/auth/login',
  '/api/auth/logout',
  '/api/auth/seed',
  '/api/health',
])

export function isPublicPath(pathname: string): boolean {
  return PUBLIC_EXACT.has(pathname)
}

export type AccessDecision = 'allow' | 'redirect-login' | 'unauthorized'

export function decideAccess(opts: {
  pathname: string
  isApi: boolean
  hasSession: boolean
  hasServiceToken: boolean
}): AccessDecision {
  if (opts.hasServiceToken) return 'allow'
  if (isPublicPath(opts.pathname)) return 'allow'
  if (opts.hasSession) return 'allow'
  return opts.isApi ? 'unauthorized' : 'redirect-login'
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/lib/auth/__tests__/access.test.ts`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add src/lib/auth/access.ts src/lib/auth/__tests__/access.test.ts
git commit -m "feat(auth): middleware access-decision logic"
```

---

## Task 5: Session config + service-token helpers (TDD)

**Files:**
- Create: `src/lib/auth/session.ts`
- Test: `src/lib/auth/__tests__/session.test.ts`

- [ ] **Step 1: Write the failing test**

Create `src/lib/auth/__tests__/session.test.ts`:
```typescript
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { safeEqual, hasValidServiceToken, serviceHeaders } from '../session'

describe('safeEqual', () => {
  it('is true for equal strings', () => expect(safeEqual('abc', 'abc')).toBe(true))
  it('is false for different strings', () => expect(safeEqual('abc', 'abd')).toBe(false))
  it('is false for different lengths', () => expect(safeEqual('abc', 'abcd')).toBe(false))
})

describe('hasValidServiceToken', () => {
  const orig = process.env.IRONFORGE_SERVICE_TOKEN
  beforeEach(() => { process.env.IRONFORGE_SERVICE_TOKEN = 'secret-token' })
  afterEach(() => { process.env.IRONFORGE_SERVICE_TOKEN = orig })

  it('is true for a matching header', () => expect(hasValidServiceToken('secret-token')).toBe(true))
  it('is false for a wrong header', () => expect(hasValidServiceToken('nope')).toBe(false))
  it('is false for a null header', () => expect(hasValidServiceToken(null)).toBe(false))
  it('is false when no token is configured', () => {
    delete process.env.IRONFORGE_SERVICE_TOKEN
    expect(hasValidServiceToken('anything')).toBe(false)
  })
})

describe('serviceHeaders', () => {
  it('returns the service header keyed value', () => {
    process.env.IRONFORGE_SERVICE_TOKEN = 'abc'
    expect(serviceHeaders()).toEqual({ 'x-ironforge-service': 'abc' })
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/lib/auth/__tests__/session.test.ts`
Expected: FAIL — cannot find module `../session`.

- [ ] **Step 3: Write minimal implementation**

Create `src/lib/auth/session.ts`:
```typescript
import type { SessionOptions } from 'iron-session'

export interface SessionData {
  userId?: number
  username?: string
  name?: string
  person?: string | null
}

export const SESSION_COOKIE = 'ironforge_session'

export const sessionOptions: SessionOptions = {
  password: process.env.IRONFORGE_SESSION_SECRET || '',
  cookieName: SESSION_COOKIE,
  cookieOptions: {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    maxAge: 60 * 60 * 24 * 30, // 30 days
    path: '/',
  },
}

/** Constant-time string compare that works on the Edge runtime (no Node crypto). */
export function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false
  let diff = 0
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i)
  return diff === 0
}

/** True when the request header carries the configured internal service token. */
export function hasValidServiceToken(headerValue: string | null | undefined): boolean {
  const expected = process.env.IRONFORGE_SERVICE_TOKEN
  if (!expected || !headerValue) return false
  return safeEqual(headerValue, expected)
}

/** Headers for internal server-to-server calls to our own gated routes. */
export function serviceHeaders(): Record<string, string> {
  return { 'x-ironforge-service': process.env.IRONFORGE_SERVICE_TOKEN || '' }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/lib/auth/__tests__/session.test.ts`
Expected: PASS (8 tests).

- [ ] **Step 5: Create the Node-only session accessor**

Create `src/lib/auth/server.ts` (no test — thin wrapper over `next/headers` + iron-session; exercised via route tests which mock it):
```typescript
import { getIronSession, type IronSession } from 'iron-session'
import { cookies } from 'next/headers'
import { sessionOptions, type SessionData } from './session'

/** Route-handler / server-component session accessor (Node runtime only). */
export async function getSession(): Promise<IronSession<SessionData>> {
  return getIronSession<SessionData>(cookies(), sessionOptions)
}
```

- [ ] **Step 6: Commit**

```bash
git add src/lib/auth/session.ts src/lib/auth/server.ts src/lib/auth/__tests__/session.test.ts
git commit -m "feat(auth): iron-session config + service-token helpers"
```

---

## Task 6: The gate — `middleware.ts` (TDD)

**Files:**
- Create: `src/middleware.ts`
- Test: `src/middleware.test.ts`

- [ ] **Step 1: Write the failing test**

Create `src/middleware.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { NextRequest } from 'next/server'

// Mock iron-session so we control whether a session exists.
// NOTE: the factory creates the vi.fn() INLINE (no outer-variable reference) to
// avoid vitest's hoisting TDZ trap; control it via vi.mocked(getIronSession).
vi.mock('iron-session', () => ({ getIronSession: vi.fn() }))

import { getIronSession } from 'iron-session'
import { middleware } from '@/middleware'

beforeEach(() => {
  process.env.IRONFORGE_SESSION_SECRET = 'x'.repeat(32)
  process.env.IRONFORGE_SERVICE_TOKEN = 'svc-token'
  vi.mocked(getIronSession).mockReset()
})

function req(path: string, headers: Record<string, string> = {}) {
  return new NextRequest(`https://app.test${path}`, { headers })
}

describe('middleware gate', () => {
  it('401s a gated API route with no session', async () => {
    vi.mocked(getIronSession).mockResolvedValue({} as never)
    const res = await middleware(req('/api/spark/status'))
    expect(res.status).toBe(401)
  })

  it('redirects a gated page with no session to /login', async () => {
    vi.mocked(getIronSession).mockResolvedValue({} as never)
    const res = await middleware(req('/spark'))
    expect(res.status).toBe(307)
    expect(res.headers.get('location')).toContain('/login')
  })

  it('allows a gated route when a session exists', async () => {
    vi.mocked(getIronSession).mockResolvedValue({ userId: 1 } as never)
    const res = await middleware(req('/api/spark/status'))
    expect(res.status).toBe(200)
    expect(res.headers.get('location')).toBeNull()
  })

  it('allows the public /login path with no session', async () => {
    vi.mocked(getIronSession).mockResolvedValue({} as never)
    const res = await middleware(req('/login'))
    expect(res.status).toBe(200)
  })

  it('allows a request bearing a valid service token', async () => {
    vi.mocked(getIronSession).mockResolvedValue({} as never)
    const res = await middleware(req('/api/spark/status', { 'x-ironforge-service': 'svc-token' }))
    expect(res.status).toBe(200)
  })

  it('treats a thrown/invalid session as no session', async () => {
    vi.mocked(getIronSession).mockRejectedValue(new Error('bad cookie'))
    const res = await middleware(req('/api/spark/status'))
    expect(res.status).toBe(401)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/middleware.test.ts`
Expected: FAIL — cannot find module `@/middleware`.

- [ ] **Step 3: Write minimal implementation**

Create `src/middleware.ts`:
```typescript
import { NextRequest, NextResponse } from 'next/server'
import { getIronSession } from 'iron-session'
import { sessionOptions, hasValidServiceToken, type SessionData } from '@/lib/auth/session'
import { decideAccess } from '@/lib/auth/access'

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl
  const isApi = pathname.startsWith('/api/')
  const hasServiceToken = hasValidServiceToken(req.headers.get('x-ironforge-service'))

  // Read (not write) the session cookie. Edge-safe: iron-session uses Web Crypto.
  const res = NextResponse.next()
  let hasSession = false
  try {
    const session = await getIronSession<SessionData>(req, res, sessionOptions)
    hasSession = Boolean(session.userId)
  } catch {
    hasSession = false
  }

  const decision = decideAccess({ pathname, isApi, hasSession, hasServiceToken })
  if (decision === 'allow') return res
  if (decision === 'unauthorized') {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 })
  }
  const url = req.nextUrl.clone()
  url.pathname = '/login'
  url.searchParams.set('next', pathname)
  return NextResponse.redirect(url)
}

// Run on everything except framework statics and static asset files (so public
// images/styles load on the unauthenticated /login page).
export const config = {
  matcher: ['/((?!_next/static|_next/image|.*\\.(?:svg|png|jpg|jpeg|gif|ico|webp|css|js|map|woff2?)).*)'],
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/middleware.test.ts`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/middleware.ts src/middleware.test.ts
git commit -m "feat(auth): default-deny edge middleware gate"
```

---

## Task 7: Login route (TDD)

**Files:**
- Create: `src/app/api/auth/login/route.ts`
- Test: `src/app/api/auth/__tests__/login.test.ts`

- [ ] **Step 1: Write the failing test**

Create `src/app/api/auth/__tests__/login.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { NextRequest } from 'next/server'

// Inline factories (no outer-variable refs) to avoid vitest's hoisting TDZ trap.
vi.mock('@/lib/db', () => ({
  dbQuery: vi.fn(),
  dbExecute: vi.fn(),
  escapeSql: (s: string) => s.replace(/'/g, "''"),
}))
vi.mock('@/lib/auth/password', () => ({ verifyPassword: vi.fn() }))
vi.mock('@/lib/auth/server', () => ({ getSession: vi.fn() }))

import { dbQuery, dbExecute } from '@/lib/db'
import { verifyPassword } from '@/lib/auth/password'
import { getSession } from '@/lib/auth/server'
import { POST } from '../login/route'

const save = vi.fn()
const sessionObj: Record<string, unknown> = {}

function post(body: unknown) {
  return new NextRequest('https://app.test/api/auth/login', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  })
}

const activeUser = {
  id: 7, username: 'matt', name: 'Matt', person: 'Matt',
  password_hash: 'hash', is_active: true, must_change_password: true,
}

beforeEach(() => {
  vi.mocked(dbQuery).mockReset()
  vi.mocked(dbExecute).mockReset()
  vi.mocked(verifyPassword).mockReset()
  save.mockReset()
  for (const k of Object.keys(sessionObj)) delete sessionObj[k]
  sessionObj.save = save
  vi.mocked(getSession).mockResolvedValue(sessionObj as never)
  vi.mocked(dbExecute).mockResolvedValue(1)
})

describe('POST /api/auth/login', () => {
  it('logs in a valid active user and reports mustChangePassword', async () => {
    vi.mocked(dbQuery).mockResolvedValue([activeUser] as never)
    vi.mocked(verifyPassword).mockResolvedValue(true)
    const res = await POST(post({ username: 'Matt', password: 'pw' }))
    const json = await res.json()
    expect(res.status).toBe(200)
    expect(json).toEqual({ ok: true, mustChangePassword: true })
    expect(save).toHaveBeenCalledOnce()
    expect(sessionObj.userId).toBe(7)
  })

  it('rejects a wrong password with 401', async () => {
    vi.mocked(dbQuery).mockResolvedValue([activeUser] as never)
    vi.mocked(verifyPassword).mockResolvedValue(false)
    const res = await POST(post({ username: 'matt', password: 'bad' }))
    expect(res.status).toBe(401)
    expect(save).not.toHaveBeenCalled()
  })

  it('rejects an inactive user with 401', async () => {
    vi.mocked(dbQuery).mockResolvedValue([{ ...activeUser, is_active: false }] as never)
    vi.mocked(verifyPassword).mockResolvedValue(true)
    const res = await POST(post({ username: 'matt', password: 'pw' }))
    expect(res.status).toBe(401)
  })

  it('rejects an unknown user with 401', async () => {
    vi.mocked(dbQuery).mockResolvedValue([] as never)
    const res = await POST(post({ username: 'ghost', password: 'pw' }))
    expect(res.status).toBe(401)
  })

  it('rejects a missing body with 400', async () => {
    const res = await POST(post({ username: '' }))
    expect(res.status).toBe(400)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/app/api/auth/__tests__/login.test.ts`
Expected: FAIL — cannot find module `../login/route`.

- [ ] **Step 3: Write minimal implementation**

Create `src/app/api/auth/login/route.ts`:
```typescript
import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, escapeSql } from '@/lib/db'
import { verifyPassword } from '@/lib/auth/password'
import { getSession } from '@/lib/auth/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

interface UserRow {
  id: number
  username: string
  name: string
  person: string | null
  password_hash: string
  is_active: boolean
  must_change_password: boolean
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json().catch(() => ({} as Record<string, unknown>))
    const username = String(body.username || '').trim().toLowerCase()
    const password = String(body.password || '')
    if (!username || !password) {
      return NextResponse.json({ error: 'Username and password required' }, { status: 400 })
    }

    const rows = await dbQuery<UserRow>(
      `SELECT id, username, name, person, password_hash, is_active, must_change_password
       FROM ironforge_users WHERE username = '${escapeSql(username)}' LIMIT 1`,
    )
    const user = rows[0]
    const ok = !!user && user.is_active && (await verifyPassword(password, user.password_hash))
    if (!ok) {
      return NextResponse.json({ error: 'Invalid username or password' }, { status: 401 })
    }

    const session = await getSession()
    session.userId = user.id
    session.username = user.username
    session.name = user.name
    session.person = user.person
    await session.save()

    await dbExecute(
      `UPDATE ironforge_users SET last_login_at = NOW(), updated_at = NOW() WHERE id = ${user.id}`,
    )

    return NextResponse.json({ ok: true, mustChangePassword: user.must_change_password })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/app/api/auth/__tests__/login.test.ts`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/app/api/auth/login/route.ts src/app/api/auth/__tests__/login.test.ts
git commit -m "feat(auth): POST /api/auth/login"
```

---

## Task 8: Logout + me routes

**Files:**
- Create: `src/app/api/auth/logout/route.ts`
- Create: `src/app/api/auth/me/route.ts`

(No dedicated unit tests — both are thin session reads verified by the build and by Task 16 manual checks. `getSession` is already covered indirectly via the login test's mock pattern.)

- [ ] **Step 1: Create the logout route**

Create `src/app/api/auth/logout/route.ts`:
```typescript
import { NextResponse } from 'next/server'
import { getSession } from '@/lib/auth/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function POST() {
  const session = await getSession()
  session.destroy()
  return NextResponse.json({ ok: true })
}
```

- [ ] **Step 2: Create the me route**

Create `src/app/api/auth/me/route.ts`:
```typescript
import { NextResponse } from 'next/server'
import { dbQuery } from '@/lib/db'
import { getSession } from '@/lib/auth/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET() {
  const session = await getSession()
  if (!session.userId) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 })
  }
  const rows = await dbQuery<{ must_change_password: boolean }>(
    `SELECT must_change_password FROM ironforge_users WHERE id = ${session.userId} LIMIT 1`,
  )
  return NextResponse.json({
    username: session.username ?? null,
    name: session.name ?? null,
    person: session.person ?? null,
    mustChangePassword: rows[0]?.must_change_password ?? false,
  })
}
```

- [ ] **Step 3: Verify build/typecheck**

Run: `npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 4: Commit**

```bash
git add src/app/api/auth/logout/route.ts src/app/api/auth/me/route.ts
git commit -m "feat(auth): logout + me routes"
```

---

## Task 9: Change-password route (TDD)

**Files:**
- Create: `src/app/api/auth/change-password/route.ts`
- Test: `src/app/api/auth/__tests__/change-password.test.ts`

- [ ] **Step 1: Write the failing test**

Create `src/app/api/auth/__tests__/change-password.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { NextRequest } from 'next/server'

vi.mock('@/lib/db', () => ({ dbQuery: vi.fn(), dbExecute: vi.fn() }))
vi.mock('@/lib/auth/password', () => ({ verifyPassword: vi.fn(), hashPassword: vi.fn() }))
vi.mock('@/lib/auth/server', () => ({ getSession: vi.fn() }))

import { dbQuery, dbExecute } from '@/lib/db'
import { verifyPassword, hashPassword } from '@/lib/auth/password'
import { getSession } from '@/lib/auth/server'
import { POST } from '../change-password/route'

let session: Record<string, unknown> = { userId: 7 }

function post(body: unknown) {
  return new NextRequest('https://app.test/api/auth/change-password', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  })
}

beforeEach(() => {
  vi.mocked(dbQuery).mockReset()
  vi.mocked(dbExecute).mockReset()
  vi.mocked(verifyPassword).mockReset()
  vi.mocked(hashPassword).mockReset()
  vi.mocked(dbExecute).mockResolvedValue(1)
  session = { userId: 7 }
  // mockImplementation reads `session` at call time, so the 401 test can reassign it.
  vi.mocked(getSession).mockImplementation(async () => session as never)
})

describe('POST /api/auth/change-password', () => {
  it('changes the password when the current one is correct', async () => {
    vi.mocked(dbQuery).mockResolvedValue([{ password_hash: 'old' }] as never)
    vi.mocked(verifyPassword).mockResolvedValue(true)
    vi.mocked(hashPassword).mockResolvedValue('newhash')
    const res = await POST(post({ currentPassword: 'old', newPassword: 'a-very-long-password' }))
    expect(res.status).toBe(200)
    expect(dbExecute).toHaveBeenCalledOnce()
    expect(hashPassword).toHaveBeenCalledWith('a-very-long-password')
  })

  it('rejects a short new password with 400', async () => {
    const res = await POST(post({ currentPassword: 'old', newPassword: 'short' }))
    expect(res.status).toBe(400)
    expect(dbExecute).not.toHaveBeenCalled()
  })

  it('rejects a wrong current password with 400', async () => {
    vi.mocked(dbQuery).mockResolvedValue([{ password_hash: 'old' }] as never)
    vi.mocked(verifyPassword).mockResolvedValue(false)
    const res = await POST(post({ currentPassword: 'wrong', newPassword: 'a-very-long-password' }))
    expect(res.status).toBe(400)
    expect(dbExecute).not.toHaveBeenCalled()
  })

  it('rejects when there is no session with 401', async () => {
    session = {}
    const res = await POST(post({ currentPassword: 'old', newPassword: 'a-very-long-password' }))
    expect(res.status).toBe(401)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/app/api/auth/__tests__/change-password.test.ts`
Expected: FAIL — cannot find module `../change-password/route`.

- [ ] **Step 3: Write minimal implementation**

Create `src/app/api/auth/change-password/route.ts`:
```typescript
import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute } from '@/lib/db'
import { getSession } from '@/lib/auth/server'
import { verifyPassword, hashPassword } from '@/lib/auth/password'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const MIN_LEN = 12

export async function POST(req: NextRequest) {
  try {
    const session = await getSession()
    if (!session.userId) {
      return NextResponse.json({ error: 'unauthorized' }, { status: 401 })
    }
    const body = await req.json().catch(() => ({} as Record<string, unknown>))
    const currentPassword = String(body.currentPassword || '')
    const newPassword = String(body.newPassword || '')
    if (newPassword.length < MIN_LEN) {
      return NextResponse.json({ error: `New password must be at least ${MIN_LEN} characters` }, { status: 400 })
    }
    const rows = await dbQuery<{ password_hash: string }>(
      `SELECT password_hash FROM ironforge_users WHERE id = ${session.userId} LIMIT 1`,
    )
    const hash = rows[0]?.password_hash
    if (!hash || !(await verifyPassword(currentPassword, hash))) {
      return NextResponse.json({ error: 'Current password is incorrect' }, { status: 400 })
    }
    const newHash = await hashPassword(newPassword)
    await dbExecute(
      `UPDATE ironforge_users SET password_hash = $1, must_change_password = FALSE, updated_at = NOW() WHERE id = ${session.userId}`,
      [newHash],
    )
    return NextResponse.json({ ok: true })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/app/api/auth/__tests__/change-password.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/app/api/auth/change-password/route.ts src/app/api/auth/__tests__/change-password.test.ts
git commit -m "feat(auth): POST /api/auth/change-password"
```

---

## Task 10: Seed route (TDD)

**Files:**
- Create: `src/app/api/auth/seed/route.ts`
- Test: `src/app/api/auth/__tests__/seed.test.ts`

- [ ] **Step 1: Write the failing test**

Create `src/app/api/auth/__tests__/seed.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { NextRequest } from 'next/server'

vi.mock('@/lib/db', () => ({
  dbQuery: vi.fn(),
  dbExecute: vi.fn(),
  escapeSql: (s: string) => s.replace(/'/g, "''"),
}))
vi.mock('@/lib/auth/password', () => ({ hashPassword: vi.fn() }))

import { dbQuery, dbExecute } from '@/lib/db'
import { hashPassword } from '@/lib/auth/password'
import { POST } from '../seed/route'

const origToken = process.env.IRONFORGE_SEED_TOKEN
beforeEach(() => {
  vi.mocked(dbQuery).mockReset()
  vi.mocked(dbExecute).mockReset()
  vi.mocked(dbExecute).mockResolvedValue(1)
  vi.mocked(hashPassword).mockResolvedValue('hashed')
  process.env.IRONFORGE_SEED_TOKEN = 'seed-secret'
})
afterEach(() => { process.env.IRONFORGE_SEED_TOKEN = origToken })

function post(token: string | null, body: unknown = {}) {
  const headers: Record<string, string> = { 'content-type': 'application/json' }
  if (token !== null) headers['x-ironforge-seed-token'] = token
  return new NextRequest('https://app.test/api/auth/seed', { method: 'POST', headers, body: JSON.stringify(body) })
}

describe('POST /api/auth/seed', () => {
  it('forbids requests without the seed token', async () => {
    const res = await POST(post(null))
    expect(res.status).toBe(403)
    expect(dbExecute).not.toHaveBeenCalled()
  })

  it('forbids a wrong seed token', async () => {
    const res = await POST(post('wrong'))
    expect(res.status).toBe(403)
  })

  it('creates missing users and returns generated passwords once', async () => {
    vi.mocked(dbQuery).mockResolvedValue([] as never) // no existing users
    const res = await POST(post('seed-secret'))
    const json = await res.json()
    expect(res.status).toBe(200)
    expect(json.users).toHaveLength(3)
    expect(json.users.every((u: { status: string }) => u.status === 'created')).toBe(true)
    expect(json.users.every((u: { password: string }) => typeof u.password === 'string' && u.password.length > 0)).toBe(true)
    expect(dbExecute).toHaveBeenCalledTimes(3)
  })

  it('is idempotent — skips users that already exist', async () => {
    vi.mocked(dbQuery).mockResolvedValue([{ id: 1 }] as never) // every user exists
    const res = await POST(post('seed-secret'))
    const json = await res.json()
    expect(json.users.every((u: { status: string }) => u.status === 'exists')).toBe(true)
    expect(dbExecute).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/app/api/auth/__tests__/seed.test.ts`
Expected: FAIL — cannot find module `../seed/route`.

- [ ] **Step 3: Write minimal implementation**

Create `src/app/api/auth/seed/route.ts`:
```typescript
import { NextRequest, NextResponse } from 'next/server'
import { randomBytes } from 'crypto'
import { dbQuery, dbExecute, escapeSql } from '@/lib/db'
import { hashPassword } from '@/lib/auth/password'
import { safeEqual } from '@/lib/auth/session'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const SEED_USERS = [
  { username: 'user', name: 'User', person: 'User' },
  { username: 'matt', name: 'Matt', person: 'Matt' },
  { username: 'logan', name: 'Logan', person: 'Logan' },
]

function genPassword(): string {
  return randomBytes(12).toString('base64url')
}

export async function POST(req: NextRequest) {
  const expected = process.env.IRONFORGE_SEED_TOKEN
  const provided = req.headers.get('x-ironforge-seed-token')
  if (!expected || !provided || !safeEqual(provided, expected)) {
    return NextResponse.json({ error: 'forbidden' }, { status: 403 })
  }
  try {
    const body = await req.json().catch(() => ({} as Record<string, unknown>))
    const overrides = (body.passwords as Record<string, string>) || {}
    const created: Array<{ username: string; password: string | null; status: string }> = []

    for (const u of SEED_USERS) {
      const existing = await dbQuery<{ id: number }>(
        `SELECT id FROM ironforge_users WHERE username = '${escapeSql(u.username)}' LIMIT 1`,
      )
      if (existing.length > 0) {
        created.push({ username: u.username, password: null, status: 'exists' })
        continue
      }
      const plain = overrides[u.username] || genPassword()
      const hash = await hashPassword(plain)
      await dbExecute(
        `INSERT INTO ironforge_users (username, name, person, password_hash, must_change_password)
         VALUES ($1, $2, $3, $4, TRUE)`,
        [u.username, u.name, u.person, hash],
      )
      created.push({ username: u.username, password: plain, status: 'created' })
    }
    return NextResponse.json({ ok: true, users: created })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/app/api/auth/__tests__/seed.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/app/api/auth/seed/route.ts src/app/api/auth/__tests__/seed.test.ts
git commit -m "feat(auth): token-guarded POST /api/auth/seed bootstrap"
```

---

## Task 11: Service-token bypass for internal self-callers

**Files:**
- Modify: `src/lib/forgeBriefings/context.ts:18-22`
- Modify: `src/app/api/builder/health/route.ts:73-75`

(No unit test — `serviceHeaders` is covered by Task 5; these are call-site wiring verified by the build and by the Task 16 briefings check.)

- [ ] **Step 1: Patch forgeBriefings/context.ts**

In `src/lib/forgeBriefings/context.ts`, add the import at the top (next to the other imports):
```typescript
import { serviceHeaders } from '@/lib/auth/session'
```
Then update the three self-fetches inside `fetchDashboardState` (currently lines 19-21) to pass the header:
```typescript
    const [statusR, posR, perfR] = await Promise.all([
      fetch(`${baseUrl}/api/${bot}/status`, { headers: serviceHeaders() }).then(r => r.ok ? r.json() : null).catch(() => null),
      fetch(`${baseUrl}/api/${bot}/positions`, { headers: serviceHeaders() }).then(r => r.ok ? r.json() : null).catch(() => null),
      fetch(`${baseUrl}/api/${bot}/performance`, { headers: serviceHeaders() }).then(r => r.ok ? r.json() : null).catch(() => null),
    ])
```

- [ ] **Step 2: Patch builder/health/route.ts**

In `src/app/api/builder/health/route.ts`, add the import at the top:
```typescript
import { serviceHeaders } from '@/lib/auth/session'
```
Then update the self-fetch (line 73) to merge the header:
```typescript
    const res = await fetch(`${origin}/api/${bot}/builder/snapshot?account_type=sandbox`, {
      cache: 'no-store',
      headers: serviceHeaders(),
    })
```

- [ ] **Step 3: Verify build/typecheck**

Run: `npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 4: Commit**

```bash
git add src/lib/forgeBriefings/context.ts src/app/api/builder/health/route.ts
git commit -m "feat(auth): pass service token on internal self-calls"
```

---

## Task 12: Login page

**Files:**
- Create: `src/app/login/page.tsx`

(Frontend — verified via `npm run build` and Task 16 manual check. No unit test; vitest env is `node`, not jsdom.)

- [ ] **Step 1: Create the login page**

Create `src/app/login/page.tsx`:
```tsx
'use client'

import { useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'

export default function LoginPage() {
  const router = useRouter()
  const params = useSearchParams()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setError(data.error || 'Login failed')
        return
      }
      if (data.mustChangePassword) {
        router.push('/change-password')
        return
      }
      router.push(params.get('next') || '/')
      router.refresh()
    } catch {
      setError('Network error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-sm mx-auto mt-24">
      <div className="flex items-center gap-2 justify-center mb-6">
        <img src="/ironforge-logo.svg" alt="" className="h-9 w-9" />
        <span className="text-2xl font-bold">
          <span className="text-white">Iron</span><span className="text-amber-400">Forge</span>
        </span>
      </div>
      <form onSubmit={onSubmit} className="bg-forge-card border border-amber-900/30 rounded-lg p-6 space-y-4">
        <h1 className="text-lg font-semibold text-gray-100">Sign in</h1>
        <div className="space-y-1">
          <label htmlFor="username" className="block text-xs text-gray-400">Username</label>
          <input
            id="username" name="username" autoComplete="username" autoFocus
            value={username} onChange={(e) => setUsername(e.target.value)}
            className="w-full rounded bg-black/40 border border-amber-900/40 px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-amber-500"
          />
        </div>
        <div className="space-y-1">
          <label htmlFor="password" className="block text-xs text-gray-400">Password</label>
          <input
            id="password" name="password" type="password" autoComplete="current-password"
            value={password} onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded bg-black/40 border border-amber-900/40 px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-amber-500"
          />
        </div>
        {error && <p className="text-sm text-red-400">{error}</p>}
        <button
          type="submit" disabled={busy}
          className="w-full rounded bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-black font-medium py-2 text-sm transition-colors"
        >
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}
```

- [ ] **Step 2: Verify build**

Run: `npm run build`
Expected: build succeeds; `/login` appears in the route manifest.

- [ ] **Step 3: Commit**

```bash
git add src/app/login/page.tsx
git commit -m "feat(auth): login page"
```

---

## Task 13: Change-password page

**Files:**
- Create: `src/app/change-password/page.tsx`

- [ ] **Step 1: Create the change-password page**

Create `src/app/change-password/page.tsx`:
```tsx
'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'

export default function ChangePasswordPage() {
  const router = useRouter()
  const [currentPassword, setCurrent] = useState('')
  const [newPassword, setNew] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (newPassword !== confirm) {
      setError('New passwords do not match')
      return
    }
    if (newPassword.length < 12) {
      setError('New password must be at least 12 characters')
      return
    }
    setBusy(true)
    try {
      const res = await fetch('/api/auth/change-password', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ currentPassword, newPassword }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setError(data.error || 'Could not change password')
        return
      }
      router.push('/')
      router.refresh()
    } catch {
      setError('Network error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-sm mx-auto mt-24">
      <form onSubmit={onSubmit} className="bg-forge-card border border-amber-900/30 rounded-lg p-6 space-y-4">
        <h1 className="text-lg font-semibold text-gray-100">Change password</h1>
        <div className="space-y-1">
          <label htmlFor="current" className="block text-xs text-gray-400">Current password</label>
          <input id="current" type="password" autoComplete="current-password"
            value={currentPassword} onChange={(e) => setCurrent(e.target.value)}
            className="w-full rounded bg-black/40 border border-amber-900/40 px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-amber-500" />
        </div>
        <div className="space-y-1">
          <label htmlFor="new" className="block text-xs text-gray-400">New password (min 12 chars)</label>
          <input id="new" type="password" autoComplete="new-password"
            value={newPassword} onChange={(e) => setNew(e.target.value)}
            className="w-full rounded bg-black/40 border border-amber-900/40 px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-amber-500" />
        </div>
        <div className="space-y-1">
          <label htmlFor="confirm" className="block text-xs text-gray-400">Confirm new password</label>
          <input id="confirm" type="password" autoComplete="new-password"
            value={confirm} onChange={(e) => setConfirm(e.target.value)}
            className="w-full rounded bg-black/40 border border-amber-900/40 px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-amber-500" />
        </div>
        {error && <p className="text-sm text-red-400">{error}</p>}
        <button type="submit" disabled={busy}
          className="w-full rounded bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-black font-medium py-2 text-sm transition-colors">
          {busy ? 'Saving…' : 'Update password'}
        </button>
      </form>
    </div>
  )
}
```

- [ ] **Step 2: Verify build**

Run: `npm run build`
Expected: build succeeds; `/change-password` appears in the route manifest.

- [ ] **Step 3: Commit**

```bash
git add src/app/change-password/page.tsx
git commit -m "feat(auth): self-serve change-password page"
```

---

## Task 14: Nav auth controls

**Files:**
- Create: `src/components/AuthControls.tsx`
- Modify: `src/components/Nav.tsx`

- [ ] **Step 1: Create the AuthControls component**

Create `src/components/AuthControls.tsx`:
```tsx
'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'

interface Me { name?: string | null; username?: string | null }

export default function AuthControls() {
  const router = useRouter()
  const [me, setMe] = useState<Me | null>(null)

  useEffect(() => {
    let active = true
    fetch('/api/auth/me')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (active) setMe(d) })
      .catch(() => {})
    return () => { active = false }
  }, [])

  async function logout() {
    await fetch('/api/auth/logout', { method: 'POST' }).catch(() => {})
    router.push('/login')
    router.refresh()
  }

  if (!me?.name) return null

  return (
    <div className="ml-auto flex items-center gap-3 shrink-0 text-sm">
      <span className="text-gray-400">
        Signed in as <span className="text-amber-300 font-medium">{me.name}</span>
      </span>
      <a href="/change-password" className="text-gray-400 hover:text-gray-200">Change password</a>
      <button
        onClick={logout}
        className="text-gray-400 hover:text-white border border-amber-900/40 rounded px-2 py-0.5 transition-colors"
      >
        Sign out
      </button>
    </div>
  )
}
```

- [ ] **Step 2: Render it in Nav.tsx**

In `src/components/Nav.tsx`, add the import after the existing imports (after line 4):
```typescript
import AuthControls from './AuthControls'
```
Then insert `<AuthControls />` as a sibling right after the nav-links `</div>` (currently line 101), before the closing `</div>` of the `max-w-7xl` container (line 102):
```tsx
        </div>

        <AuthControls />
      </div>
```

- [ ] **Step 3: Verify build**

Run: `npm run build`
Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add src/components/AuthControls.tsx src/components/Nav.tsx
git commit -m "feat(auth): signed-in/sign-out nav controls"
```

---

## Task 15: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Run all new auth tests**

Run:
```bash
npx vitest run src/lib/auth src/middleware.test.ts src/app/api/auth
```
Expected: all suites PASS (password 3, access 7, session 8, middleware 6, login 5, change-password 4, seed 4).

- [ ] **Step 2: Full production build**

Run: `npm run build`
Expected: build succeeds with no type errors; middleware compiles; `/login` and `/change-password` in the route manifest.

- [ ] **Step 3: Commit any lockfile/build artifacts if changed**

```bash
git status --short
# commit only if package-lock.json or similar changed and is not yet committed
```

---

## Task 16: Deploy + bootstrap (operational — run with the user)

**Files:** none (operational checklist; requires the user / Render dashboard)

> These steps touch credentials/env on a live, real-money-adjacent service. Per `ironforge/CLAUDE.md`, pause for explicit user confirmation before each.

- [ ] **Step 1: Generate secrets**

```bash
node -e "console.log('IRONFORGE_SESSION_SECRET=' + require('crypto').randomBytes(32).toString('base64url'))"
node -e "console.log('IRONFORGE_SERVICE_TOKEN=' + require('crypto').randomBytes(24).toString('base64url'))"
node -e "console.log('IRONFORGE_SEED_TOKEN=' + require('crypto').randomBytes(24).toString('base64url'))"
```

- [ ] **Step 2: Set the three env vars on the `ironforge-dashboard` Render service** (dashboard or MCP `update_environment_variables`). Deploy.

- [ ] **Step 3: Bootstrap operators** — once deployed, call seed (returns the generated passwords once):
```bash
curl -s -X POST https://<ironforge-host>/api/auth/seed \
  -H "x-ironforge-seed-token: <IRONFORGE_SEED_TOKEN>" \
  -H "content-type: application/json" -d '{}'
```
Record the returned passwords, distribute to User/Matt/Logan.

- [ ] **Step 4: Verify the gate** — confirm `GET /api/spark/status` returns 401 without a cookie; confirm `/login` loads; log in as one operator and confirm dashboards load and the forced change-password flow works.

- [ ] **Step 5: Verify trading is unaffected** — confirm the scanner heartbeat is fresh (`bot_heartbeats`) and that the briefings page still renders (the service-token bypass is working). 

- [ ] **Step 6: Remove `IRONFORGE_SEED_TOKEN`** from the Render service env once all operators are seeded.

- [ ] **Step 7: Open the PR / merge** per the IronForge branch policy (verified ironforge branches auto-merge to `main`).

---

## Notes / deferred (not in this plan)
- Login page renders the full shared `Nav` while logged out; links just bounce back to `/login`. A dedicated minimal login layout is a possible follow-up.
- `mustChangePassword` is enforced softly (login redirects there); it is not blocked app-wide. Acceptable for the 3-operator roster.
- See spec §11 for the future Stripe paywall path that this foundation is designed to support.
