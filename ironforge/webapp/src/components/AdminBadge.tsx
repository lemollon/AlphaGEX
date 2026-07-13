'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'

/* Floating ADMIN pill, visible on every page whenever an operator session
 * exists. Shows who you're impersonating, one-click stop, and a link to the
 * /ops/impersonate picker. Renders nothing for customers/visitors (the status
 * probe answers operator:false and reveals nothing). Dev convenience — safe to
 * remove later by unmounting it in Shell. */

interface Status {
  operator: boolean
  impersonating: { email: string | null } | null
}

export default function AdminBadge() {
  const [status, setStatus] = useState<Status | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    fetch('/api/ops/impersonate?status=true')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => (d?.operator ? setStatus(d) : setStatus(null)))
      .catch(() => setStatus(null))
  }, [])

  if (!status?.operator) return null

  const stop = async () => {
    setBusy(true)
    try {
      await fetch('/api/ops/impersonate?clear=true')
      window.location.reload()
    } catch {
      setBusy(false)
    }
  }

  return (
    <div className="fixed bottom-4 right-4 z-[100] flex items-center gap-2.5 rounded-full border border-amber-500/70 bg-black/90 py-2 pl-4 pr-2 text-xs shadow-2xl shadow-black/60 backdrop-blur">
      <span className="font-bold tracking-wider text-amber-500">ADMIN</span>
      {status.impersonating ? (
        <>
          <span className="max-w-[180px] truncate text-gray-300">
            as <span className="font-semibold text-white">{status.impersonating.email ?? 'customer'}</span>
          </span>
          <button
            type="button"
            onClick={stop}
            disabled={busy}
            className="rounded-full bg-red-600/90 px-3 py-1 font-semibold text-white transition-colors hover:bg-red-500 disabled:opacity-60"
          >
            {busy ? '…' : 'Stop'}
          </button>
        </>
      ) : (
        <span className="text-gray-400">not impersonating</span>
      )}
      <Link
        href="/spark"
        className="rounded-full border border-amber-500/60 px-3 py-1 font-semibold text-amber-500 transition-colors hover:bg-amber-500 hover:text-black"
      >
        Ops
      </Link>
      <Link
        href="/ops/impersonate"
        className="rounded-full bg-amber-500 px-3 py-1 font-semibold text-black transition-colors hover:bg-amber-400"
      >
        {status.impersonating ? 'Switch' : 'View as user'}
      </Link>
    </div>
  )
}
