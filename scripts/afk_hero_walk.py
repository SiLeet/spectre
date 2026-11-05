#!/usr/bin/env python3
"""T111: walk the homestead hero towards a goal by ground taps, with the hero VERIFIED per frame.

Frames (offline recon, 424 WORLD frames of .spectre + trash + Hermes scratch):
  .spectre/shots-41556 (06:33) is the failing T103e chain: hu_world -> tower tap (339,168) -> hu_tower.
  The hero stands at (957,497), the tower point ~700 px away. hu_tower shows the floating upgrade icon at
  (330,48), but spire() missed it: classify(hu_tower) is UNKNOWN (a drifting harvest cloud lights the BACK
  probe (474,1010), lb-lg +40 > 25) and y 48 lies above ICON_BAND's top (60). spire_after_tower() fixes
  both (no-tap re-shots, icon searched right above the tower point) BEFORE any walk.
  The hero's distance is not shown to matter for the icon: its tap opened the Spire dialog at hero-tower
  d = 46 (49372), 151 (14680), 233 (spire_sel), ~450 (57584, 68132).
  'Interact' (953,683) is a fixed HUD disc for whatever stands next to the hero (st1/px3: up 700 px from
  the Spire); the Spire's own Interact only shows with the hero AT the tower (tower_tap, 25208/hu_world).
  The camera follows the hero: it rests at a fixed screen point (957+-6, 500+-8 on 49 frames with
  different scenery), so the goal is re-located on every frame (locate), never a fixed screen point.

Flow of walk_towards(locate, tap, tag): frame 0 must be WORLD (else 'not_world', no tap); goal = locate(img),
hero = hero(img); loop: d = |goal - hero| < stop -> 'arrived'; pick the farthest safe ground point on the
line hero blob centre -> goal (target()); tap; shot; not WORLD -> 'not_world' (the caller closes a dialog via
its back plate, else rc 1 - no further tap here); re-locate goal and hero (near the previous hero); d < stop
-> 'arrived' (checked BEFORE 'selected': the Spire's own Interact shows right there, T103e); Interact HUD
newly up or an avoid point (level icon) newly within SELECT_R of the tap -> 'selected'; gain < WALK_MIN_GAIN
on two consecutive taps -> 'stuck'; max_taps -> 'max'. Taps stay GOAL_CLEAR (< stop) off the goal, so a
hero that walks to its tap point can arrive.
Returns (status, img, goal, hero), status in arrived | stuck | selected | no_hero | no_goal | no_ground |
max | not_world - every status but 'arrived' is a soft stop for the caller.

Fallback: the brief's 'Spire Go teleport (T103f)' does not exist - the Go pill sits in the Spire's own
requirement dialog and jumps to a MISSING building (80480: Kitchen), i.e. it needs the dialog we failed to
open. The frame-backed fallback is the floating upgrade icon (T103b/e, tried first); after it the soft stop.

Frame-backed walk scene: ONLY the open field of the 41556 family (night palettes, hero ~700 px from the
tower: 41556, st0/st1, hm1, px4, upn0, 13076, 79896, 3300). In the Kitchen / Requests-arch scene (hero ~440 px
off) target() finds no ground and the hero is mostly not detected -> soft stop there (LIVE-open).
Hero recall (anchor window, 429 WORLD frames): 57 hits, all the hero but 3 camera-drag frames. hu_* upgrade
frames: 5/21 - 41556, 8632, 14680 hu_tower/hu_world_c, 49372/hu_world. Misses: daylight (68132, 80480, 63328,
49372/hu_close: median hue 31..67, no aura cluster), mist (59732, 25208), and the Kitchen scene 57584 (night
blue: hero side-on behind the arch, 18x36..48 / 185..205 px, or merged with the Kitchen's selection aura,
36x150). Relaxing HERO_W/HERO_PX to 18/190 gains 57584/hu_world only and adds a false hit (trash 50780/rw_2,
a daylight platform edge) -> not relaxed.
Ground: safe_ground() needs the frame in a MEASURED night palette (GROUND) and the tap patch plus its 4
neighbours in that palette's ground colour box (grass / path), so roofs, wood decks, the Spire base, trees,
water, the crop field and the Requests arch are rejected by colour; any other palette (day, mist, snow)
has no ground -> 'no_ground' soft stop (LIVE-open).

LIVE-open (no frame): whether a ground tap moves the hero at all, and how far (no frame pair shows any
displacement; Hermes' '~50 px/tap' is not on a frame) -> STEP_MAX, WALK_WAIT unmeasured (log: d per tap);
whether (960,835) is a joystick (a held swipe might be the real way to move); the Spire's Interact range
(WALK_STOP is a walk stop, not a proven Interact distance); whether a re-shot 1.5 s later is WORLD (13/15
frames at this camera are); impassable ground; day / snow / mist ground and hero; other camera families
(hero ~(1060,440): bm_0, sn_2, norm_3) are not detected; whether a tap on the Spire platform selects the Spire.
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402

HERO_ANCHOR = (957, 500)       # LIVE: 41556/hu_world (957,497); st0..hyg1 (954..960, 494..506)
HERO_SEARCH = (60, 50)         # LIVE: +-x/+-y around anchor / last hero. Wider (760..1160, 320..660): 14
                               # off-anchor hits, all false (Requests arch pillars, Spire stone, path
                               # stones, resource discs, blue orb). A global search: 487 hero-shaped blobs.
HERO_WHITE = (195, 40)         # min channel >=, max-min <=. LIVE night hero px (217,219,222), (203,203,213)
HERO_CELL = 6                  # mask pooled in 6x6 cells; a cell counts at mean >= HERO_OCC/255
HERO_OCC = 40
HERO_GRID = (120, 80)          # cell grid origin of the recon sweep (blob sizes below were measured on it)
HERO_W = (24, 42)              # LIVE blobs w x h / px: 41556 30x42/310, hm1 36x54/709, st0 30x60/453,
HERO_H = (36, 66)              # px4 30x54/723, spire_sel 36x54/572. 56 anchor-window hits on 424 WORLD
HERO_ASPECT = 1.25             # frames: 53 the hero, 3 false (camera-dragged dg_cam frames: 33704
HERO_PX = (240, 800)           # (930,473), 49112 (939,539), 79852 (915,545)) - not separable (measured).

WALK_WIN = (360, 120, 1560, 800)   # off the left HUD column / quest tracker / bottom bar / top resources /
                                   # right column / 'Login Rewards' banner (~1690,660)
JOYSTICK, JOYSTICK_R = (960, 835), 120
INTERACT_HUD, INTERACT_R = (953, 683), 110   # Interact disc r~43 + the clover disc (867,728)
HERO_CLEAR = 80                # LIVE 41556: a companion sat 60 px out on the line (std 60)
WALK_STOP = 250                # arrival distance (brief: ~250 px)
GOAL_CLEAR = 160               # taps stay this far off the goal: the Spire platform sits 160..220 px off the
                               # tower point on the 41556 line (line points 480..540 out: std 11.7..20, deck
                               # hue 153..154 - both rejected by safe_ground anyway). < WALK_STOP - STEP_MIN,
                               # so every d >= WALK_STOP still has a tap point STEP_MIN+ out.
AVOID_R = 60                   # off every avoid point (level icons, upgrade pins, tower point)
SELECT_R = 80                  # an avoid point newly this close to the tap = we selected something
GROUND_R = 12                  # patch +-12 px around the tap point
GROUND_STD = 10                # LIVE 41556 line, open ground: L std 0.9, 0.9, 3.3, 9.2; rejected: stepping
GROUND_L = 200                 # stones 24..26, flowers 20..22, companion 60, statue 18..60, platform
                               # 11.7..20, stone border 11.1. Mean L <= 200: no white disc / cloud.
GROUND = (                     # (frame: median HSV of WALK_WIN, patch: mean HSV of a GROUND_R patch), PIL 0..255
    # LIVE night teal: frames 41556/st1/upn0/hyg0/hyg1/79896/3300 rq_leave median (144..145, 146..148, 136..140);
    # ground patches (5..95 %) h 139..147 s 146..165 v 106..160. Rejected on 41556: mill roof (174,128,66),
    # crop field (226,44,84), pine (144,233,68), lantern pillar (163,136,93), Spire deck/base (153..154,128..129,
    # 107..108), canopy (154,157,84), (145,189,80). Daylight pond 68132 (140,151..169,116..138) would pass the
    # patch box - the frame gate drops day frames (median hue 30..97).
    (((139, 147), (144, 152), (130, 145)), ((136, 146), (140, 172), (115, 165))),
    # LIVE night blue: st0/hm1/px4/13076 hs_0_world/57584/kitchen_zone_live median (141..153, 175..185,
    # 165..190); ground (5..95 %) h 146..150 s 173..189 v 167..200. Mist pond tower_tap (148,186,138): frame
    # median s 73 -> no palette.
    (((141, 154), (174, 186), (160, 190)), ((145, 151), (165, 192), (160, 205))),
)
GROUND_NB = 24                 # the 4 neighbours +-24 px must pass the same patch box: no tap on a ground
                               # sliver next to a tree / building edge (41556: 321 -> 153 grid points, all grass)
STEP_MAX, STEP_MIN, STEP = 300, 90, 30   # LIVE-open: px per tap unmeasured (41556: k 300 -> (692,356))
WALK_WAIT = 1.5                # LIVE-open
WALK_MIN_GAIN = 30             # two taps in a row below this gain = stuck. LIVE: spire_tower re-locates the
                               # same tower 14..18 px apart on frames without any scene shift (57584, 68132,
                               # 14680 hu_world vs hu_tower) -> above that jitter; the real gain is LIVE-open
MAX_TAPS = 12
WALK_RESHOTS = 2               # T111: no-tap re-shots of a non-WORLD frame after the tower tap
RESHOT_WAIT = 1.5              # LIVE-open (the cloud drifts; 13/15 frames at the 41556 camera are WORLD)
ICON_TOWER_DY = -122           # LIVE: icon - tower point dy -111..-133, dx -1..-6 on 6 frames (25208 -122,
ICON_TOWER_R = 40              # 14680 -111, 57584 -124, 68132 -130, spire_sel -133, 41556 -115)


def _dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _blobs(img, win):
    """(cx, cy, w, h, px) of every white cluster in win (cells of HERO_CELL px, 8-connected)."""
    gx, gy = HERO_GRID
    l, t = win[0] - (win[0] - gx) % HERO_CELL, win[1] - (win[1] - gy) % HERO_CELL
    nx, ny = (win[2] - l) // HERO_CELL, (win[3] - t) // HERO_CELL     # whole cells: BOX = exact cell means
    r, g, b = img.convert('RGB').crop((l, t, l + nx * HERO_CELL, t + ny * HERO_CELL)).split()
    mn, mx = ImageChops.darker(ImageChops.darker(r, g), b), ImageChops.lighter(ImageChops.lighter(r, g), b)
    m = ImageChops.multiply(mn.point(lambda p: 255 if p >= HERO_WHITE[0] else 0),
                            ImageChops.subtract(mx, mn).point(lambda p: 255 if p <= HERO_WHITE[1] else 0))
    s = m.resize((nx, ny), Image.BOX)
    d = s.load()
    occ = {(x, y): d[x, y] for x in range(s.width) for y in range(s.height) if d[x, y] >= HERO_OCC}
    seen, out = set(), []
    for q0 in occ:
        if q0 in seen:
            continue
        stack, comp = [q0], []
        seen.add(q0)
        while stack:
            q = stack.pop()
            comp.append(q)
            for n in ((q[0] + dx, q[1] + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                if n in occ and n not in seen:
                    seen.add(n)
                    stack.append(n)
        xs, ys = [q[0] for q in comp], [q[1] for q in comp]
        out.append((l + (min(xs) + max(xs) + 1) * HERO_CELL // 2, t + (min(ys) + max(ys) + 1) * HERO_CELL // 2,
                    (max(xs) - min(xs) + 1) * HERO_CELL, (max(ys) - min(ys) + 1) * HERO_CELL,
                    sum(occ[q] for q in comp) * HERO_CELL * HERO_CELL // 255))
    return out


def hero(img, near=HERO_ANCHOR):
    """Centre (x, y) of the white hero aura blob closest to `near` within +-HERO_SEARCH, else None."""
    sx, sy = HERO_SEARCH
    win = (near[0] - sx - HERO_W[1], near[1] - sy - HERO_H[1], near[0] + sx + HERO_W[1], near[1] + sy + HERO_H[1])
    w, h = img.size
    win = (max(0, win[0]), max(0, win[1]), min(w, win[2]), min(h, win[3]))
    hits = [(x, y) for x, y, bw, bh, px in _blobs(img, win)
            if HERO_W[0] <= bw <= HERO_W[1] and HERO_H[0] <= bh <= HERO_H[1] and bh >= HERO_ASPECT * bw
            and HERO_PX[0] <= px <= HERO_PX[1] and abs(x - near[0]) <= sx and abs(y - near[1]) <= sy]
    return min(hits, key=lambda p: _dist(p, near)) if hits else None


def _inside(m, box) -> bool:
    return all(lo <= x <= hi for x, (lo, hi) in zip(m, box))


def ground_box(img):
    """Ground patch HSV box of the frame's measured night palette (GROUND), else None (day / mist / snow)."""
    m = ImageStat.Stat(img.convert('RGB').crop(WALK_WIN).reduce(8).convert('HSV')).median
    return next((patch for frame_box, patch in GROUND if _inside(m, frame_box)), None)


