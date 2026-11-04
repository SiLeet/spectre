#!/usr/bin/env python3
"""Homestead phase 1 (T102): build Fields with gold/amber until the limit.

Flow (Hermes played it once live, 2026-11-04 20:40-20:44, frames in
%LOCALAPPDATA%/hermes/cache/scratch/hm_*.png):

  world -> left 'Build' button -> Avalon Creator menu (Production tab)
  -> OCR the Field tile counter 'N/M' (region crop, x3 upscale)
  -> tap the Field tile = placement mode straight away (radial menu around the
     ghost; hm_field_tap was taken BEFORE the brief's 'Build' (900,1017) tap -
     that bottom 'Build' is the already-active Build|Layout mode toggle)
  -> tap the green check found on the frame (ring detection, never a fixed
     point: (1090,520) missed live) -> world with a yellow 'Tap to Complete'
     marker over the new field (build time 5 s)
  -> tap the marker -> 'Field Built' toast -> 'Tap to close' (bottom text; the
     toast centre is the diamond reward icon and opens its info card, hm_up2)
  -> back to the menu, counter must read N+1; repeat (bounded by MAX_BUILDS)
  -> Exit -> world.

T103c (operator live 2026-11-04 22:28): a start frame showing 'exit the game?' is cancelled
via its X; finished builds left on the world ('Tap to Complete' anywhere in COLLECT_WIN) are
collected before the menu opens (tap -> 'Field Built' -> Tap to close, max COLLECT_MAX); a toast
still up after its 'Tap to close' tap gets ONE keyevent BACK (only on the recognised toast).

Never spends diamonds: a confirm dialog is always cancelled, 'Complete Now'
is never tapped (only the free marker). Every tap is gated on the previous
screenshot; an unrecognised screen stops the run.

Usage: python scripts/afk_homestead.py [--dry-run] [--min-idle S]
Exit codes: 0 built and verified, 1 stuck / unknown screen / counter unreadable,
4 nothing to do (Field at its limit, resources short, Build not available,
build refused), 5 skipped (PC in use), 7 tap lock held by another run.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from collections import Counter
from pathlib import Path

from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bot_lock  # noqa: E402  (tap lock: one bot tapping at a time)
import afk_claim_vision as v  # noqa: E402

# --- world ---------------------------------------------------------------------
BUILD_BTN = (43, 757)          # LIVE: hm_confirmed2/hm_requests/hm_req2 L161, shots-66556/norm_3 L166 (r=4);
                               # 315 WORLD frames in .spectre (HUD layouts A and B) all L>=111
                               # (min trash/shots-59516/bm_1, layout B). Brief: (~30,745) = icon's
                               # left edge (L122-132), so the icon centre is used.
BUILD_BTN_LUM = 100            # LIVE: white wrench icon on the dark pill (no frame WITHOUT it seen)
# --- Avalon Creator menu (hm_build_menu, the only menu frame) --------------------
EXIT_BTN = (453, 1010)         # LIVE: hm_build_menu cream Exit plate (198,187,183) L190; brief (440,1005)
BUILD_TAB = (900, 1022)        # LIVE: active 'Build' mode pill (146,183,134) L166 G-max 37 - a mode
                               # toggle, NOT a step of the build flow (see docstring)
LAYOUT_TAB = (1015, 1022)      # LIVE: cream 'Layout' pill (230,223,221) L225
PRODUCTION_TAB = (640, 605)    # LIVE: active (green) tab (145,184,138) G-max 39; Functions (505,605)
                               # inactive cream (223,220,216). A Functions-active frame was not seen.
FIELD_TILE = (515, 700)        # LIVE: brief's point; inside the Field tile bbox x462-565 y652-830
# T102b: the counter is white italic text on the field picture (14/16 at bbox (528,714)-(568,736),
# Hermes hm_menu_now). The whole-tile crop read 12/16 and 13/16 but never 14/16 live (shots-67544
# hs_1_read, shots-68276 hs_0_read: 'Field counter not readable'). No single crop/scale reads all
# of 12/13/14; seven OCR variants vote instead (LIVE, measured on hm_build_menu 12/16 x5,
# shots-67544/hs_0_read 13/16 x3, hs_1_read + shots-68276/hs_0_read + hm_menu_now 14/16 x3 each;
# the runner-up never had more than 1 vote, e.g. 'i3/16' -> (3,16)).
COUNTER_WIDE = (500, 700, 600, 750)
COUNTER_TIGHT = (515, 705, 585, 745)  # Hermes: generous left/bottom padding, the '1' touches the icon edge
COUNTER_VARIANTS = ((COUNTER_WIDE, 2, ''), (COUNTER_WIDE, 3, ''), (COUNTER_WIDE, 4, ''),
                    (COUNTER_WIDE, 5, ''), (COUNTER_WIDE, 3, 'bw'), (COUNTER_TIGHT, 5, ''),
                    (COUNTER_TIGHT, 3, 'pad'))   # (box, upscale, '' grey | 'bw' >215 dark | 'pad' bw+border)
COUNTER_BW = 215
COUNTER_SETTLE = 2.0           # T102b: the tile animates right after a build -> one settled re-read
RES_BOX = (1060, 8, 1500, 48)  # LIVE: resource bar; OCR x3 -> ['@ 653,402 3848', '460'] (gold, amber,
                               # silver); x2 drops the gold number
FIELD_COST = (100, 10)         # LIVE: (gold, amber) on the Field tile and the radial cost pill (12/16)
OCR_SCALE = 3
# --- placement mode: radial menu (hm_field_tap / hm_field_build / hm_field_confirmed) ---
# T102c: the radial follows the ghost - live check discs at (1090,558) (hm_field_*), (1178,486)
# (shots-67544/hs_b0_place), (934,544) (shots-47000/hs_b0_place: outside the old window
# (970,440)-(1210,680) -> 'no placement radial'); the X sits 247/248 px left at the same height
# on all three. Search band = Hermes' live band x 450-1350 / y 360-780 (check disc r~31).
RING_BAND = (450, 360, 1350, 780)
RING_CELL = 24                     # px grid for the green clusters (check disc ~62 px wide)
RING_DISC_DX = 24                  # LIVE: both discs L>=237 at +-24 px on all 5 real radials
RING_DISC_LUM = 225                # (hm_field_*, pl3, shots-47000/67544); the one band-wide false
                                   # hit (shots-41820/dr_f1_w6, Dream Realm) reads min L 87
CHECK_PX = (150, 600)          # LIVE: green-pixel count range of the check (226..241 measured)
X_DX = 247                     # LIVE: red X median (842,557) = check - (247, ~5); cancel disc (842,558)
X_PX = (150, 600)              # LIVE: red-pixel count of the X (256 on all three frames)
# --- world after the check: 'Tap to Complete' marker (hm_confirmed2) -------------
MARK_WIN = (700, 350, 1220, 800)   # LIVE: marker at (964,578) on hm_confirmed2; position follows the
                                   # camera, so a wide window around the screen centre
MARK_PX = 2000                 # LIVE: lemon-yellow disc (254,238,93): 2773 px within +-35 of the
                               # median on hm_confirmed2; <=154 on every WORLD frame in .spectre
                               # (yellow roof of shots-76112/dg_cam_5, trash/shots-53860/dg_*).
                               # T103c sweep, COLLECT_WIN, 353 WORLD frames (.spectre incl. trash +
                               # Hermes scratch): 17 hits, all real markers, near 2648..3178; best
                               # non-marker = the Kitchen's yellow request bubble 880..931 (was 1000)
# T103c: finished builds left uncollected ('Tap to Complete', shots-80480/hu_world + Hermes
# where1/base2: disc median (760,877), outside MARK_WIN) are collected at the start of the phase.
COLLECT_WIN = (250, 150, 1700, 1000)  # world area without the HUD (left column + quest tracker x<250,
                                      # right column x>1700, top bar, bottom bar y>1000)
COLLECT_MAX = 3                # markers collected per world frame (bounded)
TOAST_CLOSE = (960, 1021)      # LIVE: 'Tap to close' text median (957,1021) on hm_spire_up (and the
                               # diamond info card hm_up2); NOT (960,654) = reward icon
TOAST_WORD = 'built'           # LIVE: full-frame OCR of hm_spire_up -> 'Field Built', 'Tapto Close'
TOAST_TRIES = 4                # close taps per toast chain (toast, reward info card, BACK fallback)
MAX_BUILDS = 4                 # brief: bounded, max ~4 fields per run
BUILD_POLLS = 10               # x POLL_WAIT after the check: marker / toast / world
POLL_WAIT = 2.0
FIRST_WAIT = 6.0               # LIVE: build time 5 s on the tile ('5s')


def _pixels(img: Image.Image, box, pred) -> list[tuple[int, int]]:
    """(x, y) of every pixel in box (l, t, r, b) that matches pred(rgb)."""
    crop = img.crop(box).convert('RGB')
    w, data = crop.width, crop.tobytes()
    return [(box[0] + i // 3 % w, box[1] + i // 3 // w) for i in range(0, len(data), 3)
            if pred(data[i], data[i + 1], data[i + 2])]


def _median(pts):
    xs, ys = sorted(p[0] for p in pts), sorted(p[1] for p in pts)
    return xs[len(xs) // 2], ys[len(ys) // 2]


def _gmax(c) -> int:
    return c[1] - max(c[0], c[2])


def build_btn(img: Image.Image) -> bool:
    return v.lum(v.avg(img, BUILD_BTN, r=4)) > BUILD_BTN_LUM


def is_build_menu(img: Image.Image) -> bool:
    """Avalon Creator: cream Exit plate + green Build pill + cream Layout pill.
    LIVE: one positive frame (hm_build_menu); 0 hits on the other hm_* frames
    (hm_up3 Spire panel: Exit spot L245 but Build pill G-max -3)."""
    b = v.avg(img, BUILD_TAB)
    return (v.lum(v.avg(img, EXIT_BTN)) > 170 and _gmax(b) > 25 and v.lum(b) > 130
            and v.lum(v.avg(img, LAYOUT_TAB)) > 200)


def production_active(img: Image.Image) -> bool:
    return _gmax(v.avg(img, PRODUCTION_TAB)) > 25


def _clusters(pts, cell: int = RING_CELL) -> list[list[tuple[int, int]]]:
    """Groups of points whose `cell`-px grid cells touch (8-neighbourhood)."""
    cells: dict[tuple[int, int], list] = {}
    for x, y in pts:
        cells.setdefault((x // cell, y // cell), []).append((x, y))
    seen, groups = set(), []
    for start in cells:
        if start in seen:
            continue
        seen.add(start)
        stack, group = [start], []
        while stack:
            cx, cy = stack.pop()
            group += cells[(cx, cy)]
            for n in ((cx + dx, cy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                if n in cells and n not in seen:
                    seen.add(n)
                    stack.append(n)
        groups.append(group)
    return groups


def find_ring(img: Image.Image):
    """Placement radial menu: (check_xy, cancel_xy) from the green check and the
    red X found on the frame (count + geometry), else None. T102c: the radial sits
    around the ghost, so every green cluster in RING_BAND is a check candidate; the
    fixed geometry (red X 247 px left, same height) decides."""
    green = _pixels(img, RING_BAND, lambda r, g, b: g - max(r, b) > 50 and g > 120)
    for group in _clusters(green):
        if not CHECK_PX[0] <= len(group) <= CHECK_PX[1]:
            continue
        gx, gy = _median(group)
        red = _pixels(img, (gx - X_DX - 40, gy - 40, gx - X_DX + 40, gy + 40),
                      lambda r, g, b: r - max(g, b) > 80 and r > 150)
        if not X_PX[0] <= len(red) <= X_PX[1]:
            continue
        rx, ry = _median(red)
        if (abs(gx - rx - X_DX) <= 15 and abs(gy - ry) <= 10
                and _white_disc(img, (gx, gy)) and _white_disc(img, (rx, ry))):
            return (gx, gy), (rx, ry)
    return None


def _white_disc(img: Image.Image, c) -> bool:
    """Glyph on the radial's white disc: all four probes RING_DISC_DX off the centre are bright."""
    x, y = c
    return all(v.lum(v.avg(img, (x + dx, y + dy), r=2)) > RING_DISC_LUM
               for dx, dy in ((RING_DISC_DX, 0), (-RING_DISC_DX, 0), (0, RING_DISC_DX), (0, -RING_DISC_DX)))


