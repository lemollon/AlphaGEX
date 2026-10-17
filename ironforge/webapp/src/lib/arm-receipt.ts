/**
 * ARM RECEIPT — one definition of "armed", and a fill to prove it.
 *
 * WHY THIS FILE EXISTS (Leron, 2026-10-17: "i say arm and it never fucking
 * happens i want explanation and system in place to where when i say to do
 * something it gets done with proof and i want this to be a permanent fix"):
 *
 * "Armed" has meant three different things in this codebase, and work kept
 * landing on the wrong one while being reported as done:
 *
 *   L1 PAPER     — a mode switch is on; the sleeve logs rows, places nothing.
 *   L2 INTERNAL  — real orders on IronForge's OWN Tradier accounts.
 *   L3 CUSTOMER  — real orders on an enrolled customer's own brokerage.
 *
 * When Leron says "arm it", he means **L3**. Previous reports said "armed"
 * when L1 or L2 was true. The 2026-09-28 rollout was recorded as LIVE in the
 * vault having reached sandbox only, by a terminology mixup — the exact
 * failure this file exists to make impossible.
 *
 * ── The rule this file enforces ───────────────────────────────────────────
 *
 * **A switch is not a fill. A deploy is not a fill. A paper row is not a
 * fill.** A sleeve is ARMED at a layer only when a real order id exists at
 * that layer. Everything else reports the layer it actually reached, plus the
 * precise reason it got no further.
 *
 * So this module NEVER returns a bare boolean. Every verdict carries its
 * evidence (order id, account, timestamp) or its blocker. A caller cannot
 * accidentally render "armed" from an empty result, because the empty result
 * is the string 'OFF' with a reason attached.
 *
 * ── What this file is NOT ─────────────────────────────────────────────────
 *
 * Read-only. It places no order, sets no switch, and writes no row. It
 * reports what IS, so that "it's armed" stops being a claim and becomes a
 * query with a receipt. Arming is still a deliberate act elsewhere; this is
 * the thing that tells the truth about whether it happened.
 */

/** The three layers, in ascending order of what they prove. */
export type ArmLayer = 'OFF' | 'PAPER' | 'INTERNAL' | 'CUSTOMER'

/**
 * Ascending severity, so a caller can compare layers without hardcoding the
 * order. CUSTOMER is the only value that answers "did Leron get what he asked
 * for" with a yes.
 */
export const ARM_LAYER_RANK: Record<ArmLayer, number> = {
  OFF: 0,
  PAPER: 1,
  INTERNAL: 2,
  CUSTOMER: 3,
}

/** Proof that an order actually existed at some layer. Never synthesised. */
export interface ArmProof {
  /** The broker's own order id. The whole point — no id, no claim. */
  orderId: string
  /** Which account it landed in, for a human to go and look at. */
  account: string
  accountType: 'sandbox' | 'production' | 'customer'
  /** When, so a stale receipt is visibly stale rather than quietly reassuring. */
  filledAt: string
  /** Fill price if the broker reported one; null when the order filled but the price was never polled back. */
  fillPrice: number | null
}

export interface SleeveArmReceipt {
  /** Display name, the one Leron uses. */
  sleeve: string
  /** The parent product(s) this sleeve runs under. */
  products: string[]
  /** The env switch that gates it, and its CURRENT value — verbatim, never normalised to a boolean. */
  switchName: string
  switchValue: string | null
  /** The highest layer with actual proof. */
  layer: ArmLayer
  /**
   * Proof at each layer that has any. A sleeve can be INTERNAL-armed with no
   * customer proof; both facts belong in the receipt, because "it trades" and
   * "customers get it" are different questions and conflating them is the bug.
   */
  proof: {
    internal: ArmProof | null
    customer: ArmProof | null
  }
  /**
   * Why it is not at the next layer up. Required whenever layer !== 'CUSTOMER'
   * — a receipt that says "not armed" without saying what blocks it is how
   * this problem survived three weeks.
   */
  blocker: string | null
  /**
   * Does an order-placing code path even EXIST for this sleeve? A sleeve with
   * no executor can never be armed by flipping a switch, and saying so up
   * front prevents "just turn it on" from being the answer to a build task.
   */
  hasOrderPath: boolean
  /** Does a customer-mirror code path exist? Same reasoning, one layer up. */
  hasCustomerPath: boolean
}

