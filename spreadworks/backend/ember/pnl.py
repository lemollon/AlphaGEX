"""Realized ($) P&L aggregator for the complete 7-strategy EMBER Robinhood
fleet (account 570892331). Every number here comes from the strategy's own
actual closed-trade record -- this module never estimates, backfills, or
substitutes a paper number for a live one, and never fabricates a 0 for a
strategy that has no ledger yet.

WHERE THE DOLLARS ACTUALLY LIVE (verified 2026-10 against the live code and
spreadworks/render.yaml -- read each branch before changing a source here):

  call_diag / night_shift / divhike -- each strategy's own append-only
    ledger.csv (<name>.LEDGER_CSV in backend/ember/legacy/<name>.py). This is
    the ONLY place these three keep every closed trade. The Postgres-mirrored
    ORDER_STATE blob (fleet_runtime._mirror, autonomous_config key
    "ember.<name>.state") exists purely as crash-recovery state for
    CURRENTLY-OPEN positions, not closed-trade history -- night_shift's own
    state in fact holds room for exactly one position at a time
    ({"position": None}), so a closed trade's record is gone from state the
    moment the next position opens. The CSV is authoritative.

    CAUTION -- NOT confirmed durable. Neither spreadworks/render.yaml nor any
    other file in this repo declares a Render disk or sets
    EMBER_CALLDIAG_DATA_DIR / EMBER_NIGHT_DATA_DIR / EMBER_DIVHIKE_DATA_DIR,
    so by default each LEDGER_CSV resolves under the deployed code directory
    (CODE_DIR), which Render replaces on every deploy -- NOT the persistent
    disk Render shows mounted at /var/data. The live Render DASHBOARD may
    have set these three env vars directly, the same way the dashboard's
    Build Command already drifted from this file (see render.yaml's own
    top-of-file note) -- that cannot be confirmed without operator
    shell/dashboard access. If the override is not set, ledger rows from
    before the most recent deploy are already gone, and every future deploy
    drops more. This module reads whatever rows exist right now; it does
    not and cannot recover what a prior deploy already erased.

  xsp_flow (bot_id "xsp-flow-v1") -- the live executor's own state
    (realized_pnl, positions) is mirrored every cycle to Postgres
    autonomous_config under key "ember.xsp-flow-v1.state"
    (runtime._mirror_state) -- durable regardless of local disk.
    `ember_xsp_paper_ledger` is a SEPARATE, explicitly paper-only
    forward-tracking table (its own module docstring: "PAPER-ONLY forward
    call log... XSP Flow is paused live... still wants its signal tracked
    forward") and is never read here as a stand-in for real dollars.

  astra3_live -- the full sleeve state (realized_pnl, history) lives ONLY on
    local disk (astra_live.STATE_PATH); astra_runtime mirrors just a status
    SUMMARY (open_position_count, completed_trades) to Postgres, never the
    dollars (see astra_runtime._record). Read directly off local disk,
    in-process, best-effort -- same ephemeral-disk caution as the three CSV
    strategies above, plus: history is separately capped to the most recent
    100 closed trades inside the state file itself
    (astra_live._complete_trade).

  tv_book / spike -- NO closed-trade P&L source exists in this codebase
    today. tv_book's own module docstring says so explicitly: fills are
    logged to ember_fills.jsonl "instead of call_diag's ledger.csv... the
    task spec asks for a fill log, not a closed-trade P&L ledger." Reported
    with total_pnl=None and an explicit reason -- never a fabricated 0.
"""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

from . import astra_live
from . import runtime as xsp_runtime
from .legacy import call_diag, divhike, night_shift

logger = logging.getLogger("spreadworks.ember.pnl")

XSP_STATE_KEY = "ember.xsp-flow-v1.state"

_DISK_LEDGER_CAVEAT = (
    "read from local disk ledger.csv; EMBER_{prefix}_DATA_DIR is not set "
    "anywhere in this repo's render.yaml, so this path is not confirmed to "
    "be on the Render persistent disk -- history from before the most "
    "recent deploy may already be gone"
)


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true"}


