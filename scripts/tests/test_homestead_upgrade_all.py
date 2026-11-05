"""T105B homestead upgrade-all: quest building + green upgrade pins - detectors on live frames + flows."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402
import afk_homestead as hs  # noqa: E402
import afk_homestead_upgrade as hu  # noqa: E402
from fake_vision import FakeDevice, frame  # noqa: E402
from test_homestead import hermes  # noqa: E402
from test_homestead_upgrade import (DIALOG_BOXES, ICON, KITCHEN, KITCHEN_BOXES, NO_BACK_KEY, SPECTRE,  # noqa: E402
                                    GO, DISC, WORLD_BOXES, dialog, real)

S57, S42 = SPECTRE / 'shots-57584', SPECTRE / 'shots-42848'
# real WinRT OCR line boxes (ocr.ps1 -Boxes), recorded 2026-11-05 on the frames named
HU_BREAD_BOXES = [(1451, 91, 22, 12, '0/2'), (478, 436, 302, 26, 'Upgrade Requirement (4/4)'),     # 57584/hu_bread
                  (826, 309, 269, 39, 'Lvl. 4?Lvl. 5'), (898, 367, 113, 21, "Kitchen 'i"),
                  (842, 601, 79, 13, '654K/1500'), (614, 601, 69, 13, '2836/300'), (517, 609, 28, 12, 'Spire'),
                  (477, 715, 202, 27, 'Upgrade Rewards'), (479, 893, 115, 21, '4 Prosperity'),
                  (730, 601, 70, 13, '37K/1600'), (662, 981, 219, 36, 'Complete Now'),
                  (1334, 892, 112, 17, '60 ? 100'), (1148, 935, 301, 20, 'Timesaved byLoyalPatronage: X 00:05:00'),
                  (1188, 982, 127, 36, 'Level Up')]
HU57584_WORLD_BOXES = [(1761, 13, 67, 17, '3000/3000'), (105, 64, 44, 13, 'District'), (40, 90, 29, 14, '1411'),  # hu_world
                       (18, 307, 37, 10, '25:19:'), (25, 781, 37, 13, 'Build'), (23, 880, 41, 12, 'Quests'),
                       (1767, 173, 23, 10, '21K'), (1043, 323, 56, 13, 'Kitchen'), (938, 731, 43, 15, 'Cook'),
                       (1028, 755, 46, 11, 'Level U'), (1826, 605, 50, 16, 'IOK"I'), (101, 878, 47, 14, 'Storv'),
                       (180, 901, 63, 20, 'Refinery'), (805, 1050, 154, 20, 'Mys cal Battle Modes'),
                       (968, 1051, 69, 14, 'Resonating'), (990, 1065, 25, 12, 'Hall'), (1068, 1056, 41, 14, 'Guild')]
HU_AFTER_BOXES = [(104, 64, 45, 13, 'District'), (40, 90, 29, 14, '1411'), (18, 307, 37, 10, '25:19:'),  # hu_after
                  (1033, 326, 57, 13, 'Kitchen'), (1043, 568, 46, 11, '4m 57s'), (1761, 17, 67, 13, '3000/3000'),
                  (1540, 76, 22, 10, '18K'), (1759, 176, 23, 11, '21K'), (1817, 614, 13, 11, '10'),
                  (19, 702, 49, 15, 'R*sts'), (938, 731, 43, 15, 'Cook'), (25, 781, 36, 13, 'Build'),
                  (1025, 755, 51, 11, 'S eed U'), (23, 880, 41, 12, "Quest'"), (101, 878, 47, 14, 'Storv'),
                  (180, 901, 63, 20, 'Refinery'), (805, 1050, 154, 20, 'Mys cal Battle Modes'),
                  (968, 1050, 141, 20, 'Resonating Guild'), (990, 1065, 25, 12, 'Hall')]
RQ_CK_W_BOXES = [(105, 64, 44, 13, 'District'), (103, 79, 48, 13, 'PrevW'), (39, 90, 31, 14, '1451'),  # 42848/rq_ck_w
                 (19, 307, 49, 10, '23:10:13'), (19, 704, 49, 13, 'Requests'), (26, 781, 35, 13, 'Build'),
                 (101, 878, 47, 14, 'Storv'), (23, 880, 41, 12, 'Quests'), (180, 902, 63, 19, 'Refinery'),
                 (53, 921, 71, 24, '80 Level?'), (805, 1050, 52, 15, 'Mys cal'), (812, 1066, 38, 10, 'House'),
                 (1585, 59, 20, 11, 'Full'), (1803, 159, 24, 10, '23K'), (1858, 924, 62, 22, "Worl l'"),
                 (968, 1051, 141, 19, 'Resonating Guild'), (875, 1057, 83, 13, 'Battle Modes'), (990, 1065, 25, 12, 'Hall')]
RQ0_BOXES = [(750, 329, 425, 59, 'Kitchen Upgraded'), (1112, 471, 86, 18, '60 ? 100'),    # Hermes rq0 (POPUP)
             (869, 1010, 182, 22, 'Tapto Close')]
LU_COMPACT = (1149, 300)                 # compact Level Up disc on 42848/rq_ck_k
KITCHEN_PIN = (1110, 300)                # Kitchen pin on 57584/hu_world
P, P2 = (700, 300), (1204, 498)          # synthetic pin places (icons on the ICON_STEP grid)
SPEED_UP = (1052, 730)                   # hourglass disc on 57584/hu_after - NEVER a Level Up
BM0 = SPECTRE / 'trash' / 'shots-38632' / 'bm_0.png'     # Ore Refinery selected (label + Smelt/Level Up radial)
BM0_BOXES = [(904, 356, 116, 18, 'Ore Refinery?'), (29, 748, 39, 14, 'Build'), (25, 858, 46, 13, 'Quests'),
             (117, 892, 85, 18, 'Held x16.'), (1041, 692, 51, 17, 'Smelt'), (1142, 719, 51, 12, 'Level U')]
RW0_BOXES = [(899, 355, 113, 18, '(ore Refineryl'), (1045, 689, 51, 18, 'Smelt'),       # trash/shots-38632/rw_0
             (1147, 713, 50, 13, 'Level U')]
BM0_QUEST_BOXES = [b for b in BM0_BOXES if b[1] < 880] + [(180, 901, 63, 20, 'Refinery')]
REFINERY_LU = (1167, 695)
EDGE_PIN, EDGE_ICON = (1630, 58), (1635, 69)   # pin right of ICON_BAND (x > 1600), its compact disc beside it


def near(a, b, tol=3):
    return max(abs(x - y) for x, y in zip(a, b)) <= tol


def paste(dst, src, c, half, at):
    dst.paste(src.crop((c[0] - half, c[1] - half, c[0] + half + 1, c[1] + half + 1)), (at[0] - half, at[1] - half))
    return dst


def world(pins=(P,), compact=()):
    """Synthetic WORLD frame with real Kitchen pins at `pins` and real compact Level Up discs at `compact`."""
    img = frame('WORLD')
    for at in pins:
        paste(img, real(S57 / 'hu_world.png'), KITCHEN_PIN, 22, at)
    for at in compact:
        paste(img, real(S42 / 'rq_ck_k.png'), LU_COMPACT, 34, at)
    return img


def refinery_world():
    """bm_0 (Refinery selected) with the 57584/hu_world quest tracker pill pasted in (bm_0's tracker
    shows another quest, no orange pill)."""
    img = real(BM0)
    img.paste(real(S57 / 'hu_world.png').crop(hu.QUEST_WIN), hu.QUEST_WIN[:2])
    return img


def icon_of(pin):
    return pin[0] + 5, pin[1] + 12


def relabel(boxes, old, new):
    return [(*b[:4], b[4].replace(old, new)) for b in boxes]


class Detectors(unittest.TestCase):
    def test_pins_on_live_frames(self):
        cases = {S57 / 'hu_world.png': [(1594, 68), (1390, 180), (1110, 300)],
                 S57 / 'hu_go.png': [(1586, 72), (1382, 182), (1100, 304)],
                 S57 / 'hu_after.png': [(1586, 72), (1380, 182)],          # Kitchen pin gone: upgrade started
                 S42 / 'rq_ck_w.png': [(1630, 56), (1428, 164)], S42 / 'rq_ck_k.png': [(1630, 56), (1428, 164)],
                 KITCHEN: [(1586, 72), (1382, 182), (1098, 304)],
                 SPECTRE / 'shots-59732' / 'hu_world.png': [(1376, 122), (1100, 250)],   # fog
                 SPECTRE / 'shots-59732' / 'hu_cam1.png': [(1598, 230), (1382, 352), (1082, 504)]}
        for path, want in cases.items():
            with self.subTest(f'{path.parent.name}/{path.name}'):
                got = hu.upgrade_pins(real(path))
                self.assertEqual(len(got), len(want), got)
                self.assertTrue(all(near(g, w) for g, w in zip(got, want)), got)
        for name, want in (('hm_requests.png', [(1418, 94)]), ('spire_sel.png', [(1436, 104)]),
                           ('tower_tap.png', [(1736, 152), (1472, 282)])):
            with self.subTest(name):
                got = hu.upgrade_pins(hermes(name))
                self.assertTrue(len(got) == len(want) and all(near(g, w) for g, w in zip(got, want)), got)

    def test_no_pins_off_the_world(self):
        self.assertEqual(hu.upgrade_pins(real(S57 / 'hu_bread.png')), [])
        for name in ('hm_up3.png', 'rq0.png', 'hm_build_menu.png', 'complete1.png', 'zone2.png'):
            with self.subTest(name):
                self.assertEqual(hu.upgrade_pins(hermes(name)), [])
        self.assertEqual(hu.upgrade_pins(frame('WORLD')), [])

    def test_pins_are_searched_not_fixed(self):
        img = world()
        self.assertEqual(v.classify(img), 'WORLD')
        self.assertEqual(hu.upgrade_pins(img), [P])
        self.assertEqual(hu.level_icons(img), [])
        self.assertEqual(hu.upgrade_pins(world((P, P2))), [P, P2])     # topmost first

    def test_level_icons(self):
        self.assertEqual(hu.level_icons(real(S42 / 'rq_ck_k.png')), [LU_COMPACT])
        self.assertEqual(hu.spire_icon(real(S42 / 'rq_ck_k.png')), LU_COMPACT)   # shared with the Spire icon
        self.assertEqual(hu.level_icons(hermes('spire_sel.png')), [ICON])
        self.assertEqual(hu.level_icons(real(SPECTRE / 'shots-8632' / 'hu_world.png')), [ICON])
        for path in (S42 / 'rq_ck_w.png', S57 / 'hu_world.png', KITCHEN):
            with self.subTest(path.name):
                self.assertEqual(hu.level_icons(real(path)), [])
        self.assertEqual(hu.level_icons(frame('WORLD')), [])
        img = world((), (icon_of(P),))
        self.assertEqual(hu.level_icons(img), [icon_of(P)])
        self.assertEqual(hu.upgrade_pins(img), [])

    def test_arrow_up_is_not_the_hourglass(self):
        for img, xy in ((real(S42 / 'rq_ck_k.png'), LU_COMPACT), (hermes('spire_sel.png'), ICON),
                        (real(SPECTRE / 'shots-25208' / 'hu_tower.png'), (915, 378)),
                        (real(KITCHEN), (1051, 730)), (hermes('hm_requests.png'), DISC)):
            with self.subTest(xy):
                self.assertTrue(hu.arrow_up(img, xy))
        self.assertFalse(hu.arrow_up(real(S57 / 'hu_after.png'), SPEED_UP))

    def test_speed_up_is_never_level_up(self):
        img = real(S57 / 'hu_after.png')
        self.assertIsNone(hu.building_level_up(img, HU_AFTER_BOXES, 'kitchen'))          # 'eed' guard
        self.assertIsNone(hu.building_level_up(img, relabel(HU_AFTER_BOXES, 'S eed U', 'Level U'),
                                               'kitchen'))                              # pixel guard
        self.assertIsNone(hu.building_level_up(img, HU_AFTER_BOXES, None))

    def test_speed_up_text_unread(self):
        # fix-review: the Cook-anchor fallback (Level Up text unread) must not reach the hourglass
        img = real(S57 / 'hu_after.png')
        self.assertIsNone(hu.building_level_up(img, [b for b in HU_AFTER_BOXES if b[4] != 'S eed U'], 'kitchen'))
        self.assertIsNone(hu.building_level_up(img, relabel(HU_AFTER_BOXES, 'S eed U', 'Spe d Up'), 'kitchen'))

    def test_refinery_radial_live(self):
        # fix-review: the 'Ore Refinery' label sits ~206 px left of its 'Level U' (NAME_DX, not LABEL_DX)
        self.assertEqual(hu.building_level_up(real(BM0), BM0_BOXES, 'refinery'), REFINERY_LU)
        self.assertEqual(hu.building_level_up(real(BM0.with_name('rw_0.png')), RW0_BOXES, 'refinery'), (1168, 689))
        self.assertIsNone(hu.building_level_up(real(BM0), BM0_BOXES, 'kitchen'))
        self.assertTrue(hu.quest_pill(refinery_world()))
        self.assertFalse(hu.quest_pill(real(BM0)))
        self.assertEqual(hu.quest_building(BM0_QUEST_BOXES), 'refinery')

    def test_full_badge_is_no_pin(self):
        img = real(SPECTRE / 'trash' / 'shots-48532' / 'dg_cam_2.png')    # 'Full' production badge at (1782,888)
        self.assertEqual(v.classify(img), 'WORLD')
        self.assertEqual(hu.upgrade_pins(img), [])

    def test_icon_beside_an_edge_pin(self):
        img = world((), (EDGE_ICON,))
        self.assertEqual(hu.level_icons(img), [])                         # outside ICON_BAND
        self.assertEqual(hu.level_icons(img, hu.near_band(img, EDGE_PIN)), [EDGE_ICON])
        self.assertEqual(hu.upgrade_pins(world((EDGE_PIN,))), [EDGE_PIN])

    def test_building_level_up_any_building(self):
        k = real(KITCHEN)
        self.assertEqual(hu.building_level_up(k, KITCHEN_BOXES, None), (1051, 730))
        self.assertEqual(hu.building_level_up(k, KITCHEN_BOXES + [(1040, 340, 40, 12, 'Level 4')], None), (1051, 730))
        self.assertEqual(hu.building_level_up(real(S57 / 'hu_world.png'), HU57584_WORLD_BOXES, None), (1051, 730))
        # the 'Refinery' tracker label is below the Kitchen's radial: never lent to it
        self.assertIsNone(hu.building_level_up(real(S57 / 'hu_world.png'), HU57584_WORLD_BOXES, 'refinery'))

    def test_title_name(self):
        self.assertEqual(hu.title_name(HU_BREAD_BOXES), 'kitchen')
        self.assertEqual(hu.title_name(DIALOG_BOXES), 'radiant spire')
        self.assertIsNone(hu.title_name(WORLD_BOXES))

    def test_quest_tracker(self):
        self.assertEqual(hu.quest_building(HU57584_WORLD_BOXES), 'refinery')
        self.assertEqual(hu.quest_building(RQ_CK_W_BOXES), 'refinery')
        self.assertIsNone(hu.quest_building(WORLD_BOXES))
        self.assertIsNone(hu.quest_building([(900, 370, 100, 20, 'Ore Refinery')]))   # outside the tracker
        for img in (real(S57 / 'hu_world.png'), hermes('hm_requests.png'), hermes('quest1.png'),
                    real(S42 / 'rq_ck_w.png')):
            self.assertTrue(hu.quest_pill(img))
        for name in ('zone2.png', 'hm_up3.png'):
            self.assertFalse(hu.quest_pill(hermes(name)), name)

    def test_kitchen_dialog_live(self):
        img = real(S57 / 'hu_bread.png')
        self.assertTrue(hu.back_plate(img))
        self.assertEqual(hu.parse_requirement(HU_BREAD_BOXES), (4, 4))
        self.assertEqual(hu.parse_queue(HU_BREAD_BOXES), (0, 2))
        self.assertEqual(hu.missing_cards(img, HU_BREAD_BOXES), [])
        self.assertTrue(near(hu._centre(hu._line(HU_BREAD_BOXES, 'level up')), hu.LEVEL_UP_BTN, hu.BTN_NEAR))
        with mock.patch.object(v, 'tap') as tap:
            for xy in ((771, 999), (537, 1040)):                    # 'Complete Now' text / plate edge
                with self.assertRaises(RuntimeError):
                    hu._tap(xy, 0)
        tap.assert_not_called()

    def test_overlay_live(self):
        img = hermes('rq0.png')
        self.assertEqual(v.classify(img), 'POPUP')
        self.assertFalse(hu.back_plate(img))
        self.assertFalse(v.is_confirm_dialog(img))
        self.assertTrue(near(hu._centre(hu._line(RQ0_BOXES, 'close')), hs.TOAST_CLOSE))


class Flow(unittest.TestCase):
    def run_ua(self, frames, boxes, budget=1, dry_run=False):
        dev = FakeDevice(self, frames, boxes=boxes)
        rc = hu.upgrade_all(budget, dry_run)
        self.assertNotIn(NO_BACK_KEY, dev.taps)
        l, t, r, b = hu.COMPLETE_NOW
        self.assertFalse([xy for xy in dev.taps if l <= xy[-2] <= r and t <= xy[-1] <= b])
        return dev, rc

    def ready(self, pin=P):
        """pin tap -> compact radial -> Kitchen dialog 4/4 (frames)."""
        return [world((), (icon_of(pin),)), real(S57 / 'hu_bread.png'), real(S57 / 'hu_bread.png')]

    def test_pin_compact_level_up(self):
        dev, rc = self.run_ua([world(), world()] + self.ready() + [real(S57 / 'hu_after.png')],
                              {'ua_read0': HU_BREAD_BOXES})
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, [P, icon_of(P), hu.LEVEL_UP_BTN])
        self.assertIn('kitchen upgrade started', dev.out.getvalue())

    def test_resource_short_is_parked_next_pin(self):
        two = world((P, P2))
        forge = relabel(dialog('5/7'), 'Radiant Spire', 'Forge')
        frames = [two, two, world((P2,), (icon_of(P),)), hermes('hm_up3.png'), hermes('hm_up3.png'),
                  hermes('hm_confirmed2.png'), two] + self.ready(P2) + [real(S57 / 'hu_after.png')]
        dev, rc = self.run_ua(frames, {'ua_read0': forge, 'ua_read1': HU_BREAD_BOXES})
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, [P, icon_of(P), hu.BACK_PLATE, P2, icon_of(P2), hu.LEVEL_UP_BTN])
        self.assertIn("parked ['forge']", dev.out.getvalue())

    def test_pin_and_body_open_nothing(self):
        w = world()
        dev, rc = self.run_ua([w] * 9, {})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [P, (P[0] - 107, P[1] + 124)])
        self.assertEqual(dev.shots, ['ua_world', 'ua_pins0', 'ua_pin0', 'ua_pin0_p1', 'ua_pin0_p2',
                                     'ua_body0', 'ua_body0_p1', 'ua_body0_p2', 'ua_pins1'])

    def test_queue_full_stops(self):
        dev, rc = self.run_ua([world(), world(), world((), (icon_of(P),)), hermes('hm_up3.png'),
                               hermes('hm_up3.png'), hermes('hm_confirmed2.png')],
                              {'ua_read0': dialog('7/7', '2/2')}, budget=2)
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [P, icon_of(P), hu.BACK_PLATE])
        self.assertNotIn('ua_pins1', dev.shots)

    def test_diamond_confirm_is_cancelled(self):
        dev, rc = self.run_ua([world(), world()] + self.ready()
                              + ['DIALOG', real(S57 / 'hu_bread.png'), hermes('hm_confirmed2.png'), world()],
                              {'ua_read0': HU_BREAD_BOXES})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [P, icon_of(P), hu.LEVEL_UP_BTN, v.CONFIRM_CANCEL, hu.BACK_PLATE])

    def test_dry_run_never_levels_up(self):
        dev, rc = self.run_ua([world(), world()] + self.ready() + [hermes('hm_confirmed2.png')],
                              {'ua_read0': HU_BREAD_BOXES}, dry_run=True)
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, [P, icon_of(P), hu.BACK_PLATE])

    def test_quest_building_via_the_tracker(self):
        # fix-review: the LIVE-open tracker tap comes LAST (after the measured pins)
        refinery = relabel(KITCHEN_BOXES, 'Kitchen', 'Ore Refinery')
        dev, rc = self.run_ua([real(S57 / 'hu_world.png'), frame('WORLD'), real(S57 / 'hu_world.png'),
                               real(KITCHEN), real(S57 / 'hu_bread.png'), real(S57 / 'hu_bread.png'),
                               real(S57 / 'hu_after.png')],
                              {'ua_world': HU57584_WORLD_BOXES, 'ua_quest': refinery,
                               'ua_readq': relabel(HU_BREAD_BOXES, 'Kitchen', 'Ore Refinery')})
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, [hu.QUEST_TAP, (1051, 730), hu.LEVEL_UP_BTN])
        self.assertEqual(dev.shots[:3], ['ua_world', 'ua_pins0', 'ua_qworld'])
        self.assertIn('ore refinery upgrade started', dev.out.getvalue())

    def test_quest_tap_to_unknown_stops(self):
        dev, rc = self.run_ua([real(S57 / 'hu_world.png'), frame('WORLD'), real(S57 / 'hu_world.png'),
                               'UNKNOWN', 'UNKNOWN', 'UNKNOWN'], {'ua_world': HU57584_WORLD_BOXES})
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual(dev.taps, [hu.QUEST_TAP])

    def test_quest_tap_opens_nothing(self):
        dev, rc = self.run_ua([real(S57 / 'hu_world.png'), frame('WORLD'), real(S57 / 'hu_world.png')]
                              + ['WORLD'] * 3, {'ua_world': HU57584_WORLD_BOXES})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [hu.QUEST_TAP])
        self.assertIn('quest refinery: no Level Up reached', dev.out.getvalue())

    def test_quest_tap_unread_dialog_is_closed(self):
        dev, rc = self.run_ua([real(S57 / 'hu_world.png'), frame('WORLD'), real(S57 / 'hu_world.png')]
                              + [hermes('hm_up3.png')] * 3 + [hermes('hm_confirmed2.png')],
                              {'ua_world': HU57584_WORLD_BOXES})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [hu.QUEST_TAP, hu.BACK_PLATE])

    def test_quest_selected_refinery_first(self):
        dev, rc = self.run_ua([refinery_world(), hermes('hm_up3.png'), real(S57 / 'hu_bread.png'),
                               real(S57 / 'hu_after.png')],
                              {'ua_world': BM0_QUEST_BOXES,
                               'ua_readq': relabel(HU_BREAD_BOXES, 'Kitchen', 'Ore Refinery')})
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, [REFINERY_LU, hu.LEVEL_UP_BTN])
        self.assertNotIn('ua_pins0', dev.shots)                     # budget 1 spent on the quest building

    def test_parked_quest_building_is_not_reopened(self):
        ref = relabel(dialog('5/7'), 'Radiant Spire', 'Ore Refinery')
        dev, rc = self.run_ua([refinery_world(), hermes('hm_up3.png'), hermes('hm_up3.png'),
                               hermes('hm_confirmed2.png'), world(), hermes('hm_up3.png'),
                               hermes('hm_confirmed2.png'), world()],
                              {'ua_world': BM0_QUEST_BOXES, 'ua_readq': ref, 'ua_pin0': ref})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [REFINERY_LU, hu.BACK_PLATE, P, hu.BACK_PLATE])
        self.assertIn('ore refinery already parked this run', dev.out.getvalue())
        self.assertNotIn('ua_qworld', dev.shots)                    # parked quest building: no tracker tap

    def test_queue_full_via_the_quest_building(self):
        dev, rc = self.run_ua([refinery_world(), hermes('hm_up3.png'), hermes('hm_up3.png'),
                               hermes('hm_confirmed2.png')],
                              {'ua_world': BM0_QUEST_BOXES,
                               'ua_readq': relabel(dialog('7/7', '2/2'), 'Radiant Spire', 'Ore Refinery')},
                              budget=2)
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [REFINERY_LU, hu.BACK_PLATE])
        self.assertEqual(dev.shots[-1], 'hu_close')

    def test_pin_opens_the_dialog(self):
        dev, rc = self.run_ua([world(), world(), hermes('hm_up3.png'), real(S57 / 'hu_after.png')],
                              {'ua_pin0': dialog('7/7')})
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, [P, hu.LEVEL_UP_BTN])
        self.assertIn('radiant spire upgrade started', dev.out.getvalue())

    def test_body_tap_opens_the_radial(self):
        dev, rc = self.run_ua([world()] * 5 + self.ready() + [real(S57 / 'hu_after.png')],
                              {'ua_read0': HU_BREAD_BOXES})
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, [P, (P[0] - 107, P[1] + 124), icon_of(P), hu.LEVEL_UP_BTN])

    def test_no_body_tap_when_the_pin_moved(self):
        dev, rc = self.run_ua([world(), world()] + ['WORLD'] * 4, {})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [P])

    def test_pin_unread_dialog_is_closed(self):
        dev, rc = self.run_ua([world(), world()] + [hermes('hm_up3.png')] * 3
                              + [hermes('hm_confirmed2.png'), world()], {})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [P, hu.BACK_PLATE])
        self.assertIn('closed via its back plate - parked', dev.out.getvalue())

    def test_selected_radial_before_the_pin_is_ignored(self):
        img = real(S57 / 'hu_world.png')
        boxes = [b for b in HU57584_WORLD_BOXES if b[4] != 'Refinery']
        pin = hu.upgrade_pins(img)[0]
        names = ['ua_world', 'ua_pins0'] + [f'ua_{s}0{p}' for s in ('pin', 'body') for p in ('', '_p1', '_p2')]
        dev, rc = self.run_ua([img] * 8 + ['WORLD'], {n: boxes for n in names})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [pin, (pin[0] - 107, pin[1] + 124)])   # never the Kitchen's (1051,730)

    def test_edge_pin_finds_its_icon(self):
        dev, rc = self.run_ua([world((EDGE_PIN,)), world((EDGE_PIN,)), world((), (EDGE_ICON,)),
                               real(S57 / 'hu_bread.png'), real(S57 / 'hu_bread.png'),
                               real(S57 / 'hu_after.png')], {'ua_read0': HU_BREAD_BOXES})
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, [EDGE_PIN, EDGE_ICON, hu.LEVEL_UP_BTN])

    def test_stuck_after_a_start_is_rc0(self):
        dev, rc = self.run_ua([world(), world()] + self.ready() + [real(S57 / 'hu_after.png'), 'UNKNOWN'],
                              {'ua_read0': HU_BREAD_BOXES}, budget=2)
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertIn('1 level-up(s) already started -> rc 0', dev.out.getvalue())

    def test_pin_tap_to_unknown_stops(self):
        dev, rc = self.run_ua([world(), world(), 'UNKNOWN', 'UNKNOWN', 'UNKNOWN'], {})
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual(dev.taps, [P])

    def test_not_on_the_world_stops(self):
        dev, rc = self.run_ua(['UNKNOWN'], {})
        self.assertEqual(rc, 1)
        self.assertEqual(dev.taps, [])

    def test_budget_exhausted(self):
        dev, rc = self.run_ua([real(S57 / 'hu_world.png')], {'ua_world': HU57584_WORLD_BOXES}, budget=0)
        self.assertEqual(rc, 4)
        self.assertEqual(dev.taps, [])
        self.assertEqual(dev.shots, ['ua_world'])

    def test_upgrade_running_never_taps_speed_up(self):
        after = real(S57 / 'hu_after.png')
        boxes = [b for b in HU_AFTER_BOXES if b[4] != 'Refinery']
        names = ['ua_world'] + [f'ua_{s}{k}{p}' for k in (0, 1) for s in ('pin', 'body') for p in ('', '_p1', '_p2')]
        dev, rc = self.run_ua([after] * 16, {n: boxes for n in names})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [(1586, 72), (1479, 196), (1380, 182), (1273, 306)])
        self.assertFalse([t for t in dev.taps if near(t, SPEED_UP, 15)])
        self.assertEqual(len(dev.shots), 16)                       # bounded: ua_pins2 sees only tried pins


class Main(unittest.TestCase):
    def test_spire_then_pins(self):
        frames = [hermes('spire_sel.png'), hermes('spire_sel2.png'), hermes('spire_sel2.png'),
                  hermes('hm_confirmed2.png'), hermes('hm_confirmed2.png'), hermes('hm_confirmed2.png'),
                  world(), world()] + self.ready() + [real(S57 / 'hu_after.png'), world()]
        dev = FakeDevice(self, frames, boxes={'hu_world': WORLD_BOXES[1:2], 'hu_read': DIALOG_BOXES,
                                              'ua_read0': HU_BREAD_BOXES})
        rc = hu.main([])
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, [ICON, GO, P, icon_of(P), hu.LEVEL_UP_BTN])
        self.assertEqual(dev.shots[-1], 'ua_pins1')                 # budget 2: one more pin look

    ready = Flow.ready

    def test_spire_stuck_skips_upgrade_all(self):
        with mock.patch.object(hu, 'spire', return_value=1), mock.patch.object(hu, 'upgrade_all') as ua:
            self.assertEqual(hu.main([]), 1)
        ua.assert_not_called()

    def test_spire_started_leaves_one(self):
        with mock.patch.object(hu, 'spire', return_value=0), \
                mock.patch.object(hu, 'upgrade_all', return_value=4) as ua:
            self.assertEqual(hu.main([]), 0)
        ua.assert_called_once_with(1, False)
        with mock.patch.object(hu, 'spire', return_value=4), \
                mock.patch.object(hu, 'upgrade_all', return_value=1) as ua:
            self.assertEqual(hu.main(['--dry-run']), 1)
        ua.assert_called_once_with(2, True)
        with mock.patch.object(hu, 'spire', return_value=0), \
                mock.patch.object(hu, 'upgrade_all', return_value=1):
            self.assertEqual(hu.main([]), 0)                          # a started Spire upgrade wins

    def test_upgraded_overlay_is_closed_first(self):
        dev = FakeDevice(self, [hermes('rq0.png'), hermes('hm_requests.png'), hermes('hm_up3.png'),
                                hermes('hm_up3.png')] + [hermes('hm_confirmed2.png')] * 3,
                         boxes={'hu_world': RQ0_BOXES, 'hu_world_u': WORLD_BOXES, 'hu_read': DIALOG_BOXES})
        with mock.patch.object(hu, 'upgrade_all', return_value=4):
            rc = hu.main([])
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [hs.TOAST_CLOSE, DISC, GO])
        self.assertEqual(dev.shots[:2], ['hu_world', 'hu_world_u'])


if __name__ == '__main__':
    unittest.main()
