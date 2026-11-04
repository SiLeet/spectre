"""T91 Dream Realm prep screen (live daily 2026-11-04 13:2x).

The boss page read as prep (the centre probe sits on the dark 'Chances' label,
(86,130,78) missed _green's G>130 by 0), its PREP_TAP happened to land on the
boss bar and opened the real prep: a hero grid with ONE wide Battle bar. That
prep matched neither is_prep (centre green) nor is_boss_page (is_hero_detail
gate) -> no Battle tap ever fired ('no fight marker after the tap'), and
normalize met it as UNKNOWN. Real-frame cases skip when .spectre is gone.
"""
from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402
import afk_dream_realm as dr  # noqa: E402
import afk_normalize  # noqa: E402
from fake_vision import FakeDevice, frame  # noqa: E402
from make_frame_manifest import REPO, load_rgb  # noqa: E402

PREP = ('shots-66808/dr_f1_prewait1.png', 'shots-80660/norm_0.png')
BOSS = ('shots-66808/dr_f1_chances.png',   # 'Not Ranked', Chances 7/7
        'livecheck/now.png')                 # King Croaker 'Top 37%', Chances 4/7
LOOKALIKES = ('shots-15028/norm_0.png',       # arena lobby: back + Formation + green bar
              'livecheck/c0.png')             # hero detail: back + Ascend + Level-Up bar


def real(relpath: str):
    path = REPO / '.spectre' / relpath
    if not path.exists():
        raise unittest.SkipTest(f'frame missing: .spectre/{relpath}')
    return load_rgb(path)


class DreamCase(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(dr, '_dismiss_taps', 0)
        p.start()
        self.addCleanup(p.stop)


class RealFrames(DreamCase):
    def test_prep_is_its_own_state(self):
        for rel in PREP:
            img = real(rel)
            with self.subTest(rel):
                self.assertEqual(v.classify(img), 'DR_PREP')        # old: UNKNOWN
                self.assertTrue(dr.is_prep(img))                     # old: False
                self.assertFalse(dr.is_boss_page(img))
                self.assertTrue(dr.is_ready(img))
                self.assertFalse(dr.is_fight(img))

    def test_boss_page_is_boss(self):
        for rel in BOSS:
            img = real(rel)
            with self.subTest(rel):
                self.assertTrue(dr.is_boss_page(img))                # old: False (chances)
                self.assertFalse(dr.is_prep(img))                    # old: True (chances)
                self.assertNotEqual(v.classify(img), 'DR_PREP')

    def test_lookalikes_are_neither(self):
        for rel in LOOKALIKES:
            img = real(rel)
            with self.subTest(rel):
                self.assertNotEqual(v.classify(img), 'DR_PREP')
                self.assertFalse(dr.is_prep(img))
                self.assertFalse(dr.is_boss_page(img))               # old: True (false positive)

    def test_live_sequence_taps_boss_then_prep_bar(self):
        # old: PREP_TAP on the boss page, then 10 polls of an unrecognised prep -> None
        boss, prep = real(BOSS[0]), real(PREP[0])
        dev = FakeDevice(self, [boss, prep, prep, 'DR_FIGHT'])
        self.assertEqual(dr.start_fight(1), 'started')
        self.assertEqual(dev.taps, [dr.BOSS_TAP, dr.PREP_TAP])

    def test_prep_tap_lies_on_the_battle_bar(self):
        img = real(PREP[0])
        self.assertTrue(dr._green(v.avg(img, dr.PREP_TAP)))

    def test_normalize_backs_out_of_the_real_prep(self):
        dev = FakeDevice(self, [real(PREP[1]), 'WORLD'])
        self.assertEqual(afk_normalize.main(), 0)
        self.assertEqual(dev.taps, [afk_normalize.DR_PREP_BACK])

    def test_back_arrow_is_on_the_button(self):
        self.assertGreater(v.lum(v.avg(real(PREP[0]), (565, 1000))), 200)   # plate right of the arrow
        x, y = afk_normalize.DR_PREP_BACK
        self.assertTrue(481 <= x <= 598 and 945 <= y <= 1038)


class SyntheticPrep(DreamCase):
    def test_fake_prep_classifies(self):
        img = frame('DR_PREP_GRID')
        self.assertEqual(v.classify(img), 'DR_PREP')
        self.assertTrue(dr.is_prep(img))
        self.assertFalse(dr.is_boss_page(img))

    def test_fake_boss_is_not_dr_prep(self):
        self.assertFalse(v.is_dr_prep(frame('DR_BOSS')))
        self.assertFalse(v.is_dr_prep(frame('DR_HERO_DETAIL')))

    def test_start_fight_on_prep_taps_the_bar(self):
        dev = FakeDevice(self, ['DR_PREP_GRID', 'DR_FIGHT'])
        self.assertEqual(dr.start_fight(1), 'started')
        self.assertEqual(dev.taps, [dr.PREP_TAP])

    def test_run_from_prep_is_inside_dream_realm(self):
        # dr_start, dr_pre1_0, chances, pre0 | after0_0, speed0, w0 | w1 | resolve_0, dr_exit, dr_final
        dev = FakeDevice(self, ['DR_PREP_GRID'] * 4 + ['DR_FIGHT'] * 3 + ['DR_ENDED']
                         + ['DR_PREP_GRID'] * 3)
        self.assertEqual(dr.run(argparse.Namespace(fights=1, wait_fight=150)), 0)
        self.assertIn('already inside Dream Realm', dev.out.getvalue())
        self.assertEqual(dev.taps[0], dr.PREP_TAP)

    def test_dream_reach_world_backs_out_of_prep(self):
        dev = FakeDevice(self, ['DR_PREP_GRID', 'WORLD'])
        self.assertTrue(dr.reach_world('dr_world'))                  # old: 4 unknowns -> False
        self.assertEqual(dev.taps, [afk_normalize.DR_PREP_BACK])


class NormalizePrep(unittest.TestCase):
    def test_prep_back_then_world(self):
        dev = FakeDevice(self, ['DR_PREP_GRID', 'WORLD'])
        self.assertEqual(afk_normalize.main(), 0)
        self.assertEqual(dev.taps, [afk_normalize.DR_PREP_BACK])
        self.assertIn('Dream Realm prep -> BACK', dev.out.getvalue())

    def test_prep_back_is_bounded(self):
        # one extra step for the prep BACK, then the normal 4-step pass
        dev = FakeDevice(self, ['DR_PREP_GRID'] * 6)
        self.assertEqual(afk_normalize.main(), 1)
        self.assertEqual(dev.taps, [afk_normalize.DR_PREP_BACK] + [v.BACK] * 4)

    def test_claim_round_still_refuses_the_prep(self):
        dev = FakeDevice(self, ['DR_PREP_GRID'])
        self.assertEqual(v.claim_round('r1'), 1)
        self.assertEqual(dev.taps, [])


if __name__ == '__main__':
    unittest.main()
