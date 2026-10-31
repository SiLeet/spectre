"""Model-free wallet hunt over ALL remaining anonymous rw regions.

A = idle before claim, B = right after, C = 90 s later.
Wallet criterion (no rate model needed): A != B, B == C (stable while idle),
B > A, plausible magnitude. Continuous accumulators keep growing between B and
C and therefore drop out; churn slots fail B == C.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(r'C:/Users/Sigi/spectre')
OUT = REPO / '.spectre' / 'hunt'
OUT.mkdir(parents=True, exist_ok=True)
SPECTRE = str(REPO / 'target' / 'release' / 'spectre.exe')
PID = '7529'
COVERED = [
    (0x724DD04E7000, 0x724DD4A16000), (0x724DDFF1D000, 0x724DE4700000),
    (0x724E30000000, 0x724E33400000), (0x724E60000000, 0x724E64400000),
    (0x724EA0000000, 0x724EA9400000), (0x724EB0000000, 0x724EB4000000),
    (0x724DF0000000, 0x724DF0000000 + 0x800000),
]


def regions():
    regs = json.load(open(r'C:/Users/Sigi/AppData/Local/Temp/spectre-gold/regions.json'))

    def overlaps(s, e):
        return any(not (e <= cs or s >= ce) for cs, ce in COVERED)

    todo = []
    for r in regs:
        s, e = int(r['start'], 16), int(r['end'], 16)
        if not r['perms'].startswith('rw') or r.get('path'):
            continue
        if e - s < 64 * 1024 or overlaps(s, e):
            continue
        todo.append((s, e - s))
    todo.sort(key=lambda x: -x[1])
    return todo


def dump_all(tag, todo):
    t0 = time.time()
    for idx, (start, size) in enumerate(todo):
        f = OUT / f'{tag}_{idx}.bin'
        if f.exists() and f.stat().st_size == size:
            continue
        subprocess.run([SPECTRE, 'dump', PID, hex(start), str(size), '--adb',
                        '--format', 'raw', '--output', str(f)],
                       cwd=REPO, capture_output=True)
        if idx % 50 == 0:
            print(f'  {tag} {idx}/{len(todo)} ({time.time()-t0:.0f}s)', flush=True)
    print(f'{tag} done in {time.time()-t0:.0f}s', flush=True)


def claim():
    r = subprocess.run([SPECTRE, '-v', 'bot', 'examples/bot-config-afk-live.yaml', '--adb', '--once'],
                       cwd=REPO, capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if 'tap sequence' in line or 'WARN' in line:
            print(line, flush=True)


def main():
    todo = regions()
    print(f'regions to dump: {len(todo)} ({sum(s for _, s in todo)/1048576:.0f} MB)', flush=True)
    (OUT / 'regions.json').write_text(json.dumps([[s, z] for s, z in todo]))
    print('A', flush=True); dump_all('A', todo)
    print('CLAIM', flush=True); claim()
    print('B', flush=True); dump_all('B', todo)
    print('wait 90s', flush=True); time.sleep(90)
    print('C', flush=True); dump_all('C', todo)
    print('DONE', flush=True)


if __name__ == '__main__':
    sys.exit(main())
