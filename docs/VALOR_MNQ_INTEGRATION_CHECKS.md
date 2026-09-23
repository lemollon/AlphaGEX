# MNQ integration review

The initial isolated 47-test MNQ suite and frontend syntax check passed. The first repository-wide CI run then found eight failures in the existing AST-based execution replay: its extracted non-MNQ position-management method referenced an MNQ mixin helper that the isolated replay did not contain.

The production dispatch now checks ticker and the tagged signal source inline before invoking the MNQ-specific manager. Existing MES/commodity management therefore has no dependency on the new mixin helper in the extracted replay. No stop, SAR, trailing or accounting rule for those instruments was changed to resolve this compatibility issue. The complete strict VALOR suite must pass before merge.

The offline MNQ tests also use a private _mnqtest package namespace for mocked DB/broker adapters, so collecting them alongside other tests cannot overwrite the real trading package in sys.modules. Their 47 tests passed after this isolation correction.

The first full frontend CI run passed TypeScript checking, lint and the application build. The final combined checks and deployment still need to be inspected for the final commit, rather than accepting a green result from an older head.

Release checks: confirm paper mode; no old MNQ position needs migration; inspect all changed files; disable completed cash-research autorun so an application change does not trigger another three-year replay; merge through normal repository rules; verify the expected Render deployment and source-tagged no-entry behavior outside the cash session. A deployment is not proof of future fills. The first valid next-session candle/quote decision and eventual exit are still forward-operation observations.
