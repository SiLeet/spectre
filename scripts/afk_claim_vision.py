"""State-checked AFK Journey claim driver.

Instead of firing a blind tap sequence, this script screenshots the emulator,
classifies the screen (WORLD / PANEL / POPUP) from a few stable colour probes,
and only taps when the expected screen is actually up. That makes the claim
observable and stops the silent no-ops the blind sequence produced when the game
was sitting in some other panel.

Screen signatures (1920x1080 BlueStacks, measured 2026-10-31):
  (474,1010) back-arrow circle : WORLD  ~(62,70,50) dark green
                                PANEL  ~(184,176,174) light grey
                                POPUP  ~(62,58,57) dimmed
  (1390,704) claim chip        : PANEL/POPUP ~(240,191,52) orange
  (960,602)  popup claim bar   : POPUP  ~(233,179,117) bright

Usage: python scripts/afk_claim_vision.py [--rounds N] [--pause S] [--dry-run]
Exit codes: 0 claim verified, 1 could not reach a claimable state (or the screen
was unrecognised — blind taps are refused), 2 adb/preflight error,
4 nothing claimable yet (chest accrual too small), 5 skipped (PC in use).
"""
from __future__ import annotations

import argparse
import json
import shutil
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parent.parent
import os
TMP = REPO / '.spectre' / f'shots-{os.getpid()}'   # per-run dir: concurrent runs must not collide
# created lazily in shot(): importing this module (--help, dry-run) must not touch the disk
ADB = Path.home() / 'AppData/Local/Android/Sdk/platform-tools/adb.exe'
SERIAL = '127.0.0.1:5555'

# --- team_power guard (T44) -------------------------------------------------
# The offset is valid for ONE process lifetime only: after a game restart the
# heap base can survive while the layout inside the region moves, so the slot
# goes stale. Re-location is anchored on the last VERIFIED value (state file):
# power moves slowly and only upward for this bot, so a tight window
# [0.98x .. 5x last] + stability across two dumps + >=2 display copies
# (the game keeps display copies next to the authoritative slot) isolates the
# slot without any screen-state dependency.
POWER_STATE = REPO / '.spectre' / 'power-state.json'
DEFAULT_POWER_OFFSET = 0xA578
SCAN_BYTES = 16 * 1024 * 1024
GUARD_LO, GUARD_HI = 100_000, 10_000_000_000


def drift_window(last: int) -> int:
    """Allowed |power - last verified| (the ONE drift rule: preflight + re-location)."""
    return max(2000, int(int(last) * 0.10))


def load_power_state() -> dict:
    try:
        return json.loads(POWER_STATE.read_text())
    except Exception:
        return {}


def save_power_state(state: dict) -> None:
    try:
        state['updated'] = time.strftime('%Y-%m-%dT%H:%M:%S')
        tmp = POWER_STATE.with_suffix('.tmp')       # atomic: concurrent runs must not
        tmp.write_text(json.dumps(state))          # leave a half-written state file
        os.replace(tmp, POWER_STATE)
    except Exception:
        pass   # the guard is best-effort; never break a run over the state file


def adb_exec_dump(pid: str, addr: str, out_path: Path, size: str = '8') -> subprocess.CompletedProcess | None:
    """spectre dump <addr> as raw bytes. None on failure."""
    try:
        p = subprocess.run([str(REPO / 'target' / 'release' / 'spectre.exe'), 'dump', pid, addr, size,
                            '--adb', '--format', 'raw', '--output', str(out_path)],
                           cwd=REPO, capture_output=True, timeout=300)
    except subprocess.TimeoutExpired:      # a hung dump must not crash the run
        return None
    if p.returncode != 0 or not Path(out_path).exists():
        return None
    return p


def read_power(pid: str, base_hex: str, offset: int, width: int = 8) -> int | None:
    """Read the i32/i64 at heap_base + offset. None on failure."""
    out = TMP / 'power.bin'   # per-run path: concurrent runs raced on the shared file
    out.parent.mkdir(parents=True, exist_ok=True)
    if adb_exec_dump(pid, hex(int(base_hex, 16) + offset), out) is None:
        return None
    raw = out.read_bytes()
    if len(raw) < 8:
        return None
    return struct.unpack('<q' if width == 8 else '<i', raw[:width])[0]


