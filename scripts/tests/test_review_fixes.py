"""Regression tests for the 2026-11-03 scripts review fixes (T58).

F<n> = position of the finding in docs/reviews/2026-11-03-scripts-review.md.
Real-frame cases need the local .spectre/ frames and skip when they are gone.
"""
from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_arena as ar  # noqa: E402
import afk_claim_vision as v  # noqa: E402
import afk_dailies as dl  # noqa: E402
import afk_hero_level as hl  # noqa: E402
import afk_stage_push as sp  # noqa: E402
from fake_vision import FakeDevice, frame  # noqa: E402
from make_frame_manifest import REPO, load_rgb  # noqa: E402
import importlib.util  # noqa: E402

_gs = importlib.util.spec_from_file_location('afk_daily_gift', REPO / 'scripts' / 'afk-daily-gift.py')
gift = importlib.util.module_from_spec(_gs)
_gs.loader.exec_module(gift)
from test_parsers import DETAIL_74, DETAIL_NO_BADGE, HALL  # noqa: E402


def real(relpath: str):
    path = REPO / '.spectre' / relpath
    if not path.exists():
        raise unittest.SkipTest(f'frame missing: .spectre/{relpath}')
    return load_rgb(path)


class F1ConfirmDialog(unittest.TestCase):
    """One purchase/confirm detector for arena + stage push."""

    DIALOGS = ('screens/arena_debug1.png',            # 'Spend diamonds' (arena, row 729)
               'shots-49936/sp_auto_3.png',           # 'Turn off Auto Battle' (row 711)
               'shots-49936/sp_auto_244.png')         # same dialog, row 729
    NOT_DIALOGS = ('shots/arena_p1_pre.png',          # Select Opponent (old false positive)
                   'game_boot.png', 'shots-33404/dr_rec1_4.png')

    def test_real_dialogs_detected(self):
        for rel in self.DIALOGS:
            with self.subTest(rel):
                img = real(rel)
                self.assertTrue(v.is_confirm_dialog(img))
                self.assertEqual(sp.classify_battle(img), 'CONFIRM')

    def test_lookalikes_rejected(self):
        for rel in self.NOT_DIALOGS:
            with self.subTest(rel):
                img = real(rel)
                self.assertFalse(v.is_confirm_dialog(img))
                self.assertNotEqual(sp.classify_battle(img), 'CONFIRM')

    def test_synthetic(self):
        self.assertTrue(v.is_confirm_dialog(frame('DIALOG')))
        self.assertEqual(sp.classify_battle(frame('DIALOG')), 'CONFIRM')
        for st in ('WORLD', 'PANEL', 'POPUP', 'UNKNOWN', 'BATTLE_MODES'):
            self.assertFalse(v.is_confirm_dialog(frame(st)), st)

    def test_arena_cancels_purchase_dialog(self):
        # world -> battle modes -> lobby -> select -> pre-fight shot = dialog
        dev = FakeDevice(self, ['WORLD', 'BATTLE_MODES', 'ARENA_LOBBY', 'UNKNOWN', 'DIALOG'],
                         also=(ar,))
        with mock.patch.object(sys, 'argv', ['afk_arena.py']):
            self.assertEqual(ar.main(), 0)
        self.assertEqual(dev.taps, [v.GROUND, ar.ARENA_CARD, ar.CHALLENGE, v.CONFIRM_CANCEL])
        self.assertIn('purchase dialog cancelled', dev.out.getvalue())



class F6BattleModes(unittest.TestCase):
    """is_battle_modes must not accept other cream screens."""

    MENU = ('shots/arena_0_initial.png', 'world4.png', 'shots-48392/dr_hub.png')
    LOOKALIKES = ('hall.png', 'shots-17856/dl_final.png',          # main menu
                  'shots/arena_1_after.png', 'shots/t28_fight_end1.png',  # defeat / battle ended
                  'shots-4844/sp_0_initial.png',                    # victory card
                  'shots-40256/sp_wait.png')                        # loading tip

    def test_menu(self):
        for rel in self.MENU:
            with self.subTest(rel):
                self.assertTrue(v.is_battle_modes(real(rel)))

    def test_lookalikes(self):
        for rel in self.LOOKALIKES:
            with self.subTest(rel):
                self.assertFalse(v.is_battle_modes(real(rel)))

    def test_synthetic(self):
        self.assertTrue(v.is_battle_modes(frame('BATTLE_MODES')))
        cream = frame('BATTLE_MODES')
        cream.paste((240, 235, 225), (480, 900, 1180, 960))   # tab icons gone
        self.assertFalse(v.is_battle_modes(cream))



