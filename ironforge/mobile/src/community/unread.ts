/**
 * Community tab unread badge (mobile fidelity #229 — `tabBarBadge` had no real count
 * wired to it). GET /api/community/unread returns a real server-computed figure
 * (see webapp lib/community/store.ts's getUnreadCount) — never a fabricated number.
 *
 * Same 60s poll cadence as the notification bell's count (notifications/useUnreadCount.ts)
 * so a push-driven event shows up on the tab within a minute without a second
 * streaming connection just for a badge.
 */
import useSWR, { mutate as globalMutate } from 'swr'
import { api } from '@/api/client'

const UNREAD_KEY = '/api/community/unread'

interface UnreadResponse {
  unread_count: number
}

export function useCommunityUnreadCount(): number {
  const { data } = useSWR<UnreadResponse>(UNREAD_KEY, (p: string) => api<UnreadResponse>(p), {
    refreshInterval: 60_000,
  })
  return data?.unread_count ?? 0
}

/** Marks the feed read as of now — call when the Community tab opens/focuses. */
export async function markCommunityRead(): Promise<void> {
  await api(UNREAD_KEY, { method: 'POST' }).catch(() => {})
  // Optimistic zero — the next 60s poll will reconcile either way, but there is no
  // reason to show a stale nonzero badge for a full minute after the tab was just read.
  void globalMutate<UnreadResponse>(UNREAD_KEY, { unread_count: 0 }, { revalidate: false })
}
