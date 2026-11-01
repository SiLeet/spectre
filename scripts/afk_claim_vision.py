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
import json
import struct
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parent.parent
import os
TMP = REPO / '.spectre' / f'shots-{os.getpid()}'   # per-run dir: concurrent runs must not collide
# created lazily in shot(): importing this module (--help, dry-run) must not touch the disk
ADB = Path.home() / 'AppData/Local/Android/Sdk/platform-tools/adb.exe'
SERIAL = '127.0.0.1:5555'

# --- team_power guard (T44) -------------------------------------------------
# The offset is valid for ONE process lifetime only: after a game restart the
# heap base can survive while the layout inside the region moves, so the slot
# goes stale. Re-location is anchored on the last VERIFIED value (state file):
# power moves slowly and only upward for this bot, so a tight window
# [0.98x .. 5x last] + stability across two dumps + >=2 display copies
# (the game keeps display copies next to the authoritative slot) isolates the
# slot without any screen-state dependency.
POWER_STATE = REPO / '.spectre' / 'power-state.json'
DEFAULT_POWER_OFFSET = 0xA578
SCAN_BYTES = 16 * 1024 * 1024
GUARD_LO, GUARD_HI = 100_000, 10_000_000_000


def load_power_state() -> dict:
    try:
        return json.loads(POWER_STATE.read_text())
    except Exception:
        return {}


def save_power_state(state: dict) -> None:
    try:
        state['updated'] = time.strftime('%Y-%m-%dT%H:%M:%S')
        POWER_STATE.write_text(json.dumps(state))
    except Exception:
        pass   # the guard is best-effort; never break a run over the state file


def adb_exec_dump(pid: str, addr: str, out_path: Path, size: str = '8') -> subprocess.CompletedProcess | None:
    """spectre dump <addr> as raw bytes. None on failure."""
    p = subprocess.run([str(REPO / 'target' / 'release' / 'spectre.exe'), 'dump', pid, addr, size,
                        '--adb', '--format', 'raw', '--output', str(out_path)],
                       cwd=REPO, capture_output=True, timeout=300)
    if p.returncode != 0 or not Path(out_path).exists():
        return None
    return p


def read_power(pid: str, base_hex: str, offset: int) -> int | None:
    """Read the i64 at heap_base + offset. None on failure."""
    out = TMP / 'power.bin'   # per-run path: concurrent runs raced on the shared file
    out.parent.mkdir(parents=True, exist_ok=True)
    if adb_exec_dump(pid, hex(int(base_hex, 16) + offset), out) is None:
        return None
    raw = out.read_bytes()
    if len(raw) < 8:
        return None
    return struct.unpack('<q', raw[:8])[0]


def scan_i64_range(buf: bytes, lo: int, hi: int) -> dict[int, list[int]]:
    """All i64 slots (8-byte aligned and +4) whose signed value is in [lo, hi].

    Prefilter: for lo >= 100k every in-range value has zero bytes at +5/+6/+7,
    so the per-slot cost is three byte reads for almost all offsets."""
    hits: dict[int, list[int]] = {}
    b4_max = hi >> 32
    for off in range(0, len(buf) - 8, 4):
        if buf[off + 5] or buf[off + 6] or buf[off + 7] or buf[off + 4] > b4_max:
            continue
        v = int.from_bytes(buf[off:off + 8], 'little', signed=True)
        if lo <= v <= hi:
            hits.setdefault(v, []).append(off)
    return hits


