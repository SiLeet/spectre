"""T63 hack/frida kit: attach.py without frida installed + JS sanity (no device)."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest import mock

KIT = Path(__file__).resolve().parents[2] / 'hack' / 'frida'
_spec = importlib.util.spec_from_file_location('frida_attach', KIT / 'attach.py')
fa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fa)

PS = '''  PID  Name          Identifier
-----  ------------  ------------------------------
 4392  AFK Journey   com.farlightgames.igame.gp
    -  Settings      com.android.settings
'''


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        rc = fa.main(list(argv))
    return rc, out.getvalue()


class AttachPy(unittest.TestCase):
    def test_missing_frida_is_explained(self):
        with mock.patch.object(fa, 'tool', return_value=None):
            rc, out = run('ps')
            self.assertEqual(rc, 3)
            self.assertIn('frida-ps not found', out)
            rc, out = run('attach', str(KIT / 'probe_timescale.js'))
            self.assertEqual(rc, 3)

    def test_pick_target(self):
        self.assertEqual(fa.pick_target(PS, 'igame'),
                         ('4392', 'AFK Journey', 'com.farlightgames.igame.gp'))
        self.assertEqual(fa.pick_target(PS, 'settings')[0], '-')
        self.assertIsNone(fa.pick_target(PS, 'nothing'))

    def test_attach_dry_run_command(self):
        with mock.patch.object(fa, 'tool', return_value='frida-ps'), \
             mock.patch.object(fa, 'frida_ps', return_value=PS):
            rc, out = run('attach', str(KIT / 'set_timescale.js'), '--params', '{"scale": 1.5}',
                          '--dry-run')
        self.assertEqual(rc, 0)
        self.assertIn(f'cmd: frida -D 127.0.0.1:5555 -p 4392 -l {KIT / "set_timescale.js"} '
                      '-P {"scale": 1.5}', out)

    def test_spawn_uses_identifier_and_warns(self):
        with mock.patch.object(fa, 'tool', return_value='frida-ps'), \
             mock.patch.object(fa, 'frida_ps', return_value=PS):
            rc, out = run('spawn', str(KIT / 'probe_timescale.js'), '--dry-run')
        self.assertIn('-f com.farlightgames.igame.gp', out)
        self.assertIn('attach after login', out)

    def test_not_running_and_bad_params(self):
        with mock.patch.object(fa, 'tool', return_value='frida-ps'), \
             mock.patch.object(fa, 'frida_ps', return_value=PS):
            self.assertEqual(run('attach', str(KIT / 'probe_timescale.js'), '--match', 'settings')[0], 2)
        self.assertEqual(run('attach', str(KIT / 'set_timescale.js'), '--params', 'scale=2')[0], 2)
        self.assertEqual(run('attach', 'missing.js', '--pid', '1')[0], 2)


class Scripts(unittest.TestCase):
    def test_probe_is_log_only(self):
        src = (KIT / 'probe_timescale.js').read_text(encoding='utf-8')
        self.assertNotIn("'void'", src)               # never builds a setter call
        self.assertNotIn('.write', src)               # no memory writes
        self.assertNotIn('replace(', src)             # no Interceptor.replace

    def test_setter_needs_an_explicit_scale(self):
        src = (KIT / 'set_timescale.js').read_text(encoding='utf-8')
        self.assertIn('p.scale === undefined', src)
        self.assertIn('MAX_SCALE = 4.0', src)

    @unittest.skipUnless(shutil.which('node'), 'node not installed')
    def test_js_syntax(self):
        for js in ('probe_timescale.js', 'set_timescale.js'):
            p = subprocess.run(['node', '--check', str(KIT / js)], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)


if __name__ == '__main__':
    unittest.main()
