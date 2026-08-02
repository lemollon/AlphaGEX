# Universal Links / App Links association files

These are **templates, not live files.** They are deliberately NOT in
`webapp/public/.well-known/` yet, because both require identifiers that do not exist
until the Apple and Google developer accounts are created.

**Do not publish them with placeholder IDs.** A malformed association file is worse than
an absent one: iOS caches association failures, so shipping a wrong `appID` can leave
Universal Links broken on devices even after the correct file goes up.

## When the accounts exist

1. **Apple** — replace `TEAMID` with the Apple Developer Team ID (Membership page in
   the developer portal). The bundle id is already `trade.ironforge.app`.
2. **Android** — replace the `sha256_cert_fingerprints` entry with the release signing
   certificate's SHA-256. With EAS this is
   `eas credentials` → Android → Keystore → SHA256 Fingerprint.
   Include the Play App Signing fingerprint too if Play re-signs the build, or App Links
   will verify in internal testing and fail in production.
3. Copy both into `webapp/public/.well-known/` and deploy.
4. Verify:
   - `curl -sI https://ironforge.trade/.well-known/apple-app-site-association` → **200**,
     `content-type: application/json`, and **no redirect**.
   - `https://developers.google.com/digital-asset-links/tools/generator` for Android.

## The gate that was already fixed

`apple-app-site-association` has **no file extension**, and the middleware page matcher
excludes static assets by extension (`...|woff2?)$`). So the file matched the matcher and
Apple's cookieless fetcher got a **307 to /login** — after which Universal Links silently
never verify, with no error and no log anywhere.

`isPublicPath()` in `webapp/src/lib/auth/access.ts` now returns true for
`/.well-known/`, and `access.test.ts` pins it. Do not remove that branch.
