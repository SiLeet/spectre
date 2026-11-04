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
     A full-screen hero card may also appear and must be dismissed. T93:
     closing the card can open the letterboxed tap-to-close 'Victory
     Rewards' overlay (is_victory_rewards) -> CARD_CLOSE (<= VR_MAX_TAPS)
     -> card again / boss page.

State detection uses colour probes only (no OCR; uiautomator fails on this
UI). Unknown states never trigger blind taps: while a fight may be running
the driver waits, otherwise it aborts.

T38 hardening (review batch, 2026-11-01):
  - is_boss_page/is_prep are two-sided (calibrated): the boss page shows a
    full-width green Battle bar (left BOSS_BAR_LEFT AND right probe green,
    minus hero detail); prep = v.is_dr_prep (hero grid, one wide bar,
    PREP_TAP on it) or the legacy SKIP layout. T91: the old centre probe sat
    on the boss page's dark 'Chances' label and read it as prep.
  - dim popups need calibrated probes (dimmed back-arrow + bottom bar +
    corner glow; black loading frames and the night world do not match)
    and a 2-shot debounce before anything is dismissed.
  - a global dismiss-tap budget bounds every retry loop.
  - Battle Modes -> Dream Realm card taps are probe-verified.
  - after a Battle tap the driver waits until the ready state is left
    before tapping again (no taps into the fight-start transition).

Usage: python scripts/afk_dream_realm.py --fights N [--dry-run]
Exit codes: 0 done, 1 stuck, 2 adb error, 5 skipped (PC in use), 7 tap lock held (another run tapping).
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402
import afk_memory  # noqa: E402
import afk_normalize  # noqa: E402  (bounded escape ladder, T66)
import _bot_lock  # noqa: E402

BATTLE_MODES = (890, 1060)
DREAM_CARD = (960, 280)          # Dream Realm card in the Battle Modes menu
BOSS_TAP = (960, 1020)           # green Battle button on the boss page
PREP_TAP = (1280, 1010)          # green Battle button on the prep screen
                                 # NB: (960,1010) on prep is the SKIP button — never tap it
BATTLE_BTN_BOSS = (960, 1040)    # centre probe (legacy SKIP-layout prep / is_fight)
BATTLE_BTN_PREP = v.DR_BOSS_BAR[1]   # (1280, 1010)
BOSS_BAR_LEFT = v.DR_BOSS_BAR[0] # (700, 1000) T91: boss bar spans x 595-1655 -> green here;
                                 # the prep's Records button sits here (cream).
                                 # LIVE: boss shots-66808/dr_f1_chances (101,156,91),
                                 # prep dr_f1_prewait1 (244,240,234). The centre probe
                                 # reads (86,130,78) on the boss page (Chances label):
                                 # _green's G>130 missed it by 0 -> boss read as prep
CARD_CLOSE = (960, 1035)         # "Tap to close" strip on the BATTLE ENDED card
CARD_BANNER = (960, 90)          # orange banner of the BATTLE ENDED card
CARD_BANNER_WIDE = ((600, 60), (1500, 60))   # T93: banner spans the card width.
                                 # LIVE: card shots-72816/dr_f1_w8 + shots-69680/norm_1
                                 # (202..226, 120..132, 3..48); the main menu matched
                                 # the 3 old probes (Honor Duel tile at (960,90)) and
                                 # reads cream (236,231,220) here (shots-58752/norm_1)
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
SPEED_X2 = (1092, 788)           # 2x speed toggle in a running fight (b69fbc4)
DIM_DISMISS = (480, 300)
# T93 'Victory Rewards' overlay (tap-to-close, over the dimmed BATTLE ENDED
# card; opens on the card's close tap). LIVE: shots-72816/dr_f1_resolve_0,
# dr_post1_0, dr_post1_fight0_w0..27, shots-69680/norm_0 (all 31 identical):
# letterbox L<=5.8 (best other frame 17.2, AFK chest popups), centre
# (113,77,41) L 83.7, title band >=200 share 0.156-0.173 (0.0 on every
# other frame with dark sides). CARD_CLOSE (960,1035) reads dark (49,49,45)
# on the overlay, under 'Tap to close' (1066,1013), with the card's own close
# strip beneath; not yet tapped live on the overlay (only BACK seen closing
# it: shots-69680/norm_0 -> norm_1).
VR_SIDES = ((60, 540), (1860, 540), (60, 200), (1860, 900))
VR_CENTRE = (960, 540)
VR_TITLE = (780, 95, 1360, 175)  # 'Victory Rewards' title box
VR_MAX_TAPS = 2                  # per resolve_end_states call