class HeroCase(unittest.TestCase):
    def run_hl(self, frames, ocr, hands=(710, 840)):
        dev = FakeDevice(self, frames, ocr=ocr)
        keys = []
        for patch in (mock.patch.object(hl, 'key', lambda code, wait=1.5: dev.taps.append(('key', code))),
                      mock.patch.object(hl, 'HAND_XS', list(hands)),
                      mock.patch.object(sys, 'argv', ['afk_hero_level.py', '--target', '90'])):
            patch.start()
            self.addCleanup(patch.stop)
        return dev, hl.main()


class F2HeroLevel(HeroCase):
    """Hall re-verify between hands + exit 1 on any failed hand."""

    def test_hall_lost_is_reentered_from_town(self):
        lvl95 = ['Affinity', 'Lvl. 95']
        dev, rc = self.run_hl(['UNKNOWN', 'UNKNOWN', 'WORLD', 'UNKNOWN', 'UNKNOWN'],
                              {'hl_entry': HALL, 'hl_710_0': lvl95, 'hl_hall_840': ['Battle Modes'],
                               'hl_hall_840_reenter': HALL, 'hl_840_0': lvl95})
        self.assertEqual(rc, 0)
        self.assertEqual(dev.taps, [hl.HALL_BTN, (710, hl.HANDS_Y), ('key', 4),
                                    hl.HALL_BTN, (840, hl.HANDS_Y), ('key', 4)])

    def test_unknown_screen_between_hands_stops_without_blind_tap(self):
        dev, rc = self.run_hl(['UNKNOWN', 'UNKNOWN', 'UNKNOWN'],
                              {'hl_entry': HALL, 'hl_710_0': ['Affinity', 'Lvl. 95']})
        self.assertEqual(rc, 1)
        self.assertEqual(dev.taps, [hl.HALL_BTN, (710, hl.HANDS_Y), ('key', 4)])

    def test_unreadable_hand_exits_1(self):
        dev, rc = self.run_hl(['UNKNOWN', 'UNKNOWN', 'UNKNOWN', 'UNKNOWN'],
                              {'hl_entry': HALL, 'hl_710_0': DETAIL_NO_BADGE,
                               'hl_hall_840': HALL, 'hl_840_0': ['Affinity', 'Lvl. 95']})
        self.assertEqual(rc, 1)
        self.assertIn('with failures', dev.out.getvalue())



class F5ArenaExitCodes(unittest.TestCase):
    """A run that fought nothing must exit 1 (watch.sh burns the marker on 0)."""
    TO_SELECT = ['WORLD', 'BATTLE_MODES', 'ARENA_LOBBY', 'UNKNOWN']

    def run_arena(self, frames):
        dev = FakeDevice(self, frames, also=(ar,))
        with mock.patch.object(sys, 'argv', ['afk_arena.py']):
            return dev, ar.main()

    def test_stuck_chain_exits_1(self):
        dev, rc = self.run_arena(self.TO_SELECT + ['UNKNOWN'] + ['UNKNOWN'] * 6 + ['UNKNOWN'])
        self.assertEqual(rc, 1)
        # T66 zombie guard: two unchanged steps -> one card dismiss, the second
        # stagnation ends the chain early (was: 6 identical opponent taps)
        self.assertEqual(dev.taps[3:], [ar.OPPONENT_LEFT, ar.OPPONENT_LEFT, ar.CARD_DISMISS,
                                        ar.OPPONENT_LEFT, ar.OPPONENT_LEFT])

    def test_unchanged_screen_exits_1(self):
        dev, rc = self.run_arena(self.TO_SELECT + ['UNKNOWN', 'ARENA_PREP', 'UNKNOWN', 'UNKNOWN',
                                                   'UNKNOWN'])
        self.assertEqual(rc, 1)
        self.assertIn('screen unchanged', dev.out.getvalue())

    def test_fought_exits_0(self):
        dev, rc = self.run_arena(self.TO_SELECT + ['UNKNOWN', 'ARENA_PREP', 'UNKNOWN', 'ARENA_LOBBY',
                                                   'ARENA_LOBBY', 'BATTLE_MODES', 'WORLD'])
        self.assertEqual(rc, 0)
        self.assertIn('done: 1 arena fights driven', dev.out.getvalue())
        self.assertIn('exit: back at the world view', dev.out.getvalue())



