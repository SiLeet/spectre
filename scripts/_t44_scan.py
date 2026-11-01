"""T44 diagnostics: list ALL revalidation candidates in the anchor window."""
import sys, time, struct
sys.path.insert(0, 'scripts')
import afk_claim_vision as v

BASE = 0x724DF0000000
PID = '1443'
LAST = 259850

lo = max(v.GUARD_LO, int(LAST * 0.98))
hi = min(v.GUARD_HI, int(LAST * 5) + 1_000_000)
print(f'window: [{lo}, {hi}]')

dumps = []
for i in (1, 2):
    out = v.TMP / f'diag_{i}.bin'
    out.parent.mkdir(parents=True, exist_ok=True)
    if v.adb_exec_dump(PID, hex(BASE), out, str(v.SCAN_BYTES)) is None:
        print('dump failed'); sys.exit(1)
    dumps.append(out.read_bytes())
    if i == 1:
        time.sleep(5)
print(f'dump sizes: {[len(d) for d in dumps]}')

h1 = v.scan_i64_range(dumps[0], lo, hi)
h2 = v.scan_i64_range(dumps[1], lo, hi)
print(f'values in window dump1: {len(h1)}, dump2: {len(h2)}')

stable = [(val, offs) for val, offs in h1.items() if val in h2 and len(offs) >= 2]
stable.sort(key=lambda x: -len(x[1]))
print(f'stable + >=2 copies: {len(stable)}')
for val, offs in stable[:25]:
    is_pow2 = (val & (val - 1)) == 0
    # pointer-ish neighbor check: any 8-byte slot within +-48 bytes that looks
    # like a userspace pointer 0x7xxxxxxxxxxx (0x70..0x7f top byte)
    def has_ptr(o):
        for d in range(-48, 49, 8):
            p = o + d
            if 0 <= p <= len(dumps[0]) - 8:
                pv = int.from_bytes(dumps[0][p:p+8], 'little', signed=True)
                if 0x700000000000 <= pv <= 0x7fffffffffff:
                    return True
        return False
    addr1 = [hex(BASE + o) for o in offs[:4]]
    print(f'  val={val} copies={len(offs)} pow2={is_pow2} ptr_near={has_ptr(offs[0])} at={addr1}')

# also: does the CURRENT power show up anywhere? check wide window for values
# in [100k, 3M] with >=2 copies, to see the real power's copy structure
wide = [(val, offs) for val, offs in h1.items() if 100_000 <= val <= 3_000_000 and len(offs) >= 2]
print(f'wide window (100k..3M, >=2 copies, no stability): {len(wide)} values')
wide.sort(key=lambda x: -len(x[1]))
for val, offs in wide[:15]:
    print(f'  val={val} copies={len(offs)} first={hex(BASE+offs[0])}')
