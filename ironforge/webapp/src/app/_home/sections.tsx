import Link from 'next/link'
import Image from 'next/image'
import { IFMark } from '@/components/Brand'
import DashboardPreview, { DailyBriefList } from './DashboardPreview'
import {
  ShieldIcon,
  BarsIcon,
  PeopleIcon,
  CheckIcon,
  ChevronRightIcon,
  HashUsersIcon,
  ClipboardCheckIcon,
  GaugeIcon,
} from './icons'

/* ── Hero ──────────────────────────────────────────────────────────────────── */

export function Hero() {
  return (
    <section className="mx-auto grid max-w-[1200px] grid-cols-1 items-start gap-10 px-5 pb-14 pt-10 md:px-8 lg:grid-cols-[5fr_6fr] lg:gap-12 lg:pt-14">
      <div>
        <h1 className="text-[44px] font-extrabold leading-[1.05] tracking-tight text-white md:text-[56px]">
          Build Your <span className="text-[#FD5301]">Edge.</span>
        </h1>
        <p className="mt-5 max-w-md text-[17px] leading-relaxed text-gray-300">
          A disciplined trading ecosystem designed to help you stay informed, execute with confidence, and grow
          alongside a community of serious traders.
        </p>
        <Link
          href="/signup"
          className="mt-7 inline-block rounded-lg bg-[#FD5301] px-6 py-3 text-[15px] font-semibold text-white transition-colors hover:bg-[#FF6A1F]"
        >
          Create Account
        </Link>
        <div className="mt-12">
          <ValuePillars />
        </div>
      </div>

      {/* Illustrative dashboard preview — desktop only per spec */}
      <div className="hidden lg:block">
        <DashboardPreview />
      </div>
    </section>
  )
}

/* ── Value pillars ─────────────────────────────────────────────────────────── */

const PILLARS = [
  {
    icon: ShieldIcon,
    title: 'Discipline First',
    body: 'Risk-managed strategies and disciplined execution.',
  },
  {
    icon: BarsIcon,
    title: 'Real-Time Insights',
    body: 'AI-powered market intelligence and daily briefings.',
  },
  {
    icon: PeopleIcon,
    title: 'Stronger Together',
    body: 'Join a community of traders focused on growth.',
  },
]

function ValuePillars() {
  return (
    <div className="grid grid-cols-3 gap-4 lg:gap-5">
      {PILLARS.map(({ icon: Icon, title, body }) => (
        <div key={title} className="text-center lg:text-left">
          <div className="flex flex-col items-center gap-2 lg:flex-row lg:items-center">
            <Icon className="h-7 w-7 text-[#FD5301] lg:h-5 lg:w-5" />
            <h3 className="whitespace-nowrap text-[12.5px] font-bold tracking-tight text-white lg:tracking-normal">
              {title}
            </h3>
          </div>
          <p className="mt-2 text-[13px] leading-snug text-gray-400 lg:text-[11px]">{body}</p>
        </div>
      ))}
    </div>
  )
}

/* ── Membership ────────────────────────────────────────────────────────────── */

/* Row-major order so the rendered 2-col grid reads column-wise like the mock:
 * col 1 = AI briefings / commentary / discussions, col 2 = education / reviews / access. */
const COMMUNITY_FEATURES = [
  'AI market briefings',
  'Educational content',
  'Daily market commentary',
  'Trade reviews',
  'Member discussions',
  'Community access',
]

const AUTOMATE_FEATURES = [
  'Automated execution',
  'Real-time monitoring',
  'Risk-managed strategy',
  'Trade history',
  'Connected brokerage',
  'Performance dashboard',
]

function FeatureChecklist({ items }: { items: string[] }) {
  return (
    <ul className="grid grid-cols-2 gap-x-4 gap-y-2.5">
      {items.map((f) => (
        <li key={f} className="flex items-center gap-2">
          <CheckIcon className="h-3.5 w-3.5 shrink-0 text-[#FD5301]" />
          <span className="text-xs text-gray-200 md:text-[13px]">{f}</span>
        </li>
      ))}
    </ul>
  )
}

