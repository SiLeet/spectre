"""T62 bluestacks-fps.py on a synthetic fixture conf (never the real one)."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'bluestacks-fps.py'
ARTIFACTS = Path(__file__).resolve().parent / '.artifacts' / 'bsfps'

_spec = importlib.util.spec_from_file_location('bluestacks_fps', SCRIPT)
bf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bf)

# layout of this host's BlueStacks 5 conf (keys only, values synthetic)
FIXTURE = (b'bst.feature.rooting="0"\n'
           b'bst.instance.Pie64.eco_mode_max_fps="5"\n'
           b'bst.instance.Pie64.enable_high_fps="0"\n'
           b'bst.instance.Pie64.enable_vsync="0"\n'
           b'bst.instance.Pie64.max_fps="60"\n'
           b'bst.instance.Pie64_1.max_fps="60"\n'
           b'bst.mim.max_fps="60"\n')


class FpsTool(unittest.TestCase):
    def setUp(self):
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        self.conf = ARTIFACTS / 'bluestacks.conf'
        self.bak = ARTIFACTS / 'bluestacks.conf.bak'
        self.bak.unlink(missing_ok=True)
        self.conf.write_bytes(FIXTURE)
        p = mock.patch.object(bf, 'player_running', return_value=False)
        p.start()
        self.addCleanup(p.stop)

    def run_tool(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = bf.main([*argv, '--conf', str(self.conf)])
        return rc, out.getvalue() + err.getvalue()

    def test_show(self):
        rc, out = self.run_tool('--show')
        self.assertEqual(rc, 0)
        self.assertIn('Pie64.max_fps = 60', out)
        self.assertIn('Pie64.enable_high_fps = 0', out)
        self.assertEqual(self.conf.read_bytes(), FIXTURE)          # read-only

    def test_set_touches_only_the_instance_key(self):
        rc, out = self.run_tool('--set', '90')
        self.assertEqual(rc, 0)
        self.assertIn('Pie64.max_fps: 60 -> 90', out)
        self.assertIn('restart the BlueStacks instance', out)
        self.assertEqual(self.conf.read_bytes(),
                         FIXTURE.replace(b'Pie64.max_fps="60"', b'Pie64.max_fps="90"'))
        self.assertEqual(self.bak.read_bytes(), FIXTURE)

    def test_backup_keeps_the_original_and_restore(self):
        self.run_tool('--set', '90')
        self.run_tool('--set', '120')
        self.assertEqual(self.bak.read_bytes(), FIXTURE)
        rc, out = self.run_tool('--restore')
        self.assertEqual(rc, 0)
        self.assertIn('max_fps 120 -> 60', out)
        self.assertEqual(self.conf.read_bytes(), FIXTURE)
        self.assertFalse(self.bak.exists())
        self.assertEqual(self.run_tool('--restore')[0], 4)          # nothing left to restore

    def test_high_fps_warning(self):
        rc, out = self.run_tool('--set', '120')
        self.assertIn('enable_high_fps is not "1"', out)

    def test_running_player_warns(self):
        with mock.patch.object(bf, 'player_running', return_value=True):
            rc, out = self.run_tool('--set', '90')
        self.assertIn('BlueStacks is running', out)

    def test_crlf_kept(self):
        self.conf.write_bytes(FIXTURE.replace(b'\n', b'\r\n'))
        self.run_tool('--set', '75')
        self.assertIn(b'bst.instance.Pie64.max_fps="75"\r\n', self.conf.read_bytes())

    def test_bad_input(self):
        self.assertEqual(self.run_tool('--set', '0')[0], 3)
        self.assertEqual(self.run_tool('--set', '90', '--instance', 'Nougat64')[0], 3)
        self.assertEqual(self.conf.read_bytes(), FIXTURE)
        self.assertFalse(self.bak.exists())

    def test_conf_not_found(self):
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(bf.main(['--show', '--conf', str(ARTIFACTS / 'missing.conf')]), 2)

    def test_find_conf_env_and_programdata(self):
        with mock.patch.dict('os.environ', {'BLUESTACKS_CONF': str(self.conf)}):
            self.assertEqual(bf.find_conf(), self.conf)
        root = ARTIFACTS / 'pd'
        (root / 'BlueStacks_msi5').mkdir(parents=True, exist_ok=True)
        (root / 'BlueStacks_msi5' / 'bluestacks.conf').write_bytes(FIXTURE)
        with mock.patch.dict('os.environ', {'ProgramData': str(root), 'BLUESTACKS_CONF': ''}):
            self.assertEqual(bf.find_conf(), root / 'BlueStacks_msi5' / 'bluestacks.conf')


class SetFpsDupKeys(unittest.TestCase):
    def test_all_occurrences_replaced(self):
        nl = bytes([13, 10])                       # CRLF, no escape ambiguity
        raw = (b'bst.instance.Pie64.max_fps="60"' + nl + b'other=1' + nl
               + b'bst.instance.Pie64.max_fps="30"' + nl)
        out = bf.set_fps(raw, 'Pie64', 120)
        self.assertEqual(out.count(b'max_fps="120"'), 2)
        self.assertNotIn(b'max_fps="60"', out)
        self.assertNotIn(b'max_fps="30"', out)

    def test_missing_key_raises(self):
        with self.assertRaises(KeyError):
            bf.set_fps(b'nothing=1', 'Pie64', 120)


if __name__ == '__main__':
    unittest.main()
