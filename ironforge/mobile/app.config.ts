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
  // The EAS account that OWNS this project. Required because the project lives under
  // the organization while builds are run by a personal account that happens to be a
  // member — without it, EAS refuses the build rather than guessing which account the
  // credentials and build minutes should belong to.
  owner: 'ironforge-technologies-llc',
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
  // EAS Update. Until expo-updates was installed the `channel` keys in eas.json were
  // inert, so a one-line JS fix still meant a full store release and a review wait.
  updates: {
    url: 'https://u.expo.dev/06291eb6-55ec-48a3-9e24-80808946023b',
  },
  /**
   * fingerprint, NOT the appVersion policy `eas update:configure` suggests.
   *
   * `version` above is a hardcoded '1.0.0' and the store build numbers auto-increment
   * remotely (eas.json appVersionSource: remote), so under an appVersion policy every
   * build ever made would share the runtime version "1.0.0". An update published after
   * a native dependency changed would then be handed to installed binaries that do not
   * contain that native code — which fails at runtime, on a screen showing somebody's
   * open positions, with no way to roll back from the user's side.
   *
   * The fingerprint policy derives the runtime version from the actual native graph, so
   * an update can only ever reach a binary it genuinely matches. Native changes simply
   * stop being OTA-able, which is the correct answer rather than a silent crash.
   */
  runtimeVersion: { policy: 'fingerprint' },
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
  plugins: [
    'expo-router',
    'expo-secure-store',
    'expo-local-authentication',
    // Oswald (display) + Inter (body) are declared in theme/tokens.ts and were never
    // actually loaded, so every fontFamily silently fell back to the system face and
    // no screen matched the approved type. The plugin is required for the native build;
    // useFonts() in app/_layout.tsx covers the JS side.
    'expo-font',
    // Android API level is PINNED, not inherited from whatever the Expo SDK happens to
    // default to. Google Play requires new apps and updates to target API 36 from
    // 2026-08-31; a silent default drift below that is not a warning, it is an outright
    // upload rejection. Stating it here means the requirement is visible in the diff the
    // day it changes rather than discovered at submission time.
    [
      'expo-build-properties',
      {
        android: { compileSdkVersion: 36, targetSdkVersion: 36 },
      },
    ],
  ],
  extra: {
    apiBase: API_BASE,
    // The EAS project (expo.dev org "IronForge Technologies LLC", project "ironforge").
    // Hardcoded rather than read from the environment because it is a permanent
    // identifier for THIS project — an env var that happened to be unset would make
    // `eas build` silently offer to create a second project instead of failing.
    eas: { projectId: '06291eb6-55ec-48a3-9e24-80808946023b' },
  },
  experiments: { typedRoutes: true },
}

export default config
