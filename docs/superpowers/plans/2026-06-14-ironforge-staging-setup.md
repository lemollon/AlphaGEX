# IronForge Permanent Staging Environment — Setup Checklist

**Purpose:** a permanent, reusable staging deploy of the IronForge webapp to test the brokerage
flow (and future features) against SnapTrade's sandbox, with a public https URL (needed for the
SnapTrade Connection Portal callback + webhooks, which localhost can't provide cleanly).

**Shape:** **one** staging Postgres (serves both `DATABASE_URL` and `CUSTOMERS_DATABASE_URL` —
bot tables `flame_*`/… and customer tables `users`/`brokerage_connections`/… don't collide) + **one**
Render web service deploying the brokerage branch. Separate from production; never shares its DB.

> Secrets for the env vars below were generated and handed over in chat — paste those values.
> Do NOT commit them. This file uses placeholders only.

---

## Step A — Staging Postgres (Render)
1. Render → **New** → **Postgres**. Name `ironforge-staging-db`, region **Oregon** (match the service).
2. Plan: **basic_256mb** (paid) for a *permanent* env — the **free** plan expires (~30 days). Free is
   fine if you only need it short-term.
3. After creation, copy both the **Internal** connection string (for the service) and the **External**
   one (for running SQL / the runbook curl from your laptop).

## Step B — Staging web service (Render)
Render → **New** → **Web Service** → connect the AlphaGEX repo. Settings (mirror prod
`ironforge/render.yaml`):

| Setting | Value |
|---|---|
| Name | `ironforge-dashboard-staging` |
| Branch | `claude/ironforge-brokerage-connection` (or a long-lived `staging` branch) |
| Root directory | `ironforge/webapp` |
| Runtime | Node |
| Build command | `npm install && npm run build && cp -r .next/static .next/standalone/.next/static && cp -r public .next/standalone/public` |
| Start command | `node start.js` |
| Health check path | `/api/health` |
| Plan | Starter (paid) for always-on, or Free (sleeps) |

**Environment variables** (Add from the dashboard):

| Key | Value |
|---|---|
| `DATABASE_URL` | staging PG **internal** connection string |
| `CUSTOMERS_DATABASE_URL` | **same** staging PG internal connection string |
| `SNAPTRADE_CLIENT_ID` | `IRONFORGE-TECHNOLOGIES-LLC-TEST-KYCJZ` (test) |
| `SNAPTRADE_CONSUMER_KEY` | the test consumer key |
| `SNAPTRADE_SECRET_KEY` | generated (from chat) |
| `SNAPTRADE_WEBHOOK_SECRET` | generated (from chat) — also set in SnapTrade dashboard (Step C) |
| `IRONFORGE_SESSION_SECRET` | generated (from chat) |
| `IRONFORGE_SERVICE_TOKEN` | generated (from chat) — for the internal create-approval route |
| `NODE_ENV` | `production` |
| `ALPHAGEX_API_BASE` | `https://alphagex-api.onrender.com` |
| `TRADIER_API_KEY`, `TRADIER_SANDBOX_KEY_USER/MATT/LOGAN` | optional — reuse existing; only the paper scanner uses them (harmless if absent) |
| `RESEND_API_KEY`, `EMAIL_FROM` | optional — set to actually receive the approval/verification emails |
| `IRONFORGE_PUBLIC_MODE` | leave **unset** (login wall enforced; signup/login/onboarding still reachable) |

Deploy. Health check `/<service>/api/health` should go green. Note the public URL, e.g.
`https://ironforge-dashboard-staging.onrender.com`.

## Step C — SnapTrade dashboard (webhook for staging)
- `customRedirect` (connection callback) is passed **per-call** from the request origin, so the
  staging URL is used automatically — no dashboard change needed for connect/callback.
- To test **webhooks** on staging, add a webhook endpoint in SnapTrade →
  `https://<staging-url>/api/brokerage/webhook` with the **same** `SNAPTRADE_WEBHOOK_SECRET` you set
  above. (Optional — connect/approve/place work without it.)

## Step D — Run the brokerage E2E against staging
1. **Create a test customer:** open `https://<staging-url>/signup`, sign up.
2. **Mark it verified** (skips email; fine for a staging DB) — run against the staging **external** URL:
   ```sql
   UPDATE users
      SET email_verified = TRUE, account_status = 'email_verified',
          onboarding_step = 'email_verified', updated_at = now()
    WHERE email = '<your test email>';
   ```
   (Or, if `RESEND_*` is set, just click the verification email instead.)
3. Sign in at `/login` → you reach onboarding → go to `/onboarding/brokerage`.
4. Follow **`2026-06-14-ironforge-brokerage-local-e2e-runbook.md`** from Step 5 onward (connect a
   **PAPER** broker e.g. Alpaca Paper → create an approval with the service token → Approve at
   `/account/trades` → confirm `placed`). Use `https://<staging-url>` as the base URL and the
   `IRONFORGE_SERVICE_TOKEN` value for the internal `POST /api/brokerage/trades` call.

## Notes
- The webapp also runs the FLAME/SPARK/INFERNO **paper** scanner on boot — harmless on staging; it
  only needs `DATABASE_URL`. No real trades.
- This staging env is reusable for every future IronForge feature: point the service's branch at
  whatever you're testing, or keep a `staging` branch and merge into it before `main`.
- Production is unaffected — it keeps using the live `ironforge-customers` DB and its own env vars.
