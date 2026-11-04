#!/usr/bin/env python3
"""Hero leveling driver (T33): level the lowest Hands of Resonance to the cap.

Resonance rules (verified in-game + guides): the Resonance Level equals the
LOWEST of the 5 Hands; no Hand may exceed RL by more than 10. Levels bought in
any Hand other than the lowest buy nothing account-wide — so this script levels
the lowest Hands first, repeating until all five sit at the level cap.

Costs (pre-240 RL): gold + hero EXP + essence. Gold is the bind at stage 254.
Policy (Sergej-approved defaults): gold/EXP/essence only — never diamonds;
cap 10 levels per hand per run; abort when the x10 button is disabled or when
a level-up fails to register twice.

Daily mode (T67, rule T33 approved): --level = exactly ONE x1 level charge per
run on the lowest hand (scan of all five; fallback: last known hand), gold/EXP
only — OCR gate before, read-back (+1) after; afk-bot-watch.sh runs it once a day.

Usage: python scripts/afk_hero_level.py [--target 95] [--dry-run] [--level]
Exit codes: 0 done / charged, 1 stuck (unknown screen / hand unreadable or not
found / hall lost), 4 (--level) skipped today: resources short, no effect or a
purchase dialog (cancelled), 7 tap lock held (another bot run is tapping).
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from collections import Counter
from pathlib import Path

from PIL import Image, ImageOps


sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402  (shared adb/tap/shot/OCR helpers)
import _bot_lock  # noqa: E402  (tap lock: one bot tapping at a time)

HANDS_Y = 460                      # hands row (verified: (830,460) opened Koko)
# LIVE: measured card centres (vision measurement 2026-11-03); the old
# [710, 840, 970, 1100, 1220] was up to ~20 px off. HANDS_Y stayed valid.
HAND_XS = [730, 850, 970, 1090, 1210]
# T80b (live 2026-11-04: first read after the hand tap None 4/5x, once the
# PREVIOUS hand's level): poll until the detail is up instead of a fixed 3.0 s
DETAIL_POLLS = 16                  # LIVE: 16 x 0.5 s ~ 8 s bound
DETAIL_POLL_WAIT = 0.5
SLOT_REREADS = 2                   # fresh shots when the level read is None / stale
LEVEL_X10 = (1100, 985)            # same button; x10 assumed via badge (LIVE)
TARGET_DEFAULT = 95                # stage-253 level cap (rises with stages)
MAX_X10_PER_HAND = 2               # 10 levels per hand per run
# Bottom-nav Resonating Hall. T101: the helmet icon spans ~x 980-1047 / y 1000-1050
# (shots-66556/norm_3, layout A; helmet L 222 here); (990,1010) sat on its crest edge,
# the operator's manual tap (1030,1010) on the red badge - both opened the hall live.
# Layout B keeps the layout-A hit boxes (T98, BATTLE_MODES_BTN). LIVE: this point untapped.
HALL_BTN = (1005, 1025)
HALL_TRIES = 3                     # T101: hall taps per entry (each gated on a WORLD frame)
# Big 'Level NNN' bottom-right = the HAND level (matches the hall row on every frame:
# shots-17092 110/110/101/100/100, trash/shots-69252). T101: the 'Lvl. NN' badge is NOT
# the hand level (Shemira badge 85 at hand level 101/103/105, Cecia 82 at 100).
LEVEL_NUM_BOX = (1240, 810, 1560, 930)
LEVEL_SCALE = 2                    # T101: 2x upscale read 101/103/100/110 on every settled frame
# T101: gold / hero-EXP / essence cost line under 'Level Up' ('8572K/9390  5256K/91K',
# shots-17092/hl_daily_pre0_w2; 3 items on shots-17092/hl_scan_1090). Too small for one
# OCR pass: 5 upscaled variants are stacked into ONE image; a have/need pair counts only
# when >= 2 variants read it identically (measured: 8 of 8 settled frames read gold + EXP).
# T101b: x from 840 - the milestone 'Upgrade' preview draws the same line ~100 px further left
# (shots-43184/hl_daily_post0: the gold pair 8534K/9360 was clipped at x 900 -> 'third pair gone'
# was the crop, not a spend). Same reads at 840 on every detail frame (shots-17092/29628/43184).
COST_BOX = (840, 1016, 1320, 1044)
# T101b: milestone level-up preview ('Upgrade', 'Level 100 >> Level 101', shots-43184/hl_daily_post0,
# _rr1, _rr2 after the charge tap at hand level 100). OCR of this box: '100? 101' (x1 and x2).
# Its own green Level Up bar spans x~540-1480 / y~970-1040, so LEVEL_X1 confirms inside it.
PREVIEW_BOX = (780, 670, 1140, 790)
COST_SCALE = 3
COST_THRESHOLDS = (175, 190, 205)  # dark-text binarisations; + plain and inverted grey
LEVEL_MAX = 300                    # plausibility cap for an OCR'd level
# T82: 'Resonance Level: NN' header bar of the Resonating Hall (text ~(862..1110, 345..370)),
# measured on .spectre/shots-69252/hl_entry.png + hl_daily_hall0/1 + hl_scan_hall_850/970/1090/1210
# (region hit on all 7); region miss on all 14 negatives (detail hl_scan_*/hl_daily_pre*/post1,
# quests panel shots-47096/hl_entry*) — same verdicts as the full-frame OCR.
# LIVE: not yet run on the device; a miss only costs the full-OCR fallback (hall_lines).
HALL_BOX = (740, 315, 1180, 405)


def key(keycode, wait=1.5):
    v.adb("shell", "input", "keyevent", str(keycode))
    time.sleep(wait)


def snap(name):
    """Screenshot into the per-run shots dir, then OCR it."""
    v.shot(name)
    return v.ocr_lines(name)


def tap_x10(name):
    """Level Up x10, then OCR the result. None when a confirm/purchase dialog
    came up instead (cancelled: the policy never spends diamonds)."""
    v.tap(LEVEL_X10, 3.0)
    if v.is_confirm_dialog(v.shot(name)):
        v.tap(v.CONFIRM_CANCEL, 1.5)
        return None
    return v.ocr_lines(name)


def read_level(lines):
    """Hero level from the detail badge: 'Lvl. 74' and the OCR variants
    'LvL99', 'LV.74', 'Lv. 74' (case-insensitive). A glued run such as
    'Lv.74986' (badge + power) keeps the leading digits that form a plausible
    level instead of truncating to 749; implausible values are skipped."""
    for ln in lines:
        m = re.search(r"(?i)\blv[l.\s]*\.?\s*(\d{1,6})", ln)
        if not m:
            continue
        digits = m.group(1)
        n = int(digits)
        if n > LEVEL_MAX:
            n = int(digits[:3]) if int(digits[:3]) <= LEVEL_MAX else int(digits[:2])
        if 1 <= n <= LEVEL_MAX:
            return n
    return None


def _crop_ocr(name: str, suffix: str, make) -> list[str]:
    """OCR of make(crop source) saved as shot `{name}_{suffix}` (T101). The variant
    file sits next to the shot, so v.ocr_lines reads it (and tests can fake it by name)."""
    try:
        with Image.open(v.TMP / f"{name}.png") as im:
            make(im.convert("RGB")).save(v.TMP / f"{name}_{suffix}.png")
    except (OSError, ValueError):
        pass                    # no shot: ocr_lines returns [] for the missing variant
    return v.ocr_lines(f"{name}_{suffix}")


def slot_level(name):
    """Hand level = the big 'Level NNN' bottom-right of the detail, from saved shot `name`.

    T101: this is the level the hall row shows and a charge moves (shots-17092:
    101 -> 103, gold 8572K -> 8553K = two levels). The old note 'this box shows the
    resonance cap on a disabled button' was the true level 100 (trash/shots-69252)."""
    def make(im):
        c = im.crop(LEVEL_NUM_BOX)
        return c.resize((c.width * LEVEL_SCALE, c.height * LEVEL_SCALE), Image.LANCZOS)
    for ln in _crop_ocr(name, "lv", make):
        m = re.fullmatch(r"(\d{1,3})", ln.strip())
        if m and 1 <= int(m.group(1)) <= LEVEL_MAX:
            return int(m.group(1))
    return None


