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

T105A (BUILD-ALL, offline from 11 menu frames: Hermes hm_build_menu/hm_menu_now/menu17 + .spectre
shots-47000/67544/68276 hs_*_menu/read - all Production tab, identical layout):

  tile grid: slot s = x0 461 + 112*s (TILE_PITCH), up to TILE_SLOTS (9, the panel divider width);
  Production order Field | Mine | Logging Site | Elemental Altar (PRODUCTION_NAMES, positional).
  An AVAILABLE tile has a white lower body (TILE_WHITE gate, Field 5968 px); a tile at its limit
  is greyed (red 'Limit: N (Lvl.X Radiant Spire)' instead of a cost, 0 white px) - the gate, not
  OCR, decides. The shifted COUNTER_VARIANTS are Field-tuned (2-digit 'NN/16'): the short '1/1',
  '2/2' of slots 1..3 read None (all frames are greyed; a white single-digit counter was never
  seen) -> an unreadable non-Field tile is skipped (logged), only an unreadable Field is rc 1.
  A tile tap that leaves the menu unchanged, or a menu frame after the check, parks the tile
  (Exit plate, never BACK); a confirm dialog after the tile tap is cancelled (CONFIRM_CANCEL).
  per visit: menu -> scan white (and expected) slots: counter 'N/M' (COUNTER_VARIANTS shifted by
  112*s, vote) -> candidates = below the limit, affordable (Field: gold/wood from the resource
  bar; other tiles' costs are NOT read - the game's refusal / 'Insufficient resources' popup parks
  the tile), not parked -> build queue 'n/m' (hammer, QUEUE_VARIANTS) full -> stop -> Functions
  tab only when nothing on Production is buildable or the quest names a non-Production building
  (and on --dry-run, for calibration) -> order: quest tile first ('Build Field x16.' read from the
  quest pill on the world, QUEST_BOX), Production before Functions, left to right -> build_one on
  the tile (same flow as the Field) -> next visit verifies the counter (+1; a tile that went grey
  and unreadable at exactly its old limit counts as the limit).
  Bounded: MAX_BUILDS builds and MAX_BUILDS + 1 menu visits per run (a parked tile uses a visit).

LIVE-open (no frame): the Functions tab (active colour assumed green like Production, layout,
names via tile OCR, counters), any AVAILABLE non-Field tile (single-digit white counter read -
keep hs_*_read_s{N}_cnt* of the first live --dry-run; cost row / diamond icon on the tile; whether
its tap goes straight to placement, radial radius - find_ring is calibrated on the Field, no ring
on a still-open menu -> parked),
non-Field completion (toast word 'built', marker, build time; 'started' = rc 2 of build_one is
counted and verified by the counter), the 'Insufficient resources' popup in the build context
(seen only in Requests, rq3), queue semantics (busy/total assumed), more than 4 tiles / a second
page / scrolling, a building -> resource map for the 'resource situation' priority (only the
Field affordability skip exists), the Spire unlock text (limits rise after T105B, not parsed).

Usage: python scripts/afk_homestead.py [--dry-run] [--min-idle S]
Exit codes: 0 built (or started) and verified, 1 stuck / unknown screen / Field counter unreadable
(nothing built; a Build menu still up is left via Exit first), 4 nothing to do (every tile at its limit, resources short, all tiles parked,
queue full, Build not available, diamond/confirm dialog cancelled), 5 skipped (PC in use),
7 tap lock held by another run.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from collections import Counter
from pathlib import Path

from PIL import Image, ImageChops, ImageOps

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
# --- T105A build-all: tile grid, tabs, quest, queue (measured on the 11 menu frames, docstring) ---
TILE_X0 = 461                  # LIVE: Field tile left edge (tile y 652..831), hm_build_menu/hm_menu_now
TILE_PITCH = 112               # LIVE: bright tile runs at y 790: x 461-563 / 573-675 / 685-786 / 797-898
                               # on hm_build_menu, hm_menu_now and the .spectre hs_*_read frames
TILE_SLOTS = 9                 # LIVE: panel divider ends at x 1473 (hm_build_menu) -> 9 slots fit; only 4
                               # tiles ever seen, slots 4..8 measured 0 white px everywhere
