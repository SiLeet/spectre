#!/usr/bin/env python3
"""Homestead phase 3 (T104): Golden Supplier requests - deliver them, cooking what is missing.

Frames (Hermes live 2026-11-05, %LOCALAPPDATA%/hermes/cache/scratch): rq2/rqp4 panel 0/4 with a
green 'Quick Select'; rq3 'Insufficient resources' popup (Quick Select with too few items);
rq4 3/4 after it; qs1 4/4 with the orange 'Deliver'; del1/post1 'Request Completed'; post3 the
next NPC ('No available items. Please produce some first.', grey plate); kz1 Kitchen list with
the red 'Requests' banner over Toast; cook4/made2 its Process Deck ('Stock: 3', 'Request: 4',
Make); made1 cooking; rqp/rqq Kitchen list without a banner; fin2/claim3 world with the Kitchen
selected ('Cook' radial).

Flow (bounded, every step verified on its frame, soft phase):
  world -> Requests HUD icon -> panel (OCR 'Basic/Star Rewards')
  -> loop (MAX_STEPS, MAX_DELIVER deliveries):
     orange 'Deliver' -> 'Request Completed' -> 'Tap to close' -> the slot's next NPC
     green 'Quick Select' (once per request) -> 'Insufficient resources' popup -> its X = short
     grey plate / 'No available items' = short
  -> first short: ONE kitchen trip (leave the panel, Kitchen 'Cook' radial, open up to MAX_DECKS
     recipe decks - banner cards first - and Make while Stock < Request, MAX_COOKS, stamina floor), panel
     again; still short -> the next NPC slot (SLOTS); no slot left -> leave.
Never tapped: 'Give Up' (refused by _tap), 'Auto', the x1/x3 steppers, Process Upgrade.
No keyevent BACK (homestead menus open the exit-game dialog): panel, deck and list are left
via their own back arrows. An unrecognised screen stops the run (rc 1) without a tap.

T104b (Hermes live, shots-42848): 'Kitchen not found' after the KITCHEN_BASE tap. The tap only
FOCUSED the Kitchen (brackets, camera unmoved, no labels) and drew two floating discs above its
roof, Cook + Level Up - the unselected-building grammar of T103b's spire_sel; a SELECTED Kitchen
always shows its labelled radial below the building (18 frames). Now: labelled Cook radial, else
(up to KITCHEN_POLLS reads after the tap) the floating Cook disc (FLOAT_WIN pair, only rq_ck_k of
87 world frames); a tap that merely selects the Kitchen gets its labelled radial once more; any
other dialog is closed via its back plate. Recipe cards are anchored on their OCR 'Select'
(green = enabled); the first banner card of a fresh read is cooked while Stock < Request (the
grid reflows when a banner clears); only when the list shows no banner at all, up to MAX_PROBES
lowest-stock decks are opened (Make only if the deck reads Request > Stock).
LIVE-open: the floating Cook disc tap, a non-requested recipe's deck.

T104c (Hermes live st0/st1, shots-3300): the camera after the panel is often elsewhere - the
Kitchen stall sits at the top edge (~(814,76)) and the Golden-Supplier NPC is still SELECTED
(screen-fixed 'Interact' radial at (959,738)), so the blind KITCHEN_BASE tap hit nothing. Of 214
tower frames only 41 put the Kitchen where a tap is safe. Now two bounded, soft fallback stages:
(1) find_kitchen anchors the Kitchen on the Spire tower (TOWER_TO_KITCHEN, +-60 px on 14 frames),
taps it inside KITCHEN_WIN, else drags the camera toward KITCHEN_BASE (content follows the finger,
59732) up to KITCHEN_DRAGS times, re-anchoring and trying the Cook disc after every drag (the
floating window follows the tap point); (2) spire_go: the T103f chain via hu.spire_dialog - the
'Go' under a MISSING 'Level N Kitchen' card lands on the selected Kitchen (kitchen_go, 80480).
Hermes' fixed 'south then west' swipes were replaced by the anchored drag: st0 needs the finger
down+right (226,329), the (1290,58) camera down+left (-250,352).

LIVE-open: the header 'n/5' (Hermes: 5 requests/day; post3 shows 4/5 after ONE delivery -
not used, MAX_DELIVER bounds the run); slot 2 (never tapped live); a banner with several
recipes. T104c: whether the Spire-Go stage is live at all (Kitchen is Level 5 on fin2/rq1/claim3,
the Spire 5->6 card asks 'Level 5 Kitchen' -> most likely met, no Go, soft end after tower /
Interact / back plate; no Spire-dialog frame since the Kitchen reached 5); whether a tap on the
tower-anchored point away from the shots-42848 camera focuses/selects the Kitchen and replaces the
supplier-NPC selection; whether a second drag converges (ratio 0.85..1.11, never run live);
a drag start on other cameras (a start on a building floor pans: 59732 hu_cam1 -> hu_cam2 from
the Kitchen tiles; a start on a quest bubble is unseen - only the Kitchen + fountain are kept
clear, DRAG_CLEAR); whether a dragged
camera snaps back (59732 cam1 -> cam2: stays >= ~3 s); the floating disc at shifted tap points;
the post-Go landing frame at Kitchen Level >= 5 (all post-Go frames are from Level 4).

Usage: python scripts/afk_homestead_requests.py [--no-cook] [--min-idle S]
Exit codes: 0 at least one request delivered, 1 stuck / unknown screen, 4 nothing to do
(no Requests icon, nothing deliverable after cooking), 5 skipped (PC in use), 7 tap lock held.
"""
from __future__ import annotations