def revalidate_power_offset(pid: str, base_int: int, last_power: int) -> tuple[int, int] | None:
    """Re-locate the team_power slot after a game restart.

    Dumps the first 16 MB of the hot heap twice (5 s apart) and keeps values
    that (a) sit in the anchored window, (b) are identical in both dumps and
    (c) exist at >= 2 addresses (display copies + authoritative slot). Returns
    (offset, value) or None.
    """
    lo = max(GUARD_LO, int(last_power * 0.98))
    hi = min(GUARD_HI, int(last_power * 5) + 1_000_000)
    dumps: list[bytes] = []
    try:
        for i in (1, 2):
            out = TMP / f'power_scan_{i}.bin'
            out.parent.mkdir(parents=True, exist_ok=True)
            if adb_exec_dump(pid, hex(base_int), out, str(SCAN_BYTES)) is None:
                return None
            buf = out.read_bytes()
            if len(buf) < 1024:
                return None
            dumps.append(buf)
            if i == 1:
                time.sleep(5)
    finally:
        for i in (1, 2):
            try:
                (TMP / f'power_scan_{i}.bin').unlink()
            except OSError:
                pass
    h1 = scan_i64_range(dumps[0], lo, hi)
    h2 = scan_i64_range(dumps[1], lo, hi)
    best: tuple[int, int, int] | None = None   # (copies, value, offset)
    for val, offs in h1.items():
        if len(offs) < 2 or val not in h2:
            continue
        if best is None or len(offs) > best[0]:
            best = (len(offs), val, offs[0])
    if best is None:
        return None
    return best[2], best[1]


def memory_preflight(pid: str, base_hex: str) -> tuple[str, int | None]:
    """Read team_power as a sanity check for pid + heap base.

    Returns (status, value) with status in:
      'ok'       — plausible power; the mapping is current (state file updated,
                   so the next process restart has a fresh re-location anchor)
      'disabled' — the recorded offset is stale and re-location failed (or no
                   anchor exists): the guard is OFF for this process lifetime,
                   the vision gates still protect the taps. Callers log this
                   quietly instead of spamming a WARN every run (T44).
      'fail'     — the read itself failed (dead pid / no adb).
    """
    st = load_power_state()
    offset = int(st.get('offset', DEFAULT_POWER_OFFSET))
    power = read_power(pid, base_hex, offset)
    if power is None:
        return 'fail', None
    if GUARD_LO < power < GUARD_HI:
        save_power_state({'offset': offset, 'power': power, 'pid': pid, 'base': base_hex})
        return 'ok', power
    # stale: try to re-locate from the last verified value
    last = st.get('power')
    if last:
        found = revalidate_power_offset(pid, int(base_hex, 16), int(last))
        if found:
            new_off, val = found
            save_power_state({'offset': new_off, 'power': val, 'pid': pid,
                              'base': base_hex, 'revalidated': True})
            return 'ok', val
    return 'disabled', power

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
    TMP.mkdir(parents=True, exist_ok=True)
    with open(path, 'wb') as fh:
        p = subprocess.run([str(ADB), '-s', SERIAL, 'exec-out', 'screencap', '-p'],
                           stdout=fh, timeout=60)
    if p.returncode != 0:
        raise RuntimeError('screencap failed')
    im = Image.open(path)
    try:
        im.load()
        out = im.convert('RGB')
    finally:
        im.close()   # also on a failed convert (fd leak on the error path)
    return out


def avg(img: Image.Image, xy: tuple[int, int], r: int = 9) -> tuple[int, int, int]:
    x, y = xy
    px = img.crop((x - r, y - r, x + r, y + r)).resize((1, 1), Image.Resampling.BILINEAR).getpixel((0, 0))
    return (int(px[0]), int(px[1]), int(px[2]))


def close_to(c: tuple[int, int, int], ref: tuple[int, int, int], tol: int) -> bool:
    return all(abs(a - b) <= tol for a, b in zip(c, ref))


def lum(c: tuple[int, int, int]) -> float:
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


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
    """From the world view, open the Battle Modes menu and verify it."""
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
        if status == 'disabled':
            print(f'    team_power guard disabled (offset stale, read {power}) — '
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
        if state == 'POPUP':
            # the claim popup can persist past the tap (T38 #8): retry once,
            # then fail loudly instead of reporting a claim that never landed
            print('    claim popup still open, retrying claim', flush=True)
            tap(CLAIM, 2.5)
            state = classify(shot(f'r{rnd}_4b_retry'))
            print(f'    after claim retry: {state}', flush=True)
        if state == 'PANEL':
            tap(BACK, 1.0)
            print('    claim verified (popup closed, panel back)', flush=True)
        else:
            print(f'    ERROR: unexpected state after claim: {state}', flush=True)
            return 1

        if rnd < args.rounds and args.pause:
            time.sleep(args.pause)
    print('done', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
