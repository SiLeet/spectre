#!/usr/bin/env python3
"""Guild daily (T106 + T106b): hall state, Guild Chest countdown, Guild Store read (LOG-ONLY),
Guild Challenge claims (free Guild Medal rewards, soft + bounded).

Frames. T106 (Hermes 2026-11-05 02:30, hermes/cache/scratch): guild1/guild2/g3 world (night, Guild
icon of the bottom bar, layout A) - guild4 the same night world but classify() reads it UNKNOWN
(BACK-probe lb-lg +27.7 > the shared WORLD bound +25: rc 1, no tap, LIVE-open); guild5/gback/un1
hall; gchest/gchal/gstore the chest panel (Hermes' Challenge + Store taps there landed on chest
rows); gstore2 the Store hub (EMPTY list); un2 the world after the hall back arrow (weak evidence).
T106b: .spectre/shots-41892/gd_* = a live run of this tour (06:05-06:06): gd_world/gd_open world,
gd_open_r/gd_hall/gd_hall2 hall, gd_chest panel, gd_store Store hub MID-FADE (hall bleeds through,
no items), gd_items Guild Store with the Daily pill GREEN and 2 cards, gd_hall3 hall (full-frame
OCR garbage - the back poll needs all OPEN_POLLS), gd_out loading, gd_out_p1 world. Hermes 06:07-
06:13: gfr1/gf_now world; gfr2/gc1/gc2/gcA/gcB the 'Guild Challenge' board, 2 claimable cards
(Arena 1400, AFK Stage 500 1500); gcC/gcD the board after the Arena claim (+1400 medals: 28704 ->
30104, the tap itself not recorded); gcE the board + the 'Guild Medal' item tooltip ('Owned:
30104', the AFK badge STILL lit under it, its 1500 not credited); gcF/gcG hall; gcH loading; gcI.

Flow (bounded, every tap gated on a verified frame):
  world (classify WORLD, Guild icon px at the layout-A spot) -> Guild icon -> hall (OCR hall words)
  -> log the Challenge badge + Guild Duel phase line
  -> Guild Chest label at the spot? -> chest panel (OCR 'Distribution in') -> log -> back -> hall
  -> 'Store' label at the plate spot? -> Store hub (Daily/Monthly + 'Store' x3) -> log the Guild
     Medal balance -> Guild tab selected? -> Daily pill -> store hub with price strips? -> per card
     (slot, price by an x3 crop OCR, currency 'diamond' by the lavender icon tell) -> plan_buys()
     verdicts + medal/diamond balances + refresh timer, LOG-ONLY -> store back -> hall (or world)
  -> hall again (fresh read), Challenge badge lit + 'Challenge' label at the plate? -> Challenge
     plate -> board (is_board) -> claim loop (MAX_CLAIMS): tap the first lit badge slot -> board or
     the 'Guild Medal' tooltip (log 'Owned') -> CLOSE_TAP on the cream gutter (gated) -> board;
     progress = fewer lit slots on a clean board (cream gutter at CLOSE_TAP, else rc 1 without a tap),
     else 'did not clear' and stop -> board back -> hall (or world)
  -> hall back arrow -> world.
  A failure on a verified hall leaves via the hall back arrow before rc 1 (afk_normalize would send
  keyevent BACK - unmeasured here). An unrecognised screen stops the run (rc 1) without a tap. No
  keyevent BACK anywhere; every screen is left via its own back arrow. A confirm dialog is only
  ever cancelled (v.CONFIRM_CANCEL); _tap refuses the confirm check. Tap points are constants:
  WinRT OCR returns SKEWED boxes on the chest panel (gchest 'Distribution in' at (510,16), true
  ~(440,63) on gchal) - OCR gates words and labels only.
Claims: progress is judged ONLY by the board after the close (lit slot count dropped). 'Owned'
  rising is logged, not trusted: on gcE it had risen from the earlier Arena claim while the tapped
  badge stayed lit. Never tapped: Hermes' close point (960,850) = an achieved card once the tooltip
  is gone; the tooltip's 'Guild >' Main Source row (navigates).
Store / buys: user 2026-11-05 'Allow token buys' (guild medals) + diamonds ONLY for the multi-source
  guide item (the daily 210-diamond Invite Letter; plan_buys / guide_diamond_item). Hermes' '210 ->
  180' is an OCR merge of TWO card prices (card 0 envelope 210 diamonds, card 1 acorn x5 180
  diamonds, both -30%), not a price change. The cards carry NO names, so no card can match
  guide_diamond_item (name '?' -> 'not preferred'), and no purchase dialog is on any frame: NO buy
  tap exists (buy_measurable false), the store stays LOG-ONLY.

LIVE-open: the purchase dialog (layout, confirm, cancel/X, currency/price line); store item names
(the 210 card is the Invite Letter only by its envelope icon on one frame); a bought / sold-out
card (unmeasured: if card 0 loses its price strip, has_items() reads 'store list empty'); a guild-medal-priced
card and its price icon (Daily is all diamonds, All/Monthly unseen); whether a badge tap claims (one
proven claim, one tap that only opened the tooltip) and whether a claim-result popup exists;
CLOSE_TAP never tapped live; the board back destination (hall or world, both polled); the hall ->
board transition as a frame pair; the hall with the Challenge badge OFF (every hall frame lit,
also after a claim); board scrolling (a 4th row is cut at y~1040, no swipe: claimables below the
fold are missed; claimables sorted first on 2 samples); the Guild icon in HUD layout B (rc 1, 167
of 394 WORLD frames); a due chest (the panel has no claim button; 'Distributed 38+N' looks
automatic) and the 'Rewards' gift (~1462,40); hall back -> world (un1 -> un2 only);
keyevent BACK in guild screens; Guild Duel / Battle Drills.

Usage: python scripts/afk_guild.py [--min-idle S]
Exit codes: 0 tour done (store log-only, claims soft), 1 stuck / unknown screen / Guild icon not at
the layout-A spot, 5 skipped (PC in use), 7 tap lock held. (4 is not emitted.)
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
CHALLENGE_BTN = (1430, 930)    # LIVE: plate L>235 bbox x1391..1478 y~895..967, median (1433,929) on gd_hall,
                               # gd_hall3, gcF, gcG; Hermes ~(1445,915) on the same plate (T106 taps hit the chest)
CHALLENGE_LABEL_WIN = (1395, 935, 1480, 972)  # LIVE: OCR 'Challenge' (1404,946,61,15), centre (1434,953)
DUEL_DY, DUEL_DX = 60, 80      # LIVE guild5: 'ZGuild Duel' centre (1801,363) -> 'Preparati on' (1812,390)
# --- chest panel (gchest / gchal / gstore) ------------------------------------------------------
CHEST_WORDS = ('distribution in', 'equal distribution', 'contribution ranking')  # LIVE OCR; 0 hits elsewhere
CHEST_RE = re.compile(r'distribution in\s*:?\s*(?:(\d+)\s*d)?\s*(?:(\d+)\s*h)?', re.I)  # LIVE '... 3d 22h'
# --- store hub (gstore2) ------------------------------------------------------------------------
GUILD_TAB = (434, 270)         # LIVE gstore2: tab BACKGROUND left of the icon, selected flat L243 (x434 y240..330)
OTHER_TABS = ((434, 170), (434, 380), (434, 480), (434, 590))  # LIVE gstore2: Recruitment/Arena/Dream/Friendship
TAB_ON, TAB_OFF = 200, 120     # bg flat L91 (r=4 min=max); guild probe hall 95, chest 65, world 87..104
DAILY_PILL = (1010, 348)       # LIVE: OCR 'Daily' (985,341,50,21); pill px L>248 x939..~1080 y329..366
PILL_PROBE = (960, 348)        # LIVE: selected Daily = GREEN (98,159,89) on gd_items; unselected (237,230,224)
                               # gd_store (mid-fade), (251,..) gstore2 - the old lum<247 rule said True on both
ITEM_AREA = (545, 380, 1495, 1075)  # LIVE: cream panel x538..1497 below the pills (y327..367); no tap in here
TOKEN_X0, TOKEN_Y1 = 1300, 45  # LIVE: Guild Medal OCR (1387,13,56,16,'28 704') on gstore2 + gd_items
DIAMOND_BOX = (1170, 0, 1340, 48)  # LIVE gd_items: crop OCR '44 420'; the full frame truncates it to '44'
CARD_X0, CARD_DX, CARD_W = 800, 89, 79  # LIVE gd_items: Daily row, card i = x0+89i..+79 ('-30%' tag y429..456)
CARD_MAX = 8                   # one row x800..1495; row 2 / scrolling unseen (shortcut: first row only)
STRIP_Y = (545, 574)           # LIVE: mauve price strip ~(114,99,105), 1507 / 1496 px on cards 0 / 1, 0 on
STRIP_PX = 1000                # cards 2+ (cream) and on gstore2 / gd_store
STRIP = lambda r, g, b: abs(r - 0x72) <= 12 and abs(g - 0x63) <= 12 and abs(b - 0x69) <= 12  # noqa: E731
DIA_DX, DIA_Y = (21, 31), (560, 569)  # LIVE: lavender diamond icon px 39 / 41 (cards 0 / 1); the medal
DIA_PX = 25                    # price icon is unmeasured -> currency None for anything not lavender
LAVENDER = lambda r, g, b: b > g + 25 and r > g + 10 and v.lum((r, g, b)) > 140  # noqa: E731
PRICE_DX, PRICE_Y = (33, 79), (548, 573)  # LIVE: x3 crop OCR '210' / '180' (icon inside -> '0180', x1 -> [])
STORE_BACK = (472, 1021)       # LIVE: arrow px bbox x458..499 y1006..1037 (gstore2); destination LIVE-open
CONFIRM_OK = (1100, 670, 1190, 770)  # green check of the cream confirm dialog (v.is_confirm_dialog (1142,710/729))
# --- Guild Challenge board (gfr2 / gc1..gcE) ----------------------------------------------------
BOARD_TITLE_Y = 70             # LIVE: OCR 'Gild Challenge@' (444,19,300,44) every board frame; hall label y946
BOARD_MEMBERS = 2              # LIVE: 'Members Com...' boxes 6..9 per board frame, 0 on hall/store/chest/world
SLOT0, SLOT_DX, SLOT_DY, SLOT_R = (620, 246), 281, 260, 14  # LIVE: orange '!' plate on the reward icon of card
                               # (c, r) in a 3x3 grid; card text at (563+281c, 339+260r)
ORANGE = lambda r, g, b: r >= 235 and 60 <= g <= 150 and b <= 80  # noqa: E731
SLOT_PX = 100                  # LIVE: lit 225..263 px (pulses) on 8 board frames, unlit slots 0; all 0 on
                               # gd_hall/gd_items/gd_world/gd_chest/gcF/gf_now. Brief rule r>200,g<90,b<90: lit
                               # only 19..73 and hits avatars / banner / -30% tags -> slots + verified board only
NAME_R = 40                    # slot name = the OCR box nearest its card text origin within 40 px
BOARD_BACK = (478, 1008)       # LIVE: cream plate L>235 bbox x431..525 y969..1049 + arrow glyph (458..476,
                               # 995..1014) on gfr2/gcC/gcE; destination hall or world (LIVE-open, both polled)
CLOSE_TAP = (480, 650)         # LIVE: empty cream gutter left of the cards, avg (235,231,219) gfr2..gcE; outside
CLOSE_LUM = 225                # the tooltip (x~690..1060 y~25..400). Never tapped live (LIVE-open)
OWNED_RE = re.compile(r'owned\s*:?\s*(\d[\d ,.]*)', re.I)  # LIVE gcE: 'Owned: 30104' (709,90)
MAX_CLAIMS = 5
# --- buy policy (policy, not LIVE; buys disabled = log-only) ------------------------------------
PREFERRED = ('invite letter', 'essence')
ALLOWED_CURRENCY = ('guild', 'gold')
BUY_BUDGET = 5000
MAX_BUYS = 1                   # hard rule: at most 1 buy per run
BUYS_APPROVED = True           # user 2026-11-05: guild-token buys allowed, never diamonds (see docstring)
# User rule 2026-11-05: diamonds only for a use several INDEPENDENT guides clearly recommend. Research
# (2026-11-05, every source fetched, clones counted once): the ONLY such use is the discounted daily
# Invite Letter in the Guild Store, 210 instead of 300 diamonds, 1 per day - GameLeap 'Guild Store
# buying guide' (2024-04), Prydwen shop guide / afk.guide Emporium guide (one source, 2025), LootBar
# (2026-02), r/AFKJourney. Monthly Stellar Crystal / Epic Invite Letter: verifiers disagree -> no.
# Complete Now, refreshes, summons, attempts: no consensus -> never.
GUIDE_DIAMOND_ITEM = 'invite letter'
GUIDE_DIAMOND_PRICE = 210
GUIDE_DIAMOND_DAILY = 1
OUT_POLLS = 3
OUT_WAIT = 2.5


def _on_confirm(xy) -> bool:
    l, t, r, b = CONFIRM_OK
    return l <= xy[0] <= r and t <= xy[1] <= b


def _tap(xy, wait: float) -> None:
    """Every tap of this module (besides tap_until on GUILD_BTN): never on a confirm check."""
    if _on_confirm(xy):
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


def _card_px(img, i: int, dx, ys, pred) -> int:
    x0 = CARD_X0 + CARD_DX * i
    return len(hs._pixels(img, (x0 + dx[0], ys[0], x0 + dx[1], ys[1]), pred))


def has_items(img) -> bool:
    """Price strip of the first card (the 'Daily'/'Refreshes' header alone is not a card)."""
    return _card_px(img, 0, (0, CARD_W + 1), STRIP_Y, STRIP) >= STRIP_PX


def is_board(boxes) -> bool:
    return (any('challen' in b[4].lower() and b[1] < BOARD_TITLE_Y for b in boxes)
            and sum('members com' in b[4].lower() for b in boxes) >= BOARD_MEMBERS)


def slot_xy(c: int, r: int):
    return SLOT0[0] + SLOT_DX * c, SLOT0[1] + SLOT_DY * r


def board_badges(img) -> list[tuple[int, int]]:
    """(c, r) of every lit claim badge, row-major. Only valid on a frame where is_board() holds."""
    out = []
    for r in range(3):
        for c in range(3):
            x, y = slot_xy(c, r)
            box = (x - SLOT_R, y - SLOT_R, x + SLOT_R + 1, y + SLOT_R + 1)
            if len(hs._pixels(img, box, ORANGE)) >= SLOT_PX:
                out.append((c, r))
    return out


def slot_name(boxes, c: int, r: int):
    x, y = slot_xy(c, r)
    x, y = x - 57, y + 93                    # card text origin (563+281c, 339+260r)
    near = [(abs(b[0] - x) + abs(b[1] - y), b[4]) for b in boxes
            if abs(b[0] - x) <= NAME_R and abs(b[1] - y) <= NAME_R]
    return min(near)[1] if near else '?'


def is_medal_popup(boxes) -> bool:
    return bool(hu._line(boxes, 'guild medal') and hu._line(boxes, 'owned'))


def medal_owned(boxes):
    for b in boxes:
        m = OWNED_RE.search(b[4])
        if m:
            return _amount(m.group(1))
    return None


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
    """Daily pill filled green (selected)."""
    r, g, b = v.avg(img, PILL_PROBE, r=3)
    return g > r + 40 and g > b + 40


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


def card_currency(img, i: int):
    return 'diamond' if _card_px(img, i, DIA_DX, DIA_Y, LAVENDER) >= DIA_PX else None


def store_items(img, name: str):
    """[(name, price, currency)] per Daily card with a price strip, left to right. The cards carry
    no item names (LIVE gd_items) -> name 'card i (?)', so plan_buys says 'not preferred'. The full-
    frame OCR merges neighbouring prices ('210 ? 180'): each price is a x3 crop OCR of its strip."""
    items = []
    for i in range(CARD_MAX):
        if _card_px(img, i, (0, CARD_W + 1), STRIP_Y, STRIP) < STRIP_PX:
            continue                     # a bought / sold-out card (look unmeasured) must not hide later ones
        x0 = CARD_X0 + CARD_DX * i
        lines = hs.ocr_scaled(name, (x0 + PRICE_DX[0], PRICE_Y[0], x0 + PRICE_DX[1], PRICE_Y[1]), f'price{i}')
        amounts = [_amount(t.strip(" '`.,:;")) for t in lines]      # LIVE: card 1 x3 crop reads "'180"
        price = next((a for a in amounts if a is not None), None)
        items.append((f'card {i} (?)', price, card_currency(img, i)))
    return items


def diamond_balance(name: str):
    return next((_amount(t) for t in v.ocr_region(name, DIAMOND_BOX) if _amount(t) is not None), None)


def guide_diamond_item(name: str, price) -> bool:
    """The one diamond buy with a multi-source guide consensus: the daily 210-diamond Invite Letter
    (not the monthly Epic Invite Letter, not the 300 full price)."""
    n = name.lower()
    return GUIDE_DIAMOND_ITEM in n and 'epic' not in n and price == GUIDE_DIAMOND_PRICE


def plan_buys(items, token, budget=BUY_BUDGET, max_buys=MAX_BUYS, diamonds=None):
    """[(name, price, verdict)] in the order of `items` (row i = card i: callers zip the two). Only rows
    whose verdict starts with 'would buy' may ever be bought. Diamond prices: only guide_diamond_item(), once a day."""
    pref = lambda name: any(p in name.lower() for p in PREFERRED)  # noqa: E731
    out, n, dia = [], 0, 0
    for name, price, cur in items:
        if not pref(name):
            verdict = 'not preferred'
        elif cur == 'diamond':
            if not guide_diamond_item(name, price):
                verdict = 'diamond price'
            elif dia >= GUIDE_DIAMOND_DAILY or n >= max_buys:
                verdict = 'buy limit'
            elif diamonds is None:
                verdict = 'diamond balance unread'
            elif diamonds < price:
                verdict = 'short of diamonds'
            else:
                verdict = 'would buy (guide consensus, diamonds)'
                dia, n = dia + 1, n + 1
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


def _poll_back(tag: str):
    """After a back arrow: poll both destinations (transition frames). 'world' | 'hall' | None."""
    for i in range(rq.OPEN_POLLS):
        if i:
            time.sleep(rq.POLL_WAIT)
        name = tag if i == 0 else f'{tag}_p{i}'
        if v.classify(v.shot(name)) == 'WORLD':
            return 'world'
        if is_hall(v.ocr_boxes(name)):
            return 'hall'
    return None


def read_items():
    """Up to OPEN_POLLS shots after the Daily pill until a store hub with price strips.
    (img, boxes, shot name, ok?)."""
    for i in range(rq.OPEN_POLLS):
        if i:
            time.sleep(rq.POLL_WAIT)
        name = 'gd_items' if i == 0 else f'gd_items_p{i}'
        img, boxes = v.shot(name), v.ocr_boxes(name)
        if v.is_confirm_dialog(img):             # handled (cancelled) by the caller at once
            return img, boxes, name, False
        if is_store(boxes) and has_items(img):
            return img, boxes, name, True
    return img, boxes, name, False


def store(hboxes):
    """Verified hall (its OCR boxes) -> Store hub -> log cards + would-buys -> back.
    ('world' | 'hall' | None (stuck), the Guild Medal balance)."""
    if hu._line(hboxes, 'store', STORE_LABEL_WIN) is None:
        print('    Store label not at the measured spot - skipping the store', flush=True)
        return 'hall', None
    _tap(STORE_BTN, 3.0)
    simg, sboxes, ok = rq.read('gd_store', is_store)
    if not ok:
        print(f'    ERROR: Store hub did not open (OCR {_words(sboxes)})', flush=True)
        if is_hall(sboxes):
            leave_hall()
        return None, None
    token = token_balance(sboxes)
    print(f'    guild medals: {token}', flush=True)
    if not guild_tab_selected(simg):
        print('    Guild Store tab not selected - LIVE-open, store not read', flush=True)
    else:
        _tap(DAILY_PILL, 2.0)
        iimg, iboxes, iname, got = read_items()
        if v.is_confirm_dialog(iimg):            # defensive: never confirm a purchase
            _tap(v.CONFIRM_CANCEL, 1.5)
            print('    ERROR: confirm dialog in the store - cancelled', flush=True)
            return None, token
        if not is_store(iboxes):                 # purchase popup / loading / anything else: no tap
            print(f'    ERROR: unknown screen after the Daily pill (OCR {_words(iboxes)})', flush=True)
            return None, token
        token = token_balance(iboxes) or token
        refresh = hu._line(iboxes, 'refreshes')
        print(f'    Daily pill selected: {pill_selected(iimg)}'
              + (f' ({refresh[4]})' if refresh else ''), flush=True)
        if not got:
            print('    store list empty (LIVE-open)', flush=True)
        else:
            items, diamonds = store_items(iimg, iname), diamond_balance(iname)
            print(f'    balances: guild medals {token}, diamonds {diamonds}', flush=True)
            for (name, price, cur), (_, _, verdict) in zip(items, plan_buys(items, token, diamonds=diamonds)):
                print(f'    would-buy: {name} {price} {cur} -> {verdict}', flush=True)
        print('    buys approved (guild medals; diamonds only for the guide Invite Letter) but no item name '
              'and no purchase dialog on any frame - no buy tap (LOG-ONLY, LIVE-open)', flush=True)
    _tap(STORE_BACK, 2.5)
    where = _poll_back('gd_hall3')
    if where is None:
        print('    ERROR: neither hall nor world after the store back arrow', flush=True)
    return where, token


def _cream(img) -> bool:
    return v.lum(v.avg(img, CLOSE_TAP, r=6)) > CLOSE_LUM


def _clean_board(img) -> bool:
    """Cream gutter = no scrim/popup over the board; a dimmed board would count 0 badges (r < 235)."""
    if _cream(img):
        return True
    print('    ERROR: board gutter not cream (overlay or fade) - badges not counted, no tap', flush=True)
    return False


def claims(img, boxes, medals) -> bool:
    """Verified board -> tap lit badges (MAX_CLAIMS) until none is left or one does not clear.
    True = on a verified plain board again, False = stuck (no further tap)."""
    if not _clean_board(img):
        return False
    lit = board_badges(img)
    print(f'    Guild Challenge: {len(lit)} claimable', flush=True)
    for n in range(1, MAX_CLAIMS + 1):
        if not lit:
            return True
        c, r = lit[0]
        print(f'    claim {n}: slot {c}{r} {slot_name(boxes, c, r)!r}', flush=True)
        if _on_confirm(slot_xy(c, r)):           # slot 22 (1182,766) lies in the confirm-check guard box
            print('    slot inside the confirm-check guard - not tapped, stopping the claims', flush=True)
            return True
        _tap(slot_xy(c, r), 2.0)
        img, boxes, ok = rq.read(f'gd_claim{n}', lambda b: is_board(b) or is_medal_popup(b))
        if v.is_confirm_dialog(img):
            _tap(v.CONFIRM_CANCEL, 1.5)
            print('    ERROR: confirm dialog after a claim tap - cancelled', flush=True)
            return False
        if not ok:
            print(f'    ERROR: unknown screen after the claim tap (OCR {_words(boxes)})', flush=True)
            return False
        if is_medal_popup(boxes):
            owned = medal_owned(boxes)
            print(f'    Guild Medal owned: {owned}'
                  + (f' (store read {medals}, {owned - medals:+d})' if owned and medals else ''), flush=True)
            if not _cream(img):
                print('    ERROR: close spot not cream under the medal popup - no tap', flush=True)
                return False
            _tap(CLOSE_TAP, 1.5)
            img, boxes, ok = rq.read(f'gd_claim{n}_c', lambda b: is_board(b) and not is_medal_popup(b))
            if not ok:
                print(f'    ERROR: board not back after closing the medal popup (OCR {_words(boxes)})', flush=True)
                return False
        if not _clean_board(img):
            return False
        now = board_badges(img)
        if len(now) >= len(lit):
            print(f'    claim tap did not clear the badge ({len(now)} lit, LIVE-open) - stopping the claims',
                  flush=True)
            return True
        lit = now
    if lit:
        print(f'    claim limit {MAX_CLAIMS} reached ({len(lit)} still lit)', flush=True)
    return True


def challenge(medals):
    """Hall -> Guild Challenge board -> claims -> back. 'world' | 'hall' | None (stuck)."""
    himg, hboxes, ok = rq.read('gd_hall4', is_hall)
    if not ok:
        print(f'    ERROR: hall not recognised before the Challenge (OCR {_words(hboxes)})', flush=True)
        return None
    if not challenge_badge(himg):
        print('    Challenge badge off - nothing to claim', flush=True)
        return 'hall'
    if hu._line(hboxes, 'challenge', CHALLENGE_LABEL_WIN) is None:
        print('    Challenge label not at the measured spot - skipping the claims', flush=True)
        return 'hall'
    _tap(CHALLENGE_BTN, 3.0)
    img, boxes, ok = rq.read('gd_board', is_board)
    if not ok:
        print(f'    ERROR: Guild Challenge board did not open (OCR {_words(boxes)})', flush=True)
        if is_hall(boxes):
            leave_hall()
        return None
    if not claims(img, boxes, medals):
        return None
    _tap(BOARD_BACK, 2.5)
    where = _poll_back('gd_hall5')
    if where is None:
        print('    ERROR: neither hall nor world after the board back arrow', flush=True)
    return where


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Guild daily: chest countdown, store read (log-only), challenge claims')
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
    if hu._line(boxes, 'guild ches', CHEST_LABEL_WIN) is None:
        print('    chest label not at the measured spot - skipping the chest', flush=True)
    else:
        boxes = chest()
        if boxes is None:
            return 1
    where, medals = store(boxes)
    if where == 'hall':
        where = challenge(medals)
    elif where == 'world':
        print('    store back arrow led to the world - Challenge skipped', flush=True)
    if where is None or (where == 'hall' and not leave_hall()):
        return 1
    print('    guild tour done (store log-only)', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
