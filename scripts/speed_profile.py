#!/usr/bin/env python3
"""speed_profile — Unity timeScale profile via the T63 frida kit (T80a).

  python scripts/speed_profile.py on  [--scale 2|1.5|4] [--repeat-ms 1000]
  python scripts/speed_profile.py off                   # scale 1
  python scripts/speed_profile.py status                # probe_timescale.js (log-only)
  ... [--server-bin frida-server-<ver>-android-<abi>] [--port N] [--dry-run]

Steps: frida-tools on PATH (else rc 3) -> root check -> frida-server present
(push --server-bin if not) and running on its own port (adb forward) -> game
pid via frida-ps -> hack/frida/attach.py build() with --params -> frida -q,
bounded by a timeout. Live lane only (touches the device).

Without --repeat-ms the value is set once and frida detaches (the property
stays set until the game resets it). --repeat-ms eternalizes the script so it
re-applies the scale; OFF then only wins after a game restart.

Exit: 0 ok, 2 game not running / bad input, 3 frida missing,
4 root/frida-server not ready, 5 frida timed out.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402

KIT = v.REPO / 'hack' / 'frida'
_spec = importlib.util.spec_from_file_location('frida_attach', KIT / 'attach.py')
fa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fa)

SERVER = '/data/local/tmp/frida-server'
# LIVE: port — frida's default is 27042; a separate port keeps this server
# apart from any other frida-server on the host. Confirm frida-server accepts
# `-l 127.0.0.1:PORT` for the pushed version (frida-server --version must equal
# `frida --version` on the PC, README step 1).
PORT = int(os.environ.get('FRIDA_PORT', '27142'))
SCALES = (1.5, 2.0, 4.0)
FRIDA_TIMEOUT = 60


def sh(cmd: str, dry: bool, timeout: int = 30) -> str:
    """`adb shell su -c <cmd>` stdout (dry: print only, return '')."""
    if dry:
        print(f'  adb shell su -c "{cmd}"')
        return ''
    p = v.adb('shell', f'su -c "{cmd}"', timeout=timeout)
    return (p.stdout or b'').decode(errors='replace')


def ensure_server(port: int, server_bin: str | None, dry: bool) -> int:
    """0 when frida-server runs as root on `port` with an adb forward; else 4."""
    if not dry and 'uid=0' not in sh('id', dry):
        print('ERROR: no root on the device (BlueStacks root access, README step 3)', file=sys.stderr)
        return 4
    if not dry and sh('pidof frida-server', dry).strip():
        print('  frida-server already running')
    else:
        if not dry and 'No such file' in sh(f'ls {SERVER} 2>&1', dry) and not server_bin:
            print(f'ERROR: {SERVER} missing on the device — pass --server-bin '
                  '(same version as `frida --version`)', file=sys.stderr)
            return 4
        if server_bin:
            if dry:
                print(f'  adb push {server_bin} {SERVER}')
            elif v.adb('push', server_bin, SERVER, timeout=120).returncode != 0:
                print('ERROR: adb push of frida-server failed', file=sys.stderr)
                return 4
            sh(f'chmod 755 {SERVER}', dry)
        sh(f'{SERVER} -D -l 127.0.0.1:{port}', dry)      # LIVE: -D daemonizes, adb returns
        if not dry and not sh('pidof frida-server', dry).strip():
            print('ERROR: frida-server did not start', file=sys.stderr)
            return 4
    if dry:
        print(f'  adb forward tcp:{port} tcp:{port}')
    elif v.adb('forward', f'tcp:{port}', f'tcp:{port}').returncode != 0:
        print('ERROR: adb forward failed', file=sys.stderr)
        return 4
    return 0


def frida_cmd(mode: str, pid: str, host: str, scale: float | None, repeat_ms: int) -> list[str]:
    if mode == 'status':
        return fa.build('attach', str(KIT / 'probe_timescale.js'), fa.SERIAL, pid, None, host) + ['-q']
    params = {'scale': scale}
    if repeat_ms:
        params['repeat_ms'] = repeat_ms
    cmd = fa.build('attach', str(KIT / 'set_timescale.js'), fa.SERIAL, pid, json.dumps(params), host)
    # LIVE: -q quits after init(); --eternalize keeps the repeat timer in the game after detach
    return cmd + ['-q'] + (['--eternalize'] if repeat_ms else [])


def run(mode: str, scale: float = 2.0, repeat_ms: int = 0, server_bin: str | None = None,
        port: int = PORT, dry: bool = False) -> int:
    if mode == 'off':
        scale, repeat_ms = 1.0, 0
    if fa.tool('frida') is None or fa.tool('frida-ps') is None:
        return fa.missing('frida' if fa.tool('frida') is None else 'frida-ps')
    rc = ensure_server(port, server_bin, dry)
    if rc:
        return rc
    host = f'127.0.0.1:{port}'
    if dry:
        pid = '<pid>'
    else:
        try:
            hit = fa.pick_target(fa.frida_ps(fa.SERIAL, host), fa.MATCH)
        except subprocess.TimeoutExpired:
            return 5
        if hit is None or hit[0] == '-':
            print('ERROR: game not running (start it and log in first)', file=sys.stderr)
            return 2
        pid = hit[0]
    cmd = frida_cmd(mode, pid, host, scale, repeat_ms)
    print('cmd:', ' '.join(cmd), flush=True)
    if dry:
        return 0
    try:
        p = subprocess.run([fa.tool('frida'), *cmd[1:]], capture_output=True, text=True,
                           timeout=FRIDA_TIMEOUT)
    except subprocess.TimeoutExpired:
        print(f'ERROR: frida did not return within {FRIDA_TIMEOUT}s', file=sys.stderr)
        return 5
    print(p.stdout, end='')
    if repeat_ms and mode == 'on':
        print('NOTE: eternalized repeat — `off` only wins after a game restart')
    return p.returncode


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('mode', choices=('on', 'off', 'status'))
    ap.add_argument('--scale', type=float, default=2.0, choices=SCALES)
    ap.add_argument('--repeat-ms', type=int, default=0)
    ap.add_argument('--server-bin', default=None, help='local frida-server binary to push')
    ap.add_argument('--port', type=int, default=PORT)
    ap.add_argument('--dry-run', action='store_true', help='print adb/frida commands only')
    a = ap.parse_args(argv)
    if a.server_bin and not Path(a.server_bin).is_file():
        print(f'ERROR: --server-bin not found: {a.server_bin}', file=sys.stderr)
        return 2
    return run(a.mode, a.scale, a.repeat_ms, a.server_bin, a.port, a.dry_run)


if __name__ == '__main__':
    sys.exit(main())
