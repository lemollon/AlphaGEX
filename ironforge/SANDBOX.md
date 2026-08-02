# IronForge Sandbox

A disposable copy of the customer product where the whole funnel — signup →
verify → legal → Stripe → brokerage → activation → `/live` — can be exercised
without real money, real customers, or production data.

It exists because production can no longer be used for this: enrollment is closed
behind `ENROLLMENT_WAITLIST_MODE`, its Stripe keys are live, and its numbers are
real. Testing by being a real customer is slow, unrepeatable, and now blocked.

---

## The safety model

The sandbox runs the **same image** as production. Every dangerous capability is
one env var away, so it does not *ask* to be safe — it **proves** it at boot.

`webapp/start.js` runs `webapp/scripts/sandbox-guard.js` before the Next server
loads. When `IRONFORGE_ENV=sandbox`, the guard **exits non-zero** — failing the
Render deploy, serving zero traffic — if any of these are true:

| Check | Why |
|---|---|
| Any of `TRADIER_API_KEY`, `TRADIER_PROD_*`, `TRADIER_SPARK2/FLAME/KINDLE_API_KEY` is set | Real broker credentials |
| `TRADIER_BASE_URL` is not a sandbox host | Real broker host |
| `STRIPE_SECRET_KEY` is not `sk_test_`/`rk_test_` | Would charge real cards |
| `SCANNER_ENABLED=true` | The scanner places orders |
| `CUSTOMER_EXECUTOR_ENABLED=true` | Places orders on customer accounts |
| `IRONFORGE_FLAME_LIVE=true` | Marks FLAME real-money |
| `DATABASE_URL` / `CUSTOMERS_DATABASE_URL` resolves to `ironforge`, `ironforge_customers`, `alphagex`, `alphagex_backtest` | Would read and write production data |
| `ATTIO_API_KEY`, `TWILIO_*`, `DISCORD_WEBHOOK_URL` set without `SANDBOX_ALLOW_OUTBOUND=true` | Writes to shared real systems |

Warnings (non-fatal): missing `STRIPE_SECRET_KEY`, missing
`CUSTOMERS_DATABASE_URL`, or `ENROLLMENT_WAITLIST_MODE=true` — each makes part of
the funnel untestable but nothing unsafe.

`RESEND_API_KEY` is deliberately **allowed**: email verification is part of the
funnel under test, and every seeded persona uses `@sandbox.ironforge.test`, which
cannot receive mail.

**Production is entirely unaffected** — with `IRONFORGE_ENV` unset the guard
returns immediately. Covered by `src/lib/__tests__/sandbox-guard.test.ts`.

Every page also renders an amber `SANDBOX` ribbon, so a screenshot of seeded
positions can't be mistaken for a real account.

---

## Standing it up (one time, Render dashboard)

`render.yaml` describes the intended end state, but the live services are managed
from the dashboard — so create these there.

1. **Two Postgres instances** (`basic_256mb` each, ~$7/mo):
   - `ironforge-sandbox-db` → database name **`ironforge_sandbox`**
   - `ironforge-sandbox-customers-db` → database name **`ironforge_customers_sandbox`**

   The names matter. The guard rejects the production names by exact match.

2. **One web service** `ironforge-sandbox` (starter, ~$7/mo):
   - Repo `lemollon/AlphaGEX`, branch `main`, root dir `ironforge/webapp`
   - Build: `npm install && npm run build && cp -r .next/static .next/standalone/.next/static && cp -r public .next/standalone/public`
   - Start: `node start.js`
   - Health check: `/api/health`

3. **Env vars** (see the `ironforge-sandbox` block in `render.yaml` for the full
   list with rationale):

   ```
   IRONFORGE_ENV=sandbox
   IRONFORGE_MODE=customer
   NEXT_PUBLIC_IRONFORGE_MODE=customer
   NODE_ENV=production
   DATABASE_URL             → from ironforge-sandbox-db
   CUSTOMERS_DATABASE_URL   → from ironforge-sandbox-customers-db
   TRADIER_BASE_URL=https://sandbox.tradier.com/v1
   TRADIER_SANDBOX_KEY_USER=<sandbox key>
   STRIPE_SECRET_KEY=sk_test_...
   STRIPE_WEBHOOK_SECRET=whsec_...        (from the TEST-mode webhook, step 4)
   IRONFORGE_SESSION_SECRET=<new random>
   IRONFORGE_CUSTOMER_SESSION_SECRET=<new random>
   IRONFORGE_SERVICE_TOKEN=<new random>
   SNAPTRADE_CLIENT_ID / _CONSUMER_KEY / _SECRET_KEY   (sandbox pair)
   RESEND_API_KEY / EMAIL_FROM
   ```

   Generate fresh session secrets — do **not** reuse production's, or a sandbox
   cookie could decrypt against production.

   Do **not** set: `SCANNER_ENABLED`, `CUSTOMER_EXECUTOR_ENABLED`,
   `ENROLLMENT_WAITLIST_MODE`, any `TRADIER_*` production key, `ATTIO_API_KEY`,
   `TWILIO_*`, `DISCORD_WEBHOOK_URL`.

4. **Stripe test-mode webhook** → `https://ironforge-sandbox.onrender.com/api/billing/webhook`,
   and put its signing secret in `STRIPE_WEBHOOK_SECRET`. Test mode is free and
   completely separate from live mode.

5. **Deploy.** Watch the logs for `[sandbox-guard] OK`. If it says
   `REFUSING TO START`, it lists every offending variable — fix and redeploy.

---

## Seeding fake customers

Tables self-create on first request, so hit the site once (or `/api/health`)
before seeding.

From the Render shell on `ironforge-sandbox`:

```bash
cd ironforge/webapp
npm run seed:sandbox           # reseed in place
npm run seed:sandbox -- --reset  # remove seeded users first
```

The script refuses to run unless `IRONFORGE_ENV=sandbox` and the guard passes.

Seven personas, one per funnel stage. Password for all: **`sandbox123`**

| Email (`@sandbox.ironforge.test`) | State |
|---|---|
| `new@` | signed up, email **not** verified |
| `verified@` | verified, legal not accepted |
| `legal@` | legal accepted, unpaid |
| `paid@` | active subscription, nothing configured |
| `pastdue@` | subscription `past_due` — dunning / payment-due UX |
| `connected@` | brokerage connected, valid agent config, not activated |
| `active@` | activated, trial running, 1 open + 1 closed position |

Re-running replaces the seeded users; it never touches anything else in the
database.

---

## Gotchas

- **Seeding is a shell script, not an API route.** IronForge's rule is that
  backend operations live in `webapp/src/app/api/` — but that rule exists so ops
  work is reachable without Databricks. A remote-callable endpoint that wipes and
  fabricates customers is a liability, so this stays a script run against a
  sandbox DB, alongside the existing `webapp/scripts/*` tools.
- **`ensureCustomerTables()` is additive.** New columns arrive via `ALTER TABLE`,
  not the `CREATE TABLE` body — `CREATE TABLE IF NOT EXISTS` is a no-op on an
  existing DB. Deleting and recreating the sandbox DB is the fastest way to get a
  truly current schema.
- **The seed script only needs `CUSTOMERS_DATABASE_URL`.** It ignores the
  trading `DATABASE_URL` and skips that one guard error.
- **Costs ~$21/mo** (starter web + two basic_256mb databases). Suspend the
  service and databases from the dashboard when not testing; nothing depends on
  them.
- The old `ironforge-dashboard-staging` service and `ironforge-staging-db`
  (both suspended since 2026-07-05, pinned to a dead branch) are **not** this.
  Delete them once the sandbox is up.
