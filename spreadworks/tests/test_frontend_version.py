"""The build-version endpoint that lets an open tab notice it's running old code.

Every page polls its DATA on a timer and never re-fetches its own CODE, so a
tab left open across a deploy runs the OLD UI against FRESH numbers — clocks
ticking, values updating, nothing visibly wrong. That cost real time twice on
2026-08-19: a change that had shipped, deployed and been verified was reported
as missing, because the tab predated the deploy.
"""
from fastapi.testclient import TestClient

from backend import app

client = TestClient(app)


def test_version_reports_the_bundle_actually_on_disk():
    r = client.get("/api/spreadworks/version")
    assert r.status_code == 200
    build = r.json()["build"]
    # Either a real content-hashed bundle, or an honest null when dist is absent
    # (dev checkouts, and CI before the frontend build step).
    assert build is None or (build.startswith("index-") and build.endswith(".js"))


def test_version_matches_what_index_html_actually_serves():
    """🚨 The whole mechanism rests on these being the same string. If the
    endpoint reported a build the page never loads, the banner would either
    never fire or nag forever."""
    import re
    from backend import FRONTEND_DIST

    index = FRONTEND_DIST / "index.html"
    if not index.exists():
        return                                   # nothing built here; covered above
    html = index.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"assets/(index-[A-Za-z0-9_-]+\.js)", html)
    assert client.get("/api/spreadworks/version").json()["build"] == (m.group(1) if m else None)


def test_version_never_raises_even_with_no_dist(monkeypatch):
    """A version check that 500s is worse than no version check."""
    import backend
    from pathlib import Path
    monkeypatch.setattr(backend, "FRONTEND_DIST", Path("/nonexistent-dist-xyz"))
    r = client.get("/api/spreadworks/version")
    assert r.status_code == 200 and r.json()["build"] is None
