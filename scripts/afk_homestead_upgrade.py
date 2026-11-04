#!/usr/bin/env python3
"""Homestead phase 2 (T103): start the Radiant Spire upgrade when 7/7 requirements are met.

Flow (frames: %LOCALAPPDATA%/hermes/cache/scratch/hm_requests, hm_req2 = world with
the Spire selected; hm_up3 = Spire Lvl.5 -> Lvl.6 dialog, 5/7):

  world (verified, Spire SELECTED) -> full-frame OCR with line boxes: the
  'Radiant Spire' label AND the radial 'Level Up' button (white disc + dark arrow
  above its text, found on the frame - the camera follows the hero, so never a
  fixed point) -> tap the disc -> dialog: OCR 'Upgrade Requirement (a/b)' +
  'Radiant Spire'; missing cards = no green check under the card label
  -> a < b: log the missing cards, close via the dialog's back plate, rc 4
  -> build queue 'n/m' (hammer, top right) full: close, rc 4
  -> a == b: tap the dialog's 'Level Up' (OCR-confirmed) -> world = started.

T103b (Hermes live 2026-11-04): an UNSELECTED upgradable Spire shows a floating white
disc with a dark up-arrow above the tower (spire_sel.png); its tap opens the dialog
directly (spire_sel2.png) -> spire_icon() searches it in the upper screen when no radial
is up. A start frame that already IS the Spire dialog (shots-82892/hu_world) is read
as is - no world needed.

T103c (operator live 22:28): a start frame showing 'exit the game?' (shots-9308) is cancelled
via its X; no radial and no icon (shots-80480: Kitchen selected after a 'Go', Spire bottom-left)
-> camera_search() (deselect + 2 bounded drags, LIVE-unverified); find_radial only takes a
'Level Up' whose 'Radiant Spire' label stands above it (never the Kitchen's radial).
Not implemented, noted: quest 'Upgrade the Ore Refinery to Level 5' = a further upgrade chain.

LIVE-open (no frame): the icon with the Spire elsewhere on screen / off screen, the
same icon on other buildings (topmost wins; OCR rejects their dialog), what 'Go'
opens (the missing-requirement recursion is NOT implemented), a 7/7 dialog, the screen after
'Level Up', the queue icon's meaning (busy/total assumed).

Never spends diamonds: 'Complete Now' (1800 diamonds) is never tapped - every tap
is checked against its plate - and a confirm dialog is always cancelled.
No keyevent BACK in here: in homestead menus it opens the exit-game dialog
(Hermes, live 2026-11-04); the dialog is left via its own back plate. An
unrecognised screen stops the run (rc 1) without a tap.

Usage: python scripts/afk_homestead_upgrade.py [--dry-run] [--min-idle S]
Exit codes: 0 upgrade started (dialog closed after Level Up), 1 stuck / unknown
screen, 4 nothing to do (no Level Up radial and no Spire upgrade icon after the camera search,
requirements missing, queue full, Level Up refused), 5 skipped (PC in use),
7 tap lock held by another run.
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bot_lock  # noqa: E402  (tap lock: one bot tapping at a time)
import afk_claim_vision as v  # noqa: E402
import afk_homestead as hs  # noqa: E402  (tap_until, _gmax)

# --- world: radial of the selected Spire (hm_requests / hm_req2, identical) ------
SPIRE_LABEL = 'radiant spire'  # LIVE: full-frame OCR box (851,173,97,17) 'Radiant Spire'; the
                               # label only shows while the Spire is selected (hm_confirmed2:
                               # hero at its door, no label, no radial)
RADIAL_WIN = (600, 300, 1320, 950)  # LIVE: 'Level Up' text box (922,731,75,19); the dialog's own
                                    # 'Level Up' (y 985) and the HUD stay outside
DISC_WIN = (80, 110, 15)       # disc search window around the OCR text centre: x +-80, y -110..-15.
                               # LIVE: the WinRT box can sit ~25 px off the drawn text
                               # (shots-67544/hs_0_world: box centre (932,738), text ~(958,740))
DISC_PX = 2000                 # LIVE: cream disc px (min>215, spread<30) in the window: 5025 / 5043 /
                               # 4941 (hm_requests / hm_req2 / hs_0_world); their median = disc centre
                               # (956,686) / (956,686) / (956,685)
DISC_DX = 42                   # LIVE: disc either side of the centre L>=227, dark arrow at the
                               # centre (112,94,94) L~99; a cloud (norm_3, 6118 px) has L>230 there
LABEL_DX = 150                 # T103c: the 'Radiant Spire' label must sit ABOVE the radial's 'Level Up'
                               # within +-LABEL_DX in x. LIVE label/text centres: hm_requests (899,181)/
                               # (959,740) dx 60, hs_0_world (948,175)/(932,738) dx 16, the KITCHEN's
                               # (shots-80480) (1061,332)/(1051,760) - a 'Radiant Spire' OCR line elsewhere
                               # (quest tracker x<270 y~900, chat) must not lend its label to that radial
WORLD_WIN = (120, 80, 1800, 860)  # world area for the label check: no HUD columns, no quest tracker
# --- world: floating 'upgrade' icon above an UNSELECTED Spire (T103b) --------------
# LIVE: Hermes 2026-11-04 spire_sel.png / shots-8632 hu_world: a white disc with a dark
# up-arrow floats above the tower; a tap opens the 'Upgrade Requirement' dialog directly
# (spire_sel2.png). Disc centre (916,171), radius ~27 (white to r 26, gone at r 28),
# disc (234,230,229), arrow (102,83,85): ~450 px L<120 within r 20, their median 3..8 px
# ABOVE the centre (arrow head). No text label there. The camera moves: searched, not fixed.
ICON_BAND = (300, 60, 1600, 540)  # candidate centres: upper screen (HUD columns/bottom bar outside)
ICON_STEP = 3                  # candidate grid; the ring test holds for +-3 px off the centre
ICON_RING = (20, 23)           # radii inside the disc: >= ICON_RING_MIN of 16 samples white each
ICON_RING_MIN = 13             # LIVE: 13..16 on the grid (b16b/end1: 13 - tower glow on the rim)
ICON_OUT = 33                  # radius outside the disc: <= ICON_OUT_MAX of 16 white (bounded disc,
ICON_OUT_MAX = 3               # not a cloud / cream panel); LIVE: 0/16
ICON_DARK = (250, 700)         # L<120 px within r 20 (arrow); LIVE: 442..456 at +-3 px
ICON_HEAD = 26                 # widest dark row within r 20 = the arrow head's base; LIVE 29..32.
                               # Look-alikes: placement 'i' scroll disc (pl3) 19..24, helmet
                               # plate (livecheck/c0) 18..19 - both pass ring/out/dark
ICON_CLUSTER = 40              # hits this close to the first hit belong to the same icon
# --- T103c camera search: no radial, no icon -> deselect (GROUND) + up to 2 drags, icon re-searched.
# LIVE-unverified (no frame of a drag): that a drag pans the homestead camera at all, and the
# distances. shots-80480/hu_world (after the operator's 'Go' to the Kitchen): Kitchen selected,
# Spire door (512,705) vs (920,460) on the icon frames (spire_sel/shots-8632), ~1.1x zoom ->
# the icon would sit near (507,373), ON screen - and there is none there, so the icon is most
# likely ABSENT while another building has the focus (not just off the top edge); the deselect
# is the more promising step. Drag 1 = the brief's 'content down' (icon above the top edge),
# drag 2 = content right+up = back towards the usual Spire spot (80480: door -> ~(862,795), icon
# ~(858,506) inside ICON_BAND). Points on mid-screen ground: off the HUD (x 120..1800,
# y 80..1000), off the joystick (960,835) and the quest tracker; 350/408 px over 600 ms = a drag.
CAMERA_DRAGS = ((1300, 350, 1300, 650), (1150, 650, 1500, 440))
CAMERA_MS = 600
# --- Spire dialog (hm_up3; same layout on shots-62772/80500 hl_entry*) -------------
REQ_RE = re.compile(r'requirement\D{0,4}(\d)\s*/\s*(\d)', re.I)  # LIVE: 'Upgrade Requirement (5/7)'
CARD_ROW = (590, 625)          # LIVE: card label boxes y 601..617 ('Level 5 Kitchen' .. 'AFK stage: 80')
CHECK_BOX = (22, 14, 47)       # LIVE: green check under a met card: x +-22 around the label
                               # centre, y label top +14..+47 -> 100..103 green px on all 5 met
                               # cards, 0 on 'Level 5 Kitchen' / '3704/28K' (hm_up3, hl_entry)
CHECK_PX = 40
QUEUE_BOX = (1430, 80, 1495, 110)  # LIVE: hammer queue text '0/2' box (1451,91,22,12)
LEVEL_UP_BTN = (1252, 1000)    # LIVE: 'Level Up' text box (1201,985,102,29), plate x 1005..1488
BACK_PLATE = (478, 1007)       # LIVE: cream back plate x 432..525 y ~967..1046, corners L247-250,
                               # dark arrow at the centre L149; brief (490,995) is on the plate too
BACK_CORNERS = ((445, 980), (510, 980), (445, 1035), (510, 1035))
COMPLETE_NOW = (538, 967, 1005, 1047)  # LIVE: 1800-diamond plate (brief x 538-1005 / y 967-1047,
                                       # grey plate from x 539) - NEVER tapped
BTN_NEAR = 40                  # an OCR 'Level Up' box centre must be this close to LEVEL_UP_BTN


def _centre(b):
    return b[0] + b[2] // 2, b[1] + b[3] // 2


def _tap(xy, wait: float) -> None:
    """Every tap of this module: never inside the 'Complete Now' plate."""
    l, t, r, b = COMPLETE_NOW
    if l <= xy[0] <= r and t <= xy[1] <= b:
        raise RuntimeError(f'refusing a tap on Complete Now (diamonds): {xy}')
    v.tap(xy, wait)


def _line(boxes, word: str, win=None):
    for b in boxes:
        cx, cy = _centre(b)
        if word in b[4].lower() and (win is None or (win[0] <= cx <= win[2] and win[1] <= cy <= win[3])):
            return b
    return None


def disc_at(img, xy) -> bool:
    """Radial 'Level Up' disc: dark arrow at xy, cream disc left and right of it."""
    x, y = xy
    return (v.lum(v.avg(img, xy, r=3)) < 140
            and all(v.lum(v.avg(img, (x + dx, y), r=3)) > 200 for dx in (-DISC_DX, DISC_DX)))


def find_radial(img, boxes):
    """Tap point of the selected Spire's 'Level Up' disc, else None. T103c: the 'Radiant Spire'
    label must belong to this radial (above it, LABEL_DX) - another building's radial (Kitchen,
    shots-80480) is never taken for the Spire's."""
    lu = _line(boxes, 'level up', RADIAL_WIN)
    if lu is None:
        return None
    cx, cy = _centre(lu)
    if not any(abs(_centre(b)[0] - cx) <= LABEL_DX and _centre(b)[1] < cy
               for b in boxes if SPIRE_LABEL in b[4].lower()):
        return None
    dx, up, down = DISC_WIN
    pts = hs._pixels(img, (cx - dx, cy - up, cx + dx, cy - down),
                     lambda r, g, b: min(r, g, b) > 215 and max(r, g, b) - min(r, g, b) < 30)
    if len(pts) < DISC_PX:
        return None
    xy = hs._median(pts)
    return xy if disc_at(img, xy) else None


