"""Every routed page must bring its own scroll container.

App.jsx's shell is `flex flex-col h-dvh w-full overflow-hidden`, so a route
that does not supply one is CLIPPED AT THE VIEWPORT — everything below the
fold is unreachable, with no scrollbar to hint that it exists.

/session shipped without one. It went unnoticed because the page was short
enough to fit; it only became visible once the flow track, the calibration
scorecard and the session-history fold pushed the content past a screen. That
is the worst kind of layout bug: it appears later, on a page that was fine
when it was written, and it looks like missing data rather than missing CSS.
"""
import re
from pathlib import Path

PAGES = Path(__file__).resolve().parents[1] / "frontend" / "src" / "pages"
APP = Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.jsx"

# BuilderPage's layout lives in App.jsx (it owns the full-bleed builder shell),
# so it is scrolled by the container there rather than by its own root.
EXEMPT = {"BuilderPage.jsx"}


def _routed_pages() -> set[str]:
    src = APP.read_text(encoding="utf-8")
    return {f"{m}.jsx" for m in re.findall(r"element=\{<(\w+)\s*/>\}", src)}


def test_every_routed_page_can_scroll():
    missing = []
    for name in sorted(_routed_pages() - EXEMPT):
        f = PAGES / name
        if not f.exists():
            continue
        body = f.read_text(encoding="utf-8")
        if "overflow-y-auto" not in body and "overflowY" not in body:
            missing.append(name)
    assert not missing, (
        "these routed pages have no vertical scroll container and will be "
        f"clipped by App.jsx's h-dvh/overflow-hidden shell: {missing}")


def test_the_shell_really_does_clip():
    """If this ever stops being true the rule above can be relaxed — but it
    must be a deliberate change, not a silent one."""
    src = APP.read_text(encoding="utf-8")
    assert "h-dvh" in src and "overflow-hidden" in src
