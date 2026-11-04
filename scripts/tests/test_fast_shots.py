"""T76 shot / OCR fast paths: raw screencap + PNG fallback, region OCR."""
from __future__ import annotations

import io
import struct
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from PIL import Image  # noqa: E402

import afk_claim_vision as v  # noqa: E402
import afk_hero_level as hl  # noqa: E402

ARTIFACTS = Path(__file__).resolve().parent / '.artifacts' / 'fast_shots'


def raw(w: int, h: int, rgba=(10, 20, 30, 255), header: int = 16, fmt: int = 1) -> bytes:
    head = struct.pack('<III', w, h, fmt) + b'\0' * (header - 12)
    return head + bytes(rgba) * (w * h)


def png_bytes(w=8, h=4, rgb=(1, 2, 3)) -> bytes:
    buf = io.BytesIO()
    Image.new('RGB', (w, h), rgb).save(buf, 'PNG')
    return buf.getvalue()


class RawParse(unittest.TestCase):
    def test_both_header_sizes(self):
        for header in (12, 16):
            img = v._raw_to_image(raw(4, 3, header=header))
            self.assertEqual((img.size, img.getpixel((0, 0))), ((4, 3), (10, 20, 30)))

    def test_rejects_wrong_size_or_format(self):
        self.assertIsNone(v._raw_to_image(raw(4, 3)[:-1]))            # truncated
        self.assertIsNone(v._raw_to_image(raw(4, 3, header=20)))      # unknown header
        self.assertIsNone(v._raw_to_image(raw(4, 3, fmt=5)))          # not RGBA_8888
        self.assertIsNone(v._raw_to_image(b'\x89PNG...'))
        self.assertIsNone(v._raw_to_image(png_bytes()))


class Shot(unittest.TestCase):
    def setUp(self):
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        p = mock.patch.object(v, 'TMP', ARTIFACTS)
        p.start()
        self.addCleanup(p.stop)

    def test_raw_fast_path_saves_png_for_ocr(self):
        done = subprocess.CompletedProcess([], 0, raw(1920, 1080), b'')
        with mock.patch.object(v.subprocess, 'run', return_value=done) as run:
            img = v.shot('fast')
        self.assertEqual(img.size, (1920, 1080))
        self.assertNotIn('-p', run.call_args.args[0])                  # raw, not PNG
        with Image.open(ARTIFACTS / 'fast.png') as saved:
            self.assertEqual(saved.size, (1920, 1080))

    def test_png_fallback_when_raw_is_not_raw(self):
        def run(cmd, **kw):
            if '-p' in cmd:
                kw['stdout'].write(png_bytes())
                return subprocess.CompletedProcess(cmd, 0)
            return subprocess.CompletedProcess(cmd, 0, b'garbage', b'')
        with mock.patch.object(v.subprocess, 'run', side_effect=run) as m:
            img = v.shot('fallback')
        self.assertEqual((img.size, m.call_count), ((8, 4), 2))

    def test_png_fallback_failure_still_raises(self):
        def run(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 1, b'', b'')
        with mock.patch.object(v.subprocess, 'run', side_effect=run):
            with self.assertRaises(RuntimeError):
                v.shot('dead')


class OcrRegion(unittest.TestCase):
    def setUp(self):
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        p = mock.patch.object(v, 'TMP', ARTIFACTS)
        p.start()
        self.addCleanup(p.stop)
        Image.new('RGB', (1920, 1080), (50, 50, 50)).save(ARTIFACTS / 'detail.png')

    def test_crop_is_the_box(self):
        seen = []
        with mock.patch.object(v, 'ocr_png', side_effect=lambda p: seen.append(p) or ['81']):
            self.assertEqual(v.ocr_region('detail', (1240, 810, 1560, 930)), ['81'])
        with Image.open(seen[0]) as crop:
            self.assertEqual(crop.size, (320, 120))
        self.assertEqual(seen[0].name, 'detail_r.png')

    def test_missing_shot_is_empty(self):
        with mock.patch.object(v, 'ocr_png') as ocr:
            self.assertEqual(v.ocr_region('nope', (0, 0, 10, 10)), [])
        ocr.assert_not_called()

    def test_slot_level_reads_the_upscaled_box(self):
        # T101: slot_level OCRs only LEVEL_NUM_BOX, LEVEL_SCALE x upscaled, saved as `{name}_lv`
        seen = []
        with mock.patch.object(v, 'ocr_png', side_effect=lambda p: seen.append(p) or ['Level', '81']):
            self.assertEqual(hl.slot_level('detail'), 81)
        self.assertEqual(seen[0].name, 'detail_lv.png')
        with Image.open(seen[0]) as crop:
            left, top, right, bottom = hl.LEVEL_NUM_BOX
            self.assertEqual(crop.size, ((right - left) * hl.LEVEL_SCALE, (bottom - top) * hl.LEVEL_SCALE))
        with mock.patch.object(v, 'ocr_png', return_value=[]):
            self.assertIsNone(hl.slot_level('detail'))


if __name__ == '__main__':
    unittest.main()