class F19ArenaTapRc(unittest.TestCase):
    def setUp(self):
        for patch in (mock.patch('time.sleep'), mock.patch.object(sys, 'stdout', io.StringIO())):
            patch.start()
            self.addCleanup(patch.stop)

    def test_failed_tap_retried_once(self):
        with mock.patch.object(v, 'tap', side_effect=[RuntimeError('adb tap failed'), None]) as t:
            ar.tap(ar.CHALLENGE, 4.0)
        self.assertEqual(t.call_count, 2)

    def test_second_failure_raises(self):
        with mock.patch.object(v, 'tap', side_effect=RuntimeError('adb tap failed')):
            with self.assertRaises(RuntimeError):
                ar.tap(ar.CHALLENGE)



class F16IdleSeconds(unittest.TestCase):
    def test_tick_delta_wraps(self):
        self.assertEqual(v.tick_delta(5_000, 2_000), 3_000)
        # GetTickCount wrapped past 2**32 after the last input
        self.assertEqual(v.tick_delta(1_000, 0xFFFFFF00), 1_256)
        # past 2**31 ms uptime (where the old c_long went negative)
        self.assertEqual(v.tick_delta(2**31 + 10_000, 2**31 - 5_000), 15_000)

    @unittest.skipUnless(sys.platform == 'win32', 'GetLastInputInfo is Windows-only')
    def test_idle_seconds_non_negative(self):
        self.assertGreaterEqual(v.idle_seconds(), 0)



class F7WorldNeedsChip(unittest.TestCase):
    """WORLD requires the lit AFK chip; dim lookalikes stay UNKNOWN (no taps)."""

    def test_real_non_world_frames(self):
        for rel in ('shots-24812/dr_start.png',          # 'Use Diamond' Cancel/Confirm dialog
                    'shots-14672/bm_0.png',              # store bundle popup
                    'ar4.png',                           # Battle Modes menu
                    'shots-30096/sp_auto_19.png'):       # running battle
            with self.subTest(rel):
                self.assertNotEqual(v.classify(real(rel)), 'WORLD')

    def test_real_world_day_and_night(self):
        for rel in ('after_claim.png', 'shots-34228/t44_world.png', 'shots-20408/sp_0_initial.png'):
            with self.subTest(rel):
                self.assertEqual(v.classify(real(rel)), 'WORLD')

    def test_dim_popup_inside_the_old_cliff(self):
        # review case: dimmed popup, no bright claim bar, lb-lg = -5 (old: WORLD)
        img = frame('UNKNOWN')
        img.paste((60, 60, 60), (0, 0, 1920, 1080))
        img.paste((70, 66, 62), (460, 996, 488, 1024))   # back arrow
        img.paste((75, 71, 67), (550, 996, 578, 1024))   # right of it
        self.assertEqual(v.classify(img), 'UNKNOWN')

    def test_synthetic_world_without_chip(self):
        img = frame('WORLD')
        img.paste((62, 70, 50), (40, 1016, 80, 1056))
        self.assertEqual(v.classify(img), 'UNKNOWN')



class F8DailiesImportable(unittest.TestCase):
    def test_run_dailies_without_main_globals(self):
        # used to die with AttributeError on the ARGS global when imported
        dev = FakeDevice(self, ['UNKNOWN'])
        self.assertEqual(dl.run_dailies(0), 1)          # unknown screen -> refuse
        self.assertIn('memory preflight skipped', dev.out.getvalue())
        self.assertEqual(dev.taps, [])



