# IronForge Brokerage Connection — Implementation Plan

**Spec:** `docs/superpowers/specs/2026-06-14-ironforge-brokerage-connection-design.md`
**Working directory:** `ironforge/webapp/`
**Verification:** `npx vitest run <file>` (pure helpers), `npx next build` (routes/pages).
**Compliance invariant (every task respects it):** no code path places a real order without an
explicit, unexpired customer approval. Full hands-off auto-trading is OUT OF SCOPE (RIA-gated).

---

## Phase 1 — Keys-free spine ✅ DONE (built + verified 2026-06-14)

Everything here builds and passes with NO SnapTrade keys (routes degrade to 503 once added).

- [x] **Onboarding resolver** — `src/lib/auth/onboarding-route.ts`: `risk_assessed → /onboarding/brokerage`,
      `brokerage_connected → /onboarding/complete`. Test updated (`onboarding-route.test.ts`).
- [x] **Approval state machine (pure)** — `src/lib/brokerage/approval.ts` (`decideApproval`, `isPlaceable`)
      + `__tests__/approval.test.ts` (expiry boundary, idempotent-guard).
- [x] **Secret box (AES-256-GCM)** — `src/lib/crypto/secret-box.ts` (`encryptSecret`/`decryptSecret`/
      `loadSecretKey`) + tests (round-trip, tamper-detect, hex/base64 key).
- [x] **SnapTrade client guard** — `src/lib/snaptrade.ts` (`isSnapTradeConfigured`, `getSnapTrade`,
      `SnapTradeNotConfiguredError`). `snaptrade-typescript-sdk` installed.
- [x] **Schema** — `customers-db.ts INIT_DDL`: `users` cols (`snaptrade_user_id`,
      `snaptrade_user_secret`, `brokerage_connected`) + `brokerage_connections` + `trade_approvals`.
- [x] **Onboarding page** — `src/app/onboarding/brokerage/page.tsx` (guarded) +
      `BrokerageConnectClient.tsx` (Connect → portal redirect, Skip → /onboarding/complete).
- [x] **Completion copy** — dropped now-stale "brokerage connection … coming soon" line.
- [x] **Verified:** 16/16 unit tests pass; `npx next build` green; `/onboarding/brokerage` in route table.

---

## Phase 2 — SnapTrade routes ✅ DONE (built + verified 2026-06-14)

Each route mirrors the existing `/api/auth/*` patterns: `runtime='nodejs'`, `isSnapTradeConfigured()`
+ `isCustomersDbConfigured()` guards → clean 503, audit on success, never log `consumerKey`/`userSecret`.
SDK call shapes verified against the installed `snaptrade-typescript-sdk`. **Placement note:** `connect`
+ `callback` live under `/api/onboarding/brokerage/` so they inherit the middleware onboarding-cookie
gating (same as `/api/onboarding/risk-assessment`); identity resolves from onboarding cookie OR
customer session via `src/lib/brokerage/identity.ts`.

- [x] **`POST /api/onboarding/brokerage/connect`** — idempotent `registerSnapTradeUser({ userId: users.id })`,
      encrypt + store `userSecret`, `loginSnapTradeUser({ connectionType:'trade', customRedirect })` → `{ redirectURI }`.
- [x] **`GET /api/onboarding/brokerage/callback`** — verify via `listUserAccounts`; re-sync
      `brokerage_connections` (`active`); set `brokerage_connected=true`, `onboarding_step='brokerage_connected'`;
      audit `BROKERAGE_CONNECTED`; redirect `/onboarding/complete` (or back to the step if incomplete).
- [x] **`POST /api/brokerage/webhook`** — no session; verify `SNAPTRADE_WEBHOOK_SECRET`;
      `CONNECTION_ADDED/UPDATED/FIXED→active`, `CONNECTION_BROKEN→disabled`, `*_DELETED/REMOVED→removed`,
      `ACCOUNT_HOLDINGS_UPDATED→touch last_synced_at`; clears `brokerage_connected` when none active. Allowlisted.
- [x] **`GET /api/brokerage/accounts`** — customer-session-guarded (allowlisted, self-enforced); trimmed projection.
- [x] **`DELETE /api/brokerage/connection`** — `removeBrokerageAuthorization` + mark rows `removed` + recompute flag.
- [x] **Verified:** `npx next build` green, all 5 routes in the table; 16/16 unit tests still pass.
- [x] **Sandbox smoke test PASSED (2026-06-14)** with the free-tier test keys: `apiStatus.online=true`;
      `registerSnapTradeUser` → `loginSnapTradeUser({connectionType:'trade', customRedirect})` returned a
      real Connection Portal `redirectURI` with our `/api/onboarding/brokerage/callback` embedded;
      `deleteSnapTradeUser` cleanup OK. Our exact connect-route call path is validated against live SnapTrade.

