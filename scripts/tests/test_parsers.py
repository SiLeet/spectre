"""Parser unit tests: OCR text -> stage / power / hero level.

Guards the '74' vs '74,986' collision class of misparses. Fixture lines are
real WinRT OCR output from .spectre/wall-report.log (sp_prep frames) unless
marked synthetic.
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import afk_claim_vision as v  # noqa: E402
import afk_hero_level as hl  # noqa: E402
import afk_stage_push as sp  # noqa: E402

ARTIFACTS = Path(__file__).resolve().parent / '.artifacts'

# real: prep screen, stage 254, team power 74,986 (wall-report.log)
PREP_254 = ['57,997 v', 'AFK stage 254', '? 100', 'l?vl. 99', 'Lvl.99',
            'Lvl. 80 Lvl. 90', 'Lvl.80 LvL80', 'Auto Battle', 'Records',
            '74,986', 'LvL99', 'Battle']
# real: same screen, power line lost by OCR
PREP_254_NO_POWER = ['AFK stage 254 (D', 'ELVI 99', 'Lv199', 'LvL99',
                     'O- Lv180 Lv1.90', 'Auto Battle', 'Records', 'Battle']
# real: defeat card, no stage/power text at all
DEFEAT = ['4 Battle Advice +-', 'Level Ub', 'Hero Level Mega Boost', 'Power Up',
          'Requesting Chain AFK Proxy Battle', 'A. AFK (1/1)',
          'Try out a tank hero!', 'Retry']


class ParseStage(unittest.TestCase):
    def test_real_prep(self):
        self.assertEqual(sp.parse_stage(PREP_254), 254)
        self.assertEqual(sp.parse_stage(PREP_254_NO_POWER), 254)

    def test_short_form_at_line_end(self):
        self.assertEqual(sp.parse_stage(['AFK 249']), 249)

    def test_stage_line_beats_earlier_loose_match(self):
        self.assertEqual(sp.parse_stage(['AFK 12', 'AFK Stage 250']), 250)

    def test_quest_counter_is_not_a_stage(self):
        self.assertIsNone(sp.parse_stage(['Complete AFK 2 quests']))

    def test_none_without_text(self):
        self.assertIsNone(sp.parse_stage(DEFEAT))
        self.assertIsNone(sp.parse_stage([]))


class ParsePower(unittest.TestCase):
    def test_real_prep_comma_number(self):
        self.assertEqual(sp.parse_power(PREP_254), 74986)

    def test_afk_panel_number_next_to_battle(self):   # synthetic, panel layout
        self.assertEqual(sp.parse_power(['0 74451', 'Battle']), 74451)

    def test_nearest_number_wins_over_team_power(self):
        self.assertEqual(sp.parse_power(['99,999', 'Records', '74,986', 'Battle']), 74986)

    def test_auto_battle_is_not_an_anchor(self):
        self.assertIsNone(sp.parse_power(['74,986', 'Auto Battle']))

    def test_out_of_range_and_level_numbers_ignored(self):
        self.assertIsNone(sp.parse_power(PREP_254_NO_POWER))
        self.assertIsNone(sp.parse_power(['4,999', 'Battle']))
        self.assertIsNone(sp.parse_power(['5,000,001', 'Battle']))

    def test_none_without_anchor(self):
        self.assertIsNone(sp.parse_power(DEFEAT))
        self.assertIsNone(sp.parse_power(['74,986']))


class ReadLevel(unittest.TestCase):
    def test_badge_forms(self):
        self.assertEqual(hl.read_level(['Lv. 74']), 74)
        self.assertEqual(hl.read_level(['Lvl.99']), 99)
        self.assertEqual(hl.read_level(['Lv.74']), 74)

    def test_power_line_alone_is_not_a_level(self):
        self.assertIsNone(hl.read_level(['74,986']))
        self.assertIsNone(hl.read_level([]))

    def test_first_badge_wins(self):
        self.assertEqual(hl.read_level(['Ascend', 'Lv. 74', 'Lv. 80']), 74)

    # --- review 2026-11-03 F2 (fixed in T58 / A7a-3) ------------------------
    def test_ocr_case_variants(self):
        self.assertEqual(hl.read_level(['LvL99']), 99)
        self.assertEqual(hl.read_level(['LV.74']), 74)
        self.assertEqual(hl.read_level(['Lvl 84']), 84)          # real, hl_840_0

    def test_glued_number_never_yields_a_wrong_level(self):
        self.assertIn(hl.read_level(['Lv.74986']), (74, None))

    def test_no_word_boundary_no_level(self):
        self.assertIsNone(hl.read_level(['ELVI 99']))             # real OCR junk


# real WinRT OCR of .spectre/hl_entry.png / hl_710_0b.png / hl_840_1.png
HALL = ['?esonatingH I', 'Resonance Level: 80', 'Hands of Resonance', 'Resonance Heroes',
        'v! 80', 'Equipment', 'Artifacts', 'Resonating Guild', 'Mys Battle Modes Hall']
DETAIL_74 = ['endar?,', 'Dragonslayer Knight', 'Gwynet,LB', 'Affinih', 'Skin Not Pinned',
             'Lvl. 74', 'Reach Leeendarv+ to unlock Hero Focus.', 'Level', '11613 0',
             "' Hands of Resonance must be within 10 levels ofeach Other."]
DETAIL_NO_BADGE = ['Epic', 'Knight of Valor', 'Estrilda', '84', '3/4', 'Affinity Not',
                   'Head ear', 'Level', '10,169 0',
                   'Hands of Resonance must be within 10 levels of each Other.']


class HeroScreens(unittest.TestCase):
    def test_hall_is_not_a_detail(self):
        self.assertTrue(hl.is_hall(HALL))
        self.assertFalse(hl.is_detail(HALL))
        self.assertIsNone(hl.read_level(HALL))

    def test_detail(self):
        self.assertTrue(hl.is_detail(DETAIL_74))
        self.assertEqual(hl.read_level(DETAIL_74), 74)

    def test_detail_without_badge_is_unreadable(self):
        self.assertTrue(hl.is_detail(DETAIL_NO_BADGE))
        self.assertIsNone(hl.read_level(DETAIL_NO_BADGE))


class OcrLines(unittest.TestCase):
    """ocr_lines / ocr_text post-processing on a canned OCR stdout."""

    def setUp(self):
        ARTIFACTS.mkdir(exist_ok=True)
        (ARTIFACTS / 'ocr_fixture.png').write_bytes(b'')
        self.tmp = mock.patch.object(v, 'TMP', ARTIFACTS)
        self.tmp.start()
        self.addCleanup(self.tmp.stop)

    @staticmethod
    def done(stdout: str, rc: int = 0) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout)

    def test_strips_and_drops_blank_lines(self):
        with mock.patch.object(v.subprocess, 'run',
                               return_value=self.done('  AFK Stage 254 \r\n\n\t\n Battle\n')) as run:
            self.assertEqual(v.ocr_lines('ocr_fixture'), ['AFK Stage 254', 'Battle'])
        cmd = run.call_args.args[0]
        self.assertIsInstance(cmd, list)                     # no shell=True
        self.assertNotIn('shell', run.call_args.kwargs)
        self.assertEqual(cmd[cmd.index('-Path') + 1], str(ARTIFACTS / 'ocr_fixture.png'))

    def test_missing_png_skips_ocr(self):
        with mock.patch.object(v.subprocess, 'run') as run:
            self.assertEqual(v.ocr_lines('no_such_frame'), [])
        run.assert_not_called()

    def test_ocr_failure_is_empty(self):
        for exc in (subprocess.TimeoutExpired('ps', 20), OSError('no powershell')):
            with mock.patch.object(v.subprocess, 'run', side_effect=exc):
                self.assertEqual(v.ocr_lines('ocr_fixture'), [])

    def test_parsers_on_ocr_lines_output(self):
        out = '\n'.join(PREP_254) + '\n'
        with mock.patch.object(v.subprocess, 'run', return_value=self.done(out)):
            lines = v.ocr_lines('ocr_fixture')
        self.assertEqual((sp.parse_stage(lines), sp.parse_power(lines)), (254, 74986))

    def test_stage_push_ocr_text_rc_nonzero_is_empty(self):
        with mock.patch.object(v.subprocess, 'run', return_value=self.done('AFK Stage 1', rc=1)):
            self.assertEqual(sp.ocr_text(ARTIFACTS / 'ocr_fixture.png'), [])


if __name__ == '__main__':
    unittest.main()
