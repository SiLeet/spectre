"""Gold wallet hunt: A (idle) vs B (after claim) vs C (idle).

Wallet criteria: value changed at the claim (A != B), stable while idle
afterwards (B == C), grew (B > A), plausible magnitude, and delta big
enough that continuous accumulators (which keep growing between B and C)
are excluded.
"""
import struct
import sys
from pathlib import Path

T = Path(r'C:/Users/Sigi/AppData/Local/Temp/spectre-gold/heaps')
BASE_ADDRS = [
    0x724DD04E7000, 0x724DDFF1D000, 0x724E30000000,
    0x724E60000000, 0x724EA0000000, 0x724EB0000000,
]
PAGE = 0x1000


def load(tag, idx):
    p = T / f'{tag}_{idx}.bin'
    return p.read_bytes() if p.exists() else None


def candidates_for(i):
    a, b, c = load('A', i), load('B', i), load('C', i)
    if not (a and b and c):
        return []
    n = min(len(a), len(b), len(c))
    base = BASE_ADDRS[i]
    out = []
    for o in range(0, n - 8, 4):
        va = struct.unpack_from('<I', a, o)[0]
        vb = struct.unpack_from('<I', b, o)[0]
        vc = struct.unpack_from('<I', c, o)[0]
        if va != vb and vb == vc and vb > va:
            d = vb - va
            if 100 <= d <= 5_000_000 and 1_000 <= vb <= 2_000_000_000:
                out.append((o, 'u32', va, vb, vc, d))
        # u64 on 8-byte alignment
        if o % 8 == 0:
            wa = struct.unpack_from('<Q', a, o)[0]
            wb = struct.unpack_from('<Q', b, o)[0]
            wc = struct.unpack_from('<Q', c, o)[0]
            if wa != wb and wb == wc and wb > wa:
                d = wb - wa
                if 100 <= d <= 5_000_000 and 1_000 <= wb <= 2_000_000_000:
                    out.append((o, 'u64', wa, wb, wc, d))
    return [(base + o, w, va, vb, vc, d) for (o, w, va, vb, vc, d) in out]


def main():
    total = 0
    for i in range(len(BASE_ADDRS)):
        cands = candidates_for(i)
        print(f'--- heap{i} (0x{BASE_ADDRS[i]:X}): {len(cands)} candidates')
        for absa, w, va, vb, vc, d in cands[:40]:
            print(f'   0x{absa:X} {w}  {va} -> {vb} (C={vc}) +{d}')
        total += len(cands)
    print('total', total)


if __name__ == '__main__':
    sys.exit(main())