def preview_levels(name):
    """(from, to) of the level-up preview in saved shot `name`, None when it is not open:
    two numbers with to == from + 1 in PREVIEW_BOX (hero art there never reads like that)."""
    for ln in _crop_ocr(name, "pv", lambda im: im.crop(PREVIEW_BOX)):
        m = re.search(r"(\d{2,3})\D{1,4}(\d{2,3})", ln)
        if m and int(m.group(2)) == int(m.group(1)) + 1 <= LEVEL_MAX:
            return int(m.group(1)), int(m.group(2))
    return None


def shown_level(name, lines):
    """Hand level on shot `name`: the preview's from-level while it is open, else the detail box."""
    pv = preview_levels(name)
    if pv:
        return pv[0]
    return slot_level(name) if is_detail(lines) else None


def is_hall(lines):
    return any("Resonance Level" in ln for ln in lines)


def hall_lines(name):
    """OCR of saved shot `name` for the hall gate (T82): the HALL_BOX region
    first; no 'Resonance Level' there -> the full-frame OCR as before, so a
    negative (and the is_detail check on it) behaves exactly as without the
    region. A hit returns only the region lines."""
    lines = v.ocr_region(name, HALL_BOX)
    return lines if is_hall(lines) else v.ocr_lines(name)


def is_detail(lines):
    """Hero detail: level badge or the detail-only texts (real OCR: 'Affinity
    Not Pinned', 'Hands of Resonance must be within 10 levels ...'). The hall
    ('Resonance Level: 80') used to pass via the bare 'Level' match."""
    if is_hall(lines):
        return False
    return read_level(lines) is not None or any(
        "Affini" in ln or "within 10 level" in ln for ln in lines)


