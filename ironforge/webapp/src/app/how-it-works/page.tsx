import type { Metadata } from 'next'
import Link from 'next/link'
import Image from 'next/image'
import PerformanceOverviewCard from './PerformanceOverviewCard'
import HomeNav from '../_home/HomeNav'
import {
  ShieldIcon,
  BarsIcon,
  EyeIcon,
  SunIcon,
  SearchIcon,
  TargetIcon,
  TrendIcon,
  FlagIcon,
  CheckIcon,
  ArrowRightIcon,
  PeopleIcon,
  BoltIcon,
  PersonIcon,
  CalendarCheckIcon,
  ChartLineIcon,
  ChartUpSquareIcon,
} from '../_home/icons'

/* IronForge How It Works page — implements the approved v2 engineering spec
 * (IronForge_How_It_Works_Engineering_Specification_v2). Layout, copy, and
 * branding are locked to the canonical rendering. Conversion-first marketing
 * page: no strategy logic, timing windows, or risk thresholds appear here.
 *
 * Design tokens (spec §4.1): page #0B0B0B, surface #141414, border #2B2B2B,
 * secondary text #B8B8B8, orange #FF4F00, spark blue #128CFF,
 * trial green #4DAA2B, success green #56C62B. */

export const metadata: Metadata = {
  title: 'How It Works — IronForge',
  description:
    'Built on Discipline. Driven by Data. Automated trading powered by real-time analysis and disciplined execution.',
}

/* ── Approved copy (spec §14: centralized config, no duplicated wording) ───── */

const CONFIG = {
  hero: {
    titleLine1: ['Built on ', 'Discipline.'],
    titleLine2: ['Driven by ', 'Data.'],
    description: 'Automated trading powered by real-time analysis and disciplined execution.',
    trustNotes: ['No long-term commitment', 'Cancel anytime'],
  },
  principles: [
    { icon: ShieldIcon, title: 'Discipline First', copy: 'Every trade follows predefined rules.' },
    { icon: BarsIcon, title: 'Data Driven', copy: 'Decisions powered by real-time analysis.' },
    { icon: EyeIcon, title: 'Automation with Oversight', copy: 'Consistent execution with transparent monitoring.' },
  ],
  framework: [
    { step: 1, icon: SunIcon, title: 'Market Opens', copy: 'We track the market conditions in real time.' },
    { step: 2, icon: SearchIcon, title: 'Analyze & Evaluate', copy: 'We analyze data and evaluate opportunities.' },
    { step: 3, icon: TargetIcon, title: 'Execute Strategy', copy: 'We take disciplined trades based on our rules.' },
    { step: 4, icon: TrendIcon, title: 'Monitor Positions', copy: 'We monitor trades and manage risk throughout the day.' },
    { step: 5, icon: FlagIcon, title: 'End-of-Day Review', copy: 'We review performance and refine for tomorrow.' },
  ],
  strategies: [
    {
      key: 'spark',
      title: 'SPARK',
      bullets: ['Lower risk', 'Long-term growth', 'Automated discipline'],
      mascotSrc: '/home/spark-mascot-glow.png',
      mascotAlt: 'Spark strategy mascot',
    },
    {
      key: 'flame',
      title: 'FLAME',
      bullets: ['Greater opportunity', 'Higher risk tolerance', 'Automated discipline'],
      mascotSrc: '/home/flame-mascot-glow.png',
      mascotAlt: 'Flame strategy mascot',
    },
  ],
  comparison: [
    { label: 'Primary Objective', spark: 'Long-term growth', flame: 'Accelerated growth' },
    { label: 'Risk Profile', spark: 'Conservative', flame: 'Moderate' },
    { label: 'Portfolio Focus', spark: 'Consistency', flame: 'Higher upside' },
    { label: 'Trading Discipline', spark: 'Automated', flame: 'Automated' },
    { label: 'Risk Management', spark: 'Built In', flame: 'Built In' },
  ],
  benefits: [
    { icon: ChartLineIcon, label: 'Daily Market Intelligence', accent: 'blue', boxed: true },
    { icon: PeopleIcon, label: 'Forge Community', accent: 'orange', boxed: false },
    { icon: BoltIcon, label: 'Automated Trading', accent: 'orange', boxed: false },
    { icon: ChartUpSquareIcon, label: 'Performance Dashboard', accent: 'orange', boxed: true },
  ],
} as const

