"""T93 Dream Realm 'Victory Rewards' overlay (live 2026-11-04 14:0x).

Closing the BATTLE ENDED card opened a tap-to-close 'Victory Rewards' overlay.
is_fight read it as a running fight (every probe dark, (960,540) L 84 so not
uniform-dark) -> 150 s wait, 'boss page not restored after fight'. normalize
then met it as UNKNOWN: its BACK closed the overlay, the next BACK landed on
the card's Replay button and restarted the fight (shots-69680/norm_0..final).
Real-frame cases skip when .spectre is gone.
"""
from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402
import afk_dream_realm as dr  # noqa: E402
import afk_normalize  # noqa: E402
from fake_vision import FakeDevice, frame  # noqa: E402

K = ('key', 4)      # T97: keyevent BACK (v.back)
from make_frame_manifest import REPO, load_rgb  # noqa: E402

OVERLAY = ('shots-72816/dr_post1_0.png', 'shots-69680/norm_0.png',
           'shots-72816/dr_f1_resolve_0.png')
FIGHT = ('shots-72816/dr_f1_w0.png', 'shots-72816/dr_f1_w1.png', 'shots-72816/dr_f1_w3.png')
CARD = ('shots-72816/dr_f1_w8.png', 'shots-69680/norm_1.png')
MENU = 'shots-58752/norm_1.png'        # main menu: matched the old 3-probe card tell
BOSS = 'shots-72816/dr_f1_chances.png'


def real(relpath: str):
    path = REPO / '.spectre' / relpath
    if not path.exists():
        raise unittest.SkipTest(f'frame missing: .spectre/{relpath}')
    return load_rgb(path)


class DreamCase(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(dr, '_dismiss_taps', 0)
        p.start()
        self.addCleanup(p.stop)


class RealFrames(DreamCase):
    def test_overlay_is_no_fight(self):
        for rel in OVERLAY:
            img = real(rel)
            with self.subTest(rel):
                self.assertTrue(dr.is_victory_rewards(img))
                self.assertFalse(dr.is_fight(img))                   # old: True
                self.assertFalse(dr.is_battle_ended(img))
                self.assertEqual(v.classify(img), 'UNKNOWN')

    def test_lookalikes_are_not_overlay(self):
        for rel in (*FIGHT, *CARD, MENU, BOSS):
            with self.subTest(rel):
                self.assertFalse(dr.is_victory_rewards(real(rel)))
        for rel in FIGHT:
            with self.subTest(rel):
                self.assertTrue(dr.is_fight(real(rel)))
        for rel in CARD:
            with self.subTest(rel):
                self.assertTrue(dr.is_battle_ended(real(rel)))
        self.assertFalse(dr.is_battle_ended(real(MENU)))              # old: True

    def test_post_fight_overlay_tapped_once(self):
        # old: is_fight -> wait_for_fight_end 150 s -> False
        dev = FakeDevice(self, [real(OVERLAY[0]), real(BOSS)])
        self.assertTrue(dr.back_to_ready('dr_post1'))
        self.assertEqual(dev.taps, [dr.CARD_CLOSE])

    def test_normalize_closes_overlay_then_card(self):
        # old: BACK, BACK -> the second BACK hit the card's Replay button
        dev = FakeDevice(self, [real(OVERLAY[1]), real(CARD[1]), 'WORLD'])
        self.assertEqual(afk_normalize.main(), 0)
        self.assertEqual(dev.taps, [dr.CARD_CLOSE, dr.CARD_CLOSE])


class Synthetic(DreamCase):
    def test_fake_overlay(self):
        img = frame('DR_VICTORY_REWARDS')
        self.assertTrue(dr.is_victory_rewards(img))
        self.assertFalse(dr.is_fight(img))
        self.assertEqual(v.classify(img), 'UNKNOWN')
        for st in ('DR_ENDED', 'DR_FIGHT', 'DR_BLACK', 'DR_DIM', 'DR_BOSS', 'DR_TRANSITION'):
            with self.subTest(st):
                self.assertFalse(dr.is_victory_rewards(frame(st)))

    def test_run_card_overlay_one_tap_boss(self):
        # dr_start, dr_pre1_0, chances, pre0 | after0_0, speed0, w0 | w1 card |
        # resolve_0 overlay | resolve_1 boss | dr_exit, dr_final
        dev = FakeDevice(self, ['DR_BOSS'] * 4 + ['DR_FIGHT'] * 3
                         + ['DR_ENDED', 'DR_VICTORY_REWARDS'] + ['DR_BOSS'] * 3)
        self.assertEqual(dr.run(argparse.Namespace(fights=1, wait_fight=150)), 0)
        self.assertEqual(dev.taps, [dr.BOSS_TAP, dr.SPEED_X2, dr.CARD_CLOSE,
                                    dr.CARD_CLOSE, K])
        self.assertIn('Victory Rewards overlay -> tap to close', dev.out.getvalue())

    def test_overlay_dismiss_is_bounded(self):
        dev = FakeDevice(self, ['DR_VICTORY_REWARDS'] * 2)
        self.assertIsNone(dr.resolve_end_states(frame('DR_VICTORY_REWARDS'), 'dr_f1_resolve'))
        self.assertEqual(dev.taps, [dr.CARD_CLOSE] * dr.VR_MAX_TAPS)

    def test_live_sequence_card_overlay_card_boss(self):
        # live: closing the overlay brought the card back (norm_0 -> norm_1)
        dev = FakeDevice(self, ['DR_VICTORY_REWARDS', 'DR_ENDED', 'DR_BOSS'])
        self.assertIsNotNone(dr.resolve_end_states(frame('DR_ENDED'), 'dr_f1_resolve'))
        self.assertEqual(dev.taps, [dr.CARD_CLOSE] * 3)

    def test_card_overlay_cycle_gives_up(self):
        dev = FakeDevice(self, ['DR_VICTORY_REWARDS', 'DR_ENDED'] * 4)
        self.assertIsNone(dr.resolve_end_states(frame('DR_ENDED'), 'dr_f1_resolve'))
        self.assertEqual(dev.taps, [dr.CARD_CLOSE] * 5)

    def test_normalize_prep_after_result_tap_keeps_prep_back(self):
        # the T91 once-guard must not depend on how many T93 taps came first
        dev = FakeDevice(self, ['DR_VICTORY_REWARDS', 'DR_PREP_GRID', 'DR_BOSS', 'WORLD'])
        self.assertEqual(afk_normalize.main(), 0)
        self.assertEqual(dev.taps, [dr.CARD_CLOSE, K, K])

    def test_normalize_overlay_card_world(self):
        dev = FakeDevice(self, ['DR_VICTORY_REWARDS', 'DR_ENDED', 'WORLD'])
        self.assertEqual(afk_normalize.main(), 0)
        self.assertEqual(dev.taps, [dr.CARD_CLOSE, dr.CARD_CLOSE])
        self.assertIn('Dream Realm result screen -> tap to close', dev.out.getvalue())

    def test_normalize_end_taps_bounded_never_back(self):
        dev = FakeDevice(self, ['DR_VICTORY_REWARDS'] * 4)
        self.assertEqual(afk_normalize.main(), 1)
        self.assertEqual(dev.taps, [dr.CARD_CLOSE] * afk_normalize.DR_END_TAPS)


if __name__ == '__main__':
    unittest.main()
