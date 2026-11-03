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
        self.assertEqual(dr.start_fight(1), 'started')
        self.assertEqual(dev.taps, [dr.BOSS_TAP, dr.PREP_TAP])

    def test_endless_black_is_not_a_fight(self):
        dev = FakeDevice(self, ['DR_BOSS'] + ['DR_BLACK'] * 10 + ['DR_BLACK'] * 6)
        self.assertIsNone(dr.start_fight(1))
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



class R6SpeedTapGated(unittest.TestCase):
    def test_tap_waits_for_the_fight_marker(self):
        dev = FakeDevice(self, ['DR_BLACK', 'DR_FIGHT'])
        self.assertTrue(dr.set_speed_x2(1))
        self.assertEqual(dev.taps, [dr.SPEED_X2])

    def test_no_marker_no_tap(self):
        for frames in (['DR_BLACK', 'DR_BLACK'], ['DR_PREP', 'DR_PREP']):
            dev = FakeDevice(self, frames)
            self.assertFalse(dr.set_speed_x2(1))
            self.assertEqual(dev.taps, [])



class R7Chances(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(dr, '_dismiss_taps', 0)
        p.start()
        self.addCleanup(p.stop)

    def test_parse(self):
        self.assertEqual(dr.parse_chances(['Elite Challenge', 'Chances: 5/7']), 5)
        self.assertEqual(dr.parse_chances(['Chance 0 / 7']), 0)
        self.assertIsNone(dr.parse_chances(['Battle']))

    def test_empty_pool_stops_cleanly(self):
        import argparse
        dev = FakeDevice(self, ['DR_BOSS', 'DR_BOSS', 'DR_BOSS', 'DR_BOSS'],
                         ocr={'dr_f1_chances': ['Chances: 0/7']})
        self.assertEqual(dr.run(argparse.Namespace(fights=7, wait_fight=150)), 0)
        self.assertEqual(dev.taps, [])
        self.assertIn('no Dream Realm chances left', dev.out.getvalue())

    def test_dim_dialog_after_tap_is_not_a_fight(self):
        dev = FakeDevice(self, ['DR_BOSS', 'DR_DIM', 'DR_DIM'])
        self.assertEqual(dr.start_fight(1), 'dialog')
        self.assertEqual(dev.taps, [dr.BOSS_TAP, v.BACK])



class R8PruneCalled(unittest.TestCase):
    def test_dream_main_prunes_except_dry_run(self):
        for argv, calls in ((['--fights', '1'], 1), (['--dry-run'], 0)):
            with mock.patch.object(v, 'prune_shot_dirs', return_value=3) as prune,                  mock.patch.object(dr, 'run', return_value=0),                  mock.patch.object(v, 'shot', return_value=frame('DR_BOSS')),                  mock.patch.object(sys, 'argv', ['afk_dream_realm.py', *argv]),                  mock.patch.object(sys, 'stdout', __import__('io').StringIO()):
                self.assertEqual(dr.main(), 0)
            self.assertEqual(prune.call_count, calls, argv)

    def test_stage_push_main_prunes(self):
        with mock.patch.object(v, 'prune_shot_dirs', return_value=0) as prune,              mock.patch.object(v, 'idle_seconds', return_value=0),              mock.patch.object(sys, 'argv', ['afk_stage_push.py', '--min-idle', '999']),              mock.patch.object(sys, 'stdout', __import__('io').StringIO()):
            self.assertEqual(sp.main(), 5)           # skipped right after the prune
        prune.assert_called_once()



class R13DreamReachWorld(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(dr, '_dismiss_taps', 0)
        p.start()
        self.addCleanup(p.stop)

    def test_unknown_is_polled_not_fatal(self):
        dev = FakeDevice(self, ['UNKNOWN', 'UNKNOWN', 'WORLD'])
        self.assertTrue(dr.reach_world('dr_world'))           # old: False at once
        self.assertEqual(dev.taps, [])

    def test_running_fight_waited_out(self):
        dev = FakeDevice(self, ['DR_FIGHT', 'DR_ENDED', 'WORLD', 'WORLD'])
        self.assertTrue(dr.reach_world('dr_world'))
        self.assertEqual(dev.taps, [dr.CARD_CLOSE])

    def test_persistent_unknown_still_refuses(self):
        dev = FakeDevice(self, ['UNKNOWN'] * 4)
        self.assertFalse(dr.reach_world('dr_world'))
        self.assertNotIn(v.BACK, dev.taps)


class StagePushCase(unittest.TestCase):
    """Runs afk_stage_push.main() on FakeDevice; OCR + wall log kept offline."""

    def run_sp(self, frames, *argv, ocr=lambda png: []):
        dev = FakeDevice(self, frames)
        log = Path(__file__).resolve().parent / '.artifacts' / 'wall-report.test.log'
        log.parent.mkdir(exist_ok=True)
        for patch in (mock.patch.object(sp, 'ocr_text', ocr),
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



class R9StaleResult(StagePushCase):
    def test_stale_card_is_no_win(self):
        dev, rc = self.run_sp(['SP_RESULT', 'SP_RESULT', 'SP_RESULT', 'SP_RESULT'])
        self.assertEqual(rc, 0)
        self.assertIn('not counted', dev.out.getvalue())
        self.assertIn('pushed 0/1', dev.out.getvalue())
        self.assertEqual(dev.taps, [sp.BATTLE_BTN, sp.BATTLE_BTN])

    def test_retap_then_real_fight_counts(self):
        dev, rc = self.run_sp(['SP_RESULT', 'SP_RESULT', 'SP_BATTLE', 'SP_RESULT', 'SP_RESULT'])
        self.assertIn('pushed 1/1', dev.out.getvalue())



class R10PrepDebounce(StagePushCase):
    def test_rearmed_chain_is_not_the_wall(self):
        dev, rc = self.run_sp(['SP_PREP', 'SP_BATTLE',          # initial, auto started
                               'SP_PREP', 'SP_BATTLE',          # prep, but the chain re-armed
                               'SP_PREP', 'SP_PREP',            # prep that stays prep = wall
                               'SP_PREP'], '--auto')            # wall_report shot
        self.assertEqual(rc, 0)
        self.assertEqual(dev.frames, [])                        # old code stopped 3 frames early
        self.assertEqual(dev.out.getvalue().count('wall reached'), 1)
        self.assertEqual(dev.taps, [sp.AUTO_BATTLE_BTN, sp.SPEED_X2_BTN])

    def test_ambiguous_second_frame_gets_a_third_look(self):
        dev, rc = self.run_sp(['SP_PREP', 'SP_BATTLE', 'SP_PREP', 'UNKNOWN', 'SP_PREP',
                               'SP_PREP'], '--auto')
        self.assertIn('wall reached', dev.out.getvalue())
        self.assertIn('sp_auto_confirm2', dev.shots)



class R11TryShot(unittest.TestCase):
    def setUp(self):
        for patch in (mock.patch.object(sp, '_shot_fails', 0),
                      mock.patch.object(sys, 'stdout', __import__('io').StringIO())):
            patch.start()
            self.addCleanup(patch.stop)

    def test_hiccups_are_retried_with_backoff(self):
        img = frame('SP_PREP')
        with mock.patch.object(v, 'shot', side_effect=[RuntimeError('screencap failed'),
                                                       OSError('pipe'), img]),              mock.patch('time.sleep') as sleep:
            self.assertIs(sp.try_shot('x'), img)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [3.0, 3.0])

    def test_adb_down_exits_2_not_fatal(self):
        with mock.patch.object(v, 'shot', side_effect=RuntimeError('screencap failed')),              mock.patch.object(v, 'prune_shot_dirs', return_value=0),              mock.patch('time.sleep'),              mock.patch.object(sys, 'argv', ['afk_stage_push.py']):
            self.assertEqual(sp.main(), 2)
        self.assertIn('adb down', sys.stdout.getvalue())



class R12PopupFallback(StagePushCase):
    def test_level_popup_closed_via_centre(self):
        popup = ['Level Up!', 'Tap to close']
        dev, rc = self.run_sp(['SP_PREP', 'SP_BATTLE', 'UNKNOWN', 'SP_PREP', 'SP_PREP',
                               'SP_PREP'], '--auto',
                              ocr=lambda png: popup if 'sp_auto_' in str(png) and 'start'
                              not in str(png) and 'confirm' not in str(png) else [])
        self.assertEqual(rc, 0)
        self.assertEqual(dev.taps, [sp.AUTO_BATTLE_BTN, sp.SPEED_X2_BTN, (960, 540)])

    def test_one_recovery_before_abort(self):
        dev, rc = self.run_sp(['SP_PREP', 'SP_BATTLE'] + ['UNKNOWN'] * 30 + ['UNKNOWN'], '--auto')
        self.assertEqual(rc, 1)
        self.assertEqual(dev.taps, [sp.AUTO_BATTLE_BTN, sp.SPEED_X2_BTN, v.BACK, (960, 540)])

    def test_is_closable_popup(self):
        self.assertTrue(sp.is_closable_popup(['New Perk unlocked']))
        self.assertFalse(sp.is_closable_popup(['Leveling', 'Records']))
        self.assertFalse(sp.is_closable_popup([]))


if __name__ == '__main__':
    unittest.main()