POLL = 5.0
FIGHT_WAIT = 150.0               # same as the --wait-fight default
MAX_UNKNOWN = 20                 # back_to_ready: ~60 s of unrecognised frames
MAX_DISMISS_TAPS = 24            # global dismiss budget (T38 #12)

_dismiss_taps = 0
_battle_tap_t = 0.0              # T61: monotonic time of the last Battle tap


def _mark_battle_tap() -> None:
    global _battle_tap_t
    _battle_tap_t = time.monotonic()


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
    """Bright results card with a full-width orange banner on a dark backdrop."""
    close = v.avg(img, CARD_CLOSE)
    corner = v.avg(img, CORNER)
    return (all(b[0] > 160 and b[2] < 110
                for b in (v.avg(img, p) for p in (CARD_BANNER, *CARD_BANNER_WIDE)))
            and v.lum(close) > 200 and v.lum(corner) < 90)


def is_victory_rewards(img) -> bool:
    """T93: black letterbox + warm dim centre + bright title band. Old
    is_fight read it as a running fight (all its probes dark: centre
    (48,49,45), prep spot L 49, (960,540) L 84 so not uniform-dark) and
    waited 150 s on it."""
    c = v.avg(img, VR_CENTRE)
    h = img.crop(VR_TITLE).convert('L').histogram()
    return (all(v.lum(v.avg(img, p)) < 12 for p in VR_SIDES)
            and 50 < v.lum(c) < 130 and c[0] - c[2] > 40
            and sum(h[200:]) / sum(h) > 0.08)


def is_hero_card(img) -> bool:
    """Full-screen bright hero card (covers even the back-arrow corner).

    Two positive probes: a single threshold at ~180 sat right where the
    PANEL back-arrow reads (~178), so one probe alone was too tight (T38 #5).
    HERO_PROBE threshold 180: every archived boss page reads 171.2 there, the
    old 170 left 1.2 lum of margin (runtime review R14).
    """
    return (not is_battle_ended(img)
            and v.lum(v.avg(img, HERO_PROBE)) > 180
            and v.lum(v.avg(img, HERO_PROBE2)) > 150
            and v.lum(v.avg(img, CORNER)) > 140)


def _dim_probes(img) -> bool:
    """Dim-overlay candidate, calibrated on real screenshots (T38 #2):

    dim overlay:  back-arrow ~4-10, bottom bar ~5-8, corner glow 58-69
    fight frames: back-arrow ~137, bottom bar ~42            -> no match
    boss page:    bottom bar ~228                            -> no match
    night world:  back-arrow ~47, bottom bar bright          -> no match
    black loading frame: corner ~0 (no glow)                 -> no match
    fight-start transition: back ~4, bar ~4, blue corner ~67 -> DID match
      (shots-1752/dr_f1_resolve_0, runtime review R4): a dim popup still
      shows its card, a transition is dark at every other probe -> excluded
    """
    back = v.lum(v.avg(img, BACK_ARROW))
    bar = v.lum(v.avg(img, BOTBAR))
    glow = v.lum(v.avg(img, CORNER))
    return back < 25 and bar < 25 and 30 < glow < 100 and not is_uniform_dark(img)


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


# T94: the boss-page probes moved to afk_claim_vision (classify names the
# page DR_BOSS); the old names stay as aliases.
_green = v.dr_green
HERO_DETAIL_PROBES = v.DR_HERO_DETAIL
is_hero_detail = v.is_dr_hero_detail
is_boss_page = v.is_dr_boss_bar


