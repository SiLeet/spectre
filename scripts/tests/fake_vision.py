"""Mock-ADB helper: replaces afk_claim_vision's device I/O with scripted frames.

    dev = FakeDevice(self, ['UNKNOWN', 'WORLD'], ocr={'norm_pop0': ['Daily Rewards']})
    rc = afk_normalize.main()
    self.assertEqual(dev.taps, [v.BACK])

Patches v.adb / v.tap / v.swipe / v.shot / v.ocr_lines (and the same names on
any module passed via also=) and time.sleep for the duration of the test
(undone via addCleanup). Any real adb call fails the test.

Synthetic frames ("blank matrix"): a solid 1920x1080 base colour with only the
classifier probe patches painted (measured colours from the
afk_claim_vision docstring, 2026-10-31):

  state    base           back (474,1010)  right of back (564,1010)  extra
  WORLD    (62,70,50)     (62,70,50)       (62,70,50)                AFK chip (60,1036) (150,150,150)
  PANEL    (40,40,40)     (184,176,174)    (230,230,230)             -
  POPUP    (40,40,40)     (62,58,57)       (100,100,100)             claim bar (960,602) (233,179,117)
  UNKNOWN  (128,128,128)  -                -                         -
"""
from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from PIL import Image, ImageDraw  # noqa: E402

import afk_claim_vision as v  # noqa: E402

_SPEC = {
    'WORLD': ((62, 70, 50), {v.BACK: (62, 70, 50), (564, 1010): (62, 70, 50),
                             v.AFK_PROGRESS: (150, 150, 150)}),
    'PANEL': ((40, 40, 40), {v.BACK: (184, 176, 174), (564, 1010): (230, 230, 230)}),
    'POPUP': ((40, 40, 40), {v.BACK: (62, 58, 57), (564, 1010): (100, 100, 100),
                             v.CLAIM: (233, 179, 117)}),
    'UNKNOWN': ((128, 128, 128), {}),
    # afk_arena / review fixes (T58)
    'BATTLE_MODES': ((40, 40, 40), {(480, 270): (240, 235, 225), (890, 934): (240, 240, 240),
                                    (500, 920): (173, 85, 46), (1160, 940): (149, 82, 78)}),
    'ARENA_LOBBY': ((40, 40, 40), {(1080, 1004): (150, 200, 150)}),
    'ARENA_PREP': ((40, 40, 40), {(960, 1010): (60, 180, 60)}),
    # afk_dailies
    'MENU': ((40, 40, 40), {(480, 1010): (200, 200, 200), (1375, 1028): (200, 200, 200)}),
    'QUESTS': ((40, 40, 40), {(500, 90): (230, 230, 230)}),
    'DIALOG': ((40, 40, 40), {(200, 550): (240, 236, 228), (1720, 550): (240, 236, 228),
                              (960, 450): (240, 236, 228), (1014, 710): (245, 240, 230),
                              (1142, 710): (110, 170, 110)}),
}
_CACHE: dict[str, Image.Image] = {}


def frame(state: str) -> Image.Image:
    """Synthetic frame that afk_claim_vision.classify() reads as `state`."""
    if state not in _CACHE:
        base, patches = _SPEC[state]
        img = Image.new('RGB', (1920, 1080), base)
        draw = ImageDraw.Draw(img)
        for (x, y), rgb in patches.items():
            draw.rectangle((x - 14, y - 14, x + 14, y + 14), fill=rgb)
        _CACHE[state] = img
    return _CACHE[state].copy()


class FakeDevice:
    """Scripted screen sequence + tap/shot log."""

    def __init__(self, test, frames: list, ocr: dict[str, list[str]] | None = None, also=()):
        self.frames = [frame(f) if isinstance(f, str) else f for f in frames]
        self.ocr = ocr or {}
        self.taps: list[tuple[int, int]] = []
        self.shots: list[str] = []
        for name, fake in (('adb', self._no_adb), ('tap', self._tap), ('swipe', self._swipe),
                           ('shot', self._shot), ('ocr_lines', self._ocr)):
            for mod in (v, *also):       # also: modules with their own tap/shot copies
                if hasattr(mod, name):
                    p = mock.patch.object(mod, name, fake)
                    p.start()
                    test.addCleanup(p.stop)
        self.out = io.StringIO()   # driver prints, kept off the test runner output
        for p in (mock.patch('time.sleep'), mock.patch.object(sys, 'stdout', self.out)):
            p.start()
            test.addCleanup(p.stop)
        self.test = test

    def _no_adb(self, *args, **kw):
        self.test.fail(f'real adb call: {args}')

    def _tap(self, xy, wait=1.0):
        self.taps.append(tuple(xy))

    def _swipe(self, *args, **kw):
        self.taps.append(('swipe', *args))

    def _shot(self, name):
        self.shots.append(name)
        if not self.frames:
            self.test.fail(f'unscripted shot {name!r} (shots so far: {self.shots})')
        return self.frames.pop(0)

    def _ocr(self, name):
        return list(self.ocr.get(name, []))
