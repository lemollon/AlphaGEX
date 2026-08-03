import { NextRequest, NextResponse } from 'next/server'
import { publicOrigin } from '@/lib/public-origin'
import {
  isTradierOAuthConfigured,
  exchangeCodeForToken,
  getProfileAccounts,
  getAccountOptionBuyingPower,
} from '@/lib/tradier-oauth'
import { consumeOAuthState } from '@/lib/enrollment/oauth-state'
import { billingReturn } from '@/lib/mobile/deep-link'
import { evaluateAccountEligibility, maskAccountNumber } from '@/lib/enrollment/eligibility'
import { encryptSecret } from '@/lib/crypto/secret-box'
import { isCustomersDbConfigured, customerQuery, customerExecute, customerTransaction } from '@/lib/customers-db'
import { syncBrokerageConnectionToAttio } from '@/lib/attio'
import { enqueueCrmEvent } from '@/lib/crm/outbox'
import { mapBrokerageStatusToCrm } from '@/lib/crm/brokerage-status'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Tradier OAuth return. Verifies the signed state (→ customer id), exchanges the code for tokens
 * (stored ENCRYPTED), lists the user's Tradier accounts, syncs provider='tradier' connections,
 * advances onboarding, mirrors to Attio, then redirects into the funnel.
 */
interface UserRow {
  id: string
  email: string
  first_name: string
  last_name: string
  phone: string
  state: string | null
}

