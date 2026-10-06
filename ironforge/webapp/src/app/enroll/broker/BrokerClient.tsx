'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import EnrollShell from '../EnrollShell'
import { useEnrollment } from '../useEnrollment'
import { AGENT_CONFIG_KEY } from '../agent/AgentClient'
import { track } from '@/lib/analytics/track'
import { trackEnrollStepComplete } from '@/lib/analytics/enroll'
import { EMBER_AGENT } from '@/lib/agents/ember'

/**
 * BROKER-01 — Connect brokerage (10/5 reorder: step 4, right after Choose agent).
 *
 * EVERY broker tile offers TWO doors: "Connect account" for a customer who already
 * has one, and "Open new account ↗" (broker's own signup, new tab) for one who
 * doesn't — with the single piece of guidance that prevents the most common later
 * failure: enable options trading (defined-risk spreads) while opening the account.
 *
 * Lanes per SnapTrade's institution matrix (support.snaptrade.com/brokerages, 7/30):
 *  - Tradier    → our direct OAuth. LIVE (10/5): TRADIER_OAUTH_CLIENT_ID/_SECRET are
 *                 configured and the cookie-gate bug blocking the callback (#3180) is
 *                 fixed — the same path the mobile app already uses successfully. This
 *                 is the design's recommended/default brokerage, so it's listed first
 *                 and tagged "Official partner" rather than "coming soon."
 *  - tastytrade → SnapTrade hosted portal; multi-leg options trading is GA there,
 *                 so this is a REAL lane today
 *  - Robinhood  → SnapTrade DATA-ONLY (no trading of any kind); connect works but
 *                 accounts are honestly marked broker-limited
 *
 * Tiles are text lockups, visually equal — official broker marks are NOT used until
 * the production asset rights are cleared (Appendix A gate).
 *
 * After the round-trip (?connected=1) the account list renders with the stored
 * eligibility verdicts: exactly one eligible account is auto-selected; several require
 * an explicit choice; none shows the remediable reason for each. Selection goes through
 * PUT /v1/enrollments/{id}/broker-account, which re-validates ownership + eligibility
 * server-side.
 *
 * Selecting an account also MINTS the agent config now (server-side, same validation
 * as AGENT-01 — see lib/enrollment/agent-config-service.ts): the dedicated AGENT-01
 * screen no longer sits between this step and Billing in the web order, so there is
 * nothing left for a customer to configure here beyond picking the account. The
 * response carries `config_id`; it rides sessionStorage under the same key AGENT-01
 * and ReviewClient already use, so ReviewClient needs no change to find it.
 */

interface BrokerAccount {
  id: string
  mask: string | null
  eligibility: string | null
  ineligible_reason: string | null
}

interface Conn {
  id: string
  provider: string
  status: string
  accounts: BrokerAccount[]
  authorization_id: string | null
}

/** sessionStorage key the agent screen reads the selected account from. */
export const SELECTED_ACCOUNT_KEY = 'enroll_broker_account'

/** Per-tile status (audit M4): all three said "Available" in green, but Tradier's
 *  OAuth isn't provisioned yet and Robinhood can never trade — telling a customer
 *  they can connect and letting them fail is worse than saying the truth up front. */
type TileStatus = { label: string; tone: 'good' | 'muted' | 'coming'; canConnect: boolean }

interface Tile {
  key: 'tradier' | 'tastytrade' | 'robinhood'
  name: string
  /** How "Connect account" starts: our OAuth, or the SnapTrade portal with this slug. */
  connect: { kind: 'oauth' } | { kind: 'snaptrade'; slug: string }
  /** Honest per-broker capability, shown on the tile. */
  status: TileStatus
  /** The broker's own account-opening page — "Open new account" opens it in a new tab. */
  openUrl: string
  /** The one thing to get right while opening a new account there. */
  openNote: string
}

const TILES: readonly Tile[] = [
  {
    key: 'tradier',
    name: 'Tradier',
    connect: { kind: 'oauth' },
    status: { label: 'Official partner', tone: 'good', canConnect: true },
    openUrl: 'https://tradier.com/signup',
    openNote: 'Choose a margin account and request options level 3 (spreads) during signup.',
  },
  {
    key: 'tastytrade',
    name: 'tastytrade',
    connect: { kind: 'snaptrade', slug: 'TASTYTRADE' },
    status: { label: 'Automated trading', tone: 'good', canConnect: true },
    openUrl: 'https://open.tastytrade.com/signup',
    openNote: 'Choose a margin account and enable options trading with defined-risk spreads.',
  },
  {
    key: 'robinhood',
    name: 'Robinhood',
    connect: { kind: 'snaptrade', slug: 'ROBINHOOD' },
    status: { label: 'View only', tone: 'muted', canConnect: false },
    openUrl: 'https://robinhood.com/signup',
    openNote: 'Robinhood accounts can be viewed here, but Robinhood does not yet allow automated trading.',
  },
]

