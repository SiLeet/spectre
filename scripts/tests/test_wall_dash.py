"""afk-wall-dash robustness: broken JSONL lines and nulls must not kill the widget."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'afk-wall-dash.py'
ARTIFACTS = Path(__file__).resolve().parent / '.artifacts' / 'wall_dash'

_spec = importlib.util.spec_from_file_location('afk_wall_dash', SCRIPT)
wd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wd)

# real producer record shape (afk_stage_push.wall_report)
REAL = {"ts": "2026-11-02T01:12:44+00:00", "reason": "battle_1_no_victory_prep",
        "stage": 254, "power": 74986, "png": None, "ocr_ok": True, "lines": []}
NULLS = {"ts": None, "reason": "wall_defeat_initial", "stage": None, "power": None}


class DashCase(unittest.TestCase):
    def setUp(self):
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        self.jsonl = ARTIFACTS / f'{self._testMethodName}.log'
        self.state = ARTIFACTS / f'{self._testMethodName}.state.json'
        self.out = ARTIFACTS / f'{self._testMethodName}.html'
        for f in (self.jsonl, self.state, self.out):
            f.unlink(missing_ok=True)
        for name, val in (('JSONL', str(self.jsonl)), ('STATE', str(self.state)),
                          ('OUT', str(self.out))):
            p = mock.patch.object(wd, name, val)
            p.start()
            self.addCleanup(p.stop)

    def write(self, *lines: str):
        self.jsonl.write_text(''.join(ln + '\n' for ln in lines), encoding='utf-8')

    def run_main(self) -> str:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            wd.main()
        return buf.getvalue()


class LoadEvents(DashCase):
    def test_missing_file(self):
        self.assertEqual(wd.load_events(str(self.jsonl)), ([], []))

    def test_empty_file(self):
        self.write()
        self.assertEqual(wd.load_events(str(self.jsonl)), ([], []))

    def test_blank_lines_are_not_bad(self):
        self.write('', '   ', json.dumps(REAL))
        evs, bad = wd.load_events(str(self.jsonl))
        self.assertEqual((len(evs), bad), (1, []))

    def test_broken_json_collected(self):
        self.write('{"ts": 1, "reason": ', 'not json')
        evs, bad = wd.load_events(str(self.jsonl))
        self.assertEqual(evs, [])
        self.assertEqual(bad, ['{"ts": 1, "reason": ', 'not json'])

    def test_non_object_json_is_bad(self):
        self.write('null', '123', '[1,2,3]', '"str"', json.dumps(REAL))
        evs, bad = wd.load_events(str(self.jsonl))
        self.assertEqual(evs, [REAL])
        self.assertEqual(len(bad), 4)

    def test_non_dict_state_ignored(self):
        self.state.write_text('[1,2]', encoding='utf-8')
        self.write(json.dumps(REAL))
        cur, evs, bad = wd.load()
        self.assertEqual((cur, len(evs), bad), ({}, 1, []))


class Render(DashCase):
    def test_mixed_valid_and_broken(self):
        self.write(json.dumps(REAL), 'garbage{', 'null', json.dumps(NULLS))
        out = self.run_main()
        self.assertIn('(2 events, skipped 2 bad lines)', out)
        html = self.out.read_text(encoding='utf-8')
        self.assertIn('74,986', html)

    def test_null_fields(self):
        self.state.write_text(json.dumps({"stage": None, "power": None}), encoding='utf-8')
        self.write(json.dumps(NULLS))
        out = self.run_main()
        self.assertIn('(1 events, skipped 0 bad lines)', out)
        html = self.out.read_text(encoding='utf-8')
        self.assertNotIn('>None<', html)

    def test_string_power(self):
        self.write(json.dumps({**REAL, "power": "74986"}),
                   json.dumps({**REAL, "power": "n/a"}))
        self.run_main()
        html = self.out.read_text(encoding='utf-8')
        self.assertIn('<td>74,986</td>', html)
        self.assertIn('<td>—</td>', html)

    def test_only_bad_lines_writes_nothing(self):
        self.write('null', 'garbage')
        out = self.run_main()
        self.assertIn('no events, skipped 2 bad lines', out)
        self.assertFalse(self.out.exists())

    def test_fmt_int(self):
        self.assertEqual([wd.fmt_int(x) for x in (74986, '74986', 74986.0, None, 'n/a', [])],
                         ['74,986', '74,986', '74,986', '—', '—', '—'])



class F17ReasonFamilies(DashCase):
    REAL_REASONS = ['auto_defeat_after_20s', 'auto_prep_stop_3skipped_34s', 'auto_timeout_14skipped',
                    'auto_timeout_8skipped_end_unknown', 'battle_1_no_victory_prep',
                    'wall_defeat_initial', 'single_push_complete_2of3', 'battle_2_defeat', None]

    def test_families(self):
        self.assertEqual([wd.reason_family(r) for r in self.REAL_REASONS],
                         ['wall', 'wall', 'other', 'other', 'other', 'wall', 'progress', 'wall', 'other'])

    def test_counters_rendered(self):
        self.write(*(json.dumps({**REAL, 'reason': r}) for r in self.REAL_REASONS))
        self.run_main()
        html = self.out.read_text(encoding='utf-8')
        self.assertIn('<div class="v">4</div><div class="l">Walls</div>', html)
        self.assertIn('<div class="v">1</div><div class="l">Progress</div>', html)


if __name__ == '__main__':
    unittest.main()
