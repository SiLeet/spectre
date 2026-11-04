"""T80a: speed_profile with fake adb/frida (no device)."""
from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import speed_profile as spf  # noqa: E402

PS = ' PID  Name         Identifier\n4392  AFK Journey  com.farlightgames.igame.gp\n'


class FakeAdb:
    def __init__(self, root=True, running=False, present=True, starts=True):
        self.root, self.running, self.present, self.starts = root, running, present, starts
        self.calls = []

    def __call__(self, *args, timeout=30):
        self.calls.append(args)
        out = ''
        if args[0] == 'shell':
            cmd = args[1]
            if '"id"' in cmd:
                out = 'uid=0(root) gid=0(root)' if self.root else 'uid=2000(shell)'
            elif 'pidof' in cmd:
                out = '777\n' if self.running else ''
            elif '"ls ' in cmd:
                out = spf.SERVER if self.present else f'ls: {spf.SERVER}: No such file or directory'
            elif '-D -l' in cmd and self.starts:
                self.running = True
        return subprocess.CompletedProcess(args, 0, out.encode(), b'')


class TSpeedProfile(unittest.TestCase):
    def go(self, *argv, adb=None, frida_rc=0, frida_exc=None, tools=True):
        adb = adb or FakeAdb()
        runs = []

        def frida_run(cmd, **kw):
            runs.append(cmd)
            if frida_exc:
                raise frida_exc
            return subprocess.CompletedProcess(cmd, frida_rc, '[timescale] timeScale 1 -> 2\n', '')
        out = io.StringIO()
        with mock.patch.object(spf.v, 'adb', side_effect=adb), \
             mock.patch.object(spf.fa, 'tool', return_value='frida' if tools else None), \
             mock.patch.object(spf.fa, 'frida_ps', return_value=PS) as ps, \
             mock.patch.object(spf.subprocess, 'run', side_effect=frida_run), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            rc = spf.main(list(argv))
        return rc, out.getvalue(), adb, runs, ps

    def test_frida_missing_rc3_touches_nothing(self):
        rc, out, adb, runs, _ = self.go('on', tools=False)
        self.assertEqual((rc, adb.calls, runs), (3, [], []))
        self.assertIn('not found on PATH', out)

    def test_on_starts_server_on_own_port_and_sets_scale(self):
        rc, out, adb, runs, ps = self.go('on', '--scale', '1.5')
        self.assertEqual(rc, 0)
        shells = [c[1] for c in adb.calls if c[0] == 'shell']
        self.assertTrue(any(f'-D -l 127.0.0.1:{spf.PORT}' in s for s in shells))
        self.assertIn(('forward', f'tcp:{spf.PORT}', f'tcp:{spf.PORT}'), adb.calls)
        ps.assert_called_once_with(spf.fa.SERIAL, f'127.0.0.1:{spf.PORT}')
        cmd = runs[0]
        self.assertEqual(cmd[1:5], ['-H', f'127.0.0.1:{spf.PORT}', '-p', '4392'])
        self.assertIn('set_timescale.js', cmd[6])
        self.assertEqual(cmd[cmd.index('-P') + 1], '{"scale": 1.5}')
        self.assertIn('-q', cmd)
        self.assertNotIn('--eternalize', cmd)

    def test_off_is_scale_one_and_reuses_running_server(self):
        rc, _, adb, runs, _ = self.go('off', adb=FakeAdb(running=True))
        self.assertEqual(rc, 0)
        self.assertFalse(any('-D -l' in c[1] for c in adb.calls if c[0] == 'shell'))
        self.assertEqual(runs[0][runs[0].index('-P') + 1], '{"scale": 1.0}')

    def test_status_runs_the_log_only_probe(self):
        rc, _, _, runs, _ = self.go('status', adb=FakeAdb(running=True))
        self.assertEqual(rc, 0)
        self.assertIn('probe_timescale.js', ' '.join(runs[0]))
        self.assertNotIn('-P', runs[0])

    def test_repeat_eternalizes(self):
        _, out, _, runs, _ = self.go('on', '--repeat-ms', '1000', adb=FakeAdb(running=True))
        self.assertIn('--eternalize', runs[0])
        self.assertIn('"repeat_ms": 1000', ' '.join(runs[0]))
        self.assertIn('game restart', out)

    def test_no_root_and_missing_server_rc4(self):
        self.assertEqual(self.go('on', adb=FakeAdb(root=False))[0], 4)
        rc, out, _, runs, _ = self.go('on', adb=FakeAdb(present=False))
        self.assertEqual((rc, runs), (4, []))
        self.assertIn('--server-bin', out)
        self.assertEqual(self.go('on', adb=FakeAdb(starts=False))[0], 4)

    def test_frida_timeout_rc5(self):
        rc, _, _, _, _ = self.go('on', adb=FakeAdb(running=True),
                                 frida_exc=subprocess.TimeoutExpired('frida', 60))
        self.assertEqual(rc, 5)

    def test_bad_scale_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            spf.main(['on', '--scale', '8'])

    def test_dry_run_prints_everything_runs_nothing(self):
        rc, out, adb, runs, _ = self.go('on', '--dry-run')
        self.assertEqual((rc, adb.calls, runs), (0, [], []))
        self.assertIn('adb forward', out)
        self.assertIn('cmd: frida -H', out)


if __name__ == '__main__':
    unittest.main()
