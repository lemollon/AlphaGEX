/**
 * Web no-op (#3208 follow-up). expo-screen-capture is a native module with no
 * web implementation — calling its real hook in the web preview crashed the
 * Account screen (and the billing step, which calls the same hook). A browser
 * has no OS-level "block screenshots" concept to hook into anyway, so this is
 * a legitimate no-op rather than a workaround: there is nothing this platform
 * could actually do.
 *
 * Metro/Expo resolve this file over screen-capture.ts automatically for the
 * web bundle (the `.web.ts` suffix), so no caller needs a Platform.OS check —
 * every import of '@/security/screen-capture' already gets the right hook for
 * the platform it's running on.
 */
export function usePreventScreenCapture(): void {
  // Intentionally empty.
}