def _white(c) -> bool:
    return min(c) > 200 and max(c) - min(c) < 40


def _ring(r):
    return [(round(r * math.cos(k * math.pi / 8)), round(r * math.sin(k * math.pi / 8))) for k in range(16)]


_RINGS = [_ring(r) for r in ICON_RING]
_OUT = _ring(ICON_OUT)
_DISC20 = [(dx, dy) for dx in range(-20, 21) for dy in range(-20, 21) if dx * dx + dy * dy <= 400]


def _icon_at(px, x, y) -> bool:
    if not all(_white(px[x + dx, y + dy]) for dx, dy in (_RINGS[1][0], _RINGS[1][4], _RINGS[1][8])):
        return False                                      # cheap prefilter: right/bottom/left
    if any(sum(_white(px[x + dx, y + dy]) for dx, dy in ring) < ICON_RING_MIN for ring in _RINGS):
        return False
    if sum(_white(px[x + dx, y + dy]) for dx, dy in _OUT) > ICON_OUT_MAX:
        return False
    dark = sorted(dy for dx, dy in _DISC20 if v.lum(px[x + dx, y + dy]) < 120)
    return (ICON_DARK[0] <= len(dark) <= ICON_DARK[1] and dark[len(dark) // 2] < -1  # head up
            and max(dark.count(dy) for dy in set(dark)) >= ICON_HEAD)


def spire_icon(img):
    """Centre of the floating white-disc/dark-up-arrow upgrade icon in ICON_BAND, else None.
    shortcut: several such icons on screen -> the topmost one; the dialog OCR ('Radiant Spire')
    rejects another building's dialog. Upgrade if live shows icons on other buildings."""
    px = img.convert('RGB').load()
    l, t, r, b = ICON_BAND
    hits = [(x, y) for y in range(t, b, ICON_STEP) for x in range(l, r, ICON_STEP) if _icon_at(px, x, y)]
    if not hits:
        return None
    return hs._median([p for p in hits if max(abs(p[0] - hits[0][0]), abs(p[1] - hits[0][1])) <= ICON_CLUSTER])


def camera_search():
    """T103c: no radial and no icon on the start frame -> deselect (GROUND), then up to
    len(CAMERA_DRAGS) drags; spire_icon after each, only on the world view.
    (icon xy or None, last frame)."""
    _tap(v.GROUND, 0.8)
    for i, drag in enumerate((None, *CAMERA_DRAGS)):
        if drag:
            v.swipe(*drag, CAMERA_MS, 1.5)
        img = v.shot(f'hu_cam{i}')
        if v.classify(img) != 'WORLD':
            return None, img
        xy = spire_icon(img)
        if xy:
            return xy, img
    return None, img


def parse_requirement(boxes):
    """(met, total) of the Spire dialog, None unless 'Radiant Spire' is on it too."""
    if _line(boxes, SPIRE_LABEL) is None:
        return None
    for b in boxes:
        m = REQ_RE.search(b[4])
        if m and int(m.group(1)) <= int(m.group(2)):
            return int(m.group(1)), int(m.group(2))
    return None


def missing_cards(img, boxes) -> list[str]:
    """Labels of the requirement cards without a green check."""
    out = []
    dx, y0, y1 = CHECK_BOX
    for b in boxes:
        cx, cy = _centre(b)
        if not CARD_ROW[0] <= cy <= CARD_ROW[1]:
            continue
        box = (cx - dx, b[1] + y0, cx + dx, b[1] + y1)
        if len(hs._pixels(img, box, lambda r, g, b_: g - max(r, b_) > 40)) < CHECK_PX:
            out.append(b[4])
    return out


def parse_queue(boxes):
    """(n, m) of the hammer build-queue counter, else None. LIVE: n = busy assumed."""
    for b in boxes:
        cx, cy = _centre(b)
        m = re.fullmatch(r'\s*(\d)\s*/\s*(\d)\s*', b[4])
        if m and QUEUE_BOX[0] <= cx <= QUEUE_BOX[2] and QUEUE_BOX[1] <= cy <= QUEUE_BOX[3]:
            return int(m.group(1)), int(m.group(2))
    return None


def back_plate(img) -> bool:
    return (all(v.lum(v.avg(img, p, r=4)) > 235 for p in BACK_CORNERS)
            and v.lum(v.avg(img, BACK_PLATE, r=4)) < 180)


def close_dialog(img) -> bool:
    """Spire dialog -> world via its own back plate (never keyevent BACK). True on the world."""
    if v.classify(img) == 'WORLD':
        return True
    if not back_plate(img):
        print('    ERROR: no dialog back plate on the frame - not tapping', flush=True)
        return False
    img = hs.tap_until(BACK_PLATE, 2.0, 'hu_close', lambda im: v.classify(im) == 'WORLD', back_plate)
    if img is None:
        print('    ERROR: world not reached after the dialog back plate', flush=True)
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Homestead: start the Radiant Spire upgrade (no diamonds)')
    ap.add_argument('--dry-run', action='store_true', help='open the dialog, read it, close it')
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

    name = 'hu_world'
    img = v.shot(name)
    if v.is_confirm_dialog(img):                 # T103c: 'exit the game?' (shots-9308) - X only
        print('    confirm dialog on the start frame -> X (never the check)', flush=True)
        _tap(v.CONFIRM_CANCEL, 1.5)
        name = 'hu_world_c'
        img = v.shot(name)
    if v.classify(img) == 'WORLD':
        boxes = v.ocr_boxes(name)
        disc = find_radial(img, boxes)
        still = lambda im: v.classify(im) == 'WORLD' and disc_at(im, disc)  # noqa: E731
        if disc is None:                         # T103b: unselected Spire, floating icon
            disc = spire_icon(img)
            still = lambda im: v.classify(im) == 'WORLD' and spire_icon(im) is not None  # noqa: E731
        selected = _line(boxes, SPIRE_LABEL, WORLD_WIN) is not None
        if disc is None and not selected:        # T103c: another building focused / camera moved
            disc, img = camera_search()
            if v.classify(img) != 'WORLD':
                print('    ERROR: camera search left the world view - stopping without a tap', flush=True)
                return 1
            if disc:
                print(f'    upgrade icon at {disc} after the camera search', flush=True)
        if disc is None:
            why = ('Spire selected but no Level Up on its radial (upgrading / max?)' if selected else
                   'no Level Up radial and no upgrade icon, also after the camera search')
            print(f'    nothing to do: {why}', flush=True)
            return 4
        img = hs.tap_until(disc, 2.5, 'hu_dialog', lambda im: v.classify(im) != 'WORLD', still)
        if img is None:
            print(f'    ERROR: Spire dialog did not open after the tap at {disc}', flush=True)
            return 1
        img = v.shot('hu_read')                  # settled frame for OCR + check pixels
        boxes = v.ocr_boxes('hu_read')
    elif back_plate(img) and parse_requirement(boxes := v.ocr_boxes(name)):
        print('    Spire dialog already open', flush=True)  # T103b: live start frame shots-82892
    else:
        print('    ERROR: not on the world view or the Spire dialog (no BACK key in the homestead)',
              flush=True)
        return 1
    req = parse_requirement(boxes)
    if req is None:
        print(f'    ERROR: Spire dialog not recognised (OCR {[b[4] for b in boxes][:6]})', flush=True)
        close_dialog(img)
        return 1
    met, total = req
    queue = parse_queue(boxes)
    print(f'    Radiant Spire requirements {met}/{total}, build queue {queue}', flush=True)
    if met < total:
        print(f'    missing: {missing_cards(img, boxes)} - Go/recursion is LIVE-open', flush=True)
        return 4 if close_dialog(img) else 1
    if queue and queue[0] >= queue[1]:
        print('    build queue full', flush=True)
        return 4 if close_dialog(img) else 1
    lu = _line(boxes, 'level up')
    if lu is None or max(abs(a - b) for a, b in zip(_centre(lu), LEVEL_UP_BTN)) > BTN_NEAR:
        print('    ERROR: dialog Level Up button not read at its place', flush=True)
        close_dialog(img)
        return 1
    if args.dry_run:
        print('    dry run: 7/7, not tapping Level Up', flush=True)
        return 0 if close_dialog(img) else 1
    _tap(LEVEL_UP_BTN, 3.0)
    img = v.shot('hu_after')
    if v.is_confirm_dialog(img):
        _tap(v.CONFIRM_CANCEL, 1.5)               # never spend diamonds
        print('    confirm/purchase dialog after Level Up -> cancelled', flush=True)
        return 4 if close_dialog(v.shot('hu_cancelled')) else 1
    if v.classify(img) == 'WORLD':
        print('    upgrade started: dialog closed after Level Up (LIVE-open: 3 h timer)', flush=True)
        return 0
    if parse_requirement(v.ocr_boxes('hu_after')):
        print('    Level Up refused: dialog still up', flush=True)
        return 4 if close_dialog(img) else 1
    print('    ERROR: unknown screen after Level Up - stopping without a tap', flush=True)
    return 1


if __name__ == '__main__':
    sys.exit(main())
