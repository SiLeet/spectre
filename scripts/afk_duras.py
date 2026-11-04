#!/usr/bin/env python3
"""Dura's Trials daily driver, v1 (T69, wave-4 D4 / B1).

Mechanics (research-verified, docs/claude-wave-3-plan.md §6a): tokens reset
DAILY (never save them); a floor's first clear is a real fight and a defeat
refunds the token; cleared floors can be swept, a sweep spends one token and
drops 2-class essence. Flow:

  world -> Battle Modes -> menu OCR for 'dura'; not seen -> short swipe +
    re-OCR (max MENU_SWIPES); never seen (menu itself read) -> soft exit 4
    (not unlocked on this server) without tapping the card; seen only after
    a swipe -> exit 1 (the fixed card spot is the unscrolled one)
  -> Dura's Trials card                                  (OCR gate: 'dura';
    the tap leaves the menu unchanged = locked/Coming Soon -> soft exit 4)
  highest unlocked floor (OCR 'Floor N'); not cleared yet (no 'Sweep') ->
    exactly 1 fight: Challenge -> Battle -> result card; defeat = refund ->
    bounded retry (MAX_FIGHTS)
  then SWEEP the highest floor until the token counter 'N/6' reads 0
  marker .spectre/duras-last.txt after a clean finish (the Daily wrapper
  scripts/afk-bot-watch.sh owns the day gate and writes the same UTC date on
  rc 0/4; this write only lets a direct run count for the day too)

Non-blind: every step re-reads the screen and stops on anything that is not
the Dura's screen (or, before the fight tap, the team prep screen); a confirm/purchase dialog is always CANCELLED (tokens are
never bought). Navigation is not verified live yet: every coordinate and OCR
word below carries a LIVE: marker for Hermes to correct (constants only).
Wired into the scheduled Daily run of scripts/afk-bot-watch.sh (T84, soft
phase, AFK_DURAS=0 switches it off); not part of afk-night.sh.

Usage: python scripts/afk_duras.py [--dry-run] [--min-idle S]
Exit codes: 0 done (tokens 0, or none left), 1 stuck / Battle Modes did not
open / menu OCR read nothing / card only below the fold / unknown screen /
sweep stopped, 4 first clear not achieved or Challenge answered by a dialog
(tokens stay), or Dura's not in the menu / Coming Soon (T87), 5 skipped (PC
in use), 7 skipped (tap lock held by another run).
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
import afk_stage_push as sp  # noqa: E402  (classify_battle for the result card)

DURAS_CARD = (960, 760)        # LIVE: Dura's Trials card in the UNSCROLLED Battle Modes menu
                               # (7th-card slot; on shots-55548/bm_1 the first Coming Soon tile)
# LIVE (T87, offline OCR of shots-428/bm_final + shots-55548/bm_1, du2_scroll0-2): the full-frame
# menu OCR yields only ['00']; a crop of the card grid reads every card name ('AFK Stage Dream
# Realm Arena', 'Legend Trial', 'Arcane', 'Labyrinth Honor Duel') plus 'X Coming Soon' and the
# locked tile's 'Unlocks in a future' as SEPARATE lines, never merged with a card name, and in no
# stable order ('Arena' after 'X Coming Soon' on du2_scroll2); the faded locked-card name
# ('Supreme League') is not read at all. So Coming Soon is told by the card tap, not by OCR.
MENU_BOX = (740, 40, 1390, 880)        # LIVE: card grid of the Battle Modes menu (l, t, r, b)
MENU_WORDS = ('afk stage', 'legend trial', 'arena')   # LIVE: proof the menu OCR worked at all
MENU_SWIPE = (960, 675, 960, 392)      # LIVE: short upward drag (AdbAutoPlayer y1200->700 scaled)
MENU_SWIPE_MS = 1500                   # LIVE: slow drag = scroll without fling
MENU_SWIPES = 4                        # LIVE: AdbAutoPlayer gives up after 4 swipes
CHALLENGE_BTN = (1500, 980)    # LIVE: 'Challenge' on the highest (uncleared) floor
FIGHT_BTN = (1280, 1010)       # LIVE: 'Battle' on the team prep screen (same spot as AFK prep)
PREP_GATE = True               # LIVE: tap FIGHT_BTN only when sp.classify_battle reads PREP
                               # (green Battle button at sp.BATTLE_BTN); False = v1 (no gate)
SWEEP_BTN = (1500, 980)        # LIVE: 'Sweep' on a cleared floor (replaces Challenge)
RESULT_CLOSE = (960, 540)      # LIVE: closes the result / sweep reward card (card centre)
DURAS_WORD = 'dura'            # LIVE: OCR word that proves the Dura's screen
SWEEP_WORD = 'sweep'           # LIVE: shown once the highest floor is cleared
TOKENS_MAX = 6                 # 'N/6' daily tokens (research: daily reset)
MAX_FIGHTS = 3                 # LIVE: first-clear attempts per run (defeat refunds)
FIGHT_POLLS = 50               # x 3 s poll for the result card
MARKER = v.REPO / '.spectre' / 'duras-last.txt'


def is_duras(lines: list[str]) -> bool:
    return any(DURAS_WORD in ln.lower() for ln in lines)


def parse_tokens(lines: list[str]) -> int | None:
    """Remaining tokens from the 'N/6' counter."""
    for ln in lines:
        m = re.search(rf'\b(\d)\s*/\s*{TOKENS_MAX}\b', ln)
        if m:
            return int(m.group(1))
    return None


def parse_floor(lines: list[str]) -> int | None:
    """Highest floor number shown ('Floor 12' / 'Floor12')."""
    floors = [int(m.group(1)) for ln in lines for m in re.finditer(r'(?i)\bfloor\s*(\d{1,3})\b', ln)]
    return max(floors) if floors else None


def is_cleared(lines: list[str]) -> bool:
    return any(SWEEP_WORD in ln.lower() for ln in lines)


def read(tag: str):
    """Screenshot + OCR; (img, lines)."""
    img = v.shot(tag)
    return img, v.ocr_lines(tag)


def cancel_if_dialog(img, what: str) -> bool:
    if v.is_confirm_dialog(img):
        v.tap(v.CONFIRM_CANCEL, 1.5)       # never confirm: tokens/fights are never bought
        print(f'    {what}: confirm/purchase dialog -> cancelled, stopping', flush=True)
        return True
    return False


def find_card() -> tuple[int | None, bool]:
    """Swipes done when the menu OCR first showed 'dura' (None = never, after
    MENU_SWIPES swipes) and whether any MENU_WORDS card name was read at all."""
    menu_read = False
    for n in range(MENU_SWIPES + 1):
        if n:
            v.swipe(*MENU_SWIPE, MENU_SWIPE_MS, 2.0)
        v.shot(f'du_menu_{n}')
        text = ' '.join(v.ocr_lines(f'du_menu_{n}') + v.ocr_region(f'du_menu_{n}', MENU_BOX)).lower()
        if DURAS_WORD in text:
            return n, True
        menu_read = menu_read or any(w in text for w in MENU_WORDS)
    return None, menu_read


def enter() -> list[str] | int:
    """The Dura's screen lines, or the exit code: 1 = Battle Modes / Dura's
    screen not reached, 4 = Dura's not available (day counts as done)."""
    if not v.open_battle_modes():
        print("    ERROR: Battle Modes did not open", flush=True)
        return 1
    swipes, menu_read = find_card()
    if swipes is None:
        if not menu_read:       # OCR failure must not mark the day (tokens are daily)
            print('    ERROR: Battle Modes menu OCR read no card name (LIVE: MENU_BOX / '
                  'MENU_WORDS)', flush=True)
            return 1
        print(f"    Dura's currently not available (not in the Battle Modes menu after "
              f"{MENU_SWIPES} swipes), skipping", flush=True)
        return 4
    if swipes:
        print(f"    ERROR: Dura's card seen only after {swipes} swipe(s) - DURAS_CARD is the "
              "unscrolled spot, not tapping blind (LIVE: card position below the fold)", flush=True)
        return 1
    v.tap(DURAS_CARD, 4.0)
    img, lines = read('du_entry')
    if not is_duras(lines):
        if v.is_battle_modes(img):      # LIVE: a locked (Coming Soon) card opens nothing
            print("    Dura's not available yet (Coming Soon), skipping", flush=True)
            return 4
        print("    ERROR: Dura's Trials screen not recognised (LIVE: card position / OCR word)",
              flush=True)
        return 1
    return lines


