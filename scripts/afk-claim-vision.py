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

Usage: python scripts/afk-claim-vision.py [--rounds N] [--pause S] [--dry-run]
Exit codes: 0 claim verified, 1 could not reach a claimable state, 2 adb error.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parent.parent
TMP = REPO / '.spectre' / 'shots'
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
    adb('shell', 'input', 'tap', str(xy[0]), str(xy[1]))
    time.sleep(wait)


def shot(name: str) -> Image.Image:
    path = TMP / f'{name}.png'
    with open(path, 'wb') as fh:
        p = subprocess.run([str(ADB), '-s', SERIAL, 'exec-out', 'screencap', '-p'],
                           stdout=fh, timeout=60)
    if p.returncode != 0:
        raise RuntimeError('screencap failed')
    return Image.open(path).convert('RGB')


def avg(img: Image.Image, xy: tuple[int, int], r: int = 9) -> tuple[int, int, int]:
    x, y = xy
    px = img.crop((x - r, y - r, x + r, y + r)).resize((1, 1), Image.Resampling.BILINEAR).getpixel((0, 0))
    return (int(px[0]), int(px[1]), int(px[2]))


def close_to(c: tuple[int, int, int], ref: tuple[int, int, int], tol: int) -> bool:
    return all(abs(a - b) <= tol for a, b in zip(c, ref))


def lum(c: tuple[int, int, int]) -> float:
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


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
    if lb < 100 and lbar > 172:
        return 'POPUP'
    if lb < 100 and abs(lb - lg) < 15:
        return 'WORLD'
    if lb < 100 and lb - lg < -8:
        return 'POPUP'
    chip = avg(img, (1390, 704))
    if chip[0] > 200 and chip[1] > 150 and chip[2] < 120:
        return 'PANEL'
    return 'UNKNOWN'


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--rounds', type=int, default=1)
    ap.add_argument('--pause', type=float, default=0)
    ap.add_argument('--pid', default=None, help='game pid (memory preflight)')
    ap.add_argument('--base', default=None, help='hot-heap base hex (memory preflight)')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    if args.pid and args.base and not args.dry_run:
        import struct
        addr = hex(int(args.base, 16) + 0xA578)
        out = REPO / '.spectre' / 'power.bin'
        p = subprocess.run([str(REPO / 'target/release/spectre.exe'), 'dump', args.pid, addr, '8',
                            '--adb', '--format', 'raw', '--output', str(out)],
                           cwd=REPO, capture_output=True, timeout=120)
        if p.returncode != 0 or not out.exists():
            print('    ERROR: team_power preflight could not read memory', flush=True)
            return 2
        power = struct.unpack('<q', out.read_bytes()[:8])[0]
        print(f'    preflight team_power = {power}', flush=True)
        if power <= 100_000:
            print('    ERROR: team_power implausible — wrong pid/heap base, refusing to tap', flush=True)
            return 2

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
            print('    ERROR: chest popup did not open', flush=True)
            return 1

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
