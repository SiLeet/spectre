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

from PIL import Image, ImageChops, ImageStat

REPO = Path(__file__).resolve().parent.parent
import os
TMP = REPO / '.spectre' / f'shots-{os.getpid()}'   # per-run dir: concurrent runs must not collide
# created lazily in shot(): importing this module (--help, dry-run) must not touch the disk
ADB = Path.home() / 'AppData/Local/Android/Sdk/platform-tools/adb.exe'
SERIAL = '127.0.0.1:5555'
# T86 welcome/intro screen: place AND greeting (see intro_hint)
INTRO_PLACE = 'esperia'
INTRO_GREETINGS = ('willkommen', 'welcome')   # LIVE: 'welcome' (EN client) unverified; 'willkommen' verified shots-77952/fix_intro_0..3

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
AFK_BAR = (40, 1068)       # teal 'AFK Progress' bar under the avatar (classify's world tell)
CHEST = (975, 760)
CLAIM = (960, 602)
BACK = (474, 1010)
GROUND = (300, 250)
LOGIN_CLAIM = (960, 930)   # 'Esperia Monthly / Daily Rewards' popup Claim (verified live)
# T91 Dream Realm prep screen (hero grid in a cream panel, back + Records + one
# wide green Battle bar x 718-1652 / y 954-1042). LIVE: shots-66808/dr_f1_pre1..3,
# dr_f1_prewait1..3, dr_f1_after0_0..9, shots-80660/norm_0
DR_PREP_BAR = ((760, 1000), (1600, 1000))     # Battle bar, left + right end
DR_PREP_PLATES = ((570, 1000), (690, 1000))   # back-button plate, Records button
DR_PREP_PANEL = ((478, 700), (1656, 700))     # cream panel rim beside the hero grid (r=4)
# T94 Dream Realm boss page (probes moved here from afk_dream_realm so classify
# can name it; afk_dream_realm keeps its old names as aliases).
DR_BOSS_BAR = ((700, 1000), (1280, 1010))     # bar left end (T91 BOSS_BAR_LEFT) + right probe
DR_HERO_DETAIL = ((620, 992), (466, 1014))    # Ascend plate + back-arrow plate (A8 fund #2)
# Brown letterbox art beside the portrait panel. LIVE: 12 Necrodrakon pages
# (94,76,70) (75,55,44) (71,51,43) (76,55,45), King Croaker livecheck/now
# (90,72,64)..(72,53,42): R-B >= 24; hero level-up (livecheck/aftertap, c1;
# lights the bar probes) R-B <= -4.
DR_LETTERBOX = ((200, 540), (1720, 540), (100, 200), (1820, 900))
# Back plate on BOTH boss layouts: Necrodrakon plate x 478-586 / y 958-1043
# (now6; v.BACK sits 4 px left of it on the panel edge), King Croaker plate
# x ~430-526 with the Battle bar ~10 px right of it (livecheck/now: (535,1000)
# is that gap). LIVE: L 245-247 on all 13 boss pages + now5; not tapped live.
DR_BOSS_BACK = (502, 1005)
# Boss info card over the page (now5, Necrodrakon): cream header over a grey
# body. LIVE: header L 243 (247,242,235) both, body (91,81,80); every boss
# page reads header L <= 114 (shots-75220/r1_0_initial (33,142,180)).
DR_INFO_HEADER = ((1170, 225), (1150, 285))
DR_INFO_BODY = (1220, 550)
# T94 round-start recovery budget: taps (each on a proven state) + re-shots.
# Not counted: ONE BACK on a verified Battle Modes menu (the brief's normal
# reach_world path after the boss back, not a recovery action). Card + info
# card + boss page = 3 taps, so a transition that also needs its tap is refused.
RECOVER_BUDGET = 3
RECOVER_WAITS = 6               # black / UI-less / own-tap aftermath frames, RECOVER_WAIT s apart
RECOVER_WAIT = 2.5
# Neutral spot for the one UI-less tap: scene on now4, inert letterbox art on
# the boss page. Not the centre: that is the boss model, a tap there opens the
# info card (now5 — inferred from the operator's tap on the transition).
TRANSITION_TAP = (200, 540)
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


