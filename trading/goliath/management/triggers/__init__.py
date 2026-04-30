"""GOLIATH management triggers (T1..T8).

Each module exposes ``evaluate(position, ...) -> Optional[ManagementAction]``.
The engine (parent module) imports each submodule by name and runs them
in priority order.
"""
