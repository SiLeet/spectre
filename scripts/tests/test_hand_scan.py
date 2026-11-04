"""T72 hand-scan robustness; T101b: the scan polls like the charge (open_detail) instead of a
fixed 3 s shot + one 1.5 s retry (live shots-43184: hall / half-drawn detail caught)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_hero_level as hl  # noqa: E402
from fake_vision import FakeDevice  # noqa: E402
from test_parsers import HALL  # noqa: E402

from test_daily_leveling import hand  # noqa: E402  (T101: level = the `_lv` big-box crop)


class HandScanRetry(unittest.TestCase):
    def scan(self, hands, frames, ocr):
        dev = FakeDevice(self, frames, ocr=ocr)
        for p in (mock.patch.object(hl, 'key', lambda code, wait=1.5: dev.taps.append(('key', code))),
                  mock.patch.object(hl, 'HAND_XS', list(hands))):
            p.start()
            self.addCleanup(p.stop)
        return dev, hl.scan_hands()

    def test_detail_not_up_yet_is_polled(self):
        # live shots-43184/hl_scan_1210: still the hall 3 s after the tap
        dev, levels = self.scan([730], ['UNKNOWN', 'UNKNOWN'], hand('hl_scan_730_w1', 80))
        self.assertEqual(levels, {730: 80})
        self.assertEqual(dev.shots, ['hl_scan_730', 'hl_scan_730_w1'])
        self.assertEqual(dev.taps, [(730, hl.HANDS_Y), ('key', 4)])     # one tap, one back

    def test_detail_without_level_yet_gets_settled_rereads(self):
        # live shots-43184/hl_scan_1210b: detail drawn, level box not yet
        ocr = {'hl_scan_730': ['Affinity Not Pinned'], **hand('hl_scan_730_rr1', 80)}
        dev, levels = self.scan([730], ['UNKNOWN', 'UNKNOWN'], ocr)
        self.assertEqual(levels, {730: 80})
        self.assertEqual(dev.shots, ['hl_scan_730', 'hl_scan_730_rr1'])

    def test_permanently_none_is_skipped_cleanly(self):
        # bounded: DETAIL_POLLS shots for a hand that never shows a detail, then the next hand
        dev, levels = self.scan([730, 850], ['UNKNOWN'] * (hl.DETAIL_POLLS + 2),
                                {'hl_scan_hall_850': HALL, **hand('hl_scan_850', 78)})
        self.assertEqual(levels, {850: 78})
        self.assertEqual(dev.shots[hl.DETAIL_POLLS:], ['hl_scan_hall_850', 'hl_scan_850'])
        self.assertIn('scan hand 730: level None', dev.out.getvalue())

    def test_blocked_hand_is_reported_blocked_not_unreadable(self):
        # live shots-43184 730b/850b: 'within 10 levels' layout draws the level lower
        ocr = {'hl_scan_730': ['Affinity Not Pinned', 'Hands of Resonance must be within 10 levels of each other.']}
        dev, levels = self.scan([730], ['UNKNOWN'], ocr)
        self.assertEqual(levels, {})
        self.assertEqual(dev.shots, ['hl_scan_730'])
        self.assertIn('scan hand 730: blocked', dev.out.getvalue())

    def test_readable_first_time_no_retry(self):
        dev, levels = self.scan([730], ['UNKNOWN'], hand('hl_scan_730', 81))
        self.assertEqual((levels, dev.shots), ({730: 81}, ['hl_scan_730']))

    def test_measured_card_centres(self):
        self.assertEqual(hl.HAND_XS, [730, 850, 970, 1090, 1210])
        self.assertEqual(hl.HANDS_Y, 460)


if __name__ == '__main__':
    unittest.main()
