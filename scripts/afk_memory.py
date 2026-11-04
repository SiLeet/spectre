#!/usr/bin/env python3
"""afk_memory — one place for live memory values (T78).

snapshot(pid, base, yaml) runs `spectre read-batch --json` ONCE (bounded by a
timeout) and caches the result ~1.5 s, so several reads in one bot step cost
one process start instead of one `spectre dump` each.

power(pid, base) is the verified team_power. It does NOT re-implement the
drift guard: it calls v.memory_preflight (the only guard) and only swaps its
two reads (value + map-entry shape) for one read-batch of the stored slot.
If read-batch is unavailable (old release binary) it falls back to the
classic dump reads, so the result never gets worse than before.

Rule: a bot script that needs an offset value uses this module instead of
calling adb/spectre itself.

CLI:  python scripts/afk_memory.py --show --pid P --base 0x...
      [--offsets games/afk-journey/offsets.yaml]   (absolute base_offsets: --base 0x0)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402

SPECTRE = v.REPO / 'target' / 'release' / 'spectre.exe'
CACHE_TTL = 1.5
TIMEOUT = 30           # one attach + a handful of reads; a hung adb must not hang the bot

_snap_cache: dict[tuple, tuple[float, dict]] = {}
_power_cache: dict[tuple, tuple[float, tuple]] = {}


def _run_read_batch(pid: str, base: str, yaml_path: Path) -> list | None:
    """Raw read-batch call. None on timeout / rc != 0 / bad JSON."""
    try:
        p = subprocess.run([str(SPECTRE), 'read-batch', '--offsets', str(yaml_path),
                            '--pid', str(pid), '--base', str(base), '--adb', '--json'],
                           cwd=v.REPO, capture_output=True, text=True, timeout=TIMEOUT)
    except (subprocess.TimeoutExpired, OSError):
        return None
    if p.returncode != 0:
        return None
    try:
        data = json.loads(p.stdout)
    except ValueError:
        return None
    return data if isinstance(data, list) else None


def snapshot(pid: str, base: str, yaml_path: Path) -> dict[str, dict]:
    """{name: {address, value, fmt, valid, note?}} for every field; {} on failure.

    Cached CACHE_TTL seconds per (pid, base, yaml content); failures are not cached."""
    yaml_path = Path(yaml_path)
    try:
        key = (str(pid), str(base), yaml_path.read_text(encoding='utf-8'))
    except OSError:
        return {}
    now = time.monotonic()
    hit = _snap_cache.get(key)
    if hit and now - hit[0] < CACHE_TTL:
        return hit[1]
    rows = _run_read_batch(pid, base, yaml_path)
    if rows is None:
        return {}
    out = {r['name']: r for r in rows if isinstance(r, dict) and 'name' in r}
    _snap_cache[key] = (now, out)
    return out


def slot_yaml(offset: int) -> Path:
    """Runtime offsets YAML for the 16-byte power map entry at heap_base + offset."""
    path = v.TMP / f'afk_memory_slot_{offset:x}.yaml'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        'game: "afk-journey-runtime"\nversion: "0"\nstructures:\n'
        '  - name: "Slot"\n    base_offset: 0x0\n    fields:\n'
        f'      - {{ name: "lo", field_type: U32, offset: {offset:#x} }}\n'
        f'      - {{ name: "hi", field_type: U32, offset: {offset + 4:#x} }}\n'
        f'      - {{ name: "ptr", field_type: U64, offset: {offset + 8:#x} }}\n',
        encoding='utf-8')
    return path


def _slot_words(pid: str, base: str, offset: int) -> tuple[int, int, int] | None:
    snap = snapshot(pid, base, slot_yaml(offset))
    try:
        rows = [snap[f'Slot.{n}'] for n in ('lo', 'hi', 'ptr')]
    except KeyError:
        return None
    if not all(r.get('valid') for r in rows):
        return None
    return tuple(int(r['value']) for r in rows)


def read_value(pid: str, base: str, offset: int, width: int = 8) -> int | None:
    """Drop-in for v.read_power, served from the cached slot snapshot."""
    w = _slot_words(pid, base, offset)
    if w is None:
        return None
    raw = w[0].to_bytes(4, 'little') + w[1].to_bytes(4, 'little')
    return int.from_bytes(raw[:width], 'little', signed=True)


def read_entry(pid: str, base: str, offset: int, expected: int) -> bool | None:
    """Drop-in for v.read_power_entry_valid (same alignment + shape rule)."""
    if offset < 0 or offset % 8:
        return False
    w = _slot_words(pid, base, offset)
    if w is None:
        return None
    raw = b''.join(x.to_bytes(n, 'little') for x, n in zip(w, (4, 4, 8)))
    return w[0] == (int(expected) & 0xFFFF_FFFF) and v._ptr_after(raw, 0)


def power(pid: str, base: str) -> tuple[str, int | None]:
    """(status, value) exactly like v.memory_preflight; cached CACHE_TTL seconds."""
    key = (str(pid), str(base))
    now = time.monotonic()
    hit = _power_cache.get(key)
    if hit and now - hit[0] < CACHE_TTL:
        return hit[1]
    st = v.load_power_state()
    offset = int(st.get('offset', v.DEFAULT_POWER_OFFSET))
    if _slot_words(pid, base, offset) is not None:
        res = v.memory_preflight(pid, base, read_value=read_value, read_entry=read_entry)
    else:   # read-batch missing/failed: classic per-value dumps (pre-T78 behaviour)
        res = v.memory_preflight(pid, base)
    if res[0] != 'fail':
        _power_cache[key] = (now, res)
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--show', action='store_true', help='print a snapshot (+ power)')
    ap.add_argument('--pid', required=True)
    ap.add_argument('--base', required=True, help='hot heap base (hex)')
    ap.add_argument('--offsets', help='offsets YAML for the snapshot (default: power slot)')
    a = ap.parse_args(argv)
    if not a.show:
        ap.print_help()
        return 0
    if a.offsets:
        snap = snapshot(a.pid, a.base, Path(a.offsets))
    else:
        st = v.load_power_state()
        snap = snapshot(a.pid, a.base, slot_yaml(int(st.get('offset', v.DEFAULT_POWER_OFFSET))))
    if not snap:
        print('read-batch failed (binary without read-batch? dead pid? no adb?)')
    for name, r in snap.items():
        note = f"  ({r['note']})" if r.get('note') else ''
        print(f"{name:32} {r.get('address', '?'):>16} = {r.get('value')}{note}")
    if not a.offsets:
        status, val = power(a.pid, a.base)
        print(f'team_power: {status} {val}')
    return 0 if snap else 2


if __name__ == '__main__':
    sys.exit(main())