def read_power_entry_valid(pid: str, base_hex: str, offset: int, expected: int) -> bool | None:
    '''Validate a map entry by exact u32 value and heap pointer at +8.

    The +4 hash word is opaque; the measured layout does not require a
    particular hash value. None means the memory read failed; False means the
    bytes were readable but the value/alignment/pointer structure did not match.
    '''
    if offset < 0 or offset % 8:
        return False
    out = TMP / 'power_entry.bin'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    if adb_exec_dump(pid, hex(int(base_hex, 16) + offset), out, '16') is None:
        return None
    raw = out.read_bytes()
    if len(raw) < 16:
        return None
    # Compare the u32 bit pattern, not its signed-i32 interpretation: a map
    # value with bit 31 set is still structurally meaningful in a u64 alias.
    value = int.from_bytes(raw[:4], 'little')
    return value == (int(expected) & 0xFFFF_FFFF) and _ptr_after(raw, 0)


def scan_slots(buf: bytes, lo: int, hi: int) -> tuple[dict[int, list[int]], dict[int, list[int]]]:
    """One pass over 4-byte steps: u32 AND u64 little-endian slots in [lo, hi].

    Prefilter (valid because lo >= 100k): u32 needs byte+3 == 0, u64 needs
    bytes +5/+6/+7 == 0 and byte+4 <= hi>>32."""
    u32: dict[int, list[int]] = {}
    u64: dict[int, list[int]] = {}
    b4_max = hi >> 32
    for off in range(0, len(buf) - 8, 4):
        if buf[off + 3] == 0:
            v = int.from_bytes(buf[off:off + 4], 'little', signed=True)
            if lo <= v <= hi:
                u32.setdefault(v, []).append(off)
        if not (buf[off + 5] or buf[off + 6] or buf[off + 7] or buf[off + 4] > b4_max):
            v = int.from_bytes(buf[off:off + 8], 'little', signed=True)
            if lo <= v <= hi:
                u64.setdefault(v, []).append(off)
    return u32, u64


def _ptr_after(buf: bytes, off: int) -> bool:
    """True if the measured map-entry pointer at +8 is a userspace heap ptr."""
    if off < 0 or off + 16 > len(buf):
        return False
    pv = int.from_bytes(buf[off + 8:off + 16], 'little')
    return 0x7000_0000_0000 <= pv <= 0x7FFF_FFFF_FFFF


def _u32_map_shape(buf: bytes, off: int, value: int) -> bool:
    """True when [u32 value][opaque hash][heap pointer] matches this u64 hit."""
    if off < 0 or off % 8 or off + 16 > len(buf):
        return False
    low = int.from_bytes(buf[off:off + 4], 'little')
    combined = int.from_bytes(buf[off:off + 8], 'little', signed=True)
    # The hash can be nonzero and the u32 can set its high bit. Compare the
    # exact raw u64 candidate plus its low-word map value; do not interpret the
    # opaque hash as a requirement that it be zero.
    return low == (value & 0xFFFF_FFFF) and combined == value and _ptr_after(buf, off)


def _alloc_shape(v: int) -> bool:
    """Allocator/metadata shapes: multiples of 4096 and size|flag bit-0 values."""
    return v % 4096 in (0, 1)


