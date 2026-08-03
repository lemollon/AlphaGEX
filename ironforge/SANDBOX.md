# IronForge Sandbox

## The deploy gate

The sandbox tracks the **`staging`** branch, not `main`. That is the whole point:
if it tracked `main` it would only ever run code production had already taken, so
it could test data and flows but never catch a bad deploy before real money saw it.

```
feature branch → merge to staging → sandbox auto-deploys → click through the funnel
                                                                    ↓
                              production ← merge staging → main ← only after it passes
```

Concretely:

```bash
git checkout staging && git merge <your-branch> && git push origin staging
# sandbox redeploys; test at https://ironforge-sandbox.onrender.com
# happy? then:
git checkout main && git merge staging && git push origin main
```

Two rules that keep the gate honest:

1. **Never push straight to `main`.** A commit that skips `staging` skips the gate
   entirely, and the gate is worthless if it is optional.
2. **`staging` must never fall behind `main`.** If a hotfix lands on `main`
   directly, merge `main` back into `staging` immediately — otherwise the next
   staging→main merge silently reverts it.

The sandbox runs the same image, build command and start command as production.
The only differences are the databases, the broker host, Stripe test mode, and
the fake customers — which is exactly what makes a pass here meaningful.


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

## What exists (created 2026-08-02)

| Resource | ID | Database name |
|---|---|---|
| `ironforge-sandbox` (web, starter) | `srv-d9nqr861egvs738l2990` | — |
| `ironforge-sandbox-db` | `dpg-d9nqqpajnfac73bkjelg-a` | `ironforge_sandbox_db` |
| `ironforge-sandbox-customers-db` | `dpg-d9nqqt3ncjis73aoeba0-a` | `ironforge_sandbox_customers_db` |

URL: https://ironforge-sandbox.onrender.com

The rule on database names is **"must not be a production name"**, not "must be
one specific name" — the guard rejects `ironforge`, `ironforge_customers`,
`alphagex` and `alphagex_backtest` by *exact* match. Render derives the database
name from the instance name, so `ironforge_sandbox_db` is fine; anything that
resolves to a bare production name is not.

## Standing it up (if recreating from scratch)

`render.yaml` describes the intended end state, but the live services are managed
from the dashboard — so create these there.

1. **Two Postgres instances** (`basic_256mb` each, ~$7/mo) whose database names
   are not production names (see the table above for what was actually used).

2. **One web service** `ironforge-sandbox` (starter, ~$7/mo):
   - Repo `lemollon/AlphaGEX`, branch `main`
   - Build: `cd ironforge/webapp && npm install && npm run build && cp -r .next/static .next/standalone/.next/static && cp -r public .next/standalone/public`
   - Start: `cd ironforge/webapp && node start.js`
   - (The monorepo path is in the commands because the Render API cannot set
     `rootDir`; setting `rootDir: ironforge/webapp` in the dashboard and dropping
     the `cd` is equivalent.)

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

   A service created before its databases are attached **will fail its first
   deploy on purpose**, with `✗ DATABASE_URL is unset`. That is the guard
   working, not a misconfiguration; attach the databases and redeploy.

---

## Seeding fake customers

Tables self-create on first request, so hit the site once (or `/api/health`)
before seeding.

From the Render shell on `ironforge-sandbox`:

```bash
cd ironforge/webapp
npm run seed:sandbox             # clear + reseed
npm run seed:sandbox -- --reset  # clear ONLY (both DBs), then stop
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

### Both databases get seeded

`/live` does **not** read the customer's mirrored `customer_positions`. It reads
the master bot's book out of the **trading** database, authorized by a row in
`ironforge_customer_bots` (`lib/live/viewer.ts`). With no such row `allowedBots`
is empty and every `/live` route returns `{ empty: true }` — a fully-seeded
customer still lands on a blank dashboard.

So the script writes to both: the customer records to `CUSTOMERS_DATABASE_URL`,
and a SPARK book (paper account, one open + one closed position, an intraday
equity series, a heartbeat) to `DATABASE_URL` for `active@` only.

Two things there look alarming and are not:

- Those rows carry `account_type='production'`. SPARK is a production-mode bot
  and `ledgerFilter()` returns only those rows. It is how the read path
  partitions ledgers — not a claim about real money, which this service has
  already been proven unable to reach.
- Every row carries `person='Sandbox'`. `scopeFilter()` fails closed, so a NULL
  `person` matches nothing. That is deliberate: on 2026-07-27 a NULL `person`
  showed a signed-in customer the operator's real SPARK account.

`paid@` and `connected@` have no bot mapping, so their `/live` is empty — that is
their real state, not a gap.

---

## Billing in the sandbox

Stripe **test mode is a separate object space from live** — products, prices and
webhooks do not carry over. The sandbox has its own:

- Test webhook **"IronForge sandbox billing"** → `/api/billing/webhook`,
  subscribed to the six events `webhook/route.ts` actually handles:
  `checkout.session.completed`, the three `customer.subscription.*`,
  `invoice.paid`, `invoice.payment_failed`.
- Test prices under lookup keys `spark_monthly` ($50), `flame_monthly` ($50),
  `both_monthly` ($75), `community_monthly` ($10).

🚨 **A price can be active while its PRODUCT is archived.** Checkout then fails
with `Price … is not available to be purchased because its product is not active`
— which reads like a missing price and is not. Check the product, not the price:

```bash
curl -u "$SK_TEST:" https://api.stripe.com/v1/products/<prod_id> -d active=true
```

Verified end to end on 2026-08-02 with card `4242 4242 4242 4242`: checkout →
trial started → Stripe fired the events → the app verified the signature and
moved that persona's entitlements from none to `["spark"]`.

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

---

## Hard-won, 2026-08-02

- **A healthy URL is not proof your code is live.** `/api/health` answers from the
  OLD instance for the whole of a deploy. Check the deploy record, not the URL.
- **Render can wedge a build.** One sat `build_in_progress` for 29 minutes with a
  frozen `updatedAt`, and `trigger_deploy` merely queued behind it. Cancel it in
  the dashboard; nothing else clears the queue.
- **The Render API cannot read env vars or Postgres connection strings**, and
  cannot set a service's branch. Those three stay manual.
- **`/api/health` checks `TRADIER_API_KEY`.** That is the quote key; the guard
  permits it only with `TRADIER_BASE_URL` pinned to `sandbox.tradier.com`,
  because `tradier.ts` defaults to PRODUCTION Tradier when the key is set and the
  base URL is not.
- **The seed's cleanup is DISCOVERED from `pg_constraint`, not hardcoded.** A
  fixed list broke twice — first on `agent_configs` ordering, then when
  `mobile_refresh_tokens` arrived with the mobile-auth work. Do not reintroduce a
  literal table list; add tables freely and the seed will follow.
- **Dates in seeded rows must be derived in CT**, not `CURRENT_DATE`. Render's
  Postgres session is UTC and the /live charts filter by CT date, so a UTC-dated
  seed run after 00:00 UTC renders an empty chart for ~5 hours a day.