export async function GET(req: NextRequest) {
  const code = req.nextUrl.searchParams.get('code')

  // ONE-TIME state (§8). consumeOAuthState marks it used inside the same statement
  // that checks it, so a replayed callback finds nothing and gets the same safe
  // failure as a forged one — "Replayed or mismatched state returns a safe failure"
  // (§4). It also carries the PKCE verifier, which never left the server.
  const oauth = isCustomersDbConfigured()
    ? await consumeOAuthState(req.nextUrl.searchParams.get('state'))
    : null
  const uid = oauth?.userId ?? null

  // Land back on the surface that initiated the round-trip. return_to is an
  // allowlisted literal resolved to a fixed route — never a caller-supplied URL.
  const fromEnroll = oauth?.returnTo === 'enroll'
  const brokerageStep = new URL(fromEnroll ? '/enroll/broker' : '/onboarding/brokerage', publicOrigin(req))
  const complete = fromEnroll
    ? new URL('/enroll/broker?connected=1', publicOrigin(req))
    : new URL('/onboarding/complete', publicOrigin(req))

  // Mobile returns through the https bridge, which the installed app claims as a
  // Universal/App Link. `client` comes from the single-use state record minted at
  // connect — never from the request — so the return surface cannot be chosen by a
  // caller. Same treatment as the SnapTrade callback, so both providers behave
  // identically from the app's point of view.
  const client = oauth?.client ?? 'web'
  const doneUrl = (status: 'success' | 'incomplete' | 'error') =>
    client === 'mobile'
      ? new URL(billingReturn(publicOrigin(req), 'mobile', '/account/brokerage', { status }))
      : status === 'success'
        ? complete
        : (() => {
            brokerageStep.searchParams.set(status === 'incomplete' ? 'incomplete' : 'error', '1')
            return brokerageStep
          })()

  if (!code || !uid || !isTradierOAuthConfigured() || !isCustomersDbConfigured()) {
    return NextResponse.redirect(doneUrl('error'))
  }

  try {
    const rows = await customerQuery<UserRow>(
      `SELECT id, email, first_name, last_name, phone, state FROM users WHERE id = $1 LIMIT 1`,
      [uid],
    )
    const user = rows[0]
    if (!user) {
      return NextResponse.redirect(doneUrl('error'))
    }

    const token = await exchangeCodeForToken(code, oauth?.codeVerifier)
    const accounts = await getProfileAccounts(token.accessToken)

    // Buying power is not on /user/profile, and eligibility FAILS CLOSED on an unknown
    // one — without this fetch every account would be refused as ineligible.
    const balances = new Map<string, number | null>()
    for (const a of accounts) {
      balances.set(a.account_id, await getAccountOptionBuyingPower(token.accessToken, a.account_id))
    }

    if (accounts.length === 0) {
      return NextResponse.redirect(doneUrl('incomplete'))
    }

    const createdConnections: Array<{ id: string }> = []

    await customerTransaction(async (run) => {
      await run(
        `UPDATE users
            SET tradier_access_token = $2, tradier_refresh_token = $3, tradier_token_expires_at = $4,
                updated_at = now()
          WHERE id = $1`,
        [
          user.id,
          encryptSecret(token.accessToken),
          token.refreshToken ? encryptSecret(token.refreshToken) : null,
          token.expiresAt ?? null,
        ],
      )
      // Replace only this user's Tradier rows (leave any SnapTrade connection intact).
      // Children first: broker_accounts FK has no cascade, so a re-connect with account
      // rows present would otherwise fail the whole transaction (UAT-012).
      await run(
        `DELETE FROM broker_accounts WHERE connection_id IN
           (SELECT id FROM brokerage_connections WHERE user_id = $1 AND provider = 'tradier')`,
        [user.id],
      )
      await run(`DELETE FROM brokerage_connections WHERE user_id = $1 AND provider = 'tradier'`, [user.id])
      for (const a of accounts) {
        const inserted = (await run(
          `INSERT INTO brokerage_connections
             (user_id, provider, account_id, account_name, brokerage_slug, broker_code, status, last_synced_at)
           VALUES ($1, 'tradier', $2, $3, 'Tradier', 'tradier', 'active', now())
           RETURNING id`,
          [user.id, a.account_id, a.name ?? 'Tradier'],
        )) as unknown as Array<{ id: string }>
        const connectionId = inserted?.[0]?.id
        if (!connectionId) continue
        createdConnections.push({ id: connectionId })

        // Record the account with its ELIGIBILITY verdict (§3 BROKER-02). Until this
        // existed the eligibility gate had no data source at all, so the whole
        // account-selection step could never be satisfied.
        //
        // The full account number is ENCRYPTED and only the mask is stored for display
        // (§5, §8) — nothing here writes it in the clear or logs it.
        const verdict = evaluateAccountEligibility({
          externalRef: a.account_id,
          accountType: a.classification ?? null,
          optionsLevel: a.option_level ?? null,
          status: a.status ?? 'active',
          buyingPower: balances.get(a.account_id) ?? null,
        })
        await run(
          `INSERT INTO broker_accounts
             (connection_id, external_account_ref_ciphertext, display_mask, account_type,
              options_level, eligibility, ineligible_reason, buying_power_cents, checked_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, now())`,
          [
            connectionId,
            encryptSecret(a.account_id),
            maskAccountNumber(a.account_id),
            a.classification ?? null,
            a.option_level ?? null,
            verdict.eligible ? 'eligible' : 'ineligible',
            verdict.reason ?? null,
            (() => { const bp = balances.get(a.account_id); return bp == null ? null : Math.round(bp * 100) })(),
          ],
        )
      }
      await run(
        `UPDATE users
            SET brokerage_connected = TRUE, onboarding_step = 'brokerage_connected', updated_at = now()
          WHERE id = $1 AND email_verified = TRUE`,
        [user.id],
      )
    })

    await customerExecute(
      `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'BROKERAGE_CONNECTED', $2)`,
      [user.id, JSON.stringify({ provider: 'tradier', accounts: accounts.length })],
    ).catch(() => {})

    // One CRM connection record per brokerage_connections row created above — each is keyed on
    // its own immutable connection_id (events.ts brokerageConnection()).
    for (const conn of createdConnections) {
      await enqueueCrmEvent({
        eventId: `brokerage_connected:${conn.id}`,
        eventType: 'crm.brokerage_connected',
        userId: user.id,
        correlationId: conn.id,
        payload: {
          email: user.email,
          firstName: user.first_name,
          lastName: user.last_name,
          ironforgeUserId: user.id,
          connectionId: conn.id,
          connectionStatus: mapBrokerageStatusToCrm('active').connectionStatus,
          lastAttemptAt: new Date().toISOString(),
          reauthorizationRequired: false,
        },
      })
    }

    try {
      const attioRes = await syncBrokerageConnectionToAttio(
        {
          firstName: user.first_name,
          lastName: user.last_name,
          email: user.email,
          phone: user.phone,
          state: user.state || undefined,
        },
        { brokerage: 'Tradier', accountCount: accounts.length, connectedAt: new Date().toISOString() },
      )
      if (attioRes.synced) {
        await customerExecute(
          `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'ATTIO_BROKERAGE_SYNCED', $2)`,
          [user.id, JSON.stringify({ record_id: attioRes.recordId ?? null, provider: 'tradier' })],
        ).catch(() => {})
      } else if (!attioRes.skipped) {
        await customerExecute(
          `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'ATTIO_BROKERAGE_SYNC_FAILED', $2)`,
          [user.id, JSON.stringify({ error: (attioRes.error ?? '').slice(0, 200) })],
        ).catch(() => {})
      }
    } catch (e) {
      console.error('[tradier/callback] attio sync threw:', e)
    }

    return NextResponse.redirect(doneUrl('success'))
  } catch (e) {
    console.error('[tradier/callback] failed:', e)
    brokerageStep.searchParams.set('error', '1')
    return NextResponse.redirect(brokerageStep)
  }
}