# --- tap modes (T97b) --------------------------------------------------------
# LIVE 2026-11-04 ~16:00: every 'input tap' dead (manual ones too), 'input keyevent 4'
# always worked. A dead tap still returns rc 0, so tap() cannot fall back by itself:
# the stall sites retry ONCE in the next mode (tap_retry) and their own screen check
# makes it sticky (tap_result). AFK_TAP_MODE picks the start mode per process.
# LIVE: 'touchscreen' may not help - 'input tap' already defaults to the touchscreen
# source on Android 9; 'sendevent' (raw evdev, bypasses InputManager) is the real
# alternative and is unverified on BlueStacks.
TAP_CHAIN = ('tap', 'touchscreen', 'sendevent')


def _env_tap_mode() -> str:
    mode = os.environ.get('AFK_TAP_MODE', 'tap')
    if mode not in TAP_CHAIN:
        print(f'    WARN: AFK_TAP_MODE={mode!r} unknown -> tap', flush=True)
        return 'tap'
    return mode


TAP_MODE = _env_tap_mode()
_TAP_DEAD: set[str] = set()   # modes whose stall retry changed nothing (this process)
_SENDEVENT = None             # discovery cache: None untried, False unavailable, else the device
SCREEN_W, SCREEN_H = 1920, 1080


def parse_getevent(text: str) -> dict | None:
    """First touch device (ABS_MT_POSITION_X and _Y) in `getevent -pl` output:
    {'path', 'x': (min, max), 'y': (min, max), 'tid', 'btn', 'slot'}, else None."""
    import re
    dev = None
    for line in text.splitlines():
        if m := re.match(r'add device \d+: (\S+)', line):
            if dev and 'x' in dev and 'y' in dev:
                return dev
            dev = {'path': m[1], 'tid': False, 'btn': False, 'slot': False}
        elif dev is not None:
            if m := re.search(r'ABS_MT_POSITION_([XY])\s*:.*?min (-?\d+), max (-?\d+)', line):
                dev[m[1].lower()] = (int(m[2]), int(m[3]))
            dev['tid'] |= 'ABS_MT_TRACKING_ID' in line
            dev['btn'] |= 'BTN_TOUCH' in line
            dev['slot'] |= 'ABS_MT_SLOT' in line
    return dev if dev and 'x' in dev and 'y' in dev else None


def sendevent_cmds(dev: dict, x: int, y: int, ms: int = 0) -> list[str]:
    """A tap (ms > 0: a press of ms) at screen (x, y) as raw sendevent commands,
    scaled from 1920x1080 to the device's axis ranges. With ABS_MT_TRACKING_ID:
    MT protocol B, else protocol A (SYN_MT_REPORT). LIVE: unverified - axis
    orientation (BlueStacks landscape) and whether the game needs PRESSURE/TOUCH_MAJOR."""
    def ev(typ, code, val):
        return f'sendevent {dev["path"]} {typ} {code} {val}'

    def scale(c, n, rng):
        return rng[0] + round(c * (rng[1] - rng[0]) / (n - 1))
    pos = [ev(3, 53, scale(x, SCREEN_W, dev['x'])), ev(3, 54, scale(y, SCREEN_H, dev['y']))]
    btn = [ev(1, 330, 1)] if dev['btn'] else []
    btn_up = [ev(1, 330, 0)] if dev['btn'] else []
    if dev['tid']:      # protocol B: slot 0, tracking id 1 down, -1 up
        slot = [ev(3, 47, 0)] if dev['slot'] else []
        down = [*slot, ev(3, 57, 1), *pos, *btn, ev(0, 0, 0)]
        up = [*slot, ev(3, 57, -1), *btn_up, ev(0, 0, 0)]
    else:               # protocol A: SYN_MT_REPORT per contact, an empty one on release
        down = [*pos, ev(0, 2, 0), *btn, ev(0, 0, 0)]
        up = [ev(0, 2, 0), *btn_up, ev(0, 0, 0)]
    return down + ([f'sleep {ms / 1000:g}'] if ms else []) + up


