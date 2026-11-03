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

T38 hardening (review batch, 2026-11-01):
  - is_boss_page/is_prep are two-sided (calibrated): the boss page shows a
    full-width green Battle bar (centre AND right probe green), the prep
    screen only lights the right probe -- the prep screen can never be
    mistaken for the boss page (BOSS_TAP sits next to SKIP).
  - dim popups need calibrated probes (dimmed back-arrow + bottom bar +
    corner glow; black loading frames and the night world do not match)
    and a 2-shot debounce before anything is dismissed.
  - a global dismiss-tap budget bounds every retry loop.
  - Battle Modes -> Dream Realm card taps are probe-verified.
  - after a Battle tap the driver waits until the ready state is left
    before tapping again (no taps into the fight-start transition).

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
CORNER = (200, 270)              # ambient-glow probe: dim overlays keep a
                                 # faint glow (58-69), black loading frames
                                 # read ~0 (T38 #2, calibrated on real shots)
HERO_PROBE = (474, 1010)         # hero card covers even the back arrow
BACK_ARROW = (474, 1010)         # dim overlays darken even the back arrow
BOTBAR = (890, 1060)             # bottom-nav Battle Modes button: bright on
                                 # world view + boss page, dark under a dim
                                 # overlay
HERO_PROBE2 = (1450, 850)        # second hero-card probe (T38 #5: the PANEL
                                 # back-arrow lum ~178 is too close to a
                                 # single-probe threshold)
HERO_DISMISS = (100, 100)        # verified live: corner tap closes the hero card
DIM_DISMISS = (480, 300)

POLL = 5.0
MAX_DISMISS_TAPS = 24            # global dismiss budget (T38 #12)

_dismiss_taps = 0


def _budget(n: int = 1) -> bool:
    """Consume dismiss-tap budget; False once the global cap is exhausted."""
    global _dismiss_taps
    _dismiss_taps += n
    if _dismiss_taps > MAX_DISMISS_TAPS:
        print(f'    ABORT: dismiss-tap budget exhausted ({MAX_DISMISS_TAPS})',
              flush=True)
        return False
    return True


def is_battle_ended(img) -> bool:
    """Bright results card with orange banner on a dark backdrop."""
    b = v.avg(img, CARD_BANNER)
    close = v.avg(img, CARD_CLOSE)
    corner = v.avg(img, CORNER)
    return b[0] > 160 and b[2] < 110 and v.lum(close) > 200 and v.lum(corner) < 90


def is_hero_card(img) -> bool:
    """Full-screen bright hero card (covers even the back-arrow corner).

    Two positive probes: a single threshold at ~180 sat right where the
    PANEL back-arrow reads (~178), so one probe alone was too tight (T38 #5).
    """
    return (not is_battle_ended(img)
            and v.lum(v.avg(img, HERO_PROBE)) > 170
            and v.lum(v.avg(img, HERO_PROBE2)) > 150
            and v.lum(v.avg(img, CORNER)) > 140)


def _dim_probes(img) -> bool:
    """Dim-overlay candidate, calibrated on real screenshots (T38 #2):

    dim overlay:  back-arrow ~4-10, bottom bar ~5-8, corner glow 58-69
    fight frames: back-arrow ~137, bottom bar ~42            -> no match
    boss page:    bottom bar ~228                            -> no match
    night world:  back-arrow ~47, bottom bar bright          -> no match
    black loading frame: corner ~0 (no glow)                 -> no match
    """
    back = v.lum(v.avg(img, BACK_ARROW))
    bar = v.lum(v.avg(img, BOTBAR))
    glow = v.lum(v.avg(img, CORNER))
    return back < 25 and bar < 25 and 30 < glow < 100


def is_dim_popup(img) -> bool:
    """Single-shot dim-overlay heuristic (cheap pre-filter; dismiss actions
    gate on the debounced dim_confirmed)."""
    return _dim_probes(img)


