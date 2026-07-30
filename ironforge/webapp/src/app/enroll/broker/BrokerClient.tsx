'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import EnrollShell from '../EnrollShell'
import { useEnrollment } from '../useEnrollment'

/**
 * BROKER-01 — Connect brokerage (July 29 handoff).
 *
 * Four tiles: Tradier (direct OAuth), tastytrade, Robinhood (SnapTrade hosted portal),
 * and a disabled "More brokerages — Coming soon". tastytrade has no integration yet;
 * per the approved visual it is shown alongside the others, and its Connect opens a
 * graceful "not yet supported / notify me" state that records a BROKER_INTEREST event
 * instead of dead-ending. Tiles are text lockups, visually equal — official broker
 * marks are NOT used until the production asset rights are cleared (Appendix A gate).
 *
 * After the OAuth round-trip (?connected=1) the account list renders with the stored
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

const TILES = [
  { key: 'tradier', name: 'Tradier' },
  { key: 'tastytrade', name: 'tastytrade' },
  { key: 'robinhood', name: 'Robinhood' },
] as const

export default function BrokerClient() {
  const { enrollment, busy, setBusy, error, setError, call, router } = useEnrollment('broker')
  const params = useSearchParams()
  const [conns, setConns] = useState<Conn[] | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [confirmedMask, setConfirmedMask] = useState<string | null>(null)
  const [tastyOpen, setTastyOpen] = useState(false)
  const [tastyNotified, setTastyNotified] = useState(false)

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

  /** Tradier: our own OAuth. Robinhood: SnapTrade hosted portal. */
  async function connect(provider: 'tradier' | 'robinhood') {
    setBusy(true)
    setError(null)
    try {
      const d =
        provider === 'tradier'
          ? await call('/api/onboarding/brokerage/tradier/connect', {
              method: 'POST',
              headers: { 'content-type': 'application/json' },
              body: JSON.stringify({ return_to: 'enroll' }),
            })
          : await call('/api/onboarding/brokerage/connect', {
              method: 'POST',
              headers: { 'content-type': 'application/json' },
              body: JSON.stringify({ broker: 'ROBINHOOD', return_to: 'enroll' }),
            })
      window.location.assign(d.redirectURI)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start the connection.')
      setBusy(false)
    }
  }

  async function notifyTastytrade() {
    try {
      await call('/api/onboarding/brokerage/interest', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ broker: 'tastytrade' }),
      })
    } catch {
      // Interest logging is best-effort; the acknowledgment below is still honest.
    }
    setTastyNotified(true)
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
                onClick={() =>
                  t.key === 'tastytrade' ? setTastyOpen(true) : connect(t.key as 'tradier' | 'robinhood')
                }
                className="mt-3 w-full rounded-lg bg-amber-500 px-3 py-2 text-sm font-semibold text-black transition hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Connect
              </button>
            </div>
          ))}
          <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-forge-border bg-black/10 p-4 text-center">
            <span aria-hidden className="text-2xl text-gray-600">＋</span>
            <div className="mt-1 text-sm font-semibold text-gray-400">More brokerages</div>
            <span className="text-xs text-gray-600">Coming soon</span>
          </div>
        </div>

        {tastyOpen ? (
          <div className="mt-4 rounded-xl border border-forge-border bg-black/20 p-4">
            {tastyNotified ? (
              <p className="text-sm text-gray-300">
                <span className="font-semibold text-emerald-400">Got it.</span> We&rsquo;ll let you know the moment
                tastytrade connections open.
              </p>
            ) : (
              <>
                <p className="text-sm text-gray-300">
                  <strong className="text-white">tastytrade connections aren&rsquo;t open quite yet.</strong> We&rsquo;re
                  finishing the integration. Want an email when it&rsquo;s ready?
                </p>
                <div className="mt-3 flex gap-3">
                  <button
                    type="button"
                    onClick={notifyTastytrade}
                    className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-black transition hover:bg-amber-400"
                  >
                    Notify me
                  </button>
                  <button
                    type="button"
                    onClick={() => setTastyOpen(false)}
                    className="rounded-lg border border-white/15 px-4 py-2 text-sm text-gray-300 transition hover:text-white"
                  >
                    Not now
                  </button>
                </div>
              </>
            )}
          </div>
        ) : null}

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
