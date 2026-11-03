"""T69 Dura's Trials v1: entry, floor/token OCR, first clear, sweep to 0, clean aborts."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402
import afk_duras as du  # noqa: E402
import afk_stage_push as sp  # noqa: E402
from fake_vision import FakeDevice  # noqa: E402

ARTIFACTS = Path(__file__).resolve().parent / '.artifacts'
ENTRY = ['WORLD', 'BATTLE_MODES', 'UNKNOWN']          # open_battle_modes + du_entry


def screen(floor: int, tokens: int, cleared: bool) -> list[str]:
    return ["Dura's Trials", f'Floor {floor}', 'Sweep' if cleared else 'Challenge', f'{tokens}/6']


class Duras(unittest.TestCase):
    def run_duras(self, frames, ocr, *argv):
        ARTIFACTS.mkdir(exist_ok=True)
        marker = ARTIFACTS / 'duras-last.txt'
        marker.unlink(missing_ok=True)
        dev = FakeDevice(self, frames, ocr=ocr)
        p = mock.patch.object(du, 'MARKER', marker)
        p.start()
        self.addCleanup(p.stop)
        return dev, du.main(list(argv)), marker

    def test_sweep_until_zero(self):
        ocr = {'du_entry': screen(12, 3, True), 'du_after_sweep_1': screen(12, 2, True),
               'du_after_sweep_2': screen(12, 1, True), 'du_after_sweep_3': screen(12, 0, True)}
        dev, rc, marker = self.run_duras(ENTRY + ['UNKNOWN'] * 6, ocr)
        self.assertEqual(rc, 0)
        self.assertEqual(dev.taps, [v.GROUND, du.DURAS_CARD] + [du.SWEEP_BTN, du.RESULT_CLOSE] * 3)
        self.assertTrue(marker.exists())
        self.assertIn('tokens: 0 — done for today', dev.out.getvalue())

    def test_first_clear_defeat_refund_then_win_then_sweep(self):
        ocr = {'du_entry': screen(13, 2, False),
               'du_after_fight_1': screen(13, 2, False),                 # defeat: token refunded
               'du_after_fight_2': screen(13, 2, True),                  # cleared -> Sweep appears
               'du_after_sweep_1': screen(13, 1, True), 'du_after_sweep_2': screen(13, 0, True)}
        frames = ENTRY + ['UNKNOWN', 'SP_DEFEAT_CARD', 'UNKNOWN',       # fight 1: prep, defeat, back
                          'UNKNOWN', 'SP_VICTORY_CARD', 'UNKNOWN',      # fight 2: prep, victory, back
                          'UNKNOWN'] * 1 + ['UNKNOWN'] * 3              # sweeps: 2 x (sweep, after)
        dev, rc, marker = self.run_duras(frames, ocr)
        self.assertEqual(rc, 0, dev.out.getvalue())
        fight = [du.CHALLENGE_BTN, du.FIGHT_BTN, du.RESULT_CLOSE]
        self.assertEqual(dev.taps[2:], fight * 2 + [du.SWEEP_BTN, du.RESULT_CLOSE] * 2)
        self.assertIn('defeat (token refunded)', dev.out.getvalue())

    def test_first_clear_fails_bounded_tokens_stay(self):
        ocr = {'du_entry': screen(14, 3, False), **{f'du_after_fight_{i}': screen(14, 3, False)
                                                     for i in (1, 2, 3)}}
        frames = ENTRY + ['UNKNOWN', 'SP_DEFEAT_CARD', 'UNKNOWN'] * du.MAX_FIGHTS
        dev, rc, marker = self.run_duras(frames, ocr)
        self.assertEqual(rc, 4)
        # only the fights, no sweep (SWEEP_BTN shares the Challenge spot -> count taps)
        self.assertEqual(len(dev.taps), 2 + 3 * du.MAX_FIGHTS)
        self.assertIn('stopping (tokens stay)', dev.out.getvalue())
        self.assertFalse(marker.exists())

    def test_unknown_screen_aborts_without_taps(self):
        dev, rc, _ = self.run_duras(ENTRY, {'du_entry': ['Battle Modes', 'Arena']})
        self.assertEqual(rc, 1)
        self.assertEqual(dev.taps, [v.GROUND, du.DURAS_CARD])

    def test_sweep_count_mismatch_stops(self):
        ocr = {'du_entry': screen(12, 3, True), 'du_after_sweep_1': screen(12, 3, True)}
        dev, rc, marker = self.run_duras(ENTRY + ['UNKNOWN'] * 2, ocr)
        self.assertEqual(rc, 1)
        self.assertEqual(dev.taps.count(du.SWEEP_BTN), 1)
        self.assertFalse(marker.exists())

    def test_sweep_dialog_is_cancelled(self):
        dev, rc, _ = self.run_duras(ENTRY + ['DIALOG'], {'du_entry': screen(12, 3, True)})
        self.assertEqual(rc, 1)
        self.assertEqual(dev.taps[-2:], [du.SWEEP_BTN, v.CONFIRM_CANCEL])

    def test_dry_run_reads_only(self):
        dev, rc, _ = self.run_duras(ENTRY, {'du_entry': screen(12, 6, True)}, '--dry-run')
        self.assertEqual(rc, 0)
        self.assertEqual(dev.taps, [v.GROUND, du.DURAS_CARD])
        self.assertIn('highest floor 12, cleared=True, tokens 6/6', dev.out.getvalue())


class Parsers(unittest.TestCase):
    def test_tokens(self):
        self.assertEqual(du.parse_tokens(['Tokens: 3/6']), 3)
        self.assertEqual(du.parse_tokens(['0 / 6']), 0)
        self.assertIsNone(du.parse_tokens(['12/60', 'Floor 3']))

    def test_floor_and_cleared(self):
        self.assertEqual(du.parse_floor(['Floor 9', 'Floor12', 'floor 11']), 12)
        self.assertIsNone(du.parse_floor(['Challenge']))
        self.assertTrue(du.is_cleared(['SWEEP x1']))
        self.assertFalse(du.is_cleared(['Challenge']))

    def test_result_cards_classify(self):
        from fake_vision import frame
        self.assertEqual(sp.classify_battle(frame('SP_DEFEAT_CARD')), 'DEFEAT')
        self.assertEqual(sp.classify_battle(frame('SP_VICTORY_CARD')), 'RESULT')


if __name__ == '__main__':
    unittest.main()
