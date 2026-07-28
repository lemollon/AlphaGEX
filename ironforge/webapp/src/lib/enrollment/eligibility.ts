/**
 * Broker account eligibility (Enrollment spec §3 BROKER-02).
 *
 * "Disable ineligible accounts and state the reason: options approval, account type,
 * status, buying power or broker limitation." The reason is the product requirement,
 * not a nicety — §12 requires that when activation cannot proceed "the UI explains the
 * exact remediable reason", and "Options approval is required" is actionable where
 * "this account can't be used" is not.
 *
 * FAILS CLOSED, same contract as the activation predicate: an account is ineligible
 * until proven otherwise, and anything unknown counts as unproven. Trading is the
 * consequence of getting this wrong.
 *
 * Pure: no I/O. The caller fetches from the broker; this only judges.
 */

/** Level 3 is the usual floor for SPREADS, which is what Spark and Flame trade. */
export const MIN_OPTIONS_LEVEL = 3

/** Below this, position sizing cannot produce a legal spread. Mirrors the scanner's >$200 gate. */
export const MIN_BUYING_POWER = 200

export type IneligibleCode =
  | 'OPTIONS_APPROVAL'
  | 'ACCOUNT_TYPE'
  | 'ACCOUNT_STATUS'
  | 'BUYING_POWER'
  | 'BROKER_LIMITATION'
  | 'UNKNOWN'

export interface BrokerAccountFacts {
  /** Broker's account identifier. NEVER logged or returned unmasked. */
  externalRef: string
  accountType?: string | null      // margin | cash | ira | ...
  optionsLevel?: number | null
  status?: string | null           // active | closed | restricted | ...
  buyingPower?: number | null
  /** Broker says this account cannot be traded via API, whatever else is true. */
  brokerBlocked?: boolean
}

export interface EligibilityVerdict {
  eligible: boolean
  code?: IneligibleCode
  /** User-safe and REMEDIABLE where possible — tells them what to change. */
  reason?: string
}

/** Cash accounts cannot hold the short leg of a defined-risk spread. */
const TRADEABLE_TYPES = new Set(['margin', 'ira', 'roth', 'rollover'])

export function evaluateAccountEligibility(a: Partial<BrokerAccountFacts>): EligibilityVerdict {
  // A broker-level block beats everything else — no amount of customer action fixes it.
  if (a.brokerBlocked === true) {
    return {
      eligible: false,
      code: 'BROKER_LIMITATION',
      reason: 'Your broker does not allow automated trading on this account.',
    }
  }

  if (a.status != null && String(a.status).toLowerCase() !== 'active') {
    return {
      eligible: false,
      code: 'ACCOUNT_STATUS',
      reason: `This account is ${String(a.status).toLowerCase()}. Only active accounts can be used.`,
    }
  }

  // Unknown type is NOT assumed tradeable.
  const type = a.accountType == null ? null : String(a.accountType).toLowerCase()
  if (!type || !TRADEABLE_TYPES.has(type)) {
    return {
      eligible: false,
      code: 'ACCOUNT_TYPE',
      reason: type === 'cash'
        ? 'Cash accounts cannot trade spreads. A margin account is required.'
        : 'This account type cannot be used for automated options trading.',
    }
  }

  // Unknown approval level is NOT assumed sufficient — this is the gate that decides
  // whether a spread can legally be placed at all.
  if (a.optionsLevel == null || a.optionsLevel < MIN_OPTIONS_LEVEL) {
    return {
      eligible: false,
      code: 'OPTIONS_APPROVAL',
      reason: `Options approval level ${MIN_OPTIONS_LEVEL} (spreads) is required. Request an upgrade with your broker.`,
    }
  }

  // Checked LAST: it is the most volatile input and the one §4 re-checks immediately
  // before activation, so a customer should see the durable problems first.
  if (a.buyingPower == null || a.buyingPower < MIN_BUYING_POWER) {
    return {
      eligible: false,
      code: 'BUYING_POWER',
      reason: `At least $${MIN_BUYING_POWER} of option buying power is required to open a position.`,
    }
  }

  return { eligible: true }
}

/**
 * Last four digits only (§3 BROKER-02: "Mask account numbers to last four digits").
 *
 * Short or missing identifiers are masked ENTIRELY rather than partially revealed — a
 * 4-character account number would otherwise be printed in full by a naive slice.
 */
export function maskAccountNumber(ref: string | null | undefined): string {
  const s = String(ref ?? '')
  if (s.length <= 4) return '••••'
  return `••••${s.slice(-4)}`
}
