"""T99 (live 2026-11-04): a drifting white world cloud on CLAIM (960,602) made
classify() say POPUP on plain world frames -> normalize/open_menu fired BACK on
the world (exit confirm, shots-42960/norm_2). The open Battle Modes menu stays a
non-WORLD screen (no classify state; is_battle_modes is the positive check).
is_quests_panel recalibrated on the tab bar. Real-frame cases skip when the
frames are gone (.spectre, its trash/, hermes scratch).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402
import afk_dailies as dl  # noqa: E402
import afk_normalize  # noqa: E402
import make_frame_manifest as m  # noqa: E402
from fake_vision import FakeDevice, frame  # noqa: E402

HERMES = Path.home() / 'AppData/Local/hermes/cache/scratch'
CLOUD_WORLD = ('shots-42960/norm_pop3.png', 'shots-80396/norm_2.png', 'shots-80396/norm_final.png',
               'shots-77496/dl_menu_0.png', 'shots-44432/dg_panel.png')
POPUPS = ('shots-60424/r1_1a_popup.png', 'shots-65688/r1_1a_popup.png',
          'shots-41228/r1_1a_popup.png',
          'shots-42960/norm_2.png')          # the exit confirm the cloud BACK opened
HUB = ('shots-42960/norm_0.png', 'shots-10184/bm_1.png', 'shots-80660/norm_3.png')
QUESTS = ('shots-82080/dl_questpanel.png', 'shots-80768/dl_questpanel.png',
          'shots-67620/dl_questpanel.png', 'shots-37116/dl_questpanel.png',
          'shots-73652/dl_tab_lucky.png', 'shots-53520/dl_questpanel.png')
NOT_QUESTS = ('shots-82080/dl_menu_1.png',   # main menu (old rule: True)
              'shots-38632/bm_2.png',        # Battle Modes, same tab bar + hamburger
              'shots-10184/bm_1.png', 'livecheck/hall_now.png', 'shots-77496/dl_menu_0.png')


def real(rel: str):
    for path in (m.REPO / '.spectre' / rel, m.REPO / '.spectre' / 'trash' / rel, HERMES / rel):
        if path.exists():           # the watch moves old shot dirs to trash/
            return m.load_rgb(path)
    raise unittest.SkipTest(f'frame missing: {rel}')


class RealFrames(unittest.TestCase):
    def test_cloud_world_is_world(self):
        for rel in CLOUD_WORLD + ('world_banner_frame.png', 'world_now.png'):
            with self.subTest(rel):
                self.assertEqual(v.classify(real(rel)), 'WORLD')

    def test_real_popups_stay_popup(self):
        for rel in POPUPS:
            with self.subTest(rel):
                self.assertEqual(v.classify(real(rel)), 'POPUP')

    def test_menu_fade_in_not_world(self):
        # Battle Modes fading in over the world: HUD bar 87, below the cut
        self.assertEqual(v.classify(real('shots-73788/bm_1.png')), 'POPUP')

    def test_hub_is_battle_modes_not_world(self):
        for rel in HUB + ('bm_hub_frame.png',):
            with self.subTest(rel):
                img = real(rel)
                self.assertTrue(v.is_battle_modes(img))
                self.assertIn(v.classify(img), ('UNKNOWN', 'POPUP'))

    def test_quest_panel(self):
        for rel in QUESTS:
            with self.subTest(rel):
                self.assertTrue(dl.is_quests_panel(real(rel)))
        for rel in NOT_QUESTS:
            with self.subTest(rel):
                self.assertFalse(dl.is_quests_panel(real(rel)))


class Flows(unittest.TestCase):
    def test_normalize_cloud_world_no_taps(self):
        dev = FakeDevice(self, [real('shots-80396/norm_2.png')])
        self.assertEqual(afk_normalize.main(), 0)
        self.assertEqual(dev.taps, [])

    def test_open_menu_cloud_world_taps_menu(self):
        dev = FakeDevice(self, [real('shots-77496/dl_menu_0.png'), 'MENU'])
        self.assertTrue(dl.open_menu())
        self.assertEqual(dev.taps, [dl.MENU])

    def test_normalize_hub_back_to_world(self):
        dev = FakeDevice(self, [real('shots-42960/norm_0.png'), real('world_now.png')])
        self.assertEqual(afk_normalize.main(), 0)
        self.assertEqual(dev.taps, [('key', 4)])

    def test_open_menu_hub_backs_out(self):
        # layout A hub reads UNKNOWN: BACK, never the MENU tap onto the menu
        dev = FakeDevice(self, [real('shots-10184/bm_1.png'), frame('WORLD'), 'MENU'])
        self.assertTrue(dl.open_menu())
        self.assertEqual(dev.taps, [('key', 4), dl.MENU])


if __name__ == '__main__':
    unittest.main()
