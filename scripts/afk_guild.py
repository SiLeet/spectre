#!/usr/bin/env python3
"""Guild daily (T106): LOG-ONLY tour - hall state, Guild Chest countdown, Guild Store read.

Frames (Hermes live 2026-11-05, %LOCALAPPDATA%/hermes/cache/scratch, mtime order): guild1/guild2/
g3 homestead world (night; the Guild icon of the bottom bar, layout A) - guild4 is the same night
world but classify() reads it UNKNOWN (BACK-probe lb-lg +27.7 > the shared WORLD bound +25), so a
run starting there stops with rc 1 and no tap (known miss of the shared classify, LIVE-open);
guild5 Guild hall; gchest Guild Chest panel; gchal + gstore STILL the chest panel (Hermes'
Challenge (1445,915) and Store taps landed on chest list rows - neither frame shows Challenge or
the store); gback the hall after the chest back arrow; gstore2 the Store hub (Guild Store tab
selected, EMPTY item list - no item, price or currency visible); un1 (02:30:15) a second hall
sample, un2 (02:30:20) the world 5 s later (weak evidence for hall back arrow -> world: the tap
between them is not recorded).

Flow (bounded, every step verified on its frame, soft phase, NO buy / confirm / claim / battle tap):
  world (classify WORLD, Guild icon px at the layout-A spot) -> Guild icon -> hall (OCR hall words)
  -> log: Challenge red badge, Guild Duel phase line ('Preparation'), Challenge/Duel LIVE-open
  -> Guild Chest label (OCR at the measured spot) -> chest panel (OCR 'Distribution in') -> log the
     countdown + 'Activeness Required' -> its back arrow -> hall
  -> 'Store' label at the plate spot? -> Store plate -> Store hub (OCR Daily/Monthly + 'Store' x3)
     -> log the guild token balance -> Guild tab selected? -> Daily pill -> still the store hub? ->
     read the item area -> plan_buys(): log which items WOULD be bought (preferred Invite Letter /
     DR Essence, guild/gold price <= BUY_BUDGET, never a diamond price) -> store back arrow ->
     hall (or world) -> hall back arrow -> world. A failure on a verified hall leaves via the hall
     back arrow before rc 1 (afk_normalize would send keyevent BACK there - unmeasured in the hall).
Buys stay disabled until the user approves store purchases: enabling them = a tap step on the
'would buy' rows of plan_buys() (rc 4 is reserved for 'nothing qualifies' then).
Never tapped: the confirm dialog's green check (refused by _tap), Challenge, Guild Duel, any item.
A confirm dialog is only ever cancelled (v.CONFIRM_CANCEL). No keyevent BACK (no v.back /
reach_world / open_battle_modes): every screen is left via its own back arrow. An unrecognised
screen stops the run (rc 1) without a tap. Tap points are constants: WinRT OCR returns SKEWED
boxes on the chest panel (gchest: 'Distribution in' at (510,16), true ~(440,63) on gchal) - OCR
is used for words only.

LIVE-open (no frame): the store item list (card layout, price position, currency icon, sold-out /
limit state, purchase dialog; ITEM_DX/ITEM_DY are guesses, currency always None -> 'currency
unknown'); the Daily pill's result and which pill is 'selected' (one frame: 'All' fill L243 vs
Daily/Monthly L251 - an 8 L gap, semantics unproven, log only, nothing gates on it); store back
arrow destination (hall assumed, world accepted); hall back arrow -> world (un1 -> un2 only);
keyevent BACK in the guild hall; the hall with the Challenge badge OFF (every hall frame has it
lit: 226 / 226 / 203 px); the Guild icon in HUD layout B (refused, rc 1 - NOT rare: 167 of 394
WORLD frames, all on 11-04; T98: B hit boxes stayed at the A spots for Battle Modes, so one live
check of GUILD_BTN in layout B may unblock it); hall entry time / popups; a due chest (countdown 0) and the
'Rewards' gift (~1462,40) - the panel has NO claim button, distribution looks automatic
('Distributed 38+N' per member); personal activeness (not shown; '2916' is the guild's chest
count); the Challenge screen + attempts; the Guild Duel screen; Battle Drills / Clashfronts; the
Dream Store tab (DR Essence); hall camera stability (chest label gated by CHEST_LABEL_WIN).

Usage: python scripts/afk_guild.py [--min-idle S]
Exit codes: 0 tour done (log-only), 1 stuck / unknown screen / Guild icon not at the layout-A spot,
5 skipped (PC in use), 7 tap lock held. (4 is not emitted in v1.)
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
import afk_homestead as hs  # noqa: E402  (_pixels, tap_until)
import afk_homestead_requests as rq  # noqa: E402  (read: OPEN_POLLS x POLL_WAIT until ok(boxes))
import afk_homestead_upgrade as hu  # noqa: E402  (_line, _centre)

# --- world: Guild icon of the bottom bar --------------------------------------------------------
GUILD_BTN = (1088, 1025)       # LIVE: icon white px (L>200, |r-b|<40) bbox x1068..1109 y1000..1044, median
                               # (1086,1029) on guild1/guild2/guild4, shots-82200/rw_0, shots-73800/norm_0;
                               # label OCR 'Guild' (1068,1056,42,14) on guild2; Hermes ~(1080,1040)
GUILD_ICON_BOX = (1045, 990, 1135, 1050)
GUILD_ICON_PX = (450, 650)     # LIVE sweep: 394 WORLD frames of 1899 - layout A 525..575 (225), layout B
                               # 1125..1175 (167; Resonating Hall helmet there, trash/shots-42388/rw_0 = 1149),
                               # outliers 362 / 853; night frames guild1 (no OCR bar labels) inside A
# --- hall (guild5 / gback, identical) -----------------------------------------------------------
HALL_WORDS = ('display wall', 'battle drills', 'guild duel', 'challenge', 'lashfronts', 'guild ches')
HALL_MIN = 2                   # LIVE OCR: guild5 5 hits, gback 6; world / chest / store 0
GUILD_CHEST = (790, 235)       # Hermes live tap -> gchest
CHEST_LABEL_WIN = (720, 190, 860, 260)  # LIVE: OCR 'Guild Chesi' (726,214,112,21), centre (782,224)
HALL_BACK = (467, 1035)        # LIVE: pink arrow px (r>185, g>150, 15<r-b<70) bbox x453..493 y1019..1050,
                               # median (467,1035) on guild5/gback/gchest; Hermes (465,1030) chest -> gback
STORE_BTN = (1340, 925)        # LIVE: Store plate px L>235 bbox x1296..1382 y870..967, median (1340,932)
                               # (guild5/gback); Hermes (1345,915) from gback -> gstore2; OCR 'Store' (1323,947)
STORE_LABEL_WIN = (1296, 925, 1382, 975)  # LIVE: OCR 'Store' centre (1339,952) guild5/gback, (1340,951) un1;
                               # plate bbox x; Challenge label starts x1404 (gate against a camera shift)
CHALLENGE_BADGE = (1455, 875, 1500, 920)  # LIVE: 226 red px (bbox x1467..1485 y887..907) on guild5/gback, 203 un1,
BADGE_PX = 100                 # 0 on the other 8 guild frames; 131..317 on ~100 Battle Modes frames ->
RED = lambda r, g, b: r > 200 and g < 150 and b < 90  # noqa: E731  only valid on a verified hall
DUEL_DY, DUEL_DX = 60, 80      # LIVE guild5: 'ZGuild Duel' centre (1801,363) -> 'Preparati on' (1812,390)
# --- chest panel (gchest / gchal / gstore) ------------------------------------------------------
CHEST_WORDS = ('distribution in', 'equal distribution', 'contribution ranking')  # LIVE OCR; 0 hits elsewhere
CHEST_RE = re.compile(r'distribution in\s*:?\s*(?:(\d+)\s*d)?\s*(?:(\d+)\s*h)?', re.I)  # LIVE '... 3d 22h'
# --- store hub (gstore2) ------------------------------------------------------------------------
GUILD_TAB = (434, 270)         # LIVE gstore2: tab BACKGROUND left of the icon, selected flat L243 (x434 y240..330)
OTHER_TABS = ((434, 170), (434, 380), (434, 480), (434, 590))  # LIVE gstore2: Recruitment/Arena/Dream/Friendship
TAB_ON, TAB_OFF = 200, 120     # bg flat L91 (r=4 min=max); guild probe hall 95, chest 65, world 87..104
DAILY_PILL = (1010, 348)       # LIVE: OCR 'Daily' (985,341,50,21); pill px L>248 x939..~1080 y329..366
PILL_PROBE = (960, 348)        # LIVE gstore2: 'All' fill L243 (presumed selected - unproven), Daily/Monthly
PILL_SELECTED_LUM = 247        # fill L251; 8 L gap on ONE frame, re-measure after the Daily tap (log only)
ITEM_AREA = (545, 380, 1495, 1075)  # LIVE: cream panel x538..1497 below the pills (y327..367); empty on gstore2
TOKEN_X0, TOKEN_Y1 = 1300, 45  # LIVE: token OCR (1387,13,56,16,'28 704'); diamonds '44' (1227,13) truncated
STORE_BACK = (472, 1021)       # LIVE: arrow px bbox x458..499 y1006..1037 (gstore2); destination LIVE-open
CONFIRM_OK = (1100, 670, 1190, 770)  # green check of the cream confirm dialog (v.is_confirm_dialog (1142,710/729))
# --- buy policy (policy, not LIVE; buys disabled = log-only) ------------------------------------
PREFERRED = ('invite letter', 'essence')
ALLOWED_CURRENCY = ('guild', 'gold')
BUY_BUDGET = 5000
MAX_BUYS = 2
ITEM_DX, ITEM_DY = 120, 200    # shortcut: guessed card geometry, recalibrate on the first store frame with items
OUT_POLLS = 3
OUT_WAIT = 2.5


def _tap(xy, wait: float) -> None:
    """Every tap of this module (besides tap_until on GUILD_BTN): never on a confirm check."""
    l, t, r, b = CONFIRM_OK
    if l <= xy[0] <= r and t <= xy[1] <= b:
        raise RuntimeError(f'refusing a tap on the confirm check: {xy}')
    v.tap(xy, wait)


def guild_icon_px(img) -> int:
    return len(hs._pixels(img, GUILD_ICON_BOX, lambda r, g, b: v.lum((r, g, b)) > 200 and abs(r - b) < 40))


def is_hall(boxes) -> bool:
    return sum(any(w in b[4].lower() for b in boxes) for w in HALL_WORDS) >= HALL_MIN


def is_chest(boxes) -> bool:
    return any(hu._line(boxes, w) for w in CHEST_WORDS)


def is_store(boxes) -> bool:
    return bool(hu._line(boxes, 'monthly') and hu._line(boxes, 'daily')
                and sum('store' in b[4].lower() for b in boxes) >= 3)


def _in_items(b) -> bool:
    x, y = hu._centre(b)
    return ITEM_AREA[0] <= x <= ITEM_AREA[2] and ITEM_AREA[1] <= y <= ITEM_AREA[3]


def has_items(boxes) -> bool:
    return any(_in_items(b) for b in boxes)


def chest_hours(boxes):
    """Hours until the weekly distribution ('Distribution in : 3d 22h' -> 94), None if unread."""
    for b in boxes:
        m = CHEST_RE.search(b[4])
        if m and (m.group(1) or m.group(2)):
            return int(m.group(1) or 0) * 24 + int(m.group(2) or 0)
    return None


def duel_phase(boxes):
    """The OCR line under the hall's 'Guild Duel' label ('Preparati on' on guild5), else None."""
    d = hu._line(boxes, 'guild duel')
    if d is None:
        return None
    dx, dy = hu._centre(d)
    below = [(hu._centre(b)[1] - dy, b[4]) for b in boxes
             if 0 < hu._centre(b)[1] - dy <= DUEL_DY and abs(hu._centre(b)[0] - dx) <= DUEL_DX]
    return min(below)[1] if below else None


