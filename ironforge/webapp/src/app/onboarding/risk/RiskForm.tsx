'use client'

import { useState } from 'react'
import Link from 'next/link'
import { Wordmark } from '@/components/Brand'
import {
  RISK_QUESTIONS,
  BOT_RATIONALE,
  type RiskAnswers,
  type RiskTier,
  type RecommendedBot,
} from '@/lib/onboarding/risk-scoring'

interface RiskResult {
  tier: RiskTier
  recommendedBot: RecommendedBot
  caution: boolean
}

const TIER_BLURB: Record<RiskTier, string> = {
  Conservative: 'You prioritize protecting capital over chasing returns.',
  Moderate: 'You balance growth with a tolerance for some swings.',
  Aggressive: 'You seek higher returns and can stomach larger swings.',
}

export default function RiskForm() {
  const [answers, setAnswers] = useState<RiskAnswers>({})
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<RiskResult | null>(null)

  const allAnswered = RISK_QUESTIONS.every((q) => answers[q.key])

  function choose(key: string, id: string) {
    setAnswers((a) => ({ ...a, [key]: id }))
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!allAnswered || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      const res = await fetch('/api/onboarding/risk-assessment', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answers }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok || !data.ok) {
        setError(data.error || 'Something went wrong. Please try again.')
        setSubmitting(false)
        return
      }
      setResult({ tier: data.tier, recommendedBot: data.recommendedBot, caution: data.caution })
    } catch {
      setError('Network error. Please try again.')
      setSubmitting(false)
    }
  }

  if (result) {
    return (
      <div className="min-h-screen bg-forge-bg bg-ember-glow px-4 py-12">
        <div className="mx-auto max-w-lg">
          <div className="mb-6 flex justify-center"><Link href="/" aria-label="IronForge home"><Wordmark /></Link></div>
          <div className="rounded-2xl border border-white/10 bg-forge-card/90 p-8 shadow-2xl">
            <p className="text-xs font-semibold uppercase tracking-wide text-amber-500">Your risk profile</p>
            <h1 className="mt-1 text-2xl font-bold text-white">
              You&apos;re a <span className="text-amber-500">{result.tier}</span> investor
            </h1>
            <p className="mt-2 text-sm leading-relaxed text-gray-400">{TIER_BLURB[result.tier]}</p>

            <div className="mt-6 rounded-xl border border-amber-900/40 bg-amber-950/20 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-amber-500">We recommend</p>
              <p className="mt-1 text-lg font-bold text-white">{result.recommendedBot}</p>
              <p className="mt-1 text-sm text-gray-400">{BOT_RATIONALE[result.recommendedBot]}</p>
            </div>

            {result.caution && (
              <p className="mt-4 rounded-md border border-amber-700/40 bg-amber-950/30 px-3 py-2 text-xs leading-relaxed text-amber-200">
                Options trading carries a substantial risk of loss. We&apos;ve recommended our most
                conservative approach — consider starting small and never trade money you can&apos;t afford to lose.
              </p>
            )}

            <p className="mt-6 text-[11px] text-gray-500">
              This recommendation is a starting point. You&apos;ll confirm your strategy before anything is activated.
            </p>

            {/* Continues to the brokerage step, which is the next stage of the
                canonical resolver. This button used to jump straight to /home,
                so a new customer silently skipped brokerage connect AND the
                completion screen — the funnel dead-ended on its own dashboard. */}
            <Link
              href="/onboarding/brokerage"
              className="mt-6 flex w-full items-center justify-center rounded-md bg-amber-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-amber-500"
            >
              Continue to brokerage
            </Link>
            <p className="mt-4 text-center text-xs text-gray-500">
              Next you&apos;ll connect a brokerage. You can skip it and come back later.
            </p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-forge-bg bg-ember-glow px-4 py-12">
      <div className="mx-auto max-w-lg">
        <div className="mb-6 flex justify-center"><Link href="/" aria-label="IronForge home"><Wordmark /></Link></div>
        <div className="rounded-2xl border border-white/10 bg-forge-card/90 p-6 shadow-2xl sm:p-8">
          <p className="text-xs font-semibold uppercase tracking-wide text-amber-500">Step 3 · Risk profile</p>
          <h1 className="mt-1 text-2xl font-bold text-white">Find your best-fit bot</h1>
          <p className="mt-2 text-sm leading-relaxed text-gray-400">
            Answer six quick questions and we&apos;ll recommend the IronForge bot that matches your
            risk profile. This helps you choose — it doesn&apos;t activate anything.
          </p>

          <form onSubmit={onSubmit} noValidate className="mt-6 space-y-6">
            {RISK_QUESTIONS.map((q, i) => (
              <fieldset key={q.key}>
                <legend className="text-sm font-semibold text-white">
                  {i + 1}. {q.label}
                </legend>
                <div className="mt-2 space-y-2">
                  {q.options.map((o) => {
                    const selected = answers[q.key] === o.id
                    return (
                      <label
                        key={o.id}
                        className={`flex cursor-pointer items-center gap-2.5 rounded-lg border px-3 py-2.5 text-sm transition ${
                          selected
                            ? 'border-amber-500 bg-amber-950/20 text-white'
                            : 'border-white/10 bg-black/20 text-gray-300 hover:border-white/20'
                        }`}
                      >
                        <input
                          type="radio"
                          name={q.key}
                          value={o.id}
                          checked={selected}
                          onChange={() => choose(q.key, o.id)}
                          className="h-4 w-4 shrink-0 accent-amber-600"
                        />
                        <span>{o.label}</span>
                      </label>
                    )
                  })}
                </div>
              </fieldset>
            ))}

            {error && (
              <p className="rounded-md border border-red-700/40 bg-red-950/30 px-3 py-2 text-xs text-red-300">{error}</p>
            )}

            <button
              type="submit"
              disabled={!allAnswered || submitting}
              className="flex w-full items-center justify-center rounded-md bg-amber-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-amber-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {submitting ? 'Scoring…' : 'See my recommendation'}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
