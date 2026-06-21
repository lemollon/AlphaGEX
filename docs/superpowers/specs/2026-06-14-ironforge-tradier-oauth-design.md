# IronForge Brokerage — Tradier (direct OAuth) as a second provider — Design

**Date:** 2026-06-14
**Status:** Proposed.
**Builds on:** the SnapTrade brokerage-connection feature (Phases 1–3, live on staging).
**Why:** SnapTrade does **not** support Tradier (confirmed — Tradier is absent from the portal's
broker list). Tastytrade is covered by SnapTrade; Tradier requires its **own OAuth** integration.

## 1. Goal
Let a customer connect **their own Tradier account** (Model A, per-trade approval) alongside the
existing SnapTrade path, so the product supports **Tradier + Tastytrade** (+ everything else
SnapTrade offers). One unified approval/placement surface; provider chosen per connection.

## 2. Key decision — make connections multi-provider
Today `brokerage_connections` and `trade_approvals` implicitly assume SnapTrade. Add a
`provider` discriminator and branch the connect/place logic on it.

```sql
ALTER TABLE brokerage_connections ADD COLUMN IF NOT EXISTS provider TEXT NOT NULL DEFAULT 'snaptrade';
ALTER TABLE trade_approvals       ADD COLUMN IF NOT EXISTS provider TEXT NOT NULL DEFAULT 'snaptrade';

-- Tradier OAuth tokens (encrypted at rest, reuse @/lib/crypto/secret-box):
ALTER TABLE users ADD COLUMN IF NOT EXISTS tradier_access_token  TEXT;  -- AES-GCM ciphertext
ALTER TABLE users ADD COLUMN IF NOT EXISTS tradier_refresh_token TEXT;  -- AES-GCM ciphertext (if issued)
ALTER TABLE users ADD COLUMN IF NOT EXISTS tradier_token_expires_at TIMESTAMPTZ;
```

`provider ∈ { 'snaptrade', 'tradier' }`. SnapTrade rows keep `snaptrade_trade_id`; Tradier rows
leave it null and carry the raw order params (already on `trade_approvals`: symbol/action/units/
order_type), since Tradier places from params, not a pre-minted trade id.

## 3. Tradier OAuth flow (new — `src/lib/tradier-oauth.ts`)
Config-guarded like `snaptrade.ts` (`isTradierOAuthConfigured()` → 503 when unset). New env vars:
- `TRADIER_OAUTH_CLIENT_ID`, `TRADIER_OAUTH_CLIENT_SECRET` — **distinct** from the existing
  `TRADIER_API_KEY` (which is IronForge's own market-data/bot key, not a customer OAuth app).

Endpoints (verify against Tradier docs at build time; prod base `https://api.tradier.com`):
| Step | Call |
|---|---|
| Authorize (redirect user) | `GET /v1/oauth/authorize?client_id=…&scope=read,trade&state=…` |
| Token exchange | `POST /v1/oauth/accesstoken` (code → access_token [+ refresh, expiry]) |
| List accounts | `GET /v1/user/profile` (Bearer token) |
| Positions / balances | `GET /v1/accounts/{id}/positions` · `/balances` |
| **Order preview** | `POST /v1/accounts/{id}/orders` with `preview=true` (fees/margin) |
| **Place order** | `POST /v1/accounts/{id}/orders` (class=equity/option, side, quantity, type, duration) |

`state` is a signed nonce tying the callback to the customer (reuse the onboarding-token signer or
a short-lived signed value) so the callback can't be forged.

## 4. Routes (parallel to the SnapTrade ones)
- `POST /api/onboarding/brokerage/tradier/connect` — build the Tradier authorize URL with a signed
  `state`, return `{ redirectURI }`. (Same client contract as the SnapTrade connect, so the
  `/onboarding/brokerage` page can offer "Connect Tradier" vs "Connect another broker".)
- `GET /api/onboarding/brokerage/tradier/callback` — verify `state`, exchange `code` → tokens,
  encrypt + store, fetch `user/profile` → upsert `brokerage_connections` (provider='tradier',
  account_id from profile), set `brokerage_connected`, advance step, audit, **Attio sync** (reuse
  `syncBrokerageConnectionToAttio`), redirect to `/onboarding/complete`.
- Token refresh helper (if Tradier issues refresh tokens / short-lived access) — refresh on demand
  before a placement when `tradier_token_expires_at` has passed.

## 5. Provider-agnostic placement (the compliance-critical path stays single)
Refactor the approve route to dispatch on `trade_approvals.provider`:
- `snaptrade` → existing `placeOrder({ tradeId })`.
- `tradier`  → `POST /v1/accounts/{id}/orders` with the stored params (decrypt token first).
The `decideApproval()` gate, ownership check, audit, and "no place without an explicit unexpired
approval" invariant are **unchanged** — only the final placement call differs. Likewise the
internal create-approval route runs the provider's preview (SnapTrade `getOrderImpact` vs Tradier
`preview=true`) to populate `preview` + sets `provider`.

## 6. UI
`/onboarding/brokerage` gains a provider choice (e.g. "Connect via SnapTrade" for Tastytrade/others,
"Connect Tradier"). `/account/trades` is unchanged (provider is invisible to the approver).

## 7. Testing
- Pure: extend `decideApproval` coverage (unchanged); add a `placement-dispatch` unit (chooses the
  right placer by provider) so the branch is tested without network.
- Token crypto: reuse `secret-box` tests.
- Routes: `next build` + a Tradier **sandbox** run (`https://sandbox.tradier.com`) using a sandbox
  OAuth app — Tradier's sandbox is the safe place-order test for this provider (analogous to Alpaca
  Paper for SnapTrade).

## 8. Operational (operator)
1. Register a **Tradier OAuth application** (developer dashboard) → `client_id` + `client_secret`;
   set the redirect URL to `…/api/onboarding/brokerage/tradier/callback`.
2. Set `TRADIER_OAUTH_CLIENT_ID` / `TRADIER_OAUTH_CLIENT_SECRET` (credential env vars; staging first,
   pointed at Tradier **sandbox** for testing).
3. Same §2 compliance gate as SnapTrade applies (per-trade approval; RIA only for hands-off auto).

## 9. Out of scope (fast-follow)
Options multi-leg via Tradier; streaming; auto-refresh cron; consolidating the two connect UIs into
one broker picker beyond the basic choice.

## 10. Acceptance criteria
1. `provider` column on connections + approvals; SnapTrade path unchanged (defaults to 'snaptrade').
2. Tradier connect → authorize → callback exchanges code, stores **encrypted** tokens, upserts a
   `provider='tradier'` connection, advances onboarding, syncs Attio.
3. Approve route places via Tradier for tradier rows, via SnapTrade for snaptrade rows; the
   "no place without approval" invariant holds for both.
4. Tradier creds unset → 503 degrade; `next build` green; placement-dispatch unit tested.