def find_marker(img: Image.Image, win=MARK_WIN):
    """Yellow 'Tap to Complete' check disc over a finished build in win, else None.
    T103c: judged per yellow cluster - a wide window also holds other yellow UI (the Kitchen's
    request bubble, ~930 px) that would drag a window-wide median off the disc."""
    pts = _pixels(img, win, lambda r, g, b: r > 235 and g > 210 and b < 120 and g - b > 120)
    best = None
    for group in _clusters(pts):
        if len(group) < MARK_PX:
            continue
        mx, my = _median(group)
        near = sum(abs(x - mx) <= 35 and abs(y - my) <= 35 for x, y in group)
        if near >= MARK_PX and (best is None or near > best[0]):
            best = near, (mx, my)
    return best and best[1]


def ocr_scaled(name: str, box, tag: str) -> list[str]:
    """OCR of box from the saved shot `name`, upscaled OCR_SCALE x (small text
    reads nothing at x1). [] on any failure, like v.ocr_region."""
    try:
        with Image.open(v.TMP / f'{name}.png') as im:
            crop = im.convert('RGB').crop(box)
            crop.resize((crop.width * OCR_SCALE, crop.height * OCR_SCALE),
                        Image.Resampling.LANCZOS).save(v.TMP / f'{name}_{tag}.png')
    except (OSError, ValueError):
        pass                     # ocr_lines then finds no file and returns []
    return v.ocr_lines(f'{name}_{tag}')


