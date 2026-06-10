"""Cheap, fail-safe entry rationale. EXPLANATORY ONLY — never gates/sizes/exits a trade.

Calls Claude (Opus 4.8) once per OPEN with a tiny structured context, ~160 output
tokens. Any failure returns None and the caller opens the trade anyway. Kill via
env SPREADWORKS_AI_RATIONALE=false.
"""
from __future__ import annotations
import json
import logging
import os
from typing import Any

logger = logging.getLogger("spreadworks.bots.ai_rationale")

MODEL = "claude-opus-4-8"
_SYSTEM = (
    "You explain a single options paper-trade in 1-2 plain sentences for a trader's "
    "dashboard. Say WHY the bot entered and WHAT level or exit it is watching. Be "
    "concrete and brief. No preamble, no markdown, no disclaimers. Output only the "
    "explanation text."
)


def _enabled() -> bool:
    return os.getenv("SPREADWORKS_AI_RATIONALE", "true").strip().lower() not in ("false", "0", "no")


def _client():
    import anthropic
    return anthropic.Anthropic(max_retries=0, timeout=8.0)


def generate_entry_rationale(*, bot: str, signal_context: dict[str, Any]) -> str | None:
    if not _enabled():
        return None
    try:
        client = _client()
        msg = client.messages.create(
            model=MODEL,
            max_tokens=160,
            system=_SYSTEM,
            messages=[{"role": "user", "content":
                       f"Bot {bot} just opened this paper trade:\n{json.dumps(signal_context)}"}],
        )
        text = ""
        for block in getattr(msg, "content", []) or []:
            if getattr(block, "type", None) == "text":
                text += block.text
        text = text.strip()
        return text or None
    except Exception as e:  # noqa: BLE001 — must never raise into the scanner
        logger.warning(f"[ai_rationale] {bot} failed: {e}")
        return None
