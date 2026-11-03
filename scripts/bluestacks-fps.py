#!/usr/bin/env python3
"""Show / set / restore the frame-rate cap of one BlueStacks instance (T62).

Edits exactly one line of bluestacks.conf: bst.instance.<INSTANCE>.max_fps="N"
(layout read from this host's BlueStacks 5 conf, 2026-11-03). The first --set
keeps the untouched file as bluestacks.conf.bak; --restore puts it back.

BlueStacks reads the conf at instance start (and may rewrite it on exit), so
stop the instance before --set and restart it afterwards. Values above 60
only apply when the instance's enable_high_fps is "1" (BlueStacks' 'high frame
rate' switch) - this tool reports that flag but never changes it.

Usage:
  python scripts/bluestacks-fps.py --show
  python scripts/bluestacks-fps.py --set 120 [--instance Pie64] [--conf PATH]
  python scripts/bluestacks-fps.py --restore
Exit codes: 0 ok, 2 conf not found, 3 key missing / bad value, 4 no backup.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

FPS_MIN, FPS_MAX = 1, 240
CONF_DIRS = ('BlueStacks_nxt', 'BlueStacks_msi5', 'BlueStacks_msi2', 'BlueStacks')


def find_conf() -> Path | None:
    """BLUESTACKS_CONF, else the first existing %ProgramData%\\<dir>\\bluestacks.conf."""
    if os.environ.get('BLUESTACKS_CONF'):
        p = Path(os.environ['BLUESTACKS_CONF'])
        return p if p.is_file() else None
    root = Path(os.environ.get('ProgramData', r'C:\ProgramData'))
    for d in CONF_DIRS:
        p = root / d / 'bluestacks.conf'
        if p.is_file():
            return p
    return None


def key_re(instance: str, key: str) -> re.Pattern:
    return re.compile(rb'^(bst\.instance\.' + re.escape(instance.encode()) + rb'\.'
                      + re.escape(key.encode()) + rb'=")([^"\r\n]*)(")', re.M)


def get(raw: bytes, instance: str, key: str) -> str | None:
    m = key_re(instance, key).search(raw)
    return m.group(2).decode() if m else None


def set_fps(raw: bytes, instance: str, fps: int) -> bytes:
    """raw with only the instance's max_fps value replaced (bytes, line endings kept)."""
    new, n = key_re(instance, 'max_fps').subn(lambda m: m.group(1) + str(fps).encode() + m.group(3), raw, count=1)
    if n != 1:
        raise KeyError(f'bst.instance.{instance}.max_fps not found')
    return new


def write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_bytes(data)
    os.replace(tmp, path)


def player_running() -> bool:
    """HD-Player.exe up? (BlueStacks may rewrite the conf when it exits.)"""
    try:
        out = subprocess.run(['tasklist'], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return 'hd-player.exe' in out.lower()


def show(raw: bytes, instance: str) -> None:
    for key in ('max_fps', 'enable_high_fps', 'enable_vsync'):
        print(f'  {instance}.{key} = {get(raw, instance, key)}')


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Show/set/restore BlueStacks max_fps for one instance.')
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--show', action='store_true')
    mode.add_argument('--set', type=int, metavar='N', dest='fps')
    mode.add_argument('--restore', action='store_true')
    ap.add_argument('--instance', default=os.environ.get('BS_INSTANCE', 'Pie64'))
    ap.add_argument('--conf', type=Path, default=None, help='bluestacks.conf (default: auto-detect)')
    args = ap.parse_args(argv)

    conf = args.conf if args.conf else find_conf()
    if conf is None or not conf.is_file():
        print('ERROR: bluestacks.conf not found (set --conf or BLUESTACKS_CONF)', file=sys.stderr)
        return 2
    bak = conf.with_name(conf.name + '.bak')
    raw = conf.read_bytes()
    print(f'conf: {conf}')

    if args.show:
        show(raw, args.instance)
        return 0 if get(raw, args.instance, 'max_fps') is not None else 3

    if args.restore:
        if not bak.is_file():
            print(f'ERROR: no backup {bak}', file=sys.stderr)
            return 4
        before = get(raw, args.instance, 'max_fps')
        os.replace(bak, conf)
        print(f'restored from {bak.name}: max_fps {before} -> {get(conf.read_bytes(), args.instance, "max_fps")}')
        print(f'NOTE: restart the BlueStacks instance {args.instance} for the change to apply')
        return 0

    if not FPS_MIN <= args.fps <= FPS_MAX:
        print(f'ERROR: fps must be {FPS_MIN}..{FPS_MAX}', file=sys.stderr)
        return 3
    before = get(raw, args.instance, 'max_fps')
    try:
        new = set_fps(raw, args.instance, args.fps)
    except KeyError as exc:
        print(f'ERROR: {exc.args[0]} (instance name? see --show)', file=sys.stderr)
        return 3
    if player_running():
        print('WARN: BlueStacks is running - it may overwrite the conf on exit; '
              'stop the instance, then --set again if the value reverts')
    if not bak.is_file():                    # keep the ORIGINAL across repeated --set
        shutil.copy2(conf, bak)
        print(f'backup: {bak.name}')
    write_atomic(conf, new)
    print(f'{args.instance}.max_fps: {before} -> {args.fps}')
    if args.fps > 60 and get(new, args.instance, 'enable_high_fps') != '1':
        print(f'WARN: {args.instance}.enable_high_fps is not "1" - BlueStacks may cap at 60 '
              '(high frame rate switch in the instance settings)')
    print(f'NOTE: restart the BlueStacks instance {args.instance} for the change to apply')
    return 0


if __name__ == '__main__':
    sys.exit(main())
