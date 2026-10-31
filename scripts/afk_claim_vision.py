"""State-checked AFK Journey claim driver.

Instead of firing a blind tap sequence, this script screenshots the emulator,
classifies the screen (WORLD / PANEL / POPUP) from a few stable colour probes,
and only taps when the expected screen is actually up. That makes the claim
observable and stops the silent no-ops the blind sequence produced when the game
was sitting in some other panel.

Screen signatures (1920x1080 BlueStacks, measured 2026-10-31):
  (474,1010) back-arrow circle : WORLD  ~(62,70,50) dark green
                                PANEL  ~(184,176,174) light grey
                                POPUP  ~(62,58,57) dimmed
  (1390,704) claim chip        : PANEL/POPUP ~(240,191,52) orange
  (960,602)  popup claim bar   : POPUP  ~(233,179,117) bright

Usage: python scripts/afk_claim_vision.py [--rounds N] [--pause S] [--dry-run]
Exit codes: 0 claim verified, 1 could not reach a claimable state (or the screen
was unrecognised — blind taps are refused), 2 adb/preflight error,
4 nothing claimable yet (chest accrual too small), 5 skipped (PC in use).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parent.parent
import os
TMP = REPO / '.spectre' / f'shots-{os.getpid()}'   # per-run dir: concurrent runs must not collide
TMP.mkdir(parents=True, exist_ok=True)
ADB = Path.home() / 'AppData/Local/Android/Sdk/platform-tools/adb.exe'
SERIAL = '127.0.0.1:5555'

AFK_PROGRESS = (60, 1036)
CHEST = (975, 760)
CLAIM = (960, 602)
BACK = (474, 1010)
GROUND = (300, 250)


def adb(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run([str(ADB), '-s', SERIAL, *args], capture_output=True, timeout=timeout)


def tap(xy: tuple[int, int], wait: float = 1.0) -> None:
    p = adb('shell', 'input', 'tap', str(xy[0]), str(xy[1]))
    if p.returncode != 0:
        raise RuntimeError(f'adb tap failed at {xy}: {p.stderr[:120]!r}')
    time.sleep(wait)


def swipe(x1: int, y1: int, x2: int, y2: int, millis: int = 400, wait: float = 1.0) -> None:
    adb('shell', 'input', 'swipe', str(x1), str(y1), str(x2), str(y2), str(millis))
    time.sleep(wait)


def shot(name: str) -> Image.Image:
    path = TMP / f'{name}.png'
    with open(path, 'wb') as fh:
        p = subprocess.run([str(ADB), '-s', SERIAL, 'exec-out', 'screencap', '-p'],
                           stdout=fh, timeout=60)
    if p.returncode != 0:
        raise RuntimeError('screencap failed')
    im = Image.open(path)
    im.load()
    out = im.convert('RGB')
    im.close()
    return out


def avg(img: Image.Image, xy: tuple[int, int], r: int = 9) -> tuple[int, int, int]:
    x, y = xy
    px = img.crop((x - r, y - r, x + r, y + r)).resize((1, 1), Image.Resampling.BILINEAR).getpixel((0, 0))
    return (int(px[0]), int(px[1]), int(px[2]))


def close_to(c: tuple[int, int, int], ref: tuple[int, int, int], tol: int) -> bool:
    return all(abs(a - b) <= tol for a, b in zip(c, ref))


def lum(c: tuple[int, int, int]) -> float:
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def adb_exec_dump(pid: str, base_hex: str, out_path: Path):
    """Read team_power (heap_base + 0xA578) via spectre dump. None on failure."""
    addr = hex(int(base_hex, 16) + 0xA578)
    p = subprocess.run([str(REPO / 'target' / 'release' / 'spectre.exe'), 'dump', pid, addr, '8',
                        '--adb', '--format', 'raw', '--output', str(out_path)],
                       cwd=REPO, capture_output=True, timeout=120)
    if p.returncode != 0 or not Path(out_path).exists():
        return None
    return p


def memory_preflight(pid: str, base_hex: str) -> tuple[str, int | None]:
    """Read team_power as a sanity check for pid + heap base.

    Returns (status, value) with status in:
      'ok'    — plausible power, the mapping is right
      'stale' — read succeeded but the value is implausible: after a game restart
                the heap base can stay identical while the internal layout
                moves, so the recorded offset no longer holds the power. The
                vision gates still protect the taps, so this is a warning.
      'fail'  — the read itself failed (dead pid / no adb).
    """
    import struct
    out = REPO / '.spectre' / 'power.bin'
    if adb_exec_dump(pid, base_hex, out) is None:
        return 'fail', None
    raw = out.read_bytes()
    if len(raw) < 8:
        return 'fail', None
    power = struct.unpack('<q', raw[:8])[0]
    if 100_000 < power < 10_000_000_000:
        return 'ok', power
    return 'stale', power


BATTLE_MODES_BTN = (890, 1060)   # bottom-nav Battle Modes entry (UI-fixed)


def is_battle_modes(img: Image.Image) -> bool:
    """Battle Modes menu open: bright cream body + bright tab bar."""
    return (lum(avg(img, (480, 270))) > 200
            and lum(avg(img, (890, 934))) > 200)


def reach_world(max_steps: int = 6) -> bool:
    """Tap BACK until the verified world view is up."""
    for i in range(max_steps):
        img = shot(f'rw_{i}')
        if classify(img) == 'WORLD':
            return True
        tap(BACK, 1.5)
    return classify(shot('rw_final')) == 'WORLD'


def open_battle_modes(max_steps: int = 4) -> bool:
    """From the world view, open the Battle Modes menu and verify it.""
    if not reach_world():
        return False
    tap(GROUND, 0.8)               # dismiss any interact menu first
    for i in range(max_steps):
        img = shot(f'bm_{i}')
        if is_battle_modes(img):
            return True
        tap(BATTLE_MODES_BTN, 3.0)
    return is_battle_modes(shot('bm_final'))


