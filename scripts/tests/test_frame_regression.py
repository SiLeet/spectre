"""Replay frame_manifest.json: classifier verdicts on real frames must not drift.

Frames live under .spectre/ (local, gitignored). A missing or replaced frame
(rotation/prune) is skipped with a warning, never a failure. Pruned dirs are
re-found under .spectre/trash (F16 moves them there) until trash is emptied.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402
import afk_stage_push as sp  # noqa: E402
from make_frame_manifest import MANIFEST, REPO, load_rgb, sha16  # noqa: E402


class FrameRegression(unittest.TestCase):
    def test_manifest_verdicts(self):
        entries = json.loads(MANIFEST.read_text(encoding='utf-8'))
        checked, skipped = 0, []
        for e in entries:
            path = REPO / e['relpath']
            if not path.exists():
                # F16 prune moves old shots-* dirs to .spectre/trash - keep
                # coverage until trash is emptied instead of skipping blind
                path = REPO / '.spectre' / 'trash' / Path(e['relpath']).relative_to('.spectre')
                if not path.exists():
                    skipped.append(f"missing {e['relpath']}")
                    continue
            if sha16(path) != e['sha16']:
                skipped.append(f"changed {e['relpath']}")
                continue
            img = load_rgb(path)
            with self.subTest(frame=e['relpath']):
                self.assertEqual(v.classify(img), e['classify'])
                self.assertEqual(sp.classify_battle(img), e['battle_class'])
            checked += 1
        for s in skipped:
            print(f'WARN: skipped {s}', file=sys.stderr)
        print(f'\nframe regression: checked={checked} skipped={len(skipped)} '
              f'manifest={len(entries)}', file=sys.stderr)


if __name__ == '__main__':
    unittest.main()
