/**
 * Screen-capture blocking (APP security), native platforms. Re-exports the real
 * hook unchanged — see screen-capture.web.ts for why a second file exists at
 * all: expo-screen-capture has no web implementation, and Metro/Expo resolve
 * `*.web.ts` over this file automatically when bundling for web, so every
 * caller just imports `usePreventScreenCapture` from '@/security/screen-capture'
 * and gets the right one for the platform it's actually running on.
 */
export { usePreventScreenCapture } from 'expo-screen-capture'
