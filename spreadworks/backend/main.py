"""Entry point: ``uvicorn backend.main:app``."""

from . import app  # noqa: F401 — re-export for uvicorn
