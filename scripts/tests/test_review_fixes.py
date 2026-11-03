"""Regression tests for the 2026-11-03 scripts review fixes (T58).

F<n> = position of the finding in docs/reviews/2026-11-03-scripts-review.md.
Real-frame cases need the local .spectre/ frames and skip when they are gone.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_arena as ar  # noqa: E402
import afk_claim_vision as v  # noqa: E402
import afk_stage_push as sp  # noqa: E402
from fake_vision import FakeDevice, frame  # noqa: E402
from make_frame_manifest import REPO, load_rgb  # noqa: E402


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


if __name__ == '__main__':
    unittest.main()
