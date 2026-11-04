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
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from PIL import Image, ImageDraw  # noqa: E402

import afk_claim_vision as v  # noqa: E402

# Test isolation (Race-Fund-Fix, 2026-11-03): suite runs must never touch the
# real .spectre/afk-bot.lock. _bot_lock resolves its default at call time, so
# redirecting the module attribute here covers every main()-calling test.
# The gate is additionally stubbed out: atexit releases only at interpreter
# exit, so an acquired temp lock would leak into later tests of the same
# suite process. Flow tests exercise tap logic, not lock contention — real
# semantics live in test_bot_lock via the _real_* originals.
import _bot_lock  # noqa: E402
_bot_lock.LOCK = Path(tempfile.mkdtemp(prefix='afk-bot-lock-test-')) / 'afk-bot.lock'
if getattr(_bot_lock, '_real_acquire', None) is None:
    _bot_lock._real_acquire = _bot_lock.acquire
    _bot_lock._real_release = _bot_lock.release
    _bot_lock._real_describe = _bot_lock.describe
_bot_lock.acquire = lambda *a, **k: True
_bot_lock.release = lambda *a, **k: None
_bot_lock.describe = lambda *a, **k: 'test stub'

_SPEC = {
    'WORLD': ((62, 70, 50), {v.BACK: (62, 70, 50), (564, 1010): (62, 70, 50),
                             v.AFK_PROGRESS: (150, 150, 150), v.AFK_BAR: (52, 168, 167)}),
    # T89 daytime world (shots-79040/norm_0): dark back over a lighter strip,
    # lb-lg -33 — below the old -8 POPUP cliff, only the teal HUD bar says WORLD
    'WORLD_DAY': ((62, 70, 50), {v.BACK: (21, 21, 21), (564, 1010): (54, 54, 54),
                                 v.AFK_PROGRESS: (172, 160, 146), v.AFK_BAR: (52, 168, 167)}),
    'PANEL': ((40, 40, 40), {v.BACK: (184, 176, 174), (564, 1010): (230, 230, 230)}),
    'POPUP': ((40, 40, 40), {v.BACK: (62, 58, 57), (564, 1010): (100, 100, 100),
                             v.CLAIM: (233, 179, 117)}),
    # T88 new panel palette (shots-27712/r1_0_initial): light back on cream plus
    # the panel-only tells, green 'Battle' bar + 'AFK Rewards' badge
    'PANEL_NEW': ((40, 40, 40), {v.BACK: (225, 219, 210), (564, 1010): (253, 250, 244),
                                 (800, 893): (107, 157, 97), (1300, 893): (107, 157, 97),
                                 (712, 207): (79, 148, 75)}),
    # T90 panel still animating in (hermes after_afk_panel_frame): no badge and
    # no Battle bar yet, only the green chapter emblem + white strip band
    'PANEL_ANIM': ((40, 40, 40), {v.BACK: (225, 219, 210), (564, 1010): (253, 250, 244),
                                  (513, 348): (93, 139, 70), (800, 300): (255, 255, 255),
                                  (1200, 300): (255, 255, 255)}),
    # same light back + cream without the tells (hero hall, shots-13228/hl_scan_850)
    'CREAM_BACK': ((40, 40, 40), {v.BACK: (230, 225, 216), (564, 1010): (253, 250, 244)}),
    'UNKNOWN': ((128, 128, 128), {}),
    # afk_arena / review fixes (T58)
    # probes follow is_battle_modes' LIVE 2026-11-04 re-calibration (dcd9772)
    'BATTLE_MODES': ((40, 40, 40), {(480, 270): (240, 235, 225), (890, 960): (240, 240, 240),
                                    (500, 900): (173, 85, 46), (1300, 940): (149, 82, 78)}),
    'ARENA_LOBBY': ((40, 40, 40), {(1080, 1004): (150, 200, 150)}),
    'ARENA_PREP': ((40, 40, 40), {(960, 1010): (60, 180, 60)}),
    'ARENA_RESULT': ((40, 40, 40), {(960, 300): (240, 240, 240)}),   # T66: bright card
    # 2026-11-03 live fund: the season-skinned Select screen lights (960,300)
    # warm-orange (banner avg 198.7) AND keeps the Refresh badge bright —
    # the bare bright-card rule stalled the chain as a phantom RESULT
    'ARENA_SELECT': ((40, 40, 40), {(960, 300): (242, 201, 153),
                                    (1160, 1010): (250, 246, 240),
                                    (960, 1010): (131, 99, 98)}),
    # afk_dailies
    'MENU': ((40, 40, 40), {(480, 1010): (200, 200, 200), (1375, 1028): (200, 200, 200)}),
    'QUESTS': ((40, 40, 40), {(500, 90): (230, 230, 230)}),
    # afk-daily-gift
    'GIFT_ENTRY': ((62, 70, 50), {(1804, 662): (230, 80, 60), v.BACK: (62, 70, 50),
                                  (564, 1010): (62, 70, 50), v.AFK_PROGRESS: (150, 150, 150),
                                  v.AFK_BAR: (52, 168, 167)}),
    'EVENTS': ((40, 40, 40), {(960, 100): (220, 220, 220), v.BACK: (200, 200, 200)}),
    # afk_dream_realm (A8; values from the dream docstrings / runtime review)
    'DR_BOSS': ((60, 60, 80), {(960, 1040): (109, 154, 100), (1280, 1010): (109, 154, 100)}),
    'DR_PREP': ((60, 60, 80), {(960, 1040): (240, 240, 240), (1280, 1010): (160, 192, 152)}),
    # A8 live fund #1: the Battle-Modes menu inside the dream entry flow — its
    # dark body read (109,93,93)/(108,92,92) at the dream probes and used to
    # classify as a running fight (shots-77148/dr_world_0.png)
    'DR_BATTLE_MODES': ((40, 40, 40), {(480, 270): (240, 235, 225), (890, 960): (240, 240, 240),
                                       (500, 900): (173, 85, 46), (1300, 940): (149, 82, 78),
                                       (960, 1040): (109, 93, 93), (1280, 1010): (108, 92, 92)}),
    'DR_FIGHT': ((90, 100, 130), {(960, 1040): (40, 60, 110), (1280, 1010): (22, 32, 72),
                                  (474, 1010): (137, 137, 137)}),
    # A8 live fund #2: hero detail — the full-width green Level-Up bar lights
    # both battle probes; the Ascend + back-arrow plates are bright cream
    # (measured on shots-62080/dr_f1_pre3 / shots-65076/hl_daily_post)
    'DR_HERO_DETAIL': ((90, 100, 90), {(960, 1040): (109, 154, 100), (1280, 1010): (160, 192, 152),
                                       (620, 992): (222, 216, 211), (466, 1014): (217, 211, 207)}),
    'DR_BLACK': ((29, 29, 29), {}),
    'DR_TRANSITION': ((5, 8, 20), {(200, 270): (25, 72, 156)}),
    'DR_DIM': ((8, 8, 10), {(200, 270): (60, 62, 70), (960, 540): (180, 170, 150)}),
    'DR_ENDED': ((30, 30, 30), {(960, 90): (230, 140, 60), (960, 1035): (235, 235, 235)}),
    # afk_stage_push.classify_battle (A8; probe values from the runtime review)
    'SP_PREP': ((60, 60, 60), {(1280, 1000): (80, 200, 80)}),
    'SP_LOADING': ((30, 30, 30), {(549, 846): (23, 23, 23)}),
    'SP_BATTLE': ((50, 50, 60), {(549, 846): (20, 20, 20), (960, 40): (100, 100, 100)}),
    'SP_RESULT': ((60, 60, 60), {(960, 300): (240, 230, 200), (960, 60): (230, 180, 60)}),
    'SP_LAUNCHER': ((20, 20, 20), {(960, 124): (242, 242, 242), (549, 846): (198, 198, 198)}),
    'DIALOG': ((40, 40, 40), {(200, 550): (240, 236, 228), (1720, 550): (240, 236, 228),
                              (960, 450): (240, 236, 228), (1014, 710): (245, 240, 230),
                              (1142, 710): (110, 170, 110)}),
    # T69 Dura's: classify_battle DEFEAT = bright card + blue title band
    'SP_DEFEAT_CARD': ((60, 60, 60), {(960, 300): (240, 230, 200), (960, 60): (60, 80, 220)}),
    'SP_VICTORY_CARD': ((60, 60, 60), {(960, 300): (240, 230, 200), (960, 60): (230, 180, 60)}),
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
                           ('shot', self._shot), ('ocr_lines', self._ocr),
                           # real ocr_region would open v.TMP = .spectre/shots-<pid> (T82 review)
                           ('ocr_region', lambda name, box: []),
                           ('tap_seq', self._tap_seq), ('key_seq', self._key_seq)):
            for mod in (v, *also):       # also: modules with their own tap/shot copies
                if hasattr(mod, name):
                    p = mock.patch.object(mod, name, fake)
                    p.start()
                    test.addCleanup(p.stop)
        # disk side effects on the real .spectre/ (shot-dir prune, battle metrics): never in tests
        self.metrics = Path(__file__).resolve().parent / '.artifacts' / 'battles.test.jsonl'
        self.metrics.parent.mkdir(exist_ok=True)
        self.metrics.unlink(missing_ok=True)
        for p in (mock.patch.object(v, 'prune_shot_dirs', lambda *a, **k: 0),
                  mock.patch.object(v, 'METRICS', self.metrics)):
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

    def _tap_seq(self, steps, tolerate=True, dry=False):    # T75: one batch = taps in order
        self.taps.extend((x, y) for x, y, _ in steps)
        return True

    def _key_seq(self, steps, tolerate=True, dry=False):
        self.taps.extend(('key', k) for k, _ in steps)
        return True

    def _swipe(self, *args, **kw):
        self.taps.append(('swipe', *args))

    def _shot(self, name):
        self.shots.append(name)
        if not self.frames:
            self.test.fail(f'unscripted shot {name!r} (shots so far: {self.shots})')
        return self.frames.pop(0)

    def _ocr(self, name):
        return list(self.ocr.get(name, []))


_REAL_TAP_SEQ = v.tap_seq


def real_seq(test, rc: int = 0) -> list:
    """T83: FakeDevices created after this call run the REAL v.tap_seq on a fake
    adb that answers `rc`; returns the list of (args, kwargs) adb calls (taps
    batched this way do not show up in dev.taps). Class-level, so it also
    reaches a FakeDevice built inside a helper."""
    calls = []

    def adb(dev, *args, **kw):
        calls.append((args, kw))
        return subprocess.CompletedProcess([], rc, b'', b'device offline')
    for p in (mock.patch.object(FakeDevice, '_no_adb', adb),
              mock.patch.object(FakeDevice, '_tap_seq',
                                lambda dev, steps, tolerate=True, dry=False:
                                _REAL_TAP_SEQ(steps, tolerate, dry))):
        p.start()
        test.addCleanup(p.stop)
    return calls