def revalidate_power_offset(pid: str, base_int: int, last_power: int) -> tuple[int, int, int] | None:
    """Re-locate the team_power slot after a game restart.

    Dumps the first 16 MB of the hot heap twice (5 s apart). A fresh process
    holds only server-synced state, so the last VERIFIED value (or a slowly
    drifted version of it) must exist somewhere. Two slot shapes are accepted
    (live-measured 2026-11-01):
      u32 map entry — [u32 value][u32 hash][heap ptr], single copy,
      u64 field     — display copies + authoritative slot, >= 2 copies.
    u32 map entries are single-copy by design, but the live heap also contains
    unrelated pointer-shaped u32 values. Accept a u32 only as a unique stable
    candidate that exactly equals the last VERIFIED anchor and has the measured
    [value][hash][heap pointer] shape in both snapshots. If both widths survive,
    the exact-anchor u32 beats a merely nearby u64; otherwise prefer the ranked
    u64 identity candidate. If identity is ambiguous, fail closed.
    Alloc/metadata shapes are excluded. Returns
    (offset, width, value) or None.
    """
    anchor = int(last_power)
    tol = drift_window(anchor)
    lo = max(GUARD_LO, anchor - tol)
    hi = min(GUARD_HI, int(anchor * 5) + 1_000_000)
    dumps: list[bytes] = []
    try:
        for i in (1, 2):
            out = TMP / f'power_scan_{i}.bin'
            out.parent.mkdir(parents=True, exist_ok=True)
            if adb_exec_dump(pid, hex(base_int), out, str(SCAN_BYTES)) is None:
                return None
            buf = out.read_bytes()
            if len(buf) < 1024:
                return None
            dumps.append(buf)
            if i == 1:
                time.sleep(5)
    finally:
        for i in (1, 2):
            try:
                (TMP / f'power_scan_{i}.bin').unlink()
            except OSError:
                pass
    u32a, u64a = scan_slots(dumps[0], lo, hi)
    u32b, u64b = scan_slots(dumps[1], lo, hi)

    def best_of(hits_a: dict, hits_b: dict, width: int):
        cand = None   # (dist, stable_copies, off, value)
        ambiguous = False
        for val, offs_a in hits_a.items():
            offs_b = hits_b.get(val)
            if not offs_b or _alloc_shape(val):
                continue
            # Equal values at different offsets are not a stable slot. Require
            # exact address persistence across both snapshots before ranking.
            offs = sorted(set(offs_a) & set(offs_b))
            if width == 8:
                # The map hash is opaque: even a nonzero hash can make a
                # plausible in-range u64. Reject any measured map-entry structure
                # rather than treating its value+hash as a power field.
                # The u32-shape probe needs 16 bytes; do not trust a truncated
                # u64 candidate at the end of either dump where its alias cannot
                # be ruled out.
                offs = [o for o in offs if all(o + 16 <= len(buf) for buf in dumps)
                        and not any(_u32_map_shape(buf, o, val) for buf in dumps)]
                if len(offs) < 2:          # two stable display/authoritative copies
                    continue
            else:
                # Pointer-backed u32-shaped noise is common in live heaps.
                # Only accept the exact last-verified value, and only when it
                # identifies one stable map-entry slot.
                if val != anchor:
                    continue
                offs = [o for o in offs if o % 8 == 0
                        and _ptr_after(dumps[0], o) and _ptr_after(dumps[1], o)]
                if len(offs) != 1:
                    continue
            dist = abs(val - anchor)
            if dist > tol:
                continue
            copies = len(offs)
            if cand is None or dist < cand[0] or (dist == cand[0] and copies > cand[1]):
                cand = (dist, copies, offs[0], val)
                ambiguous = False
            elif dist == cand[0] and copies == cand[1] and val != cand[3]:
                # Do not let heap address/insertion order choose identity.
                ambiguous = True
        return None if ambiguous else cand

    u64c = best_of(u64a, u64b, 8)
    u32c = best_of(u32a, u32b, 4)
    # The exact last-verified u32 map entry is stronger evidence than a
    # different u64 value that merely falls inside the drift window.
    if u32c and u32c[3] == anchor:
        pick, width = u32c, 4
    else:
        pick, width = (u64c, 8) if u64c else (u32c, 4)
    if pick is None:
        return None
    return pick[2], width, pick[3]


def memory_preflight(pid: str, base_hex: str, *, read_value=None,
                     read_entry=None) -> tuple[str, int | None]:
    """Read team_power as a sanity check for pid + heap base.

    Returns (status, value) with status in:
      'ok'       — plausible power; the mapping is current (state file updated,
                   so the next process restart has a fresh re-location anchor)
      'disabled' — the recorded offset is stale and re-location failed (or no
                   anchor exists): the guard is OFF for this process lifetime,
                   the vision gates still protect the taps. Callers log this
                   quietly instead of spamming a WARN every run (T44).
      'fail'     — the read itself failed (dead pid / no adb).

    read_value/read_entry replace read_power/read_power_entry_valid (same
    signatures) so a faster backend (afk_memory: one read-batch) reuses this
    guard instead of duplicating it.
    """
    read_value = read_value or read_power
    read_entry = read_entry or read_power_entry_valid
    st = load_power_state()
    offset = int(st.get('offset', DEFAULT_POWER_OFFSET))
    width = int(st.get('width', 8))
    power = read_value(pid, base_hex, offset, width)
    if power is None:
        return 'fail', None
    last = st.get('power')
    try:
        same_base = int(str(st.get('base', '')), 16) == int(base_hex, 16)
    except (TypeError, ValueError):
        same_base = False
    same_process = str(st.get('pid', '')) == str(pid)
    identity_matches = same_process and same_base

    # A u32 value alone is not enough: require the measured map-entry shape
    # (same low word + heap pointer at +8) before trusting a stored direct offset.
    # A u64 read combines the map's value and hash words; probe the low u32 so a
    # non-zero hash cannot hide the same map-entry structure.
    entry_valid = True
    if width in (4, 8):
        map_value = power if width == 4 else power & 0xFFFF_FFFF
        map_entry_shape = read_entry(pid, base_hex, offset, map_value)
        if map_entry_shape is None:
            return 'fail', None
        entry_valid = map_entry_shape if width == 4 else not map_entry_shape

    # Direct reads are only trusted for the exact process + heap identity that
    # produced the verified state. A changed PID/base always re-locates, even
    # when the value at the old offset happens to be in tolerance.
    drift_ok = not last or abs(power - int(last)) <= drift_window(last)
    if (identity_matches and entry_valid and GUARD_LO < power < GUARD_HI and drift_ok):
        st.update({'offset': offset, 'width': width, 'power': power,
                   'pid': pid, 'base': base_hex})
        save_power_state(st)
        return 'ok', power
    # stale: try to re-locate from the last verified value
    if last:
        found = revalidate_power_offset(pid, int(base_hex, 16), int(last))
        if found:
            new_off, new_w, val = found
            save_power_state({'offset': new_off, 'width': new_w, 'power': val,
                              'pid': pid, 'base': base_hex, 'revalidated': True})
            return 'ok', val
    return 'disabled', power

