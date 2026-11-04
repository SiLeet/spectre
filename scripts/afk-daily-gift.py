"""Daily Journey's Gift claim, state-checked like the AFK chest driver.

Flow: open the Login Rewards panel, tap every row whose badge is green
(G-R > 40 at x=720 — claimed rows AND today's claimable row; future days are
grey and are never tapped, which keeps us away from the purchase-bearing event
tabs), and dismiss the "Rewards Obtained" popup after each successful claim.
Every tap is gated on the previous screenshot, so a mis-tap cannot cascade.

Run via scripts/afk-bot-watch.sh --daily or directly:
    python scripts/afk-daily-gift.py --pid 7529 --base 0x...
Exit codes: 0 claimed or nothing to claim, 1 could not reach the panel,
2 memory preflight failed, 3 WARN: Login Rewards entry not found (already
claimed today, event gone, or the camera pan missed it - not marked done),
5 skipped (PC in use).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402  (tap/shot/avg/lum/idle_seconds helpers)
import afk_memory  # noqa: E402

LOGIN_REWARDS = (1804, 662)
ROW_X = 890
ROW_YS = [260, 360, 480, 580, 710, 780, 880]
BADGE_X = 720


def is_events_panel(img) -> bool:
    """Events panel: bright title area, light back arrow, and dark reddish side
    edges (the panel covers the world; the AFK panel has a dark top-left title
    area instead, the world is bright)."""
    title = v.avg(img, (960, 100))
    back = v.avg(img, v.BACK)
    left = v.avg(img, (200, 270))
    right = v.avg(img, (1750, 270))
    return (v.lum(title) > 175 and v.lum(back) > 150
            and v.lum(left) < 100 and v.lum(right) < 100)


def is_dimmed(img) -> bool:
    return v.lum(v.avg(img, (200, 270))) < 25


def claim_signal(img) -> str | None:
    """Which tell says 'Rewards Obtained' is up, or None. The single dim probe
    (L<25) was never seen true on a capture and neighbours sit at L 59-60,
    so the classifier's POPUP verdict backs it up."""
    if is_dimmed(img):
        return 'dimmed'
    if v.classify(img) == 'POPUP':
        return 'classify POPUP'
    return None


def is_events_tooltip(img) -> bool:
    """An item-info tooltip covers the title area while the bottom tab bar and
    the panel edges stay visible."""
    title = v.avg(img, (960, 100))
    tabbar = v.avg(img, (620, 1010))
    return v.lum(title) < 120 and v.lum(tabbar) > 90


def badge_is_green(img, y: int) -> bool:
    c = v.avg(img, (BADGE_X, y))
    return c[1] - c[0] > 40 and c[1] > 100


def login_btn_visible(img) -> bool:
    """The Login Rewards entry floats in the world, so it moves with the camera."""
    c = v.avg(img, (1804, 662))
    return c[0] > 200 and c[2] < 120 and c[0] - c[2] > 80


def wait_events_panel(tag: str, tries: int = 3):
    """The panel animates open: up to `tries` shots ~1 s apart. Frame or None."""
    for i in range(tries):
        img = v.shot(f'{tag}_{i}' if i else tag)
        if is_events_panel(img):
            return img
        time.sleep(1.0)
    return None


