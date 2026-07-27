import Link from 'next/link'
import { Wordmark } from '@/components/Brand'

/**
 * Operator sign-in — RETIRED 2026-07-27.
 *
 * Username/password login for operators is gone: `/api/auth/login` and
 * `/api/auth/seed` were deleted and the `ironforge_users` rows they
 * authenticated against are no longer used to sign anyone in. Operator access
 * is the admin link, `/api/ops/admin?key=<IRONFORGE_ADMIN_KEY>`, which mints a
 * session from a sentinel user id and needs no database row.
 *
 * The page itself stays, deliberately. Middleware redirects every gated
 * operator route here (`/ops/login?next=…`), so deleting it would turn each of
 * those redirects into a 404 — the console would look broken rather than
 * locked. It now explains the door instead of offering a form that cannot work.
 *
 * It also carries NO signup link. This is the operator surface; pointing it at
 * /signup sent operators into the customer funnel.
 */
export const dynamic = 'force-dynamic'

export default function OpsLoginPage() {
  return (
    <div className="mx-auto mt-24 max-w-sm px-4">
      <div className="mb-6 flex items-center justify-center">
        <Wordmark markClass="h-8 w-auto" textClass="text-2xl" />
      </div>

      <div className="rounded-lg border border-amber-900/30 bg-forge-card p-6">
        <h1 className="text-lg font-semibold text-gray-100">Operator access</h1>
        <p className="mt-3 text-sm leading-relaxed text-gray-400">
          Operator sign-in has been retired. There are no operator username and
          password accounts any more.
        </p>
        <p className="mt-3 text-sm leading-relaxed text-gray-400">
          Console access is via the admin link. Open it once and this browser
          holds an operator session for 30 days.
        </p>
        <p className="mt-4 rounded border border-white/10 bg-black/40 px-3 py-2 font-mono text-xs text-gray-400">
          /api/ops/admin?key=&lt;IRONFORGE_ADMIN_KEY&gt;
        </p>
      </div>

      <p className="mt-4 text-center text-xs text-gray-500">
        Looking for your account?{' '}
        <Link href="/login" className="font-semibold text-amber-500 hover:text-amber-400">
          Customer sign-in
        </Link>
      </p>
    </div>
  )
}
