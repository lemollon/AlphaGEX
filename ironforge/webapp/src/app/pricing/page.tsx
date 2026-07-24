import Link from 'next/link'
import { Wordmark } from '@/components/Brand'
import { MARKETING_TIERS } from '@/lib/billing/plans'

export const metadata = {
  title: 'Pricing — IronForge',
  description: 'IronForge plans: Forge Community, Forge Starter, and Forge Pro. Automated trading, forged for performance.',
}

/* ── Glyphs ─────────────────────────────────────────────────────────── */

function Check() {
  return (
    <svg viewBox="0 0 20 20" className="h-4 w-4 shrink-0" aria-hidden="true">
      <circle cx="10" cy="10" r="9" fill="#E8531F" opacity="0.14" />
      <path d="M6 10.5l2.5 2.5L14 7" stroke="#EE5A24" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
function CommunityGlyph() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-6 w-6" aria-hidden="true">
      <circle cx="8" cy="9" r="2.4" stroke="#EE5A24" strokeWidth="1.6" />
      <circle cx="16" cy="9" r="2.4" stroke="#EE5A24" strokeWidth="1.6" />
      <path d="M3.5 18a4.5 4.5 0 019 0M11.5 18a4.5 4.5 0 019 0" stroke="#EE5A24" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  )
}
function DeployGlyph() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-6 w-6" aria-hidden="true">
      <path d="M12 3c3.5 1.5 5 4.5 5 8l-1.6 4H8.6L7 11c0-3.5 1.5-6.5 5-8z" stroke="#EE5A24" strokeWidth="1.6" strokeLinejoin="round" />
      <circle cx="12" cy="10" r="1.6" stroke="#EE5A24" strokeWidth="1.6" />
      <path d="M9 17l-1.5 3M15 17l1.5 3" stroke="#EE5A24" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  )
}
function GridGlyph() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-6 w-6" aria-hidden="true">
      <rect x="4" y="4" width="6.5" height="6.5" rx="1.3" stroke="#EE5A24" strokeWidth="1.6" />
      <rect x="13.5" y="4" width="6.5" height="6.5" rx="1.3" stroke="#EE5A24" strokeWidth="1.6" />
      <rect x="4" y="13.5" width="6.5" height="6.5" rx="1.3" stroke="#EE5A24" strokeWidth="1.6" />
      <rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.3" stroke="#EE5A24" strokeWidth="1.6" />
    </svg>
  )
}
function LockGlyph() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" aria-hidden="true">
      <rect x="5" y="10.5" width="14" height="9" rx="2" stroke="#EE5A24" strokeWidth="1.6" />
      <path d="M8 10.5V8a4 4 0 018 0v2.5" stroke="#EE5A24" strokeWidth="1.6" />
    </svg>
  )
}
function BotGlyph() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" aria-hidden="true">
      <rect x="5" y="8" width="14" height="10" rx="2.5" stroke="#EE5A24" strokeWidth="1.6" />
      <path d="M12 5.5V8M9 13h.01M15 13h.01" stroke="#EE5A24" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}
function StarGlyph() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" aria-hidden="true">
      <path d="M12 4l2.3 4.7 5.2.8-3.8 3.7.9 5.1L12 16.8 7.4 18.1l.9-5.1L4.5 9.5l5.2-.8L12 4z" stroke="#EE5A24" strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  )
}
function MedalGlyph() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" aria-hidden="true">
      <circle cx="12" cy="14" r="5" stroke="#EE5A24" strokeWidth="1.6" />
      <path d="M9 9.5L7 4M15 9.5L17 4M12 12l.9 1.8 2 .3-1.4 1.4.3 2-1.8-1-1.8 1 .3-2L9 14.1l2-.3.9-1.8z" stroke="#EE5A24" strokeWidth="1.3" strokeLinejoin="round" />
    </svg>
  )
}
function FounderBadge() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-7 w-7" aria-hidden="true">
      <path d="M12 3l7 3v5c0 4.2-2.9 7.4-7 8.5-4.1-1.1-7-4.3-7-8.5V6l7-3z" stroke="#EE5A24" strokeWidth="1.5" strokeLinejoin="round" />
      <path d="M12 8l1.2 2.5 2.8.4-2 2 .5 2.8L12 16.9 9.5 17.7l.5-2.8-2-2 2.8-.4L12 8z" fill="#EE5A24" />
    </svg>
  )
}

