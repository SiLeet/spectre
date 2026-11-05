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
Quest 'Upgrade the Ore Refinery to Level 5': see T105B (upgrade_all).

T103d (Hermes live: the icon is FLAKY, sometimes not drawn -> 'nothing to do'): order (a) Level Up
radial / floating icon, (b) spire_tower() - the tower found by its 4 golden light beams, tapped on
its body -> radial -> find_interact() 'Interact' disc (OCR word + cream disc, tower_tap.png) -> the
dialog, verified by OCR as before; no Interact after the tower tap -> rc 1 without a further tap.
The tower is tried on the start frame and on every camera-search frame (after the icon).
(c) 'Radiant Spire' label tap: NOT implemented - the label is only drawn while the Spire is
selected (hm_requests/hm_req2/hs_0_world, always with its radial up -> (a)); it floats over the
tower top, so a tap there is a tower tap; no frame shows what a label tap opens.

LIVE-open (no frame): the icon with the Spire elsewhere on screen / off screen, a 7/7 Spire
dialog, the queue icon's meaning (busy/total assumed).

T105B (UPGRADE-ALL): after the Spire path (rc 0|4) upgrade_all() spends the rest of the budget
(MAX_UPGRADES = 2 per run, minus a Spire start) on other buildings, in this order:
  (q) quest building: the world quest tracker (bottom left, orange pill) names it - LIVE 'Upgrade the
      Ore Refinery to Level 5' (OCR box 'Refinery' (180,901), shots-57584/80480/42848). Its labelled
      radial Level Up when already selected (LIVE trash/shots-38632 bm_0/bm_1/rw_0, trash/shots-31044
      norm_1: label 'Ore Refinery' (962,365), radial 'Smelt' + 'Level U' (1167,725) -> disc (1167,695);
      the label sits ~206 px left of the text -> NAME_DX).
  (p) green 'upgrade-ready' pins (dark disc, green up-arrow + rim, (146,214,125)): 129 hits on 247
      frames; one false hit on a 'Full' production badge at y 888 (trash/shots-48532/dg_cam_2) -> PIN_BAND
      ends at y 860. The Kitchen pin at 4/4 (57584/hu_world (1110,300)) is gone once its Level Up
      started (hu_after). Topmost first, MAX_PINS per run: pin tap -> dialog | compact radial
      (rq_ck_k: Level Up disc above the building, no text - level_icons, searched around the pin) |
      nothing -> ONE body tap (PIN_TO_BODY, only while the pin still stands where it was) -> else the
      pin is parked. A radial already up before the pin tap (57584/hu_world: the Kitchen's) is not the
      pin's - ignored after the tap. A pin that opens an unrecognised dialog: closed via its back plate.
  (t) LAST (LIVE-open tap, fix-review): the tracker pill (QUEST_TAP) when budget is left and the quest
      building was not parked; only a requirement dialog or the radial labelled with that name is used.
  The dialog -> upgrade_or_go(go=False): a missing card (resource short) / refused / diamond confirm
  -> closed, building parked by its title (title_name) for this run, next one; queue full -> stop.
Kitchen dialog now LIVE (shots-57584/hu_bread: 4/4, queue 0/2, Level Up -> world = started);
CAMERA_DRAGS do pan (shots-59732 hu_cam1/hu_cam2: Kitchen pin (1100,250) -> (1082,504) -> (1472,282)).
Fix: the Cook-anchor fallback took the 'Speed Up' hourglass for Level Up (57584/hu_after (1052,730))
-> every Level Up disc needs an arrow tip (arrow_up) and no fallback while 'Speed Up' is read.
A finished-upgrade overlay on the start frame ('Kitchen Upgraded', Hermes rq0) is closed via its
'Tap to close' (hs.TOAST_CLOSE, once).
LIVE-open (T105B, no frame): what a pin tap opens; pin = 'upgradable now' (inferred from the Kitchen
only); the Ore Refinery's dialog and pin (no frame shows either - parking uses the dialog title);
what the tracker tap opens; PIN_TO_BODY for buildings other than the Kitchen; whether pin /
tracker taps pan the camera (PIN_ICON_R assumed); buildings off screen (no zone scan, only pins on
the current frame); 'Ebenen-Unlocks' (never on a frame); an 'Insufficient resources' popup after a
met Level Up (-> unknown screen, rc 1); the Go under a missing RESOURCE card (not followed); the
queue counter after one start (1/2); other buildings' dialog layout (assumed = Spire/Kitchen).

Never spends diamonds: 'Complete Now' (1800 diamonds) is never tapped - every tap
is checked against its plate - and a confirm dialog is always cancelled.
No keyevent BACK in here: in homestead menus it opens the exit-game dialog
(Hermes, live 2026-11-04); the dialog is left via its own back plate. An
unrecognised screen stops the run (rc 1) without a tap.

Usage: python scripts/afk_homestead_upgrade.py [--dry-run] [--min-idle S]
Exit codes: 0 an upgrade started (Spire path or upgrade-all - also when a later step got stuck: the
watch marker must stop the phase for today, the normalizer handles the screen), 1 stuck / unknown
screen (also: no Interact radial after the tower tap), 4 nothing to do (no Level Up radial,
no Spire upgrade icon and no tower after the camera search,
requirements missing, queue full, Level Up refused), 5 skipped (PC in use),
7 tap lock held by another run.
"""
from __future__ import annotations

import argparse
import math
import re
import sys
import time
from pathlib import Path

from PIL import ImageChops

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
# LIVE (T105B, shots-59732): both drags DO pan - Kitchen pin (1100,250) -> (1082,504) -> (1472,282). shots-80480/hu_world (after the operator's 'Go' to the Kitchen): Kitchen selected,
# Spire door (512,705) vs (920,460) on the icon frames (spire_sel/shots-8632), ~1.1x zoom ->
# the icon would sit near (507,373), ON screen - and there is none there, so the icon is most
# likely ABSENT while another building has the focus (not just off the top edge); the deselect
# is the more promising step. Drag 1 = the brief's 'content down' (icon above the top edge),
# drag 2 = content right+up = back towards the usual Spire spot (80480: door -> ~(862,795), icon
# ~(858,506) inside ICON_BAND). Points on mid-screen ground: off the HUD (x 120..1800,
# y 80..1000), off the joystick (960,835) and the quest tracker; 350/408 px over 600 ms = a drag.
CAMERA_DRAGS = ((1300, 350, 1300, 650), (1150, 650, 1500, 440))
CAMERA_MS = 600
# --- T103d: the upgrade icon is FLAKY live (Hermes 2026-11-04: sometimes not drawn) -> tap the
# TOWER: the Spire gets selected and shows a radial with a white 'Interact' disc (tower_tap.png),
# whose tap opens the 'Upgrade Requirement' dialog (operator, live). The camera moves, so the tower
# is found on the frame. Tell: 4 golden light beams rise from the tower's buttresses - an outer pair
# at axis +-s/2 and an inner pair at axis +-s/4, 20..125 px lower. LIVE (outer dx / inner dx / axis /
# inner-mid minus outer-mid): tower_tap 229/116/915/+67, shots-80480 229/114/504/+85 (door (512,705)),
# norm_3 200/98/813/+40, hm_requests 208/105/898/+53 (door (905,430)), hs_0_world 211/107/917/+105,
# spire_sel 210/109/917/+50 (door (920,450)). The beams flicker (one may be missing or short on a
# frame) -> any 3 of the 4 at their geometric places. Sweep: 162 hits on the 358 WORLD frames of
# .spectre (+trash) + hermes scratch, all on the tower body (contact sheets); misses = tower cut by
# the screen edge / HUD or toasts over the beams (quest1).
BEAM_WIN = (120, 60, 1800, 1000)   # world area searched (HUD columns outside)
BEAM_D = 14                    # streak contrast against the pixels BEAM_D left and right (beams 6..22 px)
BEAM_DAY = (170, 40, 25)       # R >=, G-B >=, G-B above both neighbours by >=. LIVE beam (245,220,112),
                               # beside it (127,131,126) (hm_requests); sunset (219,185,67) vs (228,166,109)
BEAM_NIGHT = (150, 148, 40)    # R >=, R-B+128 >= (R-B >= 20), R-B above both neighbours by >=. LIVE deep
                               # night ck2: beam (211,194,142) vs (147,158,157)/(40,117,206) - G-B fails there
BEAM_H, BEAM_W, BEAM_ASPECT = 35, 30, 2.5  # a beam: >= 35 px tall, <= 30 px wide, h >= 2.5 w (LIVE 37..140 tall)
BEAM_PAIR_DY = 40              # a pair's beams: mid heights within 40 px (LIVE <= 26)
INNER_DX = (80, 130)           # LIVE inner pair spacing 98..116
OUTER_DX = (160, 260)          # LIVE outer pair spacing 200..229
INNER_DROP = (20, 125)         # inner mid below outer mid, LIVE +40..+105
BEAM_TOL = 12                  # x tolerance of the 3rd/4th beam at its expected place (LIVE axis spread <= 7)
# T103e: live start frame shots-25208/hu_world - the Spire was ALREADY selected ('Interact' disc
# (953,683), beam axis 916, tower tap point (916,508)); our tower tap deselected it and the next
# frame (hu_tower) showed the floating upgrade icon at (915,378) instead of a radial. An 'Interact'
# disc counts as the Spire's only right below the found tower axis (dx 37 / dy 175 measured;
# another building's radial sits elsewhere - the dialog check stays the safety net).
INTERACT_TOWER_DX = 100
INTERACT_TOWER_DY = (60, 300)
TOWER_WAIT = 2.0               # LIVE-unverified: the camera recentres on the selected tower (tower_tap)
INTERACT_RING = ((-30, 0), (30, 0), (0, -30), (0, 30))  # cream (L > 215) around the 'Interact' disc centre.
                               # LIVE tower_tap: OCR box (927,731,66,15), 5024 cream px, median (953,683),
                               # ring L 245/245/249/249, disc radius ~43; the hand glyph sits off-centre
                               # (no dark centre like the Level Up arrow -> disc_at does not apply)
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
COMPLETE_NOW = (530, 960, 1012, 1052)  # LIVE: diamond plate - NEVER tapped. hm_up3 grey plate from
                                       # x 539; T105B shots-57584/hu_bread (Kitchen) ORANGE plate x 536..1005
                                       # at y 1040 (545..1005 at y 975) -> widened from (538,967,1005,1047)
# T103f: live shots-49372/hu_read - the dialog opened, OCR read 'Upgrade Requirement (5/7)' and
# every card, but NOT the 'Radiant Spire' title (still fading in) -> 'dialog not recognised'.
# The dialog = requirement line + back plate; the title is re-read once after TITLE_SETTLE.
TITLE_SETTLE = 1.5
# T103h live (shots-68132): after the icon tap hu_dialog/hu_read showed the dialog still fading
# in (blurred world, faint buttons) -> OCR [] and no back plate -> 'dialog not recognised'.
# Poll the dialog DIALOG_POLLS x DIALOG_POLL_WAIT before the check (and its no-tap guard).
DIALOG_POLLS = 3
DIALOG_POLL_WAIT = 1.5
# T103f 'Go' on a missing building card (one level, bounded). The 'Go' pill sits under the card
# label: label 'Level 5 Kitchen' centre (531,616) -> pill centre (531,640) (hu_read, hm_up3: white
# L>=246 at x +-25, 'Go' text L~175). Go -> world with that building selected (kitchen_go.png,
# shots-80480): its small 'Level Up' radial disc (1054,730) sits 30 px above its 'Level U' text
# (centre (1051,760)), cream L>=226 at +-25 px, dark arrow L 80..117. LIVE (T105B): the Kitchen's own
# dialog after that tap = shots-57584/hu_bread (same layout as the Spire's).
GO_DY = 24
GO_PILL_DX = 25
SMALL_DISC_DY = 30
SMALL_DISC_R = 25
GO_WAIT = 3.0
# T103g live (shots-14680/hu_go after Go -> Kitchen): OCR read 'Cook' + 'Kitchen' but NOT the small
# 'Level Up' text (Hermes' kn2.png: 'l_evel CP'). Its disc sat at (1054,730) on all three Kitchen
# frames (hu_go, kn2, shots-80480) = the 'Cook' text centre (959,738) + (95,-8); the Cook disc
# passes small_disc_at too, so the fallback searches only +-ANCHOR_R around that offset.
COOK_TO_LU = (95, -8)
ANCHOR_R = 4                   # LIVE: the real disc passes at r 0 (hu_go, kn2, 80480: dy -4..+4); the 'Speed Up'
                               # hourglass (57584/hu_after) only at dy +8..+10 -> never reached (was 10)
BUILDING_RE = re.compile(r'level\s*\d+\s+([a-z][a-z ]+)', re.I)   # 'Level 5 Kitchen' -> kitchen
BTN_NEAR = 40                  # an OCR 'Level Up' box centre must be this close to LEVEL_UP_BTN
# --- T105B upgrade-all: quest building first, then buildings with a green upgrade pin ------------
NAME_DX = 230                  # building_level_up: name label vs 'Level U' text centre in x. LIVE: Ore Refinery
                               # (962,365)/(1167,725) dx 205..206 (trash/shots-38632 bm_0/bm_1/rw_0, shots-31044
                               # norm_1), Kitchen dx 10..20 (80480, 57584/hu_world). Spire path keeps LABEL_DX
ARROW_TIP = 6                  # dark px (L<120, r 20) in the topmost dark row = an up-arrow's tip. LIVE 1..5:
                               # compact rq_ck_k (1149,300) 1, spire_sel (915,171) 3, 25208/hu_tower 1, Kitchen
                               # small disc 80480 (1051,730) 1, Spire big disc hm_requests (956,686) 5; the
                               # 'Speed Up' HOURGLASS (shots-57584/hu_after (1052,730)) 20
UPGRADED_WORD = 'upgraded'     # LIVE Hermes rq0: (750,329,425,59,'Kitchen Upgraded') + 'Tapto Close' whose
                               # centre (960,1021) = hs.TOAST_CLOSE (POPUP, no back plate)
QUEST_WIN = (0, 880, 360, 960)  # LIVE: tracker box (180,901,63,20,'Refinery') on 57584/hu_world, 80480,
                                # tower_tap, fin3, 42848/rq_ck_w; rq1 OCR-shifted (190,921) still inside
QUEST_BUILDINGS = ('refinery', 'kitchen', 'forge')  # refinery LIVE (tracker 'Upgrade the Ore Refinery to
                               # Level 5'); kitchen/forge = requirement card names (hm_up3). Spire: own path
QUEST_PILL = (70, 900, 250, 940)  # LIVE: orange tracker pill x 0..262 y 891..939 (220,131,35): 4963..4998
QUEST_PILL_PX = 3600              # of 7200 px on 57584/hu_world, hm_requests, quest1, rq1; 0 on zone2 / hm_up3
QUEST_TAP = (160, 915)         # on the pill, off the gift badge (~50,903) / Story tab / AFK Progress.
                               # LIVE-open: what the tap opens (only a dialog or a labelled radial is used)
PIN_BAND = (120, 40, 1800, 860)   # LIVE: green upgrade pins at x 562..1736, y 56..564 (129 hits, 247 frames);
                                  # a 'Full' badge at (1782,888) (trash/shots-48532/dg_cam_2) passes pin_at -> y <= 860
PIN_MIN = (20, 50, 30, 6)      # IN green / MID dark / RIM green / rim octants >=. LIVE 57584/hu_world
                               # (1108,299) 35/69/62/8, (1593,68) 33/77/47/8; fog 59732 (1376,122) 32/63/32/6
PIN_OUT_MAX = 10               # green px at r 17..20 (LIVE 0): a bounded pin, not grass
PIN_CLUSTER = 20
PIN_WAIT = 1.5                 # LIVE-unverified (no frame of a pin tap)
PIN_ICON_R = 200               # compact Level Up disc near the tapped pin (scan window pin +-R, not ICON_BAND:
                               # pins reach x 1736 / y 564, the disc ~(+2,+14) from its pin): Kitchen pin camera-corrected
                               # ~(1147,286) vs its disc (1149,300) on rq_ck_k (derived, LIVE-open)
PIN_TO_BODY = (-107, 124)      # pin -> building body: Kitchen pin ~(1147,286) vs Hermes' body tap (1040,410)
                               # that selected it (rq_ck_w -> rq_ck_k). Kitchen only, LIVE-open elsewhere
TITLE_WIN = (700, 345, 1220, 400)  # LIVE dialog titles: "Kitchen 'i" (898,367,113,21) hu_bread, '? Radiant
                                   # Spire i' (844,364,199,27) hm_up3; 'Lvl. 4?Lvl. 5' y 309 is outside
MAX_UPGRADES = 2               # brief: 1-2 level-ups per run (the phase runs once a day)
MAX_PINS = 3                   # pins tried per run


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


def _disc_above(img, box):
    """Median of the cream disc px above a radial's OCR text box, else None."""
    cx, cy = _centre(box)
    dx, up, down = DISC_WIN
    pts = hs._pixels(img, (cx - dx, cy - up, cx + dx, cy - down),
                     lambda r, g, b: min(r, g, b) > 215 and max(r, g, b) - min(r, g, b) < 30)
    return hs._median(pts) if len(pts) >= DISC_PX else None


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
    xy = _disc_above(img, lu)
    return xy if xy and disc_at(img, xy) else None


def interact_at(img, xy) -> bool:
    return all(v.lum(v.avg(img, (xy[0] + dx, xy[1] + dy), r=3)) > 215 for dx, dy in INTERACT_RING)


def find_interact(img, boxes):
    """T103d: the 'Interact' disc of the radial after OUR tower tap (no label on tower_tap), else None."""
    it = _line(boxes, 'interact', RADIAL_WIN)
    xy = it and _disc_above(img, it)
    return xy if xy and interact_at(img, xy) else None


def spire_interact(img, boxes, tower):
    """T103e: the selected Spire's 'Interact' disc on a frame where the tower was found, else None."""
    xy = tower and find_interact(img, boxes)
    if xy and abs(xy[0] - tower[0]) <= INTERACT_TOWER_DX and \
            INTERACT_TOWER_DY[0] <= xy[1] - tower[1] <= INTERACT_TOWER_DY[1]:
        return xy
    return None


def _beams(img):
    """(x centre, top, bottom) of every narrow vertical warm streak in BEAM_WIN (the tower's light beams)."""
    r, g, b = img.convert('RGB').split()

    def cut(ch, t):
        return ch.point(lambda p: 255 if p >= t else 0)

    def streak(diff, rmin, dmin, con):           # warm enough, and warmer than both neighbours
        m = ImageChops.multiply(cut(r, rmin), cut(diff, dmin))
        for dx in (BEAM_D, -BEAM_D):
            m = ImageChops.multiply(m, cut(ImageChops.subtract(diff, ImageChops.offset(diff, dx, 0)), con))
        return m
    mask = ImageChops.lighter(streak(ImageChops.subtract(g, b), *BEAM_DAY),
                              streak(ImageChops.subtract(r, b, 1, 128), *BEAM_NIGHT)).crop(BEAM_WIN)
    w, data = mask.width, mask.tobytes()
    runs = []                                     # vertical runs per column, gaps <= 4 px bridged
    for x in range(w):
        y0 = last = None
        for y in (i for i, p in enumerate(data[x::w]) if p):
            if y0 is None:
                y0 = y
            elif y - last > 4:
                runs.append((x, y0, last))
                y0 = y
            last = y
        if y0 is not None:
            runs.append((x, y0, last))
    par = list(range(len(runs)))                  # union runs of columns 1..2 apart that overlap in y

    def root(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i
    byx = {}
    for i, (x, y0, y1) in enumerate(runs):
        byx.setdefault(x, []).append(i)
        for j in byx.get(x - 1, []) + byx.get(x - 2, []):
            if runs[j][1] <= y1 + 2 and y0 <= runs[j][2] + 2:
                par[root(i)] = root(j)
    comps = {}
    for i, run in enumerate(runs):
        comps.setdefault(root(i), []).append(run)
    out = []
    for rs in comps.values():
        x0, x1 = min(q[0] for q in rs), max(q[0] for q in rs)
        y0, y1 = min(q[1] for q in rs), max(q[2] for q in rs)
        if y1 - y0 >= BEAM_H and x1 - x0 <= BEAM_W and y1 - y0 >= BEAM_ASPECT * (x1 - x0 + 1):
            out.append(((x0 + x1) / 2 + BEAM_WIN[0], y0 + BEAM_WIN[1], y1 + BEAM_WIN[1]))
    return sorted(out)


def spire_tower(img):
    """T103d: tap point ON the Spire's tower body, else None: on the beams' axis at the outer beams'
    mid height. Any pair (inner or outer) + >= 1 beam at its expected place; most beams, then the
    smallest x error wins. The point is >= s/4 (~50 px) off every beam: the beams are flickering
    particle light (no collider to expect) - the tower body is what the operator tapped live."""
    bs = _beams(img)
    mid = lambda q: (q[1] + q[2]) / 2  # noqa: E731
    best = None
    for i, a in enumerate(bs):
        for b in bs[i + 1:]:
            dx, cx, m = b[0] - a[0], (a[0] + b[0]) / 2, (mid(a) + mid(b)) / 2
            if abs(mid(a) - mid(b)) > BEAM_PAIR_DY:
                continue
            if INNER_DX[0] <= dx <= INNER_DX[1]:        # inner pair -> outer beams at cx +- dx, higher
                exp = [(cx + s * dx, m - INNER_DROP[1], m - INNER_DROP[0]) for s in (-1, 1)]
            elif OUTER_DX[0] <= dx <= OUTER_DX[1]:      # outer pair -> inner beams at cx +- dx/4, lower
                exp = [(cx + s * dx / 4, m + INNER_DROP[0], m + INNER_DROP[1]) for s in (-1, 1)]
            else:
                continue
            more, err = [], 0
            for ex, lo, hi in exp:
                c = [q for q in bs if abs(q[0] - ex) <= BEAM_TOL and lo <= mid(q) <= hi]
                if c:
                    q = min(c, key=lambda q: abs(q[0] - ex))
                    more.append(q)
                    err += abs(q[0] - ex)
            if not more:
                continue
            y = m if dx >= OUTER_DX[0] else sum(map(mid, more)) / len(more)
            hit = (len(more), -err, round(cx), round(y))
            if best is None or hit[:2] > best[:2]:
                best = hit
    if best is None:
        return None
    l, t, r, b = WORLD_WIN
    return best[2:] if l <= best[2] <= r and t <= best[3] <= b else None


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


def _clusters(pts, d):
    """Medians of the points grouped by their first hit (Chebyshev distance <= d), in scan order."""
    cl = []
    for p in pts:
        c = next((c for c in cl if max(abs(c[0][0] - p[0]), abs(c[0][1] - p[1])) <= d), None)
        if c:
            c.append(p)
        else:
            cl.append([p])
    return [hs._median(c) for c in cl]


def arrow_up(img, xy) -> bool:
    """T105B: the dark glyph within r 20 of xy ends in an up-arrow TIP (topmost dark row narrow),
    not the 'Speed Up' hourglass (flat top bar, 20 px)."""
    px = img.convert('RGB').load()
    rows = [dy for dx, dy in _DISC20 if v.lum(px[xy[0] + dx, xy[1] + dy]) < 120]
    return bool(rows) and rows.count(min(rows)) <= ARROW_TIP


def level_icons(img, band=ICON_BAND) -> list:
    """T105B: centres of ALL white-disc/up-arrow Level Up icons in `band` (topmost first): the
    floating Spire icon and the compact radial disc of any selected building (rq_ck_k)."""
    px = img.convert('RGB').load()
    l, t, r, b = band
    hits = [(x, y) for y in range(t, b, ICON_STEP) for x in range(l, r, ICON_STEP) if _icon_at(px, x, y)]
    return [c for c in _clusters(hits, ICON_CLUSTER) if arrow_up(img, c)]


def near_band(img, xy, r=PIN_ICON_R):
    """level_icons window +-r around xy, clipped so the ICON_OUT ring stays on the frame."""
    w, h = img.size
    l, t = (max(ICON_OUT + ICON_STEP, c - r) for c in xy)
    return (l - l % ICON_STEP, t - t % ICON_STEP,           # same scan grid as ICON_BAND (same centres)
            min(w - ICON_OUT - 1, xy[0] + r), min(h - ICON_OUT - 1, xy[1] + r))


def spire_icon(img):
    """Centre of the floating white-disc/dark-up-arrow upgrade icon in ICON_BAND, else None.
    shortcut: several such icons on screen -> the topmost one; the dialog OCR ('Radiant Spire')
    rejects another building's dialog. T105B: the same icon is the compact radial of ANY selected
    building (rq_ck_k) - harmless, upgrade_or_go upgrades whatever dialog opens, never diamonds."""
    icons = level_icons(img)
    return icons[0] if icons else None


def _ann(r0, r1):
    return [(dx, dy) for dx in range(-r1, r1 + 1) for dy in range(-r1, r1 + 1) if r0 * r0 <= dx * dx + dy * dy <= r1 * r1]


PIN_IN, PIN_MID, PIN_RIM, PIN_OUT = _ann(0, 4), _ann(6, 8), _ann(10, 13), _ann(17, 20)


def _pin_green(c) -> bool:                    # LIVE pin arrow/rim (146,214,125)
    return c[1] > 170 and c[1] - c[0] > 45 and c[1] - c[2] > 60


def pin_at(px, x, y) -> bool:
    """Green upgrade pin centred at (x, y): green arrow, dark disc, green rim all round, no green outside."""
    def green(pts):
        return sum(_pin_green(px[x + a, y + b]) for a, b in pts)
    if green(PIN_IN) < PIN_MIN[0] or green(PIN_OUT) > PIN_OUT_MAX:
        return False
    if sum(sum(px[x + a, y + b]) < 300 for a, b in PIN_MID) < PIN_MIN[1]:
        return False
    rim = [(a, b) for a, b in PIN_RIM if _pin_green(px[x + a, y + b])]
    return len(rim) >= PIN_MIN[2] and len({round(math.atan2(b, a) / (math.pi / 4)) % 8 for a, b in rim}) >= PIN_MIN[3]


def upgrade_pins(img) -> list:
    """T105B: centres of the green 'upgrade-ready' pins on the homestead world, topmost first.
    Seeds on the measured step-2 grid."""
    px = img.convert('RGB').load()
    seeds = [p for p in hs._pixels(img, PIN_BAND, lambda r, g, b: _pin_green((r, g, b)))
             if p[0] % 2 == 0 and p[1] % 2 == 0]
    return _clusters([p for p in seeds if pin_at(px, *p)], PIN_CLUSTER)


def title_name(boxes):
    """T105B: lower-case building name from the dialog title ("Kitchen 'i" -> 'kitchen'), else None."""
    for b in boxes:
        cx, cy = _centre(b)
        if TITLE_WIN[0] <= cx <= TITLE_WIN[2] and TITLE_WIN[1] <= cy <= TITLE_WIN[3]:
            words = re.findall(r'[A-Za-z]{3,}', b[4])
            if words:
                return ' '.join(words).lower()
    return None


def quest_building(boxes):
    """T105B: building named by the world quest tracker (bottom left), else None."""
    for b in boxes:
        cx, cy = _centre(b)
        if QUEST_WIN[0] <= cx <= QUEST_WIN[2] and QUEST_WIN[1] <= cy <= QUEST_WIN[3]:
            hit = next((n for n in QUEST_BUILDINGS if n in b[4].lower()), None)
            if hit:
                return hit
    return None


def quest_pill(img) -> bool:
    return len(hs._pixels(img, QUEST_PILL, lambda r, g, b: r > 200 and 110 < g < 190 and b < 110)) >= QUEST_PILL_PX


def camera_search():
    """T103c: no radial, no icon (T103d: and no tower) on the start frame -> deselect (GROUND),
    then up to len(CAMERA_DRAGS) drags; spire_icon, then spire_tower after each, only on the
    world view. (icon xy or None, tower xy or None, last frame)."""
    _tap(v.GROUND, 0.8)
    for i, drag in enumerate((None, *CAMERA_DRAGS)):
        if drag:
            v.swipe(*drag, CAMERA_MS, 1.5)
        img = v.shot(f'hu_cam{i}')
        if v.classify(img) != 'WORLD':
            return None, None, img
        xy = spire_icon(img)
        tower = None if xy else spire_tower(img)
        if xy or tower:
            return xy, tower, img
    return None, None, img


def parse_requirement(boxes):
    """(met, total) of an 'Upgrade Requirement (a/b)' dialog line, else None. T103f: the title
    ('Radiant Spire') is no longer required - it was still fading in on the live dialog."""
    for b in boxes:
        m = REQ_RE.search(b[4])
        if m and int(m.group(1)) <= int(m.group(2)):
            return int(m.group(1)), int(m.group(2))
    return None


def missing_cards(img, boxes) -> list[str]:
    """Labels of the requirement cards without a green check."""
    return [b[4] for b in missing_boxes(img, boxes)]


def missing_boxes(img, boxes) -> list:
    """OCR boxes of the requirement card labels without a green check."""
    out = []
    dx, y0, y1 = CHECK_BOX
    for b in boxes:
        cx, cy = _centre(b)
        if not CARD_ROW[0] <= cy <= CARD_ROW[1]:
            continue
        box = (cx - dx, b[1] + y0, cx + dx, b[1] + y1)
        if len(hs._pixels(img, box, lambda r, g, b_: g - max(r, b_) > 40)) < CHECK_PX:
            out.append(b)
    return out


def read_dialog(tag: str):
    """(frame, boxes) of a requirement dialog that may still be fading in: up to DIALOG_POLLS
    shots (`tag`, `tag`_p1, ...) DIALOG_POLL_WAIT apart until back plate + requirement line
    read; the last shot otherwise (the caller's check then decides)."""
    for i in range(DIALOG_POLLS):
        if i:
            time.sleep(DIALOG_POLL_WAIT)
        name = tag if i == 0 else f'{tag}_p{i}'
        img = v.shot(name)
        boxes = v.ocr_boxes(name)
        if back_plate(img) and parse_requirement(boxes):
            break
        if v.classify(img) == 'WORLD':          # the dialog closed again: no point polling on
            break
    return img, boxes


def go_pill(img, xy) -> bool:
    """White 'Go' pill under a missing card label."""
    return all(v.lum(v.avg(img, (xy[0] + dx, xy[1]), r=2)) > 225 for dx in (-GO_PILL_DX, GO_PILL_DX))


def small_disc_at(img, xy) -> bool:
    """A building's small radial 'Level Up' disc: dark arrow at xy, cream ring at SMALL_DISC_R."""
    x, y = xy
    r = SMALL_DISC_R
    return (v.lum(v.avg(img, xy, r=2)) < 160
            and all(v.lum(v.avg(img, (x + dx, y + dy), r=2)) > 200
                    for dx, dy in ((-r, 0), (r, 0), (0, -r), (0, r))))


def building_level_up(img, boxes, name: str | None):
    """Tap point of the selected `name` building's radial 'Level Up' disc ('Level U' as read),
    with its own name label above it (NAME_DX), else None. T105B: name None = any building;
    every disc must carry an up-arrow (arrow_up), and the Cook-anchor fallback is skipped while
    the radial reads 'Speed Up' (shots-57584/hu_after: it took the hourglass disc (1052,730))."""
    def labelled(cx, cy):
        return name is None or any(name in lb[4].lower() and abs(_centre(lb)[0] - cx) <= NAME_DX
                                   and _centre(lb)[1] < cy for lb in boxes)

    def disc(x, y):
        return small_disc_at(img, (x, y)) and arrow_up(img, (x, y))

    for b in boxes:
        text = b[4].lower()                     # 'Level U', T103g live 'l_evel CP'; not 'Level 4' sub-labels
        if 'evel' not in text or re.search(r'level\s*\d', text):
            continue
        cx, cy = _centre(b)
        if not (RADIAL_WIN[0] <= cx <= RADIAL_WIN[2] and RADIAL_WIN[1] <= cy <= RADIAL_WIN[3]) \
                or not labelled(cx, cy):
            continue
        for y in (cy - SMALL_DISC_DY, cy - SMALL_DISC_DY + 4, cy - SMALL_DISC_DY - 4):
            for x in range(cx - 8, cx + 9, 4):  # the arrow sits a few px right of the text centre
                if disc(x, y):
                    return x, y
    # T103g: Level Up text unread -> anchor on 'Cook'. T105B: never while 'Speed Up' is read, nor when
    # 'Level U' WAS read cleanly but its disc failed above; ANCHOR_R 4 keeps the hourglass (dy +8) out
    cook = _line(boxes, 'cook', RADIAL_WIN)
    if name and cook and labelled(*_centre(cook)) and not _line(boxes, 'eed', RADIAL_WIN) \
            and not _line(boxes, 'level u', RADIAL_WIN):
        ax, ay = _centre(cook)[0] + COOK_TO_LU[0], _centre(cook)[1] + COOK_TO_LU[1]
        for r in range(0, ANCHOR_R + 1, 2):
            for x, y in ((ax + dx, ay + dy) for dx in (-r, 0, r) for dy in (-r, 0, r)):
                if disc(x, y):
                    return x, y
    return None


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

    rc = spire(args.dry_run)
    if rc not in (0, 4):
        return rc
    rc2 = upgrade_all(MAX_UPGRADES - (rc == 0), args.dry_run)   # T105B: quest building, then pins
    if rc == 0 and rc2 == 1:     # a started Spire upgrade must still write today's watch marker
        print('    Spire upgrade started; upgrade-all got stuck -> rc 0', flush=True)
    return 0 if 0 in (rc, rc2) else (1 if rc2 == 1 else 4)


def spire(dry_run: bool) -> int:
    """T103..T103i: the Radiant Spire path (also owns the start frame). Exit code."""
    name = 'hu_world'
    img = v.shot(name)
    if v.is_confirm_dialog(img):                 # T103c: 'exit the game?' (shots-9308) - X only
        print('    confirm dialog on the start frame -> X (never the check)', flush=True)
        _tap(v.CONFIRM_CANCEL, 1.5)
        name = 'hu_world_c'
        img = v.shot(name)
    if v.classify(img) != 'WORLD' and not back_plate(img):
        ob = v.ocr_boxes(name)                   # T105B: 'Kitchen Upgraded' overlay (Hermes rq0), once
        if _line(ob, UPGRADED_WORD) and _line(ob, 'close') and not _line(ob, 'complete'):
            print('    upgrade-finished overlay -> Tap to close', flush=True)
            # v.tap, not _tap: TOAST_CLOSE lies in the COMPLETE_NOW box, but this OCR-verified
            # overlay has no Complete Now plate (no back plate, no dialog)
            v.tap(hs.TOAST_CLOSE, 1.5)
            name = 'hu_world_u'
            img = v.shot(name)
    if v.classify(img) == 'WORLD':
        boxes = v.ocr_boxes(name)
        disc = find_radial(img, boxes)
        still = lambda im: v.classify(im) == 'WORLD' and disc_at(im, disc)  # noqa: E731
        if disc is None:                         # T103b: unselected Spire, floating icon
            disc = spire_icon(img)
            still = lambda im: v.classify(im) == 'WORLD' and spire_icon(im) is not None  # noqa: E731
        selected = _line(boxes, SPIRE_LABEL, WORLD_WIN) is not None
        tower = None
        if disc is None and not selected:        # T103d: icon flaky live -> the tower itself
            tower = spire_tower(img)
            disc = spire_interact(img, boxes, tower)
            if disc:                             # T103e: Spire already selected -> its Interact
                print(f'    Spire already selected: Interact at {disc}', flush=True)
                still = lambda im: v.classify(im) == 'WORLD' and interact_at(im, disc)  # noqa: E731
                tower = None
            elif tower is None:                  # T103c: another building focused / camera moved
                disc, tower, img = camera_search()
                if v.classify(img) != 'WORLD':
                    print('    ERROR: camera search left the world view - stopping without a tap', flush=True)
                    return 1
                if disc:
                    print(f'    upgrade icon at {disc} after the camera search', flush=True)
        if tower:
            print(f'    no upgrade icon: tapping the Spire tower at {tower}', flush=True)
            _tap(tower, TOWER_WAIT)
            img = v.shot('hu_tower')
            boxes = v.ocr_boxes('hu_tower') if v.classify(img) == 'WORLD' else []
            disc = find_radial(img, boxes)       # label-paired Level Up, as on the start frame
            still = lambda im: v.classify(im) == 'WORLD' and disc_at(im, disc)  # noqa: E731
            if disc is None:
                disc = find_interact(img, boxes)
                still = lambda im: v.classify(im) == 'WORLD' and interact_at(im, disc)  # noqa: E731
            if disc is None and v.classify(img) == 'WORLD':
                # T103e: the tap toggled a selection OFF (shots-25208/hu_tower) -> the icon shows now
                disc = spire_icon(img)
                still = lambda im: v.classify(im) == 'WORLD' and spire_icon(im) is not None  # noqa: E731
                if disc:
                    print(f'    tower tap deselected the Spire: upgrade icon at {disc}', flush=True)
            if disc is None:
                print(f'    ERROR: no Interact/Level Up radial after the tower tap '
                      f'(OCR {[b[4] for b in boxes][:6]}) - stopping without a tap', flush=True)
                return 1
        if disc is None:
            why = ('Spire selected but no Level Up on its radial (upgrading / max?)' if selected else
                   'no Level Up radial, no upgrade icon and no tower, also after the camera search')
            print(f'    nothing to do: {why}', flush=True)
            return 4
        img = hs.tap_until(disc, 2.5, 'hu_dialog', lambda im: v.classify(im) != 'WORLD', still)
        if img is None:
            print(f'    ERROR: Spire dialog did not open after the tap at {disc}', flush=True)
            return 1
        img, boxes = read_dialog('hu_read')      # T103h: settled frame for OCR + check pixels
    elif back_plate(img) and parse_requirement(boxes := v.ocr_boxes(name)):
        print('    Spire dialog already open', flush=True)  # T103b: live start frame shots-82892
    else:
        print('    ERROR: not on the world view or the Spire dialog (no BACK key in the homestead)',
              flush=True)
        return 1
    req = parse_requirement(boxes)
    if req is None or not back_plate(img):
        print(f'    ERROR: Spire dialog not recognised (OCR {[b[4] for b in boxes][:6]})', flush=True)
        close_dialog(img)
        return 1
    if _line(boxes, SPIRE_LABEL) is None:      # T103f: title still fading in -> one settled re-read
        time.sleep(TITLE_SETTLE)
        img2 = v.shot('hu_read2')
        boxes2 = v.ocr_boxes('hu_read2')
        if back_plate(img2) and parse_requirement(boxes2):
            img, boxes = img2, boxes2
        title = 'Radiant Spire' if _line(boxes, SPIRE_LABEL) else 'title unread (reached via the Spire)'
        print(f'    dialog: {title}', flush=True)
    return upgrade_or_go(img, boxes, 'Radiant Spire', dry_run, go=True)


def resolve(tag: str, near, name=None, icons=True, ignore=None):
    """T105B: after a pin / tracker tap, poll up to DIALOG_POLLS shots (no taps) for what opened:
    ('dialog', frame, boxes) | ('disc', xy, None) a labelled radial Level Up (not the one at `ignore`,
    already up before the tap) | ('icon', xy, None) a compact Level Up within PIN_ICON_R of `near` |
    ('none', frame, boxes) on the world | ('stuck', frame, boxes)."""
    for i in range(DIALOG_POLLS):
        if i:
            time.sleep(DIALOG_POLL_WAIT)
        shot = tag if i == 0 else f'{tag}_p{i}'
        img = v.shot(shot)
        boxes = v.ocr_boxes(shot)
        if back_plate(img) and parse_requirement(boxes):
            return 'dialog', img, boxes
        if v.classify(img) == 'WORLD':
            disc = building_level_up(img, boxes, name)
            if disc and not (ignore and max(abs(disc[0] - ignore[0]), abs(disc[1] - ignore[1])) <= ICON_CLUSTER):
                return 'disc', disc, None
            found = (level_icons(img, near_band(img, near)) if near else level_icons(img)) if icons else []
            if near:
                found.sort(key=lambda p: (p[0] - near[0]) ** 2 + (p[1] - near[1]) ** 2)
            if found:
                return 'icon', found[0], None
    return ('none' if v.classify(img) == 'WORLD' else 'stuck'), img, boxes


def upgrade_target(kind: str, a, boxes, k, parked: set, dry_run: bool):
    """T105B: open the building dialog (disc/icon tap) or take the open one, then upgrade_or_go
    without Go. (exit code, building name, build queue full)."""
    if kind in ('disc', 'icon'):
        if kind == 'disc':
            still = lambda im: v.classify(im) == 'WORLD' and small_disc_at(im, a)  # noqa: E731
        else:
            still = lambda im: v.classify(im) == 'WORLD' and any(  # noqa: E731
                max(abs(p[0] - a[0]), abs(p[1] - a[1])) <= ICON_CLUSTER for p in level_icons(im, near_band(im, a)))
        img = hs.tap_until(a, 2.5, f'ua_dialog{k}', lambda im: v.classify(im) != 'WORLD', still)
        if img is None:
            print(f'    ERROR: no dialog after the Level Up tap at {a} - stopping', flush=True)
            return 1, None, False
        img, boxes = read_dialog(f'ua_read{k}')
    else:
        img = a
    if not (back_plate(img) and parse_requirement(boxes)):
        print(f'    ERROR: building dialog not recognised (OCR {[b[4] for b in boxes][:6]})', flush=True)
        if back_plate(img):
            close_dialog(img)
        return 1, None, False
    name = title_name(boxes) or f'building {k}'
    if name in parked:
        print(f'    {name} already parked this run - closing', flush=True)
        return (4 if close_dialog(img) else 1), name, False
    q = parse_queue(boxes)
    return upgrade_or_go(img, boxes, name, dry_run, go=False), name, bool(q and q[0] >= q[1])


def _in(xy, win) -> bool:
    return win[0] <= xy[0] <= win[2] and win[1] <= xy[1] <= win[3]


def upgrade_all(budget: int, dry_run: bool) -> int:
    """T105B: up to `budget` level-ups: the quest-tracker building's radial when already selected, then
    buildings with a green upgrade pin (MAX_PINS), then (LIVE-open) the tracker tap. Resource-short /
    refused -> parked for this run, next one. Build queue full -> stop. Exit code (0 one started, also
    when a later step got stuck; 4 none; 1 stuck before any start)."""
    img = v.shot('ua_world')
    if v.classify(img) != 'WORLD':
        print('    ERROR: upgrade-all: not on the world view - stopping without a tap', flush=True)
        return 1
    boxes = v.ocr_boxes('ua_world')
    done, parked, tried, full = 0, set(), [], False

    def stop(why: str) -> int:
        print(f'    ERROR: {why} - stopping without a tap'
              + (f' ({done} level-up(s) already started -> rc 0)' if done else ''), flush=True)
        return 0 if done else 1

    def take(kind, a, b, k):
        nonlocal done, full
        rc, nm, full = upgrade_target(kind, a, b, k, parked, dry_run)
        done += rc == 0
        if rc == 4:
            parked.add(nm)
        return rc

    quest = quest_building(boxes) if quest_pill(img) else None
    disc = building_level_up(img, boxes, quest) if quest and budget else None   # quest building selected
    if disc and take('disc', disc, None, 'q') == 1:
        return stop(f'quest {quest} dialog')
    for k in range(MAX_PINS):
        if done >= budget or full:
            break
        img = v.shot(f'ua_pins{k}')
        if v.classify(img) != 'WORLD':
            return stop('upgrade-all: not on the world view')
        pins = [p for p in upgrade_pins(img)
                if all(max(abs(p[0] - q[0]), abs(p[1] - q[1])) > PIN_CLUSTER for q in tried)]
        if not pins:
            break
        pin = pins[0]
        tried.append(pin)
        stale = building_level_up(img, v.ocr_boxes(f'ua_pins{k}'), None)   # a radial already up is not the pin's
        print(f'    upgrade pin at {pin}', flush=True)
        _tap(pin, PIN_WAIT)
        kind, a, b = resolve(f'ua_pin{k}', pin, ignore=stale)
        body = (pin[0] + PIN_TO_BODY[0], pin[1] + PIN_TO_BODY[1])
        if kind == 'none' and _in(body, WORLD_WIN) and any(          # blind body tap only on an unchanged view
                max(abs(p[0] - pin[0]), abs(p[1] - pin[1])) <= PIN_CLUSTER for p in upgrade_pins(a)):
            print(f'    pin tap opened nothing -> building body {body} (LIVE-open)', flush=True)
            _tap(body, PIN_WAIT)
            kind, a, b = resolve(f'ua_body{k}', pin, ignore=stale)
        if kind == 'none':
            print(f'    pin {pin}: no Level Up after the taps - parked', flush=True)
            continue
        if kind == 'stuck':
            if back_plate(a) and close_dialog(a):
                print(f'    pin {pin}: unrecognised dialog closed via its back plate - parked', flush=True)
                continue
            return stop('unknown screen after the pin tap')
        if take(kind, a, b, k) == 1:
            return stop('building dialog')
    if quest and not full and done < budget and not any(quest in p for p in parked):
        img = v.shot('ua_qworld')                                    # LIVE-open tracker tap: last
        if v.classify(img) != 'WORLD':
            return stop('upgrade-all: not on the world view')
        if quest_pill(img):
            print(f'    quest {quest}: tracker tap (LIVE-open)', flush=True)
            _tap(QUEST_TAP, GO_WAIT)
            kind, a, b = resolve('ua_quest', None, quest, icons=False)
            if kind == 'stuck' and not (back_plate(a) and close_dialog(a)):
                return stop('unknown screen after the quest tracker tap')
            if kind == 'none':
                print(f'    quest {quest}: no Level Up reached', flush=True)
            elif kind in ('dialog', 'disc') and take(kind, a, b, 'q') == 1:
                return stop(f'quest {quest} dialog')
    print(f'    upgrade-all: {done} level-up(s) started, parked {sorted(parked)}', flush=True)
    return 0 if done else 4


def upgrade_or_go(img, boxes, name: str, dry_run: bool, go: bool) -> int:
    """Open requirement dialog of `name`: 7/7 + queue free -> Level Up; a missing building card
    -> its 'Go' (only when go=True: one level, bounded); else close. Exit code."""
    met, total = parse_requirement(boxes)
    queue = parse_queue(boxes)
    print(f'    {name} requirements {met}/{total}, build queue {queue}', flush=True)
    if met < total:
        missing = missing_boxes(img, boxes)
        print(f'    missing: {[b[4] for b in missing]}', flush=True)
        building = next((b for b in missing if BUILDING_RE.search(b[4])), None)
        if go and building and not dry_run:
            return go_building(img, building, dry_run)
        return 4 if close_dialog(img) else 1
    if queue and queue[0] >= queue[1]:
        print('    build queue full', flush=True)
        return 4 if close_dialog(img) else 1
    lu = _line(boxes, 'level up')
    if lu is None or max(abs(a - b) for a, b in zip(_centre(lu), LEVEL_UP_BTN)) > BTN_NEAR:
        print('    ERROR: dialog Level Up button not read at its place', flush=True)
        close_dialog(img)
        return 1
    if dry_run:
        print('    dry run: 7/7, not tapping Level Up', flush=True)
        return 0 if close_dialog(img) else 1
    _tap(LEVEL_UP_BTN, 3.0)
    img = v.shot('hu_after')
    if v.is_confirm_dialog(img):
        _tap(v.CONFIRM_CANCEL, 1.5)               # never spend diamonds
        print('    confirm/purchase dialog after Level Up -> cancelled', flush=True)
        return 4 if close_dialog(v.shot('hu_cancelled')) else 1
    if v.classify(img) == 'WORLD':
        print(f'    {name} upgrade started: dialog closed after Level Up (LIVE-open: timer)', flush=True)
        return 0
    if parse_requirement(v.ocr_boxes('hu_after')):
        print('    Level Up refused: dialog still up', flush=True)
        return 4 if close_dialog(img) else 1
    print('    ERROR: unknown screen after Level Up - stopping without a tap', flush=True)
    return 1


def go_building(img, label_box, dry_run: bool) -> int:
    """T103f: 'Go' under a missing 'Level N <Building>' card -> that building selected on the world
    -> its radial 'Level Up' -> its requirement dialog -> upgrade_or_go without a further Go.
    Every step verified on its frame; anything unexpected -> stop without a blind tap."""
    name = BUILDING_RE.search(label_box[4]).group(1).strip().lower()
    cx, cy = _centre(label_box)
    go = (cx, cy + GO_DY)
    if not go_pill(img, go):
        print(f'    no Go pill under {label_box[4]!r} - closing', flush=True)
        return 4 if close_dialog(img) else 1
    print(f'    Go -> {name} (requirement {label_box[4]!r})', flush=True)
    _tap(go, GO_WAIT)
    # T103i (Hermes live): after the Go jump the frame is still loading and the radial appears
    # late -> poll like T103h before 'no radial' (a transition frame is not yet an error)
    disc = None
    for i in range(DIALOG_POLLS):
        if i:
            time.sleep(DIALOG_POLL_WAIT)
        shot = 'hu_go' if i == 0 else f'hu_go_p{i}'
        img = v.shot(shot)
        if v.classify(img) == 'WORLD':
            disc = building_level_up(img, v.ocr_boxes(shot), name)
            if disc:
                break
    if disc is None and v.classify(img) != 'WORLD':
        print('    ERROR: Go did not lead to the world view - stopping without a tap', flush=True)
        return 1
    if disc is None:
        print(f'    nothing to do: no {name} Level Up radial after Go (LIVE: maxed / not selected?)',
              flush=True)
        return 4
    img = hs.tap_until(disc, 2.5, 'hu_bdialog', lambda im: v.classify(im) != 'WORLD',
                       lambda im: v.classify(im) == 'WORLD' and small_disc_at(im, disc))
    if img is None:
        print(f'    ERROR: {name} dialog did not open after its Level Up at {disc}', flush=True)
        return 1
    img, boxes = read_dialog('hu_bread')
    if not (back_plate(img) and parse_requirement(boxes)):
        print(f'    ERROR: {name} dialog not recognised (OCR {[b[4] for b in boxes][:6]})', flush=True)
        if back_plate(img):
            close_dialog(img)
        return 1
    return upgrade_or_go(img, boxes, name, dry_run, go=False)


if __name__ == '__main__':
    sys.exit(main())
