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
  -> first short: ONE kitchen trip (leave the panel, Kitchen 'Cook' radial, cook every recipe
     under a red 'Requests' banner while Stock < Request, MAX_COOKS, stamina floor), panel
     again; still short -> the next NPC slot (SLOTS); no slot left -> leave.
Never tapped: 'Give Up' (refused by _tap), 'Auto', the x1/x3 steppers, Process Upgrade.
No keyevent BACK (homestead menus open the exit-game dialog): panel, deck and list are left
via their own back arrows. An unrecognised screen stops the run (rc 1) without a tap.

LIVE-open: the header 'n/5' (Hermes: 5 requests/day; post3 shows 4/5 after ONE delivery -
not used, MAX_DELIVER bounds the run); slot 2 (never tapped live); a banner with several
recipes; whether the Kitchen building tap at KITCHEN_BASE selects it from other cameras.

Usage: python scripts/afk_homestead_requests.py [--no-cook] [--min-idle S]
Exit codes: 0 at least one request delivered, 1 stuck / unknown screen, 4 nothing to do
(no Requests icon, nothing deliverable after cooking), 5 skipped (PC in use), 7 tap lock held.
"""
from __future__ import annotations

import argparse
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
KITCHEN_BASE = (1040, 410)     # Hermes live: Kitchen building at the base camera
CARD_XS = (741, 888, 1035, 1183)  # LIVE kz1/rqp: Kitchen card centres (Select boxes)
BANNER = (455, 482, 40)        # red 'Requests' banner band y + half width over a card
BANNER_PX = 500                # LIVE: 779 over Toast on kz1; other cards 0..280 (rqp/rqq/kz1)
RED = lambda r, g, b: r > 150 and r - max(g, b) > 70  # noqa: E731
SELECT_Y = 662                 # LIVE kz1: green Select centre (740,661)
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
        if not any('kitchen' in lb[4].lower() and abs(hu._centre(lb)[0] - cx) <= hu.LABEL_DX
                   and hu._centre(lb)[1] < cy for lb in boxes):
            continue
        for y in (cy - hu.SMALL_DISC_DY, cy - hu.SMALL_DISC_DY + 4, cy - hu.SMALL_DISC_DY - 4):
            for x in range(cx - 8, cx + 9, 4):
                if hu.small_disc_at(img, (x, y)):
                    return x, y
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
            print(f'    deck: Stock/Request unread ({stock}/{req}) - not cooking', flush=True)
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


def cook_trip(tag: str):
    """World -> Kitchen -> cook the bannered recipes -> world. Makes done, None = stuck."""
    name = f'{tag}_w'
    img = v.shot(name)
    if v.classify(img) != 'WORLD':
        print('    ERROR: not on the world view after the panel', flush=True)
        return None
    disc = cook_disc(img, v.ocr_boxes(name))
    if disc is None:
        print(f'    no Kitchen radial - tapping the Kitchen at {KITCHEN_BASE}', flush=True)
        _tap(KITCHEN_BASE, 2.0)
        name = f'{tag}_k'
        img = v.shot(name)
        if v.classify(img) != 'WORLD':
            print('    ERROR: the Kitchen tap left the world view - stopping without a tap', flush=True)
            return None
        disc = cook_disc(img, v.ocr_boxes(name))
        if disc is None:
            print('    Kitchen not found (camera elsewhere?) - no cooking', flush=True)
            return 0
    _tap(disc, 2.5)
    img, boxes, ok = read(f'{tag}_list', is_kitchen)
    if not ok:
        print(f'    ERROR: Kitchen did not open after Cook at {disc}', flush=True)
        return None
    st = stamina(boxes)
    low = st is not None and st < STAMINA_FLOOR
    if low:
        print(f'    stamina {st} < {STAMINA_FLOOR} - no cooking', flush=True)
    made = 0
    for k in range(len(CARD_XS)):
        cards = requested_cards(img)
        if low or not cards or made >= MAX_COOKS:
            break
        print(f'    requested recipe at x={cards[0]} (stamina {st})', flush=True)
        _tap((cards[0], SELECT_Y), 2.0)
        n = cook_recipe(f'{tag}_deck{k}', MAX_COOKS - made)
        if n is None:
            return None
        _tap(KITCHEN_BACK, 2.0)
        img, _, ok = read(f'{tag}_list{k}', is_kitchen)
        if not ok:
            print('    ERROR: Kitchen list not back after the deck', flush=True)
            return None
        made += n
        if n == 0:
            break
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
