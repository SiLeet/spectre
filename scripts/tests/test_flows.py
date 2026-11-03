"""Offline state-machine tests: scripted frames in, exact tap log out."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402
import afk_normalize  # noqa: E402
from fake_vision import FakeDevice, frame  # noqa: E402


class SyntheticFrames(unittest.TestCase):
    def test_blank_matrix_classifies(self):
        for st in ('WORLD', 'PANEL', 'POPUP', 'UNKNOWN'):
            self.assertEqual(v.classify(frame(st)), st)


class Normalize(unittest.TestCase):
    def test_two_unknowns_then_world(self):
        dev = FakeDevice(self, ['UNKNOWN', 'UNKNOWN', 'WORLD'])
        self.assertEqual(afk_normalize.main(), 0)
        self.assertEqual(dev.taps, [v.BACK, v.BACK])

    def test_unknown_after_cap_fails(self):
        dev = FakeDevice(self, ['UNKNOWN'] * 5)
        self.assertEqual(afk_normalize.main(), 1)
        self.assertEqual(dev.taps, [v.BACK] * 4)
        self.assertEqual(dev.shots[-1], 'norm_final')
        self.assertIn('normalize final: UNKNOWN', dev.out.getvalue())

    def test_world_first_no_taps(self):
        dev = FakeDevice(self, ['WORLD'])
        self.assertEqual(afk_normalize.main(), 0)
        self.assertEqual(dev.taps, [])

    def test_panel_counts_as_normal(self):
        dev = FakeDevice(self, ['PANEL'])
        self.assertEqual(afk_normalize.main(), 0)
        self.assertEqual(dev.taps, [])


class LoginPopup(unittest.TestCase):
    def test_daily_rewards_ocr_claims(self):
        # norm_0 POPUP -> resolver shot (norm_pop0) -> after-claim WORLD -> norm_1 WORLD
        dev = FakeDevice(self, ['POPUP', 'POPUP', 'WORLD', 'WORLD'],
                         ocr={'norm_pop0': ['Esperia', 'Daily Rewards', 'Claim']})
        self.assertEqual(afk_normalize.main(), 0)
        self.assertEqual(dev.taps, [v.LOGIN_CLAIM])

    def test_rewards_card_after_claim_is_dismissed(self):
        dev = FakeDevice(self, ['POPUP', 'POPUP', 'POPUP', 'WORLD', 'WORLD'],
                         ocr={'norm_pop0': ['Esperia Monthly']})
        self.assertEqual(afk_normalize.main(), 0)
        self.assertEqual(dev.taps, [v.LOGIN_CLAIM, v.BACK])

    def test_unrecognised_popup_gets_back_not_claim(self):
        dev = FakeDevice(self, ['POPUP', 'POPUP', 'WORLD'], ocr={'norm_pop0': ['Store', 'Buy']})
        self.assertEqual(afk_normalize.main(), 0)
        self.assertEqual(dev.taps, [v.BACK])
        self.assertNotIn(v.LOGIN_CLAIM, dev.taps)


class ClaimFlow(unittest.TestCase):
    def run_main(self, *argv):
        with mock.patch.object(sys, 'argv', ['afk_claim_vision.py', *argv]):
            return v.main()

    def test_happy_path(self):
        # initial WORLD -> panel -> chest popup -> claim popup persists -> panel
        dev = FakeDevice(self, ['WORLD', 'PANEL', 'POPUP', 'POPUP', 'PANEL'])
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(dev.taps, [v.GROUND, v.AFK_PROGRESS, v.CHEST, v.CLAIM, v.CLAIM, v.BACK])
        self.assertEqual(dev.shots, ['r1_0_initial', 'r1_1_panel', 'r1_3_chest',
                                     'r1_4_after', 'r1_4b_retry'])

    def test_unknown_screen_refuses_to_tap(self):
        dev = FakeDevice(self, ['UNKNOWN'])
        self.assertEqual(self.run_main(), 1)
        self.assertEqual(dev.taps, [])

    def test_nothing_claimable(self):
        dev = FakeDevice(self, ['PANEL', 'PANEL', 'PANEL'])
        self.assertEqual(self.run_main(), 4)
        self.assertEqual(dev.taps, [v.CHEST, v.CHEST])

    def test_login_popup_claimed_then_chest(self):
        # initial POPUP: resolver (r1_1a_popup + _after) -> recover PANEL -> chest -> claim
        dev = FakeDevice(self, ['POPUP', 'POPUP', 'PANEL', 'PANEL', 'POPUP', 'PANEL'],
                         ocr={'r1_1a_popup': ['Daily Rewards']})
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(dev.taps, [v.LOGIN_CLAIM, v.CHEST, v.CLAIM, v.BACK])

    def test_dry_run_world_taps_nothing(self):
        dev = FakeDevice(self, ['WORLD'])
        self.assertEqual(self.run_main('--dry-run'), 0)
        self.assertEqual(dev.taps, [])


if __name__ == '__main__':
    unittest.main()
