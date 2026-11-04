"""T80a/T85: speed_profile with fake adb/frida (no device)."""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import speed_profile as spf  # noqa: E402

PS = ' PID  Name         Identifier\n4392  AFK Journey  com.farlightgames.igame.gp\n'
VER = '17.2.0'


class FakeAdb:
    def __init__(self, root=True, running=False, present=True, starts=True, version=VER,
                 listen_port=None, forward_rc=0, listen_state='0A'):
        self.root, self.running, self.present, self.starts = root, running, present, starts
        self.version, self.forward_rc, self.listen_state = version, forward_rc, listen_state
        self.listen_port = spf.PORT if listen_port is None else listen_port
        self.calls = []

    def __call__(self, *args, timeout=30):
        self.calls.append(args)
        out, rc = '', 0
        if args[0] == 'forward':
            rc = self.forward_rc
        if args[0] == 'shell':
            cmd = args[1]
            if '--version' in cmd:
                out = self.version
            elif '/proc/net/tcp' in cmd:
                out = ('  sl  local_address rem_address   st\n'
                       f'   0: 0100007F:{self.listen_port:04X} 00000000:0000 {self.listen_state} 0\n'
                       if self.running else '')
            elif '"id"' in cmd:
                out = 'uid=0(root) gid=0(root)' if self.root else 'uid=2000(shell)'
            elif 'pidof' in cmd:
                out = '777\n' if self.running else ''
            elif '"ls ' in cmd:
                out = spf.SERVER if self.present else f'ls: {spf.SERVER}: No such file or directory'
            elif '-D -l' in cmd and self.starts:
                self.running = True
        return subprocess.CompletedProcess(args, rc, out.encode(), b'')


class TSpeedProfile(unittest.TestCase):
    def go(self, *argv, adb=None, frida_rc=0, frida_exc=None, tools=True, pc_ver=VER,
           frida_out='[timescale] timeScale 1 -> 2\n'):
        adb = adb or FakeAdb()
        runs = []

        def frida_run(cmd, **kw):
            if cmd[1:] == ['--version']:          # T85 version check, not an attach run
                return subprocess.CompletedProcess(cmd, 0, pc_ver + '\n', '')
            runs.append(cmd)
            if frida_exc:
                raise frida_exc
            return subprocess.CompletedProcess(cmd, frida_rc, frida_out, '')
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(spf.v, 'adb', side_effect=adb), \
             mock.patch.object(spf.fa, 'tool', return_value='frida' if tools else None), \
             mock.patch.object(spf.fa, 'frida_ps', return_value=PS) as ps, \
             mock.patch.object(spf.subprocess, 'run', side_effect=frida_run), \
             mock.patch.object(spf.time, 'sleep'), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = spf.main(list(argv))
        self.stdout = out.getvalue()
        return rc, out.getvalue() + err.getvalue(), adb, runs, ps

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


