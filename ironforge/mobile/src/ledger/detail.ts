/**
 * Trade detail route helper (APP-019). Exported as its own module — not inlined in
 * the ledger screen — because WP-E's notification tap handler (route-for.ts) also
 * needs it for `data.trade_id` without importing the whole ledger screen.
 */
export function tradeDetailHref(id: string): string {
  return `/trade/${id}`
}
