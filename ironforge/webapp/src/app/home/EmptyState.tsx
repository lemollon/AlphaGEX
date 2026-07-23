'use client'

import Link from 'next/link'
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'

/**
 * Perspective-4 screen — a signed-in customer with no bot assigned yet.
 *
 * This is where EVERY new signup currently lands (bots are provisioned by an
 * operator), so it must never read as a blank or broken dashboard. It tells the
 * person exactly where they are, what happens next, and gives them something real
 * to do in the meantime (see the track record, join the community).
 */

interface CustomerMe {
  ok: boolean
  customer?: { email?: string; onboardingStep?: string }
}

/** Funnel order — used to mark checklist items done vs pending. */
const STEP_ORDER = [
  'account_created', 'email_verified', 'legal_accepted', 'risk_assessed', 'brokerage_connected',
]
function reached(step: string | undefined, target: string): boolean {
  if (!step) return false
  const i = STEP_ORDER.indexOf(step)
  const j = STEP_ORDER.indexOf(target)
  return i >= 0 && j >= 0 && i >= j
}

function Check({ done }: { done: boolean }) {
  return done ? (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"
      strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5 shrink-0 text-emerald-500">
      <circle cx="12" cy="12" r="10" className="text-emerald-500/30" stroke="currentColor" />
      <path d="m8 12 3 3 5-6" />
    </svg>
  ) : (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
      className="h-5 w-5 shrink-0 text-amber-500/70">
      <circle cx="12" cy="12" r="9" strokeDasharray="3 3" />
    </svg>
  )
}

function TeaserCard({ k, name, tag, hex, glow }: {
  k: 'spark' | 'flame'; name: string; tag: string; hex: string; glow: string
}) {
  return (
    <Link href="/track-record"
      className="group relative flex items-center gap-3 overflow-hidden rounded-xl border border-white/10 bg-forge-card/70 p-4 transition hover:border-white/25">
      <div className="pointer-events-none absolute -right-6 -top-6 h-24 w-24 rounded-full opacity-40 blur-2xl" style={{ background: glow }} />
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={`/home/${k}-mascot-glow.png`} alt="" className="h-11 w-11 shrink-0"
        style={{ filter: `drop-shadow(0 0 10px ${glow})` }} />
      <div className="min-w-0">
        <div className="font-display text-lg leading-none text-white">{name}</div>
        <div className="mt-0.5 truncate text-xs text-gray-500">{tag}</div>
      </div>
      <span className="ml-auto shrink-0 text-xs font-semibold" style={{ color: hex }}>
        Track record →
      </span>
    </Link>
  )
}

