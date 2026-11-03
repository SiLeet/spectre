#!/usr/bin/env python3
"""Thin wrapper around the frida CLI for AFK Journey on BlueStacks (T63).

Builds and runs frida / frida-ps commands against the adb device
127.0.0.1:5555. Needs frida-tools on PATH (pip install frida-tools==<the
frida-server version>, see README.md); without it every command explains that
and exits 3. Prefer `attach` AFTER the game has logged in (anti-debug
checks run at start); `spawn` is there for completeness.

Usage:
  python hack/frida/attach.py ps
  python hack/frida/attach.py attach hack/frida/probe_timescale.js
  python hack/frida/attach.py attach hack/frida/set_timescale.js --params '{"scale": 1.5}'
  python hack/frida/attach.py spawn  hack/frida/probe_timescale.js
  ... [--serial 127.0.0.1:5555] [--match igame] [--pid N] [--dry-run]
Exit codes: 0 ok, 2 game process not found / not running / bad input,
3 frida-tools missing, otherwise frida's own exit code.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

SERIAL = os.environ.get('ADB_SERIAL', '127.0.0.1:5555')
MATCH = os.environ.get('AFK_PROCESS_MATCH', 'igame')   # same key the bot uses (spectre find igame)


def tool(name: str) -> str | None:
    return shutil.which(name)


def missing(name: str) -> int:
    print(f'ERROR: {name} not found on PATH. Install frida-tools matching the frida-server '
          f'version on the device (see hack/frida/README.md).', file=sys.stderr)
    return 3


def pick_target(ps_output: str, match: str) -> tuple[str, str, str] | None:
    """(pid, name, identifier) of the first `frida-ps -ai` row containing
    `match`; pid is '-' when the app is installed but not running."""
    for line in ps_output.splitlines():
        parts = line.split()
        if len(parts) < 3 or set(line.strip()) <= set('- ') or parts[0] == 'PID':
            continue
        if match.lower() in line.lower():
            return parts[0], ' '.join(parts[1:-1]), parts[-1]
    return None


def frida_ps(serial: str) -> str:
    return subprocess.run([tool('frida-ps') or 'frida-ps', '-D', serial, '-ai'],
                          capture_output=True, text=True, timeout=60).stdout


def build(mode: str, script: str, serial: str, target: str, params: str | None) -> list[str]:
    cmd = ['frida', '-D', serial]
    cmd += ['-f', target] if mode == 'spawn' else ['-p', target]
    cmd += ['-l', script]
    if params:
        cmd += ['-P', params]
    return cmd


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='frida helper for AFK Journey on BlueStacks')
    ap.add_argument('mode', choices=('ps', 'attach', 'spawn'))
    ap.add_argument('script', nargs='?', help='JS file to load (attach/spawn)')
    ap.add_argument('--serial', default=SERIAL)
    ap.add_argument('--match', default=MATCH, help='substring of the game identifier/name')
    ap.add_argument('--pid', default=None, help='attach to this pid (skips frida-ps)')
    ap.add_argument('--params', default=None, help='JSON handed to rpc.exports.init (frida -P)')
    ap.add_argument('--dry-run', action='store_true', help='print the frida command only')
    args = ap.parse_args(argv)

    if args.params:
        try:
            json.loads(args.params)
        except ValueError:
            print('ERROR: --params must be JSON, e.g. {"scale": 1.5}', file=sys.stderr)
            return 2
    if args.mode == 'ps':
        if tool('frida-ps') is None:
            return missing('frida-ps')
        print(frida_ps(args.serial), end='')
        return 0
    if not args.script or not os.path.isfile(args.script):
        print(f'ERROR: script not found: {args.script}', file=sys.stderr)
        return 2

    target = args.pid
    if target is None:
        if tool('frida-ps') is None:
            return missing('frida-ps')
        hit = pick_target(frida_ps(args.serial), args.match)
        if hit is None:
            print(f'ERROR: no app matching "{args.match}" on {args.serial} (frida-ps -ai)',
                  file=sys.stderr)
            return 2
        pid, name, ident = hit
        if args.mode == 'attach' and pid == '-':
            print(f'ERROR: {ident} is not running - start the game and log in first', file=sys.stderr)
            return 2
        target = ident if args.mode == 'spawn' else pid
        print(f'target: {name} ({ident}) pid={pid}')
    if args.mode == 'spawn':
        print('WARN: spawn runs the hooks before login - anti-debug checks see them; '
              'attach after login is the safer default', file=sys.stderr)

    cmd = build(args.mode, args.script, args.serial, target, args.params)
    print('cmd:', ' '.join(cmd))
    if args.dry_run:
        return 0
    exe = tool('frida')
    if exe is None:
        return missing('frida')
    return subprocess.run([exe, *cmd[1:]]).returncode


if __name__ == '__main__':
    sys.exit(main())