def first_clear(floor: int | None) -> list[str] | int:
    """One fight on the uncleared highest floor; a defeat refunds the token,
    so retry up to MAX_FIGHTS. Returns the Dura's screen lines afterwards, or
    the exit code: 4 = not cleared / dialog (tokens stay, day is done), 1 =
    stuck (no result card / unknown screen) - the Daily wrapper marks the day
    on 4, so a stuck run must not report 4 (T84)."""
    for attempt in range(1, MAX_FIGHTS + 1):
        print(f'    floor {floor}: first clear, fight {attempt}/{MAX_FIGHTS}', flush=True)
        v.tap(CHALLENGE_BTN, 3.0)
        img = v.shot(f'du_prep_{attempt}')
        if cancel_if_dialog(img, 'challenge'):
            return 4
        if PREP_GATE and sp.classify_battle(img) != 'PREP':
            # T84: the Daily run taps this unattended - never tap FIGHT_BTN blind
            print('    ERROR: team prep screen not recognised after Challenge (LIVE: CHALLENGE_BTN '
                  '/ prep probe) - not fighting', flush=True)
            return 1
        v.tap(FIGHT_BTN, 3.0)
        result = None
        for n in range(FIGHT_POLLS):
            st = sp.classify_battle(v.shot(f'du_fight_{attempt}_{n}'))
            if st in ('RESULT', 'DEFEAT'):
                result = st
                break
            if st == 'CONFIRM':
                v.tap(v.CONFIRM_CANCEL, 1.5)
            time.sleep(3)
        if result is None:
            print('    ERROR: no result card after the fight', flush=True)
            return 1
        v.tap(RESULT_CLOSE, 2.5)
        _, lines = read(f'du_after_fight_{attempt}')
        if not is_duras(lines):
            print("    ERROR: not back on the Dura's screen after the fight", flush=True)
            return 1
        if result == 'RESULT':
            print(f'    floor {floor}: cleared', flush=True)
            return lines
        print(f'    floor {floor}: defeat (token refunded)', flush=True)
    print(f'    floor {floor}: not cleared in {MAX_FIGHTS} fights — stopping (tokens stay)', flush=True)
    return 4