def sendevent_device() -> dict | None:
    """One-time discovery for TAP_MODE 'sendevent': `getevent -pl` -> touch device,
    plus the T85 speed-profile root check (`su -c id` -> uid=0: sendevent runs under su).
    None = unavailable (logged once): the tap chain stops before 'sendevent'.
    LIVE: unverified - that getevent -pl exits by itself and that shell (group
    input) may write /dev/input without root on BlueStacks."""
    global _SENDEVENT
    if _SENDEVENT is None:
        _SENDEVENT = False
        try:
            p = adb('shell', 'getevent -pl', timeout=10)
            dev = parse_getevent(p.stdout.decode(errors='replace')) if p.returncode == 0 else None
            if dev:
                dev['root'] = 'uid=0' in adb('shell', 'su -c id', timeout=10).stdout.decode(errors='replace')
                _SENDEVENT = dev
        except (OSError, subprocess.SubprocessError) as exc:
            print(f'    sendevent discovery failed: {exc}', flush=True)
        print(f'    sendevent device: {_SENDEVENT or "unavailable (tap chain stops here)"}', flush=True)
    return _SENDEVENT or None


def _tap_cmd(x: int, y: int, ms: int = 0, mode: str | None = None) -> str:
    """The ONE place that builds a tap's device command line (ms > 0: a press)."""
    mode = mode or TAP_MODE
    x, y = int(x), int(y)
    if mode == 'sendevent' and (dev := sendevent_device()):
        line = ' && '.join(sendevent_cmds(dev, x, y, ms))
        return f'su -c "{line}"' if dev['root'] else line
    src = 'input touchscreen' if mode == 'touchscreen' else 'input'
    return f'{src} swipe {x} {y} {x} {y} {ms}' if ms else f'{src} tap {x} {y}'


def _press(xy, ms: int, wait: float, mode: str | None, what: str) -> None:
    # adb joins shell argv with ' ' (no re-quoting), so split == the same device line;
    # 'tap' mode keeps the exact pre-T97b argv `adb -s SERIAL shell input tap X Y`
    p = adb('shell', *_tap_cmd(xy[0], xy[1], ms, mode).split())
    if p.returncode != 0:
        raise RuntimeError(f'adb {what} failed at {xy}: {p.stderr[:120]!r}')
    time.sleep(wait)


def tap(xy: tuple[int, int], wait: float = 1.0, mode: str | None = None) -> None:
    _press(xy, 0, wait, mode, 'tap')


def tap_retry(xy: tuple[int, int], wait: float = 1.0) -> str | None:
    """T97b stall stage 1: the ONE retry of a tap that left the screen unchanged, in
    the next TAP_CHAIN mode after TAP_MODE not yet dead in this process ('sendevent'
    only if discovery finds a device). Returns that mode - the caller reports its
    own screen check via tap_result(). Chain exhausted: T97's hold-tap, None."""
    nxt = next((m for m in TAP_CHAIN[TAP_CHAIN.index(TAP_MODE) + 1:]
                if m not in _TAP_DEAD and (m != 'sendevent' or sendevent_device())), None)
    if nxt is None:
        tap_hold(xy, wait=wait)
        return None
    print(f'    tap retry at {xy} via {nxt}', flush=True)
    try:
        tap(xy, wait, mode=nxt)
    except RuntimeError as exc:     # e.g. sendevent without write access to /dev/input
        _TAP_DEAD.add(nxt)
        print(f'    tap mode {nxt} failed: {exc} -> hold-tap', flush=True)
        tap_hold(xy, wait=wait)
        return None
    return nxt


