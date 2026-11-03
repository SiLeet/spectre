"""Regression tests for the 2026-11-03 scripts review fixes (T58).

F<n> = position of the finding in docs/reviews/2026-11-03-scripts-review.md.
Real-frame cases need the local .spectre/ frames and skip when they are gone.
"""
from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_arena as ar  # noqa: E402
import afk_claim_vision as v  # noqa: E402
import afk_hero_level as hl  # noqa: E402
import afk_stage_push as sp  # noqa: E402
from fake_vision import FakeDevice, frame  # noqa: E402
from make_frame_manifest import REPO, load_rgb  # noqa: E402
from test_parsers import DETAIL_74, DETAIL_NO_BADGE, HALL  # noqa: E402


def real(relpath: str):
    path = REPO / '.spectre' / relpath
    if not path.exists():
        raise unittest.SkipTest(f'frame missing: .spectre/{relpath}')
    return load_rgb(path)


class F1ConfirmDialog(unittest.TestCase):
    """One purchase/confirm detector for arena + stage push."""

    DIALOGS = ('screens/arena_debug1.png',            # 'Spend diamonds' (arena, row 729)
               'shots-49936/sp_auto_3.png',           # 'Turn off Auto Battle' (row 711)
               'shots-49936/sp_auto_244.png')         # same dialog, row 729
    NOT_DIALOGS = ('shots/arena_p1_pre.png',          # Select Opponent (old false positive)
                   'game_boot.png', 'shots-33404/dr_rec1_4.png')

    def test_real_dialogs_detected(self):
        for rel in self.DIALOGS:
            with self.subTest(rel):
                img = real(rel)
                self.assertTrue(v.is_confirm_dialog(img))
                self.assertEqual(sp.classify_battle(img), 'CONFIRM')

    def test_lookalikes_rejected(self):
        for rel in self.NOT_DIALOGS:
            with self.subTest(rel):
                img = real(rel)
                self.assertFalse(v.is_confirm_dialog(img))
                self.assertNotEqual(sp.classify_battle(img), 'CONFIRM')

    def test_synthetic(self):
        self.assertTrue(v.is_confirm_dialog(frame('DIALOG')))
        self.assertEqual(sp.classify_battle(frame('DIALOG')), 'CONFIRM')
        for st in ('WORLD', 'PANEL', 'POPUP', 'UNKNOWN', 'BATTLE_MODES'):
            self.assertFalse(v.is_confirm_dialog(frame(st)), st)

    def test_arena_cancels_purchase_dialog(self):
        # world -> battle modes -> lobby -> select -> pre-fight shot = dialog
        dev = FakeDevice(self, ['WORLD', 'BATTLE_MODES', 'ARENA_LOBBY', 'UNKNOWN', 'DIALOG'],
                         also=(ar,))
        with mock.patch.object(sys, 'argv', ['afk_arena.py']):
            self.assertEqual(ar.main(), 0)
        self.assertEqual(dev.taps, [v.GROUND, ar.ARENA_CARD, ar.CHALLENGE, v.CONFIRM_CANCEL])
        self.assertIn('purchase dialog cancelled', dev.out.getvalue())



class F6BattleModes(unittest.TestCase):
    """is_battle_modes must not accept other cream screens."""

    MENU = ('shots/arena_0_initial.png', 'world4.png', 'shots-48392/dr_hub.png')
    LOOKALIKES = ('hall.png', 'shots-17856/dl_final.png',          # main menu
                  'shots/arena_1_after.png', 'shots/t28_fight_end1.png',  # defeat / battle ended
                  'shots-4844/sp_0_initial.png',                    # victory card
                  'shots-40256/sp_wait.png')                        # loading tip

    def test_menu(self):
        for rel in self.MENU:
            with self.subTest(rel):
                self.assertTrue(v.is_battle_modes(real(rel)))

    def test_lookalikes(self):
        for rel in self.LOOKALIKES:
            with self.subTest(rel):
                self.assertFalse(v.is_battle_modes(real(rel)))

    def test_synthetic(self):
        self.assertTrue(v.is_battle_modes(frame('BATTLE_MODES')))
        cream = frame('BATTLE_MODES')
        cream.paste((240, 235, 225), (480, 900, 1180, 960))   # tab icons gone
        self.assertFalse(v.is_battle_modes(cream))