def challenge_badge(img) -> bool:
    return len(hs._pixels(img, CHALLENGE_BADGE, RED)) >= BADGE_PX


def guild_tab_selected(img) -> bool:
    return (v.lum(v.avg(img, GUILD_TAB, r=4)) > TAB_ON
            and all(v.lum(v.avg(img, xy, r=4)) < TAB_OFF for xy in OTHER_TABS))


def pill_selected(img) -> bool:
    """Daily pill darker than an unselected pill (log only)."""
    return v.lum(v.avg(img, PILL_PROBE, r=3)) < PILL_SELECTED_LUM


def _amount(text: str):
    """'28 704' -> 28704, '1.2K' -> 1200, '210' -> 210; anything else None."""
    t = text.strip()
    m = re.fullmatch(r'(\d+(?:[.,]\d+)?)\s*[kK]', t)
    if m:
        return round(float(m.group(1).replace(',', '.')) * 1000)
    if re.fullmatch(r'\d{1,3}(?:[ ,.]\d{3})+|\d+', t):
        return int(re.sub(r'\D', '', t))
    return None


def token_balance(boxes):
    for b in boxes:
        if b[0] >= TOKEN_X0 and b[1] < TOKEN_Y1 and _amount(b[4]) is not None:
            return _amount(b[4])
    return None