/* ── Data ───────────────────────────────────────────────────────────── */

interface Tier {
  name: string
  tagline: string
  price: number
  glyph: React.ReactNode
  cta: string
  highlight?: boolean
  plusLabel?: string
  features: string[]
}

const TIERS: Tier[] = [
  {
    name: 'FORGE COMMUNITY',
    tagline: 'LEARN. CONNECT. IMPROVE.',
    price: MARKETING_TIERS.community.priceMonthly,
    glyph: <CommunityGlyph />,
    cta: 'JOIN THE COMMUNITY',
    features: [
      'Discord community access',
      'Market insights & updates',
      'Education & strategy content',
      'Member discussions',
      'Roadmap updates',
      'Support access',
    ],
  },
  {
    name: 'FORGE STARTER',
    tagline: 'DEPLOY YOUR FIRST AUTOMATED STRATEGY.',
    price: MARKETING_TIERS.starter.priceMonthly,
    glyph: <DeployGlyph />,
    cta: 'GET STARTED',
    highlight: true,
    plusLabel: 'Everything in Community, plus:',
    features: ['1 Active Bot'],
  },
  {
    name: 'FORGE PRO',
    tagline: 'RUN MULTIPLE STRATEGIES WITH MAXIMUM FLEXIBILITY.',
    // $75 for two bots — reads BOTH_PLAN.priceMonthly via MARKETING_TIERS, which
    // is what checkout actually charges. The page had 100 hardcoded, so it
    // contradicted the real billed price (corrected 2026-07-23 per operator).
    price: MARKETING_TIERS.pro.priceMonthly,
    glyph: <GridGlyph />,
    cta: 'GO PRO',
    plusLabel: 'Everything in Community, plus:',
    features: ['Up to 2 Active Bots'],
  },
]

// The founding perk is TWO bots at the one-bot price — i.e. Forge Pro for what
// Starter costs. Stating "$50/month for life" alone read as no discount at all,
// because $50 IS the Starter list price; the saving is the tier, not the number.
const FOUNDER_SAVING = MARKETING_TIERS.pro.priceMonthly - MARKETING_TIERS.starter.priceMonthly

const FOUNDER_ITEMS = [
  {
    glyph: <LockGlyph />,
    title: `Forge Pro for $${MARKETING_TIERS.starter.priceMonthly}/month`,
    body: `Save $${FOUNDER_SAVING}/month, locked while your subscription stays active`,
  },
  { glyph: <BotGlyph />, title: '2 Active Bots', body: 'Forge Pro value at the Starter price' },
  { glyph: <StarGlyph />, title: 'Priority Access', body: 'To new features & roadmap' },
  { glyph: <MedalGlyph />, title: 'Limited to First 100', body: 'Use code FORGE50 at signup' },
]

/* ── Page ───────────────────────────────────────────────────────────── */

