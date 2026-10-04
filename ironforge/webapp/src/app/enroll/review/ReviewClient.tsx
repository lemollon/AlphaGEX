'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import EnrollShell from '../EnrollShell'
import { useEnrollment } from '../useEnrollment'
import { AGENT_CONFIG_KEY } from '../agent/AgentClient'
import { EMBER_AGENT } from '@/lib/agents/ember'

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
  const isEmber = agent === 'ember'
  const agentName = isSpark ? 'Spark' : isEmber ? EMBER_AGENT.name : 'Flame'
  // Color law: Spark = spark token, Flame = brand amber, Ember = the --ember token
  // (purple), applied inline since Tailwind has no `ember-*` scale (unlike spark/
  // amber, which are already remapped design tokens — see tailwind.config.ts).
  const agentAccentStyle = isSpark
    ? undefined // the `spark-*` Tailwind classes below already cover this case
    : isEmber
      ? { color: EMBER_AGENT.accent }
      : undefined // amber-* Tailwind classes cover Flame
  const pct =
    preview && preview.snapshot.buying_power_cents > 0
      ? Math.round((preview.snapshot.max_deployment_cents / preview.snapshot.buying_power_cents) * 100)
      : null
  const visibleBlockers = blockers.filter((b) => b.code !== 'ACKNOWLEDGMENTS_MISSING' && b.code !== 'PREVIEW_STALE')
  // Gate on the server's own verdict (audit minor): the button used to be live even
  // while "Before you can activate:" listed blockers, so clicking just re-rendered
  // the same list. can_activate is the authority; ACKNOWLEDGMENTS_MISSING is the only
  // blocker the checkboxes below clear, so it doesn't count here.
  const serverBlocks = visibleBlockers.length > 0 || (preview != null && !preview.can_activate)
  const canActivate = riskAck && authAck && !busy && preview != null && !serverBlocks

  return (
    <EnrollShell
      headline="Review. Authorize. Go live."
      subline="Confirm your setup and activate automated trading."
      maxWidthClass="max-w-3xl"
      step="review"
      enrollment={enrollment}
    >
        {error ? <p className="err" style={{ marginBottom: 14 }}>{error}</p> : null}
        {staleNotice ? (
          <p className="help" style={{ marginBottom: 14, color: 'var(--warn)' }}>
            Something changed while you were reviewing — the summary below has been refreshed. Please review it again.
          </p>
        ) : null}

        {!preview && !error ? <div className="card pad" style={{ height: 320 }} /> : null}

        {preview ? (
          <>
            {/* Checks banner */}
            {visibleBlockers.length === 0 ? (
              <p className="check-row ok" style={{ marginTop: 20 }}>
                <span
                  aria-hidden
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: '50%',
                    display: 'inline-block',
                    background: isSpark ? 'var(--spark)' : isEmber ? EMBER_AGENT.accent : 'var(--flame)',
                  }}
                />
                All required checks passed
              </p>
            ) : (
              <div className="check-row bad" style={{ display: 'block', marginTop: 20 }}>
                <p style={{ fontWeight: 600 }}>Before you can activate:</p>
                <ul style={{ marginTop: 8, display: 'grid', gap: 6 }}>
                  {visibleBlockers.map((b) => (
                    <li key={b.code} style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'baseline' }}>
                      <span>{b.message}</span>
                      {b.remediable && BLOCKER_ROUTE[b.code] ? (
                        <Link href={BLOCKER_ROUTE[b.code]} className="link" style={{ fontSize: '.78rem' }}>
                          Fix this →
                        </Link>
                      ) : !b.remediable ? (
                        /* Non-remediable (e.g. KILL_SWITCH_ENGAGED, a platform pause):
                           there's no self-service fix, but a dead end with no next
                           action is worse (audit M12). Point to support. */
                        <a href="/support" className="link" style={{ fontSize: '.78rem' }}>
                          Contact support →
                        </a>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="row2" style={{ marginTop: 20 }}>
              {/* Trading setup */}
              <div className="card pad">
                <h3>Trading setup</h3>
                <dl className="rv" style={{ marginTop: 10, gap: 10, display: 'grid' }}>
                  <div className="sum-row"><dt>Membership</dt><dd>{isEmber ? 'Ember (free)' : 'Forge Automate'}</dd></div>
                  <div className="sum-row">
                    <dt>Agent</dt>
                    <dd>
                      <span
                        className="badge"
                        style={{
                          backgroundColor: isSpark ? 'var(--spark)' : isEmber ? EMBER_AGENT.accent : 'var(--flame)',
                          color: '#fff',
                        }}
                      >
                        {agentName}
                      </span>
                    </dd>
                  </div>
                  <div className="sum-row"><dt>Strategy</dt><dd>Rules-based iron condor</dd></div>
                  <div className="sum-row"><dt>Brokerage account</dt><dd className="mono">{preview.snapshot.account_mask || '—'}</dd></div>
                  <div className="sum-row"><dt>Account eligibility</dt><dd style={{ color: 'var(--up)' }}>✓ Options enabled</dd></div>
                  <div className="sum-row">
                    <dt>Maximum capital deployment</dt>
                    <dd className="num">
                      {pct != null ? `${pct}% · ` : ''}
                      {usd(preview.snapshot.max_deployment_cents)}
                    </dd>
                  </div>
                </dl>
              </div>

              {/* Trial & billing */}
              <div className="card pad">
                <h3>Trial &amp; billing</h3>
                <dl className="rv" style={{ marginTop: 10, gap: 10, display: 'grid' }}>
                  <div className="sum-row"><dt>Due today</dt><dd>$0.00</dd></div>
                  {isEmber ? (
                    <div className="sum-row"><dt>Free trial</dt><dd>Always free</dd></div>
                  ) : (
                    <div className="sum-row"><dt>Free trial</dt><dd>{preview.snapshot.trial.eligible_days_total} eligible trading days</dd></div>
                  )}
                  <div className="sum-row"><dt>Trial begins</dt><dd>When trading is activated</dd></div>
                  <div className="sum-row">
                    <dt>After trial</dt>
                    <dd>
                      {isEmber
                        ? 'Free · no card needed'
                        : preview.snapshot.plan
                          ? `$${preview.snapshot.plan.price_monthly}/month`
                          : '—'}
                    </dd>
                  </div>
                  <div className="sum-row"><dt>Membership</dt><dd>{isEmber ? 'One Ember account, $500–$2,000 capital' : 'Cancel anytime'}</dd></div>
                </dl>
                <p
                  className="help"
                  style={{
                    marginTop: 14,
                    padding: '10px 12px',
                    borderRadius: 'var(--r-sm)',
                    background: 'var(--bg-2)',
                    color: isSpark ? 'var(--spark)' : isEmber ? EMBER_AGENT.accent : 'var(--flame)',
                  }}
                >
                  Activation authorizes IronForge to submit and manage orders under the selected {agentName}{' '}
                  configuration.
                </p>
              </div>
            </div>

            {/* Acknowledgments */}
            <div className="stack" style={{ marginTop: 20 }}>
              <label className="field" style={{ gridTemplateColumns: '18px 1fr', display: 'grid', alignItems: 'start' }}>
                <input
                  type="checkbox"
                  checked={riskAck}
                  onChange={(e) => setRiskAck(e.target.checked)}
                  style={{ width: 16, height: 16, marginTop: 2 }}
                />
                <span style={{ fontWeight: 400 }}>I understand automated options trading involves substantial risk.</span>
              </label>
              <label className="field" style={{ gridTemplateColumns: '18px 1fr', display: 'grid', alignItems: 'start' }}>
                <input
                  type="checkbox"
                  checked={authAck}
                  onChange={(e) => setAuthAck(e.target.checked)}
                  style={{ width: 16, height: 16, marginTop: 2 }}
                />
                <span style={{ fontWeight: 400 }}>I authorize IronForge to submit and manage orders using this configuration.</span>
              </label>
            </div>

            <button
              type="button"
              disabled={!canActivate}
              onClick={activate}
              className="btn btn-block btn-lg"
              style={{
                marginTop: 24,
                backgroundColor: isSpark ? 'var(--spark)' : isEmber ? EMBER_AGENT.accent : 'var(--flame)',
                borderColor: isSpark ? 'var(--spark)' : isEmber ? EMBER_AGENT.accent : 'var(--flame)',
                color: '#fff',
              }}
            >
              {busy ? 'Activating…' : `Activate ${agentName}`}
            </button>
            <p className="help" style={{ marginTop: 10, textAlign: 'center' }}>
              Trading will begin only when {agentName} identifies an eligible opportunity. You can pause automation at
              any time.
            </p>

            <div className="nav-row">
              <Link href="/enroll/agent" className="btn">← Back to agent selection</Link>
            </div>
          </>
        ) : null}
    </EnrollShell>
  )
}
