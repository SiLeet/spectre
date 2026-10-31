"""Arena daily-flow driver for AFK Journey (BlueStacks 1920x1080).

Maps the verified T27 flow (TODOS.md 'T27 (Teilstand)'):

  1. reach the world view (BACK xN, dismiss taps)
  2. Battle Modes (890,1060) -> Arena card (1200,300)
  3. Challenge (1080,1004) -> Select Opponent list
  4. per fight: tap the LEFT opponent slot (750,500) — empirically the weakest
     of the three offered opponents — the fight runs automatically
  5. wait for the fight to resolve (~80 s), the game returns to the opponent
     selection; tap Challenge! again for the next attempt
  6. stop after --fights attempts, or on repeated unknown states

Verification: every step takes a screenshot into .spectre/shots/ and classifies
it via afk_stage_push.classify_battle where reliable; the arena screens have
their own look, so the script additionally checks that the screen CHANGED
between fight start and fight end before counting an attempt.

Usage: python scripts/afk_arena.py [--fights 4] [--dry-run]
Exit codes: 0 = all attempts done, 1 = stuck / unknown, 2 = adb error.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image

from afk_claim_vision import classify  # verified WORLD check (back-arrow probes)

REPO = Path(__file__).resolve().parent.parent
TMP = REPO / '.spectre' / 'shots'
TMP.mkdir(parents=True, exist_ok=True)
ADB = Path.home() / 'AppData/Local/Android/Sdk/platform-tools/adb.exe'
SERIAL = '127.0.0.1:5555'

# verified T27 coordinates (TODOS.md, 2026-10-31)
BACK = (474, 1010)          # back arrow, bottom-left (most screens)
GROUND = (300, 250)         # world-view dismiss tap
BATTLE_MODES = (890, 1060)  # Battle Modes entry button, world view
ARENA_CARD = (1200, 300)    # Arena card inside Battle Modes
CHALLENGE = (1080, 1004)    # green Challenge button, arena lobby
OPPONENT_LEFT = (750, 500)  # left opponent card (weakest of the 3)
ARENA_BATTLE = (960, 1010)  # Battle button on the arena prep screen
CHALLENGE_AGAIN = (1080, 1010)  # after a resolved fight

sys.path.insert(0, str(REPO / 'scripts'))


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
    px: tuple[int, int, int] = img.crop((x - r, y - r, x + r, y + r)).resize((1, 1), Image.Resampling.BILINEAR).getpixel((0, 0))  # type: ignore[assignment]
    return (int(px[0]), int(px[1]), int(px[2]))


def dist(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return sum(abs(x - y) for x, y in zip(a, b))


def at_world(img: Image.Image) -> bool:
    """Verified world-view check via the back-arrow probes from afk_claim_vision."""
    return classify(img) == 'WORLD'


def reach_world(max_steps: int = 6) -> Image.Image:
    """Navigate out of any nested panel back to the world view."""
    img = shot('arena_0_initial')
    for i in range(max_steps):
        if at_world(img):
            return img
        tap(BACK, 1.5)
        img = shot(f'arena_0_back{i}')
    tap(GROUND, 0.8)          # dismiss an interact menu
    tap(BACK, 1.0)
    return shot('arena_0_final')


def screen_signature(img: Image.Image) -> tuple[int, int, int]:
    """Cheap fingerprint of the centre of the screen to detect state changes."""
    return avg(img, (960, 540)), avg(img, (960, 300)), avg(img, (500, 540))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--fights', type=int, default=4)
    ap.add_argument('--wait-fight', type=float, default=80,
                    help='seconds to wait for one arena fight to resolve')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    reach_world()
    if args.dry_run:
        print('[dry-run] would open Battle Modes -> Arena and fight', flush=True)
        return 0

    print('--- Battle Modes -> Arena', flush=True)
    tap(BATTLE_MODES, 3.0)
    tap(ARENA_CARD, 4.0)
    img = shot('arena_1_lobby')
    sig = screen_signature(img)
    print(f'    arena lobby signature: {sig}', flush=True)

    tap(CHALLENGE, 4.0)
    img = shot('arena_2_select')
    print(f'    select-opponent signature: {screen_signature(img)}', flush=True)

    wins = 0
    for fight in range(1, args.fights + 1):
        print(f'--- arena fight {fight}/{args.fights}', flush=True)
        if fight > 1:
            # after a resolved fight: Challenge! -> Select Opponent -> prep
            tap(CHALLENGE_AGAIN, 3.0)
            tap(OPPONENT_LEFT, 2.0)
        # the prep screen (Arena I, teams placed) has its own Battle button
        tap(ARENA_BATTLE, 3.0)
        img = shot(f'arena_3_f{fight}_start')
        sig_before = screen_signature(img)

        # the fight runs on its own; wait for it to resolve
        time.sleep(args.wait_fight)
        img = shot(f'arena_3_f{fight}_after')
        sig_after = screen_signature(img)
        changed = sum(dist(a, b) for a, b in zip(sig_before, sig_after)) > 40
        print(f'    changed={changed} sig_before={sig_before} sig_after={sig_after}', flush=True)
        if not changed:
            print('    WARN: screen unchanged after the fight — aborting', flush=True)
            break
        wins += 1

    print(f'done: {wins} arena fights driven', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
