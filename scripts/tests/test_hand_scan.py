"""T72 hand-scan robustness: one bounded re-read per unreadable hand."""
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

    def test_none_then_value_retry_reads_it(self):
        dev, levels = self.scan([730], ['UNKNOWN', 'UNKNOWN'], hand('hl_scan_730b', 80))
        self.assertEqual(levels, {730: 80})
        self.assertEqual(dev.shots, ['hl_scan_730', 'hl_scan_730b'])
        self.assertEqual(dev.taps, [(730, hl.HANDS_Y), ('key', 4)])     # one tap, one back
        self.assertIn('scan hand 730: level not readable — one retry', dev.out.getvalue())

    def test_permanently_none_is_skipped_cleanly(self):
        dev, levels = self.scan([730, 850], ['UNKNOWN'] * 4,
                                {'hl_scan_hall_850': HALL, **hand('hl_scan_850', 78)})
        self.assertEqual(levels, {850: 78})
        self.assertEqual(dev.shots, ['hl_scan_730', 'hl_scan_730b', 'hl_scan_hall_850', 'hl_scan_850'])
        self.assertEqual(dev.out.getvalue().count('one retry'), 1)     # bounded: once, and only for 730
        self.assertIn('scan hand 730: level None', dev.out.getvalue())

    def test_readable_first_time_no_retry(self):
        dev, levels = self.scan([730], ['UNKNOWN'], hand('hl_scan_730', 81))
        self.assertEqual((levels, dev.shots), ({730: 81}, ['hl_scan_730']))

    def test_measured_card_centres(self):
        self.assertEqual(hl.HAND_XS, [730, 850, 970, 1090, 1210])
        self.assertEqual(hl.HANDS_Y, 460)


if __name__ == '__main__':
    unittest.main()
