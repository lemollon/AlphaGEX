#!/usr/bin/env python3
"""Verify GOLIATH paper-trading deployment is live on Render.

Run this on any alphagex-* Render service shell that has DATABASE_URL
set (alphagex-api, alphagex-trader, alphagex-collector, alphagex-backtester):

    python scripts/verify_goliath_deployment.py

Reports green/red on each requirement so the operator doesn't have to
go check three separate dashboards. Exit code 0 if all pass, 1 otherwise.

Checks:
    1. DATABASE_URL connectivity
    2. All 6 GOLIATH migration tables exist (028..033)
    3. DISCORD_WEBHOOK_URL env var set (per-service; only meaningful on trader)
    4. trading.goliath imports cleanly (engine, runner, monitoring)
    5. scheduler.goliath_scheduler.add_goliath_jobs is callable
    6. backend/api/routes/goliath_routes loads (smoke check the routes module)
    7. (optional, --hit-api URL) live HTTP check of /api/goliath/status

Usage:
    python scripts/verify_goliath_deployment.py
    python scripts/verify_goliath_deployment.py --hit-api https://alphagex-api.onrender.com
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"

_GOLIATH_TABLES = [
    "goliath_gate_failures",         # 028
    "goliath_news_flags",             # 029
    "goliath_kill_state",             # 030
    "goliath_trade_audit",            # 031
    "goliath_paper_positions",        # 032
    "goliath_equity_snapshots",       # 033
]


def _ok(label: str, detail: str = "") -> None:
    print(f"  {GREEN}✓{RESET} {label}{(' — ' + detail) if detail else ''}")


def _fail(label: str, detail: str = "") -> None:
    print(f"  {RED}✗{RESET} {label}{(' — ' + detail) if detail else ''}")


def _warn(label: str, detail: str = "") -> None:
    print(f"  {YELLOW}!{RESET} {label}{(' — ' + detail) if detail else ''}")


def check_database_url() -> tuple[bool, Optional[str]]:
    print("\n[1/7] DATABASE_URL connectivity")
    url = os.environ.get("DATABASE_URL")
    if not url:
        _fail("DATABASE_URL not set in this shell")
        return False, None
    try:
        import psycopg2  # type: ignore
    except ImportError:
        _fail("psycopg2 not installed")
        return False, url
    try:
        conn = psycopg2.connect(url, connect_timeout=10, sslmode="require")
    except Exception as exc:  # noqa: BLE001
        _fail("connection failed", repr(exc))
        return False, url
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.close()
        _ok("connected")
        return True, url
    finally:
        conn.close()


def check_migrations(url: str) -> bool:
    print("\n[2/7] GOLIATH migration tables (028..033)")
    import psycopg2  # type: ignore
    conn = psycopg2.connect(url, connect_timeout=10, sslmode="require")
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = ANY(%s)",
            (_GOLIATH_TABLES,),
        )
        present = {row[0] for row in cur.fetchall()}
        cur.close()
    finally:
        conn.close()
    missing = [t for t in _GOLIATH_TABLES if t not in present]
    if missing:
        _fail(
            f"{len(present)}/6 tables present",
            f"missing: {', '.join(missing)} -- run scripts/apply_goliath_migrations.py",
        )
        return False
    _ok("all 6 tables present")
    for t in _GOLIATH_TABLES:
        print(f"        · {t}")
    return True


def check_discord_webhook() -> bool:
    print("\n[3/7] DISCORD_WEBHOOK_URL env var")
    val = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not val:
        _warn(
            "DISCORD_WEBHOOK_URL not set in this shell",
            "expected on alphagex-trader; harmless if running on api/collector",
        )
        return False
    if not val.startswith("https://discord"):
        _warn("DISCORD_WEBHOOK_URL set but doesn't look like a Discord webhook URL")
        return False
    masked = val[:30] + "…" + val[-6:] if len(val) > 40 else "***"
    _ok("set", masked)
    return True


def check_trading_imports() -> bool:
    print("\n[4/7] trading.goliath module imports")
    try:
        from trading.goliath import engine, instance, main, monitoring  # noqa: F401
        from trading.goliath.broker import paper_executor  # noqa: F401
        from trading.goliath.data import build_market_snapshot  # noqa: F401
        from trading.goliath import equity_snapshots  # noqa: F401
        _ok("engine, instance, main, monitoring, broker, data, equity_snapshots all import")
        return True
    except Exception as exc:  # noqa: BLE001
        _fail("import failed", repr(exc))
        return False


def check_scheduler_hook() -> bool:
    print("\n[5/7] scheduler.goliath_scheduler.add_goliath_jobs")
    try:
        from scheduler.goliath_scheduler import add_goliath_jobs
    except Exception as exc:  # noqa: BLE001
        _fail("import failed", repr(exc))
        return False

    try:
        from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore
    except ImportError:
        _warn("APScheduler not installed -- can't dry-run add_goliath_jobs")
        return False

    sched = BackgroundScheduler()
    try:
        result = add_goliath_jobs(sched)
    except Exception as exc:  # noqa: BLE001
        _fail("add_goliath_jobs raised", repr(exc))
        return False

    job_ids = [j.id for j in sched.get_jobs()]
    if not result:
        _fail("add_goliath_jobs returned False")
        return False
    _ok(f"hook returned True; registered jobs: {job_ids}")
    return True


def check_routes_module() -> bool:
    print("\n[6/7] backend.api.routes.goliath_routes")
    try:
        sys.path.insert(0, str(_REPO_ROOT / "backend"))
        from api.routes import goliath_routes  # type: ignore
    except Exception as exc:  # noqa: BLE001
        _fail("import failed", repr(exc))
        return False
    paths = [r.path for r in goliath_routes.router.routes]
    expected_count = 13
    if len(paths) < expected_count:
        _fail(f"only {len(paths)} routes found, expected {expected_count}")
        return False
    _ok(f"{len(paths)} routes registered")
    for p in paths:
        print(f"        · {p}")
    return True


def check_live_api(base_url: str) -> bool:
    print(f"\n[7/7] live HTTP check: {base_url}/api/goliath/status")
    try:
        import urllib.request
        import json
    except ImportError:
        _fail("stdlib urllib/json missing")
        return False
    try:
        with urllib.request.urlopen(f"{base_url}/api/goliath/status", timeout=15) as resp:
            body = json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001
        _fail("request failed", repr(exc))
        return False
    if "instances" not in body or len(body.get("instances", [])) != 5:
        _fail(
            "response shape unexpected",
            f"got keys: {list(body.keys())}, instance_count={len(body.get('instances', []))}",
        )
        return False
    _ok(
        "API live",
        f"5 instances, platform_killed={body.get('platform_killed')}, "
        f"platform_cap=${body.get('platform_cap')}",
    )
    return True


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--hit-api",
        default=None,
        help="If set, also do a live HTTP GET to {base}/api/goliath/status "
             "(e.g. https://alphagex-api.onrender.com).",
    )
    args = parser.parse_args(argv)

    print("=" * 70)
    print(" GOLIATH deployment verification")
    print("=" * 70)

    db_ok, url = check_database_url()
    mig_ok = check_migrations(url) if (db_ok and url) else False
    discord_ok = check_discord_webhook()
    trading_ok = check_trading_imports()
    scheduler_ok = check_scheduler_hook()
    routes_ok = check_routes_module()
    api_ok = True
    if args.hit_api:
        api_ok = check_live_api(args.hit_api.rstrip("/"))
    else:
        print("\n[7/7] live HTTP check -- skipped (pass --hit-api URL to enable)")

    print()
    print("=" * 70)
    print(" SUMMARY")
    print("=" * 70)

    must_pass = {
        "DATABASE_URL connect": db_ok,
        "Migrations applied": mig_ok,
        "Trading modules import": trading_ok,
        "Scheduler hook callable": scheduler_ok,
        "Routes module loads": routes_ok,
    }
    advisory = {
        "DISCORD_WEBHOOK_URL set": discord_ok,
    }
    if args.hit_api:
        must_pass["Live API responds"] = api_ok

    for label, ok in must_pass.items():
        marker = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
        print(f"  [{marker}] {label}")
    for label, ok in advisory.items():
        marker = (
            f"{GREEN}SET{RESET}" if ok
            else f"{YELLOW}NOT SET (advisory){RESET}"
        )
        print(f"  [{marker}] {label}")

    failed = [l for l, ok in must_pass.items() if not ok]
    print()
    if failed:
        print(f"{RED}FAIL{RESET}: {len(failed)} check(s) failed -- {', '.join(failed)}")
        return 1
    if not discord_ok:
        print(
            f"{YELLOW}OK{RESET}: hard checks pass. Discord advisory: "
            "set DISCORD_WEBHOOK_URL on alphagex-trader env to enable Discord alerts."
        )
    else:
        print(f"{GREEN}OK{RESET}: GOLIATH deployment is healthy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
