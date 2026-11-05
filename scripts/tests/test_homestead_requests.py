"""T104 homestead requests + gazette claim - detectors on Hermes' live frames + FakeVision flows."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402
import afk_homestead as hs  # noqa: E402
import afk_homestead_requests as rq  # noqa: E402
import afk_homestead_upgrade as hu  # noqa: E402
from fake_vision import FakeDevice, frame  # noqa: E402
from test_homestead import SPECTRE, hermes  # noqa: E402
from test_homestead_upgrade import (DIALOG_BOXES, GO, INTERACT, KITCHEN_BOXES,  # noqa: E402
                                   TOWER_BOXES, TOWER_TAP)

_gs = importlib.util.spec_from_file_location('afk_daily_gift_t104', Path(rq.__file__).with_name('afk-daily-gift.py'))
gift = importlib.util.module_from_spec(_gs)
_gs.loader.exec_module(gift)

# real WinRT OCR line boxes (ocr.ps1 -Boxes), recorded 2026-11-05 on Hermes' frames
PANEL = [(1422, 107, 42, 11, 'Golden'), (805, 271, 310, 18, "I 'm curious about how these items"),  # rqp4
         (731, 349, 121, 15, 'Basic Rewards'), (712, 515, 80, 21, 'Requests'), (944, 672, 27, 15, '0/4'),
         (1009, 348, 109, 16, 'Star Rewards'), (922, 898, 165, 31, 'Quick Select'), (712, 928, 50, 13, 'Give Up')]
FULL = [(719, 358, 120, 23, 'Basic Rewards'), (711, 531, 81, 21, 'Requests'), (954, 672, 28, 16, '4/4'),  # qs1
        (995, 338, 110, 23, 'Star Rewards'), (984, 897, 96, 28, 'Deliver'), (742, 942, 49, 13, 'Give Up')]
DONE = [(687, 234, 535, 70, 'Request Completed'), (896, 352, 129, 16, 'Basic Rewards'),            # del1
        (901, 557, 118, 15, 'Star Rewards'), (871, 814, 156, 19, 'Reward Details'),
        (869, 1010, 182, 22, '? Tapto Close ?')]
EMPTY = [(731, 320, 121, 16, 'Basic Rewards'), (712, 487, 80, 21, 'Requests'), (825, 644, 27, 15, '0/2'),  # post3
         (1009, 320, 109, 16, 'Star Rewards'),
         (760, 763, 405, 21, 'No available items. Please produce some first.'),
         (922, 870, 165, 30, 'Quick Select'), (712, 899, 50, 14, 'Give Up')]
INSUF = [(734, 403, 450, 17, 'Insufficient resources. You can obtain them from :'),                 # rq3
         (744, 610, 163, 20, 'Level 3 Kitchen')]
PARTIAL = [(732, 349, 120, 15, 'Basic Rewards'), (712, 515, 80, 21, 'Requests'), (945, 672, 26, 15, '3/4'),  # rq4
           (922, 898, 165, 31, 'Quick Select'), (712, 928, 50, 13, 'Give Up')]
WORLD = [(1033, 326, 57, 13, 'Kitchen'), (938, 731, 43, 15, 'Cook'), (1028, 755, 46, 11, 'Level U'),     # fin2
         (25, 781, 63, 21, 'puild 4.'), (1767, 654, 57, 16, 'ewards')]
LIST = [(465, 18, 201, 54, 'Kitchen i'), (721, 609, 43, 14, 'Toast'), (714, 628, 56, 12, 'Stock : 3'),   # kz1
        (719, 655, 42, 14, 'Select'), (1380, 18, 97, 15, '3000/3000 +'), (1021, 407, 106, 14, 'What should 1'),
        (714, 870, 56, 13, 'Stock: O'), (1008, 870, 57, 13, 'Stock: 6')]
LIST2 = [(465, 18, 201, 54, 'Kitchen i'), (1380, 18, 97, 15, '2996/3000 +'),                              # rqp
         (1021, 407, 106, 14, 'What should 1'), (691, 608, 102, 15, 'Salted Raisin'),
         (714, 628, 56, 12, 'Stock: O'), (1163, 609, 43, 14, 'Toast'), (1156, 627, 56, 13, 'Stock: 4')]
DECK = [(712, 516, 122, 17, 'Process Deck'), (704, 616, 152, 22, 'Deck Setup (5/5)'),                     # cook4
        (1098, 518, 129, 22, '*Stock: 3 i'), (1094, 549, 146, 29, '*Request : 4 (Ci'), (935, 997, 51, 16, 'Make')]
COOKING = [(995, 503, 72, 22, 'Points:'), (892, 995, 85, 24, 'Cooking..')]                                # made1
DECK2 = [(699, 602, 153, 27, 'Deck Setup (5/5)'), (1098, 526, 128, 26, '*Stock: 4 i'),                    # made2
         (1095, 561, 111, 28, "'Reqgest: 4"), (908, 995, 51, 19, 'Make')]
GAZETTE = ['Monthl?', 'Daily Rewards', 'Classic Gazette', 'Claimy']                                       # claim1

DELIVER, QUICK, COOK = (1032, 911), (1004, 913), (959, 708)
FLOAT = (1075, 298)                       # T104b: floating Cook disc on shots-42848/rq_ck_k
TOAST_CARD = (740, 662)                   # OCR 'Select' (719,655,42,14) under the banner on kz1
# T104b: full card OCR of rqp (no banner; the two Dry Fruit cards are locked, grey Select)
RQP_ALL = [(1380, 18, 97, 15, '2996/3000 +'), (1021, 407, 106, 14, 'What should 1'),
           (714, 628, 56, 12, 'Stock: O'), (719, 655, 43, 14, 'Select'), (714, 861, 57, 12, 'Stock: 7'),
           (719, 888, 43, 14, 'Select'), (861, 627, 57, 13, 'Stock: O'), (866, 655, 43, 14, 'Select'),
           (857, 861, 65, 12, 'Stock: 23'), (866, 888, 43, 14, 'Select'), (1008, 628, 57, 12, 'Stock: 6'),
           (1013, 655, 43, 14, 'Select'), (1009, 861, 56, 12, 'Stock : 0'), (1014, 889, 42, 13, 'Select'),
           (1156, 627, 56, 13, 'Stock: 4'), (1161, 655, 43, 14, 'Select'), (1156, 861, 56, 12, 'Stock: 0'),
           (1161, 889, 42, 13, 'Select')]
KZ1_ALL = [(714, 628, 56, 12, 'Stock : 3'), (719, 655, 42, 14, 'Select'), (1021, 407, 106, 14, 'What should 1'),
           (714, 870, 56, 13, 'Stock: O'), (719, 898, 43, 14, 'Select'), (861, 870, 57, 13, 'Stock: O'),
           (866, 898, 43, 14, 'Select'), (1008, 870, 57, 13, 'Stock: 6'), (1014, 898, 42, 14, 'Select'),
           (1156, 870, 56, 13, 'stock: 7'), (1161, 898, 43, 14, 'Select')]
NOREQ = [(704, 616, 152, 22, 'Deck Setup (5/5)'), (1098, 518, 129, 22, '*Stock: 0 i')]
LIVE = SPECTRE / 'shots-42848'            # T104b: Hermes' live run, 'Kitchen not found'


def real_frame(path):
    if not path.exists():
        raise unittest.SkipTest(f'frame missing: {path}')
    from make_frame_manifest import load_rgb
    return load_rgb(path)


def live(name):
    return real_frame(LIVE / name)
NO_BACK_KEY = ('key', 4)
TOWER_W = (564, 502)                      # T104c: spire_tower on shots-42848/rq_ck_w


class Detectors(unittest.TestCase):
    def test_panel_buttons(self):
        self.assertEqual(rq.button(hermes('rqp4.png'), PANEL), ('quick', QUICK))
        self.assertEqual(rq.button(hermes('qs1.png'), FULL), ('deliver', DELIVER))
        self.assertEqual(rq.button(hermes('post3.png'), EMPTY), (None, None))   # grey plate

    def test_panel_vs_completed_toast(self):
        for boxes in (PANEL, FULL, EMPTY, PARTIAL):
            self.assertTrue(rq.is_panel(boxes))
        for boxes in (DONE, INSUF, WORLD, LIST):        # del1 shows Basic/Star Rewards too
            self.assertFalse(rq.is_panel(boxes))

    def test_selected_slot_ring(self):
        for name in ('rqp4.png', 'qs1.png', 'post3.png'):
            img = hermes(name)
            self.assertEqual([rq.slot_selected(img, k) for k in (0, 1)], [True, False], name)

    def test_kitchen_banner_and_screens(self):
        self.assertEqual(rq.requested_cards(hermes('kz1.png')), [741])
        self.assertEqual(rq.requested_cards(hermes('rqp.png')), [])
        self.assertTrue(rq.is_kitchen(LIST) and rq.is_kitchen(LIST2))
        self.assertFalse(rq.is_kitchen(EMPTY))           # 'Quick Select' + 'produce some first'
        self.assertTrue(rq.is_deck(DECK) and rq.is_deck(COOKING))
        self.assertEqual(rq.stamina(LIST), 3000)

    def test_deck_make_and_counts(self):
        self.assertTrue(rq.make_ready(hermes('cook4.png')))
        self.assertTrue(rq.make_ready(hermes('made2.png')))
        self.assertFalse(rq.make_ready(hermes('made1.png')))   # cooking
        self.assertEqual(rq.deck_counts(DECK), (3, 4))
        self.assertEqual(rq.deck_counts(DECK2), (4, 4))
        self.assertEqual(rq.deck_counts(COOKING), (None, None))

    def test_cook_radial(self):
        for name in ('fin2.png', 'claim3.png', 'rqp2.png'):
            self.assertEqual(rq.cook_disc(hermes(name), WORLD), COOK, name)
        self.assertIsNone(rq.cook_disc(hermes('fin2.png'), [b for b in WORLD if b[4] != 'Kitchen']))

    def test_hud_icon(self):
        for name in ('rq1.png', 'fin2.png', 'claim3.png'):
            self.assertGreater(v.lum(v.avg(hermes(name), rq.HUD_PROBE, r=3)), rq.HUD_LUM, name)
        self.assertLess(v.lum(v.avg(hermes('zone2.png'), rq.HUD_PROBE, r=3)), rq.HUD_LUM)

    def test_give_up_is_never_tapped(self):
        FakeDevice(self, [])
        for xy in ((712, 928), (737, 905), (712, 899)):
            with self.assertRaises(RuntimeError):
                rq._tap(xy, 1.0)


class KitchenT104b(unittest.TestCase):
    def test_cards_anchor_on_select(self):
        # locked Dry Fruit cards (grey Select) are skipped; Stock 0 (Salted Raisin, Grape Vinegar) first
        self.assertEqual(rq.kitchen_cards(hermes('rqp.png'), RQP_ALL),
                         [(740, 662, 0, False), (887, 662, 0, False), (1182, 662, 4, False),
                          (1034, 662, 6, False), (740, 895, 7, False), (887, 895, 23, False)])

    def test_banner_card_first(self):
        self.assertEqual(rq.kitchen_cards(hermes('kz1.png'), KZ1_ALL),
                         [(740, 662, 3, True), (740, 905, 0, False), (887, 905, 0, False),
                          (1035, 905, 6, False), (1182, 905, 7, False)])

    def test_live_kitchen_tap_only_focused_it(self):
        # shots-42848: brackets + two floating discs above the roof, no labels, camera unmoved
        img = live('rq_ck_k.png')
        self.assertEqual(v.classify(img), 'WORLD')
        self.assertIsNone(rq.cook_disc(img, []))
        self.assertEqual(rq.floating_cook(img), FLOAT)
        for other in (live('rq_ck_w.png'), live('rq_world.png'), hermes('fin2.png'), hermes('claim3.png'),
                      hermes('spire_sel.png'), hermes('tower_tap.png')):
            self.assertIsNone(rq.floating_cook(other))

    def test_cook_disc_with_the_label_far_right(self):
        img = real_frame(SPECTRE / 'shots-63328' / 'hu_go.png')   # 'Cook' read at x 912, label 164 px right
        self.assertEqual(rq.cook_disc(img, [(1070, 336, 55, 20, 'Kitchen'), (912, 727, 43, 20, 'Cook')]),
                         (957, 707))

    def test_floating_cook_disc_opens_the_kitchen(self):
        low = [b if '3000/3000' not in b[4] else (*b[:4], '800/3000 +') for b in LIST]
        dev = FakeDevice(self, [live('rq_ck_w.png'), live('rq_ck_k.png'), hermes('kz1.png'), hermes('fin2.png')],
                         boxes={'t_list': low})
        self.assertEqual(rq.cook_trip('t'), 0)
        self.assertEqual(dev.taps, [rq.KITCHEN_BASE, FLOAT, rq.KITCHEN_BACK])
        self.assertIn('floating Cook disc at (1075, 298)', dev.out.getvalue())

    def test_floating_tap_that_only_selects_takes_the_radial(self):
        low = [b if '3000/3000' not in b[4] else (*b[:4], '800/3000 +') for b in LIST]
        f = hermes('fin2.png')
        dev = FakeDevice(self, [live('rq_ck_w.png'), live('rq_ck_k.png'), f, f, f, hermes('kz1.png'), f],
                         boxes={'t_list': WORLD, 't_list_p1': WORLD, 't_list_p2': WORLD, 't_list_s': low})
        self.assertEqual(rq.cook_trip('t'), 0)
        self.assertEqual(dev.taps, [rq.KITCHEN_BASE, FLOAT, COOK, rq.KITCHEN_BACK])

    def test_foreign_dialog_after_the_floating_tap_is_closed(self):
        d = hermes('hm_up3.png')                  # a requirement dialog with its back plate
        dev = FakeDevice(self, [live('rq_ck_w.png'), live('rq_ck_k.png'), d, d, d, hermes('fin2.png')])
        self.assertEqual(rq.cook_trip('t'), 0)
        self.assertEqual(dev.taps, [rq.KITCHEN_BASE, FLOAT, hu.BACK_PLATE])

    def test_kitchen_not_found_after_the_polls(self):
        # T104c: anchor == KITCHEN_BASE (no drag) -> Spire-Go stage; the Kitchen card is met (its label
        # dropped from the hm_up3 boxes) -> no Go -> dialog closed via its back plate -> soft 0
        w, d = live('rq_ck_w.png'), hermes('spire_sel2.png')
        met = [b for b in DIALOG_BOXES if 'Kitchen' not in b[4]]
        dev = FakeDevice(self, [w, w, w, w, w, real_frame(TOWER_TAP), d, d, hermes('fin2.png')],
                         boxes={'hu_tower': TOWER_BOXES, 'hu_read': met})
        self.assertEqual(rq.cook_trip('t'), 0)
        self.assertEqual(dev.taps, [rq.KITCHEN_BASE, TOWER_W, INTERACT, hu.BACK_PLATE])
        self.assertNotIn('swipe', [x[0] for x in dev.taps if isinstance(x[0], str)])
        self.assertIn('no Kitchen Go', dev.out.getvalue())
        self.assertIn('Kitchen not found', dev.out.getvalue())

    def test_probes_only_without_a_banner_and_bounded(self):
        dev = FakeDevice(self, [hermes('fin2.png'), hermes('rqp.png'),
                                hermes('cook4.png'), hermes('rqp.png'), hermes('fin2.png')],
                         boxes={'t_w': WORLD, 't_list': RQP_ALL, 't_deck0': NOREQ, 't_list0': RQP_ALL})
        with mock.patch.object(rq, 'MAX_PROBES', 1):
            self.assertEqual(rq.cook_trip('t'), 0)
        self.assertEqual(dev.taps, [COOK, (740, 662), rq.KITCHEN_BACK, rq.KITCHEN_BACK])

    def test_probe_deck_without_request_is_left_and_the_next_probe_cooked(self):
        dev = FakeDevice(self, [hermes('fin2.png'), hermes('rqp.png'),
                                hermes('cook4.png'), hermes('rqp.png'),                  # no Request -> back
                                hermes('cook4.png'), hermes('made2.png'), hermes('rqp.png'),
                                hermes('fin2.png')],
                         boxes={'t_w': WORLD, 't_list': RQP_ALL, 't_deck0': NOREQ, 't_list0': RQP_ALL,
                                't_deck1': DECK, 't_deck1_m0_0': DECK2, 't_list1': RQP_ALL})
        with mock.patch.object(rq, 'MAX_DECKS', 2):
            self.assertEqual(rq.cook_trip('t'), 1)
        self.assertEqual(dev.taps, [COOK, (740, 662), rq.KITCHEN_BACK, (887, 662), rq.MAKE,
                                    rq.KITCHEN_BACK, rq.KITCHEN_BACK])
        self.assertIn('not requested, not cooking', dev.out.getvalue())


class KitchenT104c(unittest.TestCase):
    def test_anchor_on_the_live_frames(self):
        self.assertEqual(rq.kitchen_at(live('rq_ck_w.png')), rq.KITCHEN_BASE)     # defines the offset
        for name in ('st0.png', 'st1.png'):                                         # Kitchen at the top edge
            at = rq.kitchen_at(hermes(name))
            self.assertLess(abs(at[0] - 814) + abs(at[1] - 78), 8, name)
            self.assertFalse(hu._in(at, rq.KITCHEN_WIN), name)
        for name in ('fin2.png', 'claim3.png', 'rq1.png'):                          # Kitchen selected
            self.assertTrue(hu._in(rq.kitchen_at(hermes(name)), rq.KITCHEN_WIN), name)
        cam1 = real_frame(SPECTRE / 'shots-59732' / 'hu_cam1.png')                  # anchor ON the Interact disc
        self.assertFalse(hu._in(rq.kitchen_at(cam1), rq.KITCHEN_WIN))

    def test_st1_npc_radial_is_no_kitchen(self):
        for name in ('st0.png', 'st1.png'):
            img = hermes(name)
            self.assertIsNone(rq.cook_disc(img, [(927, 731, 66, 15, 'Interact')]), name)
            self.assertIsNone(rq.floating_cook(img), name)
            self.assertIsNone(rq.floating_cook(img, rq.kitchen_at(img)), name)

    def test_floating_window_follows_the_tap(self):
        img = live('rq_ck_k.png')
        self.assertEqual(rq.floating_cook(img, rq.KITCHEN_BASE), FLOAT)
        self.assertEqual(rq.floating_cook(img, (1042, 442)), (1074, 297))
        self.assertIsNone(rq.floating_cook(img, (1040, 700)))

    def test_st0_drag_then_tap(self):
        low = [b if '3000/3000' not in b[4] else (*b[:4], '800/3000 +') for b in LIST]
        dev = FakeDevice(self, [hermes('st0.png'), live('rq_ck_w.png'), live('rq_ck_k.png'),
                                hermes('kz1.png'), hermes('fin2.png')], boxes={'t_list': low})
        self.assertEqual(rq.cook_trip('t'), 0)
        self.assertEqual(dev.taps, [('swipe', 1300, 350, 1526, 679, hu.CAMERA_MS, 1.5),
                                    rq.KITCHEN_BASE, FLOAT, rq.KITCHEN_BACK])
        self.assertEqual(dev.shots[:3], ['t_w', 't_cam1', 't_k1'])

    def test_cook_disc_rescue_after_the_drag(self):
        low = [b if '3000/3000' not in b[4] else (*b[:4], '800/3000 +') for b in LIST]
        dev = FakeDevice(self, [hermes('st1.png'), hermes('fin2.png'), hermes('kz1.png'), hermes('fin2.png')],
                         boxes={'t_cam1': WORLD, 't_list': low})
        self.assertEqual(rq.cook_trip('t'), 0)
        self.assertEqual(dev.taps, [('swipe', 1300, 350, 1526, 684, hu.CAMERA_MS, 1.5), COOK, rq.KITCHEN_BACK])

    def test_two_drags_at_most(self):
        s = hermes('st0.png')
        dev = FakeDevice(self, [s, s, s, s, real_frame(TOWER_TAP), 'UNKNOWN', 'UNKNOWN'],
                         boxes={'hu_tower': []})
        self.assertIsNone(rq.cook_trip('t'))      # stage 2: no Interact after the tower tap, off the world
        self.assertEqual([x[0] for x in dev.taps], ['swipe', 'swipe', 338])

    def test_spire_go_reaches_the_kitchen(self):
        low = [b if '3000/3000' not in b[4] else (*b[:4], '800/3000 +') for b in LIST]
        w, d = live('rq_ck_w.png'), hermes('spire_sel2.png')
        dev = FakeDevice(self, [w, w, w, w, w, real_frame(TOWER_TAP), d, d,
                                real_frame(SPECTRE / 'shots-80480' / 'hu_world.png'),
                                hermes('kz1.png'), hermes('fin2.png')],
                         boxes={'hu_tower': TOWER_BOXES, 'hu_read': DIALOG_BOXES, 't_go': KITCHEN_BOXES,
                                't_list': low})
        self.assertEqual(rq.cook_trip('t'), 0)
        self.assertEqual(dev.taps, [rq.KITCHEN_BASE, TOWER_W, INTERACT, GO, COOK, rq.KITCHEN_BACK])
        self.assertNotIn(hu.LEVEL_UP_BTN, dev.taps)

    def test_spire_stage_stuck_off_the_world(self):
        w = live('rq_ck_w.png')
        dev = FakeDevice(self, [w, w, w, w, w, 'UNKNOWN', 'UNKNOWN'], boxes={'hu_tower': TOWER_BOXES})
        self.assertIsNone(rq.cook_trip('t'))
        self.assertEqual(dev.taps, [rq.KITCHEN_BASE, TOWER_W])

    def test_drag_off_the_world_stops_without_a_tap(self):
        dev = FakeDevice(self, [hermes('st0.png'), 'UNKNOWN'])
        self.assertIsNone(rq.cook_trip('t'))
        self.assertEqual([x[0] for x in dev.taps], ['swipe'])
        self.assertIn('the camera drag left the world view', dev.out.getvalue())

    def test_kitchen_tap_opening_a_dialog_closes_it_then_spire_stage(self):
        w, d = live('rq_ck_w.png'), hermes('hm_up3.png')   # a requirement dialog with its back plate
        dev = FakeDevice(self, [w, d, w, w, 'UNKNOWN', 'UNKNOWN'],
                         boxes={'hu_tower': TOWER_BOXES})
        self.assertIsNone(rq.cook_trip('t'))           # closed (soft) -> stage 2 -> off the world there
        self.assertEqual(dev.taps, [rq.KITCHEN_BASE, hu.BACK_PLATE, TOWER_W])
        self.assertIn('the Kitchen tap opened another dialog', dev.out.getvalue())

    # --- T104c fix round: review findings ---
    def test_drag_starts_clear_of_the_fountain(self):
        # spire_sel camera: (1300,350) is the fountain's stone rim -> the (1450,400) grass start
        dev = FakeDevice(self, [hermes('spire_sel.png'), 'UNKNOWN'])
        self.assertIsNone(rq.cook_trip('t'))
        self.assertEqual(dev.taps, [('swipe', 1450, 400, 1097, 598, hu.CAMERA_MS, 1.5)])

    def test_no_clear_drag_start_goes_to_the_spire_stage(self):
        # tower_tap camera: bubble corner / fountain under both starts -> no drag at all
        dev = FakeDevice(self, [real_frame(TOWER_TAP), 'UNKNOWN', 'UNKNOWN'])
        self.assertIsNone(rq.cook_trip('t'))
        self.assertEqual(dev.taps, [])
        self.assertIn('no clear drag start', dev.out.getvalue())

    def test_drag_end_clipped_off_the_right_hud(self):
        img = hermes('st0.png')
        with mock.patch.object(rq, 'kitchen_at', side_effect=[(600, 80), None]):
            dev = FakeDevice(self, [img, img, 'UNKNOWN', 'UNKNOWN'])
            self.assertIsNone(rq.cook_trip('t'))
        self.assertEqual(dev.taps[0], ('swipe', 1300, 350, 1600, 680, hu.CAMERA_MS, 1.5))

    def test_spire_go_never_taps_the_npc_interact(self):
        # st1: supplier NPC selected; its Interact is pixel-identical to the Spire's -> after the tower
        # tap only a tower-anchored Interact counts -> no Interact tap, soft 0
        s, npc = hermes('st1.png'), [(927, 731, 66, 15, 'Interact')]
        dev = FakeDevice(self, [s, s, s], boxes={'hu_world': npc, 'hu_tower': npc})
        self.assertEqual(rq.spire_go('t'), 0)
        self.assertEqual(dev.taps, [(338, 168)])
        self.assertIn('no Interact/Level Up radial after the tower tap', dev.out.getvalue())

    def test_kitchen_tap_off_the_world_is_stuck(self):
        dev = FakeDevice(self, [live('rq_ck_w.png'), 'UNKNOWN'])
        self.assertIsNone(rq.cook_trip('t'))
        self.assertEqual(dev.taps, [rq.KITCHEN_BASE])

    def test_no_tower_after_the_drag_goes_to_the_spire_stage(self):
        dev = FakeDevice(self, [hermes('st0.png'), hermes('quest1.png'), 'UNKNOWN', 'UNKNOWN'])
        self.assertIsNone(rq.cook_trip('t'))
        self.assertEqual([x[0] for x in dev.taps], ['swipe'])
        self.assertIn('no Spire tower on the frame', dev.out.getvalue())

    def test_spire_stage_nothing_to_do_is_soft(self):
        w = live('rq_ck_w.png')
        with mock.patch.object(hu, 'spire_dialog', return_value=4):
            dev = FakeDevice(self, [w, w, w, w])
            self.assertEqual(rq.cook_trip('t'), 0)
        self.assertEqual(dev.taps, [rq.KITCHEN_BASE])
        self.assertIn('Kitchen not found', dev.out.getvalue())

    def _go(self, after):
        w, d = live('rq_ck_w.png'), hermes('spire_sel2.png')
        dev = FakeDevice(self, [w, w, w, w, w, real_frame(TOWER_TAP), d, d] + after,
                         boxes={'hu_tower': TOWER_BOXES, 'hu_read': DIALOG_BOXES})
        return dev, rq.cook_trip('t')

    def test_go_without_a_cook_disc_is_soft(self):
        w = live('rq_ck_w.png')
        dev, rc = self._go([w, w, w])
        self.assertEqual(rc, 0)
        self.assertEqual(dev.taps, [rq.KITCHEN_BASE, TOWER_W, INTERACT, GO])
        self.assertIn('no Kitchen Cook radial after Go', dev.out.getvalue())

    def test_go_to_an_unknown_screen_is_stuck(self):
        dev, rc = self._go(['UNKNOWN'] * 3)
        self.assertIsNone(rc)
        self.assertEqual(dev.taps, [rq.KITCHEN_BASE, TOWER_W, INTERACT, GO])
        self.assertIn('Go did not lead to the world view', dev.out.getvalue())


class Gazette(unittest.TestCase):
    def test_claim_plate_on_the_live_frames(self):
        for name in ('backzone.png', 'cook1.png', 'claim1.png', 'claim2.png'):
            x, y = v.gazette_claim(hermes(name))
            self.assertLess(abs(x - 959) + abs(y - 934), 6, name)
            self.assertTrue(895 <= y <= 975, name)   # (965,888) missed the plate live

    def test_no_plate_elsewhere(self):
        self.assertIsNone(v.gazette_claim(frame('WORLD')))
        self.assertIsNone(v.gazette_claim(hermes('fin2.png')))

    def test_ocr_tell(self):
        self.assertTrue(v.is_gazette(GAZETTE))
        self.assertFalse(v.is_gazette(['Requests', 'Basic Rewards']))

    def test_startup_popup_taps_the_plate(self):
        dev = FakeDevice(self, [gazette_frame(), 'WORLD'], ocr={'p': GAZETTE})
        self.assertTrue(v.resolve_startup_popup('p'))
        self.assertEqual(len(dev.taps), 1)
        self.assertLess(abs(dev.taps[0][0] - 959) + abs(dev.taps[0][1] - 935), 6)

    def test_daily_gift_entry_opens_the_gazette(self):
        g = gazette_frame()
        dev = FakeDevice(self, ['WORLD', 'GIFT_ENTRY', g, g, g,     # init, cam_0, panel wait x3
                                g, 'WORLD'],                        # resolver shot + after
                         ocr={'dg_panel_2': GAZETTE, 'dg_gazette': GAZETTE})
        with mock.patch.object(sys, 'argv', ['afk-daily-gift.py']):
            self.assertEqual(gift.main(), 0)
        self.assertEqual(dev.taps[0], gift.LOGIN_REWARDS)
        self.assertEqual(len(dev.taps), 2)
        self.assertIn('Esperia gazette: daily reward claimed', dev.out.getvalue())


def gazette_frame():
    img = frame('POPUP')
    img.paste((240, 160, 60), (815, 895, 1104, 975))
    return img


class Flow(unittest.TestCase):
    def run_rq(self, frames, boxes, *argv):
        dev = FakeDevice(self, [hermes(f) if isinstance(f, str) and f.endswith('.png') else f
                                for f in frames], boxes=boxes)
        rc = rq.main(list(argv))
        self.assertNotIn(NO_BACK_KEY, dev.taps)       # keyevent BACK opens the exit-game dialog here
        return dev, rc

    def test_full_request_is_delivered(self):
        dev, rc = self.run_rq(['fin2.png', 'qs1.png', 'qs1.png',                 # world, open, panel
                               'qs1.png', 'del1.png', 'post3.png',               # Deliver, toast, closed
                               'post3.png',                                      # next NPC: grey
                               'post3.png', 'fin2.png'],                         # slot 2 not taken, leave
                              {'rq_open_r': FULL, 'rq0_0': FULL, 'rq0_0_done': DONE,
                               'rq0_0_done_c0': EMPTY, 'rq1_0': EMPTY, 'rq_slot1': EMPTY}, '--no-cook')
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, [rq.REQUESTS_BTN, DELIVER, hs.TOAST_CLOSE, rq.SLOTS[1], rq.PANEL_BACK])
        self.assertIn('slot 2 not selected', dev.out.getvalue())

    def test_short_request_cooks_then_delivers(self):
        dev, rc = self.run_rq(['fin2.png', 'rqp4.png', 'rqp4.png',               # world, open, panel
                               'rqp4.png', 'rq3.png', 'rq4.png',                 # Quick Select, popup, X
                               'fin2.png',                                       # panel left
                               'fin2.png', 'kz1.png',                            # Cook radial, Kitchen
                               'cook4.png', 'made1.png', 'made2.png',            # deck, cooking, stock 4
                               'rqp.png', 'fin2.png',                            # list (no banner), world
                               'rqp4.png', 'rqp4.png',                           # panel again
                               'rqp4.png', 'qs1.png', 'qs1.png',                 # Quick Select -> 4/4
                               'del1.png', 'post3.png', 'post3.png',             # deliver, next NPC grey
                               'post3.png', 'fin2.png'],                         # slot 2, leave
                              {'rq_open_r': PANEL, 'rq0_0': PANEL, 'rq0_0_qs': INSUF, 'rq0_0_qs_x': PARTIAL,
                               'rq_ck_w': WORLD, 'rq_ck_list': LIST, 'rq_ck_deck0': DECK,
                               'rq_ck_deck0_m0_0': COOKING, 'rq_ck_deck0_m0_1': DECK2, 'rq_ck_list0': LIST2,
                               'rq_open2_r': PANEL, 'rq1_0': PANEL, 'rq1_0_qs': FULL, 'rq1_1': FULL,
                               'rq1_1_done': DONE, 'rq1_1_done_c0': EMPTY, 'rq2_0': EMPTY, 'rq_slot1': EMPTY})
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, [rq.REQUESTS_BTN, QUICK, rq.INSUF_X, rq.PANEL_BACK,
                                    COOK, TOAST_CARD, rq.MAKE, rq.KITCHEN_BACK, rq.KITCHEN_BACK,
                                    rq.REQUESTS_BTN, QUICK, DELIVER, hs.TOAST_CLOSE, rq.SLOTS[1], rq.PANEL_BACK])
        self.assertIn('requests delivered 1, cooked 1', dev.out.getvalue())

    def test_low_stamina_does_not_cook(self):
        low = [b if '3000/3000' not in b[4] else (*b[:4], '800/3000 +') for b in LIST]
        dev, rc = self.run_rq(['fin2.png', 'post3.png', 'post3.png',              # world, open, panel
                               'post3.png', 'fin2.png',                          # grey -> leave
                               'fin2.png', 'kz1.png', 'fin2.png',                # Kitchen, back
                               'post3.png', 'post3.png',                         # panel again
                               'post3.png', 'post3.png', 'fin2.png'],            # grey, slot 2, leave
                              {'rq_open_r': EMPTY, 'rq0_0': EMPTY, 'rq_ck_w': WORLD, 'rq_ck_list': low,
                               'rq_open2_r': EMPTY, 'rq1_0': EMPTY, 'rq_slot1': EMPTY})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertNotIn(rq.MAKE, dev.taps)
        self.assertNotIn(TOAST_CARD, dev.taps)
        self.assertIn('stamina 800 < 1000 - no cooking', dev.out.getvalue())

    def test_dead_close_tap_is_retried_once(self):
        dev, rc = self.run_rq(['fin2.png', 'qs1.png', 'qs1.png', 'qs1.png',
                               'del1.png', 'del1.png', 'del1.png', 'del1.png',   # toast stays (3 polls)
                               'post3.png',                                      # retry closed it
                               'post3.png', 'post3.png', 'fin2.png'],
                              {'rq_open_r': FULL, 'rq0_0': FULL, 'rq0_0_done': DONE,
                               'rq0_0_done_c0': DONE, 'rq0_0_done_c0_p1': DONE, 'rq0_0_done_c0_p2': DONE,
                               'rq0_0_done_c1': EMPTY, 'rq1_0': EMPTY, 'rq_slot1': EMPTY}, '--no-cook')
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps[2:4], [hs.TOAST_CLOSE, ('touchscreen', *hs.TOAST_CLOSE)])

    def test_no_requests_icon_is_nothing_to_do(self):
        dev, rc = self.run_rq(['WORLD'], {})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [])

    def test_off_the_world_stops_without_a_tap(self):
        dev, rc = self.run_rq(['UNKNOWN'], {})
        self.assertEqual(rc, 1)
        self.assertEqual(dev.taps, [])

    def test_unknown_screen_after_deliver_stops(self):
        dev, rc = self.run_rq(['fin2.png', 'qs1.png', 'qs1.png', 'qs1.png',
                               'UNKNOWN', 'UNKNOWN', 'UNKNOWN'],
                              {'rq_open_r': FULL, 'rq0_0': FULL}, '--no-cook')
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual(dev.taps, [rq.REQUESTS_BTN, DELIVER])


if __name__ == '__main__':
    unittest.main()
