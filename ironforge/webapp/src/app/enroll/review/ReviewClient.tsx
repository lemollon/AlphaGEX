'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import EnrollShell from '../EnrollShell'
import { useEnrollment } from '../useEnrollment'
import { AGENT_CONFIG_KEY } from '../agent/AgentClient'

/**
 * ACT-SPARK-01 / ACT-FLAME-01 — Review and activate (July 29 handoff).
 *
 * Everything shown here is LIVE preview data from the server — the capital figures
 * are computed from current buying power × the active rule version and are never
 * hard-coded (the mockup's 20% / $4,972.04 are illustrative). Consent binds to the
 * preview hash; the server recomputes it at activation and refuses on drift
 * (PREVIEW_STALE → refresh-and-retry here, never a dead end).
 *
 * The Idempotency-Key is generated ONCE per screen visit and reused for retries of
 * the same intent — a fresh key per click would defeat the double-activation guard.
 */

interface Blocker {
  code: string
  message: string
  remediable: boolean
}

interface Preview {
  preview_hash: string
  snapshot: {
    agent: string
    rule_version: string
    account_mask: string
    max_deployment_cents: number
    buying_power_cents: number
    plan: { name: string; price_monthly: number } | null
    trial: { eligible_days_total: number }
  }
  can_activate: boolean
  blockers: Blocker[]
}

/** Where each remediable blocker is fixed. */
const BLOCKER_ROUTE: Record<string, string> = {
  MEMBERSHIP_NOT_ACTIVE: '/enroll/billing',
  PAYMENT_METHOD_INVALID: '/enroll/billing',
  LEGAL_ACCEPTANCE_STALE: '/enroll/legal',
  BROKERAGE_NOT_CONNECTED: '/enroll/broker',
  BROKER_ACCOUNT_INELIGIBLE: '/enroll/broker',
  AGENT_CONFIG_NOT_VALID: '/enroll/agent',
}

function usd(cents: number): string {
  return (cents / 100).toLocaleString('en-US', { style: 'currency', currency: 'USD' })
}

