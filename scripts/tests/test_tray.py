"""T66 spectre-tray.ps1: state logic via -StateOnly on a fixture .spectre dir."""
from __future__ import annotations

import os
import shutil
import subprocess
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'spectre-tray.ps1'
FIXTURE = Path(__file__).resolve().parent / '.artifacts' / 'tray' / '.spectre'
PS = shutil.which('powershell.exe') or shutil.which('powershell')


@unittest.skipUnless(PS, 'Windows PowerShell not available')
class TrayState(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(FIXTURE.parent, ignore_errors=True)        # test-owned dir
        (FIXTURE / 'logs').mkdir(parents=True)
        self.lock = FIXTURE / 'afk-bot.lock'
        log = FIXTURE / 'logs' / f"afk-bot-{datetime.now(timezone.utc):%Y-%m-%d}.log"
        log.write_text('=== 2026-11-03T05:10:00Z watch start (mode=--scheduled shell_pid=1)\n'
                       '    initial state: WORLD\n'
                       '=== 2026-11-03T05:12:00Z arena attempt 1/4\n'
                       '    --- Arena card -> lobby\n', encoding='utf-8')

    def state(self, **env) -> str:
        p = subprocess.run([PS, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(SCRIPT),
                            '-StateOnly', '-SpectreDir', str(FIXTURE)],
                           capture_output=True, text=True, timeout=60, env={**os.environ, **env})
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout.strip()

    def test_idle_without_lock(self):
        self.assertTrue(self.state().startswith('idle '))

    def test_running_with_fresh_lock(self):
        self.lock.write_text('1234\n', encoding='utf-8')
        self.assertEqual(self.state().split(' age=')[0], 'running pid=1234')
        self.assertTrue(self.state().endswith('phase=arena attempt 1/4'))

    def test_stale_lock(self):
        self.lock.write_text('1234\n', encoding='utf-8')
        old = time.time() - 2 * 3600
        os.utime(self.lock, (old, old))
        self.assertTrue(self.state().startswith('stale pid=1234'))
        self.assertTrue(self.state(AFK_LOCK_STALE='99999').startswith('running '))

    def test_script_parses(self):
        cmd = ("$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile("
               f"'{SCRIPT}', [ref]$null, [ref]$e); $e.Count")
        p = subprocess.run([PS, '-NoProfile', '-Command', cmd], capture_output=True, text=True, timeout=60)
        self.assertEqual(p.stdout.strip(), '0', p.stderr)

    def test_bom_for_windows_powershell(self):
        self.assertEqual(SCRIPT.read_bytes()[:3], b'\xef\xbb\xbf')   # umlauts in 5.1


if __name__ == '__main__':
    unittest.main()