def dim_confirmed(tag: str, img) -> bool:
    """Debounced dim-popup detection: two consecutive shots must both read
    dim before any dismiss tap fires (T38 #2)."""
    if not _dim_probes(img):
        return False
    time.sleep(1.2)
    return _dim_probes(v.shot(f'{tag}_dim2'))


def _green(c: tuple[int, int, int]) -> bool:
    # boss-page Battle button ~(109,154,100), prep Battle button ~(160,192,152);
    # the in-fight olive probes (129,143,88)/(167,178,96) must NOT match
    return c[1] > 130 and c[1] > c[0] + 25 and c[2] < 170


def is_boss_page(img) -> bool:
    """Boss page: the Battle button is a FULL-WIDTH green bar, so the centre
    AND the right probe both read green (calibrated 2026-11-01 on real
    shots). A prep screen only lights the right probe, so it can never
    classify as boss page (T38 #1: BOSS_TAP sits next to SKIP)."""
    return (_green(v.avg(img, BATTLE_BTN_BOSS))
            and _green(v.avg(img, BATTLE_BTN_PREP)))


def is_prep(img) -> bool:
    """Prep screen: green Battle button on the RIGHT (1280,1010) while the
    centre probe is NOT green -- there the centre is the white SKIP button,
    which is never tapped (T38 #1)."""
    return (_green(v.avg(img, BATTLE_BTN_PREP))
            and not _green(v.avg(img, BATTLE_BTN_BOSS)))


def is_ready(img) -> bool:
    """Boss page or prep screen: a green Battle button, no end-state card."""
    if is_battle_ended(img) or is_hero_card(img) or _dim_probes(img):
        return False
    return is_boss_page(img) or is_prep(img)


FRAME_PROBES = ((960, 540), (480, 300), (1440, 300), (960, 100), BACK_ARROW)


def is_uniform_dark(img) -> bool:
    """Black/near-black transition frame (shots-33128: uniform (29,29,29))."""
    return all(v.lum(v.avg(img, p)) < 40 for p in FRAME_PROBES)


def is_fight(img) -> bool:
    """Positive in-fight marker (runtime review A8a-1, profile from
    shots-1752/dr_f1_w*): the bottom-centre (960,1040) is neither the white
    SKIP nor a green Battle button and the prep-Battle spot (1280,1010) is
    dark (~(22,32,72)). Uniform-dark transitions match that too, so they are
    excluded explicitly; ready/end screens never count."""
    centre = v.avg(img, BATTLE_BTN_BOSS)
    if v.lum(centre) > 200 or _green(centre) or v.lum(v.avg(img, BATTLE_BTN_PREP)) >= 120:
        return False
    return not (is_uniform_dark(img) or is_ready(img) or is_battle_ended(img)
                or is_hero_card(img))


def is_world(img) -> bool:
    return v.classify(img) == "WORLD"


def enter_dream(tag: str) -> bool:
    """From the world view: open Battle Modes (probe-verified) and tap the
    Dream Realm card. Never fires both taps unverified (T38 #7)."""
    for i in range(2):
        v.tap(BATTLE_MODES, 3.0)
        img = v.shot(f'{tag}_bm{i}')
        if v.is_battle_modes(img):
            v.tap(DREAM_CARD, 4.0)
            return True
        print(f'    {tag}: Battle Modes menu not detected (attempt {i + 1}/2)',
              flush=True)
    return False