AFK_PROGRESS = (60, 1036)
CHEST = (975, 760)
CLAIM = (960, 602)
BACK = (474, 1010)
GROUND = (300, 250)
LOGIN_CLAIM = (960, 930)   # 'Esperia Monthly / Daily Rewards' popup Claim (verified live)
POWERSHELL = r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
OCR_PS1 = Path(__file__).resolve().parent.parent / 'templates' / 'ocr.ps1'


def ocr_png(png: Path, timeout: int = 20, check_rc: bool = False) -> list[str]:
    """WinRT OCR (templates/ocr.ps1, offline) on a PNG; [] on any failure.

    check_rc=True also treats a non-zero exit as failure (afk_stage_push's
    historical semantics); ocr_lines keeps its stdout-only behaviour."""
    png = Path(png).resolve()          # ocr.ps1 needs absolute native paths
    try:
        pr = subprocess.run([POWERSHELL, '-NoProfile', '-ExecutionPolicy', 'Bypass',
                             '-File', str(OCR_PS1), '-Path', str(png)],
                            capture_output=True, timeout=timeout, text=True,
                            encoding='utf-8', errors='replace')
        if check_rc and pr.returncode != 0:
            return []
        return [ln.strip() for ln in pr.stdout.splitlines() if ln.strip()]
    except (subprocess.SubprocessError, OSError):
        return []


def ocr_region(name: str, box: tuple[int, int, int, int]) -> list[str]:
    """OCR only `box` (l, t, r, b) of the saved shot `name` (T76). A crop
    isolates small text the full-frame OCR merges with the layout; [] on any
    failure, like ocr_lines."""
    try:
        with Image.open(TMP / f'{name}.png') as im:
            crop = im.crop(box)
            out = TMP / f'{name}_r.png'
            crop.save(out)
    except (OSError, ValueError):
        return []
    return ocr_png(out)


def ocr_lines(name: str) -> list[str]:
    """WinRT OCR on a screenshot already saved by shot() (offline, real text)."""
    png = TMP / f'{name}.png'
    if not png.exists():
        return []
    return ocr_png(png)


def resolve_startup_popup(tag: str) -> bool:
    """Handle the known login popup (Esperia Monthly / Daily Rewards).

    Appears on a fresh game login, sits in POPUP state and blocks every flow.
    The Claim is free (accumulated daily rewards). OCR gates the tap so the
    resolver stays non-blind; a follow-up card is dismissed with one BACK.
    Returns True when the popup was recognised and handled.
    """
    shot(tag)
    lines = ocr_lines(tag)
    hit = any(('monthly' in l.lower() or 'gazette' in l.lower()
               or 'daily rewards' in l.lower()) for l in lines)
    if not hit:
        return False
    print(f'    {tag}: login popup detected -> claim', flush=True)
    tap(LOGIN_CLAIM, 3.0)
    st = classify(shot(f'{tag}_after'))
    if st in ('POPUP', 'UNKNOWN'):
        tap(BACK, 1.5)          # rewards-obtained card / second popup
        st = classify(shot(f'{tag}_dismiss'))
    print(f'    {tag}: after login claim: {st}', flush=True)
    return True


