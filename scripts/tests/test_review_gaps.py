"""T70: close the gaps the wave-4 reviewer's mutations found (tests only).

  a) dream world recovery: exactly 2 ladder cycles, then 'gave up' + exit 1
  b) arena: a purchase dialog INSIDE the fight chain -> 'DIALOG', one STOP line
  d) duras: sweep only with 'Sweep' on screen / Challenge dialog / no tokens
(c and e live in test_device_ensure_wiring.py / test_afk_daily_exit_code.py.)
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
import afk_duras as du  # noqa: E402
from fake_vision import FakeDevice  # noqa: E402

ARTIFACTS = Path(__file__).resolve().parent / '.artifacts'
CYCLE_SHOTS = 5         # escape ladder: resolver (+its own shot), back, ground, back2
CYCLE_TAPS = [v.BACK, v.GROUND, v.BACK, v.BACK]


class DreamTwoCycleBound(unittest.TestCase):
    def test_exactly_two_cycles_then_gave_up(self):
        frames = ['UNKNOWN'] + ['UNKNOWN'] * 4 + ['UNKNOWN'] * (2 * CYCLE_SHOTS + 1)
        dev = FakeDevice(self, frames)
        with mock.patch.object(dr, '_dismiss_taps', 0):
            self.assertEqual(dr.run(argparse.Namespace(fights=0, wait_fight=150)), 1)
        out = dev.out.getvalue()
        self.assertIn('ESCAPE: gave up after 2 cycle(s)', out)
        self.assertIn('escape 2/back2', out)
        self.assertNotIn('escape 3/', out)
        self.assertEqual(dev.frames, [])                     # one cycle less leaves frames
        self.assertEqual(dev.taps, CYCLE_TAPS * 2)


class ArenaChainDialog(unittest.TestCase):
    def test_advance_returns_dialog_and_cancels(self):
        dev = FakeDevice(self, ['DIALOG'], also=(ar,))
        self.assertEqual(ar.advance_to_fight('arena_f1'), 'DIALOG')
        self.assertEqual(dev.taps, [v.CONFIRM_CANCEL])

    def test_main_logs_one_stop_line(self):
        # lobby -> select -> pre-fight shot is clean -> step 0 of the chain is the dialog
        dev = FakeDevice(self, ['WORLD', 'BATTLE_MODES', 'ARENA_LOBBY', 'UNKNOWN', 'UNKNOWN',
                                'DIALOG'], also=(ar,))
        with mock.patch.object(sys, 'argv', ['afk_arena.py']):
            self.assertEqual(ar.main(), 0)
        self.assertEqual(dev.out.getvalue().count('STOP: purchase dialog during the fight chain'), 1)
        self.assertEqual(dev.taps[-1], v.CONFIRM_CANCEL)
        self.assertNotIn(ar.ARENA_BATTLE, dev.taps)


def screen(tokens: int, cleared: bool) -> list[str]:
    return ["Dura's Trials", 'Floor 12', 'Sweep' if cleared else 'Challenge', f'{tokens}/6']


class DurasPaths(unittest.TestCase):
    # T87: + du_menu_0, whose OCR must show 'dura' before the card tap
    ENTRY = ['WORLD', 'BATTLE_MODES', 'UNKNOWN', 'UNKNOWN']

    def run_duras(self, frames, ocr):
        ARTIFACTS.mkdir(exist_ok=True)
        marker = ARTIFACTS / 'duras-gaps-last.txt'
        marker.unlink(missing_ok=True)
        dev = FakeDevice(self, frames, ocr={'du_menu_0': ["Dura's Trials"], **ocr})
        p = mock.patch.object(du, 'MARKER', marker)
        p.start()
        self.addCleanup(p.stop)
        return dev, du.main([]), marker

    def test_sweep_stops_when_sweep_is_gone(self):
        dev, rc, marker = self.run_duras(self.ENTRY + ['UNKNOWN'] * 2,
                                         {'du_entry': screen(3, True),
                                          'du_after_sweep_1': screen(2, False)})
        self.assertEqual(rc, 1)
        self.assertEqual(dev.taps.count(du.SWEEP_BTN), 1)
        self.assertIn("no 'Sweep' on screen — not sweeping", dev.out.getvalue())
        self.assertFalse(marker.exists())

    def test_challenge_dialog_returns_without_fight(self):
        dev, rc, marker = self.run_duras(self.ENTRY + ['DIALOG'], {'du_entry': screen(2, False)})
        self.assertEqual(rc, 4)
        self.assertEqual(dev.taps[2:], [du.CHALLENGE_BTN, v.CONFIRM_CANCEL])
        self.assertNotIn(du.FIGHT_BTN, dev.taps)
        self.assertFalse(marker.exists())

    def test_no_tokens_uncleared_ends_cleanly(self):
        dev, rc, marker = self.run_duras(self.ENTRY, {'du_entry': screen(0, False)})
        self.assertEqual(rc, 0)
        self.assertEqual(dev.taps, [v.GROUND, du.DURAS_CARD])
        self.assertIn('no tokens left today', dev.out.getvalue())


if __name__ == '__main__':
    unittest.main()
