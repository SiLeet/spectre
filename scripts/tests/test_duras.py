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
# open_battle_modes + du_menu_0 + du_entry. T87: the card is tapped only once the menu OCR
# shows 'dura', so every flow fixture reads it on du_menu_0 (MENU, merged in run_duras)
ENTRY = ['WORLD', 'BATTLE_MODES', 'UNKNOWN', 'UNKNOWN']
MENU = {'du_menu_0': ['Legend Trial', "Dura's Trials"]}
SWIPE = ('swipe', *du.MENU_SWIPE, du.MENU_SWIPE_MS, 2.0)


def screen(floor: int, tokens: int, cleared: bool) -> list[str]:
    return ["Dura's Trials", f'Floor {floor}', 'Sweep' if cleared else 'Challenge', f'{tokens}/6']


class Duras(unittest.TestCase):
    def run_duras(self, frames, ocr, *argv, region=None):
        ARTIFACTS.mkdir(exist_ok=True)
        marker = ARTIFACTS / 'duras-last.txt'
        marker.unlink(missing_ok=True)
        dev = FakeDevice(self, frames, ocr={**MENU, **ocr})
        if region is not None:          # card-grid crop OCR (the live path: full frame reads '00')
            def ocr_region(name, box):
                self.assertEqual(box, du.MENU_BOX)
                return list(region.get(name, []))
            p = mock.patch.object(v, 'ocr_region', ocr_region)
            p.start()
            self.addCleanup(p.stop)
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
        frames = ENTRY + ['SP_PREP', 'SP_DEFEAT_CARD', 'UNKNOWN',       # fight 1: prep, defeat, back
                          'SP_PREP', 'SP_VICTORY_CARD', 'UNKNOWN',      # fight 2: prep, victory, back
                          'UNKNOWN'] * 1 + ['UNKNOWN'] * 3              # sweeps: 2 x (sweep, after)
        dev, rc, marker = self.run_duras(frames, ocr)
        self.assertEqual(rc, 0, dev.out.getvalue())
        fight = [du.CHALLENGE_BTN, du.FIGHT_BTN, du.RESULT_CLOSE]
        self.assertEqual(dev.taps[2:], fight * 2 + [du.SWEEP_BTN, du.RESULT_CLOSE] * 2)
        self.assertIn('defeat (token refunded)', dev.out.getvalue())

    def test_first_clear_fails_bounded_tokens_stay(self):
        ocr = {'du_entry': screen(14, 3, False), **{f'du_after_fight_{i}': screen(14, 3, False)
                                                     for i in (1, 2, 3)}}
        frames = ENTRY + ['SP_PREP', 'SP_DEFEAT_CARD', 'UNKNOWN'] * du.MAX_FIGHTS
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

    # --- T84 hardening: stuck != 'not cleared' (the Daily wrapper marks the day on rc 4) ---
    def test_no_result_card_is_stuck_not_done(self):
        p = mock.patch.object(du, 'FIGHT_POLLS', 2)
        p.start()
        self.addCleanup(p.stop)
        dev, rc, marker = self.run_duras(ENTRY + ['SP_PREP', 'UNKNOWN', 'UNKNOWN'],
                                         {'du_entry': screen(13, 2, False)})
        self.assertEqual(rc, 1)
        self.assertIn('no result card after the fight', dev.out.getvalue())
        self.assertNotIn(du.RESULT_CLOSE, dev.taps)
        self.assertFalse(marker.exists())

    def test_unknown_screen_after_fight_is_stuck_not_done(self):
        dev, rc, marker = self.run_duras(ENTRY + ['SP_PREP', 'SP_VICTORY_CARD', 'UNKNOWN'],
                                         {'du_entry': screen(13, 2, False),
                                          'du_after_fight_1': ['Battle Modes']})
        self.assertEqual(rc, 1)
        self.assertEqual(dev.taps[2:], [du.CHALLENGE_BTN, du.FIGHT_BTN, du.RESULT_CLOSE])
        self.assertFalse(marker.exists())

    def test_no_prep_screen_after_challenge_never_taps_fight(self):
        dev, rc, marker = self.run_duras(ENTRY + ['UNKNOWN'], {'du_entry': screen(13, 2, False)})
        self.assertEqual(rc, 1)
        self.assertEqual(dev.taps[2:], [du.CHALLENGE_BTN])
        self.assertNotIn(du.FIGHT_BTN, dev.taps)
        self.assertIn('team prep screen not recognised', dev.out.getvalue())
        self.assertFalse(marker.exists())

    def test_tap_lock_held_skips_without_taps(self):
        import _bot_lock
        p = mock.patch.object(_bot_lock, 'acquire', lambda *a, **k: False)
        p.start()
        self.addCleanup(p.stop)
        dev, rc, marker = self.run_duras([], {})
        self.assertEqual(rc, 7)
        self.assertEqual(dev.taps, [])
        self.assertIn('SKIP: tap lock held', dev.out.getvalue())
        self.assertFalse(marker.exists())

    def test_dry_run_reads_only(self):
        dev, rc, _ = self.run_duras(ENTRY, {'du_entry': screen(12, 6, True)}, '--dry-run')
        self.assertEqual(rc, 0)
        self.assertEqual(dev.taps, [v.GROUND, du.DURAS_CARD])
        self.assertIn('highest floor 12, cleared=True, tokens 6/6', dev.out.getvalue())

    # --- T87: Dura's missing from the Battle Modes menu (not unlocked) = soft rc 4 ---
    def test_card_found_after_swipes_is_not_tapped_blind(self):
        # review F3: DURAS_CARD is the unscrolled spot -> found below the fold = stop, rc 1
        frames = ['WORLD', 'BATTLE_MODES'] + ['UNKNOWN'] * 3                 # du_menu_0..2
        dev, rc, marker = self.run_duras(frames, {'du_menu_0': []},
                                         region={'du_menu_2': ['Arena', "Dura's Trials"]})
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual(dev.taps, [v.GROUND, SWIPE, SWIPE])
        self.assertEqual(SWIPE[1:5], (960, 675, 960, 392))
        self.assertIn('seen only after 2 swipe(s)', dev.out.getvalue())
        self.assertFalse(marker.exists())

    def test_not_in_menu_after_max_swipes_is_soft_4(self):
        frames = ['WORLD', 'BATTLE_MODES'] + ['UNKNOWN'] * (du.MENU_SWIPES + 1)
        dev, rc, marker = self.run_duras(frames, {'du_menu_0': []}, region={
            'du_menu_0': ['AFK Stage Dream Realm Arena', 'Legend Trial', 'X Coming Soon']})
        self.assertEqual(rc, 4)
        self.assertEqual(dev.taps, [v.GROUND] + [SWIPE] * du.MENU_SWIPES)
        self.assertNotIn(du.DURAS_CARD, dev.taps)
        self.assertIn("Dura's currently not available", dev.out.getvalue())
        self.assertFalse(marker.exists())     # the Daily wrapper marks the day on rc 4

    def test_menu_ocr_empty_is_stuck_not_done(self):
        # review F2: OCR failure (ocr_png -> []) must not mark the day via rc 4
        frames = ['WORLD', 'BATTLE_MODES'] + ['UNKNOWN'] * (du.MENU_SWIPES + 1)
        dev, rc, marker = self.run_duras(frames, {'du_menu_0': []}, region={})
        self.assertEqual(rc, 1)
        self.assertNotIn(du.DURAS_CARD, dev.taps)
        self.assertIn('menu OCR read no card name', dev.out.getvalue())
        self.assertFalse(marker.exists())

    def test_coming_soon_is_soft_4(self):
        # review F1: live OCR never merges 'Coming Soon' with a card name; a locked card's
        # tap opens nothing, so the menu is still there on du_entry
        dev, rc, marker = self.run_duras(['WORLD', 'BATTLE_MODES', 'UNKNOWN', 'BATTLE_MODES'],
                                         {'du_menu_0': ["Dura's Trials", 'X Coming Soon']})
        self.assertEqual(rc, 4)
        self.assertEqual(dev.taps, [v.GROUND, du.DURAS_CARD])
        self.assertIn("not available yet (Coming Soon), skipping", dev.out.getvalue())
        self.assertFalse(marker.exists())

    def test_battle_modes_not_open_stays_1(self):
        dev, rc, marker = self.run_duras(['WORLD'] + ['UNKNOWN'] * 5, {})
        self.assertEqual(rc, 1)
        self.assertEqual(dev.taps, [v.GROUND] + [v.BATTLE_MODES_BTN] * 4)
        self.assertIn('Battle Modes did not open', dev.out.getvalue())
        self.assertFalse(marker.exists())


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
