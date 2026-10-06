import { useMemo } from 'react'
import { View, Text, ScrollView, Pressable, ActivityIndicator, StyleSheet } from 'react-native'
import { Stack, useRouter } from 'expo-router'
import useSWRInfinite from 'swr/infinite'
// Deep import: `from '@expo/vector-icons'` reaches all 19 icon fonts.
import Ionicons from '@expo/vector-icons/Ionicons'
import { api } from '@/api/client'
import type { NotificationItem, NotificationsReadResponse } from '@/api/types'
import {
  getNotificationsKey,
  mergeNotificationPages,
  hasMoreNotificationPages,
  latestUnreadCount,
  type NotificationsPage,
} from '@/notifications/history'
import { routeFor } from '@/notifications/route-for'
import { tradeDetailHref } from '@/ledger/detail'
import { agentDetailHref } from '@/agents/routes'
import { space, radius, type, font } from '@/theme/tokens'
import { useTheme } from '@/theme/ThemeContext'
import type { ColorTokens } from '@/theme/palette'
import { Card, Loading, Empty, ErrorState } from '@/components/ui'
import { Sheet, SheetHeader } from '@/components/Sheet'
import { Mascot } from '@/components/Brand'

/** Rows whose `data.agent` names a real agent get that agent's mascot (10.4 design:
 *  "agent mascot avatar for agent events") instead of the generic glyph below. */
const KNOWN_AGENTS = new Set(['spark', 'flame', 'ember'])
function agentForNotification(item: NotificationItem): string | null {
  const a = item.data?.agent
  return typeof a === 'string' && KNOWN_AGENTS.has(a) ? a : null
}

/**
 * Notifications — the real HISTORY feed (10.4 gap audit).
 *
 * The app.html design's notifications sheet shows past events (trade opened/closed,
 * daily summary) with no API behind it — grepped at the time: only
 * /api/notifications/preferences and /devices existed. GET /api/v1/notifications now
 * backs this screen with real rows, written server-side from inside dispatchToCustomers
 * (the same function that sends every push) — so this feed is never out of sync with
 * what was actually sent, and never invented example data.
 *
 * The preference toggles that used to live at this route moved to
 * app/notification-preferences.tsx, one tap away via the "Notification settings" link
 * below — unchanged in every other respect.
 */
const ICON_FOR_KIND: Record<string, React.ComponentProps<typeof Ionicons>['name']> = {
  trade_opened: 'flash-outline',
  trade_closed: 'checkmark-circle-outline',
  trade_approval: 'alert-circle-outline',
  brokerage_health: 'link-outline',
  billing: 'card-outline',
  community: 'chatbubbles-outline',
}

function iconForKind(kind: string): React.ComponentProps<typeof Ionicons>['name'] {
  return ICON_FOR_KIND[kind] ?? 'notifications-outline'
}

/** "9:42 AM" today, "Yesterday", or "Sep 3" further back — same convention as the
 *  Forge hero chart's scrub label (formatPointStamp in app/(tabs)/index.tsx). */
