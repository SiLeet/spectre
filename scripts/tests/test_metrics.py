"""T61 battle wall-time metrics: helper + stage_push / dream / arena hooks.

Time is patched (time.monotonic); FakeDevice points v.METRICS at
scripts/tests/.artifacts/battles.test.jsonl, never at .spectre/.
"""
from __future__ import annotations

import argparse
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_arena as ar  # noqa: E402
import afk_claim_vision as v  # noqa: E402
import afk_dream_realm as dr  # noqa: E402
import afk_stage_push as sp  # noqa: E402
from fake_vision import FakeDevice  # noqa: E402
from test_runtime_fixes import StagePushCase  # noqa: E402

ARTIFACTS = Path(__file__).resolve().parent / '.artifacts'


def records(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding='utf-8').splitlines()]


class Helper(unittest.TestCase):
    def setUp(self):
        ARTIFACTS.mkdir(exist_ok=True)
        self.path = ARTIFACTS / 'metrics.helper.jsonl'
        self.path.unlink(missing_ok=True)

    def test_append_metric_lines(self):
        self.assertTrue(v.append_metric({'mode': 'push', 'wall_s': 1.5}, self.path))
        self.assertTrue(v.append_metric({'mode': 'dream', 'wall_s': 2.0}, self.path))
        recs = records(self.path)
        self.assertEqual([r['mode'] for r in recs], ['push', 'dream'])
        self.assertTrue(all('ts' in r for r in recs))

    def test_append_metric_never_raises(self):
        self.assertFalse(v.append_metric({'x': 1}, ARTIFACTS))           # a directory
        self.assertFalse(v.append_metric({'x': object()}, self.path))    # not JSON

    def test_battle_metric_and_summary(self):
        with mock.patch.object(v, 'METRICS', self.path):
            self.assertEqual(v.battle_metric('push', 'victory', 42.46, stage=254), 'wall=42.5s')
        self.assertEqual({k: records(self.path)[0][k] for k in ('mode', 'stage', 'result', 'wall_s')},
                         {'mode': 'push', 'stage': 254, 'result': 'victory', 'wall_s': 42.5})
        self.assertIn('2 battle(s), wall mean 15.0s (min 10.0s, max 20.0s)',
                      v.wall_summary('push', [10.0, 20.0]))
        self.assertIn('no timed battles', v.wall_summary('dream', []))


class StagePushWall(StagePushCase):
    def test_single_battle_wall(self):
        with mock.patch('time.monotonic', side_effect=[100.0, 142.5]):
            dev, rc = self.run_sp(['SP_PREP', 'SP_BATTLE', 'SP_RESULT', 'SP_RESULT'])
        self.assertIn('battle 1: VICTORY (AFK progress +1) wall=42.5s', dev.out.getvalue())
        self.assertIn('metrics[push]: 1 battle(s)', dev.out.getvalue())
        rec = records(dev.metrics)[0]
        self.assertEqual((rec['mode'], rec['result'], rec['wall_s']), ('push', 'victory', 42.5))

    def test_retap_restarts_the_clock(self):
        # first tap swallowed (wait_for -> PREP), the re-tap starts the fight
        waits = [('PREP', None), ('BATTLE', None), ('RESULT', None)]
        with mock.patch('time.monotonic', side_effect=[0.0, 30.0, 75.0]), \
             mock.patch.object(sp, 'wait_for', side_effect=waits):
            dev, rc = self.run_sp(['SP_PREP', 'SP_RESULT'])
        self.assertEqual(dev.taps, [sp.BATTLE_BTN, sp.BATTLE_BTN])
        self.assertIn('wall=45.0s', dev.out.getvalue())


class DreamWall(unittest.TestCase):
    def test_fight_wall(self):
        dev = FakeDevice(self, ['DR_BOSS', 'DR_BOSS', 'DR_BOSS',      # start, back_to_ready, chances
                                'DR_BOSS', 'DR_FIGHT',               # start_fight: pre0, after0_0
                                'DR_FIGHT',                          # set_speed_x2
                                'DR_ENDED', 'DR_BOSS',               # wait end, resolve
                                'DR_BOSS', 'DR_BOSS'])               # dr_exit, dr_final
        with mock.patch.object(dr, '_dismiss_taps', 0), \
             mock.patch('time.monotonic', side_effect=[10.0, 100.0]):
            self.assertEqual(dr.run(argparse.Namespace(fights=1, wait_fight=150)), 0)
        self.assertIn('completed (chance consumed) wall=90.0s', dev.out.getvalue())
        self.assertIn('metrics[dream]: 1 battle(s)', dev.out.getvalue())
        self.assertEqual(records(dev.metrics)[0]['result'], 'ended')


class ArenaWall(unittest.TestCase):
    def test_fight_wall(self):
        dev = FakeDevice(self, ['WORLD', 'BATTLE_MODES', 'ARENA_LOBBY', 'UNKNOWN',
                                'UNKNOWN', 'ARENA_PREP', 'UNKNOWN', 'ARENA_LOBBY',
                                'ARENA_LOBBY', 'BATTLE_MODES', 'WORLD'], also=(ar,))
        with mock.patch.object(sys, 'argv', ['afk_arena.py']), \
             mock.patch('time.monotonic', side_effect=[0.0, 81.2]):
            self.assertEqual(ar.main(), 0)
        self.assertIn('wall=81.2s', dev.out.getvalue())
        self.assertEqual(records(dev.metrics)[0]['result'], 'changed')


if __name__ == '__main__':
    unittest.main()
