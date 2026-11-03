"""T66 zombie recovery (night log 2026-11-03): one scenario per escape path.

  normalize: 5x POPUP -> escape ladder -> world / gave up (bounded)
  arena:     SELECT, then stagnant RESULT -> card dismiss + re-select -> Challenge
  stage:     still 'BATTLE' at start -> one dismiss retry -> normal flow / abort
  dream:     'could not reach the world view' -> ladder -> recovered
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
import afk_stage_push as sp  # noqa: E402
from fake_vision import FakeDevice, frame  # noqa: E402
from test_runtime_fixes import StagePushCase  # noqa: E402

NORMAL_PASS = 9         # 4 x (norm_i + resolver shot) + norm_final, all POPUP


class NormalizeLadder(unittest.TestCase):
    def test_popup_streak_escapes_to_world(self):
        dev = FakeDevice(self, ['POPUP'] * (NORMAL_PASS + 4) + ['WORLD'])
        self.assertEqual(afk_normalize.main(), 0)
        out = dev.out.getvalue()
        self.assertIn('5x POPUP in a row', out)
        self.assertIn('ESCAPE: recovered (WORLD) before step back2, cycle 1', out)
        # normal pass: 4 BACKs; ladder: resolver (no OCR hit), BACK, ground tap
        self.assertEqual(dev.taps, [v.BACK] * 4 + [v.BACK, v.GROUND])

    def test_gives_up_bounded(self):
        dev = FakeDevice(self, ['POPUP'] * (NORMAL_PASS + 2 * 5 + 1))
        self.assertEqual(afk_normalize.main(), 1)
        self.assertIn('ESCAPE: gave up after 2 cycle(s), screen POPUP', dev.out.getvalue())
        self.assertEqual(dev.frames, [])                       # nothing beyond the cap

    def test_ground_tap_skipped_on_purchase_text(self):
        dev = FakeDevice(self, ['POPUP'] * 5 + ['WORLD'],       # cycle 1 = 5 shots
                         ocr={'esc_1_ground': ['Special Pack', 'Buy now']})
        self.assertTrue(afk_normalize.escape_ladder('esc'))
        self.assertNotIn(v.GROUND, dev.taps)
        self.assertIn('ground tap skipped', dev.out.getvalue())

    def test_confirm_dialog_is_cancelled(self):
        dev = FakeDevice(self, ['DIALOG', 'WORLD'])
        self.assertTrue(afk_normalize.escape_ladder('esc'))
        self.assertEqual(dev.taps, [v.CONFIRM_CANCEL])

    def test_unknown_streak_does_not_trigger_the_ladder(self):
        dev = FakeDevice(self, ['UNKNOWN'] * 5)
        self.assertEqual(afk_normalize.main(), 1)
        self.assertNotIn('ESCAPE', dev.out.getvalue())


class ArenaZombie(unittest.TestCase):
    def test_select_result_zombie_then_challenge(self):
        # night log: step 0 SELECT, steps 1..5 RESULT (the card never goes away)
        dev = FakeDevice(self, ['WORLD', 'BATTLE_MODES', 'ARENA_LOBBY', 'UNKNOWN', 'UNKNOWN',
                                'UNKNOWN',                                       # step0 SELECT
                                'ARENA_RESULT', 'ARENA_RESULT', 'ARENA_RESULT',  # 1, 2, 3 (stagnant 2)
                                'UNKNOWN', 'ARENA_PREP',                         # re-select, prep
                                'UNKNOWN', 'ARENA_LOBBY'], also=(ar,))           # fight start/after
        with mock.patch.object(sys, 'argv', ['afk_arena.py']):
            self.assertEqual(ar.main(), 0)
        self.assertEqual(dev.taps[3:], [ar.OPPONENT_LEFT, ar.CARD_DISMISS, ar.CARD_DISMISS,
                                        ar.CARD_DISMISS,                         # zombie recovery
                                        ar.OPPONENT_LEFT, ar.ARENA_BATTLE])
        self.assertIn('zombie: 2 steps without progress', dev.out.getvalue())


class StageStillBattle(StagePushCase):
    def test_still_battle_dismiss_retry_then_normal(self):
        dev, rc = self.run_sp(['SP_BATTLE', 'SP_BATTLE',            # start + 3 s later: identical
                               'SP_PREP',                           # after BACK + centre
                               'SP_BATTLE', 'SP_RESULT', 'SP_RESULT'])
        self.assertEqual(rc, 0)
        self.assertEqual(dev.taps, [v.BACK, sp.CARD_CLOSE, sp.BATTLE_BTN])
        self.assertIn('after dismiss retry: PREP', dev.out.getvalue())

    def test_still_battle_twice_aborts(self):
        dev, rc = self.run_sp(['SP_BATTLE'] * 4)
        self.assertEqual(rc, 1)
        self.assertEqual(dev.taps, [v.BACK, sp.CARD_CLOSE])

    def test_is_static(self):
        a = frame('SP_BATTLE')
        b = frame('SP_BATTLE')
        b.paste((250, 250, 250), (300, 200, 1600, 900))           # a fight animates
        self.assertTrue(sp.is_static(a, frame('SP_BATTLE')))
        self.assertFalse(sp.is_static(a, b))


class DreamWorldFail(unittest.TestCase):
    def test_world_fail_recovered_by_ladder(self):
        dev = FakeDevice(self, ['UNKNOWN',                    # dr_start
                                'UNKNOWN', 'UNKNOWN', 'UNKNOWN', 'UNKNOWN',  # reach_world: 4 -> fail
                                'WORLD',                      # ladder: recovered at once
                                'WORLD',                      # reach_world('dr_world2')
                                'BATTLE_MODES', 'DR_BOSS',    # enter_dream, back_to_ready
                                'DR_BOSS'])                   # dr_final
        with mock.patch.object(dr, '_dismiss_taps', 0):
            self.assertEqual(dr.run(argparse.Namespace(fights=0, wait_fight=150)), 0)
        out = dev.out.getvalue()
        self.assertIn('escape ladder (max 2 cycles)', out)
        self.assertIn('ESCAPE: recovered (WORLD)', out)
        self.assertEqual(dev.taps, [dr.BATTLE_MODES, dr.DREAM_CARD])

    def test_world_fail_ladder_gives_up(self):
        dev = FakeDevice(self, ['UNKNOWN'] * 5 + ['UNKNOWN'] * 11)
        with mock.patch.object(dr, '_dismiss_taps', 0):
            self.assertEqual(dr.run(argparse.Namespace(fights=0, wait_fight=150)), 1)
        self.assertIn('ESCAPE: gave up', dev.out.getvalue())


if __name__ == '__main__':
    unittest.main()
