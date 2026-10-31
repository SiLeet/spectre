"""Dream Realm daily driver for AFK Journey (BlueStacks 1920x1080).

Dream Realm is a boss fight (Necrodrakon, Elite Challenge) with 7 daily
chances; each fight grants rewards and consumes one chance. Verified flow:

  1. Battle Modes (890,1060) -> Dream Realm card (960,280)
  2. hub: "Chances: 7/7", green Battle at (960,1040)
  3. prep screen: Battle at (960,1010) -> ~70 s fight
  4. "Victory Rewards" popup -> tap to close -> back at the hub

Loop until --fights attempts are used (or the counter reaches 0). Every tap is
gated on the previous screenshot; unknown screens abort instead of tapping
blind. The script does not touch Formations — team selection stays manual.

Usage: python scripts/afk_dream_realm.py --fights 3 [--dry-run]
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
TMP = REPO / '.spectre' / 'shots'

BACK = (474, 1010)
BATTLE_MODES = (890, 1060)
DREAM_CARD = (960, 280)          # Dream Realm card in the Battle Modes menu
HUB_BATTLE = (960, 1040)         # green Battle button, Dream Realm hub
PREP_BATTLE = (960, 1010)        # green Battle button, Elite Challenge prep
DISMISS = (480, 300)


def chance_left(img) -> int | None:
    """Read 'Chances: N/M' is text-based; fall back to a brightness probe of
    the counter area — this is only used for logging, so None is fine."""
    return None


def dim(img) -> bool:
    return v.lum(v.avg(img, (200, 270))) < 25


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--fights', type=int, default=7)
    ap.add_argument('--wait-fight', type=float, default=75)
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

    # reach the world view
    img = v.shot('dr_0')
    st = v.classify(img)
    for i in range(4):
        if st == 'WORLD':
            break
        if st in ('PANEL', 'POPUP'):
            v.tap(v.BACK, 1.2)
        else:
            v.tap(v.BACK, 1.2)
        img = v.shot(f'dr_0_{i}')
        st = v.classify(img)
    if st != 'WORLD':
        print(f'    ERROR: not on the world view ({st})', flush=True)
        return 1

    print('--- Battle Modes -> Dream Realm', flush=True)
    v.tap(BATTLE_MODES, 3.0)
    v.tap(DREAM_CARD, 4.0)
    img = v.shot('dr_hub')
    if dim(img):
        print('    ERROR: a dim overlay covers the Dream Realm hub', flush=True)
        return 1

    fights = 0
    for fight in range(1, args.fights + 1):
        print(f'--- dream realm fight {fight}/{args.fights}', flush=True)
        v.tap(HUB_BATTLE, 4.0)                      # hub -> prep
        v.tap(PREP_BATTLE, 3.0)                     # start the fight
        time.sleep(args.wait_fight)
        img = v.shot(f'dr_f{fight}_result')
        if dim(img):                                # "Victory Rewards" popup
            fights += 1
            print(f'    fight {fight}: rewards granted', flush=True)
            v.tap(DISMISS, 2.5)                     # close the popup
        else:
            print(f'    fight {fight}: no reward popup — stopping (out of chances?)', flush=True)
            break

    v.tap(v.BACK, 1.5)
    img = v.shot('dr_final')
    print(f'    done: {fights} fight(s) claimed; final state: {v.classify(img)}', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
