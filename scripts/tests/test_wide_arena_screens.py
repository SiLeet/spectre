"""T100 soft-fails of the 17:5x/18:00 run (afk-bot-2026-11-04.log ~628-700).

classify()'s old PANEL rule (back ~(184,176,174) on cream) also matched the main
menu and the wide arena lobby: normalize accepted them as PANEL, Dream Realm's
'already inside' tapped the lobby's Challenge bar (fight 1 -> Select Opponent),
the hall tap landed on the lobby's Continue bar, and is_lobby / is_select /
is_detail knew only the zoomed (T92/T95) arena layout. Real-frame cases skip
when .spectre is gone.
"""
from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_arena as ar  # noqa: E402
import afk_claim_vision as v  # noqa: E402
import afk_dream_realm as dr  # noqa: E402
import afk_normalize  # noqa: E402
import fake_vision  # noqa: E402
import make_frame_manifest as m  # noqa: E402
from fake_vision import DeadTapDevice, FakeDevice  # noqa: E402

K = ('key', 4)
PANEL = ('shots-2704/r1_1_panel.png', 'shots-49764/r1_1_panel.png')       # old-palette AFK panel
MAIN_MENU = ('shots-70368/norm_0.png', 'shots-75792/rw_0.png', 'livecheck/hub1.png')
WIDE_LOBBY = ('shots-75792/arena_1_lobby.png', 'shots-13684/dr_start.png',
              'shots-81308/norm_1.png')                                    # last: 'Continue' variant
WIDE_SELECT = ('shots-81892/hl_entry.png', 'shots-81308/norm_0.png')
WIDE_DETAIL = ('shots-62888/arena_f1_step1.png', 'shots-42200/arena_f1_step1.png')
NOT_DETAIL = ('shots-58780/sp_prep.png', 'shots-6048/rw_0.png')             # stage prep, defeat card


def real(rel: str):
    for path in (m.REPO / '.spectre' / rel, m.REPO / '.spectre' / 'trash' / rel):
        if path.exists():
            return m.load_rgb(path)
    raise unittest.SkipTest(f'frame missing: .spectre/{rel}')


class RealFrames(unittest.TestCase):
    def test_old_palette_panel_stays_panel(self):
        for rel in PANEL:
            with self.subTest(rel):
                self.assertEqual(v.classify(real(rel)), 'PANEL')

    def test_main_menu_is_not_panel(self):
        for rel in MAIN_MENU:
            with self.subTest(rel):
                img = real(rel)
                self.assertEqual(v.classify(img), 'UNKNOWN')        # old: PANEL
                self.assertFalse(ar.is_lobby(img) or ar.is_select(img) or ar.is_detail(img))

    def test_wide_lobby(self):
        for rel in WIDE_LOBBY:
            with self.subTest(rel):
                img = real(rel)
                self.assertTrue(ar.is_lobby(img))                   # old: plate probe on the bar
                self.assertEqual(v.classify(img), 'UNKNOWN')        # old: PANEL
                self.assertFalse(ar.is_select(img) or ar.is_detail(img))
        self.assertTrue(ar.is_lobby(real('shots-63812/arena_1_lobby.png')))   # zoomed T92 lobby

    def test_wide_select(self):
        for rel in WIDE_SELECT:
            with self.subTest(rel):
                img = real(rel)
                self.assertEqual(ar.sword(img), ar.SWORD_LEFT_W)
                self.assertGreater(v.lum(ar.avg(img, ar.SWORD_LEFT_W, r=4)), 240)   # white icon
                self.assertFalse(ar.is_detail(img) or ar.is_lobby(img))
        self.assertEqual(ar.sword(real('shots-52268/arena_2_select.png')), ar.SWORD_LEFT)

    def test_wide_detail(self):
        gmax = lambda c: c[1] - max(c[0], c[2])
        for rel in WIDE_DETAIL:
            with self.subTest(rel):
                img = real(rel)
                self.assertTrue(ar.is_detail(img))
                self.assertFalse(ar.is_select(img))
                self.assertGreater(gmax(ar.avg(img, ar.DETAIL_CHALLENGE, r=4)), 35)
        for rel in NOT_DETAIL + WIDE_SELECT + WIDE_LOBBY:
            with self.subTest(rel):
                self.assertFalse(ar.is_detail(real(rel)))

    def test_dr_start_lobby_is_not_inside_dream_realm(self):
        img = real('shots-13684/dr_start.png')
        self.assertTrue(dr.is_ready(img))                   # the green bar alone still matches
        self.assertNotIn(v.classify(img), ('DR_BOSS', 'DR_PREP'))
        dev = FakeDevice(self, [img, 'WORLD'])
        with mock.patch.object(dr, 'enter_dream', return_value=False):
            self.assertEqual(dr.run(argparse.Namespace(fights=7, wait_fight=150)), 1)
        self.assertNotIn('already inside', dev.out.getvalue())   # old: fight 1 tapped the bar
        self.assertEqual(dev.taps, [])


