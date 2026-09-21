"""EMBER Fix 3 -- overlap guard shared by tools/ember.py (the scanner, in the
ironforge-data repo) and this executor. Kept as an identical standalone copy
here since the two live in different repos/drives -- see
ironforge-data/tools/ember_lock.py for the scanner's copy. A PID lock file so
Task Scheduler's single-instance policy is real even though run-hidden.vbs
does not wait for the previous run to exit.

Split into a pure decision function (lock_decision -- unit-testable with an
injected pid_alive callable, no filesystem/subprocess touched) and the real
file/process I/O around it (read_lock/acquire_lock/release_lock,
default_pid_alive). Never raises: any I/O failure is treated the same as
"lock unreadable" (stale) or "process check failed" (dead) -- this guard
must never be the reason a scheduled run deadlocks.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Tuple

LOCK_STALE_MIN = 40.0   # a lock file older than this is treated as abandoned regardless of pid


def lock_decision(exists: bool, pid: Optional[int], age_min: float,
                   pid_alive: Callable[[int], bool]) -> str:
    """Pure: what to do with an existing lock file.
      "acquire" -- no lock exists, take it.
      "locked"  -- another instance is genuinely still running (pid alive AND
                   age < LOCK_STALE_MIN) -- refuse, caller must exit without
                   doing anything.
      "stale"   -- pid is dead, OR the lock is older than LOCK_STALE_MIN
                   regardless of pid -- remove it and take it.
    """
    if not exists:
        return "acquire"
    if pid is not None and age_min < LOCK_STALE_MIN and pid_alive(pid):
        return "locked"
    return "stale"


def default_pid_alive(pid: int) -> bool:
    """Windows liveness check via tasklist. Any failure (tasklist missing,
    timeout, unexpected output) is treated as "dead" -- fails toward taking
    the lock rather than deadlocking a scheduled run forever."""
    try:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True,
                              text=True, timeout=10).stdout
        return str(pid) in out
    except Exception:
        return False


def read_lock(path: Path) -> Tuple[Optional[int], Optional[float]]:
    """(pid, age_min) from an existing lock file's JSON body
    ({"pid": N, "started_at": iso}); (None, None) if the file is missing or
    unparseable (lock_decision treats a None pid as not-alive -> stale)."""
    if not path.exists():
        return None, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        pid = int(data["pid"])
        started = datetime.fromisoformat(data["started_at"])
        now = datetime.now(started.tzinfo) if started.tzinfo else datetime.now()
        age_min = (now - started).total_seconds() / 60.0
        return pid, age_min
    except Exception:
        return None, None


def acquire_lock(path: Path, pid_alive: Callable[[int], bool] = default_pid_alive) -> bool:
    """True if the lock is now held by THIS process (either it was free, or a
    stale one was removed and replaced). False if another live instance
    holds it -- caller must exit immediately without doing anything else.
    Never raises."""
    exists = path.exists()
    pid, age_min = read_lock(path)
    decision = lock_decision(exists, pid, age_min if age_min is not None else 1e9, pid_alive)
    if decision == "locked":
        print(f"LOCKED: another instance (pid {pid}, age {age_min:.0f} min) is running -- exiting")
        return False
    if decision == "stale" and exists:
        print("stale lock removed")
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps({"pid": os.getpid(), "started_at": datetime.now().isoformat()}))
        return True
    except FileExistsError:
        # race: another instance created the lock between our stale-check and our create
        print("LOCKED: lock created by another instance between check and create -- exiting")
        return False
    except Exception as e:
        # never let the lock mechanism itself block a real run
        print(f"lock: failed to create ({e}) -- proceeding without a lock")
        return True


def release_lock(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except Exception:
        pass


