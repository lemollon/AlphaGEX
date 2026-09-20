"""EMBER live-execution modules.

Each strategy owns its state and broker idempotency keys.  The surrounding
SpreadWorks scheduler is only the clock; it never invents or alters signals.
"""
