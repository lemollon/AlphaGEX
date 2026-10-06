/**
 * Lightweight in-memory, per-instance rate limiter. Fine for low-QPS routes
 * (support chat, Sparky chat) that just need to stop obvious abuse — not a
 * distributed limiter, and it resets on every deploy/restart.
 *
 * Extracted out of support/chat/route.ts when sparky/chat/route.ts (#264)
 * needed the identical logic a second time. Callers should namespace `key`
 * per route (e.g. `sparky:${userId}`, not just `userId`) — two routes
 * sharing a bare user-id key would also share the same bucket and apply
 * each other's limits to each other's traffic.
 */
const buckets = new Map<string, number[]>()

export function rateLimited(key: string, opts: { windowMs: number; maxPerWindow: number }): boolean {
  const now = Date.now()
  const arr = (buckets.get(key) ?? []).filter((t) => now - t < opts.windowMs)
  arr.push(now)
  buckets.set(key, arr)
  return arr.length > opts.maxPerWindow
}