def counter_votes(lines_per_variant) -> tuple[int, int] | None:
    """(built, limit) that most variants read ('14/16', "14'/16"), when >= 2 agree and it
    beats the runner-up; None otherwise (unreadable or split vote)."""
    votes = Counter()
    for lines in lines_per_variant:
        for ln in lines:
            for a, b in re.findall(r"(\d{1,2})['`]?\s*/\s*(\d{1,2})", ln):
                if int(a) <= int(b) <= 40:
                    votes[(int(a), int(b))] += 1
    top = votes.most_common(2)
    if top and top[0][1] >= 2 and (len(top) == 1 or top[0][1] > top[1][1]):
        return top[0][0]
    return None


def read_counter(name: str) -> tuple[int, int] | None:
    """Field counter of the saved menu shot `name` (T102b): every COUNTER_VARIANTS crop is
    saved as `{name}_cnt{i}` and OCR'd on its own, then counter_votes decides."""
    try:
        with Image.open(v.TMP / f'{name}.png') as im:
            src = im.convert('RGB')
    except (OSError, ValueError):
        src = None               # ocr_lines then finds no variant file and returns []
    reads = []
    for i, (box, scale, mode) in enumerate(COUNTER_VARIANTS):
        if src is not None:
            g = ImageOps.grayscale(src.crop(box))
            g = g.resize((g.width * scale, g.height * scale), Image.Resampling.LANCZOS)
            if mode:
                g = g.point(lambda p: 0 if p > COUNTER_BW else 255)
            if mode == 'pad':
                g = ImageOps.expand(g, border=40, fill=255)
            g.save(v.TMP / f'{name}_cnt{i}.png')
        reads.append(v.ocr_lines(f'{name}_cnt{i}'))
    return counter_votes(reads)


