"""T79: mem_probe with fake `spectre hot --json` outputs (no device)."""
from __future__ import annotations

import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import mem_probe as mp  # noqa: E402

BASE = 0x724DF0000000


def fake_hot(by_hex: dict, calls: list, rc: int = 0):
    def run(cmd, **kw):
        calls.append(cmd)
        addrs = by_hex.get(cmd[3], [])
        return subprocess.CompletedProcess(cmd, rc, json.dumps([hex(a) for a in addrs]), '')
    return mock.patch.object(mp.subprocess, 'run', side_effect=run)


class TProbe(unittest.TestCase):
    def run_probe(self, by_hex, values=(9963, 12300), limit=20000, rc=0):
        calls, between = [], []
        with fake_hot(by_hex, calls, rc), mock.patch('sys.stdout', new=io.StringIO()):
            res = mp.probe('4321', hex(BASE), 'gold', 'u32', list(values), limit, between.append)
        return res, calls, between

    def test_encode_matches_docs(self):
        self.assertEqual(mp.encode(259850, 'u32'), '0af70300')
        self.assertEqual(mp.encode(-2, 'i64'), 'feffffffffffffff')

    def test_intersection_single_candidate_high(self):
        gold = BASE + 0x453B58
        (rc, rep), calls, between = self.run_probe({
            mp.encode(9963, 'u32'): [BASE + 0x10, gold, BASE + 0x99000],
            mp.encode(12300, 'u32'): [gold, BASE + 0x20]})
        self.assertEqual(rc, 0)
        self.assertEqual(between, [1])                      # one in-game change between 2 scans
        self.assertIn('offset: 0x453b58', rep)
        self.assertIn('HIGH (1 candidate(s))', rep)
        self.assertIn('candidates per scan: 3 -> 2 -> intersection 1', rep)
        self.assertIn('field_type: U32', rep)
        cmd = calls[0]
        self.assertEqual(cmd[1:4], ['hot', '4321', mp.encode(9963, 'u32')])
        for flag in ('--adb', '--json', '--limit', '--base'):
            self.assertIn(flag, cmd)

    def test_many_candidates_low_with_alts(self):
        shared = [BASE + 8 * i for i in range(12)]
        (rc, rep), _, _ = self.run_probe({mp.encode(9963, 'u32'): shared,
                                          mp.encode(12300, 'u32'): shared})
        self.assertEqual(rc, 0)
        self.assertIn('LOW (12 candidate(s))', rep)
        self.assertEqual(rep.count('# alt: offset'), 9)
        self.assertIn('... 2 more', rep)

    def test_three_values_narrow_further(self):
        a, b = BASE + 0x100, BASE + 0x200
        (rc, rep), calls, between = self.run_probe({
            mp.encode(1, 'u32'): [a, b], mp.encode(2, 'u32'): [a, b], mp.encode(3, 'u32'): [a]},
            values=(1, 2, 3))
        self.assertEqual((rc, len(calls), between), (0, 3, [1, 2]))
        self.assertIn('offset: 0x100', rep)

    def test_no_candidate_rc3(self):
        (rc, rep), _, _ = self.run_probe({mp.encode(9963, 'u32'): [BASE + 1]})
        self.assertEqual(rc, 3)
        self.assertIn('no candidate survived', rep)

    def test_truncated_scan_caps_confidence(self):
        gold = BASE + 0x40
        (rc, rep), _, _ = self.run_probe({mp.encode(9963, 'u32'): [gold, BASE + 0x80],
                                          mp.encode(12300, 'u32'): [gold]}, limit=2)
        self.assertEqual(rc, 0)
        self.assertIn('LOW (1 candidate(s))', rep)
        self.assertIn('TRUNCATED', rep)

    def test_spectre_failure_rc2_and_stops(self):
        (rc, rep), calls, between = self.run_probe({}, rc=1)
        self.assertEqual((rc, len(calls), between), (2, 1, []))
        with mock.patch.object(mp.subprocess, 'run',
                               side_effect=subprocess.TimeoutExpired('hot', 300)), \
             mock.patch('sys.stdout', new=io.StringIO()):
            self.assertEqual(mp.probe('1', '0x0', 'x', 'u32', [1, 2], 10, lambda i: None)[0], 2)

    def test_cli_rejects_unchanged_values(self):
        with mock.patch('sys.stderr', new=io.StringIO()), \
             mock.patch.object(mp.subprocess, 'run') as run:
            self.assertEqual(mp.main(['--pid', '1', '--base', '0x0', '--name', 'g',
                                      '--values', '5', '5']), 1)
            self.assertEqual(mp.main(['--pid', '1', '--base', '0x0', '--name', 'g',
                                      '--values', '5']), 1)
        run.assert_not_called()

    def test_cli_no_prompt_sleeps_between(self):
        calls = []
        with fake_hot({mp.encode(5, 'u32'): [0x10], mp.encode(6, 'u32'): [0x10]}, calls), \
             mock.patch.object(mp.time, 'sleep') as sl, \
             mock.patch('sys.stdout', new=io.StringIO()) as out:
            rc = mp.main(['--pid', '1', '--base', '0x0', '--name', 'g', '--values', '5', '6',
                          '--no-prompt', '--wait', '7'])
        self.assertEqual(rc, 0)
        sl.assert_called_once_with(7.0)
        self.assertIn('offset: 0x10', out.getvalue())


class WarnPrefix(unittest.TestCase):
    def test_ansi_warn_lines_before_json_are_tolerated(self):
        calls = []

        def run(cmd, **kw):
            calls.append(kw)
            return subprocess.CompletedProcess(
                cmd, 0,
                '\x1b[33mWARN spectre_adb::reader: skipping unreadable chunk\x1b[0m\n'
                '[\"0x796590a6fa74\"]', '')

        with mock.patch.object(mp.subprocess, 'run', side_effect=run), \
             mock.patch('sys.stdout', new=io.StringIO()):
            out = mp.hot_scan('5176', 258488, 'u32', '0x796590000000', 50)
        self.assertEqual(out, [0x796590a6fa74])
        self.assertGreaterEqual(mp.SCAN_TIMEOUT, 900)
        self.assertGreaterEqual(calls[0].get('timeout', 0), 900)


if __name__ == '__main__':
    unittest.main()