def safe_ground(img, p, hero_xy, goal, avoid=()) -> bool:
    """True when a tap at p lands on open ground: inside WALK_WIN, off the joystick / Interact HUD, off the
    hero, GOAL_CLEAR off the goal, AVOID_R off every avoid point, a flat, not-white L patch, and the patch and
    its 4 neighbours GROUND_NB out in the ground colour of the frame's palette."""
    l, t, r, b = WALK_WIN
    if not (l <= p[0] <= r and t <= p[1] <= b):
        return False
    if _dist(p, JOYSTICK) <= JOYSTICK_R or _dist(p, INTERACT_HUD) <= INTERACT_R:
        return False
    if _dist(p, hero_xy) < HERO_CLEAR or _dist(p, goal) < GOAL_CLEAR or any(_dist(p, a) < AVOID_R for a in avoid):
        return False
    box = ground_box(img)
    if box is None:
        return False
    st = ImageStat.Stat(img.convert('L').crop((p[0] - GROUND_R, p[1] - GROUND_R, p[0] + GROUND_R + 1, p[1] + GROUND_R + 1)))
    if st.stddev[0] > GROUND_STD or st.mean[0] > GROUND_L:
        return False
    r = GROUND_NB + GROUND_R
    hsv = img.crop((p[0] - r, p[1] - r, p[0] + r + 1, p[1] + r + 1)).convert('RGB').convert('HSV')
    return all(_inside(ImageStat.Stat(hsv.crop((r + dx - GROUND_R, r + dy - GROUND_R, r + dx + GROUND_R + 1,
                                                r + dy + GROUND_R + 1))).mean, box)
               for dx, dy in ((0, 0), (GROUND_NB, 0), (-GROUND_NB, 0), (0, GROUND_NB), (0, -GROUND_NB)))