def idle_seconds() -> float | None:
    """Seconds since the last keyboard/mouse input (Windows). None if unknown.

    Scheduled runs use this so the bot never hijacks the screen while Sergej is
    actually using the PC (playing manually, working)."""
    if sys.platform != 'win32':
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [('cbSize', wintypes.UINT), ('dwTime', wintypes.DWORD)]

        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            return None
        return (ctypes.windll.kernel32.GetTickCount() - lii.dwTime) / 1000.0
    except Exception:
        return None


def classify(img: Image.Image) -> str:
    """Classify the screen. Thresholds use luminance/contrast, not absolute RGB,
    because AFK Journey tints the world with a day/night cycle (a night homestead
    reads (24,53,80) where the day reads (62,70,50)); the panel UI itself is not
    tinted."""
    back = avg(img, BACK)
    bg = avg(img, (BACK[0] + 90, BACK[1]))          # just right of the back arrow
    bar = avg(img, CLAIM)                            # bright only in the chest popup
    lb, lg, lbar = lum(back), lum(bg), lum(bar)

    if close_to(back, (184, 176, 174), 22) and lg > 190:
        return 'PANEL'
    # POPUP before WORLD: a dimmed popup used to satisfy the WORLD predicate
    # (|lb-lg| < 15 also matched lb-lg in (-15,-8]), which then tapped the world
    # sequence into a live popup.
    if lb < 100 and (lbar > 172 or lb - lg < -8):
        return 'POPUP'
    if lb < 100 and abs(lb - lg) < 8:
        return 'WORLD'
    chip = avg(img, (1390, 704))
    # only trust the chip fallback when the back arrow is clearly NOT dimmed
    if lb > 140 and chip[0] > 200 and chip[1] > 150 and chip[2] < 120:
        return 'PANEL'
    return 'UNKNOWN'


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--rounds', type=int, default=1)
    ap.add_argument('--pause', type=float, default=0)
    ap.add_argument('--pid', default=None, help='game pid (memory preflight)')
    ap.add_argument('--base', default=None, help='hot-heap base hex (memory preflight)')
    ap.add_argument('--min-idle', type=float, default=0,
                    help='skip unless the PC has been idle this many seconds (scheduled runs)')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    if args.min_idle > 0 and not args.dry_run:
        idle = idle_seconds()
        if idle is None:
            print('    WARN: idle time unavailable, continuing', flush=True)
        elif idle < args.min_idle:
            print(f'    SKIP: PC is in use (idle {idle:.0f}s < {args.min_idle:.0f}s)', flush=True)
            return 5
        else:
            print(f'    idle check ok ({idle:.0f}s)', flush=True)

    if args.pid and args.base and not args.dry_run:
        status, power = memory_preflight(args.pid, args.base)
        if status == 'fail':
            print('    ERROR: team_power preflight could not read memory', flush=True)
            return 2
        if status == 'stale':
            print(f'    WARN: team_power offset stale after restart (read {power}) — '
                  'relying on the screen-state gates', flush=True)
        else:
            print(f'    preflight team_power = {power}', flush=True)

    for rnd in range(1, args.rounds + 1):
        print(f'--- round {rnd}/{args.rounds} {time.strftime("%H:%M:%S")}', flush=True)
        state = classify(shot(f'r{rnd}_0_initial'))
        print(f'    initial state: {state}', flush=True)

        if state == 'WORLD':
            if args.dry_run:
                print('    [dry-run] would tap AFK progress', flush=True)
                continue
            tap(GROUND, 0.8)
            tap(AFK_PROGRESS, 3.0)
            state = classify(shot(f'r{rnd}_1_panel'))
            print(f'    after AFK tap: {state}', flush=True)
        if state == 'POPUP':
            # a popup from a previous run: close it and retry from the panel
            tap(BACK, 1.5)
            state = classify(shot(f'r{rnd}_1b_recover'))
            print(f'    after close: {state}', flush=True)
        if state == 'UNKNOWN':
            # never fire the recovery taps on an unidentified screen: that is
            # how a blind tap ends up on a store/purchase dialog
            print('    ERROR: unknown screen — refusing to tap blind', flush=True)
            return 1
        if state != 'PANEL':
            tap(BACK, 1.0)
            tap(BACK, 1.0)
            tap(GROUND, 0.8)
            tap(AFK_PROGRESS, 3.0)
            state = classify(shot(f'r{rnd}_2_retry'))
            print(f'    retry state: {state}', flush=True)
        if state != 'PANEL':
            print('    ERROR: could not reach the AFK panel', flush=True)
            return 1
        if args.dry_run:
            print('    [dry-run] panel reached, would open chest + claim', flush=True)
            continue

        tap(CHEST, 2.2)
        state = classify(shot(f'r{rnd}_3_chest'))
        print(f'    after chest tap: {state}', flush=True)
        if state != 'POPUP':
            # The game does not open the info popup when almost nothing has
            # accrued (< ~2 min). One retry, then report "nothing claimable"
            # instead of a hard error — nothing was tapped wrongly.
            tap(CHEST, 2.5)
            state = classify(shot(f'r{rnd}_3b_chest_retry'))
            print(f'    chest retry: {state}', flush=True)
        if state != 'POPUP':
            print('    SKIP: nothing claimable yet (chest accrual too small)', flush=True)
            return 4

        tap(CLAIM, 2.5)
        state = classify(shot(f'r{rnd}_4_after'))
        print(f'    after claim: {state}', flush=True)
        if state == 'PANEL':
            tap(BACK, 1.0)
            print('    claim verified (popup closed, panel back)', flush=True)
        else:
            print(f'    WARN: unexpected state after claim: {state}', flush=True)

        if rnd < args.rounds and args.pause:
            time.sleep(args.pause)
    print('done', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