export default function PricingPage() {
  return (
    <div className="min-h-screen bg-forge-bg bg-ember-glow px-4 py-10 sm:py-14">
      <div className="mx-auto max-w-6xl">
        {/* Top utility bar — standalone page, so it carries its own nav */}
        <div className="mb-6 flex items-center justify-between text-sm">
          <Link href="/" className="flex items-center gap-1.5 text-gray-300 transition-colors hover:text-white">
            <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" aria-hidden="true">
              <path d="M10 3l-5 5 5 5" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Home
          </Link>
          <Link href="/login" className="font-semibold text-amber-500 transition-colors hover:text-amber-400">
            Sign in
          </Link>
        </div>

        {/* Header */}
        <header className="mb-10 text-center">
          <Link href="/" className="inline-flex justify-center" aria-label="IronForge home">
            <Wordmark markClass="h-10 w-auto" textClass="text-2xl" />
          </Link>
          <p className="mt-3 text-xs font-semibold uppercase tracking-[0.25em] text-amber-500">
            Automated Trading. Forged for Performance.
          </p>
        </header>

        {/* Tiers */}
        <div className="grid gap-5 lg:grid-cols-3">
          {TIERS.map((t) => (
            <div
              key={t.name}
              className={`relative flex flex-col overflow-hidden rounded-2xl border bg-forge-card/70 p-6 shadow-xl ${
                t.highlight ? 'border-amber-600/60 ring-1 ring-amber-600/30' : 'border-white/10'
              }`}
            >
              <div className="pointer-events-none absolute inset-x-0 -top-16 h-32 bg-[radial-gradient(ellipse_at_50%_0%,rgba(232,83,31,0.16),transparent_70%)]" />
              {t.highlight && (
                <span className="absolute right-4 top-4 rounded-full bg-amber-600/90 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white">
                  Most Popular
                </span>
              )}
              <span className="flex h-11 w-11 items-center justify-center rounded-xl border border-amber-900/40 bg-amber-950/20">
                {t.glyph}
              </span>
              <h3 className="mt-4 text-lg font-bold tracking-wide text-white">{t.name}</h3>
              <p className="mt-1 text-xs leading-relaxed text-gray-400">{t.tagline}</p>

              <div className="fire-divider my-5" />

              <div className="flex items-baseline gap-1">
                <span className="text-4xl font-extrabold text-white">${t.price}</span>
                <span className="text-sm text-gray-400">/mo</span>
              </div>

              <ul className="mt-5 flex-1 space-y-2.5">
                {t.plusLabel && <li className="text-xs font-semibold text-amber-500">{t.plusLabel}</li>}
                {t.features.map((f) => (
                  <li key={f} className="flex items-center gap-2.5 text-sm text-gray-300">
                    <Check />
                    {f}
                  </li>
                ))}
              </ul>

              <Link
                href={`/signup?plan=${encodeURIComponent(t.name.toLowerCase().replace('forge ', ''))}`}
                className={`mt-6 block rounded-md px-4 py-3 text-center text-sm font-semibold transition ${
                  t.highlight || t.name === 'FORGE PRO'
                    ? 'bg-amber-600 text-white hover:bg-amber-500'
                    : 'border border-amber-600/60 text-amber-500 hover:bg-amber-600/10'
                }`}
              >
                {t.cta}
              </Link>
            </div>
          ))}
        </div>

        {/* Founding member offer */}
        <section className="mt-6 overflow-hidden rounded-2xl border border-amber-600/50 bg-gradient-to-r from-amber-950/30 via-forge-card/70 to-amber-950/20 p-6 shadow-xl">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-2.5">
                <FounderBadge />
                <h2 className="text-base font-bold uppercase tracking-wide text-white">
                  Founding Member Offer <span className="text-amber-500">— First 100 Members</span>
                </h2>
              </div>
              <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {FOUNDER_ITEMS.map((it) => (
                  <div key={it.title} className="flex items-start gap-2.5">
                    <span className="mt-0.5">{it.glyph}</span>
                    <div>
                      <p className="text-sm font-semibold text-white">{it.title}</p>
                      <p className="text-xs text-gray-400">{it.body}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <Link
              href="/signup?code=FORGE50"
              className="shrink-0 rounded-md bg-amber-600 px-6 py-3 text-center text-sm font-bold text-white transition hover:bg-amber-500"
            >
              JOIN AS A FOUNDER
            </Link>
          </div>
        </section>

        <p className="mt-8 text-center text-xs uppercase tracking-widest text-gray-600">
          Pricing in USD. Cancel anytime.
        </p>
      </div>
    </div>
  )
}