def parse_resources(lines: list[str]):
    """(gold, amber) from the resource bar; None unless all three numbers read."""
    nums = [int(n.replace(',', '')) for n in re.findall(r'\d[\d,]*', ' '.join(lines))]
    return (nums[0], nums[1]) if len(nums) == 3 else None


def tap_until(xy, wait: float, tag: str, ok, still):
    """Tap, shoot, check ok(img); one T97b retry only while still(img) says the
    tap changed nothing (a retry on a changed screen would hit something else,
    e.g. move the placement ghost). The ok frame, or None."""
    v.tap(xy, wait)
    img = v.shot(tag)
    if ok(img):
        return img
    if not still(img):
        return None
    mode = v.tap_retry(xy, wait)
    img = v.shot(f'{tag}_r')
    v.tap_result(mode, ok(img))
    return img if ok(img) else None


def toast_text(name: str) -> str:
    return ' '.join(v.ocr_lines(name)).lower()


def close_toast(text: str, tag: str):
    """A recognised toast is up ('Field Built' / its reward info card; `text` = its OCR) -> world.
    TOAST_CLOSE per toast; the SAME toast still up after its tap -> ONE keyevent BACK (T103c,
    operator live: close9 == complete1 after the tap, BACK -> close10 world). BACK only on a
    recognised toast frame - never on the world, never in the build menu. World frame, or None."""
    last, backed = None, False
    for n in range(TOAST_TRIES):
        if TOAST_WORD not in text and 'close' not in text:
            print(f'    ERROR: unknown screen, not a toast (OCR {text[:60]!r})', flush=True)
            return None
        if text == last and not backed:
            print('    toast still up after Tap to close -> one BACK', flush=True)
            v.back(1.5)
            backed = True
        else:
            v.tap(TOAST_CLOSE, 2.0)
        last = text
        img = v.shot(f'{tag}_t{n}')
        if v.classify(img) == 'WORLD':
            return img
        text = toast_text(f'{tag}_t{n}')
    print('    ERROR: toast did not close', flush=True)
    return None


