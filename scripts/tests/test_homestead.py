"""T102 homestead phase 1: build Fields — detectors on Hermes' live frames + FakeVision flows."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from PIL import ImageDraw  # noqa: E402

import afk_claim_vision as v  # noqa: E402
import afk_homestead as hs  # noqa: E402
from fake_vision import FakeDevice, frame  # noqa: E402
from make_frame_manifest import load_rgb  # noqa: E402

HERMES = Path.home() / 'AppData' / 'Local' / 'hermes' / 'cache' / 'scratch'
SPECTRE = Path(__file__).resolve().parents[3] / 'spectre' / '.spectre'   # worktrees have no .spectre


def hermes(name: str):
    path = HERMES / name
    if not path.exists():
        raise unittest.SkipTest(f'frame missing: {path}')
    return load_rgb(path)


def paint(base: str, boxes) -> object:
    img = frame(base)
    d = ImageDraw.Draw(img)
    for (x, y), half, rgb in boxes:
        d.rectangle((x - half, y - half, x + half, y + half), fill=rgb)
    return img


BTN = (hs.BUILD_BTN, 6, (165, 165, 165))
# synthetic screens with the measured colours (constants' LIVE notes)
WORLD = lambda: paint('WORLD', [BTN])                                       # noqa: E731
MENU = lambda: paint('UNKNOWN', [(hs.EXIT_BTN, 12, (198, 187, 183)), (hs.BUILD_TAB, 12, (146, 183, 134)),  # noqa: E731
                                 (hs.LAYOUT_TAB, 12, (230, 223, 221)),
                                 (hs.PRODUCTION_TAB, 12, (145, 184, 138)),
                                 ((512, 786), 40, (255, 255, 255))])   # T105A: white Field tile body
RING = lambda: paint('UNKNOWN', [((1089, 562), 30, (250, 250, 250)), ((842, 557), 30, (250, 250, 250)),  # noqa: E731
                                 ((1089, 562), 7, (60, 200, 60)), ((842, 557), 7, (220, 40, 40))])
MARK = lambda: paint('WORLD', [BTN, ((964, 560), 26, (254, 238, 93))])       # noqa: E731
TOAST = lambda: frame('UNKNOWN')                                            # noqa: E731
LEFT = lambda: paint('WORLD', [BTN, ((760, 877), 26, (254, 238, 93))])      # noqa: E731  (T103c)
FIELD_BUILT = ['Field Built', '"ProQerity', 'Tapto Close', 'o 10']          # live OCR of complete1/close9
CHECK, CANCEL = (1089, 562), (842, 557)
RES = ['@ 653,402 3848', '460']


def cnt(name: str, n: int, limit: int = 16) -> dict:
    """Fake OCR of every counter variant of shot `name` reading n/limit (T102b vote)."""
    return {f'{name}_cnt{i}': [f'{n}/{limit}'] for i in range(len(hs.COUNTER_VARIANTS))}


class Detectors(unittest.TestCase):
    """Real frames from the 2026-11-04 20:40 live run (skip when missing)."""

    def test_build_menu(self):
        img = hermes('hm_build_menu.png')
        self.assertTrue(hs.is_build_menu(img))
        self.assertTrue(hs.production_active(img))
        self.assertIsNone(hs.find_ring(img))

    def test_ring_found_on_the_frame(self):
        for name in ('hm_field_tap.png', 'hm_field_build.png', 'hm_field_confirmed.png'):
            with self.subTest(name):
                img = hermes(name)
                (cx, cy), (xx, xy) = hs.find_ring(img)
                self.assertLessEqual(abs(cx - 1090) + abs(cy - 558), 8)   # check disc centre
                self.assertLessEqual(abs(xx - 842) + abs(xy - 558), 8)    # cancel disc centre
                self.assertGreater(cy, 527)     # (1090,520) missed live: above the disc
                self.assertFalse(hs.is_build_menu(img))

    def test_ring_follows_the_ghost(self):
        # T102c live: the radial sits around the ghost - (934,544) was outside the old window
        spectre = Path(r'C:\Users\Sigi\spectre\.spectre')
        cases = [(spectre / 'shots-47000' / 'hs_b0_place.png', (933, 550)),
                 (spectre / 'shots-67544' / 'hs_b0_place.png', (1176, 491)),
                 (HERMES / 'pl3.png', (1284, 574))]
        ran = 0
        for path, (cx, cy) in cases:
            if not path.exists():
                continue
            with self.subTest(str(path)):
                (gx, gy), (rx, ry) = hs.find_ring(load_rgb(path))
                self.assertLessEqual(abs(gx - cx) + abs(gy - cy), 8)
                self.assertLessEqual(abs(gx - rx - hs.X_DX), 15)
            ran += 1
        if not ran:
            raise unittest.SkipTest('no live placement frames')

    def test_dream_realm_red_green_is_not_a_ring(self):
        # T102c sweep: the only band-wide geometry hit without white discs
        path = Path(r'C:\Users\Sigi\spectre\.spectre\shots-41820\dr_f1_w6.png')
        if not path.exists():
            raise unittest.SkipTest('frame missing')
        self.assertIsNone(hs.find_ring(load_rgb(path)))

    def test_marker_and_world(self):
        img = hermes('hm_confirmed2.png')
        self.assertEqual(v.classify(img), 'WORLD')
        self.assertTrue(hs.build_btn(img))
        mx, my = hs.find_marker(img)
        self.assertLessEqual(abs(mx - 964) + abs(my - 580), 8)

    def test_negatives(self):
        for name in ('hm_requests.png', 'hm_req2.png', 'hm_spire_up.png', 'hm_up2.png', 'hm_up3.png'):
            with self.subTest(name):
                img = hermes(name)
                self.assertFalse(hs.is_build_menu(img))
                self.assertIsNone(hs.find_ring(img))
                self.assertIsNone(hs.find_marker(img))
        for name in ('hm_requests.png', 'hm_req2.png'):
            self.assertTrue(hs.build_btn(hermes(name)))

    def test_finished_build_outside_the_build_window(self):
        # T103c live (shots-80480 / where1 / base2): marker (760,877), outside MARK_WIN; the
        # Kitchen's yellow request bubble (874,425) on the same frame is no marker
        for path in (SPECTRE / 'shots-80480' / 'hu_world.png', HERMES / 'where1.png', HERMES / 'base2.png'):
            if not path.exists():
                continue
            with self.subTest(path.name):
                img = load_rgb(path)
                self.assertIsNone(hs.find_marker(img))
                mx, my = hs.find_marker(img, hs.COLLECT_WIN)
                self.assertLessEqual(abs(mx - 760) + abs(my - 877), 8)
        for name in ('close10.png', 'hm_requests.png', 'hm_req2.png', 'spire_sel2.png', 'hm_build_menu.png',
                     'complete1.png'):                                # bubble only / no marker / toast
            with self.subTest(name):
                self.assertIsNone(hs.find_marker(hermes(name), hs.COLLECT_WIN))

    def test_synthetic_frames_match_the_detectors(self):
        self.assertEqual(v.classify(WORLD()), 'WORLD')
        self.assertTrue(hs.build_btn(WORLD()))
        self.assertTrue(hs.is_build_menu(MENU()) and hs.production_active(MENU()))
        self.assertTrue(hs.white_tile(MENU(), 0))
        self.assertFalse(hs.white_tile(MENU(), 1))
        self.assertEqual(hs.find_ring(RING()), (CHECK, CANCEL))
        self.assertEqual(v.classify(MARK()), 'WORLD')
        self.assertEqual(hs.find_marker(MARK()), (964, 560))
        self.assertIsNone(hs.find_marker(WORLD()))


class RealCounter(unittest.TestCase):
    """T102b: the vote on the live menu frames (real WinRT OCR, offline; skip when missing)."""

    def test_live_counters(self):
        import shutil
        import tempfile
        spectre = Path(__file__).resolve().parents[2] / '.spectre'
        if not spectre.exists():
            spectre = Path(r'C:\Users\Sigi\spectre\.spectre')     # worktrees have no .spectre
        cases = [(HERMES / 'hm_build_menu.png', (12, 16)), (HERMES / 'hm_menu_now.png', (14, 16)),
                 (spectre / 'shots-67544' / 'hs_0_read.png', (13, 16)),
                 (spectre / 'shots-67544' / 'hs_1_read.png', (14, 16)),
                 (spectre / 'shots-68276' / 'hs_0_read.png', (14, 16))]
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        p = mock.patch.object(v, 'TMP', tmp)                    # crops never land in .spectre
        p.start()
        self.addCleanup(p.stop)
        ran = 0
        for i, (src, want) in enumerate(cases):
            if not src.exists():
                continue
            shutil.copy(src, tmp / f'c{i}.png')
            with self.subTest(str(src)):
                self.assertEqual(hs.read_counter(f'c{i}'), want)
            ran += 1
        if not ran:
            raise unittest.SkipTest('no live menu frames')


class Parsers(unittest.TestCase):
    def test_counter_vote(self):
        # T102b live reads: hs_1_read variants -> [], '14/16', [], [], "14'/16", [], "14'/16"
        self.assertEqual(hs.counter_votes([[], ['14/16'], [], [], ["14'/16"], [], ["14'/16"]]), (14, 16))
        self.assertEqual(hs.counter_votes([['13/16'], ['i3/16'], ['13/16']]), (13, 16))  # (3,16) loses
        self.assertIsNone(hs.counter_votes([['14/16'], [], []]))          # one vote is not enough
        self.assertIsNone(hs.counter_votes([['14/16'], ['14/16'], ['13/16'], ['13/16']]))  # split
        self.assertIsNone(hs.counter_votes([["14716'"], ['14 O-']]))      # the old stacked misread
        self.assertIsNone(hs.counter_votes([['17/16'], ['17/16']]))       # built > limit: implausible

    def test_resources(self):
        self.assertEqual(hs.parse_resources(RES), (653402, 3848))
        self.assertIsNone(hs.parse_resources(['3848', '460']))  # x2 OCR drops gold


class Flow(unittest.TestCase):
    def run_hs(self, frames, ocr, *argv, max_builds=1):
        for p in (mock.patch.object(hs, 'MAX_BUILDS', max_builds),
                  mock.patch.object(hs, 'TABS', hs.TABS[:1])):   # T105A: Production only (legacy taps)
            p.start()
            self.addCleanup(p.stop)
        dev = FakeDevice(self, [f() if callable(f) else f for f in frames], ocr=ocr)
        return dev, hs.main(list(argv))

    def entry(self, k):
        """reach_world, ground-tap shot, menu after Build, read shot."""
        return [WORLD, WORLD, MENU, MENU]

    def test_one_field_built_and_verified(self):
        frames = (self.entry(0) + [RING, MARK, TOAST, WORLD] + self.entry(1)
                  + [MENU, WORLD])                                  # exit shot, reach_world
        ocr = {**cnt('hs_0_read', 12), 'hs_0_read_res': RES, 'hs_b0_1': ['Field Built'],
               **cnt('hs_1_read', 13), 'hs_1_read_res': RES}
        dev, rc = self.run_hs(frames, ocr)
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, [v.GROUND, hs.BUILD_BTN, hs.FIELD_TILE, CHECK, (964, 560),
                                    hs.TOAST_CLOSE, v.GROUND, hs.BUILD_BTN, hs.EXIT_BTN])
        self.assertIn('run cap reached', dev.out.getvalue())

    def test_real_frames_one_field(self):
        w, menu = hermes('hm_requests.png'), hermes('hm_build_menu.png')
        frames = [w, w, menu, menu, hermes('hm_field_tap.png'), hermes('hm_confirmed2.png'),
                  hermes('hm_spire_up.png'), w, w, w, menu, menu, menu, w]
        ocr = {**cnt('hs_0_read', 12), 'hs_0_read_res': RES,
               'hs_b0_1': ['Field Built', '"Proqerity', 'Tapto Close'],
               **cnt('hs_1_read', 13), 'hs_1_read_res': RES}
        dev, rc = self.run_hs(frames, ocr)
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps[2], hs.FIELD_TILE)
        cx, cy = dev.taps[3]
        self.assertTrue(1059 <= cx <= 1121 and 527 <= cy <= 589, dev.taps[3])   # inside the check disc
        self.assertEqual(dev.taps[5:], [hs.TOAST_CLOSE, v.GROUND, hs.BUILD_BTN, hs.EXIT_BTN])

    def test_reward_info_card_is_closed_too(self):
        frames = self.entry(0) + [RING, MARK, TOAST, TOAST, WORLD] + self.entry(1) + [MENU, WORLD]
        ocr = {**cnt('hs_0_read', 12), 'hs_0_read_res': RES, 'hs_b0_1': ['Field Built'],
               'hs_b0_t0': ['Diamond', 'Tapto Close'], **cnt('hs_1_read', 13),
               'hs_1_read_res': RES}
        dev, rc = self.run_hs(frames, ocr)
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps.count(hs.TOAST_CLOSE), 2)
        self.assertNotIn(('key', 4), dev.taps)                  # a different toast: no BACK fallback

    def test_toast_left_up_gets_one_back(self):
        # T103c: the same toast after its Tap to close -> ONE keyevent BACK (only on the toast)
        frames = self.entry(0) + [RING, MARK, TOAST, TOAST, WORLD] + self.entry(1) + [MENU, WORLD]
        ocr = {**cnt('hs_0_read', 12), 'hs_0_read_res': RES, 'hs_b0_1': FIELD_BUILT,
               'hs_b0_t0': FIELD_BUILT, **cnt('hs_1_read', 13), 'hs_1_read_res': RES}
        dev, rc = self.run_hs(frames, ocr)
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps[4:7], [(964, 560), hs.TOAST_CLOSE, ('key', 4)])
        self.assertEqual(dev.taps.count(('key', 4)), 1)

    def test_toast_that_never_closes_is_bounded(self):
        frames = self.entry(0) + [RING, MARK] + [TOAST] * (hs.TOAST_TRIES + 2)   # + stuck shot
        ocr = {**cnt('hs_0_read', 12), 'hs_0_read_res': RES, 'hs_b0_1': FIELD_BUILT,
               **{f'hs_b0_t{n}': FIELD_BUILT for n in range(hs.TOAST_TRIES)}}
        dev, rc = self.run_hs(frames, ocr)
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual(dev.taps.count(('key', 4)), 1)          # BACK once, the rest are taps
        self.assertEqual(dev.taps.count(hs.TOAST_CLOSE), hs.TOAST_TRIES - 1)

    def test_finished_build_collected_before_the_menu(self):
        # T103c: world with a waiting marker -> tap it, Tap to close (left up -> BACK), then Build
        frames = [WORLD, LEFT, TOAST, TOAST, WORLD, MENU, MENU, MENU, WORLD]
        ocr = {'hs_0_world_col0': FIELD_BUILT, 'hs_0_world_col0_t0': FIELD_BUILT,
               **cnt('hs_0_read', 16), 'hs_0_read_res': RES}
        dev, rc = self.run_hs(frames, ocr)
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [v.GROUND, (760, 877), hs.TOAST_CLOSE, ('key', 4), hs.BUILD_BTN,
                                    hs.EXIT_BTN])
        self.assertIn('collecting', dev.out.getvalue())

    def test_collect_is_bounded(self):
        frames = [WORLD, LEFT] + [LEFT] * hs.COLLECT_MAX + [MENU, MENU, MENU, WORLD]
        dev, rc = self.run_hs(frames, {**cnt('hs_0_read', 16), 'hs_0_read_res': RES})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps.count((760, 877)), hs.COLLECT_MAX)

    def test_unknown_screen_after_a_collect_tap_stops(self):
        dev, rc = self.run_hs([WORLD, LEFT, TOAST], {'hs_0_world_col0': ['Something else']})
        self.assertEqual(rc, 1)
        self.assertEqual(dev.taps, [v.GROUND, (760, 877)])

    def test_real_frames_collect(self):
        # operator live 22:28: where1 (marker) -> complete1 -> close9 (still up) -> BACK -> close10
        w, menu = hermes('where1.png'), hermes('hm_build_menu.png')
        frames = [w, w, hermes('complete1.png'), hermes('close9.png'), hermes('close10.png'),
                  menu, menu, menu, hermes('close10.png')]
        ocr = {'hs_0_world_col0': FIELD_BUILT, 'hs_0_world_col0_t0': FIELD_BUILT,
               **cnt('hs_0_read', 16), 'hs_0_read_res': RES}
        dev, rc = self.run_hs(frames, ocr)
        self.assertEqual(rc, 4, dev.out.getvalue())
        mx, my = dev.taps[1]
        self.assertLessEqual(abs(mx - 760) + abs(my - 877), 8)
        self.assertEqual(dev.taps[2:], [hs.TOAST_CLOSE, ('key', 4), hs.BUILD_BTN, hs.EXIT_BTN])

    def test_exit_game_dialog_on_the_start_frame_is_cancelled(self):
        # T103c live (shots-9308): X, re-shoot, continue - never the green check (exits the game)
        dev, rc = self.run_hs(['DIALOG', WORLD, WORLD, MENU, MENU, MENU, WORLD],
                              {**cnt('hs_0_read', 16), 'hs_0_read_res': RES})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [v.CONFIRM_CANCEL, v.GROUND, hs.BUILD_BTN, hs.EXIT_BTN])
        self.assertNotIn(('key', 4), dev.taps)

    def test_at_limit_is_nothing_to_do(self):
        dev, rc = self.run_hs(self.entry(0) + [MENU, WORLD],
                              {**cnt('hs_0_read', 16), 'hs_0_read_res': RES})
        self.assertEqual(rc, 4)
        self.assertEqual(dev.taps, [v.GROUND, hs.BUILD_BTN, hs.EXIT_BTN])
        self.assertIn('at the limit', dev.out.getvalue())

    def test_resources_short_stops_cleanly(self):
        dev, rc = self.run_hs(self.entry(0) + [MENU, WORLD],
                              {**cnt('hs_0_read', 12), 'hs_0_read_res': ['@ 50 3848', '460']})
        self.assertEqual(rc, 4)
        self.assertNotIn(hs.FIELD_TILE, dev.taps)
        self.assertIn('resources short', dev.out.getvalue())

    def test_dry_run_reads_only(self):
        dev, rc = self.run_hs(self.entry(0) + [MENU, WORLD],
                              {**cnt('hs_0_read', 12), 'hs_0_read_res': RES}, '--dry-run')
        self.assertEqual(rc, 0)
        self.assertEqual(dev.taps, [v.GROUND, hs.BUILD_BTN, hs.EXIT_BTN])

    def test_no_build_button_is_nothing_to_do(self):
        dev, rc = self.run_hs(['WORLD', 'WORLD'], {})
        self.assertEqual(rc, 4)
        self.assertEqual(dev.taps, [v.GROUND])

    def test_counter_unreadable_stops(self):
        dev, rc = self.run_hs(self.entry(0) + [MENU, MENU, WORLD], {})
        self.assertEqual(rc, 1)
        self.assertNotIn(hs.FIELD_TILE, dev.taps)
        self.assertIn('hs_0_read2', dev.shots)                  # T102b: one settled re-read
        self.assertNotIn(('key', 4), dev.taps)                  # never BACK in the menu

    def test_counter_reread_after_build_accepts_the_settled_value(self):
        # T102b live: 'built field 1 (expect 14/16)' then the tile (animating) read nothing
        frames = (self.entry(0) + [RING, MARK, TOAST, WORLD] + self.entry(1)
                  + [MENU, MENU, WORLD])                         # read2, exit shot, Exit -> world
        ocr = {**cnt('hs_0_read', 13), 'hs_0_read_res': RES, 'hs_b0_1': ['Field Built'],
               **cnt('hs_1_read2', 14), 'hs_1_read2_res': RES}
        dev, rc = self.run_hs(frames, ocr)
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertIn('Field 14/16', dev.out.getvalue())

    def test_menu_left_open_is_used_without_back(self):
        # T102b live: run 2 started inside the menu a failed run left open; keyevent 4 there
        # opens 'exit game?' -> no reach_world, no ground tap, no Build tap
        dev, rc = self.run_hs([MENU, MENU, MENU, WORLD], {**cnt('hs_0_read', 16), 'hs_0_read_res': RES})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [hs.EXIT_BTN])
        self.assertIn('already open', dev.out.getvalue())

    def test_placement_left_open_is_cancelled_first(self):
        dev, rc = self.run_hs([RING, MENU, MENU, MENU, WORLD], {**cnt('hs_0_read', 16),
                                                              'hs_0_read_res': RES})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [CANCEL, hs.EXIT_BTN])

    def test_exit_that_does_not_close_never_backs(self):
        # Exit, its T97b retry, menu still up -> stop there (BACK would ask 'exit game?')
        dev, rc = self.run_hs(self.entry(0) + [MENU, MENU, MENU],
                              {**cnt('hs_0_read', 16), 'hs_0_read_res': RES})
        self.assertEqual(rc, 4)
        self.assertEqual(dev.taps[-2:], [hs.EXIT_BTN, ('touchscreen', *hs.EXIT_BTN)])
        self.assertNotIn(('key', 4), dev.taps)

    def test_counter_mismatch_after_build_stops(self):
        frames = self.entry(0) + [RING, MARK, TOAST, WORLD] + self.entry(1) + [MENU, MENU, WORLD]
        ocr = {**cnt('hs_0_read', 12), 'hs_0_read_res': RES, 'hs_b0_1': ['Field Built'],
               **cnt('hs_1_read', 12), **cnt('hs_1_read2', 12), 'hs_1_read_res': RES}
        dev, rc = self.run_hs(frames, ocr, max_builds=2)
        self.assertEqual(rc, 1)
        self.assertIn('expected 13', dev.out.getvalue())
        self.assertEqual(dev.taps.count(hs.FIELD_TILE), 1)

    def test_refused_build_cancels_and_exits(self):
        # check tap: still placing, the T97b retry too -> X, Exit, world; T105A: the Field is
        # parked, the next visit finds nothing else to build
        frames = self.entry(0) + [RING, RING, RING, MENU, WORLD] + self.entry(1) + [MENU, WORLD]
        dev, rc = self.run_hs(frames, {**cnt('hs_0_read', 12), 'hs_0_read_res': RES,
                                       **cnt('hs_1_read', 12), 'hs_1_read_res': RES})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps[3:], [CHECK, ('touchscreen', *CHECK), CANCEL, hs.EXIT_BTN,
                                        v.GROUND, hs.BUILD_BTN, hs.EXIT_BTN])

    def test_diamond_dialog_is_cancelled(self):
        frames = self.entry(0) + [RING, 'DIALOG', MENU, WORLD]
        dev, rc = self.run_hs(frames, {**cnt('hs_0_read', 12), 'hs_0_read_res': RES})
        self.assertEqual(rc, 4)
        self.assertEqual(dev.taps[3:], [CHECK, v.CONFIRM_CANCEL, hs.EXIT_BTN])

    def test_unknown_screen_while_building_stops_without_taps(self):
        frames = self.entry(0) + [RING, MARK, TOAST, TOAST]     # + stuck shot (no menu -> no Exit)
        dev, rc = self.run_hs(frames, {**cnt('hs_0_read', 12), 'hs_0_read_res': RES,
                                       'hs_b0_1': ['Something else']})
        self.assertEqual(rc, 1)
        self.assertEqual(dev.taps[-1], (964, 560))      # the marker; nothing after the unknown frame

    def test_tile_tap_without_placement_never_retries_on_a_changed_screen(self):
        dev, rc = self.run_hs(self.entry(0) + [TOAST, TOAST], {**cnt('hs_0_read', 12),
                                                                'hs_0_read_res': RES})
        self.assertEqual(rc, 1)
        self.assertEqual(dev.taps[-1], hs.FIELD_TILE)

    def test_tap_lock_held(self):
        import _bot_lock
        p = mock.patch.object(_bot_lock, 'acquire', lambda *a, **k: False)
        p.start()
        self.addCleanup(p.stop)
        dev, rc = self.run_hs([], {})
        self.assertEqual(rc, 7)
        self.assertEqual(dev.taps, [])


if __name__ == '__main__':
    unittest.main()
