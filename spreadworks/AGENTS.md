# Report changes

Before changing morning, market-open, intraday or full report code, read
`REPORT_REQUIREMENTS.md`, `backend/report_contract.py` and
`backend/report_policy.py`. These files are the durable report specification;
chat history and model-generated prose are not authoritative implementations.

Preserve every existing required field when adding requirements. Extend the
versioned contract, deterministic producer mapping, renderer and failure-path
tests together. Do not satisfy a new requirement with a prompt-only change.

Run the strict report checks listed in `REPORT_REQUIREMENTS.md`. Do not bypass
publication validation or replace missing observations with invented numbers.
Keep existing schedules and notification destinations enabled unless the user
explicitly asks to change them. No report changes authorize broker orders.
