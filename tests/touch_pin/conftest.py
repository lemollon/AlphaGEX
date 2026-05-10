"""touch_pin test configuration: skip DB-marked tests when DATABASE_URL is unset."""
import os
import pytest


def _has_db():
    return bool(os.environ.get("DATABASE_URL"))


def pytest_configure(config):
    config.addinivalue_line("markers", "db: requires production DATABASE_URL set")


def pytest_collection_modifyitems(config, items):
    if _has_db():
        return
    skip_db = pytest.mark.skip(reason="DATABASE_URL not set; skipping DB-backed test")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip_db)
