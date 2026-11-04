"""T67 daily leveling: exactly one x1 charge on the lowest hand, gated + soft."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402
import afk_hero_level as hl  # noqa: E402
from fake_vision import FakeDevice, real_seq  # noqa: E402
from test_parsers import HALL  # noqa: E402

ARTIFACTS = Path(__file__).resolve().parent / '.artifacts'
# real WinRT OCR of a hero detail (.spectre/hd_pre.png, 2026-11-02)
DETAIL_COSTS = ['Epic,', 'Corpsemaker', 'Shemira', 'Affinity', 'Skin Not Pinned', 'Lvl. 74',
                'scend', '0/1', 'Level', '7970', 'O', '5104K/2780', 'eve Up',
                "2395K,'63K 02985/1100"]


def detail(level: int, costs: str = '5104K/2780') -> list[str]:
    return ['Affinity Not Pinned', f'Lvl. {level}', 'Level', costs]


class DailyCharge(unittest.TestCase):
    FRAMES = ['UNKNOWN'] * 7      # entry, scan 710, hall check, scan 840, hall check, pre, post

    def run_level(self, ocr, frames=None, last_hand=None):
        ARTIFACTS.mkdir(exist_ok=True)
        last = ARTIFACTS / 'level-last-hand.txt'
        last.unlink(missing_ok=True)
        if last_hand is not None:
            last.write_text(str(last_hand), encoding='utf-8')
        dev = FakeDevice(self, frames or self.FRAMES, ocr={'hl_entry': HALL,
                                                          'hl_scan_hall_840': HALL,
                                                          'hl_daily_hall0': HALL,
                                                          'hl_daily_hall1': HALL, **ocr})
        for patch in (mock.patch.object(hl, 'key', lambda code, wait=1.5: dev.taps.append(('key', code))),
                      mock.patch.object(hl, 'HAND_XS', [710, 840]),
                      mock.patch.object(hl, 'LAST_HAND', last),
                      mock.patch.object(sys, 'argv', ['afk_hero_level.py', '--level'])):
            patch.start()
            self.addCleanup(patch.stop)
        return dev, hl.main(), last

    def test_exactly_one_charge_on_the_lowest_hand(self):
        dev, rc, last = self.run_level({'hl_scan_710': detail(80), 'hl_scan_840': detail(78),
                                        'hl_daily_pre0': detail(78), 'hl_daily_post0': ['Lvl. 79']})
        self.assertEqual(rc, 0)
        self.assertEqual(dev.taps.count(hl.LEVEL_X1), 2)          # preview panel + confirm
        self.assertEqual(dev.taps, [hl.HALL_BTN, (710, hl.HANDS_Y), ('key', 4), (840, hl.HANDS_Y),
                                    ('key', 4), (840, hl.HANDS_Y), hl.LEVEL_X1, hl.LEVEL_X1, ('key', 4)])
        self.assertIn('charged: hand 840 level 78 -> 79', dev.out.getvalue())
        self.assertEqual(last.read_text(encoding='utf-8'), '840')

    def test_blocked_hand_is_skipped_for_the_next(self):
        blocked = 'Hands of Resonance must be within 10 levels of each other.'
        dev, rc, _ = self.run_level({'hl_scan_710': detail(80), 'hl_scan_840': detail(78),
                                     'hl_daily_pre0': detail(78) + [blocked],
                                     'hl_daily_pre1': detail(80), 'hl_daily_post1': ['Lvl. 81']},
                                    frames=['UNKNOWN'] * 9)
        self.assertEqual(rc, 0)
        self.assertIn('blocked', dev.out.getvalue())
        self.assertIn('charged: hand 710 level 80 -> 81', dev.out.getvalue())

    def test_gate_resources_short_no_charge(self):
        dev, rc, _ = self.run_level({'hl_scan_710': detail(80), 'hl_scan_840': detail(78),
                                     'hl_daily_pre0': detail(78, '120K/2780K')},
                                    frames=['UNKNOWN'] * 6)
        self.assertEqual(rc, 4)
        self.assertNotIn(hl.LEVEL_X1, dev.taps)

    def test_no_effect_is_soft_skip(self):
        dev, rc, _ = self.run_level({'hl_scan_710': detail(80), 'hl_scan_840': detail(78),
                                     'hl_daily_pre0': detail(78), 'hl_daily_post0': ['Lvl. 78']})
        self.assertEqual(rc, 4)
        self.assertIn('no effect', dev.out.getvalue())

    def test_purchase_dialog_cancelled(self):
        dev, rc, _ = self.run_level({'hl_scan_710': detail(80), 'hl_scan_840': detail(78),
                                     'hl_daily_pre0': detail(78)},
                                    frames=['UNKNOWN'] * 6 + ['DIALOG'])
        self.assertEqual(rc, 4)
        self.assertEqual(dev.taps[-3:], [hl.LEVEL_X1, v.CONFIRM_CANCEL, ('key', 4)])

    def test_scan_fails_uses_last_known_hand(self):
        dev, rc, _ = self.run_level({'hl_daily_pre0': detail(90), 'hl_daily_post0': ['Lvl. 91']},
                                    frames=self.FRAMES + ['UNKNOWN'] * 2,   # T72: 1 retry per hand
                                    last_hand=1100)
        self.assertEqual(rc, 0)
        self.assertIn('LIVE: hand scan read no level — using last known hand 1100', dev.out.getvalue())
        self.assertIn((1100, hl.HANDS_Y), dev.taps)

    def test_unreadable_detail_soft_skips_without_charge(self):
        # T80b: a detail that never shows costs the bounded poll per hand (was one 3 s read)
        dev, rc, _ = self.run_level({'hl_scan_710': detail(80), 'hl_scan_840': detail(78)},
                                    frames=['UNKNOWN'] * (6 + 2 * hl.DETAIL_POLLS))
        self.assertEqual(rc, 4)
        self.assertNotIn(hl.LEVEL_X1, dev.taps)

    CHARGE_OCR = {'hl_scan_710': detail(80), 'hl_scan_840': detail(78),
                  'hl_daily_pre0': detail(78), 'hl_daily_post0': ['Lvl. 79']}

    def test_charge_taps_go_out_as_one_adb_shell(self):
        # T83: panel + confirm tap = ONE adb shell, waits unchanged, read only after it
        calls = real_seq(self, rc=0)
        dev, rc, _ = self.run_level(self.CHARGE_OCR)
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [(('shell', 'input tap 1100 985; sleep 2.5; input tap 1100 985; sleep 3'),
                                  {'timeout': 20})])
        self.assertNotIn(hl.LEVEL_X1, dev.taps)                   # not as two single taps
        self.assertEqual(dev.taps[-1], ('key', 4))
        self.assertIn('charged: hand 840 level 78 -> 79', dev.out.getvalue())

    def test_charge_adb_failure_raises_like_tap(self):
        # tolerate=False: adb transport failure (shell rc != 0) -> RuntimeError, no read-back.
        # Not the full v.tap contract: the line ends in 'sleep', so a failing
        # 'input tap' inside the batch is not seen (';'-joined steps).
        calls = real_seq(self, rc=1)
        with self.assertRaises(RuntimeError):
            self.run_level(self.CHARGE_OCR)
        self.assertEqual(len(calls), 1)


class ResourceGate(unittest.TestCase):
    def test_real_detail_ocr(self):
        self.assertTrue(hl.resources_ok(DETAIL_COSTS))

    def test_short_and_unknown(self):
        self.assertFalse(hl.resources_ok(['1.2M/3M']))
        self.assertIsNone(hl.resources_ok(['3/4', '0/1', 'Level']))   # affinity/ascend counters


if __name__ == '__main__':
    unittest.main()
