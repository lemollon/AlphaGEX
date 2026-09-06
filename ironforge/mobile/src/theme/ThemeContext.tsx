/**
 * ThemeProvider / useTheme() — Light / Dark / System appearance.
 *
 * Not unit-tested directly (it's a React hook/provider; vitest.config.ts scopes to
 * pure `src/**\/*.test.ts` modules with no renderer). The logic worth testing —
 * palette resolution and the persistence round-trip — lives in palette.ts and
 * preference.ts, both plain .ts and both covered.
 *
 * Renders synchronously on the DARK palette (the brand default) so there is never a
 * flash of the wrong theme while the stored preference loads from SecureStore; once
 * it resolves (or resolves to nothing, i.e. no preference ever saved) the provider
 * re-renders with the correct scheme. 'system' with no preference saved is NOT the
 * default — see preference.ts.
 */
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useColorScheme } from 'react-native'
import {
  dark,
  light,
  resolveScheme,
  resolveTone,
  type AppearancePreference,
  type ColorTokens,
  type Scheme,
} from './palette'
import { loadAppearancePreference, saveAppearancePreference } from './preference'

export interface ThemeContextValue {
  colors: ColorTokens
  scheme: Scheme
  /** The customer's saved choice — 'system' | 'light' | 'dark'. Not necessarily equal
   *  to `scheme`: 'system' resolves to whichever `scheme` the OS currently reports. */
  preference: AppearancePreference
  setPreference: (pref: AppearancePreference) => void
  /** Translate a DARK-canonical hex (from card-stats.ts, alerts/banner.ts, or any
   *  other pure helper that still returns theme/tokens.ts's dark values) into the
   *  currently active scheme's equivalent. Identity in dark scheme. */
  resolveTone: (hex: string) => string
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

export function ThemeProvider({ children }: { children: ReactNode }) {
  const systemScheme = useColorScheme() // 'light' | 'dark' | null
  const [preference, setPreferenceState] = useState<AppearancePreference>('dark')

  useEffect(() => {
    let cancelled = false
    loadAppearancePreference().then((stored) => {
      if (!cancelled && stored) setPreferenceState(stored)
    })
    return () => {
      cancelled = true
    }
  }, [])

  function setPreference(pref: AppearancePreference) {
    setPreferenceState(pref)
    void saveAppearancePreference(pref)
  }

  const scheme = resolveScheme(preference, systemScheme === 'light' ? 'light' : systemScheme === 'dark' ? 'dark' : null)
  const colors = scheme === 'light' ? light : dark

  const value = useMemo<ThemeContextValue>(
    () => ({
      colors,
      scheme,
      preference,
      setPreference,
      resolveTone: (hex: string) => resolveTone(hex, scheme),
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [colors, scheme, preference],
  )

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme() must be called inside <ThemeProvider>')
  return ctx
}
