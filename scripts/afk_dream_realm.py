"""Dream Realm daily driver for AFK Journey (BlueStacks 1920x1080).

Dream Realm is a TIMED boss fight (e.g. Necrodrakon, Elite Challenge) with 7
daily chances; every fight consumes one chance. Live-verified sequence
(2026-11-01):

  1. World view -> Battle Modes (890,1060) -> Dream Realm card (960,280)
  2. Boss page: green Battle button (~960,1020) with "Chances: N/7"
  3. (optional prep screen with its own Battle button) -> fight starts
  4. Fight runs a full ~90 s damage race (boss HP bar + countdown). DO NOT
     tap anything while it runs -- an earlier version tapped Back here and
     misread the running fight as a defeat.
  5. End state: a bright "BATTLE ENDED" results card ("Tap to close" at the
     bottom centre, orange top banner). Closing it returns to the boss page.
     A dim Victory-Rewards popup and/or a full-screen hero card may also
     appear and must be dismissed.

State detection uses colour probes only (no OCR; uiautomator fails on this
UI). Unknown states never trigger blind taps: while a fight may be running
the driver waits, otherwise it aborts.

Usage: python scripts/afk_dream_realm.py --fights N [--dry-run]
Exit codes: 0 done, 1 stuck, 2 adb error, 5 skipped (PC in use).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402

REPO = Path(__file__).resolve().parent.parent

BACK = (474, 1010)
BATTLE_MODES = (890, 1060)
DREAM_CARD = (960, 280)          # Dream Realm card in the Battle Modes menu
BOSS_TAP = (960, 1020)           # green Battle button on the boss page
PREP_TAP = (1280, 1010)          # green Battle button on the prep screen
                                 # NB: (960,1010) on prep is the SKIP button — never tap it
BATTLE_BTN_BOSS = (960, 1040)    # probe points for the two green Battle buttons
BATTLE_BTN_PREP = (1280, 1010)
CARD_CLOSE = (960, 1035)         # "Tap to close" strip on the BATTLE ENDED card
CARD_BANNER = (960, 90)          # orange banner of the BATTLE ENDED card
CORNER = (200, 270)              # dark surround probe
HERO_PROBE = (474, 1010)         # hero card covers even the back arrow
HERO_DISMISS = (100, 100)        # verified live: corner tap closes the hero card
DIM_DISMISS = (480, 300)

POLL = 5.0


def is_battle_ended(img) -> bool:
    """Bright results card with orange banner on a dark backdrop."""
    b = v.avg(img, CARD_BANNER)
    close = v.avg(img, CARD_CLOSE)
    corner = v.avg(img, CORNER)
    return b[0] > 160 and b[2] < 110 and v.lum(close) > 200 and v.lum(corner) < 90


def is_hero_card(img) -> bool:
    """Full-screen bright hero card (covers even the back-arrow corner)."""
    return (v.lum(v.avg(img, HERO_PROBE)) > 180
            and v.lum(v.avg(img, CORNER)) > 140
            and not is_battle_ended(img))


def is_dim_popup(img) -> bool:
    """Dimmed overlay (e.g. Victory Rewards popup)."""
    return v.lum(v.avg(img, CORNER)) < 25


def _green(c: tuple[int, int, int]) -> bool:
    # boss-page Battle button ~(109,154,100), prep Battle button ~(160,192,152);
    # the in-fight olive probes (129,143,88)/(167,178,96) must NOT match
    return c[1] > 130 and c[1] > c[0] + 25 and c[2] < 170


def is_boss_page(img) -> bool:
    """Boss page: green Battle button at the bottom centre."""
    return _green(v.avg(img, BATTLE_BTN_BOSS))


def is_prep(img) -> bool:
    """Prep screen: green Battle button on the RIGHT (1280,1010); the centre
    bottom is the SKIP button there, which must never be tapped."""
    return not is_boss_page(img) and _green(v.avg(img, BATTLE_BTN_PREP))


def is_ready(img) -> bool:
    """Boss page or prep screen: a green Battle button, no end-state card."""
    if is_battle_ended(img) or is_hero_card(img) or is_dim_popup(img):
        return False
    return is_boss_page(img) or is_prep(img)


def is_world(img) -> bool:
    return v.classify(img) == "WORLD"


def resolve_end_states(img, tag: str):
    """Dismiss any sequence of battle-ended card / dim popup / hero card.

    Returns the final screenshot once none of those states remain.
    """
    for i in range(8):
        if is_battle_ended(img):
            print(f'    {tag}: battle ended card -> tap to close', flush=True)
            v.tap(CARD_CLOSE, 3.0)
        elif is_dim_popup(img):
            print(f'    {tag}: dim popup -> dismiss', flush=True)
            v.tap(DIM_DISMISS, 2.5)
        elif is_hero_card(img):
            print(f'    {tag}: hero card -> corner dismiss', flush=True)
            v.tap(HERO_DISMISS, 2.5)
        else:
            return img
        img = v.shot(f'{tag}_{i}')
    return img


def back_to_ready(tag: str, attempts: int = 10) -> bool:
    """Get back to the boss page / prep screen from wherever we are.

    Never taps blindly: unknown frames are waited out (a fight may be
    running), and only recognised panels are dismissed.
    """
    unknown = 0
    for i in range(attempts):
        img = v.shot(f'{tag}_{i}')
        if is_ready(img):
            return True
        if is_battle_ended(img) or is_dim_popup(img) or is_hero_card(img):
            img = resolve_end_states(img, f'{tag}_end{i}')
            if is_ready(img):
                return True
            continue
        if is_world(img):
            v.tap(BATTLE_MODES, 3.0)
            v.tap(DREAM_CARD, 4.0)
            unknown = 0
            continue
        unknown += 1
        if unknown >= 4:
            print(f'    {tag}: giving up, {unknown} unrecognised frames', flush=True)
            return False
        time.sleep(3)
    return is_ready(v.shot(f'{tag}_final'))


def wait_for_fight_end(tag: str, max_wait: float):
    """Poll while the timed fight runs. Returns the last screenshot if an
    end state appears, else None on timeout."""
    deadline = time.time() + max_wait
    n = 0
    img = v.shot(f'{tag}_w0')
    while time.time() < deadline:
        if is_battle_ended(img) or is_dim_popup(img) or is_hero_card(img):
            return img
        time.sleep(POLL)
        n += 1
        img = v.shot(f'{tag}_w{n}')
    print(f'    {tag}: fight did not end within {max_wait:.0f}s', flush=True)
    return None


def reach_world(tag: str) -> bool:
    for i in range(6):
        img = v.shot(f'{tag}_{i}')
        if v.classify(img) == 'WORLD':
            return True
        img = resolve_end_states(img, f'{tag}_end{i}')
        if v.classify(img) == 'WORLD':
            return True
        v.tap(v.BACK, 1.5)
    return v.classify(v.shot(f'{tag}_final')) == 'WORLD'


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--fights', type=int, default=7)
    ap.add_argument('--wait-fight', type=float, default=150,
                    help='max seconds to wait for one timed fight to end')
    ap.add_argument('--pid', default=None)
    ap.add_argument('--base', default=None)
    ap.add_argument('--min-idle', type=float, default=0)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    if args.min_idle > 0:
        idle = v.idle_seconds()
        if idle is not None and idle < args.min_idle:
            print(f'    SKIP: PC is in use (idle {idle:.0f}s)', flush=True)
            return 5
        print(f'    idle check ok ({idle:.0f}s)' if idle is not None else '    idle unknown', flush=True)

    if args.pid and args.base:
        status, power = v.memory_preflight(args.pid, args.base)
        if status == 'fail':
            print('    ERROR: memory preflight failed', flush=True)
            return 2
        if status == 'stale':
            print(f'    WARN: team_power offset stale after restart (read {power})', flush=True)
        else:
            print(f'    preflight team_power = {power}', flush=True)

    if args.dry_run:
        print('    dry-run: state probes verified, no actions taken', flush=True)
        return 0

    img = v.shot('dr_start')
    if is_ready(img):
        print('--- already inside Dream Realm', flush=True)
    else:
        if not reach_world('dr_world'):
            print('    ERROR: could not reach the world view', flush=True)
            return 1

        print('--- Battle Modes -> Dream Realm', flush=True)
        v.tap(BATTLE_MODES, 3.0)
        v.tap(DREAM_CARD, 4.0)
        if not back_to_ready('dr_enter'):
            print('    ERROR: Dream Realm boss page not reachable', flush=True)
            return 1

    fights = 0
    for fight in range(1, args.fights + 1):
        print(f'--- dream realm fight {fight}/{args.fights}', flush=True)
        if not back_to_ready(f'dr_pre{fight}'):
            print('    ERROR: Dream Realm boss page not reachable', flush=True)
            return 1

        # Start the fight: the boss page opens a prep screen whose Battle
        # button sits on the RIGHT (1280,1010); tapping (960,1010) there is
        # the SKIP button and must never happen. Unknown frames (loading
        # transitions) are waited out, never tapped.
        started = False
        for attempt in range(3):
            img = v.shot(f'dr_f{fight}_pre{attempt}')
            if is_prep(img):
                print(f'    fight {fight}: prep screen -> Battle', flush=True)
                v.tap(PREP_TAP, 4.0)
            elif is_boss_page(img):
                v.tap(BOSS_TAP, 4.0)
            else:
                time.sleep(3)
                img = v.shot(f'dr_f{fight}_prewait{attempt}')
                if is_prep(img):
                    v.tap(PREP_TAP, 4.0)
                elif is_boss_page(img):
                    v.tap(BOSS_TAP, 4.0)
                else:
                    continue
            img = v.shot(f'dr_f{fight}_after_tap{attempt}')
            if is_ready(img):
                continue        # a prep screen just opened; next iteration taps Battle
            img = resolve_end_states(img, f'dr_f{fight}_quick{attempt}')
            if not is_ready(img):
                started = True              # fight (or an end state) is underway
                break
        if not started:
            print('    ERROR: fight did not start after 3 battle taps', flush=True)
            return 1

        end_img = wait_for_fight_end(f'dr_f{fight}', args.wait_fight)
        if end_img is None:
            return 1
        fights += 1
        print(f'    fight {fight}: completed (chance consumed)', flush=True)
        final = resolve_end_states(end_img, f'dr_f{fight}_resolve')
        if not is_ready(final) and not back_to_ready(f'dr_post{fight}'):
            print('    ERROR: boss page not restored after fight', flush=True)
            return 1

    # leave the Dream Realm cleanly
    if fights > 0:
        img = v.shot('dr_exit')
        if is_ready(img):
            v.tap(BACK, 2.0)
    img = v.shot('dr_final')
    print(f'    done: {fights} fight(s) completed; final state: {v.classify(img)}', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
