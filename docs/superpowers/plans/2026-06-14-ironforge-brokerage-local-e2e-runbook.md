# IronForge Brokerage — Local End-to-End Sandbox Runbook

**Goal:** drive the full **connect → approve → place** loop locally against SnapTrade's sandbox,
exercising the one path that can't be verified from a build alone (`placeOrder`).

**Why this is a runbook, not an automated test:** it requires (a) a reachable Postgres and (b) a
human completing SnapTrade's hosted Connection Portal in a browser. The `ironforge-customers`
Render DB is internal-only (not reachable from a dev box), so use a throwaway Postgres.

> ⚠️ **SAFETY: place the test order in a PAPER brokerage.** `placeOrder` puts a *real* order into
> whatever account is connected. For testing, connect a **paper** broker in the portal (e.g.
> **Alpaca Paper**) — never a funded real account — so no live order is executed.

---

## 1. Provision a throwaway Postgres
Any of: a free **Neon**/**Supabase** project, a local Postgres install, or `docker run -e
POSTGRES_PASSWORD=pw -p 5432:5432 postgres`. Copy its connection string.

## 2. Fill `ironforge/webapp/.env.local` (gitignored)
Already has the SnapTrade test keys + `SNAPTRADE_SECRET_KEY`. Add:
```
CUSTOMERS_DATABASE_URL=postgres://<your throwaway DB>
IRONFORGE_SESSION_SECRET=<32+ random chars>
IRONFORGE_SERVICE_TOKEN=<any secret string>
# optional — to actually send the approval email; otherwise it just no-ops:
# RESEND_API_KEY=...    EMAIL_FROM=IronForge <no-reply@ironforge.trade>
```
Tables auto-create on first DB call (`ensureCustomerTables`).

## 3. Run the app
```
cd ironforge/webapp && npm run dev    # http://localhost:3000  (NODE_ENV=development)
```

## 4. Create + verify a test customer
1. `/signup` — fill the form. In dev the JSON response includes `verifyUrl` (Network tab).
2. Open that `verifyUrl` → email verified.
3. `/login` with those creds → you land in onboarding.

## 5. Connect a (paper) brokerage
1. Go to `/onboarding/brokerage` → **Connect your brokerage**.
2. In SnapTrade's portal, choose a **paper** broker (e.g. Alpaca Paper) and authorize.
3. You're redirected to `/api/onboarding/brokerage/callback` → `/onboarding/complete`. Connected.
   - Sanity check: `GET http://localhost:3000/api/brokerage/accounts` (logged in) lists the account.

## 6. Grab the IDs you need
- **userId** (customer id): `GET /api/auth/customer-me` → `customer.id`.
- **accountId**: from `/api/brokerage/accounts` → `accounts[0].id`.

## 7. Create a pending approval (simulates a bot signal — internal route)
```
curl -X POST http://localhost:3000/api/brokerage/trades \
  -H 'content-type: application/json' \
  -H 'x-ironforge-service: <IRONFORGE_SERVICE_TOKEN>' \
  -d '{"userId":"<uuid>","accountId":"<acct id>","symbol":"AAPL","action":"BUY","units":1}'
```
Expect `{ ok:true, approvalId, expiresAt }`. (If RESEND is set, the approval email sends.)

## 8. Approve → place (the compliance-critical path)
1. Open `/account/trades` (logged in) → the pending `BUY 1 AAPL` row appears.
2. Click **Approve** within the 5-minute window.
3. Expect the row to flip to **placed** (an order id is stored). A real paper order now exists
   in the connected Alpaca-Paper account.

## 9. Verify persistence
```sql
SELECT status, placed_order_id, error FROM trade_approvals ORDER BY created_at DESC LIMIT 1;
-- expect: placed | <order id> | null
SELECT event_type FROM audit_events ORDER BY event_timestamp DESC LIMIT 5;
-- expect TRADE_PLACED, TRADE_APPROVAL_CREATED, BROKERAGE_CONNECTED, ...
```

## Expected results checklist
- [ ] Portal connect → `brokerage_connections.status='active'`, `users.brokerage_connected=true`.
- [ ] Approval created → `trade_approvals` row `pending` with a `snaptrade_trade_id`.
- [ ] Approve before expiry → `placed` (+ order id); a paper order exists at the broker.
- [ ] Approve after 5 min → `expired`, refused (no order). (Wait it out to confirm the gate.)
- [ ] Decline a fresh one → `declined`, no order.

## Notes
- The connect/callback live under `/api/onboarding/brokerage/*` (onboarding-cookie/session gated);
  the approval routes under `/api/brokerage/*` (customer session / service token; allowlisted).
- Production keys / go-live are separate (see the main plan's Phase 4 + the §2 compliance gate).
