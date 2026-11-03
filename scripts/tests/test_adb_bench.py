"""T64 adb-bench.py with a mocked adb + clock (no device)."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402
from fake_vision import frame  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    'adb_bench', Path(__file__).resolve().parents[2] / 'scripts' / 'adb-bench.py')
ab = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ab)



class Bench(unittest.TestCase):
    def run_bench(self, *argv, screen='WORLD', adb_rc=0, clock=None):
        adb = mock.Mock(return_value=subprocess.CompletedProcess([], adb_rc, b'', b'offline'))
        out = io.StringIO()
        with mock.patch.object(v, 'adb', adb), \
             mock.patch.object(v, 'shot', return_value=frame(screen)), \
             mock.patch('time.perf_counter', side_effect=clock or [0.0, 0.01] * 100), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            rc = ab.main(list(argv))
        return rc, out.getvalue(), adb

    def test_percentile(self):
        xs = [float(i) for i in range(1, 101)]
        self.assertEqual((ab.percentile(xs, 50), ab.percentile(xs, 90), ab.percentile(xs, 99)),
                         (50.0, 90.0, 99.0))
        self.assertEqual(ab.percentile([7.0], 99), 7.0)

    def test_table(self):
        clock = [0.0, 0.010, 1.0, 1.020, 2.0, 2.030,          # tap: 10, 20, 30 ms
                 3.0, 3.100, 4.0, 4.200, 5.0, 5.300]          # screencap: 100, 200, 300 ms
        rc, out, adb = self.run_bench('--n', '3', clock=clock)
        self.assertEqual(rc, 0)
        self.assertRegex(out, r'tap\s+3\s+20\.0\s+30\.0\s+30\.0\s+30\.0')
        self.assertRegex(out, r'screencap\s+3\s+200\.0\s+300\.0\s+300\.0\s+300\.0')
        self.assertEqual(adb.call_args_list[0].args, ('shell', 'input', 'tap', '300', '250'))
        self.assertEqual(adb.call_args_list[-1].args, ('exec-out', 'screencap', '-p'))

    def test_tap_refused_off_world(self):
        rc, out, adb = self.run_bench('--n', '3', screen='PANEL')
        self.assertEqual(rc, 1)
        adb.assert_not_called()

    def test_screencap_only_needs_no_gate(self):
        rc, out, adb = self.run_bench('--n', '2', '--only', 'screencap', screen='PANEL')
        self.assertEqual(rc, 0)
        self.assertEqual(adb.call_count, 2)

    def test_adb_failure(self):
        rc, out, adb = self.run_bench('--n', '5', adb_rc=1)
        self.assertEqual(rc, 2)
        self.assertEqual(adb.call_count, 1)


if __name__ == '__main__':
    unittest.main()
