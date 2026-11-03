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


if __name__ == '__main__':
    unittest.main()
