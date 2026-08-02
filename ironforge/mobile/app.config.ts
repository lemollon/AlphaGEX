import type { ExpoConfig } from 'expo/config'

/**
 * Bundle id / package name are PERMANENT once either store accepts a build. Changing
 * them later means a new listing and losing every existing install.
 */
const BUNDLE_ID = 'trade.ironforge.app'

/**
 * Which backend the build talks to. Staging must never reach production trading or
 * production push (APP-050), so this is an explicit build-time choice with a
 * production default rather than something inferred from __DEV__ at runtime.
 */
const API_BASE = process.env.EXPO_PUBLIC_API_BASE ?? 'https://ironforge.trade'

const config: ExpoConfig = {
  name: 'IronForge',
  slug: 'ironforge',
  version: '1.0.0',
  orientation: 'portrait',
  scheme: 'ironforge',
  userInterfaceStyle: 'dark',
  // Dark-only for MVP (APP-002). Declaring it here stops the OS from ever handing the
  // app a light appearance the design system has no tokens for.
  backgroundColor: '#0B0B0D',
  icon: './assets/icon/icon-1024.png',
  splash: {
    image: './assets/icon/icon-1024.png',
    resizeMode: 'contain',
    backgroundColor: '#0B0B0D',
  },
  assetBundlePatterns: ['**/*'],
  ios: {
    bundleIdentifier: BUNDLE_ID,
    supportsTablet: false,
    // Universal Links. The paths must match the association file served from
    // webapp/public/.well-known/apple-app-site-association.
    associatedDomains: ['applinks:ironforge.trade'],
    infoPlist: {
      // Shown in the Face ID prompt (APP-008). Apple rejects builds that use
      // biometrics without an explanation string.
      NSFaceIDUsageDescription:
        'Use Face ID to unlock IronForge without re-entering your password.',
      ITSAppUsesNonExemptEncryption: false,
    },
  },
  android: {
    package: BUNDLE_ID,
    adaptiveIcon: {
      foregroundImage: './assets/icon/android/ic_launcher_foreground.png',
      backgroundImage: './assets/icon/android/ic_launcher_background.png',
    },
    // App Links: autoVerify makes Android check /.well-known/assetlinks.json, so
    // ironforge.trade links open the app instead of a chooser.
    intentFilters: [
      {
        action: 'VIEW',
        autoVerify: true,
        data: [{ scheme: 'https', host: 'ironforge.trade', pathPrefix: '/app' }],
        category: ['BROWSABLE', 'DEFAULT'],
      },
    ],
    permissions: ['USE_BIOMETRIC', 'USE_FINGERPRINT'],
  },
  plugins: ['expo-router', 'expo-secure-store', 'expo-local-authentication'],
  extra: {
    apiBase: API_BASE,
    eas: { projectId: process.env.EAS_PROJECT_ID ?? '' },
  },
  experiments: { typedRoutes: true },
}

export default config