def store_items(boxes):
    """[(name, price, currency)] from the item area: a price = an amount box, its name the nearest
    non-amount box above it. shortcut: currency is None (the price icon is unread), read the icon
    once a live store frame with items exists."""
    area = [b for b in boxes if _in_items(b)]
    names = [b for b in area if _amount(b[4]) is None]
    items = []
    for b in area:
        price = _amount(b[4])
        if price is None:
            continue
        px, py = hu._centre(b)
        above = [(py - hu._centre(n)[1], n[4]) for n in names
                 if 0 < py - hu._centre(n)[1] <= ITEM_DY and abs(hu._centre(n)[0] - px) <= ITEM_DX]
        items.append((min(above)[1] if above else '?', price, None))
    return items


def plan_buys(items, token, budget=BUY_BUDGET, max_buys=MAX_BUYS):
    """[(name, price, verdict)], preferred items first. Only 'would buy' rows may ever be bought."""
    pref = lambda name: any(p in name.lower() for p in PREFERRED)  # noqa: E731
    out, n = [], 0
    for name, price, cur in sorted(items, key=lambda it: not pref(it[0])):
        if not pref(name):
            verdict = 'not preferred'
        elif cur == 'diamond':
            verdict = 'diamond price'
        elif cur not in ALLOWED_CURRENCY:
            verdict = 'currency unknown'
        elif price is None:
            verdict = 'price unread'
        elif price > budget:
            verdict = 'over budget'
        elif token is None:
            verdict = 'balance unread'
        elif price > token:
            verdict = 'short of tokens'
        elif n >= max_buys:
            verdict = 'buy limit'
        else:
            verdict = 'would buy'
            n += 1
        out.append((name, price, verdict))
    return out


