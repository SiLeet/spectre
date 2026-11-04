"""Arena daily-flow driver for AFK Journey (BlueStacks 1920x1080).

Maps the verified T27 flow (TODOS.md 'T27 (Teilstand)'):

  1. reach the world view (BACK xN, dismiss taps)
  2. Battle Modes (890,1060) -> Arena card (1200,300)
  3. Challenge (1080,1004) -> Select Opponent list
  4. per fight: tap the LEFT opponent's green sword button (T95; the old card
     tap (750,500) only toggles the opponent detail on the current layout)
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
Exit codes: 0 = all attempts done (incl. the attempts-exhausted stop), 1 = stuck / unknown / aborted with no fight, 5 = idle-gate skip, 7 = tap lock held by another run.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402
import _bot_lock  # noqa: E402


# verified T27 coordinates (TODOS.md, 2026-10-31)
GROUND = (300, 250)         # world-view dismiss tap
ARENA_CARD = (1200, 300)    # Arena card inside Battle Modes
CHALLENGE = (1080, 1004)    # green Challenge button, arena lobby
OPPONENT_LEFT = (750, 500)  # old-layout left card; current layout: opens/closes the detail view
# LIVE: on the T95 opponent detail view (shots-52268/arena_f1_step1|3|5) this spot is
# the cream 'Refresh: 6/6' plate (x 869-991); only arena_state's green test gates it.
ARENA_BATTLE = (960, 1010)  # Battle button on the arena prep screen
CHALLENGE_AGAIN = (1080, 1010)  # after a resolved fight

# T92 lobby gate. LIVE: shots-63812/arena_1_lobby (+ shots-59516/arena_1_lobby,
# shots-15028|17920/norm_*): bar (101,156,91) G-max 55, plate L 250, band L 13.
# Same back+plate+green-bar row on the DR prep (band L 229) and hero detail
# (band L 226): only the dark band tells those apart (their plate reads L 250
# too). The DR boss page also fails the plate (L 132). The old
# lum(1080,1004)>150 read L 132 here.
LOBBY_BAR = ((800, 1000), (1400, 1000))   # Challenge bar, both sides of the label
LOBBY_PLATE = (685, 975)                  # Formation plate, top-right corner (r=4)
LOBBY_BAND = (1100, 1068)                 # dark navy band under the bar (r=6)
# LIVE: shots-52268/arena_1_lobby + shots-15028|17920/norm_0: back plate x 478-583,
# arrow (530,1000) L 186. v.BACK (474,1010) sits 4 px left of the plate (it did
# press it live: norm_1 arrow highlighted, then Battle Modes); the centre has margin.
LOBBY_BACK = (530, 1000)

# T95 select screen, current layout. LIVE: shots-52268/arena_2_select,
# arena_f1_step0|2|4, arena_p1_pre, arena_exit0 (all identical): three 3D cards,
# one green sword button under each (left one centred (845,782), white icon in
# the middle, ring G-max 54/63 left/right of it), cream back plate x 742-846 /
# y 964-1044 (L 250), cream 'Refresh: 6/6' plate x 1282-1386 (L 250, NEVER tap).
# The opponent detail view (f1_step1|3|5) keeps the back plate but puts the
# green Challenge! bar where the Refresh plate was and covers the sword.
# The cards are not sorted by power (12K/81K/18K here): left = weakest is not
# guaranteed. shortcut: no OCR power pick yet, add one if left loses too often.
SWORD_LEFT = (845, 782)                   # left card's sword button
SWORD_RING = ((807, 782), (883, 782))     # green ring beside the icon (r=4)
SELECT_ARROW = (793, 1000)                # back plate centre -> lobby
SELECT_PLATES = ((760, 1000), (1300, 1000))   # back plate, Refresh plate (probe only, r=4)
# LIVE: detail view (f1_step1|3|5): back plate (760,1000) L 250, arrow (793,1000) L 175
# as on select; green Challenge! bar at (1300,1000) G-max 66 (select: cream -3);
# dark floor left of the back plate (720,1000) L 49. Without that gap check the
# AFK-stage DEFEAT card (trash/shots-6048/rw_0, 77760/sp_auto_25: cream stats
# plate L 250 + green Retry G-max 55) matched.
DETAIL_GAP = (720, 1000)
# Detail view's green 'Challenge!' bar (x ~995-1385), left of the label. LIVE:
# f1_step1|3|5 G-max 55 here (label centre (1190,1000) only 15: white text);
# select frames read floor (-33). The old card tap opened this view and the next
# card tap closed it again (f1_step0..5) — its Challenge! was never pressed.
DETAIL_CHALLENGE = (1050, 1000)


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


def unchanged(sig, img: Image.Image) -> bool:
    """T97: img still shows the screen `sig` was taken of (an input there did nothing)."""
    return sum(dist(a, b) for a, b in zip(sig, screen_signature(img))) < STAGNANT_DIST



def is_lobby(img: Image.Image) -> bool:
    """Arena lobby: green Challenge bar + cream Formation plate + dark band
    below the bar, and the dark hall at (480,270) (not Battle Modes)."""
    gmax = lambda c: c[1] - max(c[0], c[2])
    return (all(gmax(avg(img, p)) > 35 for p in LOBBY_BAR)
            and v.lum(avg(img, LOBBY_PLATE, r=4)) > 200
            and v.lum(avg(img, LOBBY_BAND, r=6)) < 40
            and v.lum(avg(img, (480, 270))) < 200)


def is_select(img: Image.Image) -> bool:
    """T95 select screen (current layout): left sword ring green on both sides
    + cream back and Refresh plates (the detail view has the green bar there)."""
    gmax = lambda c: c[1] - max(c[0], c[2])
    return (all(gmax(avg(img, p, r=4)) > 35 for p in SWORD_RING)
            and all(v.lum(avg(img, p, r=4)) > 200 for p in SELECT_PLATES))


def is_detail(img: Image.Image) -> bool:
    """T95 opponent detail view: cream back plate (dark floor left of it) +
    green Challenge! bar where the select screen has its Refresh plate.
    Left via keyevent BACK (T97)."""
    back, bar = (avg(img, p, r=4) for p in SELECT_PLATES)
    return (v.lum(back) > 200 and bar[1] - max(bar[0], bar[2]) > 35
            and v.lum(avg(img, DETAIL_GAP, r=4)) < 120)


def arena_state(img: Image.Image) -> str:
    """Classify the arena chain: RESULT card, PREP (Battle button) or SELECT.

    PREP is checked first (the green Battle button is unambiguous). SELECT is
    identified POSITIVELY: the season banners light the card probe (960,300)
    warm-orange while the Refresh badge (1160,1010) stays bright — the old
    bare 'bright card => RESULT' rule read the season-skinned Select screen
    as RESULT (banner avg 198.7 > 190) and stalled the whole chain
    (2026-11-03, shots-6048 + f1probe_select). A real RESULT card dims the
    underlying UI, so the refresh badge reads dark there. The T95 layout (select
    and detail view) reaches SELECT through the final fallback; is_select /
    is_detail decide what to tap there."""
    btn = avg(img, ARENA_BATTLE)
    if btn[1] > 120 and btn[1] > btn[0] + 20 and btn[1] > btn[2] + 20:
        return 'PREP'                       # green Battle button at the bottom
    card = avg(img, (960, 300))
    refresh = avg(img, (1160, 1010))
    if refresh[0] > 190 and refresh[1] > 190 \
            and card[0] > 180 and card[0] - card[2] > 50:
        return 'SELECT'                     # warm season banners + bright refresh badge
    if sum(card) / 3 > 190:                 # bright victory/defeat card
        return 'RESULT'
    return 'SELECT'


_battle_tap_t = 0.0


def _mark_battle_tap() -> None:
    global _battle_tap_t
    _battle_tap_t = time.monotonic()


STAGNANT_STEPS = 2      # LIVE: unchanged steps before the zombie recovery
STAGNANT_DIST = 40      # LIVE: screen_signature distance below which a step "did nothing"
CARD_DISMISS = (480, 300)


def advance_to_fight(tag: str, steps: int = 6) -> str:
    """Drive the arena chain to a running fight: dismiss results, pick the left
    opponent (the left card, not necessarily the weakest), press Battle on the
    prep screen.

    Zombie guard (T66, night log 2026-11-03: 'steps 0=SELECT, 1..5=RESULT ->
    could not reach a fight (STUCK)'): after STAGNANT_STEPS steps whose state
    and screen did not change, one card dismiss + a fresh select attempt; a
    second stagnation ends the chain as STUCK at once (bounded).
    T97 (live 2026-11-04: every sword tap dead, keyevent BACK worked): on the T95
    select / detail view the recovery is the same tap once more as a short press
    (v.tap_hold, LIVE: unverified); still stagnant -> ONE keyevent BACK out of
    select/detail (exit_to_world goes on from there), then STUCK as before."""
    prev = None
    stagnant = 0
    recovered = False
    for i in range(steps):
        img = v.shot(f'{tag}_step{i}')
        if v.is_confirm_dialog(img):
            tap(v.CONFIRM_CANCEL, 1.5)      # CANCEL — never confirm a purchase
            return 'DIALOG'
        st = arena_state(img)
        same = prev is not None and prev[0] == st and unchanged(prev[1], img)
        stagnant = stagnant + 1 if same else 0
        prev = (st, screen_signature(img))
        print(f'    [{tag}] step {i}: {st}' + (f' (stagnant {stagnant})' if stagnant else ''), flush=True)
        if stagnant >= STAGNANT_STEPS:
            t95 = SWORD_LEFT if is_select(img) else DETAIL_CHALLENGE if is_detail(img) else None
            if recovered:
                print(f'    [{tag}] still stagnant after the recovery — giving up', flush=True)
                if t95:
                    print(f'    [{tag}] select/detail still up -> keyevent BACK (out of select/detail)', flush=True)
                    v.back(2.0)
                return 'STUCK'
            if t95:
                print(f'    [{tag}] zombie: {stagnant} steps without progress -> hold-tap {t95}',
                      flush=True)
                v.tap_hold(t95, wait=2.5)
            else:
                print(f'    [{tag}] zombie: {stagnant} steps without progress -> card dismiss + re-select',
                      flush=True)
                tap(CARD_DISMISS, 1.5)
            recovered, stagnant, prev = True, 0, None
            continue                        # next step re-reads; SELECT taps the opponent again
        if st == 'RESULT':
            tap((480, 300), 1.5)            # dismiss the result card
        elif st == 'PREP':
            _mark_battle_tap()              # T61: wall time starts at the Battle tap
            tap(ARENA_BATTLE, 3.0)
            return 'PREP'
        elif is_select(img):
            tap(SWORD_LEFT, 2.5)            # T95: the sword button starts the challenge
        elif is_detail(img):
            tap(DETAIL_CHALLENGE, 3.0)      # T95: detail view (sword or card tap) -> its Challenge!
        else:
            tap(OPPONENT_LEFT, 2.5)         # old layout; closes a T95 detail view (f1_step1 -> 2)
    return 'STUCK'


def exit_to_world(max_steps: int = 5) -> bool:
    """Navigate out of the arena chain after the fights (WARN-only).

    A run that ends on the select screen blocks the following flows twice over
    (both live-verified 2026-11-03): classify() reads select as POPUP (R13)
    and the generic BACK (474,1010) cannot leave it — the select screen's own
    back arrow sits at (714,1010). Route: select -> lobby (714) -> battle
    modes (474) -> world (474); T95 layout: select back arrow SELECT_ARROW
    (793,1000). Result cards are dismissed on the way; an
    unrecognised screen stops the exit (bounded), the run keeps its result.
    T97: every back arrow here is a keyevent BACK (live 2026-11-04 the SELECT_ARROW
    tap was dead x5, 'input keyevent 4' left select -> lobby -> world); each fires
    only after classify() read the frame as non-WORLD.
    """
    for i in range(max_steps):
        img = v.shot(f'arena_exit{i}')
        if v.classify(img) == 'WORLD':
            return True
        if v.is_confirm_dialog(img):
            tap(v.CONFIRM_CANCEL, 1.5)      # CANCEL — never confirm a purchase
            continue
        if v.is_battle_modes(img):
            v.back(2.0)
            continue
        if arena_state(img) == 'RESULT':
            tap(CARD_DISMISS, 1.5)
            continue
        if arena_state(img) == 'PREP':
            # live 2026-11-03 (shots-78504): after the LAST fight the game sits
            # on the arena prep screen (hero grid) — its back arrow at (474,1010)
            # goes to the select screen, not to the lobby
            v.back(2.5)
            continue
        if is_select(img) or is_detail(img):
            v.back(2.0)                     # T95: v.BACK / SELECT_BACK taps hit the floor here
            continue
        # Old layout: the positive SELECT rule (refresh badge at (1160,1010) bright
        # white on real select frames). A real lobby already reads PREP above
        # (bar under (960,1010)) and leaves via the same BACK; is_lobby here
        # covers lobbies that do not.
        select = arena_state(img) == 'SELECT'
        badge = avg(img, (1160, 1010))
        if select and badge[0] > 190 and badge[1] > 190:
            v.back(2.0)
            continue
        if is_lobby(img):
            v.back(2.0)                     # lobby back arrow -> battle modes
            continue
        print(f'    WARN: arena exit step {i}: unrecognised screen — stopping exit',
              flush=True)
        return False
    print('    WARN: arena exit did not reach the world view', flush=True)
    return False


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

    if not v.open_battle_modes():
        print('    ERROR: Battle Modes did not open', flush=True)
        return 1
    if args.dry_run:
        print('[dry-run] would open Arena and fight', flush=True)
        return 0

    print('--- Arena card -> lobby', flush=True)
    tap(ARENA_CARD, 4.0)
    img = v.shot('arena_1_lobby')
    if not is_lobby(img):
        print('    ERROR: arena lobby did not open', flush=True)
        return 1

    tap(CHALLENGE, 4.0)
    img = v.shot('arena_2_select')
    print(f'    select-opponent signature: {screen_signature(img)}', flush=True)

    wins = 0
    failed = False
    walls: list[float] = []
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
        # no end detection here: the wall time is ~the --wait-fight sleep
        wall = time.monotonic() - _battle_tap_t
        walls.append(wall)
        wall_f = v.battle_metric('arena', 'changed' if changed else 'unchanged', wall)
        print(f'    changed={changed} {sig_before} -> {sig_after} {wall_f}', flush=True)
        if not changed:
            print('    WARN: screen unchanged after the fight — aborting', flush=True)
            failed = True
            break
        wins += 1

    print(v.wall_summary('arena', walls), flush=True)
    print(f'done: {wins} arena fights driven', flush=True)
    if exit_to_world():
        print('    exit: back at the world view', flush=True)
    # exit 1 when nothing was fought: afk-bot-watch.sh writes the once-per-day
    # arena marker on exit 0, so a failed run must not burn the day
    return 1 if failed and wins == 0 else 0


if __name__ == '__main__':
    sys.exit(main())
