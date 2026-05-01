"""GOLIATH broker layer.

v0.2 paper-only: paper_executor.py simulates fills using current
mid-prices from the Tradier snapshot. v0.3 V3-5 unlocks live Tradier
execution via a separate live_executor module.
"""
from .paper_executor import paper_broker_executor

__all__ = ["paper_broker_executor"]