TILE_BODY = (2, 742, 100, 830)  # relative to the slot's x0: lower body (counter tail, time, name, cost)
TILE_WHITE = 235               # LIVE: white px = min(r,g,b) > 235; per slot 0..8 [5968, 0, 0, ...] on all
TILE_WHITE_PX = 3000           # 11 menu frames (greyed tiles body L 137..164 -> 0 px). Non-menus hit
                               # more (hm_up3 3281+), but the gate only runs on is_build_menu frames
TILE_NAME = (4, 762, 99, 784)  # LIVE: name row relative to x0 ('Field' glyphs x 493..533, y 766..780);
                               # grey x3 + 20 px white border reads 'Field' (white tile) on 6 menu frames,
                               # no border reads [] there; greyed tiles read only WITHOUT the border
                               # ('Mine', 'Logging Site') -> bordered first, raw fallback. Functions only
PRODUCTION_NAMES = ('Field', 'Mine', 'Logging Site', 'Elemental Altar')  # LIVE: slot order, 11 frames
FUNCTIONS_TAB = (505, 605)     # LIVE hm_build_menu: inactive cream pill x 446..563 y 585..624, G-max -3
                               # on all 11 frames; the ACTIVE colour was never seen (assumed green)
TABS = (('production', PRODUCTION_TAB), ('functions', FUNCTIONS_TAB))
QUEST_BOX = (40, 890, 300, 945)  # LIVE: quest pill bottom-left, white text on orange: min channel
QUEST_WHITE = 200              # > 200 -> black, x2 LANCZOS first, 20 px border: 21/21 world frames read
                               # (b16a/reset2 'build field x16.', end1 'upgrade the ore refinery ...',
                               # hm_requests 'respond to speed-up ...'); 170 garbles, raw crops garble
Q1, Q2 = (1440, 84, 1485, 108), (1445, 86, 1480, 106)
QUEUE_VARIANTS = ((Q1, 3, ''), (Q1, 5, ''), (Q2, 3, ''), (Q2, 4, ''), (Q2, 5, ''), (Q1, 5, 'pad'),
                  (Q2, 4, 'pad'))  # LIVE: hammer queue '0/2' (glyphs x 1450-1473, y 90-103): 11/11
QUEUE_BW = 200                 # menu frames vote (0,2); weakest shots-67544/hs_1_read 2 votes; bw 170
                               # lost that frame
INSUF_X = (960, 732)           # LIVE: rq3 only (Requests context, 1 source row): X disc of 'Insufficient
INSUF_WORD = 'insufficient'    # resources. You can obtain them from:'; is_confirm_dialog(rq3) is False.
INSUF_DISC_DX = 25             # LIVE rq3: X glyph L 91..94 (r 2..4), white disc L 246..250 at +-15..35 px;
INSUF_GLYPH_LUM = 140          # more source rows would move the X down -> the gate fails, no blind tap
INSUF_DISC_LUM = 230


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


# T105b (Hermes live, shots-79896/hs_0_menu = scratch/t105b_diag): 'Avalon Creator menu not recognised
# after Build' - the menu had opened in LAYOUT mode (decoration grid, 'Multiselect'/'Foundation', Save):
# it keeps its last mode. Layout mode = Build pill cream (G-max -7, L222) + Layout pill green (G-max 39,
# L157); Build mode is the reverse (hm_build_menu, shots-47000/67544/68276). Sweep of 149 frames: layout
# mode only on shots-79896, t105b_diag, final16, reset1. Its 'Build' pill sits at BUILD_TAB (~902,1022 on
# shots-79896); 'Save' (~1466,1010) is never tapped.
MODE_POLLS = 3                 # reads after the Build tap: fade-in, or the mode switch
MODE_WAIT = 1.5
MENU_WORDS = ('avalon creator', 'functions', 'production', 'multiselect', 'foundation')


def layout_mode(img: Image.Image) -> bool:
    b, lay = v.avg(img, BUILD_TAB), v.avg(img, LAYOUT_TAB)
    return (v.lum(v.avg(img, EXIT_BTN)) > 170 and _gmax(lay) > 25 and v.lum(lay) > 130
            and v.lum(b) > 200 and _gmax(b) < 10)


