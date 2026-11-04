"""T101b: milestone level-up preview + widened cost line (live 2026-11-04, shots-43184).

At hand level 100 the single charge tap opened an 'Upgrade 100 >> 101' preview instead of
levelling; the detail's level box was gone, so the read-back said None -> 'undetermined'.
The preview's own Level Up bar takes the same single charge. Its cost line sits ~100 px
further left, so COST_BOX at x 900 clipped the gold pair ('third pair gone' was the crop).
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402
import afk_hero_level as hl  # noqa: E402
from make_frame_manifest import REPO  # noqa: E402

import test_daily_leveling as dl  # noqa: E402  (module import: its tests are not collected twice)
from test_daily_leveling import COVERED, SCAN, hand  # noqa: E402


class PreviewCharge(unittest.TestCase):
    """Borrows DailyCharge's harness (hl_start WORLD, entry, scan 710/840, pre, post)."""
    FRAMES = dl.DailyCharge.FRAMES
    run_level = dl.DailyCharge.run_level

    def preview(self, name, frm):
        return {f'{name}_pv': ['Level', 'Level', f'{frm}? {frm + 1}']}

    def test_preview_is_confirmed_once_and_read_back(self):
        ocr = {**SCAN, **hand('hl_daily_pre0', 78, COVERED), **self.preview('hl_daily_post0', 78),
               **self.preview('hl_daily_post0_ok', 79)}          # still open, now 79 >> 80
        dev, rc, _ = self.run_level(ocr, frames=self.FRAMES + ['UNKNOWN'])
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps.count(hl.LEVEL_X1), 2)         # tap + confirm = ONE level
        self.assertEqual(dev.taps[-4:], [hl.LEVEL_X1, hl.LEVEL_X1, ('key', 4), ('key', 4)])
        self.assertIn('level-up preview 78 -> 79 — confirming inside it', dev.out.getvalue())
        self.assertIn('charged: hand 840 level 78 -> 79', dev.out.getvalue())

    def test_preview_closed_after_confirm_reads_the_detail(self):
        ocr = {**SCAN, **hand('hl_daily_pre0', 78, COVERED), **self.preview('hl_daily_post0', 78),
               **hand('hl_daily_post0_ok', 79)}
        dev, rc, _ = self.run_level(ocr, frames=self.FRAMES + ['UNKNOWN'])
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps[-3:], [hl.LEVEL_X1, hl.LEVEL_X1, ('key', 4)])

    def test_preview_of_another_level_is_never_confirmed(self):
        ocr = {**SCAN, **hand('hl_daily_pre0', 78, COVERED), **self.preview('hl_daily_post0', 90)}
        dev, rc, _ = self.run_level(ocr)
        self.assertEqual(rc, 1)
        self.assertEqual(dev.taps.count(hl.LEVEL_X1), 1)

    def test_direct_level_needs_no_confirm(self):
        # 101 -> 102 style: the tap levels at once (T101: two taps were two levels)
        ocr = {**SCAN, **hand('hl_daily_pre0', 78, COVERED), **hand('hl_daily_post0', 79)}
        dev, rc, _ = self.run_level(ocr)
        self.assertEqual(rc, 0)
        self.assertEqual(dev.taps.count(hl.LEVEL_X1), 1)


class RealPreviewFrames(unittest.TestCase):
    """Real WinRT OCR on copies of the live frames (skip when missing)."""

    def setUp(self):
        src = REPO / '.spectre' / 'shots-43184'
        if not src.exists():
            src = Path(r'C:\Users\Sigi\spectre\.spectre\shots-43184')     # worktrees: main checkout
        if not (src / 'hl_daily_post0.png').exists():
            raise unittest.SkipTest('frames missing: .spectre/shots-43184')
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        p = mock.patch.object(v, 'TMP', self.tmp)              # crops never land in .spectre
        p.start()
        self.addCleanup(p.stop)
        for name in ('hl_daily_pre0_w2', 'hl_daily_post0', 'hl_daily_post0_rr2'):
            shutil.copy(src / f'{name}.png', self.tmp / f'{name}.png')

    def test_preview_detected_only_on_the_preview(self):
        self.assertEqual(hl.preview_levels('hl_daily_post0'), (100, 101))
        self.assertEqual(hl.preview_levels('hl_daily_post0_rr2'), (100, 101))
        self.assertIsNone(hl.preview_levels('hl_daily_pre0_w2'))
        self.assertEqual(hl.slot_level('hl_daily_pre0_w2'), 100)

    def test_cost_line_keeps_the_gold_pair_in_the_preview(self):
        gold = (8534000.0, 9360.0)
        self.assertIn(gold, hl.cost_pairs('hl_daily_pre0_w2'))
        self.assertIn(gold, hl.cost_pairs('hl_daily_post0'))   # clipped at COST_BOX x 900
        self.assertEqual(hl.cost_pairs('hl_daily_pre0_w2'), hl.cost_pairs('hl_daily_post0'))


if __name__ == '__main__':
    unittest.main()