class F15SharedChestClaim(unittest.TestCase):
    def test_dailies_uses_claim_round(self):
        dev = FakeDevice(self, ['WORLD', 'PANEL', 'POPUP', 'PANEL'])
        self.assertTrue(dl.afk_chest_claim())
        self.assertEqual(dev.taps, [v.GROUND, v.AFK_PROGRESS, v.CHEST, v.CLAIM, v.BACK])
        self.assertEqual(dev.shots[0], 'dl_afk_0_initial')

    def test_unconfirmed_claim_is_failure(self):
        # claim popup persists through the retry: old copy returned True
        dev = FakeDevice(self, ['PANEL', 'POPUP', 'POPUP', 'POPUP'])
        self.assertFalse(dl.afk_chest_claim())
        self.assertEqual(dev.taps, [v.CHEST, v.CLAIM, v.CLAIM])

    def test_nothing_claimable_is_ok(self):
        FakeDevice(self, ['PANEL', 'PANEL', 'PANEL'])
        self.assertTrue(dl.afk_chest_claim())



class F9QuestTabs(unittest.TestCase):
    def test_failed_tab_reopens_panel_before_next_tab(self):
        dev = FakeDevice(self, ['QUESTS', 'QUESTS',                # homestead
                                'UNKNOWN', 'MENU', 'QUESTS',       # daily fails -> reopen
                                'QUESTS', 'QUESTS', 'QUESTS', 'QUESTS', 'QUESTS', 'QUESTS'])
        self.assertTrue(dl.claim_quest_tabs())
        self.assertEqual(dev.taps, [dl.QUICK_CLAIM, dl.DAILY_TAB, v.BACK, dl.QUESTS_ICON,
                                    dl.LUCKY_FLIP_TAB, dl.QUICK_CLAIM, dl.GROWTH_TAB, dl.QUICK_CLAIM,
                                    dl.GUILD_TAB, dl.QUICK_CLAIM])

    def test_panel_lost_stops(self):
        dev = FakeDevice(self, ['QUESTS', 'QUESTS', 'UNKNOWN'] + ['UNKNOWN'] * 5)
        self.assertFalse(dl.claim_quest_tabs())
        self.assertNotIn(dl.LUCKY_FLIP_TAB, dev.taps)

    def test_open_menu_closes_popup_with_back(self):
        dev = FakeDevice(self, ['POPUP', 'MENU'])
        self.assertTrue(dl.open_menu())
        self.assertEqual(dev.taps, [v.BACK])



class F10GiftEntry(unittest.TestCase):
    def run_gift(self, frames):
        dev = FakeDevice(self, frames)
        with mock.patch.object(sys, 'argv', ['afk-daily-gift.py']):
            return dev, gift.main()

    def test_entry_tap_retried_once(self):
        dev, rc = self.run_gift(['WORLD', 'GIFT_ENTRY',                  # init, cam_0
                                 'WORLD', 'WORLD', 'WORLD',              # panel never opened
                                 'GIFT_ENTRY', 'EVENTS']                 # entry still there -> retry
                                + ['EVENTS'] * 7 + ['WORLD'])           # 7 rows (no green badge), close
        self.assertEqual(rc, 0)
        self.assertEqual(dev.taps, [gift.LOGIN_REWARDS, gift.LOGIN_REWARDS, v.BACK])

    def test_entry_not_found_is_warn_not_done(self):
        dev, rc = self.run_gift(['WORLD'] + ['WORLD'] * 9)
        self.assertEqual(rc, 3)
        self.assertNotIn(gift.LOGIN_REWARDS, dev.taps)



class F11GiftClaimSignal(unittest.TestCase):
    def test_signals(self):
        dim = frame('EVENTS')
        dim.paste((10, 10, 10), (180, 250, 220, 290))
        self.assertEqual(gift.claim_signal(dim), 'dimmed')
        self.assertEqual(gift.claim_signal(frame('POPUP')), 'classify POPUP')
        self.assertIsNone(gift.claim_signal(frame('EVENTS')))

    def test_late_popup_caught_by_reshot(self):
        green_row = frame('EVENTS')
        green_row.paste((60, 180, 60), (700, 240, 740, 280))     # badge at (720,260)
        dev = FakeDevice(self, ['WORLD', 'GIFT_ENTRY', 'EVENTS', green_row,
                                'EVENTS', 'POPUP',                 # after-tap: still panel, then popup
                                'EVENTS', 'WORLD'])                # dismissed, close
        with mock.patch.object(sys, 'argv', ['afk-daily-gift.py']):
            self.assertEqual(gift.main(), 0)
        self.assertIn('claimed row y=260 (Rewards Obtained, classify POPUP)', dev.out.getvalue())
        self.assertEqual(dev.taps, [gift.LOGIN_REWARDS, (gift.ROW_X, 260), (700, 500), v.BACK])



