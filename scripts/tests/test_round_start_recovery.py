"""T94 round start on Dream Realm leftovers (live 2026-11-04, 4 discarded runs).

claim_round's initial path refused a leftover BATTLE ENDED card (UNKNOWN), and
the letterboxed boss page read POPUP (now6, shots-75220): its BACK left the
page into a black transition (r1_1b_recover), which it then refused. Now
v.recover_leftover spends <= RECOVER_BUDGET state-proven taps. Real-frame cases
skip when the frames are gone (now3..6 live in %TEMP%).
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
import afk_normalize  # noqa: E402
import afk_stage_push as sp  # noqa: E402
from fake_vision import FakeDevice, frame  # noqa: E402
from make_frame_manifest import REPO, load_rgb  # noqa: E402

K = ('key', 4)      # T97: keyevent BACK (v.back)

TEMP = Path.home() / 'AppData' / 'Local' / 'Temp'
BOSS = ('now6.png', 'shots-75220/r1_0_initial.png', 'shots-75220/r1_1a_popup.png',
        'shots-66808/dr_f1_chances.png',      # older Necrodrakon skin, 'Not Ranked'
        'livecheck/now.png')                  # King Croaker layout (plate further left)
INFO = 'now5.png'                             # boss page + Necrodrakon info card
CARD = ('now3.png', 'shots-68168/r1_0_initial.png')
UI_LESS = ('now4.png',
           'shots-82560/dr_f3_resolve_0.png')   # trash: 2.3 s later the boss page, no tap
BLACK = 'shots-75220/r1_1b_recover.png'       # 1.5 s after BACK on the boss page
BATTLE_MODES = 'shots-80660/norm_3.png'       # boss page BACK -> black -> this
LEVEL_UP = ('livecheck/aftertap.png', 'livecheck/c1.png')   # light the bar probes too
NOT_UI_LESS = ('shots-80660/norm_1.png',      # letterboxed boss mid-load
               'shots-69680/norm_2.png')      # fight intro camera, no HUD
CLAIM = ['PANEL', 'POPUP', 'PANEL']           # AFK panel, chest popup, after claim
CLAIM_TAPS = [v.GROUND, v.AFK_PROGRESS, v.CHEST, v.CLAIM, K]


def real(rel: str):
    path = TEMP / rel if rel.startswith('now') else REPO / '.spectre' / rel
    if not path.exists() and not rel.startswith('now'):
        path = REPO / '.spectre' / 'trash' / rel    # pruned dirs (as test_frame_regression)
    if not path.exists():
        raise unittest.SkipTest(f'frame missing: {path}')
    return load_rgb(path)


class RealFrames(unittest.TestCase):
    def test_boss_page_is_dr_boss(self):
        for rel in BOSS:
            img = real(rel)
            with self.subTest(rel):
                self.assertEqual(v.classify(img), 'DR_BOSS')      # old: POPUP / UNKNOWN (KC)
                self.assertTrue(dr.is_boss_page(img))
                self.assertGreater(v.lum(v.avg(img, v.DR_BOSS_BACK)), 200)   # tap on the plate

    def test_info_card_stays_popup(self):
        img = real(INFO)
        self.assertEqual(v.classify(img), 'POPUP')
        self.assertTrue(v.is_dr_boss(img))
        self.assertTrue(v.is_dr_info(img))

    def test_after_boss_back_is_black_not_boss(self):
        img = real(BLACK)
        self.assertEqual(v.classify(img), 'UNKNOWN')
        self.assertTrue(dr.is_uniform_dark(img))
        self.assertFalse(v.is_dr_boss(img))

    def test_result_card(self):
        for rel in CARD:
            img = real(rel)
            with self.subTest(rel):
                self.assertEqual(v.classify(img), 'UNKNOWN')
                self.assertTrue(dr.is_battle_ended(img))
                self.assertFalse(v.is_ui_less(img))

    def test_ui_less_transition(self):
        for rel in UI_LESS:
            img = real(rel)
            with self.subTest(rel):
                self.assertEqual(v.classify(img), 'UNKNOWN')
                self.assertTrue(v.is_ui_less(img))
                self.assertFalse(dr.is_uniform_dark(img))

    def test_lookalikes(self):
        for rel in LEVEL_UP:
            img = real(rel)
            with self.subTest(rel):
                self.assertTrue(dr.is_boss_page(img))             # bar probes alone match
                self.assertNotEqual(v.classify(img), 'DR_BOSS')
        for rel in NOT_UI_LESS:
            with self.subTest(rel):
                self.assertFalse(v.is_ui_less(real(rel)))
        self.assertTrue(v.is_battle_modes(real(BATTLE_MODES)))

    def test_stage_push_keeps_boss_page_popup(self):
        # review blocker: as DR_BOSS the page fell through to the green-button
        # rule (PREP) and stage push / Dura's tapped Battle on the Dream bar
        for rel in BOSS[:3]:
            img = real(rel)
            with self.subTest(rel):
                self.assertEqual(sp.classify_battle(img), 'POPUP')
        for argv in (['--auto'], ['--battles', '1']):
            with self.subTest(argv):
                dev = FakeDevice(self, [real(BOSS[0])] * 6)
                log = Path(__file__).resolve().parent / '.artifacts' / 'wall-report.test.log'
                log.parent.mkdir(exist_ok=True)
                with mock.patch.object(sp, 'ocr_text', lambda png: []),                         mock.patch.object(sp, 'WALL_LOG', log),                         mock.patch.object(sys, 'argv', ['afk_stage_push.py', *argv]):
                    self.assertEqual(sp.main(), 1)
                self.assertEqual(dev.taps, [])

    def test_live_sequence_card_transition_boss_world(self):
        frames = [real(r) for r in (CARD[0], UI_LESS[0], BOSS[0], BLACK, BATTLE_MODES)]
        dev = FakeDevice(self, frames + ['WORLD'] + CLAIM)
        self.assertEqual(v.claim_round('r1'), 0)                 # old: 1 at once
        self.assertEqual(dev.taps, [dr.CARD_CLOSE, K, K] + CLAIM_TAPS)


class ClaimRound(unittest.TestCase):
    def test_a_card_transition_boss_modes_world_claim(self):
        dev = FakeDevice(self, ['DR_ENDED', 'DR_UI_LESS', 'DR_BOSS_PAGE', 'DR_BLACK',
                                'BATTLE_MODES', 'WORLD'] + CLAIM)
        self.assertEqual(v.claim_round('r1'), 0)
        self.assertEqual(dev.taps, [dr.CARD_CLOSE, K, K] + CLAIM_TAPS)
        self.assertIn('after leftover recovery: WORLD', dev.out.getvalue())

    def test_a_transition_persists_one_neutral_tap(self):
        dev = FakeDevice(self, ['DR_ENDED', 'DR_UI_LESS', 'DR_UI_LESS', 'DR_BOSS_PAGE',
                                'WORLD'] + CLAIM)
        self.assertEqual(v.claim_round('r1'), 0)
        self.assertEqual(dev.taps, [dr.CARD_CLOSE, v.TRANSITION_TAP, K] + CLAIM_TAPS)

    def test_transition_with_text_gets_no_tap(self):
        dev = FakeDevice(self, ['DR_UI_LESS'] * (1 + v.RECOVER_WAITS),
                         ocr={f'r1_0w{n}': ['Tap to continue'] for n in range(1, 7)})
        self.assertEqual(v.claim_round('r1'), 1)
        self.assertEqual(dev.taps, [])

    def test_a_operator_chain_with_info_card(self):
        # card -> transition (waited out) -> page + info card -> page -> modes:
        # 3 counted taps, the Battle Modes BACK is outside the budget
        dev = FakeDevice(self, ['DR_ENDED', 'DR_UI_LESS', 'DR_BOSS_INFO', 'DR_BOSS_PAGE',
                                'DR_BLACK', 'BATTLE_MODES', 'WORLD'] + CLAIM)
        self.assertEqual(v.claim_round('r1'), 0)
        self.assertEqual(dev.taps, [dr.CARD_CLOSE, K, K, K]
                         + CLAIM_TAPS)

    def test_battle_modes_back_only_once(self):
        dev = FakeDevice(self, ['BATTLE_MODES', 'BATTLE_MODES'])
        self.assertEqual(v.claim_round('r1'), 1)
        self.assertEqual(dev.taps, [K])

    def test_b_info_card_boss_world_claim(self):
        self.assertEqual(v.classify(frame('DR_BOSS_INFO')), 'POPUP')
        self.assertEqual(v.classify(frame('DR_BOSS_PAGE')), 'DR_BOSS')
        dev = FakeDevice(self, ['DR_BOSS_INFO', 'DR_BOSS_PAGE', 'DR_BLACK', 'BATTLE_MODES',
                                'WORLD'] + CLAIM)
        self.assertEqual(v.claim_round('r1'), 0)                 # old: POPUP -> BACK -> refused
        self.assertEqual(dev.taps, [K, K, K] + CLAIM_TAPS)

    def test_c_budget_exhausted_no_fourth_tap(self):
        dev = FakeDevice(self, ['DR_ENDED'] * 4)
        self.assertEqual(v.claim_round('r1'), 1)
        self.assertEqual(dev.taps, [dr.CARD_CLOSE] * v.RECOVER_BUDGET)
        dev = FakeDevice(self, ['DR_ENDED', 'DR_UI_LESS', 'DR_UI_LESS', 'DR_BOSS_INFO',
                                'DR_BOSS_PAGE'])
        self.assertEqual(v.claim_round('r1'), 1)
        self.assertEqual(dev.taps, [dr.CARD_CLOSE, v.TRANSITION_TAP, K])

    def test_d_truly_unknown_refused_without_tap_or_wait(self):
        dev = FakeDevice(self, ['UNKNOWN'])
        self.assertEqual(v.claim_round('r1'), 1)
        self.assertEqual((dev.taps, dev.shots), ([], ['r1_0_initial']))

    def test_unknown_after_own_tap_is_waited_then_refused(self):
        dev = FakeDevice(self, ['DR_ENDED'] + ['UNKNOWN'] * (1 + v.RECOVER_WAITS))
        self.assertEqual(v.claim_round('r1'), 1)
        self.assertEqual(dev.taps, [dr.CARD_CLOSE])

    def test_black_waited_out_then_world(self):
        dev = FakeDevice(self, ['DR_BLACK', 'DR_BLACK', 'WORLD'] + CLAIM)
        self.assertEqual(v.claim_round('r1'), 0)
        self.assertEqual(dev.taps, CLAIM_TAPS)


class Normalize(unittest.TestCase):
    def test_boss_page_shared_recovery(self):
        dev = FakeDevice(self, ['DR_BOSS_PAGE', 'DR_BLACK', 'BATTLE_MODES', 'WORLD'])
        self.assertEqual(afk_normalize.main(), 0)                # old: BACK, blind BACK on black
        self.assertEqual(dev.taps, [K, K])

    def test_card_then_transition_then_boss(self):
        dev = FakeDevice(self, ['DR_ENDED', 'DR_UI_LESS', 'DR_BOSS_PAGE', 'WORLD'])
        self.assertEqual(afk_normalize.main(), 0)
        self.assertEqual(dev.taps, [dr.CARD_CLOSE, K])

    def test_card_info_page_shares_one_budget(self):
        # review: the T93 card tap counts against the helper's budget
        dev = FakeDevice(self, ['DR_ENDED', 'DR_BOSS_INFO', 'DR_BOSS_PAGE', 'DR_BLACK',
                                'BATTLE_MODES', 'WORLD'])
        self.assertEqual(afk_normalize.main(), 0)
        self.assertEqual(dev.taps, [dr.CARD_CLOSE, K, K, K])
        dev = FakeDevice(self, ['DR_ENDED', 'DR_ENDED', 'DR_BOSS_INFO', 'DR_BOSS_PAGE'])
        self.assertEqual(afk_normalize.main(), 1)                # 3 taps, no 4th
        self.assertEqual(dev.taps, [dr.CARD_CLOSE, dr.CARD_CLOSE, K])
        dev = FakeDevice(self, ['DR_PREP_GRID', 'DR_BOSS_INFO', 'DR_BOSS_PAGE', 'DR_BOSS_PAGE'])
        self.assertEqual(afk_normalize.main(), 1)
        self.assertEqual(dev.taps, [K, K, K])

    def test_black_then_unknown_is_waited_out(self):
        dev = FakeDevice(self, ['DR_BLACK', 'UNKNOWN', 'WORLD'])
        self.assertEqual(afk_normalize.main(), 0)                # old: 2 BACKs, rc 0
        self.assertEqual(dev.taps, [])

    def test_black_then_login_popup_is_resolved(self):
        # review: the helper ending on a non-Dream POPUP hands back to normalize
        dev = FakeDevice(self, ['DR_BLACK', 'POPUP', 'POPUP', 'POPUP', 'POPUP', 'POPUP', 'WORLD'],
                         ocr={'norm_pop1': ['Esperia Monthly']})
        self.assertEqual(afk_normalize.main(), 0)                # WT before: rc 1, no tap
        self.assertEqual(dev.taps, [v.LOGIN_CLAIM, v.BACK])   # rewards card: stays a tap

    def test_budget_exhausted_fails(self):
        dev = FakeDevice(self, ['DR_BOSS_PAGE'] * 4)
        self.assertEqual(afk_normalize.main(), 1)
        self.assertEqual(dev.taps, [K] * v.RECOVER_BUDGET)


if __name__ == '__main__':
    unittest.main()
