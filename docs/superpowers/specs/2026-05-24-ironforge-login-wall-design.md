# IronForge Login Wall — Design Spec

**Date:** 2026-05-24
**Status:** Approved (design); pending implementation plan
**Scope:** `ironforge/webapp` (Next.js 14, Render single web service)

## 1. Goal & Non-Goals

### Goal
Gate the entire IronForge dashboard behind authentication. No page or API route is
reachable without a valid login. Accounts are **named per-operator**, **invite-only**
(seeded, no public signup), backed by **iron-session** encrypted cookies and **bcrypt**
password hashing.

### Non-Goals (explicitly out of scope — YAGNI)
- **No per-user data isolation.** Every logged-in operator sees all bots and all data.
  This is a shared instance gated by login, not a multi-tenant SaaS.
- **No change to `?person=` semantics.** The existing person selector (User / Matt /
  Logan) remains a *view filter* over shared data, not a security boundary. Any
  logged-in operator may view any person's account, exactly as today.
- No public signup, no email-based password reset, no OAuth/social login.
- No admin user-management UI (seed-only provisioning).
- No changes to trading logic, the scanner, exit logic, or any bot behavior.

### Decisions locked in
- Auth mechanism: **iron-session + bcryptjs**.
- Provisioning: **seed once + self-serve password change**.
- Login identifier: **username** (lowercased). An `email` column is captured now (nullable,
  unused for login in phase 1) for forward-compatibility with the planned Stripe paywall.
- Immediate revocation: **rotate `IRONFORGE_SESSION_SECRET`** (logs everyone out).
  No per-request session-version check (keeps middleware off the connection-limited DB).

### Product context
This login wall is **phase 1 of a paid product**. A tiered Stripe paywall is planned
(not in this scope): first a **bot-alerts subscription** (pay to receive the shared bots'
signals), later a **bot-automation tier**. The phase-1 shared-data design is the permanent
foundation for the alerts tier; the automation tier will later require per-user isolation.
See §11 for the forward-compatibility decisions that keep that path open.

## 2. Context (current state)

- IronForge is a single Next.js 14 web service on Render (`ironforge/webapp`), App
  Router, PostgreSQL via `pg` (`src/lib/db.ts`). Health check path: `/api/health`.
- **No authentication exists today.** All pages and all `/api/[bot]/*` routes (including
  `force-trade`, `force-close`, `toggle`, `config`, `eod-close`) are open.
- The **scanner runs in-process**: `db.ts ensureTables()` calls
  `ensureScannerStarted()` → `startScanner()` (`src/lib/scanner.ts`), which registers
  `setInterval` loops. It calls the DB/Tradier libraries directly — it does **not** make
  HTTP requests to its own API routes.
- The `person` concept (User / Matt / Logan) maps 1:1 to the three
  `TRADIER_SANDBOX_KEY_*` env vars. Roster is fixed and rarely changes.