def target(img, hero_xy, goal, avoid=()):
    """Farthest safe ground point on the line hero -> goal, STEP_MAX..STEP_MIN out, else None.
    The line starts at the blob centre (the LIVE 41556 line samples were measured from it, not the feet)."""
    fx, fy = hero_xy
    d = _dist((fx, fy), goal)
    if d == 0:
        return None
    ux, uy = (goal[0] - fx) / d, (goal[1] - fy) / d
    k = min(d - GOAL_CLEAR, STEP_MAX)
    k -= (k - STEP_MIN) % STEP if k >= STEP_MIN else 0     # on the STEP grid from STEP_MIN
    while k >= STEP_MIN:
        p = (round(fx + ux * k), round(fy + uy * k))
        if safe_ground(img, p, hero_xy, goal, avoid):
            return p
        k -= STEP
    return None


def walk_towards(locate, tap, tag, max_taps=MAX_TAPS, stop=WALK_STOP, wait=WALK_WAIT,
                 avoid=lambda img: [], interact=lambda img: False):
    """Ground taps towards locate(frame) until the verified hero is < stop px from it (see module doc).
    tap(xy, wait) is the caller's guarded tap; interact(img) says whether the Interact HUD is up."""
    img = v.shot(f'{tag}_0')
    if v.classify(img) != 'WORLD':
        print('    walk: start frame not WORLD - no tap', flush=True)
        return 'not_world', img, None, None
    goal, me = locate(img), hero(img)
    if goal is None or me is None:
        print(f'    walk: goal {goal} hero {me} - no tap', flush=True)
        return ('no_goal' if goal is None else 'no_hero'), img, goal, me
    low, d = 0, _dist(goal, me)
    for i in range(1, max_taps + 1):
        if d < stop:
            print(f'    walk: arrived, hero {me} goal {goal} d {d:.0f}', flush=True)
            return 'arrived', img, goal, me
        pts = avoid(img)
        p = target(img, me, goal, pts)
        if p is None:
            print(f'    walk: no safe ground towards {goal} from hero {me} (d {d:.0f}) - stop', flush=True)
            return 'no_ground', img, goal, me
        was_up = interact(img)
        near_before = any(_dist(a, p) <= SELECT_R for a in pts)
        tap(p, wait)
        img = v.shot(f'{tag}_{i}')
        if v.classify(img) != 'WORLD':
            print(f'    walk: tap {i} at {p}: frame not WORLD - stop', flush=True)
            return 'not_world', img, goal, me
        goal, me2 = locate(img), hero(img, me)
        print(f'    walk: tap {i} at {p}: hero {me2} goal {goal} '
              f'd {_dist(goal, me2) if goal and me2 else -1:.0f}', flush=True)
        if goal is None or me2 is None:
            return ('no_goal' if goal is None else 'no_hero'), img, goal, me2
        me, d0, d = me2, d, _dist(goal, me2)
        if d < stop:
            continue                                # -> 'arrived' (beats 'selected', see module doc)
        if (interact(img) and not was_up) or (not near_before and any(_dist(a, p) <= SELECT_R for a in avoid(img))):
            print(f'    walk: tap {i} selected something - stop', flush=True)
            return 'selected', img, goal, me
        low = low + 1 if d0 - d < WALK_MIN_GAIN else 0
        if low >= 2:
            print(f'    walk: stuck (two taps without {WALK_MIN_GAIN} px gain)', flush=True)
            return 'stuck', img, goal, me
    status = 'arrived' if d < stop else 'max'
    print(f'    walk: {status} after {max_taps} taps, d {d:.0f}', flush=True)
    return status, img, goal, me


