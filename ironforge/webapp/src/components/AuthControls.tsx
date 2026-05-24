'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'

interface Me { name?: string | null; username?: string | null }

export default function AuthControls() {
  const router = useRouter()
  const [me, setMe] = useState<Me | null>(null)

  useEffect(() => {
    let active = true
    fetch('/api/auth/me')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (active) setMe(d) })
      .catch(() => {})
    return () => { active = false }
  }, [])

  async function logout() {
    await fetch('/api/auth/logout', { method: 'POST' }).catch(() => {})
    router.push('/login')
    router.refresh()
  }

  if (!me?.name) return null

  return (
    <div className="ml-auto flex items-center gap-3 shrink-0 text-sm">
      <span className="text-gray-400">
        Signed in as <span className="text-amber-300 font-medium">{me.name}</span>
      </span>
      <a href="/change-password" className="text-gray-400 hover:text-gray-200">Change password</a>
      <button
        onClick={logout}
        className="text-gray-400 hover:text-white border border-amber-900/40 rounded px-2 py-0.5 transition-colors"
      >
        Sign out
      </button>
    </div>
  )
}
