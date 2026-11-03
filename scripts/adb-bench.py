#!/usr/bin/env python3
"""adb latency benchmark: `input tap` and `screencap` round trips (T64, H6).

Times N calls of each (default 50) through the bot's own adb helper and
prints p50 / p90 / p99 / max in milliseconds. The tap goes to (300,250), the
world-view 'ground' tap the drivers already use to dismiss menus; it only
runs when a screenshot classifies as WORLD (pass --force to skip the gate).
Live device -> Hermes lane, bot idle.

Usage: python scripts/adb-bench.py [--n 50] [--only tap|screencap] [--force]
Exit codes: 0 done, 1 tap bench refused (not on the world view), 2 adb failure.
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402

TAP = v.GROUND                      # (300,250): harmless on the world view


def percentile(samples: list[float], p: float) -> float:
    """Nearest-rank percentile (p in 0..100) of a non-empty sample list."""
    s = sorted(samples)
    return s[max(0, math.ceil(p / 100 * len(s)) - 1)]


def time_calls(n: int, args: tuple[str, ...]) -> list[float]:
    """Milliseconds per adb call; RuntimeError on the first failed call."""
    out = []
    for _ in range(n):
        t0 = time.perf_counter()
        p = v.adb(*args)
        out.append((time.perf_counter() - t0) * 1000)
        if p.returncode != 0:
            raise RuntimeError(f'adb {" ".join(args[:3])} failed: {p.stderr[:120]!r}')
    return out


def row(name: str, ms: list[float]) -> str:
    return (f'{name:<10} {len(ms):>4} {percentile(ms, 50):>8.1f} {percentile(ms, 90):>8.1f} '
            f'{percentile(ms, 99):>8.1f} {max(ms):>8.1f}')


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='adb tap / screencap latency percentiles')
    ap.add_argument('--n', type=int, default=50)
    ap.add_argument('--only', choices=('tap', 'screencap'))
    ap.add_argument('--force', action='store_true', help='tap even if the screen is not the world view')
    args = ap.parse_args(argv)

    results = {}
    try:
        if args.only != 'screencap':
            if not args.force and v.classify(v.shot('bench_pre')) != 'WORLD':
                print('REFUSED: tap bench needs the world view ((300,250) is only harmless there); '
                      'use --only screencap or --force', file=sys.stderr)
                return 1
            results['tap'] = time_calls(args.n, ('shell', 'input', 'tap', str(TAP[0]), str(TAP[1])))
        if args.only != 'tap':
            results['screencap'] = time_calls(args.n, ('exec-out', 'screencap', '-p'))
    except RuntimeError as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2
    print(f'{"call":<10} {"n":>4} {"p50 ms":>8} {"p90 ms":>8} {"p99 ms":>8} {"max ms":>8}')
    for name, ms in results.items():
        print(row(name, ms))
    return 0


if __name__ == '__main__':
    sys.exit(main())
