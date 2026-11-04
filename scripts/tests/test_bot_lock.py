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
                     'afk_stage_push.py', 'afk_dailies.py',
                     'afk_hero_level.py', 'afk_duras.py'):
            self._assert_wired(name)

    def test_hero_level_gate_precedes_navigation(self):
        src = (SCRIPTS / 'afk_hero_level.py').read_text(encoding='utf-8')
        self.assertLess(src.index('_bot_lock.acquire'),
                        src.index('# navigate: town -> Resonating Hall'),
                        'hero_level: lock gate must run before the first tap')

    def test_wrappers_export_held_env(self):
        for name in ('afk-bot-watch.sh', 'afk-night.sh'):
            src = (SCRIPTS / name).read_text(encoding='utf-8')
            self.assertRegex(src, r'export AFK_BOT_LOCK_HELD=1',
                             f'{name}: wrapper does not mark the lock held')


class HeroLevelLockBehaviour(unittest.TestCase):
    """T71: the 5th entrypoint behaves like the other four - a fresh foreign
    lock stops afk_hero_level before any screenshot or tap (exit 7)."""

    def setUp(self):
        from fake_vision import FakeDevice  # also stubs the gate globally; re-armed per test
        import afk_hero_level
        self.hl, self.FakeDevice = afk_hero_level, FakeDevice
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.lock = Path(self._tmp.name) / 'afk-bot.lock'

    def run_main(self, env, frames):
        from unittest import mock
        dev = self.FakeDevice(self, frames)
        with mock.patch.multiple(self.hl._bot_lock,
                                 acquire=lambda: acquire(lock=self.lock, env=env),
                                 describe=lambda: describe(lock=self.lock)), \
             mock.patch.object(sys, 'argv', ['afk_hero_level.py', '--level']):
            return dev, self.hl.main()

    def foreign_lock(self, age=0):
        self.lock.write_text('999999')
        t = time.time() - age
        os.utime(self.lock, (t, t))

    def test_fresh_foreign_lock_exits_7_without_any_tap(self):
        self.foreign_lock()
        dev, rc = self.run_main({}, [])
        self.assertEqual(rc, 7)
        self.assertEqual((dev.taps, dev.shots), ([], []))
        self.assertIn('SKIP: tap lock held', dev.out.getvalue())
        self.assertIn('999999', dev.out.getvalue())

    def test_wrapper_held_env_proceeds_and_keeps_the_foreign_lock(self):
        self.foreign_lock()
        dev, rc = self.run_main({'AFK_BOT_LOCK_HELD': '1'}, ['UNKNOWN', 'UNKNOWN'])
        self.assertEqual(dev.taps[0], self.hl.HALL_BTN)          # past the gate
        self.assertEqual(self.lock.read_text().strip(), '999999')

    def test_stale_lock_is_taken_over(self):
        self.foreign_lock(age=7200)
        dev, rc = self.run_main({}, ['UNKNOWN', 'UNKNOWN'])
        self.assertEqual(dev.taps[0], self.hl.HALL_BTN)
        self.assertEqual(self.lock.read_text().strip(), str(os.getpid()))


if __name__ == '__main__':
    unittest.main()
