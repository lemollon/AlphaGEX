import { useMemo } from 'react'
import { View, Text, Pressable, StyleSheet } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { useRouter } from 'expo-router'
// Deep import: `from '@expo/vector-icons'` reaches all 19 icon fonts.
import Ionicons from '@expo/vector-icons/Ionicons'
import { space, radius, type, font } from '@/theme/tokens'
import { useTheme } from '@/theme/ThemeContext'
import type { ColorTokens } from '@/theme/palette'

/** Join the Waitlist (screen 3 of 3) — terminal screen after a successful submission. */
export default function WaitlistSuccessScreen() {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  const router = useRouter()

  return (
    <SafeAreaView style={s.screen} edges={['top']}>
      <View style={s.header}>
        <Text style={s.wordmark}>
          IRON<Text style={{ color: color.wordmark }}>FORGE</Text>
        </Text>
      </View>

      <View style={s.body}>
        <View style={s.ring}>
          <Ionicons name="checkmark" size={48} color={color.accent} />
        </View>

        <Text style={s.headline}>You&rsquo;re on the list.</Text>
        <Text style={s.subhead}>
          Thanks for joining the IronForge waitlist. Spots are limited.
        </Text>
      </View>

      <View style={s.footer}>
        <Pressable onPress={() => router.replace('/sign-in')} style={s.done}>
          <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold }]}>Done</Text>
        </Pressable>
      </View>
    </SafeAreaView>
  )
}

const makeStyles = (color: ColorTokens) =>
  StyleSheet.create({
    screen: { flex: 1, backgroundColor: color.bg },
    header: {
      alignItems: 'center',
      paddingVertical: space.md,
    },
    wordmark: {
      fontFamily: font.display,
      fontSize: 18,
      letterSpacing: 1,
      color: color.text,
    },
    body: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      paddingHorizontal: space.xl,
    },
    ring: {
      width: 112,
      height: 112,
      borderRadius: 56,
      borderWidth: 3,
      borderColor: color.accent,
      alignItems: 'center',
      justifyContent: 'center',
      marginBottom: space.xl,
    },
    headline: {
      ...type.title,
      fontFamily: font.display,
      color: color.text,
      textAlign: 'center',
    },
    subhead: {
      ...type.body,
      color: color.textDim,
      textAlign: 'center',
      marginTop: space.sm,
    },
    footer: {
      paddingHorizontal: space.xl,
      paddingBottom: space.xl,
    },
    done: {
      backgroundColor: color.accent,
      borderRadius: radius.md,
      paddingVertical: space.lg,
      alignItems: 'center',
    },
  })
