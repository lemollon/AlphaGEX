import Link from 'next/link'

/* Always-available "⌂ Home" link back to the public homepage — shared by the
 * auth and onboarding screens so no page strands the visitor. */

function HomeGlyph() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" aria-hidden="true">
      <path d="M4 11l8-7 8 7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M6 10v9h12v-9" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M10 19v-5h4v5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export default function HomeLink({ className = '' }: { className?: string }) {
  return (
    <Link
      href="/"
      className={`inline-flex items-center gap-1.5 font-medium text-gray-400 transition hover:text-amber-400 ${className}`}
    >
      <HomeGlyph />
      Home
    </Link>
  )
}
