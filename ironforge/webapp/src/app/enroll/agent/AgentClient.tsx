'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import EnrollShell from '../EnrollShell'
import { useEnrollment } from '../useEnrollment'
import { SELECTED_ACCOUNT_KEY } from '../broker/BrokerClient'
import { BOT_PLANS, botTagline } from '@/lib/billing/plans'

/**
 * AGENT-01 — Choose Spark or Flame (July 29 handoff).
 *
 * Selecting an agent creates a DRAFT configuration with the rule-schema defaults
 * (config: {} → server defaults apply) against the account chosen at BROKER-01 — it
 * never activates anything, and the footnote says so. There is no separate configure
 * screen: the approved flow has none, and the review screen renders the server-computed
 * deployment limits as display-only truth.
 *
 * FLOW ORDER NOTE. The handoff's §2 sequence puts Agent before Brokerage; here the
 * account comes first because the built agent-config API computes limits from a real
 * account's buying power at draft time — a deliberate, documented deviation that keeps
 * the review numbers live instead of hypothetical.
 *
 * Color law: Spark = the `spark` token (blue-* is remapped to neutral in Tailwind);
 * Flame = brand orange (amber-*).
 */

export const AGENT_CONFIG_KEY = 'enroll_agent_config'

interface AccountPick {
  id: string
  mask: string | null
}

