'use client'

import { useEffect, useState } from 'react'

/**
 * True when the browser holds an operator session (ops login or magic link).
 * Uses the AdminBadge status probe, which answers operator:false for everyone
 * else and reveals nothing. Drives the operator-only "Ops" nav items.
 */
export function useIsOperator(): boolean {
  const [isOperator, setIsOperator] = useState(false)
  useEffect(() => {
    fetch('/api/ops/impersonate?status=true')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setIsOperator(Boolean(d?.operator)))
      .catch(() => setIsOperator(false))
  }, [])
  return isOperator
}
