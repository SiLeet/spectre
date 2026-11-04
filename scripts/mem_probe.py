#!/usr/bin/env python3
"""mem_probe — generic offset hunt around `spectre hot` (T79).

  scan(value 1) -> candidates -> change the value in-game -> scan(value 2)
  -> ... -> intersection of the addresses -> offsets.yaml proposal

Log-only: never writes memory, never edits an offsets file; the proposal goes
to stdout. Every scan is bounded (timeout + --limit); a scan that hit --limit
is flagged truncated and caps the confidence at 'low'.

  python scripts/mem_probe.py --pid 4321 --base 0x724DF0000000 --name gold \\
      --type u32 --values 9963 12300            # Enter between the scans
  ... --no-prompt --wait 20                      # or sleep between the scans

Exit: 0 proposal (>=1 candidate), 3 no candidate, 2 spectre failed, 1 bad args.
"""
from __future__ import annotations

import argparse
import json
import re
import struct
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SPECTRE = REPO / 'target' / 'release' / 'spectre.exe'
TYPES = {'u32': ('<I', 'U32'), 'i32': ('<i', 'I32'), 'u64': ('<Q', 'U64'), 'i64': ('<q', 'I64')}
SCAN_TIMEOUT = 1200    # hot greps the whole heap on the device (measured 13m39s, 11/2026)
MAX_SHOWN = 10


def encode(value: int, typ: str) -> str:
    return struct.pack(TYPES[typ][0], value).hex()


def hot_scan(pid: str, value: int, typ: str, base: str, limit: int) -> list[int] | None:
    """Addresses of `value` (>= base) via spectre hot. None on failure."""
    cmd = [str(SPECTRE), 'hot', str(pid), encode(value, typ), '--adb',
           '--base', base, '--limit', str(limit), '--json']
    try:
        p = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=SCAN_TIMEOUT)
    except (subprocess.TimeoutExpired, OSError):
        return None
    if p.returncode != 0:
        return None
    try:
        text = p.stdout
        cut = text.find('\n[')          # tracing WARN lines (ANSI) may precede the JSON array
        if cut >= 0:
            text = text[cut + 1:]
        else:
            text = re.sub(r'\x1b\[[0-9;]*m', '', text)
            cut = text.find('[')
            if cut < 0:
                return None
            text = text[cut:]
        return [int(a, 16) for a in json.loads(text)]
    except (ValueError, TypeError):
        return None


def confidence(n: int, scans: int, truncated: bool) -> str:
    if n == 0:
        return 'none'
    if truncated:
        return 'low'
    if n == 1:
        return 'high' if scans >= 2 else 'medium'
    return 'medium' if n <= 3 else 'low'


def proposal(name: str, typ: str, base: int, cands: list[int], values: list[int],
             counts: list[int], conf: str, truncated: bool) -> str:
    """offsets.yaml field snippet (paste under the structure whose base_offset = base)."""
    trail = ' -> '.join(f'{c}' for c in counts)
    head = [f'# mem_probe {time.strftime("%Y-%m-%d")}: {name} {typ} '
            f'values {" -> ".join(map(str, values))}',
            f'# candidates per scan: {trail} -> intersection {len(cands)}; '
            f'confidence {conf}{" (TRUNCATED scan)" if truncated else ""}',
            f'# base {base:#x}; verify with an action-diff before use']
    if not cands:
        return '\n'.join(head + ['# no candidate survived the intersection'])
    first, rest = cands[0], cands[1:MAX_SHOWN]
    body = [f'      - name: "{name}"',
            f'        field_type: {TYPES[typ][1]}',
            f'        offset: {first - base:#x}   # {conf.upper()} ({len(cands)} candidate(s))',
            f'        desc: "mem_probe: {" -> ".join(map(str, values))}, confidence {conf}"']
    alts = [f'      # alt: offset {a - base:#x}' for a in rest]
    if len(cands) > MAX_SHOWN:
        alts.append(f'      # ... {len(cands) - MAX_SHOWN} more')
    return '\n'.join(head + body + alts)


def probe(pid: str, base: str, name: str, typ: str, values: list[int], limit: int,
          between) -> tuple[int, str]:
    """(rc, report). `between(i)` runs before scan i>0 (prompt / sleep / test hook)."""
    base_int = int(base, 16)
    survivors: set[int] | None = None
    counts: list[int] = []
    truncated = False
    for i, val in enumerate(values):
        if i:
            between(i)
        hits = hot_scan(pid, val, typ, base, limit)
        if hits is None:
            return 2, f'spectre hot failed for value {val} (binary? pid? root? adb?)'
        print(f'  scan {i + 1}: {val} -> {len(hits)} match(es)', flush=True)
        counts.append(len(hits))
        truncated |= limit > 0 and len(hits) >= limit
        survivors = set(hits) if survivors is None else survivors & set(hits)
    cands = sorted(survivors or ())
    conf = confidence(len(cands), len(values), truncated)
    return (0 if cands else 3), proposal(name, typ, base_int, cands, values, counts, conf, truncated)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--pid', required=True)
    ap.add_argument('--base', required=True, help='heap base (hex); offsets are relative to it')
    ap.add_argument('--name', required=True, help='field name for the proposal')
    ap.add_argument('--type', default='u32', choices=sorted(TYPES))
    ap.add_argument('--values', type=int, nargs='+', required=True,
                    help='the value before, then after each in-game change (>= 2)')
    ap.add_argument('--limit', type=int, default=20000, help='max matches per scan')
    ap.add_argument('--no-prompt', action='store_true', help='sleep --wait instead of Enter')
    ap.add_argument('--wait', type=float, default=15.0)
    a = ap.parse_args(argv)
    if len(a.values) < 2 or any(x == y for x, y in zip(a.values, a.values[1:])):
        print('need >= 2 values and each change must alter the value', file=sys.stderr)
        return 1
    try:
        int(a.base, 16)
        [encode(x, a.type) for x in a.values]
    except (ValueError, struct.error) as e:
        print(f'bad --base/--values: {e}', file=sys.stderr)
        return 1

    def between(i: int) -> None:
        msg = f'change {a.name} in-game to {a.values[i]}'
        if a.no_prompt:
            print(f'  {msg} — waiting {a.wait:g}s', flush=True)
            time.sleep(a.wait)
        else:
            input(f'  {msg}, then press Enter ')

    rc, report = probe(a.pid, a.base, a.name, a.type, a.values, a.limit, between)
    print(report)
    return rc


if __name__ == '__main__':
    sys.exit(main())