export function MembershipSection() {
  return (
    <section id="memberships" className="mx-auto max-w-[1200px] px-5 pb-16 md:px-8">
      <h2 className="text-center text-[26px] font-bold tracking-tight text-white md:text-[28px]">
        Choose Your Membership
      </h2>

      <div className="mt-10 grid grid-cols-1 gap-8 lg:grid-cols-2 lg:gap-6">
        {/* Forge Community */}
        <div className="flex flex-col rounded-2xl border border-white/10 bg-[#0A0B0C] p-6 md:p-7">
          <div className="flex items-center gap-4">
            <PeopleIcon className="h-11 w-11 text-[#FD5301]" />
            <div>
              <h3 className="text-[22px] font-bold text-white">
                Forge <span className="text-[#FD5301]">Community</span>
              </h3>
              <p className="mt-0.5 text-sm text-gray-400">The foundation.</p>
            </div>
          </div>

          <div className="mt-6">
            <FeatureChecklist items={COMMUNITY_FEATURES} />
          </div>

          <div className="mt-6 flex items-center justify-between gap-4 border-t border-white/10 pt-5">
            <div className="text-white">
              <span className="text-[30px] font-extrabold">$10</span>
              <span className="ml-1 text-sm text-gray-400">/month</span>
            </div>
            <Link
              href="/signup?plan=community"
              className="whitespace-nowrap rounded-lg bg-[#FD5301] px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#FF6A1F] md:px-8 md:text-[15px]"
            >
              Join Community
            </Link>
          </div>
        </div>

        {/* Forge Automate */}
        <div className="relative flex flex-col rounded-2xl border border-[#FD5301] bg-[#0A0B0C] p-6 md:p-7">
          <div className="absolute -top-3.5 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full border border-[#4C7A22] bg-[#1E3B14] px-4 py-1 text-[11px] font-bold tracking-wide text-[#8FD14F]">
            5 TRADING DAY FREE TRIAL
          </div>

          <div className="flex items-center gap-4">
            <div className="relative flex h-12 w-12 shrink-0 items-center justify-center">
              <ShieldIcon className="h-12 w-12 text-[#FD5301]" />
              <IFMark className="absolute h-5 w-auto" />
            </div>
            <div>
              <h3 className="text-[22px] font-bold text-white">
                Forge <span className="text-[#FD5301]">Automate</span>
              </h3>
              <p className="mt-0.5 text-sm text-gray-400">Everything in Forge Community, plus:</p>
            </div>
          </div>

          <div className="mt-6">
            <FeatureChecklist items={AUTOMATE_FEATURES} />
          </div>

          <div className="mt-6 border-t border-white/10 pt-5">
            <div className="flex items-center justify-between gap-4">
              <div className="text-white">
                <span className="text-[30px] font-extrabold">$50</span>
                <span className="ml-1 text-sm text-gray-400">/month</span>
              </div>
              <Link
                href="/signup?plan=automate"
                className="whitespace-nowrap rounded-lg bg-[#4C9A2A] px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#58AC33] md:px-7 md:text-[15px]"
              >
                Start 5-Day Free Trial
              </Link>
            </div>
            <p className="mt-3 text-center text-xs text-gray-500 lg:text-right">
              No long-term commitment. Cancel anytime.
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}

/* ── Everything You Need ───────────────────────────────────────────────────── */

/* Static lifetime-return sparkline for the Performance Dashboard preview card. */
function PerformanceChart() {
  const points =
    '0,88 10,84 18,86 26,79 34,81 42,74 50,77 58,70 66,72 74,64 82,68 90,60 98,63 106,55 114,58 122,50 130,54 138,46 146,49 154,41 162,45 170,36 178,40 186,31 194,35 202,26 210,30 218,22 226,25 234,17 242,21 250,13 258,16 266,9 274,13 280,6'
  return (
    <svg viewBox="0 0 280 100" className="h-28 w-full" preserveAspectRatio="none" aria-hidden>
      <defs>
        <linearGradient id="perf-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#3C9D2E" stopOpacity="0.35" />
          <stop offset="100%" stopColor="#3C9D2E" stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={`0,100 ${points} 280,100`} fill="url(#perf-fill)" />
      <polyline points={points} fill="none" stroke="#4FBF3C" strokeWidth="1.6" />
    </svg>
  )
}

function DesktopFeatureCards() {
  return (
    <div className="hidden grid-cols-3 gap-5 md:grid">
      {/* Daily Brief */}
      <div className="flex flex-col rounded-2xl border border-white/10 bg-[#0A0B0C] p-5">
        <div className="flex-1 rounded-xl border border-white/10 bg-[#0C0D0E] p-4">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-gray-300">Daily Brief</div>
          <div className="mt-2.5">
            <DailyBriefList compact />
          </div>
          <div className="mt-3 text-[11px] font-semibold text-[#FD5301]">View Full Brief &rsaquo;</div>
        </div>
        <h3 className="mt-5 text-lg font-bold text-white">Daily Brief</h3>
        <p className="mt-1.5 text-sm leading-relaxed text-gray-400">
          Start every day with AI-powered insights that cut through the noise.
        </p>
      </div>

      {/* Community Intelligence */}
      <div className="flex flex-col rounded-2xl border border-white/10 bg-[#0A0B0C] p-5">
        <div className="flex-1 rounded-xl border border-white/10 bg-[#0C0D0E] p-4">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-gray-300">Forge Community</div>
          <div className="mt-2 flex items-center gap-1.5 border-b border-white/10 pb-2 text-[11px] text-gray-400">
            <HashUsersIcon className="h-3.5 w-3.5" />
            <span># market-talk</span>
          </div>
          <div className="mt-3 space-y-3">
            <div className="flex items-start gap-2">
              <Image
                src="/home/avatar-spark-agent.png"
                alt="Spark Agent avatar"
                width={28}
                height={28}
                className="mt-0.5 shrink-0 rounded-full"
              />
              <div>
                <div className="flex items-center gap-1.5">
                  <span className="text-[11px] font-bold text-white">Spark Agent</span>
                  <span className="rounded border border-white/20 px-1 text-[8px] font-semibold text-gray-400">AI</span>
                </div>
                <div className="mt-1 rounded-lg border border-white/10 bg-[#101112] px-2.5 py-1.5 text-[11px] leading-snug text-gray-300">
                  SPX volatility is heating up. Here&apos;s what I&apos;m watching...
                </div>
              </div>
            </div>
            <div className="flex items-start gap-2">
              <Image
                src="/home/avatar-tradertom.png"
                alt="TraderTom avatar"
                width={28}
                height={28}
                className="mt-0.5 shrink-0 rounded-full"
              />
              <div>
                <span className="text-[11px] font-bold text-white">TraderTom</span>
                <div className="mt-1 rounded-lg border border-white/10 bg-[#101112] px-2.5 py-1.5 text-[11px] leading-snug text-gray-300">
                  Agree. Watching key levels into tomorrow.
                </div>
              </div>
            </div>
          </div>
        </div>
        <h3 className="mt-5 text-lg font-bold text-white">Community Intelligence</h3>
        <p className="mt-1.5 text-sm leading-relaxed text-gray-400">
          Connect with traders, share ideas, and get real-time market discussion.
        </p>
      </div>

      {/* Performance Dashboard */}
      <div className="flex flex-col rounded-2xl border border-white/10 bg-[#0A0B0C] p-5">
        <div className="flex-1 rounded-xl border border-white/10 bg-[#0C0D0E] p-4">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-gray-300">Lifetime Return</div>
          <div className="mt-2 text-xl font-bold text-[#63C132]">+18.74%</div>
          <div className="text-[10px] text-gray-500">All Time</div>
          <div className="mt-2 flex gap-2">
            <div className="flex flex-col justify-between py-1 text-right text-[8px] text-gray-500">
              <span>20%</span>
              <span>10%</span>
              <span>-10%</span>
            </div>
            <div className="min-w-0 flex-1">
              <PerformanceChart />
              <div className="mt-1 flex justify-between text-[8px] text-gray-500">
                <span>JAN</span>
                <span>FEB</span>
                <span>MAR</span>
                <span>APR</span>
                <span>MAY</span>
              </div>
            </div>
          </div>
        </div>
        <h3 className="mt-5 text-lg font-bold text-white">Performance Dashboard</h3>
        <p className="mt-1.5 text-sm leading-relaxed text-gray-400">
          Track your accounts, trades, and performance in real time.
        </p>
      </div>
    </div>
  )
}

const MOBILE_FEATURE_ROWS = [
  { icon: ClipboardCheckIcon, title: 'Daily Brief', body: 'AI-powered insights that cut through the noise.' },
  {
    icon: PeopleIcon,
    title: 'Community Intelligence',
    body: 'Real-time market discussion and trader insights.',
  },
  {
    icon: GaugeIcon,
    title: 'Performance Dashboard',
    body: 'Track your accounts, trades, and performance in real time.',
  },
]

function MobileFeatureRows() {
  return (
    <div className="space-y-3 md:hidden">
      {MOBILE_FEATURE_ROWS.map(({ icon: Icon, title, body }) => (
        <div key={title} className="flex items-center gap-3 rounded-xl border border-white/10 bg-[#0A0B0C] px-4 py-3.5">
          <Icon className="h-5 w-5 shrink-0 text-white" />
          <div className="min-w-0 flex-1">
            <div className="text-sm font-bold text-white">{title}</div>
            <div className="truncate text-[11px] text-gray-400">{body}</div>
          </div>
          <ChevronRightIcon className="h-4 w-4 shrink-0 text-gray-400" />
        </div>
      ))}
    </div>
  )
}

export function EverythingSection() {
  return (
    <section className="mx-auto max-w-[1200px] px-5 pb-16 md:px-8">
      <h2 className="text-center text-[22px] font-bold tracking-tight text-white md:text-[28px]">
        Everything You Need. All in One Place.
      </h2>
      <div className="mt-8">
        <DesktopFeatureCards />
        <MobileFeatureRows />
      </div>
    </section>
  )
}

/* ── Final CTA banner ──────────────────────────────────────────────────────── */

export function CTABanner() {
  return (
    <section className="mx-auto max-w-[1200px] px-5 pb-16 md:px-8">
      {/* Desktop: single row (logo / copy / button) */}
      <div className="hidden items-center gap-5 rounded-2xl border border-white/10 bg-[#0A0B0C] p-8 md:flex">
        <IFMark className="h-14 w-auto shrink-0" />
        <div className="min-w-0 flex-1">
          <h2 className="text-2xl font-bold text-white">Ready to Build Your Edge?</h2>
          <p className="mt-1 text-sm text-gray-400">
            Join thousands of disciplined traders building consistency every day.
          </p>
        </div>
        <Link
          href="/signup"
          className="shrink-0 rounded-lg bg-[#FD5301] px-6 py-3 text-[15px] font-semibold text-white transition-colors hover:bg-[#FF6A1F]"
        >
          Create Account
        </Link>
      </div>

      {/* Mobile: title beside logo, then copy with the button at its right */}
      <div className="rounded-2xl border border-white/10 bg-[#0A0B0C] p-4 md:hidden">
        <div className="flex items-center gap-3">
          <IFMark className="h-10 w-auto shrink-0" />
          <h2 className="text-[17px] font-bold text-white">Ready to Build Your Edge?</h2>
        </div>
        <div className="mt-2 flex items-center gap-3">
          <p className="min-w-0 flex-1 text-[12px] leading-snug text-gray-400">
            Join thousands of disciplined traders building consistency every day.
          </p>
          <Link
            href="/signup"
            className="shrink-0 whitespace-nowrap rounded-lg bg-[#FD5301] px-4 py-2.5 text-[13px] font-semibold text-white"
          >
            Create Account
          </Link>
        </div>
      </div>
    </section>
  )
}
