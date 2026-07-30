'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import EnrollShell from '../EnrollShell'
import { useEnrollment } from '../useEnrollment'

/**
 * BROKER-01 — Connect brokerage (July 29 handoff + 7/30 dual-path directive).
 *
 * EVERY broker tile offers TWO doors: "Connect account" for a customer who already
 * has one, and "Open new account ↗" (broker's own signup, new tab) for one who
 * doesn't — with the single piece of guidance that prevents the most common later
 * failure: enable options trading (defined-risk spreads) while opening the account.
 *
 * Lanes per SnapTrade's institution matrix (support.snaptrade.com/brokerages, 7/30):
 *  - Tradier    → our direct OAuth (503 until partner creds land)
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
}

/** sessionStorage key the agent screen reads the selected account from. */
export const SELECTED_ACCOUNT_KEY = 'enroll_broker_account'

interface Tile {
  key: 'tradier' | 'tastytrade' | 'robinhood'
  name: string
  /** How "Connect account" starts: our OAuth, or the SnapTrade portal with this slug. */
  connect: { kind: 'oauth' } | { kind: 'snaptrade'; slug: string }
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
    openUrl: 'https://tradier.com/signup',
    openNote: 'Choose a margin account and request options level 3 (spreads) during signup.',
  },
  {
    key: 'tastytrade',
    name: 'tastytrade',
    connect: { kind: 'snaptrade', slug: 'TASTYTRADE' },
    openUrl: 'https://open.tastytrade.com/signup',
    openNote: 'Choose a margin account and enable options trading with defined-risk spreads.',
  },
  {
    key: 'robinhood',
    name: 'Robinhood',
    connect: { kind: 'snaptrade', slug: 'ROBINHOOD' },
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

  const oauthError = params.get('error') === '1'
  const oauthIncomplete = params.get('incomplete') === '1'

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
      setBusy(false)
    }
  }

  async function continueWithAccount() {
    if (!enrollment || !selected) return
    setBusy(true)
    setError(null)
    try {
      const d = await call(`/api/v1/enrollments/${enrollment.id}/broker-account`, {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ broker_account_id: selected }),
      })
      setConfirmedMask(d.broker_account?.display_mask ?? null)
      try {
        sessionStorage.setItem(SELECTED_ACCOUNT_KEY, selected)
      } catch {
        /* agent screen falls back to re-deriving the selection */
      }
      router.push('/enroll/agent')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not select that account.')
      setBusy(false)
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
    >
      <div className="rounded-2xl border border-forge-border bg-forge-card/60 p-6 lg:p-8">
        <h2 className="text-2xl font-bold text-white">Connect your brokerage</h2>
        <p className="mt-1 text-sm text-gray-400">Choose the brokerage account your selected agent will use.</p>

        {oauthError ? (
          <p className="mt-4 rounded-md border border-red-700/40 bg-red-950/30 px-3 py-2 text-sm text-red-300">
            The connection could not be completed. Nothing was changed — you can try again.
          </p>
        ) : null}
        {oauthIncomplete ? (
          <p className="mt-4 rounded-md border border-white/15 bg-black/30 px-3 py-2 text-sm text-gray-300">
            The connection was not finished. You can retry whenever you&rsquo;re ready.
          </p>
        ) : null}
        {error ? (
          <p className="mt-4 rounded-md border border-red-700/40 bg-red-950/30 px-3 py-2 text-sm text-red-300">{error}</p>
        ) : null}

        <h3 className="mt-6 text-xs font-bold uppercase tracking-wider text-gray-400">Supported brokerages</h3>
        <div className="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
          {TILES.map((t) => (
            <div key={t.key} className="flex flex-col items-center rounded-xl border border-forge-border bg-black/20 p-4">
              <div className="flex h-10 items-center text-base font-bold text-white">{t.name}</div>
              <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-400">Available</span>
              <button
                type="button"
                disabled={busy}
                onClick={() => connect(t)}
                className="mt-3 w-full rounded-lg bg-amber-500 px-3 py-2 text-sm font-semibold text-black transition hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Connect account
              </button>
              <button
                type="button"
                onClick={() => setOpenGuide((k) => (k === t.key ? null : t.key))}
                className="mt-2 text-xs font-semibold text-gray-400 underline-offset-2 transition hover:text-white hover:underline"
              >
                Don&rsquo;t have one? Open an account
              </button>
            </div>
          ))}
          <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-forge-border bg-black/10 p-4 text-center">
            <span aria-hidden className="text-2xl text-gray-600">＋</span>
            <div className="mt-1 text-sm font-semibold text-gray-400">More brokerages</div>
            <span className="text-xs text-gray-600">Coming soon</span>
          </div>
        </div>

        {openGuide
          ? (() => {
              const t = TILES.find((x) => x.key === openGuide)
              if (!t) return null
              return (
                <div className="mt-4 rounded-xl border border-forge-border bg-black/20 p-4">
                  <p className="text-sm text-gray-300">
                    <strong className="text-white">Opening a new {t.name} account?</strong> {t.openNote} Account
                    opening happens on {t.name}&rsquo;s site and usually takes 10–15 minutes plus approval time.
                    Once it&rsquo;s open and funded, come back here and hit{' '}
                    <span className="font-semibold text-gray-100">Connect account</span>.
                  </p>
                  <div className="mt-3 flex gap-3">
                    <a
                      href={t.openUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-black transition hover:bg-amber-400"
                    >
                      Open a {t.name} account ↗
                    </a>
                    <button
                      type="button"
                      onClick={() => setOpenGuide(null)}
                      className="rounded-lg border border-white/15 px-4 py-2 text-sm text-gray-300 transition hover:text-white"
                    >
                      Close
                    </button>
                  </div>
                </div>
              )
            })()
          : null}

        {/* Connected accounts + selection */}
        {hasConnections ? (
          <div className="mt-6">
            <h3 className="text-xs font-bold uppercase tracking-wider text-gray-400">Your accounts</h3>
            {accounts.length === 0 ? (
              <p className="mt-2 text-sm text-gray-400">
                No accounts came back from your brokerage yet. Try reconnecting.
              </p>
            ) : (
              <ul className="mt-3 space-y-2">
                {accounts.map((a) => {
                  const ok = a.eligibility === 'eligible'
                  return (
                    <li key={a.id}>
                      <label
                        className={`flex cursor-pointer items-start gap-3 rounded-lg border px-4 py-3 transition ${
                          selected === a.id ? 'border-amber-500/60 bg-amber-500/5' : 'border-white/10 bg-black/20'
                        } ${!ok ? 'cursor-not-allowed opacity-70' : ''}`}
                      >
                        <input
                          type="radio"
                          name="broker-account"
                          checked={selected === a.id}
                          disabled={!ok || busy}
                          onChange={() => setSelected(a.id)}
                          className="mt-1 h-4 w-4 shrink-0 accent-amber-500"
                        />
                        <span className="min-w-0 flex-1">
                          <span className="flex flex-wrap items-center gap-2">
                            <span className="font-mono text-sm text-gray-200">{a.mask ?? '••••'}</span>
                            <span className="text-xs text-gray-500">{a.provider}</span>
                            <span
                              className={`ml-auto text-[10px] font-bold uppercase tracking-wider ${
                                ok ? 'text-emerald-400' : 'text-gray-500'
                              }`}
                            >
                              {ok ? 'Eligible' : 'Not eligible'}
                            </span>
                          </span>
                          {/* The REMEDIABLE reason, never a bare refusal. */}
                          {!ok && a.ineligible_reason ? (
                            <span className="mt-1 block text-xs leading-snug text-gray-500">{a.ineligible_reason}</span>
                          ) : null}
                        </span>
                      </label>
                    </li>
                  )
                })}
              </ul>
            )}

            {eligibleCount === 0 && accounts.length > 0 ? (
              <p className="mt-3 text-xs leading-relaxed text-gray-500">
                None of these accounts can be used yet — each shows what to fix. After updating with
                your broker, reconnect above to refresh the verdicts.
              </p>
            ) : null}

            <button
              type="button"
              disabled={!selected || busy}
              onClick={continueWithAccount}
              className="mt-5 w-full rounded-lg bg-amber-500 px-5 py-3 text-sm font-semibold text-black transition hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy ? 'Saving…' : confirmedMask ? `Continue with ${confirmedMask}` : 'Continue with this account'}
            </button>
          </div>
        ) : null}

        {conns === null && !error ? (
          <div className="mt-6 h-24 animate-pulse rounded-2xl border border-forge-border bg-forge-card/40" />
        ) : null}

        <div className="mt-6 rounded-xl border border-forge-border bg-black/20 p-4">
          <p className="flex items-start gap-2 text-sm text-gray-300">
            <span aria-hidden>🔒</span>
            <span>
              <strong className="text-white">Secure brokerage authorization.</strong> You will sign in directly with
              your broker. IronForge cannot withdraw funds or transfer cash.
            </span>
          </p>
          <p className="mt-2 border-t border-forge-border pt-2 text-xs text-gray-500">
            Recommended: use a dedicated brokerage account for IronForge automation.
          </p>
        </div>

        <Link href="/enroll/billing" className="mt-5 inline-block text-sm text-gray-400 hover:text-white">
          ← Back to billing
        </Link>

        <p className="mt-6 text-center text-[11px] text-gray-600">
          Brokerage names and marks belong to their respective owners. Availability does not imply endorsement.
        </p>
      </div>
    </EnrollShell>
  )
}
