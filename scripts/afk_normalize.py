#!/usr/bin/env python3
"""Normalize the game screen back to a known state (world / AFK panel).

Used by the scheduler wrapper between phases: a phase that ends on an unknown
screen (live case: the gift driver's camera pan accidentally tapped into the
Arcane Labyrinth card) otherwise poisons every follow-up phase. Non-blind:
classify() per step, capped BACK taps, login popups get claimed when OCR'd.

Zombie popup (T66, night log 2026-11-03: "normalize 0..4: POPUP", dream then
"could not reach the world view"): when every read of the normal pass is
POPUP, a bounded escape ladder runs — login resolver -> BACK -> empty ground
(300,250) -> BACK x2 — classify after every step, a purchase/confirm dialog
is always cancelled, the ground tap is skipped when OCR shows purchase words.
It ends with one clear marker line: 'ESCAPE: recovered ...' or 'ESCAPE: gave up ...'.

Exit: 0 world/panel reached, 1 still unknown after the cap.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402

POPUP_STREAK = 5        # LIVE: 5 POPUP reads in a row = zombie popup (03.11.: 0..4 POPUP)
ESCAPE_CYCLES = 2       # LIVE: ladder repetitions before giving up
LADDER = ('resolver', 'back', 'ground', 'back2')
PURCHASE_WORDS = ('purchase', 'buy', 'recharge', 'top up', 'top-up', 'diamond', 'pack')


def escape_ladder(tag: str = 'esc', cycles: int = ESCAPE_CYCLES) -> bool:
    """Bounded escape from a screen the normal pass could not leave. True when
    WORLD/PANEL was reached (marker 'ESCAPE: recovered'), else 'ESCAPE: gave up'."""
    for cycle in range(1, cycles + 1):
        for step in LADDER:
            name = f'{tag}_{cycle}_{step}'
            img = v.shot(name)
            st = v.classify(img)
            if st in ('WORLD', 'PANEL'):
                print(f'    ESCAPE: recovered ({st}) before step {step}, cycle {cycle}', flush=True)
                return True
            if v.is_confirm_dialog(img):
                print(f'    escape {cycle}/{step}: confirm dialog -> cancel', flush=True)
                v.tap(v.CONFIRM_CANCEL, 1.5)
                continue
            if step == 'resolver':
                hit = v.resolve_startup_popup(f'{name}_pop')
                print(f'    escape {cycle}/{step}: login popup {"claimed" if hit else "not recognised"}',
                      flush=True)
            elif step == 'back':
                print(f'    escape {cycle}/{step}: BACK ({st})', flush=True)
                v.tap(v.BACK, 1.5)
            elif step == 'ground':
                lines = ' '.join(v.ocr_lines(name)).lower()
                if any(w in lines for w in PURCHASE_WORDS):
                    print(f'    escape {cycle}/{step}: purchase text on screen -> ground tap skipped',
                          flush=True)
                    continue
                print(f'    escape {cycle}/{step}: tap empty ground {v.GROUND}', flush=True)
                v.tap(v.GROUND, 1.5)
            else:
                print(f'    escape {cycle}/{step}: BACK x2 ({st})', flush=True)
                v.tap(v.BACK, 1.2)
                v.tap(v.BACK, 1.5)
    st = v.classify(v.shot(f'{tag}_final'))
    if st in ('WORLD', 'PANEL'):
        print(f'    ESCAPE: recovered ({st}) after {cycles} cycle(s)', flush=True)
        return True
    print(f'    ESCAPE: gave up after {cycles} cycle(s), screen {st}', flush=True)
    return False


def main() -> int:
    popups = 0
    for i in range(4):
        st = v.classify(v.shot(f'norm_{i}'))
        print(f'    normalize {i}: {st}', flush=True)
        if st in ('WORLD', 'PANEL'):
            return 0
        popups = popups + 1 if st == 'POPUP' else 0
        if st == 'POPUP' and v.resolve_startup_popup(f'norm_pop{i}'):
            time.sleep(1.0)
            continue
        v.tap(v.BACK, 1.5)
    st = v.classify(v.shot('norm_final'))
    print(f'    normalize final: {st}', flush=True)
    if st in ('WORLD', 'PANEL'):
        return 0
    popups = popups + 1 if st == 'POPUP' else 0
    if popups >= POPUP_STREAK:
        print(f'    normalize: {popups}x POPUP in a row — escape ladder', flush=True)
        return 0 if escape_ladder('norm_esc') else 1
    return 1


if __name__ == '__main__':
    sys.exit(main())
