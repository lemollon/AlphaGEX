'use client'

import useSWR, { mutate } from 'swr'
import { useState } from 'react'
import { fetcher } from '@/lib/fetcher'
import type { LiveSummary, LiveTrade } from '@/lib/live/types'
import { LIVE_BOT_LABEL, type LiveBot } from '@/lib/live/bots'
import { accentFor } from './components/accent'
import { isSwingActive } from '@/lib/live/swing'
import LiveHeader from './components/LiveHeader'
import CustomerShell from '@/components/customer/CustomerShell'
import CheckoutNotice from '@/components/customer/CheckoutNotice'
import SparkHeroCard from './components/SparkHeroCard'
import ActivationConfirmationCard from './components/ActivationConfirmationCard'
import LiveTradeCard from './components/LiveTradeCard'
import SwingTradeCards from './components/SwingTradeCards'
import NowTimelineCard from './components/NowTimelineCard'
import MarketConditionsCard from './components/MarketConditionsCard'
import TodayPerformanceChart from './components/TodayPerformanceChart'
import PauseTradingPanel from './components/PauseTradingPanel'

/** Non-customer /live conversion CTAs — one per strategy, Spark then Flame.
 *  Both link into the existing signup flow with the bot preselected. */
const SIGNUP_CTAS = [
  {
    slug: 'spark',
    name: 'Spark',
    tagline: 'Next-day SPY spreads',
    pill: 'Live',
    mascot: '/home/spark-mascot-glow.png',
    cardClass: 'border-spark/40 bg-spark/5 hover:bg-spark/10',
    pillClass: 'bg-spark/20 text-spark',
    btnClass: 'bg-spark group-hover:brightness-110',
  },
  {
    slug: 'flame',
    name: 'Flame',
    tagline: 'Two-day SPY put credit spreads',
    pill: 'Paper',
    mascot: '/home/flame-mascot-glow.png',
    cardClass: 'border-flame/40 bg-flame/5 hover:bg-flame/10',
    pillClass: 'bg-flame/20 text-flame',
    btnClass: 'bg-flame group-hover:brightness-110',
  },
] as const

