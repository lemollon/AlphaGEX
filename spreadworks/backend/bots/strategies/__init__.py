"""SpreadWorks bot strategy builders.

`CREDIT_STRATEGIES` is the single source of truth for which strategies collect a
net credit at entry (entry_price = credit received, P&L = credit − cost-to-close)
versus pay a net debit. `LONG_OPTION_STRATEGIES` identifies the single-long
option modes whose liquidation value is bounded below by zero. Keeping both
sets here prevents the scanner and executor from drifting apart.
"""
from __future__ import annotations

CREDIT_STRATEGIES = frozenset(
    {"iron_condor", "iron_butterfly", "double_diagonal_credit",
     "bull_put_spread", "bear_call_spread"}
)

LONG_OPTION_STRATEGIES = frozenset(
    {"updraft", "backdraft", "reversal", "em_breach", "afterburn",
     "weekender", "flashpoint", "afterglow", "ember", "tempest",
     "astra3"}
)