def to_build_mode(img: Image.Image, tag: str):
    """T105b: a frame right after opening the Avalon Creator -> the Build-mode menu frame, else None.
    Layout mode -> its 'Build' pill (once per read, bounded); anything else (still fading in) -> read
    again MODE_WAIT later. No tap unless the frame IS the layout-mode menu."""
    for i in range(MODE_POLLS):
        if is_build_menu(img):
            return img
        if layout_mode(img):
            print('    Avalon Creator opened in Layout mode -> Build pill', flush=True)
            v.tap(BUILD_TAB, 2.0)
        else:
            time.sleep(MODE_WAIT)
        img = v.shot(f'{tag}_m{i}')
    if is_build_menu(img):
        return img
    words = [w for w in MENU_WORDS if w in ' '.join(v.ocr_lines(f'{tag}_m{MODE_POLLS - 1}')).lower()]
    print(f'    Avalon Creator not in Build mode after {MODE_POLLS} reads (menu words {words})', flush=True)
    return None


def production_active(img: Image.Image) -> bool:
    return _gmax(v.avg(img, PRODUCTION_TAB)) > 25


def functions_active(img: Image.Image) -> bool:
    """LIVE-open: assumed green like the active Production tab."""
    return _gmax(v.avg(img, FUNCTIONS_TAB)) > 25


def tile_xy(slot: int) -> tuple[int, int]:
    return FIELD_TILE[0] + TILE_PITCH * slot, FIELD_TILE[1]


def white_tile(img: Image.Image, slot: int) -> bool:
    """Build-menu tile `slot` is available (white body), not greyed at its limit / empty."""
    x0, (l, t, r, b) = TILE_X0 + TILE_PITCH * slot, TILE_BODY
    return len(_pixels(img, (x0 + l, t, x0 + r, b),
                       lambda r_, g, b_: min(r_, g, b_) > TILE_WHITE)) >= TILE_WHITE_PX


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


def read_counter(name: str, dx: int = 0, variants=COUNTER_VARIANTS, bw: int = COUNTER_BW,
                 tag: str = 'cnt') -> tuple[int, int] | None:
    """Field counter of the saved menu shot `name` (T102b): every variant crop is saved as
    `{name}_{tag}{i}` and OCR'd on its own, then counter_votes decides. T105A: dx shifts the
    boxes to another tile slot; QUEUE_VARIANTS read the build queue the same way."""
    try:
        with Image.open(v.TMP / f'{name}.png') as im:
            src = im.convert('RGB')
    except (OSError, ValueError):
        src = None               # ocr_lines then finds no variant file and returns []
    reads = []
    for i, ((l, t, r, b), scale, mode) in enumerate(variants):
        if src is not None:
            g = ImageOps.grayscale(src.crop((l + dx, t, r + dx, b)))
            g = g.resize((g.width * scale, g.height * scale), Image.Resampling.LANCZOS)
            if mode:
                g = g.point(lambda p: 0 if p > bw else 255)
            if mode == 'pad':
                g = ImageOps.expand(g, border=40, fill=255)
            g.save(v.TMP / f'{name}_{tag}{i}.png')
        reads.append(v.ocr_lines(f'{name}_{tag}{i}'))
    return counter_votes(reads)


def tile_counter(name: str, slot: int):
    return read_counter(name) if slot == 0 else read_counter(name, TILE_PITCH * slot, tag=f's{slot}_cnt')


def tile_name(name: str, tab: str, slot: int) -> str:
    """Production: positional PRODUCTION_NAMES. Otherwise (Functions, LIVE-open) OCR of the
    tile's name row (grey, x3), 'tile N' when unreadable."""
    if tab == 'production' and slot < len(PRODUCTION_NAMES):
        return PRODUCTION_NAMES[slot]
    x0, (l, t, r, b) = TILE_X0 + TILE_PITCH * slot, TILE_NAME
    try:
        with Image.open(v.TMP / f'{name}.png') as im:
            g = ImageOps.grayscale(im.convert('RGB').crop((x0 + l, t, x0 + r, b)))
        g = g.resize((g.width * 3, g.height * 3), Image.Resampling.LANCZOS)
        ImageOps.expand(g, border=20, fill=255).save(v.TMP / f'{name}_s{slot}_name.png')
        g.save(v.TMP / f'{name}_s{slot}_name_raw.png')
    except (OSError, ValueError):
        pass
    lines = v.ocr_lines(f'{name}_s{slot}_name') or v.ocr_lines(f'{name}_s{slot}_name_raw')
    return lines[0].strip() if lines else f'tile {slot}'


