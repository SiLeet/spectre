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
# T101: real cost line of shots-17092/hl_daily_pre0_w2 (8.57M gold vs a 9,390 need)
COVERED = '8572K/9390'


def detail(level: int, costs: str = '5104K/2780') -> list[str]:
    return ['Affinity Not Pinned', f'Lvl. {level}', 'Level', costs]


def hand(name: str, level: int, costs: str | None = None, badge: int | None = None) -> dict:
    """T101 fake OCR of detail shot `name`: the full frame (badge = is_detail tell only),
    the big 'Level NNN' crop (`_lv` = the hand level) and the cost crop (`_cost`: two
    agreeing variant lines = one voted pair)."""
    ocr = {name: detail(level if badge is None else badge), f'{name}_lv': [str(level), 'Level']}
    if costs:
        ocr[f'{name}_cost'] = [costs, costs]
    return ocr


_REAL_TAP = v.tap        # captured at import, before any FakeDevice patch
SCAN = {**hand('hl_scan_710', 80), **hand('hl_scan_840', 78)}          # lowest: 840 @ 78


class DailyCharge(unittest.TestCase):
    # after hl_start (the WORLD frame run_level prepends): entry, scan 710, hall check,
    # scan 840, hall check, pre, post
    FRAMES = ['UNKNOWN'] * 7

    def run_level(self, ocr, frames=None, last_hand=None):
        ARTIFACTS.mkdir(exist_ok=True)
        last = ARTIFACTS / 'level-last-hand.txt'
        last.unlink(missing_ok=True)
        if last_hand is not None:
            last.write_text(str(last_hand), encoding='utf-8')
        # T101: enter_hall shoots 'hl_start' first; WORLD there -> exactly one HALL_BTN tap
        dev = FakeDevice(self, ['WORLD'] + (frames or self.FRAMES),
                         ocr={'hl_entry': HALL, 'hl_scan_hall_840': HALL, 'hl_daily_hall0': HALL,
                              'hl_daily_hall1': HALL, **ocr})
        for patch in (mock.patch.object(hl, 'key', lambda code, wait=1.5: dev.taps.append(('key', code))),
                      mock.patch.object(hl, 'HAND_XS', [710, 840]),
                      mock.patch.object(hl, 'LAST_HAND', last),
                      mock.patch.object(sys, 'argv', ['afk_hero_level.py', '--level'])):
            patch.start()
            self.addCleanup(patch.stop)
        return dev, hl.main(), last

    def test_exactly_one_charge_on_the_lowest_hand(self):
        dev, rc, last = self.run_level({**SCAN, **hand('hl_daily_pre0', 78, COVERED),
                                        **hand('hl_daily_post0', 79)})
        self.assertEqual(rc, 0)
        # T101: ONE tap (the T83 preview+confirm pair levelled twice: shots-17092 101 -> 103)
        self.assertEqual(dev.taps.count(hl.LEVEL_X1), 1)
        self.assertEqual(dev.taps, [hl.HALL_BTN, (710, hl.HANDS_Y), ('key', 4), (840, hl.HANDS_Y),
                                    ('key', 4), (840, hl.HANDS_Y), hl.LEVEL_X1, ('key', 4)])
        self.assertIn('charged: hand 840 level 78 -> 79', dev.out.getvalue())
        self.assertEqual(last.read_text(encoding='utf-8'), '840')

    def test_live_8138k_gold_is_covered_not_short(self):
        # T101 (was: '8138K/9360' must report 'resources short'): the old 'need inherits
        # the K' parse made that a false skip; trash/shots-13228/hl_scan_970 shows 8138K
        # gold vs a 9,390 need -> covered, so the charge goes out.
        dev, rc, _ = self.run_level({**SCAN, **hand('hl_daily_pre0', 78, '8138K/9360'),
                                     **hand('hl_daily_post0', 79)})
        self.assertEqual(rc, 0)
        self.assertNotIn('resources short', dev.out.getvalue())
        self.assertEqual(dev.taps.count(hl.LEVEL_X1), 1)

    def test_big_box_is_the_hand_level(self):
        # T101 (was: 'box cap 100 must not leak'): the big 'Level NNN' box IS the hand level
        # (shots-17092 hall row 110/110/101/100/100 = the boxes; trash/shots-69252 'Level 100'
        # was the true level). The 'Lvl. NN' badge (85 / 82 here) must not leak into reads.
        dev, rc, _ = self.run_level({**hand('hl_scan_710', 101, badge=85),
                                     **hand('hl_scan_840', 100, badge=82),
                                     **hand('hl_daily_pre0', 100, COVERED, badge=82),
                                     **hand('hl_daily_post0', 101, badge=82)})
        self.assertEqual(rc, 0)
        self.assertIn('charged: hand 840 level 100 -> 101', dev.out.getvalue())

    def test_blocked_hand_is_skipped_for_the_next(self):
        blocked = 'Hands of Resonance must be within 10 levels of each other.'
        pre0 = hand('hl_daily_pre0', 78, COVERED)
        pre0['hl_daily_pre0'] = pre0['hl_daily_pre0'] + [blocked]
        dev, rc, _ = self.run_level({**SCAN, **pre0, **hand('hl_daily_pre1', 80, COVERED),
                                     **hand('hl_daily_post1', 81)},
                                    frames=['UNKNOWN'] * 9)
        self.assertEqual(rc, 0)
        self.assertIn('blocked', dev.out.getvalue())
        self.assertIn('charged: hand 710 level 80 -> 81', dev.out.getvalue())

    def test_gate_resources_short_no_charge(self):
        dev, rc, _ = self.run_level({**SCAN, **hand('hl_daily_pre0', 78, '120K/2780K')},
                                    frames=['UNKNOWN'] * 6)
        self.assertEqual(rc, 4)
        self.assertIn('resources short', dev.out.getvalue())
        self.assertNotIn(hl.LEVEL_X1, dev.taps)

    def test_no_effect_is_soft_skip(self):
        dev, rc, _ = self.run_level({**SCAN, **hand('hl_daily_pre0', 78, COVERED),
                                     **hand('hl_daily_post0', 78)}, frames=self.FRAMES + ['UNKNOWN'] * 2)
        self.assertEqual(rc, 4)                     # post cost line unread: undetermined
        self.assertIn('no effect', dev.out.getvalue())

    def test_purchase_dialog_cancelled(self):
        dev, rc, _ = self.run_level({**SCAN, **hand('hl_daily_pre0', 78, COVERED)},
                                    frames=['UNKNOWN'] * 6 + ['DIALOG'])
        self.assertEqual(rc, 4)
        self.assertEqual(dev.taps[-3:], [hl.LEVEL_X1, v.CONFIRM_CANCEL, ('key', 4)])

    def test_scan_fails_uses_last_known_hand(self):
        dev, rc, _ = self.run_level({**hand('hl_daily_pre0', 90, COVERED), **hand('hl_daily_post0', 91)},
                                    frames=self.FRAMES + ['UNKNOWN'] * 2,   # T72: 1 retry per hand
                                    last_hand=1100)
        self.assertEqual(rc, 0)
        self.assertIn('LIVE: hand scan read no level — using last known hand 1100', dev.out.getvalue())
        self.assertIn((1100, hl.HANDS_Y), dev.taps)

    def test_unreadable_detail_soft_skips_without_charge(self):
        # T80b: a detail that never shows costs the bounded poll per hand (was one 3 s read)
        dev, rc, _ = self.run_level(SCAN, frames=['UNKNOWN'] * (6 + 2 * hl.DETAIL_POLLS))
        self.assertEqual(rc, 4)
        self.assertNotIn(hl.LEVEL_X1, dev.taps)

    CHARGE_OCR = {**SCAN, **hand('hl_daily_pre0', 78, COVERED), **hand('hl_daily_post0', 79)}

    def test_charge_is_one_single_tap(self):
        # T101 (was T83 'panel + confirm as one adb shell'): that pair levelled twice per run
        # (shots-17092 101 -> 103, shots-48104 103 -> 105; gold 8572K -> 8553K = 9390 + 9450).
        # Now ONE plain tap, no batched sequence, read back only after it.
        calls = real_seq(self, rc=0)
        dev, rc, _ = self.run_level(self.CHARGE_OCR)
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [])                               # no tap_seq batch
        self.assertEqual(dev.taps.count(hl.LEVEL_X1), 1)
        self.assertEqual(dev.shots[dev.shots.index('hl_daily_pre0') + 1], 'hl_daily_post0')
        self.assertEqual(dev.taps[-1], ('key', 4))
        self.assertIn('charged: hand 840 level 78 -> 79', dev.out.getvalue())

    def test_charge_adb_failure_raises_like_tap(self):
        # the charge is a plain v.tap: adb transport failure (rc != 0) raises, no read-back
        calls = real_seq(self, rc=1)
        orig = FakeDevice._tap

        def tap(dev, xy, wait=1.0, mode=None):
            if tuple(xy) == hl.LEVEL_X1:
                return _REAL_TAP(xy, wait, mode)              # real _press on the fake adb
            return orig(dev, xy, wait, mode)
        p = mock.patch.object(FakeDevice, '_tap', tap)
        p.start()
        self.addCleanup(p.stop)
        with self.assertRaises(RuntimeError):
            self.run_level(self.CHARGE_OCR)
        self.assertEqual(calls, [(('shell', 'input', 'tap', '1100', '985'), {})])


class ResourceGate(unittest.TestCase):
    def test_real_detail_ocr(self):
        self.assertTrue(hl.resources_ok(DETAIL_COSTS))

    def test_short_and_unknown(self):
        self.assertFalse(hl.resources_ok(['1.2M/3M']))
        # T101 (was asserted short): each number keeps its OWN suffix - trash/shots-13228/
        # hl_scan_970 shows 8138K gold vs a 9,390 need, i.e. covered
        self.assertTrue(hl.resources_ok(['8138K/9360']))
        self.assertTrue(hl.resources_ok(['6396K/2840']))
        self.assertIsNone(hl.resources_ok(['3/4', '0/1', 'Level']))   # affinity/ascend counters


if __name__ == '__main__':
    unittest.main()