def is_prep(img) -> bool:
    """Prep screen: green Battle button on the RIGHT (1280,1010) while the
    centre probe is NOT green -- there the centre is the white SKIP button,
    which is never tapped (T38 #1). T91: the live prep is a hero grid with
    ONE wide Battle bar (centre green too, and is_hero_detail matches it):
    v.is_dr_prep; PREP_TAP (1280,1010) lies on that bar (x 718-1652,
    y 954-1042). The boss page also leaves the centre un-green (label), so
    the old rule needs 'not boss'."""
    if v.is_dr_prep(img):
        return True
    return (_green(v.avg(img, BATTLE_BTN_PREP))
            and not _green(v.avg(img, BATTLE_BTN_BOSS))
            and not is_boss_page(img))


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
    excluded explicitly; ready/end screens never count. The Battle-Modes menu
    is excluded too (A8 live fund #1: its dark body reads (109,93,93) at both
    probes — neither white nor green — and used to classify as a running
    fight, blocking reach_world for 150 s)."""
    if v.is_battle_modes(img):
        return False
    centre = v.avg(img, BATTLE_BTN_BOSS)
    if v.lum(centre) > 200 or _green(centre) or v.lum(v.avg(img, BATTLE_BTN_PREP)) >= 120:
        return False
    return not (is_uniform_dark(img) or is_ready(img) or is_battle_ended(img)
                or is_victory_rewards(img) or is_hero_card(img) or _dim_probes(img))


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
    """Dismiss any sequence of battle-ended card / Victory Rewards overlay /
    dim popup / hero card.

    Returns the final screenshot once none of those states remain, or None
    when the dismiss budget is exhausted or a popup refuses to close.
    """
    vr = 0
    for i in range(8):
        if is_battle_ended(img):
            if not _budget():
                return None
            print(f'    {tag}: battle ended card -> tap to close', flush=True)
            v.tap(CARD_CLOSE, 3.0)
        elif is_victory_rewards(img):
            if vr >= VR_MAX_TAPS or not _budget():
                print(f'    {tag}: Victory Rewards overlay persists', flush=True)
                return None
            vr += 1
            print(f'    {tag}: Victory Rewards overlay -> tap to close', flush=True)
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
                v.back(2.0)             # T97: keyevent, cannot land on a buy button
        elif is_hero_card(img):
            if not _budget():
                return None
            print(f'    {tag}: hero card -> corner dismiss', flush=True)
            v.tap(HERO_DISMISS, 2.5)
        else:
            return img
        img = v.shot(f'{tag}_{i}')
    # the 8th action may have closed the last card: judge that frame too
    if is_battle_ended(img) or is_victory_rewards(img) or is_hero_card(img) or _dim_probes(img):
        return None   # still cycling end states after 8 rounds -> give up
    return img


def back_to_ready(tag: str, attempts: int = 10) -> bool:
    """Get back to the boss page / prep screen from wherever we are.

    Never taps blindly: unknown frames are waited out (a fight may be
    running), and only recognised panels are dismissed. A frame with the
    fight marker hands over to wait_for_fight_end (a fight lasts ~90 s; the
    old 4-unknown limit gave up after ~12 s — runtime review R5).
    """
    unknown = 0
    for i in range(attempts + MAX_UNKNOWN):
        img = v.shot(f'{tag}_{i}')
        if is_ready(img):
            return True
        if is_battle_ended(img) or is_victory_rewards(img) or is_hero_card(img) or _dim_probes(img):
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
        if is_fight(img):
            print(f'    {tag}: fight running — waiting for its end', flush=True)
            end = wait_for_fight_end(f'{tag}_fight{i}', FIGHT_WAIT)
            img = resolve_end_states(end, f'{tag}_fend{i}') if end is not None else None
            if img is None:
                return False
            if is_ready(img):
                return True
            continue
        unknown += 1
        if unknown >= MAX_UNKNOWN:
            print(f'    {tag}: giving up, {unknown} unrecognised frames',
                  flush=True)
            return False
        time.sleep(3)
    return is_ready(v.shot(f'{tag}_final'))


def wait_for_fight_end(tag: str, max_wait: float):
    """Poll while the timed fight runs. Returns the screenshot of the first
    end state, else None on timeout. The shot taken at/after the deadline is
    still classified before giving up (T38 #9).

    Ready re-arm (A8a-2): if the boss page / prep screen stands for 3 polls
    and no fight marker was seen yet, the fight never started — Battle is
    re-tapped once (budgeted) and the wait window restarts.
    """
    deadline = time.time() + max_wait
    n = 0
    ready_run = 0
    fought = rearmed = False
    img = v.shot(f'{tag}_w0')
    while time.time() < deadline:
        if (is_battle_ended(img) or is_victory_rewards(img) or is_hero_card(img)
                or dim_confirmed(f'{tag}_w{n}', img)):
            return img
        if is_fight(img):
            fought, ready_run = True, 0
        elif is_ready(img):
            ready_run += 1
            if ready_run >= 3 and not fought and not rearmed:
                if not _budget():
                    return None
                cls = 'prep' if is_prep(img) else 'boss'
                print(f'    {tag}: still on the {cls} screen, no fight marker — '
                      're-tapping Battle once', flush=True)
                _mark_battle_tap()
                v.tap(PREP_TAP if cls == 'prep' else BOSS_TAP, 4.0)
                rearmed, ready_run = True, 0
                deadline = time.time() + max_wait
        else:
            ready_run = 0
        time.sleep(POLL)
        n += 1
        img = v.shot(f'{tag}_w{n}')
    if is_battle_ended(img) or is_victory_rewards(img) or is_hero_card(img) or _dim_probes(img):
        return img
    print(f'    {tag}: fight did not end within {max_wait:.0f}s', flush=True)
    return None


def reach_world(tag: str) -> bool:
    """BACK (keyevent, T97) back to the world view. UNKNOWN frames never get a BACK
    (T38 #3): a running fight is waited out, other unknowns are polled a few
    times before aborting (runtime review R13 — every fight frame is UNKNOWN,
    so starting mid-fight used to exit 1 at once)."""
    unknown = 0
    for i in range(6 + 4):
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
            if v.is_battle_modes(img):
                print(f'    {tag}: Battle Modes menu -> BACK (A8 fund #1)',
                      flush=True)
                v.back(2.0)
                continue
            if is_fight(img):
                print(f'    {tag}: fight running — waiting for its end', flush=True)
                end = wait_for_fight_end(f'{tag}_fight{i}', FIGHT_WAIT)
                if end is None or resolve_end_states(end, f'{tag}_fend{i}') is None:
                    return False
                continue
            unknown += 1
            if unknown >= 4:
                print(f'    {tag}: unknown frame -- refusing to tap BACK blind',
                      flush=True)
                return False
            time.sleep(3)
            continue
        v.back(1.5)                     # T97: PANEL/POPUP/DR_PREP/DR_BOSS, never WORLD
    return v.classify(v.shot(f'{tag}_final')) == 'WORLD'


def start_fight(fight: int, attempts_max: int = 4) -> str | None:
    """Tap Battle on the boss page / prep screen until the fight is underway.

    Never re-taps while the same ready screen still stands (T38 #6). "Underway"
    needs positive evidence (A8a-1): the in-fight marker or an end state.
    Black/undecided transition frames keep polling — accepting them left the
    driver on the pre-fight screen for 153 s (shots-33128).

    Returns 'started' (fight marker or end card seen), 'dialog' (a dim
    dialog answered the tap — chance purchase / empty pool: BACK, no fight
    counted; runtime review R7) or None (no start after attempts_max taps).
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
        if not _budget():                  # start taps count into the global budget (R14)
            return None
        _mark_battle_tap()
        v.tap(btn, 4.0)
        same = 0
        for k in range(10):
            img = v.shot(f'dr_f{fight}_after{attempt}_{k}')
            if is_fight(img) or is_battle_ended(img) or is_hero_card(img):
                return 'started'
            if dim_confirmed(f'dr_f{fight}_after{attempt}_{k}', img):
                print(f'    fight {fight}: dim dialog after the Battle tap — BACK, '
                      'not counted as a fight', flush=True)
                v.back(2.0)
                return 'dialog'
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
    return None


def parse_chances(lines: list[str]) -> int | None:
    """Remaining chances from the boss page OCR ('Chances: 5/7')."""
    for ln in lines:
        m = re.search(r'chances?\W*(\d+)\s*/\s*\d+', ln, re.I)
        if m:
            return int(m.group(1))
    return None


def set_speed_x2(fight: int) -> bool:
    """Tap 2x only on a frame that shows the fight marker (runtime review R6:
    the blind tap 1.5 s after start_fight hit the black transition, or a
    roster card on a pre-fight screen). One retry ~3 s later."""
    for k in range(2):
        if is_fight(v.shot(f'dr_f{fight}_speed{k}')):
            v.tap(SPEED_X2, 1.5)
            print(f'    fight {fight}: 2x speed enabled', flush=True)
            return True
        time.sleep(3)
    print(f'    fight {fight}: no fight marker for the 2x tap — running at 1x', flush=True)
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

    if not _bot_lock.acquire():
        print(f'    SKIP: tap lock held ({_bot_lock.describe()}) — '
              'another bot run is tapping (exit 7)', flush=True)
        return 7
    _bot_lock.release_at_exit()

    if args.min_idle > 0:
        idle = v.idle_seconds()
        if idle is not None and idle < args.min_idle:
            print(f'    SKIP: PC is in use (idle {idle:.0f}s)', flush=True)
            return 5
        print(f'    idle check ok ({idle:.0f}s)' if idle is not None
              else '    idle unknown', flush=True)

    if args.pid and args.base:
        status, power = afk_memory.power(args.pid, args.base)
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

    moved = v.prune_shot_dirs()        # old shots-<pid> dirs -> .spectre/trash (R8)
    if moved:
        print(f'    moved {moved} old shot dirs to .spectre/trash/', flush=True)
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
            # T66 (night log 2026-11-03: normalize 0..4 POPUP, then 'could not
            # reach the world view'): bounded escapes first, then one more try
            print('    could not reach the world view — escape ladder (max 2 cycles)', flush=True)
            if not (afk_normalize.escape_ladder('dr_esc', cycles=2) and reach_world('dr_world2')):
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
    walls: list[float] = []
    for fight in range(1, args.fights + 1):
        print(f'--- dream realm fight {fight}/{args.fights}', flush=True)
        if not back_to_ready(f'dr_pre{fight}'):
            print('    ERROR: Dream Realm boss page not reachable', flush=True)
            return 1
        img = v.shot(f'dr_f{fight}_chances')
        if is_boss_page(img):
            chances = parse_chances(v.ocr_lines(f'dr_f{fight}_chances'))
            print(f'    fight {fight}: chances left = '
                  f'{"unreadable" if chances is None else chances}', flush=True)
            if chances == 0:
                print('    STOP: no Dream Realm chances left', flush=True)
                break
        started = start_fight(fight)
        if started == 'dialog':
            print('    STOP: Battle opened a dialog instead of a fight '
                  '(chance purchase / empty pool?)', flush=True)
            break
        if started is None:
            print('    ERROR: fight did not start after 4 battle taps',
                  flush=True)
            return 1

        # fight is running: set 2x speed (same damage per game-second,
        # half the real wall-clock time; x4 is premium-locked)
        set_speed_x2(fight)

        end_img = wait_for_fight_end(f'dr_f{fight}', args.wait_fight)
        wall = time.monotonic() - _battle_tap_t   # T61: Battle tap -> end detected
        if end_img is None:
            print(f'    fight {fight}: {v.battle_metric("dream", "timeout", wall)}', flush=True)
            print(v.wall_summary('dream', walls), flush=True)
            return 1
        fights += 1
        walls.append(wall)
        print(f'    fight {fight}: completed (chance consumed) '
              f'{v.battle_metric("dream", "ended", wall)}', flush=True)
        if v.prune_shot_dirs():            # bound the within-run dir growth (R8)
            print('    (old shot dirs moved to .spectre/trash)', flush=True)
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
            v.back(2.0)
    img = v.shot('dr_final')
    print(v.wall_summary('dream', walls), flush=True)
    print(f'    done: {fights} fight(s) completed; final state: '
          f'{v.classify(img)}', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
