"""Harmless practice target for spectre (Python version).

Holds a "score" in memory and changes it every time you press Enter, so you
can learn the find -> search -> search --continue -> dump -> dumpdiff
workflow without a real game (see examples/README.md).

The score lives in a ctypes buffer: a plain little-endian 32-bit integer at a
fixed address for the life of the process (CPython never moves objects), so
`spectre search <pid> u32 <value> --continue` can follow it.

Usage:
    python examples/practice_target.py [--start 31337] [--step 100] [--reveal]

The script only touches its own memory. Quit with q + Enter or Ctrl+C.
"""

import argparse
import ctypes
import os
import sys

BLOCK_SIZE = 64
SCORE_OFFSET = 0x10


def main() -> int:
    parser = argparse.ArgumentParser(description="spectre practice target")
    parser.add_argument("--start", type=int, default=31337, help="initial score")
    parser.add_argument("--step", type=int, default=100, help="added on every Enter")
    parser.add_argument(
        "--reveal", action="store_true", help="print the score address (answer key)"
    )
    args = parser.parse_args()

    # 64-byte block filled with 0xAB markers; the score sits at offset 0x10,
    # the round counter in the byte right after it.
    block = (ctypes.c_uint8 * BLOCK_SIZE)(*([0xAB] * BLOCK_SIZE))
    score = ctypes.c_uint32.from_buffer(block, SCORE_OFFSET)
    rounds = ctypes.c_uint8.from_buffer(block, SCORE_OFFSET + 4)
    score.value = args.start
    rounds.value = 0

    print("spectre practice target")
    print(f"PID:   {os.getpid()}")
    if args.reveal:
        base = ctypes.addressof(block)
        print(f"score address: {base + SCORE_OFFSET:#x}  (block starts at {base:#x})")
    print(f"score: {score.value}")
    print(f"Press Enter to add {args.step} to the score, q + Enter to quit.")
    sys.stdout.flush()

    for line in sys.stdin:
        if line.strip() == "q":
            break
        rounds.value = (rounds.value + 1) % 256
        score.value = (score.value + args.step) & 0xFFFFFFFF
        print(f"score: {score.value}")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
