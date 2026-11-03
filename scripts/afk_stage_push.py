"""AFK stage push: fight stage after stage, verified by screen state.

Each victory raises AFK Progress by one stage and permanently increases the AFK
income rate. Battles are free (no attempts, no resources), they just take ~90 s
of what looks like auto-combat, so this loop is safe to run while idle.

Flow: PREP/VICTORY (green Battle button at (1280,1000)) -> BATTLE -> VICTORY ->
repeat. Stops on DEFEAT (stage too hard) or when the requested count is reached,
and always leaves the game on the result screen (no stray taps).

Usage: python scripts/afk_stage_push.py [--battles N] [--max-battle-seconds 150]
Exit codes: 0 finished/pushed, 1 stuck (unknown screen), 2 memory preflight
or adb down (5 screenshots in a row failed), 3 game crashed (BlueStacks launcher), 5 skipped (PC in use).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
BATTLE_BTN = (1280, 1000)
AUTO_BATTLE_BTN = (780, 1000)
SPEED_X2_BTN = (1160, 855)   # x4 is greyed out without premium; do not tap it
CARD_CLOSE = (960, 540)      # card centre closes victory + 'Auto Battle Complete' cards;
                             # (960,1000) sat on the Auto Battle pill of the prep screen (R16)
SKIP_BTN = (1220, 788)       # verified: skips the running fight instantly to PREP/RESULT
AFK_PROGRESS = (60, 1036)
WALL_LOG = REPO / ".spectre" / "wall-report.log"


def classify_battle(img) -> str:
    dark = v.lum(v.avg(img, (960, 300)))
    header = v.lum(v.avg(img, (960, 40)))
    # one probe, two meanings (runtime review R15): dark backdrop for the
    # LAUNCHER/LOADING gates (< 60 / < 45) and the bright result card (> 160)
    card = dark
    search = v.lum(v.avg(img, (960, 124)))
    # Theme-independent battle marker: the pause button is dark during a fight
    # (L~44 day and night) while prep ground is bright (L~147) and result cards
    # are very bright (L~238). The arena colour alone is unreliable — stages use
    # different day/night themes.
    pause = v.lum(v.avg(img, (549, 846)))
    # The confirm dialog ('Turn off Auto Battle mode?', 'Spend diamonds ...')
    # outranks everything: its dimmed backdrop reads as BATTLE (pause L~8-13
    # on every captured dialog), which made the auto loop tap Skip into it.
    if v.is_confirm_dialog(img):
        return 'CONFIRM'
    # The AFK panel's orange Claim chip outranks everything below: the panel
    # sits on a dark blurred backdrop that (a) v.classify() itself reads as
    # WORLD and (b) the LOADING gate matched, which starved the push loop
    # (live shots-20408: panel open, Battle button visible, stuck until abort).
    claim = v.avg(img, (1390, 704))
    if claim[0] > 200 and claim[1] > 150 and claim[2] < 110:
        return 'AFK_PANEL'
    # Cross-check with the calibrated vision classifier BEFORE any brightness
    # heuristic: the open world reads as a bright centre (card ~121-200) or a
    # dark uniform frame depending on camera/time-of-day, which made pushes
    # misclassify WORLD as DEFEAT (shots-48848) or abort UNKNOWN (shots-30140).
    # v.classify puts POPUP first, so dimmed popups never fall through here.
    # The check ALSO requires the AFK Progress chip (60,1036): the world HUD
    # is the only screen that has it (chip lum 132-173 on every true world
    # frame; night prep / battle transitions read 2-64, where v.classify's
    # dim-uniform back-arrow predicate falsely says WORLD — shots-19744).
    if v.classify(img) == 'WORLD' and v.lum(v.avg(img, AFK_PROGRESS)) > 100:
        return 'WORLD'
    if search > 200 and pause > 150 and dark < 60:
        # BlueStacks launcher: bright search field on a dark background — the
        # game crashed or was closed. Without this, a crash looked like a
        # never-ending LOADING screen. Gate measured (runtime review R3):
        # launcher search 242 / pause 196-200, live fights search 30-180 /
        # pause 0-46 — the old 'search > 120' called fights 'game crashed'.
        return 'LAUNCHER'
    if dark < 45 and header < 45:
        return 'LOADING'
    if pause < 55:
        return 'BATTLE'
    # POPUP before the bright-card branch: a reward popup over a bright
    # backdrop otherwise read as RESULT/DEFEAT (single mode counted a popup
    # as a victory; the RESULT path then taps (960,540) blind, which can land
    # on a store tile — review finding).
    # NOTE: keep this AFTER the BATTLE check — night battle frames read as
    # v.classify POPUP (verified on shots-36248 sp_auto_3/_14) and must
    # still classify as BATTLE.
    if v.classify(img) == 'POPUP':
        return 'POPUP'
    if card > 160:   # victory ~232, defeat ~183, prep arena ~82
        title = v.avg(img, (960, 60))
        return 'DEFEAT' if title[2] > title[0] + 40 else 'RESULT'
    back = v.lum(v.avg(img, v.BACK))
    if back > 150 and v.lum(v.avg(img, (549, 846))) < 110 and v.lum(v.avg(img, (780, 1000))) < 120:
        return 'STATS'
    if v.avg(img, BATTLE_BTN)[1] > 150:
        return 'PREP'
    return 'UNKNOWN'


# --- T41: wall report (OCR on the real screen, offline WinRT OCR) -------------

_ocr_warm = False


def ocr_text(png: Path) -> list[str]:
    """Run templates/ocr.ps1 (Windows.Media.Ocr) on a screenshot PNG.

    The first call of a process pays the cold PowerShell/WinRT start, so it
    gets 30 s instead of 15 s (runtime review R18: the initial auto-complete
    check could silently time out)."""
    global _ocr_warm
    timeout = 15 if _ocr_warm else 30
    _ocr_warm = True
    return v.ocr_png(png, timeout=timeout, check_rc=True)


def parse_stage(lines: list[str]) -> int | None:
    """Stage number from OCR lines like 'AFK Stage 249' / 'AFK 249'.

    Anchored so quest counters ('Complete AFK 2 quests') cannot win: 'Stage'
    lines are matched first with word boundaries, the loose 'AFK <n>' fallback
    only accepts the number at the end of the line.
    """
    for ln in lines:
        m = re.search(r"\bAFK\s*Stage\s*(\d{1,4})\b", ln, re.I)
        if m:
            return int(m.group(1))
    for ln in lines:
        m = re.search(r"\bAFK\s*(\d{1,4})\s*$", ln, re.I)
        if m:
            return int(m.group(1))
    return None


def parse_power(lines: list[str]) -> int | None:
    """Battle-Power: a 5.000..5M number near a BARE 'Battle' line.

    The prep screen prints the power well above the Battle button (WinRT OCR
    puts 'Auto Battle', 'Records', hero levels between them — verified on
    shots-38404/sp_prep.png), the AFK panel prints it right next to 'Battle'
    ('0 74451'). 'Auto Battle' lines are explicitly NOT anchors. Scan upward
    from each bare anchor so the nearest number (the button's own power)
    wins over the team power higher up. The line below the anchor is only
    tried after the eight above it; OCR punctuation ('Battle !', 'Battle .')
    still counts as a bare anchor, words after it do not ('Battle Advice')
    (runtime review R17).
    """
    for i, ln in enumerate(lines):
        if re.fullmatch(r"Battle\b\W*", ln.strip(), re.I):
            for j in [*range(i - 1, i - 9, -1), i + 1]:
                if 0 <= j < len(lines):
                    for m in re.finditer(r"(\d{1,3}(?:[.,]\d{3})+|\d{4,8})", lines[j]):
                        val = int(m.group(1).replace(",", "").replace(".", ""))
                        if 5_000 <= val <= 5_000_000:
                            return val
    return None


def is_auto_complete(lines: list[str]) -> bool:
    """The auto chain's end card ('Auto Battle Complete' / 'Tap to Close')."""
    joined = " ".join(lines).lower()
    return "auto battle complete" in joined


def is_closable_popup(lines: list[str]) -> bool:
    """Routine post-fight popups (level-up / perk / reward card) that the
    victory-card close point dismisses (runtime review R12)."""
    joined = " ".join(lines).lower()
    return "tap to close" in joined or bool(re.search(r"\b(level|perk)\b", joined))


def wall_report(reason: str, tag: str = "sp_wall_report") -> dict:
    """Screenshot -> OCR -> JSONL line in .spectre/wall-report.log.

    Never raises: a failed report must not break the push run.
    Reason vocabulary (afk-wall-dash.reason_family groups it): walls =
    '*defeat*' + 'auto_prep_stop_*'; progress = 'single_push_complete_*';
    everything else (timeouts, aborts, 'battle_N_no_victory_*') is 'other'.
    """
    rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "reason": reason, "stage": None, "power": None,
           "png": None, "ocr_ok": False, "lines": []}
    try:
        img = v.shot(tag)
        png = v.TMP / f"{tag}.png"
        rec["png"] = str(png)
        lines = ocr_text(png)
        rec["ocr_ok"] = bool(lines)
        if not lines:
            # a failed OCR run and a text-free frame are otherwise
            # indistinguishable in the JSONL
            rec["ocr_error"] = "ocr returned no text (failed or text-free frame)"
        rec["stage"] = parse_stage(lines)
        rec["power"] = parse_power(lines)
        rec["lines"] = lines[:14]
    except Exception as exc:                      # noqa: BLE001 - report must not kill the run
        rec["error"] = f"{type(exc).__name__}: {exc}"
    try:
        WALL_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(WALL_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as exc:                      # noqa: BLE001 - report must not kill the run
        rec["log_error"] = f"log write failed: {exc}"   # keep the report error (R18)
    err = "".join(f" {k}={rec[k]}" for k in ("error", "log_error") if rec.get(k))
    print(f"    wall report: {reason} stage={rec.get('stage')} "
          f"power={rec.get('power')}{err}", flush=True)
    return rec


ADB_FAIL_CAP = 5        # consecutive failed screenshots -> adb is down, exit 2
_shot_fails = 0


class AdbDown(RuntimeError):
    pass


def try_shot(name: str, backoff: float = 3.0):
    """v.shot that survives adb hiccups (runtime review R11): retries with a
    backoff and raises AdbDown after ADB_FAIL_CAP consecutive failures, which
    main() turns into exit 2 instead of a FATAL mid-chain."""
    global _shot_fails
    while True:
        try:
            img = v.shot(name)
            _shot_fails = 0
            return img
        except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
            _shot_fails += 1
            print(f'    WARN: shot failed ({exc}) [{_shot_fails}/{ADB_FAIL_CAP}]', flush=True)
            if _shot_fails >= ADB_FAIL_CAP:
                raise AdbDown(f'{_shot_fails} screenshots in a row failed') from exc
            time.sleep(backoff)


def wait_for(states: set[str], timeout: float, tag: str) -> tuple[str, object]:
    t0 = time.time()
    last = 'UNKNOWN'
    while time.time() - t0 < timeout:
        img = try_shot(tag)
        last = classify_battle(img)
        try:
            if last == 'STATS':
                v.tap(v.BACK, 1.5)
            elif last == 'CONFIRM':
                v.tap(v.CONFIRM_CANCEL, 1.5)   # cancel, never confirm
        except Exception as exc:
            print(f'    WARN: tap failed ({exc})', flush=True)
        if last in states:
            return last, img
        if last == 'LAUNCHER':          # game crashed/closed: no point waiting
            return last, img
        time.sleep(2.0)
    return last, None


def main() -> int:
    try:
        return _run()
    except AdbDown as exc:
        print(f'    ERROR: adb down — {exc}', flush=True)
        return 2


def _run() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--battles', type=int, default=1)
    ap.add_argument('--auto', action='store_true',
                    help='use the Auto Battle button (climbs stages until defeat)')
    ap.add_argument('--retry-defeats', action='store_true',
                    help='night mode: on DEFEAT tap Retry and keep pushing (for '
                         'long idle windows - the retry loop wins the wall '
                         'eventually, verified 249->252)')
    ap.add_argument('--auto-minutes', type=float, default=10)
    ap.add_argument('--max-battle-seconds', type=float, default=150)
    ap.add_argument('--pid', default=None)
    ap.add_argument('--base', default=None)
    ap.add_argument('--min-idle', type=float, default=0)
    args = ap.parse_args()

    moved = v.prune_shot_dirs()        # old shots-<pid> dirs -> .spectre/trash (R8)
    if moved:
        print(f'    moved {moved} old shot dirs to .spectre/trash/', flush=True)

    if args.min_idle > 0:
        idle = v.idle_seconds()
        if idle is not None and idle < args.min_idle:
            print(f'    SKIP: PC is in use (idle {idle:.0f}s)', flush=True)
            return 5

    if args.pid and args.base:
        status, power = v.memory_preflight(args.pid, args.base)
        if status == 'fail':
            print('    ERROR: memory preflight failed', flush=True)
            return 2
        if status == 'disabled':
            print(f'    team_power guard disabled (offset stale, read {power})', flush=True)
        else:
            print(f'    preflight team_power = {power}', flush=True)

    img = try_shot('sp_0_initial')
    st = classify_battle(img)
    print(f'    initial battle screen state: {st}', flush=True)

    if st in ('UNKNOWN', 'POPUP'):
        if is_auto_complete(ocr_text(v.TMP / 'sp_0_initial.png')):
            print('    auto battle summary card open — closing it', flush=True)
            v.tap(CARD_CLOSE, 2.5)
            img = try_shot('sp_after_close')
            st = classify_battle(img)
            print(f'    after closing summary: {st}', flush=True)
        if st == 'UNKNOWN':
            print('    ERROR: unknown screen — refusing to tap blind', flush=True)
            return 1
    if st == 'POPUP':
        # known login popup (free monthly/daily rewards) -> claim it;
        # anything else: abort (no blind dismiss, cancelling risks a buy)
        if v.resolve_startup_popup('sp_1a_popup'):
            st = classify_battle(try_shot('sp_1b_after_popup'))
            print(f'    after login popup: {st}', flush=True)
        if st == 'POPUP':
            print('    ERROR: popup on screen — aborting (no blind dismiss)', flush=True)
            return 1
    if st not in ('PREP', 'RESULT', 'DEFEAT'):
        # enter the stage screen through the AFK panel
        for _ in range(3):
            if st in ('PREP', 'RESULT', 'DEFEAT', 'POPUP'):
                break
            if st == 'WORLD':
                # NO BACK here: in the world view BACK opens the exit confirm.
                # The bottom-left AFK Progress chip opens the panel directly.
                v.tap(AFK_PROGRESS, 3.0)
                st, _ = wait_for({'PREP', 'RESULT', 'DEFEAT', 'AFK_PANEL'}, 25, 'sp_world')
                print(f'    after AFK Progress tap: {st}', flush=True)
                continue
            if st in ('BATTLE', 'LOADING'):
                st, _ = wait_for({'PREP', 'RESULT', 'DEFEAT', 'AFK_PANEL'}, args.max_battle_seconds, 'sp_wait')
                continue
            if st == 'STATS':
                v.tap(v.BACK, 1.5)
                st, _ = wait_for({'PREP', 'RESULT', 'DEFEAT', 'AFK_PANEL', 'BATTLE'}, 20, 'sp_stats')
                print(f'    stats overlay dismissed: {st}', flush=True)
                continue
            if st == 'CONFIRM':
                v.tap(v.CONFIRM_CANCEL, 2.0)         # cancel, never confirm
                st, _ = wait_for({'PREP', 'RESULT', 'DEFEAT', 'AFK_PANEL', 'BATTLE'},
                                 15, 'sp_confirm')
                print(f'    confirm dialog cancelled: {st}', flush=True)
                continue
            if st == 'AFK_PANEL':
                v.tap((960, 910), 4.0)
                st, _ = wait_for({'PREP', 'RESULT', 'DEFEAT', 'BATTLE'}, 25, 'sp_prep')
                print(f'    after AFK panel Battle: {st}', flush=True)
                continue
            if st == 'LAUNCHER':
                break                        # crash: handled below (exit 3)
            # DEFEAT / POPUP / leftover UNKNOWN: never tap fixed coords from
            # here — abort instead (review finding: blind-tap fallthrough)
            print(f'    ERROR: unhandled state {st} — refusing to tap blind', flush=True)
            return 1
    if st == 'BATTLE':
        st, _ = wait_for({'PREP', 'RESULT'}, args.max_battle_seconds, 'sp_wait2')
    if st == 'LAUNCHER':
        print('    ERROR: game crashed / not running (BlueStacks launcher) — restart the game', flush=True)
        return 3
    if st == 'DEFEAT':
        wall_report('wall_defeat_initial')
        print('    DEFEAT — stage wall reached, nothing to push', flush=True)
        return 0
    if st not in ('PREP', 'RESULT', 'DEFEAT'):
        print(f'    ERROR: not on a battle screen ({st})', flush=True)
        return 1

    wins = 0
    planned = args.battles

    if args.auto:
        if st == 'RESULT':
            # victory card of a finished chain still open: close it, then prep
            v.tap((960, 540), 2.5)
            st, _ = wait_for({'PREP', 'RESULT', 'DEFEAT'}, 20, 'sp_close_result')
            print(f'    after closing result card: {st}', flush=True)
        if st == 'AFK_PANEL':
            # the stage screen behind the closed victory card is the AFK panel
            v.tap((960, 910), 4.0)
            st, _ = wait_for({'PREP', 'RESULT', 'DEFEAT', 'BATTLE'}, 25, 'sp_prep_auto')
            print(f'    after panel Battle: {st}', flush=True)
        if st == 'DEFEAT':
            wall_report('wall_defeat_at_auto_start')
            print('    DEFEAT — stage wall reached, nothing to push', flush=True)
            return 0
        if st != 'PREP':
            print(f'    WARN: auto battle needs the prep screen (state={st})', flush=True)
            return 1
        v.tap(AUTO_BATTLE_BTN, 4.0)
        st, _ = wait_for({'BATTLE', 'LOADING'}, 12, 'sp_auto_start')
        if st == 'PREP':
            # the 12 s wait can catch the prep->battle transition frame
            # (live: 'auto battle not available' although the chain started)
            time.sleep(3)
            st = classify_battle(try_shot('sp_auto_start_recheck'))
            if st == 'BATTLE':
                print('    auto battle started (confirmed on recheck)', flush=True)
        if st in ('PREP', 'RESULT', 'DEFEAT'):
            # Auto Battle is inert after a defeat: fall through to single battles
            # instead of idling until the timeout.
            print('    auto battle not available — fighting single battles', flush=True)
            args.auto = False
            planned = max(args.battles, 3)   # floor, without rewriting the user's --battles
            st = 'PREP'
        else:
            print(f'    auto battle started ({st})', flush=True)
            if st == 'BATTLE':
                v.tap(SPEED_X2_BTN, 1.5)   # x4 is premium-locked; never tap it
                print('    2x speed enabled', flush=True)
            # Auto Battle chains the fights; each running fight is skipped
            # instantly via the Skip button (verified: 21 s remaining -> PREP).
            t0 = time.time()
            skipped = 0
            retries = 0
            unknowns = 0
            recovered = False
            while time.time() - t0 < args.auto_minutes * 60:
                if args.min_idle > 0:
                    idle = v.idle_seconds()
                    if idle is not None and idle < args.min_idle:
                        wall_report(f'auto_abort_pc_in_use_{int(time.time()-t0)}s')
                        print('    SKIP: PC is in use — aborting the auto run', flush=True)
                        return 5
                time.sleep(3)
                tag = f'sp_auto_{int(time.time()-t0)}'
                img = try_shot(tag)
                st = classify_battle(img)
                if st == 'LAUNCHER':
                    wall_report(f'auto_launcher_after_{int(time.time()-t0)}s')
                    print('    ERROR: game crashed (launcher) mid-chain — aborting', flush=True)
                    return 3
                lines = ocr_text(v.TMP / f'{tag}.png') if st in ('UNKNOWN', 'POPUP') else []
                if is_auto_complete(lines):
                    # the chain ended by itself: close the summary card and
                    # restart Auto Battle while the time window is open
                    print('    auto battle complete — closing summary, restarting', flush=True)
                    v.tap(CARD_CLOSE, 2.5)
                    st, _ = wait_for({'PREP', 'RESULT', 'DEFEAT'}, 20, 'sp_auto_restart')
                    if st == 'PREP':
                        v.tap(AUTO_BATTLE_BTN, 4.0)
                        st, _ = wait_for({'BATTLE', 'LOADING'}, 12, 'sp_auto_start2')
                        if st == 'BATTLE':
                            continue
                    if st == 'DEFEAT':
                        wall_report(f'auto_defeat_after_{int(time.time()-t0)}s')
                        print(f'    DEFEAT after {int(time.time()-t0)}s ({skipped} skipped) '
                              '— stage wall reached', flush=True)
                        break
                    continue
                if st == 'RESULT':
                    # victory card mid-chain (also the win after a night-mode
                    # retry): close it and re-arm Auto Battle while the window
                    # is open — otherwise the loop spun silently to the timeout.
                    print('    victory card mid-chain — closing, re-arming auto', flush=True)
                    v.tap((960, 540), 2.5)
                    st, _ = wait_for({'PREP', 'RESULT', 'DEFEAT', 'BATTLE'}, 20, 'sp_auto_result')
                    if st == 'PREP':
                        v.tap(AUTO_BATTLE_BTN, 4.0)
                        st, _ = wait_for({'BATTLE', 'LOADING'}, 12, 'sp_auto_rearm')
                        if st == 'BATTLE':
                            v.tap(SPEED_X2_BTN, 1.5)   # re-armed chains lose the x2 tap
                            continue
                    continue
                if st == 'BATTLE':
                    v.tap(SKIP_BTN, 1.5)   # resolve the fight instantly
                    skipped += 1
                    unknowns = 0
                elif st == 'CONFIRM':
                    v.tap(v.CONFIRM_CANCEL, 1.5)   # cancel "turn off auto battle?"
                    unknowns = 0
                elif st == 'STATS':
                    v.tap(v.BACK, 1.5)
                    unknowns = 0
                elif st == 'DEFEAT':
                    if retries == 0 or retries % 10 == 0:
                        wall_report(f'auto_defeat_after_{int(time.time()-t0)}s')
                    if args.retry_defeats:
                        if retries >= 200:
                            print(f'    DEFEAT x{retries} — retry cap reached, stopping',
                                  flush=True)
                            break
                        retries += 1
                        print(f'    DEFEAT after {int(time.time()-t0)}s ({skipped} skipped) '
                              f'- retrying (night mode, retry {retries})', flush=True)
                        v.tap((1280, 1020), 3.0)   # Retry button
                        # verify the retry engaged; a dialog may own the screen
                        st2, _ = wait_for({'BATTLE', 'PREP', 'LOADING', 'CONFIRM'}, 12, 'sp_retry')
                        if st2 == 'CONFIRM':
                            v.tap(v.CONFIRM_CANCEL, 1.5)   # cancel, never confirm
                        continue
                    print(f'    DEFEAT after {int(time.time()-t0)}s ({skipped} skipped) '
                          '— stage wall reached', flush=True)
                    break
                elif st == 'PREP':
                    # debounce: a transient prep between chained fights looks
                    # like the wall, but the chain may already be losing —
                    # confirm with a second shot before reporting.
                    time.sleep(3)
                    st2 = classify_battle(try_shot('sp_auto_confirm'))
                    if st2 == 'DEFEAT':
                        if retries == 0 or retries % 10 == 0:
                            wall_report(f'auto_defeat_after_{int(time.time()-t0)}s')
                        if args.retry_defeats:
                            if retries >= 200:
                                print(f'    DEFEAT x{retries} — retry cap reached, stopping',
                                      flush=True)
                                break
                            retries += 1
                            print('    DEFEAT confirmed - retrying (night mode)', flush=True)
                            v.tap((1280, 1020), 3.0)   # Retry button
                            st3, _ = wait_for({'BATTLE', 'PREP', 'LOADING', 'CONFIRM'},
                                              12, 'sp_retry2')
                            if st3 == 'CONFIRM':
                                v.tap(v.CONFIRM_CANCEL, 1.5)   # cancel, never confirm
                            continue
                        print(f'    DEFEAT after {int(time.time()-t0)}s ({skipped} skipped) '
                              '— stage wall reached', flush=True)
                        break
                    # only a PREP that stays PREP is the wall (runtime review
                    # R10): a re-armed chain keeps running, a dialog is
                    # cancelled, anything else gets a third look
                    if st2 in ('BATTLE', 'LOADING', 'RESULT'):
                        continue
                    if st2 == 'CONFIRM':
                        v.tap(v.CONFIRM_CANCEL, 1.5)
                        continue
                    if st2 != 'PREP':
                        time.sleep(3)
                        if classify_battle(try_shot('sp_auto_confirm2')) != 'PREP':
                            continue
                    wall_report(f'auto_prep_stop_{skipped}skipped_{int(time.time()-t0)}s')
                    print(f'    wall reached: {skipped} fights skipped in {int(time.time()-t0)}s',
                          flush=True)
                    break
                elif st == 'LOADING':
                    pass    # no information: dark night fight frames read LOADING (R3)
                else:
                    # UNKNOWN/POPUP without the summary card: tolerated briefly,
                    # but a persistent unknown screen must not spin silently.
                    if is_closable_popup(lines):
                        print('    popup (level/perk/reward) — closing via the card centre',
                              flush=True)
                        v.tap((960, 540), 2.0)
                        unknowns = 0
                        continue
                    unknowns += 1
                    if unknowns >= 15 and not recovered:
                        # one recovery before giving up: BACK, then the centre
                        print(f'    {st} persists — one BACK + centre tap before aborting',
                              flush=True)
                        v.tap(v.BACK, 1.5)
                        v.tap((960, 540), 2.0)
                        recovered, unknowns = True, 0
                        continue
                    if unknowns >= 15:
                        wall_report(f'auto_unknown_streak_{int(time.time()-t0)}s')
                        print(f'    ERROR: {st} persists ({unknowns} polls) — aborting',
                              flush=True)
                        return 1
            else:
                # leave the game clean: cancel a possibly open confirm dialog
                # (a stray skip tap can hit the auto toggle) and close the
                # auto-complete summary card, THEN report the resulting state.
                img = try_shot('sp_auto_end')
                end_st = classify_battle(img)
                if end_st == 'CONFIRM':
                    v.tap(v.CONFIRM_CANCEL, 2.0)
                    end_st = classify_battle(try_shot('sp_auto_end2'))
                elif end_st in ('UNKNOWN', 'POPUP') and is_auto_complete(ocr_text(v.TMP / 'sp_auto_end.png')):
                    v.tap(CARD_CLOSE, 2.5)
                    end_st = classify_battle(try_shot('sp_auto_end2'))
                wall_report(f'auto_timeout_{skipped}skipped_end_{end_st.lower()}')
                print(f'    still fighting after {args.auto_minutes:.0f} min ({skipped} skipped)',
                      flush=True)
            return 0

    for i in range(1, planned + 1):
        if args.min_idle > 0:
            idle = v.idle_seconds()
            if idle is not None and idle < args.min_idle:
                print('    SKIP: PC is in use — aborting the run', flush=True)
                return 5
        v.tap(BATTLE_BTN, 3.0)
        st, _ = wait_for({'BATTLE', 'LOADING', 'RESULT', 'DEFEAT'}, 25, f'sp_start_{i}')
        print(f'    battle {i}: started ({st})', flush=True)
        if st in ('PREP', 'RESULT'):
            # PREP: the Battle tap was swallowed by a transition frame;
            # RESULT: the previous card is still up (stale). One re-tap
            # before judging (review finding / runtime review R9).
            v.tap(BATTLE_BTN, 3.0)
            st, _ = wait_for({'BATTLE', 'LOADING', 'RESULT', 'DEFEAT'}, 25, f'sp_start_{i}b')
            print(f'    battle {i}: restarted ({st})', flush=True)
        fought = st in ('BATTLE', 'LOADING')
        if fought:
            st, _ = wait_for({'RESULT', 'PREP', 'DEFEAT'}, args.max_battle_seconds, f'sp_end_{i}')
        if st == 'RESULT' and not fought:
            # a result card without any battle phase is the old card, not a win
            wall_report(f'battle_{i}_stale_result')
            print(f'    battle {i}: result card without a battle phase — not counted, '
                  'stopping', flush=True)
            break
        if st == 'RESULT':
            wins += 1
            print(f'    battle {i}: VICTORY (AFK progress +1)', flush=True)
        elif st == 'DEFEAT':
            wall_report(f'battle_{i}_defeat')
            print(f'    battle {i}: DEFEAT — stage wall reached, stopping', flush=True)
            break
        else:
            # neither result card nor prep after a battle: likely stall
            wall_report(f'battle_{i}_no_victory_{st.lower()}')
            print(f'    battle {i}: no victory screen ({st}) — stopping', flush=True)
            break
        time.sleep(1.5)

    if wins:
        wall_report(f'single_push_complete_{wins}of{planned}')
    print(f'    pushed {wins}/{planned} stage(s); game left on the result screen', flush=True)
    return 0


def prune_shots(keep: int = 30) -> None:
    """Keep only the newest screenshots of this run's shots dir.

    A 10-minute auto run polls every ~3 s — hundreds of MB per run if never
    pruned; scheduled runs would fill the disk over weeks.
    """
    try:
        pngs = sorted(v.TMP.glob('*.png'), key=lambda p: p.stat().st_mtime)
        for p in pngs[:-keep]:
            p.unlink()
    except OSError:
        pass


if __name__ == '__main__':
    try:
        code = main()
    except Exception as exc:                      # noqa: BLE001 - clean exit, no traceback
        print(f'    FATAL: {type(exc).__name__}: {exc}', flush=True)
        code = 1
    finally:
        prune_shots()
    sys.exit(code)
