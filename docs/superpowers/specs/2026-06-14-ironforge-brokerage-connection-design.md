# IronForge Brokerage Connection (Model A — customer-linked, per-trade approval) — Design

**Date:** 2026-06-14
**Status:** Approved — implementing v1.
**Depends on:** Sub-project F (onboarding guard + handoff cookie) and customer-auth (session + onboarding-resume) — both shipped + live. Risk-assessment step — shipped.
**Vendor:** SnapTrade (brokerage-aggregation API; hosted Connection Portal).
**Working directory for all paths:** `ironforge/webapp/`

---

## 1. Purpose & model

Insert the **brokerage connection** step into onboarding, replacing the "billing & brokerage
coming soon" half of the completion placeholder. This is **Model A**: each customer links
**their own** brokerage account (Robinhood, Schwab, Fidelity, etc.) via SnapTrade's hosted
Connection Portal. Funds never leave the customer's account and stay in their name. IronForge
becomes an automation/recommendation layer on top.

The reference UX (Autopilot's Robinhood connection) is SnapTrade's Connection Portal verbatim —
the broker login, passkey, device-approval, and OTP screens are **hosted by SnapTrade**, so we
do not build them.

## 2. ⚠️ COMPLIANCE GATE — read before any production launch

This is a HARD gate. Code can be built and tested in the SnapTrade **sandbox** without it, but
**no live customer, no real order** until it is resolved.

1. **v1 ships PER-TRADE APPROVAL only.** Every order requires the account owner's explicit
   confirmation at placement time. This is the lane SnapTrade permits for **non-registered**
   apps ("explicit confirmation from the account owner at placement time"). No blanket
   authority, no discretionary/hands-off auto-trading in v1.
2. **Full hands-off auto-trading is OUT OF SCOPE** and is gated behind becoming a **Registered
   Investment Adviser (RIA)** or discretionary portfolio manager. SnapTrade requires this for
   "fully managed services." Do not build it in this sub-project.
3. **SnapTrade trade-enabled review:** going live requires SnapTrade's pre-launch compliance
   review for `trade`-permission apps (they get unrestricted access to review the app, and
   monitor post-launch). Budget for it.
4. **Securities counsel sign-off** before the first live trade — per-trade approval removes the
   discretionary trigger but does not by itself settle whether personalized recommendations for
   a fee require registration. This spec is not legal advice.

Source policy: https://snaptrade.com/compliance-policy ·
https://docs.snaptrade.com/docs/launch-guide

## 3. Funnel placement

```
risk_assessed → /onboarding/brokerage → (connect succeeds) onboarding_step='brokerage_connected'
  → /onboarding/complete ("you're all set")
```

- `/onboarding/brokerage` is guarded exactly like `/onboarding/risk` / `/onboarding/legal`:
  server-component check of the onboarding handoff cookie (`verifyOnboardingToken`) OR a valid
  customer session, redirecting to `/login` if absent. No middleware change needed (already
  matches the `/onboarding/*` rule).
- The risk step's success now redirects to `/onboarding/brokerage` instead of `/onboarding/complete`.
- **Connect is skippable** (advisory product): a "Skip for now" path still advances to
  `/onboarding/complete` but leaves `brokerage_connected=false` so the customer can connect later
  from their dashboard. Skipping never hard-blocks.

`nextRouteForOnboarding` resolver update (+ tests):

```ts
case 'legal_accepted':   return '/onboarding/risk'
case 'risk_assessed':    return '/onboarding/brokerage'   // NEW
case 'brokerage_connected':
default:                 return '/onboarding/complete'
```

## 4. Architecture

### 4.1 SnapTrade client — `src/lib/snaptrade.ts`
Lazy singleton over the official `snaptrade-typescript-sdk`, keyed on two env vars, mirroring the
`customers-db.ts` guard pattern so routes degrade to a clean 503 when unconfigured:

- `SNAPTRADE_CLIENT_ID`
- `SNAPTRADE_CONSUMER_KEY` (credential — signs requests; operator-set, never logged)
- `isSnapTradeConfigured(): boolean` → `!!CLIENT_ID && !!CONSUMER_KEY`
- Throws `SnapTradeNotConfiguredError` (mirrors `CustomersDbNotConfiguredError`).

The SDK handles request signing (clientId + consumerKey + timestamp signature). Verify exact
method names against the installed SDK version at implementation time; documented flow:

| Need | SDK method (verify at impl) |
|---|---|
| Register user | `authentication.registerSnapTradeUser({ userId })` → `{ userId, userSecret }` |
| Connection Portal URL | `authentication.loginSnapTradeUser({ userId, userSecret, connectionType: 'trade', customRedirect })` → `{ redirectURI }` |
| List accounts | `accountInformation.listUserAccounts({ userId, userSecret })` |
| Positions / balances | `accountInformation.getUserAccountPositions` / `getUserAccountBalance` |
| Order preview (fees/impact) | `trading.getOrderImpact({ userId, userSecret, accountId, action, universalSymbolId, orderType, timeInForce, units })` → impact + `tradeId` |
| Place a previewed order | `trading.placeOrder({ tradeId, userId, userSecret })` |
| List connections | `connections.listUserConnections({ userId, userSecret })` |
| Remove a connection | `connections.removeBrokerageAuthorization({ authorizationId, userId, userSecret })` |

### 4.2 Secrets handling
`userSecret` is a per-user credential. **Encrypt at rest** (AES-256-GCM with a new
`SNAPTRADE_SECRET_KEY` env var) before storing in the customers DB; decrypt only server-side at
call time. `userId` we set to the IronForge `users.id` (uuid) for a stable mapping.

### 4.3 Where trade-mirroring lives (scoped)
IronForge's FLAME/SPARK/INFERNO bots are **paper** today (real data, paper execution). Turning a
bot signal into a real customer order is a separate, larger capability. **v1 builds the
connection + the per-trade approval data model + UI + sandbox order placement**; wiring live
bot-signal → approval fan-out is a fast-follow. Per the IronForge HARD RULE, all backend lives in
the webapp, so approval creation is an internal API the scanner (or an AlphaGEX caller) hits — not
a separate worker.

## 5. Schema (append to `INIT_DDL` in `customers-db.ts`)

```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS snaptrade_user_id TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS snaptrade_user_secret TEXT;      -- AES-GCM ciphertext
ALTER TABLE users ADD COLUMN IF NOT EXISTS brokerage_connected BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS brokerage_connections (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id),
  authorization_id TEXT,                 -- SnapTrade brokerage authorization id
  brokerage_slug TEXT,                   -- e.g. 'ROBINHOOD'
  account_id TEXT,                       -- SnapTrade account id
  account_name TEXT,
  status TEXT NOT NULL DEFAULT 'pending', -- pending | active | disabled | removed
  last_synced_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_brokerage_conn_user ON brokerage_connections(user_id);

CREATE TABLE IF NOT EXISTS trade_approvals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id),
  account_id TEXT NOT NULL,
  bot TEXT,                              -- flame | spark | inferno (source signal)
  symbol TEXT NOT NULL,
  action TEXT NOT NULL,                  -- BUY | SELL
  units NUMERIC,
  order_type TEXT NOT NULL DEFAULT 'Market',
  preview JSONB,                         -- getOrderImpact result (est. fees, value)
  snaptrade_trade_id TEXT,               -- tradeId from getOrderImpact
  status TEXT NOT NULL DEFAULT 'pending',-- pending | approved | placed | failed | expired | declined
  expires_at TIMESTAMPTZ NOT NULL,
  placed_order_id TEXT,
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  decided_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_trade_approvals_user_status ON trade_approvals(user_id, status);
```

## 6. Routes (all `runtime='nodejs'`, customer-session-guarded unless noted)

| Route | Method | Purpose |
|---|---|---|
| `/api/brokerage/connect` | POST | Idempotently register SnapTrade user for the customer, store encrypted `userSecret`, generate a `connectionType:'trade'` portal URL with `customRedirect` → return `{ redirectURI }`. |
| `/api/brokerage/callback` | GET | Return target from the portal. Verify via `listUserAccounts`/`listUserConnections`, upsert `brokerage_connections` (status `active`), set `users.brokerage_connected=true`, advance `onboarding_step='brokerage_connected'`, audit `BROKERAGE_CONNECTED`. Redirect to `/onboarding/complete`. |
| `/api/brokerage/webhook` | POST | **No session** — SnapTrade webhooks. Verify shared `SNAPTRADE_WEBHOOK_SECRET`. Handle `CONNECTION_ADDED` / `CONNECTION_BROKEN` / `ACCOUNT_HOLDINGS_UPDATED` → update `brokerage_connections.status` + `last_synced_at`. |
| `/api/brokerage/accounts` | GET | List the customer's connected accounts + positions/balances. |
| `/api/brokerage/connection` | DELETE | `removeBrokerageAuthorization` + mark row `removed`, flip `brokerage_connected=false` if none remain. |
| `/api/brokerage/trades` | GET | List the customer's `trade_approvals` (pending + recent). |
| `/api/brokerage/trades/[id]/approve` | POST | Customer approves a pending approval → `trading.placeOrder({ tradeId })` → status `placed` (store `placed_order_id`) or `failed`. Reject if expired. Audit `TRADE_APPROVED` / `TRADE_PLACED`. |
| `/api/brokerage/trades/[id]/decline` | POST | Mark `declined`. |
| `/api/brokerage/trades` | POST | **Internal** (service-token guarded, not customer session) — create a pending approval from a bot signal: runs `getOrderImpact` for preview + `tradeId`, sets `expires_at`, notifies the customer. This is the seam the scanner/AlphaGEX calls. |

Public allowlist additions in `src/lib/auth/access.ts`: `/api/brokerage/webhook` (secret-verified),
`/api/brokerage/callback` (reached mid-portal; it sets the step then redirects).

## 7. Frontend

- **`/onboarding/brokerage`** — explains the connection (their account, their money, per-trade
  approval), a **Connect your brokerage** button → POST `/api/brokerage/connect` → redirect to
  `redirectURI`; plus **Skip for now** → `/onboarding/complete`. Full-bleed (Shell `isStandalone`
  already covers `/onboarding/*`).
- **Approvals UI** (post-onboarding, e.g. `/account/trades` or a dashboard panel) — lists pending
  `trade_approvals` with the preview (symbol, action, units, **estimated fees** from
  `getOrderImpact`) and **Approve / Decline** buttons. This is the compliance-critical surface:
  every real order passes through an explicit human Approve here.

## 8. Testing (TDD)

Pure, unit-tested (no I/O), per the repo's helper-extraction pattern:
- `onboarding-route.ts` — updated mapping (`risk_assessed → /onboarding/brokerage`,
  `brokerage_connected → /onboarding/complete`). Extend existing test.
- `src/lib/brokerage/approval.ts` — pure approval state machine
  `decideApproval({ status, now, expiresAt })` → `'place' | 'expired' | 'invalid'`; preview/fee
  formatting. Full unit coverage.
- `src/lib/crypto/secret-box.ts` — encrypt/decrypt round-trip for `userSecret`.
Routes verified by `npx next build` + manual SnapTrade **sandbox** run. Keep to touched test files.

## 9. Operational steps (operator — not done by code)

1. **Sign up SnapTrade** (Free tier is fine for build/test: 1 connected user, trading included) →
   obtain `clientId` + `consumerKey`.
2. Set on the IronForge webapp service (credential env vars — applied only on explicit go-ahead,
   triggers redeploy): `SNAPTRADE_CLIENT_ID`, `SNAPTRADE_CONSUMER_KEY`, `SNAPTRADE_WEBHOOK_SECRET`,
   `SNAPTRADE_SECRET_KEY` (32-byte key for AES-GCM).
3. In the SnapTrade dashboard, configure the **webhook URL** (`/api/brokerage/webhook`) and the
   **customRedirect** return URL (`/api/brokerage/callback`).
4. Build entirely against the **sandbox**; do not flip to live/paid until the §2 compliance gate
   is cleared.

Until step 2, all `/api/brokerage/*` routes return a clean 503 (config guard), UI shows
"connection unavailable," and `next build` + tests still pass.

## 10. Out of scope (fast-follow)

- Hands-off / discretionary auto-trading (RIA-gated).
- Live bot-signal → approval fan-out wiring (which customers get which bot's signals, sizing in a
  real account, fractional handling). v1 builds the seam + sandbox placement only.
- Billing/payment onboarding step.
- Multi-account selection UX, position-reconciliation dashboard, reconnect-on-broken nudges beyond
  the webhook status flip.

## 11. Acceptance criteria (v1)

1. `nextRouteForOnboarding` routes `risk_assessed → /onboarding/brokerage` and
   `brokerage_connected → /onboarding/complete`; unit tests pass.
2. `/onboarding/brokerage` renders, is guarded, and offers Connect + Skip.
3. POST `/api/brokerage/connect` registers a SnapTrade user (sandbox), stores an **encrypted**
   `userSecret`, and returns a portal `redirectURI`.
4. Returning via `/api/brokerage/callback` persists an `active` `brokerage_connections` row, sets
   `brokerage_connected=true`, advances the step, and writes `BROKERAGE_CONNECTED`.
5. A pending `trade_approvals` row can be created (internal route, sandbox) and **only** results in
   a placed order after an explicit customer Approve; expired approvals cannot be placed.
6. No code path places an order without a corresponding `approved` approval (compliance invariant).
7. Missing SnapTrade env vars degrade to 503; `npx next build` green.
8. `userSecret`/`consumerKey` never logged or returned to the client.

## 12. Open questions

- **userSecret encryption:** confirm AES-GCM + `SNAPTRADE_SECRET_KEY` is acceptable vs a managed
  KMS. (Recommend the env-key AES for v1; revisit at scale.)
- **Signal → customer mapping:** does a customer's `recommended_bot` (from risk assessment)
  determine which bot's signals they get approval requests for? Assume yes for the fast-follow.
- **Paper → real:** IronForge bots are paper today. Confirm the intended path for producing real
  orders (translate paper IC legs to the customer's broker, or a simplified single-leg/equity
  signal first?). Affects the `trade_approvals` shape for options vs equities.
- **Fractional/options support per broker** via SnapTrade (Robinhood options support varies).
```