def _words(boxes) -> list[str]:
    return [b[4] for b in boxes][:6]


def leave_hall() -> bool:
    """Verified hall -> its back arrow -> world (OUT_POLLS). False = world not reached."""
    _tap(HALL_BACK, 3.0)
    for i in range(OUT_POLLS):
        if i:
            time.sleep(OUT_WAIT)
        if v.classify(v.shot('gd_out' if i == 0 else f'gd_out_p{i}')) == 'WORLD':
            return True
    print('    ERROR: world not reached after the hall back arrow', flush=True)
    return False


def chest():
    """Hall -> chest panel (log the countdown) -> hall. The hall's OCR boxes, None = stuck."""
    _tap(GUILD_CHEST, 2.5)
    _, cboxes, ok = rq.read('gd_chest', is_chest)
    if not ok:
        if is_hall(cboxes):
            print('    chest panel did not open (still the hall) - skipping the chest', flush=True)
            return cboxes
        print(f'    ERROR: neither chest panel nor hall after the chest tap (OCR {_words(cboxes)})', flush=True)
        return None
    act = hu._line(cboxes, 'activeness')
    hours = chest_hours(cboxes)
    print(f'    Guild Chest: distribution in {hours} h' + (f" ({act[4]})" if act else ''), flush=True)
    if hours == 0:
        print('    distribution due - LIVE-open, no measured claim button', flush=True)
    _tap(HALL_BACK, 2.5)
    _, hboxes, ok = rq.read('gd_hall2', is_hall)
    if not ok:
        print('    ERROR: hall not back after the chest back arrow', flush=True)
        return None
    return hboxes


