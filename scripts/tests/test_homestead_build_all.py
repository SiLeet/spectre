"""T105A homestead build-all: tile grid / quest / queue detectors on real frames + FakeVision flows."""
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
import afk_homestead as hs  # noqa: E402
from fake_vision import FakeDevice, frame  # noqa: E402
from make_frame_manifest import load_rgb  # noqa: E402
from test_homestead import (CHECK, HERMES, MARK, MENU, RES, RING, SPECTRE, TOAST, WORLD,  # noqa: E402
                            cnt, paint)

WHITE = (255, 255, 255)
MENU_PROBES = [(hs.EXIT_BTN, 12, (198, 187, 183)), (hs.BUILD_TAB, 12, (146, 183, 134)),
               (hs.LAYOUT_TAB, 12, (230, 223, 221))]
MENU_GREY = lambda: paint('UNKNOWN', MENU_PROBES + [(hs.PRODUCTION_TAB, 12, (145, 184, 138))])  # noqa: E731
MENU2 = lambda: paint('UNKNOWN', MENU_PROBES + [(hs.PRODUCTION_TAB, 12, (145, 184, 138)),  # noqa: E731
                                                ((512, 786), 40, WHITE), ((624, 786), 40, WHITE)])
FUNC = lambda: paint('UNKNOWN', MENU_PROBES + [(hs.PRODUCTION_TAB, 12, (223, 220, 216)),  # noqa: E731
                                               (hs.FUNCTIONS_TAB, 12, (145, 184, 138)),
                                               ((512, 786), 40, WHITE)])
MINE = hs.tile_xy(1)
INSUF = ['Insufficient resources. You can obtain them from :']   # live OCR of rq3
INSUF_POP = lambda: paint('UNKNOWN', [(hs.INSUF_X, 40, (250, 248, 244)),  # noqa: E731  rq3 X disc
                                      (hs.INSUF_X, 4, (99, 88, 88))])

MENU_FRAMES = [HERMES / 'hm_build_menu.png', HERMES / 'hm_menu_now.png', HERMES / 'menu17.png',
               *(SPECTRE / d / f'hs_{n}_{kind}.png' for d, n in (('shots-47000', 0), ('shots-67544', 0),
                                                                ('shots-67544', 1), ('shots-68276', 0))
                 for kind in ('menu', 'read'))]


def cnt_s(name: str, slot: int, n: int, limit: int) -> dict:
    """Fake OCR of every counter variant of tile `slot` (>0) on shot `name`."""
    return {f'{name}_s{slot}_cnt{i}': [f'{n}/{limit}'] for i in range(len(hs.COUNTER_VARIANTS))}


def queue(name: str, text: str) -> dict:
    return {f'{name}_q{i}': [text] for i in range(len(hs.QUEUE_VARIANTS))}


def entry(menu=MENU):
    """start shot, ground-tap shot, menu after Build, read shot."""
    return [WORLD, WORLD, menu, menu]


BUILD = [RING, MARK, TOAST, WORLD]       # tile tap -> radial, marker, toast, world


def built(k: int) -> dict:
    return {f'hs_b{k}_1': ['Field Built']}


