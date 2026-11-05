"""T106/T106b guild daily (store log-only, challenge claims) - detectors on live frames + FakeVision flows."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402
import afk_guild as gd  # noqa: E402
from fake_vision import FakeDevice, frame  # noqa: E402
from test_homestead import SPECTRE, hermes, load_rgb  # noqa: E402

# real WinRT OCR line boxes (ocr.ps1 -Boxes), recorded 2026-11-05 on Hermes' frames (garbled names removed)
HALL = [(92, 59, 45, 17, 'Lvi. 5'), (148, 63, 71, 14, 'Niflheim'), (245, 263, 139, 27, 'Display Wall'),  # guild5
        (726, 214, 112, 21, 'Guild Chesi'), (649, 441, 104, 16, 'Splendid Puppy'),
        (1058, 238, 117, 21, 'Battle Drills'), (1068, 1055, 41, 14, 'Guild'), (1210, 355, 95, 25, 'OExploryxg.'),
        (1726, 352, 150, 23, 'ZGuild Duel'), (1781, 384, 62, 12, 'Preparati on'), (1369, 418, 56, 21, 'u Busy'),
        (807, 1049, 49, 11, 'Mvs cal'), (1323, 947, 33, 10, 'Store'), (1404, 946, 61, 15, 'Challenge'),
        (970, 1050, 66, 13, 'Resonating'), (877, 1056, 80, 12, 'Battle Modes'), (991, 1064, 24, 11, 'Hall')]
HALL2 = [(92, 59, 45, 17, 'Lvi. 5'), (245, 263, 139, 27, 'Display Wall'), (726, 214, 112, 21, 'Guild Chesi'),  # gback
         (1058, 237, 117, 22, 'battle Drills'), (1260, 322, 143, 26, '?lashfronts'),
         (1726, 352, 150, 23, 'ZGuild Duel'), (1781, 384, 62, 12, 'Preparati on'), (1323, 947, 33, 10, 'Store'),
         (1068, 1055, 41, 14, 'Guild'), (1404, 946, 61, 15, 'Challenge'), (877, 1056, 80, 12, 'Battle Modes')]
CHEST = [(440, 63, 197, 18, 'X Distribution in : 3d 22h'), (438, 348, 105, 43, '2916'),  # gchal
         (596, 371, 199, 26, 'Equal Distribution O'), (467, 404, 46, 13, 'Chests'),
         (596, 401, 193, 17, 'Activeness Required: 200'), (540, 466, 60, 26, 'besay'), (540, 710, 62, 13, 'Membro'),
         (1316, 465, 86, 14, 'Distributed'), (1336, 497, 65, 18, '38+35'), (1357, 811, 23, 17, '38'),
         (860, 1058, 49, 12, 'Chests'), (1055, 1057, 152, 17, 'Contribution Ranking')]
CHEST_SKEW = [(510, 16, 177, 32, 'Distribution in : 3d 22h'), (457, 300, 107, 46, '2916'),  # gchest (skewed)
              (614, 339, 166, 33, 'Equal Distribution'), (549, 423, 59, 30, 'besay'), (536, 528, 81, 27, 'Anocki'),
              (806, 1045, 49, 16, 'Chests'), (1321, 504, 85, 21, 'Distributed'), (1310, 535, 92, 26, "Z' 38+35"),
              (1327, 641, 63, 23, '38+15')]
STORE = [(1227, 13, 22, 16, '44'), (1387, 13, 56, 16, '28 704'),  # gstore2 (complete)
         (945, 96, 244, 18, 'Worry not, my friend I Shall handle'), (1029, 118, 75, 18, 'everything.'),
         (431, 191, 89, 12, 'Recrui tment'), (457, 206, 37, 13, 'Store'), (451, 295, 49, 17, 'Guild'),
         (452, 317, 47, 15, 'Store'), (449, 404, 52, 15, 'Arena'), (454, 423, 43, 14, 'Store'),
         (446, 512, 59, 14, 'Dream'), (454, 530, 43, 15, 'Store'), (431, 619, 88, 19, 'Friendship'),
         (454, 638, 43, 15, 'Store'), (665, 196, 201, 41, 'uild Store'), (842, 340, 27, 17, 'All'),
         (985, 341, 50, 21, 'Daily'), (1125, 340, 78, 22, 'Monthly')]
WORLD_BAR = [(1033, 326, 57, 13, 'Kitchen'), (938, 731, 43, 15, 'Cook'), (1028, 755, 54, 14, 'Level Up'),  # guild2
             (875, 1057, 84, 13, 'Battle Modes'), (968, 1050, 69, 15, 'Resonating'), (990, 1065, 25, 12, 'Hall'),
             (1068, 1056, 42, 14, 'Guild')]
UN1 = [(245, 263, 139, 27, 'Display Wall'), (726, 214, 112, 21, 'Guild Chesi'),  # un1 (02:30:15, subset)
       (1058, 237, 117, 22, 'battle Drills'), (1253, 322, 150, 22, '? ?lashfronts'),
       (1726, 352, 150, 23, 'ZGuild Duel'), (1781, 384, 62, 12, 'Preparati on'), (1324, 946, 32, 11, 'Store'), (1404, 946, 61, 14, 'Challenge')]
# T106b (WinRT ocr.ps1 -Boxes on the real frames, recorded 2026-11-05)
BOARD = [(444, 19, 300, 44, 'Gild Challenge@'), (563, 339, 176, 20, 'Reach 2000 points in'),  # gfr2
         (562, 365, 56, 15, 'Arena.'), (565, 406, 230, 17, 'Members CompletedP 15/15'),
         (564, 599, 220, 19, 'Upgrade the Radiant Spire'), (565, 665, 230, 18, 'Members Completed P 0/15'),
         (563, 859, 193, 15, 'Reach Resonance Level'), (565, 925, 231, 18, 'Members CompletedP 0/10'),
         (844, 339, 183, 19, 'Reach AFK stage 500.'), (846, 406, 173, 17, 'Members Completed P'),
         (844, 599, 168, 15, 'Clear Floor 45 of All'), (846, 665, 173, 18, 'Members Completed P'),
         (1125, 339, 220, 20, 'Upgrade the Radiant Spire'), (1127, 406, 172, 17, 'Members Comp leted P'),
         (1125, 599, 168, 15, 'Clear Floor 80 of All'), (1127, 665, 172, 18, 'Members Completed P'),
         (845, 859, 219, 19, 'Upgrade the Radiant Spire'), (842, 924, 175, 14, 'Achieved on 2026-11-3'),
         (1123, 924, 187, 14, 'Achieved on 2026-10-30')]
BOARD_AFTER = [(444, 19, 300, 44, 'Gild Challenge@'), (563, 339, 183, 19, 'Reach AFK stage 500.'),  # gcC
               (565, 406, 173, 17, 'Members CompletedP'), (563, 599, 168, 15, 'Clear Floor 45 of All'),
               (565, 665, 173, 18, 'Members Completed P'), (844, 339, 220, 20, 'Upgrade the Radiant Spire'),
               (846, 406, 173, 17, 'Members CompletedP'), (846, 665, 173, 18, 'Members Completed P'),
               (1127, 406, 230, 17, 'Members Comp leted P 0/15'), (1127, 665, 231, 18, 'Members Completed P 0/10'),
               (562, 924, 174, 14, 'Achieved on 2026-11-3')]
POPUP = [(444, 19, 234, 43, 'Gild Challen'), (563, 339, 118, 15, 'Reach AFK St'),  # gcE (subset)
         (565, 406, 115, 17, 'Members Com I'), (701, 34, 146, 22, 'Guild Medal'), (709, 90, 120, 15, 'Owned: 30104'),
         (702, 289, 352, 17, 'Used to redeem rewards in Guild Store.'), (702, 328, 116, 16, 'Main Source'),
         (715, 382, 51, 17, 'Guild'), (565, 665, 173, 18, 'Members Completed P'),
         (846, 665, 173, 18, 'Members Completed P'), (1127, 406, 230, 17, 'Members Comp leted P 0/15')]
ITEMS = [(1227, 13, 22, 16, '44'), (1387, 13, 56, 16, '28 704'),  # gd_items (shots-41892, complete)
         (945, 96, 244, 19, 'Worry not, my friend I Shall handle'), (1029, 118, 75, 17, 'everything.'),
         (431, 191, 89, 12, 'Recrui tment'), (457, 207, 37, 12, 'Store'), (451, 295, 49, 17, 'Guild'),
         (452, 317, 47, 15, 'Store'), (449, 404, 52, 15, 'Arena'), (454, 423, 43, 14, 'Store'),
         (446, 512, 59, 14, 'Dream'), (454, 530, 43, 15, 'Store'), (431, 619, 88, 19, 'Friendship'),
         (454, 638, 43, 15, 'Store'), (665, 196, 201, 41, 'uild Store'), (983, 340, 55, 23, 'Daily'),
         (806, 387, 50, 21, 'Daily'), (807, 410, 113, 13, 'Refreshes in 18'), (801, 439, 167, 98, 'ei3'),
         (838, 555, 112, 14, '210 ? 180'), (1125, 340, 78, 22, 'Monthly')]
CREAM, ORANGE = (235, 231, 219), (255, 120, 40)
NO_BACK_KEY = ('key', 4)


def spectre(rel: str):
    path = SPECTRE / rel
    if not path.exists():
        raise unittest.SkipTest(f'frame missing: {path}')
    return load_rgb(path)


def gd41(name: str):
    return spectre(f'shots-41892/{name}.png')


def board(k: int):
    """gcC with every badge slot cream, then the first k slots (row-major) painted lit."""
    img = hermes('gcC.png').copy()
    for i in range(9):
        x, y = gd.slot_xy(i % 3, i // 3)
        img.paste(ORANGE if i < k else CREAM, (x - 14, y - 14, x + 15, y + 15))
    return img


class Detectors(unittest.TestCase):
    def test_guild_icon_layout_a(self):
        for name in ('guild1.png', 'guild2.png', 'guild4.png'):
            n = gd.guild_icon_px(hermes(name))
            self.assertTrue(gd.GUILD_ICON_PX[0] <= n <= gd.GUILD_ICON_PX[1], (name, n))
        for rel in ('shots-82200/rw_0.png', 'shots-73800/norm_0.png'):
            if (SPECTRE / rel).exists():
                n = gd.guild_icon_px(spectre(rel))
                self.assertTrue(gd.GUILD_ICON_PX[0] <= n <= gd.GUILD_ICON_PX[1], (rel, n))

    def test_guild_icon_off_spot(self):
        self.assertEqual(gd.guild_icon_px(frame('WORLD')), 0)
        n = gd.guild_icon_px(spectre('trash/shots-42388/rw_0.png'))    # layout B helmet
        self.assertGreater(n, gd.GUILD_ICON_PX[1])

    def test_screen_words(self):
        self.assertTrue(gd.is_hall(HALL) and gd.is_hall(HALL2) and gd.is_hall(UN1))
        for boxes in (CHEST, CHEST_SKEW, STORE, WORLD_BAR, BOARD, POPUP, ITEMS):
            self.assertFalse(gd.is_hall(boxes))
        self.assertTrue(gd.is_chest(CHEST) and gd.is_chest(CHEST_SKEW))
        for boxes in (HALL, STORE, WORLD_BAR, BOARD):
            self.assertFalse(gd.is_chest(boxes))
        self.assertTrue(gd.is_store(STORE) and gd.is_store(ITEMS))
        for boxes in (HALL, CHEST, WORLD_BAR, BOARD, POPUP):
            self.assertFalse(gd.is_store(boxes))

    def test_board_words(self):
        for boxes in (BOARD, BOARD_AFTER, POPUP):
            self.assertTrue(gd.is_board(boxes))
        for boxes in (HALL, HALL2, UN1, CHEST, STORE, ITEMS, WORLD_BAR):   # hall 'Challenge' label is y946
            self.assertFalse(gd.is_board(boxes))
        self.assertTrue(gd.is_medal_popup(POPUP))
        self.assertFalse(gd.is_medal_popup(BOARD) or gd.is_medal_popup(ITEMS))   # 'Guild' alone is not it
        self.assertEqual(gd.medal_owned(POPUP), 30104)
        self.assertIsNone(gd.medal_owned(BOARD))
        self.assertEqual(gd.slot_name(BOARD, 0, 0), 'Reach 2000 points in')
        self.assertEqual(gd.slot_name(BOARD, 1, 0), 'Reach AFK stage 500.')
        self.assertEqual(gd.slot_name(BOARD_AFTER, 0, 0), 'Reach AFK stage 500.')
        self.assertEqual(gd.slot_name([], 2, 2), '?')

    def test_board_badges(self):
        for name in ('gfr2.png', 'gc1.png', 'gc2.png', 'gcA.png', 'gcB.png'):   # gc1 = pulse phase
            self.assertEqual(gd.board_badges(hermes(name)), [(0, 0), (1, 0)], name)
        for name in ('gcC.png', 'gcD.png', 'gcE.png'):             # Arena claimed; gcE under the tooltip
            self.assertEqual(gd.board_badges(hermes(name)), [(0, 0)], name)
        for img in (hermes('gcF.png'), hermes('gf_now.png'), gd41('gd_hall'), gd41('gd_items'), gd41('gd_chest')):
            self.assertEqual(gd.board_badges(img), [])
        self.assertEqual(gd.board_badges(board(0)), [])
        self.assertEqual(gd.board_badges(board(9)), [(c, r) for r in range(3) for c in range(3)])

    def test_brief_red_rule_counter_example(self):
        """The red-haired avatar on an achieved card passes the brief's rule but lies in no slot."""
        img = hermes('gfr2.png')
        red = gd.hs._pixels(img, (982, 964, 1000, 977), lambda r, g, b: r > 200 and g < 90 and b < 90)
        self.assertGreater(len(red), 50)
        for r in range(3):
            for c in range(3):
                x, y = gd.slot_xy(c, r)
                self.assertFalse(x - 14 <= 990 <= x + 14 and y - 14 <= 970 <= y + 14)

    def test_challenge_plate_and_close_spot(self):
        for img in (gd41('gd_hall'), gd41('gd_hall3'), hermes('gcF.png'), hermes('gcG.png')):
            self.assertTrue(gd.challenge_badge(img))
            plate = gd.hs._pixels(img, (1391, 895, 1479, 968), lambda r, g, b: v.lum((r, g, b)) > 235)
            self.assertGreater(len(plate), 2000)                             # cream Challenge plate
            mx, my = gd.hs._median(plate)
            self.assertLess(abs(mx - gd.CHALLENGE_BTN[0]) + abs(my - gd.CHALLENGE_BTN[1]), 8)
        self.assertTrue(gd.hu._line(HALL, 'challenge', gd.CHALLENGE_LABEL_WIN))
        self.assertIsNone(gd.hu._line(HALL, 'store', gd.CHALLENGE_LABEL_WIN))
        for name in ('gfr2.png', 'gcC.png', 'gcE.png'):
            self.assertTrue(gd._cream(hermes(name)), name)
            back = gd.hs._pixels(hermes(name), (431, 969, 526, 1050), lambda r, g, b: v.lum((r, g, b)) > 235)
            self.assertGreater(len(back), 5000)                              # cream back plate (arrow glyph
            self.assertLess(v.lum(v.avg(hermes(name), gd.BOARD_BACK, r=3)), 200)  # dark at BOARD_BACK)
        self.assertFalse(gd._cream(gd41('gd_hall')))
        for img in (hermes('gfr2.png'), hermes('gcE.png'), gd41('gd_hall')):
            self.assertFalse(v.is_confirm_dialog(img))

    def test_chest_countdown(self):
        self.assertEqual(gd.chest_hours(CHEST), 94)
        self.assertEqual(gd.chest_hours(CHEST_SKEW), 94)
        self.assertEqual(gd.chest_hours([(0, 0, 9, 9, 'Distribution in : 22h')]), 22)
        self.assertEqual(gd.chest_hours([(0, 0, 9, 9, 'Distribution in : 0d 0h')]), 0)
        self.assertIsNone(gd.chest_hours(HALL))

    def test_duel_phase(self):
        self.assertEqual(gd.duel_phase(HALL), 'Preparati on')
        self.assertEqual(gd.duel_phase(UN1), 'Preparati on')
        self.assertIsNone(gd.duel_phase(STORE))

    def test_challenge_badge(self):
        for name in ('guild5.png', 'gback.png', 'un1.png'):     # 226 / 226 / 203 px (badge OFF unmeasured)
            self.assertTrue(gd.challenge_badge(hermes(name)), name)
        for name in ('gchest.png', 'gstore2.png'):
            self.assertFalse(gd.challenge_badge(hermes(name)), name)

    def test_store_tab_and_pill(self):
        self.assertTrue(gd.guild_tab_selected(hermes('gstore2.png')))
        self.assertTrue(gd.guild_tab_selected(gd41('gd_items')))
        for name in ('gchest.png', 'guild5.png', 'un1.png', 'un2.png', 'guild2.png'):
            self.assertFalse(gd.guild_tab_selected(hermes(name)), name)
        img = hermes('gstore2.png').copy()          # another tab selected: Arena bg lit, Guild bg dark
        img.paste((243, 243, 243), (400, 360, 450, 420))
        self.assertFalse(gd.guild_tab_selected(img))
        img.paste((91, 91, 91), (400, 240, 450, 330))
        self.assertFalse(gd.guild_tab_selected(img))
        self.assertTrue(gd.pill_selected(gd41('gd_items')))          # Daily pill green
        for img in (hermes('gstore2.png'), gd41('gd_store')):        # 'All' selected / mid-fade
            self.assertFalse(gd.pill_selected(img))

    def test_store_cards(self):
        items = gd41('gd_items')
        self.assertTrue(gd.has_items(items))
        for img in (hermes('gstore2.png'), gd41('gd_store'), gd41('gd_hall')):
            self.assertFalse(gd.has_items(img))
        self.assertEqual([gd.card_currency(items, i) for i in range(3)], ['diamond', 'diamond', None])
        self.assertEqual(gd.token_balance(ITEMS), 28704)
        with mock.patch.object(gd.hs, 'ocr_scaled', lambda name, box, tag: {'price0': ['210'],
                                                                           'price1': ["'180"]}[tag]):
            self.assertEqual(gd.store_items(items, 'gd_items'),
                             [('card 0 (?)', 210, 'diamond'), ('card 1 (?)', 180, 'diamond')])
        # no names -> never preferred, so neither card is ever a would-buy (the 180 one never is)
        rows = gd.plan_buys([('card 0 (?)', 210, 'diamond'), ('card 1 (?)', 180, 'diamond')], 28704, diamonds=44420)
        self.assertEqual([r[2] for r in rows], ['not preferred', 'not preferred'])
        for text, want in (('28 704', 28704), ('1.2K', 1200), ('210', 210), ('44 420', 44420),
                           ('Daily', None), ('38+35', None), ('210 ? 180', None)):
            self.assertEqual(gd._amount(text), want, text)

    def test_price_crop_ocr(self):
        """Optional (WinRT OCR via PowerShell): the x3 crop reads each card's price."""
        items = gd41('gd_items')
        with tempfile.TemporaryDirectory() as tmp:
            items.save(Path(tmp) / 'gd_items.png')
            with mock.patch.object(v, 'TMP', Path(tmp)):
                got = gd.store_items(items, 'gd_items')
                dia = gd.diamond_balance('gd_items')
        if all(p is None for _, p, _ in got):
            self.skipTest('WinRT OCR unavailable')
        self.assertEqual([p for _, p, _ in got], [210, 180])
        self.assertEqual(dia, 44420)

    def test_plan_buys(self):
        P = gd.plan_buys
        self.assertEqual(P([('Invite Letter', 500, 'guild')], 28704), [('Invite Letter', 500, 'would buy')])
        self.assertEqual(P([('DR Essence', 210, 'diamond')], 28704)[0][2], 'diamond price')
        # user rule 2026-11-05 + guide consensus: only the daily 210-diamond Invite Letter
        self.assertEqual(P([('Invite Letter', 210, 'diamond')], 28704, diamonds=5000)[0][2],
                         'would buy (guide consensus, diamonds)')
        self.assertEqual(P([('Invite Letter', 300, 'diamond')], 28704, diamonds=5000)[0][2], 'diamond price')
        self.assertEqual(P([('Invite Letter', 180, 'diamond')], 28704, diamonds=5000)[0][2], 'diamond price')
        self.assertEqual(P([('Epic Invite Letter', 210, 'diamond')], 28704, diamonds=5000)[0][2], 'diamond price')
        self.assertEqual(P([('Invite Letter', 210, 'diamond')], 28704)[0][2], 'diamond balance unread')
        self.assertEqual(P([('Invite Letter', 210, 'diamond')], 28704, diamonds=100)[0][2], 'short of diamonds')
        two = P([('Invite Letter', 210, 'diamond'), ('Invite Letter', 210, 'diamond')], 28704, diamonds=5000)
        self.assertEqual([r[2] for r in two], ['would buy (guide consensus, diamonds)', 'buy limit'])
        self.assertEqual(P([('Invite Letter', 500, None)], 28704)[0][2], 'currency unknown')
        self.assertEqual(P([('Invite Letter', 6000, 'guild')], 28704)[0][2], 'over budget')
        self.assertEqual(P([('Invite Letter', 500, 'guild')], 100)[0][2], 'short of tokens')
        self.assertEqual(P([('Invite Letter', 500, 'guild')], None)[0][2], 'balance unread')
        self.assertEqual(P([('Hero Shard', 500, 'guild')], 28704)[0][2], 'not preferred')
        three = P([('Invite Letter', 100, 'guild'), ('DR Essence', 100, 'gold'), ('Invite Letter', 200, 'guild')],
                  28704)
        self.assertEqual([r[2] for r in three], ['would buy', 'buy limit', 'buy limit'])   # max 1 buy per run
        one = P([('Invite Letter', 210, 'diamond'), ('DR Essence', 100, 'guild')], 28704, diamonds=5000)
        self.assertEqual([r[2] for r in one], ['would buy (guide consensus, diamonds)', 'buy limit'])
        # rows keep the card order (store() zips them with the cards): a diamond card never gets the
        # verdict of a later guild-priced card
        mixed = P([('card 0 (?)', 210, 'diamond'), ('Invite Letter', 100, 'guild')], 28704, diamonds=5000)
        self.assertEqual(mixed, [('card 0 (?)', 210, 'not preferred'), ('Invite Letter', 100, 'would buy')])

    def test_confirm_check_is_never_tapped(self):
        FakeDevice(self, [])
        for xy in ((1142, 710), (1142, 729)):
            with self.assertRaises(RuntimeError):
                gd._tap(xy, 1.0)