/* ── Sections ──────────────────────────────────────────────────────────────── */

function HeroSection() {
  return (
    <section className="mx-auto grid max-w-[1200px] grid-cols-1 items-center gap-10 px-4 pb-8 pt-10 md:px-8 lg:grid-cols-[11fr_10fr] lg:gap-12 lg:pt-12">
      <div>
        <h1 className="text-[38px] font-bold leading-[1.08] tracking-tight text-white md:text-[56px] md:leading-[1.05]">
          {CONFIG.hero.titleLine1[0]}
          <span className="text-[#FF4F00]">{CONFIG.hero.titleLine1[1]}</span>
          <br />
          {CONFIG.hero.titleLine2[0]}
          <span className="text-[#FF4F00]">{CONFIG.hero.titleLine2[1]}</span>
        </h1>
        <p className="mt-4 max-w-sm text-[16px] leading-relaxed text-gray-300">{CONFIG.hero.description}</p>
        <div className="mt-7 flex flex-col gap-3 sm:flex-row sm:items-stretch">
          <Link
            href="/signup?source=how_it_works&placement=hero"
            className="inline-flex items-center justify-center whitespace-nowrap rounded-lg bg-[#FF4F00] px-7 py-3 text-[15px] font-semibold text-white transition-[filter] hover:brightness-110"
          >
            Create Account
          </Link>
          <Link
            href="/signup?plan=automate&source=how_it_works&placement=hero"
            className="inline-flex flex-col items-center justify-center whitespace-nowrap rounded-lg bg-[#4DAA2B] px-6 py-2 text-white transition-[filter] hover:brightness-110"
          >
            <span className="text-[15px] font-semibold leading-tight">Start 5-Day Free Trial</span>
            <span className="text-[11px] leading-tight text-white/85">Forge Automate</span>
          </Link>
        </div>
        <ul className="mt-5 flex flex-wrap items-center gap-x-3 gap-y-2">
          {CONFIG.hero.trustNotes.map((note, i) => (
            <li key={note} className="flex items-center gap-3">
              {i > 0 ? <span className="h-4 w-px bg-[#2B2B2B]" aria-hidden /> : null}
              <span className="flex items-center gap-1.5 text-[13px] text-gray-300">
                <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" aria-hidden>
                  <circle cx="12" cy="12" r="9" stroke="#FF4F00" strokeWidth="1.6" />
                  <path d="M8.5 12.3l2.3 2.3 4.7-5.1" stroke="#FF4F00" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                {note}
              </span>
            </li>
          ))}
        </ul>
      </div>
      <PerformanceOverviewCard />
    </section>
  )
}