import argparse
import math
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bot_lock  # noqa: E402  (tap lock: one bot tapping at a time)
import afk_claim_vision as v  # noqa: E402
import afk_homestead as hs  # noqa: E402  (_pixels, tap_until, TOAST_CLOSE)
import afk_homestead_upgrade as hu  # noqa: E402  (_centre, _line, small_disc_at, radial constants)

REQUESTS_BTN = (42, 672)       # LIVE: HUD icon x 20..65 y 650..700 above its 'Requests' label (rq1, fin2,
HUD_PROBE = (42, 659)          # sett1, claim3, rqp2, cook3); its cream frame top avg L 198..200 (r=3),
HUD_LUM = 170                  # zone2 (HUD hidden) L 48
PANEL_WORDS = ('basic rewards', 'star rewards')   # LIVE OCR on rq2/rqp4/qs1/rq4/post3
GREEN = lambda r, g, b: g - max(r, b) > 40        # noqa: E731  'Quick Select' (102,155,91)
ORANGE = lambda r, g, b: r > 215 and 110 < g < 190 and b < 110  # noqa: E731  'Deliver'
PLATE_HALF = (150, 25)         # colour window around the button's OCR centre
PLATE_PX = 6000                # LIVE: plate x 880..1221 y 880..949 (22090 green / 22669 orange px)
GIVE_UP = (680, 840, 800, 960)  # LIVE: 'Give Up' text (712,928) / (712,899 on post3) + its icon: never tapped
INSUF_X = (960, 732)           # LIVE rq3: X disc centre (glyph L 91, disc L 235 at 52 px above)
SLOTS = ((575, 1024), (675, 1024))  # LIVE: NPC portraits; slots 3/4 at x 778/878 are locked
SLOT_HALF = 52
RING_PX = 800                  # LIVE: green ring px of the selected slot 1688..1762, others 0
PANEL_BACK = (464, 1014)       # Hermes live (arrow x 450..490 y 1005..1045)
KITCHEN_BASE = (1040, 410)     # Hermes live: Kitchen building at the base camera (T104c: drag target, tap
                               # without a tower, FLOAT_WIN reference)
CARD_XS = (741, 888, 1035, 1183)  # LIVE kz1/rqp: Kitchen card centres (Select boxes)
BANNER = (455, 482, 40)        # red 'Requests' banner band y + half width over a card
BANNER_PX = 500                # LIVE: 779 over Toast on kz1; other cards 0..280 (rqp/rqq/kz1)
RED = lambda r, g, b: r > 150 and r - max(g, b) > 70  # noqa: E731
SELECT_HALF = (30, 8)          # T104b: green px around an OCR 'Select' centre: LIVE 657..671 on every
SELECT_PX = 300                # enabled card (rqp, kz1), 0 on the locked Dry Fruit cards (rqp)
BANNER_ROW_Y = 700             # Select of a card under the banner row (kz1: y 662; next row 905)
STOCK_DY = (10, 45)            # 'Stock: n' box centre this far above its card's 'Select' (LIVE 27)
MAX_DECKS = 6                  # T104b: recipe decks opened per Kitchen trip
MAX_PROBES = 3                 # T104b: decks of un-bannered cards, only when the list shows NO banner
CARD_TOL = 40                  # opened-card match: OCR 'Select' centres jitter by 1 px between reads
KITCHEN_POLLS = 3              # T104b: reads after a Kitchen tap
KITCHEN_LABEL_DX = 200         # T104b: 'Kitchen' label centre vs 'Cook' text: LIVE dx 102 (fin2..) / 164
                               # (shots-63328/hu_go, Cook read at x 912)
