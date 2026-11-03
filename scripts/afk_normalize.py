#!/usr/bin/env python3
"""Normalize the game screen back to a known state (world / AFK panel).

Used by the scheduler wrapper between phases: a phase that ends on an unknown
screen (live case: the gift driver's camera pan accidentally tapped into the
Arcane Labyrinth card) otherwise poisons every follow-up phase. Non-blind:
classify() per step, capped BACK taps, login popups get claimed when OCR'd.

Exit: 0 world/panel reached, 1 still unknown after the cap.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402


def main() -> int:
    for i in range(4):
        st = v.classify(v.shot(f'norm_{i}'))
        print(f'    normalize {i}: {st}', flush=True)
        if st in ('WORLD', 'PANEL'):
            return 0
        if st == 'POPUP' and v.resolve_startup_popup(f'norm_pop{i}'):
            time.sleep(1.0)
            continue
        v.tap(v.BACK, 1.5)
    st = v.classify(v.shot('norm_final'))
    print(f'    normalize final: {st}', flush=True)
    return 0 if st in ('WORLD', 'PANEL') else 1


if __name__ == '__main__':
    sys.exit(main())
