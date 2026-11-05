#!/usr/bin/env python3
"""Events phase, stage 1 (T109): READ-ONLY tour of the Battle Modes 'Events' tab.

Flow (bounded, every tap on a verified frame, soft phase, NO event-card / claim / buy tap):
  v.reach_world (keyevent BACK only on non-WORLD frames) -> GROUND -> BATTLE_MODES_BTN until
  is_battle_modes (or is_events_list: the menu reopened on the Events tab - tab persistence is
  LIVE-open; then the list is read directly and BATTLE_MODES_BTN is never tapped on it)
  -> layout A/B (v.BM_TABS bar probe) -> pre-gate: Events-tab badge (A only; off -> rc 4, no tap)
  -> EVENTS_TAB -> is_events_list (3 polls) -> read the cards: title + timer per column OCR,
  badge per card by an orange-pixel strip above its top-right corner -> log one line per card
  -> ROUTINES_TAB (restore the tab: is_battle_modes only matches Routines-selected, so a menu left
  on Events would break the later arena / duras open_battle_modes) -> is_battle_modes ->
  v.back (measured: Battle Modes -> BACK -> world) -> v.reach_world.
No keyevent BACK on the events list (destination unmeasured). An unknown screen stops the run
(rc 1) without a further tap; the watch.sh normalize before 'stage push' takes over and DOES press
keyevent BACK there (classify: list A = UNKNOWN, B = POPUP; up to 4x, unmeasured) - so watch.sh
marks the day on rc 1 too: one attempt per day, the unverified taps never repeat each cycle.

Frames (all 1920x1080, sweep of 1988 frames in .spectre + Hermes scratch): events list layout A
(bottom-HUD diamond ~917) = Hermes scratch/ev0.png (11-05 06:18), .spectre/shots-readonly-122730.png,
trash/shots-4392/readonly-season-20261103-043509/043629/043802.png; layout B (menu ~1.11x larger)
= trash/shots-46412/tab_events.png (11-04). Routines menu: lt0, arena1..3, bm_hub_frame + 102 A /
27 B .spectre frames. ev0 (06:18:27) -> lt0 (06:18:38) and tab_events -> tab_back: one unrecorded
action leads from the Events tab back to the Routines menu (the ROUTINES_TAB tap is inferred).
No frame shows an OPENED event, an event claim button or a 'Rewards Obtained' popup from an
event, so claims are LIVE-open and stage 1 never taps a card. afk-daily-gift.is_events_panel is
NOT reused (TRUE on ~35 arena-lobby / DR / norm frames). classify() reads the list UNKNOWN (A) /
POPUP (B): never gate on classify here.

Stage 2 guard (policy 2026-11-05: free claims only, never a price / currency / Purchase / Buy /
Top up / diamond pack): NEVER_OPEN titles stay closed until their screens are measured (summon
banner / likely purchase-bearing), SKIP_OPEN is claimed elsewhere (afk-daily-gift, world Login
Rewards entry), MAX_OPEN = 2 is reserved - stage 1 opens 0 events.

LIVE-open (frames needed from Hermes; FIRST: the ROUTINES_TAB result and keyevent BACK on the
list, then the layout-B EVENTS_TAB_B result): an opened event (Dreamdelve, Autumn Whirlwind, Stormbound
Seas, ...) with its free-claim button, price / currency tells, 'Rewards Obtained' popup + dismiss
and back arrow; Journey's Gift tapped from the list (same Login Rewards panel?); the ROUTINES_TAB
result; keyevent BACK on the list; tab persistence; layout B: EVENTS_TAB result, a LIT B tab badge
(1625,900), a B card badge (geometry scaled x1.11, negatives only); layout A with the tab badge OFF
(all 102 A menu frames have it lit); badge semantics (gift glyph vs '!'); the scrolled list (row 4
titles sit under the tab bar, list end); any splash after the EVENTS_TAB tap (none on ev0).

Usage: python scripts/afk_events.py [--min-idle S]
Exit codes: 0 list read + logged with >= 1 card badge, 4 nothing to do (Events-tab badge off in
layout A, or no card badge), 1 stuck / unverified screen, 5 skipped (PC in use), 7 tap lock held.
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
import afk_homestead as hs  # noqa: E402  (_pixels)

# --- Battle Modes menu (Routines selected) ------------------------------------------------------
EVENTS_TAB = (1310, 930)       # LIVE: Hermes' tap 2026-11-05 06:18 (layout A) opened ev0; inside A's drawn tab
                               # (x1145-1480, y912-962). Layout A only.
EVENTS_TAB_B = (1460, 925)     # GUESSED: centre of B's drawn Events plate (tab_back x~1290-1630, y897-950);
                               # no B tap recorded (1310 sat 27 px inside B's left edge, next to the Guild tab)
ROUTINES_TAB = (640, 935)      # position LIVE: inside A's unselected Routines plate (x450-762, y915-960) and B's
                               # (x500-848, y897-948); effect GUESSED: tap inferred (ev0 -> lt0, tab_events -> tab_back)
EV_TAB_BADGE_A = (1466, 918)   # LIVE: orange px r=10 lit on all 104 A menu frames (181..350); B spot (1625,900)
TAB_BADGE_R, TAB_BADGE_PX = 10, 60  # GUESSED threshold: no OFF sample (lit min 181); B reads 0 on 27 frames -> not gated
MENU_STEPS = 4                 # GUESSED: BATTLE_MODES_BTN taps at most (as v.open_battle_modes(max_steps=4))
# --- events list (is_events_list) ---------------------------------------------------------------
# LIVE: per layout the selected-tab pointer triangle, the Events tab's left border (orange on the list;
# (236,232,221) / (236,231,220) on the Routines menu) and the Guild plate (L~244 / ~247; BATTLE ENDED card
# (222,72,73)). Sweep: 6/6 true (5 A, 1 B), 0 false in 2019 frames, disjoint from is_battle_modes.
# NOT three independent tells for A: (1310,906) is orange on every B menu (B Events icon, (243,164,73)) and
# ~30 other screens, so A rests on the (1150,935) border + the Guild plate.
EV_LIST = {'A': ((1310, 906), (1150, 935), (990, 938)),   # ev0: (241,135,36) / (194,99,36) / L244
           'B': ((1455, 885), (1270, 935), (1100, 922))}  # tab_events: (239,133,36) / (239,147,68) / L247
EV_BODY, EV_NAV = (480, 270), (700, 1035)  # LIVE: cream body L237..249; dark nav band L~95 (BATTLE ENDED 236)
LIST_POLLS, LIST_WAIT = 3, 1.0   # GUESSED: no frame shows the post-tap timing (as the 2.0 s tap waits)
# --- cards (column OCR + badge strip) -----------------------------------------------------------
COLS = {'A': ((676, 856), (870, 1050), (1064, 1245)),     # LIVE: column crops separate the titles that
        'B': ((751, 953), (966, 1168), (1182, 1384))}     # full-frame OCR merges (4 frames)
COL_Y = {'A': (371, 900), 'B': (291, 885)}
TITLE_Y = {'A': (467, 636, 805), 'B': (399, 587, 774)}    # LIVE: OCR box top y per row (ev0 / tab_events)
TIMER_Y = {'A': (494, 663, 831), 'B': (429, 616, 803)}
ROW_TOL = 12
RIGHTS = {'A': (856, 1050, 1245), 'B': (953, 1168, 1384)}  # LIVE A: cream-edge scan on ev0; B GUESSED (x1.11)
TOPS = {'A': (371, 540, 708, 876), 'B': (291, 479, 666, 853)}  # row 4 under the tab bar; B GUESSED (x1.11)
STRIP = {'A': (16, 7, 10), 'B': (18, 8, 11)}  # x right-dl..right+dr, y top-dt..top-1 (above the corner); B GUESSED
# B card edges agree with tab_events by eye, but no B frame has a lit card badge: B badges are unverified.
BADGE_PX = 50                  # LIVE A: 34 badges 96..109 px, 26 non-badge cards 0..7 (Baden red art 7,
                               # Golden Supplier orange art 0, green 'New' tags 0); B: 12/12 negatives 0
BADGE_ORANGE = lambda r, g, b: r > 200 and 60 < g < 190 and b < 110 and r - b > 120  # noqa: E731
# The badge is an ORANGE disc (gift glyph or '!', semantics LIVE-open), not red: a red rule misses it.
TITLES = {'journey': "Journey's Gift", 'dreamdelve': 'Dreamdelve', 'golden': 'Golden Supplier',
          'district': 'District Preview', 'crescent': 'Crescent Offering', 'baden': 'Baden Rate Up',
          'stormbound': 'Stormbound Seas', 'autumn': 'Autumn Whirlwind', 'arcane': 'Arcane Atelier'}
# --- stage 2 guard (policy, not LIVE): default CLOSED - stage 2 opens only titles whose free-claim ---
# screens are measured (an allow-list then); unknown / garbled OCR titles log 'not measured'.
NEVER_OPEN = ('Baden Rate Up', 'Golden Supplier', 'Crescent Offering')  # summon banner / likely paid offers
# Hermes live 2026-11-05 (T111 note): 'District Preview' = the server district opening in 10 d - its
# rewards are a preview only, nothing to claim; 'Golden Supplier' = the homestead Requests NPC
# (afk_homestead_requests delivers there, never from this list).
SKIP_OPEN = ("Journey's Gift", 'District Preview')  # claimed elsewhere / nothing to claim
MAX_OPEN = 2                   # reserved for stage 2; stage 1 opens 0 events


def orng(c) -> bool:
    return c[0] > 170 and c[0] - c[2] > 110 and c[0] - c[1] > 60


def is_events_list(img):
    """'A' | 'B' | None: the Battle Modes menu with the Events tab selected."""
    if v.lum(v.avg(img, EV_BODY)) <= 200 or v.lum(v.avg(img, EV_NAV, r=4)) >= 140:
        return None
    for lay, (tri, border, plate) in EV_LIST.items():
        if (orng(v.avg(img, tri, r=3)) and orng(v.avg(img, border, r=3))
                and v.lum(v.avg(img, plate, r=4)) > 230):
            return lay
    return None


def menu_layout(img) -> str:
    return 'A' if v.lum(v.avg(img, v.BM_TABS[0][0])) > 190 else 'B'


def tab_badge(img) -> int:
    x, y = EV_TAB_BADGE_A
    r = TAB_BADGE_R
    return len(hs._pixels(img, (x - r, y - r, x + r + 1, y + r + 1), BADGE_ORANGE))


def card_badge(img, lay: str, row: int, col: int) -> int:
    """Orange px in the strip just above card (row, col)'s top-right corner (0-based)."""
    right, top = RIGHTS[lay][col], TOPS[lay][row]
    dl, dr, dt = STRIP[lay]
    return len(hs._pixels(img, (right - dl, top - dt, right + dr + 1, top), BADGE_ORANGE))