function formatWhen(iso: string): string {
  const d = new Date(iso)
  const now = new Date()
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
  }
  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday'
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export default function NotificationsScreen() {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  const router = useRouter()

  const { data, error, isLoading, isValidating, size, setSize, mutate } = useSWRInfinite<NotificationsPage>(
    getNotificationsKey(),
    (p: string) => api<NotificationsPage>(p),
    { refreshInterval: 60_000 },
  )

  const notifications = mergeNotificationPages(data)
  const canLoadMore = hasMoreNotificationPages(data)
  const loadingMore = isValidating && size > 0 && !!data && data.length < size
  const unreadCount = latestUnreadCount(data)

  async function markAllRead() {
    if (unreadCount === 0) return
    const now = new Date().toISOString()
    mutate(
      (pages) =>
        pages?.map((p) => ({
          ...p,
          unread_count: 0,
          notifications: p.notifications.map((n) => ({ ...n, read_at: n.read_at ?? now })),
        })),
      { revalidate: false },
    )
    try {
      await api<NotificationsReadResponse>('/api/v1/notifications/read', { method: 'POST', body: { all: true } })
    } catch {
      // Best-effort — a failed mark-all leaves the dot wrong until the next 60s poll
      // corrects it, same tolerance as every other optimistic toggle in this app.
    }
  }

  function openNotification(item: NotificationItem) {
    if (!item.read_at) {
      const now = new Date().toISOString()
      mutate(
        (pages) =>
          pages?.map((p) => ({
            ...p,
            unread_count: Math.max(0, p.unread_count - 1),
            notifications: p.notifications.map((n) => (n.id === item.id ? { ...n, read_at: now } : n)),
          })),
        { revalidate: false },
      )
      api<NotificationsReadResponse>('/api/v1/notifications/read', { method: 'POST', body: { id: item.id } }).catch(
        () => {},
      )
    }
    const href = routeFor(item.data, { tradeDetailHref, agentDetailHref })
    if (href) router.push(href as never)
  }

  return (
    <>
      <Stack.Screen
        options={{ presentation: 'transparentModal', animation: 'fade', contentStyle: { backgroundColor: 'transparent' } }}
      />
      <Sheet onClose={() => router.back()}>
        {(close) => (
          <>
            <SheetHeader
              title="Notifications"
              right={
                unreadCount > 0 ? (
                  <Pressable onPress={markAllRead} accessibilityRole="button" style={{ marginRight: space.sm }}>
                    <Text style={[type.label, { color: color.accent, fontFamily: font.bodyMedium }]}>
                      Mark all read
                    </Text>
                  </Pressable>
                ) : null
              }
              onClose={close}
            />
            {isLoading && !data ? (
              <Loading label="Loading notifications…" />
            ) : error && !data ? (
              <ErrorState message={String((error as Error).message)} onRetry={() => mutate()} />
            ) : notifications.length === 0 ? (
              <Empty
                title="No notifications yet"
                detail="Trade activity, brokerage alerts, and billing updates will show up here."
              />
            ) : (
              <ScrollView
                contentContainerStyle={{ padding: space.lg }}
                onScroll={({ nativeEvent }) => {
                  const { layoutMeasurement, contentOffset, contentSize } = nativeEvent
                  const nearBottom = layoutMeasurement.height + contentOffset.y >= contentSize.height - 200
                  if (nearBottom && canLoadMore && !loadingMore) setSize(size + 1)
                }}
                scrollEventThrottle={200}
              >
                <Card style={{ padding: 0 }}>
                  {notifications.map((item, i) => (
                    <Pressable
                      key={item.id}
                      onPress={() => openNotification(item)}
                      style={[s.row, i > 0 && s.rowDivider]}
                      accessibilityRole="button"
                      accessibilityLabel={`${item.title}. ${item.body}${item.read_at ? '' : '. Unread'}`}
                    >
                      {agentForNotification(item) ? (
                        <View style={s.iconWrap}>
                          <Mascot bot={agentForNotification(item)!} size={28} />
                        </View>
                      ) : (
                        <View style={s.iconWrap}>
                          <Ionicons name={iconForKind(item.kind)} size={20} color={color.textDim} />
                        </View>
                      )}
                      <View style={{ flex: 1 }}>
                        <View style={s.titleRow}>
                          <Text style={[type.body, { color: color.text, fontFamily: font.bodyMedium, flex: 1 }]}>
                            {item.title}
                          </Text>
                          {!item.read_at ? <View style={s.unreadDot} /> : null}
                        </View>
                        <Text style={[type.label, { color: color.muted, marginTop: 2 }]} numberOfLines={2}>
                          {item.body}
                        </Text>
                        <Text style={[type.label, { color: color.muted, marginTop: 4 }]}>{formatWhen(item.created_at)}</Text>
                      </View>
                    </Pressable>
                  ))}
                </Card>
                {/* 10.4 design shows no pagination control at all — older rows load
                    silently from the onScroll near-bottom check above. A spinner
                    rather than a tappable button keeps that invisible, while still
                    telling a member mid-fetch that more is on the way. */}
                {loadingMore ? (
                  <View style={s.loadMore}>
                    <ActivityIndicator size="small" color={color.muted} />
                  </View>
                ) : null}
              </ScrollView>
            )}

            <Pressable
              onPress={() => {
                close()
                router.push('/notification-preferences')
              }}
              style={s.settingsRow}
              accessibilityRole="button"
            >
              <Ionicons name="settings-outline" size={16} color={color.muted} />
              <Text style={[type.label, { color: color.muted }]}>Notification settings</Text>
            </Pressable>
          </>
        )}
      </Sheet>
    </>
  )
}

const makeStyles = (color: ColorTokens) =>
  StyleSheet.create({
    row: { flexDirection: 'row', gap: space.md, paddingVertical: space.md, paddingHorizontal: space.lg },
    rowDivider: { borderTopWidth: 1, borderTopColor: color.border },
    iconWrap: {
      width: 34,
      height: 34,
      borderRadius: radius.md,
      backgroundColor: color.bg,
      alignItems: 'center',
      justifyContent: 'center',
    },
    titleRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
    unreadDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: color.accent },
    loadMore: {
      alignItems: 'center',
      paddingVertical: space.md,
      marginTop: space.sm,
    },
    settingsRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: space.sm,
      justifyContent: 'center',
      paddingVertical: space.md,
      borderTopWidth: 1,
      borderTopColor: color.border,
    },
  })