def in_hall(tag):
    """Re-verify the Resonating Hall before the next hand: key(4) out of a
    detail can leave the hall entirely. Detail still open -> one more back;
    town (WORLD) -> re-enter via the bottom nav; anything else -> False."""
    img = v.shot(tag)
    lines = hall_lines(tag)
    if is_hall(lines):
        return True
    if is_detail(lines):
        key(4)
        img = v.shot(f"{tag}_b")
        lines = hall_lines(f"{tag}_b")
        if is_hall(lines):
            return True
    if v.classify(img) == "WORLD":
        v.tap(HALL_BTN, 4.0)
        v.shot(f"{tag}_reenter")
        return is_hall(hall_lines(f"{tag}_reenter"))
    return False


def enter_hall() -> list | None:
    """Town -> Resonating Hall, every tap gated on a frame (T101). A direct run met the
    homestead upgrade panel ('Radiant Spire Lvl 5 > 6', shots-62772/80500: classify
    UNKNOWN), where HALL_BTN lies on its 'Complete Now' (diamonds) button: a non-world
    screen gets keyevents to the world first (v.reach_world, bounded), never a hall tap.
    Up to HALL_TRIES verified taps; a tap that left the world unchanged is retried via
    the T97b tap chain. Returns the hall OCR lines, None when it never opened."""
    name = "hl_start"
    img = v.shot(name)
    stale_world = False
    for i in range(HALL_TRIES + 1):
        lines = hall_lines(name)
        if is_hall(lines) or i == HALL_TRIES:
            break
        if v.classify(img) != "WORLD" and not v.reach_world():
            return None
        mode = v.tap_retry(HALL_BTN, wait=4.0) if stale_world else v.tap(HALL_BTN, 4.0)
        name = "hl_entry" if i == 0 else f"hl_entry{i}"
        img = v.shot(name)
        dialog = v.is_confirm_dialog(img)
        if dialog:                              # a 'spend diamonds?' prompt: never confirm
            v.tap(v.CONFIRM_CANCEL, 1.5)
            name = f"{name}_c"
            img = v.shot(name)
        if stale_world:                         # a dialog means the retried tap landed
            v.tap_result(mode, dialog or v.classify(img) != "WORLD")
        stale_world = v.classify(img) == "WORLD"
    return lines if is_hall(lines) else None