function PrinciplesStrip() {
  return (
    <section className="mx-auto max-w-[1200px] px-4 pb-12 md:px-8">
      <div className="grid grid-cols-1 divide-y divide-[#2B2B2B] rounded-2xl border border-[#2B2B2B] bg-[#101010] md:grid-cols-3 md:divide-x md:divide-y-0">
        {CONFIG.principles.map(({ icon: Icon, title, copy }) => (
          <div key={title} className="flex items-center gap-4 px-6 py-5">
            <Icon className="h-9 w-9 shrink-0 text-[#FF4F00]" />
            <div>
              <h2 className="text-[15px] font-bold text-white">{title}</h2>
              <p className="mt-1 text-[13px] leading-snug text-[#B8B8B8]">{copy}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

function TradingFramework() {
  return (
    <section className="mx-auto max-w-[1200px] px-4 pb-14 md:px-8">
      <h2 className="text-center text-[24px] font-bold tracking-tight text-white md:text-[28px]">
        Every Trading Day Follows the Same Framework
      </h2>
      <ol className="mt-10 flex flex-col items-center gap-6 md:flex-row md:items-start md:justify-between md:gap-2">
        {CONFIG.framework.map(({ step, icon: Icon, title, copy }, i) => (
          <li key={step} className="contents">
            {i > 0 ? (
              <ArrowRightIcon className="mt-2 h-5 w-5 shrink-0 rotate-90 text-[#FF4F00] md:mt-7 md:rotate-0" aria-hidden />
            ) : null}
            <div className="flex w-44 flex-col items-center text-center">
              <div className="relative">
                <div className="flex h-[72px] w-[72px] items-center justify-center rounded-full border border-[#3A3A3A] bg-[#101010]">
                  <Icon className="h-7 w-7 text-[#FF4F00]" />
                </div>
                <span className="absolute -left-1.5 -top-1.5 flex h-6 w-6 items-center justify-center rounded-full bg-[#FF4F00] text-[12px] font-bold text-white">
                  {step}
                </span>
              </div>
              <h3 className="mt-4 text-[14.5px] font-bold text-white">{title}</h3>
              <p className="mt-2 text-[12.5px] leading-snug text-[#B8B8B8]">{copy}</p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  )
}

function StrategyCard({ strategy }: { strategy: (typeof CONFIG.strategies)[number] }) {
  const spark = strategy.key === 'spark'
  return (
    <div
      className={`flex items-center gap-6 rounded-2xl border p-6 md:p-7 ${
        spark
          ? 'border-[#128CFF]/70 bg-[#07111C] shadow-[inset_0_0_60px_rgba(18,140,255,0.06)]'
          : 'border-[#FF4F00]/70 bg-[#140D08] shadow-[inset_0_0_60px_rgba(255,79,0,0.05)]'
      }`}
    >
      <Image
        src={strategy.mascotSrc}
        alt={strategy.mascotAlt}
        width={128}
        height={128}
        className="h-28 w-28 shrink-0 object-contain md:h-32 md:w-32"
      />
      <div>
        <h3 className={`text-[22px] font-bold tracking-wide ${spark ? 'text-[#4DA6FF]' : 'text-[#FF4F00]'}`}>
          {strategy.title}
        </h3>
        <ul className="mt-3 space-y-2">
          {strategy.bullets.map((b) => (
            <li key={b} className="flex items-center gap-2.5">
              <CheckIcon className={`h-3.5 w-3.5 shrink-0 ${spark ? 'text-[#128CFF]' : 'text-[#FF4F00]'}`} />
              <span className="text-[14px] text-gray-200">{b}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

function StrategySection() {
  return (
    <section className="mx-auto max-w-[1200px] px-4 pb-10 md:px-8">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {CONFIG.strategies.map((s) => (
          <StrategyCard key={s.key} strategy={s} />
        ))}
      </div>

      {/* Comparison table — semantic markup per spec §6.6; horizontal scroll with
          sticky row labels on mobile. */}
      <div className="mt-8 overflow-x-auto rounded-xl border border-[#2B2B2B]">
        <table className="w-full min-w-[560px] border-collapse text-[13.5px]">
          <thead>
            <tr>
              <th
                scope="col"
                className="sticky left-0 w-[30%] bg-[#141414] px-4 py-2.5 text-left font-semibold text-white"
              >
                Strategy Comparison
              </th>
              <th scope="col" className="w-[35%] bg-[#113353] px-4 py-2.5 text-center font-semibold text-[#7FBBFF]">
                Spark
              </th>
              <th scope="col" className="w-[35%] bg-[#943F08] px-4 py-2.5 text-center font-semibold text-[#FFC9A3]">
                Flame
              </th>
            </tr>
          </thead>
          <tbody>
            {CONFIG.comparison.map(({ label, spark, flame }) => (
              <tr key={label} className="border-t border-[#222]">
                <th scope="row" className="sticky left-0 bg-[#0E0F0F] px-4 py-2.5 text-left font-normal text-gray-200">
                  {label}
                </th>
                <td className="bg-[#0B0C0D] px-4 py-2.5 text-center text-gray-100">{spark}</td>
                <td className="bg-[#0B0C0D] px-4 py-2.5 text-center text-gray-100">{flame}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function MemberBenefits() {
  return (
    <section className="mx-auto max-w-[1200px] px-4 pb-12 md:px-8">
      <h2 className="text-center text-[22px] font-bold tracking-tight text-white md:text-[24px]">
        What Members Receive
      </h2>
      <ul className="mt-6 grid grid-cols-2 gap-y-6 md:flex md:items-center md:justify-center">
        {CONFIG.benefits.map(({ icon: Icon, label, accent, boxed }, i) => {
          const color = accent === 'blue' ? 'text-[#128CFF]' : 'text-[#FF4F00]'
          const border = accent === 'blue' ? 'border-[#128CFF]' : 'border-[#FF4F00]'
          const words = label.split(' ')
          const line1 = words.slice(0, -1).join(' ')
          const line2 = words[words.length - 1]
          return (
            <li key={label} className="flex items-center justify-center gap-3 md:px-8">
              {i > 0 ? <span className="hidden h-9 w-px bg-[#2B2B2B] md:-ml-8 md:mr-8 md:block" aria-hidden /> : null}
              {boxed ? (
                <span className={`flex h-11 w-11 items-center justify-center rounded-lg border-[1.5px] ${border}`}>
                  <Icon className={`h-6 w-6 ${color}`} />
                </span>
              ) : (
                <Icon className={`h-9 w-9 ${color}`} />
              )}
              <span className="text-[13.5px] font-semibold leading-snug text-white">
                {line1}
                <br />
                {line2}
              </span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function FinalCTA() {
  return (
    <section className="mx-auto max-w-[1200px] px-4 pb-10 md:px-8">
      <div className="rounded-2xl border border-[#2B2B2B] bg-[#111111] px-6 py-6 md:px-10 md:py-7">
        <div className="flex flex-col gap-5 md:flex-row md:items-center">
          <div className="min-w-0 flex-1">
            <h2 className="text-[24px] font-bold text-white md:text-[28px]">Ready to Build Your Edge?</h2>
            <p className="mt-1 text-[14px] text-[#B8B8B8]">Discipline. Data. Execution.</p>
          </div>
          <span className="hidden h-14 w-px bg-[#2B2B2B] md:block" aria-hidden />
          <Link
            href="/signup?source=how_it_works&placement=final_cta"
            className="inline-flex shrink-0 items-center justify-center whitespace-nowrap rounded-lg bg-[#FF4F00] px-10 py-3.5 text-[16px] font-semibold text-white transition-[filter] hover:brightness-110"
          >
            Create Account
          </Link>
        </div>
        <div className="mt-5 flex flex-col items-center justify-center gap-3 border-t border-[#2B2B2B] pt-4 sm:flex-row sm:gap-0">
          <span className="flex items-center gap-2 text-[13px] text-gray-300">
            <PersonIcon className="h-[18px] w-[18px] text-[#FF4F00]" />
            Community starts at $10/month.
          </span>
          <span className="mx-6 hidden h-4 w-px bg-[#2B2B2B] sm:block" aria-hidden />
          <span className="flex items-center gap-2 text-[13px] text-gray-300">
            <CalendarCheckIcon className="h-[18px] w-[18px] text-[#56C62B]" />
            Try Forge Automate free for 5 trading days.
          </span>
        </div>
      </div>
    </section>
  )
}

function LegalFooter() {
  return (
    <footer className="pb-8 pt-2">
      <nav aria-label="Legal" className="flex items-center justify-center gap-4 text-[13px] text-[#B8B8B8]">
        <Link href="/privacy" className="transition-colors hover:text-white">
          Privacy Policy
        </Link>
        <span className="h-4 w-px bg-[#2B2B2B]" aria-hidden />
        <Link href="/terms" className="transition-colors hover:text-white">
          Risk Disclosure
        </Link>
      </nav>
    </footer>
  )
}

export default function HowItWorksPage() {
  return (
    <div className="min-h-screen bg-[#0B0B0B]">
      <HomeNav active="how-it-works" />
      <main>
        <HeroSection />
        <PrinciplesStrip />
        <TradingFramework />
        <StrategySection />
        <MemberBenefits />
        <FinalCTA />
      </main>
      <LegalFooter />
    </div>
  )
}
