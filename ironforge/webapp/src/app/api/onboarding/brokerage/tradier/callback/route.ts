import { NextRequest, NextResponse } from 'next/server'
import {
  isTradierOAuthConfigured,
  verifyState,
  exchangeCodeForToken,
  getProfileAccounts,
} from '@/lib/tradier-oauth'
import { encryptSecret } from '@/lib/crypto/secret-box'
import { isCustomersDbConfigured, customerQuery, customerExecute, customerTransaction } from '@/lib/customers-db'
import { syncBrokerageConnectionToAttio } from '@/lib/attio'

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
  const brokerageStep = new URL('/onboarding/brokerage', req.nextUrl.origin)
  const complete = new URL('/onboarding/complete', req.nextUrl.origin)

  const code = req.nextUrl.searchParams.get('code')
  const uid = verifyState(req.nextUrl.searchParams.get('state'))
  if (!code || !uid || !isTradierOAuthConfigured() || !isCustomersDbConfigured()) {
    brokerageStep.searchParams.set('error', '1')
    return NextResponse.redirect(brokerageStep)
  }

  try {
    const rows = await customerQuery<UserRow>(
      `SELECT id, email, first_name, last_name, phone, state FROM users WHERE id = $1 LIMIT 1`,
      [uid],
    )
    const user = rows[0]
    if (!user) {
      brokerageStep.searchParams.set('error', '1')
      return NextResponse.redirect(brokerageStep)
    }

    const token = await exchangeCodeForToken(code)
    const accounts = await getProfileAccounts(token.accessToken)

    if (accounts.length === 0) {
      brokerageStep.searchParams.set('incomplete', '1')
      return NextResponse.redirect(brokerageStep)
    }

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
      await run(`DELETE FROM brokerage_connections WHERE user_id = $1 AND provider = 'tradier'`, [user.id])
      for (const a of accounts) {
        await run(
          `INSERT INTO brokerage_connections
             (user_id, provider, account_id, account_name, brokerage_slug, status, last_synced_at)
           VALUES ($1, 'tradier', $2, $3, 'Tradier', 'active', now())`,
          [user.id, a.account_id, a.name ?? 'Tradier'],
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

    return NextResponse.redirect(complete)
  } catch (e) {
    console.error('[tradier/callback] failed:', e)
    brokerageStep.searchParams.set('error', '1')
    return NextResponse.redirect(brokerageStep)
  }
}
