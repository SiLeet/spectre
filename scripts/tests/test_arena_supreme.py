"""T108 arena ticket pill + Supreme check.

The lobby's 'N/1' pill = Warrior's Guarantee tickets held / cost per Challenge.
At 0/1 (shots-41632, 54424 norm_0, 82200 arena_exit2) Challenge opened 'Spend 10 diamonds to purchase ...':
ticket_clusters >= 2 -> main() stops before Challenge (user policy: never buy).
Supreme Arena is on no frame -> no Supreme code (LIVE-open TODO in afk_arena).
Real-frame cases skip when the frames are gone.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_arena as ar  # noqa: E402
import afk_claim_vision as v  # noqa: E402
from fake_vision import FakeDevice, frame  # noqa: E402
from test_homestead import SPECTRE, hermes, load_rgb  # noqa: E402

ZERO = ('shots-41632/arena_1_lobby.png',                   # 0/1, orange '0'
        'shots-54424/norm_0.png',
        'shots-82200/arena_exit2.png')
LEFT = ('shots-54808/arena_1_lobby.png',                    # 2/1
        'shots-82200/arena_1_lobby.png',                    # 1/1
        'trash/shots-63812/arena_1_lobby.png')
CONTINUE = ('shots-66656/arena_1_lobby.png', 'trash/shots-6048/arena_1_lobby.png')


def real(rel: str):
    path = SPECTRE / rel
    if not path.exists():
        raise unittest.SkipTest(f'frame missing: {path}')
    return load_rgb(path)


class RealFrames(unittest.TestCase):
    def test_zero_tickets(self):
        for rel in ZERO:
            with self.subTest(rel):
                img = real(rel)
                self.assertTrue(ar.is_lobby(img))
                self.assertEqual(ar.ticket_clusters(img), 2)

    def test_tickets_left(self):
        for rel in LEFT:
            with self.subTest(rel):
                self.assertEqual(ar.ticket_clusters(real(rel)), 1)

    def test_tickets_left_hermes_wide_lobby(self):
        for name in ('ar5.png', 'ar6.png'):                 # 4/1
            with self.subTest(name):
                self.assertEqual(ar.ticket_clusters(hermes(name)), 1)

    def test_continue_has_no_pill(self):
        for rel in CONTINUE:
            with self.subTest(rel):
                self.assertEqual(ar.ticket_clusters(real(rel)), 0)

    def test_main_stops_at_zero_without_challenge(self):
        # real exit (shots-82200 exit2 -> exit3): 0/1 lobby reads PREP -> BACK -> Battle Modes -> BACK
        zero = real(ZERO[0])
        dev = FakeDevice(self, ['WORLD', 'BATTLE_MODES', zero, zero, 'BATTLE_MODES', 'WORLD'],
                         also=(ar,))
        with mock.patch.object(sys, 'argv', ['afk_arena.py']):
            self.assertEqual(ar.main(), 0)
        self.assertNotIn(ar.CHALLENGE, dev.taps)
        self.assertNotIn(v.CONFIRM_CANCEL, dev.taps)
        self.assertEqual(dev.taps, [v.GROUND, ar.ARENA_CARD, ('key', 4), ('key', 4)])

    def test_main_challenges_with_tickets_left(self):
        # replaces the skipped trash/shots-63812 case in test_arena_lobby; ends on the cancel backstop
        dev = FakeDevice(self, ['WORLD', 'BATTLE_MODES', real(LEFT[1]), 'UNKNOWN', 'DIALOG'],
                         also=(ar,))
        with mock.patch.object(sys, 'argv', ['afk_arena.py']):
            self.assertEqual(ar.main(), 0)
        self.assertEqual(dev.taps, [v.GROUND, ar.ARENA_CARD, ar.CHALLENGE, v.CONFIRM_CANCEL])


class Synthetic(unittest.TestCase):
    def test_fake_lobby_has_no_pill(self):
        # synthetic lobby -> 0 clusters -> existing flow proceeds (test_arena_lobby)
        self.assertEqual(ar.ticket_clusters(frame('ARENA_LOBBY')), 0)


if __name__ == '__main__':
    unittest.main()
