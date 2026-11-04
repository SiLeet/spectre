"""T97b tap-mode chain (live 2026-11-04 ~16:00: every 'input tap' dead, manual ones
too; 'input keyevent 4' always worked): TAP_MODE command building, AFK_TAP_MODE,
getevent -pl parsing + sendevent commands, discovery failure, sticky mode."""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_arena as ar  # noqa: E402
import afk_claim_vision as v  # noqa: E402
from fake_vision import DeadTapDevice  # noqa: E402

# synthetic, LIVE: capture the real one (`adb shell getevent -pl` on Pie64)
GETEVENT_B = """\
add device 1: /dev/input/event3
  name:     "BlueStacks Virtual Touch"
  events:
    KEY (0001): BTN_TOUCH
    ABS (0003): ABS_MT_SLOT           : value 0, min 0, max 9, fuzz 0, flat 0, resolution 0
                ABS_MT_TRACKING_ID    : value 0, min 0, max 65535, fuzz 0, flat 0, resolution 0
                ABS_MT_POSITION_X     : value 0, min 0, max 32767, fuzz 0, flat 0, resolution 0
                ABS_MT_POSITION_Y     : value 0, min 0, max 32767, fuzz 0, flat 0, resolution 0
  input props:
    INPUT_PROP_DIRECT
add device 2: /dev/input/event0
  name:     "Power Button"
  events:
    KEY (0001): KEY_POWER
  input props:
    <none>
"""
GETEVENT_A = """\
add device 1: /dev/input/event0
  name:     "Power Button"
  events:
    KEY (0001): KEY_POWER
add device 2: /dev/input/event1
  name:     "virtio_input_multi_touch"
  events:
    ABS (0003): ABS_MT_POSITION_X     : value 0, min 0, max 1919, fuzz 0, flat 0, resolution 0
                ABS_MT_POSITION_Y     : value 0, min 0, max 1079, fuzz 0, flat 0, resolution 0
"""


def cp(out: str = '', rc: int = 0):
    return subprocess.CompletedProcess([], rc, out.encode(), b'')


class TapModeState(unittest.TestCase):
    def setUp(self):
        for name, val in (('TAP_MODE', 'tap'), ('_TAP_DEAD', set()), ('_SENDEVENT', None)):
            p = mock.patch.object(v, name, val)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch('time.sleep')
        p.start()
        self.addCleanup(p.stop)


class Commands(TapModeState):
    def test_tap_mode_default_keeps_pre_t97b_argv(self):
        with mock.patch.object(v, 'adb', return_value=cp()) as adb:
            v.tap((300, 250), 0)
        adb.assert_called_once_with('shell', 'input', 'tap', '300', '250')
        self.assertEqual(v.tap_seq([(300, 250, 0.8)], dry=True), 'input tap 300 250 && sleep 0.8')

    def test_touchscreen_mode(self):
        v.TAP_MODE = 'touchscreen'
        with mock.patch.object(v, 'adb', return_value=cp()) as adb:
            v.tap((300, 250), 0)
            v.tap_hold((845, 782), wait=0)
        self.assertEqual(adb.call_args_list, [
            mock.call('shell', 'input', 'touchscreen', 'tap', '300', '250'),
            mock.call('shell', 'input', 'touchscreen', 'swipe', '845', '782', '845', '782', '120')])
        self.assertEqual(v.tap_seq([(1, 2, 0), (3, 4, 1)], dry=True),
                         'input touchscreen tap 1 2 && input touchscreen tap 3 4 && sleep 1')

    def test_sendevent_mode(self):
        v.TAP_MODE, v._SENDEVENT = 'sendevent', dict(v.parse_getevent(GETEVENT_A), root=False)
        with mock.patch.object(v, 'adb', return_value=cp()) as adb:
            v.tap((960, 540), 0)
            v.tap_hold((960, 540), wait=0)
        tap_line = ' '.join(adb.call_args_list[0].args[1:])
        self.assertEqual(tap_line, ' && '.join(v.sendevent_cmds(v._SENDEVENT, 960, 540)))
        self.assertIn('sleep 0.12', ' '.join(adb.call_args_list[1].args))
        self.assertTrue(v.tap_seq([(960, 540, 0)], dry=True).startswith('sendevent /dev/input/event1 3 53 960'))
        v._SENDEVENT['root'] = True
        self.assertTrue(v._tap_cmd(1, 2).startswith('su -c "sendevent '))

    def test_tap_mode_failure_still_raises(self):
        with mock.patch.object(v, 'adb', return_value=cp(rc=1)), self.assertRaises(RuntimeError):
            v.tap((1, 2), 0, mode='touchscreen')

    def test_env_override(self):
        for env, want in (('touchscreen', 'touchscreen'), ('sendevent', 'sendevent'), ('bogus', 'tap')):
            with mock.patch.dict(os.environ, {'AFK_TAP_MODE': env}), mock.patch('sys.stdout'):
                self.assertEqual(v._env_tap_mode(), want)
        with mock.patch.dict(os.environ, clear=True):
            self.assertEqual(v._env_tap_mode(), 'tap')