HALL_IN = ['guild2.png', 'guild5.png', 'guild5.png']           # world, open, hall
CHEST_SEG = ['gchal.png', 'gback.png']                         # chest, hall again
STORE_SEG = ['gstore2.png'] + ['gstore2.png'] * 3              # store hub, empty items x3 polls
BACK_HALL = ['gback.png']                                      # gd_hall3 after the store back
OUT = ['guild2.png']                                           # world after the hall back
SLOT00 = gd.slot_xy(0, 0)
BASE_BOXES = {'gd_hall': HALL, 'gd_chest': CHEST, 'gd_hall2': HALL2, 'gd_store': STORE,
              'gd_items': STORE, 'gd_items_p1': STORE, 'gd_items_p2': STORE, 'gd_hall3': HALL2,
              'gd_hall4': HALL2, 'gd_board': BOARD, 'gd_hall5': HALL2}
PRE_TAPS = [gd.GUILD_BTN, gd.GUILD_CHEST, gd.HALL_BACK, gd.STORE_BTN, gd.DAILY_PILL, gd.STORE_BACK]


def claim_tour():
    """gfr2 (2 lit) -> tap 00 -> gcE tooltip -> close -> gcC (1 lit) -> tap 00 -> board cleared -> back."""
    chal = ['gback.png', 'gfr2.png', 'gcE.png', 'gcC.png', board(0), 'gback.png']
    boxes = dict(BASE_BOXES, gd_claim1=POPUP, gd_claim1_c=BOARD_AFTER, gd_claim2=BOARD_AFTER)
    return HALL_IN + CHEST_SEG + STORE_SEG + BACK_HALL + chal + OUT, boxes


