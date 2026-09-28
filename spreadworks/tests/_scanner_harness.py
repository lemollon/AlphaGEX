"""Shared harness for tests that need to run tv_scanner.py's top-level scan directly.

tv_scanner.py has no __main__ guard -- it executes its scan top-level on import by design
(see PR #3104's own test notes: importing it directly would run the live scanner).
Importing the REAL `backend.ember.legacy.tv_scanner` package would also drag in the full
FastAPI app via backend/__init__.py (2000+ lines, DB engine, 69 route modules) since Python
must import every ancestor package first. build_pkg() avoids both: it copies the requested
tv_scanner.py source (defaults to this worktree's current file) plus ember_lock.py,
rate_limiter.py, and shortlist.py into a disposable synthetic package with empty
__init__.py files at every level, so `from . import ember_lock, rate_limiter, shortlist`
resolves without ever touching the real `backend` package.

Not a test file itself (leading underscore keeps pytest from collecting it); imported by
test_tv_scanner_concurrency_equivalence.py and test_tv_scanner_daily_curves.py.
"""
from __future__ import annotations

import io
import itertools
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]  # .../AlphaGEX-wt-tvbook
LEGACY_DIR = REPO_ROOT / "spreadworks" / "backend" / "ember" / "legacy"

_counter = itertools.count()


def build_pkg(tmp_path: Path, name: str, tv_scanner_src: str | None = None) -> str:
    """Returns the dotted module path to import (e.g. via importlib.import_module) --
    importing it runs tv_scanner.py's scan immediately. tv_scanner_src defaults to this
    worktree's current tv_scanner.py; pass an alternate source (e.g. a vendored older
    version) to compare behavior across versions.

    The returned package name is unique per call (derived from `name` plus a counter) --
    NOT a fixed "pkgroot...", because Python caches imports by dotted name in sys.modules
    regardless of sys.path: two calls returning the same name would make the second
    importlib.import_module() silently hand back the FIRST call's already-executed module
    instead of re-running anything, which would make any test comparing two build_pkg()
    results (e.g. old vs new tv_scanner.py, or two different fixture scenarios in the same
    test session) compare a module against itself and pass for the wrong reason."""
    safe_name = re.sub(r"\W", "_", name)  # a Python identifier -- computed outside the
    # f-string below on purpose: f-string expressions may not contain a backslash before
    # Python 3.12 (this repo's CI runs 3.11), and re.sub's pattern needs one (\W).
    pkg_name = f"pkg_{safe_name}_{next(_counter)}"
    root = tmp_path / pkg_name
    pkg = root / pkg_name / "ember" / "legacy"
    pkg.mkdir(parents=True)
    (root / pkg_name / "__init__.py").write_text("")
    (root / pkg_name / "ember" / "__init__.py").write_text("")
    (pkg / "__init__.py").write_text("")
    (pkg / "tv_scanner.py").write_text(
        tv_scanner_src if tv_scanner_src is not None else (LEGACY_DIR / "tv_scanner.py").read_text()
    )
    (pkg / "ember_lock.py").write_text((LEGACY_DIR / "ember_lock.py").read_text())
    for optional in ("rate_limiter.py", "shortlist.py"):
        src = LEGACY_DIR / optional
        if src.exists():
            (pkg / optional).write_text(src.read_text())
    sys.path.insert(0, str(root))
    return f"{pkg_name}.ember.legacy.tv_scanner"


class FakeResponse(io.BytesIO):
    """Stands in for urllib.request.urlopen()'s return value: a context manager with
    .read() (from BytesIO) and .status."""

    def __init__(self, data: bytes, status: int = 200):
        super().__init__(data)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
