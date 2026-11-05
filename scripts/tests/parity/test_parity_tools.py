"""Self-tests of the E0 parity tooling (not part of the bot suite: run with
`python -m unittest discover -s scripts/tests/parity`; lives here so it never changes py_tree)."""
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from PIL import Image  # noqa: E402

import export_goldens as eg  # noqa: E402
import freeze_corpus as fc  # noqa: E402


class FrameKey(unittest.TestCase):
    def test_key_depends_on_pixels_not_png_encoding(self):
        img = Image.new('RGB', (4, 3), (10, 20, 30))
        img.putpixel((1, 1), (200, 0, 7))
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / 'a.png', Path(d) / 'b.png'
            img.save(a, compress_level=0)
            img.save(b, compress_level=9)
            self.assertNotEqual(a.read_bytes(), b.read_bytes())
            with Image.open(a) as ia, Image.open(b) as ib:
                self.assertEqual(fc.frame_key(ia), fc.frame_key(ib))
        self.assertNotEqual(fc.frame_key(img), fc.frame_key(img.convert('RGBA')))   # mode is part of it

    def test_alpha_min_and_crc(self):
        rgba = Image.new('RGBA', (2, 2), (1, 2, 3, 255))
        self.assertEqual(fc.alpha_min(rgba), 255)
        rgba.putpixel((0, 0), (1, 2, 3, 9))
        self.assertEqual(fc.alpha_min(rgba), 9)
        self.assertIsNone(fc.alpha_min(Image.new('RGB', (2, 2))))
        import zlib
        self.assertEqual(fc.rgb_crc32(Image.new('RGB', (1, 1), (1, 2, 3))), zlib.crc32(b'\x01\x02\x03'))
        self.assertEqual(fc.rgb_crc32(Image.new('L', (1, 1), 5)), zlib.crc32(b'\x05\x05\x05'))   # via RGB


class Masks(unittest.TestCase):
    def test_clock_and_tmp_masks(self):
        t = tempfile.gettempdir()
        s = eg.mask_clock(f'--- round 1/1 15:23:45 on 2026-11-05 evidence {t}\\tmpab12\\x.png 1234-56')
        self.assertEqual(s, '--- round 1/1 <TIME> on <DATE> evidence <TMP>\\x.png 1234-56')
        self.assertEqual(eg.mask_tmp(t.replace('\\', '/') + '/parity-shots-q1/a.png'), '<TMP>/a.png')


class ProxyAndEncoding(unittest.TestCase):
    def test_proxy_records_and_stays_transparent(self):
        seen = []
        m = mock.MagicMock(return_value=7)
        p = eg.Proxy(m, lambda inner, a, k: seen.append((a, k)) or inner(*a, **k))
        self.assertEqual(p(1, x=2), 7)
        m.assert_called_once_with(1, x=2)
        p.assert_called_once_with(1, x=2)          # attribute access reaches the mock
        p.return_value = 9                         # and so do writes
        self.assertEqual(p(), 9)
        self.assertEqual(seen, [((1,), {'x': 2}), ((), {})])

    def test_enc_blob_and_opaque(self):
        rec = eg.Recorder(Path('.'), eg.Frames.__new__(eg.Frames))
        with mock.patch.object(eg, 'PARITY_DIR', Path(tempfile.mkdtemp())):
            big = rec.enc(b'\x01' * eg.BLOB_MIN)
            self.assertEqual(big['len'], eg.BLOB_MIN)
            self.assertTrue((eg.PARITY_DIR / 'blobs' / f'{big["blob"]}.bin').is_file())
        self.assertEqual(rec.enc(b'\x01\x02'), {'bytes': '0102'})
        opaque = []
        self.assertEqual(rec.enc((1, [2.5, None], {'a': object()}), opaque),
                         [1, [2.5, None], {'a': {'repr': 'object'}}])
        self.assertEqual(opaque, ['object'])
        self.assertEqual(rec.enc(float('nan')), {'float': 'nan'})


class Compare(unittest.TestCase):
    def test_compare_names_differing_records(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / 'a', Path(d) / 'b'
            for root, rc in ((a, 0), (b, 1)):
                (root / 'flows').mkdir(parents=True)
                (root / 'flows' / 'm.jsonl').write_text(
                    json.dumps({'header': {}}) + '\n' + json.dumps({'test': 't.x', 'i': 0, 'rc': rc}) + '\n',
                    encoding='utf-8')
            (a / 'only.json').write_text('{}', encoding='utf-8')
            diffs = eg.compare(a, b)
        self.assertEqual(diffs, [{'file': 'only.json', 'only_in_one_run': True},
                                 {'file': 'flows/m.jsonl', 'records': ['t.x#0'], 'n_records': 1}])


class Collect(unittest.TestCase):
    def test_skip_reason_feeds_frame_missing(self):
        res = fc._Result(io.StringIO(), True, 0)
        t = unittest.FunctionTestCase(lambda: None)
        res.addSkip(t, 'frame missing: .spectre/shots-1/x.png')
        res.addSkip(t, 'bash not available')
        self.assertEqual(res.missing, [(t.id(), '.spectre/shots-1/x.png')])


if __name__ == '__main__':
    unittest.main()