export default function EmptyState() {
  const { data } = useSWR<CustomerMe>('/api/auth/customer-me', fetcher)
  const step = data?.customer?.onboardingStep
  const email = data?.customer?.email
  const firstName = email ? email.split('@')[0].split(/[.\-_]/)[0] : ''
  const greet = firstName ? firstName.charAt(0).toUpperCase() + firstName.slice(1) : 'there'

  const checklist = [
    { label: 'Account created', done: true },
    { label: 'Email verified', done: reached(step, 'email_verified') || Boolean(step) },
    { label: 'Disclosures accepted', done: reached(step, 'legal_accepted') },
    { label: 'Risk profile complete', done: reached(step, 'risk_assessed') },
    { label: 'Brokerage connected', done: reached(step, 'brokerage_connected') },
  ]
  const nextStep = checklist.find((c) => !c.done)

  return (
    <div className="flex flex-col gap-5">
      {/* welcome + status */}
      <div className="relative overflow-hidden rounded-2xl border border-amber-600/30 bg-gradient-to-br from-amber-950/25 via-forge-card to-forge-card p-6 sm:p-8">
        <div className="pointer-events-none absolute -right-10 -top-10 h-44 w-44 rounded-full bg-amber-600/10 blur-3xl" />
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-amber-500">You&apos;re in</p>
        <h1 className="mt-2 font-display text-2xl text-white sm:text-3xl">Welcome to IronForge, {greet}.</h1>
        <p className="mt-2 max-w-xl text-sm leading-relaxed text-gray-300">
          Your account is live. Your strategy isn&apos;t running <span className="text-white">yet</span> —
          there&apos;s one last step on our side, and then a bot goes to work on your account. Here&apos;s
          exactly where things stand.
        </p>
      </div>

      <div className="grid gap-5 lg:grid-cols-[1fr_360px]">
        {/* left: progress + what's next */}
        <div className="flex flex-col gap-5">
          <div className="rounded-2xl border border-white/10 bg-forge-card p-6">
            <h2 className="font-display text-lg text-white">Your setup</h2>
            <ul className="mt-4 flex flex-col gap-3">
              {checklist.map((c) => (
                <li key={c.label} className="flex items-center gap-3">
                  <Check done={c.done} />
                  <span className={`text-sm ${c.done ? 'text-gray-300' : 'text-white'}`}>{c.label}</span>
                  {!c.done && c === nextStep && (
                    <span className="ml-auto rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-400">
                      next
                    </span>
                  )}
                </li>
              ))}
              <li className="flex items-center gap-3">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
                  className="h-5 w-5 shrink-0 text-amber-500/70"><circle cx="12" cy="12" r="9" strokeDasharray="3 3" /></svg>
                <span className="text-sm text-white">Your bot is activated</span>
                <span className="ml-auto text-[11px] text-gray-500">we handle this</span>
              </li>
            </ul>

            {nextStep?.label === 'Brokerage connected' && (
              <Link href="/onboarding/brokerage"
                className="mt-5 inline-block rounded-md bg-amber-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-amber-500">
                Connect your brokerage
              </Link>
            )}
          </div>

          <div className="rounded-2xl border border-white/10 bg-forge-card p-6">
            <h2 className="font-display text-lg text-white">What happens next</h2>
            <ol className="mt-4 flex flex-col gap-4">
              {[
                ['We finish activation', 'We attach a strategy to your account and switch it on. You don’t need to do anything.'],
                ['Your bot starts trading', 'It places trades on your connected account under the same rules you can watch on our track record right now.'],
                ['You stay in control', 'Watch it live, pause it anytime, and keep your day. The bot does the sitting-and-waiting.'],
              ].map(([t, d], i) => (
                <li key={t} className="flex gap-3">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-amber-600/50 bg-amber-950/30 font-mono text-xs text-amber-400">{i + 1}</span>
                  <div>
                    <div className="text-sm font-semibold text-white">{t}</div>
                    <div className="mt-0.5 text-xs leading-relaxed text-gray-400">{d}</div>
                  </div>
                </li>
              ))}
            </ol>
            <p className="mt-5 rounded-lg border border-amber-900/40 bg-amber-950/15 px-4 py-3 text-xs text-amber-200/80">
              We&apos;ll email you the moment your bot is live — you don&apos;t need to keep checking back.
            </p>
          </div>
        </div>

        {/* right: what you can do now */}
        <div className="flex flex-col gap-5">
          <div className="rounded-2xl border border-white/10 bg-forge-card p-6">
            <h2 className="font-display text-lg text-white">While you wait</h2>
            <p className="mt-1 text-xs text-gray-500">See exactly what your bot will be doing.</p>
            <div className="mt-4 flex flex-col gap-3">
              <TeaserCard k="spark" name="SPARK" tag="Next-day SPY spreads" hex="#3B9EFF" glow="rgba(59,158,255,0.5)" />
              <TeaserCard k="flame" name="FLAME" tag="Two-day SPY put credit spreads" hex="#E8531F" glow="rgba(232,83,31,0.5)" />
            </div>
            <Link href="/track-record"
              className="mt-4 block rounded-md border border-amber-600/50 px-4 py-2.5 text-center text-sm font-semibold text-amber-500 transition hover:bg-amber-600/10">
              See the full track record
            </Link>
          </div>

          <div className="rounded-2xl border border-white/10 bg-forge-card p-6">
            <h2 className="font-display text-lg text-white">Meet the other traders</h2>
            <p className="mt-1 text-sm leading-relaxed text-gray-400">
              The Forge Community is where members compare notes, ask questions, and see what&apos;s
              coming next.
            </p>
            <Link href="/community"
              className="mt-4 block rounded-md bg-amber-600 px-4 py-2.5 text-center text-sm font-semibold text-white transition hover:bg-amber-500">
              Visit the Forge Community
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}