def purchase_stop(tag, x, lvl, taps, stop_flag):
    print(f"    [{tag} {x}] purchase/confirm dialog after x10 — cancelled, stopping run", flush=True)
    key(4)
    stop_flag.append(True)
    return lvl, taps


def level_hand(x: int, target: int, tag: str, stop_flag: list) -> tuple[int | None, int]:
    """Open a hand, read its level, tap x10 while below target. Returns
    (final_level_or_None, x10_taps_used). Sets stop_flag[0]=True when the
    resources are exhausted (x10 had no effect) so the caller can skip the
    remaining hands — if one hand is out of hero EXP, the others are too."""
    taps = 0
    v.tap((x, HANDS_Y), 3.0)
    lvl = None
    for attempt in range(MAX_X10_PER_HAND + 1):
        name = f"{tag}_{x}_{attempt}"
        lines = snap(name)
        if not lines and attempt == 0:
            # retry once: dark hero art backgrounds break a single WinRT pass
            name += "b"
            lines = snap(name)
        if not is_detail(lines):
            print(f"    [{tag} {x}] not a hero detail (lines={len(lines)}) — back out", flush=True)
            key(4)
            return None, taps
        new_lvl = slot_level(name)         # T101: big 'Level NNN', not the badge
        if new_lvl is None:
            print(f"    [{tag} {x}] level unreadable — skip", flush=True)
            key(4)
            return None, taps
        lvl = new_lvl                  # last level actually read (review F13)
        if new_lvl >= target:
            print(f"    [{tag} {x}] level {new_lvl} >= target {target}", flush=True)
            key(4)
            return new_lvl, taps
        if taps >= MAX_X10_PER_HAND:
            print(f"    [{tag} {x}] level {new_lvl} < {target} but tap cap reached", flush=True)
            key(4)
            return new_lvl, taps
        print(f"    [{tag} {x}] level {new_lvl} < {target} — tapping x10", flush=True)
        taps += 1
        # re-read: if the level did not move, hero EXP/gold ran out — the other
        # hands will fail identically, so stop the whole run (review lesson)
        lines2 = tap_x10(f"{tag}_{x}_check{taps}")
        if lines2 is None:
            return purchase_stop(tag, x, lvl, taps, stop_flag)
        lvl2 = slot_level(f"{tag}_{x}_check{taps}")
        if lvl2 is not None:
            lvl = lvl2
        if lvl2 is not None and lvl2 == new_lvl:
            # one unchanged read can be a missed tap (adb hiccup, animation):
            # only two unchanged x10 taps in a row mean the resources are out
            if taps >= MAX_X10_PER_HAND:
                print(f"    [{tag} {x}] level unchanged after x10 ({lvl2}) at the tap cap — not concluding", flush=True)
                key(4)
                return lvl2, taps
            print(f"    [{tag} {x}] level unchanged after x10 ({lvl2}) — confirming with one more tap", flush=True)
            taps += 1
            lines3 = tap_x10(f"{tag}_{x}_check{taps}")
            if lines3 is None:
                return purchase_stop(tag, x, lvl, taps, stop_flag)
            lvl3 = slot_level(f"{tag}_{x}_check{taps}")
            if lvl3 is not None and lvl3 == new_lvl:
                print(f"    [{tag} {x}] level unchanged after 2 x10 taps ({lvl3}) — resources exhausted, stopping run", flush=True)
                key(4)
                stop_flag.append(True)
                return lvl3, taps
    key(4)
    return lvl, taps


# --- T67: daily leveling - exactly ONE level charge per day (rule T33, approved) ---
LEVEL_X1 = (1100, 985)             # 'Level Up' button center (verified live 2026-11-03; x1 badge active)
LAST_HAND = v.REPO / ".spectre" / "level-last-hand.txt"   # last scanned lowest hand (fallback)
_RES_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*([KkMm]?)\s*/\s*(\d+(?:[.,]\d+)?)\s*([KkMm]?)")


def _amount(num: str, suffix: str) -> float:
    return float(num.replace(",", ".")) * {"k": 1e3, "m": 1e6}.get(suffix.lower(), 1)


