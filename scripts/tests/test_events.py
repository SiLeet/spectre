"""T109 events phase, stage 1 (read-only) - detectors on real frames + synthetic FakeVision flows."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from PIL import Image, ImageDraw  # noqa: E402
import afk_claim_vision as v  # noqa: E402
import _bot_lock  # noqa: E402
import afk_events as ev  # noqa: E402
from fake_vision import FakeDevice, frame  # noqa: E402
from test_homestead import SPECTRE, hermes, load_rgb  # noqa: E402

# real WinRT OCR of the column crops (ocr.ps1 -Boxes), recorded 2026-11-05; x crop-relative, y ABSOLUTE
EV0_COLS = [  # Hermes scratch/ev0.png (layout A)
    [(23, 467, 131, 24, "Journey's Gift"), (49, 494, 85, 15, 'X No Limit'), (11, 637, 157, 17, 'District Preview'),
     (6, 805, 166, 18, 'Stormbound Seas'), (25, 831, 133, 15, 'X Ends in 13d 18h')],
    [(31, 468, 116, 18, 'Dreamdelve'), (49, 494, 85, 15, 'X No Limit'), (4, 636, 169, 23, 'Crescent@ff��ring'),
     (25, 663, 133, 14, 'X Ends in 13d 1811'), (2, 805, 173, 18, 'Autumn Whirlwind'),
     (28, 831, 127, 15, 'X Ends in 6d 18h')],
    [(14, 468, 153, 23, 'Golden Supplier'), (28, 494, 127, 15, 'X Ends in 4d 18h'), (20, 636, 137, 23, 'Baden Rate Up'),
     (25, 663, 133, 14, 'X Ends in 13d 18h'), (19, 805, 140, 18, 'ArcaneAteIier'), (24, 831, 105, 15, 'X Ends in 49d')]]
B_COLS = [  # .spectre/trash/shots-46412/tab_events.png (layout B)
    [(25, 399, 147, 27, "Journey's Gift"), (54, 429, 95, 17, 'X No Limit'), (13, 588, 173, 19, 'District Preview'),
     (7, 774, 184, 20, 'Stormbound Seas'), (27, 803, 148, 17, 'X Ends in Md 14h')],
    [(35, 400, 129, 20, 'Dreamdelve'), (74, 431, 76, 14, 'No Limit'), (5, 587, 188, 26, 'Crescent@ffering'),
     (28, 616, 148, 17, 'X Ends in 14d 14h'), (4, 774, 191, 20, 'Autumn Whirlwind'), (52, 804, 121, 16, 'Ends in 7d 1411')],
    [(16, 400, 170, 26, 'Golden Supplier'), (32, 429, 140, 17, 'X Ends in 5d 14h'), (23, 587, 152, 26, 'Baden Rate Up'),
     (47, 617, 129, 16, 'Ends in Md 14h'), (22, 774, 155, 20, 'Arcane A telier'), (47, 804, 130, 16, 'Ends in 50d 14h')]]
EV0_BADGED = {(1, 1), (1, 2), (2, 2), (3, 2), (4, 2), (4, 3)}   # JG, DD, Crescent, AW, r4c2, r4c3 (11-05)
BACK_KEY = ('key', 4)


def spectre(rel: str):
    path = SPECTRE / rel
    if not path.exists():
        raise unittest.SkipTest(f'frame missing: {path}')
    return load_rgb(path)


def fake_ocr(cols, lay):
    """_ocr_crop stand-in: the recorded column boxes, back in crop coordinates."""
    top = ev.COL_Y[lay][0]
    by_left = {l: c for (l, _), c in zip(ev.COLS[lay], cols)}
    return lambda img, box: [(x, y - top, w, h, t) for x, y, w, h, t in by_left[box[0]]]


def paint(base, patches, half=10):
    img = Image.new('RGB', (1920, 1080), base)
    d = ImageDraw.Draw(img)
    for (x, y), rgb in patches.items():
        d.rectangle((x - half, y - half, x + half, y + half), fill=rgb)
    return img


ORANGE = (241, 135, 36)
# Routines menu, layout A (bar (890,934) bright) with the Events-tab badge lit
MENU_A = {(480, 270): (240, 235, 225), (890, 934): (240, 240, 240), (500, 920): (173, 85, 46),
          (1160, 940): (60, 60, 60), ev.EV_TAB_BADGE_A: ORANGE}
LIST_A = {ev.EV_BODY: (245, 240, 230), ev.EV_NAV: (95, 95, 95), (1310, 906): ORANGE, (1150, 935): (194, 99, 36),
          (990, 938): (244, 244, 244)}
LIST_B = {ev.EV_BODY: (245, 240, 230), ev.EV_NAV: (95, 95, 95), (1455, 885): ORANGE, (1270, 935): (239, 147, 68),
          (1100, 922): (247, 247, 247)}


def menu_a(badge=True):
    p = dict(MENU_A)
    if not badge:
        del p[ev.EV_TAB_BADGE_A]
    return paint((40, 40, 40), p)


def list_a(badges=((0, 1),)):
    img = paint((40, 40, 40), LIST_A)
    d = ImageDraw.Draw(img)
    for row, col in badges:                      # badge disc poking out above the card corner
        right, top = ev.RIGHTS['A'][col], ev.TOPS['A'][row]
        d.rectangle((right - 12, top - 9, right + 3, top - 1), fill=ORANGE)
    return img


class Detectors(unittest.TestCase):
    def test_events_list_real_frames(self):
        self.assertEqual(ev.is_events_list(hermes('ev0.png')), 'A')
        for rel in ('shots-readonly-122730.png', 'trash/shots-4392/readonly-season-20261103-043509.png'):
            if (SPECTRE / rel).exists():
                self.assertEqual(ev.is_events_list(spectre(rel)), 'A', rel)
        self.assertEqual(ev.is_events_list(spectre('trash/shots-46412/tab_events.png')), 'B')

    def test_not_events_list_real_frames(self):
        for name in ('lt0.png', 'arena1.png'):             # Routines menu (A)
            img = hermes(name)
            self.assertIsNone(ev.is_events_list(img), name)
            self.assertTrue(v.is_battle_modes(img), name)
        for rel in ('trash/shots-46412/tab_back.png', 'trash/shots-46412/tab_guild.png', 'shots-41820/dr_f2_w16.png'):
            if (SPECTRE / rel).exists():
                self.assertIsNone(ev.is_events_list(spectre(rel)), rel)

    def test_events_list_synthetic(self):
        self.assertEqual(ev.is_events_list(list_a()), 'A')
        self.assertEqual(ev.is_events_list(paint((40, 40, 40), LIST_B)), 'B')
        self.assertFalse(v.is_battle_modes(list_a()))
        self.assertIsNone(ev.is_events_list(frame('BATTLE_MODES')))
        self.assertIsNone(ev.is_events_list(menu_a()))
        ended = paint((40, 40, 40), {**LIST_A, ev.EV_NAV: (236, 236, 236)})   # BATTLE ENDED: bright nav
        self.assertIsNone(ev.is_events_list(ended))
        ended = paint((40, 40, 40), {**LIST_A, (990, 938): (222, 72, 73)})   # red plate, no Guild plate
        self.assertIsNone(ev.is_events_list(ended))

    def test_tab_badge_and_layout(self):
        for name in ('lt0.png', 'arena1.png'):              # LIVE 218 / 243
            img = hermes(name)
            self.assertEqual(ev.menu_layout(img), 'A')
            self.assertGreater(ev.tab_badge(img), ev.TAB_BADGE_PX, name)
        self.assertGreater(ev.tab_badge(menu_a()), ev.TAB_BADGE_PX)
        self.assertEqual(ev.tab_badge(menu_a(badge=False)), 0)
        self.assertEqual(ev.menu_layout(menu_a()), 'A')
        self.assertEqual(ev.menu_layout(frame('BATTLE_MODES')), 'B')

    def test_badge_strip(self):
        img = paint((40, 40, 40), {})
        right, top = ev.RIGHTS['A'][0], ev.TOPS['A'][0]
        ImageDraw.Draw(img).rectangle((right - 9, top - 10, right, top - 1), fill=ORANGE)   # 10x10 = 100 px
        self.assertEqual(ev.card_badge(img, 'A', 0, 0), 100)
        img = paint((40, 40, 40), {})
        ImageDraw.Draw(img).rectangle((right - 6, top - 1, right, top - 1), fill=ORANGE)    # 7 px (Baden art)
        self.assertEqual(ev.card_badge(img, 'A', 0, 0), 7)
        self.assertLess(7, ev.BADGE_PX)
        self.assertLess(ev.BADGE_PX, 96)

    def test_card_badges_real_frames(self):
        img = hermes('ev0.png')
        got = {(r + 1, c + 1) for r in range(4) for c in range(3) if ev.card_badge(img, 'A', r, c) >= ev.BADGE_PX}
        self.assertEqual(got, EV0_BADGED)
        img = spectre('trash/shots-46412/tab_events.png')              # B: negatives only (JG orange art 0)
        self.assertFalse(any(ev.card_badge(img, 'B', r, c) for r in range(4) for c in range(3)))

    def test_titles_and_timers(self):
        self.assertEqual(ev.title_name('Crescent@ff��ring'), 'Crescent Offering')
        self.assertEqual(ev.title_name('ArcaneAteIier'), 'Arcane Atelier')
        self.assertEqual(ev.title_name('Mystery Fair'), 'Mystery Fair')
        self.assertEqual(ev.timer_text('X Ends in 13d 1811'), 'Ends in 13d 1811')
        self.assertEqual(ev.timer_text('X No Limit'), 'No Limit')

    def test_read_cards_real_ocr(self):
        for lay, cols, img in (('A', EV0_COLS, lambda: hermes('ev0.png')),
                               ('B', B_COLS, lambda: spectre('trash/shots-46412/tab_events.png'))):
            with self.subTest(lay=lay), mock.patch.object(ev, '_ocr_crop', fake_ocr(cols, lay)):
                cards = {(r, c): (t, tm, px) for r, c, t, tm, px in ev.read_cards(img(), lay)}
                self.assertEqual(len(cards), 12)
                self.assertEqual(cards[(1, 1)][:2], ("Journey's Gift", 'No Limit'))
                self.assertEqual(cards[(1, 2)][:2], ('Dreamdelve', 'No Limit'))
                self.assertEqual(cards[(2, 1)][:2], ('District Preview', '-'))       # no timer (page dots)
                self.assertEqual(cards[(2, 2)][0], 'Crescent Offering')
                self.assertEqual(cards[(2, 3)][0], 'Baden Rate Up')
                self.assertEqual(cards[(3, 1)][0], 'Stormbound Seas')                # not merged with AW
                self.assertEqual(cards[(3, 2)][0], 'Autumn Whirlwind')
                self.assertEqual(cards[(3, 3)][0], 'Arcane Atelier')
                self.assertIsNone(cards[(4, 2)][0])                                   # row 4 title hidden
        with mock.patch.object(ev, '_ocr_crop', fake_ocr(EV0_COLS, 'A')):
            cards = ev.read_cards(hermes('ev0.png'), 'A')
        self.assertEqual(cards[4][2:4], ('Crescent Offering', 'Ends in 13d 1811'))   # raw, never gated

    def test_row_assignment_tolerance(self):
        cols = [[(0, 467 + 12, 9, 9, 'Dreamdelve'), (0, 636 + 13, 9, 9, 'Stray')], [], []]
        with mock.patch.object(ev, '_ocr_crop', fake_ocr(cols, 'A')):
            cards = ev.read_cards(paint((40, 40, 40), {}), 'A')
        self.assertEqual(cards[0][2], 'Dreamdelve')
        self.assertEqual(cards[3][2], '?')                                            # 13 px off: dropped

    def test_stage2_guard(self):
        for t in ('Baden Rate Up', 'Golden Supplier', 'Crescent Offering'):
            self.assertIn('never open', ev.stage2_note(t))
        self.assertIn('afk-daily-gift', ev.stage2_note("Journey's Gift"))
        self.assertEqual(ev.MAX_OPEN, 2)
        for t in ('Mystery Fair', '?', 'Dreamdelve'):                 # default closed: unknown = not measured
            self.assertIn('not measured', ev.stage2_note(t))


WORLD = 'WORLD'


class Flow(unittest.TestCase):
    def run_ev(self, frames, cols=None):
        dev = FakeDevice(self, frames)
        p = mock.patch.object(ev, '_ocr_crop', fake_ocr(cols, 'A') if cols else lambda img, box: [])
        p.start()
        self.addCleanup(p.stop)
        rc = ev.main([])
        out = dev.out.getvalue()
        self.allowed(dev)
        return dev, rc, out

    def allowed(self, dev):
        """Only these taps exist: no event card, claim, price or BATTLE_MODES_BTN-on-the-list tap."""
        for t in dev.taps:
            self.assertIn(t, (v.GROUND, v.BATTLE_MODES_BTN, ev.EVENTS_TAB, ev.EVENTS_TAB_B, ev.ROUTINES_TAB,
                              BACK_KEY), dev.taps)
        l, r = ev.COLS['A'][0][0], ev.COLS['A'][2][1]
        self.assertFalse(any(isinstance(t[0], int) and l <= t[0] <= r and t[1] < 900 for t in dev.taps), dev.taps)

    def test_full_read_only_tour(self):
        dev, rc, out = self.run_ev([WORLD, menu_a(), list_a(), menu_a(), WORLD], EV0_COLS)
        self.assertEqual(rc, 0, out)
        self.assertEqual(dev.taps, [v.GROUND, ev.EVENTS_TAB, ev.ROUTINES_TAB, BACK_KEY])
        self.assertIn('events: r1c2 Dreamdelve | No Limit | badge', out)
        self.assertIn("events: r1c1 Journey's Gift | No Limit | no badge", out)
        self.assertIn('0 opened', out)

    def test_badge_on_a_paid_title_is_logged_never_opened(self):
        dev, rc, out = self.run_ev([WORLD, menu_a(), list_a(badges=((1, 2), (0, 2))), menu_a(), WORLD], EV0_COLS)
        self.assertEqual(rc, 0, out)
        self.assertIn('Baden Rate Up | Ends in 13d 18h | badge | stage 2: never open', out)
        self.assertIn('Golden Supplier | Ends in 4d 18h | badge | stage 2: never open', out)
        self.assertEqual(dev.taps, [v.GROUND, ev.EVENTS_TAB, ev.ROUTINES_TAB, BACK_KEY])

    def test_no_card_badge_is_nothing_to_do(self):
        dev, rc, out = self.run_ev([WORLD, menu_a(), list_a(badges=()), menu_a(), WORLD], EV0_COLS)
        self.assertEqual(rc, 4, out)
        self.assertEqual(dev.taps, [v.GROUND, ev.EVENTS_TAB, ev.ROUTINES_TAB, BACK_KEY])

    def test_tab_badge_off_skips_the_events_tab(self):
        dev, rc, out = self.run_ev([WORLD, menu_a(badge=False), WORLD])
        self.assertEqual(rc, 4, out)
        self.assertEqual(dev.taps, [v.GROUND, BACK_KEY])
        self.assertNotIn(ev.EVENTS_TAB, dev.taps)

    def test_layout_b_menu_proceeds(self):
        dev, rc, out = self.run_ev([WORLD, 'BATTLE_MODES', list_a(), 'BATTLE_MODES', WORLD], EV0_COLS)
        self.assertEqual(rc, 0, out)
        self.assertIn('layout B: Events-tab badge unmeasured', out)
        self.assertEqual(dev.taps[1], ev.EVENTS_TAB_B)                     # centre of B's plate, not A's point

    def test_layout_b_list_through_main(self):
        dev = FakeDevice(self, [WORLD, 'BATTLE_MODES', paint((40, 40, 40), LIST_B), 'BATTLE_MODES', WORLD])
        with mock.patch.object(ev, '_ocr_crop', fake_ocr(B_COLS, 'B')):
            rc = ev.main([])
        out = dev.out.getvalue()
        self.allowed(dev)
        self.assertEqual(rc, 4, out)
        self.assertIn('Dreamdelve | No Limit | no badge', out)
        self.assertIn('events list (layout B): 0 badged', out)
        self.assertEqual(dev.taps, [v.GROUND, ev.EVENTS_TAB_B, ev.ROUTINES_TAB, BACK_KEY])

    def test_lock_held(self):
        dev = FakeDevice(self, [])
        with mock.patch.object(_bot_lock, 'acquire', lambda *a, **k: False):
            self.assertEqual(ev.main([]), 7)
        self.assertEqual(dev.taps, [])

    def test_badge_off_world_not_reached(self):
        dev, rc, out = self.run_ev([WORLD, menu_a(badge=False)] + ['UNKNOWN'] * 7)
        self.assertEqual(rc, 1, out)
        self.assertNotIn(ev.EVENTS_TAB, dev.taps)

    def test_leave_world_not_reached(self):
        dev, rc, out = self.run_ev([WORLD, menu_a(), list_a(), menu_a()] + ['UNKNOWN'] * 7, EV0_COLS)
        self.assertEqual(rc, 1, out)
        self.assertEqual(dev.taps[:4], [v.GROUND, ev.EVENTS_TAB, ev.ROUTINES_TAB, BACK_KEY])
        self.assertIn('world not reached after leaving Battle Modes', out)

    def test_list_never_verified_stops(self):
        dev, rc, out = self.run_ev([WORLD, menu_a()] + ['UNKNOWN'] * 3)
        self.assertEqual(rc, 1, out)
        self.assertEqual(dev.taps, [v.GROUND, ev.EVENTS_TAB])

    def test_events_tap_dead_leaves_the_menu(self):
        dev, rc, out = self.run_ev([WORLD, menu_a(), menu_a(), menu_a(), menu_a()])
        self.assertEqual(rc, 1, out)
        self.assertEqual(dev.taps, [v.GROUND, ev.EVENTS_TAB, BACK_KEY])

    def test_routines_tab_dead_stops_on_the_list(self):
        dev, rc, out = self.run_ev([WORLD, menu_a(), list_a()] + [list_a()] * 3, EV0_COLS)
        self.assertEqual(rc, 1, out)
        self.assertEqual(dev.taps, [v.GROUND, ev.EVENTS_TAB, ev.ROUTINES_TAB])   # no BACK on the list
        self.assertIn('still the events list', out)

    def test_menu_reopened_on_events_reads_directly(self):
        dev, rc, out = self.run_ev([WORLD, list_a(), menu_a(), WORLD], EV0_COLS)
        self.assertEqual(rc, 0, out)
        self.assertEqual(dev.taps, [v.GROUND, ev.ROUTINES_TAB, BACK_KEY])     # no BATTLE_MODES_BTN on the list
        self.assertIn('tab persistence', out)

    def test_menu_never_opens(self):
        dev, rc, out = self.run_ev([WORLD] + ['UNKNOWN'] * 5)
        self.assertEqual(rc, 1, out)
        self.assertEqual(dev.taps, [v.GROUND] + [v.BATTLE_MODES_BTN] * ev.MENU_STEPS)

    def test_world_not_reached_is_stuck(self):
        dev, rc, out = self.run_ev(['UNKNOWN'] * 7)
        self.assertEqual(rc, 1, out)
        self.assertNotIn(ev.EVENTS_TAB, dev.taps)

    def test_pc_in_use(self):
        dev = FakeDevice(self, [])
        with mock.patch.object(v, 'idle_seconds', lambda: 5.0):
            self.assertEqual(ev.main(['--min-idle', '180']), 5)
        self.assertEqual(dev.taps, [])


if __name__ == '__main__':
    unittest.main()


class StageTwoNotes(unittest.TestCase):
    def test_hermes_event_facts(self):
        # Hermes live 2026-11-05: District Preview = preview only; Golden Supplier = Requests NPC
        self.assertEqual(ev.stage2_note('District Preview'), 'preview only, nothing to claim')
        self.assertIn('Requests NPC', ev.stage2_note('Golden Supplier'))
        self.assertIn('never open', ev.stage2_note('Baden Rate Up'))
        self.assertEqual(ev.stage2_note("Journey's Gift"), 'claimed by afk-daily-gift')
        self.assertIn('District Preview', ev.SKIP_OPEN)