def _tower_icon(hu, img, tower):
    """spire_icon, else a Level Up icon right above the tower point (41556: y 48, above ICON_BAND)."""
    return hu.spire_icon(img) or next(iter(hu.level_icons(
        img, hu.near_band(img, (tower[0], tower[1] + ICON_TOWER_DY), ICON_TOWER_R))), None)


def spire_after_tower(img, tower, hu):
    """T111 hook of spire() after a tower tap gave no radial/Interact/icon: (disc, still, img) or
    (None, None, img). hu = the afk_homestead_upgrade module (passed in: no import cycle).
    (i) non-WORLD frame -> up to WALK_RESHOTS no-tap re-shots, then radial / Interact / icon on the re-shot;
    (ii) icon (also above ICON_BAND, next to the tower); (iii) walk towards the tower, re-tap it, radial /
    Interact / icon."""
    tag = None
    for i in range(WALK_RESHOTS):
        if v.classify(img) == 'WORLD':
            break
        time.sleep(RESHOT_WAIT)
        tag = f'hu_tower_s{i}'
        img = v.shot(tag)
    if v.classify(img) != 'WORLD':
        return None, None, img
    if tag:                                      # spire() read no radial / Interact on a non-WORLD hu_tower
        xy, still = _spire_pick(hu, img, tag, tower)
    else:
        xy = _tower_icon(hu, img, tower)
        still = xy and _icon_still(hu, xy)
    if xy:
        print(f'    {xy} after the tower tap (tower {tower})', flush=True)
        return xy, still, img
    status, img, goal, _ = walk_towards(
        hu.spire_tower, hu._tap, 'hu_walk', avoid=lambda im: hu.level_icons(im) + hu.upgrade_pins(im),
        interact=lambda im: hu.interact_at(im, INTERACT_HUD))
    if status != 'arrived':
        print(f'    walk to the Spire: {status}', flush=True)
        if status == 'not_world' and hu.back_plate(img):
            hu.close_dialog(img)
        return None, None, img
    print(f'    re-tapping the Spire tower at {goal}', flush=True)
    hu._tap(goal, hu.TOWER_WAIT)
    img = v.shot('hu_tower2')
    if v.classify(img) != 'WORLD':
        return None, None, img
    return (*_spire_pick(hu, img, 'hu_tower2', goal), img)


def _spire_pick(hu, img, tag, tower):
    """(disc, still) on the WORLD frame `tag`: Level Up radial, the Spire's Interact, the icon by the tower."""
    boxes = v.ocr_boxes(tag)
    xy = hu.find_radial(img, boxes)
    if xy:
        return xy, lambda im: v.classify(im) == 'WORLD' and hu.disc_at(im, xy)
    tower = hu.spire_tower(img) or tower         # the camera may recentre on the selected tower (T103d)
    xy = hu.spire_interact(img, boxes, tower)
    if xy:
        return xy, lambda im: v.classify(im) == 'WORLD' and hu.interact_at(im, xy)
    xy = _tower_icon(hu, img, tower)
    return (xy, _icon_still(hu, xy)) if xy else (None, None)


def _icon_still(hu, xy):
    return lambda im: v.classify(im) == 'WORLD' and bool(hu.level_icons(im, hu.near_band(im, xy, ICON_TOWER_R)))