def _read_csv_ledger(path: Path, *, pnl_col: str, date_col: str, prefix: str) -> dict[str, Any]:
    """Read one strategy's closed-trade ledger.csv. Excludes dry_run rows --
    those never moved real money and must never inflate a live $ total."""
    if not path.exists():
        return {
            "source": "disk_csv", "path": str(path), "available": False,
            "total_pnl": None, "trade_count": 0, "trades": [],
            "caveat": _DISK_LEDGER_CAVEAT.format(prefix=prefix),
        }
    trades: list[dict[str, Any]] = []
    total = 0.0
    try:
        with path.open("r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if _truthy(row.get("dry_run")):
                    continue
                raw_pnl = row.get(pnl_col)
                if raw_pnl in (None, ""):
                    continue
                pnl = float(raw_pnl)
                total += pnl
                trades.append({"date": row.get(date_col), "pnl": round(pnl, 2)})
    except (OSError, csv.Error, ValueError) as exc:
        logger.warning("[EMBER:pnl] ledger unreadable for %s: %s", prefix, exc)
        return {
            "source": "disk_csv", "path": str(path), "available": False,
            "total_pnl": None, "trade_count": 0, "trades": [],
            "caveat": f"ledger.csv exists but could not be parsed: {exc}",
        }
    return {
        "source": "disk_csv", "path": str(path), "available": True,
        "total_pnl": round(total, 2), "trade_count": len(trades), "trades": trades,
        "caveat": _DISK_LEDGER_CAVEAT.format(prefix=prefix),
    }


def _read_xsp_flow() -> dict[str, Any]:
    raw = xsp_runtime._config_get(XSP_STATE_KEY)
    if not raw:
        return {
            "source": "postgres_mirror", "available": False,
            "total_pnl": None, "trade_count": 0, "trades": [],
            "caveat": "no mirrored state row yet (autonomous_config key "
                      f"{XSP_STATE_KEY!r})",
        }
    try:
        state = json.loads(raw)
    except json.JSONDecodeError:
        return {
            "source": "postgres_mirror", "available": False,
            "total_pnl": None, "trade_count": 0, "trades": [],
            "caveat": "mirrored state is malformed JSON",
        }
    positions = state.get("positions") if isinstance(state, dict) else None
    closed = [
        p for p in (positions or [])
        if isinstance(p, dict) and p.get("state") == "closed"
    ]
    realized = state.get("realized_pnl") if isinstance(state, dict) else None
    return {
        "source": "postgres_mirror", "available": realized is not None,
        "total_pnl": round(float(realized), 2) if realized is not None else None,
        "trade_count": len(closed),
        # Per-trade $ breakdown is intentionally NOT reported for xsp_flow: the
        # SETTLEMENT agent (an LLM with live broker tools, not deterministic
        # Python -- see xsp_flow_live.py's own prompt docstring) is what writes
        # each closed position's own fields, so no single field name for one
        # trade's pnl is guaranteed across every settlement. Only the
        # cumulative realized_pnl above is a confirmed, code-read field (the
        # same one runtime.read_status() already surfaces).
        "trades": [],
        "caveat": (
            "durable (Postgres-mirrored every cycle); per-trade breakdown is "
            "unavailable -- only the cumulative total is a confirmed field"
            if realized is not None
            else "mirrored state has no realized_pnl field yet"
        ),
    }


def _read_astra3() -> dict[str, Any]:
    if not astra_live.STATE_PATH.exists():
        return {
            "source": "disk_json", "path": str(astra_live.STATE_PATH), "available": False,
            "total_pnl": None, "trade_count": 0, "trades": [],
            "caveat": "no state.json on disk yet",
        }
    try:
        state = json.loads(astra_live.STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "source": "disk_json", "path": str(astra_live.STATE_PATH), "available": False,
            "total_pnl": None, "trade_count": 0, "trades": [],
            "caveat": f"state.json could not be parsed: {exc}",
        }
    sleeve = state.get("sleeve") if isinstance(state, dict) else None
    realized = sleeve.get("realized_pnl") if isinstance(sleeve, dict) else None
    history = state.get("history") if isinstance(state, dict) else None
    trades = [
        {"date": h.get("closed_at_ct"), "pnl": h.get("pnl")}
        for h in (history or [])
        if isinstance(h, dict) and h.get("pnl") is not None
    ]
    return {
        "source": "disk_json", "path": str(astra_live.STATE_PATH),
        "available": realized is not None,
        "total_pnl": round(float(realized), 2) if realized is not None else None,
        "trade_count": (
            sleeve.get("completed_trades") if isinstance(sleeve, dict) else len(trades)
        ),
        "trades": trades,
        "caveat": (
            "NOT mirrored to Postgres -- local-disk-only, not confirmed to be on "
            "the Render persistent disk; astra_runtime only mirrors a status "
            "summary (open_position_count/completed_trades), never the dollars. "
            "history is also capped to the most recent 100 closed trades inside "
            "the state file itself."
        ),
    }


def _no_ledger(reason: str) -> dict[str, Any]:
    return {
        "source": None, "available": False,
        "total_pnl": None, "trade_count": 0, "trades": [],
        "caveat": reason,
    }


def aggregate_pnl() -> dict[str, Any]:
    """Combined realized-$-P&L view across all 7 EMBER strategies, read from
    each strategy's own actual source of truth. See module docstring for
    where every number (and every caveat) comes from."""
    by_strategy: dict[str, dict[str, Any]] = {
        "call_diag": _read_csv_ledger(
            call_diag.LEDGER_CSV, pnl_col="pnl_fill_to_fill", date_col="trade_date",
            prefix="CALLDIAG",
        ),
        "night_shift": _read_csv_ledger(
            night_shift.LEDGER_CSV, pnl_col="pnl_usd", date_col="date", prefix="NIGHT",
        ),
        "divhike": _read_csv_ledger(
            divhike.LEDGER_CSV, pnl_col="pnl_usd", date_col="exit_date", prefix="DIVHIKE",
        ),
        "xsp_flow": _read_xsp_flow(),
        "astra3_live": _read_astra3(),
        "tv_book": _no_ledger(
            "no closed-trade P&L ledger exists for tv_book yet -- its own module "
            "docstring: fills are logged to ember_fills.jsonl, 'the task spec "
            "asks for a fill log, not a closed-trade P&L ledger'"
        ),
        "spike": _no_ledger("no closed-trade P&L ledger exists for spike yet"),
    }
    covered = [name for name, s in by_strategy.items() if s.get("total_pnl") is not None]
    missing = [name for name, s in by_strategy.items() if s.get("total_pnl") is None]
    total = sum(by_strategy[name]["total_pnl"] for name in covered)
    # A combined time series is only honest where a strategy carries real
    # per-trade dates -- call_diag/night_shift/divhike/astra3_live do; xsp_flow
    # and tv_book/spike do not (see each branch above). This is every known
    # closed trade from those four, tagged with its own strategy and sorted by
    # date -- NOT a cumulative fleet-wide equity curve.
    series = sorted(
        (
            {"strategy": name, **trade}
            for name, s in by_strategy.items()
            for trade in s.get("trades", [])
            if trade.get("date")
        ),
        key=lambda t: t["date"],
    )
    return {
        "total_realized_pnl": round(total, 2),
        "strategies_with_data": covered,
        "strategies_without_data": missing,
        "by_strategy": by_strategy,
        "trade_series": series,
    }
