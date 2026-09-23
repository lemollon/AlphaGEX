# V7 integration correction: JSONB signed zero

The first v7 attempt deployed at September 23, 2026 17:03 UTC and failed closed while verifying the fourth job (MES 2023 regenerated GEX), before claiming completion. Run ID: valor-all-affected-repair-v7-20260923-81026f9eddfc37c9a861. It is preserved as blocked_integrity, not relabeled completed.

PostgreSQL JSONB normalizes -0.0 to 0.0. The evaluator can produce negative floating zero for gross losses when all retained trades are nonlosing. The evidence file retained IEEE negative zero while JSONB dropped its sign, causing strict serialized-hash summary comparison to reject economically identical output. SQL on the live database confirmed this normalization and zero-loss cohorts in the failing job. Its compressed evidence SHA256 still matched. This is a representation mismatch, not proof of altered trade outcomes.

Canonical serialization now recursively normalizes floating zero to positive 0.0. It does not round, change nonzero values, equate booleans with numbers, ignore missing fields, or accept NaN/Infinity. Artifact checksums, per-job source/data/config/runtime identity checks, scenario counts and accounting validations remain enabled. The new source blob is b52ffec0cf94a9e9d2f2843d83231db648d02a4a; it supersedes the initial coordinator hash listed in the original v7 protocol. Runtime manifests contain the new SHA256.

The source change necessarily creates a new run identity and fresh calculations; it cannot resume the old blocked run as though it used the same code. No vendor requests, cost assumptions, strategy rules, production trading settings or old result rows are changed.

Seven targeted local tests passed for this normalization behavior, supplementing the previous 32 repair tests. The repository regression file imports canonical directly from the coordinator. Full real-data round-trip verification is required after deployment; synthetic tests alone are not proof the complete research run succeeds.
