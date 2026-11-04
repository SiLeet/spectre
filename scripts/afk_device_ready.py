#!/usr/bin/env python3
"""Poll a freshly started game until it is playable (T65, used by device-ensure.sh).

Per step (classify() on a screenshot, never a blind tap):
  WORLD / PANEL -> ready (exit 0)
  POPUP         -> the login-popup resolver (free Monthly/Daily rewards);
                   any other popup gets one BACK (afk_normalize semantics)
  UNKNOWN       -> title screen ('tap to start', OCR-gated) gets a centre tap;
                   everything else is a loading screen and is waited out —
                   no BACK here (on the title it opens the quit dialog)
After the timeout afk_normalize runs once (bounded, classify-gated) as the
last resort. Exit codes: 0 ready, 1 not reached.

Usage: python scripts/afk_device_ready.py [--timeout 180] [--poll 5]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402
import afk_normalize  # noqa: E402

TITLE_TAP = (960, 540)                       # 'tap anywhere' title screen (LIVE to check)
TITLE_WORDS = ('tap to start', 'touch to start', 'tap anywhere', 'tap to continue')


def is_title(lines: list[str]) -> bool:
    joined = ' '.join(lines).lower()
    return any(w in joined for w in TITLE_WORDS)


def wait_ready(timeout: float, poll: float) -> bool:
    deadline = time.monotonic() + timeout
    i = 0
    while time.monotonic() < deadline:
        tag = f'dev_{i}'
        st = v.classify(v.shot(tag))
        print(f'    device-ready {i}: {st}', flush=True)
        if st in ('WORLD', 'PANEL'):
            return True
        if st == 'POPUP':
            if not v.resolve_startup_popup(f'dev_pop{i}'):
                v.back(1.5)             # T97: keyevent on the POPUP, never the world
        elif st == 'UNKNOWN' and is_title(v.ocr_lines(tag)):
            print('    title screen -> tap to start', flush=True)
            v.tap(TITLE_TAP, 3.0)
        i += 1
        time.sleep(poll)
    return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--timeout', type=float, default=180)
    ap.add_argument('--poll', type=float, default=5)
    args = ap.parse_args(argv)
    if wait_ready(args.timeout, args.poll):
        print('    device ready (world/panel)', flush=True)
        return 0
    print(f'    world not reached in {args.timeout:.0f}s — one normalizer pass', flush=True)
    return afk_normalize.main()


if __name__ == '__main__':
    sys.exit(main())
