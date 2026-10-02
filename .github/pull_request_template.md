<!--
Fill this in for every PR. If your change doesn't touch a FLAME/SPARK env
flag or trading behavior, you can delete the "Account coverage" section —
but check first: this table exists because FLINT, fast-start/floor,
favorable upsize, and the SPARK add-ons were all shipped to the internal
order path only, and app customers never got them. Nobody noticed for weeks.
-->

## What changed

<!-- One or two sentences: what does this PR do, and why. -->

## Account coverage

**Required whenever this PR adds, removes, or changes behavior for any
FLAME/SPARK env-var flag, or touches `tradier.ts`, `scanner.ts`, or
`customer-executor/**`.** If none of that applies, delete this section.

| Account | Reaches this change? | Reason |
|---|---|---|
| Leron's production account (6YB71371 / "Flame") | Yes / No | |
| Sandbox accounts (User / Matt / Logan) | Yes / No | |
| App customers (customer-executor mirror) | Yes / No | |

- [ ] `src/lib/bot-feature-coverage.ts` is updated for every new/changed env
      flag, with a decision (`covered` / `excluded` / `n/a`) for **all three**
      account types. Every `excluded` entry has a `reason` and an
      `approvedBy`.
- [ ] `npx vitest run src/lib/__tests__/bot-feature-coverage.test.ts` passes.
- [ ] If a "No" above is a gap rather than a deliberate exclusion, it's
      recorded as `excluded — pending (tracked)` in the registry, not left
      out and not marked `covered`.

## Test plan

<!-- What you ran, and what you saw. -->

- [ ] `npx vitest run` (full suite)
- [ ] `npx next build`
