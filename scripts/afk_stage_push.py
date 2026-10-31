"""AFK stage push: fight stage after stage, verified by screen state.

Each victory raises AFK Progress by one stage and permanently increases the AFK
income rate. Battles are free (no attempts, no resources), they just take ~90 s
of what looks like auto-combat, so this loop is safe to run while idle.

Flow: PREP/VICTORY (green Battle button at (1280,1000)) -> BATTLE -> VICTORY ->
repeat. Stops on DEFEAT (stage too hard) or when the requested count is reached,
and always leaves the game on the result screen (no stray taps).

Usage: python scripts/afk_stage_push.py [--battles N] [--max-battle-seconds 150]
Exit codes: 0 finished/pushed, 1 stuck (unknown screen), 2 memory preflight,
5 skipped (PC in use).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
BATTLE_BTN = (1280, 1000)
AFK_PROGRESS = (60, 1036)


def classify_battle(img) -> str:
    dark = v.lum(v.avg(img, (960, 300)))
    header = v.lum(v.avg(img, (960, 40)))
    arena = v.avg(img, (960, 400))
    card = v.lum(v.avg(img, (960, 300)))
    search = v.lum(v.avg(img, (960, 124)))
    if search > 120 and dark < 60:
        # BlueStacks launcher: bright search field on a dark background — the
        # game crashed or was closed. Without this, a crash looked like a
        # never-ending LOADING screen.
        return 'LAUNCHER'
    if dark < 45 and header < 45:
        return 'LOADING'
    if arena[2] > arena[0] + 50 and arena[2] > 150:
        return 'BATTLE'
    if card > 200:
        return 'RESULT'
    if v.avg(img, BATTLE_BTN)[1] > 150:
        return 'PREP'
    return 'UNKNOWN'


def wait_for(states: set[str], timeout: float, tag: str) -> tuple[str, object]:
    t0 = time.time()
    last = 'UNKNOWN'
    while time.time() - t0 < timeout:
        img = v.shot(tag)
        last = classify_battle(img)
        if last in states:
            return last, img
        time.sleep(2.0)
    return last, None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--battles', type=int, default=1)
    ap.add_argument('--max-battle-seconds', type=float, default=150)
    ap.add_argument('--pid', default=None)
    ap.add_argument('--base', default=None)
    ap.add_argument('--min-idle', type=float, default=0)
    args = ap.parse_args()

    if args.min_idle > 0:
        idle = v.idle_seconds()
        if idle is not None and idle < args.min_idle:
            print(f'    SKIP: PC is in use (idle {idle:.0f}s)', flush=True)
            return 5

    if args.pid and args.base:
        status, power = v.memory_preflight(args.pid, args.base)
        if status == 'fail':
            print('    ERROR: memory preflight failed', flush=True)
            return 2
        if status == 'stale':
            print(f'    WARN: team_power offset stale after restart (read {power})', flush=True)
        else:
            print(f'    preflight team_power = {power}', flush=True)

    img = v.shot('sp_0_initial')
    st = classify_battle(img)
    print(f'    initial battle screen state: {st}', flush=True)

    if st not in ('PREP', 'RESULT'):
        # enter the stage screen through the AFK panel
        for _ in range(3):
            if st in ('PREP', 'RESULT'):
                break
            if st in ('BATTLE', 'LOADING'):
                st, _ = wait_for({'PREP', 'RESULT'}, args.max_battle_seconds, 'sp_wait')
                continue
            v.tap(v.BACK, 1.2)
            v.tap(AFK_PROGRESS, 3.0)
            v.tap((960, 910), 4.0)          # "Battle" in the AFK panel
            st, _ = wait_for({'PREP', 'RESULT', 'BATTLE'}, 30, 'sp_enter')
            print(f'    after entering: {st}', flush=True)
    if st == 'BATTLE':
        st, _ = wait_for({'PREP', 'RESULT'}, args.max_battle_seconds, 'sp_wait2')
    if st == 'LAUNCHER':
        print('    ERROR: game crashed / not running (BlueStacks launcher) — restart the game', flush=True)
        return 3
    if st not in ('PREP', 'RESULT'):
        print(f'    ERROR: not on a battle screen ({st})', flush=True)
        return 1

    wins = 0
    for i in range(1, args.battles + 1):
        v.tap(BATTLE_BTN, 3.0)
        st, _ = wait_for({'BATTLE', 'RESULT'}, 25, f'sp_start_{i}')
        print(f'    battle {i}: started ({st})', flush=True)
        if st == 'BATTLE':
            st, _ = wait_for({'RESULT', 'PREP'}, args.max_battle_seconds, f'sp_end_{i}')
        if st == 'RESULT':
            wins += 1
            print(f'    battle {i}: VICTORY (AFK progress +1)', flush=True)
        else:
            # neither result card nor prep after a battle: likely defeat or stall
            print(f'    battle {i}: no victory screen ({st}) — likely DEFEAT, stopping', flush=True)
            break
        time.sleep(1.5)

    print(f'    pushed {wins}/{args.battles} stage(s); game left on the result screen', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
