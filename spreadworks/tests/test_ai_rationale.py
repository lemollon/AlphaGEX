"""AI entry rationale — must be fail-safe and never raise."""
from __future__ import annotations
import backend.bots.ai_rationale as air


class _FakeBlock:
    type = "text"
    def __init__(self, t): self.text = t


class _FakeMsg:
    def __init__(self, t): self.content = [_FakeBlock(t)]


class _FakeClient:
    def __init__(self, text=None, raise_exc=None):
        self._text = text; self._raise = raise_exc
        self.messages = self
    def create(self, **kwargs):
        if self._raise: raise self._raise
        return _FakeMsg(self._text)


CTX = {"ticker": "NVDA", "kind": "bull_call_spread", "direction": "bullish",
       "setup": "dip", "magnitude_pct": 0.067, "rsi": 5.0}


def test_returns_text_on_success(monkeypatch):
    monkeypatch.setattr(air, "_client", lambda: _FakeClient(text="Bought the NVDA dip."))
    out = air.generate_entry_rationale(bot="undertow", signal_context=CTX)
    assert out == "Bought the NVDA dip."


def test_returns_none_on_exception(monkeypatch):
    monkeypatch.setattr(air, "_client", lambda: _FakeClient(raise_exc=RuntimeError("boom")))
    assert air.generate_entry_rationale(bot="undertow", signal_context=CTX) is None


def test_returns_none_when_disabled(monkeypatch):
    monkeypatch.setattr(air, "_enabled", lambda: False)
    assert air.generate_entry_rationale(bot="undertow", signal_context=CTX) is None


def test_returns_none_on_empty(monkeypatch):
    monkeypatch.setattr(air, "_client", lambda: _FakeClient(text="   "))
    assert air.generate_entry_rationale(bot="undertow", signal_context=CTX) is None