TOUR_TAPS = PRE_TAPS + [gd.CHALLENGE_BTN, SLOT00, gd.CLOSE_TAP, SLOT00, gd.BOARD_BACK, gd.HALL_BACK]


def with_board(*chal):
    """Tour up to the board, then `chal` (frames from gd_board on), then the hall back -> world."""
    return HALL_IN + CHEST_SEG + STORE_SEG + BACK_HALL + ['gback.png'] + list(chal)


class Flow(unittest.TestCase):
    def run_gd(self, frames, boxes, ocr=None):
        dev = FakeDevice(self, [hermes(f) if isinstance(f, str) and f.endswith('.png') else f
                                for f in frames], boxes=boxes, ocr=ocr)
        rc = gd.main([])
        self.assertNotIn(NO_BACK_KEY, dev.taps)       # keyevent BACK opens the exit-game dialog
        l, t, r, b = gd.ITEM_AREA                      # never a tap on a store card
        store = dev.taps[dev.taps.index(gd.STORE_BTN) + 1:dev.taps.index(gd.STORE_BACK)] \
            if gd.STORE_BACK in dev.taps else []
        self.assertFalse(any(l <= x <= r and t <= y <= b for x, y in store), store)
        return dev, rc

    def test_full_tour_with_claims(self):
        frames, boxes = claim_tour()
        dev, rc = self.run_gd(frames, boxes)
        out = dev.out.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertEqual(dev.taps, TOUR_TAPS)
        self.assertNotIn((960, 850), dev.taps)        # Hermes' close point = an achieved card
        for s in ('distribution in 94', 'Activeness Required: 200', 'Challenge badge lit',
                  'Guild Duel phase: Preparati on', 'guild medals: 28704', 'store list empty', 'LOG-ONLY',
                  'buys approved', 'Guild Challenge: 2 claimable', "claim 1: slot 00 'Reach 2000 points in'",
                  'Guild Medal owned: 30104 (store read 28704, +1400)', "claim 2: slot 00 'Reach AFK stage 500.'",
                  'guild tour done'):
            self.assertIn(s, out)

    def test_items_are_logged_not_bought(self):
        frames = HALL_IN + CHEST_SEG + ['gstore2.png', gd41('gd_items')] + BACK_HALL + ['gback.png', board(0)] \
            + ['gback.png'] + OUT
        ocr = {'gd_items_price0': ['210'], 'gd_items_price1': ["'180"]}
        dev, rc = self.run_gd(frames, dict(BASE_BOXES, gd_items=ITEMS), ocr)
        out = dev.out.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn('would-buy: card 0 (?) 210 diamond -> not preferred', out)
        self.assertIn('would-buy: card 1 (?) 180 diamond -> not preferred', out)
        self.assertIn('Daily pill selected: True (Refreshes in 18)', out)
        self.assertIn('balances: guild medals 28704, diamonds None', out)
        self.assertEqual(dev.taps, PRE_TAPS + [gd.CHALLENGE_BTN, gd.BOARD_BACK, gd.HALL_BACK])

    def test_board_without_badges_goes_back(self):
        dev, rc = self.run_gd(with_board(board(0), 'gback.png') + OUT, BASE_BOXES)
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, PRE_TAPS + [gd.CHALLENGE_BTN, gd.BOARD_BACK, gd.HALL_BACK])
        self.assertIn('Guild Challenge: 0 claimable', dev.out.getvalue())

    def test_badge_that_does_not_clear_stops_the_claims(self):
        dev, rc = self.run_gd(with_board('gfr2.png', 'gfr2.png', 'gback.png') + OUT,
                              dict(BASE_BOXES, gd_claim1=BOARD))
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, PRE_TAPS + [gd.CHALLENGE_BTN, SLOT00, gd.BOARD_BACK, gd.HALL_BACK])
        self.assertIn('did not clear the badge', dev.out.getvalue())

    def test_tooltip_close_without_progress_stops(self):   # gcE: the tooltip, badge still lit after it
        dev, rc = self.run_gd(with_board('gcC.png', 'gcE.png', 'gcD.png', 'gback.png') + OUT,
                              dict(BASE_BOXES, gd_board=BOARD_AFTER, gd_claim1=POPUP, gd_claim1_c=BOARD_AFTER))
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, PRE_TAPS + [gd.CHALLENGE_BTN, SLOT00, gd.CLOSE_TAP, gd.BOARD_BACK,
                                               gd.HALL_BACK])
        self.assertIn('did not clear the badge', dev.out.getvalue())

    def test_unknown_screen_after_the_badge_tap(self):
        dev, rc = self.run_gd(with_board('gfr2.png', 'UNKNOWN', 'UNKNOWN', 'UNKNOWN'), BASE_BOXES)
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual(dev.taps, PRE_TAPS + [gd.CHALLENGE_BTN, SLOT00])
        self.assertIn('unknown screen after the claim tap', dev.out.getvalue())

    def test_confirm_dialog_after_the_badge_tap_is_cancelled(self):
        dev, rc = self.run_gd(with_board('gfr2.png', 'DIALOG', 'DIALOG', 'DIALOG'), BASE_BOXES)
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual(dev.taps, PRE_TAPS + [gd.CHALLENGE_BTN, SLOT00, v.CONFIRM_CANCEL])

    def test_close_spot_not_cream_stops_without_a_tap(self):
        dark = hermes('gcE.png').copy()
        dark.paste((60, 40, 30), (440, 610, 520, 690))
        dev, rc = self.run_gd(with_board('gfr2.png', dark), dict(BASE_BOXES, gd_claim1=POPUP))
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual(dev.taps, PRE_TAPS + [gd.CHALLENGE_BTN, SLOT00])

    def test_tooltip_does_not_close(self):
        dev, rc = self.run_gd(with_board('gfr2.png', 'gcE.png', 'gcE.png', 'gcE.png', 'gcE.png'),
                              dict(BASE_BOXES, gd_claim1=POPUP, gd_claim1_c=POPUP, gd_claim1_c_p1=POPUP,
                                   gd_claim1_c_p2=POPUP))
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual(dev.taps, PRE_TAPS + [gd.CHALLENGE_BTN, SLOT00, gd.CLOSE_TAP])

    def test_at_most_five_claims(self):
        boards = [board(k) for k in range(9, 3, -1)]           # 9 lit, then 8 .. 4 after each claim
        boxes = dict(BASE_BOXES, **{f'gd_claim{n}': BOARD for n in range(1, 6)})
        dev, rc = self.run_gd(with_board(*boards, 'gback.png') + OUT, boxes)
        out = dev.out.getvalue()
        self.assertEqual(rc, 0, out)
        slots = [t for t in dev.taps if t not in PRE_TAPS + [gd.CHALLENGE_BTN, gd.BOARD_BACK, gd.HALL_BACK]]
        self.assertEqual(slots, [SLOT00] * 5)                  # always the first lit slot, max 5
        self.assertIn('claim limit 5 reached (4 still lit)', out)

    def test_slot_on_the_confirm_guard_is_not_tapped(self):
        img = board(0)
        x, y = gd.slot_xy(2, 2)
        img.paste(ORANGE, (x - 14, y - 14, x + 15, y + 15))
        dev, rc = self.run_gd(with_board(img, 'gback.png') + OUT, BASE_BOXES)
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, PRE_TAPS + [gd.CHALLENGE_BTN, gd.BOARD_BACK, gd.HALL_BACK])
        self.assertIn('confirm-check guard', dev.out.getvalue())

    def test_board_back_to_the_world(self):
        dev, rc = self.run_gd(with_board(board(0), 'guild2.png'), dict(BASE_BOXES, gd_hall5=[]))
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, PRE_TAPS + [gd.CHALLENGE_BTN, gd.BOARD_BACK])

    def test_board_back_to_nowhere(self):
        dev, rc = self.run_gd(with_board(board(0), 'UNKNOWN', 'UNKNOWN', 'UNKNOWN'), dict(BASE_BOXES, gd_hall5=[]))
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual(dev.taps, PRE_TAPS + [gd.CHALLENGE_BTN, gd.BOARD_BACK])

    def test_board_does_not_open_leaves_the_hall(self):
        hall = {k: HALL2 for k in ('gd_board', 'gd_board_p1', 'gd_board_p2')}
        dev, rc = self.run_gd(with_board('gback.png', 'gback.png', 'gback.png') + OUT, dict(BASE_BOXES, **hall))
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual(dev.taps, PRE_TAPS + [gd.CHALLENGE_BTN, gd.HALL_BACK])

    def test_board_opens_onto_an_unknown_screen(self):
        dev, rc = self.run_gd(with_board('UNKNOWN', 'UNKNOWN', 'UNKNOWN'), dict(BASE_BOXES, gd_board=[]))
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual(dev.taps, PRE_TAPS + [gd.CHALLENGE_BTN])

    def test_hall_not_recognised_before_the_challenge(self):
        frames = HALL_IN + CHEST_SEG + STORE_SEG + BACK_HALL + ['UNKNOWN'] * 3
        dev, rc = self.run_gd(frames, dict(BASE_BOXES, gd_hall4=[]))
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual(dev.taps, PRE_TAPS)
        self.assertIn('hall not recognised before the Challenge', dev.out.getvalue())

    def test_dimmed_board_after_a_claim_stops_without_a_tap(self):   # scrim / fade: no badge reads lit
        dim = hermes('gcC.png').point(lambda p: p // 2)
        dev, rc = self.run_gd(with_board('gfr2.png', dim), dict(BASE_BOXES, gd_claim1=BOARD_AFTER))
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual(dev.taps, PRE_TAPS + [gd.CHALLENGE_BTN, SLOT00])
        self.assertIn('board gutter not cream', dev.out.getvalue())

    def test_dimmed_board_on_open_stops_without_a_tap(self):
        dim = hermes('gfr2.png').point(lambda p: p // 2)
        dev, rc = self.run_gd(with_board(dim), BASE_BOXES)
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual(dev.taps, PRE_TAPS + [gd.CHALLENGE_BTN])

    def test_challenge_badge_off_no_tap(self):
        off = hermes('gback.png').copy()
        off.paste((99, 58, 17), gd.CHALLENGE_BADGE)
        frames = HALL_IN + CHEST_SEG + STORE_SEG + BACK_HALL + [off] + OUT
        dev, rc = self.run_gd(frames, BASE_BOXES)
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, PRE_TAPS + [gd.HALL_BACK])
        self.assertIn('Challenge badge off', dev.out.getvalue())

    def test_challenge_label_off_spot_no_tap(self):
        hall = [b for b in HALL2 if b[4] != 'Challenge']
        frames = HALL_IN + CHEST_SEG + STORE_SEG + BACK_HALL + ['gback.png'] + OUT
        dev, rc = self.run_gd(frames, dict(BASE_BOXES, gd_hall4=hall))
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, PRE_TAPS + [gd.HALL_BACK])

    def test_off_the_world_stops_without_a_tap(self):
        dev, rc = self.run_gd(['UNKNOWN'], {})
        self.assertEqual(rc, 1)
        self.assertEqual(dev.taps, [])

    def test_confirm_dialog_at_start_is_cancelled(self):
        dev, rc = self.run_gd(['DIALOG', 'UNKNOWN'], {})
        self.assertEqual(rc, 1)
        self.assertEqual(dev.taps, [v.CONFIRM_CANCEL])

    def test_guild_icon_off_spot_stops(self):
        dev, rc = self.run_gd(['WORLD'], {})
        self.assertEqual(rc, 1)
        self.assertEqual(dev.taps, [])
        self.assertIn('layout-A', dev.out.getvalue())

    def test_hall_never_appears(self):
        dev, rc = self.run_gd(['guild2.png', 'gstore2.png'] + ['gstore2.png'] * 3, {})
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual(dev.taps, [gd.GUILD_BTN])

    def test_chest_label_missing_skips_the_chest(self):
        hall = [b for b in HALL if b[4] != 'Guild Chesi']
        frames = HALL_IN + STORE_SEG + BACK_HALL + ['gback.png', board(0), 'gback.png'] + OUT
        dev, rc = self.run_gd(frames, dict(BASE_BOXES, gd_hall=hall))
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, [gd.GUILD_BTN, gd.STORE_BTN, gd.DAILY_PILL, gd.STORE_BACK, gd.CHALLENGE_BTN,
                                    gd.BOARD_BACK, gd.HALL_BACK])
        self.assertIn('skipping the chest', dev.out.getvalue())

    def test_night_world_guild4_stops_without_a_tap(self):
        dev, rc = self.run_gd(['guild4.png'], {})     # shared classify() reads it UNKNOWN (LIVE-open)
        self.assertEqual(rc, 1)
        self.assertEqual(dev.taps, [])

    def test_confirm_dialog_in_the_store_is_cancelled(self):
        frames = HALL_IN + CHEST_SEG + ['gstore2.png', 'DIALOG']
        dev, rc = self.run_gd(frames, dict(BASE_BOXES, gd_items=ITEMS))
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual(dev.taps, PRE_TAPS[:5] + [v.CONFIRM_CANCEL])

    def test_unknown_screen_after_daily_stops_without_a_tap(self):
        for frames, boxes in ((['UNKNOWN'] * 3, {}),
                              (['gback.png'] * 3, {'gd_items': HALL2, 'gd_items_p1': HALL2, 'gd_items_p2': HALL2})):
            with self.subTest(frames=frames[0]):
                base = {k: b for k, b in BASE_BOXES.items() if not k.startswith('gd_items')}
                dev, rc = self.run_gd(HALL_IN + CHEST_SEG + ['gstore2.png'] + frames, dict(base, **boxes))
                self.assertEqual(rc, 1, dev.out.getvalue())
                self.assertEqual(dev.taps, PRE_TAPS[:5])
                self.assertIn('unknown screen after the Daily pill', dev.out.getvalue())

    def test_store_back_to_the_world_skips_the_challenge(self):
        for after in (['guild2.png'], ['UNKNOWN', 'guild2.png']):   # direct / after a transition frame
            with self.subTest(after=len(after)):
                dev, rc = self.run_gd(HALL_IN + CHEST_SEG + STORE_SEG + after, dict(BASE_BOXES, gd_hall3=[]))
                self.assertEqual(rc, 0, dev.out.getvalue())
                self.assertEqual(dev.taps, PRE_TAPS)
                self.assertIn('Challenge skipped', dev.out.getvalue())

    def test_guild_tab_not_selected_skips_the_daily_pill(self):
        frames = HALL_IN + CHEST_SEG + ['UNKNOWN'] + BACK_HALL + ['gback.png', board(0), 'gback.png'] + OUT
        dev, rc = self.run_gd(frames, BASE_BOXES)
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, PRE_TAPS[:4] + PRE_TAPS[5:] + [gd.CHALLENGE_BTN, gd.BOARD_BACK, gd.HALL_BACK])
        self.assertIn('tab not selected', dev.out.getvalue())

    def test_chest_tap_leaves_the_hall_unchanged(self):
        still = {k: HALL2 for k in ('gd_chest', 'gd_chest_p1', 'gd_chest_p2')}
        frames = HALL_IN + ['gback.png'] * 3 + STORE_SEG + BACK_HALL + ['gback.png', board(0), 'gback.png'] + OUT
        dev, rc = self.run_gd(frames, dict(BASE_BOXES, **still))
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, [gd.GUILD_BTN, gd.GUILD_CHEST] + PRE_TAPS[3:]
                         + [gd.CHALLENGE_BTN, gd.BOARD_BACK, gd.HALL_BACK])

    def test_chest_tap_to_an_unknown_screen(self):
        dev, rc = self.run_gd(HALL_IN + ['UNKNOWN'] * 3, dict(BASE_BOXES, gd_chest=[]))
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual(dev.taps, [gd.GUILD_BTN, gd.GUILD_CHEST])

    def test_store_hub_not_open_leaves_the_hall(self):
        hall = {k: HALL2 for k in ('gd_store', 'gd_store_p1', 'gd_store_p2')}
        dev, rc = self.run_gd(HALL_IN + CHEST_SEG + ['gback.png'] * 3 + OUT, dict(BASE_BOXES, **hall))
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual(dev.taps, PRE_TAPS[:4] + [gd.HALL_BACK])
        self.assertEqual(dev.shots[-1], 'gd_out')

    def test_store_label_off_spot_skips_the_store(self):
        hall = [b for b in HALL if b[4] not in ('Guild Chesi', 'Store')]
        frames = HALL_IN + ['gback.png', board(0), 'gback.png'] + OUT
        dev, rc = self.run_gd(frames, dict(BASE_BOXES, gd_hall=hall))
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, [gd.GUILD_BTN, gd.CHALLENGE_BTN, gd.BOARD_BACK, gd.HALL_BACK])
        self.assertIn('skipping the store', dev.out.getvalue())

    def test_world_not_reached_at_the_end(self):
        frames, boxes = claim_tour()
        dev, rc = self.run_gd(frames[:-1] + ['gback.png'] * 3, boxes)
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual(dev.taps[-1], gd.HALL_BACK)
        self.assertEqual(dev.shots[-3:], ['gd_out', 'gd_out_p1', 'gd_out_p2'])


if __name__ == '__main__':
    unittest.main()
