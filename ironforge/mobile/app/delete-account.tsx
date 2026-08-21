import { useState } from 'react'
import { View, Text, ScrollView, Pressable, StyleSheet, Alert } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { useRouter } from 'expo-router'
// Deep import: `from '@expo/vector-icons'` reaches all 19 icon fonts.
import Ionicons from '@expo/vector-icons/Ionicons'
import useSWR from 'swr'
import { api, ApiError } from '@/api/client'
import type { DeletionStatusResponse, DeletionRequestResponse } from '@/api/types'
import { color, space, radius, type, font } from '@/theme/tokens'
import { Card, Loading, ErrorState } from '@/components/ui'
import { SUPPORT_EMAIL } from '@/support/contact'

/**
 * Delete Account — App Store Review Guideline 5.1.1(v).
 *
 * The app previously had NO deletion path at all: `/delete-account` existed on the web
 * and satisfied Google Play, which accepts a public URL. Apple does not — deletion has
 * to be initiable from inside the app, and its absence is one of the most common first
 * -submission rejections there is.
 *
 * This calls the SAME endpoint the web page does, so there is one deletion policy rather
 * than two implementations that will drift:
 *   - it REFUSES (409) while any position is unsettled, and says which ones,
 *   - it cancels billing and disconnects the brokerage,
 *   - it opens a 14-day grace period the customer can call off.
 *
 * 🚨 The 409 body carries a human sentence in `message` while `error` is the machine code
 * `open_positions`. Reading `err.message` here would show a customer the literal string
 * "open_positions" at the single worst moment to do that — hence ApiError.humanMessage.
 *
 * 🚨 This screen does NOT sign the customer out on success, and that is deliberate: the
 * server leaves sessions alive precisely so the request can be cancelled during the
 * grace period. A purge you cannot call off is not a grace period.
 */
