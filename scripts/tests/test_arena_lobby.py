"""T92 arena lobby gate (live daily 2026-11-04 13:00).

The card tap opened the lobby, but the old probe lum(avg(1080,1004)) > 150
read the green Challenge bar at L 132 -> 'ERROR: arena lobby did not open'.
is_lobby: bar G-dominant both sides + cream Formation plate + dark band under
the bar. Look-alikes share the back+plate+green-bar row. Real-frame cases
skip when .spectre is gone.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

from PIL import ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_arena as ar  # noqa: E402
import afk_claim_vision as v  # noqa: E402
from fake_vision import FakeDevice, frame  # noqa: E402
from make_frame_manifest import REPO, load_rgb  # noqa: E402

LOBBY = ('shots-63812/arena_1_lobby.png',      # the failing live frame
         'shots-59516/arena_1_lobby.png', 'shots-15028/norm_0.png')
LOOKALIKES = ('shots-66808/dr_f1_prewait1.png',  # DR prep: back + Records + bar, cream band
              'shots-66808/dr_f1_chances.png',   # DR boss page: bar under the plate slot
              'livecheck/c0.png',                # hero detail: back + Ascend + Level-Up bar
              'shots-27712/r1_0_initial.png')    # AFK Rewards panel: Battle bar (old: True)


def real(relpath: str):
    path = REPO / '.spectre' / relpath
    if not path.exists():
        raise unittest.SkipTest(f'frame missing: .spectre/{relpath}')
    return load_rgb(path)


class RealFrames(unittest.TestCase):
    def test_lobby(self):
        for rel in LOBBY:
            with self.subTest(rel):
                self.assertTrue(ar.is_lobby(real(rel)))

    def test_challenge_tap_lies_on_the_bar(self):
        c = ar.avg(real(LOBBY[0]), ar.CHALLENGE)
        self.assertGreater(c[1] - max(c[0], c[2]), 35)       # measured (101,156,91)

    def test_lookalikes(self):
        for rel in LOOKALIKES:
            with self.subTest(rel):
                self.assertFalse(ar.is_lobby(real(rel)))

    def test_main_passes_the_live_lobby(self):
        # old: 'ERROR: arena lobby did not open', rc 1, no Challenge tap
        dev = FakeDevice(self, ['WORLD', 'BATTLE_MODES', real(LOBBY[0]), 'UNKNOWN', 'DIALOG'],
                         also=(ar,))
        with mock.patch.object(sys, 'argv', ['afk_arena.py']):
            self.assertEqual(ar.main(), 0)
        self.assertEqual(dev.taps, [v.GROUND, ar.ARENA_CARD, ar.CHALLENGE, v.CONFIRM_CANCEL])


class Synthetic(unittest.TestCase):
    def test_fake_lobby(self):
        self.assertTrue(ar.is_lobby(frame('ARENA_LOBBY')))

    def test_fake_lookalikes(self):
        for st in ('DR_PREP_GRID', 'DR_BOSS', 'DR_HERO_DETAIL', 'PANEL_NEW', 'BATTLE_MODES',
                   'ARENA_SELECT', 'ARENA_PREP', 'UNKNOWN'):
            with self.subTest(st):
                self.assertFalse(ar.is_lobby(frame(st)))

    def test_each_gate_is_needed(self):
        # lobby with one tell swapped for the look-alike's value -> False
        for xy, rgb in ((ar.LOBBY_BAR[1], (236, 231, 220)),    # bar end cream (hero detail)
                        (ar.LOBBY_PLATE, (101, 156, 91)),      # bar under the plate (DR boss)
                        (ar.LOBBY_BAND, (240, 236, 228)),      # cream band (DR prep)
                        ((480, 270), (240, 235, 225))):        # bright hall (Battle Modes)
            img = frame('ARENA_LOBBY')
            x, y = xy
            ImageDraw.Draw(img).rectangle((x - 14, y - 14, x + 14, y + 14), fill=rgb)
            with self.subTest(xy):
                self.assertFalse(ar.is_lobby(img))


if __name__ == '__main__':
    unittest.main()
