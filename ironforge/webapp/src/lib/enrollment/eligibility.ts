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

/**
 * SnapTrade brokers where MULTI-LEG option trading is Generally Available per
 * SnapTrade's institution support matrix (support.snaptrade.com/brokerages, checked
 * 2026-07-30). These brokers don't expose an options approval level through SnapTrade,
 * so the options gate for them is CAPABILITY-based: the platform can preview and place
 * defined-risk spreads, and a permissions rejection at order preview is the enforcement
 * backstop. Deliberately starts with tastytrade only — the lane we ship first; widening
 * it is a one-line diff made per broker, never by default.
 */
export const SNAPTRADE_MLEG_SLUGS = new Set(['TASTYTRADE'])

/**
 * SnapTrade brokers that are DATA-ONLY (no trading of any kind in the matrix).
 * Robinhood connections import accounts we can read but can never trade — saying
 * "options approval required" there would send a customer to fix something that
 * cannot make the account usable. BROKER_LIMITATION is the honest verdict.
 */
export const SNAPTRADE_DATA_ONLY_SLUGS = new Set(['ROBINHOOD'])

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
  /**
   * Normalized SnapTrade institution slug (e.g. 'TASTYTRADE'), when the account came
   * through SnapTrade. Selects the capability-based options gate for mleg-capable
   * brokers and the honest data-only refusal for read-only ones. Absent for direct
   * integrations (Tradier OAuth), which report a real options level.
   */
  brokerSlug?: string | null
}

export interface EligibilityVerdict {
  eligible: boolean
  code?: IneligibleCode
  /** User-safe and REMEDIABLE where possible — tells them what to change. */
  reason?: string
  /** How the options gate was satisfied — audit detail, never shown raw to customers. */
  optionsVerification?: 'broker_level' | 'platform_capability'
}

/** Cash accounts cannot hold the short leg of a defined-risk spread. */
const TRADEABLE_TYPES = new Set(['margin', 'ira', 'roth', 'rollover'])

/** Broker type strings vary ('MARGIN', 'Individual Margin', ...) — normalize + contains. */
function isTradeableType(raw: string): boolean {
  if (TRADEABLE_TYPES.has(raw)) return true
  return raw.includes('margin') || raw.includes('ira') || raw.includes('roth') || raw.includes('rollover')
}

export function evaluateAccountEligibility(a: Partial<BrokerAccountFacts>): EligibilityVerdict {
  const slug = a.brokerSlug ? String(a.brokerSlug).toUpperCase() : null

  // A broker-level block beats everything else — no amount of customer action fixes it.
  // SnapTrade data-only brokers (Robinhood) are exactly this: readable, never tradable.
  if (a.brokerBlocked === true || (slug && SNAPTRADE_DATA_ONLY_SLUGS.has(slug))) {
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
  if (!type || !isTradeableType(type)) {
    return {
      eligible: false,
      code: 'ACCOUNT_TYPE',
      reason: type === 'cash'
        ? 'Cash accounts cannot trade spreads. A margin account is required.'
        : 'This account type cannot be used for automated options trading.',
    }
  }

  // The options gate, two ways of satisfying it:
  //  - broker_level: the broker reports a real approval level (Tradier direct OAuth).
  //    Unknown or too-low is NOT assumed sufficient.
  //  - platform_capability: an mleg-capable SnapTrade broker (tastytrade). SnapTrade
  //    exposes no approval level, so the level read is impossible; the platform's
  //    ability to preview/place defined-risk spreads is the gate, and a permissions
  //    rejection at order preview is the enforcement backstop. This is a deliberate
  //    per-broker decision, never a default.
  const capabilityGate = slug != null && SNAPTRADE_MLEG_SLUGS.has(slug) && a.optionsLevel == null
  if (!capabilityGate && (a.optionsLevel == null || a.optionsLevel < MIN_OPTIONS_LEVEL)) {
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

  return { eligible: true, optionsVerification: capabilityGate ? 'platform_capability' : 'broker_level' }
}

/**
 * SnapTrade returns institution DISPLAY names ('tastytrade', 'Robinhood', 'Webull US');
 * the capability sets key on slugs. Normalize: uppercase, alphanumeric only.
 */
export function normalizeInstitutionSlug(name: string | null | undefined): string | null {
  if (!name) return null
  const s = String(name).toUpperCase().replace(/[^A-Z0-9]/g, '')
  return s.length ? s : null
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
