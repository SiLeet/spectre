"""T82 region-OCR rollout: hall gate of afk_hero_level reads HALL_BOX first,
falls back to the full-frame OCR on a region miss (negatives unchanged).

Real-frame cases copy local .spectre/ frames (read-only) into .artifacts/ and
skip when the frames are gone (wave rule 7).
"""
from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402
import afk_hero_level as hl  # noqa: E402
from fake_vision import FakeDevice  # noqa: E402
from make_frame_manifest import REPO  # noqa: E402

ARTIFACTS = Path(__file__).resolve().parent / '.artifacts' / 'region_ocr'
HALL_HIT = ['Resonance Level: 100', 'of Resonance']        # real region read (shots-69252)


class HallBox(unittest.TestCase):
    def test_box_is_the_measured_one(self):
        self.assertEqual(hl.HALL_BOX, (740, 315, 1180, 405))

    def test_region_hit_skips_full_ocr(self):
        with mock.patch.object(v, 'ocr_region', return_value=HALL_HIT) as reg, \
                mock.patch.object(v, 'ocr_lines') as full:
            self.assertEqual(hl.hall_lines('hl_entry'), HALL_HIT)
        reg.assert_called_once_with('hl_entry', hl.HALL_BOX)
        full.assert_not_called()

    def test_region_miss_falls_back_to_full_ocr(self):
        detail = ['Lvl. 74', 'Affinity Not Pinned']
        for region in ([], ['Loki helped speed up your']):
            with mock.patch.object(v, 'ocr_region', return_value=region), \
                    mock.patch.object(v, 'ocr_lines', return_value=detail) as full:
                self.assertEqual(hl.hall_lines('hl_x'), detail)
            full.assert_called_once_with('hl_x')


class HallFlows(unittest.TestCase):
    def test_entry_region_hit_no_full_ocr(self):
        # T101: hl_start (town, region miss) -> hall tap -> hl_entry region hit
        dev = FakeDevice(self, ['WORLD', 'UNKNOWN'], ocr={'hl_entry': []})   # full OCR: no hall
        region = {'hl_entry': HALL_HIT}
        with mock.patch.object(v, 'ocr_region', side_effect=lambda n, b: region.get(n, [])), \
                mock.patch.object(sys, 'argv', ['afk_hero_level.py', '--dry-run']):
            self.assertEqual(hl.main(), 0)
        self.assertIn('hall open: Resonance Level: 100', dev.out.getvalue())
        self.assertEqual(dev.taps, [hl.HALL_BTN])

    def test_in_hall_region_hit(self):
        FakeDevice(self, ['UNKNOWN'])
        with mock.patch.object(v, 'ocr_region', return_value=HALL_HIT), \
                mock.patch.object(v, 'ocr_lines') as full:
            self.assertTrue(hl.in_hall('hl_scan_hall_850'))
        full.assert_not_called()

    def test_in_hall_detail_then_region_hit_after_back(self):
        dev = FakeDevice(self, ['UNKNOWN', 'UNKNOWN'],
                         ocr={'hl_scan_hall_850': ['Lvl. 74', 'Affinity Not Pinned']})
        region = {'hl_scan_hall_850_b': HALL_HIT}
        with mock.patch.object(v, 'ocr_region', side_effect=lambda n, b: region.get(n, [])), \
                mock.patch.object(hl, 'key', lambda code, wait=1.5: dev.taps.append(('key', code))):
            self.assertTrue(hl.in_hall('hl_scan_hall_850'))
        self.assertEqual(dev.shots, ['hl_scan_hall_850', 'hl_scan_hall_850_b'])
        self.assertEqual(dev.taps, [('key', 4)])

    def test_in_hall_world_reenter_region_hit(self):
        dev = FakeDevice(self, ['WORLD', 'UNKNOWN'], ocr={'hl_x': []})
        region = {'hl_x_reenter': HALL_HIT}
        with mock.patch.object(v, 'ocr_region', side_effect=lambda n, b: region.get(n, [])),                 mock.patch.object(v, 'ocr_lines', side_effect=lambda n: dev.ocr.get(n, [])) as full:
            self.assertTrue(hl.in_hall('hl_x'))
        self.assertEqual(dev.shots, ['hl_x', 'hl_x_reenter'])
        self.assertEqual(dev.taps, [hl.HALL_BTN])
        self.assertNotIn(mock.call('hl_x_reenter'), full.call_args_list)


class RealFrames(unittest.TestCase):
    """HALL_BOX on real frames: same hall verdict as the full-frame OCR."""

    HALL = ('shots-69252/hl_entry.png', 'shots-69252/hl_scan_hall_850.png')
    NOT_HALL = ('shots-69252/hl_scan_970.png',           # hero detail
                'shots-47096/hl_entry.png')              # quests panel (hall did not open)

    def setUp(self):
        if sys.platform != 'win32':
            self.skipTest('WinRT OCR is Windows-only')
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        p = mock.patch.object(v, 'TMP', ARTIFACTS)       # crops land here, never in .spectre
        p.start()
        self.addCleanup(p.stop)

    def region_hall(self, relpath: str) -> bool:
        src = REPO / '.spectre' / relpath
        if not src.exists():
            self.skipTest(f'frame missing: .spectre/{relpath}')
        name = relpath.replace('/', '_')[:-4]
        shutil.copyfile(src, ARTIFACTS / f'{name}.png')
        return hl.is_hall(v.ocr_region(name, hl.HALL_BOX))

    def test_hall_frames_hit(self):
        for rel in self.HALL:
            with self.subTest(rel=rel):
                self.assertTrue(self.region_hall(rel))

    def test_non_hall_frames_miss(self):
        for rel in self.NOT_HALL:
            with self.subTest(rel=rel):
                self.assertFalse(self.region_hall(rel))


if __name__ == '__main__':
    unittest.main()
