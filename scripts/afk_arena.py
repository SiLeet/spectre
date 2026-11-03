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

NOTE: the single-fight path is the verified one (3 live runs). Chaining several
fights in one run needs the victory-card dismissal to line up, which is flaky —
the scheduler calls this script once per attempt instead.

Verification: every step takes a screenshot and classifies it with
arena_state() / the shared purchase-dialog detector (v.is_confirm_dialog);
the arena screens have their own look, so the script additionally checks
that the screen CHANGED between fight start and fight end before counting
an attempt. Reaching Battle Modes is v.open_battle_modes (classify-gated).

Usage: python scripts/afk_arena.py [--fights 4] [--dry-run]
Exit codes: 0 = all attempts done, 1 = stuck / unknown, 2 = adb error.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402


# verified T27 coordinates (TODOS.md, 2026-10-31)
BACK = (474, 1010)          # back arrow, bottom-left (most screens)
GROUND = (300, 250)         # world-view dismiss tap
BATTLE_MODES = (890, 1060)  # Battle Modes entry button, world view
ARENA_CARD = (1200, 300)    # Arena card inside Battle Modes
CHALLENGE = (1080, 1004)    # green Challenge button, arena lobby
OPPONENT_LEFT = (750, 500)  # left opponent card (weakest of the 3)
ARENA_BATTLE = (960, 1010)  # Battle button on the arena prep screen
CHALLENGE_AGAIN = (1080, 1010)  # after a resolved fight


def tap(xy: tuple[int, int], wait: float = 1.0) -> None:
    """v.tap (raises on an adb failure) with one retry. The old copy ignored
    the return code: a missed Challenge tap spun the advance loop to STUCK."""
    try:
        v.tap(xy, wait)
    except RuntimeError as exc:
        print(f'    WARN: {exc} — retrying once', flush=True)
        time.sleep(1.0)
        v.tap(xy, wait)


def avg(img: Image.Image, xy: tuple[int, int], r: int = 9) -> tuple[int, int, int]:
    x, y = xy
    px: tuple[int, int, int] = img.crop((x - r, y - r, x + r, y + r)).resize((1, 1), Image.Resampling.BILINEAR).getpixel((0, 0))  # type: ignore[assignment]
    return (int(px[0]), int(px[1]), int(px[2]))


def dist(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return sum(abs(x - y) for x, y in zip(a, b))


def screen_signature(img: Image.Image) -> tuple[int, int, int]:
    """Cheap fingerprint of the centre of the screen to detect state changes."""
    return avg(img, (960, 540)), avg(img, (960, 300)), avg(img, (500, 540))



def arena_state(img: Image.Image) -> str:
    """Classify the arena chain: RESULT card, PREP (Battle button) or SELECT."""
    card = avg(img, (960, 300))
    if sum(card) / 3 > 190:                 # bright victory/defeat card
        return 'RESULT'
    btn = avg(img, ARENA_BATTLE)
    if btn[1] > 120 and btn[1] > btn[0] + 20 and btn[1] > btn[2] + 20:
        return 'PREP'                       # green Battle button at the bottom
    return 'SELECT'


def advance_to_fight(tag: str, steps: int = 6) -> str:
    """Drive the arena chain to a running fight: dismiss results, pick the left
    (lowest-power) opponent, press Battle on the prep screen."""
    for i in range(steps):
        img = v.shot(f'{tag}_step{i}')
        if v.is_confirm_dialog(img):
            tap(v.CONFIRM_CANCEL, 1.5)      # CANCEL — never confirm a purchase
            return 'DIALOG'
        st = arena_state(img)
        print(f'    [{tag}] step {i}: {st}', flush=True)
        if st == 'RESULT':
            tap((480, 300), 1.5)            # dismiss the result card
        elif st == 'PREP':
            tap(ARENA_BATTLE, 3.0)
            return 'PREP'
        else:
            tap(OPPONENT_LEFT, 2.5)         # left card = lowest combat power
    return 'STUCK'


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--fights', type=int, default=1,
                    help='fights per run; the verified path is 1 — call the script N times for N attempts')
    ap.add_argument('--wait-fight', type=float, default=80,
                    help='seconds to wait for one arena fight to resolve')
    ap.add_argument('--dry-run', action='store_true',
                    help='no arena fight; reaching Battle Modes still taps (BACK/GROUND/menu)')
    ap.add_argument('--min-idle', type=float, default=0,
                    help='skip when the PC has been in use for less than this many seconds')
    args = ap.parse_args()

    if args.min_idle > 0:
        idle = v.idle_seconds()
        if idle is not None and idle < args.min_idle:
            print(f'    SKIP: PC is in use (idle {idle:.0f}s)', flush=True)
            return 5

    if not v.open_battle_modes():
        print('    ERROR: Battle Modes did not open', flush=True)
        return 1
    if args.dry_run:
        print('[dry-run] would open Arena and fight', flush=True)
        return 0

    print('--- Arena card -> lobby', flush=True)
    tap(ARENA_CARD, 4.0)
    img = v.shot('arena_1_lobby')
    lobby = v.lum(v.avg(img, (1080, 1004))) > 150 and v.lum(v.avg(img, (480, 270))) < 200
    if not lobby:
        print('    ERROR: arena lobby did not open', flush=True)
        return 1

    tap(CHALLENGE, 4.0)
    img = v.shot('arena_2_select')
    print(f'    select-opponent signature: {screen_signature(img)}', flush=True)

    wins = 0
    failed = False
    for fight in range(1, args.fights + 1):
        print(f'--- arena fight {fight}/{args.fights}', flush=True)
        if v.is_confirm_dialog(v.shot(f'arena_p{fight}_pre')):
            tap(v.CONFIRM_CANCEL, 1.5)   # CANCEL — never confirm a purchase
            print('    STOP: daily arena attempts exhausted (purchase dialog cancelled)', flush=True)
            return 0
        st = advance_to_fight(f'arena_f{fight}')
        if st == 'DIALOG':
            print('    STOP: purchase dialog during the fight chain (cancelled)', flush=True)
            return 0
        if st != 'PREP':
            print(f'    ERROR: could not reach a fight ({st}) — aborting', flush=True)
            failed = True
            break
        sig_before = screen_signature(v.shot(f'arena_{fight}_start'))
        time.sleep(args.wait_fight)
        img = v.shot(f'arena_{fight}_after')
        sig_after = screen_signature(img)
        changed = sum(dist(a, b) for a, b in zip(sig_before, sig_after)) > 40
        print(f'    changed={changed} {sig_before} -> {sig_after}', flush=True)
        if not changed:
            print('    WARN: screen unchanged after the fight — aborting', flush=True)
            failed = True
            break
        wins += 1

    print(f'done: {wins} arena fights driven', flush=True)
    # exit 1 when nothing was fought: afk-bot-watch.sh writes the once-per-day
    # arena marker on exit 0, so a failed run must not burn the day
    return 1 if failed and wins == 0 else 0


if __name__ == '__main__':
    sys.exit(main())