def quest_text(name: str) -> str:
    """Quest pill of the saved world shot `name`, lower case ('' when unreadable / no file)."""
    try:
        with Image.open(v.TMP / f'{name}.png') as im:
            r, g, b = im.convert('RGB').crop(QUEST_BOX).split()
        m = ImageChops.darker(ImageChops.darker(r, g), b)     # white text = high min channel
        m = m.resize((m.width * 2, m.height * 2), Image.Resampling.LANCZOS)
        m = m.point(lambda p: 0 if p > QUEST_WHITE else 255)
        ImageOps.expand(m, border=20, fill=255).save(v.TMP / f'{name}_quest.png')
    except (OSError, ValueError):
        pass
    return ' '.join(v.ocr_lines(f'{name}_quest')).lower()


def quest_first(quest: str, label: str) -> bool:
    """A 'Build <label> xN.' quest makes that tile the first candidate."""
    return 'build' in quest and label.lower() in quest


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
    if is_build_menu(img) or layout_mode(img):
        print('    Build menu already open', flush=True)
        img = to_build_mode(img, f'{tag}_start')
        if img is None:
            return 1
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
    img = tap_until(BUILD_BTN, 2.5, f'{tag}_menu', lambda im: v.classify(im) != 'WORLD',
                    lambda im: v.classify(im) == 'WORLD')
    img = img and to_build_mode(img, f'{tag}_menu')   # T105b: Layout mode / fade-in
    if img is None:
        print('    ERROR: Avalon Creator menu not recognised after Build', flush=True)
        return 1
    return production_menu(img, tag)


def insufficient(k: int, img) -> int:
    """T105A: 'Insufficient resources' popup (frame img, rq3 layout, LIVE-open in the build context)
    -> its X, then out of the menu. 3 (park the tile), or 1 when the X disc is not where rq3 has it
    (no tap) or the X leads to an unknown screen."""
    x, y = INSUF_X
    if not (v.lum(v.avg(img, INSUF_X, r=4)) < INSUF_GLYPH_LUM and all(
            v.lum(v.avg(img, (x + dx, y + dy), r=2)) > INSUF_DISC_LUM for dx, dy in (
                (INSUF_DISC_DX, 0), (-INSUF_DISC_DX, 0), (0, INSUF_DISC_DX), (0, -INSUF_DISC_DX)))):
        print('    ERROR: insufficient resources popup, but its X is not at the rq3 spot - no tap',
              flush=True)
        return 1
    print('    insufficient resources popup -> X, tile parked', flush=True)
    v.tap(INSUF_X, 1.5)
    img = v.shot(f'hs_b{k}_insuf')
    if not (is_build_menu(img) or find_ring(img)):
        print('    ERROR: unknown screen after the insufficient-popup X', flush=True)
        return 1
    leave(img)
    return 3