export default function DeleteAccountScreen() {
  const router = useRouter()
  const { data, error, isLoading, mutate } = useSWR<DeletionStatusResponse>(
    '/api/account/deletion-request',
    (p: string) => api<DeletionStatusResponse>(p),
  )
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)

  const pending = data?.pending === true
  const graceDays = data?.gracePeriodDays ?? 14

  function confirmDelete() {
    // Two taps, and the second one names the consequence rather than saying "Confirm".
    // Alert is used rather than a Modal because there are only two choices here —
    // Android's three-button cap (which forced the report-reason picker to a Modal) is
    // not in play.
    Alert.alert(
      'Delete your IronForge account?',
      `Your membership will be cancelled and your brokerage connection removed immediately. ` +
        `You will have ${graceDays} days to change your mind before anything is erased.`,
      [
        { text: 'Keep my account', style: 'cancel' },
        { text: 'Request deletion', style: 'destructive', onPress: requestDelete },
      ],
    )
  }

  async function requestDelete() {
    setBusy(true)
    setFailure(null)
    try {
      const res = await api<DeletionRequestResponse>('/api/account/deletion-request', {
        method: 'POST',
      })
      // Re-read state rather than trusting the response shape: `alreadyRequested` and a
      // fresh request return different bodies, and the GET is the one source of truth
      // this screen renders from.
      await mutate()
      Alert.alert(
        res.alreadyRequested ? 'Deletion already requested' : 'Deletion requested',
        `Nothing is erased for ${res.gracePeriodDays} days. You can cancel the request from this screen at any point before then.`,
      )
    } catch (e) {
      setFailure(e instanceof ApiError ? e.humanMessage : (e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function cancelRequest() {
    setBusy(true)
    setFailure(null)
    try {
      await api('/api/account/deletion-request', { method: 'DELETE' })
      await mutate()
      // Stated plainly because it is the thing people assume and it is not true. The
      // server deliberately does not resubscribe or reconnect — neither is ours to
      // re-create on someone's behalf.
      Alert.alert(
        'Deletion cancelled',
        'Your account is no longer scheduled for deletion. Your membership and brokerage connection were NOT restored — you will need to set those up again yourself.',
      )
    } catch (e) {
      setFailure(e instanceof ApiError ? e.humanMessage : (e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <SafeAreaView style={s.screen} edges={['top']}>
      <View style={s.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} accessibilityLabel="Back">
          <Ionicons name="chevron-back" size={26} color={color.text} />
        </Pressable>
        <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold, fontSize: 18 }]}>
          Delete Account
        </Text>
      </View>

      {isLoading ? (
        <Loading />
      ) : error ? (
        <ErrorState message={String((error as Error).message)} onRetry={() => mutate()} />
      ) : (
        <ScrollView contentContainerStyle={{ padding: space.lg }}>
          {pending ? (
            <Card>
              <View style={s.rowStart}>
                <Ionicons name="alert-circle" size={20} color={color.warn} />
                <Text
                  style={[
                    type.body,
                    { color: color.text, fontFamily: font.bodyBold, marginLeft: space.sm },
                  ]}
                >
                  Deletion requested
                </Text>
              </View>
              <Text style={[type.body, { color: color.textDim, marginTop: space.sm }]}>
                {data?.requestedAt
                  ? `Requested ${formatRequestedAt(data.requestedAt)}. `
                  : ''}
                Your data is erased after the {graceDays}-day grace period. Cancel below if you
                want to keep the account.
              </Text>
            </Card>
          ) : (
            <>
              <Text style={[type.body, { color: color.textDim }]}>
                Deleting your account is permanent. Here is exactly what happens when you
                request it:
              </Text>
              <View style={{ marginTop: space.md }}>
                <Bullet>Your membership is cancelled straight away — no further charges.</Bullet>
                <Bullet>
                  Your brokerage connection is removed, so IronForge can no longer see or place
                  anything in your account.
                </Bullet>
                <Bullet>
                  Your profile, trade history and community posts are erased after {graceDays}{' '}
                  days.
                </Bullet>
                <Bullet>
                  You can cancel the request at any point during those {graceDays} days.
                </Bullet>
              </View>

              <Card style={{ marginTop: space.lg }}>
                <View style={s.rowStart}>
                  <Ionicons name="information-circle-outline" size={18} color={color.textDim} />
                  <Text
                    style={[type.label, { color: color.textDim, marginLeft: space.sm, flex: 1 }]}
                  >
                    Open positions block deletion. If anything is still running, close it first
                    — we will not delete an account with real money exposed behind it.
                  </Text>
                </View>
              </Card>
            </>
          )}

          {failure ? (
            <Text style={[type.body, { color: color.neg, marginTop: space.lg }]}>{failure}</Text>
          ) : null}

          {pending ? (
            <Pressable
              onPress={cancelRequest}
              disabled={busy}
              style={[s.outlineBtn, busy && { opacity: 0.4 }]}
            >
              <Text style={[type.body, { color: color.accent, fontFamily: font.bodyMedium }]}>
                {busy ? 'Working…' : 'Cancel deletion request'}
              </Text>
            </Pressable>
          ) : (
            <Pressable
              onPress={confirmDelete}
              disabled={busy}
              style={[s.destructive, busy && { opacity: 0.4 }]}
            >
              <Text style={[type.body, { color: color.neg, fontFamily: font.bodyMedium }]}>
                {busy ? 'Working…' : 'Delete my account'}
              </Text>
            </Pressable>
          )}

          <Text style={[type.label, { color: color.muted, marginTop: space.lg }]}>
            Questions before you do this? {SUPPORT_EMAIL}
          </Text>
        </ScrollView>
      )}
    </SafeAreaView>
  )
}

function Bullet({ children }: { children: React.ReactNode }) {
  return (
    <View style={s.bullet}>
      <Text style={[type.body, { color: color.accent }]}>•</Text>
      <Text style={[type.body, { color: color.textDim, flex: 1, marginLeft: space.sm }]}>
        {children}
      </Text>
    </View>
  )
}

/**
 * 🚨 Parsed as LOCAL time, not UTC. `new Date('2026-08-31')` is midnight UTC and renders
 * as the 30th anywhere west of Greenwich — which is every US timezone, i.e. every
 * customer. Same trap the membership renewal date already documents.
 */
function formatRequestedAt(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return 'recently'
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: color.bg },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    borderBottomColor: color.border,
    borderBottomWidth: 1,
  },
  rowStart: { flexDirection: 'row', alignItems: 'flex-start' },
  bullet: { flexDirection: 'row', alignItems: 'flex-start', marginBottom: space.sm },
  outlineBtn: {
    marginTop: space.lg,
    borderColor: color.border,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingVertical: space.md,
    alignItems: 'center',
  },
  destructive: {
    marginTop: space.lg,
    borderColor: color.neg,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingVertical: space.md,
    alignItems: 'center',
  },
})
