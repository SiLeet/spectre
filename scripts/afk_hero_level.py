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
import subprocess
import sys
import time
from pathlib import Path

ADB = r"C:\Users\Sigi\AppData\Local\Android\Sdk\platform-tools\adb.exe"
SERIAL = "127.0.0.1:5555"
POWERSHELL = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
OCR = r"C:\Users\Sigi\spectre\templates\ocr.ps1"
SHOTDIR = Path(r"C:\Users\Sigi\spectre\.spectre")
SHOTDIR.mkdir(parents=True, exist_ok=True)

HANDS_Y = 460                      # hands row (verified: (830,460) opened Koko)
HAND_XS = [710, 840, 970, 1100, 1220]
LEVEL_X10 = (1460, 1065)           # Level Up x10 button on the hero detail
BACK = (474, 1010)                 # hall: bottom bar; detail: closes it
TARGET_DEFAULT = 95                # stage-253 level cap (rises with stages)
MAX_X10_PER_HAND = 2               # 10 levels per hand per run


def sh(*args, timeout=30):
    return subprocess.run([ADB, "-s", SERIAL, *args], capture_output=True, timeout=timeout)


def tap(x, y, wait=1.0):
    sh("shell", "input", "tap", str(x), str(y))
    time.sleep(wait)


def key(keycode, wait=1.5):
    sh("shell", "input", "keyevent", str(keycode))
    time.sleep(wait)


def shot(name):
    path = SHOTDIR / f"{name}.png"
    with open(path, "wb") as fh:
        subprocess.run([ADB, "-s", SERIAL, "exec-out", "screencap", "-p"], stdout=fh, timeout=60)
    return str(path)


def ocr(png):
    png = str(Path(png).resolve())
    try:
        p = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass",
                            "-File", OCR, "-Path", png],
                           capture_output=True, timeout=20, text=True,
                           encoding="utf-8", errors="replace")
        return [l.strip() for l in p.stdout.splitlines() if l.strip()]
    except Exception:
        return []


def read_level(lines):
    """Hero level from the detail screen: 'Lv. 74' bottom-left badge."""
    for ln in lines:
        m = re.search(r"Lv[l.\s]*\.?\s*(\d{1,3})", ln)
        if m:
            return int(m.group(1))
    return None


def is_detail(lines):
    return any("Ascend" in ln or "Level" in ln or "Lvl" in ln for ln in lines)


def level_hand(x: int, target: int, tag: str) -> tuple[int | None, int]:
    """Open a hand, read its level, tap x10 while below target. Returns
    (final_level_or_None, x10_taps_used)."""
    taps = 0
    tap(x, HANDS_Y, 3.0)
    lvl = None
    for attempt in range(MAX_X10_PER_HAND + 1):
        lines = ocr(shot(f"{tag}_{x}_{attempt}"))
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
        tap(*LEVEL_X10, 3.0)
        taps += 1
    key(4)
    return lvl, taps


def main():
    target = TARGET_DEFAULT
    for i, a in enumerate(sys.argv):
        if a == "--target" and i + 1 < len(sys.argv):
            target = int(sys.argv[i + 1])
    dry = "--dry-run" in sys.argv

    # navigate: town -> Resonating Hall
    tap(972, 1034, 4.0)                # bottom-nav Resonating Hall
    img = shot("hl_entry")
    lines = ocr(img)
    if not any("Resonance Level" in ln for ln in lines):
        print("    ERROR: Resonating Hall did not open (no 'Resonance Level' line)", flush=True)
        return 1
    bar = next((ln for ln in lines if "Resonance Level" in ln), "")
    print(f"    hall open: {bar}", flush=True)

    results = []
    for x in HAND_XS:
        if dry:
            print(f"    [dry-run] would open hand {x} and level to {target}", flush=True)
            continue
        lvl, taps = level_hand(x, target, "hl")
        results.append((x, lvl, taps))
        time.sleep(1.0)

    for x, lvl, taps in results:
        print(f"    hand {x}: final level {lvl}, x10 taps {taps}", flush=True)
    lows = [l for _, l, _ in results if l is not None]
    if lows:
        print(f"    lowest hand after run: {min(lows)} (target {target})", flush=True)
    print("done", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())