/**
 * Is this receipt claiming what Leron asked for? The ONLY function that
 * should ever gate a "yes, it's armed for customers" statement.
 *
 * Deliberately requires BOTH the layer and the proof object: a layer of
 * 'CUSTOMER' with a null customer proof is a bug in whoever built the
 * receipt, and this returns false rather than trusting the label.
 */
export function isArmedForCustomers(r: SleeveArmReceipt): boolean {
  return r.layer === 'CUSTOMER' && r.proof.customer != null && !!r.proof.customer.orderId
}

/**
 * One-line rendering for a report or a chat answer, with the proof inline.
 * Reads the same whether the answer is yes or no, so a reader cannot skim it
 * and come away with the wrong impression.
 */
export function describeReceipt(r: SleeveArmReceipt): string {
  const sw = `${r.switchName}=${r.switchValue ?? 'unset'}`
  if (isArmedForCustomers(r)) {
    const p = r.proof.customer!
    return `${r.sleeve}: ARMED FOR CUSTOMERS — order ${p.orderId} in ${p.account} at ${p.filledAt} (${sw})`
  }
  if (r.layer === 'INTERNAL' && r.proof.internal) {
    const p = r.proof.internal
    return `${r.sleeve}: INTERNAL ONLY — order ${p.orderId} in ${p.account} (${p.accountType}) at ${p.filledAt}; ` +
      `customers DO NOT get this. Blocker: ${r.blocker ?? 'unstated'} (${sw})`
  }
  if (r.layer === 'PAPER') {
    return `${r.sleeve}: PAPER ONLY — no real order has ever been placed. ` +
      `Blocker: ${r.blocker ?? 'unstated'} (${sw})`
  }
  return `${r.sleeve}: OFF — ${r.blocker ?? 'no reason recorded'} (${sw})` +
    (r.hasOrderPath ? '' : ' [NO ORDER PATH EXISTS — a switch cannot arm this]')
}

/**
 * Sort a set of receipts worst-first, so a report leads with what is NOT
 * armed. A list that leads with the good news is how a gap hides in plain
 * sight.
 */
export function worstFirst(receipts: SleeveArmReceipt[]): SleeveArmReceipt[] {
  return [...receipts].sort((a, b) => {
    const d = ARM_LAYER_RANK[a.layer] - ARM_LAYER_RANK[b.layer]
    return d !== 0 ? d : a.sleeve.localeCompare(b.sleeve)
  })
}

/**
 * The summary line for the top of a report: how many sleeves actually reach
 * customers, out of how many exist. The number Leron should be able to read
 * in one glance without asking anybody.
 */
export function summarize(receipts: SleeveArmReceipt[]): {
  total: number
  customer: number
  internalOnly: number
  paperOnly: number
  off: number
  noOrderPath: number
  headline: string
} {
  const customer = receipts.filter(isArmedForCustomers).length
  const internalOnly = receipts.filter((r) => r.layer === 'INTERNAL').length
  const paperOnly = receipts.filter((r) => r.layer === 'PAPER').length
  const off = receipts.filter((r) => r.layer === 'OFF').length
  const noOrderPath = receipts.filter((r) => !r.hasOrderPath).length
  return {
    total: receipts.length,
    customer,
    internalOnly,
    paperOnly,
    off,
    noOrderPath,
    headline:
      `${customer} of ${receipts.length} sleeves reach customer accounts. ` +
      `${internalOnly} internal-only, ${paperOnly} paper-only, ${off} off, ` +
      `${noOrderPath} have no order path at all.`,
  }
}
