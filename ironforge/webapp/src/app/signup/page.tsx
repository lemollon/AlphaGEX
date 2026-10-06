import { redirect } from 'next/navigation'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * /signup — now a thin redirect to /enroll/account (10/5 reorder: account creation
 * is step 1 of the enrollment rail, not a screen before it). Forwards the query
 * string so existing links (`?bot=`, `?plan=`, `?code=`) keep working unchanged.
 * The real page — session guard, SignedInGate, SignupClient — lives at
 * src/app/enroll/account/page.tsx.
 */
export default function SignupPage({
  searchParams,
}: {
  searchParams?: Record<string, string | string[] | undefined>
}) {
  const qs = new URLSearchParams()
  for (const [key, value] of Object.entries(searchParams ?? {})) {
    if (Array.isArray(value)) {
      for (const v of value) qs.append(key, v)
    } else if (value != null) {
      qs.append(key, value)
    }
  }
  const suffix = qs.toString()
  redirect(suffix ? `/enroll/account?${suffix}` : '/enroll/account')
}