def resolve_end_states(img, tag: str):
    """Dismiss any sequence of battle-ended card / dim popup / hero card.

    Returns the final screenshot once none of those states remain, or None
    when the dismiss budget is exhausted or a popup refuses to close.
    """
    for i in range(8):
        if is_battle_ended(img):
            if not _budget():
                return None
            print(f'    {tag}: battle ended card -> tap to close', flush=True)
            v.tap(CARD_CLOSE, 3.0)
        elif dim_confirmed(f'{tag}_d{i}', img):
            if not _budget():
                return None
            print(f'    {tag}: dim popup -> dismiss', flush=True)
            v.tap(DIM_DISMISS, 2.5)
            img = v.shot(f'{tag}_dd{i}')
            if dim_confirmed(f'{tag}_dd{i}', img):
                if not _budget():
                    return None
                print(f'    {tag}: dim popup persists -> BACK', flush=True)
                v.tap(v.BACK, 2.0)
        elif is_hero_card(img):
            if not _budget():
                return None
            print(f'    {tag}: hero card -> corner dismiss', flush=True)
            v.tap(HERO_DISMISS, 2.5)
        else:
            return img
        img = v.shot(f'{tag}_{i}')
    return None   # still cycling end states after 8 rounds -> give up


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
        if is_battle_ended(img) or is_hero_card(img) or _dim_probes(img):
            img = resolve_end_states(img, f'{tag}_end{i}')
            if img is None:
                return False
            if is_ready(img):
                return True
            continue
        if is_world(img):
            if not enter_dream(f'{tag}_enter'):
                return False
            unknown = 0
            continue
        unknown += 1
        if unknown >= 4:
            print(f'    {tag}: giving up, {unknown} unrecognised frames',
                  flush=True)
            return False
        time.sleep(3)
    return is_ready(v.shot(f'{tag}_final'))


def wait_for_fight_end(tag: str, max_wait: float):
    """Poll while the timed fight runs. Returns the screenshot of the first
    end state, else None on timeout. The shot taken at/after the deadline is
    still classified before giving up (T38 #9)."""
    deadline = time.time() + max_wait
    n = 0
    img = v.shot(f'{tag}_w0')
    while time.time() < deadline:
        if is_battle_ended(img) or is_hero_card(img) or _dim_probes(img):
            return img
        time.sleep(POLL)
        n += 1
        img = v.shot(f'{tag}_w{n}')
    if is_battle_ended(img) or is_hero_card(img) or _dim_probes(img):
        return img
    print(f'    {tag}: fight did not end within {max_wait:.0f}s', flush=True)
    return None


def reach_world(tag: str) -> bool:
    """BACK-tap back to the world view. UNKNOWN frames abort instead of
    tapping blind (T38 #3)."""
    for i in range(6):
        img = v.shot(f'{tag}_{i}')
        state = v.classify(img)
        if state == 'WORLD':
            return True
        img = resolve_end_states(img, f'{tag}_end{i}')
        if img is None:
            return False
        state = v.classify(img)
        if state == 'WORLD':
            return True
        if state == 'UNKNOWN':
            print(f'    {tag}: unknown frame -- refusing to tap BACK blind',
                  flush=True)
            return False
        v.tap(v.BACK, 1.5)
    return v.classify(v.shot(f'{tag}_final')) == 'WORLD'


