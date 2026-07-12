'use client'

import { useState } from 'react'
import Link from 'next/link'
import { Wordmark } from '@/components/Brand'
import { ArrowRightIcon, XSocialIcon, DiscordIcon, YouTubeIcon } from './icons'

/* Newsletter has no backend yet — same approach as the previous landing page:
 * open a pre-filled email so signups actually reach the inbox. */
const NEWSLETTER_EMAIL = 'shairan2016@gmail.com'

const COMPANY_LINKS = [
  { label: 'About Us', href: '/contact' },
  { label: 'Our Mission', href: '/contact' },
  { label: 'Careers', href: '/contact' },
  { label: 'Contact', href: '/contact' },
]

const RESOURCE_LINKS = [
  { label: 'Blog', href: '/community' },
  { label: 'Help Center', href: '/contact' },
  { label: 'FAQ', href: '/how-it-works' },
  { label: 'Risk Disclosure', href: '/terms' },
]

export default function HomeFooter() {
  const [email, setEmail] = useState('')

  const onSubscribe = (e: React.FormEvent) => {
    e.preventDefault()
    const subject = encodeURIComponent('IronForge updates signup')
    const body = encodeURIComponent(`Please add ${email || 'me'} to IronForge market insights and updates.`)
    window.location.href = `mailto:${NEWSLETTER_EMAIL}?subject=${subject}&body=${body}`
  }

  return (
    <footer className="border-t border-white/10 bg-[#050607]">
      <div className="mx-auto max-w-[1200px] px-5 pb-6 pt-10 md:px-8">
        <div className="grid grid-cols-1 gap-8 md:grid-cols-[4fr_3fr_3fr_4fr]">
          {/* Brand */}
          <div className="flex flex-col items-center md:items-start">
            <Wordmark markClass="h-8 w-auto" textClass="text-lg" />
            <p className="mt-2 text-sm text-gray-400">Discipline. Execution. Edge.</p>
            <div className="mt-4 hidden items-center gap-4 text-gray-400 md:flex">
              <a href="#" aria-label="IronForge on X" className="transition-colors hover:text-white">
                <XSocialIcon className="h-[18px] w-[18px]" />
              </a>
              <a href="#" aria-label="IronForge on Discord" className="transition-colors hover:text-white">
                <DiscordIcon className="h-[18px] w-[18px]" />
              </a>
              <a href="#" aria-label="IronForge on YouTube" className="transition-colors hover:text-white">
                <YouTubeIcon className="h-[18px] w-[18px]" />
              </a>
            </div>
          </div>

          {/* Company */}
          <div className="hidden md:block">
            <div className="text-xs font-semibold uppercase tracking-wider text-gray-300">Company</div>
            <ul className="mt-4 space-y-2.5">
              {COMPANY_LINKS.map(({ label, href }) => (
                <li key={label}>
                  <Link href={href} className="text-sm text-gray-400 transition-colors hover:text-white">
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Resources */}
          <div className="hidden md:block">
            <div className="text-xs font-semibold uppercase tracking-wider text-gray-300">Resources</div>
            <ul className="mt-4 space-y-2.5">
              {RESOURCE_LINKS.map(({ label, href }) => (
                <li key={label}>
                  <Link href={href} className="text-sm text-gray-400 transition-colors hover:text-white">
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Newsletter */}
          <div className="hidden md:block">
            <div className="text-xs font-semibold uppercase tracking-wider text-gray-300">Stay in the Know</div>
            <p className="mt-4 text-sm text-gray-400">Market insights, updates, and community highlights.</p>
            <form onSubmit={onSubscribe} className="mt-4 flex overflow-hidden rounded-lg border border-white/15 bg-[#0C0D0E]">
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Enter your email"
                className="min-w-0 flex-1 bg-transparent px-3 py-2.5 text-sm text-white placeholder-gray-500 outline-none"
              />
              <button
                type="submit"
                aria-label="Subscribe"
                className="flex items-center bg-[#FD5301] px-3.5 text-white transition-colors hover:bg-[#FF6A1F]"
              >
                <ArrowRightIcon className="h-4 w-4" />
              </button>
            </form>
          </div>
        </div>

        {/* Legal bar */}
        <div className="mt-8 flex flex-col items-center gap-3 border-t border-white/10 pt-5 md:flex-row md:justify-between">
          <div className="flex items-center gap-6 text-xs text-gray-400 md:order-2">
            <Link href="/privacy" className="transition-colors hover:text-white">
              Privacy Policy
            </Link>
            <Link href="/terms" className="transition-colors hover:text-white">
              Terms of Service
            </Link>
            <Link href="/terms" className="transition-colors hover:text-white">
              Risk Disclosure
            </Link>
          </div>
          <div className="text-xs text-gray-500 md:order-1">© 2025 IronForge. All rights reserved.</div>
        </div>
      </div>
    </footer>
  )
}