def _ocr_crop(img, box):
    """OCR boxes of img.crop(box), in crop coordinates (tests patch this)."""
    v.TMP.mkdir(parents=True, exist_ok=True)
    out = v.TMP / f'ev_col_{box[0]}.png'
    img.crop(box).save(out)
    return v.parse_boxes(v.ocr_png(out, boxes=True))


def title_name(text: str) -> str:
    t = re.sub(r'[^a-z]', '', text.lower())
    return next((name for key, name in TITLES.items() if key in t), text)


def timer_text(text: str) -> str:
    """Raw timer ('No Limit' / 'Ends in 13d 1811' - OCR reads h as 11, 14 as M): log only, never gate."""
    m = re.search(r'No Limit|Ends in\s*\S.*', text)
    return m.group(0) if m else text


def stage2_note(title: str) -> str:
    if title == 'Golden Supplier':
        return 'never open: homestead Requests NPC (afk_homestead_requests)'
    if title == 'District Preview':
        return 'preview only, nothing to claim'
    if title in NEVER_OPEN:
        return 'never open (summon / paid offers)'
    if title in SKIP_OPEN:
        return 'claimed by afk-daily-gift'
    return 'not measured (stays closed)'


def read_cards(img, lay: str):
    """[(row, col, title, timer, badge px)], 1-based; row 4 has title None (under the tab bar)."""
    slots = {}
    for c, (l, r) in enumerate(COLS[lay]):
        top = COL_Y[lay][0]
        for x, y, w, h, text in _ocr_crop(img, (l, top, r, COL_Y[lay][1])):
            for kind, ys in (('title', TITLE_Y[lay]), ('timer', TIMER_Y[lay])):
                d, row = min((abs(y + top - ry), i) for i, ry in enumerate(ys))
                if d <= ROW_TOL:
                    slots.setdefault((row, c, kind), []).append((x, text))
    cards = []
    for row in range(len(TOPS[lay])):
        for c in range(3):
            title = timer = None
            if row < 3:
                t = ' '.join(s for _, s in sorted(slots.get((row, c, 'title'), [])))
                title = title_name(t) if t else '?'
                timer = timer_text(' '.join(s for _, s in sorted(slots.get((row, c, 'timer'), [])))) or '-'
            cards.append((row + 1, c + 1, title, timer, card_badge(img, lay, row, c)))
    return cards


