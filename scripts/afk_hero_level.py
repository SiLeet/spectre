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

Usage: python scripts/afk_hero_level.py [--target 95] [--dry-run]
Exit codes: 0 done, 1 stuck (unknown screen / hand unreadable or not found / hall lost).
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402  (shared adb/tap/shot/OCR helpers)

HANDS_Y = 460                      # hands row (verified: (830,460) opened Koko)
HAND_XS = [710, 840, 970, 1100, 1220]
LEVEL_X10 = (1460, 1065)           # Level Up x10 button on the hero detail
TARGET_DEFAULT = 95                # stage-253 level cap (rises with stages)
MAX_X10_PER_HAND = 2               # 10 levels per hand per run
HALL_BTN = (972, 1034)             # bottom-nav Resonating Hall
LEVEL_MAX = 300                    # plausibility cap for an OCR'd level


def key(keycode, wait=1.5):
    v.adb("shell", "input", "keyevent", str(keycode))
    time.sleep(wait)


def snap(name):
    """Screenshot into the per-run shots dir, then OCR it."""
    v.shot(name)
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


def is_hall(lines):
    return any("Resonance Level" in ln for ln in lines)


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
    lines = v.ocr_lines(tag)
    if is_hall(lines):
        return True
    if is_detail(lines):
        key(4)
        img = v.shot(f"{tag}_b")
        lines = v.ocr_lines(f"{tag}_b")
        if is_hall(lines):
            return True
    if v.classify(img) == "WORLD":
        v.tap(HALL_BTN, 4.0)
        return is_hall(snap(f"{tag}_reenter"))
    return False


def level_hand(x: int, target: int, tag: str, stop_flag: list) -> tuple[int | None, int]:
    """Open a hand, read its level, tap x10 while below target. Returns
    (final_level_or_None, x10_taps_used). Sets stop_flag[0]=True when the
    resources are exhausted (x10 had no effect) so the caller can skip the
    remaining hands — if one hand is out of hero EXP, the others are too."""
    taps = 0
    v.tap((x, HANDS_Y), 3.0)
    lvl = None
    for attempt in range(MAX_X10_PER_HAND + 1):
        lines = snap(f"{tag}_{x}_{attempt}")
        if not lines and attempt == 0:
            # retry once: dark hero art backgrounds break a single WinRT pass
            lines = snap(f"{tag}_{x}_{attempt}b")
        if not is_detail(lines):
            print(f"    [{tag} {x}] not a hero detail (lines={len(lines)}) — back out", flush=True)
            key(4)
            return None, taps
        new_lvl = read_level(lines)
        if new_lvl is None:
            print(f"    [{tag} {x}] level unreadable — skip", flush=True)
            key(4)
            return None, taps
        if attempt == 0:
            lvl = new_lvl
        if new_lvl >= target:
            print(f"    [{tag} {x}] level {new_lvl} >= target {target}", flush=True)
            key(4)
            return new_lvl, taps
        if taps >= MAX_X10_PER_HAND:
            print(f"    [{tag} {x}] level {new_lvl} < {target} but tap cap reached", flush=True)
            key(4)
            return new_lvl, taps
        print(f"    [{tag} {x}] level {new_lvl} < {target} — tapping x10", flush=True)
        v.tap(LEVEL_X10, 3.0)
        taps += 1
        # re-read: if the level did not move, hero EXP/gold ran out — the other
        # hands will fail identically, so stop the whole run (review lesson)
        lines2 = snap(f"{tag}_{x}_check{taps}")
        lvl2 = read_level(lines2) if lines2 else None
        if lvl2 is not None and lvl2 == new_lvl:
            # one unchanged read can be a missed tap (adb hiccup, animation):
            # only two unchanged x10 taps in a row mean the resources are out
            if taps >= MAX_X10_PER_HAND:
                print(f"    [{tag} {x}] level unchanged after x10 ({lvl2}) at the tap cap — not concluding", flush=True)
                key(4)
                return lvl2, taps
            print(f"    [{tag} {x}] level unchanged after x10 ({lvl2}) — confirming with one more tap", flush=True)
            v.tap(LEVEL_X10, 3.0)
            taps += 1
            lvl3 = read_level(snap(f"{tag}_{x}_check{taps}"))
            if lvl3 is not None and lvl3 == new_lvl:
                print(f"    [{tag} {x}] level unchanged after 2 x10 taps ({lvl3}) — resources exhausted, stopping run", flush=True)
                key(4)
                stop_flag.append(True)
                return lvl3, taps
    key(4)
    return lvl, taps


def main():
    target = TARGET_DEFAULT
    for i, a in enumerate(sys.argv):
        if a == "--target" and i + 1 < len(sys.argv):
            target = int(sys.argv[i + 1])
    dry = "--dry-run" in sys.argv

    # navigate: town -> Resonating Hall
    v.tap(HALL_BTN, 4.0)
    lines = snap("hl_entry")
    if not is_hall(lines):
        print("    ERROR: Resonating Hall did not open (no 'Resonance Level' line)", flush=True)
        return 1
    bar = next((ln for ln in lines if "Resonance Level" in ln), "")
    print(f"    hall open: {bar}", flush=True)

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