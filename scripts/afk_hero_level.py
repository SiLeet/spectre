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
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402  (shared adb/tap/shot/OCR helpers)
import _bot_lock  # noqa: E402  (tap lock: one bot tapping at a time)

HANDS_Y = 460                      # hands row (verified: (830,460) opened Koko)
HAND_XS = [710, 840, 970, 1100, 1220]
LEVEL_X10 = (1100, 985)            # same button; x10 assumed via badge (LIVE)
TARGET_DEFAULT = 95                # stage-253 level cap (rises with stages)
MAX_X10_PER_HAND = 2               # 10 levels per hand per run
HALL_BTN = (990, 1010)             # bottom-nav Resonating Hall (verified live 2026-11-03)
LEVEL_NUM_BOX = (1240, 810, 1560, 930)   # big 'Level NN' bottom-right (LIVE 2026-11-03)
LEVEL_MAX = 300                    # plausibility cap for an OCR'd level


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


def slot_level(name):
    """The hero's slot level (big 'Level NN' bottom-right) from a saved shot.

    The full-frame OCR merges the big number with the layout; a region crop
    isolates it (live-verified 2026-11-03: read 80 -> 81 after one charge)."""
    p = v.TMP / f"{name}.png"
    try:
        c = Image.open(p).crop(LEVEL_NUM_BOX)
        cp = v.TMP / f"{name}_r.png"
        c.save(cp)
        lines = v.ocr_png(cp)
    except (OSError, ValueError):
        return None
    for ln in lines:
        m = re.fullmatch(r"(\d{1,3})", ln.strip())
        if m and 1 <= int(m.group(1)) <= LEVEL_MAX:
            return int(m.group(1))
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
        lvl2 = read_level(lines2) if lines2 else None
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
            lvl3 = read_level(lines3)
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


def resources_ok(lines):
    """Gold/EXP gate from the detail screen's 'have/need' cost lines (real OCR:
    '5104K/2780', '02985/1100'). False = something is short, True = all shown
    costs covered, None = no cost line read (LIVE: layout). Small pairs without
    K/M ('3/4' affinity, '0/1' ascend) are ignored."""
    seen = False
    for ln in lines:
        for m in _RES_RE.finditer(ln):
            have, need = _amount(m.group(1), m.group(2)), _amount(m.group(3), m.group(4))
            if not (m.group(2) or m.group(4)) and need < 100:
                continue
            seen = True
            if have < need:
                return False
    return True if seen else None


def scan_hands():
    """{hand_x: level} for every hand whose detail reads a level (hall re-verified between)."""
    levels = {}
    for i, x in enumerate(HAND_XS):
        if i > 0 and not in_hall(f"hl_scan_hall_{x}"):
            break
        v.tap((x, HANDS_Y), 3.0)
        lines = snap(f"hl_scan_{x}")
        lvl = (slot_level(f"hl_scan_{x}") or read_level(lines)) if is_detail(lines) else None
        if lvl is not None:
            levels[x] = lvl
        print(f"    scan hand {x}: level {lvl}", flush=True)
        key(4)
    return levels


def daily_charge() -> int:
    """One x1 level charge on the lowest slot-level hand. Exit: 0 charged
    (read-back +1), 4 skipped for today (blocked / resources / no effect),
    1 failed (screen not as expected). Never spends diamonds. Up to 3 lowest
    hands are tried; blocked ones ('within 10 levels') are skipped."""
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
        v.tap((x, HANDS_Y), 3.0)
        lines = snap(f"hl_daily_pre{attempt}")
        if "within 10" in " ".join(lines):
            print(f"    SKIP hand {x}: blocked (hands must be within 10 levels)", flush=True)
            key(4)
            continue
        before = slot_level(f"hl_daily_pre{attempt}") or (read_level(lines) if is_detail(lines) else None)
        if before is None:
            print(f"    SKIP hand {x}: level not readable", flush=True)
            key(4)
            continue
        res = resources_ok(lines)
        if res is False:
            print(f"    SKIP: resources short for hand {x} (level {before}) — no charge today", flush=True)
            key(4)
            return 4
        if res is None:
            print("    LIVE: cost lines not read — charging, read-back decides", flush=True)
        v.tap(LEVEL_X1, 2.5)                  # 1st tap: opens the upgrade preview panel
        v.tap(LEVEL_X1, 3.0)                  # 2nd tap: confirms inside the panel (same spot)
        if v.is_confirm_dialog(v.shot(f"hl_daily_post{attempt}")):
            v.tap(v.CONFIRM_CANCEL, 1.5)      # a 'use diamonds?' prompt: never confirm
            print("    SKIP: confirm/purchase dialog after the charge — cancelled", flush=True)
            key(4)
            return 4
        after = slot_level(f"hl_daily_post{attempt}") or read_level(v.ocr_lines(f"hl_daily_post{attempt}"))
        key(4)
        if after is not None and after == before + 1:
            print(f"    charged: hand {x} level {before} -> {after}", flush=True)
            return 0
        if after == before:
            print(f"    SKIP: charge had no effect on hand {x} (level {before})", flush=True)
            return 4
        print(f"    WARN: unexpected read-back {before} -> {after} (LIVE: x1 vs x10 mode?)", flush=True)
        return 0 if after is not None and after > before else 1
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

    # navigate: town -> Resonating Hall
    v.tap(HALL_BTN, 4.0)
    lines = snap("hl_entry")
    if not is_hall(lines):
        # one guarded retry (missed tap / slow open): in_hall re-taps only
        # from the town view, never blind
        if not in_hall("hl_entry_retry"):
            print("    ERROR: Resonating Hall did not open (no 'Resonance Level' line)", flush=True)
            return 1
        lines = v.ocr_lines("hl_entry_retry_reenter") or v.ocr_lines("hl_entry_retry")
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