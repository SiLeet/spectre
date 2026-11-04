"""T102 homestead phase 1: build Fields — detectors on Hermes' live frames + FakeVision flows."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from PIL import ImageDraw  # noqa: E402

import afk_claim_vision as v  # noqa: E402
import afk_homestead as hs  # noqa: E402
from fake_vision import FakeDevice, frame  # noqa: E402
from make_frame_manifest import load_rgb  # noqa: E402

HERMES = Path.home() / 'AppData' / 'Local' / 'hermes' / 'cache' / 'scratch'


def hermes(name: str):
    path = HERMES / name
    if not path.exists():
        raise unittest.SkipTest(f'frame missing: {path}')
    return load_rgb(path)


def paint(base: str, boxes) -> object:
    img = frame(base)
    d = ImageDraw.Draw(img)
    for (x, y), half, rgb in boxes:
        d.rectangle((x - half, y - half, x + half, y + half), fill=rgb)
    return img


BTN = (hs.BUILD_BTN, 6, (165, 165, 165))
# synthetic screens with the measured colours (constants' LIVE notes)
WORLD = lambda: paint('WORLD', [BTN])                                       # noqa: E731
MENU = lambda: paint('UNKNOWN', [(hs.EXIT_BTN, 12, (198, 187, 183)), (hs.BUILD_TAB, 12, (146, 183, 134)),  # noqa: E731
                                 (hs.LAYOUT_TAB, 12, (230, 223, 221)),
                                 (hs.PRODUCTION_TAB, 12, (145, 184, 138))])
RING = lambda: paint('UNKNOWN', [((1089, 562), 7, (60, 200, 60)), ((842, 557), 7, (220, 40, 40))])  # noqa: E731
MARK = lambda: paint('WORLD', [BTN, ((964, 560), 20, (254, 238, 93))])       # noqa: E731
TOAST = lambda: frame('UNKNOWN')                                            # noqa: E731
CHECK, CANCEL = (1089, 562), (842, 557)
RES = ['@ 653,402 3848', '460']


def counter(n: int, limit: int = 16) -> list[str]:
    return [f'{n}/{limit}', '5s', 'Field', '010', '0100']


class Detectors(unittest.TestCase):
    """Real frames from the 2026-11-04 20:40 live run (skip when missing)."""

    def test_build_menu(self):
        img = hermes('hm_build_menu.png')
        self.assertTrue(hs.is_build_menu(img))
        self.assertTrue(hs.production_active(img))
        self.assertIsNone(hs.find_ring(img))

    def test_ring_found_on_the_frame(self):
        for name in ('hm_field_tap.png', 'hm_field_build.png', 'hm_field_confirmed.png'):
            with self.subTest(name):
                img = hermes(name)
                (cx, cy), (xx, xy) = hs.find_ring(img)
                self.assertLessEqual(abs(cx - 1090) + abs(cy - 558), 8)   # check disc centre
                self.assertLessEqual(abs(xx - 842) + abs(xy - 558), 8)    # cancel disc centre
                self.assertGreater(cy, 527)     # (1090,520) missed live: above the disc
                self.assertFalse(hs.is_build_menu(img))

    def test_marker_and_world(self):
        img = hermes('hm_confirmed2.png')
        self.assertEqual(v.classify(img), 'WORLD')
        self.assertTrue(hs.build_btn(img))
        mx, my = hs.find_marker(img)
        self.assertLessEqual(abs(mx - 964) + abs(my - 580), 8)

    def test_negatives(self):
        for name in ('hm_requests.png', 'hm_req2.png', 'hm_spire_up.png', 'hm_up2.png', 'hm_up3.png'):
            with self.subTest(name):
                img = hermes(name)
                self.assertFalse(hs.is_build_menu(img))
                self.assertIsNone(hs.find_ring(img))
                self.assertIsNone(hs.find_marker(img))
        for name in ('hm_requests.png', 'hm_req2.png'):
            self.assertTrue(hs.build_btn(hermes(name)))

    def test_synthetic_frames_match_the_detectors(self):
        self.assertEqual(v.classify(WORLD()), 'WORLD')
        self.assertTrue(hs.build_btn(WORLD()))
        self.assertTrue(hs.is_build_menu(MENU()) and hs.production_active(MENU()))
        self.assertEqual(hs.find_ring(RING()), (CHECK, CANCEL))
        self.assertEqual(v.classify(MARK()), 'WORLD')
        self.assertEqual(hs.find_marker(MARK()), (964, 560))
        self.assertIsNone(hs.find_marker(WORLD()))


class Parsers(unittest.TestCase):
    def test_counter(self):
        self.assertEqual(hs.parse_counter(['"12/16', 'Field']), (12, 16))   # x2 OCR read
        self.assertEqual(hs.parse_counter(counter(16)), (16, 16))
        self.assertIsNone(hs.parse_counter(['12/16']))          # not proven to be the Field tile
        self.assertIsNone(hs.parse_counter(['12', 'Field']))    # x1 OCR read

    def test_resources(self):
        self.assertEqual(hs.parse_resources(RES), (653402, 3848))
        self.assertIsNone(hs.parse_resources(['3848', '460']))  # x2 OCR drops gold


class Flow(unittest.TestCase):
    def run_hs(self, frames, ocr, *argv, max_builds=1):
        p = mock.patch.object(hs, 'MAX_BUILDS', max_builds)
        p.start()
        self.addCleanup(p.stop)
        dev = FakeDevice(self, [f() if callable(f) else f for f in frames], ocr=ocr)
        return dev, hs.main(list(argv))

    def entry(self, k):
        """reach_world, ground-tap shot, menu after Build, read shot."""
        return [WORLD, WORLD, MENU, MENU]

    def test_one_field_built_and_verified(self):
        frames = (self.entry(0) + [RING, MARK, TOAST, WORLD] + self.entry(1)
                  + [MENU, WORLD])                                  # exit shot, reach_world
        ocr = {'hs_0_read_field': counter(12), 'hs_0_read_res': RES, 'hs_b0_1': ['Field Built'],
               'hs_1_read_field': counter(13), 'hs_1_read_res': RES}
        dev, rc = self.run_hs(frames, ocr)
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, [v.GROUND, hs.BUILD_BTN, hs.FIELD_TILE, CHECK, (964, 560),
                                    hs.TOAST_CLOSE, v.GROUND, hs.BUILD_BTN, hs.EXIT_BTN])
        self.assertIn('run cap reached', dev.out.getvalue())

    def test_real_frames_one_field(self):
        w, menu = hermes('hm_requests.png'), hermes('hm_build_menu.png')
        frames = [w, w, menu, menu, hermes('hm_field_tap.png'), hermes('hm_confirmed2.png'),
                  hermes('hm_spire_up.png'), w, w, w, menu, menu, menu, w]
        ocr = {'hs_0_read_field': counter(12), 'hs_0_read_res': RES,
               'hs_b0_1': ['Field Built', '"Proqerity', 'Tapto Close'],
               'hs_1_read_field': counter(13), 'hs_1_read_res': RES}
        dev, rc = self.run_hs(frames, ocr)
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps[2], hs.FIELD_TILE)
        cx, cy = dev.taps[3]
        self.assertTrue(1059 <= cx <= 1121 and 527 <= cy <= 589, dev.taps[3])   # inside the check disc
        self.assertEqual(dev.taps[5:], [hs.TOAST_CLOSE, v.GROUND, hs.BUILD_BTN, hs.EXIT_BTN])

    def test_reward_info_card_is_closed_too(self):
        frames = self.entry(0) + [RING, MARK, TOAST, TOAST, WORLD] + self.entry(1) + [MENU, WORLD]
        ocr = {'hs_0_read_field': counter(12), 'hs_0_read_res': RES, 'hs_b0_1': ['Field Built'],
               'hs_b0_2': ['Diamond', 'Tapto Close'], 'hs_1_read_field': counter(13),
               'hs_1_read_res': RES}
        dev, rc = self.run_hs(frames, ocr)
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps.count(hs.TOAST_CLOSE), 2)

    def test_at_limit_is_nothing_to_do(self):
        dev, rc = self.run_hs(self.entry(0) + [MENU, WORLD],
                              {'hs_0_read_field': counter(16), 'hs_0_read_res': RES})
        self.assertEqual(rc, 4)
        self.assertEqual(dev.taps, [v.GROUND, hs.BUILD_BTN, hs.EXIT_BTN])
        self.assertIn('at the limit', dev.out.getvalue())

    def test_resources_short_stops_cleanly(self):
        dev, rc = self.run_hs(self.entry(0) + [MENU, WORLD],
                              {'hs_0_read_field': counter(12), 'hs_0_read_res': ['@ 50 3848', '460']})
        self.assertEqual(rc, 4)
        self.assertNotIn(hs.FIELD_TILE, dev.taps)
        self.assertIn('resources short', dev.out.getvalue())

    def test_dry_run_reads_only(self):
        dev, rc = self.run_hs(self.entry(0) + [MENU, WORLD],
                              {'hs_0_read_field': counter(12), 'hs_0_read_res': RES}, '--dry-run')
        self.assertEqual(rc, 0)
        self.assertEqual(dev.taps, [v.GROUND, hs.BUILD_BTN, hs.EXIT_BTN])

    def test_no_build_button_is_nothing_to_do(self):
        dev, rc = self.run_hs(['WORLD', 'WORLD'], {})
        self.assertEqual(rc, 4)
        self.assertEqual(dev.taps, [v.GROUND])

    def test_counter_unreadable_stops(self):
        dev, rc = self.run_hs(self.entry(0) + [MENU, WORLD], {})
        self.assertEqual(rc, 1)
        self.assertNotIn(hs.FIELD_TILE, dev.taps)

    def test_counter_mismatch_after_build_stops(self):
        frames = self.entry(0) + [RING, MARK, TOAST, WORLD] + self.entry(1) + [MENU, WORLD]
        ocr = {'hs_0_read_field': counter(12), 'hs_0_read_res': RES, 'hs_b0_1': ['Field Built'],
               'hs_1_read_field': counter(12), 'hs_1_read_res': RES}
        dev, rc = self.run_hs(frames, ocr, max_builds=2)
        self.assertEqual(rc, 1)
        self.assertIn('expected 13', dev.out.getvalue())
        self.assertEqual(dev.taps.count(hs.FIELD_TILE), 1)

    def test_refused_build_cancels_and_exits(self):
        # check tap: still placing, the T97b retry too -> X, Exit, world
        frames = self.entry(0) + [RING, RING, RING, MENU, WORLD]
        dev, rc = self.run_hs(frames, {'hs_0_read_field': counter(12), 'hs_0_read_res': RES})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps[3:], [CHECK, ('touchscreen', *CHECK), CANCEL, hs.EXIT_BTN])

    def test_diamond_dialog_is_cancelled(self):
        frames = self.entry(0) + [RING, 'DIALOG', MENU, WORLD]
        dev, rc = self.run_hs(frames, {'hs_0_read_field': counter(12), 'hs_0_read_res': RES})
        self.assertEqual(rc, 4)
        self.assertEqual(dev.taps[3:], [CHECK, v.CONFIRM_CANCEL, hs.EXIT_BTN])

    def test_unknown_screen_while_building_stops_without_taps(self):
        frames = self.entry(0) + [RING, MARK, TOAST]
        dev, rc = self.run_hs(frames, {'hs_0_read_field': counter(12), 'hs_0_read_res': RES,
                                       'hs_b0_1': ['Something else']})
        self.assertEqual(rc, 1)
        self.assertEqual(dev.taps[-1], (964, 560))      # the marker; nothing after the unknown frame

    def test_tile_tap_without_placement_never_retries_on_a_changed_screen(self):
        dev, rc = self.run_hs(self.entry(0) + [TOAST], {'hs_0_read_field': counter(12),
                                                         'hs_0_read_res': RES})
        self.assertEqual(rc, 1)
        self.assertEqual(dev.taps[-1], hs.FIELD_TILE)

    def test_tap_lock_held(self):
        import _bot_lock
        p = mock.patch.object(_bot_lock, 'acquire', lambda *a, **k: False)
        p.start()
        self.addCleanup(p.stop)
        dev, rc = self.run_hs([], {})
        self.assertEqual(rc, 7)
        self.assertEqual(dev.taps, [])


if __name__ == '__main__':
    unittest.main()