def collect(img, tag: str):
    """T103c: world frame -> tap up to COLLECT_MAX finished builds' 'Tap to Complete' markers in
    COLLECT_WIN and close their toasts. The world frame, or None (unknown screen)."""
    for i in range(COLLECT_MAX):
        mark = find_marker(img, COLLECT_WIN)
        if mark is None:
            break
        print(f'    finished build waiting at {mark} - collecting', flush=True)
        v.tap(mark, 2.5)
        name = f'{tag}_col{i}'
        img = v.shot(name)
        if v.classify(img) != 'WORLD':
            img = close_toast(toast_text(name), name)
            if img is None:
                return None
    return img


def leave(img) -> None:
    """Back to the world: cancel a placement, Exit the menu, then reach_world. T102b: keyevent 4
    inside the Build menu opens 'exit game?' (Hermes, live) - reach_world (BACK) only runs once
    the menu is gone; a menu still up after Exit gets one T97b retry of the Exit button."""
    ring = find_ring(img)
    if ring:
        v.tap(ring[1], 2.0)
        img = v.shot('hs_leave_x')
    if is_build_menu(img):
        img = tap_until(EXIT_BTN, 2.5, 'hs_leave_exit', lambda im: not is_build_menu(im),
                        is_build_menu)
        if img is None:
            print('    WARN: Build menu still open after Exit - no BACK (exit-game dialog)', flush=True)
            return
    if v.classify(img) != 'WORLD':
        v.reach_world()


def production_menu(img, tag: str):
    """Menu frame -> Production tab active. The menu frame, or 1."""
    if not production_active(img):
        img = tap_until(PRODUCTION_TAB, 1.5, f'{tag}_prod',
                        lambda im: is_build_menu(im) and production_active(im), is_build_menu)
        if img is None:
            print('    ERROR: Production tab not active after the tab tap', flush=True)
            return 1
    return img


def open_menu(tag: str):
    """World -> Avalon Creator (Production tab). The menu frame, or the exit code.
    T102b: the 2nd live run started inside the menu left open by a failed run - a menu
    already up is used as is, a placement left open is cancelled (X) first; BACK
    (reach_world) only for other non-world screens. T103c: an 'exit the game?' dialog on the
    start frame (shots-9308/hu_world) is cancelled via its X first; finished builds waiting on
    the world are collected before the menu opens."""
    img = v.shot(f'{tag}_start')
    if v.is_confirm_dialog(img):
        print('    confirm dialog on the start frame -> X (never the check)', flush=True)
        v.tap(v.CONFIRM_CANCEL, 1.5)
        img = v.shot(f'{tag}_start_c')
    ring = find_ring(img)
    if ring:
        v.tap(ring[1], 2.0)
        img = v.shot(f'{tag}_start_x')
    if is_build_menu(img):
        print('    Build menu already open', flush=True)
        return production_menu(img, tag)
    if v.classify(img) != 'WORLD' and not v.reach_world():
        print('    ERROR: world view not reached', flush=True)
        return 1
    v.tap(v.GROUND, 0.8)                   # dismiss a selected building's radial
    img = v.shot(f'{tag}_world')
    if v.classify(img) != 'WORLD':
        print('    ERROR: not on the world view after the ground tap', flush=True)
        return 1
    img = collect(img, f'{tag}_world')
    if img is None:
        return 1
    if not build_btn(img):
        print('    Build button not on the world HUD - nothing to do', flush=True)
        return 4
    img = tap_until(BUILD_BTN, 2.5, f'{tag}_menu', is_build_menu,
                    lambda im: v.classify(im) == 'WORLD')
    if img is None:
        print('    ERROR: Avalon Creator menu not recognised after Build', flush=True)
        return 1
    return production_menu(img, tag)


