"""T75 tap/key batching: one adb shell per blind sequence."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import afk_claim_vision as v  # noqa: E402


def done(rc: int) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], rc, b'', b'device offline')


class TapSeq(unittest.TestCase):
    def test_dry_command_string(self):
        self.assertEqual(v.tap_seq([(474, 1010, 1.2), (474, 1010, 1.5)], dry=True),
                         'input tap 474 1010; sleep 1.2; input tap 474 1010; sleep 1.5')
        self.assertEqual(v.tap_seq([(300, 250, 0), (60, 1036, 3)], dry=True),
                         'input tap 300 250; input tap 60 1036; sleep 3')
        self.assertEqual(v.key_seq([(4, 1.5), (4, 0)], dry=True),
                         'input keyevent 4; sleep 1.5; input keyevent 4')

    def test_one_adb_round_trip_bounded(self):
        with mock.patch.object(v, 'adb', return_value=done(0)) as adb:
            self.assertTrue(v.tap_seq([(300, 250, 0.8), (60, 1036, 3.0)]))
        adb.assert_called_once_with('shell', 'input tap 300 250; sleep 0.8; input tap 60 1036; sleep 3',
                                    timeout=18)

    def test_failure_tolerated_or_raised(self):
        with mock.patch.object(v, 'adb', return_value=done(1)):
            self.assertFalse(v.tap_seq([(1, 2, 0)]))
            with self.assertRaises(RuntimeError):
                v.tap_seq([(1, 2, 0)], tolerate=False)

    def test_converted_call_site_uses_one_batch(self):
        # claim_round world branch: GROUND + AFK chip go out as ONE adb call
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from fake_vision import frame
        calls = []
        with mock.patch.object(v, 'adb', side_effect=lambda *a, **k: calls.append(a) or done(0)), \
             mock.patch.object(v, 'shot', side_effect=[frame('WORLD'), frame('UNKNOWN')]), \
             mock.patch('time.sleep'), mock.patch.object(sys, 'stdout'):
            self.assertEqual(v.claim_round('r1'), 1)          # stops at UNKNOWN after the batch
        self.assertEqual(calls, [('shell', 'input tap 300 250; sleep 0.8; input tap 60 1036; sleep 3')])


if __name__ == '__main__':
    unittest.main()
