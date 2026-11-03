"""T68: afk-bot-watch.sh / afk-night.sh call device-ensure only when no game is reachable.

Integration in a temp copy of the repo layout: fake spectre (find returns a pid
only once the "game" is up), stub scripts/device-ensure.sh (records its args,
exits FAKE_ENSURE_RC, brings the game up on 0), fake python (every phase 0).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LOCK_KEEPER = '( while [ -e "$LOCK" ]; do sleep 240; touch "$LOCK" 2>/dev/null || true; done ) &'
BASH = shutil.which('bash')


def bash_path(path) -> str:
    if os.name == 'nt':
        return subprocess.check_output(['cygpath', '-u', str(path)], text=True).strip()
    return str(path)


@unittest.skipUnless(BASH, 'bash not available')
class EnsureWiring(unittest.TestCase):
    def run_wrapper(self, script: str, *args: str, game_up=False, **env_over):
        with tempfile.TemporaryDirectory(prefix='afk-ensure-wiring-') as temp:
            root = Path(temp)
            for d in ('scripts', 'examples', 'target/release', 'bin'):
                (root / d).mkdir(parents=True)
            (root / 'examples' / 'bot-config-afk-live.yaml').write_text(
                (REPO / 'examples' / 'bot-config-afk-live.yaml').read_text(encoding='utf-8'),
                encoding='utf-8')
            wrapper = (REPO / 'scripts' / script).read_text(encoding='utf-8')
            self.assertIn(LOCK_KEEPER, wrapper)
            (root / 'scripts' / script).write_text(wrapper.replace(LOCK_KEEPER, '( true ) &'),
                                                   encoding='utf-8', newline='\n')
            flag = root / 'game_up'
            if game_up:
                flag.write_text('1')
            files = {
                'target/release/spectre.exe':
                    'case "$1" in\n'
                    '  find) [ -e "$GAME_UP_FLAG" ] && printf \'4392 com.farlightgames.igame.gp\\n\' ;;\n'
                    '  regions) printf \'%s\\n\' \'[{"start":"0x724dd0000000","end":"0x724de0000000",'
                    '"perms":"rw-p","path":""}]\' ;;\n'
                    '  *) exit 2 ;;\n'
                    'esac\n',
                'scripts/device-ensure.sh':
                    'printf \'%s\\n\' "$*" >> "$ENSURE_CALLS"\n'
                    '[ "${FAKE_ENSURE_RC:-0}" = "0" ] && touch "$GAME_UP_FLAG"\n'
                    'exit "${FAKE_ENSURE_RC:-0}"\n',
                'bin/python':
                    'if [ "${1:-}" = "-c" ]; then exit 0; fi\n'
                    'if [ "${1:-}" = "-" ]; then echo 0x724DD0000000; exit 0; fi\n'
                    'exit 0\n',
            }
            for rel, body in files.items():
                p = root / rel
                p.write_text('#!/usr/bin/env bash\n' + body, encoding='utf-8', newline='\n')
                p.chmod(0o755)
            calls = root / 'ensure_calls.txt'
            env = os.environ.copy()
            path = env.get('PATH', '')
            if os.name == 'nt':
                path = subprocess.check_output(['cygpath', '-p', '-u', path], text=True).strip()
            env.update(PATH=f"{bash_path(root / 'bin')}:{path}", AFK_PYTHON=bash_path(root / 'bin' / 'python'),
                       GAME_UP_FLAG=bash_path(flag), ENSURE_CALLS=bash_path(calls), AFK_MIN_IDLE='180')
            env.pop('AFK_DEVICE_ENSURE', None)
            env.update(env_over)
            result = subprocess.run([BASH, bash_path(root / 'scripts' / script), *args], env=env,
                                    capture_output=True, text=True, encoding='utf-8',
                                    errors='replace', timeout=60)
            ensure = calls.read_text(encoding='utf-8').splitlines() if calls.exists() else []
            return result, ensure

    def test_ensure_ok_then_normal_run(self):
        for script, args in (('afk-night.sh', ()), ('afk-bot-watch.sh', ('--scheduled',))):
            with self.subTest(script):
                result, ensure = self.run_wrapper(script, *args)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(ensure, ['--min-idle 180'])
                self.assertIn('device-ensure ok', result.stdout)

    def test_ensure_fail_is_a_warning_and_the_normal_check_decides(self):
        for script in ('afk-night.sh', 'afk-bot-watch.sh'):
            with self.subTest(script):
                result, ensure = self.run_wrapper(script, FAKE_ENSURE_RC='8')
                self.assertEqual(result.returncode, 2)             # game process not found, as before
                self.assertIn('WARN device-ensure rc=8', result.stdout)
                self.assertEqual(len(ensure), 1)

    def test_ensure_skipped_by_idle_gate(self):
        result, ensure = self.run_wrapper('afk-night.sh', FAKE_ENSURE_RC='4')
        self.assertEqual(result.returncode, 2)
        self.assertIn('device-ensure skipped (idle gate', result.stdout)

    def test_game_reachable_no_ensure(self):
        for script in ('afk-night.sh', 'afk-bot-watch.sh'):
            with self.subTest(script):
                result, ensure = self.run_wrapper(script, game_up=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(ensure, [])

    def test_switch_off(self):
        result, ensure = self.run_wrapper('afk-night.sh', AFK_DEVICE_ENSURE='0')
        self.assertEqual((result.returncode, ensure), (2, []))

    def test_manual_watch_run_forces(self):
        result, ensure = self.run_wrapper('afk-bot-watch.sh')
        self.assertEqual(ensure, ['--force'])


if __name__ == '__main__':
    unittest.main()