class F2HeroLevel(unittest.TestCase):
    """Hall re-verify between hands + exit 1 on any failed hand."""

    def run_hl(self, frames, ocr, hands=(710, 840)):
        dev = FakeDevice(self, frames, ocr=ocr)
        keys = []
        for patch in (mock.patch.object(hl, 'key', lambda code, wait=1.5: dev.taps.append(('key', code))),
                      mock.patch.object(hl, 'HAND_XS', list(hands)),
                      mock.patch.object(sys, 'argv', ['afk_hero_level.py', '--target', '90'])):
            patch.start()
            self.addCleanup(patch.stop)
        return dev, hl.main()

    def test_hall_lost_is_reentered_from_town(self):
        lvl95 = ['Affinity', 'Lvl. 95']
        dev, rc = self.run_hl(['UNKNOWN', 'UNKNOWN', 'WORLD', 'UNKNOWN', 'UNKNOWN'],
                              {'hl_entry': HALL, 'hl_710_0': lvl95, 'hl_hall_840': ['Battle Modes'],
                               'hl_hall_840_reenter': HALL, 'hl_840_0': lvl95})
        self.assertEqual(rc, 0)
        self.assertEqual(dev.taps, [hl.HALL_BTN, (710, hl.HANDS_Y), ('key', 4),
                                    hl.HALL_BTN, (840, hl.HANDS_Y), ('key', 4)])

    def test_unknown_screen_between_hands_stops_without_blind_tap(self):
        dev, rc = self.run_hl(['UNKNOWN', 'UNKNOWN', 'UNKNOWN'],
                              {'hl_entry': HALL, 'hl_710_0': ['Affinity', 'Lvl. 95']})
        self.assertEqual(rc, 1)
        self.assertEqual(dev.taps, [hl.HALL_BTN, (710, hl.HANDS_Y), ('key', 4)])

    def test_unreadable_hand_exits_1(self):
        dev, rc = self.run_hl(['UNKNOWN', 'UNKNOWN', 'UNKNOWN', 'UNKNOWN'],
                              {'hl_entry': HALL, 'hl_710_0': DETAIL_NO_BADGE,
                               'hl_hall_840': HALL, 'hl_840_0': ['Affinity', 'Lvl. 95']})
        self.assertEqual(rc, 1)
        self.assertIn('with failures', dev.out.getvalue())



class F5ArenaExitCodes(unittest.TestCase):
    """A run that fought nothing must exit 1 (watch.sh burns the marker on 0)."""
    TO_SELECT = ['WORLD', 'BATTLE_MODES', 'ARENA_LOBBY', 'UNKNOWN']

    def run_arena(self, frames):
        dev = FakeDevice(self, frames, also=(ar,))
        with mock.patch.object(sys, 'argv', ['afk_arena.py']):
            return dev, ar.main()

    def test_stuck_chain_exits_1(self):
        dev, rc = self.run_arena(self.TO_SELECT + ['UNKNOWN'] + ['UNKNOWN'] * 6)
        self.assertEqual(rc, 1)
        self.assertEqual(dev.taps[3:], [ar.OPPONENT_LEFT] * 6)

    def test_unchanged_screen_exits_1(self):
        dev, rc = self.run_arena(self.TO_SELECT + ['UNKNOWN', 'ARENA_PREP', 'UNKNOWN', 'UNKNOWN'])
        self.assertEqual(rc, 1)
        self.assertIn('screen unchanged', dev.out.getvalue())

    def test_fought_exits_0(self):
        dev, rc = self.run_arena(self.TO_SELECT + ['UNKNOWN', 'ARENA_PREP', 'UNKNOWN', 'ARENA_LOBBY'])
        self.assertEqual(rc, 0)
        self.assertIn('done: 1 arena fights driven', dev.out.getvalue())



class F19ArenaTapRc(unittest.TestCase):
    def setUp(self):
        for patch in (mock.patch('time.sleep'), mock.patch.object(sys, 'stdout', io.StringIO())):
            patch.start()
            self.addCleanup(patch.stop)

    def test_failed_tap_retried_once(self):
        with mock.patch.object(v, 'tap', side_effect=[RuntimeError('adb tap failed'), None]) as t:
            ar.tap(ar.CHALLENGE, 4.0)
        self.assertEqual(t.call_count, 2)

    def test_second_failure_raises(self):
        with mock.patch.object(v, 'tap', side_effect=RuntimeError('adb tap failed')):
            with self.assertRaises(RuntimeError):
                ar.tap(ar.CHALLENGE)



class F16IdleSeconds(unittest.TestCase):
    def test_tick_delta_wraps(self):
        self.assertEqual(v.tick_delta(5_000, 2_000), 3_000)
        # GetTickCount wrapped past 2**32 after the last input
        self.assertEqual(v.tick_delta(1_000, 0xFFFFFF00), 1_256)
        # past 2**31 ms uptime (where the old c_long went negative)
        self.assertEqual(v.tick_delta(2**31 + 10_000, 2**31 - 5_000), 15_000)

    @unittest.skipUnless(sys.platform == 'win32', 'GetLastInputInfo is Windows-only')
    def test_idle_seconds_non_negative(self):
        self.assertGreaterEqual(v.idle_seconds(), 0)


if __name__ == '__main__':
    unittest.main()
