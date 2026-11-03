"""Generate frame_manifest.json: the locked vision verdicts on real screenshots.

The manifest pins what classify() (afk_claim_vision) and classify_battle()
(afk_stage_push) say about real frames under .spectre/. test_frame_regression
replays it, so any vision change that flips a verdict shows up offline.

REGENERATE ONLY ON PURPOSE: when a classifier change is meant to change
verdicts, re-run this script with --relabel (same frames, fresh verdicts),
review the diff of frame_manifest.json (every flipped entry is a behaviour
change) and commit it together with the change. A plain run re-picks frames.

Usage: python scripts/tests/make_frame_manifest.py [--per-dir 2] [--relabel] [--out PATH]
Frames stay local (.spectre/ is gitignored); only the text manifest is committed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from PIL import Image  # noqa: E402

import afk_claim_vision as v  # noqa: E402
import afk_stage_push as sp  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
MANIFEST = Path(__file__).resolve().parent / 'frame_manifest.json'
GLOBS = ('.spectre/shots-*', '.spectre/shots', '.spectre/screens')


def sha16(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def load_rgb(path: Path) -> Image.Image:
    with Image.open(path) as im:
        return im.convert('RGB')


def pick(pngs: list[Path], n: int) -> list[Path]:
    """n frames spread over the sorted dir listing (first, last, ...)."""
    if len(pngs) <= n:
        return pngs
    step = (len(pngs) - 1) / (n - 1) if n > 1 else 0
    return [pngs[round(i * step)] for i in range(n)]


def build(per_dir: int) -> list[dict]:
    entries = []
    for pattern in GLOBS:
        for d in sorted(REPO.glob(pattern)):
            if not d.is_dir():
                continue
            for png in pick(sorted(d.glob('*.png')), per_dir):
                try:
                    img = load_rgb(png)
                except OSError as exc:      # truncated screencap: not a test frame
                    print(f'skip {png}: {exc}', file=sys.stderr)
                    continue
                entries.append({'relpath': png.relative_to(REPO).as_posix(),
                                'size': list(img.size), 'sha16': sha16(png),
                                'classify': v.classify(img),
                                'battle_class': sp.classify_battle(img)})
    return entries


def relabel(entries: list[dict]) -> list[dict]:
    """Fresh verdicts for the frames already in the manifest (unchanged files only)."""
    out = []
    for e in entries:
        path = REPO / e['relpath']
        if path.exists() and sha16(path) == e['sha16']:
            img = load_rgb(path)
            e = {**e, 'classify': v.classify(img), 'battle_class': sp.classify_battle(img)}
        out.append(e)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--per-dir', type=int, default=2)
    ap.add_argument('--relabel', action='store_true',
                    help='keep the frame set, re-evaluate verdicts (deliberate behaviour change)')
    ap.add_argument('--out', type=Path, default=MANIFEST)
    args = ap.parse_args()
    if args.relabel:
        entries = relabel(json.loads(args.out.read_text(encoding='utf-8')))
    else:
        entries = build(args.per_dir)
    args.out.write_text(json.dumps(entries, indent=1) + '\n', encoding='utf-8')
    print(f'wrote {args.out} ({len(entries)} frames)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