def build_one(k: int, xy=FIELD_TILE) -> int:
    """Menu up (verified) -> the tile at xy placed and completed, back on the world.
    0 done, 2 started but not finished in the poll budget (long build), 3 refused / insufficient /
    no radial on a still-open menu (park the tile, menu left), 4 confirm dialog cancelled (stop the
    run), 1 stuck (unknown screen)."""
    name, seen = f'hs_b{k}_place', []

    def placed(im) -> bool:
        seen.append(im)
        return find_ring(im) is not None

    img = tap_until(xy, 2.5, name, placed, is_build_menu)
    if img is None:
        img, name = seen[-1], (name if len(seen) == 1 else f'{name}_r')   # the last frame tap_until saw
        if v.is_confirm_dialog(img):
            v.tap(v.CONFIRM_CANCEL, 1.5)       # never spend diamonds
            print('    confirm/purchase dialog after the tile tap -> cancelled, stopping', flush=True)
            leave(v.shot(f'hs_b{k}_cancelled'))
            return 4
        if INSUF_WORD in toast_text(name):
            return insufficient(k, img)
        if is_build_menu(img):
            print('    no placement radial after the tile tap (menu still up, LIVE-open) - parked',
                  flush=True)
            leave(img)
            return 3
        print('    ERROR: no placement radial after the tile tap', flush=True)
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
                return 3
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
        if is_build_menu(img):             # LIVE-open: never seen after a check tap
            print('    back in the Build menu after the check (LIVE-open) - tile parked', flush=True)
            leave(img)
            return 3
        text = toast_text(f'hs_b{k}_{n}')
        if INSUF_WORD in text:
            return insufficient(k, img)
        if TOAST_WORD in text:             # 'Field Built' (+ a reward info card on top of it)
            return 0 if close_toast(text, f'hs_b{k}') is not None else 1
        print(f'    ERROR: unknown screen while building (OCR {text[:60]!r})', flush=True)
        return 1
    if not tapped:
        print('    started, still building (long build, LIVE-open) - the counter verifies it',
              flush=True)
        return 2
    print('    ERROR: build did not finish within the poll budget', flush=True)
    return 1


def scan(img, name: str, tab: str, expect: dict, parked: set):
    """T105A: tiles of one build-menu tab (frame `img`, saved as `name`) -> (candidates, unreadable,
    frame, shot name) or 1 (stuck). Read: white slots + slots built this run (expect[(tab, slot)] =
    (n, old limit)). A None / unexpected read gets ONE settled re-read (T102b). Candidates:
    (tab, slot, label, have, limit) below the limit, affordable (Field), not parked."""
    def todo(im):
        return [s for s in range(TILE_SLOTS) if white_tile(im, s) or (tab, s) in expect]

    def off(s, got):
        return got is None or ((tab, s) in expect and got[0] != expect[(tab, s)][0])

    menu = is_build_menu(img)
    reads = {s: tile_counter(name, s) for s in todo(img)} if menu else {}
    bad = [s for s, got in reads.items() if off(s, got)]
    if bad or not menu:
        print(f'    {tab} counters {[reads[s] for s in bad]} - settling, one re-read', flush=True)
        time.sleep(COUNTER_SETTLE)
        name = f'{name}2'
        img = v.shot(name)
        if not is_build_menu(img):
            print('    ERROR: Build menu not recognised on the read frame', flush=True)
            return 1
        for s in (bad if menu else todo(img)):
            reads[s] = tile_counter(name, s)
    cands, unreadable = [], False
    for s, got in sorted(reads.items()):
        label, want = tile_name(name, tab, s), expect.get((tab, s))
        if want and got is None and want[0] == want[1] and not white_tile(img, s):
            print(f'    {label} {want[0]}/{want[1]} - limit reached (tile greyed)', flush=True)
            continue
        if want and (got is None or got[0] != want[0]):
            print(f'    ERROR: {label} counter {got}, expected {want[0]} after the build', flush=True)
            leave(v.shot(f'{name}_fail'))
            return 1
        if got is None:
            print(f'    {label} counter not readable (LIVE: COUNTER_VARIANTS)', flush=True)
            # only the calibrated Field makes the run stuck; another white tile is skipped (LIVE-open
            # short 'N/M' counters), so the watch still writes its daily marker
            unreadable |= tab == 'production' and s == 0
            continue
        have, limit = got
        if have >= limit:
            print(f'    {label} {have}/{limit} - at the limit', flush=True)
            continue
        if tab == 'production' and s == 0:
            res = parse_resources(ocr_scaled(name, RES_BOX, 'res'))
            if res is not None and (res[0] < FIELD_COST[0] or res[1] < FIELD_COST[1]):
                print(f'    {label} {have}/{limit}: resources short (gold/amber {res})', flush=True)
                continue
        if (tab, s) in parked:
            print(f'    {label} {have}/{limit} - parked this run', flush=True)
            continue
        print(f'    {label} {have}/{limit}', flush=True)
        cands.append((tab, s, label, have, limit))
    return cands, unreadable, img, name


