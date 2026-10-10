"""Opportunity Scanner API: /api/spreadworks/opportunity

STORE-AND-SERVE ONLY. ThetaData (the primary market-data source) is a local
terminal on Leron's laptop (http://127.0.0.1:25510) — unreachable from
Render — so all computation happens on the laptop:
    C:\\Users\\lemol\\dev\\meltup\\opportunity\\build_opportunity_snapshot.py
which builds the full snapshot (THE RULE's dividend-raise rows, the same-day
SPY put spread, FilingSense) and POSTs it here. This module's job is exactly
two things: persist whatever gets pushed, and serve the last one back with
its age so the page can show staleness. No APScheduler job, no market-data
calls, no FastAPI-side computation — opportunity_scanner.py (imported below
only for its pure, network-free rule/wording functions) never talks to
ThetaData/Polygon/yfinance itself.

Persistence: uses the app's existing SQLAlchemy/Postgres setup
(models.OpportunitySnapshot / models.OpportunityFilingSenseRow) when
DATABASE_URL is configured — same `if SessionLocal is None` guard
routes_risk.py uses everywhere else in this backend. Falls back to JSON
files under OPPORTUNITY_DATA_DIR (default <spreadworks>/data) when it isn't,
so a Render preview / local dev run without a database still works instead
of 500ing on every push.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, HTTPException, Request

from . import opportunity_scanner as scanner
from .db import SessionLocal

logger = logging.getLogger(__name__)
CT = ZoneInfo("America/Chicago")

router = APIRouter(prefix="/api/spreadworks/opportunity", tags=["Opportunity Scanner"])

_DATA_DIR = Path(os.environ.get("OPPORTUNITY_DATA_DIR") or
                  (Path(__file__).resolve().parent.parent / "data"))
_SNAPSHOT_JSON_STORE = _DATA_DIR / "opportunity_snapshot.json"
_FS_JSON_STORE = _DATA_DIR / "opportunity_filingsense_rows.json"


def _require_push_key(x_opportunity_key: str | None) -> None:
    expected = os.environ.get("OPPORTUNITY_PUSH_KEY", "").strip()
    if not expected or x_opportunity_key != expected:
        raise HTTPException(status_code=401, detail="invalid or missing X-Opportunity-Key")


# ---------------------------------------------------------------------------
# Snapshot storage — DB when available, JSON file otherwise
# ---------------------------------------------------------------------------
def _load_snapshot() -> dict | None:
    if SessionLocal is not None:
        from .models import OpportunitySnapshot
        db = SessionLocal()
        try:
            rec = db.get(OpportunitySnapshot, "latest")
            if rec is None:
                return None
            try:
                return json.loads(rec.payload_json)
            except (json.JSONDecodeError, TypeError):
                return None
        finally:
            db.close()

    if not _SNAPSHOT_JSON_STORE.exists():
        return None
    try:
        return json.loads(_SNAPSHOT_JSON_STORE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _store_snapshot(snapshot: dict) -> None:
    payload = json.dumps(snapshot, default=str)
    if SessionLocal is not None:
        from .models import OpportunitySnapshot
        db = SessionLocal()
        try:
            rec = db.get(OpportunitySnapshot, "latest")
            if rec is None:
                db.add(OpportunitySnapshot(id="latest", payload_json=payload))
            else:
                rec.payload_json = payload
            db.commit()
        finally:
            db.close()
        return

    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _SNAPSHOT_JSON_STORE.write_text(payload, encoding="utf-8")


# ---------------------------------------------------------------------------
# FilingSense row storage — DB when available, JSON file otherwise. Kept as
# a secondary ingestion path (Leron: "keep the FilingSense push endpoint");
# the primary path is the laptop script folding rendered FilingSense rows
# directly into the pushed snapshot (see build_opportunity_snapshot.py).
# ---------------------------------------------------------------------------
def _row_id(row: dict) -> str:
    return f"{row.get('ticker', '?')}|{row.get('posted_utc', '?')}"


def _load_filingsense_rows() -> list[dict]:
    if SessionLocal is not None:
        from .models import OpportunityFilingSenseRow
        db = SessionLocal()
        try:
            out = []
            for rec in db.query(OpportunityFilingSenseRow).all():
                try:
                    out.append(json.loads(rec.payload_json))
                except (json.JSONDecodeError, TypeError):
                    continue
            return out
        finally:
            db.close()

    if not _FS_JSON_STORE.exists():
        return []
    try:
        return json.loads(_FS_JSON_STORE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _upsert_filingsense_rows(rows: list[dict]) -> int:
    """Upsert by stable id (ticker+posted timestamp). Returns count written."""
    if SessionLocal is not None:
        from .models import OpportunityFilingSenseRow
        db = SessionLocal()
        try:
            n = 0
            for row in rows:
                rid = _row_id(row)
                rec = db.get(OpportunityFilingSenseRow, rid)
                payload = json.dumps(row, default=str)
                if rec is None:
                    db.add(OpportunityFilingSenseRow(
                        id=rid, ticker=str(row.get("ticker", "?")),
                        posted_utc=str(row.get("posted_utc", "?")), payload_json=payload,
                    ))
                else:
                    rec.payload_json = payload
                n += 1
            db.commit()
            return n
        finally:
            db.close()

    existing = _load_filingsense_rows()
    by_id = {_row_id(r): r for r in existing}
    for row in rows:
        by_id[_row_id(row)] = row
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _FS_JSON_STORE.write_text(json.dumps(list(by_id.values()), default=str, indent=2), encoding="utf-8")
    return len(rows)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
_EMPTY_SNAPSHOT = {
    "as_of_ct": None,
    "dividend_raises": [],
    "dividend_raises_status": "no_snapshot_yet",
    "sameday_spy": {},
    "filingsense": {"rows": [], "scorecard": None, "n_live_total": 0,
                     "window_days": scanner.FS_WINDOW_DAYS},
    "warnings": ["No snapshot has been pushed yet from the laptop."],
}


@router.get("")
async def get_opportunity_snapshot():
    stored = _load_snapshot()
    now_ct = datetime.now(CT)

    if stored is None:
        return {**_EMPTY_SNAPSHOT, "age_seconds": None}

    # FilingSense fallback: if the laptop's own push didn't carry a rendered
    # filingsense section (e.g. an older/lighter snapshot), render fresh
    # from whatever rows have been pushed directly to /filingsense instead
    # of showing a false "nothing to report".
    fs = stored.get("filingsense") or {}
    if not fs.get("rows") and not fs.get("scorecard"):
        fallback_rows = _load_filingsense_rows()
        if fallback_rows:
            stored = {**stored, "filingsense": scanner.filingsense_snapshot(fallback_rows, now_ct)}

    age_seconds = None
    as_of_ct = stored.get("as_of_ct")
    if as_of_ct:
        parsed = scanner.parse_any_iso_to_ct(as_of_ct)
        if parsed is not None:
            age_seconds = (now_ct - parsed).total_seconds()

    return {**stored, "age_seconds": age_seconds}


@router.post("/snapshot")
async def push_opportunity_snapshot(request: Request,
                                     x_opportunity_key: str | None = Header(None)):
    """The laptop script's primary push — the whole snapshot, computed
    entirely off-Render. Replaces the previous /refresh (there is no
    computation left on this side to refresh)."""
    _require_push_key(x_opportunity_key)

    body = await request.json()
    required = ("as_of_ct", "dividend_raises", "sameday_spy", "filingsense", "warnings")
    missing = [k for k in required if k not in body]
    if missing:
        raise HTTPException(status_code=400, detail=f"snapshot missing keys: {missing}")

    _store_snapshot(body)
    logger.info("[OpportunityScanner] snapshot pushed, as_of_ct=%s", body.get("as_of_ct"))
    return {"status": "ok"}


@router.post("/filingsense")
async def push_filingsense_rows(request: Request,
                                 x_opportunity_key: str | None = Header(None)):
    _require_push_key(x_opportunity_key)

    body = await request.json()
    rows = body.get("rows")
    if not isinstance(rows, list):
        raise HTTPException(status_code=400, detail='body must be {"rows": [...]}')

    n = _upsert_filingsense_rows(rows)
    logger.info("[OpportunityScanner] filingsense push: %d row(s) upserted", n)
    return {"status": "ok", "rows_upserted": n}
