"""Regression tests for the runtime review (docs/reviews/2026-11-03-runtime-review.md, A8 / T60).

R<n> = position of the finding in that report. Frames are synthetic
(fake_vision, calibration values from the report); .spectre was emptied (R13).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402
import afk_dream_realm as dr  # noqa: E402
import afk_stage_push as sp  # noqa: E402
from fake_vision import FakeDevice, frame  # noqa: E402


class R1FightMarker(unittest.TestCase):
    """A8a-1: start_fight needs positive evidence, black frames keep polling."""

    def test_is_fight_profile(self):
        self.assertTrue(dr.is_fight(frame('DR_FIGHT')))
        for st in ('DR_BLACK', 'DR_BOSS', 'DR_PREP', 'DR_ENDED'):
            self.assertFalse(dr.is_fight(frame(st)), st)

    def test_black_transition_then_prep_gets_the_prep_tap(self):
        # shots-33128: boss tap -> black -> black -> pre-fight screen. The old
        # code returned 'underway' on the black frames and never tapped prep.
        dev = FakeDevice(self, ['DR_BOSS', 'DR_BLACK', 'DR_BLACK', 'DR_PREP',
                                'DR_PREP', 'DR_FIGHT'])
        self.assertTrue(dr.start_fight(1))
        self.assertEqual(dev.taps, [dr.BOSS_TAP, dr.PREP_TAP])

    def test_endless_black_is_not_a_fight(self):
        dev = FakeDevice(self, ['DR_BOSS'] + ['DR_BLACK'] * 10 + ['DR_BLACK'] * 6)
        self.assertFalse(dr.start_fight(1))
        self.assertEqual(dev.taps, [dr.BOSS_TAP])



class R2ReadyRearm(unittest.TestCase):
    """A8a-2: a ready screen that keeps standing gets one Battle re-tap."""

    def setUp(self):
        p = mock.patch.object(dr, '_dismiss_taps', 0)
        p.start()
        self.addCleanup(p.stop)

    def test_prep_standing_is_retapped_once(self):
        dev = FakeDevice(self, ['DR_PREP'] * 3 + ['DR_FIGHT', 'DR_ENDED'])
        img = dr.wait_for_fight_end('dr_f1', 150)
        self.assertTrue(dr.is_battle_ended(img))
        self.assertEqual(dev.taps, [dr.PREP_TAP])

    def test_only_one_rearm(self):
        dev = FakeDevice(self, ['DR_BOSS'] * 6 + ['DR_ENDED'])
        dr.wait_for_fight_end('dr_f1', 150)
        self.assertEqual(dev.taps, [dr.BOSS_TAP])

    def test_ready_after_a_seen_fight_is_not_retapped(self):
        dev = FakeDevice(self, ['DR_FIGHT', 'DR_BOSS', 'DR_BOSS', 'DR_BOSS', 'DR_ENDED'])
        dr.wait_for_fight_end('dr_f1', 150)
        self.assertEqual(dev.taps, [])




class R4DimVsTransition(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(dr, '_dismiss_taps', 0)
        p.start()
        self.addCleanup(p.stop)

    def test_probes(self):
        self.assertTrue(dr._dim_probes(frame('DR_DIM')))
        self.assertFalse(dr._dim_probes(frame('DR_TRANSITION')))   # old: True
        self.assertFalse(dr.is_fight(frame('DR_DIM')))             # a popup is no fight marker

    def test_transition_is_not_a_fight_end(self):
        # fight-start transition, then the fight, then the end card
        dev = FakeDevice(self, ['DR_TRANSITION', 'DR_FIGHT', 'DR_ENDED'])
        img = dr.wait_for_fight_end('dr_f1', 150)
        self.assertTrue(dr.is_battle_ended(img))

    def test_dim_end_needs_the_debounce_shot(self):
        dev = FakeDevice(self, ['DR_DIM', 'DR_FIGHT', 'DR_DIM', 'DR_DIM'])
        img = dr.wait_for_fight_end('dr_f1', 150)
        self.assertTrue(dr._dim_probes(img))
        self.assertEqual(len(dev.shots), 4)          # first dim was not confirmed



class R5BackToReadyMidFight(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(dr, '_dismiss_taps', 0)
        p.start()
        self.addCleanup(p.stop)

    def test_running_fight_is_waited_out(self):
        dev = FakeDevice(self, ['DR_FIGHT', 'DR_FIGHT', 'DR_ENDED', 'DR_BOSS'])
        self.assertTrue(dr.back_to_ready('dr_post1'))
        self.assertEqual(dev.taps, [dr.CARD_CLOSE])

    def test_more_than_four_unknowns_tolerated(self):
        dev = FakeDevice(self, ['UNKNOWN'] * 6 + ['DR_BOSS'])
        self.assertTrue(dr.back_to_ready('dr_post1'))      # old: gave up at 4
        self.assertEqual(dev.taps, [])


class StagePushCase(unittest.TestCase):
    """Runs afk_stage_push.main() on FakeDevice; OCR + wall log kept offline."""

    def run_sp(self, frames, *argv):
        dev = FakeDevice(self, frames)
        log = Path(__file__).resolve().parent / '.artifacts' / 'wall-report.test.log'
        log.parent.mkdir(exist_ok=True)
        for patch in (mock.patch.object(sp, 'ocr_text', lambda png: []),
                      mock.patch.object(sp, 'WALL_LOG', log),
                      mock.patch.object(sys, 'argv', ['afk_stage_push.py', *argv])):
            patch.start()
            self.addCleanup(patch.stop)
        return dev, sp.main()


class R3LauncherLoading(StagePushCase):
    def test_classifier(self):
        self.assertEqual(sp.classify_battle(frame('SP_LAUNCHER')), 'LAUNCHER')
        fight = frame('SP_BATTLE')
        fight.paste((170, 170, 170), (946, 110, 974, 138))   # bright search probe (fight UI)
        self.assertEqual(sp.classify_battle(fight), 'BATTLE')   # old gate: LAUNCHER
        self.assertEqual(sp.classify_battle(frame('SP_LOADING')), 'LOADING')

    def test_single_battle_through_a_loading_frame(self):
        # dark night fight reads LOADING: used to end as 'no victory (LOADING)'
        dev, rc = self.run_sp(['SP_PREP', 'SP_LOADING', 'SP_RESULT', 'SP_RESULT'])
        self.assertEqual(rc, 0)
        self.assertIn('battle 1: VICTORY', dev.out.getvalue())
        self.assertEqual(dev.taps, [sp.BATTLE_BTN])


if __name__ == '__main__':
    unittest.main()