export default function BrokerClient() {
  const { enrollment, busy, setBusy, error, setError, call, router } = useEnrollment('broker')
  const params = useSearchParams()
  const [conns, setConns] = useState<Conn[] | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [confirmedMask, setConfirmedMask] = useState<string | null>(null)
  /** Which tile's "Open new account" guidance is showing. */
  const [openGuide, setOpenGuide] = useState<string | null>(null)
  /** Dedicated Ember $500-$2,000 banner (gap audit "Broker step — Ember banner"
   *  PARTIAL — previously only a generic ineligible_reason string). */
  const [emberBanner, setEmberBanner] = useState<string | null>(null)
  const [disconnecting, setDisconnecting] = useState<string | null>(null)

  const oauthError = params.get('error') === '1'
  const oauthIncomplete = params.get('incomplete') === '1'
  const oauthConnected = params.get('connected') === '1'

  // Fire the round-trip outcome exactly once per landing — not every re-render —
  // and only when the URL actually carries one of these query params. provider is
  // best-effort from the broker param SnapTrade/Tradier callbacks echo back.
  useEffect(() => {
    const provider = params.get('broker') ?? params.get('provider') ?? 'unknown'
    if (oauthConnected) track('broker_connect_success', { provider })
    else if (oauthError) track('broker_connect_error', { provider })
    else if (oauthIncomplete) track('broker_connect_cancel', { provider })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [oauthConnected, oauthError, oauthIncomplete])

  const loadAccounts = useCallback(async () => {
    const d = await call('/api/brokerage/connections')
    const list: Conn[] = d.connections ?? []
    setConns(list)
    // Auto-select when EXACTLY ONE eligible account exists; several require a choice.
    const eligible = list.flatMap((c) => c.accounts.filter((a) => a.eligibility === 'eligible'))
    if (eligible.length === 1) setSelected(eligible[0].id)
  }, [call])

  useEffect(() => {
    if (!enrollment) return
    loadAccounts().catch((e) => setError(e instanceof Error ? e.message : 'Could not load your brokerage connections.'))
  }, [enrollment, loadAccounts, setError])

  /** Tradier: our own OAuth. Everything else: SnapTrade hosted portal with the slug. */
  async function connect(tile: Tile) {
    setBusy(true)
    setError(null)
    track('broker_connect_start', { provider: tile.key })
    try {
      const d =
        tile.connect.kind === 'oauth'
          ? await call('/api/onboarding/brokerage/tradier/connect', {
              method: 'POST',
              headers: { 'content-type': 'application/json' },
              body: JSON.stringify({ return_to: 'enroll' }),
            })
          : await call('/api/onboarding/brokerage/connect', {
              method: 'POST',
              headers: { 'content-type': 'application/json' },
              body: JSON.stringify({ broker: tile.connect.slug, return_to: 'enroll' }),
            })
      window.location.assign(d.redirectURI)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start the connection.')
      track('broker_connect_error', { provider: tile.key })
      setBusy(false)
    }
  }

  async function continueWithAccount() {
    if (!enrollment || !selected) return
    setBusy(true)
    setError(null)
    setEmberBanner(null)
    try {
      const d = await call(`/api/v1/enrollments/${enrollment.id}/broker-account`, {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ broker_account_id: selected }),
      })
      setConfirmedMask(d.broker_account?.display_mask ?? null)
      try {
        sessionStorage.setItem(SELECTED_ACCOUNT_KEY, selected)
        if (d.config_id) sessionStorage.setItem(AGENT_CONFIG_KEY, d.config_id)
      } catch {
        /* the agent screen (fallback) re-derives the selection/config if this is lost */
      }
      if (!d.config_id) {
        // The server could not mint a valid config from this account. Ember's
        // $500-$2,000 band gets a dedicated banner right here so the customer can pick
        // a different account without leaving the step; any other agent falls back to
        // the AGENT-01 screen, which surfaces the violation.
        if (enrollment.selected_plan === 'ember') {
          track('ember_balance_block')
          setEmberBanner(d.violation || EMBER_AGENT.balanceOutOfRangeCopy)
          setBusy(false)
          return
        }
        router.push('/enroll/agent')
        return
      }
      trackEnrollStepComplete('broker')
      router.push(enrollment.selected_plan === 'ember' ? '/enroll/review' : '/enroll/billing')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not select that account.')
      setBusy(false)
    }
  }

  /** "Disconnect and choose another brokerage" (gap audit PARTIAL — not present once
   *  an account is connected). Removes the authorization and reloads the account list
   *  so the broker tiles become selectable again. */
  async function disconnect(authorizationId: string) {
    setDisconnecting(authorizationId)
    setError(null)
    try {
      await call('/api/brokerage/connection', {
        method: 'DELETE',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ authorizationId }),
      })
      setSelected(null)
      setConfirmedMask(null)
      setEmberBanner(null)
      await loadAccounts()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not disconnect that brokerage.')
    } finally {
      setDisconnecting(null)
    }
  }

  const accounts = (conns ?? []).flatMap((c) => c.accounts.map((a) => ({ ...a, provider: c.provider })))
  const hasConnections = (conns ?? []).length > 0
  const eligibleCount = accounts.filter((a) => a.eligibility === 'eligible').length

  return (
    <EnrollShell
      headline="Connect securely."
      subline="Authorize IronForge through your broker. We never see or store your brokerage password."
      maxWidthClass="max-w-3xl"
      step="broker"
      enrollment={enrollment}
    >
      {oauthError ? <p className="err" style={{ marginBottom: 14 }}>The connection could not be completed. Nothing was changed — you can try again.</p> : null}
      {oauthIncomplete ? <p className="help" style={{ marginBottom: 14 }}>The connection was not finished. You can retry whenever you&rsquo;re ready.</p> : null}
      {error ? <p className="err" style={{ marginBottom: 14 }}>{error}</p> : null}

      {/* Dedicated Ember $500-$2,000 banner — a generic ineligible_reason string isn't
          enough here because the fix is specific: a different account, or a different
          agent. */}
      {emberBanner ? (
        <div className="check-row bad" style={{ marginBottom: 14, display: 'block' }}>
          <strong>This account doesn&rsquo;t fit Ember.</strong>
          <p style={{ marginTop: 4 }}>{emberBanner}</p>
        </div>
      ) : null}

      <h3 className="rail-h">Supported brokerages</h3>
      <div className="bk-card" style={{ gridTemplateColumns: 'repeat(2, 1fr)', display: 'grid', marginTop: 12 }}>
        {TILES.map((t) => (
          <div key={t.key} className="card pad" style={{ textAlign: 'center' }}>
            <div className="bk-head" style={{ justifyContent: 'center' }}>
              <span className="bk-logo">{t.name.slice(0, 1)}</span>
              <b>{t.name}</b>
            </div>
            <span className={`badge ${t.status.tone === 'good' ? 'ok' : 'grey'}`} style={{ marginTop: 10, display: 'inline-block' }}>
              {t.status.label}
            </span>
            <button
              type="button"
              disabled={busy || !t.status.canConnect}
              onClick={() => connect(t)}
              className="btn btn-accent btn-block"
              style={{ marginTop: 12 }}
            >
              {t.status.canConnect ? 'Connect account' : t.status.tone === 'coming' ? 'Coming soon' : 'Not available'}
            </button>
            {/* en-4 #121: "If either isn't available ... 'Coming soon' with a notify-me
                option." Automated trading isn't live for this tile — offer notice of
                when it is, rather than a dead end. */}
            {!t.status.canConnect ? (
              <a
                href={`mailto:support@ironforge.trade?subject=${encodeURIComponent(`Notify me when ${t.name} supports automated trading`)}`}
                className="link"
                style={{ marginTop: 8, fontSize: '.8rem', display: 'block' }}
              >
                Notify me when available →
              </a>
            ) : null}
            <button type="button" onClick={() => setOpenGuide((k) => (k === t.key ? null : t.key))} className="link" style={{ marginTop: 10, fontSize: '.8rem' }}>
              Don&rsquo;t have one? Open an account
            </button>
          </div>
        ))}
      </div>

      {openGuide
        ? (() => {
            const t = TILES.find((x) => x.key === openGuide)
            if (!t) return null
            return (
              <div className="card pad" style={{ marginTop: 14 }}>
                <p style={{ fontSize: '.9rem' }}>
                  <strong>Opening a new {t.name} account?</strong> {t.openNote} Account opening happens on{' '}
                  {t.name}&rsquo;s site and usually takes 10–15 minutes plus approval time. Once it&rsquo;s open and
                  funded, come back here and hit <strong>Connect account</strong>.
                </p>
                <div className="nav-row" style={{ borderTop: 'none', marginTop: 14, paddingTop: 0, justifyContent: 'flex-start' }}>
                  <a href={t.openUrl} target="_blank" rel="noopener noreferrer" className="btn btn-accent">
                    Open a {t.name} account ↗
                  </a>
                  <button type="button" onClick={() => setOpenGuide(null)} className="btn">Close</button>
                </div>
              </div>
            )
          })()
        : null}

      {/* Connected accounts + selection */}
      {hasConnections ? (
        <div style={{ marginTop: 20 }}>
          <div className="nav-row" style={{ borderTop: 'none', paddingTop: 0 }}>
            <h3 className="rail-h" style={{ margin: 0 }}>Your accounts</h3>
            {/* "Disconnect and choose another brokerage" (gap audit PARTIAL — not
                present once an account is connected). */}
            {(conns ?? []).filter((c) => c.authorization_id).map((c) => (
              <button
                key={c.id}
                type="button"
                disabled={busy || disconnecting === c.authorization_id}
                onClick={() => disconnect(c.authorization_id!)}
                className="link"
              >
                {disconnecting === c.authorization_id ? 'Disconnecting…' : 'Disconnect and choose another brokerage'}
              </button>
            ))}
          </div>
          {accounts.length === 0 ? (
            <p className="help" style={{ marginTop: 8 }}>No accounts came back from your brokerage yet. Try reconnecting.</p>
          ) : (
            <div className="card" style={{ marginTop: 10 }}>
              {accounts.map((a) => {
                const ok = a.eligibility === 'eligible'
                return (
                  <label
                    key={a.id}
                    className="ack"
                    style={{
                      gridTemplateColumns: '18px 1fr',
                      cursor: ok ? 'pointer' : 'not-allowed',
                      opacity: ok ? 1 : 0.7,
                      background: selected === a.id ? 'var(--bg-2)' : undefined,
                    }}
                  >
                    <input
                      type="radio"
                      name="broker-account"
                      checked={selected === a.id}
                      disabled={!ok || busy}
                      onChange={() => setSelected(a.id)}
                    />
                    <span>
                      <span style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
                        <b className="mono">{a.mask ?? '••••'}</b>
                        <span className="muted" style={{ fontSize: '.78rem' }}>{a.provider}</span>
                        <span className={`badge ${ok ? 'ok' : 'grey'}`} style={{ marginLeft: 'auto' }}>
                          {ok ? 'Eligible' : 'Not eligible'}
                        </span>
                      </span>
                      {!ok && a.ineligible_reason ? <p className="help" style={{ marginTop: 4 }}>{a.ineligible_reason}</p> : null}
                    </span>
                  </label>
                )
              })}
            </div>
          )}

          {eligibleCount === 0 && accounts.length > 0 ? (
            <p className="help" style={{ marginTop: 10, lineHeight: 1.5 }}>
              None of these accounts can be used yet — each shows what to fix. After updating with your broker,
              reconnect above to refresh the verdicts.
            </p>
          ) : null}

          <button type="button" disabled={!selected || busy} onClick={continueWithAccount} className="btn btn-accent btn-block btn-lg" style={{ marginTop: 16 }}>
            {busy ? 'Saving…' : confirmedMask ? `Continue with ${confirmedMask}` : 'Continue with this account'}
          </button>
        </div>
      ) : null}

      {conns === null && !error ? <div className="card pad" style={{ height: 96, marginTop: 20 }} /> : null}

      {/* en-4 #116: "Permissions shown before connecting: view balances, view
          positions, place and cancel option orders, never withdraw." */}
      <div className="check-row ok" style={{ marginTop: 20, display: 'block' }}>
        <strong>Secure brokerage authorization.</strong> You will sign in directly with your broker and grant
        IronForge permission to:
        <ul style={{ marginTop: 8, marginBottom: 0, display: 'grid', gap: 4, paddingLeft: 18 }}>
          <li>View your account balances</li>
          <li>View your open positions</li>
          <li>Place and cancel option orders</li>
        </ul>
        <p style={{ marginTop: 8, fontWeight: 600 }}>IronForge can never withdraw funds or transfer cash.</p>
        <p className="help" style={{ marginTop: 6 }}>Recommended: use a dedicated brokerage account for IronForge automation.</p>
      </div>

      <div className="nav-row">
        <Link href="/enroll/plan" className="btn">← Back to agent selection</Link>
      </div>

      <p className="help" style={{ marginTop: 18, textAlign: 'center' }}>
        Brokerage names and marks belong to their respective owners. Availability does not imply endorsement.
      </p>
    </EnrollShell>
  )
}