class Flows(unittest.TestCase):
    def test_claim_round_refuses_the_main_menu(self):
        dev = FakeDevice(self, [real(MAIN_MENU[0])])
        self.assertEqual(v.claim_round('r1'), 1)            # old: PANEL -> CHEST on 'Guide'
        self.assertEqual(dev.taps, [])

    def test_normalize_main_menu(self):
        # LIVE: BACK closed the menu 3/3 (shots-75792|73788|51424 rw_0 -> rw_1 WORLD)
        dev = FakeDevice(self, [real('shots-75792/rw_0.png'), real('shots-75792/rw_1.png')])
        self.assertEqual(afk_normalize.main(), 0)
        self.assertEqual(dev.taps, [K])

    def test_normalize_wide_lobby(self):
        dev = FakeDevice(self, [real(WIDE_LOBBY[2]), 'BATTLE_MODES', 'WORLD'])
        self.assertEqual(afk_normalize.main(), 0)           # old: 'normalize 0: PANEL', rc 0 on the lobby
        self.assertEqual(dev.taps, [K, K])

    def test_normalize_wide_select(self):
        # LIVE: shots-81308 norm_0 (select) -> BACK -> norm_1 (lobby)
        dev = FakeDevice(self, [real('shots-81308/norm_0.png'), real('shots-81308/norm_1.png'),
                                'BATTLE_MODES', 'WORLD'])
        self.assertEqual(afk_normalize.main(), 0)           # old: resolver + BACK, then lobby = PANEL
        self.assertEqual(dev.taps, [K, K, K])

    def test_advance_wide_select_detail_prep(self):
        # old: neither tell matched -> OPPONENT_LEFT toggled the detail; the wide
        # detail's bar also reads PREP, so ARENA_BATTLE fired there and returned early
        dev = FakeDevice(self, [real(WIDE_SELECT[0]), real(WIDE_DETAIL[0]), 'ARENA_PREP'], also=(ar,))
        self.assertEqual(ar.advance_to_fight('arena_f1'), 'PREP')
        self.assertEqual(dev.taps, [ar.SWORD_LEFT_W, ar.DETAIL_CHALLENGE, ar.ARENA_BATTLE])

    def test_wide_detail_dead_retry_does_not_stick(self):
        # review: the wide detail reads PREP itself, so a dead DETAIL_CHALLENGE retry
        # counted as progress and its tap mode stuck
        with mock.patch.dict(fake_vision._CACHE, {'WIDE_DETAIL': real(WIDE_DETAIL[0])}):
            dev = DeadTapDevice(self, ['WIDE_DETAIL', 'ARENA_LOBBY'], also=(ar,))
            self.assertEqual(ar.advance_to_fight('arena_f1'), 'STUCK')
        c = ar.DETAIL_CHALLENGE
        self.assertEqual(dev.taps, [c, c, ('touchscreen', *c), c, c, K])
        self.assertEqual((v.TAP_MODE, v._TAP_DEAD), ('tap', {'touchscreen'}))

    def test_normalize_old_battle_ended_card_closes_never_back(self):
        # review: the 11-03 card (brown backdrop) was PANEL, then UNKNOWN without a
        # tell -> keyevent BACK (Replay risk, T93); now is_battle_ended -> CARD_CLOSE
        img = real('shots-82560/dr_f1_w16.png')
        self.assertTrue(dr.is_battle_ended(img))
        dev = FakeDevice(self, [img, 'WORLD'])
        self.assertEqual(afk_normalize.main(), 0)
        self.assertEqual(dev.taps, [dr.CARD_CLOSE])


if __name__ == '__main__':
    unittest.main()
