"""Race-Fund-Fix (2026-11-03): _bot_lock semantics + entrypoint wiring."""
from __future__ import annotations

import os
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bot_lock  # noqa: E402

# When the shared harness (fake_vision) has stubbed the gate for flow tests,
# test the REAL semantics through the saved originals.
acquire = _bot_lock._real_acquire or _bot_lock.acquire
release = _bot_lock._real_release or _bot_lock.release
describe = _bot_lock._real_describe or _bot_lock.describe

SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'


class BotLockSemantics(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.lock = Path(self._tmp.name) / 'afk-bot.lock'

    def test_acquire_free_lock_writes_own_pid(self):
        self.assertTrue(acquire(lock=self.lock, env={}))
        self.assertEqual(self.lock.read_text().strip(), str(os.getpid()))

    def test_acquire_fresh_foreign_lock_refuses(self):
        self.lock.write_text('999999')
        self.lock.touch()  # mtime = now -> fresh
        self.assertFalse(acquire(lock=self.lock, env={}))

    def test_acquire_stale_lock_takes_over(self):
        self.lock.write_text('999999')
        old = time.time() - 4000
        os.utime(self.lock, (old, old))
        self.assertTrue(acquire(lock=self.lock, env={}, stale=3600))
        self.assertEqual(self.lock.read_text().strip(), str(os.getpid()))

    def test_acquire_respects_custom_stale_threshold(self):
        self.lock.write_text('999999')
        self.lock.touch()
        # lock is ~0s old; a stale threshold of 0 makes even a fresh lock
        # takeover-eligible, 3600 refuses it
        self.assertTrue(acquire(lock=self.lock, env={}, stale=0))
        self.assertEqual(self.lock.read_text().strip(), str(os.getpid()))
        self.lock.write_text('888888')
        self.lock.touch()
        self.assertFalse(acquire(lock=self.lock, env={}, stale=3600))

    def test_wrapper_env_bypasses_lock(self):
        self.lock.write_text('999999')
        self.lock.touch()
        self.assertTrue(acquire(lock=self.lock,
                                          env={'AFK_BOT_LOCK_HELD': '1'}))
        # release under wrapper env must NOT delete the foreign lock
        release(lock=self.lock, env={'AFK_BOT_LOCK_HELD': '1'})
        self.assertTrue(self.lock.exists())

    def test_release_removes_only_own_lock(self):
        acquire(lock=self.lock, env={})
        release(lock=self.lock, env={})
        self.assertFalse(self.lock.exists())
        self.lock.write_text('777')
        release(lock=self.lock, env={})
        self.assertTrue(self.lock.exists())

    def test_describe_reports_owner_and_age(self):
        self.assertEqual(describe(lock=self.lock), 'no lock file')
        self.lock.write_text('4242')
        text = describe(lock=self.lock)
        self.assertIn('pid 4242', text)
        self.assertIn('age 0s', text)


class BotLockWiring(unittest.TestCase):
    """Every tap-carrying entrypoint must gate on the lock; wrappers must
    export AFK_BOT_LOCK_HELD=1 for their children."""

    def _assert_wired(self, filename):
        src = (SCRIPTS / filename).read_text(encoding='utf-8')
        self.assertIn('_bot_lock.acquire', src, f'{filename}: no lock gate')
        self.assertIn('_bot_lock.release_at_exit', src,
                      f'{filename}: lock never released')

    def test_direct_scripts_wired(self):
        for name in ('afk_dream_realm.py', 'afk_arena.py',
                     'afk_stage_push.py', 'afk_dailies.py'):
            self._assert_wired(name)
        # the parallel-writer-owned file is intentionally NOT wired here
        # (uncommitted at fix time) — wiring it is a follow-up.
        self.assertNotIn('_bot_lock.acquire',
                         (SCRIPTS / 'afk_hero_level.py').read_text(encoding='utf-8'))

    def test_wrappers_export_held_env(self):
        for name in ('afk-bot-watch.sh', 'afk-night.sh'):
            src = (SCRIPTS / name).read_text(encoding='utf-8')
            self.assertRegex(src, r'export AFK_BOT_LOCK_HELD=1',
                             f'{name}: wrapper does not mark the lock held')


if __name__ == '__main__':
    unittest.main()
