"""T101: direct hero-level runs - gated hall entry, big-box hand level, single charge,
own-suffix cost line with a no-effect verdict.

Real-frame cases copy local .spectre/ frames (read-only) into a temp dir pointed at by
v.TMP and skip when the frames are gone (or WinRT OCR returns nothing).
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402
import afk_hero_level as hl  # noqa: E402
import test_daily_leveling as tdl  # noqa: E402  (module import: no re-collected tests)
from fake_vision import FakeDevice  # noqa: E402
from make_frame_manifest import REPO, load_rgb  # noqa: E402
from test_parsers import HALL  # noqa: E402

hand, COVERED, SCAN = tdl.hand, tdl.COVERED, tdl.SCAN
K = ('key', 4)
SPIRE = 'shots-62772/hl_entry.png'     # homestead 'Radiant Spire Lvl 5 > 6' panel (UNKNOWN)


def spectre(relpath: str) -> Path:
    path = REPO / '.spectre' / relpath
    if not path.exists():
        raise unittest.SkipTest(f'frame missing: .spectre/{relpath}')
    return path


class GatedDevice(FakeDevice):
    """A HALL_BTN tap (any tap mode) on a non-WORLD frame fails the test: on the
    Radiant Spire panel that point is the 'Complete Now' (diamonds) button."""

    def _tap(self, xy, wait=1.0, mode=None):
        if tuple(xy) == hl.HALL_BTN and (self.last is None or v.classify(self.last) != 'WORLD'):
            self.test.fail(f'hall tap on a non-WORLD frame (shots: {self.shots})')
        return super()._tap(xy, wait, mode)

    def _tap_hold(self, xy, ms=120, wait=1.0):
        self._tap(xy, wait, 'hold')


class EnterHall(unittest.TestCase):
    def enter(self, frames, ocr=None):
        dev = GatedDevice(self, frames, ocr=ocr)
        return dev, hl.enter_hall()

    def test_spire_panel_backs_to_world_before_the_hall_tap(self):
        # hl_start UNKNOWN -> reach_world: rw_0 UNKNOWN (BACK), rw_1 WORLD -> tap -> hall
        dev, lines = self.enter(['UNKNOWN', 'UNKNOWN', 'WORLD', 'UNKNOWN'], {'hl_entry': HALL})
        self.assertEqual(lines, HALL)
        self.assertEqual(dev.taps, [K, hl.HALL_BTN])
        self.assertEqual(dev.shots, ['hl_start', 'rw_0', 'rw_1', 'hl_entry'])

    def test_world_never_reached_no_hall_tap(self):
        dev, lines = self.enter(['UNKNOWN'] * 8)          # hl_start + rw_0..5 + rw_final
        self.assertIsNone(lines)
        self.assertNotIn(hl.HALL_BTN, dev.taps)
        self.assertEqual(dev.taps, [K] * 6)

    def test_real_spire_frame(self):
        img = load_rgb(spectre(SPIRE))
        self.assertEqual(v.classify(img), 'UNKNOWN')
        dev, lines = self.enter([img, 'UNKNOWN', 'WORLD', 'UNKNOWN'], {'hl_entry': HALL})
        self.assertEqual(lines, HALL)
        self.assertEqual(dev.taps, [K, hl.HALL_BTN])

    def test_hall_already_open_zero_taps(self):
        dev, lines = self.enter(['UNKNOWN'], {'hl_start': HALL})
        self.assertEqual((lines, dev.taps, dev.shots), (HALL, [], ['hl_start']))

    def test_dead_hall_tap_goes_through_the_tap_chain_bounded(self):
        with mock.patch.object(v, 'tap_retry', wraps=v.tap_retry) as retry, \
                mock.patch.object(v, 'tap_result', wraps=v.tap_result) as result:
            dev, lines = self.enter(['WORLD'] * (1 + hl.HALL_TRIES))
        self.assertIsNone(lines)
        self.assertEqual(dev.taps, [hl.HALL_BTN, ('touchscreen', *hl.HALL_BTN), ('hold', *hl.HALL_BTN)])
        self.assertEqual(retry.call_count, hl.HALL_TRIES - 1)
        self.assertEqual(result.call_args_list, [mock.call('touchscreen', False), mock.call(None, False)])
        self.assertEqual(len(dev.shots), 1 + hl.HALL_TRIES)

    def test_retry_that_opens_the_hall_sticks(self):
        with mock.patch.object(v, 'tap_result', wraps=v.tap_result) as result:
            dev, lines = self.enter(['WORLD', 'WORLD', 'UNKNOWN'], {'hl_entry1': HALL})
        self.assertEqual(lines, HALL)
        result.assert_called_once_with('touchscreen', True)
        self.assertEqual(v.TAP_MODE, 'touchscreen')          # FakeDevice restores it after the test

    def test_confirm_dialog_after_the_tap_is_cancelled(self):
        dev, lines = self.enter(['WORLD', 'DIALOG', 'WORLD', 'UNKNOWN'], {'hl_entry1': HALL})
        self.assertEqual(lines, HALL)
        self.assertEqual(dev.taps[:2], [hl.HALL_BTN, v.CONFIRM_CANCEL])
        self.assertNotIn((1142, 710), dev.taps)                # never the confirm check
        self.assertEqual(dev.shots[:3], ['hl_start', 'hl_entry', 'hl_entry_c'])

    def test_retry_opening_a_dialog_counts_as_landed(self):
        # review: a retried tap that opened a confirm dialog must not mark its mode dead
        with mock.patch.object(v, 'tap_result', wraps=v.tap_result) as result:
            dev, lines = self.enter(['WORLD', 'WORLD', 'DIALOG', 'WORLD', 'UNKNOWN'], {'hl_entry2': HALL})
        self.assertEqual(lines, HALL)
        self.assertEqual(result.call_args_list[0], mock.call('touchscreen', True))
        self.assertNotIn((1142, 710), dev.taps)                # never the confirm check

    def test_hall_btn_is_the_helmet_centre(self):
        self.assertEqual(hl.HALL_BTN, (1005, 1025))    # icon ~x 980-1047 / y 1000-1050 (shots-66556/norm_3)


class Charge(unittest.TestCase):
    run_level, FRAMES = tdl.DailyCharge.run_level, tdl.DailyCharge.FRAMES

    def test_one_tap_read_back_plus_one(self):
        dev, rc, _ = self.run_level({**SCAN, **hand('hl_daily_pre0', 78, COVERED),
                                     **hand('hl_daily_post0', 79)})
        self.assertEqual((rc, dev.taps.count(hl.LEVEL_X1)), (0, 1))

    def no_effect(self, post_costs):
        posts = ('hl_daily_post0', 'hl_daily_post0_rr1', 'hl_daily_post0_rr2')
        dev, rc, _ = self.run_level({**SCAN, **hand('hl_daily_pre0', 78, COVERED),
                                     **{k: val for p in posts for k, val in hand(p, 78, post_costs).items()}},
                                    frames=self.FRAMES + ['UNKNOWN'] * 2)
        self.assertEqual(dev.taps.count(hl.LEVEL_X1), 1)
        self.assertEqual(dev.shots[-3:], list(posts))   # unchanged level: re-read before any verdict
        self.assertIn(str(v.TMP / 'hl_daily_post0_rr2.png'), dev.out.getvalue())   # evidence shot
        return rc, dev.out.getvalue()

    def test_lagging_post_frame_is_not_a_missed_tap(self):
        # review: first post frame still shows the old level + old costs -> rr1 shows the charge
        dev, rc, _ = self.run_level({**SCAN, **hand('hl_daily_pre0', 78, COVERED),
                                     **hand('hl_daily_post0', 78, COVERED), **hand('hl_daily_post0_rr1', 79)},
                                    frames=self.FRAMES + ['UNKNOWN'])
        self.assertEqual((rc, dev.taps.count(hl.LEVEL_X1)), (0, 1))

    def test_pre_cost_read_from_the_settled_reread(self):
        # review: first pre frame unreadable (clipped layout) -> the cost line comes from _rr1
        dev, rc, _ = self.run_level({**SCAN, 'hl_daily_pre0': tdl.detail(78),
                                     **hand('hl_daily_pre0_rr1', 78, '8K/9390')},
                                    frames=self.FRAMES + ['UNKNOWN'])
        self.assertEqual(rc, 4)
        self.assertIn('resources short', dev.out.getvalue())
        self.assertNotIn(hl.LEVEL_X1, dev.taps)

    def test_lower_read_back_is_never_retried(self):
        dev, rc, _ = self.run_level({**SCAN, **hand('hl_daily_pre0', 78, COVERED),
                                     **{k: val for p in ('hl_daily_post0', 'hl_daily_post0_rr1', 'hl_daily_post0_rr2')
                                        for k, val in hand(p, 77).items()}},
                                    frames=self.FRAMES + ['UNKNOWN'] * 2)
        self.assertEqual((rc, dev.taps.count(hl.LEVEL_X1)), (4, 1))

    def test_no_effect_short_after(self):
        rc, out = self.no_effect('8572K/9390K')
        self.assertEqual(rc, 4)
        self.assertIn('resources short', out)

    def test_no_effect_identical_covered_costs_is_a_missed_tap(self):
        rc, out = self.no_effect(COVERED)
        self.assertEqual(rc, 1)                    # no day marker: the next cycle retries
        self.assertIn('tap missed', out)

    def test_no_effect_undetermined(self):
        rc, out = self.no_effect('8553K/9450')     # spent, covered, level unchanged
        self.assertEqual(rc, 4)
        self.assertIn('undetermined', out)

    def test_short_before_no_tap(self):
        dev, rc, _ = self.run_level({**SCAN, **hand('hl_daily_pre0', 78, '8K/9390')},
                                    frames=['UNKNOWN'] * 6)
        self.assertEqual(rc, 4)
        self.assertNotIn(hl.LEVEL_X1, dev.taps)

    def test_verdict_table(self):
        pre = frozenset({(8572e3, 9390.0)})
        self.assertEqual(hl.no_effect_verdict(pre, frozenset({(8e3, 9390.0)}))[0], 4)
        self.assertEqual(hl.no_effect_verdict(pre, pre)[0], 1)
        self.assertEqual(hl.no_effect_verdict(pre, frozenset())[0], 4)
        self.assertEqual(hl.no_effect_verdict(frozenset(), frozenset())[0], 4)


class LowestHand(unittest.TestCase):
    def test_big_level_not_the_badge_picks_the_lowest(self):
        # shots-17092: hall row 110/110/101/100/100 = the big boxes; badges 82/92/85/82/85.
        # By badge 730 (82) would win; the real lowest hands are 1090/1210 (100).
        xs, levels, badges = hl.HAND_XS, (110, 110, 101, 100, 100), (82, 92, 85, 82, 85)
        ocr = {'hl_daily_hall0': HALL, **hand('hl_daily_pre0', 100, COVERED, badge=82),
               **hand('hl_daily_post0', 101, badge=82)}
        for x, lvl, badge in zip(xs, levels, badges):
            ocr.update(hand(f'hl_scan_{x}', lvl, badge=badge), **{f'hl_scan_hall_{x}': HALL})
        dev = FakeDevice(self, ['UNKNOWN'] * (2 * len(xs) - 1 + 3), ocr=ocr)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for p in (mock.patch.object(hl, 'key', lambda code, wait=1.5: dev.taps.append(K)),
                  mock.patch.object(hl, 'LAST_HAND', Path(tmp.name) / 'last.txt')):
            p.start()
            self.addCleanup(p.stop)
        self.assertEqual(hl.daily_charge(), 0)
        self.assertIn('lowest hands: [(1090, 100), (1210, 100), (970, 101)]', dev.out.getvalue())
        self.assertIn('charged: hand 1090 level 100 -> 101', dev.out.getvalue())


class CostParsing(unittest.TestCase):
    def test_own_suffix_pairs(self):
        self.assertEqual(hl._pairs('8572K/9390'), {(8572e3, 9390.0)})
        self.assertTrue(hl.costs_ok(hl._pairs('8572K/9390')))
        self.assertFalse(hl.costs_ok(hl._pairs('1.2M/3M')))
        self.assertEqual(hl._pairs('3/4'), set())
        self.assertIsNone(hl.costs_ok(set()))

    def cost(self, lines):
        FakeDevice(self, [], ocr={'x_cost': lines})
        return hl.cost_pairs('x')

    def test_vote_needs_two_lines(self):
        pairs = self.cost(['8572K/9390 5256K/91K', '8572K/9390', '5256K/91K', '1.2M/3M'])
        self.assertEqual(pairs, {(8572e3, 9390.0), (5256e3, 91e3)})      # 1.2M/3M seen once

    def test_ghost_pair_agreed_twice_is_kept(self):
        # real OCR of shots-17092/hl_scan_1090 agreed on both; both covered -> verdict unchanged
        pairs = self.cost(['51898/1178 1898/1178', '51898/1178', '1898/1178'])
        self.assertEqual(pairs, {(51898.0, 1178.0), (1898.0, 1178.0)})
        self.assertTrue(hl.costs_ok(pairs))


class RealFrameOcr(unittest.TestCase):
    """WinRT OCR on the T101 evidence frames (copied; v.TMP points at a temp dir)."""

    def setUp(self):
        if sys.platform != 'win32':
            self.skipTest('WinRT OCR is Windows-only')
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        p = mock.patch.object(v, 'TMP', self.tmp)
        p.start()
        self.addCleanup(p.stop)

    def copy(self, relpath: str) -> str:
        name = relpath.replace('/', '_')[:-4]
        shutil.copyfile(spectre(relpath), self.tmp / f'{name}.png')
        return name

    def level(self, relpath):
        name = self.copy(relpath)
        lvl = hl.slot_level(name)
        if lvl is None and not v.ocr_lines(f'{name}_lv'):
            self.skipTest('WinRT OCR returned nothing')
        return lvl

    def costs(self, relpath):
        name = self.copy(relpath)
        pairs = hl.cost_pairs(name)
        if not pairs and not v.ocr_lines(f'{name}_cost'):
            self.skipTest('WinRT OCR returned nothing')
        return pairs

    def test_slot_levels(self):
        for rel, want in (('shots-17092/hl_daily_pre0_w2.png', 101), ('shots-17092/hl_daily_post0.png', 103),
                          ('shots-17092/hl_scan_1090.png', 100), ('shots-48104/hl_scan_970.png', 103)):
            with self.subTest(rel=rel):
                self.assertEqual(self.level(rel), want)

    def test_cost_pairs(self):
        pre = self.costs('shots-17092/hl_daily_pre0_w2.png')
        self.assertIn((8572000.0, 9390.0), pre)
        self.assertIn((5256000.0, 91000.0), pre)
        self.assertIn((8553000.0, 9450.0), self.costs('shots-17092/hl_daily_post0.png'))


if __name__ == '__main__':
    unittest.main()