COOK_DX = 30                   # T104b: disc search +-x around the 'Cook' text (shots-63328/hu_go read it
                               # at x 912 instead of 938; disc still (951,708))
FLOAT_WIN = (790, 160, 1290, 380)  # T104b LIVE shots-42848/rq_ck_k: the KITCHEN_BASE tap only FOCUSED the
FLOAT_DX = (55, 95)            # Kitchen (brackets, camera unmoved, no labels) with two floating discs
FLOAT_DY = 8                   # above its roof, Cook (1075,298) + Level Up (1147,298) - the T103b
                               # spire_sel grammar. Such a pair in FLOAT_WIN: 1 of 87 world frames
                               # (only rq_ck_k). What the Cook disc tap opens is LIVE-unverified.
TOWER_TO_KITCHEN = (476, -92)  # T104c LIVE: KITCHEN_BASE - spire_tower(shots-42848/rq_ck_w) (564,502); that tap
                               # focused the Kitchen (rq_ck_k). Lands on the stall on 13 frames (59732 hu_world/cam2,
                               # fin2, kitchen_go, st0, st1, tower_tap, spire_sel, hm_requests, 80480/hu_world,
                               # 3300/rq_ck_w, world_now); +-60 px only near the centre (KITCHEN_WIN: 41 of 41 on the
                               # stall), drifts ~100 px with the tower low on screen (59732/hu_cam1: on the Interact
                               # disc, tower read off); post-Go frames read (981..991, 411..456)
KITCHEN_WIN = (740, 250, 1340, 570)  # T104c: the anchored Kitchen is tapped only here - its label and floating
                               # discs (112 px above, rq_ck_k) stay on screen, clear of the screen-fixed radial
                               # (Interact/Cook text (959,738), disc (958,690): tower_tap, 59732 hu_cam0..2, st1,
                               # fin2) and the HUD columns. LIVE sweep: 41 of 214 tower frames inside; st0/st1/3300
                               # (814,~76) and the (1290,~58) camera -> drag; 59732/hu_cam1 (924,664) = NPC Interact
KITCHEN_DRAGS = 2              # Hermes: at most 2 camera drags per trip
DRAG_FROM = tuple(d[:2] for d in hu.CAMERA_DRAGS)  # LIVE 59732: (1300,350) for a downward drag, (1150,650) upward
DRAG_STARTS = ((DRAG_FROM[0], (1450, 400)), (DRAG_FROM[1],))  # downward / upward, first one clear of the Kitchen
                               # + fountain wins. (1450,400): grass on spire_sel, hm_requests, hm_req2, hm_confirmed2,
                               # hm_built15, b16a, end1, tooltip, where (1300,350) is the fountain's stone rim
DRAG_CLEAR = 150               # min distance of a drag start from the anchored Kitchen and the fountain
FOUNTAIN_DXY = (-143, 140)     # LIVE: fountain/pavilion centre - Kitchen anchor (spire_sel (-156,138), tower_tap
                               # (-129,154)); on tower_tap both starts fail (bubble corner / fountain) -> no drag
DRAG_MAX = (450, 400)          # per-axis clip: st0 needs (226,329), the (1290,58) camera (-250,352); content/finger
                               # 0.85..1.11 by the Kitchen pin (59732: finger (0,+300) -> pin (-18,+254); (+350,-210)
                               # -> (+390,-222); the tower read on hu_cam1 is off ~(57,40), hence its 1.34)
                               # -> re-anchor after every drag
DRAG_END_MAX = (1600, 750)     # drag end clip off the right HUD column (st1 'Login Rewards' x 1690..1840 y 645..685)
DRAG_MIN = 100                 # smaller: the Kitchen is in place and did not answer -> Spire stage (selected /
                               # post-Go frames |d| 41..59)
MAKE = (960, 955)              # LIVE cook4/made2: mortar disc L 220, ring (900,955) L 105;
MAKE_RING = (900, 955)         # cooking (made1): cog L 150, ring L 245
KITCHEN_BACK = (470, 1000)     # Hermes live: deck -> list -> world
STAMINA_FLOOR = 1000           # brief: stamina sparingly (cap 3000, +610/day); 4 per Make
STAMINA_RE = re.compile(r'(\d{1,5})\s*/\s*(\d{4})')  # LIVE kz1 '3000/3000 +' (1380,18)
STOCK_RE = re.compile(r'stock\s*:\s*([\dO]+)', re.I)            # '*Stock: 3 i'
REQUEST_RE = re.compile(r're\w{1,5}st\s*:\s*([\dO]+)', re.I)    # '*Request : 4', "'Reqgest: 4"
MAX_DELIVER = 5                # Hermes: 5 requests a day
MAX_COOKS = 8                  # Makes per run (32 stamina)
MAX_STEPS = 12
OPEN_POLLS = 3
POLL_WAIT = 1.5
COOK_POLLS = 10                # x COOK_WAIT: LIVE 'Cooking..' ~25 s
COOK_WAIT = 5.0
CLOSE_TRIES = 3


