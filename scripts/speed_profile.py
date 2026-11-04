#!/usr/bin/env python3
"""speed_profile — Unity timeScale profile via the T63 frida kit (T80a, T85).

  python scripts/speed_profile.py on  [--scale 2|1.5|4] [--repeat-ms 1000]
  python scripts/speed_profile.py off                   # scale 1
  python scripts/speed_profile.py status [--json]       # probe_timescale.js (log-only)
  ... [--server-bin frida-server-<ver>-android-<abi>] [--port N] [--dry-run]

Steps: frida-tools on PATH (else rc 3) -> root check -> frida-server present
(push --server-bin if not) -> `frida --version` on the PC must equal
`<SERVER> --version` on the device -> server running and listening on PORT
(adb forward) -> game pid via frida-ps -> hack/frida/attach.py build() with
--params -> frida -q, bounded by a timeout. Live lane only (touches the device).
HERMES-SETUP: Hermes installs/starts frida-server live; SERVER and DEFAULT_PORT
below must match his setup (FRIDA_PORT / --port override the port).

`status` is read-only: it never pushes or starts frida-server - a dead server
is rc 4 (only the adb forward to PORT is set; it changes no device state).
`status --json` prints exactly ONE JSON object on stdout (all logs -> stderr):
  {"rc": 0, "frida": "17.2.0", "server": {"running": true, "version": "17.2.0",
   "port": 27142}, "timescale": 1.0, "error": null}
frida / server.version / timescale are null when unknown, error is null on success.
timescale null with rc 0 = "not observed" (LIVE: frida -q may quit before the
probe's 500 ms interval logs the value).

Without --repeat-ms the value is set once and frida detaches (the property
stays set until the game resets it). --repeat-ms eternalizes the script so it
re-applies the scale; OFF then only wins after a game restart.

Not part of the daily run (afk-bot-watch.sh / afk-night.sh never call it) until
it is proven live; any future hook must be gated by AFK_SPEED_PROFILE=1 (off by
default).

Exit codes:
  0  ok
  2  game not running / bad input
  3  frida missing: frida or frida-ps not on PATH, or `frida --version` answers nothing
  4  server dead/unreachable: no root, frida-server binary missing, not running
     (status) or did not start, not listening on PORT, PC/server version mismatch
     (both versions printed), adb push/forward failed, adb hung/unreachable
  5  frida (or frida-ps) timed out
  otherwise frida's own exit code after the attach.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402

KIT = v.REPO / 'hack' / 'frida'
_spec = importlib.util.spec_from_file_location('frida_attach', KIT / 'attach.py')
fa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fa)

# LIVE: HERMES-SETUP — path Hermes installs frida-server to (README step 4).
SERVER = '/data/local/tmp/frida-server'
# LIVE: HERMES-SETUP port — frida's default is 27042; a separate port keeps this
# server apart from any other frida-server on the host. Confirm frida-server
# accepts `-l 127.0.0.1:PORT` for the pushed version and that Hermes' server
# listens here (else rc 4 "does not listen"; override via FRIDA_PORT / --port).
DEFAULT_PORT = 27142
PORT = int(os.environ.get('FRIDA_PORT', str(DEFAULT_PORT)))
SCALES = (1.5, 2.0, 4.0)
FRIDA_TIMEOUT = 60
# LIVE: probe_timescale.js log line `[probe] Time.timeScale = <v>  (<icall> @ <ptr>)`
TIMESCALE_RE = re.compile(r'\[probe\] Time\.timeScale = ([-+0-9.eE]+)')


def sh(cmd: str, dry: bool, timeout: int = 30) -> str:
    """`adb shell su -c <cmd>` stdout (dry: print only, return '')."""
    if dry:
        print(f'  adb shell su -c "{cmd}"')
        return ''
    p = v.adb('shell', f'su -c "{cmd}"', timeout=timeout)
    return (p.stdout or b'').decode(errors='replace')


def new_state(port: int) -> dict:
    """The `status --json` object; run() / ensure_server() fill it in."""
    return {'rc': None, 'frida': None,
            'server': {'running': False, 'version': None, 'port': port},
            'timescale': None, 'error': None}


def fail(st: dict, rc: int, msg: str) -> int:
    print(f'ERROR: {msg}', file=sys.stderr)
    st['error'] = msg
    return rc


def pc_version() -> str:
    """`frida --version` on the PC ('' when it does not answer)."""
    try:
        return subprocess.run([fa.tool('frida') or 'frida', '--version'], capture_output=True,
                              text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ''


def listening(port: int) -> bool:
    """A LISTEN (state 0A) socket on `port` in the device's /proc/net/tcp{,6}."""
    out = sh('cat /proc/net/tcp /proc/net/tcp6', False)   # LIVE: readable via su on BlueStacks
    return any(len(f) > 3 and f[1].upper().endswith(f':{port:04X}') and f[3] == '0A'
               for f in (line.split() for line in out.splitlines()))


