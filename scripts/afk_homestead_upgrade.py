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

LIVE-open (no frame): selecting the Spire from an arbitrary world view (no
label/locator without a selection, the camera moves), what 'Go' opens (the
missing-requirement recursion is NOT implemented), a 7/7 dialog, the screen after
'Level Up', the queue icon's meaning (busy/total assumed).

Never spends diamonds: 'Complete Now' (1800 diamonds) is never tapped - every tap
is checked against its plate - and a confirm dialog is always cancelled.
No keyevent BACK in here: in homestead menus it opens the exit-game dialog
(Hermes, live 2026-11-04); the dialog is left via its own back plate. An
unrecognised screen stops the run (rc 1) without a tap.

Usage: python scripts/afk_homestead_upgrade.py [--dry-run] [--min-idle S]
Exit codes: 0 upgrade started (dialog closed after Level Up), 1 stuck / unknown
screen, 4 nothing to do (Spire not selected / no Level Up on its radial,
requirements missing, queue full, Level Up refused), 5 skipped (PC in use),
7 tap lock held by another run.
"""
from __future__ import annotations

import argparse
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
    """Tap point of the selected Spire's 'Level Up' disc, else None."""
    lu = _line(boxes, 'level up', RADIAL_WIN)
    if lu is None or _line(boxes, SPIRE_LABEL) is None:
        return None
    cx, cy = _centre(lu)
    dx, up, down = DISC_WIN
    pts = hs._pixels(img, (cx - dx, cy - up, cx + dx, cy - down),
                     lambda r, g, b: min(r, g, b) > 215 and max(r, g, b) - min(r, g, b) < 30)
    if len(pts) < DISC_PX:
        return None
    xy = hs._median(pts)
    return xy if disc_at(img, xy) else None


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

    img = v.shot('hu_world')
    if v.classify(img) != 'WORLD':
        print('    ERROR: not on the world view (no BACK key in the homestead)', flush=True)
        return 1
    boxes = v.ocr_boxes('hu_world')
    disc = find_radial(img, boxes)
    if disc is None:
        why = ('Spire selected but no Level Up on its radial (upgrading / max?)'
               if _line(boxes, SPIRE_LABEL) else
               'Spire not selected on the world view - selecting it is LIVE-open')
        print(f'    nothing to do: {why}', flush=True)
        return 4
    img = hs.tap_until(disc, 2.5, 'hu_dialog', lambda im: v.classify(im) != 'WORLD',
                       lambda im: v.classify(im) == 'WORLD' and disc_at(im, disc))
    if img is None:
        print('    ERROR: Spire dialog did not open after the Level Up disc', flush=True)
        return 1
    img = v.shot('hu_read')                      # settled frame for OCR + check pixels
    boxes = v.ocr_boxes('hu_read')
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