def adb(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run([str(ADB), '-s', SERIAL, *args], capture_output=True, timeout=timeout)


def tap(xy: tuple[int, int], wait: float = 1.0) -> None:
    p = adb('shell', 'input', 'tap', str(xy[0]), str(xy[1]))
    if p.returncode != 0:
        raise RuntimeError(f'adb tap failed at {xy}: {p.stderr[:120]!r}')
    time.sleep(wait)


def _run_seq(cmds: list[str], waits: list[float], tolerate: bool, dry: bool):
    """One `adb shell` for several input commands: 'cmd && sleep W && cmd ...'.
    Steps are '&&'-joined (wave-6 review: with ';' a failing middle step was
    swallowed) - a failure stops the rest and its rc reaches tolerate=False
    like tap(); a trailing `sleep` when its wait > 0; bounded by waits + 15 s."""
    parts = []
    for cmd, wait in zip(cmds, waits):
        parts.append(cmd)
        if wait > 0:
            parts.append(f'sleep {wait:g}')   # LIVE: fractional sleep (toybox, Android 9 Pie64)
    line = ' && '.join(parts)
    if dry:
        return line
    p = adb('shell', line, timeout=int(sum(waits)) + 15)
    if p.returncode != 0 and not tolerate:
        raise RuntimeError(f'adb input sequence failed: {p.stderr[:120]!r}')
    return p.returncode == 0


def tap_seq(steps, tolerate: bool = True, dry: bool = False):
    """Several taps in ONE adb round trip (T75; each adb call costs ~0.5-1.5 s).

    steps: [(x, y, wait_s), ...]. Returns True/False (tolerate=True) or raises
    RuntimeError like tap() (tolerate=False); dry=True returns the shell line.
    Only for BLIND runs - a step that needs a screenshot in between stays tap()."""
    return _run_seq([f'input tap {int(x)} {int(y)}' for x, y, _ in steps],
                    [w for _, _, w in steps], tolerate, dry)


def key_seq(steps, tolerate: bool = True, dry: bool = False):
    """Several keyevents in ONE adb round trip; steps: [(keycode, wait_s), ...]."""
    return _run_seq([f'input keyevent {int(k)}' for k, _ in steps],
                    [w for _, w in steps], tolerate, dry)


def swipe(x1: int, y1: int, x2: int, y2: int, millis: int = 400, wait: float = 1.0) -> None:
    p = adb('shell', 'input', 'swipe', str(x1), str(y1), str(x2), str(y2), str(millis))
    if p.returncode != 0:                  # same contract as tap()
        raise RuntimeError(f'adb swipe failed {(x1, y1)}->{(x2, y2)}: {p.stderr[:120]!r}')
    time.sleep(wait)


RAW_HEADERS = (12, 16)   # screencap raw header: w,h,format (+ colorspace on Android 9+)


def _raw_to_image(data: bytes) -> Image.Image | None:
    """`screencap` raw output -> RGB image; None unless the size is exactly
    w*h*4 + a known header and the format is RGBA_8888 (1)."""
    if len(data) < 16:
        return None
    w, h, fmt = struct.unpack_from('<III', data, 0)
    hdr = len(data) - w * h * 4
    if fmt != 1 or hdr not in RAW_HEADERS or not (0 < w <= 8192 and 0 < h <= 8192):
        return None
    return Image.frombytes('RGBA', (w, h), data[hdr:]).convert('RGB')


def shot(name: str) -> Image.Image:
    path = TMP / f'{name}.png'
    TMP.mkdir(parents=True, exist_ok=True)
    # T76 fast path: raw RGBA (no PNG encode on the device). LIVE: header size /
    # format on this BlueStacks. Anything unexpected -> the PNG path below.
    try:
        p = subprocess.run([str(ADB), '-s', SERIAL, 'exec-out', 'screencap'],
                           capture_output=True, timeout=60)
        img = _raw_to_image(p.stdout) if p.returncode == 0 else None
    except (subprocess.SubprocessError, OSError, ValueError):
        img = None
    if img is not None:
        img.save(path, compress_level=1)    # OCR / region crops read the file
        return img
    with open(path, 'wb') as fh:
        p = subprocess.run([str(ADB), '-s', SERIAL, 'exec-out', 'screencap', '-p'],
                           stdout=fh, timeout=60)
    if p.returncode != 0:
        raise RuntimeError('screencap failed')
    im = Image.open(path)
    try:
        im.load()
        out = im.convert('RGB')
    finally:
        im.close()   # also on a failed convert (fd leak on the error path)
    return out


def avg(img: Image.Image, xy: tuple[int, int], r: int = 9) -> tuple[int, int, int]:
    x, y = xy
    px = img.crop((x - r, y - r, x + r, y + r)).resize((1, 1), Image.Resampling.BILINEAR).getpixel((0, 0))
    return (int(px[0]), int(px[1]), int(px[2]))


def close_to(c: tuple[int, int, int], ref: tuple[int, int, int], tol: int) -> bool:
    return all(abs(a - b) <= tol for a, b in zip(c, ref))


def lum(c: tuple[int, int, int]) -> float:
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


CONFIRM_CANCEL = (1014, 710)     # inside the X circle for both button rows below
CONFIRM_ROWS = (710, 729)        # the dialog's button row sits at either y (measured)


def is_confirm_dialog(img: Image.Image) -> bool:
    """Cream-band confirm dialog: X = cancel, green check = confirm.

    One layout for 'Spend <diamonds> to purchase ...?' (arena attempts,
    screens/arena_debug1.png) and 'Turn off Auto Battle mode?' (stage push).
    Must always be CANCELLED (CONFIRM_CANCEL), never confirmed. The full-width
    cream band is required: the arena Select Opponent screen matched a bare
    X/check probe pair (white card + green swords button, shots/arena_p1_pre)."""
    if not all(lum(avg(img, p)) > 200 for p in ((200, 550), (1720, 550), (960, 450))):
        return False
    for y in CONFIRM_ROWS:
        ok = avg(img, (1142, y))
        if lum(avg(img, (1014, y))) > 140 and ok[1] > ok[0] + 20 and ok[1] > ok[2] + 20:
            return True
    return False


BATTLE_MODES_BTN = (890, 1060)   # bottom-nav Battle Modes entry (UI-fixed)


def is_battle_modes(img: Image.Image) -> bool:
    """Battle Modes menu open: bright cream body + bright tab bar, plus the
    menu's own tab icons — orange Routines (500,920) ~(173,85,46) and the dark
    Events icon (1160,940) L~102. Body + tab bar alone also matched the main
    menu, Victory/Defeat/Battle-Ended cards and loading tips (review F6; 25 of
    25 captured menu frames carry both icons, no other frame does)."""
    routines = avg(img, (500, 920))
    return (lum(avg(img, (480, 270))) > 200
            and lum(avg(img, (890, 934))) > 200
            and routines[0] > routines[2] + 80
            and lum(avg(img, (1160, 940))) < 150)


def reach_world(max_steps: int = 6) -> bool:
    """Tap BACK until the verified world view is up."""
    for i in range(max_steps):
        img = shot(f'rw_{i}')
        if classify(img) == 'WORLD':
            return True
        tap(BACK, 1.5)
    return classify(shot('rw_final')) == 'WORLD'


def open_battle_modes(max_steps: int = 4) -> bool:
    """From the world view, open the Battle Modes menu and verify it."""
    if not reach_world():
        return False
    tap(GROUND, 0.8)               # dismiss any interact menu first
    for i in range(max_steps):
        img = shot(f'bm_{i}')
        if is_battle_modes(img):
            return True
        tap(BATTLE_MODES_BTN, 3.0)
    return is_battle_modes(shot('bm_final'))


def idle_seconds() -> float | None:
    """Seconds since the last keyboard/mouse input (Windows). None if unknown.

    Scheduled runs use this so the bot never hijacks the screen while Sergej is
    actually using the PC (playing manually, working)."""
    if sys.platform != 'win32':
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [('cbSize', wintypes.UINT), ('dwTime', wintypes.DWORD)]

        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            return None
        get_tick = ctypes.windll.kernel32.GetTickCount
        get_tick.restype = ctypes.c_uint32   # default c_long goes negative after ~24.8 d uptime
        return tick_delta(get_tick(), lii.dwTime) / 1000.0
    except Exception:
        return None


def prune_shot_dirs(root: Path = REPO / '.spectre', keep: int = 30,
                    trash_max_age_days: float = 14) -> int:
    """Move all but the newest `keep` shots-<pid> dirs into <root>/trash/.

    Every run writes a per-pid dir and nothing cleaned them up (1.3 GB in 104
    dirs by 2026-11-03). Moved first (frames stay usable for the manifest
    fallback); trash entries older than `trash_max_age_days` are then deleted
    so disk is actually reclaimed without hand-emptying. This run's own dir is
    never touched. Returns the number of dirs moved."""
    trash = root / 'trash'
    try:
        dirs = sorted((d for d in root.glob('shots-*') if d.is_dir() and d != TMP),
                      key=lambda d: d.stat().st_mtime, reverse=True)
        old = dirs[keep:]
        if old:
            trash.mkdir(exist_ok=True)
    except OSError:
        return 0
    cutoff = time.time() - trash_max_age_days * 86400
    try:
        for t in trash.glob('shots-*'):    # aged trash leaves the disk for good
            if t.is_dir() and t.stat().st_mtime < cutoff:
                shutil.rmtree(t, ignore_errors=True)
    except OSError:
        pass
    moved = 0
    for d in old:
        dest = trash / d.name
        n = 1
        while dest.exists():               # pids repeat across reboots
            dest = trash / f'{d.name}.{n}'
            n += 1
        try:
            d.rename(dest)
            moved += 1
        except OSError:
            pass                           # in use / locked: try again next run
    return moved


METRICS = REPO / '.spectre' / 'metrics' / 'battles.jsonl'


def append_metric(rec: dict, path: Path | None = None) -> bool:
    """Append one JSON line to the metrics log (default METRICS).

    One os.write() on an O_APPEND descriptor: concurrent runs never interleave
    partial lines. 'ts' (UTC ISO) is added when missing. Never raises — a
    metric must not break a run; returns False when the write failed."""
    path = Path(path or METRICS)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        rec = {'ts': datetime.now(timezone.utc).isoformat(timespec='seconds'), **rec}
        line = (json.dumps(rec, ensure_ascii=False) + '\n').encode('utf-8')
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, 'O_BINARY', 0), 0o644)
        try:
            os.write(fd, line)
        finally:
            os.close(fd)
        return True
    except (OSError, TypeError, ValueError):
        return False


