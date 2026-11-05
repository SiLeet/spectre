#!/usr/bin/env python3
"""E0a check: every frame in parity/frames.json exists in $SPECTRE_PARITY_DIR/frames
with the same key, size and mode (sha16 recomputed from the pixels).

Runs before every parity run under SPECTRE_PARITY=1. Exit 0 = corpus intact,
1 = missing or changed frames (each one is listed), 2 = no manifest.

  python scripts/tests/parity/verify_corpus.py [--quick]   (--quick: existence + PNG header only)
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from freeze_corpus import OUT, PARITY_DIR, frame_key  # noqa: E402


def png_size(path: Path) -> tuple[int, int] | None:
    with open(path, 'rb') as f:
        head = f.read(24)
    if head[:8] != b'\x89PNG\r\n\x1a\n' or head[12:16] != b'IHDR':
        return None
    return struct.unpack('>II', head[16:24])


def verify(manifest: Path, quick: bool = False) -> tuple[int, list[str]]:
    from PIL import Image
    data = json.loads(manifest.read_text(encoding='utf-8'))
    bad = []
    for e in data['frames']:
        p = PARITY_DIR / 'frames' / f'{e["sha16"]}.png'
        if not p.is_file():
            bad.append(f'MISSING {e["sha16"]} ({e["src"][0]["path"]})')
            continue
        if png_size(p) != (e['w'], e['h']):
            bad.append(f'SIZE {e["sha16"]}: {png_size(p)} != {(e["w"], e["h"])}')
            continue
        if quick:
            continue
        with Image.open(p) as im:
            key, mode = frame_key(im), im.mode
        if key != e['sha16'] or mode != e['mode']:
            bad.append(f'CHANGED {e["sha16"]}: key {key}, mode {mode}')
    return len(data['frames']), bad


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--manifest', type=Path, default=OUT / 'frames.json')
    ap.add_argument('--quick', action='store_true')
    a = ap.parse_args(argv)
    if not a.manifest.is_file():
        print(f'FAIL no manifest {a.manifest}')
        return 2
    n, bad = verify(a.manifest, a.quick)
    for line in bad:
        print('FAIL', line)
    print(f'verify_corpus: {n - len(bad)}/{n} ok ({PARITY_DIR / "frames"})')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