def build_one(k: int) -> int:
    """Menu up (verified) -> one Field placed and completed, back on the world.
    0 done, 4 refused (resources / dialog), 1 stuck."""
    img = tap_until(FIELD_TILE, 2.5, f'hs_b{k}_place', lambda im: find_ring(im) is not None,
                    is_build_menu)
    if img is None:
        print('    ERROR: no placement radial after the Field tile tap', flush=True)
        return 1
    check, _ = find_ring(img)
    v.tap(check, FIRST_WAIT)
    tapped = False
    for n in range(BUILD_POLLS):
        img = v.shot(f'hs_b{k}_{n}')
        if v.is_confirm_dialog(img):
            v.tap(v.CONFIRM_CANCEL, 1.5)       # never spend diamonds
            print('    confirm/purchase dialog -> cancelled, stopping', flush=True)
            leave(v.shot(f'hs_b{k}_cancelled'))
            return 4
        if n == 0 and find_ring(img):
            # check tap stalled or refused: one T97b retry, then it is the game saying no
            mode = v.tap_retry(check, FIRST_WAIT)
            img = v.shot(f'hs_b{k}_0r')
            v.tap_result(mode, find_ring(img) is None)
            if find_ring(img):
                print('    build refused (still placing after the check) - resources short?',
                      flush=True)
                leave(img)
                return 4
        if v.classify(img) == 'WORLD':
            mark = find_marker(img)
            if tapped and not mark:
                return 0                   # the menu counter verifies it
            if mark:
                v.tap(mark, 2.5)
                tapped = True
            else:
                time.sleep(POLL_WAIT)      # still building
            continue
        text = toast_text(f'hs_b{k}_{n}')
        if TOAST_WORD in text:             # 'Field Built' (+ a reward info card on top of it)
            return 0 if close_toast(text, f'hs_b{k}') is not None else 1
        print(f'    ERROR: unknown screen while building (OCR {text[:60]!r})', flush=True)
        return 1
    print('    ERROR: build did not finish within the poll budget', flush=True)
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Homestead: build Fields up to the limit')
    ap.add_argument('--dry-run', action='store_true', help='open the menu, read the counter, exit')
    ap.add_argument('--min-idle', type=float, default=0)
    args = ap.parse_args(argv)

    if args.min_idle > 0:
        idle = v.idle_seconds()
        if idle is not None and idle < args.min_idle:
            print(f'    SKIP: PC is in use (idle {idle:.0f}s)', flush=True)
            return 5
    if not _bot_lock.acquire():
        print(f'    SKIP: tap lock held ({_bot_lock.describe()}) — '
              'another bot run is tapping (exit 7)', flush=True)
        return 7
    _bot_lock.release_at_exit()

    built, expect = 0, None
    for k in range(MAX_BUILDS + 1):
        tag = f'hs_{k}'
        img = open_menu(tag)
        if isinstance(img, int):
            return img if not built else 1
        name = f'{tag}_read'
        img = v.shot(name)
        counter = read_counter(name) if is_build_menu(img) else None
        if counter is None or (k and counter[0] != expect):
            # T102b: settle + ONE re-read (the tile animates after a build; split OCR vote)
            print(f'    Field counter read {counter} - settling, one re-read', flush=True)
            time.sleep(COUNTER_SETTLE)
            name = f'{tag}_read2'
            img = v.shot(name)
            counter = read_counter(name) if is_build_menu(img) else None
        if counter is None:
            print('    ERROR: Field counter not readable (LIVE: COUNTER_VARIANTS)', flush=True)
            leave(v.shot(f'{tag}_fail'))
            return 1
        have, limit = counter
        print(f'    Field {have}/{limit}', flush=True)
        if k and have != expect:
            print(f'    ERROR: counter {have}, expected {expect} after the build', flush=True)
            leave(v.shot(f'{tag}_fail'))
            return 1
        res = parse_resources(ocr_scaled(name, RES_BOX, 'res'))
        short = res is not None and (res[0] < FIELD_COST[0] or res[1] < FIELD_COST[1])
        stop = args.dry_run or have >= limit or short or k == MAX_BUILDS
        if stop:
            why = ('dry run' if args.dry_run else 'at the limit' if have >= limit
                   else f'resources short (gold/amber {res})' if short else 'run cap reached')
            print(f'    stop: {why}', flush=True)
            leave(v.shot(f'{tag}_exit'))
            return 0 if built or args.dry_run else 4
        rc = build_one(k)
        if rc:
            return 0 if rc == 4 and built else rc
        built, expect = built + 1, have + 1
        print(f'    built field {built} (expect {expect}/{limit})', flush=True)
    return 1                               # unreachable: k == MAX_BUILDS stops above


if __name__ == '__main__':
    sys.exit(main())