def find_login_button(max_tries: int = 8) -> bool:
    """Pan the camera until the Login Rewards entry is on screen. Swipes start
    on open grass so they never select a building (which opens an Interact
    menu and blocks the pan)."""
    for i in range(max_tries):
        if login_btn_visible(v.shot(f'dg_cam_{i}')):
            return True
        # alternate pan directions with growing distance
        dx, dy = [(700, 0), (-700, 0), (0, 350), (0, -350),
                  (1300, 0), (-1300, 0), (0, 700), (0, -700)][i]
        # keep the end point on screen (dx up to 1300 sent x to -900); the
        # origin stays on the verified open-grass spot (400,700)
        v.swipe(400, 700, min(max(400 - dx, 0), 1919), min(max(700 - dy, 0), 1079), 500, 1.2)
    return login_btn_visible(v.shot('dg_cam_final'))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--pid', default=None)
    ap.add_argument('--base', default=None)
    ap.add_argument('--min-idle', type=float, default=0)
    args = ap.parse_args()

    if args.min_idle > 0:
        idle = v.idle_seconds()
        if idle is not None and idle < args.min_idle:
            print(f'    SKIP: PC is in use (idle {idle:.0f}s < {args.min_idle:.0f}s)', flush=True)
            return 5
        print(f'    idle check ok ({idle:.0f}s)' if idle is not None else '    idle unknown', flush=True)

    if args.pid and args.base:
        status, power = afk_memory.power(args.pid, args.base)
        if status == 'fail':
            print('    ERROR: team_power preflight failed', flush=True)
            return 2
        if status == 'disabled':
            print(f'    team_power guard disabled (offset stale, read {power})', flush=True)
        else:
            print(f'    preflight team_power = {power}', flush=True)

    # leave whatever state we are in: dismiss popups/tooltips, close other panels,
    # but never close the events panel if it is already open
    for attempt in range(4):
        img = v.shot(f'dg_{attempt}_init')
        if is_dimmed(img):
            print('    reward popup still open — dismissing', flush=True)
            v.tap((700, 500), 1.5)
            continue
        if is_events_panel(img):
            break
        if is_events_tooltip(img):
            print('    item tooltip open — dismissing', flush=True)
            v.tap((1500, 600), 1.2)
            continue
        st = v.classify(img)
        if st in ('PANEL', 'POPUP'):
            v.tap(v.BACK, 1.2)
            continue
        break  # world (or unknown) -> open the events panel next

    if not find_login_button():
        # The Login Rewards entry only floats in the world while a claim is
        # available; once the daily reward is taken it disappears (verified:
        # same camera position, button gone after the Day-3 claim).
        # Not 0: watch.sh marks the day done on 0, which masked a missed pan.
        print('    WARN: no Login Rewards entry — already claimed today, event gone, '
              'or the pan missed it', flush=True)
        return 3
    v.tap(LOGIN_REWARDS, 3.5)
    img = wait_events_panel('dg_panel')
    if img is None and login_btn_visible(v.shot('dg_entry_retry')):
        # live 10-31: the entry tap opened nothing (dg_panel was the world)
        print('    panel did not open — re-tapping the entry once', flush=True)
        v.tap(LOGIN_REWARDS, 3.5)
        img = wait_events_panel('dg_panel_retry')
    if img is None:
        print('    ERROR: Login Rewards panel did not open', flush=True)
        return 1
    print('    events panel open', flush=True)

    claimed = []
    closed = False                           # T83: closing BACK already sent in a batch
    for y in ROW_YS:
        img = v.shot(f'dg_row_{y}')
        if not is_events_panel(img):
            if is_events_tooltip(img):
                v.tap((1500, 600), 1.2)
                img = v.shot(f'dg_row_{y}_rec')
                if not is_events_panel(img):
                    print('    panel not visible — stopping', flush=True)
                    break
            else:
                print('    panel closed unexpectedly — stopping', flush=True)
                break
        if not badge_is_green(img, y):
            continue
        v.tap((ROW_X, y), 1.6)
        img = v.shot(f'dg_after_{y}')
        sig = claim_signal(img)
        if sig is None and not is_events_tooltip(img):
            time.sleep(1.0)                  # popup animation: one re-shot before judging
            img = v.shot(f'dg_after_{y}b')
            sig = claim_signal(img)
        if sig:
            print(f'    claimed row y={y} (Rewards Obtained, {sig})', flush=True)
            claimed.append(y)
            v.tap((700, 500), 2.0)          # dismiss the reward popup
            img = v.shot(f'dg_dismiss_{y}')
            if is_dimmed(img):
                # second dimmed layer: dismiss again + the closing BACK, nothing read
                # between (gate shot above, dg_back shot below) -> one adb round trip
                # LIVE: batched dismiss+BACK not yet run on device
                v.tap_seq([(700, 500, 2.0), (*v.BACK, 1.5)], tolerate=False)
                closed = True
            break                            # one daily claim is all there is
        if is_events_tooltip(img):
            # claimed row: opens the item info instead — dismiss and continue
            v.tap((1500, 600), 1.2)
            print(f'    row y={y}: item info (already claimed), dismissed', flush=True)
            continue
        if not is_events_panel(img):
            # unknown overlay: BACK instead of a blind (1500,600) tap; the
            # next row check re-verifies the panel and stops if it is gone
            v.tap(v.BACK, 1.2)

    if not closed:
        v.tap(v.BACK, 1.5)
    img = v.shot('dg_back')
    st = v.classify(img)
    print(f'    after close: {st}; claimed rows: {claimed or "none (already claimed today)"}', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