def _poll(tag: str, pred):
    """Up to LIST_POLLS shots LIST_WAIT apart until pred(img). (img, pred result)."""
    for i in range(LIST_POLLS):
        if i:
            time.sleep(LIST_WAIT)
        img = v.shot(tag if i == 0 else f'{tag}_p{i}')
        got = pred(img)
        if got:
            return img, got
    return img, None


def open_menu():
    """v.open_battle_modes() with an Events-list exit: (img, 'menu' | 'list' | None).
    shortcut: copies its 4-poll loop so BATTLE_MODES_BTN is never tapped on the events list."""
    if not v.reach_world():
        return None, None
    v.tap(v.GROUND, 0.8)
    for i in range(MENU_STEPS + 1):
        img = v.shot(f'ev_bm_{i}')
        if v.is_battle_modes(img):
            return img, 'menu'
        if is_events_list(img):
            return img, 'list'
        if i < MENU_STEPS:
            v.tap(v.BATTLE_MODES_BTN, 3.0)
    return img, None


def leave() -> bool:
    """Verified events list -> Routines tab -> menu -> BACK -> world."""
    v.tap(ROUTINES_TAB, 2.0)
    img, ok = _poll('ev_out', v.is_battle_modes)
    if not ok:
        what = 'still the events list' if is_events_list(img) else 'unknown screen'
        print(f'    ERROR: Routines menu not back after the Routines tab ({what}) - no further tap', flush=True)
        return False
    v.back(2.5)
    if not v.reach_world():
        print('    ERROR: world not reached after leaving Battle Modes', flush=True)
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Events tab: read the event cards (stage 1, read-only)')
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

    img, where = open_menu()
    if where is None:
        print('    ERROR: Battle Modes menu not verified - stopping without a tap', flush=True)
        return 1
    if where == 'menu':
        lay = menu_layout(img)
        if lay == 'A':
            n = tab_badge(img)
            if n <= TAB_BADGE_PX:
                print(f'    no event badge on the Events tab (px {n}) - nothing to do', flush=True)
                v.back(2.5)               # measured: Battle Modes -> BACK -> world
                return 4 if v.reach_world() else 1
        else:
            print('    layout B: Events-tab badge unmeasured - proceeding', flush=True)
        v.tap(EVENTS_TAB if lay == 'A' else EVENTS_TAB_B, 2.0)
        img, lay = _poll('ev_list', is_events_list)
        if lay is None:
            if v.is_battle_modes(img):
                print('    ERROR: Events tab did not open (still Routines) - leaving', flush=True)
                v.back(2.5)
            else:
                print('    ERROR: unknown screen after the Events tab - stopping without a tap', flush=True)
            return 1
    else:
        lay = is_events_list(img)
        print('    menu reopened on the Events tab (tab persistence)', flush=True)
    cards = read_cards(img, lay)
    for row, col, title, timer, px in cards:
        badge = 'badge' if px >= BADGE_PX else 'no badge'
        if title is None:
            print(f'    events: r{row}c{col} {badge}, title hidden', flush=True)
        else:
            note = f' | stage 2: {stage2_note(title)}' if px >= BADGE_PX else ''
            print(f'    events: r{row}c{col} {title} | {timer} | {badge}{note}', flush=True)
    badged = sum(px >= BADGE_PX for *_, px in cards)
    print(f'    events list (layout {lay}): {badged} badged card(s), 0 opened (stage 1 read-only)', flush=True)
    if not leave():
        return 1
    return 0 if badged else 4


if __name__ == '__main__':
    sys.exit(main())