def battle_metric(mode: str, result: str, wall_s: float, stage: int | None = None) -> str:
    """Record one battle {mode, stage, result, wall_s}; returns 'wall=NN.Ns'
    for the driver's log line (T61: wall-time baseline for speed experiments)."""
    append_metric({'mode': mode, 'stage': stage, 'result': result, 'wall_s': round(wall_s, 1)})
    return f'wall={wall_s:.1f}s'


def wall_summary(mode: str, walls: list[float]) -> str:
    """One-line per-run summary of the recorded battle wall times."""
    if not walls:
        return f'    metrics[{mode}]: no timed battles'
    return (f'    metrics[{mode}]: {len(walls)} battle(s), wall mean '
            f'{sum(walls) / len(walls):.1f}s (min {min(walls):.1f}s, max {max(walls):.1f}s)')


def tick_delta(tick: int, last: int) -> int:
    """Milliseconds from `last` to `tick` on the 32-bit tick counter, wrap-safe
    (the counter wraps every ~49.7 days; a negative idle used to SKIP every
    scheduled run as 'PC in use' until reboot)."""
    return (tick - last) & 0xFFFFFFFF


def classify(img: Image.Image) -> str:
    """Classify the screen. Thresholds use luminance/contrast, not absolute RGB,
    because AFK Journey tints the world with a day/night cycle (a night homestead
    reads (24,53,80) where the day reads (62,70,50)); the panel UI itself is not
    tinted."""
    back = avg(img, BACK)
    bg = avg(img, (BACK[0] + 90, BACK[1]))          # just right of the back arrow
    bar = avg(img, CLAIM)                            # bright only in the chest popup
    lb, lg, lbar = lum(back), lum(bg), lum(bar)

    if close_to(back, (184, 176, 174), 22) and lg > 190:
        return 'PANEL'
    # POPUP before WORLD: a dimmed popup used to satisfy the WORLD predicate
    # (|lb-lg| < 15 also matched lb-lg in (-15,-8]), which then tapped the world
    # sequence into a live popup.
    if lb < 100 and (lbar > 172 or lb - lg < -8):
        return 'POPUP'
    # WORLD also needs the world-only tell: the lit AFK Progress chip
    # (60,1036), L 103-174 on all 51 captured world frames (day + night).
    # The back-arrow probes alone said WORLD on 110 non-world frames —
    # battles, Battle Modes, a store bundle popup, a 'Use Diamond' dialog —
    # and on dimmed popups one luminance point from the POPUP cliff (review
    # F7). Without the chip the frame stays UNKNOWN: no taps.
    if lb < 100 and abs(lb - lg) < 8 and lum(avg(img, AFK_PROGRESS)) > 100:
        return 'WORLD'
    chip = avg(img, (1390, 704))
    # only trust the chip fallback when the back arrow is clearly NOT dimmed
    if lb > 140 and chip[0] > 200 and chip[1] > 150 and chip[2] < 120:
        return 'PANEL'
    return 'UNKNOWN'


