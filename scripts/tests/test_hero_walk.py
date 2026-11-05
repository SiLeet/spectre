"""T111: hero detector + safe ground on live frames, walk_towards flows on synthetic WORLD frames."""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_hero_walk as w  # noqa: E402
import afk_homestead_upgrade as hu  # noqa: E402
from fake_vision import FakeDevice  # noqa: E402
from PIL import ImageDraw  # noqa: E402
from test_homestead import HERMES  # noqa: E402
from test_homestead_upgrade import SPECTRE, real, walk_frame  # noqa: E402

S41556 = SPECTRE / 'shots-41556' / 'hu_world.png'
HERO_41556, TOWER_41556 = (957, 497), (339, 168)


def line(k):
    """Point k px out on the 41556 line hero -> tower (the recon's line samples)."""
    (hx, hy), (gx, gy) = HERO_41556, TOWER_41556
    d = math.hypot(gx - hx, gy - hy)
    return round(hx + (gx - hx) * k / d), round(hy + (gy - hy) * k / d)


class Hero(unittest.TestCase):
    def test_hero_on_live_frames(self):
        for path, xy in ((S41556, HERO_41556), (HERMES / 'st0.png', (957, 500)), (HERMES / 'hm1.png', (954, 497)),
                         (HERMES / 'px4.png', (957, 497)), (HERMES / 'upn0.png', (957, 494))):
            with self.subTest(path.name):
                self.assertEqual(w.hero(real(path)), xy)

    def test_hero_other_camera_family_near_last_position(self):
        self.assertEqual(w.hero(real(HERMES / 'spire_sel.png'), near=(984, 527)), (984, 527))

    def test_no_hero(self):
        # hidden behind the tower (Spire selected), daylight (min channel 170..195: low recall -> soft stop)
        for path in (HERMES / 'tower_tap.png', SPECTRE / 'shots-25208' / 'hu_world.png', HERMES / 'bk2.png'):
            with self.subTest(path.name):
                self.assertIsNone(w.hero(real(path)))

    def test_hero_search_is_bounded(self):
        img = walk_frame((400, 300), hero_xy=(1300, 500))          # a white figure far off the anchor
        self.assertIsNone(w.hero(img))
        self.assertLessEqual(math.dist(w.hero(img, near=(1300, 500)), (1300, 500)), w.HERO_CELL)  # cell grid


class Ground(unittest.TestCase):
    def test_safe_ground_on_the_41556_line(self):
        img = real(S41556)
        self.assertTrue(w.safe_ground(img, line(300), HERO_41556, TOWER_41556))
        # companion, stepping stones, flowers, waypoint statue, Spire platform | open ground within
        # GROUND_NB of the stepping stones (180) / the flower bed (330): rejected by the neighbour ring
        for k in (60, 120, 210, 390, 510, 180, 330):
            with self.subTest(k=k):
                self.assertFalse(w.safe_ground(img, line(k), HERO_41556, TOWER_41556))
        self.assertEqual(w.target(img, HERO_41556, TOWER_41556), line(300))

    def test_buildings_trees_water_are_not_ground(self):
        # review negatives (flat dark patches the L test alone passed): mill roof, crop field, pine, lantern
        # pillar base, Spire deck, pine canopies, Spire base slab | mist pond + its rock edge (tower_tap)
        img = real(S41556)
        for p in ((1340, 720), (560, 740), (840, 720), (760, 380), (500, 480), (1200, 264), (840, 744),
                  (408, 456)):
            with self.subTest(p=p):
                self.assertFalse(w.safe_ground(img, p, HERO_41556, TOWER_41556))
        img = real(HERMES / 'tower_tap.png')
        for p in ((552, 408), (504, 360)):
            with self.subTest(p=p):
                self.assertFalse(w.safe_ground(img, p, (957, 500), (-999, -999)))

    def test_ground_needs_a_measured_night_palette(self):
        self.assertIsNotNone(w.ground_box(real(S41556)))
        self.assertIsNotNone(w.ground_box(real(HERMES / 'st0.png')))           # night blue
        self.assertEqual(w.target(real(HERMES / 'st0.png'), (957, 500), TOWER_41556), (693, 358))
        for path in (SPECTRE / 'shots-68132' / 'hu_world.png', HERMES / 'tower_tap.png'):   # day, mist
            with self.subTest(path.name):
                self.assertIsNone(w.ground_box(real(path)))

    def test_requests_arch_is_not_ground(self):
        # review: hero forced to the anchor on the Kitchen scene -> the gap between the Requests statue
        # and its arch pillar (807, 511) was chosen; now no ground at all there (soft stop)
        img = real(SPECTRE / 'shots-57584' / 'hu_after.png')
        self.assertFalse(w.safe_ground(img, (807, 511), (957, 500), (515, 524)))
        self.assertIsNone(w.target(img, (957, 500), (515, 524)))

    def test_hud_points_are_never_ground(self):
        img = walk_frame((400, 300))                                          # flat ground everywhere else
        for p in ((960, 835), (953, 683), (867, 728), (100, 500), (180, 915), (960, 1000), (1700, 660),
                  (957, 500), (1000, 520), (500, 350)):
            with self.subTest(p=p):
                self.assertFalse(w.safe_ground(img, p, (957, 500), (400, 300)))
        self.assertTrue(w.safe_ground(img, (700, 300), (957, 500), (400, 300)))
        self.assertFalse(w.safe_ground(img, (700, 300), (957, 500), (400, 300), avoid=[(730, 320)]))