export default function LiveClient({ account }: { account: LiveBot }) {
  // Agent workspace (UAT-008 / IF-NAV-001): the account is FIXED by the route
  // (/agents/spark, /agents/flame) — no in-page switcher. Navigation between
  // agents happens in the left rail, where each agent is a top-level item.
  const summaryKey = `/api/live/summary?account=${account}`
  const tradeKey = `/api/live/trade?account=${account}`
  const { data: summary, error: summaryError } = useSWR<LiveSummary>(
    summaryKey, fetcher, { refreshInterval: 60_000 },
  )
  const { data: trade, error: tradeError } = useSWR<LiveTrade>(
    tradeKey, fetcher, { refreshInterval: 30_000 },
  )
  const [pausePending, setPausePending] = useState(false)
  // The whole surface takes the active bot's identity colour (Spark blue / Flame orange).
  const accent = accentFor(account)

  async function handlePauseToggle(nextPaused: boolean) {
    setPausePending(true)
    try {
      const res = await fetch(`/api/${account}/production-pause`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          paused: nextPaused,
          reason: nextPaused ? 'customer_pause' : 'customer_resume',
          by: 'live_page',
        }),
      })
      if (!res.ok) throw new Error(`${res.status}`)
      await Promise.all([mutate(summaryKey), mutate(tradeKey)])
    } finally {
      setPausePending(false)
    }
  }

  // Drives the empty-state CTA. customerId is non-null only for a signed-in
  // customer, which is exactly the distinction the CTA needs: an existing account
  // must never be sent back through account creation.
  const signedIn = !!summary?.viewer?.customerId

  return (
    <CustomerShell membership={summary?.membership ?? null}>
          {/* Where a bot purchase lands (`?welcome=spark|flame`). The subscription row
              is written by the Stripe webhook, so without this a customer who just paid
              can briefly see a dashboard that says they own nothing. */}
          <CheckoutNotice labels={LIVE_BOT_LABEL} />
          <LiveHeader viewer={summary?.viewer ?? null} />
          {/* Billing needs attention (audit M11): a failed payment previously produced
              NO customer-facing state anywhere in the workspace. */}
          {summary?.membership?.badge === 'Payment due' && (
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-600/40 bg-amber-950/25 px-4 py-3">
              <p className="text-sm text-amber-200">
                Your last payment didn’t go through. Update your card to keep {LIVE_BOT_LABEL[account]} running.
              </p>
              <a href="/account/billing" className="rounded-md bg-amber-500 px-3 py-1.5 text-xs font-semibold text-black transition hover:bg-amber-400">
                Update payment
              </a>
            </div>
          )}
          {summary?.empty && summary.activation_confirmation ? (
            /* DASH-FIRST-01, empty-viewer case: a JUST-ACTIVATED customer has no
               ironforge_customer_bots mapping yet, so the summary is empty — but
               showing them the "Put a bot to work" conversion CTAs would read as
               "your activation didn't happen". The confirmation card is the truthful
               state: authorized, waiting, account provisioning in progress. */
            <div className="mt-4 flex flex-col gap-4">
              <ActivationConfirmationCard confirmation={summary.activation_confirmation} />
              <div className="rounded-xl border border-forge-border bg-forge-card/60 p-5 text-sm leading-relaxed text-gray-400">
                Your dashboard is being provisioned — live trade data appears here once your account
                is fully linked. Nothing is required from you.
              </div>
            </div>
          ) : summary?.empty ? (
            /* No bot mapped — a conversion surface, not a dashboard. Customers WITH
               a mapped bot never reach this branch.

               Two very different visitors land here and they must not get the same
               CTA. This used to send everyone to /signup?bot=..., so a SIGNED-IN
               customer clicking "Sign up" on their own dashboard was handed the
               create-an-account form and asked for their name, email and password
               again — for an account they were already logged into. The old comment
               said "anonymous / no bot mapped" as if those were one case; they are
               not. Every other surface (sidebar ADD chips, /onboarding/complete,
               /performance, /account/billing) already routes a signed-in customer to
               /live/{bot}/open; this was the one that didn't. */
            <div className="mt-4">
              <div className="text-center">
                <h2 className="font-display text-2xl tracking-wide text-white">Put a bot to work</h2>
                <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-gray-400">
                  Start a dedicated account for a strategy and it trades the same disciplined
                  rules every session.
                </p>
              </div>
              <div className="mx-auto mt-6 grid max-w-xl gap-4">
                {SIGNUP_CTAS.map((c) => (
                  <a
                    key={c.slug}
                    // Cutover (7/30): a signed-in viewer on the EMPTY state owns no
                    // strategy, so their door is the enrollment funnel — /live/{bot}/open
                    // remains only for existing owners adding a second bot (bundle).
                    href={signedIn ? '/enroll' : `/signup?bot=${c.slug}`}
                    className={`group flex items-center gap-4 rounded-xl border p-5 transition ${c.cardClass}`}
                  >
                    <img src={c.mascot} alt="" className="h-14 w-14 shrink-0" />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-base font-bold text-white">{c.name}</span>
                        <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${c.pillClass}`}>
                          {c.pill}
                        </span>
                      </div>
                      <p className="mt-0.5 text-sm text-gray-400">{c.tagline}</p>
                    </div>
                    <span className={`shrink-0 rounded-md px-4 py-2 text-sm font-semibold text-white transition ${c.btnClass}`}>
                      {signedIn ? 'Open Account' : 'Sign up'}
                    </span>
                  </a>
                ))}
              </div>
            </div>
          ) : summaryError && !summary ? (
            <div className="mt-4 rounded-xl border border-forge-border bg-forge-card/80 p-6 text-sm text-gray-400">
              Live data is temporarily unavailable. We&apos;re on it — try refreshing in a moment.
            </div>
          ) : !summary ? (
            /* LOADING. Without this branch the page fell through to the dashboard
               below while `summary` was still undefined — so a visitor who owns
               nothing was shown the full trading chrome, Pause Trading included, and
               only after the fetch resolved did it swap to the conversion surface.
               Ownership is not yet known here, so nothing that implies ownership may
               render. Skeletons carry no digits, so no figure is ever implied either. */
            <div className="mt-4 flex flex-col gap-4" aria-busy="true" aria-live="polite">
              <span className="sr-only">Loading your account…</span>
              <div className="h-[104px] animate-pulse rounded-2xl border border-forge-border bg-forge-card/40" />
              <div className="grid gap-4 lg:grid-cols-[11fr_9fr]">
                <div className="h-[320px] animate-pulse rounded-2xl border border-forge-border bg-forge-card/40" />
                <div className="h-[320px] animate-pulse rounded-2xl border border-forge-border bg-forge-card/40" />
              </div>
              <div className="h-[132px] animate-pulse rounded-2xl border border-forge-border bg-forge-card/40" />
            </div>
          ) : (
            <div className="mt-4 flex flex-col gap-4">
              {/* Paper-mode disclosure. Every number below this line (account
                  value, Today's Result, the chart) is simulated for a paper bot,
                  and the page's copy otherwise reads as real money — so this
                  banner is not optional dressing. */}
              {summary?.account.mode === 'paper' && summary.account.disclosure ? (
                <div className="order-0 flex items-start gap-2.5 rounded-xl border border-flame/30 bg-flame/10 px-4 py-3">
                  <span className="mt-px rounded bg-flame/20 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-flame">
                    Paper
                  </span>
                  <p className="text-sm leading-relaxed text-gray-300">
                    {summary.account.disclosure}
                  </p>
                </div>
              ) : null}
              <div className="order-1">
                {/* DASH-FIRST-01: the first entry after activation temporarily replaces
                    the status card with the confirmation (once per activation id — the
                    card stamps itself seen on mount); afterwards the normal runtime
                    states return. Replaces, never stacks (no second banner). */}
                {summary?.activation_confirmation ? (
                  <ActivationConfirmationCard confirmation={summary.activation_confirmation} />
                ) : (
                  <SparkHeroCard state={summary?.state ?? null} market={summary?.market ?? null} bot={account} />
                )}
              </div>
              {/* A SWING is live when two positions are open at once — yesterday's held
                  leg plus today's new one. Only SPARK swings, so only SPARK reaches this
                  branch; the single-position day is untouched below. Each card carries
                  its own timeline, so NowTimelineCard is not repeated here. */}
              {isSwingActive(trade?.positions) ? (
                <div className="order-2">
                  <SwingTradeCards positions={trade!.positions} accountValue={summary?.account?.value ?? null} />
                </div>
              ) : (
                <div className="order-2 grid gap-4 lg:grid-cols-[11fr_9fr]">
                  <LiveTradeCard trade={trade ?? null} error={Boolean(tradeError)} state={summary?.state ?? null} accent={accent} accountValue={summary?.account?.value ?? null} />
                  <NowTimelineCard state={summary?.state ?? null} openedAt={trade?.opened_at ?? null} accent={accent} />
                </div>
              )}
              {/* Mobile stacks Today Performance before Market Conditions; desktop reads Conditions first. */}
              <div className="order-4 lg:order-3">
                <MarketConditionsCard market={summary?.market ?? null} accent={accent} />
              </div>
              <div className="order-3 lg:order-4">
                <TodayPerformanceChart account={summary?.account ?? null} intraday={summary?.intraday ?? null} marketOpen={summary?.market.open ?? false} accent={accent} />
              </div>
              {/* Pause is a PRODUCTION control. /api/{bot}/production-pause answers
                  400 for any paper bot, so rendering this on Flame or Spark paper
                  gave the owner a button whose only outcome was a generic failure.
                  There is nothing to pause on a simulated account. */}
              {summary?.account.mode === 'paper' ? null : (
                <div className="order-5">
                  <PauseTradingPanel
                    state={summary?.state ?? null}
                    pending={pausePending}
                    onToggle={handlePauseToggle}
                    accent={accent}
                    botLabel={LIVE_BOT_LABEL[account]}
                  />
                </div>
              )}
            </div>
          )}
    </CustomerShell>
  )
}
