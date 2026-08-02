import { NextRequest, NextResponse } from 'next/server'
import { publicOrigin } from '@/lib/public-origin'
import { resolveCustomerUserId } from '@/lib/brokerage/identity'
import { getSnapTrade, isSnapTradeConfigured } from '@/lib/snaptrade'
import { decryptSecret, encryptSecret } from '@/lib/crypto/secret-box'
import { evaluateAccountEligibility, maskAccountNumber, normalizeInstitutionSlug } from '@/lib/enrollment/eligibility'
import { isCustomersDbConfigured, customerQuery, customerExecute, customerTransaction } from '@/lib/customers-db'
import { syncBrokerageConnectionToAttio } from '@/lib/attio'
import { enqueueCrmEvent, recurringEventId } from '@/lib/crm/outbox'
import { mapBrokerageStatusToCrm } from '@/lib/crm/brokerage-status'

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
  email: string
  first_name: string
  last_name: string
  phone: string
  state: string | null
}

export async function GET(req: NextRequest) {
  // Land back on the surface that initiated the round-trip. return_to rides our own
  // customRedirect URL (set by the connect route) and is an allowlisted literal
  // resolved to a fixed route — never a caller-supplied URL.
  const fromEnroll = req.nextUrl.searchParams.get('return_to') === 'enroll'
  const brokerageStep = new URL(fromEnroll ? '/enroll/broker' : '/onboarding/brokerage', publicOrigin(req))
  const complete = fromEnroll
    ? new URL('/enroll/broker?connected=1', publicOrigin(req))
    : new URL('/onboarding/complete', publicOrigin(req))

  const uid = await resolveCustomerUserId(req)
  if (!uid || !isSnapTradeConfigured() || !isCustomersDbConfigured()) {
    brokerageStep.searchParams.set('error', '1')
    return NextResponse.redirect(brokerageStep)
  }

  try {
    const rows = await customerQuery<UserRow>(
      `SELECT id, snaptrade_user_id, snaptrade_user_secret,
              email, first_name, last_name, phone, state
         FROM users WHERE id = $1 LIMIT 1`,
      [uid],
    )
    const user = rows[0]
    if (!user?.snaptrade_user_id || !user.snaptrade_user_secret) {
      await customerExecute(
        `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'BROKERAGE_CONNECT_FAILED', $2)`,
        [uid, JSON.stringify({ reason: 'missing_snaptrade_registration' })],
      ).catch(() => {})
      if (user) {
        await enqueueCrmEvent({
          eventId: recurringEventId(`brokerage_failed:${uid}:missing_registration`),
          eventType: 'crm.brokerage_failed',
          userId: uid,
          payload: {
            email: user.email,
            firstName: user.first_name,
            lastName: user.last_name,
            ironforgeUserId: uid,
            connectionId: `pending:${uid}`,
            connectionStatus: mapBrokerageStatusToCrm('pending').connectionStatus,
            lastAttemptAt: new Date().toISOString(),
            errorCode: 'missing_registration',
            errorSummary: 'The brokerage connection could not be completed — registration was missing.',
            reauthorizationRequired: false,
          },
        })
      }
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
      await customerExecute(
        `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'BROKERAGE_CONNECT_INCOMPLETE', $2)`,
        [user.id, JSON.stringify({})],
      ).catch(() => {})
      await enqueueCrmEvent({
        eventId: recurringEventId(`brokerage_failed:${user.id}:incomplete`),
        eventType: 'crm.brokerage_failed',
        userId: user.id,
        payload: {
          email: user.email,
          firstName: user.first_name,
          lastName: user.last_name,
          ironforgeUserId: user.id,
          connectionId: `pending:${user.id}`,
          connectionStatus: mapBrokerageStatusToCrm('pending').connectionStatus,
          lastAttemptAt: new Date().toISOString(),
          errorCode: 'connection_incomplete',
          errorSummary: 'The customer opened the brokerage connection portal but did not complete linking an account.',
          reauthorizationRequired: false,
        },
      })
      brokerageStep.searchParams.set('incomplete', '1')
      return NextResponse.redirect(brokerageStep)
    }

    // Buying power per account, fetched BEFORE the transaction (network calls don't
    // belong inside it). Best-effort: a failed balance read stores null, and the
    // BUYING_POWER gate fails closed with a remediable reason — reconnecting refreshes.
    // Without this fetch every SnapTrade account failed eligibility on a null balance
    // even when the options gate was satisfiable.
    const balances = new Map<string, number | null>()
    for (const a of accounts) {
      try {
        const bal = await snaptrade.accountInformation.getUserAccountBalance({
          userId: user.snaptrade_user_id,
          userSecret,
          accountId: a.id,
        })
        const rows = Array.isArray(bal.data) ? (bal.data as Array<{ buying_power?: number | null; cash?: number | null }>) : []
        const usd = rows[0]
        balances.set(a.id, usd?.buying_power ?? usd?.cash ?? null)
      } catch {
        balances.set(a.id, null)
      }
    }

    const createdConnections: Array<{ id: string }> = []

    await customerTransaction(async (run) => {
      // Re-sync: replace this user's SNAPTRADE connection rows with the current account
      // set. Scoped by provider (an unscoped DELETE here wiped a coexisting Tradier
      // connection — UAT-012), and children first: broker_accounts has an FK with no
      // cascade, so deleting the parent with account rows present rolled the whole
      // re-sync back.
      await run(
        `DELETE FROM broker_accounts WHERE connection_id IN
           (SELECT id FROM brokerage_connections WHERE user_id = $1 AND provider = 'snaptrade')`,
        [user.id],
      )
      await run(`DELETE FROM brokerage_connections WHERE user_id = $1 AND provider = 'snaptrade'`, [user.id])
      for (const a of accounts) {
        const inserted = (await run(
          `INSERT INTO brokerage_connections
             (user_id, authorization_id, brokerage_slug, account_id, account_name, status, last_synced_at)
           VALUES ($1, $2, $3, $4, $5, 'active', now())
           RETURNING id`,
          [user.id, a.brokerage_authorization, a.institution_name, a.id, a.name ?? a.institution_name],
        )) as unknown as Array<{ id: string }>
        const connectionId = inserted?.[0]?.id
        if (!connectionId) continue
        createdConnections.push({ id: connectionId })

        // ── broker_accounts (§3 BROKER-02) ──
        //
        // Only the TRADIER callback wrote this table, so a customer who connected via
        // SnapTrade produced a brokerage_connections row and nothing else — and the
        // account-selection step reads broker_accounts, so their account list was empty
        // with no explanation. An empty picker reads as "the product is broken"; a
        // listed account with a reason reads as "here is what to fix".
        //
        // SnapTrade does NOT expose options approval level — `option_level` is sourced
        // from Tradier alone in this codebase. evaluateAccountEligibility fails CLOSED on
        // an unknown level, so these rows come back ineligible with
        // OPTIONS_APPROVAL. That is the honest verdict, not a bug to work around: we
        // genuinely cannot show a customer is approved for spreads, and guessing would
        // authorise automated options trading on an unverified account.
        //
        // The account reference is ENCRYPTED and only the mask is stored for display
        // (§5, §8); nothing here writes it in the clear or logs it.
        const meta = a as unknown as {
          number?: string; status?: string; meta?: { type?: string }; raw_type?: string
        }
        const acctRef = String(meta.number ?? a.id)
        const bp = balances.get(a.id) ?? null
        // SnapTrade exposes no options approval level. Eligibility is slug-aware:
        // mleg-capable brokers (tastytrade) pass the options gate on platform
        // capability; data-only brokers (Robinhood) get the honest BROKER_LIMITATION
        // instead of an unfixable "options approval required".
        const verdict = evaluateAccountEligibility({
          externalRef: acctRef,
          accountType: meta.meta?.type ?? meta.raw_type ?? null,
          optionsLevel: null,
          status: meta.status ?? 'active',
          buyingPower: bp,
          brokerSlug: normalizeInstitutionSlug(a.institution_name),
        })
        await run(
          `INSERT INTO broker_accounts
             (connection_id, external_account_ref_ciphertext, display_mask, account_type,
              options_level, eligibility, ineligible_reason, buying_power_cents, checked_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, now())`,
          [
            connectionId,
            encryptSecret(acctRef),
            maskAccountNumber(acctRef),
            meta.meta?.type ?? meta.raw_type ?? null,
            null,
            verdict.eligible ? 'eligible' : 'ineligible',
            verdict.reason ?? null,
            bp == null ? null : Math.round(bp * 100),
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
      [user.id, JSON.stringify({ accounts: accounts.length })],
    ).catch(() => {})

    // One CRM connection record per brokerage_connections row created above — each is keyed on
    // its own immutable connection_id (events.ts brokerageConnection()), matching the 1:1 we just
    // wrote to the database.
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

    // Mirror the brokerage-connection milestone into Attio CRM (best-effort; never blocks
    // the redirect). Awaited like the signup sync so it runs before the handler returns.
    try {
      const first = accounts[0]
      const attioRes = await syncBrokerageConnectionToAttio(
        {
          firstName: user.first_name,
          lastName: user.last_name,
          email: user.email,
          phone: user.phone,
          state: user.state || undefined,
        },
        {
          brokerage: first?.institution_name,
          accountName: first?.name ?? first?.institution_name,
          accountCount: accounts.length,
          connectedAt: new Date().toISOString(),
        },
      )
      if (attioRes.synced) {
        await customerExecute(
          `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'ATTIO_BROKERAGE_SYNCED', $2)`,
          [user.id, JSON.stringify({ record_id: attioRes.recordId ?? null })],
        ).catch(() => {})
      } else if (!attioRes.skipped) {
        await customerExecute(
          `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'ATTIO_BROKERAGE_SYNC_FAILED', $2)`,
          [user.id, JSON.stringify({ error: (attioRes.error ?? '').slice(0, 200) })],
        ).catch(() => {})
      }
    } catch (e) {
      console.error('[brokerage/callback] attio sync threw:', e)
    }

    return NextResponse.redirect(complete)
  } catch (e) {
    console.error('[brokerage/callback] failed:', e)
    if (uid && isCustomersDbConfigured()) {
      try {
        const basicRows = await customerQuery<{ email: string; first_name: string; last_name: string }>(
          `SELECT email, first_name, last_name FROM users WHERE id = $1 LIMIT 1`,
          [uid],
        )
        const basic = basicRows[0]
        if (basic) {
          await customerExecute(
            `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'BROKERAGE_CONNECT_FAILED', $2)`,
            [uid, JSON.stringify({ error: (e instanceof Error ? e.message : String(e)).slice(0, 200) })],
          ).catch(() => {})
          await enqueueCrmEvent({
            eventId: recurringEventId(`brokerage_failed:${uid}:exception`),
            eventType: 'crm.brokerage_failed',
            userId: uid,
            payload: {
              email: basic.email,
              firstName: basic.first_name,
              lastName: basic.last_name,
              ironforgeUserId: uid,
              connectionId: `pending:${uid}`,
              connectionStatus: mapBrokerageStatusToCrm('pending').connectionStatus,
              lastAttemptAt: new Date().toISOString(),
              errorCode: 'connection_error',
              errorSummary: 'The brokerage connection attempt failed unexpectedly.',
              reauthorizationRequired: false,
            },
          })
        }
      } catch (inner) {
        console.error('[brokerage/callback] failure audit/CRM emit threw:', inner)
      }
    }
    brokerageStep.searchParams.set('error', '1')
    return NextResponse.redirect(brokerageStep)
  }
}
