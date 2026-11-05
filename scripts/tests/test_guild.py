"""T106 guild daily (log-only) - detectors on Hermes' live frames + FakeVision flows."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

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
ITEM = [(700, 520, 140, 20, 'Invite Letter'), (735, 650, 40, 18, '500')]   # synthetic card (LIVE-open)
NO_BACK_KEY = ('key', 4)


def spectre(rel: str):
    path = SPECTRE / rel
    if not path.exists():
        raise unittest.SkipTest(f'frame missing: {path}')
    return load_rgb(path)


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
        for boxes in (CHEST, CHEST_SKEW, STORE, WORLD_BAR):
            self.assertFalse(gd.is_hall(boxes))
        self.assertTrue(gd.is_chest(CHEST) and gd.is_chest(CHEST_SKEW))
        for boxes in (HALL, STORE, WORLD_BAR):
            self.assertFalse(gd.is_chest(boxes))
        self.assertTrue(gd.is_store(STORE))
        for boxes in (HALL, CHEST, WORLD_BAR):
            self.assertFalse(gd.is_store(boxes))

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
        for name in ('gchest.png', 'guild5.png', 'un1.png', 'un2.png', 'guild2.png'):
            self.assertFalse(gd.guild_tab_selected(hermes(name)), name)
        img = hermes('gstore2.png').copy()          # another tab selected: Arena bg lit, Guild bg dark
        img.paste((243, 243, 243), (400, 360, 450, 420))
        self.assertFalse(gd.guild_tab_selected(img))
        img.paste((91, 91, 91), (400, 240, 450, 330))
        self.assertFalse(gd.guild_tab_selected(img))
        self.assertFalse(gd.pill_selected(hermes('gstore2.png')))     # 'All' is the selected pill

    def test_store_reading(self):
        self.assertFalse(gd.has_items(STORE))
        self.assertTrue(gd.has_items(STORE + ITEM[:1]))
        self.assertEqual(gd.token_balance(STORE), 28704)
        for text, want in (('28 704', 28704), ('1.2K', 1200), ('210', 210), ('Daily', None), ('38+35', None)):
            self.assertEqual(gd._amount(text), want, text)
        self.assertEqual(gd.store_items(ITEM), [('Invite Letter', 500, None)])

    def test_plan_buys(self):
        P = gd.plan_buys
        self.assertEqual(P([('Invite Letter', 500, 'guild')], 28704), [('Invite Letter', 500, 'would buy')])
        self.assertEqual(P([('DR Essence', 210, 'diamond')], 28704)[0][2], 'diamond price')
        # user rule 2026-11-05 + guide consensus: only the daily 210-diamond Invite Letter
        self.assertEqual(P([('Invite Letter', 210, 'diamond')], 28704, diamonds=5000)[0][2],
                         'would buy (guide consensus, diamonds)')
        self.assertEqual(P([('Invite Letter', 300, 'diamond')], 28704, diamonds=5000)[0][2], 'diamond price')
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
        self.assertEqual([r[2] for r in three], ['would buy', 'would buy', 'buy limit'])
        mixed = P([('Hero Shard', 100, 'guild'), ('Invite Letter', 100, 'guild')], 28704)
        self.assertEqual([r[0] for r in mixed], ['Invite Letter', 'Hero Shard'])

    def test_confirm_check_is_never_tapped(self):
        FakeDevice(self, [])
        for xy in ((1142, 710), (1142, 729)):
            with self.assertRaises(RuntimeError):
                gd._tap(xy, 1.0)


TOUR = ['guild2.png', 'guild5.png', 'guild5.png',              # world, open, hall
        'gchal.png', 'gback.png',                              # chest, hall again
        'gstore2.png', 'gstore2.png', 'gstore2.png', 'gstore2.png',  # store hub, items x3 polls
        'gback.png', 'guild2.png']                             # after store (hall), world
TOUR_BOXES = {'gd_hall': HALL, 'gd_chest': CHEST, 'gd_hall2': HALL2, 'gd_store': STORE,
              'gd_items': STORE, 'gd_items_p1': STORE, 'gd_items_p2': STORE, 'gd_hall3': HALL2}
TOUR_TAPS = [gd.GUILD_BTN, gd.GUILD_CHEST, gd.HALL_BACK, gd.STORE_BTN, gd.DAILY_PILL, gd.STORE_BACK, gd.HALL_BACK]


class Flow(unittest.TestCase):
    def run_gd(self, frames, boxes):
        dev = FakeDevice(self, [hermes(f) if isinstance(f, str) and f.endswith('.png') else f
                                for f in frames], boxes=boxes)
        rc = gd.main([])
        self.assertNotIn(NO_BACK_KEY, dev.taps)       # keyevent BACK opens the exit-game dialog
        return dev, rc

    def test_full_tour_is_log_only(self):
        dev, rc = self.run_gd(TOUR, TOUR_BOXES)
        out = dev.out.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertEqual(dev.taps, TOUR_TAPS)
        l, t, r, b = gd.ITEM_AREA
        after = dev.taps[dev.taps.index(gd.STORE_BTN) + 1:]      # taps on the store screen
        self.assertFalse(any(l <= x <= r and t <= y <= b for x, y in after), after)
        for s in ('distribution in 94', 'Activeness Required: 200', 'Challenge badge lit',
                  'Guild Duel phase: Preparati on', '28704', 'store list empty', 'LOG-ONLY', 'buys approved'):
            self.assertIn(s, out)

    def test_items_are_logged_not_bought(self):
        boxes = dict(TOUR_BOXES, gd_items=STORE + ITEM)
        frames = TOUR[:7] + TOUR[9:]                  # items found on the first poll
        dev, rc = self.run_gd(frames, boxes)
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertIn('would-buy: Invite Letter 500 -> currency unknown', dev.out.getvalue())
        self.assertEqual(dev.taps, TOUR_TAPS)

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
        frames = TOUR[:3] + TOUR[5:]
        dev, rc = self.run_gd(frames, dict(TOUR_BOXES, gd_hall=hall))
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, [gd.GUILD_BTN, gd.STORE_BTN, gd.DAILY_PILL, gd.STORE_BACK, gd.HALL_BACK])
        self.assertIn('skipping the chest', dev.out.getvalue())

    def test_night_world_guild4_stops_without_a_tap(self):
        dev, rc = self.run_gd(['guild4.png'], {})     # shared classify() reads it UNKNOWN (LIVE-open)
        self.assertEqual(rc, 1)
        self.assertEqual(dev.taps, [])

    def test_confirm_dialog_in_the_store_is_cancelled(self):
        dev, rc = self.run_gd(TOUR[:6] + ['DIALOG'], dict(TOUR_BOXES, gd_items=STORE + ITEM))
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual(dev.taps, TOUR_TAPS[:5] + [v.CONFIRM_CANCEL])

    def test_unknown_screen_after_daily_stops_without_a_tap(self):
        for frames, boxes in ((['UNKNOWN'] * 3, {}),
                              (['gback.png'] * 3, {'gd_items': HALL2, 'gd_items_p1': HALL2, 'gd_items_p2': HALL2})):
            with self.subTest(frames=frames[0]):
                dev, rc = self.run_gd(TOUR[:6] + frames, dict(TOUR_BOXES, **boxes) if boxes else
                                      {k: b for k, b in TOUR_BOXES.items() if not k.startswith('gd_items')})
                self.assertEqual(rc, 1, dev.out.getvalue())
                self.assertEqual(dev.taps, TOUR_TAPS[:5])
                self.assertIn('unknown screen after the Daily pill', dev.out.getvalue())

    def test_store_back_to_the_world(self):
        for after in (['guild2.png'], ['UNKNOWN', 'guild2.png']):   # direct / after a transition frame
            with self.subTest(after=len(after)):
                dev, rc = self.run_gd(TOUR[:9] + after, dict(TOUR_BOXES, gd_hall3=[]))
                self.assertEqual(rc, 0, dev.out.getvalue())
                self.assertEqual(dev.taps, TOUR_TAPS[:-1])

    def test_guild_tab_not_selected_skips_the_daily_pill(self):
        dev, rc = self.run_gd(TOUR[:5] + ['UNKNOWN'] + TOUR[-2:], TOUR_BOXES)
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, TOUR_TAPS[:4] + TOUR_TAPS[5:])
        self.assertIn('tab not selected', dev.out.getvalue())

    def test_chest_tap_leaves_the_hall_unchanged(self):
        still = {k: HALL2 for k in ('gd_chest', 'gd_chest_p1', 'gd_chest_p2')}
        dev, rc = self.run_gd(TOUR[:3] + ['gback.png'] * 3 + TOUR[5:], dict(TOUR_BOXES, **still))
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, [gd.GUILD_BTN, gd.GUILD_CHEST] + TOUR_TAPS[3:])

    def test_chest_tap_to_an_unknown_screen(self):
        dev, rc = self.run_gd(TOUR[:3] + ['UNKNOWN'] * 3, dict(TOUR_BOXES, gd_chest=[]))
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual(dev.taps, [gd.GUILD_BTN, gd.GUILD_CHEST])

    def test_store_hub_not_open_leaves_the_hall(self):
        hall = {k: HALL2 for k in ('gd_store', 'gd_store_p1', 'gd_store_p2')}
        dev, rc = self.run_gd(TOUR[:5] + ['gback.png'] * 3 + ['guild2.png'], dict(TOUR_BOXES, **hall))
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual(dev.taps, TOUR_TAPS[:4] + [gd.HALL_BACK])
        self.assertEqual(dev.shots[-1], 'gd_out')

    def test_store_label_off_spot_skips_the_store(self):
        hall = [b for b in HALL if b[4] not in ('Guild Chesi', 'Store')]
        dev, rc = self.run_gd(TOUR[:3] + ['guild2.png'], dict(TOUR_BOXES, gd_hall=hall))
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, [gd.GUILD_BTN, gd.HALL_BACK])
        self.assertIn('skipping the store', dev.out.getvalue())

    def test_world_not_reached_at_the_end(self):
        frames = TOUR[:-1] + ['gback.png'] * 3
        dev, rc = self.run_gd(frames, TOUR_BOXES)
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual(dev.taps[-1], gd.HALL_BACK)
        self.assertEqual(dev.shots[-3:], ['gd_out', 'gd_out_p1', 'gd_out_p2'])


if __name__ == '__main__':
    unittest.main()
