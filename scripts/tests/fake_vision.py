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
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from PIL import Image, ImageDraw  # noqa: E402

os.environ.pop('AFK_TAP_MODE', None)   # T97b: a caller's AFK_TAP_MODE must not leak into tests
import afk_claim_vision as v  # noqa: E402
v.TAP_MODE, v._SENDEVENT = 'tap', False   # also if imported earlier; no discovery (adb) in tests

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
    # T92 is_lobby probes, measured on shots-63812/arena_1_lobby: Challenge bar
    # both sides, cream Formation plate, dark navy band under the bar
    'ARENA_LOBBY': ((40, 40, 40), {(800, 1000): (101, 156, 91), (1400, 1000): (101, 156, 91),
                                   (685, 975): (253, 250, 244), (1100, 1068): (11, 11, 26)}),
    'ARENA_PREP': ((40, 40, 40), {(960, 1010): (60, 180, 60)}),
    'ARENA_RESULT': ((40, 40, 40), {(960, 300): (240, 240, 240)}),   # T66: bright card
    # 2026-11-03 live fund: the season-skinned Select screen lights (960,300)
    # warm-orange (banner avg 198.7) AND keeps the Refresh badge bright —
    # the bare bright-card rule stalled the chain as a phantom RESULT
    'ARENA_SELECT': ((40, 40, 40), {(960, 300): (242, 201, 153),
                                    (1160, 1010): (250, 246, 240),
                                    (960, 1010): (131, 99, 98)}),
    # T95 current-layout select (shots-52268/arena_2_select): left sword ring
    # green both sides of the icon, cream back + Refresh plates
    'ARENA_SELECT_T95': ((110, 63, 66), {(807, 782): (103, 157, 92), (883, 782): (105, 172, 109),
                                         (760, 1000): (253, 250, 244), (1300, 1000): (253, 250, 244)}),
    # T95 opponent detail view: cream back plate + green Challenge! bar (T97 test)
    'ARENA_DETAIL_T95': ((110, 63, 66), {(760, 1000): (253, 250, 244), (1300, 1000): (103, 157, 92)}),
    # afk_dailies
    'MENU': ((40, 40, 40), {(480, 1010): (200, 200, 200), (1375, 1028): (200, 200, 200)}),
    'QUESTS': ((40, 40, 40), {(500, 90): (230, 230, 230)}),
    # afk-daily-gift
    'GIFT_ENTRY': ((62, 70, 50), {(1804, 662): (230, 80, 60), v.BACK: (62, 70, 50),
                                  (564, 1010): (62, 70, 50), v.AFK_PROGRESS: (150, 150, 150),
                                  v.AFK_BAR: (52, 168, 167)}),
    'EVENTS': ((40, 40, 40), {(960, 100): (220, 220, 220), v.BACK: (200, 200, 200)}),
    # afk_dream_realm (A8; values from the dream docstrings / runtime review)
    # T91: is_boss_page reads the bar's left end (700,1000) — (101,156,91) on
    # shots-66808/dr_f1_chances — instead of the centre (dark 'Chances' label)
    'DR_BOSS': ((60, 60, 80), {(960, 1040): (109, 154, 100), (1280, 1010): (109, 154, 100),
                               (700, 1000): (101, 156, 91)}),
    'DR_PREP': ((60, 60, 80), {(960, 1040): (240, 240, 240), (1280, 1010): (160, 192, 152)}),
    # T91 live prep (shots-66808/dr_f1_prewait1): hero grid in a cream panel,
    # back + Records plates, one wide Battle bar; classify() reads DR_PREP
    'DR_PREP_GRID': ((60, 60, 80), {v.BACK: (236, 231, 224), (570, 1000): (249, 246, 240),
                                    (690, 1000): (244, 240, 234), (760, 1000): (101, 156, 91),
                                    (960, 1040): (133, 171, 123), (1280, 1010): (101, 156, 91),
                                    (1600, 1000): (100, 177, 78), (478, 700): (246, 242, 235),
                                    (1656, 700): (246, 242, 235)}),
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
    # T94 letterboxed boss page as classify sees it (now6 / shots-75220):
    # dark panel edge at v.BACK, cream back plate, bar, brown letterbox
    'DR_BOSS_PAGE': ((40, 47, 73), {v.BACK: (97, 90, 86), (564, 1010): (253, 249, 244),
                                    v.DR_BOSS_BACK: (250, 247, 242),
                                    (700, 1000): (101, 156, 91), (1280, 1010): (101, 156, 91),
                                    (200, 540): (94, 76, 70), (1720, 540): (75, 55, 44),
                                    (100, 200): (71, 51, 43), (1820, 900): (76, 55, 45)}),
    # + the boss info card (now5): cream header over a grey body -> POPUP
    'DR_BOSS_INFO': ((40, 47, 73), {v.BACK: (97, 90, 86), (564, 1010): (253, 249, 244),
                                    v.DR_BOSS_BACK: (250, 247, 242),
                                    (700, 1000): (101, 156, 91), (1280, 1010): (101, 156, 91),
                                    (200, 540): (94, 76, 70), (1720, 540): (75, 55, 44),
                                    (100, 200): (71, 51, 43), (1820, 900): (76, 55, 45),
                                    (1170, 225): (247, 242, 235), (1150, 285): (247, 242, 235),
                                    (1220, 550): (91, 81, 80)}),
    # T94 UI-less night/aurora transition (now4: mean L 35, B-R 43, nothing white)
    'DR_UI_LESS': ((30, 55, 80), {}),
    'DR_BLACK': ((29, 29, 29), {}),
    'DR_TRANSITION': ((5, 8, 20), {(200, 270): (25, 72, 156)}),
    'DR_DIM': ((8, 8, 10), {(200, 270): (60, 62, 70), (960, 540): (180, 170, 150)}),
    'DR_ENDED': ((30, 30, 30), {(960, 90): (230, 140, 60), (960, 1035): (235, 235, 235),
                                (600, 60): (203, 121, 42), (1500, 60): (203, 121, 42)}),
    # T93 Victory Rewards overlay (shots-72816/dr_post1_0): black letterbox,
    # warm dim centre, bright 'Victory Rewards' title letters
    'DR_VICTORY_REWARDS': ((5, 5, 5), {(960, 540): (113, 77, 41), **{
        (x, 135): (240, 240, 240) for x in range(810, 1340, 90)}}),
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
        self.last = None            # frame of the latest shot (T97 world-BACK guard)
        for name, fake in (('adb', self._no_adb), ('tap', self._tap), ('swipe', self._swipe),
                           ('shot', self._shot), ('ocr_lines', self._ocr),
                           # real ocr_region would open v.TMP = .spectre/shots-<pid> (T82 review)
                           ('ocr_region', lambda name, box: []),
                           ('tap_seq', self._tap_seq), ('key_seq', self._key_seq),
                           ('tap_hold', self._tap_hold)):
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
                  mock.patch.object(v, 'METRICS', self.metrics),
                  # T97b: per-test tap-mode state; sendevent discovery 'unavailable' (no adb)
                  mock.patch.object(v, 'TAP_MODE', 'tap'), mock.patch.object(v, '_TAP_DEAD', set()),
                  mock.patch.object(v, '_SENDEVENT', False)):
            p.start()
            test.addCleanup(p.stop)
        self.out = io.StringIO()   # driver prints, kept off the test runner output
        for p in (mock.patch('time.sleep'), mock.patch.object(sys, 'stdout', self.out)):
            p.start()
            test.addCleanup(p.stop)
        self.test = test

    def _no_adb(self, *args, **kw):
        self.test.fail(f'real adb call: {args}')

    def _tap(self, xy, wait=1.0, mode=None):
        mode = mode or v.TAP_MODE           # T97b: non-default modes are logged as (mode, x, y)
        self.taps.append(tuple(xy) if mode == 'tap' else (mode, *xy))
        return mode

    def _tap_seq(self, steps, tolerate=True, dry=False):    # T75: one batch = taps in order
        self.taps.extend((x, y) for x, y, _ in steps)
        return True

    def _key_seq(self, steps, tolerate=True, dry=False):
        # T97: keyevent BACK on the world view opens the exit confirm — every flow
        # must have read the frame as non-WORLD first
        if (any(k == 4 for k, _ in steps) and self.last is not None
                and v.classify(self.last) == 'WORLD'):
            self.test.fail(f'keyevent BACK on the world view (shots: {self.shots})')
        self.taps.extend(('key', k) for k, _ in steps)
        return True

    def _tap_hold(self, xy, ms=120, wait=1.0):
        self.taps.append(('hold', *xy))

    def _swipe(self, *args, **kw):
        self.taps.append(('swipe', *args))

    def _shot(self, name):
        self.shots.append(name)
        if not self.frames:
            self.test.fail(f'unscripted shot {name!r} (shots so far: {self.shots})')
        self.last = self.frames.pop(0)
        return self.last

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


class DeadTapDevice(FakeDevice):
    """T97 (live 2026-11-04): taps (plain, batched, hold) change nothing; only
    keyevent 4 advances `screens` by one. Every shot shows the current screen;
    more than `max_shots` shots fails the test (unbounded loop)."""

    def __init__(self, test, screens: list, max_shots: int = 40, live_modes=(), **kw):
        super().__init__(test, [], **kw)
        self.screens, self.pos, self.max_shots = list(screens), 0, max_shots
        self.live_modes = live_modes        # T97b: tap modes that DO advance the screen

    def _tap(self, xy, wait=1.0, mode=None):
        if super()._tap(xy, wait, mode) in self.live_modes:
            self.pos = min(self.pos + 1, len(self.screens) - 1)

    def _shot(self, name):
        self.shots.append(name)
        if len(self.shots) > self.max_shots:
            self.test.fail(f'more than {self.max_shots} shots: {self.shots}')
        self.last = frame(self.screens[self.pos])
        return self.last

    def _key_seq(self, steps, tolerate=True, dry=False):
        super()._key_seq(steps, tolerate, dry)
        self.pos = min(self.pos + sum(k == 4 for k, _ in steps), len(self.screens) - 1)
        return True