class TOpsT85(unittest.TestCase):
    """T85: version/port consistency, read-only status, status --json, rc semantics."""
    go = TSpeedProfile.go

    def status_json(self, **kw):
        rc, out, adb, runs, _ = self.go('status', '--json', **kw)
        st = json.loads(self.stdout)               # stdout is exactly one JSON object
        self.assertEqual(self.stdout.count('\n'), 1)
        self.assertEqual(st['rc'], rc)
        self.assertEqual(set(st), {'rc', 'frida', 'server', 'timescale', 'error'})
        self.assertEqual(set(st['server']), {'running', 'version', 'port'})
        return rc, st, out, adb, runs

    def test_constants_carry_live_markers(self):
        src = Path(spf.__file__).read_text(encoding='utf-8')
        self.assertEqual(spf.DEFAULT_PORT, 27142)
        self.assertIn('# LIVE: HERMES-SETUP — path', src)
        self.assertIn('# LIVE: HERMES-SETUP port', src)
        for rc in ('3  frida missing', '4  server dead/unreachable'):
            self.assertIn(rc, spf.__doc__)

    def test_version_mismatch_rc4_prints_both(self):
        rc, out, adb, runs, _ = self.go('on', adb=FakeAdb(running=True, version='16.5.9'))
        self.assertEqual((rc, runs), (4, []))
        self.assertIn('PC frida 17.2.0', out)
        self.assertIn('frida-server 16.5.9', out)
        self.assertNotIn('forward', [c[0] for c in adb.calls])

    def test_mismatch_checked_before_start(self):
        rc, _, adb, _, _ = self.go('on', adb=FakeAdb(version='16.5.9'))
        self.assertEqual(rc, 4)
        self.assertFalse(any('-D -l' in c[1] for c in adb.calls if c[0] == 'shell'))

    def test_pc_frida_without_version_rc3(self):
        rc, out, adb, runs, _ = self.go('on', pc_ver='')
        self.assertEqual((rc, adb.calls, runs), (3, [], []))
        self.assertIn('--version', out)

    def test_not_listening_on_port_rc4(self):
        rc, out, _, runs, _ = self.go('on', adb=FakeAdb(running=True, listen_port=27042))
        self.assertEqual((rc, runs), (4, []))
        self.assertIn(f'does not listen on 127.0.0.1:{spf.PORT}', out)

    def test_non_listen_socket_on_port_rc4(self):
        rc, out, _, runs, _ = self.go('on', adb=FakeAdb(running=True, listen_state='06'))  # TIME_WAIT
        self.assertEqual((rc, runs), (4, []))
        self.assertIn('does not listen', out)

    def test_running_server_without_version_output_rc4(self):
        rc, out, _, runs, _ = self.go('on', adb=FakeAdb(running=True, version=''))
        self.assertEqual((rc, runs), (4, []))
        self.assertIn('gave no output', out)
        self.assertNotIn('mismatch', out)

    def test_adb_hang_status_json_rc4(self):
        def hang(*a, **kw):
            raise subprocess.TimeoutExpired('adb', 30)
        rc, st, *_ = self.status_json(adb=hang)
        self.assertEqual(rc, 4)
        self.assertIn('adb hung or unreachable', st['error'])

    def test_frida_nonzero_exit_sets_error(self):
        rc, st, *_ = self.status_json(adb=FakeAdb(running=True), frida_rc=1)
        self.assertEqual(rc, 1)
        self.assertIn('frida exited 1', st['error'])

    def test_forward_failure_rc4(self):
        rc, out, _, runs, _ = self.go('on', adb=FakeAdb(running=True, forward_rc=1))
        self.assertEqual((rc, runs), (4, []))
        self.assertIn('adb forward failed', out)

    def test_status_is_read_only_dead_server_rc4(self):
        rc, out, adb, runs, _ = self.go('status', '--server-bin', __file__)
        self.assertEqual((rc, runs), (4, []))
        self.assertIn('not running', out)
        self.assertFalse([c for c in adb.calls if c[0] in ('push', 'forward')])
        self.assertFalse(any('-D -l' in c[1] or 'chmod' in c[1] for c in adb.calls if c[0] == 'shell'))

    def test_status_json_ok(self):
        rc, st, out, _, runs = self.status_json(
            adb=FakeAdb(running=True),
            frida_out='[probe] Time.timeScale = 1.5  (UnityEngine.Time::get_timeScale() @ 0x1)\n')
        self.assertEqual(rc, 0)
        self.assertEqual(st, {'rc': 0, 'frida': VER, 'timescale': 1.5, 'error': None,
                              'server': {'running': True, 'version': VER, 'port': spf.PORT}})
        self.assertIn('probe_timescale.js', ' '.join(runs[0]))
        self.assertIn('cmd: frida', out)           # logs went to stderr, not stdout
        self.assertNotIn('cmd:', self.stdout)

    def test_status_json_failures(self):
        rc, st, *_ = self.status_json(tools=False)
        self.assertEqual((rc, st['frida'], st['error']), (3, None, 'frida not found on PATH'))
        rc, st, *_ = self.status_json()
        self.assertEqual((rc, st['server']['running']), (4, False))
        self.assertIn('not running', st['error'])
        rc, st, *_ = self.status_json(adb=FakeAdb(running=True, version='16.5.9'))
        self.assertEqual((rc, st['frida'], st['server']['version']), (4, VER, '16.5.9'))
        self.assertIn('mismatch', st['error'])
        rc, st, *_ = self.status_json(adb=FakeAdb(root=False))
        self.assertEqual(rc, 4)
        self.assertIn('no root', st['error'])
        rc, st, *_ = self.status_json(adb=FakeAdb(running=True), frida_out='[probe] no il2cpp\n')
        self.assertEqual((rc, st['timescale']), (0, None))

    def test_json_only_for_status(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            spf.main(['on', '--json'])

    def test_dry_run_status_json(self):
        rc, out, adb, runs, _ = self.go('status', '--json', '--dry-run')
        self.assertEqual((rc, adb.calls, runs), (0, [], []))
        self.assertEqual(json.loads(self.stdout)['rc'], 0)
        self.assertIn('frida --version', out)

    def test_daily_wrappers_never_call_speed_profile(self):
        scripts = Path(spf.__file__).resolve().parent
        hits = [p.name for g in ('*.sh', '*.py', '*.cmd', '*.ps1') for p in scripts.glob(g)
                if p.name != 'speed_profile.py'
                and 'speed_profile' in p.read_text(encoding='utf-8', errors='replace')]
        self.assertEqual(hits, [])


if __name__ == '__main__':
    unittest.main()