def _tap(xy, wait: float) -> None:
    """Every tap of this module: never on 'Give Up'."""
    l, t, r, b = GIVE_UP
    if l <= xy[0] <= r and t <= xy[1] <= b:
        raise RuntimeError(f'refusing a tap on Give Up: {xy}')
    v.tap(xy, wait)


def is_panel(boxes) -> bool:
    """LIVE: the 'Request Completed' toast (del1) shows Basic/Star Rewards too."""
    return any(hu._line(boxes, w) for w in PANEL_WORDS) and not hu._line(boxes, 'completed')


def button(img, boxes):
    """('deliver' | 'quick', tap point) of an ENABLED panel button, else (None, None).
    The grey plate (post3, nothing to select) has neither colour."""
    for word, kind, pred in (('deliver', 'deliver', ORANGE), ('quick select', 'quick', GREEN)):
        b = hu._line(boxes, word)
        if b:
            cx, cy = hu._centre(b)
            dx, dy = PLATE_HALF
            if len(hs._pixels(img, (cx - dx, cy - dy, cx + dx, cy + dy), pred)) >= PLATE_PX:
                return kind, (cx, cy)
    return None, None


def slot_selected(img, k: int) -> bool:
    x, y = SLOTS[k]
    return len(hs._pixels(img, (x - SLOT_HALF, y - SLOT_HALF, x + SLOT_HALF, y + SLOT_HALF), GREEN)) >= RING_PX


def requested_cards(img) -> list[int]:
    """x of the Kitchen cards under a red 'Requests' banner (kz1), left to right."""
    t, b, dx = BANNER
    return [x for x in CARD_XS if len(hs._pixels(img, (x - dx, t, x + dx, b), RED)) >= BANNER_PX]


def kitchen_cards(img, boxes) -> list[tuple[int, int, int | None, bool]]:
    """T104b: (x, y, stock, under the banner) of every ENABLED recipe card, anchored on its OCR
    'Select' (green button; locked cards are grey), banner cards first, then lowest stock."""
    banner = requested_cards(img)
    dx, dy = SELECT_HALF
    out = []
    for b in boxes:
        if not b[4].lower().startswith('select'):
            continue
        cx, cy = hu._centre(b)
        if len(hs._pixels(img, (cx - dx, cy - dy, cx + dx, cy + dy), GREEN)) < SELECT_PX:
            continue
        stock = None
        for sb in boxes:
            m = STOCK_RE.search(sb[4])
            sx, sy = hu._centre(sb)
            if m and abs(sx - cx) <= 35 and STOCK_DY[0] <= cy - sy <= STOCK_DY[1]:
                stock = _num(m.group(1))
        req = cy < BANNER_ROW_Y and any(abs(cx - x) <= BANNER[2] for x in banner)
        out.append((cx, cy, stock, req))
    return sorted(out, key=lambda c: (not c[3], 10 ** 9 if c[2] is None else c[2], c[1], c[0]))


def make_ready(img) -> bool:
    return v.lum(v.avg(img, MAKE, r=3)) > 200 and v.lum(v.avg(img, MAKE_RING, r=3)) < 150


def _num(s: str) -> int:
    return int(s.replace('O', '0'))


def deck_counts(boxes):
    """(stock, request) on the Process Deck, None where unread."""
    text = ' '.join(b[4] for b in boxes)
    s, r = STOCK_RE.search(text), REQUEST_RE.search(text)
    return (_num(s.group(1)) if s else None), (_num(r.group(1)) if r else None)


def stamina(boxes):
    for b in boxes:
        m = STAMINA_RE.search(b[4])
        if m and b[0] > 1300 and b[1] < 70:
            return int(m.group(1))
    return None


def is_kitchen(boxes) -> bool:
    """Kitchen recipe list: 'What should I produce?' or several card 'Stock:' lines (kz1, rqp; the
    panel's 'Quick Select' / 'produce some first' on post3 is neither)."""
    return bool(hu._line(boxes, 'what should')) or sum(b[4].lower().startswith('stock') for b in boxes) >= 2


def is_deck(boxes) -> bool:
    return any(hu._line(boxes, w) for w in ('deck setup', 'process d', 'cooking'))


