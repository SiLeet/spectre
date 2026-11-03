"""Shared tap lock for direct script runs (Race-Fund-Fix, 2026-11-03).

``.spectre/afk-bot.lock`` was held only by the watch.sh / afk-night.sh
wrappers, so scripts started directly (queue driver, manual runs) tapped
concurrently with scheduled runs — live collision 2026-11-03 15:31
(dream realm vs. a livecheck session on the same hero-detail screen).
Every tap-carrying entrypoint now acquires the same lock at start.

Wrappers keep owning the lock: they export AFK_BOT_LOCK_HELD=1 so the
child scripts skip acquisition (the wrapper already serialized the run).

Semantics match the wrappers (R7): a lock younger than AFK_LOCK_STALE
(default 3600 s) means "another run in progress" -> acquire() False; an
older lock is taken over. release() removes the file only when it still
carries OUR pid, so a wrapper lock or a taken-over foreign lock is never
deleted.
"""
from __future__ import annotations

import atexit
import os
import time
from pathlib import Path
from typing import Mapping

REPO = Path(__file__).resolve().parent.parent
LOCK = REPO / '.spectre' / 'afk-bot.lock'
HELD_ENV = 'AFK_BOT_LOCK_HELD'

# originals saved by scripts/tests/fake_vision.py when it stubs the gate for
# flow tests (see there); None outside the test harness.
_real_acquire = None
_real_release = None
_real_describe = None


def _default_lock() -> Path:
    """Resolve the default lock AT CALL TIME so tests can redirect it
    (module attribute patch) without touching .spectre/afk-bot.lock."""
    return LOCK


def acquire(lock: Path | None = None, env: Mapping[str, str] | None = None,
            stale: int | None = None, now: float | None = None) -> bool:
    """Take the tap lock unless a wrapper already holds it for us.

    Returns True when the caller may tap (lock acquired or inherited from
    the wrapper), False when another live run holds it. A lock older than
    the stale threshold is taken over, exactly like the wrappers do.
    """
    if lock is None:
        lock = _default_lock()
    if env is None:
        env = os.environ
    if stale is None:
        stale = int(env.get('AFK_LOCK_STALE', '3600'))
    now = time.time() if now is None else now
    if env.get(HELD_ENV) == '1':
        return True
    try:
        age = now - lock.stat().st_mtime
    except FileNotFoundError:
        age = None
    if age is not None and age < stale:
        return False
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(str(os.getpid()), encoding='ascii')
    return True


def release(lock: Path | None = None, env: Mapping[str, str] | None = None) -> None:
    """Drop the lock only if WE created it (never delete a wrapper's lock)."""
    if lock is None:
        lock = _default_lock()
    if env is None:
        env = os.environ
    if env.get(HELD_ENV) == '1':
        return
    try:
        if lock.read_text(encoding='ascii', errors='replace').strip() == str(os.getpid()):
            lock.unlink()
    except FileNotFoundError:
        pass


def release_at_exit(lock: Path | None = None) -> None:
    """Release our lock when the process exits (safe: PID-guarded)."""
    atexit.register(release, lock)


def describe(lock: Path | None = None) -> str:
    """Human-readable lock state for SKIP log lines."""
    if lock is None:
        lock = _default_lock()
    try:
        owner = lock.read_text(encoding='ascii', errors='replace').strip()
    except FileNotFoundError:
        return 'no lock file'
    try:
        age = max(0, int(time.time() - lock.stat().st_mtime))
    except FileNotFoundError:
        return 'no lock file'
    return f'pid {owner or "?"}, age {age}s'
