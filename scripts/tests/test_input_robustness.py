"""T97 input robustness (live 2026-11-04 15:44-16:15): every tap on the arena
select was dead (sword x6 -> STUCK, SELECT_ARROW x5 in the exit, normalize
'waiting' x4), while 'input keyevent 4' x3 left select -> lobby -> world.

DeadTapDevice: taps change nothing, only keyevent 4 advances the screen list.
FakeDevice itself fails any keyevent BACK fired on a frame classify() reads as
WORLD (exit confirm), across the whole suite."""
from __future__ import annotations

import subprocess
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
from fake_vision import DeadTapDevice, FakeDevice, frame  # noqa: E402

K = ('key', 4)
OUT = ['ARENA_SELECT_T95', 'ARENA_LOBBY', 'BATTLE_MODES', 'WORLD']   # one keyevent per step


class DeadTaps(unittest.TestCase):
    def test_arena_select_stall_hold_then_back_then_stuck(self):
        dev = DeadTapDevice(self, OUT, also=(ar,))
        self.assertEqual(ar.advance_to_fight('arena_f1'), 'STUCK')
        s = ar.SWORD_LEFT
        # 2 dead taps -> hold-tap -> 2 dead taps -> ONE keyevent out to the lobby
        self.assertEqual(dev.taps, [s, s, ('hold', *s), s, s, K])
        self.assertEqual(len(dev.shots), 6)
        self.assertTrue(ar.exit_to_world())                 # lobby -> modes -> world by keyevent
        self.assertEqual(dev.taps[6:], [K, K])

    def test_arena_detail_stall_hold_then_back(self):
        dev = DeadTapDevice(self, ['ARENA_DETAIL_T95', 'ARENA_LOBBY'], also=(ar,))
        self.assertEqual(ar.advance_to_fight('arena_f1'), 'STUCK')
        c = ar.DETAIL_CHALLENGE
        self.assertEqual(dev.taps, [c, c, ('hold', *c), c, c, K])

    def test_normalize_on_select(self):
        dev = DeadTapDevice(self, OUT)
        self.assertEqual(afk_normalize.main(), 0)           # live: rc 1 after 'waiting' x4
        self.assertEqual(dev.taps, [K, K, K])

    def test_recover_leftover_within_budget(self):
        dev = DeadTapDevice(self, OUT)
        st, _ = v.recover_leftover('r1', frame(OUT[0]), 'r1_0_initial')
        self.assertEqual(st, 'WORLD')
        self.assertEqual(dev.taps, [K, K, K])               # select, lobby (counted) + modes
        self.assertIn('recovery 2/3', dev.out.getvalue())

    def test_reach_world(self):
        dev = DeadTapDevice(self, OUT)
        self.assertTrue(v.reach_world())
        self.assertEqual(dev.taps, [K, K, K])

    def test_dream_card_keeps_card_close(self):
        dev = DeadTapDevice(self, ['DR_ENDED'])
        self.assertEqual(afk_normalize.main(), 1)
        self.assertEqual(dev.taps, [dr.CARD_CLOSE] * afk_normalize.DR_END_TAPS)

    def test_purchase_dialog_keeps_confirm_cancel(self):
        dev = DeadTapDevice(self, ['DIALOG'])
        self.assertFalse(afk_normalize.escape_ladder('esc', cycles=1))
        self.assertEqual(dev.taps, [v.CONFIRM_CANCEL] * len(afk_normalize.LADDER))
        dev = DeadTapDevice(self, ['DIALOG'], also=(ar,))
        self.assertEqual(ar.advance_to_fight('arena_f1'), 'DIALOG')
        self.assertEqual(dev.taps, [v.CONFIRM_CANCEL])

    def test_dailies_quest_icon_hold_only_while_menu_is_open(self):
        import afk_dailies as dl
        # chest: nothing claimable (PANEL x3) -> pre-quests -> menu -> icon tap dead
        # (menu still open) -> ONE hold-tap -> still no quest panel -> rc 1
        dev = FakeDevice(self, ['PANEL'] * 4 + ['MENU', 'MENU', 'UNKNOWN'])
        self.assertEqual(dl.run_dailies(0), 1)
        self.assertEqual(dev.taps[-2:], [dl.QUESTS_ICON, ('hold', *dl.QUESTS_ICON)])


class Guards(unittest.TestCase):
    def test_world_never_gets_keyevent_back(self):
        FakeDevice(self, ['WORLD'])
        v.shot('w')
        with self.assertRaises(AssertionError):
            v.back()

    def test_back_and_hold_commands(self):
        self.assertEqual(v.key_seq([(4, 1.5)], dry=True), 'input keyevent 4 && sleep 1.5')
        with mock.patch.object(v, 'adb', return_value=subprocess.CompletedProcess([], 0)) as adb:
            v.tap_hold((845, 782), wait=0)
        adb.assert_called_once_with('shell', 'input', 'swipe', '845', '782', '845', '782', '120')


if __name__ == '__main__':
    unittest.main()