- **Internal self-HTTP callers** (server-side code that fetches IronForge's *own*
  routes, and would be 401'd by a naive gate):
  - `src/lib/forgeBriefings/context.ts:19-21` → `/api/{bot}/status|positions|performance`
  - `src/app/api/builder/health/route.ts:73` → `/api/{bot}/builder/snapshot`
  - (Other `fetch` calls go to Tradier / external alphagex-api with their own tokens and
    are unaffected.)

## 3. Data Model

One additive table, created in `src/lib/db.ts` `INIT_DDL` alongside the other
`ironforge_*` tables (auto-creates on first use; no standalone migration script — matches
the existing pattern and the IronForge hard rule that backend logic lives in the webapp).

```sql
CREATE TABLE IF NOT EXISTS ironforge_users (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  username TEXT NOT NULL UNIQUE,        -- login id, stored lowercased (e.g. "matt")
  email TEXT UNIQUE,                    -- nullable; captured now for future Stripe paywall (§11)
  name TEXT NOT NULL,                   -- display name shown in nav
  person TEXT,                          -- optional link to existing person (User/Matt/Logan)
  password_hash TEXT NOT NULL,          -- bcrypt hash
  is_active BOOLEAN DEFAULT TRUE,
  must_change_password BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  last_login_at TIMESTAMPTZ
);
```

Purely additive `CREATE TABLE IF NOT EXISTS`. No existing table is altered or migrated.
`ironforge_users` is intentionally the **future subscriber/tenant root**: the Stripe
paywall (§11) will add columns here (e.g. `stripe_customer_id`, `subscription_status`,
`tier`) rather than introducing a separate identity table.

## 4. Sessions (iron-session)

- Encrypted, signed, httpOnly cookie named `ironforge_session`.
- Flags: `httpOnly`, `secure` (production), `sameSite=lax`, `maxAge` ≈ 30 days.
- Payload: `{ userId: number, username: string, name: string, person: string | null }`.
- iron-session uses Web Crypto, so it decrypts in **both** the Edge runtime (middleware)
  and the Node runtime (route handlers).
- **Stateless tradeoff:** there is no DB lookup per request. Setting `is_active=false`
  takes effect at the operator's next login or session expiry. For immediate global
  lockout, rotate `IRONFORGE_SESSION_SECRET` (invalidates all existing cookies).

## 5. The Gate — `middleware.ts`

Default-deny across the whole app.

- **Pages** without a valid session → 302 redirect to `/login`.
- **`/api/*`** without a valid session → `401` JSON.
- **Whitelist (no auth required):** `/login`, `/api/auth/login`, `/api/auth/logout`,
  `/api/auth/seed`, `/api/health`, `/_next/*` (static/image), favicon and other static
  assets.
- **Internal service-token bypass:** requests carrying header
  `x-ironforge-service: <IRONFORGE_SERVICE_TOKEN>` pass without a session. The two
  internal self-callers (§2) attach this header.
- **Edge constraint:** middleware runs on the Edge runtime and must be **DB-free**. It
  only decrypts the iron-session cookie. `pg` and `bcryptjs` are never imported into
  middleware (they would fail on Edge regardless).

### Scanner safety
The middleware intercepts inbound HTTP only. The scanner runs in-process and is booted by
`ensureTables()`, which is triggered by the public, whitelisted `/api/health` request
Render already issues. Therefore the gate cannot starve automated trading. This must be
verified post-implementation (scanner heartbeat fresh after deploy).

## 6. Auth API Routes (Node runtime)

All under `src/app/api/auth/`.

| Route | Method | Behavior |
|-------|--------|----------|
| `/api/auth/login` | POST | Body `{username, password}`. Look up active user by lowercased username; `bcrypt.compare`. On success set iron-session, update `last_login_at`, return `{ok:true, mustChangePassword}`. On failure return generic `401` (no user-enumeration). |
| `/api/auth/logout` | POST | Destroy session, clear cookie. |
| `/api/auth/change-password` | POST | Session required. Body `{currentPassword, newPassword}`. Verify current, hash new, set `must_change_password=false`. Enforce a minimum new-password length (≥ 12). |
| `/api/auth/me` | GET | Return current session user `{username, name, person, mustChangePassword}` or `401`. |
| `/api/auth/seed` | POST | **Bootstrap only.** Requires header `x-ironforge-seed-token: <IRONFORGE_SEED_TOKEN>`. Idempotent: skips usernames that already exist. Seeds User / Matt / Logan with `must_change_password=true`. If body supplies passwords, use them; otherwise generate random passwords and return them **once** in the response. Whitelisted in middleware but self-guarded by the token. |

Notes:
- Use **bcryptjs** (pure JS) to avoid native-build issues in Render's node build.
- Login throttling: rely on bcrypt cost for v1; optional lightweight in-memory
  per-username/IP counter may be added but is not required for this scope.

## 7. Frontend

- `src/app/login/page.tsx` — username + password form → `POST /api/auth/login`.
  On success redirect to `/`, or to `/change-password` if `mustChangePassword`.
- `src/app/change-password/page.tsx` — self-serve change. First-login forced flow lands
  here and blocks navigation until `must_change_password` clears.
- `src/components/Nav.tsx` — add "Signed in as {name}", a Logout action, and a
  Change-password link. Styling stays clean and custom (no emojis / stock icons), per the
  project UI standard.
- Root `src/app/layout.tsx` — fetch `/api/auth/me` to render the signed-in state.
  Middleware already guarantees authentication; the client only needs the display name.

## 8. Configuration / Environment

New env vars in `ironforge/render.yaml` (`sync: false`):

| Var | Purpose | Lifetime |
|-----|---------|----------|
| `IRONFORGE_SESSION_SECRET` | iron-session encryption key (≥ 32 chars) | Permanent; rotating it logs everyone out |
| `IRONFORGE_SERVICE_TOKEN` | Internal self-call bypass header value | Permanent |
| `IRONFORGE_SEED_TOKEN` | Guards `/api/auth/seed` | Temporary; remove after bootstrap |

New dependencies: `iron-session`, `bcryptjs` (+ `@types/bcryptjs` dev).

## 9. Testing (vitest — matches existing `src/lib/__tests__` setup)

- **login:** success; wrong password → 401; inactive user → 401; unknown user → 401
  (generic message, no enumeration).
- **change-password:** wrong current rejected; success clears `must_change_password`;
  new-password length enforced.
- **seed:** missing/invalid token → 403; idempotent (re-run skips existing users);
  generated passwords returned once.
- **middleware:** unauthenticated `/api/[bot]/*` → 401; unauthenticated page → redirect;
  whitelisted paths pass; valid session passes; valid service-token header passes.

Per the IronForge scope-discipline rule: verification is `npm run build` plus the new
test files only — do not run the full suite (it drags in unrelated pre-existing failures).

## 10. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Edge runtime cannot use `pg`/bcrypt | Middleware is DB-free; decrypts cookie only. Node-runtime route handlers do all DB/bcrypt work. |
| Auth gate starves the in-process scanner | Scanner is in-process, booted via public `/api/health`; gate intercepts inbound HTTP only. Verify heartbeat post-deploy. |
| Internal self-HTTP calls 401'd | `x-ironforge-service` token bypass; add header to `forgeBriefings/context.ts` and `builder/health`. |
| Need to revoke an operator immediately | Rotate `IRONFORGE_SESSION_SECRET` (global logout). `is_active=false` covers next-login. |
| Native bcrypt build failure on Render | Use `bcryptjs` (pure JS). |
| Schema change on production DB | Additive `CREATE TABLE IF NOT EXISTS` only; no destructive migration. |

## 11. Future direction — Stripe paywall (tiered)

**Not in this scope.** Documented so phase-1 choices stay forward-compatible.

Planned tiers:
1. **Bot-alerts subscription** — pay to receive the shared bots' alerts/signals. Builds
   directly on the phase-1 shared-data model; no per-user data isolation needed. Phase 2
   work: public signup, Stripe Checkout/Customer Portal, a subscription-status check in
   the gate, and per-subscriber alert delivery (the existing `DISCORD_WEBHOOK_URL` plumbing
   is a starting point).
2. **Bot-automation tier** — a higher tier unlocking automation. This is where per-user
   isolation (user_id FK across bot tables, per-user configs/accounts, per-user broker
   linking) becomes necessary. Treated as a later, larger effort.

Phase-1 decisions that keep this path open (all already in this spec):
- `ironforge_users` is the single identity/subscriber root; paywall adds columns here.
- `email` column captured now (avoids backfilling subscriber emails later).
- The middleware gate is written generically so a "subscription active?" check slots in
  next to the "logged in?" check without restructuring.
- Seed-only provisioning is cleanly replaceable by a public signup route; nothing about
  the auth routes assumes a fixed roster except the seed endpoint itself.

## 12. Out-of-scope follow-ups (deferred)
- In-app admin user-management UI (add/disable/reset operators).
- Per-request session-version revocation.
- Email-based password reset.
- Stripe paywall and per-user data isolation (see §11).

## 13. Estimated effort
~3–4 days: data model + sessions + middleware (~1d), auth routes + seed (~1d), frontend
login/change-password/nav (~1d), tests + render.yaml + deploy verification (~0.5–1d).
