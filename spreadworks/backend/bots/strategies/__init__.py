"""SpreadWorks bot strategy builders.

`CREDIT_STRATEGIES` is the single source of truth for which strategies collect a
net credit at entry (entry_price = credit received, P&L = credit − cost-to-close)
versus pay a net debit. Both `bots.executor` and `routes` import it so the
credit/debit branch can never drift between the two.
"""
from __future__ import annotations

CREDIT_STRATEGIES = frozenset(
    {"iron_condor", "iron_butterfly", "double_diagonal_credit",
     "bull_put_spread", "bear_call_spread"}
)