def cook_disc(img, boxes):
    """The selected Kitchen's 'Cook' radial disc (fin2: text (959,738), disc 30 px above), else None."""
    for b in boxes:
        if not b[4].lower().startswith('cook'):
            continue
        cx, cy = hu._centre(b)
        if not any('kitchen' in lb[4].lower() and abs(hu._centre(lb)[0] - cx) <= KITCHEN_LABEL_DX
                   and hu._centre(lb)[1] < cy for lb in boxes):
            continue
        hits = [(x, y) for y in (cy - hu.SMALL_DISC_DY, cy - hu.SMALL_DISC_DY + 4, cy - hu.SMALL_DISC_DY - 4)
                for x in range(cx - COOK_DX, cx + COOK_DX + 1, 3) if hu.small_disc_at(img, (x, y))]
        if hits:
            return hs._median(hits)
    return None


def floating_cook(img, at=KITCHEN_BASE):
    """T104b: the left (Cook) disc of a floating Cook / Level Up pair over a focused Kitchen, else None.
    T104c: FLOAT_WIN moves with the tapped Kitchen point `at`, kept 30 px inside the frame."""
    dx, dy = at[0] - KITCHEN_BASE[0], at[1] - KITCHEN_BASE[1]
    w, h = img.size
    l, t, r, b = (max(30, FLOAT_WIN[0] + dx), max(30, FLOAT_WIN[1] + dy),
                  min(w - 30, FLOAT_WIN[2] + dx), min(h - 30, FLOAT_WIN[3] + dy))
    groups = []
    for y in range(t, b, 3):
        for x in range(l, r, 3):
            if hu.small_disc_at(img, (x, y)):
                g = next((g for g in groups if abs(g[0][0] - x) <= 20 and abs(g[0][1] - y) <= 20), None)
                if g:
                    g.append((x, y))
                else:
                    groups.append([(x, y)])
    centres = sorted(hs._median(g) for g in groups)
    for a in centres:
        if any(FLOAT_DX[0] <= c[0] - a[0] <= FLOAT_DX[1] and abs(c[1] - a[1]) <= FLOAT_DY for c in centres):
            return a
    return None


def read(tag: str, ok):
    """Up to OPEN_POLLS shots until ok(boxes) (animations). (img, boxes, ok?)."""
    for i in range(OPEN_POLLS):
        if i:
            time.sleep(POLL_WAIT)
        name = tag if i == 0 else f'{tag}_p{i}'
        img = v.shot(name)
        boxes = v.ocr_boxes(name)
        if ok(boxes):
            return img, boxes, True
    return img, boxes, False


def open_panel(tag: str) -> bool:
    img = hs.tap_until(REQUESTS_BTN, 2.5, tag, lambda im: v.classify(im) != 'WORLD',
                       lambda im: v.classify(im) == 'WORLD')
    if img is None or not read(f'{tag}_r', is_panel)[2]:
        print('    ERROR: Requests panel did not open', flush=True)
        return False
    return True


def leave_panel(tag: str) -> bool:
    if hs.tap_until(PANEL_BACK, 2.0, tag, lambda im: v.classify(im) == 'WORLD',
                    lambda im: v.classify(im) != 'WORLD') is None:
        print('    ERROR: world not reached after the panel back arrow', flush=True)
        return False
    return True


def close_completed(tag: str) -> bool:
    """'Request Completed' -> 'Tap to close' until the panel is back (Hermes: sometimes twice; a
    dead tap -> one T97b retry). Taps only while the OCR still shows that toast."""
    retried = False
    for n in range(CLOSE_TRIES):
        name = f'{tag}_c{n}'
        if n and not retried:
            retried = True
            mode = v.tap_retry(hs.TOAST_CLOSE, 2.0)
            _, boxes, ok = read(name, is_panel)
            v.tap_result(mode, ok or not hu._line(boxes, 'completed'))
        else:
            v.tap(hs.TOAST_CLOSE, 2.0)
            _, boxes, ok = read(name, is_panel)
        if ok:
            return True
        if not (hu._line(boxes, 'completed') or hu._line(boxes, 'close')):
            break
    print('    ERROR: panel not back after Request Completed', flush=True)
    return False