def tap_result(mode: str | None, changed: bool) -> None:
    """The stall site's verdict on tap_retry(): screen changed -> `mode` sticks for
    the rest of the process, else it is dead and the next stall tries the one after."""
    global TAP_MODE
    if mode is None:
        return
    if changed:
        TAP_MODE = mode
        print(f'    TAP_MODE -> {mode} (taps were dead)', flush=True)
    else:
        _TAP_DEAD.add(mode)
        print(f'    tap mode {mode}: no effect either', flush=True)


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
    return _run_seq([_tap_cmd(x, y) for x, y, _ in steps],
                    [w for _, _, w in steps], tolerate, dry)


def key_seq(steps, tolerate: bool = True, dry: bool = False):
    """Several keyevents in ONE adb round trip; steps: [(keycode, wait_s), ...]."""
    return _run_seq([f'input keyevent {int(k)}' for k, _ in steps],
                    [w for _, w in steps], tolerate, dry)


def back(wait: float = 1.5) -> None:
    """T97: Android BACK (keyevent 4) instead of a tap on an on-screen back arrow.
    LIVE 2026-11-04: came through every time on arena select -> lobby -> world while
    taps there were dead. NEVER on the world view (opens the exit confirm): callers
    fire it only on a frame classify()/a detector just read as non-WORLD."""
    key_seq([(4, wait)], tolerate=False)


