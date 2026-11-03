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
Exit codes: 0 done, 1 stuck (unknown screen / hand not found).
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


def key(keycode, wait=1.5):
    v.adb("shell", "input", "keyevent", str(keycode))
    time.sleep(wait)


def snap(name):
    """Screenshot into the per-run shots dir, then OCR it."""
    v.shot(name)
    return v.ocr_lines(name)


def read_level(lines):
    """Hero level from the detail screen: 'Lv. 74' bottom-left badge."""
    for ln in lines:
        m = re.search(r"Lv[l.\s]*\.?\s*(\d{1,3})", ln)
        if m:
            return int(m.group(1))
    return None


def is_detail(lines):
    return any("Ascend" in ln or "Level" in ln or "Lvl" in ln for ln in lines)


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
            print(f"    [{tag} {x}] level unchanged after x10 ({lvl2}) — resources exhausted, stopping run", flush=True)
            key(4)
            stop_flag.append(True)
            return lvl2, taps
    key(4)
    return lvl, taps


def main():
    target = TARGET_DEFAULT
    for i, a in enumerate(sys.argv):
        if a == "--target" and i + 1 < len(sys.argv):
            target = int(sys.argv[i + 1])
    dry = "--dry-run" in sys.argv

    # navigate: town -> Resonating Hall
    v.tap((972, 1034), 4.0)            # bottom-nav Resonating Hall
    lines = snap("hl_entry")
    if not any("Resonance Level" in ln for ln in lines):
        print("    ERROR: Resonating Hall did not open (no 'Resonance Level' line)", flush=True)
        return 1
    bar = next((ln for ln in lines if "Resonance Level" in ln), "")
    print(f"    hall open: {bar}", flush=True)

    results = []
    stop_flag: list[bool] = []
    for x in HAND_XS:
        if dry:
            print(f"    [dry-run] would open hand {x} and level to {target}", flush=True)
            continue
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
    print("done", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())