def sweep_all(lines: list[str]) -> bool:
    """Sweep the highest cleared floor until the counter reads 0. Each sweep
    must lower it by exactly one; anything else stops (bounded by TOKENS_MAX)."""
    tokens = parse_tokens(lines)
    if tokens is None:
        print('    ERROR: token counter not readable (LIVE: N/6 position)', flush=True)
        return False
    for n in range(1, TOKENS_MAX + 1):
        if tokens == 0:
            print('    tokens: 0 — done for today', flush=True)
            return True
        if not is_cleared(lines):
            # SWEEP_BTN shares the Challenge spot: without 'Sweep' on screen the
            # tap would start a fight instead
            print("    ERROR: no 'Sweep' on screen — not sweeping", flush=True)
            return False
        v.tap(SWEEP_BTN, 3.0)
        img = v.shot(f'du_sweep_{n}')
        if cancel_if_dialog(img, 'sweep'):
            return False
        v.tap(RESULT_CLOSE, 2.5)
        _, lines = read(f'du_after_sweep_{n}')
        left = parse_tokens(lines)
        if not is_duras(lines) or left != tokens - 1:
            print(f'    ERROR: sweep {n}: expected {tokens - 1} tokens, read {left} '
                  f"(dura screen: {is_duras(lines)})", flush=True)
            return False
        print(f'    sweep {n}: tokens {tokens} -> {left}', flush=True)
        tokens = left
    return tokens == 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Dura's Trials: first clear + sweep all tokens")
    ap.add_argument('--dry-run', action='store_true', help='enter + read floor/tokens only')
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
    lines = enter()
    if isinstance(lines, int):
        return lines
    floor, tokens, cleared = parse_floor(lines), parse_tokens(lines), is_cleared(lines)
    print(f"    dura's: highest floor {floor}, cleared={cleared}, tokens {tokens}/{TOKENS_MAX}", flush=True)
    if args.dry_run:
        return 0
    if not cleared:
        if tokens == 0:
            print('    no tokens left today', flush=True)
            return 0
        lines = first_clear(floor)
        if isinstance(lines, int):
            return lines
    if not sweep_all(lines):
        return 1
    try:
        MARKER.parent.mkdir(parents=True, exist_ok=True)
        MARKER.write_text(datetime.now(timezone.utc).strftime('%Y-%m-%d'), encoding='utf-8')
    except OSError:
        pass
    print("    done: Dura's Trials tokens used", flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