class F12HeroExhaustion(HeroCase):
    """Exhaustion needs two unchanged x10 taps in a row."""

    def test_missed_tap_is_not_exhaustion(self):
        dev, rc = self.run_hl(['UNKNOWN'] * 5,
                              {'hl_entry': HALL, 'hl_710_0': ['Affinity', 'Lvl. 80'],
                               'hl_710_check1': ['Lvl. 80'], 'hl_710_check2': ['Lvl. 90'],
                               'hl_710_1': ['Affinity', 'Lvl. 90']}, hands=(710,))
        self.assertEqual(rc, 0)
        self.assertNotIn('resources exhausted', dev.out.getvalue())
        self.assertEqual(dev.taps, [hl.HALL_BTN, (710, hl.HANDS_Y), hl.LEVEL_X10, hl.LEVEL_X10, ('key', 4)])

    def test_two_unchanged_taps_stop_the_run(self):
        dev, rc = self.run_hl(['UNKNOWN'] * 4,
                              {'hl_entry': HALL, 'hl_710_0': ['Affinity', 'Lvl. 80'],
                               'hl_710_check1': ['Lvl. 80'], 'hl_710_check2': ['Lvl. 80']},
                              hands=(710, 840))
        self.assertEqual(rc, 0)
        self.assertIn('resources exhausted', dev.out.getvalue())
        self.assertNotIn((840, hl.HANDS_Y), dev.taps)



class F20HeroPurchaseDialog(HeroCase):
    def test_dialog_after_x10_is_cancelled_and_stops(self):
        dev, rc = self.run_hl(['UNKNOWN', 'UNKNOWN', 'DIALOG'],
                              {'hl_entry': HALL, 'hl_710_0': ['Affinity', 'Lvl. 80']},
                              hands=(710, 840))
        self.assertEqual(rc, 0)
        self.assertEqual(dev.taps, [hl.HALL_BTN, (710, hl.HANDS_Y), hl.LEVEL_X10,
                                    v.CONFIRM_CANCEL, ('key', 4)])
        self.assertIn('purchase/confirm dialog after x10', dev.out.getvalue())



class F26ClaimVisionPlumbing(unittest.TestCase):
    def test_swipe_rc_raises(self):
        failed = __import__('subprocess').CompletedProcess([], 1, b'', b'device offline')
        with mock.patch.object(v, 'adb', return_value=failed), mock.patch('time.sleep'):
            with self.assertRaises(RuntimeError):
                v.swipe(400, 700, 0, 700)

    def test_dump_timeout_is_none(self):
        import subprocess
        with mock.patch.object(v.subprocess, 'run', side_effect=subprocess.TimeoutExpired('spectre', 300)):
            self.assertIsNone(v.adb_exec_dump('1', '0x0', Path('x.bin')))

    def test_save_power_state_atomic(self):
        target = Path(__file__).resolve().parent / '.artifacts' / 'power-state.json'
        target.parent.mkdir(exist_ok=True)
        target.unlink(missing_ok=True)
        with mock.patch.object(v, 'POWER_STATE', target):
            v.save_power_state({'power': 259850})
            self.assertEqual(v.load_power_state()['power'], 259850)
        self.assertFalse(target.with_suffix('.tmp').exists())