def claim_round(tag: str, dry_run: bool = False) -> int:
    """One verified AFK-chest claim from wherever the game is: world -> AFK
    panel -> chest popup -> Claim -> panel (BACK). Shared by main() and
    afk_dailies. Returns main()'s exit codes: 0 claim verified (or dry-run
    reached its stop), 1 unreachable/unknown screen, 4 nothing claimable."""
    state = classify(shot(f'{tag}_0_initial'))
    print(f'    initial state: {state}', flush=True)

    if state == 'WORLD':
        if dry_run:
            print('    [dry-run] would tap AFK progress', flush=True)
            return 0
        tap_seq([(*GROUND, 0.8), (*AFK_PROGRESS, 3.0)], tolerate=False)   # T75: 1 round trip
        state = classify(shot(f'{tag}_1_panel'))
        print(f'    after AFK tap: {state}', flush=True)
    if state == 'POPUP':
        # known login popup (free monthly/daily rewards) gets claimed,
        # anything else is closed and retried from the panel
        if resolve_startup_popup(f'{tag}_1a_popup'):
            state = classify(shot(f'{tag}_1b_recover'))
        else:
            tap(BACK, 1.5)
            state = classify(shot(f'{tag}_1b_recover'))
        print(f'    after close: {state}', flush=True)
    if state == 'UNKNOWN':
        # never fire the recovery taps on an unidentified screen: that is
        # how a blind tap ends up on a store/purchase dialog
        print('    ERROR: unknown screen — refusing to tap blind', flush=True)
        return 1
    if state != 'PANEL':
        # classify-gated way back (BACK on the world view opens the exit
        # confirm, a second blind BACK can punch through two layers)
        if not reach_world():
            print('    ERROR: could not get back to the world view', flush=True)
            return 1
        tap_seq([(*GROUND, 0.8), (*AFK_PROGRESS, 3.0)], tolerate=False)   # T75: 1 round trip
        state = classify(shot(f'{tag}_2_retry'))
        print(f'    retry state: {state}', flush=True)
    if state != 'PANEL':
        print('    ERROR: could not reach the AFK panel', flush=True)
        return 1
    if dry_run:
        print('    [dry-run] panel reached, would open chest + claim', flush=True)
        return 0

    tap(CHEST, 2.2)
    state = classify(shot(f'{tag}_3_chest'))
    print(f'    after chest tap: {state}', flush=True)
    if state != 'POPUP':
        # The game does not open the info popup when almost nothing has
        # accrued (< ~2 min). One retry, then report "nothing claimable"
        # instead of a hard error — nothing was tapped wrongly.
        tap(CHEST, 2.5)
        state = classify(shot(f'{tag}_3b_chest_retry'))
        print(f'    chest retry: {state}', flush=True)
    if state != 'POPUP':
        print('    SKIP: nothing claimable yet (chest accrual too small)', flush=True)
        return 4

    tap(CLAIM, 2.5)
    state = classify(shot(f'{tag}_4_after'))
    print(f'    after claim: {state}', flush=True)
    if state == 'POPUP':
        # the claim popup can persist past the tap (T38 #8): retry once,
        # then fail loudly instead of reporting a claim that never landed
        print('    claim popup still open, retrying claim', flush=True)
        tap(CLAIM, 2.5)
        state = classify(shot(f'{tag}_4b_retry'))
        print(f'    after claim retry: {state}', flush=True)
    if state == 'PANEL':
        tap(BACK, 1.0)
        print('    claim verified (popup closed, panel back)', flush=True)
    else:
        print(f'    ERROR: unexpected state after claim: {state}', flush=True)
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--rounds', type=int, default=1)
    ap.add_argument('--pause', type=float, default=0)
    ap.add_argument('--pid', default=None, help='game pid (memory preflight)')
    ap.add_argument('--base', default=None, help='hot-heap base hex (memory preflight)')
    ap.add_argument('--min-idle', type=float, default=0,
                    help='skip unless the PC has been idle this many seconds (scheduled runs)')
    ap.add_argument('--dry-run', action='store_true',
                    help='no chest/claim tap; a popup on screen is still closed '
                         '(BACK, or the login-popup claim)')
    args = ap.parse_args()

    if not args.dry_run:
        moved = prune_shot_dirs()
        if moved:
            print(f'    moved {moved} old shot dirs to .spectre/trash/', flush=True)

    if args.min_idle > 0 and not args.dry_run:
        idle = idle_seconds()
        if idle is None:
            print('    WARN: idle time unavailable, continuing', flush=True)
        elif idle < args.min_idle:
            print(f'    SKIP: PC is in use (idle {idle:.0f}s < {args.min_idle:.0f}s)', flush=True)
            return 5
        else:
            print(f'    idle check ok ({idle:.0f}s)', flush=True)

    if args.pid and args.base and not args.dry_run:
        import afk_memory  # local: afk_memory imports this module at top level (circular)
        status, power = afk_memory.power(args.pid, args.base)
        if status == 'fail':
            print('    ERROR: team_power preflight could not read memory', flush=True)
            return 2
        if status == 'disabled':
            print(f'    team_power guard disabled (offset stale, read {power}) — '
                  'relying on the screen-state gates', flush=True)
        else:
            print(f'    preflight team_power = {power}', flush=True)

    for rnd in range(1, args.rounds + 1):
        print(f'--- round {rnd}/{args.rounds} {time.strftime("%H:%M:%S")}', flush=True)
        rc = claim_round(f'r{rnd}', args.dry_run)
        if rc:
            return rc
        if rnd < args.rounds and args.pause:
            time.sleep(args.pause)
    print('done', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
