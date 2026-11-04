"""T65 device-ensure: afk_device_ready (FakeDevice) + device-ensure.sh exit paths (stubbed adb)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402
import afk_device_ready as dready  # noqa: E402
import afk_normalize  # noqa: E402
from fake_vision import FakeDevice  # noqa: E402

K = ('key', 4)      # T97: keyevent BACK (v.back)

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'device-ensure.sh'
ARTIFACTS = Path(__file__).resolve().parent / '.artifacts' / 'device_ensure'


class DeviceReady(unittest.TestCase):
    def test_loading_then_title_then_world(self):
        dev = FakeDevice(self, ['UNKNOWN', 'UNKNOWN', 'WORLD'],
                         ocr={'dev_1': ['AFK Journey', 'Tap to Start']})
        self.assertEqual(dready.main(['--timeout', '60']), 0)
        self.assertEqual(dev.taps, [dready.TITLE_TAP])          # loading frame: no tap, no BACK

    def test_login_popup_claimed(self):
        dev = FakeDevice(self, ['POPUP', 'POPUP', 'WORLD', 'WORLD'],
                         ocr={'dev_pop0': ['Esperia', 'Daily Rewards']})
        self.assertEqual(dready.main([]), 0)
        self.assertEqual(dev.taps, [v.LOGIN_CLAIM])

    def test_other_popup_gets_back(self):
        dev = FakeDevice(self, ['POPUP', 'POPUP', 'PANEL'], ocr={'dev_pop0': ['Store']})
        self.assertEqual(dready.main([]), 0)
        self.assertEqual(dev.taps, [K])

    def test_timeout_falls_back_to_normalize(self):
        dev = FakeDevice(self, ['UNKNOWN', 'UNKNOWN'])
        with mock.patch('time.monotonic', side_effect=[0.0, 1.0, 100.0, 300.0]), \
             mock.patch.object(afk_normalize, 'main', return_value=1) as norm:
            self.assertEqual(dready.main(['--timeout', '180']), 1)
        norm.assert_called_once()
        self.assertEqual(dev.taps, [])


@unittest.skipUnless(shutil.which('bash'), 'bash not available')
class DeviceEnsureSh(unittest.TestCase):
    def setUp(self):
        ARTIFACTS.mkdir(parents=True, exist_ok=True)

    def stub(self, name: str, body: str) -> Path:
        p = ARTIFACTS / name
        p.write_text('#!/usr/bin/env bash\n' + body + '\n', encoding='utf-8', newline='\n')
        os.chmod(p, 0o755)
        return p

    def run_sh(self, *argv, ensure_rc=0, adb_body='exit 0'):
        env = {**os.environ,
               'BS_ENSURE': self.stub('ensure.sh', f'exit {ensure_rc}').as_posix(),
               'ADB': self.stub('adb.sh', adb_body).as_posix(),
               'DEVICE_LOG': (ARTIFACTS / 'device-ensure.log').as_posix()}
        env.pop('AFK_PACKAGE', None)
        return subprocess.run(['bash', SCRIPT.as_posix(), *argv], env=env,
                              capture_output=True, text=True, encoding='utf-8',
                              errors='replace', timeout=60)

    def test_ensure_exit_codes_pass_through(self):
        for rc in (2, 3, 4, 5):
            self.assertEqual(self.run_sh(ensure_rc=rc).returncode, rc)

    def test_game_not_installed(self):
        p = self.run_sh(adb_body='echo "package:com.android.settings"')
        self.assertEqual(p.returncode, 6, p.stdout + p.stderr)

    def test_unknown_argument(self):
        self.assertEqual(self.run_sh('--bogus').returncode, 64)


if __name__ == '__main__':
    unittest.main()