def serve(tag: str) -> str:
    """One request of the current slot: 'delivered' | 'short' | 'error'."""
    quick = False
    for i in range(3):
        img, boxes, ok = read(f'{tag}_{i}', is_panel)
        if not ok:
            print(f'    ERROR: not on the Requests panel (OCR {[b[4] for b in boxes][:6]})', flush=True)
            return 'error'
        kind, xy = button(img, boxes)
        if kind == 'deliver':
            print(f'    Deliver at {xy}', flush=True)
            _tap(xy, 3.0)
            _, boxes, ok = read(f'{tag}_{i}_done', lambda bx: bool(hu._line(bx, 'completed')))
            if not ok:
                print(f'    ERROR: no Request Completed after Deliver (OCR {[b[4] for b in boxes][:6]})',
                      flush=True)
                return 'error'
            return 'delivered' if close_completed(f'{tag}_{i}_done') else 'error'
        if kind != 'quick' or quick or hu._line(boxes, 'no available'):
            return 'short'
        print(f'    Quick Select at {xy}', flush=True)
        _tap(xy, 2.0)
        quick = True
        name = f'{tag}_{i}_qs'
        v.shot(name)
        if hu._line(v.ocr_boxes(name), 'insufficient'):
            print('    too few items for this request -> popup X', flush=True)
            _tap(INSUF_X, 1.5)
            return 'short' if read(f'{name}_x', is_panel)[2] else 'error'
    return 'short'


def cook_recipe(tag: str, budget: int):
    """Process Deck open: Make while Stock < Request (budget Makes). Makes done, None = stuck."""
    made = 0
    img, boxes, ok = read(tag, is_deck)
    if not ok:
        print('    ERROR: Process Deck did not open after Select', flush=True)
        return None
    while made < budget:
        stock, req = deck_counts(boxes)
        if stock is None or req is None:
            print(f'    deck: no Stock/Request read ({stock}/{req}) - not requested, not cooking', flush=True)
            break
        if stock >= req:
            print(f'    stock {stock} covers the request {req}', flush=True)
            break
        if not make_ready(img):
            print('    Make button not ready - not cooking', flush=True)
            break
        print(f'    Make (stock {stock} / request {req})', flush=True)
        _tap(MAKE, COOK_WAIT)
        for p in range(COOK_POLLS):
            name = f'{tag}_m{made}_{p}'
            img = v.shot(name)
            if make_ready(img):
                break
            time.sleep(COOK_WAIT)
        else:
            print('    ERROR: still cooking after the poll window', flush=True)
            return None
        boxes = v.ocr_boxes(name)
        after = deck_counts(boxes)[0]
        if after is None or after <= stock:
            print(f'    Make had no effect (stock {after}) - resources short?', flush=True)
            break
        made += 1
    return made


def kitchen_at(img):
    """T104c: the Kitchen body anchored on the Spire tower (hu.spire_tower), else None."""
    t = hu.spire_tower(img)
    return t and (t[0] + TOWER_TO_KITCHEN[0], t[1] + TOWER_TO_KITCHEN[1])


def kitchen_tap(tag: str, at):
    """T104c: tap the Kitchen body at `at`, then up to KITCHEN_POLLS reads: labelled Cook radial, else the
    floating Cook disc above `at`. xy | 0 (nothing / foreign dialog closed) | None (stuck)."""
    print(f'    no Kitchen radial - tapping the Kitchen at {at}', flush=True)
    _tap(at, 2.0)
    for i in range(KITCHEN_POLLS):
        if i:
            time.sleep(POLL_WAIT)
        name = tag if i == 0 else f'{tag}_p{i}'
        img = v.shot(name)
        if v.classify(img) != 'WORLD':
            if hu.back_plate(img):
                print('    the Kitchen tap opened another dialog - closing it', flush=True)
                return 0 if hu.close_dialog(img) else None
            print('    ERROR: the Kitchen tap left the world view - stopping without a tap', flush=True)
            return None
        disc = cook_disc(img, v.ocr_boxes(name))
        if disc is None:
            disc = floating_cook(img, at)
            if disc:
                print(f'    Kitchen focused, not selected: floating Cook disc at {disc}', flush=True)
        if disc:
            return disc
    return 0