class Sendevent(TapModeState):
    def test_parse_protocol_b(self):
        dev = v.parse_getevent(GETEVENT_B)
        self.assertEqual(dev, {'path': '/dev/input/event3', 'x': (0, 32767), 'y': (0, 32767),
                               'tid': True, 'btn': True, 'slot': True})

    def test_parse_protocol_a_skips_non_touch(self):
        dev = v.parse_getevent(GETEVENT_A)
        self.assertEqual((dev['path'], dev['x'], dev['tid'], dev['btn']),
                         ('/dev/input/event1', (0, 1919), False, False))
        self.assertIsNone(v.parse_getevent('add device 1: /dev/input/event0\n  name: "Power"\n'))
        self.assertIsNone(v.parse_getevent(''))

    def test_cmds_with_tracking_id(self):
        e = 'sendevent /dev/input/event3'
        self.assertEqual(v.sendevent_cmds(v.parse_getevent(GETEVENT_B), 1919, 0), [
            f'{e} 3 47 0', f'{e} 3 57 1', f'{e} 3 53 32767', f'{e} 3 54 0', f'{e} 1 330 1', f'{e} 0 0 0',
            f'{e} 3 47 0', f'{e} 3 57 -1', f'{e} 1 330 0', f'{e} 0 0 0'])

    def test_cmds_without_tracking_id_and_hold(self):
        e = 'sendevent /dev/input/event1'
        self.assertEqual(v.sendevent_cmds(v.parse_getevent(GETEVENT_A), 960, 540, ms=200), [
            f'{e} 3 53 960', f'{e} 3 54 540', f'{e} 0 2 0', f'{e} 0 0 0',
            'sleep 0.2', f'{e} 0 2 0', f'{e} 0 0 0'])

    def test_scaling(self):
        dev = v.parse_getevent(GETEVENT_B)
        x, y = (int(c.split()[-1]) for c in v.sendevent_cmds(dev, 960, 540)[2:4])
        self.assertEqual((x, y), (round(960 * 32767 / 1919), round(540 * 32767 / 1079)))

    def test_discovery_with_root(self):
        with mock.patch.object(v, 'adb', side_effect=[cp(GETEVENT_B), cp('uid=0(root) gid=0(root)')]) as adb, \
                mock.patch('sys.stdout'):
            self.assertTrue(v.sendevent_device()['root'])
            self.assertTrue(v.sendevent_device())            # cached: no second discovery
        self.assertEqual(adb.call_args_list, [mock.call('shell', 'getevent -pl', timeout=10),
                                              mock.call('shell', 'su -c id', timeout=10)])

    def test_discovery_failure_stops_the_chain(self):
        for effect in ([cp(rc=1)], [cp('add device 1: /dev/input/event0\n')],
                       subprocess.TimeoutExpired('adb', 10)):
            v._SENDEVENT, v._TAP_DEAD = None, {'touchscreen'}
            with mock.patch.object(v, 'adb', side_effect=effect), mock.patch('sys.stdout'):
                self.assertIsNone(v.sendevent_device())
            self.assertIs(v._SENDEVENT, False)
            # chain: touchscreen dead, sendevent unavailable -> T97 hold-tap, no mode
            with mock.patch.object(v, 'tap_hold') as hold, mock.patch.object(v, 'tap') as tap, \
                    mock.patch('sys.stdout'):
                self.assertIsNone(v.tap_retry((5, 6), 0))
            hold.assert_called_once_with((5, 6), wait=0)
            tap.assert_not_called()
        # forced sendevent mode without a device falls back to plain input (no crash)
        v.TAP_MODE = 'sendevent'
        self.assertEqual(v._tap_cmd(5, 6), 'input tap 5 6')


