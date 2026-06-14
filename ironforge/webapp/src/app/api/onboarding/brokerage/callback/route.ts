import { NextRequest, NextResponse } from 'next/server'
import { resolveCustomerUserId } from '@/lib/brokerage/identity'
import { getSnapTrade, isSnapTradeConfigured } from '@/lib/snaptrade'
import { decryptSecret } from '@/lib/crypto/secret-box'
import { isCustomersDbConfigured, customerQuery, customerExecute, customerTransaction } from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Return target from SnapTrade's Connection Portal (customRedirect). Verifies the connection by
 * listing the user's accounts, syncs them into brokerage_connections, flips the user to
 * brokerage_connected, advances onboarding_step, then redirects into the funnel. If the user
 * backed out without connecting, sends them back to the brokerage step (skippable).
 */

interface UserRow {
  id: string
  snaptrade_user_id: string | null
  snaptrade_user_secret: string | null
}

export async function GET(req: NextRequest) {
  const brokerageStep = new URL('/onboarding/brokerage', req.nextUrl.origin)
  const complete = new URL('/onboarding/complete', req.nextUrl.origin)

  const uid = await resolveCustomerUserId(req)
  if (!uid || !isSnapTradeConfigured() || !isCustomersDbConfigured()) {
    brokerageStep.searchParams.set('error', '1')
    return NextResponse.redirect(brokerageStep)
  }

  try {
    const rows = await customerQuery<UserRow>(
      `SELECT id, snaptrade_user_id, snaptrade_user_secret FROM users WHERE id = $1 LIMIT 1`,
      [uid],
    )
    const user = rows[0]
    if (!user?.snaptrade_user_id || !user.snaptrade_user_secret) {
      brokerageStep.searchParams.set('error', '1')
      return NextResponse.redirect(brokerageStep)
    }

    const snaptrade = getSnapTrade()
    const userSecret = decryptSecret(user.snaptrade_user_secret)
    const accountsRes = await snaptrade.accountInformation.listUserAccounts({
      userId: user.snaptrade_user_id,
      userSecret,
    })
    const accounts = Array.isArray(accountsRes.data) ? accountsRes.data : []

    if (accounts.length === 0) {
      // User opened the portal but didn't complete a connection — let them retry or skip.
      brokerageStep.searchParams.set('incomplete', '1')
      return NextResponse.redirect(brokerageStep)
    }

    await customerTransaction(async (run) => {
      // Re-sync: replace this user's connection rows with the current account set.
      await run(`DELETE FROM brokerage_connections WHERE user_id = $1`, [user.id])
      for (const a of accounts) {
        await run(
          `INSERT INTO brokerage_connections
             (user_id, authorization_id, brokerage_slug, account_id, account_name, status, last_synced_at)
           VALUES ($1, $2, $3, $4, $5, 'active', now())`,
          [user.id, a.brokerage_authorization, a.institution_name, a.id, a.name ?? a.institution_name],
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
      [user.id, JSON.stringify({ accounts: accounts.length })],
    ).catch(() => {})

    return NextResponse.redirect(complete)
  } catch (e) {
    console.error('[brokerage/callback] failed:', e)
    brokerageStep.searchParams.set('error', '1')
    return NextResponse.redirect(brokerageStep)
  }
}
