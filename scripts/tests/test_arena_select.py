"""T95 arena select screen (live daily 2026-11-04 14:36, shots-52268).

The left-card tap (750,500) only toggled the opponent detail view (f1_step0
-> step1 detail -> step2 select ...) -> 'could not reach a fight (STUCK)'.
The exit then met the select screen as 'unrecognised' (the old refresh-badge
probe (1160,1010) reads the carpet on this layout) and normalize BACKed the
floor 4x (shots-79700/norm_*). is_select: left sword ring green + cream back
and Refresh plates. Real-frame cases skip when .spectre is gone.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_arena as ar  # noqa: E402
import afk_claim_vision as v  # noqa: E402
import afk_normalize  # noqa: E402
from fake_vision import FakeDevice  # noqa: E402
from make_frame_manifest import REPO, load_rgb  # noqa: E402

SELECT = ('shots-52268/arena_2_select.png', 'shots-52268/arena_f1_step0.png',
          'shots-52268/arena_exit0.png', 'shots-79700/norm_0.png')
LOBBY = ('shots-52268/arena_1_lobby.png', 'shots-15028/norm_0.png')
DETAIL = ('shots-52268/arena_f1_step1.png', 'shots-52268/arena_f1_step5.png')
OTHER = ('shots-66808/dr_f1_chances.png',    # DR boss page
         'shots-27712/r1_0_initial.png',     # AFK Rewards panel
         'trash/shots-6048/rw_0.png')        # AFK DEFEAT card: cream plate + green Retry
NOT_SELECT = LOBBY + DETAIL[:1] + OTHER


def real(relpath: str):
    path = REPO / '.spectre' / relpath
    if not path.exists():
        raise unittest.SkipTest(f'frame missing: .spectre/{relpath}')
    return load_rgb(path)


class RealFrames(unittest.TestCase):
    def test_select(self):
        for rel in SELECT:
            with self.subTest(rel):
                img = real(rel)
                self.assertTrue(ar.is_select(img))
                self.assertEqual(ar.arena_state(img), 'SELECT')

    def test_not_select(self):
        for rel in NOT_SELECT:
            with self.subTest(rel):
                self.assertFalse(ar.is_select(real(rel)))

    def test_detail(self):
        for rel in DETAIL:
            with self.subTest(rel):
                img = real(rel)
                self.assertTrue(ar.is_detail(img))
                self.assertEqual(ar.arena_state(img), 'SELECT')     # never PREP: (960,1010) is Refresh
                self.assertGreater(v.lum(ar.avg(img, ar.SELECT_ARROW)), 170)
        for rel in SELECT + LOBBY + OTHER:
            with self.subTest(rel):
                self.assertFalse(ar.is_detail(real(rel)))

    def test_exit_from_detail(self):
        dev = FakeDevice(self, [real(DETAIL[1]), real(SELECT[0]), real(LOBBY[0]), 'BATTLE_MODES',
                                'WORLD'], also=(ar,))
        self.assertTrue(ar.exit_to_world())
        self.assertEqual(dev.taps, [ar.SELECT_ARROW, ar.SELECT_ARROW, ar.BACK, ar.BACK])

    def test_normalize_from_detail(self):
        # old: POPUP -> resolver -> BACK on the carpet -> escape ladder
        dev = FakeDevice(self, [real(DETAIL[0]), real(SELECT[0]), real(LOBBY[0]), 'BATTLE_MODES',
                                'WORLD'])
        self.assertEqual(afk_normalize.main(), 0)
        self.assertEqual(dev.taps, [ar.SELECT_ARROW, ar.SELECT_ARROW, ar.LOBBY_BACK, v.BACK])

    def test_tap_spots(self):
        img = real(SELECT[0])
        gmax = lambda c: c[1] - max(c[0], c[2])
        self.assertGreater(v.lum(ar.avg(img, ar.SWORD_LEFT, r=4)), 240)    # white sword icon
        for p in ar.SWORD_RING:
            self.assertGreater(gmax(ar.avg(img, p, r=4)), 50)              # measured 54 / 63
        self.assertGreater(v.lum(ar.avg(img, ar.SELECT_ARROW)), 170)       # arrow on the plate
        self.assertLess(v.lum(ar.avg(img, v.BACK)), 90)                     # v.BACK: carpet
        for rel in LOBBY:
            self.assertGreater(v.lum(ar.avg(real(rel), ar.LOBBY_BACK)), 170)

    def test_advance_taps_the_sword(self):
        # old: OPPONENT_LEFT x6 -> STUCK
        dev = FakeDevice(self, [real(SELECT[1]), 'ARENA_PREP'], also=(ar,))
        self.assertEqual(ar.advance_to_fight('arena_f1'), 'PREP')
        self.assertEqual(dev.taps, [ar.SWORD_LEFT, ar.ARENA_BATTLE])

    def test_advance_presses_challenge_on_the_detail_view(self):
        # live f1_step0..5: select <-> detail toggled until STUCK; the detail
        # view now gets its own Challenge! bar (green on every detail frame)
        dev = FakeDevice(self, [real(SELECT[1]), real(DETAIL[0]), 'ARENA_PREP'], also=(ar,))
        self.assertEqual(ar.advance_to_fight('arena_f1'), 'PREP')
        self.assertEqual(dev.taps, [ar.SWORD_LEFT, ar.DETAIL_CHALLENGE, ar.ARENA_BATTLE])
        for rel in DETAIL:
            c = ar.avg(real(rel), ar.DETAIL_CHALLENGE, r=4)
            self.assertGreater(c[1] - max(c[0], c[2]), 35, rel)
        c = ar.avg(real(SELECT[0]), ar.DETAIL_CHALLENGE, r=4)
        self.assertLess(c[1] - max(c[0], c[2]), 0)

    def test_exit_from_select(self):
        # old: 'unrecognised screen', no tap
        dev = FakeDevice(self, [real(SELECT[2]), real(LOBBY[0]), 'BATTLE_MODES', 'WORLD'],
                         also=(ar,))
        self.assertTrue(ar.exit_to_world())
        self.assertEqual(dev.taps, [ar.SELECT_ARROW, ar.BACK, ar.BACK])

    def test_normalize_from_select(self):
        # old: BACK x4 on the carpet, rc 1 (shots-79700)
        dev = FakeDevice(self, [real(SELECT[3]), real(LOBBY[0]), 'BATTLE_MODES', 'WORLD'])
        self.assertEqual(afk_normalize.main(), 0)
        self.assertEqual(dev.taps, [ar.SELECT_ARROW, ar.LOBBY_BACK, v.BACK])

    def test_normalize_pressed_lobby_skips_the_resolver(self):
        # old: norm_1 POPUP -> OCR 'Daily Rewards' -> LOGIN_CLAIM onto Battle Modes
        dev = FakeDevice(self, [real('shots-17920/norm_0.png'), real('shots-17920/norm_1.png'),
                                'BATTLE_MODES', 'WORLD'],
                         ocr={'norm_pop1': ['Daily Rewards']})
        self.assertEqual(afk_normalize.main(), 0)
        self.assertEqual(dev.taps, [ar.LOBBY_BACK, v.BACK])     # pressed lobby: wait, no re-tap
        self.assertNotIn(v.LOGIN_CLAIM, dev.taps)


class Synthetic(unittest.TestCase):
    def test_states(self):
        from fake_vision import frame
        self.assertTrue(ar.is_select(frame('ARENA_SELECT_T95')))
        self.assertEqual(ar.arena_state(frame('ARENA_SELECT_T95')), 'SELECT')
        self.assertEqual(v.classify(frame('ARENA_SELECT_T95')), 'UNKNOWN')
        for st in ('ARENA_SELECT', 'ARENA_LOBBY', 'ARENA_PREP', 'BATTLE_MODES', 'UNKNOWN', 'DR_BOSS'):
            with self.subTest(st):
                self.assertFalse(ar.is_select(frame(st)))
                self.assertFalse(ar.is_detail(frame(st)))

    def test_advance_select_sword_prep(self):
        dev = FakeDevice(self, ['ARENA_SELECT_T95', 'ARENA_PREP'], also=(ar,))
        self.assertEqual(ar.advance_to_fight('arena_f1'), 'PREP')
        self.assertEqual(dev.taps, [ar.SWORD_LEFT, ar.ARENA_BATTLE])

    def test_old_layout_keeps_the_card_tap(self):
        dev = FakeDevice(self, ['ARENA_SELECT', 'ARENA_PREP'], also=(ar,))
        self.assertEqual(ar.advance_to_fight('arena_f1'), 'PREP')
        self.assertEqual(dev.taps, [ar.OPPONENT_LEFT, ar.ARENA_BATTLE])

    def test_exit_select_lobby_modes_world(self):
        dev = FakeDevice(self, ['ARENA_SELECT_T95', 'ARENA_LOBBY', 'BATTLE_MODES', 'WORLD'],
                         also=(ar,))
        self.assertTrue(ar.exit_to_world())
        self.assertEqual(dev.taps, [ar.SELECT_ARROW, ar.BACK, ar.BACK])

    def test_normalize_select_and_lobby(self):
        dev = FakeDevice(self, ['ARENA_SELECT_T95', 'ARENA_LOBBY', 'BATTLE_MODES', 'WORLD'])
        self.assertEqual(afk_normalize.main(), 0)
        self.assertEqual(dev.taps, [ar.SELECT_ARROW, ar.LOBBY_BACK, v.BACK])

    def test_normalize_lobby(self):
        dev = FakeDevice(self, ['ARENA_LOBBY', 'BATTLE_MODES', 'WORLD'])
        self.assertEqual(afk_normalize.main(), 0)
        self.assertEqual(dev.taps, [ar.LOBBY_BACK, v.BACK])

    def test_normalize_arena_is_bounded(self):
        # one back tap per screen (one extra step), then waits — no BACK, no resolver
        dev = FakeDevice(self, ['ARENA_SELECT_T95'] * 6)
        self.assertEqual(afk_normalize.main(), 1)
        self.assertEqual(dev.taps, [ar.SELECT_ARROW])
        self.assertEqual(len(dev.shots), 6)                 # norm_0..4 + norm_final

    def test_normalize_stale_select_still_backs_the_lobby(self):
        # shared 2-tap budget: the stale select re-tapped (793,1000) and stranded the lobby
        dev = FakeDevice(self, ['ARENA_SELECT_T95', 'ARENA_SELECT_T95', 'ARENA_LOBBY',
                                'BATTLE_MODES', 'WORLD'])
        self.assertEqual(afk_normalize.main(), 0)
        self.assertEqual(dev.taps, [ar.SELECT_ARROW, ar.LOBBY_BACK, v.BACK])

    def test_arena_taps_count_toward_the_recover_budget(self):
        # select + lobby taps use 2 of the 3 T94 taps: one boss-back left
        dev = FakeDevice(self, ['ARENA_SELECT_T95', 'ARENA_LOBBY', 'DR_BOSS_PAGE', 'DR_BOSS_PAGE',
                                'DR_BOSS_PAGE'])
        self.assertEqual(afk_normalize.main(), 1)
        self.assertEqual(dev.taps, [ar.SELECT_ARROW, ar.LOBBY_BACK, v.DR_BOSS_BACK])


if __name__ == '__main__':
    unittest.main()
