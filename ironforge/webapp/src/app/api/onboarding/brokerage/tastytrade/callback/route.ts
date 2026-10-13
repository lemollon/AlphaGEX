import { NextRequest, NextResponse } from 'next/server'
import { publicOrigin } from '@/lib/public-origin'
import {
  isTastytradeOAuthConfigured,
  exchangeCodeForToken,
  getProfileAccounts,
  getAccountOptionsLevel,
  getAccountOptionBuyingPower,
} from '@/lib/tastytrade-oauth'
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
 * tastytrade OAuth return. Mirrors onboarding/brokerage/tradier/callback/route.ts field for
 * field — verifies the signed state, exchanges the code for tokens (stored ENCRYPTED), lists the
 * user's tastytrade accounts, syncs provider='tastytrade' connections, advances onboarding,
 * mirrors to Attio, then redirects into the funnel.
 *
 * No bot trades a tastytrade account directly today (unlike the Tradier lane, which guards
 * against double-trading 6YB71371) — so knownBotAccountNumbers is [] below, which eligibility.ts
 * treats as "skip the check", not "nothing is bot-traded".
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

  const oauth = isCustomersDbConfigured()
    ? await consumeOAuthState(req.nextUrl.searchParams.get('state'))
    : null
  const uid = oauth?.userId ?? null

  const fromEnroll = oauth?.returnTo === 'enroll'
  const brokerageStep = new URL(fromEnroll ? '/enroll/broker' : '/onboarding/brokerage', publicOrigin(req))
  const complete = fromEnroll
    ? new URL('/enroll/broker?connected=1', publicOrigin(req))
    : new URL('/onboarding/complete', publicOrigin(req))

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

  if (!code || !uid || !isTastytradeOAuthConfigured() || !isCustomersDbConfigured()) {
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

    // MUST match the redirect_uri sent to /auth.html in the connect route exactly — tastytrade's
    // token endpoint (unlike Tradier's) requires it on both legs.
    const redirectUri = `${publicOrigin(req)}/api/onboarding/brokerage/tastytrade/callback`
    const token = await exchangeCodeForToken(code, redirectUri, oauth?.codeVerifier)
    const accounts = await getProfileAccounts(token.accessToken)

    const optionsLevels = new Map<string, number | null>()
    const balances = new Map<string, number | null>()
    for (const a of accounts) {
      optionsLevels.set(a.account_id, await getAccountOptionsLevel(token.accessToken, a.account_id))
      balances.set(a.account_id, await getAccountOptionBuyingPower(token.accessToken, a.account_id))
    }

    if (accounts.length === 0) {
      return NextResponse.redirect(doneUrl('incomplete'))
    }

    const createdConnections: Array<{ id: string }> = []

    await customerTransaction(async (run) => {
      await run(
        `UPDATE users
            SET tastytrade_access_token = $2, tastytrade_refresh_token = $3, tastytrade_token_expires_at = $4,
                updated_at = now()
          WHERE id = $1`,
        [
          user.id,
          encryptSecret(token.accessToken),
          token.refreshToken ? encryptSecret(token.refreshToken) : null,
          token.expiresAt ?? null,
        ],
      )
      await run(
        `DELETE FROM broker_accounts WHERE connection_id IN
           (SELECT id FROM brokerage_connections WHERE user_id = $1 AND provider = 'tastytrade')`,
        [user.id],
      )
      await run(`DELETE FROM brokerage_connections WHERE user_id = $1 AND provider = 'tastytrade'`, [user.id])
      for (const a of accounts) {
        const inserted = (await run(
          `INSERT INTO brokerage_connections
             (user_id, provider, account_id, account_name, brokerage_slug, broker_code, status, last_synced_at)
           VALUES ($1, 'tastytrade', $2, $3, 'tastytrade', 'tastytrade', 'active', now())
           RETURNING id`,
          [user.id, a.account_id, a.name ?? 'tastytrade'],
        )) as unknown as Array<{ id: string }>
        const connectionId = inserted?.[0]?.id
        if (!connectionId) continue
        createdConnections.push({ id: connectionId })

        const verdict = evaluateAccountEligibility({
          externalRef: a.account_id,
          accountType: a.classification ?? null,
          optionsLevel: optionsLevels.get(a.account_id) ?? null,
          status: a.status ?? 'active',
          buyingPower: balances.get(a.account_id) ?? null,
          brokerSlug: 'TASTYTRADE',
          displayMask: maskAccountNumber(a.account_id),
          knownBotAccountNumbers: [],
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
            optionsLevels.get(a.account_id) ?? null,
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
      [user.id, JSON.stringify({ provider: 'tastytrade', accounts: accounts.length })],
    ).catch(() => {})

    for (const conn of createdConnections) {
      await enqueueCrmEvent({
        eventId: `brokerage_connected:${conn.id}`,
        eventType: 'crm.brokerage_connected',
        userId: user.id,
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
        { brokerage: 'tastytrade', accountCount: accounts.length, connectedAt: new Date().toISOString() },
      )
      if (attioRes.synced) {
        await customerExecute(
          `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'ATTIO_BROKERAGE_SYNCED', $2)`,
          [user.id, JSON.stringify({ record_id: attioRes.recordId ?? null, provider: 'tastytrade' })],
        ).catch(() => {})
      } else if (!attioRes.skipped) {
        await customerExecute(
          `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'ATTIO_BROKERAGE_SYNC_FAILED', $2)`,
          [user.id, JSON.stringify({ error: (attioRes.error ?? '').slice(0, 200) })],
        ).catch(() => {})
      }
    } catch (e) {
      console.error('[tastytrade/callback] attio sync threw:', e)
    }

    return NextResponse.redirect(doneUrl('success'))
  } catch (e) {
    console.error('[tastytrade/callback] failed:', e)
    brokerageStep.searchParams.set('error', '1')
    return NextResponse.redirect(brokerageStep)
  }
}
