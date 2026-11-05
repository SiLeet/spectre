"""T105b: the Avalon Creator opened in Layout mode (Hermes live, shots-79896) - detector + flows."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402
import afk_homestead as hs  # noqa: E402
from fake_vision import FakeDevice  # noqa: E402
from make_frame_manifest import load_rgb  # noqa: E402
from test_homestead import HERMES, MENU, RES, SPECTRE, WORLD, cnt, hermes, paint  # noqa: E402

# measured colours of shots-79896/hs_0_menu: Build pill cream, Layout pill green
LAYOUT = lambda: paint('UNKNOWN', [(hs.EXIT_BTN, 12, (198, 187, 183)), (hs.BUILD_TAB, 12, (230, 223, 221)),  # noqa: E731
                                   (hs.LAYOUT_TAB, 12, (130, 175, 125))])
LAYOUT_FRAMES = [SPECTRE / 'shots-79896' / 'hs_0_menu.png', HERMES / 't105b_diag.png',
                 HERMES / 'final16.png', HERMES / 'reset1.png']
BUILD_FRAMES = [HERMES / 'hm_build_menu.png', SPECTRE / 'shots-47000' / 'hs_0_menu.png',
                SPECTRE / 'shots-67544' / 'hs_1_menu.png', SPECTRE / 'shots-68276' / 'hs_0_menu.png']


def real(path):
    if not path.exists():
        raise unittest.SkipTest(f'frame missing: {path}')
    return load_rgb(path)


class Detector(unittest.TestCase):
    def test_layout_mode_on_the_live_frames(self):
        for p in LAYOUT_FRAMES:
            img = real(p)
            self.assertTrue(hs.layout_mode(img), p)
            self.assertFalse(hs.is_build_menu(img), p)

    def test_build_mode_and_world_are_not_layout(self):
        for p in BUILD_FRAMES:
            img = real(p)
            self.assertFalse(hs.layout_mode(img), p)
            self.assertTrue(hs.is_build_menu(img), p)
        for name in ('hm_requests.png', 'menu16.png', 't105exit.png', 'hm_up3.png'):
            self.assertFalse(hs.layout_mode(hermes(name)), name)

    def test_synthetic_layout_frame(self):
        self.assertTrue(hs.layout_mode(LAYOUT()))
        self.assertFalse(hs.layout_mode(MENU()))


class ToBuildMode(unittest.TestCase):
    def test_layout_mode_taps_the_build_pill(self):
        dev = FakeDevice(self, [MENU()])
        self.assertIsNotNone(hs.to_build_mode(LAYOUT(), 't'))
        self.assertEqual(dev.taps, [hs.BUILD_TAB])

    def test_fade_in_is_read_again_without_a_tap(self):
        dev = FakeDevice(self, ['UNKNOWN', MENU()])
        self.assertIsNotNone(hs.to_build_mode(WORLD(), 't'))
        self.assertEqual(dev.taps, [])
        self.assertEqual(dev.shots, ['t_m0', 't_m1'])

    def test_never_recognised_is_none_without_a_tap(self):
        dev = FakeDevice(self, ['UNKNOWN'] * 3, ocr={'t_m2': ['Multiselect', 'Foundation']})
        self.assertIsNone(hs.to_build_mode(WORLD(), 't'))
        self.assertEqual(dev.taps, [])
        self.assertIn("menu words ['multiselect', 'foundation']", dev.out.getvalue())

    def test_layout_mode_that_stays_is_bounded(self):
        dev = FakeDevice(self, [LAYOUT(), LAYOUT(), LAYOUT()])
        self.assertIsNone(hs.to_build_mode(LAYOUT(), 't'))
        self.assertEqual(dev.taps, [hs.BUILD_TAB] * 3)


class Flow(unittest.TestCase):
    def run_hs(self, frames, ocr):
        for p in (mock.patch.object(hs, 'MAX_BUILDS', 1), mock.patch.object(hs, 'TABS', hs.TABS[:1])):
            p.start()
            self.addCleanup(p.stop)
        dev = FakeDevice(self, [f() if callable(f) else f for f in frames], ocr=ocr)
        return dev, hs.main([])

    def test_menu_opened_in_layout_mode(self):
        # live shots-79896: Build tap -> Layout mode -> Build pill -> Build mode -> Field at the limit
        dev, rc = self.run_hs([WORLD, WORLD, LAYOUT, MENU, MENU, MENU, WORLD],
                              {**cnt('hs_0_read', 16), 'hs_0_read_res': RES})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [v.GROUND, hs.BUILD_BTN, hs.BUILD_TAB, hs.EXIT_BTN])
        self.assertIn('Layout mode -> Build pill', dev.out.getvalue())

    def test_start_frame_in_layout_mode(self):
        dev, rc = self.run_hs([LAYOUT, MENU, MENU, MENU, WORLD], {**cnt('hs_0_read', 16), 'hs_0_read_res': RES})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [hs.BUILD_TAB, hs.EXIT_BTN])
        self.assertNotIn(('key', 4), dev.taps)


if __name__ == '__main__':
    unittest.main()