class TGuardDriftGate(unittest.TestCase):
    """Drift gate in memory_preflight (2026-11-03 live fund): a heap-base
    change put garbage (108449240) at the anchored offset; the plain-read
    'ok' branch accepted it and overwrote the verified 259850 anchor."""

    STATE = {'offset': 1824824, 'width': 4, 'power': 259850,
             'pid': '1', 'base': '0x7964E0000000', 'revalidated': True}

    def pref(self, read_value, base='0x796590000000', relocate=None):
        target = Path(__file__).resolve().parent / '.artifacts' / 'power-state-drift.json'
        target.parent.mkdir(exist_ok=True)
        target.unlink(missing_ok=True)
        with mock.patch.object(v, 'POWER_STATE', target):
            v.save_power_state(dict(self.STATE))
            with mock.patch.object(v, 'read_power', return_value=read_value), \
                 mock.patch.object(v, 'revalidate_power_offset', return_value=relocate):
                status, val = v.memory_preflight('1', base)
            st = v.load_power_state()
        return status, val, st

    def test_garbage_in_range_is_not_accepted(self):
        status, val, st = self.pref(108449240, relocate=None)
        self.assertEqual((status, val), ('disabled', 108449240))
        self.assertEqual(st['power'], 259850)
        self.assertEqual(st['base'], '0x7964E0000000')

    def test_in_tolerance_read_updates_anchor(self):
        status, val, st = self.pref(265000, base='0x7964E0000000')
        self.assertEqual((status, val), ('ok', 265000))
        self.assertEqual(st['power'], 265000)
        self.assertEqual(st['base'], '0x7964E0000000')

    def test_relocation_result_is_stored(self):
        status, val, st = self.pref(108449240, relocate=(999, 4, 260100))
        self.assertEqual((status, val), ('ok', 260100))
        self.assertEqual((st['offset'], st['width'], st['power'], st['base']),
                         (999, 4, 260100, '0x796590000000'))



class F27NoBlindBackAfterPopup(unittest.TestCase):
    def test_popup_closed_onto_world_goes_straight_to_afk(self):
        # popup (not the login one) -> BACK -> WORLD: old code tapped BACK twice
        # on the world view (exit confirm) before the AFK chip
        dev = FakeDevice(self, ['POPUP', 'POPUP', 'WORLD', 'WORLD', 'PANEL', 'POPUP', 'PANEL'])
        self.assertEqual(v.claim_round('r1'), 0)
        self.assertEqual(dev.taps, [v.BACK, v.GROUND, v.AFK_PROGRESS, v.CHEST, v.CLAIM, v.BACK])

    def test_stuck_popup_refuses_after_reach_world_fails(self):
        dev = FakeDevice(self, ['POPUP', 'POPUP', 'POPUP'] + ['UNKNOWN'] * 7)
        self.assertEqual(v.claim_round('r1'), 1)
        self.assertNotIn(v.AFK_PROGRESS, dev.taps)



class F28DailiesDismiss(unittest.TestCase):
    def dimmed(self):
        img = frame('QUESTS')
        img.paste((5, 5, 5), (180, 250, 220, 290))
        return img

    def test_dismiss_verified(self):
        dev = FakeDevice(self, ['QUESTS'])
        dl.dismiss_popup('t')
        self.assertEqual(dev.taps, [dl.DISMISS])

    def test_dismiss_retried_once_then_warns(self):
        dev = FakeDevice(self, [self.dimmed(), self.dimmed()])
        dl.dismiss_popup('t')
        self.assertEqual(dev.taps, [dl.DISMISS, dl.DISMISS])
        self.assertIn('still dimmed', dev.out.getvalue())



class F29GiftSwipesOnScreen(unittest.TestCase):
    def test_pan_endpoints_clamped(self):
        dev = FakeDevice(self, ['WORLD'] * 9)
        self.assertFalse(gift.find_login_button())
        swipes = [t[1:] for t in dev.taps if t[0] == 'swipe']
        self.assertEqual(len(swipes), 8)
        for x1, y1, x2, y2, *_ in swipes:
            self.assertEqual((x1, y1), (400, 700))
            self.assertTrue(0 <= x2 <= 1919 and 0 <= y2 <= 1079, (x2, y2))



