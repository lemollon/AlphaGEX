# IronForge Account Creation — Backend (Sub-project C) Design Spec

**Date:** 2026-06-10
**Depends on:** Phase A+B (shipped). **Defers to:** D (email transport), E (Attio), F (onboarding guard).
**Decisions locked:** extend existing custom auth (bcrypt + iron-session); customer data lives in the dedicated `ironforge-customers` Render Postgres; C also owns the verification-token model + verify callback (email *sending* is D).

---

## 1. Context

The handoff doc (`IronForge_AccountCreation_DeveloperHandoff_v1`) defines the full enrollment
flow. Phase B shipped the `/signup` UI + a validate-only stub `POST /api/auth/signup`. This
spec makes account creation real and persistent.

**Customer database (resolved):** `ironforge-customers` — Render Postgres
`dpg-d8eeek740ujc73dh446g-a`, region **oregon**, PG **18**, owner Optionist_Prime, basic_256mb,
~empty. This is SEPARATE from the IronForge bot Postgres (`DATABASE_URL`) and from the
`ironforge_users` operator table. External traffic is blocked; the webapp connects over the
**internal** URL.

**Auth model:** No third-party auth provider. We store a bcrypt `password_hash` directly on the
customer `users` row and keep `auth_user_id` nullable (reserved for a future managed-provider
migration). Sessions continue to use the existing iron-session stack.

---

## 2. Architecture

### 2.1 Second DB connection — `lib/customers-db.ts`
A dedicated `pg.Pool` keyed on a new env var **`CUSTOMERS_DATABASE_URL`**, mirroring
`lib/db.ts` (prod SSL `{ rejectUnauthorized: false }`, lazy singleton pool). Exposes:
- `customerQuery<T>(sql): Promise<T[]>`, `customerExecute(sql): Promise<void>`
- `ensureCustomerTables()` — idempotent `CREATE TABLE IF NOT EXISTS` on first use (same pattern
  as the bot DB). Called at the top of each customer route.
- `escapeSql` reused from `lib/db`.
The webapp's existing `DATABASE_URL` (bot Postgres) is untouched.

### 2.2 Schema (created in `ironforge-customers`)

```sql
CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  auth_user_id TEXT UNIQUE,                       -- nullable; reserved for future provider
  password_hash TEXT NOT NULL,                    -- bcrypt (custom auth)
  first_name TEXT NOT NULL,
  last_name TEXT NOT NULL,
  email TEXT UNIQUE NOT NULL,                      -- stored lowercased
  phone TEXT NOT NULL,
  state TEXT NOT NULL,
  referral_code TEXT,
  account_status TEXT NOT NULL DEFAULT 'pending_email_verification',
  onboarding_step TEXT NOT NULL DEFAULT 'account_created',
  email_verified BOOLEAN NOT NULL DEFAULT FALSE,
  phone_verified BOOLEAN NOT NULL DEFAULT FALSE,
  age_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
  no_advice_acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
  electronic_comm_consent BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id),
  event_type TEXT NOT NULL,
  event_timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
  ip_address TEXT,
  user_agent TEXT,
  metadata JSONB
);

CREATE TABLE IF NOT EXISTS email_verification_tokens (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id),
  token_hash TEXT NOT NULL,                        -- sha256 of the raw token; raw only in the link
  expires_at TIMESTAMPTZ NOT NULL,
  consumed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_evt_token_hash ON email_verification_tokens(token_hash);
```
`gen_random_uuid()` is core in PG18. Email uniqueness enforced on the lowercased value.

### 2.3 Token utility — `lib/auth/verification-token.ts`
Pure, unit-testable:
- `generateToken(): { raw, hash }` — raw = 32 random bytes base64url (raw goes in the link);
  hash = sha256(raw) (stored).
- `hashToken(raw): string` — sha256, for lookup on verify.
- `isExpired(expiresAt, now): boolean`.
- `TOKEN_TTL_MS` = 24h.
(`crypto` from Node; routes run `runtime = 'nodejs'`.)

---

## 3. `POST /api/auth/signup` — real implementation (replaces the stub)

Sequence (doc §5), all against `ironforge-customers`:
1. Parse body → `validateSignup` (existing shared validator). On fail → 400 `{ ok:false, error, fields }`.
2. `ensureCustomerTables()`.
3. **Email uniqueness:** `SELECT id FROM users WHERE email = <normalized>`. If exists →
   write `DUPLICATE_EMAIL_ATTEMPT` audit (masked email, ip, ua) → 409
   `{ ok:false, error:'This email is already associated with an IronForge account. Log in or reset your password.', code:'duplicate_email' }`.