def start_fight(fight: int, attempts_max: int = 4) -> bool:
    """Tap Battle on the boss page / prep screen until the fight is underway.

    Never re-taps while the same ready screen still stands (T38 #6). "Underway"
    needs positive evidence (A8a-1): the in-fight marker or an end state.
    Black/undecided transition frames keep polling — accepting them left the
    driver on the pre-fight screen for 153 s (shots-33128).
    """
    for attempt in range(attempts_max):
        img = v.shot(f'dr_f{fight}_pre{attempt}')
        cls = 'prep' if is_prep(img) else 'boss' if is_boss_page(img) else None
        if cls is None:
            time.sleep(3)
            img = v.shot(f'dr_f{fight}_prewait{attempt}')
            cls = 'prep' if is_prep(img) else 'boss' if is_boss_page(img) else None
            if cls is None:
                continue
        btn = PREP_TAP if cls == 'prep' else BOSS_TAP
        print(f'    fight {fight}: {cls} screen -> Battle', flush=True)
        v.tap(btn, 4.0)
        same = 0
        for k in range(10):
            img = v.shot(f'dr_f{fight}_after{attempt}_{k}')
            if is_fight(img) or is_battle_ended(img) or is_hero_card(img) or _dim_probes(img):
                return True
            now = 'prep' if is_prep(img) else 'boss' if is_boss_page(img) else None
            if now is not None and now != cls:
                break                       # boss <-> prep: next attempt taps the right button
            if now == cls:
                same += 1
                if same >= 6:
                    print(f'    fight {fight}: {cls} screen unchanged after tap, '
                          're-tapping', flush=True)
                    break
            time.sleep(2.5)                 # dark / undecided transition: keep polling
        else:
            print(f'    fight {fight}: no fight marker after the tap', flush=True)
    return False


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
        print(f'    idle check ok ({idle:.0f}s)' if idle is not None
              else '    idle unknown', flush=True)

    if args.pid and args.base:
        status, power = v.memory_preflight(args.pid, args.base)
        if status == 'fail':
            print('    ERROR: memory preflight failed', flush=True)
            return 2
        if status == 'disabled':
            print(f'    team_power guard disabled (offset stale, read {power})', flush=True)
        else:
            print(f'    preflight team_power = {power}', flush=True)

    if args.dry_run:
        # T38 #10: the dry-run executes the real probes instead of a no-op
        img = v.shot('dr_start')
        print('    dry-run probes:', flush=True)
        print(f'      classify={v.classify(img)} world={is_world(img)} '
              f'boss={is_boss_page(img)} prep={is_prep(img)} '
              f'ready={is_ready(img)}', flush=True)
        print(f'      battle_ended={is_battle_ended(img)} '
              f'hero={is_hero_card(img)} dim={is_dim_popup(img)}', flush=True)
        print('    dry-run: no actions taken', flush=True)
        return 0

    try:
        return run(args)
    except RuntimeError as exc:
        print(f'    ERROR: adb failure: {exc}', flush=True)
        return 2


def run(args) -> int:
    img = v.shot('dr_start')
    if is_ready(img):
        print('--- already inside Dream Realm', flush=True)
    else:
        if not reach_world('dr_world'):
            print('    ERROR: could not reach the world view', flush=True)
            return 1

        print('--- Battle Modes -> Dream Realm', flush=True)
        if not enter_dream('dr_enter0'):
            print('    ERROR: Battle Modes menu not detected', flush=True)
            return 1
        if not back_to_ready('dr_enter'):
            print('    ERROR: Dream Realm boss page not reachable', flush=True)
            return 1

    fights = 0
    for fight in range(1, args.fights + 1):
        print(f'--- dream realm fight {fight}/{args.fights}', flush=True)
        if not back_to_ready(f'dr_pre{fight}'):
            print('    ERROR: Dream Realm boss page not reachable', flush=True)
            return 1
        if not start_fight(fight):
            print('    ERROR: fight did not start after 4 battle taps',
                  flush=True)
            return 1

        # fight is running: set 2x speed (same damage per game-second,
        # half the real wall-clock time; x4 is premium-locked)
        v.tap((1092, 788), 1.5)
        print(f'    fight {fight}: 2x speed enabled', flush=True)

        end_img = wait_for_fight_end(f'dr_f{fight}', args.wait_fight)
        if end_img is None:
            return 1
        fights += 1
        print(f'    fight {fight}: completed (chance consumed)', flush=True)
        final = resolve_end_states(end_img, f'dr_f{fight}_resolve')
        if final is None:
            print('    ERROR: end-state dismiss failed', flush=True)
            return 1
        if not is_ready(final) and not back_to_ready(f'dr_post{fight}'):
            print('    ERROR: boss page not restored after fight', flush=True)
            return 1

    # leave the Dream Realm cleanly
    if fights > 0:
        img = v.shot('dr_exit')
        if is_ready(img):
            v.tap(BACK, 2.0)
    img = v.shot('dr_final')
    print(f'    done: {fights} fight(s) completed; final state: '
          f'{v.classify(img)}', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