class Walk(unittest.TestCase):
    def walk(self, frames, **kw):
        dev = FakeDevice(self, frames)
        res = w.walk_towards(hu.spire_tower, hu._tap, 'tw', **kw)
        return dev, res

    def test_arrives(self):
        dev, (status, _, goal, me) = self.walk([walk_frame((400, 300)), walk_frame((760, 420))])
        self.assertEqual((status, goal), ('arrived', (760, 420)))
        self.assertLessEqual(math.dist(me, (957, 500)), w.HERO_CELL)               # cell grid
        self.assertEqual(len(dev.taps), 1)
        self.assertEqual(dev.shots, ['tw_0', 'tw_1'])

    def test_arrives_when_the_hero_walks_to_each_tap_point(self):
        # review: taps stay GOAL_CLEAR off the goal -> a hero reaching its tap point arrives (camera follows)
        goal, frames, taps = (400, 300), [], []
        for _ in range(3):
            f = walk_frame(goal)
            frames.append(f)
            me = w.hero(f)
            if math.dist(goal, me) < w.WALK_STOP:
                break
            p = w.target(f, me, goal)
            taps.append(p)
            goal = (goal[0] - (p[0] - me[0]), goal[1] - (p[1] - me[1]))
        dev, (status, *_) = self.walk(frames)
        self.assertEqual(status, 'arrived', dev.out.getvalue())
        self.assertEqual(dev.taps, taps)
        self.assertEqual(len(taps), 2)

    def test_arrival_beats_selected(self):
        # review: the tap that brings the hero to the Spire also brings up its Interact -> 'arrived'
        near = walk_frame((760, 420))
        ImageDraw.Draw(near).rectangle((953 - 35, 683 - 35, 953 + 35, 683 + 35), fill=(240, 236, 228))
        dev, (status, *_) = self.walk([walk_frame((400, 300)), near],
                                      interact=lambda im: hu.interact_at(im, w.INTERACT_HUD))
        self.assertEqual((status, len(dev.taps)), ('arrived', 1))

    def test_stuck_after_two_taps_without_gain(self):
        f = walk_frame((400, 300))
        dev, (status, *_) = self.walk([f, f, f])
        self.assertEqual(status, 'stuck')
        self.assertEqual(len(dev.taps), 2)

    def test_max_taps(self):
        goal, me = (300, 200), (957, 500)
        d = math.hypot(goal[0] - me[0], goal[1] - me[1])
        axes = [(round(me[0] + (goal[0] - me[0]) * (1 - 35 * i / d)), round(me[1] + (goal[1] - me[1]) * (1 - 35 * i / d)))
                for i in range(13)]                                     # 35 px gain per tap, never < 250
        dev, (status, *_) = self.walk([walk_frame(a) for a in axes])
        self.assertEqual(status, 'max', dev.out.getvalue())
        self.assertEqual(len(dev.taps), w.MAX_TAPS)

    def test_not_world_after_a_tap_stops(self):
        dev, (status, *_) = self.walk([walk_frame((400, 300)), 'UNKNOWN'])
        self.assertEqual(status, 'not_world')
        self.assertEqual(len(dev.taps), 1)

    def test_not_world_start_no_tap(self):
        dev, (status, *_) = self.walk(['UNKNOWN'])
        self.assertEqual((status, dev.taps), ('not_world', []))

    def test_no_ground_no_tap(self):
        img = walk_frame((400, 300))
        d = ImageDraw.Draw(img)
        for x in range(520, 900, 8):                 # rough ground between the beams and the hero
            d.rectangle((x, 120, x + 3, 800), fill=(120, 120, 120))
        dev, (status, *_) = self.walk([img])
        self.assertEqual((status, dev.taps), ('no_ground', []))

    def test_selection_after_a_tap_stops(self):
        after = walk_frame((600, 350))
        ImageDraw.Draw(after).rectangle((953 - 35, 683 - 35, 953 + 35, 683 + 35), fill=(240, 236, 228))
        dev, (status, *_) = self.walk([walk_frame((400, 300)), after],
                                      interact=lambda im: hu.interact_at(im, w.INTERACT_HUD))
        self.assertEqual((status, len(dev.taps)), ('selected', 1))


if __name__ == '__main__':
    unittest.main()