def store(hboxes):
    """Verified hall (its OCR boxes) -> Store hub -> log the would-buys -> back.
    'world' | 'hall' | None (stuck)."""
    if hu._line(hboxes, 'store', STORE_LABEL_WIN) is None:
        print('    Store label not at the measured spot - skipping the store', flush=True)
        return 'hall'
    _tap(STORE_BTN, 3.0)
    simg, sboxes, ok = rq.read('gd_store', is_store)
    if not ok:
        print(f'    ERROR: Store hub did not open (OCR {_words(sboxes)})', flush=True)
        if is_hall(sboxes):
            leave_hall()
        return None
    token = token_balance(sboxes)
    print(f'    guild tokens: {token}', flush=True)
    if not guild_tab_selected(simg):
        print('    Guild Store tab not selected - LIVE-open, store not read', flush=True)
    else:
        _tap(DAILY_PILL, 2.0)
        iimg, iboxes, got = rq.read('gd_items', lambda b: is_store(b) and has_items(b))
        if v.is_confirm_dialog(iimg):            # defensive: never confirm a purchase
            _tap(v.CONFIRM_CANCEL, 1.5)
            print('    ERROR: confirm dialog in the store - cancelled', flush=True)
            return None
        if not is_store(iboxes):                 # purchase popup / loading / anything else: no tap
            print(f'    ERROR: unknown screen after the Daily pill (OCR {_words(iboxes)})', flush=True)
            return None
        print(f'    Daily pill selected: {pill_selected(iimg)}', flush=True)
        if not got:
            print('    store list empty (LIVE-open)', flush=True)
        else:
            print(f'    store item OCR: {[b for b in iboxes if _in_items(b)]}', flush=True)
            for name, price, verdict in plan_buys(store_items(iboxes), token_balance(iboxes) or token):
                print(f'    would-buy: {name} {price} -> {verdict}', flush=True)
        print('    store is LOG-ONLY (no buy/confirm taps)', flush=True)
    _tap(STORE_BACK, 2.5)
    for i in range(rq.OPEN_POLLS):               # transition frames: poll both destinations
        if i:
            time.sleep(rq.POLL_WAIT)
        name = 'gd_hall3' if i == 0 else f'gd_hall3_p{i}'
        if v.classify(v.shot(name)) == 'WORLD':
            return 'world'
        if is_hall(v.ocr_boxes(name)):
            return 'hall'
    print('    ERROR: neither hall nor world after the store back arrow', flush=True)
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Guild daily: chest countdown + store read (log-only)')
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

    img = v.shot('gd_world')
    if v.is_confirm_dialog(img):                 # 'exit the game?' - X only
        _tap(v.CONFIRM_CANCEL, 1.5)
        img = v.shot('gd_world_c')
    if v.classify(img) != 'WORLD':
        print('    ERROR: not on the world view - stopping without a tap', flush=True)
        return 1
    n = guild_icon_px(img)
    if not GUILD_ICON_PX[0] <= n <= GUILD_ICON_PX[1]:
        print(f'    Guild icon not at the layout-A spot (px {n}; HUD layout B?) - LIVE-open, no tap', flush=True)
        return 1
    if hs.tap_until(GUILD_BTN, 4.0, 'gd_open', lambda im: v.classify(im) != 'WORLD',
                    lambda im: v.classify(im) == 'WORLD') is None:
        print('    ERROR: the Guild tap left the world view to an unknown screen', flush=True)
        return 1
    img, boxes, ok = rq.read('gd_hall', is_hall)
    if not ok:
        print(f'    ERROR: Guild hall not recognised (OCR {_words(boxes)})', flush=True)
        return 1
    print(f"    Challenge badge {'lit' if challenge_badge(img) else 'off'}", flush=True)
    print(f'    Guild Duel phase: {duel_phase(boxes)}', flush=True)
    print('    LIVE-open: Challenge / Guild Duel flows not recorded - no tap', flush=True)
    if hu._line(boxes, 'guild ches', CHEST_LABEL_WIN) is None:
        print('    chest label not at the measured spot - skipping the chest', flush=True)
    else:
        boxes = chest()
        if boxes is None:
            return 1
    where = store(boxes)
    if where is None or (where == 'hall' and not leave_hall()):
        return 1
    print('    guild tour done (log-only)', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
