# IronForge Mobile

Expo / React Native client for iOS + Android. Standalone package — this repo has **no
workspace tooling**, so `ironforge/mobile` owns its own lockfile and deploy target,
exactly like `ironforge/webapp`.

## Status

Scaffold + four approved tabs, wired to the live customer API. **Not yet run against a
device or simulator** — no Apple/Google developer accounts exist yet, and `npm install`
has not been executed here, so treat the dependency versions as unverified pins.

| Piece | State |
|---|---|
| Design tokens, primitives, four-tab nav | Written |
| Sign-in + token storage + silent refresh | Written |
| Forge / Ledger / Community / Account | Written, wired to real endpoints |
| Biometric unlock toggle | Written |
| Push registration UI | Not started (backend is ready) |
| Trade Detail, agent activate/pause | Not started (1.1) |
| Ever executed | **No** |

## Run

```bash
npm install
npx expo start                      # dev client / Expo Go
EXPO_PUBLIC_API_BASE=http://localhost:3000 npx expo start   # against a local webapp
```

Builds and store submissions go through **EAS** (no Mac required):

```bash
npx eas build --platform ios --profile preview
npx eas build --platform android --profile preview
```

## Architecture notes worth knowing before editing

**Tokens live in `expo-secure-store`** (Keychain / Keystore), never AsyncStorage —
APP-046 requires tokens encrypted at rest, and AsyncStorage is plaintext.

**Refresh is single-flight.** Screens poll concurrently, so an expired access token
would otherwise fire N parallel refreshes. Refresh tokens are single-use with
server-side reuse detection, so the 2nd..Nth would present an already-rotated token,
trip the theft alarm, and sign the customer out of every device. The shared in-flight
promise in `src/api/client.ts` is a **correctness requirement**, not an optimisation.

**The auth gate keys on the REFRESH token, not the access token.** The access token is
15 minutes and routinely expired at cold start; gating on it would bounce a valid
session to sign-in on every launch.

**Colours are raw hex, copied from `botColors.ts` / `accent.ts` — never from a web class
name.** The webapp's Tailwind config remaps `blue, sky, cyan, orange, …` to `stone`
(gray), so `text-blue-500` renders gray on the web. React Native has no such remap, so
reading a class name and copying "blue" gives you the wrong colour. Spark is `#3B82F6`.

**Polling is 30–60s, not the web's 4s.** A 4-second community poll is a battery and
cellular-data problem on a phone.

## Deliberate omissions

- **No sign-up.** Enrollment is web-only for MVP (per the requirements tracker), which
  also keeps the app clear of Apple's IAP rules.
- **No in-app payment surface.** Billing opens a server-created Stripe portal session in
  the *system browser*, never a WebView — Apple reads an in-app WebView payment flow as
  IAP circumvention, and the customer should see the real URL and padlock.
- **No hardcoded plan name.** The membership card must render `LiveSummary.membership`,
  which the server derives from real subscription rows and fails soft. A hardcoded
  "Forge Automate" card that rendered identically for payers, trialers, and
  non-subscribers is precisely the bug deleted when Stripe landed.

## Security hardening (native — ships in a store build, never OTA)

**Screenshot / screen-recording block.** `expo-screen-capture`'s
`usePreventScreenCapture()` is scoped per-screen (not global) to the two
screens that show billing/payment information: `app/enroll/billing.tsx` (the
subscribe/purchase step) and `app/(tabs)/account.tsx` (membership card +
payment method last 4 — there is no separate `/account/billing` route to
scope this more narrowly). Prevention turns off automatically on unmount, so
no other screen is affected.

**Certificate (public-key) pinning.** `react-native-ssl-public-key-pinning`
pins `ironforge.trade` only — see `src/security/ssl-pinning.ts` for the full
reasoning, the current SPKI hashes, and exact rotation commands. Short
version: pin the WE1 intermediate (current issuer) **and** GTS Root R4
(backup, same CA family) so a routine leaf renewal — or Google moving
issuance from WE1 to its sibling WE2 — never bricks the app; only a
deliberate move off Google Trust Services breaks both at once. Apple, Stripe,
Expo's OTA server, and Sentry are never pinned — this app doesn't own their
certificate chains, and none of them are reached through `fetch` anyway
(StoreKit, expo-updates, @sentry/react-native, or the system browser each
handle their own TLS). A pin mismatch fails closed (the request is blocked)
and surfaces as "Secure connection to IronForge failed" — see
`throwSecureConnectionError` in `src/api/client.ts` and the toast wired in
`app/_layout.tsx` — never a raw native exception or a crash.

Both changes add native modules, so the next iOS/Android build is required
before either takes effect; an OTA update cannot carry them.

## Before the first store submission

1. Apple Team ID + Android release SHA-256 → fill `well-known/*.template`, copy into
   `webapp/public/.well-known/`, deploy, verify both fetch **200 with no redirect**.
2. `EAS_PROJECT_ID` set.
3. `PUSH_ENABLED=true` on `ironforge-customer` (push ships inert otherwise).
4. A seeded reviewer account showing populated tabs on **paper bots only**.