def find_kitchen(tag: str, img):
    """T104c stage 1: anchor the Kitchen on the Spire tower; tap it inside KITCHEN_WIN, else drag the
    camera (closed loop, toward KITCHEN_BASE) up to KITCHEN_DRAGS times, with a Cook-disc rescue on
    every frame after a drag. No tower on the first frame -> the T104b blind KITCHEN_BASE tap; no blind
    drags (spire_go's camera_search has its own). xy | 0 | None."""
    for k in range(KITCHEN_DRAGS + 1):
        if k:
            name = f'{tag}_cam{k}'
            img = v.shot(name)
            if v.classify(img) != 'WORLD':
                print('    ERROR: the camera drag left the world view - stopping without a tap', flush=True)
                return None
            disc = cook_disc(img, v.ocr_boxes(name))
            if disc:
                print(f'    Kitchen radial after the drag: Cook at {disc}', flush=True)
                return disc
        at = kitchen_at(img) or (KITCHEN_BASE if k == 0 else None)
        if at is None:
            print('    no Spire tower on the frame - no Kitchen anchor', flush=True)
            break
        if hu._in(at, KITCHEN_WIN):
            disc = kitchen_tap(f'{tag}_k{k or ""}', at)
            if disc != 0:
                return disc
        d = tuple(max(-m, min(m, b - a)) for a, b, m in zip(at, KITCHEN_BASE, DRAG_MAX))
        if k == KITCHEN_DRAGS or max(map(abs, d)) < DRAG_MIN:
            break
        well = (at[0] + FOUNTAIN_DXY[0], at[1] + FOUNTAIN_DXY[1])
        s = next((p for p in DRAG_STARTS[d[1] < 0]
                  if min(math.dist(p, q) for q in (at, well)) >= DRAG_CLEAR), None)
        if s is None:
            print(f'    Kitchen anchored at {at} - no clear drag start (Kitchen / fountain)', flush=True)
            break
        e = (min(s[0] + d[0], DRAG_END_MAX[0]), min(s[1] + d[1], DRAG_END_MAX[1]))
        print(f'    Kitchen anchored at {at} - camera drag {s} -> {e}', flush=True)
        v.swipe(*s, *e, hu.CAMERA_MS, 1.5)
    return 0


def spire_go(tag: str):
    """T104c stage 2 (the LIVE T103f chain): hu.spire_dialog (tower -> Interact -> requirement dialog)
    -> the 'Go' under a MISSING 'Level N Kitchen' card -> world with the Kitchen selected -> its Cook
    disc. A met card has no Go -> the dialog is closed via its back plate (soft). Only the Go and the
    back plate are tapped in the dialog - never Level Up / Complete Now. xy | 0 | None."""
    print('    Kitchen not found - Spire dialog Go fallback', flush=True)
    got = hu.spire_dialog(strict=True)    # never the supplier NPC's look-alike Interact (st1)
    if isinstance(got, int):
        if got == 4:
            return 0
        img = v.shot(f'{tag}_sp')
        if v.classify(img) == 'WORLD':
            return 0
        return 0 if hu.back_plate(img) and hu.close_dialog(img) else None
    img, boxes = got
    card = next((b for b in hu.missing_boxes(img, boxes)
                 if (m := hu.BUILDING_RE.search(b[4])) and 'kitchen' in m.group(1).lower()), None)
    go = card and (hu._centre(card)[0], hu._centre(card)[1] + hu.GO_DY)
    if not (go and hu.go_pill(img, go)):
        print('    no Kitchen Go on the dialog (card met?) - closing it', flush=True)
        return 0 if hu.close_dialog(img) else None
    print(f'    Go -> Kitchen at {go}', flush=True)
    hu._tap(go, hu.GO_WAIT)                # Complete-Now guard; the only dialog tap besides its back plate
    for i in range(hu.DIALOG_POLLS):
        if i:
            time.sleep(hu.DIALOG_POLL_WAIT)
        name = f'{tag}_go' if i == 0 else f'{tag}_go_p{i}'
        img = v.shot(name)
        if v.classify(img) == 'WORLD':
            disc = cook_disc(img, v.ocr_boxes(name)) or floating_cook(img)
            if disc:
                return disc
    if v.classify(img) == 'WORLD':
        print('    no Kitchen Cook radial after Go', flush=True)
        return 0
    if hu.back_plate(img):
        return 0 if hu.close_dialog(img) else None
    print('    ERROR: Go did not lead to the world view - stopping without a tap', flush=True)
    return None


def open_kitchen(tag: str):
    """World -> Kitchen recipe list: (img, boxes); 0 = Kitchen not found / not opened (soft);
    None = stuck on an unknown screen."""
    name = f'{tag}_w'
    img = v.shot(name)
    if v.classify(img) != 'WORLD':
        print('    ERROR: not on the world view after the panel', flush=True)
        return None
    disc = cook_disc(img, v.ocr_boxes(name))
    if disc is None:
        disc = find_kitchen(tag, img)
        if disc == 0:
            disc = spire_go(tag)
        if not disc:
            if disc == 0:
                print('    Kitchen not found (camera elsewhere?) - no cooking', flush=True)
            return disc
    for attempt in range(2):
        _tap(disc, 2.5)
        img, boxes, ok = read(f'{tag}_list' if attempt == 0 else f'{tag}_list_s', is_kitchen)
        if ok:
            return img, boxes
        disc = cook_disc(img, boxes) if attempt == 0 and v.classify(img) == 'WORLD' else None
        if disc is None:
            break
        print(f'    the tap selected the Kitchen: its Cook radial at {disc}', flush=True)
    if v.classify(img) == 'WORLD':
        print('    Kitchen did not open (no Cook radial after the tap) - no cooking', flush=True)
        return 0
    if hu.back_plate(img):
        print('    ERROR: not the Kitchen after the Cook tap - closing that dialog', flush=True)
        return 0 if hu.close_dialog(img) else None
    print(f'    ERROR: Kitchen did not open after Cook (OCR {[b[4] for b in boxes][:6]})', flush=True)
    return None


