"""T75 tap/key batching: one adb shell per blind sequence."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
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


class DailiesLeftoverPopup(unittest.TestCase):
    """T83: run_dailies' leftover dim popup -> DISMISS + BACK batched, only
    after the is_dimmed gate shot; the menu check stays a separate read."""

    def run_dailies(self, pre: str):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from fake_vision import FakeDevice
        from PIL import Image
        import afk_dailies as dl
        dim = Image.new('RGB', (1920, 1080), (10, 10, 10))      # L < 25 at (200,270)
        # chest: nothing claimable (PANEL x3) -> pre-quests shot -> menu -> no quest panel (stop)
        dev = FakeDevice(self, ['PANEL', 'PANEL', 'PANEL', dim if pre == 'DIM' else pre,
                                'MENU', 'UNKNOWN'])
        return dev, dl

    def test_tap_order_unchanged(self):
        dev, dl = self.run_dailies('DIM')
        self.assertEqual(dl.run_dailies(0), 1)
        self.assertEqual(dev.taps, [v.CHEST, v.CHEST, dl.DISMISS, v.BACK, dl.QUESTS_ICON])
        self.assertEqual(dev.shots[3:5], ['dl_pre_quests', 'dl_menu_0'])

    def test_not_dimmed_single_back(self):
        dev, dl = self.run_dailies('PANEL')
        self.assertEqual(dl.run_dailies(0), 1)
        self.assertEqual(dev.taps, [v.CHEST, v.CHEST, v.BACK, dl.QUESTS_ICON])

    def test_one_adb_shell(self):
        from fake_vision import real_seq
        calls = real_seq(self, rc=0)
        dev, dl = self.run_dailies('DIM')
        self.assertEqual(dl.run_dailies(0), 1)
        self.assertEqual(calls, [(('shell', 'input tap 480 300; sleep 2; input tap 474 1010; sleep 1.2'),
                                  {'timeout': 18})])
        self.assertEqual(dev.taps, [v.CHEST, v.CHEST, dl.QUESTS_ICON])

    def test_adb_failure_raises_before_menu_read(self):
        from fake_vision import real_seq
        real_seq(self, rc=1)
        dev, dl = self.run_dailies('DIM')
        with self.assertRaises(RuntimeError):
            dl.run_dailies(0)
        self.assertEqual(dev.shots[-1], 'dl_pre_quests')


class GiftSecondDimLayer(unittest.TestCase):
    """T83: gift claim -> second dimmed layer (gate shot dg_dismiss_*) -> dismiss
    + closing BACK batched; the dg_back read stays after the batch."""

    def run_gift(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from fake_vision import FakeDevice, frame
        from test_review_fixes import gift
        green_row = frame('EVENTS')
        green_row.paste((60, 180, 60), (700, 240, 740, 280))     # badge at (720,260)
        dim = frame('EVENTS')
        dim.paste((10, 10, 10), (180, 250, 220, 290))           # is_dimmed probe (200,270)
        dev = FakeDevice(self, ['WORLD', 'GIFT_ENTRY', 'EVENTS', green_row,
                                'POPUP',                          # after-tap: claimed
                                dim,                              # dg_dismiss: 2nd layer
                                'WORLD'])                         # dg_back
        with mock.patch.object(sys, 'argv', ['afk-daily-gift.py']):
            rc = gift.main()
        return dev, rc, gift

    def test_tap_order_unchanged(self):
        dev, rc, gift = self.run_gift()
        self.assertEqual(rc, 0)
        self.assertEqual(dev.taps, [gift.LOGIN_REWARDS, (gift.ROW_X, 260), (700, 500),
                                    (700, 500), v.BACK])          # exactly one closing BACK
        self.assertEqual(dev.shots[-2:], ['dg_dismiss_260', 'dg_back'])

    def test_one_adb_shell(self):
        from fake_vision import real_seq
        calls = real_seq(self, rc=0)
        dev, rc, gift = self.run_gift()
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [(('shell', 'input tap 700 500; sleep 2; input tap 474 1010; sleep 1.5'),
                                  {'timeout': 18})])
        self.assertEqual(dev.taps, [gift.LOGIN_REWARDS, (gift.ROW_X, 260), (700, 500)])

    def test_adb_failure_raises_before_close_read(self):
        from fake_vision import real_seq
        real_seq(self, rc=1)
        with self.assertRaises(RuntimeError):
            self.run_gift()


if __name__ == '__main__':
    unittest.main()
