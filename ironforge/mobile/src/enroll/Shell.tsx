import { View, Text, Pressable, ScrollView, StyleSheet } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { useRouter } from 'expo-router'
import type { ReactNode } from 'react'
// Deep import: `from '@expo/vector-icons'` reaches all 19 icon fonts.
import Ionicons from '@expo/vector-icons/Ionicons'
import { color, space, type, font } from '@/theme/tokens'
import { ProgressBar } from '@/components/ui'

/** Total numbered screens in the funnel, per the SERVER's real order (plan before
 * legal, brokerage before agent — see the PR description for why this differs from
 * the originally-briefed screen order). create-account=1 … review=8; `done` has no
 * number, same as the web /enroll/done page (topRight="none" there). */
export const ENROLL_TOTAL_STEPS = 8

/** Shared chrome for every /enroll/* screen: back chevron, title, step progress, error banner. */
export function EnrollShell({
  title,
  step,
  error,
  children,
}: {
  title: string
  /** 1-based step number, or omit for the unnumbered `done` screen. */
  step?: number
  error?: string | null
  children: ReactNode
}) {
  const router = useRouter()
  return (
    <SafeAreaView style={s.screen} edges={['top']}>
      <View style={s.header}>
        {router.canGoBack() ? (
          <Pressable onPress={() => router.back()} hitSlop={12} accessibilityLabel="Back">
            <Ionicons name="chevron-back" size={26} color={color.text} />
          </Pressable>
        ) : (
          <View style={{ width: 26 }} />
        )}
        <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold, fontSize: 18 }]}>{title}</Text>
        <View style={{ width: 26 }} />
      </View>

      {step != null ? (
        <View style={{ paddingHorizontal: space.lg, paddingTop: space.md }}>
          <ProgressBar step={step} total={ENROLL_TOTAL_STEPS} />
        </View>
      ) : null}

      <ScrollView
        contentContainerStyle={{ padding: space.lg, paddingBottom: space.xxl }}
        keyboardShouldPersistTaps="handled"
      >
        {error ? (
          <View style={s.errorBanner}>
            <Text style={[type.body, { color: color.neg }]}>{error}</Text>
          </View>
        ) : null}
        {children}
      </ScrollView>
    </SafeAreaView>
  )
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: color.bg },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    borderBottomColor: color.border,
    borderBottomWidth: 1,
  },
  errorBanner: {
    borderWidth: 1,
    borderColor: color.neg,
    borderRadius: 10,
    padding: space.md,
    marginBottom: space.lg,
  },
})