def cook_trip(tag: str):
    """World -> Kitchen -> cook the bannered recipes -> world. Makes done, None = stuck."""
    got = open_kitchen(tag)
    if not isinstance(got, tuple):
        return got
    img, boxes = got
    st = stamina(boxes)
    low = st is not None and st < STAMINA_FLOOR
    if low:
        print(f'    stamina {st} < {STAMINA_FLOOR} - no cooking', flush=True)
    made = probes = 0
    opened = []
    bannered = bool(requested_cards(img))
    for k in range(MAX_DECKS):
        if low or made >= MAX_COOKS:
            break
        cards = kitchen_cards(img, boxes)
        if cards and cards[0][3]:
            card = cards[0]                      # first banner card of a FRESH read (the grid reflows)
        elif bannered:
            break                                # every bannered recipe covered
        else:                                    # no banner at all: probe lowest-stock decks
            rest = [c for c in cards if not any(abs(c[0] - x) <= CARD_TOL and abs(c[1] - y) <= CARD_TOL
                                                for x, y in opened)]
            if not rest or probes >= MAX_PROBES:
                break
            card, probes = rest[0], probes + 1
        x, y, stock, req = card
        opened.append((x, y))
        print(f'    recipe card at ({x},{y}), stock {stock}, banner {req} (stamina {st})', flush=True)
        _tap((x, y), 2.0)
        n = cook_recipe(f'{tag}_deck{k}', MAX_COOKS - made)
        if n is None:
            return None
        _tap(KITCHEN_BACK, 2.0)
        img, boxes, ok = read(f'{tag}_list{k}', is_kitchen)
        if not ok:
            print('    ERROR: Kitchen list not back after the deck', flush=True)
            return None
        made += n
        if req and n == 0:
            break                                # a bannered recipe that cannot be cooked: no loop
    _tap(KITCHEN_BACK, 2.0)
    if v.classify(v.shot(f'{tag}_world')) != 'WORLD':
        print('    ERROR: world not reached after the Kitchen back arrow', flush=True)
        return None
    print(f'    cooked {made}', flush=True)
    return made


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Homestead: deliver Golden Supplier requests (cook what is missing)')
    ap.add_argument('--no-cook', action='store_true', help='never open the Kitchen')
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

    img = v.shot('rq_world')
    if v.is_confirm_dialog(img):                 # 'exit the game?' - X only
        _tap(v.CONFIRM_CANCEL, 1.5)
        img = v.shot('rq_world_c')
    if v.classify(img) != 'WORLD':
        print('    ERROR: not on the world view - stopping without a tap', flush=True)
        return 1
    if v.lum(v.avg(img, HUD_PROBE, r=3)) < HUD_LUM:
        print('    nothing to do: no Requests icon in the HUD', flush=True)
        return 4
    if not open_panel('rq_open'):
        return 1
    delivered = made = slot = 0
    cooked = False
    for step in range(MAX_STEPS):
        r = serve(f'rq{step}')
        if r == 'error':
            return 1
        if r == 'delivered':
            delivered += 1
            print(f'    request delivered ({delivered}/{MAX_DELIVER})', flush=True)
            if delivered >= MAX_DELIVER:
                break
            continue
        if not cooked and not args.no_cook:
            cooked = True
            if not leave_panel('rq_out'):
                return 1
            n = cook_trip('rq_ck')
            if n is None or not open_panel('rq_open2'):
                return 1
            made, slot = n, 0
            if n:
                continue                         # the first slot again, with the cooked items
        slot += 1
        if slot >= len(SLOTS):
            break
        print(f'    next NPC slot {slot + 1}', flush=True)
        _tap(SLOTS[slot], 2.0)
        img, _, ok = read(f'rq_slot{slot}', is_panel)
        if not ok:
            return 1
        if not slot_selected(img, slot):
            print(f'    slot {slot + 1} not selected (locked / dead tap?)', flush=True)
            break
    if not leave_panel('rq_leave'):
        return 1
    print(f'    requests delivered {delivered}, cooked {made}', flush=True)
    return 0 if delivered else 4


if __name__ == '__main__':
    sys.exit(main())