class Chain(TapModeState):
    def test_retry_order_and_result(self):
        with mock.patch.object(v, 'tap') as tap, mock.patch('sys.stdout'):
            self.assertEqual(v.tap_retry((5, 6), 0), 'touchscreen')
            tap.assert_called_once_with((5, 6), 0, mode='touchscreen')
            v.tap_result('touchscreen', False)
            v._SENDEVENT = dict(v.parse_getevent(GETEVENT_B), root=True)
            self.assertEqual(v.tap_retry((5, 6), 0), 'sendevent')
            v.tap_result('sendevent', True)
        self.assertEqual(v.TAP_MODE, 'sendevent')
        v.tap_result(None, True)                              # hold-tap fallback: no verdict
        self.assertEqual(v.TAP_MODE, 'sendevent')

    def test_failing_retry_mode_is_dead_and_falls_back_to_hold(self):
        # sendevent without write access to /dev/input: adb rc 1 -> no exception at the stall site
        v._TAP_DEAD, v._SENDEVENT = {'touchscreen'}, dict(v.parse_getevent(GETEVENT_B), root=False)
        with mock.patch.object(v, 'adb', return_value=cp(rc=1)),                 mock.patch.object(v, 'tap_hold') as hold, mock.patch('sys.stdout'):
            self.assertIsNone(v.tap_retry((5, 6), 0))
        hold.assert_called_once_with((5, 6), wait=0)
        self.assertIn('sendevent', v._TAP_DEAD)

    def test_dead_taps_touchscreen_retry_sticks(self):
        # select: 2 dead plain taps -> 'touchscreen' retry moves the screen -> the mode
        # sticks; the Battle tap on PREP already goes out as 'touchscreen'
        dev = DeadTapDevice(self, ['ARENA_SELECT_T95', 'ARENA_PREP'], live_modes=('touchscreen',),
                            also=(ar,))
        self.assertEqual(ar.advance_to_fight('arena_f1'), 'PREP')
        s = ar.SWORD_LEFT
        self.assertEqual(dev.taps, [s, s, ('touchscreen', *s), ('touchscreen', *ar.ARENA_BATTLE)])
        self.assertEqual(v.TAP_MODE, 'touchscreen')
        self.assertIn('TAP_MODE -> touchscreen (taps were dead)', dev.out.getvalue())
        self.assertEqual(v._tap_cmd(1, 2), 'input touchscreen tap 1 2')   # the real builder follows

    def test_arena_retry_landing_elsewhere_does_not_stick(self):
        # the retry moves the screen, but not to detail/PREP (mis-aimed): no sticky mode
        DeadTapDevice(self, ['ARENA_SELECT_T95', 'ARENA_LOBBY'], live_modes=('touchscreen',), also=(ar,))
        ar.advance_to_fight('arena_f1')
        self.assertEqual((v.TAP_MODE, v._TAP_DEAD), ('tap', {'touchscreen'}))


if __name__ == '__main__':
    unittest.main()
