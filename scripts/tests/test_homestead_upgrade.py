"""T103 homestead phase 2: Radiant Spire upgrade - detectors on Hermes' live frames + FakeVision flows."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402
import afk_homestead_upgrade as hu  # noqa: E402
from fake_vision import FakeDevice, frame  # noqa: E402
from PIL import ImageDraw  # noqa: E402
from test_homestead import HERMES, hermes  # noqa: E402

# real WinRT OCR line boxes (ocr.ps1 -Boxes), recorded 2026-11-04 on the frames named
WORLD_BOXES = [(851, 173, 97, 17, 'Radiant Spire'), (25, 781, 37, 13, 'Build'),   # hm_requests
               (922, 731, 75, 19, 'Level Up'), (875, 1057, 84, 13, 'Battle Modes')]
DIALOG_BOXES = [(844, 364, 199, 27, '? Radiant Spire i'),                          # hm_up3
                (477, 436, 302, 26, 'Upgrade Requirement (5/7)'),
                (482, 601, 99, 12, 'Level 5 Kitchen'), (612, 601, 72, 13, '3704/28K'),
                (726, 601, 79, 13, '653K/6800'), (845, 601, 73, 13, '1836/1800'),
                (949, 601, 95, 17, 'Level 5 Forge'), (1078, 601, 72, 13, '37K/5800'),
                (1179, 602, 99, 15, 'AFK stage: 80'), (477, 715, 202, 27, 'Upgrade Rewards'),
                (684, 984, 175, 29, 'Complete Now'), (770, 1023, 27, 11, '1800'),
                (1201, 985, 102, 29, 'Level Up'), (1451, 91, 22, 12, '0/2')]
DISC = (956, 686)
NO_BACK_KEY = ('key', 4)
SPECTRE = Path(__file__).resolve().parents[3] / 'spectre' / '.spectre'
ICON_FRAMES = [HERMES / 'spire_sel.png', SPECTRE / 'shots-8632' / 'hu_world.png',   # T103b live
               HERMES / 'b16b.png', HERMES / 'end1.png']
ICON = (915, 171)
# T103c: real WinRT boxes of shots-80480/hu_world (Kitchen selected after 'Go'; 'Level U' as read)
KITCHEN_BOXES = [(1761, 17, 67, 13, '3000/3000'), (1033, 326, 57, 13, 'Kitchen'),
                 (938, 731, 43, 15, 'Cook'), (1028, 755, 46, 11, 'Level U'), (25, 781, 36, 15, 'Build'),
                 (180, 901, 63, 20, 'Refinery'), (53, 921, 74, 22, 'p Level 5.')]
KITCHEN = SPECTRE / 'shots-80480' / 'hu_world.png'
EXIT_GAME = SPECTRE / 'shots-9308' / 'hu_world.png'
DRAGS = [('swipe', *d, hu.CAMERA_MS, 1.5) for d in hu.CAMERA_DRAGS]
# T103d: the tower tap fallback. Real WinRT boxes of tower_tap.png (Hermes: after a tower tap)
TOWER_TAP = HERMES / 'tower_tap.png'
TOWER_BOXES = [(25, 781, 37, 13, 'Build'), (180, 901, 63, 20, 'Refinery'), (927, 731, 66, 15, 'Interact'),
               (1068, 1056, 42, 14, 'Guild')]
INTERACT = (953, 683)
GO = (531, 631)                           # T103f: 'Go' pill under 'Level 5 Kitchen' on hm_up3
KITCHEN_LU = (1051, 730)                  # T103f: the Kitchen's radial Level Up on shots-80480
TOWER_K = (507, 528)                      # spire_tower on shots-80480 (operator tapped ~(520,450))
TOWERS = {TOWER_TAP: (915, 500), KITCHEN: TOWER_K, HERMES / 'spire_sel.png': (917, 304),
          HERMES / 'hm_requests.png': (898, 284), HERMES / 'hm_confirmed2.png': (904, 282),
          HERMES / 'ck2.png': (504, 510),                                        # deep night
          SPECTRE / 'shots-66556' / 'norm_3.png': (813, 148),                    # day, tower at the top
          SPECTRE / 'shots-47000' / 'hs_0_world.png': (917, 264),                # sunset
          SPECTRE / 'shots-8632' / 'hu_world.png': (916, 308)}
NO_TOWER = [SPECTRE / 'shots-76112' / 'dg_cam_3.png', SPECTRE / 'shots-76112' / 'dg_cam_4.png',  # sunset
            SPECTRE / 'shots-79852' / 'dg_cam_3.png', HERMES / 'hm_up3.png']        # night wheat, dialog


def real(path):
    if not path.exists():
        raise unittest.SkipTest(f'frame missing: {path}')
    from make_frame_manifest import load_rgb
    return load_rgb(path)


def icon_frame(xy, arrow='up', disc=(234, 230, 229), head=15):
    """Synthetic WORLD frame with the T103b upgrade icon (measured colours) at xy:
    arrow head base 2*head+1 px wide (live 29..32), shaft 11 px."""
    img = frame('WORLD')
    d, (x, y) = ImageDraw.Draw(img), xy
    d.ellipse((x - 27, y - 27, x + 27, y + 27), fill=disc)
    s = -1 if arrow == 'up' else 1
    if arrow:
        d.polygon([(x, y + 19 * s), (x - head, y + 7 * s), (x + head, y + 7 * s)], fill=(102, 83, 85))
        d.rectangle((x - 5, min(y + 7 * s, y - 14 * s), x + 5, max(y + 7 * s, y - 14 * s)), fill=(102, 83, 85))
    return img


def beams_frame(axis=(960, 400), s=220, skip=()):
    """Synthetic WORLD frame with the 4 tower beams (measured colour) around axis: outer pair at
    +-s/2, inner pair at +-s/4 and 60 px lower; `skip` drops beams by index (0..3, left to right)."""
    img = frame('WORLD')
    d, (x, y) = ImageDraw.Draw(img), axis
    for i, (dx, dy) in enumerate(((-s / 2, 0), (-s / 4, 60), (s / 4, 60), (s / 2, 0))):
        if i not in skip:
            d.rectangle((x + dx - 5, y + dy - 50, x + dx + 5, y + dy + 50), fill=(245, 220, 112))
    return img


def dialog(met='5/7', queue='0/2'):
    return [(*b[:4], b[4].replace('5/7', met)) if 'Requirement' in b[4]
            else (*b[:4], queue) if b[4] == '0/2' else b for b in DIALOG_BOXES]


class Detectors(unittest.TestCase):
    def test_radial_on_the_selected_spire(self):
        for name in ('hm_requests.png', 'hm_req2.png'):
            with self.subTest(name):
                self.assertEqual(hu.find_radial(hermes(name), WORLD_BOXES), DISC)

    def test_radial_where_the_ocr_box_is_off(self):
        # live T102 run: WinRT box centre (932,738), drawn text ~(958,740)
        path = Path(__file__).resolve().parents[3] / 'spectre' / '.spectre' / 'shots-67544' / 'hs_0_world.png'
        if not path.exists():
            self.skipTest(f'frame missing: {path}')
        from make_frame_manifest import load_rgb
        boxes = [(901, 163, 95, 25, 'Radiant Spire'), (895, 725, 75, 27, 'Level Up')]
        self.assertEqual(hu.find_radial(load_rgb(path), boxes), (956, 685))

    def test_radial_needs_label_text_and_disc(self):
        img = hermes('hm_requests.png')
        self.assertIsNone(hu.find_radial(img, [b for b in WORLD_BOXES if 'Spire' not in b[4]]))
        self.assertIsNone(hu.find_radial(img, [b for b in WORLD_BOXES if 'Level' not in b[4]]))
        # same OCR, but no disc on the pixels (hero at the door, nothing selected)
        self.assertIsNone(hu.find_radial(hermes('hm_confirmed2.png'), WORLD_BOXES))
        # the dialog's own 'Level Up' is outside the radial window
        self.assertIsNone(hu.find_radial(hermes('hm_up3.png'), DIALOG_BOXES))

    def test_kitchen_radial_is_not_the_spire(self):
        # T103c live: the Kitchen's radial ('Cook' + 'Level Up') after the operator's 'Go'
        img = real(KITCHEN)
        self.assertEqual(v.classify(img), 'WORLD')
        self.assertIsNone(hu.find_radial(img, KITCHEN_BOXES))
        self.assertIsNone(hu.spire_icon(img))                            # no icon on this frame
        # OCR reading 'Level Up' in full plus a 'Radiant Spire' line in the quest tracker / at the
        # Kitchen label's place: the label must stand above THIS radial
        lu = [(*b[:4], 'Level Up') if b[4] == 'Level U' else b for b in KITCHEN_BOXES]
        self.assertIsNone(hu.find_radial(img, lu + [(56, 901, 200, 20, 'Upgrade the Radiant Spire')]))
        self.assertIsNone(hu.find_radial(img, lu + [(1600, 950, 120, 17, 'Radiant Spire')]))  # below

    def test_label_pairing_keeps_the_spire_radial(self):
        img = hermes('hm_requests.png')
        quest = (56, 901, 200, 20, 'Upgrade the Radiant Spire')
        self.assertEqual(hu.find_radial(img, [quest] + WORLD_BOXES), DISC)   # first label is not it
        far = [(*b[:4], b[4]) if 'Spire' not in b[4] else (300, 173, 97, 17, b[4]) for b in WORLD_BOXES]
        self.assertIsNone(hu.find_radial(img, far))                          # label 650 px left

    def test_exit_game_dialog_start_frame(self):
        img = real(EXIT_GAME)                                            # live 22:28 start frame
        self.assertTrue(v.is_confirm_dialog(img))
        self.assertGreater(v.lum(v.avg(img, v.CONFIRM_CANCEL)), 140)       # white X disc (dark glyph inside)
        ok = v.avg(img, (1142, 710))                                     # the check = EXIT, never tapped
        self.assertGreater(ok[1], ok[0] + 20)

    def test_spire_icon_on_the_live_frames(self):
        for path in ICON_FRAMES:
            with self.subTest(path.name):
                xy = hu.spire_icon(real(path))
                self.assertIsNotNone(xy)
                self.assertLessEqual(max(abs(a - b) for a, b in zip(xy, ICON)), 3)

    def test_spire_icon_not_on_other_frames(self):
        # selected Spire (radial disc is outside the band), hero at the door, the dialog itself
        for name in ('hm_requests.png', 'hm_req2.png', 'hm_confirmed2.png', 'hm_up3.png',
                     'spire_sel2.png', 'hm_build_menu.png'):
            with self.subTest(name):
                self.assertIsNone(hu.spire_icon(hermes(name)))

    def test_spire_icon_is_searched_not_fixed(self):
        for xy in ((420, 120), (1250, 480), ICON):
            with self.subTest(xy):
                got = hu.spire_icon(icon_frame(xy))
                self.assertLessEqual(max(abs(a - b) for a, b in zip(got, xy)), 3)
        self.assertIsNone(hu.spire_icon(icon_frame((960, 800))))          # below the band
        self.assertIsNone(hu.spire_icon(frame('WORLD')))

    def test_spire_icon_shape_tells(self):
        self.assertIsNone(hu.spire_icon(icon_frame(ICON, arrow=None)))     # white orb, no arrow
        self.assertIsNone(hu.spire_icon(icon_frame(ICON, arrow='down')))   # arrow head below
        self.assertIsNone(hu.spire_icon(icon_frame(ICON, head=10)))        # narrow glyph ('i' scroll, pl3)
        big = frame('WORLD')
        ImageDraw.Draw(big).rectangle((700, 100, 1100, 400), fill=(234, 230, 229))
        ImageDraw.Draw(big).rectangle((905, 160, 925, 180), fill=(102, 83, 85))
        self.assertIsNone(hu.spire_icon(big))                              # cloud / cream panel

    def test_spire_tower_on_the_live_frames(self):
        for path, xy in TOWERS.items():
            with self.subTest(path.name):
                got = hu.spire_tower(real(path))
                self.assertIsNotNone(got)
                self.assertLessEqual(max(abs(a - b) for a, b in zip(got, xy)), 3)

    def test_spire_tower_not_on_other_frames(self):
        # golden wheat / reeds at sunset and night, the dialog; synthetic world
        for path in NO_TOWER:
            with self.subTest(path.name):
                self.assertIsNone(hu.spire_tower(real(path)))
        self.assertIsNone(hu.spire_tower(frame('WORLD')))

    def test_spire_tower_is_searched_between_the_beams(self):
        for axis in ((960, 400), (500, 520), (1300, 200)):
            with self.subTest(axis):
                self.assertEqual(hu.spire_tower(beams_frame(axis)), axis)        # on the axis, never a beam
        self.assertEqual(hu.spire_tower(beams_frame(skip=(0,))), (960, 400))     # 3 of 4 (flicker)
        self.assertEqual(hu.spire_tower(beams_frame(skip=(3,))), (960, 400))
        self.assertIsNone(hu.spire_tower(beams_frame(skip=(1, 2))))              # one pair alone
        self.assertIsNone(hu.spire_tower(beams_frame(skip=(0, 3))))
        self.assertIsNone(hu.spire_tower(beams_frame(s=120)))                    # wrong spacing
        self.assertIsNone(hu.spire_tower(beams_frame((960, 900))))               # tap point off the world

    def test_interact_disc_after_the_tower_tap(self):
        img = real(TOWER_TAP)
        self.assertEqual(v.classify(img), 'WORLD')
        self.assertEqual(hu.find_interact(img, TOWER_BOXES), INTERACT)
        self.assertIsNone(hu.find_radial(img, TOWER_BOXES))                   # no Level Up here
        self.assertIsNone(hu.find_interact(img, [b for b in TOWER_BOXES if b[4] != 'Interact']))
        self.assertIsNone(hu.find_interact(img, [(927, 1031, 66, 15, 'Interact')]))  # outside the radial
        self.assertIsNone(hu.find_interact(hermes('hm_confirmed2.png'), TOWER_BOXES))  # word, no disc
        self.assertIsNone(hu.find_interact(frame('WORLD'), TOWER_BOXES))

    def test_dialog_already_open_start_frame(self):
        img = real(SPECTRE / 'shots-82892' / 'hu_world.png')            # live T103 run start frame
        self.assertNotEqual(v.classify(img), 'WORLD')
        self.assertTrue(hu.back_plate(img))
        self.assertEqual(hu.missing_cards(img, DIALOG_BOXES), ['Level 5 Kitchen', '3704/28K'])

    def test_dialog(self):
        img = hermes('hm_up3.png')
        self.assertEqual(hu.parse_requirement(DIALOG_BOXES), (5, 7))
        self.assertEqual(hu.missing_cards(img, DIALOG_BOXES), ['Level 5 Kitchen', '3704/28K'])
        self.assertEqual(hu.parse_queue(DIALOG_BOXES), (0, 2))
        self.assertTrue(hu.back_plate(img))
        self.assertEqual(v.classify(img), 'UNKNOWN')
        self.assertIsNone(hu.parse_requirement(WORLD_BOXES))
        # T103f: the title is not required any more (live hu_read: still fading in, 5/7 read)
        self.assertEqual(hu.parse_requirement([b for b in DIALOG_BOXES if 'Spire' not in b[4]]), (5, 7))
        for name in ('hm_requests.png', 'hm_confirmed2.png', 'hm_build_menu.png'):
            self.assertFalse(hu.back_plate(hermes(name)), name)

    def test_complete_now_is_never_tapped(self):
        with mock.patch.object(v, 'tap') as tap:
            for xy in ((770, 995), (538, 967), (1005, 1047)):
                with self.assertRaises(RuntimeError):
                    hu._tap(xy, 0)
            hu._tap(hu.LEVEL_UP_BTN, 0)
        tap.assert_called_once_with(hu.LEVEL_UP_BTN, 0)

    @unittest.skipUnless(sys.platform == 'win32', 'WinRT OCR')
    def test_real_ocr_boxes(self):
        png = HERMES / 'hm_up3.png'
        if not png.exists():
            self.skipTest(f'frame missing: {png}')
        boxes = v.parse_boxes(v.ocr_png(png, timeout=40, boxes=True))
        if not boxes:
            self.skipTest('OCR unavailable')
        self.assertEqual(hu.parse_requirement(boxes), (5, 7))
        self.assertLessEqual(max(abs(a - b) for a, b in zip(hu._centre(hu._line(boxes, 'level up')),
                                                              hu.LEVEL_UP_BTN)), hu.BTN_NEAR)


class OcrBoxes(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(v.parse_boxes(['922 731 75 19 Level Up', 'Level Up', '1 2 3 Spire', '-3 4 5 6 a b']),
                         [(922, 731, 75, 19, 'Level Up'), (-3, 4, 5, 6, 'a b')])

    def test_switch_only_with_boxes(self):
        done = subprocess.CompletedProcess([], 0, '1 2 3 4 x\n', '')
        with mock.patch.object(v.subprocess, 'run', return_value=done) as run:
            v.ocr_png(Path('a.png'))
            self.assertNotIn('-Boxes', run.call_args[0][0])
            self.assertEqual(v.ocr_png(Path('a.png'), boxes=True), ['1 2 3 4 x'])
            self.assertEqual(run.call_args[0][0][-1], '-Boxes')


class Flow(unittest.TestCase):
    def run_hu(self, frames, boxes, *argv):
        dev = FakeDevice(self, [hermes(f) if isinstance(f, str) and f.endswith('.png') else f
                                for f in frames], boxes=boxes)
        rc = hu.main(list(argv))
        self.assertNotIn(NO_BACK_KEY, dev.taps)       # keyevent BACK opens the exit-game dialog here
        return dev, rc

    def test_requirements_missing_goes_to_the_kitchen(self):
        # T103f: 5/7 with 'Level 5 Kitchen' missing -> its Go; no Kitchen radial after it -> rc 4
        dev, rc = self.run_hu(['hm_requests.png', 'hm_up3.png', 'hm_up3.png', 'hm_confirmed2.png', 'hm_confirmed2.png', 'hm_confirmed2.png'],
                              {'hu_world': WORLD_BOXES, 'hu_read': DIALOG_BOXES})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [DISC, GO])
        self.assertIn("missing: ['Level 5 Kitchen', '3704/28K']", dev.out.getvalue())

    def test_all_met_starts_the_upgrade(self):
        dev, rc = self.run_hu(['hm_requests.png', 'hm_up3.png', 'hm_up3.png', 'hm_confirmed2.png'],
                              {'hu_world': WORLD_BOXES, 'hu_read': dialog('7/7')})
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, [DISC, hu.LEVEL_UP_BTN])

    def test_dry_run_reads_and_closes(self):
        dev, rc = self.run_hu(['hm_requests.png', 'hm_up3.png', 'hm_up3.png', 'hm_confirmed2.png'],
                              {'hu_world': WORLD_BOXES, 'hu_read': dialog('7/7')}, '--dry-run')
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, [DISC, hu.BACK_PLATE])

    def test_queue_full_is_nothing_to_do(self):
        dev, rc = self.run_hu(['hm_requests.png', 'hm_up3.png', 'hm_up3.png', 'hm_confirmed2.png'],
                              {'hu_world': WORLD_BOXES, 'hu_read': dialog('7/7', '2/2')})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [DISC, hu.BACK_PLATE])

    def test_diamond_dialog_after_level_up_is_cancelled(self):
        dev, rc = self.run_hu(['hm_requests.png', 'hm_up3.png', 'hm_up3.png', 'DIALOG', 'hm_up3.png',
                               'hm_confirmed2.png'],
                              {'hu_world': WORLD_BOXES, 'hu_read': dialog('7/7')})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [DISC, hu.LEVEL_UP_BTN, v.CONFIRM_CANCEL, hu.BACK_PLATE])

    def test_level_up_refused(self):
        dev, rc = self.run_hu(['hm_requests.png', 'hm_up3.png', 'hm_up3.png', 'hm_up3.png',
                               'hm_confirmed2.png'],
                              {'hu_world': WORLD_BOXES, 'hu_read': dialog('7/7'), 'hu_after': dialog('7/7')})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [DISC, hu.LEVEL_UP_BTN, hu.BACK_PLATE])

    def test_unknown_screen_after_level_up_stops_without_taps(self):
        dev, rc = self.run_hu(['hm_requests.png', 'hm_up3.png', 'hm_up3.png', 'UNKNOWN'],
                              {'hu_world': WORLD_BOXES, 'hu_read': dialog('7/7')})
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual(dev.taps, [DISC, hu.LEVEL_UP_BTN])

    def test_spire_not_selected_is_nothing_to_do(self):
        # T103c: deselect + the bounded drags first, the icon re-searched after each
        # (T103d: synthetic worlds - hm_confirmed2 shows the tower, which is tapped now)
        dev, rc = self.run_hu(['WORLD'] * 4, {'hu_world': WORLD_BOXES[1:]})
        self.assertEqual(rc, 4)
        self.assertEqual(dev.taps, [v.GROUND, *DRAGS])
        self.assertEqual(dev.shots, ['hu_world', 'hu_cam0', 'hu_cam1', 'hu_cam2'])
        self.assertIn('no tower, also after the camera search', dev.out.getvalue())

    def test_drags_stay_off_the_hud(self):
        for x1, y1, x2, y2 in hu.CAMERA_DRAGS:
            for x, y in ((x1, y1), (x2, y2)):
                self.assertTrue(120 < x < 1800 and 80 < y < 1000, (x, y))
                self.assertGreater(abs(x - 960) + abs(y - 835), 200)    # joystick
            self.assertGreaterEqual(((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5, 300)

    def test_camera_search_finds_the_icon(self):
        dev, rc = self.run_hu(['WORLD', 'WORLD', 'spire_sel.png', 'spire_sel2.png',
                               'spire_sel2.png', 'hm_confirmed2.png', 'hm_confirmed2.png', 'hm_confirmed2.png'],
                              {'hu_world': [], 'hu_read': DIALOG_BOXES})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [v.GROUND, DRAGS[0], ICON, GO])

    def test_kitchen_selected_live_frame(self):
        # T103c live (shots-80480): no Spire radial/icon, never the Kitchen's Level Up. T103d: the
        # tower is on screen -> tower tap -> tower_tap.png (Hermes) -> Interact -> dialog 5/7
        dev, rc = self.run_hu([real(KITCHEN), real(TOWER_TAP), 'spire_sel2.png', 'spire_sel2.png',
                               'hm_confirmed2.png', 'hm_confirmed2.png', 'hm_confirmed2.png'],
                              {'hu_world': KITCHEN_BOXES, 'hu_tower': TOWER_BOXES, 'hu_read': DIALOG_BOXES})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [TOWER_K, INTERACT, GO])
        self.assertIn('tapping the Spire tower', dev.out.getvalue())

    def test_tower_tap_all_met_starts_the_upgrade(self):
        dev, rc = self.run_hu([real(KITCHEN), real(TOWER_TAP), 'spire_sel2.png', 'spire_sel2.png',
                               'hm_confirmed2.png'],
                              {'hu_world': KITCHEN_BOXES, 'hu_tower': TOWER_BOXES, 'hu_read': dialog('7/7')})
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, [TOWER_K, INTERACT, hu.LEVEL_UP_BTN])

    def test_tower_tap_without_interact_stops(self):
        # radial not read / another screen after the tower tap: bounded stop, no blind tap
        for name, after, boxes in (('no OCR', real(TOWER_TAP), []), ('no disc', 'hm_confirmed2.png', TOWER_BOXES),
                                   ('not world', 'UNKNOWN', TOWER_BOXES)):
            with self.subTest(name):
                dev, rc = self.run_hu([real(KITCHEN), after], {'hu_world': KITCHEN_BOXES, 'hu_tower': boxes})
                self.assertEqual(rc, 1, dev.out.getvalue())
                self.assertEqual(dev.taps, [TOWER_K])

    def test_interact_tap_retried_once_then_stops(self):
        t = real(TOWER_TAP)
        dev, rc = self.run_hu([real(KITCHEN), t, t, t], {'hu_world': KITCHEN_BOXES, 'hu_tower': TOWER_BOXES})
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual([x[-2:] for x in dev.taps], [TOWER_K, INTERACT, INTERACT])

    def test_camera_search_finds_the_tower(self):
        dev, rc = self.run_hu(['WORLD', 'WORLD', real(KITCHEN), real(TOWER_TAP), 'spire_sel2.png',
                               'spire_sel2.png', 'hm_confirmed2.png', 'hm_confirmed2.png', 'hm_confirmed2.png'],
                              {'hu_world': [], 'hu_tower': TOWER_BOXES, 'hu_read': DIALOG_BOXES})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [v.GROUND, DRAGS[0], TOWER_K, INTERACT, GO])

    def test_camera_search_off_the_world_stops(self):
        dev, rc = self.run_hu(['WORLD', 'WORLD', 'UNKNOWN'], {'hu_world': []})
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual(dev.taps, [v.GROUND, DRAGS[0]])

    def test_live_selected_spire_start_taps_interact_directly(self):
        # T103e live shots-25208: the start frame already had the Spire selected (Interact up);
        # T103d tapped the tower instead, which deselected it -> 'no Interact' stop
        start = SPECTRE / 'shots-25208' / 'hu_world.png'
        dev, rc = self.run_hu([real(start), 'spire_sel2.png', 'spire_sel2.png', 'hm_confirmed2.png', 'hm_confirmed2.png', 'hm_confirmed2.png'],
                              {'hu_world': TOWER_BOXES, 'hu_read': DIALOG_BOXES})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [INTERACT, GO])           # no tower tap
        self.assertIn('Spire already selected', dev.out.getvalue())

    def test_tower_tap_that_deselects_uses_the_icon(self):
        # T103e live shots-25208/hu_tower: after the tower tap no radial, the upgrade icon instead
        after = SPECTRE / 'shots-25208' / 'hu_tower.png'
        dev, rc = self.run_hu([real(KITCHEN), real(after), 'spire_sel2.png', 'spire_sel2.png',
                               'hm_confirmed2.png', 'hm_confirmed2.png', 'hm_confirmed2.png'],
                              {'hu_world': KITCHEN_BOXES, 'hu_tower': [], 'hu_read': DIALOG_BOXES})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [TOWER_K, (915, 378), GO])
        self.assertIn('tower tap deselected the Spire', dev.out.getvalue())

    def test_interact_far_from_the_tower_is_not_the_spires(self):
        img = real(TOWER_TAP)
        self.assertEqual(hu.spire_interact(img, TOWER_BOXES, (915, 500)), INTERACT)
        self.assertIsNone(hu.spire_interact(img, TOWER_BOXES, None))      # no tower found
        self.assertIsNone(hu.spire_interact(img, TOWER_BOXES, (507, 528)))  # tower elsewhere
        self.assertIsNone(hu.spire_interact(img, TOWER_BOXES, (953, 900)))  # disc above the tower

    def test_go_kitchen_all_met_starts_the_kitchen_upgrade(self):
        # T103f: Spire 5/7 -> Go under 'Level 5 Kitchen' -> Kitchen selected (shots-80480) -> its
        # radial Level Up -> Kitchen dialog 7/7 -> Level Up. LIVE: the Kitchen dialog was never seen
        dev, rc = self.run_hu(['hm_requests.png', 'hm_up3.png', 'hm_up3.png', real(KITCHEN), 'hm_up3.png',
                               'hm_up3.png', 'hm_confirmed2.png'],
                              {'hu_world': WORLD_BOXES, 'hu_read': DIALOG_BOXES, 'hu_go': KITCHEN_BOXES,
                               'hu_bread': dialog('7/7')})
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, [DISC, GO, KITCHEN_LU, hu.LEVEL_UP_BTN])
        self.assertIn('kitchen upgrade started', dev.out.getvalue())

    def test_go_kitchen_missing_too_closes_without_a_second_go(self):
        # bounded: one Go level only - the Kitchen's own missing cards are not followed
        dev, rc = self.run_hu(['hm_requests.png', 'hm_up3.png', 'hm_up3.png', real(KITCHEN), 'hm_up3.png',
                               'hm_up3.png', 'hm_confirmed2.png'],
                              {'hu_world': WORLD_BOXES, 'hu_read': DIALOG_BOXES, 'hu_go': KITCHEN_BOXES,
                               'hu_bread': DIALOG_BOXES})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [DISC, GO, KITCHEN_LU, hu.BACK_PLATE])

    def test_go_off_the_world_stops_without_a_tap(self):
        dev, rc = self.run_hu(['hm_requests.png', 'hm_up3.png', 'hm_up3.png', 'UNKNOWN', 'UNKNOWN', 'UNKNOWN'],
                              {'hu_world': WORLD_BOXES, 'hu_read': DIALOG_BOXES})
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual(dev.taps, [DISC, GO])

    def test_dry_run_with_missing_cards_never_goes(self):
        dev, rc = self.run_hu(['hm_requests.png', 'hm_up3.png', 'hm_up3.png', 'hm_confirmed2.png'],
                              {'hu_world': WORLD_BOXES, 'hu_read': DIALOG_BOXES}, '--dry-run')
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [DISC, hu.BACK_PLATE])

    def test_live_dialog_without_title_is_accepted(self):
        # T103f live shots-49372/hu_read OCR: title still fading in -> one settled re-read, then on
        live = [(0, 0, 10, 10, 'diillt'), (477, 444, 302, 27, 'Upgrade Requirement (5/7)'),
                (482, 610, 98, 12, 'Level 5 Kitchen'), (600, 610, 60, 12, '3854/28K'),
                (1201, 984, 102, 29, 'Level Up'), (1440, 85, 22, 12, '0/2')]
        read = SPECTRE / 'shots-49372' / 'hu_read.png'
        dev, rc = self.run_hu(['hm_requests.png', 'hm_up3.png', real(read), real(read), 'hm_confirmed2.png', 'hm_confirmed2.png', 'hm_confirmed2.png'],
                              {'hu_world': WORLD_BOXES, 'hu_read': live, 'hu_read2': live})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertIn('hu_read2', dev.shots)
        self.assertIn('title unread', dev.out.getvalue())
        self.assertEqual(dev.taps, [DISC, (531, 640)])          # its Go, measured on the live frame

    def test_go_pill_and_kitchen_disc_on_live_frames(self):
        self.assertTrue(hu.go_pill(real(SPECTRE / 'shots-49372' / 'hu_read.png'), (531, 640)))
        self.assertTrue(hu.go_pill(hermes('hm_up3.png'), GO))
        self.assertFalse(hu.go_pill(hermes('hm_requests.png'), GO))
        k = real(KITCHEN)
        self.assertEqual(hu.building_level_up(k, KITCHEN_BOXES, 'kitchen'), KITCHEN_LU)
        self.assertIsNone(hu.building_level_up(k, KITCHEN_BOXES, 'forge'))     # label must match

    def test_kitchen_level_up_without_its_text(self):
        # T103g live: after Go the Kitchen radial was up but OCR missed / garbled 'Level Up'
        go = SPECTRE / 'shots-14680' / 'hu_go.png'
        kn2 = HERMES / 'kn2.png'
        go_boxes = [(1043, 323, 57, 13, 'Kitchen'), (938, 731, 43, 15, 'Cook')]          # live hu_go
        kn2_boxes = go_boxes + [(1028, 755, 54, 14, 'l_evel CP')]                        # kn2.png
        self.assertEqual(hu.building_level_up(real(go), go_boxes, 'kitchen'), (1054, 730))
        if kn2.exists():
            self.assertEqual(hu.building_level_up(hermes('kn2.png'), kn2_boxes, 'kitchen')[1] // 10, 73)
        self.assertIsNone(hu.building_level_up(real(go), go_boxes, 'forge'))            # label must match
        self.assertIsNone(hu.building_level_up(real(go), [(938, 731, 43, 15, 'Cook')], 'kitchen'))

    def test_live_go_kitchen_chain(self):
        # T103g: Spire 5/7 -> Go -> live hu_go (no Level Up text) -> Kitchen Level Up -> dialog 7/7
        go = SPECTRE / 'shots-14680' / 'hu_go.png'
        dev, rc = self.run_hu(['hm_requests.png', 'hm_up3.png', 'hm_up3.png', real(go), 'hm_up3.png',
                               'hm_up3.png', 'hm_confirmed2.png'],
                              {'hu_world': WORLD_BOXES, 'hu_read': DIALOG_BOXES,
                               'hu_go': [(1043, 323, 57, 13, 'Kitchen'), (938, 731, 43, 15, 'Cook')],
                               'hu_bread': dialog('7/7')})
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, [DISC, GO, (1054, 730), hu.LEVEL_UP_BTN])

    def test_dialog_still_fading_in_is_polled(self):
        # T103h live shots-68132: hu_dialog + hu_read blurred/faint, OCR [] -> poll, then read
        fade = SPECTRE / 'shots-68132' / 'hu_read.png'
        dev, rc = self.run_hu(['hm_requests.png', real(fade), real(fade), 'hm_up3.png', 'hm_confirmed2.png', 'hm_confirmed2.png', 'hm_confirmed2.png'],
                              {'hu_world': WORLD_BOXES, 'hu_read': [], 'hu_read_p1': DIALOG_BOXES})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.shots[:4], ['hu_world', 'hu_dialog', 'hu_read', 'hu_read_p1'])
        self.assertEqual(dev.taps, [DISC, GO])

    def test_dialog_never_settles_stops_without_a_tap(self):
        fade = SPECTRE / 'shots-68132' / 'hu_read.png'
        dev, rc = self.run_hu(['hm_requests.png'] + [real(fade)] * (1 + hu.DIALOG_POLLS),
                              {'hu_world': WORLD_BOXES})
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual(dev.taps, [DISC])                      # guard: no back plate, no tap
        self.assertEqual(len(dev.shots), 2 + hu.DIALOG_POLLS)   # bounded

    def test_go_radial_appearing_late_is_polled(self):
        # T103i: the first post-Go frame has no radial yet (loading), the second has it
        go = SPECTRE / 'shots-14680' / 'hu_go.png'
        dev, rc = self.run_hu(['hm_requests.png', 'hm_up3.png', 'hm_up3.png', 'UNKNOWN', real(go),
                               'hm_up3.png', 'hm_up3.png', 'hm_confirmed2.png'],
                              {'hu_world': WORLD_BOXES, 'hu_read': DIALOG_BOXES,
                               'hu_go_p1': [(1043, 323, 57, 13, 'Kitchen'), (938, 731, 43, 15, 'Cook')],
                               'hu_bread': dialog('7/7')})
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, [DISC, GO, (1054, 730), hu.LEVEL_UP_BTN])

    def test_go_without_radial_after_all_polls_is_nothing_to_do(self):
        dev, rc = self.run_hu(['hm_requests.png', 'hm_up3.png', 'hm_up3.png']
                              + ['hm_confirmed2.png'] * hu.DIALOG_POLLS,
                              {'hu_world': WORLD_BOXES, 'hu_read': DIALOG_BOXES})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [DISC, GO])
        self.assertEqual(dev.shots[-hu.DIALOG_POLLS:], ['hu_go', 'hu_go_p1', 'hu_go_p2'])

    def test_selected_spire_without_level_up_skips_the_camera(self):
        dev, rc = self.run_hu(['hm_requests.png'], {'hu_world': WORLD_BOXES[:2]})
        self.assertEqual(rc, 4)
        self.assertEqual(dev.taps, [])
        self.assertIn('Spire selected', dev.out.getvalue())

    def test_exit_game_dialog_on_the_start_frame_is_cancelled(self):
        # T103c live (shots-9308): X, re-shoot, continue - never the green check (exits the game)
        dev, rc = self.run_hu(['DIALOG', 'hm_requests.png', 'hm_up3.png', 'hm_up3.png', 'hm_confirmed2.png', 'hm_confirmed2.png', 'hm_confirmed2.png'],
                              {'hu_world_c': WORLD_BOXES, 'hu_read': DIALOG_BOXES})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [v.CONFIRM_CANCEL, DISC, GO])

    def test_exit_game_dialog_cancelled_once_only(self):
        dev, rc = self.run_hu(['DIALOG', 'DIALOG'], {})
        self.assertEqual(rc, 1)
        self.assertEqual(dev.taps, [v.CONFIRM_CANCEL])

    def test_unselected_spire_via_the_upgrade_icon(self):
        # T103b live: spire_sel (icon, no radial) -> tap -> spire_sel2 (dialog 5/7)
        dev, rc = self.run_hu(['spire_sel.png', 'spire_sel2.png', 'spire_sel2.png', 'hm_confirmed2.png', 'hm_confirmed2.png', 'hm_confirmed2.png'],
                              {'hu_world': WORLD_BOXES[1:2], 'hu_read': DIALOG_BOXES})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [ICON, GO])

    def test_icon_tap_retried_once_then_stops(self):
        dev, rc = self.run_hu(['spire_sel.png', 'spire_sel.png', 'spire_sel.png'], {'hu_world': []})
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual(len(dev.taps), 2)                # the tap + ONE T97b retry, both on the icon
        self.assertEqual([t[-2:] for t in dev.taps], [ICON, ICON])

    def test_icon_all_met_starts_the_upgrade(self):
        dev, rc = self.run_hu(['spire_sel.png', 'spire_sel2.png', 'spire_sel2.png', 'hm_confirmed2.png'],
                              {'hu_world': [], 'hu_read': dialog('7/7')})
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, [ICON, hu.LEVEL_UP_BTN])

    def test_dialog_already_open(self):
        # T103b live: shots-82892 started ON the Spire dialog -> read it, no world needed
        dev, rc = self.run_hu(['hm_up3.png', 'hm_confirmed2.png', 'hm_confirmed2.png', 'hm_confirmed2.png'], {'hu_world': DIALOG_BOXES})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [GO])
        self.assertIn('already open', dev.out.getvalue())

    def test_dialog_already_open_all_met(self):
        dev, rc = self.run_hu(['spire_sel2.png', 'hm_confirmed2.png'], {'hu_world': dialog('7/7')})
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, [hu.LEVEL_UP_BTN])

    def test_not_on_the_world_stops_without_back_key(self):
        for start in ('hm_up3.png', 'UNKNOWN'):           # dialog plate but no Spire OCR / anything else
            with self.subTest(start):
                dev, rc = self.run_hu([start], {})
                self.assertEqual(rc, 1)
                self.assertEqual(dev.taps, [])

    def test_unrecognised_dialog_closes_and_stops(self):
        # T103h: a dialog whose OCR never reads is polled DIALOG_POLLS times, then closed
        dev, rc = self.run_hu(['hm_requests.png', 'hm_up3.png'] + ['hm_up3.png'] * hu.DIALOG_POLLS
                              + ['hm_confirmed2.png'], {'hu_world': WORLD_BOXES, 'hu_read': []})
        self.assertEqual(rc, 1)
        self.assertEqual(dev.taps, [DISC, hu.BACK_PLATE])

    def test_tap_lock_held(self):
        import _bot_lock
        with mock.patch.object(_bot_lock, 'acquire', lambda *a, **k: False):
            dev, rc = self.run_hu([], {})
        self.assertEqual(rc, 7)


if __name__ == '__main__':
    unittest.main()
