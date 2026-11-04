"""T103 homestead phase 2: Radiant Spire upgrade - detectors on Hermes' live frames + FakeVision flows."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402
import afk_homestead_upgrade as hu  # noqa: E402
from fake_vision import FakeDevice  # noqa: E402
from test_homestead import HERMES, hermes  # noqa: E402

# real WinRT OCR line boxes (ocr.ps1 -Boxes), recorded 2026-11-04 on the frames named
WORLD_BOXES = [(851, 173, 97, 17, 'Radiant Spire'), (25, 781, 37, 13, 'Build'),   # hm_requests
               (922, 731, 75, 19, 'Level Up'), (875, 1057, 84, 13, 'Battle Modes')]
DIALOG_BOXES = [(844, 364, 199, 27, '? Radiant Spire i'),                          # hm_up3
                (477, 436, 302, 26, 'Upgrade Requirement (5/7)'),
                (482, 601, 99, 12, 'Level 5 Kitchen'), (612, 601, 72, 13, '3704/28K'),
                (726, 601, 79, 13, '653K/6800'), (845, 601, 73, 13, '1836/1800'),
                (949, 601, 95, 17, 'Level 5 Forge'), (1078, 601, 72, 13, '37K/5800'),
                (1179, 602, 99, 15, 'AFK stage: 80'), (477, 715, 202, 27, 'Upgrade Rewards'),
                (684, 984, 175, 29, 'Complete Now'), (770, 1023, 27, 11, '1800'),
                (1201, 985, 102, 29, 'Level Up'), (1451, 91, 22, 12, '0/2')]
DISC = (956, 686)
NO_BACK_KEY = ('key', 4)


def dialog(met='5/7', queue='0/2'):
    return [(*b[:4], b[4].replace('5/7', met)) if 'Requirement' in b[4]
            else (*b[:4], queue) if b[4] == '0/2' else b for b in DIALOG_BOXES]


class Detectors(unittest.TestCase):
    def test_radial_on_the_selected_spire(self):
        for name in ('hm_requests.png', 'hm_req2.png'):
            with self.subTest(name):
                self.assertEqual(hu.find_radial(hermes(name), WORLD_BOXES), DISC)

    def test_radial_where_the_ocr_box_is_off(self):
        # live T102 run: WinRT box centre (932,738), drawn text ~(958,740)
        path = Path(__file__).resolve().parents[3] / 'spectre' / '.spectre' / 'shots-67544' / 'hs_0_world.png'
        if not path.exists():
            self.skipTest(f'frame missing: {path}')
        from make_frame_manifest import load_rgb
        boxes = [(901, 163, 95, 25, 'Radiant Spire'), (895, 725, 75, 27, 'Level Up')]
        self.assertEqual(hu.find_radial(load_rgb(path), boxes), (956, 685))

    def test_radial_needs_label_text_and_disc(self):
        img = hermes('hm_requests.png')
        self.assertIsNone(hu.find_radial(img, [b for b in WORLD_BOXES if 'Spire' not in b[4]]))
        self.assertIsNone(hu.find_radial(img, [b for b in WORLD_BOXES if 'Level' not in b[4]]))
        # same OCR, but no disc on the pixels (hero at the door, nothing selected)
        self.assertIsNone(hu.find_radial(hermes('hm_confirmed2.png'), WORLD_BOXES))
        # the dialog's own 'Level Up' is outside the radial window
        self.assertIsNone(hu.find_radial(hermes('hm_up3.png'), DIALOG_BOXES))

    def test_dialog(self):
        img = hermes('hm_up3.png')
        self.assertEqual(hu.parse_requirement(DIALOG_BOXES), (5, 7))
        self.assertEqual(hu.missing_cards(img, DIALOG_BOXES), ['Level 5 Kitchen', '3704/28K'])
        self.assertEqual(hu.parse_queue(DIALOG_BOXES), (0, 2))
        self.assertTrue(hu.back_plate(img))
        self.assertEqual(v.classify(img), 'UNKNOWN')
        self.assertIsNone(hu.parse_requirement(WORLD_BOXES))
        self.assertIsNone(hu.parse_requirement([b for b in DIALOG_BOXES if 'Spire' not in b[4]]))
        for name in ('hm_requests.png', 'hm_confirmed2.png', 'hm_build_menu.png'):
            self.assertFalse(hu.back_plate(hermes(name)), name)

    def test_complete_now_is_never_tapped(self):
        with mock.patch.object(v, 'tap') as tap:
            for xy in ((770, 995), (538, 967), (1005, 1047)):
                with self.assertRaises(RuntimeError):
                    hu._tap(xy, 0)
            hu._tap(hu.LEVEL_UP_BTN, 0)
        tap.assert_called_once_with(hu.LEVEL_UP_BTN, 0)

    @unittest.skipUnless(sys.platform == 'win32', 'WinRT OCR')
    def test_real_ocr_boxes(self):
        png = HERMES / 'hm_up3.png'
        if not png.exists():
            self.skipTest(f'frame missing: {png}')
        boxes = v.parse_boxes(v.ocr_png(png, timeout=40, boxes=True))
        if not boxes:
            self.skipTest('OCR unavailable')
        self.assertEqual(hu.parse_requirement(boxes), (5, 7))
        self.assertLessEqual(max(abs(a - b) for a, b in zip(hu._centre(hu._line(boxes, 'level up')),
                                                              hu.LEVEL_UP_BTN)), hu.BTN_NEAR)


class OcrBoxes(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(v.parse_boxes(['922 731 75 19 Level Up', 'Level Up', '1 2 3 Spire', '-3 4 5 6 a b']),
                         [(922, 731, 75, 19, 'Level Up'), (-3, 4, 5, 6, 'a b')])

    def test_switch_only_with_boxes(self):
        done = subprocess.CompletedProcess([], 0, '1 2 3 4 x\n', '')
        with mock.patch.object(v.subprocess, 'run', return_value=done) as run:
            v.ocr_png(Path('a.png'))
            self.assertNotIn('-Boxes', run.call_args[0][0])
            self.assertEqual(v.ocr_png(Path('a.png'), boxes=True), ['1 2 3 4 x'])
            self.assertEqual(run.call_args[0][0][-1], '-Boxes')


class Flow(unittest.TestCase):
    def run_hu(self, frames, boxes, *argv):
        dev = FakeDevice(self, [hermes(f) if f.endswith('.png') else f for f in frames], boxes=boxes)
        rc = hu.main(list(argv))
        self.assertNotIn(NO_BACK_KEY, dev.taps)       # keyevent BACK opens the exit-game dialog here
        return dev, rc

    def test_requirements_missing_closes_via_back_plate(self):
        dev, rc = self.run_hu(['hm_requests.png', 'hm_up3.png', 'hm_up3.png', 'hm_confirmed2.png'],
                              {'hu_world': WORLD_BOXES, 'hu_read': DIALOG_BOXES})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [DISC, hu.BACK_PLATE])
        self.assertIn("missing: ['Level 5 Kitchen', '3704/28K']", dev.out.getvalue())

    def test_all_met_starts_the_upgrade(self):
        dev, rc = self.run_hu(['hm_requests.png', 'hm_up3.png', 'hm_up3.png', 'hm_confirmed2.png'],
                              {'hu_world': WORLD_BOXES, 'hu_read': dialog('7/7')})
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, [DISC, hu.LEVEL_UP_BTN])

    def test_dry_run_reads_and_closes(self):
        dev, rc = self.run_hu(['hm_requests.png', 'hm_up3.png', 'hm_up3.png', 'hm_confirmed2.png'],
                              {'hu_world': WORLD_BOXES, 'hu_read': dialog('7/7')}, '--dry-run')
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, [DISC, hu.BACK_PLATE])

    def test_queue_full_is_nothing_to_do(self):
        dev, rc = self.run_hu(['hm_requests.png', 'hm_up3.png', 'hm_up3.png', 'hm_confirmed2.png'],
                              {'hu_world': WORLD_BOXES, 'hu_read': dialog('7/7', '2/2')})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [DISC, hu.BACK_PLATE])

    def test_diamond_dialog_after_level_up_is_cancelled(self):
        dev, rc = self.run_hu(['hm_requests.png', 'hm_up3.png', 'hm_up3.png', 'DIALOG', 'hm_up3.png',
                               'hm_confirmed2.png'],
                              {'hu_world': WORLD_BOXES, 'hu_read': dialog('7/7')})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [DISC, hu.LEVEL_UP_BTN, v.CONFIRM_CANCEL, hu.BACK_PLATE])

    def test_level_up_refused(self):
        dev, rc = self.run_hu(['hm_requests.png', 'hm_up3.png', 'hm_up3.png', 'hm_up3.png',
                               'hm_confirmed2.png'],
                              {'hu_world': WORLD_BOXES, 'hu_read': dialog('7/7'), 'hu_after': dialog('7/7')})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [DISC, hu.LEVEL_UP_BTN, hu.BACK_PLATE])

    def test_unknown_screen_after_level_up_stops_without_taps(self):
        dev, rc = self.run_hu(['hm_requests.png', 'hm_up3.png', 'hm_up3.png', 'UNKNOWN'],
                              {'hu_world': WORLD_BOXES, 'hu_read': dialog('7/7')})
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual(dev.taps, [DISC, hu.LEVEL_UP_BTN])

    def test_spire_not_selected_is_nothing_to_do(self):
        dev, rc = self.run_hu(['hm_confirmed2.png'], {'hu_world': WORLD_BOXES[1:]})
        self.assertEqual(rc, 4)
        self.assertEqual(dev.taps, [])
        self.assertIn('LIVE-open', dev.out.getvalue())

    def test_not_on_the_world_stops_without_back_key(self):
        dev, rc = self.run_hu(['hm_up3.png'], {})
        self.assertEqual(rc, 1)
        self.assertEqual(dev.taps, [])

    def test_unrecognised_dialog_closes_and_stops(self):
        dev, rc = self.run_hu(['hm_requests.png', 'hm_up3.png', 'hm_up3.png', 'hm_confirmed2.png'],
                              {'hu_world': WORLD_BOXES, 'hu_read': []})
        self.assertEqual(rc, 1)
        self.assertEqual(dev.taps, [DISC, hu.BACK_PLATE])

    def test_tap_lock_held(self):
        import _bot_lock
        with mock.patch.object(_bot_lock, 'acquire', lambda *a, **k: False):
            dev, rc = self.run_hu([], {})
        self.assertEqual(rc, 7)


if __name__ == '__main__':
    unittest.main()
