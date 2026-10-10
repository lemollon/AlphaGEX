/**
 * "Assigned: Spark/Flame" on a brokerage connection row (APP-040).
 *
 * Neither payload carries the join a caller actually wants: LiveAgent.account has no
 * broker_account_id or mask, and BrokerageConnection has no owning agent — there is no
 * server field linking the two. The one case that is still honest without it is the
 * same one the Forge tile already leans on (see soleConnection in api/brokerage.ts):
 * with exactly ONE connection, every agent this viewer owns is necessarily trading
 * through it, so attribution needs no join at all. With more than one connection the
 * match would be a guess, and a guessed account number under an agent on a trading
 * screen is worse than admitting it cannot be shown.
 */
export function assignedAgentLabels(
  connectionCount: number,
  ownedAgentLabels: string[],
): string[] | null {
  if (connectionCount !== 1) return null
  return ownedAgentLabels
}
