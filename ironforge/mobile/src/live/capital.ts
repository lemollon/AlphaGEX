import type { LiveAgent, LiveSummary } from '@/api/types'

/**
 * The headline "Total Account Capital" across every agent.
 *
 * Extracted from the Forge screen so the rule can be TESTED rather than trusted. The rule
 * is the point: summing is only honest when every agent reported an account AND they are
 * all the same mode. Adding a paper balance to a production balance produces a number
 * that is part pretend, and on a trading dashboard a plausible wrong total is worse than
 * an obviously missing one.
 */
export interface Capital {
  value: number | null
  note: string | null
}

export function totalCapital(list: LiveAgent[], summary: LiveSummary): Capital {
  const accounts = list.map((a) => a.account).filter((x): x is NonNullable<typeof x> => !!x)

  // One agent (or none) is the single-account view — nothing to combine.
  if (list.length <= 1) return { value: summary.account.value, note: null }

  // A partial answer is not a total. If any agent failed to report, summing what did
  // report understates the balance while still looking authoritative.
  if (accounts.length !== list.length) {
    return {
      value: summary.account.value,
      note: 'One account shown — we could not read every agent just now.',
    }
  }

  const modes = new Set(accounts.map((a) => a.mode))
  const values = accounts.map((a) => a.value).filter((v): v is number => v != null)

  if (modes.size === 1 && values.length === accounts.length) {
    return {
      value: values.reduce((t, v) => t + v, 0),
      note: `Across ${accounts.length} accounts`,
    }
  }

  return {
    value: summary.account.value,
    note: 'One account shown — your agents run on different account types.',
  }
}
