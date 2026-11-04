"""Offline state-machine tests: scripted frames in, exact tap log out."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402
import afk_hero_level as hl  # noqa: E402
import afk_normalize  # noqa: E402
from fake_vision import FakeDevice, frame  # noqa: E402

K = ('key', 4)      # T97: keyevent BACK (v.back)


class SyntheticFrames(unittest.TestCase):
    def test_blank_matrix_classifies(self):
        for st in ('WORLD', 'PANEL', 'POPUP', 'UNKNOWN'):
            self.assertEqual(v.classify(frame(st)), st)

    def test_new_panel_palette(self):
        self.assertEqual(v.classify(frame('PANEL_NEW')), 'PANEL')
        # light back on cream alone is hero hall/dailies too: never a blind CHEST tap
        self.assertEqual(v.classify(frame('CREAM_BACK')), 'UNKNOWN')


class Normalize(unittest.TestCase):
    def test_two_unknowns_then_world(self):
        dev = FakeDevice(self, ['UNKNOWN', 'UNKNOWN', 'WORLD'])
        self.assertEqual(afk_normalize.main(), 0)
        self.assertEqual(dev.taps, [K, K])

    def test_unknown_after_cap_fails(self):
        dev = FakeDevice(self, ['UNKNOWN'] * 5)
        self.assertEqual(afk_normalize.main(), 1)
        self.assertEqual(dev.taps, [K] * 4)
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
        self.assertEqual(dev.taps, [K])
        self.assertNotIn(v.LOGIN_CLAIM, dev.taps)


class ClaimFlow(unittest.TestCase):
    def run_main(self, *argv):
        with mock.patch.object(sys, 'argv', ['afk_claim_vision.py', *argv]):
            return v.main()

    def test_happy_path(self):
        # initial WORLD -> panel -> chest popup -> claim popup persists -> panel
        dev = FakeDevice(self, ['WORLD', 'PANEL', 'POPUP', 'POPUP', 'PANEL'])
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(dev.taps, [v.GROUND, v.AFK_PROGRESS, v.CHEST, v.CLAIM, v.CLAIM, K])
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
        self.assertEqual(dev.taps, [v.LOGIN_CLAIM, v.CHEST, v.CLAIM, K])

    def test_dry_run_world_taps_nothing(self):
        dev = FakeDevice(self, ['WORLD'])
        self.assertEqual(self.run_main('--dry-run'), 0)
        self.assertEqual(dev.taps, [])


class HeroLevelEntry(unittest.TestCase):
    """afk_hero_level runs on the shared claim_vision helpers (T48)."""

    # T101: enter_hall shoots 'hl_start' first; every hall tap is gated on a WORLD frame
    def test_hall_not_open_aborts_after_bounded_tries(self):
        # town stays town: HALL_TRIES taps (plain, then the T97b retry chain), then exit 1
        dev = FakeDevice(self, ['WORLD'] * (1 + hl.HALL_TRIES), ocr={'hl_entry': ['Battle Modes']})
        with mock.patch.object(sys, 'argv', ['afk_hero_level.py']):
            self.assertEqual(hl.main(), 1)
        self.assertEqual(dev.taps, [hl.HALL_BTN, ('touchscreen', *hl.HALL_BTN), ('hold', *hl.HALL_BTN)])
        self.assertEqual(dev.shots, ['hl_start', 'hl_entry', 'hl_entry1', 'hl_entry2'])

    def test_unknown_screen_after_entry_tap_no_blind_retry(self):
        # an unknown screen after the tap gets bounded BACKs (reach_world), never a 2nd hall tap
        dev = FakeDevice(self, ['WORLD'] + ['UNKNOWN'] * 8, ocr={'hl_entry': []})
        with mock.patch.object(sys, 'argv', ['afk_hero_level.py']):
            self.assertEqual(hl.main(), 1)
        self.assertEqual(dev.taps, [hl.HALL_BTN] + [('key', 4)] * 6)

    def test_slow_hall_open_recovered(self):
        dev = FakeDevice(self, ['WORLD', 'WORLD', 'UNKNOWN'],
                         ocr={'hl_entry': [], 'hl_entry1': ['Resonance Level: 80']})
        with mock.patch.object(sys, 'argv', ['afk_hero_level.py', '--dry-run']):
            self.assertEqual(hl.main(), 0)
        self.assertIn('hall open: Resonance Level: 80', dev.out.getvalue())

    def test_dry_run_reads_hall_only(self):
        dev = FakeDevice(self, ['WORLD', 'UNKNOWN'], ocr={'hl_entry': ['Resonance Level: 80']})
        with mock.patch.object(sys, 'argv', ['afk_hero_level.py', '--dry-run']):
            self.assertEqual(hl.main(), 0)
        self.assertEqual(dev.taps, [hl.HALL_BTN])


if __name__ == '__main__':
    unittest.main()