export default function AgentClient() {
  const { enrollment, busy, setBusy, error, setError, call, router } = useEnrollment('agent')
  const [account, setAccount] = useState<AccountPick | null>(null)
  const [resolving, setResolving] = useState(true)

  // The selected account rides sessionStorage from BROKER-01; a fresh device or a
  // cleared session falls back to re-deriving it (single eligible account), and a
  // customer with several eligible accounts goes back to choose explicitly.
  useEffect(() => {
    if (!enrollment) return
    ;(async () => {
      try {
        let id: string | null = null
        try {
          id = sessionStorage.getItem(SELECTED_ACCOUNT_KEY)
        } catch {
          /* fall through to re-derive */
        }
        const d = await call('/api/brokerage/connections')
        const accounts: Array<{ id: string; mask: string | null; eligibility: string | null }> = (
          d.connections ?? []
        ).flatMap((c: { accounts: Array<{ id: string; mask: string | null; eligibility: string | null }> }) => c.accounts)
        const eligible = accounts.filter((a) => a.eligibility === 'eligible')
        const chosen = (id && eligible.find((a) => a.id === id)) || (eligible.length === 1 ? eligible[0] : null)
        if (!chosen) {
          router.replace('/enroll/broker')
          return
        }
        setAccount({ id: chosen.id, mask: chosen.mask })
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Could not load your account.')
      } finally {
        setResolving(false)
      }
    })()
  }, [enrollment, call, router, setError])

  async function select(agent: 'spark' | 'flame') {
    if (!account) return
    setBusy(true)
    setError(null)
    try {
      const d = await call('/api/v1/agent-configs', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ agent_code: agent, broker_account_id: account.id, config: {} }),
      })
      if (d.status !== 'valid') {
        const detail = Array.isArray(d.violations) && d.violations.length ? ` ${d.violations.join(' ')}` : ''
        setError(`Your setup needs attention before review.${detail}`)
        setBusy(false)
        return
      }
      try {
        sessionStorage.setItem(AGENT_CONFIG_KEY, d.id)
      } catch {
        /* review screen will bounce back here if it can't find the config */
      }
      router.push('/enroll/review')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save your selection.')
      setBusy(false)
    }
  }

  return (
    <EnrollShell
      headline="Choose your trading agent."
      subline="Select the risk profile that best fits how you want to trade."
      maxWidthClass="max-w-3xl"
    >
      <div className="rounded-2xl border border-forge-border bg-forge-card/60 p-6 lg:p-8">
        <h2 className="text-2xl font-bold text-white">Choose Spark or Flame</h2>
        <p className="mt-1 text-sm text-gray-400">
          Both agents use rules-based iron condor strategies with different risk profiles.
        </p>
        {account?.mask ? (
          <p className="mt-2 text-xs text-gray-500">
            Trading account: <span className="font-mono text-gray-300">{account.mask}</span>
          </p>
        ) : null}

        {error ? (
          <p className="mt-4 rounded-md border border-red-700/40 bg-red-950/30 px-3 py-2 text-sm text-red-300">{error}</p>
        ) : null}

        {resolving && !error ? (
          <div className="mt-6 h-72 animate-pulse rounded-2xl border border-forge-border bg-forge-card/40" />
        ) : null}

        {account ? (
          <div className="mt-6 grid gap-5 md:grid-cols-2">
          {/*
            ONE STRATEGY AT TWO CLOCKS — this is the screen where a customer picks
            which bot trades their money, so the copy has to be true.

            It used to sell a risk ladder: Spark badged "Lower risk" and described
            as "a more conservative IRON CONDOR strategy", Flame badged "Higher
            risk" as "TWO-DAY SPY put credit spreads with heavier capital
            deployment". Every one of those claims was wrong after the 2026-08-16
            EBB change:
              - `dteMode` returns '0DTE' for BOTH — neither is an iron condor or
                a two-day spread any more.
              - Their scanner configs are identical on wing width, positions at a
                time, contracts, profit target and end-of-day handling.
              - `bp_pct` is 0.20 for both, so "heavier capital deployment" was
                false in the direction that matters most.

            A fabricated risk grade on an enrolment screen means someone picking
            "Lower risk" believed they were buying a safer product. They were
            buying the same product at a different time of day. Structure and
            cadence are read from BOT_PLANS so this cannot drift from checkout.
          */}
            {/* Spark */}
            <div className="flex flex-col rounded-xl border border-spark/60 bg-black/20 p-6">
              {/* Badge states WHEN, not a risk grade — see the block comment above. */}
              <span className="self-start rounded-md bg-spark px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-white">
                Morning entry
              </span>
              <h3 className="mt-3 text-2xl font-bold text-spark">Spark</h3>
              <p className="mt-2 text-sm leading-relaxed text-gray-300">
                {botTagline('spark')}, entered {BOT_PLANS.spark.cadence}. The most a trade can lose
                is fixed before it opens.
              </p>
              <p className="mt-4 text-[10px] font-bold uppercase tracking-wider text-gray-500">Best for</p>
              <p className="mt-1 text-sm text-gray-400">
                Traders who want the day&rsquo;s position established early in the session.
              </p>
              <ul className="mt-4 space-y-2 border-t border-forge-border pt-4">
                {[botTagline('spark'), `Trades ${BOT_PLANS.spark.cadence}`, 'Defined risk on every trade'].map((f) => (
                  <li key={f} className="flex items-start gap-2 text-sm text-gray-300">
                    <span aria-hidden className="mt-0.5 font-bold text-spark">✓</span>
                    {f}
                  </li>
                ))}
              </ul>
              <button
                type="button"
                disabled={busy}
                onClick={() => select('spark')}
                className="mt-auto w-full rounded-lg bg-spark px-5 py-3 text-sm font-semibold text-white transition hover:bg-spark-dark disabled:cursor-not-allowed disabled:opacity-50"
              >
                Select Spark
              </button>
            </div>

            {/* Flame */}
            <div className="flex flex-col rounded-xl border border-amber-500/60 bg-black/20 p-6">
              <span className="self-start rounded-md bg-amber-500 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-black">
                Afternoon entry
              </span>
              <h3 className="mt-3 text-2xl font-bold text-amber-500">Flame</h3>
              <p className="mt-2 text-sm leading-relaxed text-gray-300">
                The same strategy as Spark, entered {BOT_PLANS.flame.cadence} instead — a shorter
                run to expiry. The most a trade can lose is fixed before it opens.
              </p>
              {/* Honesty (audit M6): Flame currently executes in simulation. Selling it
                  as live automation while delivering paper was a trust problem. */}
              <p className="mt-2 rounded-md border border-amber-500/30 bg-amber-950/20 px-3 py-2 text-xs leading-relaxed text-amber-200">
                Flame currently trades in simulation mode while live rollout completes — your
                dashboard shows its real-time paper record, and your plan includes the live
                upgrade when it ships.
              </p>
              <p className="mt-4 text-[10px] font-bold uppercase tracking-wider text-gray-500">Best for</p>
              <p className="mt-1 text-sm text-gray-400">
                Traders who prefer a later entry &mdash; or who already run Spark and want entries
                spread across the day rather than concentrated in one window.
              </p>
              <ul className="mt-4 space-y-2 border-t border-forge-border pt-4">
                {[botTagline('flame'), `Trades ${BOT_PLANS.flame.cadence}`, 'Defined risk on every trade'].map((f) => (
                  <li key={f} className="flex items-start gap-2 text-sm text-gray-300">
                    <span aria-hidden className="mt-0.5 font-bold text-amber-500">✓</span>
                    {f}
                  </li>
                ))}
              </ul>
              <button
                type="button"
                disabled={busy}
                onClick={() => select('flame')}
                className="mt-auto w-full rounded-lg bg-amber-500 px-5 py-3 text-sm font-semibold text-black transition hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Select Flame
              </button>
            </div>
          </div>
        ) : null}

        <p className="mt-5 text-sm text-gray-500">
          Agent selection does not activate trading. You will review your setup before activation.
        </p>

        <Link href="/enroll/broker" className="mt-4 inline-block text-sm text-gray-400 hover:text-white">
          ← Back to brokerage
        </Link>
      </div>
    </EnrollShell>
  )
}