export default function ReviewClient() {
  const { enrollment, busy, setBusy, error, setError, router } = useEnrollment('review')
  const [configId, setConfigId] = useState<string | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [riskAck, setRiskAck] = useState(false)
  const [authAck, setAuthAck] = useState(false)
  const [staleNotice, setStaleNotice] = useState(false)
  const [blockers, setBlockers] = useState<Blocker[]>([])
  // ONE key per screen visit — reused across retries of this same activation intent.
  const idemKey = useRef<string>(crypto.randomUUID())

  useEffect(() => {
    if (!enrollment) return
    let id: string | null = null
    try {
      id = sessionStorage.getItem(AGENT_CONFIG_KEY)
    } catch {
      /* handled below */
    }
    if (!id) {
      router.replace('/enroll/agent')
      return
    }
    setConfigId(id)
  }, [enrollment, router])

  const loadPreview = useCallback(async () => {
    if (!configId) return
    const res = await fetch('/api/v1/activations/preview', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ config_id: configId }),
    })
    const body = await res.json().catch(() => null)
    if (!res.ok) throw new Error(body?.message || 'Could not build your review.')
    setPreview(body as Preview)
    setBlockers((body as Preview).blockers ?? [])
  }, [configId])

  useEffect(() => {
    if (!configId) return
    loadPreview().catch((e) => setError(e instanceof Error ? e.message : 'Could not build your review.'))
  }, [configId, loadPreview, setError])

  async function activate() {
    if (!configId || !preview) return
    setBusy(true)
    setError(null)
    setStaleNotice(false)
    try {
      const res = await fetch('/api/v1/activations', {
        method: 'POST',
        headers: { 'content-type': 'application/json', 'Idempotency-Key': idemKey.current },
        body: JSON.stringify({
          config_id: configId,
          preview_hash: preview.preview_hash,
          risk_acknowledged: riskAck,
          authorization_acknowledged: authAck,
        }),
      })
      const body = await res.json().catch(() => null)
      if (res.ok && body?.ok) {
        try {
          sessionStorage.removeItem(AGENT_CONFIG_KEY)
        } catch {
          /* nothing to clean */
        }
        router.push(`/agents/${body.agent}?welcome=${body.agent}`)
        return
      }
      // Blocked: render every blocker; PREVIEW_STALE additionally refreshes the
      // snapshot so the customer re-reviews CURRENT numbers, not an error dead end.
      const got: Blocker[] = Array.isArray(body?.blockers) ? body.blockers : []
      setBlockers(got)
      if (got.some((b) => b.code === 'PREVIEW_STALE')) {
        setStaleNotice(true)
        await loadPreview()
      } else if (got.length === 0) {
        setError(body?.message || 'Activation could not be completed. Please try again.')
      }
      setBusy(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Activation could not be completed. Please try again.')
      setBusy(false)
    }
  }

  const agent = preview?.snapshot.agent ?? 'spark'
  const isSpark = agent === 'spark'
  const agentName = isSpark ? 'Spark' : 'Flame'
  const pct =
    preview && preview.snapshot.buying_power_cents > 0
      ? Math.round((preview.snapshot.max_deployment_cents / preview.snapshot.buying_power_cents) * 100)
      : null
  const visibleBlockers = blockers.filter((b) => b.code !== 'ACKNOWLEDGMENTS_MISSING' && b.code !== 'PREVIEW_STALE')
  const canActivate = riskAck && authAck && !busy && preview != null

  return (
    <EnrollShell
      headline="Review. Authorize. Go live."
      subline="Confirm your setup and activate automated trading."
      maxWidthClass="max-w-3xl"
    >
      <div className="rounded-2xl border border-forge-border bg-forge-card/60 p-6 lg:p-8">
        <h2 className="text-2xl font-bold text-white">Review and activate</h2>
        <p className="mt-1 text-sm text-gray-400">Confirm your configuration before enabling automated execution.</p>

        {error ? (
          <p className="mt-4 rounded-md border border-red-700/40 bg-red-950/30 px-3 py-2 text-sm text-red-300">{error}</p>
        ) : null}
        {staleNotice ? (
          <p className="mt-4 rounded-md border border-amber-500/40 bg-amber-950/30 px-3 py-2 text-sm text-amber-300">
            Something changed while you were reviewing — the summary below has been refreshed. Please review it again.
          </p>
        ) : null}

        {!preview && !error ? (
          <div className="mt-6 h-80 animate-pulse rounded-2xl border border-forge-border bg-forge-card/40" />
        ) : null}

        {preview ? (
          <>
            {/* Checks banner */}
            {visibleBlockers.length === 0 ? (
              <p
                className={`mt-5 flex items-center gap-2 rounded-lg border px-4 py-2.5 text-sm ${
                  isSpark ? 'border-spark/40 text-gray-200' : 'border-amber-500/40 text-gray-200'
                }`}
              >
                <span aria-hidden className={`h-2 w-2 rounded-full ${isSpark ? 'bg-spark' : 'bg-amber-500'}`} />
                All required checks passed
              </p>
            ) : (
              <div className="mt-5 rounded-lg border border-red-700/40 bg-red-950/20 p-4">
                <p className="text-sm font-semibold text-red-300">Before you can activate:</p>
                <ul className="mt-2 space-y-1.5">
                  {visibleBlockers.map((b) => (
                    <li key={b.code} className="flex flex-wrap items-baseline gap-2 text-sm text-gray-300">
                      <span>{b.message}</span>
                      {b.remediable && BLOCKER_ROUTE[b.code] ? (
                        <Link href={BLOCKER_ROUTE[b.code]} className="text-xs font-semibold text-amber-500 hover:text-amber-400">
                          Fix this →
                        </Link>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="mt-5 grid gap-5 md:grid-cols-2">
              {/* Trading setup */}
              <div className="rounded-xl border border-forge-border bg-black/20 p-5">
                <h3 className="text-sm font-bold text-white">Trading setup</h3>
                <dl className="mt-3 space-y-2.5 text-sm">
                  <div className="flex justify-between gap-3">
                    <dt className="text-gray-500">Membership</dt>
                    <dd className="text-gray-200">Forge Automate</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-gray-500">Agent</dt>
                    <dd>
                      <span
                        className={`rounded-md px-2 py-0.5 text-xs font-bold ${
                          isSpark ? 'bg-spark text-black' : 'bg-amber-500 text-black'
                        }`}
                      >
                        {agentName}
                      </span>
                    </dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-gray-500">Strategy</dt>
                    <dd className="text-gray-200">Rules-based iron condor</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-gray-500">Brokerage account</dt>
                    <dd className="font-mono text-gray-200">{preview.snapshot.account_mask || '—'}</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-gray-500">Account eligibility</dt>
                    <dd className="text-emerald-400">✓ Options enabled</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-gray-500">Maximum capital deployment</dt>
                    <dd className="text-right text-gray-200">
                      {pct != null ? `${pct}% · ` : ''}
                      {usd(preview.snapshot.max_deployment_cents)}
                    </dd>
                  </div>
                </dl>
              </div>

              {/* Trial & billing */}
              <div className="rounded-xl border border-forge-border bg-black/20 p-5">
                <h3 className="text-sm font-bold text-white">Trial &amp; billing</h3>
                <dl className="mt-3 space-y-2.5 text-sm">
                  <div className="flex justify-between gap-3">
                    <dt className="text-gray-500">Due today</dt>
                    <dd className="text-gray-200">$0.00</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-gray-500">Free trial</dt>
                    <dd className="text-gray-200">{preview.snapshot.trial.eligible_days_total} eligible trading days</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-gray-500">Trial begins</dt>
                    <dd className="text-gray-200">When trading is activated</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-gray-500">After trial</dt>
                    <dd className="text-gray-200">
                      {preview.snapshot.plan ? `$${preview.snapshot.plan.price_monthly}/month` : '—'}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-gray-500">Membership</dt>
                    <dd className="text-gray-200">Cancel anytime</dd>
                  </div>
                </dl>
                <p
                  className={`mt-4 rounded-lg border px-3 py-2.5 text-xs leading-relaxed ${
                    isSpark ? 'border-spark/50 text-spark' : 'border-amber-500/50 text-amber-500'
                  }`}
                >
                  Activation authorizes IronForge to submit and manage orders under the selected {agentName}{' '}
                  configuration.
                </p>
              </div>
            </div>

            {/* Acknowledgments */}
            <div className="mt-5 space-y-3">
              <label className="flex items-start gap-3 text-sm text-gray-200">
                <input
                  type="checkbox"
                  checked={riskAck}
                  onChange={(e) => setRiskAck(e.target.checked)}
                  className="mt-1 h-4 w-4 shrink-0 accent-amber-500"
                />
                I understand automated options trading involves substantial risk.
              </label>
              <label className="flex items-start gap-3 text-sm text-gray-200">
                <input
                  type="checkbox"
                  checked={authAck}
                  onChange={(e) => setAuthAck(e.target.checked)}
                  className="mt-1 h-4 w-4 shrink-0 accent-amber-500"
                />
                I authorize IronForge to submit and manage orders using this configuration.
              </label>
            </div>

            <button
              type="button"
              disabled={!canActivate}
              onClick={activate}
              className={`mt-6 w-full rounded-lg px-5 py-3 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 ${
                isSpark ? 'bg-spark text-black hover:bg-spark-dark' : 'bg-amber-500 text-black hover:bg-amber-400'
              }`}
            >
              {busy ? 'Activating…' : `Activate ${agentName}`}
            </button>
            <p className="mt-2 text-center text-xs text-gray-500">
              Trading will begin only when {agentName} identifies an eligible opportunity. You can pause automation at
              any time.
            </p>

            <Link href="/enroll/agent" className="mt-5 inline-block text-sm text-gray-400 hover:text-white">
              ← Back to agent selection
            </Link>
          </>
        ) : null}
      </div>
    </EnrollShell>
  )
}
