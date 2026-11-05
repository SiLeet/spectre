#!/usr/bin/env python3
"""Legend Trial tower push, soft Daily phase (T112).

Flow (every tap gated on a verified frame; an unknown screen stops WITHOUT a tap):

  world -> Battle Modes (v.open_battle_modes) -> lobby label OCR 'legend trial'
  -> ~5 s settle, Legend Trial card (max 2 verified taps) -> tower select
  -> per tower whose tab reads 'Go!' (frame first, calendar only logged):
     card -> floor view (header OCR = tower name) -> pill 'x3' read (0 -> next tower; LIVE:
     probably the envelope milestone reward 'x3 / 5 more floors required', not tickets)
     -> floor loop (max MAX_FLOORS fights per run):
        'Challenge!' ribbon (OCR box + yellow pixel cluster; OCR miss: both ribbon slots)
        -> loading -> prep
        -> deploy heroes from the roster (each tap verified by the green check)
        -> Battle (only on a re-verified prep, >= 1 hero) -> fight (HP tell, scaled by team)
        -> victory card -> close -> floor view or next floor's prep; defeat -> stop
  -> back arrows (floor view -> towers -> Battle Modes) -> v.reach_world()
  rc 1 -> the same verified back-arrow leave() (stops on an unknown frame) so afk_normalize
  does not have to keyevent-BACK out of LT screens before stage push
  marker .spectre/legend-trial-last.txt (UTC date) on rc 0/4, like afk_duras

Frames (Hermes scratch, 2026-11-05 06:44-06:53 local): ltg0/1 Battle Modes lobby, ltg2
tower select, ltg3..5 Eternity floor view (ltg3 = ribbon still animating in), ltg6 loading,
ltg7..F prep with an EMPTY team. Reference frames of working preps / fights:
.spectre/shots-41820/dr_f1_pre1 + dr_f1_w*, shots-54808/arena_f1_step4 + arena_1_start.

BATTLE START DIAGNOSIS (Hermes: 6 'Battle' taps on ltg7..F changed nothing, arena taps work):
the Legend Trial formation is EMPTY - first visit of Eternity Floor 1, no saved team.
  1. Deployed roster cards carry a green check: avg((x,725), r=6) reads (89,175,115) on all
     5 deployed cards of dr_f1_pre1 and arena_f1_step4; on ltg8 the same probes read
     (98,113,75) (173,174,172) (162,161,152) ... - no check anywhere. The hex cluster holds
     only the player avatar (DR/arena show 5 hero sprites). Only 6 row-1 cards are eligible
     (faction rule): white level text px 241/286/262/262/258/259 vs 0-22 on locked cards.
  2. The Battle button is NOT disabled: avg(1280,1010) = (162,194,154) on LT vs (161,193,153)
     on the enabled DR prep; sp.classify_battle reads ltg7..F PREP.
  3. Same bottom row / hitbox as the DR and stage preps where (1280,1010) starts fights, so
     the tap mode is not the variable.
  4. Nothing covers the panel: ltg7..F (9 frames, ~6 min) are pixel-identical below y 556.
  -> Deploy heroes first (ensure_team), then Battle; start proven only by the fight HP tell,
     a loading frame followed by a non-prep frame, or a result card. Two existing detectors
     lie on LT frames and are NOT used alone: dr.is_fight(ltg6 loading) is True,
     sp.classify_battle(ltg2 tower select) is 'DEFEAT'.

LIVE TEST FOR HERMES (on an ltg8-like prep, empty team):
  (a) tap Battle (1280,1010) once, screencap at +0.3 s (a 'deploy a hero' toast?).
  (b) tap (482,712), screencap after 1.5 s: expect (482,725) ~ (89,175,115), a hero on a
      hex and the top-left team power (~60-140, 20-55) > 0 (ltg8: '0' vs enemy 29,859).
      Repeat (578,712) (673,712) (769,712) (864,712): expect 5 checks.
  (c) tap Battle (1280,1010) once; screencaps +1/+3/+6 s: loading, then >= 600 green HP px
      in (680,1030,1240,1052) (G>180, G-R>80, G-B>100).
  (d) only if (b) does not deploy: `input swipe 482 712 872 472 600` (card onto the hex
      centroid), repeat (b)/(c); if that works set DRAG_DEPLOY = True.
  Then: `python scripts/afk_legend_trial.py --dry-run` and a real run with --max-floors 1;
  capture the victory / defeat card and the frame after CARD_CLOSE, the floor view on floor 2
  (ribbon slot), the pill text before/after one win, and the frame after CARD_CLOSE on the 5th
  win (milestone reward popup?). On a Mon/Tue/Wed/Fri/Sat/Sun: an ltg2-like tower select.

LIVE-open (not on any frame): roster tap deploys (vs drag); toast on an empty-team Battle;
team slot limit (5 assumed) and an 'empty slots, start anyway?' confirm; roster re-sort after a
deploy (rescanned every tap); HP-strip tell in LT fights (measured on DR/arena only); victory
card layout + CARD_CLOSE + auto-advance to the next floor's prep; defeat card and a safe close
(not tapped: left to normalize); Challenge ribbon position on floor 2+ (OCR box + yellow
check, no blind fallback); ticket semantics (per fight / victory / defeat), purchase dialog
at 0 (cancelled), daily reset; Eternity schedule ('Go!' without Start Time: daily per brief,
Thu/Sat/Sun by pattern); an elemental tower's 'Go!' tab colour (an
unclassified tab is skipped and logged); server day boundary vs the
UTC marker; the back-arrow taps (476,1010) on floor view / tower select / prep (only the plate
colours are measured); keyevent BACK on LT screens (never sent here); '5 more floors
required' (log only).

Never: 'Auto Battle' (860,1000) (may chain floors / tickets), Retry, any purchase, the green
check of a confirm dialog (dialogs only via v.CONFIRM_CANCEL), keyevent BACK inside LT screens
(the only BACK is v.reach_world on a verified Battle Modes menu, T97-measured).

Clock: towers open by server day. The calendar is a hint only and is read in UTC
(datetime.now(timezone.utc).weekday(), the same UTC day as the watch markers); the frame's
'Go!' / locked tabs decide. A mismatch is logged.

Usage: python scripts/afk_legend_trial.py [--dry-run] [--min-idle S] [--max-floors N]
Exit codes: 0 at least one floor won (dry run: floor view + tickets read), 4 nothing to do
(no tower open / pill x0 / defeat on the first fight / purchase dialog cancelled), 1 stuck
or unknown screen (also a verified floor view without a ribbon), 5 PC in use, 7 tap lock held.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bot_lock  # noqa: E402  (tap lock: one bot tapping at a time)
import afk_claim_vision as v  # noqa: E402
import afk_stage_push as sp  # noqa: E402  (classify_battle: PREP / LOADING / result cards)

# --- lobby (Battle Modes) ---
LT_CARD = (766, 580)            # LIVE: ltg0/lt0 card centre (383,290) half-frame; Hermes ~(770,562)
LOBBY_LABEL_BOX = (670, 650, 870, 712)   # LIVE: OCR 'Legend Trial J' on ltg0 + lt0 (duras
                                         # MENU_BOX full crop garbles it to "'lid Trial")
CARD_SETTLE = 5.0               # LIVE (Hermes): card taps before ~5 s settle are dropped
CARD_TAPS = 2                   # LIVE (Hermes): taps sometimes need 2 attempts

# --- tower select (ltg2) ---
# (name, card tap, tab probe); LIVE: ltg2. Hermes' Eternity tap (960,697) produced ltg3.
TOWERS = (('light', (900, 380), (1160, 370)),
          ('nature', (890, 536), (1150, 530)),
          ('eternity', (960, 697), (1170, 690)),
          ('will', (900, 850), (1160, 840)))
TAB_R = 12
# LIVE ltg2: locked tabs (237,234,226) (238,236,228) (240,238,230); 'Go!' (64,169,145)
BACK_PLATE = (476, 1010)        # LIVE: back-arrow plate L 174-177 on ltg2..5 + ltg7..F
BACK_RIM = (520, 1010)          # LIVE: L 241-247 there; Battle Modes reads 93
CALENDAR = {'light': (0, 4, 6), 'nature': (2, 5, 6), 'will': (1, 4, 6)}   # LIVE: OCR ltg2
                                # Mon/Fri/Sun, Wed/Sat/Sun, Tue/Fri/Sun; eternity: 'Go!', no schedule

# --- floor view (ltg3..5) ---
HEADER_BOX = (440, 30, 900, 90)          # LIVE: OCR 'ower ofEternity' on ltg3/4
TICKET_BOX = (510, 92, 640, 132)         # LIVE: OCR 'x3' on ltg4/5 at 1x (2x upscale reads [])
PILL_BOX = (620, 92, 880, 132)           # LIVE: '5 more floors required' (log only)
CHALLENGE_RE = re.compile(r'(?i)cha\W{0,3}\w{0,3}eng')   # LIVE: 'Cha//enge/' ltg4, 'Challenger' ltg5
YELLOW_WIN = (130, 70)          # +-x, +-y around the OCR box centre
YELLOW_PX = 3000                # LIVE: ribbon 10.5-11.4k px on ltg3..5, tower select 0, lobby <=308
# OCR miss: floors alternate sides (ltg4: floor 1 right x984-1230 y700-770, floor 2 plate left
# x~700-920 y~430-490). LIVE ltg3/4/5 yellow px: left 95-185, right 10.5-11k; y >= 140 keeps the
# pill (~2k yellow px) out. Tap = centroid of the slot's cluster.
CHALLENGE_SLOTS = ((680, 140, 940, 1000), (975, 140, 1245, 1000))
LOAD_POLLS, LOAD_WAIT = 6, 2.5  # LIVE: ltg6 loading = uniform (29,29,29) + emblem

# --- prep (ltg7..F) ---
PREP_PLATES = ((760, 1000),)    # LIVE: cream 'Auto Battle' plate L 250 on ltg7..F; floor view
                                # ltg3..5 33-35, tower select ltg2 230 (+ classify_battle PREP)
PREP_HEADER_BOX = (800, 15, 1120, 60)     # LIVE: OCR 'Tower of Eternity - Floor 1 (D' on ltg8/F
PREP_BATTLE = (1280, 1010)      # LIVE: (162,194,154) = enabled DR prep (161,193,153); DR PREP_TAP
ROSTER_X = [482 + round(95.6 * i) for i in range(11)]   # LIVE: row-1 card centres ltg8
ROSTER_TAP_Y = 712              # LIVE: row-1 card body y 668-783
CHECK_PROBE_Y, CHECK_RGB, CHECK_TOL, CHECK_R = 725, (89, 175, 115), 30, 6   # LIVE: dr_f1_pre1,
                                # arena_f1_step4: 5/5 deployed cards; ltg8: 0
AVAIL_DY = (760, 782)           # level-text band; box (x-40, 760, x+45, 782)
AVAIL_PX = 120                  # LIVE ltg8: eligible 241-286 white px, locked 0-22
MAX_TEAM = 5                    # LIVE: slot limit assumed
HEX_DROP = (872, 472)           # LIVE-open: beige hex cluster centroid (drag fallback)
DRAG_DEPLOY = False             # LIVE-open: True = drag the card onto HEX_DROP when a tap does nothing
START_POLLS, START_WAIT = 10, 2.5

# --- fight / end ---
FIGHT_HP_BOX = (680, 1030, 1240, 1052)   # LIVE: 1428-1804 px at fight start (DR, arena; 1965
FIGHT_HP_PX = 600                        # frames), best non-fight 205; LT prep/loading 0
HP_PER_HERO = 250               # LIVE: 292-362 px per 112-px slice (dr_f1_w0, arena_1_start)
FIGHT_WAIT, POLL = 180, 3
CARD_CLOSE = (960, 540)         # LIVE-open: victory card close, as stage push; never on defeat
DIALOG_WORDS = ('purchase', 'spend', 'buy', 'ticket')   # a cancelled one of these = rc 4
MAX_FLOORS = 10
MARKER = v.REPO / '.spectre' / 'legend-trial-last.txt'


def log(msg: str) -> None:
    print(f'    {msg}', flush=True)


def count_px(img, box, pred) -> int:
    data = img.crop(box).convert('RGB').tobytes()
    return sum(1 for i in range(0, len(data), 3) if pred(data[i], data[i + 1], data[i + 2]))


def _yellow(r, g, b) -> bool:
    return r > 215 and g > 175 and b < 150 and r - b > 90


def _back_row(img) -> bool:
    return v.lum(v.avg(img, BACK_PLATE)) > 170 and v.lum(v.avg(img, BACK_RIM)) > 230


# --- detectors ---
def tower_tabs(img) -> dict:
    """{tower: 'go' | 'locked' | None} from the tab colour right of each card."""
    out = {}
    for name, _, probe in TOWERS:
        c = v.avg(img, probe, TAB_R)
        out[name] = ('go' if c[1] - c[0] > 60 else
                     'locked' if v.lum(c) > 200 and max(c) - min(c) < 15 else None)
    return out


def is_lt_towers(img) -> bool:
    """Back row + a 'Go!' tab (Eternity is open daily) or >= 2 locked tabs; one unmeasured tab
    colour (None) no longer hides the screen. LIVE: floor views ltg3..5 read 1 locked, 0 go."""
    tabs = list(tower_tabs(img).values())
    return (not v.is_battle_modes(img) and _back_row(img) and not prep_px(img)
            and ('go' in tabs or tabs.count('locked') >= 2))


def prep_px(img) -> bool:
    return (sp.classify_battle(img) == 'PREP'
            and all(v.lum(v.avg(img, p)) > 240 for p in PREP_PLATES))


def parse_floor(lines) -> int | None:
    m = re.search(r'(?i)floor\s*(\d+)', ' '.join(lines))
    return int(m.group(1)) if m else None


def is_lt_prep(img, header_lines) -> bool:
    """Prep pixels (the stage prep matches them too) + header 'Tower of X - Floor N'."""
    return prep_px(img) and parse_floor(header_lines) is not None


def is_floor_view(img, header_lines, name: str | None = None) -> bool:
    text = ''.join(header_lines).lower()
    names = [name] if name else [t[0] for t in TOWERS]
    return (_back_row(img) and not is_lt_towers(img) and not prep_px(img)
            and any(n in text for n in names))


def parse_tickets(lines) -> int | None:
    m = re.search(r'(?i)x\s*(\d+)', ' '.join(lines))
    return int(m.group(1)) if m else None


def tickets(tag: str) -> int | None:
    return parse_tickets(v.ocr_region(tag, TICKET_BOX))


def find_challenge(img, boxes) -> tuple[int, int] | None:
    """Tap point of the 'Challenge!' ribbon: the OCR box centre, clamped into the yellow
    pixel cluster around it (>= YELLOW_PX). OCR miss: the cluster centroid of either ribbon slot."""
    hits = [(x + w // 2, y + h // 2) for x, y, w, h, t in boxes if CHALLENGE_RE.search(t)]
    wins = [((cx - YELLOW_WIN[0], cy - YELLOW_WIN[1], cx + YELLOW_WIN[0], cy + YELLOW_WIN[1]),
             (cx, cy)) for cx, cy in hits] + [(box, None) for box in CHALLENGE_SLOTS]
    for box, at in wins:
        crop = img.crop(box).convert('RGB')
        w, data = crop.width, crop.tobytes()
        pts = [(i // 3 % w, i // 3 // w) for i in range(0, len(data), 3)
               if _yellow(data[i], data[i + 1], data[i + 2])]
        if len(pts) < YELLOW_PX:
            continue
        xs, ys = [p[0] + box[0] for p in pts], [p[1] + box[1] for p in pts]
        cx, cy = at or (sum(xs) // len(xs), sum(ys) // len(ys))
        return min(max(cx, min(xs)), max(xs)), min(max(cy, min(ys)), max(ys))
    return None


def team_state(img) -> tuple[int, list[int]]:
    """(deployed checks, eligible undeployed card x's) on the roster's first row."""
    checks, eligible = 0, []
    for x in ROSTER_X:
        if v.close_to(v.avg(img, (x, CHECK_PROBE_Y), CHECK_R), CHECK_RGB, CHECK_TOL):
            checks += 1
        elif count_px(img, (x - 40, AVAIL_DY[0], x + 45, AVAIL_DY[1]),
                      lambda r, g, b: v.lum((r, g, b)) >= 235) >= AVAIL_PX:
            eligible.append(x)
    return checks, eligible


def is_lt_fight(img, heroes: int = MAX_TEAM) -> bool:
    """HP-strip tell; the strip scales with the team (one hero ~360 px < FIGHT_HP_PX)."""
    return count_px(img, FIGHT_HP_BOX, lambda r, g, b: g > 180 and g - r > 80 and g - b > 100) \
        >= min(FIGHT_HP_PX, HP_PER_HERO * heroes)


def end_card(img, tag: str) -> str | None:
    """'victory' / 'defeat' on a result card: classify_battle RESULT/DEFEAT, NOT the tower
    select (classify reads ltg2 as DEFEAT). 'victory' only when the title colour (RESULT) and
    the OCR agree; a DEFEAT verdict or any disagreement is a defeat (no tap, stop)."""
    verdict = sp.classify_battle(img)
    if verdict not in ('RESULT', 'DEFEAT') or is_lt_towers(img):
        return None
    text = ' '.join(v.ocr_lines(tag)).lower()
    lost = 'defeat' in text or 'retry' in text
    if verdict == 'RESULT' and 'victory' in text and not lost:
        return 'victory'
    return 'defeat' if lost or 'victory' in text or verdict == 'DEFEAT' else None


# --- steps ---
def cancel_dialog(img, tag: str) -> int | None:
    """Confirm/purchase dialog -> cancel only. rc 4 for a ticket/purchase dialog, else 1."""
    if not v.is_confirm_dialog(img):
        return None
    words = ' '.join(v.ocr_lines(tag)).lower()
    v.tap(v.CONFIRM_CANCEL, 1.5)
    rc = 4 if any(w in words for w in DIALOG_WORDS) else 1
    log(f'{tag}: confirm dialog -> cancelled, stopping (rc {rc})')
    return rc


def wait_prep(tag: str):
    """After the Challenge tap: (img, floor) on the LT prep, or an rc (dialog) / None."""
    for n in range(LOAD_POLLS):
        name = f'{tag}_{n}'
        img = v.shot(name)
        rc = cancel_dialog(img, name)
        if rc is not None:
            return rc
        if prep_px(img):
            hdr = v.ocr_region(name, PREP_HEADER_BOX)
            if is_lt_prep(img, hdr):
                return img, parse_floor(hdr)
        time.sleep(LOAD_WAIT)
    return None


def ensure_team(tag: str) -> int:
    """Deploy eligible roster cards until MAX_TEAM checks; every tap verified by the check
    count. Returns the deployed count (bounded to MAX_TEAM + 1 cards), or -1 as soon as a
    shot is no longer the prep (Battle is then never tapped)."""
    img = v.shot(f'{tag}_0')
    if not prep_px(img):
        log('deploy: not on the prep - stopping')
        return -1
    checks, eligible = team_state(img)
    for n in range(1, MAX_TEAM + 2):
        if checks >= MAX_TEAM or not eligible:
            break
        x = eligible[0]
        v.tap((x, ROSTER_TAP_Y), 1.5)
        img = v.shot(f'{tag}_{n}')
        if not prep_px(img):
            log(f'deploy: prep left after the card tap at x={x} - stopping')
            return -1
        now, nxt = team_state(img)
        if now <= checks:
            mode = v.tap_retry((x, ROSTER_TAP_Y), 1.5)
            img = v.shot(f'{tag}_{n}r')
            if not prep_px(img):
                v.tap_result(mode, True)
                log(f'deploy: prep left after the retry at x={x} - stopping')
                return -1
            now, nxt = team_state(img)
            v.tap_result(mode, now > checks)
            if now <= checks and DRAG_DEPLOY:
                v.swipe(x, ROSTER_TAP_Y, *HEX_DROP, 600, 1.5)
                img = v.shot(f'{tag}_{n}d')
                if not prep_px(img):
                    log(f'deploy: prep left after the drag at x={x} - stopping')
                    return -1
                now, nxt = team_state(img)
            if now <= checks:
                log(f'deploy: card x={x} did not deploy (checks stay {checks}) - stopping')
                break
        checks, eligible = now, nxt
    log(f'deployed {checks}/eligible {checks + len(eligible)}')
    return checks


def start_battle(tag: str, heroes: int) -> str | int | None:
    """Tap Battle once on the verified prep; 'started' only on proof (HP tell, loading then a
    non-prep frame, result card). Prep unchanged 3x -> ONE tap_retry, 3 more polls -> None.
    A confirm dialog -> cancelled, its rc."""
    v.tap(PREP_BATTLE, 3.0)
    same, retried, loading = 0, False, False
    for n in range(START_POLLS):
        name = f'{tag}_{n}'
        img = v.shot(name)
        rc = cancel_dialog(img, name)
        if rc is not None:
            return rc
        if is_lt_fight(img, heroes) or (sp.classify_battle(img) in ('RESULT', 'DEFEAT')
                                and not is_lt_towers(img)):
            return 'started'
        if sp.classify_battle(img) == 'LOADING':
            loading = True
        elif prep_px(img):
            same += 1
            if same >= 3:
                if retried:
                    return None
                mode = v.tap_retry(PREP_BATTLE, 3.0)
                retried, same = True, 0
                v.tap_result(mode, not prep_px(v.shot(f'{name}r')))
        elif loading:
            return 'started'
        time.sleep(START_WAIT)
    return None


def wait_end(tag: str) -> str | int | None:
    for n in range(FIGHT_WAIT // POLL):
        name = f'{tag}_{n}'
        img = v.shot(name)
        rc = cancel_dialog(img, name)
        if rc is not None:
            return rc
        res = end_card(img, name)
        if res:
            return res
        time.sleep(POLL)
    return None


def leave(tag: str) -> bool:
    """Verified back-arrow taps (prep / floor view / tower select) up to Battle Modes, then
    v.reach_world(). Unknown frame (e.g. a defeat card) -> stop without a tap (normalize)."""
    for n in range(4):
        name = f'{tag}_{n}'
        img = v.shot(name)
        if v.is_battle_modes(img):
            return v.reach_world()
        if prep_px(img):
            known = is_lt_prep(img, v.ocr_region(name, PREP_HEADER_BOX))
        else:
            known = is_lt_towers(img) or is_floor_view(img, v.ocr_region(name, HEADER_BOX))
        if known:
            v.tap(BACK_PLATE, 3.0)
            continue
        log(f'{name}: screen not recognised - leaving it to normalize (no tap)')
        return False
    return False


def enter() -> object:
    """Tower select image, or an rc."""
    if not v.open_battle_modes():
        log('ERROR: Battle Modes did not open')
        return 1
    img = v.shot('lt_lobby')
    label = v.ocr_region('lt_lobby', LOBBY_LABEL_BOX)
    if not v.is_battle_modes(img) or 'legend trial' not in ' '.join(label).lower():
        log(f'ERROR: Legend Trial card not seen in the lobby (OCR {label!a})')
        return 1
    time.sleep(CARD_SETTLE)
    for n in range(CARD_TAPS):
        v.tap(LT_CARD, 4.0)
        img = v.shot(f'lt_towers_{n}')
        if is_lt_towers(img):
            return img
        if not v.is_battle_modes(img):
            log('ERROR: tower select not recognised after the card tap')
            return 1
    log(f'ERROR: still on Battle Modes after {CARD_TAPS} card taps')
    return 1


def push_tower(name: str, card, budget: int, dry: bool) -> tuple[int, int, str]:
    """(fights, wins, status) for one tower; status 'next' (try the next tower), 'stop'
    (defeat / bound - do not navigate on), 'dry', or 'rc1'/'rc4'."""
    v.tap(card, 4.0)
    img = v.shot(f'lt_{name}')
    if not is_floor_view(img, v.ocr_region(f'lt_{name}', HEADER_BOX), name):
        log(f'ERROR: {name}: floor view not recognised after the card tap')
        return 0, 0, 'rc1'
    view = f'lt_{name}'                 # latest verified floor-view shot
    left = tickets(view)
    log(f'{name}: pill x{left} {v.ocr_region(f"lt_{name}", PILL_BOX)!a} '
        '(LIVE: milestone reward or tickets?)')
    if left == 0:
        log(f'{name}: pill reads x0 - next tower')
        return 0, 0, 'next'
    if left is None:
        log('LIVE: pill OCR read nothing - continuing (Challenge still pixel-gated)')
    if dry:
        return 0, 0, 'dry'
    fights = wins = 0
    prep = None
    while fights < budget:
        if prep is None:
            xy = find_challenge(img, v.ocr_boxes(view))
            if xy is None:      # verified floor view: a detection miss, not 'nothing to do'
                log(f'ERROR: {name}: no Challenge ribbon on the floor view')
                return fights, wins, 'rc1'
            v.tap(xy, 3.0)
            prep = wait_prep(f'lt_{name}_p{fights}')
            if isinstance(prep, int):
                return fights, wins, f'rc{prep}'
            if prep is None:
                log(f'ERROR: {name}: prep not reached after Challenge')
                return fights, wins, 'rc1'
        log(f'{name}: floor {prep[1]} prep')
        checks = ensure_team(f'lt_{name}_t{fights}')
        if checks < 0:
            return fights, wins, 'rc1'
        if checks < 1:
            log(f'{name}: no hero deployed - not tapping Battle')
            return fights, wins, 'rc1'
        fights += 1
        t0 = time.time()
        started = start_battle(f'lt_{name}_s{fights}', checks)
        if isinstance(started, int):
            return fights, wins, f'rc{started}'
        if started is None:
            log(f'ERROR: Battle tap no effect with {checks} deployed')
            return fights, wins, 'rc1'
        res = wait_end(f'lt_{name}_w{fights}')
        if isinstance(res, int):
            return fights, wins, f'rc{res}'
        if res is None:
            log('ERROR: no result card after the fight')
            return fights, wins, 'rc1'
        log(f'{name}: floor {prep[1]} {res} ({time.time() - t0:.0f}s)')
        if res == 'defeat':
            return fights, wins, 'stop'       # never Retry; the card is left to normalize
        wins += 1
        v.tap(CARD_CLOSE, 3.0)
        prep = None
        for n in range(LOAD_POLLS):
            tag = f'lt_{name}_a{fights}_{n}'
            img = v.shot(tag)
            if prep_px(img):
                hdr = v.ocr_region(tag, PREP_HEADER_BOX)
                if is_lt_prep(img, hdr):
                    prep = (img, parse_floor(hdr))      # auto-advance to the next floor
                    break
            elif is_floor_view(img, v.ocr_region(tag, HEADER_BOX), name):
                view, now = tag, tickets(tag)
                log(f'{name}: pill x{left} -> x{now} (LIVE: milestone or tickets?)')
                left = now
                break
            time.sleep(LOAD_WAIT)
        else:
            log('ERROR: neither floor view nor prep after the victory card')
            return fights, wins, 'rc1'
        if prep is None and left == 0:
            return fights, wins, 'next'
    log(f'{name}: MAX_FLOORS bound reached')
    return fights, wins, 'stop'


def run(args) -> int:
    img = enter()
    if isinstance(img, int):
        return img
    tabs = tower_tabs(img)
    day = datetime.now(timezone.utc).weekday()
    for name, cal in CALENDAR.items():
        if tabs[name] is None:
            log(f'{name}: tab colour not measured - skipped (LIVE-open)')
        elif (day in cal) != (tabs[name] == 'go'):
            log(f'{name}: calendar says {"open" if day in cal else "closed"} (UTC weekday {day}), '
                f'frame says {tabs[name]}')
    log(f'towers: {tabs}')
    fights = wins = 0
    for name, card, _ in TOWERS:
        if tabs[name] != 'go' or fights >= args.max_floors:
            continue
        f, w, status = push_tower(name, card, args.max_floors - fights, args.dry_run)
        fights, wins = fights + f, wins + w
        if status == 'dry':
            leave('lt_leave')
            return 0
        if status == 'rc1':
            return 1                          # main() runs the verified leave()
        if status in ('stop', 'rc4'):
            break
        # 'next': back to the tower select for the next open tower
        v.tap(BACK_PLATE, 3.0)
        if not is_lt_towers(v.shot(f'lt_back_{name}')):
            log('ERROR: tower select not back after the floor view')
            return 1
    if not any(t == 'go' for t in tabs.values()):
        log('no tower open today')
    leave('lt_leave')
    log(f'done: {wins} floor(s) won in {fights} fight(s)')
    return 0 if wins else 4


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Legend Trial: push the open tower(s), free tickets only')
    ap.add_argument('--dry-run', action='store_true', help='enter + read towers/tickets only')
    ap.add_argument('--min-idle', type=float, default=0)
    ap.add_argument('--max-floors', type=int, default=MAX_FLOORS)
    args = ap.parse_args(argv)
    if args.min_idle > 0:
        idle = v.idle_seconds()
        if idle is not None and idle < args.min_idle:
            log(f'SKIP: PC is in use (idle {idle:.0f}s)')
            return 5
    if not _bot_lock.acquire():
        log(f'SKIP: tap lock held ({_bot_lock.describe()}) - another bot run is tapping (exit 7)')
        return 7
    _bot_lock.release_at_exit()
    rc = run(args)
    if rc == 1:     # verified back plates only (unknown frame -> no tap): spares normalize's BACKs
        leave('lt_fail')
    if rc in (0, 4) and not args.dry_run:
        try:
            MARKER.parent.mkdir(parents=True, exist_ok=True)
            MARKER.write_text(datetime.now(timezone.utc).strftime('%Y-%m-%d'), encoding='utf-8')
        except OSError:
            pass
    return rc


if __name__ == '__main__':
    sys.exit(main())
