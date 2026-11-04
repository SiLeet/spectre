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
from pathlib import Path

from PIL import Image

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
FIELD_BOX = (462, 652, 565, 830)   # LIVE: whole Field tile; OCR x3 -> ['12/16', 'Field', '? 10', '0100']
                                   # (x1 reads only '12'; x2 '12/16')
RES_BOX = (1060, 8, 1500, 48)  # LIVE: resource bar; OCR x3 -> ['@ 653,402 3848', '460'] (gold, amber,
                               # silver); x2 drops the gold number
FIELD_COST = (100, 10)         # LIVE: (gold, amber) on the Field tile and the radial cost pill (12/16)
OCR_SCALE = 3
# --- placement mode: radial menu (hm_field_tap / hm_field_build / hm_field_confirmed) ---
CHECK_WIN = (970, 440, 1210, 680)  # LIVE: search window for the green check; measured check disc
                                   # centre (1090,558), r~31 (y 527..589): brief (1090,565) inside,
                                   # (1090,520) above the disc. Green px: 226/223/241, median (1089,562)
CHECK_PX = (150, 600)          # LIVE: green-pixel count range of the check (226..241 measured)
X_DX = 247                     # LIVE: red X median (842,557) = check - (247, ~5); cancel disc (842,558)
X_PX = (150, 600)              # LIVE: red-pixel count of the X (256 on all three frames)
# --- world after the check: 'Tap to Complete' marker (hm_confirmed2) -------------
MARK_WIN = (700, 350, 1220, 800)   # LIVE: marker at (964,578) on hm_confirmed2; position follows the
                                   # camera, so a wide window around the screen centre
MARK_PX = 1000                 # LIVE: lemon-yellow disc (254,238,93): 2773 px within +-35 of the
                               # median on hm_confirmed2; <=154 on every WORLD frame in .spectre
                               # (yellow roof of shots-76112/dg_cam_5, trash/shots-53860/dg_*)
TOAST_CLOSE = (960, 1021)      # LIVE: 'Tap to close' text median (957,1021) on hm_spire_up (and the
                               # diamond info card hm_up2); NOT (960,654) = reward icon
TOAST_WORD = 'built'           # LIVE: full-frame OCR of hm_spire_up -> 'Field Built', 'Tapto Close'
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


def find_ring(img: Image.Image):
    """Placement radial menu: (check_xy, cancel_xy) from the green check and the
    red X found on the frame (count + geometry), else None."""
    green = _pixels(img, CHECK_WIN, lambda r, g, b: g - max(r, b) > 50 and g > 120)
    if not CHECK_PX[0] <= len(green) <= CHECK_PX[1]:
        return None
    gx, gy = _median(green)
    red = _pixels(img, (gx - X_DX - 40, gy - 40, gx - X_DX + 40, gy + 40),
                  lambda r, g, b: r - max(g, b) > 80 and r > 150)
    if not X_PX[0] <= len(red) <= X_PX[1]:
        return None
    rx, ry = _median(red)
    if abs(gx - rx - X_DX) > 15 or abs(gy - ry) > 10:
        return None
    return (gx, gy), (rx, ry)


def find_marker(img: Image.Image):
    """Yellow 'Tap to Complete' check disc over a finished build, else None."""
    pts = _pixels(img, MARK_WIN, lambda r, g, b: r > 235 and g > 210 and b < 120 and g - b > 120)
    if len(pts) < MARK_PX:
        return None
    mx, my = _median(pts)
    near = sum(abs(x - mx) <= 35 and abs(y - my) <= 35 for x, y in pts)
    return (mx, my) if near >= MARK_PX else None


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


def parse_counter(lines: list[str]):
    """(built, limit) from the Field tile ('12/16'), None unless 'Field' is read too."""
    if not any('field' in ln.lower() for ln in lines):
        return None
    for ln in lines:
        m = re.search(r'(\d{1,2})\s*/\s*(\d{1,2})', ln)
        if m and int(m.group(1)) <= int(m.group(2)):
            return int(m.group(1)), int(m.group(2))
    return None


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


def leave(img) -> None:
    """Back to the world: cancel a placement, Exit the menu, then reach_world."""
    ring = find_ring(img)
    if ring:
        v.tap(ring[1], 2.0)
        img = v.shot('hs_leave_x')
    if is_build_menu(img):
        v.tap(EXIT_BTN, 2.5)
    v.reach_world()


def open_menu(tag: str):
    """World -> Avalon Creator (Production tab). The menu frame, or the exit code."""
    if not v.reach_world():
        print('    ERROR: world view not reached', flush=True)
        return 1
    v.tap(v.GROUND, 0.8)                   # dismiss a selected building's radial
    img = v.shot(f'{tag}_world')
    if v.classify(img) != 'WORLD':
        print('    ERROR: not on the world view after the ground tap', flush=True)
        return 1
    if not build_btn(img):
        print('    Build button not on the world HUD - nothing to do', flush=True)
        return 4
    img = tap_until(BUILD_BTN, 2.5, f'{tag}_menu', is_build_menu,
                    lambda im: v.classify(im) == 'WORLD')
    if img is None:
        print('    ERROR: Avalon Creator menu not recognised after Build', flush=True)
        return 1
    if not production_active(img):
        img = tap_until(PRODUCTION_TAB, 1.5, f'{tag}_prod',
                        lambda im: is_build_menu(im) and production_active(im), is_build_menu)
        if img is None:
            print('    ERROR: Production tab not active after the tab tap', flush=True)
            return 1
    return img


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
    toast = tapped = False
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
            if toast or (tapped and not mark):
                return 0                   # the menu counter verifies it
            if mark:
                v.tap(mark, 2.5)
                tapped = True
            else:
                time.sleep(POLL_WAIT)      # still building
            continue
        text = ' '.join(v.ocr_lines(f'hs_b{k}_{n}')).lower()
        if TOAST_WORD in text or (toast and 'close' in text):
            toast = True                   # 'Field Built' / a reward info card on top of it
            v.tap(TOAST_CLOSE, 2.0)
            continue
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
        counter = parse_counter(ocr_scaled(name, FIELD_BOX, 'field')) if is_build_menu(img) else None
        if counter is None:
            print('    ERROR: Field counter not readable (LIVE: FIELD_BOX)', flush=True)
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