def stuck(tag: str) -> int:
    """rc 1 after the menu was verified: a menu / placement still up is left via X / Exit, so the
    watch's next normalize never sends BACK inside it (T102b: BACK there = exit-game dialog)."""
    img = v.shot(f'{tag}_stuck')
    if is_build_menu(img) or find_ring(img):
        leave(img)
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Homestead: build every build-menu tile up to its limit')
    ap.add_argument('--dry-run', action='store_true', help='open the menu, read both tabs, exit')
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

    built, expect, pending, parked, quest, unreadable = 0, {}, set(), set(), '', False
    func_tab = dict(TABS).get('functions')
    for k in range(MAX_BUILDS + 1):
        tag = f'hs_{k}'
        img = open_menu(tag)
        if isinstance(img, int):
            return img if not built else 1
        if k == 0:
            quest = quest_text(f'{tag}_world')      # '' when the menu was already open
            print(f'    quest: {quest!r}', flush=True)
        name = f'{tag}_read'
        got = scan(v.shot(name), name, 'production', expect, parked)
        if isinstance(got, int):
            return got
        cands, bad, img, name = got
        unreadable |= bad
        pending -= {key for key in pending if key[0] == 'production'}
        queue = read_counter(name, variants=QUEUE_VARIANTS, bw=QUEUE_BW, tag='q')
        if queue is None:
            print('    build queue unreadable', flush=True)
        why = None
        if queue and queue[0] >= queue[1]:
            why = f'build queue full ({queue[0]}/{queue[1]})'
        elif func_tab and (args.dry_run or not cands or (
                'build' in quest and not any(n.lower() in quest for n in PRODUCTION_NAMES))):
            img2 = tap_until(func_tab, 1.5, f'{tag}_func',
                             lambda im: is_build_menu(im) and functions_active(im),
                             lambda im: is_build_menu(im) and not functions_active(im))
            if img2 is None:
                img = v.shot(f'{tag}_func_chk')
                if not is_build_menu(img):
                    print('    ERROR: unknown screen after the Functions tab tap', flush=True)
                    return 1
                print('    Functions tab did not switch (LIVE-open) - Production only', flush=True)
            else:
                fname = f'{tag}_fread'
                got = scan(v.shot(fname), fname, 'functions', expect, parked)
                if isinstance(got, int):
                    return got
                fcands, bad, img, _ = got
                cands, unreadable = cands + fcands, unreadable or bad
                pending -= {key for key in pending if key[0] == 'functions'}
        cands.sort(key=lambda c: (not quest_first(quest, c[2]), c[0] != 'production', c[1]))
        if why is None:
            why = ('dry run' if args.dry_run else 'nothing to build' if not cands
                   else 'run cap reached' if built >= MAX_BUILDS or k == MAX_BUILDS else None)
        if why:
            print(f'    stop: {why}', flush=True)
            if pending:      # shortcut: a tab not re-scanned keeps its builds unverified
                print(f'    unverified builds (tab not re-read): {sorted(pending)}', flush=True)
            leave(v.shot(f'{tag}_exit'))
            return 0 if built or args.dry_run else 1 if unreadable else 4
        tab, slot, label, have, limit = cands[0]
        if tab == 'production' and not production_active(img):
            img = production_menu(img, tag)
            if isinstance(img, int):
                return stuck(tag)
        rc = build_one(k, tile_xy(slot))
        if rc == 3:
            parked.add((tab, slot))
            print(f'    {label} parked for this run', flush=True)
            continue
        if rc == 4:
            return 0 if built else 4
        if rc == 1:
            return stuck(tag)
        built += 1
        expect[(tab, slot)] = (have + 1, limit)
        pending.add((tab, slot))
        print(f'    built {label} {built} (expect {have + 1}/{limit})'
              + (' - started, still building' if rc == 2 else ''), flush=True)
    return 1                               # unreachable: k == MAX_BUILDS stops above


if __name__ == '__main__':
    sys.exit(main())