class RealOcr(unittest.TestCase):
    """Real WinRT OCR on copies in a temp v.TMP (crops never land in .spectre)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        p = mock.patch.object(v, 'TMP', self.tmp)
        p.start()
        self.addCleanup(p.stop)

    def stage(self, src: Path, name: str) -> str:
        if not src.exists():
            self.skipTest(f'frame missing: {src}')
        shutil.copy(src, self.tmp / f'{name}.png')
        return name


class Detectors(unittest.TestCase):
    def test_only_the_field_tile_is_white_on_every_menu_frame(self):
        ran = 0
        for path in MENU_FRAMES:
            if not path.exists():
                continue
            with self.subTest(str(path)):
                img = load_rgb(path)
                self.assertTrue(hs.is_build_menu(img))
                self.assertEqual([s for s in range(hs.TILE_SLOTS) if hs.white_tile(img, s)], [0])
                self.assertTrue(hs.production_active(img))
                self.assertFalse(hs.functions_active(img))
            ran += 1
        if not ran:
            raise unittest.SkipTest('no live menu frames')

    def test_tile_geometry(self):
        self.assertEqual(hs.tile_xy(0), hs.FIELD_TILE)
        self.assertEqual(MINE, (627, 700))           # inside the Mine tile x 573-675
        self.assertEqual(dict(hs.TABS)['functions'], hs.FUNCTIONS_TAB)

    def test_synthetic_frames(self):
        self.assertEqual([s for s in range(hs.TILE_SLOTS) if hs.white_tile(MENU2(), s)], [0, 1])
        self.assertEqual([s for s in range(hs.TILE_SLOTS) if hs.white_tile(MENU_GREY(), s)], [])
        f = FUNC()
        self.assertTrue(hs.is_build_menu(f) and hs.functions_active(f) and not hs.production_active(f))


class RealQuest(RealOcr):
    def test_quest_pill(self):
        cases = [('b16a', 'build field x16'), ('reset2', 'build field x16'),
                 ('end1', 'upgrade the ore refinery'), ('kitchen_go', 'upgrade the ore refinery'),
                 ('hm_requests', 'respond to speed-up')]
        for src, want in cases:
            with self.subTest(src):
                q = hs.quest_text(self.stage(HERMES / f'{src}.png', src))
                self.assertIn(want, q)
                self.assertEqual(hs.quest_first(q, 'Field'), want.startswith('build'))

    def test_menu_frame_has_no_quest(self):
        self.assertEqual(hs.quest_text(self.stage(HERMES / 'hm_build_menu.png', 'm')), '')

    def test_missing_file_is_empty(self):
        self.assertEqual(hs.quest_text('nope'), '')


class RealQueue(RealOcr):
    def test_queue_reads_0_of_2(self):
        for i, src in enumerate((HERMES / 'hm_build_menu.png', HERMES / 'menu17.png',
                                 SPECTRE / 'shots-67544' / 'hs_1_read.png')):    # weakest frame
            with self.subTest(str(src)):
                name = self.stage(src, f'q{i}')
                self.assertEqual(hs.read_counter(name, variants=hs.QUEUE_VARIANTS, bw=hs.QUEUE_BW,
                                                 tag='q'), (0, 2))

    def test_short_greyed_counters_read_none_so_the_white_gate_decides(self):
        # T105A fix: Mine 1/1, Logging Site 2/2, Altar 1/1 are legible but 3-char; 36 tight
        # box/scale/mode variants also read nothing (max 1 vote) -> unreadable non-Field = skip
        name = self.stage(HERMES / 'hm_build_menu.png', 'g')
        for s in (1, 2, 3):
            with self.subTest(s):
                self.assertIsNone(hs.read_counter(name, hs.TILE_PITCH * s, tag=f's{s}_cnt'))
        self.assertEqual(hs.tile_counter(name, 0), (12, 16))


class Parsers(unittest.TestCase):
    def test_quest_first(self):
        self.assertTrue(hs.quest_first(') build field x16.', 'Field'))
        self.assertFalse(hs.quest_first('upgrade the ore refinery ) tolevel 5.', 'Field'))
        self.assertTrue(hs.quest_first('build mine x2.', 'Mine'))
        self.assertFalse(hs.quest_first('', 'Mine'))

    def test_tile_name(self):
        self.assertEqual(hs.tile_name('x', 'production', 2), 'Logging Site')
        dev = FakeDevice(self, [], ocr={'f_s3_name': ['Kitchen']})
        self.assertEqual(hs.tile_name('f', 'functions', 3), 'Kitchen')
        self.assertEqual(hs.tile_name('f', 'functions', 4), 'tile 4')
        self.assertEqual(dev.taps, [])


class Flow(unittest.TestCase):
    def run_hs(self, frames, ocr, *argv, max_builds=1, all_tabs=False):
        for p in (mock.patch.object(hs, 'MAX_BUILDS', max_builds),
                  mock.patch.object(hs, 'TABS', hs.TABS if all_tabs else hs.TABS[:1])):
            p.start()
            self.addCleanup(p.stop)
        dev = FakeDevice(self, [f() if callable(f) else f for f in frames], ocr=ocr)
        rc = hs.main(list(argv))
        self.assertNotIn(('key', 4), dev.taps)             # never BACK in the homestead menus
        self.assertNotIn(v.CONFIRM_CANCEL, dev.taps)
        return dev, rc

    def test_mine_built_when_the_field_is_full(self):
        frames = entry(MENU2) + BUILD + entry(MENU2) + [MENU2, WORLD]
        ocr = {**cnt('hs_0_read', 16), **cnt_s('hs_0_read', 1, 1, 2), 'hs_b0_1': ['Mine Built'],
               **cnt('hs_1_read', 16), **cnt_s('hs_1_read', 1, 2, 2)}
        dev, rc = self.run_hs(frames, ocr)
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, [v.GROUND, hs.BUILD_BTN, MINE, CHECK, (964, 560), hs.TOAST_CLOSE,
                                    v.GROUND, hs.BUILD_BTN, hs.EXIT_BTN])
        self.assertIn('Mine 2/2 - at the limit', dev.out.getvalue())

    def test_quest_tile_goes_first(self):
        ocr = {**cnt('hs_0_read', 12), **cnt_s('hs_0_read', 1, 1, 2), 'hs_0_read_res': RES,
               **cnt('hs_1_read', 12), **cnt_s('hs_1_read', 1, 2, 2), 'hs_1_read_res': RES}
        frames = entry(MENU2) + BUILD + entry(MENU2) + [MENU2, WORLD]
        dev, rc = self.run_hs(frames, {**ocr, 'hs_0_world_quest': [') build mine x2.'],
                                       **built(0)})
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps[2], MINE)
        ocr.update({**cnt('hs_1_read', 13), **cnt_s('hs_1_read', 1, 1, 2), **built(0)})
        dev, rc = self.run_hs(frames, ocr)                   # no quest: left to right
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps[2], hs.FIELD_TILE)

    def test_queue_full_stops_without_a_tile_tap(self):
        dev, rc = self.run_hs(entry() + [MENU, WORLD], {**cnt('hs_0_read', 12), 'hs_0_read_res': RES,
                                                       **queue('hs_0_read', '2/2')})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [v.GROUND, hs.BUILD_BTN, hs.EXIT_BTN])
        self.assertIn('queue full', dev.out.getvalue())

    def test_queue_with_a_free_slot_builds(self):
        frames = entry() + BUILD + entry() + [MENU, WORLD]
        dev, rc = self.run_hs(frames, {**cnt('hs_0_read', 12), 'hs_0_read_res': RES,
                                       **queue('hs_0_read', '1/2'), **built(0), **cnt('hs_1_read', 13)})
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertIn(hs.FIELD_TILE, dev.taps)

    def test_refused_tile_is_parked_and_the_next_one_built(self):
        frames = (entry(MENU2) + [RING, RING, RING, MENU2, WORLD]       # Mine refused -> X, Exit
                  + entry(MENU2) + BUILD + entry(MENU2) + [MENU2, WORLD])
        ocr = {'hs_0_world_quest': ['build mine x2.'], **built(1)}
        for k, n in ((0, 12), (1, 12), (2, 13)):
            ocr.update({**cnt(f'hs_{k}_read', n), **cnt_s(f'hs_{k}_read', 1, 1, 2)})
        dev, rc = self.run_hs(frames, ocr, max_builds=2)
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps.count(MINE), 1)
        self.assertEqual(dev.taps.count(hs.FIELD_TILE), 1)
        self.assertIn('Mine 1/2 - parked this run', dev.out.getvalue())
        self.assertIn('run cap reached', dev.out.getvalue())

    def test_insufficient_popup_is_closed_and_parks(self):
        frames = entry() + [INSUF_POP, MENU, WORLD] + entry() + [MENU, WORLD]
        ocr = {**cnt('hs_0_read', 12), **cnt('hs_1_read', 12), 'hs_b0_place': INSUF}
        dev, rc = self.run_hs(frames, ocr)
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [v.GROUND, hs.BUILD_BTN, hs.FIELD_TILE, hs.INSUF_X, hs.EXIT_BTN,
                                    v.GROUND, hs.BUILD_BTN, hs.EXIT_BTN])

    def test_insufficient_popup_after_the_check_parks(self):
        frames = entry() + [RING, INSUF_POP, MENU, WORLD] + entry() + [MENU, WORLD]
        ocr = {**cnt('hs_0_read', 12), **cnt('hs_1_read', 12), 'hs_b0_0': INSUF}
        dev, rc = self.run_hs(frames, ocr)
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps[2:5], [hs.FIELD_TILE, CHECK, hs.INSUF_X])

    def test_unknown_screen_after_the_insufficient_x_stops(self):
        dev, rc = self.run_hs(entry() + [INSUF_POP, TOAST, TOAST],   # X, unknown, stuck shot
                              {**cnt('hs_0_read', 12), 'hs_b0_place': INSUF})
        self.assertEqual(rc, 1)
        self.assertEqual(dev.taps[-1], hs.INSUF_X)

    def test_insufficient_popup_without_the_rq3_x_is_not_tapped(self):
        dev, rc = self.run_hs(entry() + [TOAST, TOAST], {**cnt('hs_0_read', 12), 'hs_b0_place': INSUF})
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertNotIn(hs.INSUF_X, dev.taps)
        self.assertEqual(dev.taps[-1], hs.FIELD_TILE)

    def test_functions_tab_scanned_when_production_is_full(self):
        frames = entry() + [FUNC, FUNC, FUNC, WORLD]          # tab tap, fread, exit shot, world
        ocr = {**cnt('hs_0_read', 16), **cnt('hs_0_fread', 1, 1), 'hs_0_fread_s0_name': ['Kitchen']}
        dev, rc = self.run_hs(frames, ocr, all_tabs=True)
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [v.GROUND, hs.BUILD_BTN, hs.FUNCTIONS_TAB, hs.EXIT_BTN])
        self.assertIn('Kitchen 1/1 - at the limit', dev.out.getvalue())

    def test_functions_tile_built_and_verified(self):
        frames = (entry() + [FUNC, FUNC] + BUILD + entry() + [FUNC, FUNC, FUNC, WORLD])
        ocr = {**cnt('hs_0_read', 16), **cnt('hs_0_fread', 0, 1), 'hs_0_fread_s0_name': ['Kitchen'],
               **built(0), **cnt('hs_1_read', 16), **cnt('hs_1_fread', 1, 1),
               'hs_1_fread_s0_name': ['Kitchen']}
        dev, rc = self.run_hs(frames, ocr, all_tabs=True)
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps[2:4], [hs.FUNCTIONS_TAB, hs.tile_xy(0)])
        self.assertNotIn('unverified', dev.out.getvalue())

    def test_functions_tab_that_does_not_switch(self):
        frames = entry() + [MENU, MENU, MENU, MENU, WORLD]  # tab, its retry, check, exit, world
        dev, rc = self.run_hs(frames, cnt('hs_0_read', 16), all_tabs=True)
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [v.GROUND, hs.BUILD_BTN, hs.FUNCTIONS_TAB,
                                    ('touchscreen', *hs.FUNCTIONS_TAB), hs.EXIT_BTN])
        self.assertIn('did not switch', dev.out.getvalue())

    def test_unknown_screen_after_the_functions_tap_stops(self):
        dev, rc = self.run_hs(entry() + [TOAST, TOAST], cnt('hs_0_read', 16), all_tabs=True)
        self.assertEqual(rc, 1)
        self.assertEqual(dev.taps[-1], hs.FUNCTIONS_TAB)

    def test_dry_run_reads_both_tabs(self):
        frames = entry() + [FUNC, FUNC, FUNC, WORLD]
        dev, rc = self.run_hs(frames, {**cnt('hs_0_read', 12), 'hs_0_read_res': RES,
                                       **cnt('hs_0_fread', 0, 1)}, '--dry-run', all_tabs=True)
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, [v.GROUND, hs.BUILD_BTN, hs.FUNCTIONS_TAB, hs.EXIT_BTN])
        self.assertIn('hs_0_fread', dev.shots)

    def test_sixteenth_field_greys_the_tile(self):
        frames = (entry() + BUILD + [WORLD, WORLD, MENU_GREY, MENU_GREY, MENU_GREY, MENU_GREY, WORLD])
        dev, rc = self.run_hs(frames, {**cnt('hs_0_read', 15), **built(0)}, max_builds=2)
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertIn('limit reached (tile greyed)', dev.out.getvalue())
        self.assertIn('hs_1_read2', dev.shots)

    def test_greyed_but_below_the_limit_is_an_error(self):
        frames = (entry() + BUILD + [WORLD, WORLD, MENU_GREY, MENU_GREY, MENU_GREY, MENU_GREY, WORLD])
        dev, rc = self.run_hs(frames, {**cnt('hs_0_read', 14), **built(0)}, max_builds=2)
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertIn('expected 15', dev.out.getvalue())

    def test_long_build_is_counted_and_verified(self):
        frames = entry() + [RING] + [WORLD] * hs.BUILD_POLLS + entry() + [MENU, WORLD]
        dev, rc = self.run_hs(frames, {**cnt('hs_0_read', 12), **cnt('hs_1_read', 13)})
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertIn('still building', dev.out.getvalue())

    def test_unreadable_other_tile_does_not_block_the_field(self):
        frames = entry(MENU2) + [MENU2] + BUILD + entry(MENU2) + [MENU2, MENU2, WORLD]
        dev, rc = self.run_hs(frames, {**cnt('hs_0_read', 12), **built(0), **cnt('hs_1_read', 13)})
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps.count(hs.FIELD_TILE), 1)
        self.assertIn('Mine counter not readable', dev.out.getvalue())

    def test_unreadable_other_tile_is_skipped_not_stuck(self):
        dev, rc = self.run_hs(entry(MENU2) + [MENU2, MENU2, WORLD], cnt('hs_0_read', 16))
        self.assertEqual(rc, 4, dev.out.getvalue())     # watch marker still written
        self.assertNotIn(MINE, dev.taps)
        self.assertIn('Mine counter not readable', dev.out.getvalue())

    def test_unreadable_field_and_nothing_built_is_stuck(self):
        dev, rc = self.run_hs(entry() + [MENU, MENU, WORLD], {})
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertNotIn(hs.FIELD_TILE, dev.taps)

    def test_cap_across_two_tiles(self):
        frames, ocr = [], {}
        for k, (field, mine) in enumerate(((14, 0), (15, 0), (16, 0), (16, 1), (16, 2))):
            frames += entry(MENU2) + (BUILD if k < 4 else [MENU2, WORLD])
            ocr.update({**cnt(f'hs_{k}_read', field), **cnt_s(f'hs_{k}_read', 1, mine, 3), **built(k)})
        dev, rc = self.run_hs(frames, ocr, max_builds=4)
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps.count(hs.FIELD_TILE), 2)
        self.assertEqual(dev.taps.count(MINE), 2)
        self.assertIn('run cap reached', dev.out.getvalue())

    def test_diamond_dialog_during_a_mine_build_stops_the_run(self):
        frames = entry(MENU2) + [RING, 'DIALOG', MENU2, WORLD]
        ocr = {**cnt('hs_0_read', 16), **cnt_s('hs_0_read', 1, 1, 2)}
        for p in (mock.patch.object(hs, 'MAX_BUILDS', 1), mock.patch.object(hs, 'TABS', hs.TABS[:1])):
            p.start()
            self.addCleanup(p.stop)
        dev = FakeDevice(self, [f() if callable(f) else f for f in frames], ocr=ocr)
        self.assertEqual(hs.main([]), 4, dev.out.getvalue())
        self.assertEqual(dev.taps[2:], [MINE, CHECK, v.CONFIRM_CANCEL, hs.EXIT_BTN])

    def test_confirm_dialog_right_after_the_tile_tap_is_cancelled(self):
        frames = entry(MENU2) + ['DIALOG', MENU2, WORLD]       # tile tap -> dialog, cancelled, exit
        ocr = {**cnt('hs_0_read', 16), **cnt_s('hs_0_read', 1, 1, 2), 'hs_b0_place': INSUF}
        for p in (mock.patch.object(hs, 'MAX_BUILDS', 1), mock.patch.object(hs, 'TABS', hs.TABS[:1])):
            p.start()
            self.addCleanup(p.stop)
        dev = FakeDevice(self, [f() if callable(f) else f for f in frames], ocr=ocr)
        self.assertEqual(hs.main([]), 4, dev.out.getvalue())
        self.assertEqual(dev.taps[2:], [MINE, v.CONFIRM_CANCEL, hs.EXIT_BTN])   # never INSUF_X

    def test_tile_tap_without_radial_parks_and_leaves_by_exit(self):
        frames = (entry(MENU2) + [MENU2, MENU2, WORLD]                # Mine tap + retry: no radial
                  + entry(MENU2) + BUILD + entry(MENU2) + [MENU2, WORLD])
        ocr = {'hs_0_world_quest': ['build mine x2.'], **built(1)}
        for k, n in ((0, 12), (1, 12), (2, 13)):
            ocr.update({**cnt(f'hs_{k}_read', n), **cnt_s(f'hs_{k}_read', 1, 1, 2),
                        f'hs_{k}_read_res': RES})
        dev, rc = self.run_hs(frames, ocr, max_builds=2)
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps[2:5], [MINE, ('touchscreen', *MINE), hs.EXIT_BTN])
        self.assertEqual(dev.taps.count(hs.FIELD_TILE), 1)
        self.assertIn('Mine 1/2 - parked this run', dev.out.getvalue())

    def test_menu_after_the_check_parks(self):
        frames = entry() + [RING, MENU, WORLD] + entry() + [MENU, WORLD]
        dev, rc = self.run_hs(frames, {**cnt('hs_0_read', 12), **cnt('hs_1_read', 12)})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps[2:5], [hs.FIELD_TILE, CHECK, hs.EXIT_BTN])

    def test_stuck_build_leaves_an_open_menu_by_exit(self):
        frames = entry() + [RING, TOAST, MENU, WORLD]           # unknown after check, stuck shot = menu
        dev, rc = self.run_hs(frames, cnt('hs_0_read', 12))
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual(dev.taps[-1], hs.EXIT_BTN)

    def quest_kitchen_ocr(self) -> dict:
        ocr = {'hs_0_world_quest': ['build kitchen x1.'], **built(0)}
        for k, n in ((0, 12), (1, 13)):
            ocr.update({**cnt(f'hs_{k}_read', n), f'hs_{k}_read_res': RES, **cnt(f'hs_{k}_fread', 1, 1),
                        f'hs_{k}_fread_s0_name': ['Kitchen']})
        return ocr

    def test_functions_quest_then_production_tab_for_the_field(self):
        frames = entry() + [FUNC, FUNC, MENU] + BUILD + entry() + [FUNC, FUNC, FUNC, WORLD]
        dev, rc = self.run_hs(frames, self.quest_kitchen_ocr(), all_tabs=True)
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps[2:5], [hs.FUNCTIONS_TAB, hs.PRODUCTION_TAB, hs.FIELD_TILE])
        self.assertIn('Kitchen 1/1 - at the limit', dev.out.getvalue())

    def test_production_tab_that_does_not_switch_back_is_stuck(self):
        frames = entry() + [FUNC, FUNC, FUNC, FUNC, FUNC, WORLD]   # ..., prod tap + retry, stuck, exit
        dev, rc = self.run_hs(frames, self.quest_kitchen_ocr(), all_tabs=True)
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual(dev.taps[2:], [hs.FUNCTIONS_TAB, hs.PRODUCTION_TAB,
                                        ('touchscreen', *hs.PRODUCTION_TAB), hs.EXIT_BTN])
        self.assertNotIn(hs.FIELD_TILE, dev.taps)

    def test_functions_build_left_unverified_when_production_has_work(self):
        frames = entry() + [FUNC, FUNC] + BUILD + entry() + [MENU, WORLD]
        ocr = {**cnt('hs_0_read', 16), **cnt('hs_0_fread', 0, 1), 'hs_0_fread_s0_name': ['Kitchen'],
               **built(0), **cnt('hs_1_read', 16, 20), 'hs_1_read_res': RES}    # Spire raised the limit
        dev, rc = self.run_hs(frames, ocr, all_tabs=True)
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertIn("unverified builds (tab not re-read): [('functions', 0)]", dev.out.getvalue())
        self.assertEqual(dev.taps[-1], hs.EXIT_BTN)


class RealTileName(RealOcr):
    def test_white_functions_tile_name_reads(self):
        name = self.stage(HERMES / 'hm_build_menu.png', 'n')
        self.assertEqual(hs.tile_name(name, 'functions', 0), 'Field')     # white tile: bordered crop
        self.assertEqual(hs.tile_name(name, 'functions', 1), 'Mine')      # greyed tile: raw fallback


if __name__ == '__main__':
    unittest.main()