def ensure_server(port: int, server_bin: str | None, dry: bool, st: dict,
                  read_only: bool = False) -> int:
    """0 when frida-server (same version as the PC's frida, st['frida']) runs as
    root and listens on `port` with an adb forward; else 4 with st['error'].
    read_only (status): never push/start - a dead server is rc 4."""
    if not dry and 'uid=0' not in sh('id', dry):
        return fail(st, 4, 'no root on the device (BlueStacks root access, README step 3)')
    running = not dry and bool(sh('pidof frida-server', dry).strip())
    st['server']['running'] = running
    if running:
        print('  frida-server already running')
    elif read_only:
        if not dry:
            return fail(st, 4, 'frida-server not running (status never starts it - '
                        'run `on` or start it per README step 4)')
    else:
        if not dry and 'No such file' in sh(f'ls {SERVER} 2>&1', dry) and not server_bin:
            return fail(st, 4, f'{SERVER} missing on the device — pass --server-bin '
                        '(same version as `frida --version`)')
        if server_bin:
            if dry:
                print(f'  adb push {server_bin} {SERVER}')
            elif v.adb('push', server_bin, SERVER, timeout=120).returncode != 0:
                return fail(st, 4, 'adb push of frida-server failed')
            sh(f'chmod 755 {SERVER}', dry)
    server_ver = sh(f'{SERVER} --version', dry).strip()   # LIVE: prints the bare version
    st['server']['version'] = server_ver or None
    if not dry and not server_ver:
        return fail(st, 4, f'`{SERVER} --version` gave no output (binary missing or at '
                    'another path? HERMES-SETUP)')
    if not dry and server_ver != st['frida']:
        return fail(st, 4, f'frida version mismatch: PC frida {st["frida"]} != device '
                    f'frida-server {server_ver or "?"} ({SERVER}) — both must be equal '
                    '(README step 1)')
    if not running and not read_only:
        sh(f'{SERVER} -D -l 127.0.0.1:{port}', dry)      # LIVE: -D daemonizes, adb returns
        if not dry and not sh('pidof frida-server', dry).strip():
            return fail(st, 4, 'frida-server did not start')
        st['server']['running'] = not dry
    if dry:
        print('  adb shell su -c "cat /proc/net/tcp /proc/net/tcp6"   # LISTEN on port?')
    else:
        for i in range(3):          # LIVE: a just-started -D server may need a moment to bind
            if listening(port):
                break
            if i < 2:
                time.sleep(1)
        else:
            return fail(st, 4, f'frida-server runs but does not listen on 127.0.0.1:{port} '
                        '(Hermes setup on another port? pass --port / FRIDA_PORT)')
    if dry:
        print(f'  adb forward tcp:{port} tcp:{port}')
    elif v.adb('forward', f'tcp:{port}', f'tcp:{port}').returncode != 0:
        return fail(st, 4, 'adb forward failed')
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
        port: int = PORT, dry: bool = False, st: dict | None = None) -> int:
    st = new_state(port) if st is None else st
    if mode == 'off':
        scale, repeat_ms = 1.0, 0
    if fa.tool('frida') is None or fa.tool('frida-ps') is None:
        name = 'frida' if fa.tool('frida') is None else 'frida-ps'
        st['error'] = f'{name} not found on PATH'
        return fa.missing(name)
    if dry:
        print('  frida --version')
    else:
        st['frida'] = pc_version() or None
        if st['frida'] is None:
            return fail(st, 3, '`frida --version` answered nothing (broken frida-tools install)')
    rc = ensure_server(port, server_bin, dry, st, read_only=mode == 'status')
    if rc:
        return rc
    host = f'127.0.0.1:{port}'
    if dry:
        pid = '<pid>'
    else:
        try:
            hit = fa.pick_target(fa.frida_ps(fa.SERIAL, host), fa.MATCH)
        except subprocess.TimeoutExpired:
            return fail(st, 5, 'frida-ps timed out')
        if hit is None or hit[0] == '-':
            return fail(st, 2, 'game not running (start it and log in first)')
        pid = hit[0]
    cmd = frida_cmd(mode, pid, host, scale, repeat_ms)
    print('cmd:', ' '.join(cmd), flush=True)
    if dry:
        return 0
    try:
        p = subprocess.run([fa.tool('frida'), *cmd[1:]], capture_output=True, text=True,
                           timeout=FRIDA_TIMEOUT)
    except subprocess.TimeoutExpired:
        return fail(st, 5, f'frida did not return within {FRIDA_TIMEOUT}s')
    print(p.stdout, end='')
    if p.returncode != 0:
        st['error'] = f'frida exited {p.returncode}: ' + (p.stderr or '').strip()[-200:]
    if mode == 'status':
        m = TIMESCALE_RE.search(p.stdout or '')
        st['timescale'] = float(m.group(1)) if m else None
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
    ap.add_argument('--json', action='store_true',
                    help='status only: ONE JSON object on stdout, all logs on stderr')
    a = ap.parse_args(argv)
    if a.json and a.mode != 'status':
        ap.error('--json is only for status')
    st = new_state(a.port)
    with contextlib.redirect_stdout(sys.stderr) if a.json else contextlib.nullcontext():
        if a.server_bin and not Path(a.server_bin).is_file():
            st['rc'] = fail(st, 2, f'--server-bin not found: {a.server_bin}')
        else:
            try:
                st['rc'] = run(a.mode, a.scale, a.repeat_ms, a.server_bin, a.port, a.dry_run, st)
            except (subprocess.TimeoutExpired, OSError) as e:   # frida timeouts are caught in run()
                st['rc'] = fail(st, 4, f'adb hung or unreachable: {e}')
    if a.json:
        print(json.dumps(st))
    return st['rc']


if __name__ == '__main__':
    sys.exit(main())
