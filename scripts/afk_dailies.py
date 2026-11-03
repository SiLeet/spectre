"""Full daily routine for AFK Journey, state-checked like the other drivers.

Chains the verified flows:
  1. AFK idle-chest claim        (afk_claim_vision.claim_round)
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

MENU = (1880, 1030)
QUESTS_ICON = (1140, 610)
MAIL_ICON = (840, 750)
QUICK_CLAIM = (1360, 850)
READ_ALL = (1080, 1010)
DAILY_TAB = (800, 934)
GUILD_TAB = (1020, 934)
LUCKY_FLIP_TAB = (910, 1034)
GROWTH_TAB = (1010, 1034)
DISMISS = (480, 300)


def is_dimmed(img) -> bool:
    return v.lum(v.avg(img, (200, 270))) < 25    # dimmed "Rewards Obtained" card


def dismiss_popup(tag: str) -> None:
    """Close the dimmed rewards card: tap, verify it is gone, one retry."""
    for i in range(2):
        v.tap(DISMISS, 2.0)
        if not is_dimmed(v.shot(f'{tag}_dismiss{i}')):
            return
    print(f'    WARN: [{tag}] rewards card still dimmed after 2 dismiss taps', flush=True)


def open_menu() -> bool:
    """Open the main menu. 5 attempts (3 MENU taps failed live on 10-31); a
    popup in the way gets BACK instead of another MENU tap."""
    for attempt in range(5):
        img = v.shot(f'dl_menu_{attempt}')
        # menu probes: the light back arrow and the gear/settings circle are
        # both bright only while the menu panel is open (world: L 64 / 31)
        if v.lum(v.avg(img, (480, 1010))) > 150 and v.lum(v.avg(img, (1375, 1028))) > 150:
            return True
        v.tap(v.BACK if v.classify(img) == 'POPUP' else MENU, 3.0)
    return False


def reopen_quests() -> bool:
    """After a tab that did not verify: back out of the unknown screen and
    re-open the quest panel instead of tapping the next tab blind."""
    v.tap(v.BACK, 1.5)
    if not open_menu():
        return False
    v.tap(QUESTS_ICON, 3.5)
    return is_quests_panel(v.shot('dl_questpanel_re'))


QUEST_TABS = (('homestead', None), ('daily', DAILY_TAB),
              ('lucky', LUCKY_FLIP_TAB),    # Lucky Flip: free daily flip claims
              ('growth', GROWTH_TAB),       # Growth Trials: milestone claims
              ('guild', GUILD_TAB))         # the guild tab has to be selected explicitly


def claim_quest_tabs() -> bool:
    """Quick Claim on every quest tab; False when the panel is lost."""
    for i, (name, tab) in enumerate(QUEST_TABS):
        if tab:
            v.tap(tab, 2.5)
        if quick_claim_tab(name) is None and i + 1 < len(QUEST_TABS) and not reopen_quests():
            print('    ERROR: quest panel lost after a failed tab', flush=True)
            return False
    return True


def quick_claim_tab(name: str) -> bool | None:
    """True claimed, False nothing claimable, None = tab not verified (the
    screen is unknown; the caller must not tap the next tab on it)."""
    img = v.shot(f'dl_tab_{name}')
    if not is_quests_panel(img):
        print(f'    [{name}] tab did not open', flush=True)
        return None
    v.tap(QUICK_CLAIM, 3.0)
    img = v.shot(f'dl_qc_{name}')
    got = is_dimmed(img)
    if got:
        print(f'    [{name}] rewards claimed', flush=True)
        dismiss_popup(f'dl_qc_{name}')
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


def run_dailies(min_idle: float, pid: str | None = None, base: str | None = None) -> int:
    if min_idle > 0:
        idle = v.idle_seconds()
        if idle is not None and idle < min_idle:
            print(f'    SKIP: PC is in use (idle {idle:.0f}s)', flush=True)
            return 5
        print(f'    idle check ok ({idle:.0f}s)' if idle is not None else '    idle unknown', flush=True)

    status, power = v.memory_preflight(pid, base) if pid and base else ('skip', None)
    if status == 'fail':
        print('    ERROR: memory preflight failed', flush=True)
        return 2
    if status == 'ok':
        print(f'    preflight team_power = {power}', flush=True)
    elif status == 'skip':
        print('    no pid/base given — memory preflight skipped', flush=True)
    else:   # 'disabled' — memory_preflight returns only ok/disabled/fail
        print(f'    team_power guard disabled (offset stale, read {power})', flush=True)

    # 1. AFK chest claim (existing verified sequence)
    print('--- AFK chest claim', flush=True)
    if not afk_chest_claim():
        return 1

    # 2. Quests: menu -> Quests -> each tab -> Quick Claim
    print('--- Quests', flush=True)
    img = v.shot('dl_pre_quests')
    if is_dimmed(img):                      # leftover dim popup
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
    if not claim_quest_tabs():
        return 1
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
    if is_dimmed(img):
        print('    [mail] rewards claimed', flush=True)
        dismiss_popup('dl_mail')
    else:
        print('    [mail] nothing new', flush=True)
    v.tap(v.BACK, 1.5)

    img = v.shot('dl_final')
    print(f'    final state: {v.classify(img)}', flush=True)
    return 0


def afk_chest_claim() -> bool:
    """The shared, verified chest flow (afk_claim_vision.claim_round). True
    when the claim landed or nothing was claimable yet; False on an unknown /
    unreachable screen or a claim that did not confirm (the old local copy
    reported True there)."""
    rc = v.claim_round('dl_afk')
    if rc == 0:
        print('    chest claim verified', flush=True)
    return rc in (0, 4)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--pid', default=None, help='game pid (memory preflight; skipped if absent)')
    ap.add_argument('--base', default=None, help='hot-heap base hex (memory preflight)')
    ap.add_argument('--min-idle', type=float, default=0)
    args = ap.parse_args()
    sys.exit(run_dailies(args.min_idle, args.pid, args.base))