**Local dev config:** `ironforge/webapp/.env.local` (gitignored) holds the TEST `SNAPTRADE_CLIENT_ID`
(`IRONFORGE-TECHNOLOGIES-LLC-TEST-KYCJZ`) + `SNAPTRADE_CONSUMER_KEY` + a generated 32-byte
`SNAPTRADE_SECRET_KEY`. `SNAPTRADE_WEBHOOK_SECRET` is still a placeholder — set it to match the value
configured in the SnapTrade dashboard.

**Free-tier limits (sufficient for all of Phase 2/3 dev):** up to 5 connected users (sandbox), testing only.
**Webhook already configured** in SnapTrade: `https://ironforge.trade/api/brokerage/webhook`.

## Phase 3 — Per-trade approval flow ✅ DONE (built + verified 2026-06-14)

The compliance-critical surface. Order placement lives in exactly ONE route, gated by
`decideApproval()`; nothing places without an explicit, unexpired customer approval.

- [x] **`POST /api/brokerage/trades`** (internal, **service-token** guarded via `hasValidServiceToken`) —
      resolves ticker → universal symbol (`symbolSearchUserAccount`), runs `getOrderImpact` for the
      preview + `tradeId`, inserts a `pending` row with a 5-min TTL, audits `TRADE_APPROVAL_CREATED`,
      and **notifies the customer by email** (`sendTradeApprovalEmail`, best-effort). The seam the
      scanner / AlphaGEX calls.
- [x] **`GET /api/brokerage/trades`** — customer-session list of recent approvals.
- [x] **`POST /api/brokerage/trades/[id]/approve`** — ownership-checked; `decideApproval()` gate;
      on `'place'` → `placeOrder({ tradeId })` → `placed`(+order id)/`failed`(+error); `'expired'`/`'invalid'`
      refuse. Audits `TRADE_PLACED`.
- [x] **`POST /api/brokerage/trades/[id]/decline`** — marks `declined` (idempotent). Audits `TRADE_DECLINED`.
- [x] **Approvals UI** — `/account/trades` + client: lists pending approvals with Approve/Decline;
      middleware-open page, data API self-guards the customer session (renders sign-in prompt if 401).
- [x] Helper `src/lib/brokerage/snaptrade-user.ts` (load + decrypt creds); access.ts now prefix-allows
      `/api/brokerage/*` (self-guarded) + the `/account/trades` page; Shell standalone for it.
- [x] **Verified:** `npx next build` green (all 3 trade routes + page in the table); 16/16 unit tests pass.
      Runtime (place order) needs a sandbox-connected account → exercise during the live smoke test.

## Phase 4 — Operator + go-live (gated by §2 compliance gate)

- [x] Sign up SnapTrade (Free) → TEST `clientId` + `consumerKey` obtained (in `.env.local`).
- [ ] Set PRODUCTION env vars on the Render webapp (explicit go-ahead; triggers redeploy):
      `SNAPTRADE_CLIENT_ID`, `SNAPTRADE_CONSUMER_KEY`, `SNAPTRADE_WEBHOOK_SECRET`, `SNAPTRADE_SECRET_KEY`.
- [x] Webhook URL configured in dashboard: `https://ironforge.trade/api/brokerage/webhook`.
      `customRedirect` is passed per-call (`/api/onboarding/brokerage/callback`) — no dashboard field needed.
- [ ] Full sandbox run (connect → approve → place) once Phase 3 ships.
- [ ] **Production access application** is partially saved in SnapTrade (steps 1–5 done). To go live:
      fill **Tax ID / EIN on step 3** (left blank), complete **step 6** (PAYGO plan + payment method),
      hit **Confirm**. No charges until production access is explicitly enabled. Do NOT submit until the
      §2 compliance gate is cleared (SnapTrade trade-enabled review needs a working app to inspect + the
      per-trade-approval flow live; securities-counsel sign-off).

## Notifications ✅ DONE (2026-06-14)
- [x] `sendTradeApprovalEmail` (Resend, mirrors verification/reset emails) + wired into the create
      route (best-effort, non-blocking). Unit-tested (`trade-approval-email.test.ts`, 3 tests).

## Local end-to-end test
- See **`2026-06-14-ironforge-brokerage-local-e2e-runbook.md`** — full connect → approve → place
  loop against SnapTrade sandbox. Requires a throwaway Postgres + a PAPER broker (e.g. Alpaca Paper)
  in the portal. Not runnable from CI (needs human-in-portal + a reachable DB); `placeOrder` is the
  one path verified only by this runbook.

## Out of scope (fast-follow)
Live bot-signal → approval fan-out wiring; hands-off auto-trading (RIA); billing step; multi-account UX;
reconciliation dashboard.
