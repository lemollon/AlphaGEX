import type { Metadata } from 'next'
import Link from 'next/link'
import HomeNav from '../_home/HomeNav'
import HomeFooter from '../_home/HomeFooter'
import { CTABanner } from '../_home/sections'

/* "How It Works" was removed from the homepage per the locked UX decisions and
 * lives behind top navigation instead. Public-safe overview only — no
 * execution logic, algorithms, or automation details. */

export const metadata: Metadata = {
  title: 'How It Works — IronForge',
  description: 'How the IronForge trading ecosystem works: join, stay informed, and trade with discipline.',
}

const STEPS = [
  {
    n: '01',
    title: 'Create your account',
    body: 'Sign up in minutes. Every membership starts with access to the Forge Community and the daily brief.',
  },
  {
    n: '02',
    title: 'Choose your membership',
    body: 'Forge Community keeps you informed with AI market briefings and trader discussion. Forge Automate adds automated, risk-managed execution with a connected brokerage.',
  },
  {
    n: '03',
    title: 'Build consistency',
    body: 'Follow your daily brief, track performance on your dashboard, and grow alongside a community of serious traders.',
  },
]

export default function HowItWorksPage() {
  return (
    <div className="min-h-screen bg-[#050607]">
      <HomeNav active="how-it-works" />
      <main>
        <section className="mx-auto max-w-[900px] px-5 pb-4 pt-12 text-center md:px-8">
          <h1 className="text-4xl font-extrabold tracking-tight text-white md:text-5xl">
            How It <span className="text-[#FD5301]">Works.</span>
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-[17px] leading-relaxed text-gray-300">
            Discipline, insight, and community — in three steps.
          </p>
        </section>

        <section className="mx-auto max-w-[1000px] px-5 py-10 md:px-8">
          <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
            {STEPS.map(({ n, title, body }) => (
              <div key={n} className="rounded-2xl border border-white/10 bg-[#0A0B0C] p-6">
                <div className="text-sm font-bold text-[#FD5301]">{n}</div>
                <h2 className="mt-2 text-lg font-bold text-white">{title}</h2>
                <p className="mt-2 text-sm leading-relaxed text-gray-400">{body}</p>
              </div>
            ))}
          </div>
          <p className="mt-8 text-center text-sm text-gray-500">
            Questions?{' '}
            <Link href="/contact" className="font-semibold text-[#FD5301] hover:text-[#FF6A1F]">
              Contact us
            </Link>
            .
          </p>
        </section>

        <CTABanner />
      </main>
      <HomeFooter />
    </div>
  )
}