def _pairs(line: str) -> set[tuple[float, float]]:
    """(have, need) pairs of one OCR line, each number with its OWN suffix. T101:
    '8572K/9390' is 8.57M gold for a 9,390 cost (shots-17092: 2 levels spent 19K);
    the old 'need inherits the K' read it as 9.39M -> the false 'resources short'
    of 11-04 18:22Z. Small pairs without K/M ('3/4' affinity, '0/1' ascend) skip."""
    out = set()
    for m in _RES_RE.finditer(line):
        have, need = _amount(m.group(1), m.group(2)), _amount(m.group(3), m.group(4))
        if (m.group(2) or m.group(4)) or need >= 100:
            out.add((have, need))
    return out


def costs_ok(pairs) -> bool | None:
    """False = a shown cost is not covered, True = all covered, None = no pair read."""
    if not pairs:
        return None
    return all(have >= need for have, need in pairs)


def resources_ok(lines):
    """Gold/EXP gate over plain OCR lines (any pair parsed counts)."""
    return costs_ok(set().union(*map(_pairs, lines)) if lines else set())


def cost_pairs(name: str) -> frozenset:
    """T101: the cost line of saved detail shot `name` as agreed (have, need) pairs:
    COST_BOX upscaled in 5 variants stacked into one image (one OCR call); a pair
    counts when >= 2 variant lines read it. Empty = unreadable."""
    def make(im):
        c = im.crop(COST_BOX)
        g = ImageOps.grayscale(c).resize((c.width * COST_SCALE, c.height * COST_SCALE),
                                         Image.LANCZOS)
        variants = [g, ImageOps.invert(g)] + [g.point(lambda p, t=t: 0 if p > t else 255)
                                              for t in COST_THRESHOLDS]
        gap = 40                                   # white rows keep the variants on own lines
        sheet = Image.new("L", (g.width + gap, len(variants) * (g.height + gap)), 255)
        for i, var in enumerate(variants):
            sheet.paste(var, (gap // 2, gap // 2 + i * (g.height + gap)))
        return sheet
    votes = Counter(pair for ln in _crop_ocr(name, "cost", make) for pair in _pairs(ln))
    return frozenset(pair for pair, n in votes.items() if n >= 2)


def no_effect_verdict(pre: frozenset, post: frozenset) -> tuple[int, str]:
    """T101: why a charge left the level unchanged, from the cost line before/after.
    (a) post costs not covered -> resources short (rc 4, done for today); (b) costs
    covered before AND the line identical after -> nothing was spent, the tap missed
    (rc 1: no day marker, the next cycle retries); else undetermined (rc 4)."""
    if costs_ok(post) is False:
        return 4, f"resources short (cost line after: {sorted(post)})"
    if costs_ok(pre) and post == pre:
        return 1, f"tap missed — costs covered and nothing spent ({sorted(pre)})"
    return 4, f"undetermined (cost line before {sorted(pre)} / after {sorted(post)})"


def scan_hands():
    """{hand_x: level} for every hand whose detail reads a level (hall re-verified between).
    T101b: poll until the detail is up (open_detail) + up to SLOT_REREADS settled reads -
    live shots-43184 the fixed 3 s / +1.5 s shots caught the hall or a half-drawn detail
    (hl_scan_1210 hall, _1210b no level yet). Blocked hands ('within 10 levels') draw the
    level lower (shots-43184 730b/850b) and cannot be charged: logged as blocked, not read."""
    levels = {}
    for i, x in enumerate(HAND_XS):
        if i > 0 and not in_hall(f"hl_scan_hall_{x}"):
            break
        name, lines = open_detail(x, f"hl_scan_{x}")
        if "within 10" in " ".join(lines):
            print(f"    scan hand {x}: blocked (within 10 levels)", flush=True)
            key(4)
            continue
        lvl = slot_level(name) if is_detail(lines) else None
        if is_detail(lines):
            lvl, _ = reread_level(name, lvl)
        if lvl is not None:
            levels[x] = lvl
        print(f"    scan hand {x}: level {lvl}", flush=True)
        key(4)
    return levels


def open_detail(x: int, name: str) -> tuple[str, list]:
    """Tap hand x, then poll (bounded) until its detail is up. (shot name, OCR lines)."""
    v.tap((x, HANDS_Y), DETAIL_POLL_WAIT)
    shot = name
    for i in range(DETAIL_POLLS):
        if i:
            time.sleep(DETAIL_POLL_WAIT)
            shot = f"{name}_w{i}"
        lines = snap(shot)
        if is_detail(lines):
            break
    return shot, lines


def reread_level(name: str, lvl: int | None, expect: int | None = None) -> tuple[int | None, str]:
    """`lvl` (first read of shot `name`); None or != expect -> up to SLOT_REREADS fresh reads.
    Returns (level, last shot read): the cost line is read from that same settled shot."""
    shot = name
    for i in range(1, SLOT_REREADS + 1):
        if lvl is not None and expect in (None, lvl):
            break
        time.sleep(DETAIL_POLL_WAIT)
        shot = f"{name}_rr{i}"
        lines = snap(shot)
        lvl = shown_level(shot, lines)
    return lvl, shot


def close_detail(name: str) -> None:
    """Back out of the detail after the charge; a preview still open on shot `name` needs
    one more back first (preview -> detail -> hall). LIVE: preview after the confirm unseen."""
    if preview_levels(name):
        key(4)
    key(4)


def daily_charge() -> int:
    """One x1 level charge on the lowest hand (big 'Level NNN'). Exit: 0 charged
    (read-back +1), 4 skipped for today (blocked / resources / no effect),
    1 failed (screen not as expected, or the charge tap missed). Never spends
    diamonds. Up to 3 lowest hands are tried; blocked ones ('within 10 levels')
    are skipped."""
    levels = scan_hands()
    ordered = sorted(levels, key=levels.get) if levels else []
    if not ordered:
        try:
            x = int(LAST_HAND.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            x = HAND_XS[0]
        print(f"    LIVE: hand scan read no level — using last known hand {x}", flush=True)
        ordered = [x]
    else:
        print(f"    lowest hands: {[(x, levels[x]) for x in ordered[:3]]}", flush=True)
    for attempt, x in enumerate(ordered[:3]):
        if not in_hall(f"hl_daily_hall{attempt}"):
            print("    ERROR: lost the Resonating Hall before the charge", flush=True)
            return 1
        try:
            LAST_HAND.parent.mkdir(parents=True, exist_ok=True)
            LAST_HAND.write_text(str(x), encoding="utf-8")
        except OSError:
            pass
        pre, lines = open_detail(x, f"hl_daily_pre{attempt}")
        if "within 10" in " ".join(lines):
            print(f"    SKIP hand {x}: blocked (hands must be within 10 levels)", flush=True)
            key(4)
            continue
        before = slot_level(pre) if is_detail(lines) else None
        if is_detail(lines):                  # != scanned level: stale previous detail
            before, pre = reread_level(pre, before, levels.get(x))
        if before is None:
            print(f"    SKIP hand {x}: level not readable", flush=True)
            key(4)
            continue
        pre_cost = cost_pairs(pre)
        res = costs_ok(pre_cost)
        if res is False:
            print(f"    SKIP: resources short for hand {x} (level {before}, costs {sorted(pre_cost)})"
                  " — no charge today", flush=True)
            key(4)
            return 4
        if res is None:
            print("    LIVE: cost line not read — charging, read-back decides", flush=True)
        # T101: ONE tap. The T83 pair (preview + confirm) levelled twice on 11-04:
        # shots-17092 101 -> 103 and shots-48104 103 -> 105, gold 8572K -> 8553K = 9390 + 9450.
        post = f"hl_daily_post{attempt}"
        v.tap(LEVEL_X1, 3.0)
        if v.is_confirm_dialog(v.shot(post)):
            v.tap(v.CONFIRM_CANCEL, 1.5)      # a 'use diamonds?' prompt: never confirm
            print("    SKIP: confirm/purchase dialog after the charge — cancelled", flush=True)
            key(4)
            return 4
        pv = preview_levels(post)
        if pv:
            # T101b: at a milestone (live 100 -> 101, shots-43184) the tap opens the 'Upgrade'
            # preview; its own Level Up bar takes the SAME single charge (T83's second tap).
            # At 101/103 the tap levels directly (T101: two taps were two levels).
            if pv[0] != before:
                print(f"    ERROR: level-up preview {pv[0]} -> {pv[1]} on hand level {before}", flush=True)
                close_detail(post)
                return 1
            print(f"    level-up preview {pv[0]} -> {pv[1]} — confirming inside it", flush=True)
            v.tap(LEVEL_X1, 3.0)
            post = f"{post}_ok"
            if v.is_confirm_dialog(v.shot(post)):
                v.tap(v.CONFIRM_CANCEL, 1.5)
                print("    SKIP: confirm/purchase dialog in the preview — cancelled", flush=True)
                close_detail(post)
                return 4
        # expect +1: a lagging detail (old level, old costs) gets fresh shots before any
        # 'tap missed' rc 1, which would let the next cycle charge again
        after, post = reread_level(post, shown_level(post, v.ocr_lines(post)), before + 1)
        if after is not None and after == before + 1:
            close_detail(post)
            print(f"    charged: hand {x} level {before} -> {after}", flush=True)
            return 0
        if after is None or after == before:
            rc, why = no_effect_verdict(pre_cost, cost_pairs(post))
            close_detail(post)
            print(f"    SKIP: charge had no effect on hand {x} (level {before} -> {after}): {why};"
                  f" evidence {v.TMP / (post + '.png')}", flush=True)
            return rc
        close_detail(post)
        print(f"    WARN: unexpected read-back {before} -> {after} (LIVE: x1 vs x10 mode?)", flush=True)
        return 0 if after > before else 4     # lower = misread after a real tap: never retry
    print("    SKIP: no chargeable hand today", flush=True)
    return 4


def main():
    ap = argparse.ArgumentParser(description="Level the lowest Hands of Resonance.")
    ap.add_argument("--target", type=int, default=TARGET_DEFAULT,
                    help=f"level to reach per hand (default {TARGET_DEFAULT})")
    ap.add_argument("--dry-run", action="store_true",
                    help="open the hall only; no hand / x10 taps")
    ap.add_argument("--level", action="store_true",
                    help="daily mode (T67): exactly one x1 level charge on the lowest hand")
    args = ap.parse_args()
    target, dry = args.target, args.dry_run

    if not _bot_lock.acquire():
        print(f'    SKIP: tap lock held ({_bot_lock.describe()}) — '
              'another bot run is tapping (exit 7)', flush=True)
        return 7
    _bot_lock.release_at_exit()

    lines = enter_hall()
    if lines is None:
        print("    ERROR: Resonating Hall did not open (no 'Resonance Level' line)", flush=True)
        return 1
    bar = next((ln for ln in lines if "Resonance Level" in ln), "")
    print(f"    hall open: {bar}", flush=True)
    if args.level and not dry:
        return daily_charge()

    results = []
    stop_flag: list[bool] = []
    failed = False
    for i, x in enumerate(HAND_XS):
        if dry:
            print(f"    [dry-run] would open hand {x} and level to {target}", flush=True)
            continue
        if i > 0 and not in_hall(f"hl_hall_{x}"):
            print(f"    ERROR: lost the Resonating Hall before hand {x} — stopping", flush=True)
            failed = True
            break
        lvl, taps = level_hand(x, target, "hl", stop_flag)
        results.append((x, lvl, taps))
        time.sleep(1.0)
        if stop_flag:
            print("    stopping run: resources exhausted (hero EXP/gold out)", flush=True)
            break

    for x, lvl, taps in results:
        print(f"    hand {x}: final level {lvl}, x10 taps {taps}", flush=True)
    lows = [l for _, l, _ in results if l is not None]
    if lows:
        print(f"    lowest hand after run: {min(lows)} (target {target})", flush=True)
    if stop_flag:
        print("    NOTE: run stopped early — hero leveling resources exhausted "
              "(top up hero EXP/gold, then rerun)", flush=True)
    if failed or any(lvl is None for _, lvl, _ in results):
        print("done — with failures (hand unreadable / not found / hall lost)", flush=True)
        return 1
    print("done", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())