def tap_hold(xy: tuple[int, int], ms: int = 120, wait: float = 1.0) -> None:
    """T97: a short press ('input swipe x y x y ms') for the ONE retry after a tap
    left the screen unchanged (Unity UIs can drop zero-duration taps).
    LIVE: unverified. Retries only — normal taps stay tap(). T97b: in TAP_MODE."""
    _press(xy, ms, wait, None, 'hold-tap')


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
    menu's own tab icons — orange Routines (500,900) and the dark Events icon
    (1300,940). Body + tab bar alone also matched the main menu, Victory/
    Defeat/Battle-Ended cards and loading tips (review F6). LIVE 2026-11-04
    re-calibrated: the tab row sits ~26 px lower and the Events icon moved
    right (was (890,934)/(1160,940)); verified 3/3 true on the live menu
    frames, 0 false positives on all 199 captured frames."""
    routines = avg(img, (500, 900))
    return (lum(avg(img, (480, 270))) > 200
            and lum(avg(img, (890, 960))) > 190
            and routines[0] > routines[1] + 60 and routines[0] > routines[2] + 80
            and lum(avg(img, (1300, 940))) < 150)


def is_dr_prep(img: Image.Image) -> bool:
    """Dream Realm prep screen (T91, live 2026-11-04): it classified UNKNOWN,
    so normalize could not leave it and the dream driver never tapped its
    Battle bar. Green bar at both ends + cream back/Records plates + the cream
    panel rim left and right of the hero grid. LIVE (all 245 1920x1080 frames
    in .spectre): prep bar G-max >=55, plates L 249, rim L 242. Best non-prep
    frame with the other two tells lit: bar -5 (AFK panel / menu), plates 59.5
    (shots-readonly-1226xx), rim 72.5 (arena lobby: same back+button+bar row).
    The boss page fails Records (green bar, L 132) and the left rim (L 12)."""
    gmax = lambda c: c[1] - max(c[0], c[2])
    return (all(gmax(avg(img, p)) > 35 for p in DR_PREP_BAR)
            and all(lum(avg(img, p)) > 200 for p in DR_PREP_PLATES)
            and all(lum(avg(img, p, r=4)) > 200 for p in DR_PREP_PANEL))


def dr_green(c: tuple[int, int, int]) -> bool:
    # boss-page Battle button ~(109,154,100), prep Battle button ~(160,192,152);
    # the in-fight olive probes (129,143,88)/(167,178,96) must NOT match
    return c[1] > 130 and c[1] > c[0] + 25 and c[2] < 170


def is_dr_hero_detail(img: Image.Image) -> bool:
    """Hero-detail screen (A8 live fund #2, shots-62080/dr_f1_pre3 +
    shots-65076/hl_daily_post): the full-width green 'Level Up' bar lights
    BOTH battle probes, so is_boss_page used to match and start_fight fired
    BOSS_TAP onto the Level-Up button. Both the Ascend badge plate and the
    back-arrow plate are bright cream here (~(222,216,211) / (217,211,207))
    while the real boss page reads dark/blue at both spots (King Croaker,
    shots-77148/readonly-state-1513: ~(25,49,118) / (87,150,199)). A bright
    boss-page background would be gated too — that fails SAFE (clean abort,
    no chance consumed), never into wrong taps."""
    return all(lum(avg(img, p)) > 190 for p in DR_HERO_DETAIL)


def is_dr_boss_bar(img: Image.Image) -> bool:
    """Boss page (afk_dream_realm.is_boss_page): the Battle button is a
    FULL-WIDTH green bar, so the left AND the right probe both read green
    (T91: the left probe replaces the centre one, which sits on the dark
    'Chances' label). Neither prep layout lights the left probe (old: SKIP in
    the centre; new: the cream Records button), so a prep never classifies as
    boss page. The hero detail matches the green signature too — excluded
    explicitly (A8 live fund #2); the Arena lobby carried the same false
    positive (shots-59516/arena_1_lobby) — T91: its Formation plate leaves
    the left probe un-green. T94: the hero level-up screen still matches
    (livecheck/aftertap, c1) — classify uses is_dr_boss."""
    if is_dr_hero_detail(img):
        return False
    return all(dr_green(avg(img, p)) for p in DR_BOSS_BAR)


def is_dr_boss(img: Image.Image) -> bool:
    """T94: the boss page as classify sees it — green bar + brown letterbox +
    the back plate under DR_BOSS_BACK (also true under the info card)."""
    return (is_dr_boss_bar(img)
            and all(c[0] - c[2] > 12 and 40 < lum(c) < 110
                    for c in (avg(img, p) for p in DR_LETTERBOX))
            and lum(avg(img, DR_BOSS_BACK)) > 200)


def is_dr_info(img: Image.Image) -> bool:
    """T94: the boss info card (tap on the boss model) is up."""
    return (all(lum(avg(img, p)) > 200 for p in DR_INFO_HEADER)
            and lum(avg(img, DR_INFO_BODY)) < 150)


def is_ui_less(img: Image.Image) -> bool:
    """T94 UI-less transition (night/aurora scene, no HUD, no card, no button;
    Battle-Ended card -> boss page, now4). LIVE over all 285 1920x1080 frames
    (480x270 box): now4 white 0, L 35.4, B-R 43.0 — the only match. Nearest
    misses: shots-80660/norm_1 (letterboxed boss mid-load) B-R 19.4,
    shots-69680/norm_2 (fight intro) white 4 + L 77.5, black frames L 0,
    'Loading...' white >= 82."""
    sm = img.resize((480, 270), Image.Resampling.BOX)
    r, g, b = sm.split()
    white = sum(ImageChops.darker(ImageChops.darker(r, g), b).histogram()[201:])
    mean = tuple(ImageStat.Stat(sm).mean)
    return white == 0 and 20 < lum(mean) < 60 and mean[2] - mean[0] > 30


def recover_leftover(tag: str, img: Image.Image, name: str,
                     budget: int = RECOVER_BUDGET) -> tuple[str, str]:
    """T94: bounded, state-proven way out of Dream Realm leftovers at a round
    start (result card / Victory Rewards -> CARD_CLOSE, boss page or its info
    card / prep -> BACK). At most `budget` taps, plus one
    uncounted BACK on a verified Battle Modes menu; black / UI-less frames (and
    any unknown frame after one of its own taps or waits) are waited out, a
    UI-less frame still up after a wait gets ONE neutral tap (counted). Returns (state, name of the last shot); the
    name is unchanged when the frame was none of these (nothing done).
    T96: arena leftovers (select / detail / lobby) get one counted BACK per
    screen kind. T97: every back-arrow step (boss page, prep, arena, Battle
    Modes) is a keyevent BACK (back()); an arena screen still UNCHANGED after its
    BACK (ar.unchanged) gets ONE more (counted), any other repeat is waited out."""
    import afk_dream_realm as dr    # lazy: both import this module
    import afk_arena as ar          # lazy: afk_arena imports this module
    taps = waits = 0
    prev_ui_less = ui_tapped = modes = False
    arena: dict = {}                # kind -> signature its BACK fired on (None: BACKed twice)
    while True:
        st = classify(img)
        if st in ('WORLD', 'PANEL'):
            return st, name
        ui_less = st == 'UNKNOWN' and is_ui_less(img)
        kind = ('select' if ar.is_select(img) else 'detail' if ar.is_detail(img)
                else 'lobby' if ar.is_lobby(img) else '')
        if dr.is_battle_ended(img) or dr.is_victory_rewards(img):
            what, xy = 'Dream Realm result screen -> tap to close', dr.CARD_CLOSE
        elif is_dr_boss(img):
            what, xy = f'Dream Realm boss page ({st}) -> BACK', None
        elif st == 'DR_PREP':
            what, xy = 'Dream Realm prep -> BACK', None
        elif kind and (kind not in arena or (arena[kind] and ar.unchanged(arena[kind], img))):
            what, xy = (f'arena {kind} ({st}) -> BACK' if kind not in arena
                        else f'arena {kind} ({st}) unchanged -> one more BACK'), None
            arena[kind] = None if kind in arena else ar.screen_signature(img)
        elif is_battle_modes(img):
            if modes:
                return st, name         # the one BACK did not leave it
            modes, prev_ui_less = True, False
            print('    recovery: Battle Modes menu -> BACK (outside the budget)', flush=True)
            back(2.5)
            name = f'{tag}_0m'
            img = shot(name)
            continue
        elif ui_less and prev_ui_less and not ui_tapped and not ocr_lines(name):
            ui_tapped = True
            what, xy = 'UI-less transition persists -> one neutral tap', TRANSITION_TAP
        elif (((st == 'UNKNOWN' and (taps or waits or modes or ui_less or dr.is_uniform_dark(img)))
               or kind)             # arena repeat that changed (pressed lobby reads POPUP): mid-transition
              and waits < RECOVER_WAITS):
            waits, prev_ui_less = waits + 1, ui_less
            print(f'    recovery: transition, waiting ({waits}/{RECOVER_WAITS})', flush=True)
            time.sleep(RECOVER_WAIT)
            name = f'{tag}_0w{waits}'
            img = shot(name)
            continue
        else:
            return st, name
        if taps >= budget:
            print(f'    recovery: budget of {budget} taps used up ({what}) — no tap', flush=True)
            return st, name
        taps, prev_ui_less = taps + 1, False
        print(f'    recovery {taps}/{budget}: {what}', flush=True)
        if xy:
            tap(xy, 2.5)
        else:
            back(2.5)
        name = f'{tag}_0r{taps}'
        img = shot(name)


def reach_world(max_steps: int = 6) -> bool:
    """BACK (keyevent, T97) until the verified world view is up; each BACK only
    after classify() read the frame as non-WORLD."""
    for i in range(max_steps):
        img = shot(f'rw_{i}')
        if classify(img) == 'WORLD':
            return True
        back(1.5)
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


def is_afk_panel(img: Image.Image) -> bool:
    """Re-skinned AFK Rewards panel (no orange chip at (1390,704) any more).

    LIVE 2026-11-04 (shots-27712/r1_0_initial): back (225,219,210) on cream
    (253,250,244). Light back + cream also sit on hero hall/dailies
    (shots-13228/hl_*), so the green 'Battle' bar (107,157,97) and the green
    'AFK Rewards' badge (79,148,75) must both be lit; lb>190 excludes POPUP.
    Badge is ratio-only: lum 119 sits near any floor, but G-max 69 vs best
    non-panel 30 (all .spectre frames). shortcut: probe sits in the English
    title's green tail; a shorter title fails safe (UNKNOWN) -> re-probe then.

    T90: while the panel animates in (or with a locked '?' next stage) the
    badge and the Battle bar are not drawn yet -> second tell set, both
    stage-independent: the green chapter emblem left of the stage strip
    (513,348) and the white strip band above the nodes (y=300, both probes).
    LIVE: ONE frame, shots-58212/r1_1_panel (12:21 daily; = hermes
    after_afk_panel_frame): emblem r=8 G-max 39 (33..41 within +-12 px; r=4
    hotspot 46 drops to 31 at +-4 px, so r=8), gated non-panel <=2 (hl_*);
    band lum 255/255, gated non-panel min-of-two <=193 (hl_daily_pre0_w3)."""
    gmax = lambda c: c[1] - max(c[0], c[2])
    bar = lambda c: gmax(c) > 35 and lum(c) > 110
    if not (lum(avg(img, BACK)) > 190 and lum(avg(img, (BACK[0] + 90, BACK[1]))) > 230):
        return False
    if bar(avg(img, (800, 893))) and bar(avg(img, (1300, 893))) and gmax(avg(img, (712, 207), r=4)) > 35:
        return True
    # LIVE: shots-58212/r1_1_panel only (emblem 39 vs 2, band 255 vs 193; docstring T90)
    return (gmax(avg(img, (513, 348), r=8)) > 20
            and min(lum(avg(img, (x, 300), r=4)) for x in (800, 1200)) > 240)


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
    if is_afk_panel(img):
        return 'PANEL'
    # T94: before POPUP — the letterboxed boss page puts (474,1010) on the dark
    # panel edge next to its cream back plate, which the POPUP rule read as a
    # dimmed back arrow (now6, shots-75220). With the info card up it stays POPUP.
    if is_dr_boss(img) and not is_dr_info(img):
        return 'DR_BOSS'
    # POPUP before WORLD: a dimmed popup used to satisfy the WORLD predicate
    # (|lb-lg| < 15 also matched lb-lg in (-15,-8]), which then tapped the world
    # sequence into a live popup.
    # T89: the daytime world reads lb-lg -40..-12, so the -8 cliff only counts
    # as POPUP without the world-only tell: the teal 'AFK Progress' bar
    # (min(G,B)-R; a popup dims it). The old chip probe (60,1036) sits on the
    # avatar sprite, which changes (red cloak: livecheck/after_norm chip L 77)
    # and lit up on non-world screens (livecheck/hall_test2 L 133).
    # LIVE 2026-11-04: bar >=106 on all 57 world frames (day/night/snow; lowest
    # livecheck/after_norm, shots-40348/dg_cam_*); <=36 on every lb<100
    # non-world frame (hall_test2, shots-readonly-1226xx; r1_1a_popup family 1).
    # lbar>172 stays an unconditional POPUP (shots-60424/r1_1a_popup).
    t = avg(img, AFK_BAR, r=4)
    hud = min(t[1], t[2]) - t[0] > 80
    if lb < 100 and (lbar > 172 or (lb - lg < -8 and not hud)):
        return 'POPUP'
    # WORLD also needs that tell: the back-arrow probes alone said WORLD on 110
    # non-world frames — battles, Battle Modes, a store bundle popup, a 'Use
    # Diamond' dialog — and on dimmed popups one luminance point from the POPUP
    # cliff (review F7). Without it the frame stays UNKNOWN: no taps.
    # LIVE 2026-11-04: night-snow world reads lb-lg +14.8, +25 is the upper
    # bound; no lower bound since T89 (day world -40, see above).
    if lb < 100 and lb - lg < 25 and hud:
        return 'WORLD'
    # T91: before the chip fallback — an orange hero card can sit at (1390,704)
    if is_dr_prep(img):
        return 'DR_PREP'
    chip = avg(img, (1390, 704))
    # only trust the chip fallback when the back arrow is clearly NOT dimmed
    if lb > 140 and chip[0] > 200 and chip[1] > 150 and chip[2] < 120:
        return 'PANEL'
    return 'UNKNOWN'


def intro_hint(lines: list[str]) -> bool:
    """The season/login welcome screen ('Willkommen in Esperia!'): no world
    tells, classifies UNKNOWN — its OCR words are the only tell.

    Greeting AND 'esperia' together: a bare 'welcome'/'willkommen' also sits on
    event/returner offer pages, a bare 'esperia' on the Esperia Monthly popup."""
    low = ' '.join(lines).lower()
    return INTRO_PLACE in low and any(w in low for w in INTRO_GREETINGS)


def claim_round(tag: str, dry_run: bool = False) -> int:
    """One verified AFK-chest claim from wherever the game is: world -> AFK
    panel -> chest popup -> Claim -> panel (BACK). Shared by main() and
    afk_dailies. Returns main()'s exit codes: 0 claim verified (or dry-run
    reached its stop), 1 unreachable/unknown screen, 4 nothing claimable.
    Dry-run too spends the T94 leftover recovery taps (recover_leftover)."""
    last = f'{tag}_0_initial'          # the shot `state` was read from (intro OCR)
    img = shot(last)
    state = classify(img)
    print(f'    initial state: {state}', flush=True)
    if state not in ('WORLD', 'PANEL'):
        # T94/T96: Dream Realm + arena leftovers get <= RECOVER_BUDGET state-proven taps;
        # anything else is untouched and handled below as before
        state, now = recover_leftover(tag, img, last)
        if now != last:
            last = now
            print(f'    after leftover recovery: {state}', flush=True)
            if state not in ('WORLD', 'PANEL'):
                print('    ERROR: leftover screen not left within the budget — refusing', flush=True)
                return 1

    if state == 'WORLD':
        if dry_run:
            print('    [dry-run] would tap AFK progress', flush=True)
            return 0
        tap_seq([(*GROUND, 0.8), (*AFK_PROGRESS, 3.0)], tolerate=False)   # T75: 1 round trip
        last = f'{tag}_1_panel'
        state = classify(shot(last))
        print(f'    after AFK tap: {state}', flush=True)
    if state == 'POPUP':
        # known login popup (free monthly/daily rewards) gets claimed,
        # anything else is closed and retried from the panel
        if resolve_startup_popup(f'{tag}_1a_popup'):
            state = classify(shot(f'{tag}_1b_recover'))
        else:
            back(1.5)                   # T97: POPUP, never the world view
            state = classify(shot(f'{tag}_1b_recover'))
        last = f'{tag}_1b_recover'
        print(f'    after close: {state}', flush=True)
    if state == 'UNKNOWN' and intro_hint(ocr_lines(last)):
        # live 2026-11-04 (daily 05:10): the season/login welcome cinematic
        # classifies UNKNOWN and used to stop the daily; BACK closes it
        # (verified live). Once only — the gate below catches a second one.
        print('    welcome/intro screen — BACK', flush=True)
        tap(BACK, 2.0)
        state = classify(shot(f'{tag}_1c_intro'))
        print(f'    after intro BACK: {state}', flush=True)
    if state not in ('WORLD', 'PANEL', 'POPUP'):
        # never fire the recovery taps on an unidentified screen: that is
        # how a blind tap ends up on a store/purchase dialog (T94: also a
        # DR_PREP / DR_BOSS reached after the popup close — reach_world's
        # repeated BACK must not run into the transition behind them)
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
        back(1.0)                       # T97: verified panel -> world
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
                         '(BACK, or the login-popup claim), and Dream Realm leftovers get '
                         'up to RECOVER_BUDGET recovery taps')
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