4. `hashPassword` (bcrypt, existing helper).
5. **Transaction:** insert `users` (normalized fields, flags from checkboxes,
   status `pending_email_verification`, onboarding `account_created`) → generate token →
   insert `email_verification_tokens` (hash, expiry). Commit. On failure → rollback, 500
   `{ ok:false, error:'Something went wrong creating your account. Please try again.' }`.
6. Write `ACCOUNT_CREATED` audit (best-effort; failure logged, does not block): metadata
   `{ source:'signup', state, referral_code, age_confirmed, no_advice_acknowledged, electronic_comm_consent }`,
   ip from `x-forwarded-for`, user_agent header.
7. **Deferred hooks (no-ops with TODO):** Attio sync (E); verification email send (D). In
   non-production, include `verifyUrl` in the response so the flow is testable before D ships;
   in production omit it.
8. → 200 `{ ok:true }`.

Response contract is unchanged from the Phase-B stub, so the `/signup` client form needs **no
changes**.

## 4. `GET /api/auth/verify?token=…` — verify callback (owned by C)

1. `ensureCustomerTables()`; `hashToken(raw)`; look up `email_verification_tokens` by hash.
2. Reject if missing / consumed / expired → redirect `/login?verifyError=1`.
3. **Transaction:** set `users.email_verified=true, account_status='email_verified',
   onboarding_step='email_verified', updated_at=now()`; set `consumed_at=now()` on the token.
4. Write `EMAIL_VERIFIED` audit.
5. Redirect to **`/login?verified=1`** for now. (F later changes this target to
   `/onboarding/legal` and adds the route guard.)

The existing Screen-2 "Verify your email" shell stays as-is; its Resend/Continue remain disabled
until D wires email transport.

---

## 5. Testing (TDD)

- `lib/auth/verification-token.ts` — generate/hash determinism, expiry boundary. (pure unit)
- `app/api/auth/signup/route.ts` — `vi.mock('@/lib/customers-db')` + `@/lib/auth/password`
  (same pattern as the existing change-password route test): happy path inserts user + token +
  audit; duplicate-email returns 409 + writes DUPLICATE_EMAIL_ATTEMPT; validation failure returns
  400 and does NOT touch the DB.
- `app/api/auth/verify/route.ts` — valid token verifies + consumes; expired/consumed/unknown
  token redirects with error.
- Verification: `npx next build` green; only the touched test files are run.

---

## 6. Operational steps (require the operator — NOT done by code)

These gate the live flow and involve credentials/region, so they need explicit action:
1. **Rotate** the `ironforge-customers` DB password (the one pasted in chat) — Render →
   Credentials → New default credential → delete old.
2. Confirm the IronForge **webapp service region is Oregon** (same as the DB) so the internal URL
   resolves. (Requires selecting the Render workspace so it can be verified.)
3. Set **`CUSTOMERS_DATABASE_URL`** = the fresh **internal** URL on the webapp service. This is a
   credential env var → applied only with explicit go-ahead; it triggers a webapp redeploy.

Until step 3, `/api/auth/signup` will return a clean 503-style error if `CUSTOMERS_DATABASE_URL`
is unset (the code guards for it) — the UI still validates and the build/tests pass.

---

## 7. Out of scope (later sub-projects)
- **D** — email transport: send + resend the verification token via an email provider; enable the
  Screen-2 Resend/Continue actions.
- **E** — Attio contact create/update + `ATTIO_SYNC_FAILED` retry queue.
- **F** — onboarding route guard + `/onboarding/legal`; switch verify redirect target.

## 8. Acceptance Criteria (C)
1. `lib/customers-db.ts` connects to `ironforge-customers` via `CUSTOMERS_DATABASE_URL` and
   auto-creates `users`, `audit_events`, `email_verification_tokens`.
2. `POST /api/auth/signup` persists a real `users` row (bcrypt hash, pending_email_verification),
   stores a verification token, writes `ACCOUNT_CREATED`, and returns `{ ok:true }` — same
   contract as the stub; `/signup` UI unchanged.
3. Duplicate email returns 409 with the doc's message and writes `DUPLICATE_EMAIL_ATTEMPT`.
4. `GET /api/auth/verify` validates/consumes a token, flips the user to `email_verified`, writes
   `EMAIL_VERIFIED`, redirects to `/login?verified=1`.
5. Password is never stored plaintext nor logged; never sent anywhere external.
6. TDD coverage for token util + both routes; `npx next build` green.
7. Missing `CUSTOMERS_DATABASE_URL` degrades gracefully (clean error), does not crash the app.
