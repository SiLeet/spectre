"""Full daily routine for AFK Journey, state-checked like the other drivers.

Chains the verified flows:
  1. AFK idle-chest claim        (reuse of the chest tap sequence)
  2. Main menu -> Quests -> every tab -> Quick Claim
  3. Main menu -> Mail -> Read All

Every tap is gated on the previous screenshot; unknown screens abort instead of
tapping blind. Run through scripts/afk-bot-watch.sh so pid/heap-base are fresh,
or directly: python scripts/afk_dailies.py --pid <pid> --base <base>

Exit codes: 0 done, 1 a screen never appeared, 2 memory preflight, 5 skipped
(PC in use).
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

MENU = (1880, 1030)
QUESTS_ICON = (1140, 610)
MAIL_ICON = (840, 750)
QUICK_CLAIM = (1360, 850)
READ_ALL = (1080, 1010)
DAILY_TAB = (800, 934)
GUILD_TAB = (1020, 934)
DISMISS = (480, 300)


def dismiss_popup() -> None:
    v.tap(DISMISS, 2.0)


def open_menu() -> bool:
    for attempt in range(3):
        img = v.shot(f'dl_menu_{attempt}')
        # menu probes: the light back arrow and the gear/settings circle are
        # both bright only while the menu panel is open (world: L 64 / 31)
        if v.lum(v.avg(img, (480, 1010))) > 150 and v.lum(v.avg(img, (1375, 1028))) > 150:
            return True
        v.tap(MENU, 3.0)
    return False


def quick_claim_tab(name: str) -> bool:
    img = v.shot(f'dl_tab_{name}')
    if not is_quests_panel(img):
        print(f'    [{name}] tab did not open', flush=True)
        return False
    v.tap(QUICK_CLAIM, 3.0)
    img = v.shot(f'dl_qc_{name}')
    got = v.lum(v.avg(img, (200, 270))) < 25   # dimmed "Rewards Obtained"
    if got:
        print(f'    [{name}] rewards claimed', flush=True)
        dismiss_popup()
    else:
        print(f'    [{name}] nothing claimable', flush=True)
    return got


def is_quests_panel(img) -> bool:
    """The quest panel: bright title top-left area, dark reddish edges."""
    # the panel title sits top-left at (500,90); (960,100) is artwork and dark
    return (v.lum(v.avg(img, (500, 90))) > 190
            and v.lum(v.avg(img, (200, 270))) < 100
            and v.lum(v.avg(img, (1750, 270))) < 100)


def is_mail(img) -> bool:
    # "Mail" title glyph hits (560,90) exactly (L~196); neighbours are dim
    return v.lum(v.avg(img, (560, 90))) > 180 and v.lum(v.avg(img, (500, 90))) < 130


def run_dailies(min_idle: float) -> int:
    if min_idle > 0:
        idle = v.idle_seconds()
        if idle is not None and idle < min_idle:
            print(f'    SKIP: PC is in use (idle {idle:.0f}s)', flush=True)
            return 5
        print(f'    idle check ok ({idle:.0f}s)' if idle is not None else '    idle unknown', flush=True)

    status, power = v.memory_preflight(ARGS.pid, ARGS.base) if ARGS.pid and ARGS.base else ('skip', None)
    if status == 'fail':
        print('    ERROR: memory preflight failed', flush=True)
        return 2
    if status == 'ok':
        print(f'    preflight team_power = {power}', flush=True)
    elif status == 'skip':
        print('    no pid/base given — memory preflight skipped', flush=True)
    else:
        print(f'    WARN: team_power offset stale (read {power})', flush=True)

    # 1. AFK chest claim (existing verified sequence)
    print('--- AFK chest claim', flush=True)
    if not afk_chest_claim():
        return 1

    # 2. Quests: menu -> Quests -> each tab -> Quick Claim
    print('--- Quests', flush=True)
    img = v.shot('dl_pre_quests')
    if v.lum(v.avg(img, (200, 270))) < 25:  # leftover dim popup
        v.tap(DISMISS, 2.0)
    v.tap(v.BACK, 1.2)                      # make sure we are on the world view
    if not open_menu():
        print('    ERROR: main menu did not open', flush=True)
        return 1
    v.tap(QUESTS_ICON, 3.5)
    img = v.shot('dl_questpanel')
    if not is_quests_panel(img):
        print('    ERROR: quest panel did not open', flush=True)
        return 1
    quick_claim_tab('homestead')
    v.tap(DAILY_TAB, 2.5)
    quick_claim_tab('daily')
    v.tap(GUILD_TAB, 2.5)          # the guild tab has to be selected explicitly
    quick_claim_tab('guild')
    v.tap(v.BACK, 1.5)

    # 3. Mail: menu -> Mail -> Read All
    print('--- Mail', flush=True)
    if not open_menu():
        print('    ERROR: main menu did not open', flush=True)
        return 1
    v.tap(MAIL_ICON, 3.5)
    img = v.shot('dl_mail')
    if not is_mail(img):
        print('    ERROR: mail did not open', flush=True)
        return 1
    v.tap(READ_ALL, 4.0)
    img = v.shot('dl_readall')
    if v.lum(v.avg(img, (200, 270))) < 25:
        print('    [mail] rewards claimed', flush=True)
        dismiss_popup()
    else:
        print('    [mail] nothing new', flush=True)
    v.tap(v.BACK, 1.5)

    img = v.shot('dl_final')
    print(f'    final state: {v.classify(img)}', flush=True)
    return 0


def afk_chest_claim() -> bool:
    """The verified chest tap sequence from afk_claim_vision, condensed."""
    img = v.shot('dl_afk_0')
    st = v.classify(img)
    if st == 'WORLD':
        v.tap((300, 250), 0.8)
        v.tap((60, 1036), 3.0)
        st = v.classify(v.shot('dl_afk_1'))
    if st == 'POPUP':
        v.tap(v.BACK, 1.2)
        st = v.classify(v.shot('dl_afk_1b'))
    if st == 'UNKNOWN':
        print('    ERROR: unknown screen — refusing to tap blind', flush=True)
        return False
    if st != 'PANEL':
        v.tap(v.BACK, 1.2)
        v.tap(v.BACK, 1.2)
        v.tap((300, 250), 0.8)
        v.tap((60, 1036), 3.0)
        st = v.classify(v.shot('dl_afk_2'))
    if st != 'PANEL':
        print('    ERROR: could not reach the AFK panel', flush=True)
        return False
    v.tap((975, 760), 2.2)
    st = v.classify(v.shot('dl_afk_3'))
    if st != 'POPUP':
        v.tap((975, 760), 2.5)
        st = v.classify(v.shot('dl_afk_3b'))
    if st != 'POPUP':
        print('    SKIP: chest empty (accrual too small)', flush=True)
        v.tap(v.BACK, 1.2)      # normalize: leave the AFK panel
        return True
    v.tap((960, 602), 2.5)
    st = v.classify(v.shot('dl_afk_4'))
    ok = st == 'PANEL'
    print(f'    chest claim {"verified" if ok else "state " + st}', flush=True)
    if st == 'PANEL':
        v.tap(v.BACK, 1.2)      # normalize: leave the panel
    return True


ARGS = None

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--pid', required=True)
    ap.add_argument('--base', required=True)
    ap.add_argument('--min-idle', type=float, default=0)
    ARGS = ap.parse_args()
    sys.exit(run_dailies(ARGS.min_idle))