class F30GiftNoBlindDismiss(unittest.TestCase):
    def green_row(self):
        img = frame('EVENTS')
        img.paste((60, 180, 60), (700, 240, 740, 280))           # badge at (720,260)
        return img

    def run_rows(self, after_tap):
        dev = FakeDevice(self, ['WORLD', 'GIFT_ENTRY', 'EVENTS', self.green_row(),
                                after_tap, after_tap]                # after + re-shot
                         + ['EVENTS'] * 6 + ['WORLD'])
        with mock.patch.object(sys, 'argv', ['afk-daily-gift.py']):
            self.assertEqual(gift.main(), 0)
        return dev

    def test_panel_unchanged_no_tap(self):
        dev = self.run_rows(frame('EVENTS'))
        self.assertEqual(dev.taps, [gift.LOGIN_REWARDS, (gift.ROW_X, 260), v.BACK])

    def test_unknown_overlay_gets_back_not_blind_tap(self):
        dev = self.run_rows(frame('UNKNOWN'))
        self.assertNotIn((1500, 600), dev.taps)
        self.assertEqual(dev.taps, [gift.LOGIN_REWARDS, (gift.ROW_X, 260), v.BACK, v.BACK])



class PruneWiring(unittest.TestCase):
    """F16 wiring: main() must call the prune once per real run, not on --dry-run.

    FakeDevice stubs prune_shot_dirs with a no-op; this re-patches it into a
    spy on top, asserting the CALL (the prune itself is covered above)."""

    def _run_with_spy(self, frames, *argv):
        calls = []
        FakeDevice(self, frames)
        spy = mock.patch.object(v, 'prune_shot_dirs', lambda *a, **k: calls.append(1) or 0)
        spy.start()
        self.addCleanup(spy.stop)
        with mock.patch.object(sys, 'argv', ['afk_claim_vision.py', *argv]):
            rc = v.main()
        return rc, calls

    def test_prune_called_on_real_run(self):
        rc, calls = self._run_with_spy(['WORLD', 'PANEL', 'POPUP', 'POPUP', 'PANEL'])
        self.assertEqual(rc, 0)
        self.assertEqual(len(calls), 1, 'prune_shot_dirs must run once per real claim round')

    def test_prune_skipped_on_dry_run(self):
        rc, calls = self._run_with_spy(['WORLD'], '--dry-run')
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [])


class F16PruneToTrash(unittest.TestCase):
    def setUp(self):
        import os
        self.root = Path(__file__).resolve().parent / '.artifacts' / 'prune'
        self.root.mkdir(parents=True, exist_ok=True)
        for d in self.root.rglob('*'):                 # previous run's leftovers (test-owned dir)
            if d.is_file():
                d.unlink()
        for d in sorted(self.root.rglob('*'), reverse=True):
            d.rmdir()
        for i in range(5):
            d = self.root / f'shots-{i}'
            d.mkdir()
            (d / 'x.png').write_bytes(b'png')
            os.utime(d, (1_000 + i, 1_000 + i))      # shots-4 newest
        (self.root / 'trash').mkdir()
        (self.root / 'trash' / 'shots-1').mkdir()      # same pid from an earlier boot

    def test_moves_old_keeps_newest_and_current(self):
        with mock.patch.object(v, 'TMP', self.root / 'shots-0'):   # oldest, but this run's
            self.assertEqual(v.prune_shot_dirs(self.root, keep=2), 2)
        self.assertEqual(sorted(p.name for p in self.root.glob('shots-*')),
                         ['shots-0', 'shots-3', 'shots-4'])
        self.assertEqual(sorted(p.name for p in (self.root / 'trash').iterdir()),
                         ['shots-1', 'shots-1.1', 'shots-2'])
        self.assertEqual((self.root / 'trash' / 'shots-2' / 'x.png').read_bytes(), b'png')

    def test_nothing_to_move(self):
        with mock.patch.object(v, 'TMP', self.root / 'shots-0'):
            self.assertEqual(v.prune_shot_dirs(self.root, keep=30), 0)

    def test_aged_trash_is_deleted_fresh_trash_kept(self):
        import os
        aged = self.root / 'trash' / 'shots-77'
        aged.mkdir()
        os.utime(aged, (1_000, 1_000))                 # ~ancient
        fresh = self.root / 'trash' / 'shots-1'        # from setUp (now)
        with mock.patch.object(v, 'TMP', self.root / 'shots-0'):
            v.prune_shot_dirs(self.root, keep=30, trash_max_age_days=7)
        self.assertFalse(aged.exists())
        self.assertTrue(fresh.exists())


if __name__ == '__main__':
    unittest.main()
