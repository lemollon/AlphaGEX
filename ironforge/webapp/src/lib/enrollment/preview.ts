import { createHash } from 'crypto'

/**
 * The immutable activation snapshot (Enrollment spec §3 ACT-01, §6).
 *
 * "Display immutable activation snapshot before consent" and "Requires preview hash".
 * The hash is what makes the consent MEAN something: the customer agreed to a specific
 * account, agent, rule version and capital limit — not to "whatever the server thinks
 * now". If any of it moved between preview and submit, the consent no longer describes
 * what would happen, and §4 requires a fresh confirmation.
 *
 * "If buying power changes during review, server recalculates limits and requires a
 * fresh confirmation" (§4) falls out of this for free: buying power is IN the snapshot,
 * so a change alters the hash.
 *
 * Deterministic by construction — fields are hashed in a FIXED order, never by
 * iterating object keys, so two identical snapshots always produce the same hash
 * regardless of how the object was built.
 */

export interface ActivationSnapshot {
  userId: string
  brokerAccountId: string
  /** Masked only — a full account number must never enter a hash we log or return. */
  accountMask: string
  agentCode: string
  ruleVersion: string
  /** Integer cents. Floats would make the hash depend on formatting. */
  maxDeploymentCents: number
  buyingPowerCents: number
  /** Sorted document codes@versions the customer has accepted. */
  legalVersions: string[]
}

const SEP = ''

/**
 * Order is FIXED and explicit. Object key iteration order is an implementation detail;
 * relying on it would make the hash silently unstable across refactors.
 */
export function previewHash(s: ActivationSnapshot): string {
  const parts = [
    s.userId,
    s.brokerAccountId,
    s.accountMask,
    s.agentCode,
    s.ruleVersion,
    String(s.maxDeploymentCents),
    String(s.buyingPowerCents),
    [...s.legalVersions].sort().join(','),
  ]
  return createHash('sha256').update(parts.join(SEP), 'utf8').digest('hex').slice(0, 32)
}

/** Previews go stale quickly — buying power and eligibility both move. */
export const PREVIEW_TTL_MS = 10 * 60 * 1000

export function isPreviewFresh(issuedAtMs: number, now = Date.now()): boolean {
  return now - issuedAtMs <= PREVIEW_TTL_MS
}
