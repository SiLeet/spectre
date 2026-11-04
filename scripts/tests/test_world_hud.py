"""T98 world-HUD taps (live 2026-11-04, 'Battle Modes did not open' at 15:40Z/15:48Z).

Two world-HUD layouts: A (11-03, again from 15:39Z) and B (seen 11-04
10:39-15:53 local, appeared mid-session: bottom bar drawn ~100 px right, no hamburger drawn).
BATTLE_MODES_BTN / MENU opened their menus in both, but is_battle_modes only
knew B's menu tab row, so the open A menu read as 'not open'. Real-frame cases
skip when .spectre is gone.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402
import afk_dailies as dl  # noqa: E402
import make_frame_manifest as m  # noqa: E402
from fake_vision import FakeDevice  # noqa: E402

BM_A = ('shots-10184/bm_1.png', 'shots-73788/bm_2.png', 'shots-51424/bm_1.png')
BM_B = ('shots-80660/norm_3.png', 'shots-42388/bm_1.png')
BM_OTHER_TAB = ('livecheck/world1.png',          # Guild Mode tab
                'shots-readonly-122730.png')     # Events tab
WORLD_A = ('shots-10184/rw_0.png', 'shots-10184/bm_0.png', 'shots-73788/bm_0.png',
           'shots-37116/dl_menu_0.png', 'shots-78504/rw_2.png')
WORLD_B = ('shots-79040/norm_0.png', 'shots-53520/dl_menu_0.png', 'shots-428/rw_0.png')


def real(rel: str):
    for path in (m.REPO / '.spectre' / rel, m.REPO / '.spectre' / 'trash' / rel):
        if path.exists():           # the watch moves old shot dirs to trash/
            return m.load_rgb(path)
    raise unittest.SkipTest(f'frame missing: .spectre/{rel}')


def hamburger(img) -> int:
    """60th-brightest pixel around MENU: A >= 244 (white stripes), B <= 65."""
    box = img.convert('L').crop((dl.MENU[0] - 14, dl.MENU[1] - 14, dl.MENU[0] + 15, dl.MENU[1] + 15))
    return sorted(box.tobytes())[-60]


class RealFrames(unittest.TestCase):
    def test_battle_modes_both_layouts(self):
        for rel in BM_A + BM_B:
            with self.subTest(rel):
                self.assertTrue(v.is_battle_modes(real(rel)))

    def test_not_battle_modes(self):
        for rel in BM_OTHER_TAB + WORLD_A + WORLD_B:
            with self.subTest(rel):
                self.assertFalse(v.is_battle_modes(real(rel)))

    def test_menu_on_hamburger(self):
        for rel in WORLD_A:
            with self.subTest(rel):
                img = real(rel)
                self.assertEqual(v.classify(img), 'WORLD')
                self.assertGreater(hamburger(img), 200)
        for rel in WORLD_B:         # B draws none (the tap still opened the menu live)
            with self.subTest(rel):
                self.assertLess(hamburger(real(rel)), 120)

    def test_open_battle_modes_layout_a(self):
        # the 15:40Z run (shots-10184): world -> one tap -> open A menu = success
        dev = FakeDevice(self, [real('shots-10184/rw_0.png'), real('shots-10184/bm_0.png'),
                                real('shots-10184/bm_1.png')])
        self.assertTrue(v.open_battle_modes())
        self.assertEqual(dev.taps, [v.GROUND, v.BATTLE_MODES_BTN])


if __name__ == '__main__':
    unittest.main()
