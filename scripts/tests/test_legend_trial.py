"""T112 Legend Trial: detectors on Hermes' real LT frames + FakeDevice flows."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from PIL import ImageDraw  # noqa: E402

import afk_claim_vision as v  # noqa: E402
import afk_dream_realm as dr  # noqa: E402
import afk_legend_trial as lt  # noqa: E402
import afk_stage_push as sp  # noqa: E402
from fake_vision import FakeDevice, frame  # noqa: E402
from make_frame_manifest import load_rgb  # noqa: E402
from test_homestead import SPECTRE, hermes  # noqa: E402

ARTIFACTS = Path(__file__).resolve().parent / '.artifacts'
CHALLENGE_BOX = (981, 735, 125, 43, 'Cha//enge/')       # recorded OCR box on ltg4
ELIGIBLE = [482, 578, 673, 769, 864, 960]


def spectre(rel: str):
    path = SPECTRE / rel
    if not path.exists():
        raise unittest.SkipTest(f'frame missing: {path}')
    return load_rgb(path)


def paint(img, boxes):
    img = img.copy()
    d = ImageDraw.Draw(img)
    for box, rgb in boxes:
        d.rectangle(box, fill=rgb)
    return img


def deployed(n: int):
    """ltg8 with the green check on the first n eligible cards."""
    return paint(hermes('ltg8.png'), [((x - 8, lt.CHECK_PROBE_Y - 8, x + 8, lt.CHECK_PROBE_Y + 8),
                                       lt.CHECK_RGB) for x in ELIGIBLE[:n]])


def left_ribbon():
    """ltg4 with the floor-1 ribbon moved to the left slot (floors alternate sides)."""
    img = hermes('ltg4.png').copy()
    rib = img.crop((984, 700, 1230, 770))
    img.paste((40, 40, 40), (975, 690, 1245, 780))
    img.paste(rib, (700, 430))
    return img


def fight():
    """Loading-dark base + a green HP-strip row (DR/arena fight tell)."""
    return paint(hermes('ltg6.png'), [((700, 1036, 1100, 1042), (60, 220, 80))])


class Detectors(unittest.TestCase):
    def test_tower_tabs_and_is_lt_towers(self):
        self.assertEqual(lt.tower_tabs(hermes('ltg2.png')),
                         {'light': 'locked', 'nature': 'locked', 'eternity': 'go', 'will': 'locked'})
        self.assertTrue(lt.is_lt_towers(hermes('ltg2.png')))
        for n in ('ltg0', 'ltg3', 'ltg4', 'ltg5', 'ltg8', 'ltg6', 'lt0'):
            self.assertFalse(lt.is_lt_towers(hermes(f'{n}.png')), n)
        odd = paint(hermes('ltg2.png'), [((1148, 358, 1172, 382), (200, 60, 60))])   # red 'Go!'?
        self.assertIsNone(lt.tower_tabs(odd)['light'])
        self.assertTrue(lt.is_lt_towers(odd))         # an unmeasured tab no longer hides the screen

    def test_challenge_ribbon(self):
        yellow = lambda img: lt.count_px(img, (930, 600, 1270, 800), lambda r, g, b: lt._yellow(r, g, b))  # noqa: E731
        for n in ('ltg4', 'ltg5'):
            self.assertGreaterEqual(yellow(hermes(f'{n}.png')), lt.YELLOW_PX, n)
        self.assertEqual(yellow(hermes('ltg2.png')), 0)
        x, y = lt.find_challenge(hermes('ltg4.png'), [CHALLENGE_BOX])
        self.assertTrue(984 <= x <= 1230 and 700 <= y <= 770, (x, y))
        x, y = lt.find_challenge(hermes('ltg5.png'), [(1020, 723, 126, 29, 'Challenger')])
        self.assertTrue(984 <= x <= 1230 and 700 <= y <= 770, (x, y))
        x, y = lt.find_challenge(hermes('ltg3.png'), [])                    # OCR miss: slot scan
        self.assertTrue(984 <= x <= 1230 and 700 <= y <= 770, (x, y))
        x, y = lt.find_challenge(left_ribbon(), [])        # floor 2+: ribbon on the left side
        self.assertTrue(700 <= x <= 946 and 430 <= y <= 500, (x, y))
        self.assertIsNone(lt.find_challenge(hermes('ltg2.png'), [CHALLENGE_BOX]))
        self.assertIsNone(lt.find_challenge(hermes('ltg8.png'), []))

    def test_prep_pixels(self):
        for n in ('ltg7', 'ltg8', 'ltg9', 'ltgA', 'ltgB', 'ltgC', 'ltgD', 'ltgE', 'ltgF'):
            self.assertTrue(lt.prep_px(hermes(f'{n}.png')), n)
        for n in ('ltg2', 'ltg4', 'ltg6', 'ltg0'):
            self.assertFalse(lt.prep_px(hermes(f'{n}.png')), n)
        hdr = ['Tower of Eternity - Floor 1 (D']
        self.assertTrue(lt.is_lt_prep(hermes('ltg8.png'), hdr))
        self.assertFalse(lt.is_lt_prep(hermes('ltg8.png'), []))

    def test_floor_view(self):
        hdr = ['ower ofEternity']
        for n in ('ltg3', 'ltg4', 'ltg5'):
            self.assertTrue(lt.is_floor_view(hermes(f'{n}.png'), hdr, 'eternity'), n)
        self.assertFalse(lt.is_floor_view(hermes('ltg4.png'), hdr, 'light'))
        for n in ('ltg2', 'ltg8', 'ltg0', 'ltg6'):
            self.assertFalse(lt.is_floor_view(hermes(f'{n}.png'), hdr), n)

    def test_team_state(self):
        self.assertEqual(lt.team_state(hermes('ltg8.png')), (0, ELIGIBLE))
        self.assertEqual(lt.team_state(spectre('shots-41820/dr_f1_pre1.png'))[0], 5)
        self.assertEqual(lt.team_state(spectre('shots-54808/arena_f1_step4.png'))[0], 5)
        self.assertEqual(lt.team_state(deployed(2)), (2, ELIGIBLE[2:]))

    def test_fight_tell(self):
        for rel in ('shots-41820/dr_f1_w0.png', 'shots-54808/arena_1_start.png',
                    'shots-66656/arena_1_start.png', 'shots-82200/arena_1_start.png'):
            self.assertTrue(lt.is_lt_fight(spectre(rel)), rel)
        for n in ('ltg6', 'ltg7', 'ltg2', 'ltg0'):
            self.assertFalse(lt.is_lt_fight(hermes(f'{n}.png')), n)
        self.assertTrue(lt.is_lt_fight(fight()))
        one = paint(hermes('ltg6.png'), [((700, 1036, 779, 1041), (60, 220, 80))])   # 480 px
        self.assertFalse(lt.is_lt_fight(one))
        self.assertTrue(lt.is_lt_fight(one, heroes=1))

    def test_end_card_needs_title_and_text_to_agree(self):
        with mock.patch.object(v, 'ocr_lines', lambda tag: ['Victory', 'Retry']):
            self.assertEqual(lt.end_card(frame('SP_VICTORY_CARD'), 't'), 'defeat')
        with mock.patch.object(v, 'ocr_lines', lambda tag: ['Victory conditions']):
            self.assertEqual(lt.end_card(frame('SP_DEFEAT_CARD'), 't'), 'defeat')
            self.assertEqual(lt.end_card(frame('SP_VICTORY_CARD'), 't'), 'victory')
        with mock.patch.object(v, 'ocr_lines', lambda tag: []):
            self.assertIsNone(lt.end_card(frame('SP_VICTORY_CARD'), 't'))

    def test_why_lt_has_own_gates(self):
        # regression notes: the existing detectors lie on LT frames
        self.assertEqual(sp.classify_battle(hermes('ltg2.png')), 'DEFEAT')
        self.assertTrue(dr.is_fight(hermes('ltg6.png')))
        self.assertIsNone(lt.end_card(hermes('ltg2.png'), 'unused'))

    def test_battle_button_enabled_colour(self):
        self.assertTrue(v.close_to(v.avg(hermes('ltg8.png'), lt.PREP_BATTLE), (161, 193, 153), 3))


class Parsers(unittest.TestCase):
    def test_tickets_and_floor(self):
        self.assertEqual(lt.parse_tickets(['x3']), 3)
        self.assertEqual(lt.parse_tickets(['x 0']), 0)
        self.assertIsNone(lt.parse_tickets([]))
        self.assertEqual(lt.parse_floor(['Tower of Eternity - Floor 1 (D']), 1)
        self.assertEqual(lt.parse_floor(['Floor12']), 12)
        self.assertIsNone(lt.parse_floor(['Auto Battle']))


class KeyGuard(FakeDevice):
    """keyevent BACK only on a verified Battle Modes menu (never on LT screens)."""

    def _key_seq(self, steps, tolerate=True, dry=False):
        if any(k == 4 for k, _ in steps):
            self.test.assertTrue(v.is_battle_modes(self.last), f'BACK off Battle Modes: {self.shots}')
        return super()._key_seq(steps, tolerate, dry)


ETERNITY = lt.TOWERS[2][1]
BACK = lt.BACK_PLATE


class Flows(unittest.TestCase):
    def run_lt(self, frames, *argv, ocr=None, boxes=None, region=None):
        ARTIFACTS.mkdir(exist_ok=True)
        marker = ARTIFACTS / 'legend-trial-last.txt'
        marker.unlink(missing_ok=True)
        dev = KeyGuard(self, frames, ocr=ocr or {},
                       boxes={'lt_eternity': [CHALLENGE_BOX], **(boxes or {})})
        by_box = {lt.LOBBY_LABEL_BOX: ['Legend Trial J'], lt.HEADER_BOX: ['ower ofEternity'],
                  lt.TICKET_BOX: ['x3'], lt.PILL_BOX: ['5 more floors required'],
                  lt.PREP_HEADER_BOX: ['Tower of Eternity - Floor 1 (D']}
        region = region or {}
        for p in (mock.patch.object(v, 'ocr_region',
                                    lambda name, box: list(region.get((name, box), by_box.get(box, [])))),
                  mock.patch.object(lt, 'MARKER', marker)):
            p.start()
            self.addCleanup(p.stop)
        return dev, lt.main(list(argv)), marker

    # world -> Battle Modes (open_battle_modes) -> lobby check -> towers -> Eternity floor view
    def entry(self):
        return ['WORLD', hermes('ltg0.png'), hermes('ltg0.png'), hermes('ltg2.png'), hermes('ltg4.png')]

    def leave_from_floor(self):
        return [hermes('ltg4.png'), hermes('ltg2.png'), hermes('ltg0.png'), hermes('ltg0.png'), 'WORLD']

    def leave_from_prep(self):
        return [hermes('ltg8.png')] + self.leave_from_floor()

    def prep_to_fight(self, deploy=True):
        team = [hermes('ltg8.png')] + [deployed(n) for n in range(1, 6)] if deploy else [deployed(5)]
        return team + [fight()]

    def test_happy_path_deploys_then_battles_then_wins(self):
        frames = (self.entry() + [hermes('ltg6.png'), hermes('ltg8.png')] + self.prep_to_fight()
                  + [fight(), frame('SP_VICTORY_CARD'), hermes('ltg4.png')] + self.leave_from_floor())
        dev, rc, marker = self.run_lt(frames, '--max-floors', '1',
                                      ocr={'lt_eternity_w1_1': ['Victory']},
                                      region={('lt_eternity_a1_0', lt.TICKET_BOX): ['x2']})
        out = dev.out.getvalue()
        self.assertEqual(rc, 0, out)
        taps = dev.taps
        self.assertEqual(taps[:3], [v.GROUND, lt.LT_CARD, ETERNITY])
        xy = taps[3]
        self.assertTrue(984 <= xy[0] <= 1230 and 700 <= xy[1] <= 770, xy)
        deploys = [(x, lt.ROSTER_TAP_Y) for x in ELIGIBLE[:5]]
        self.assertEqual(taps[4:9], deploys)
        self.assertEqual(taps[9:11], [lt.PREP_BATTLE, lt.CARD_CLOSE])
        self.assertEqual(taps[11:], [BACK, BACK, ('key', 4)])
        self.assertIn('deployed 5/eligible 6', out)
        self.assertIn('pill x3 -> x2', out)
        self.assertNotIn((860, 1000), taps)                       # never Auto Battle
        self.assertTrue(marker.exists())

    def test_deploy_taps_dead_never_taps_battle(self):
        frames = self.entry() + [hermes('ltg8.png')] * 4 + self.leave_from_prep()
        dev, rc, marker = self.run_lt(frames)
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertNotIn(lt.PREP_BATTLE, dev.taps)
        self.assertEqual(dev.taps[-6:], [(482, 712), ('touchscreen', 482, 712), BACK, BACK, BACK,
                                         ('key', 4)])                # verified leave, not normalize
        self.assertIn('no hero deployed - not tapping Battle', dev.out.getvalue())
        self.assertFalse(marker.exists())

    def test_prep_lost_during_deploy_never_taps_battle(self):
        # 2 heroes deploy, the 3rd card tap opens something else (hero detail?)
        frames = (self.entry() + [hermes('ltg8.png'), hermes('ltg8.png'), deployed(1), deployed(2),
                                  'DR_HERO_DETAIL', 'DR_HERO_DETAIL'])
        dev, rc, marker = self.run_lt(frames)
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertNotIn(lt.PREP_BATTLE, dev.taps)
        self.assertEqual(dev.taps[-1], (673, 712))                   # no tap after leaving prep
        self.assertIn('prep left after the card tap', dev.out.getvalue())
        self.assertIn('leaving it to normalize (no tap)', dev.out.getvalue())
        self.assertFalse(marker.exists())

    def test_prep_lost_after_tap_retry(self):
        frames = self.entry() + [hermes('ltg8.png'), hermes('ltg8.png'), hermes('ltg8.png'),
                                 'DR_HERO_DETAIL', 'DR_HERO_DETAIL']
        dev, rc, _ = self.run_lt(frames)
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertNotIn(lt.PREP_BATTLE, dev.taps)
        self.assertEqual(dev.taps[-1], ('touchscreen', 482, 712))
        self.assertIn('prep left after the retry', dev.out.getvalue())

    def test_battle_tap_without_effect_is_bounded(self):
        frames = (self.entry() + [hermes('ltg8.png'), deployed(5)]      # prep, team already set
                  + [deployed(5)] * 3 + [deployed(5)] + [deployed(5)] * 3   # 3 polls, retry shot, 3 polls
                  + self.leave_from_prep())
        dev, rc, _ = self.run_lt(frames)
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertEqual(dev.taps[-6:], [lt.PREP_BATTLE, ('touchscreen', *lt.PREP_BATTLE),
                                         BACK, BACK, BACK, ('key', 4)])
        self.assertIn('Battle tap no effect with 5 deployed', dev.out.getvalue())

    def test_no_go_tab_no_tower_tap(self):
        closed = paint(hermes('ltg2.png'), [((1110, 630, 1230, 750), (238, 236, 228))])
        self.assertEqual(set(lt.tower_tabs(closed).values()), {'locked'})
        frames = ['WORLD', hermes('ltg0.png'), hermes('ltg0.png'), closed,
                  closed, hermes('ltg0.png'), 'WORLD']
        dev, rc, marker = self.run_lt(frames)
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [v.GROUND, lt.LT_CARD, BACK])
        self.assertTrue(marker.exists())

    def test_defeat_stops_without_retry_or_close(self):
        frames = (self.entry() + [hermes('ltg8.png')] + self.prep_to_fight()
                  + [frame('SP_DEFEAT_CARD'), frame('SP_DEFEAT_CARD')])
        dev, rc, marker = self.run_lt(frames, ocr={'lt_eternity_w1_0': ['Defeat', 'Retry']})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps[-1], lt.PREP_BATTLE)              # nothing after the fight
        self.assertNotIn(lt.CARD_CLOSE, dev.taps)
        self.assertIn('leaving it to normalize (no tap)', dev.out.getvalue())

    def test_confirm_dialog_after_battle_only_cancelled(self):
        frames = (self.entry() + [hermes('ltg8.png'), deployed(5), frame('DIALOG')]
                  + [deployed(5)] + self.leave_from_floor())
        dev, rc, _ = self.run_lt(frames, ocr={'lt_eternity_s1_0': ['Spend 50 Diamonds to purchase?']})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertIn(v.CONFIRM_CANCEL, dev.taps)
        self.assertFalse({(1142, 710), (1142, 729)} & set(dev.taps))
        self.assertEqual(dev.taps[-4:], [BACK, BACK, BACK, ('key', 4)])

    def test_max_floors_bound(self):
        win = lambda: [fight(), frame('SP_VICTORY_CARD')]          # noqa: E731
        frames = (self.entry() + [hermes('ltg8.png'), deployed(5)] + [fight()] + win()
                  + [deployed(5), deployed(5), fight()] + win() + [deployed(5)]   # auto-advance
                  + [deployed(5)] + self.leave_from_floor())
        ocr = {'lt_eternity_w1_1': ['Victory'], 'lt_eternity_w2_1': ['Victory']}
        dev, rc, _ = self.run_lt(frames, '--max-floors', '2', ocr=ocr)
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps.count(lt.PREP_BATTLE), 2)
        self.assertIn('MAX_FLOORS bound reached', dev.out.getvalue())
        self.assertEqual(lt.MAX_FLOORS, 10)

    def test_unknown_frame_after_challenge_no_further_tap(self):
        frames = self.entry() + ['UNKNOWN'] * (lt.LOAD_POLLS + 1)      # + leave()'s look
        dev, rc, marker = self.run_lt(frames)
        self.assertEqual(rc, 1)
        self.assertEqual(len(dev.taps), 4)                          # ..., Eternity, Challenge
        self.assertIn('prep not reached after Challenge', dev.out.getvalue())
        self.assertFalse(marker.exists())

    def test_tickets_zero_skips_tower(self):
        frames = self.entry() + [hermes('ltg2.png')] + [hermes('ltg2.png'), hermes('ltg0.png'), 'WORLD']
        dev, rc, _ = self.run_lt(frames, region={('lt_eternity', lt.TICKET_BOX): ['x0']})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [v.GROUND, lt.LT_CARD, ETERNITY, BACK, BACK])

    def test_card_tap_needs_second_try_then_still_lobby(self):
        frames = ['WORLD', hermes('ltg0.png'), hermes('ltg0.png'), hermes('ltg0.png'), hermes('ltg0.png'),
                  hermes('ltg0.png'), hermes('ltg0.png'), 'WORLD']
        dev, rc, _ = self.run_lt(frames)
        self.assertEqual(rc, 1)
        self.assertEqual(dev.taps, [v.GROUND, lt.LT_CARD, lt.LT_CARD, ('key', 4)])   # reach_world

    def test_no_ribbon_on_floor_view_is_rc1(self):
        no_rib = paint(hermes('ltg4.png'), [((975, 690, 1245, 780), (40, 40, 40))])
        frames = self.entry()[:-1] + [no_rib, no_rib, hermes('ltg2.png'), hermes('ltg0.png'),
                                      hermes('ltg0.png'), 'WORLD']
        dev, rc, marker = self.run_lt(frames, boxes={'lt_eternity': []})
        self.assertEqual(rc, 1, dev.out.getvalue())
        self.assertIn('no Challenge ribbon on the floor view', dev.out.getvalue())
        self.assertEqual(dev.taps, [v.GROUND, lt.LT_CARD, ETERNITY, BACK, BACK, ('key', 4)])
        self.assertFalse(marker.exists())

    def test_two_floors_via_floor_view(self):
        win = lambda: [fight(), fight(), frame('SP_VICTORY_CARD'), hermes('ltg4.png')]   # noqa: E731
        frames = (self.entry() + [hermes('ltg8.png'), deployed(5)] + win()
                  + [hermes('ltg8.png'), deployed(5)] + win() + self.leave_from_floor())
        dev, rc, _ = self.run_lt(frames, '--max-floors', '2',
                                 ocr={'lt_eternity_w1_1': ['Victory'], 'lt_eternity_w2_1': ['Victory']},
                                 boxes={'lt_eternity_a1_0': [CHALLENGE_BOX]})
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps.count(lt.PREP_BATTLE), 2)
        self.assertEqual(dev.taps.count(lt.CARD_CLOSE), 2)
        self.assertIn('done: 2 floor(s) won in 2 fight(s)', dev.out.getvalue())

    def test_two_open_towers(self):
        two = paint(hermes('ltg2.png'), [((1148, 358, 1172, 382), (64, 169, 145))])   # Light 'Go!'
        self.assertEqual(lt.tower_tabs(two)['light'], 'go')
        frames = (['WORLD', hermes('ltg0.png'), hermes('ltg0.png'), two, hermes('ltg4.png'), two,
                   hermes('ltg4.png'), two] + self.leave_from_floor()[1:])
        dev, rc, _ = self.run_lt(frames, region={('lt_light', lt.HEADER_BOX): ['ower of Light'],
                                                 ('lt_light', lt.TICKET_BOX): ['x0'],
                                                 ('lt_eternity', lt.TICKET_BOX): ['x0']})
        self.assertEqual(rc, 4, dev.out.getvalue())
        self.assertEqual(dev.taps, [v.GROUND, lt.LT_CARD, lt.TOWERS[0][1], BACK, ETERNITY, BACK,
                                    BACK, ('key', 4)])

    def test_calendar_mismatch_logged_in_utc(self):
        class Monday(lt.datetime):
            @classmethod
            def now(cls, tz=None):
                return lt.datetime(2026, 11, 2, 12, tzinfo=tz)    # Light opens Mon by calendar
        with mock.patch.object(lt, 'datetime', Monday):
            dev, rc, _ = self.run_lt(self.entry() + self.leave_from_floor(), '--dry-run')
        self.assertEqual(rc, 0)
        self.assertIn('light: calendar says open (UTC weekday 0), frame says locked', dev.out.getvalue())

    def test_dry_run_reads_only(self):
        frames = self.entry() + self.leave_from_floor()
        dev, rc, marker = self.run_lt(frames, '--dry-run')
        self.assertEqual(rc, 0, dev.out.getvalue())
        self.assertEqual(dev.taps, [v.GROUND, lt.LT_CARD, ETERNITY, BACK, BACK, ('key', 4)])
        self.assertFalse(marker.exists())

    def test_lock_and_idle(self):
        import _bot_lock
        with mock.patch.object(_bot_lock, 'acquire', lambda *a, **k: False):
            dev, rc, _ = self.run_lt([])
        self.assertEqual((rc, dev.taps), (7, []))
        with mock.patch.object(v, 'idle_seconds', lambda: 5.0):
            dev, rc, _ = self.run_lt([], '--min-idle', '180')
        self.assertEqual((rc, dev.taps), (5, []))


if __name__ == '__main__':
    unittest.main()
